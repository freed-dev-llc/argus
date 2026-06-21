"""Tests for the manifest-driven release engine (argus.devtools.release)."""

from __future__ import annotations

from pathlib import Path

import pytest

from argus.devtools.release import (
    ConsistencyError,
    LiteralSite,
    RegexSite,
    bump,
    changelog_apply,
    current_version,
    find_repo_root,
    load_config,
    verify_steps,
)

REPO_ROOT = find_repo_root(Path(__file__).parent)


# --------------------------------------------------------------------- unit: sites


def test_literal_site_replaces_and_counts() -> None:
    site = LiteralSite("x", 'version = "{version}"', count=1)
    out, n = site.apply('version = "1.0.0"\n', "1.0.0", "1.0.1")
    assert out == 'version = "1.0.1"\n'
    assert n == 1


def test_literal_site_wrong_count_aborts() -> None:
    site = LiteralSite("x", 'version = "{version}"', count=1)
    with pytest.raises(ConsistencyError):
        site.apply("no version here", "1.0.0", "1.0.1")


def test_regex_site_rewrites_only_named_group() -> None:
    # Two root occurrences at differing indentation, plus a dependency we must not touch.
    text = (
        '{\n  "name": "argus-web",\n  "version": "1.0.0",\n'
        '  "packages": {\n    "": {\n      "name": "argus-web",\n      "version": "1.0.0",\n'
        '      "dependencies": { "deep-is": "1.0.0" }\n}}}\n'
    )
    site = RegexSite("lock", r'"name": "argus-web",\s*"version": "(?P<version>[^"]+)"', count=2)
    out, n = site.apply(text, "1.0.0", "2.0.0")
    assert n == 2
    assert out.count('"version": "2.0.0"') == 2
    assert '"deep-is": "1.0.0"' in out  # dependency version untouched


# ----------------------------------------------------------------- unit: changelog


def test_changelog_cut_inserts_section_and_links() -> None:
    text = (
        "## [Unreleased]\n\n### Added\n\n- a thing\n\n## [1.0.0] - 2020-01-01\n\n"
        "[Unreleased]: https://github.com/o/r/compare/v1.0.0...HEAD\n"
        "[1.0.0]: https://github.com/o/r/compare/v0.9.0...v1.0.0\n"
    )
    out, n = changelog_apply(text, "o/r", "1.0.0", "1.1.0", "2020-06-01")
    assert n == 2
    assert "## [1.1.0] - 2020-06-01" in out
    assert "[Unreleased]: https://github.com/o/r/compare/v1.1.0...HEAD" in out
    assert "[1.1.0]: https://github.com/o/r/compare/v1.0.0...v1.1.0" in out
    # the previously-unreleased entry now sits under the new dated section
    assert out.index("## [1.1.0]") < out.index("- a thing")


# ------------------------------------------------------------------ unit: bump e2e


def _mini_repo(tmp: Path) -> Path:
    (tmp / "release.toml").write_text(
        'repo = "o/r"\n'
        'changelog = "CHANGELOG.md"\n'
        'version_file = "pyproject.toml"\n'
        "[[site]]\n"
        'path = "pyproject.toml"\n'
        "literal = 'version = \"{version}\"'\n"
        "count = 1\n"
    )
    (tmp / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "1.0.0"\n')
    (tmp / "CHANGELOG.md").write_text(
        "## [Unreleased]\n\n### Added\n\n- x\n\n"
        "[Unreleased]: https://github.com/o/r/compare/v1.0.0...HEAD\n"
    )
    return tmp


def test_bump_writes_all_files(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    res = bump(root, "1.1.0", when="2020-06-01")
    assert (res.old, res.new) == ("1.0.0", "1.1.0")
    assert 'version = "1.1.0"' in (root / "pyproject.toml").read_text()
    assert "## [1.1.0] - 2020-06-01" in (root / "CHANGELOG.md").read_text()


def test_bump_dry_run_writes_nothing(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    before = (root / "pyproject.toml").read_text()
    res = bump(root, "1.1.0", when="2020-06-01", dry_run=True)
    assert res.dry_run is True
    assert (root / "pyproject.toml").read_text() == before  # unchanged


def test_bump_rejects_bad_version(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    with pytest.raises(ValueError):
        bump(root, "not-a-version", when="2020-06-01")


def test_bump_rejects_same_version(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    with pytest.raises(ValueError):
        bump(root, "1.0.0", when="2020-06-01")


def test_bump_aborts_without_writing_on_mismatch(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    # break a later site (the CHANGELOG marker) so phase 1 fails *after* the pyproject
    # edit is computed in memory — the all-or-nothing write must leave pyproject untouched.
    (root / "CHANGELOG.md").write_text("no unreleased section here\n")
    before = (root / "pyproject.toml").read_text()
    with pytest.raises(ConsistencyError):
        bump(root, "1.1.0", when="2020-06-01")
    assert (root / "pyproject.toml").read_text() == before  # nothing written


# ----------------------------------------------- keystone: manifest vs the real repo


def test_real_manifest_matches_repo() -> None:
    """Every site in the repo's release.toml resolves against the live files (dry-run).

    This is the consistency guard: if a managed file is reworded so a site no longer
    matches its expected count, this fails — the same failure a real bump would hit.
    """
    cfg = load_config(REPO_ROOT)
    cur = current_version(REPO_ROOT, cfg)
    major, minor, patch = (int(p) for p in cur.split("."))
    nxt = f"{major}.{minor}.{patch + 1}"
    res = bump(REPO_ROOT, nxt, when="2020-01-01", dry_run=True)
    assert res.old == cur
    # every declared site (+ the changelog) reported at least one replacement
    assert len(res.changes) == len(cfg.sites) + 1
    assert all(c.replacements >= 1 for c in res.changes)


def test_verify_steps_cover_lint_type_test_build() -> None:
    names = {s.name for s in verify_steps(REPO_ROOT)}
    assert {"ruff", "mypy", "pytest", "web-build"} <= names
