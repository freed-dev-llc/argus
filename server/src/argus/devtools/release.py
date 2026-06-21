"""Release / version-bump engine — manifest-driven, deterministic, testable.

The *what* lives in ``release.toml`` at the repo root (a declarative list of version
"sites"); this module is the generic *engine* that consumes it. One bump rewrites every
version reference, cuts the CHANGELOG, and (optionally) verifies the build — so an agent
or human runs ``argus-release bump X.Y.Z`` instead of re-deriving a multi-file edit.

Invariant (the "consistent" guarantee): every site declares an exact occurrence
``count``; if the file doesn't match, the bump aborts *before writing anything* rather
than silently leaving a stale reference behind.

Usage::

    argus-release current                 # print the canonical current version
    argus-release bump 0.1.6 [--dry-run]  # rewrite all sites + cut CHANGELOG
    argus-release verify                  # run lint / type / test / web build

(or ``python -m argus.devtools.release ...``)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from datetime import date as _date
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "release.toml"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


class ConsistencyError(RuntimeError):
    """A site did not match its manifest (wrong occurrence count) — the bump is aborted."""

    def __init__(self, path: str, anchor: str, expected: int, found: int) -> None:
        super().__init__(
            f"{path}: expected {expected} occurrence(s) of {anchor!r}, found {found} "
            "— manifest (release.toml) is out of sync with the file"
        )
        self.path = path
        self.anchor = anchor
        self.expected = expected
        self.found = found


# --------------------------------------------------------------------------- sites


@dataclass(frozen=True)
class LiteralSite:
    """Replace every rendering of the old version with the new one (exact-count guarded)."""

    path: str
    template: str
    count: int

    def apply(self, text: str, old: str, new: str) -> tuple[str, int]:
        old_str = self.template.format(version=old)
        new_str = self.template.format(version=new)
        found = text.count(old_str)
        if found != self.count:
            raise ConsistencyError(self.path, old_str, self.count, found)
        return text.replace(old_str, new_str), found


@dataclass(frozen=True)
class RegexSite:
    """Rewrite the named ``(?P<version>...)`` group of each match (old-version-agnostic)."""

    path: str
    regex: str
    count: int

    def apply(self, text: str, old: str, new: str) -> tuple[str, int]:
        matches = list(re.finditer(self.regex, text))
        if len(matches) != self.count:
            raise ConsistencyError(self.path, self.regex, self.count, len(matches))
        out = text
        for m in reversed(matches):  # splice from the end so offsets stay valid
            start, end = m.span("version")
            out = out[:start] + new + out[end:]
        return out, len(matches)


Site = LiteralSite | RegexSite


@dataclass(frozen=True)
class ReleaseConfig:
    repo: str
    changelog: str
    version_file: str
    sites: tuple[Site, ...]


def _parse_site(raw: dict[str, Any]) -> Site:
    path = str(raw["path"])
    count = int(raw["count"])
    if "literal" in raw:
        return LiteralSite(path, str(raw["literal"]), count)
    if "regex" in raw:
        return RegexSite(path, str(raw["regex"]), count)
    raise ValueError(f"site {path!r} must define either 'literal' or 'regex'")


def load_config(root: Path) -> ReleaseConfig:
    data = tomllib.loads((root / CONFIG_FILENAME).read_text())
    return ReleaseConfig(
        repo=str(data["repo"]),
        changelog=str(data["changelog"]),
        version_file=str(data["version_file"]),
        sites=tuple(_parse_site(s) for s in data["site"]),
    )


def find_repo_root(start: Path | None = None) -> Path:
    here = (start or Path.cwd()).resolve()
    for cand in (here, *here.parents):
        if (cand / CONFIG_FILENAME).exists():
            return cand
    raise FileNotFoundError(f"no {CONFIG_FILENAME} found in {here} or any parent")


def current_version(root: Path, cfg: ReleaseConfig) -> str:
    data = tomllib.loads((root / cfg.version_file).read_text())
    return str(data["project"]["version"])


# ----------------------------------------------------------------------- changelog


def changelog_apply(text: str, repo: str, old: str, new: str, when: str) -> tuple[str, int]:
    """Cut ``[Unreleased]`` -> ``[new] - when`` and refresh the compare links."""
    base = f"https://github.com/{repo}/compare"

    marker = "## [Unreleased]\n\n"
    if text.count(marker) != 1:
        raise ConsistencyError(repo, marker, 1, text.count(marker))
    text = text.replace(marker, f"{marker}## [{new}] - {when}\n\n", 1)

    old_link = f"[Unreleased]: {base}/v{old}...HEAD"
    if text.count(old_link) != 1:
        raise ConsistencyError("CHANGELOG.md", old_link, 1, text.count(old_link))
    new_links = f"[Unreleased]: {base}/v{new}...HEAD\n[{new}]: {base}/v{old}...v{new}"
    return text.replace(old_link, new_links, 1), 2


# ---------------------------------------------------------------------------- bump


@dataclass
class SiteChange:
    path: str
    replacements: int


@dataclass
class BumpResult:
    old: str
    new: str
    when: str
    dry_run: bool
    changes: list[SiteChange] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def bump(root: Path, new: str, *, when: str, dry_run: bool = False) -> BumpResult:
    if not SEMVER_RE.match(new):
        raise ValueError(f"{new!r} is not a valid semantic version (expected X.Y.Z)")
    cfg = load_config(root)
    old = current_version(root, cfg)
    if new == old:
        raise ValueError(f"version is already {old} — nothing to bump")

    pending: dict[str, str] = {}  # path -> new content (computed, not yet written)
    changes: list[SiteChange] = []

    def text_of(path: str) -> str:
        if path not in pending:
            pending[path] = (root / path).read_text()
        return pending[path]

    # Phase 1: compute + validate everything (raises before any write on mismatch).
    for site in cfg.sites:
        updated, n = site.apply(text_of(site.path), old, new)
        pending[site.path] = updated
        changes.append(SiteChange(site.path, n))

    cl_updated, n = changelog_apply(text_of(cfg.changelog), cfg.repo, old, new, when)
    pending[cfg.changelog] = cl_updated
    changes.append(SiteChange(cfg.changelog, n))

    # Phase 2: write (skipped on dry-run).
    if not dry_run:
        for path, content in pending.items():
            (root / path).write_text(content)

    return BumpResult(old=old, new=new, when=when, dry_run=dry_run, changes=changes)


# -------------------------------------------------------------------------- verify


@dataclass(frozen=True)
class VerifyStep:
    name: str
    cmd: list[str]
    cwd: str


def verify_steps(root: Path) -> list[VerifyStep]:
    return [
        VerifyStep("ruff", ["ruff", "check", "src", "tests"], str(root / "server")),
        VerifyStep("mypy", ["mypy", "src"], str(root / "server")),
        VerifyStep("pytest", ["pytest", "-q"], str(root / "server")),
        VerifyStep("web-build", ["npm", "run", "build"], str(root / "web")),
    ]


def run_verify(root: Path) -> int:
    rc = 0
    for step in verify_steps(root):
        print(f"\n=== {step.name}: {' '.join(step.cmd)} (cwd={step.cwd}) ===")
        result = subprocess.run(step.cmd, cwd=step.cwd)
        status = "ok" if result.returncode == 0 else f"FAILED (rc={result.returncode})"
        print(f"--- {step.name}: {status}")
        rc = rc or result.returncode
    return rc


# ----------------------------------------------------------------------------- cli


def _today() -> str:
    return os.environ.get("ARGUS_RELEASE_DATE") or _date.today().isoformat()


def _print_human(res: BumpResult) -> None:
    verb = "would bump" if res.dry_run else "bumped"
    print(f"{verb} {res.old} -> {res.new} (dated {res.when})")
    for c in res.changes:
        print(f"  {c.path}: {c.replacements}")
    if res.dry_run:
        print("(dry-run — no files written)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="argus-release", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("current", help="print the canonical current version")
    b = sub.add_parser("bump", help="rewrite every version site + cut the CHANGELOG")
    b.add_argument("version", help="the new version, e.g. 0.1.6")
    b.add_argument("--date", help="CHANGELOG date (default: today / $ARGUS_RELEASE_DATE)")
    b.add_argument("--dry-run", action="store_true", help="report changes without writing")
    b.add_argument("--json", action="store_true", help="emit the result as JSON")
    v = sub.add_parser("verify", help="run lint / type / test / web build")
    v.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    root = find_repo_root()
    cfg = load_config(root)

    if args.cmd == "current":
        print(current_version(root, cfg))
        return 0

    if args.cmd == "bump":
        try:
            res = bump(root, args.version, when=args.date or _today(), dry_run=args.dry_run)
        except (ConsistencyError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(res.to_dict(), indent=2))
        else:
            _print_human(res)
        return 0

    if args.cmd == "verify":
        return run_verify(root)

    return 2  # unreachable (subparser is required)


if __name__ == "__main__":
    raise SystemExit(main())
