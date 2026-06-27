"""Tests for the maintenance MCP tools (argus.devtools.maint_tools).

``release_verify`` is always stubbed here — these tests must NEVER actually spawn
ruff/mypy/pytest/npm (that would recurse into the suite and be slow). ``release_bump`` is
exercised against a throwaway mini-repo and asserted to write nothing (dry-run only).
"""

from __future__ import annotations

from pathlib import Path

from argus.devtools import maint_tools
from argus.devtools.release import current_version, find_repo_root, load_config

REPO_ROOT = find_repo_root(Path(__file__).parent)


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


# --- release_current -------------------------------------------------------------


async def test_release_current_reports_live_version() -> None:
    cfg = load_config(REPO_ROOT)
    out = await maint_tools.release_current()
    assert out == {"version": current_version(REPO_ROOT, cfg)}


# --- release_verify (stubbed — never spawns ruff/mypy/pytest/npm) ----------------


async def test_release_verify_structures_steps_and_aggregates_ok(monkeypatch) -> None:
    fake_steps = [
        {
            "name": "ruff", "cmd": ["ruff"], "cwd": "x", "returncode": 0,
            "ok": True, "stdout_tail": "", "stderr_tail": "",
        },
        {
            "name": "mypy", "cmd": ["mypy"], "cwd": "x", "returncode": 1,
            "ok": False, "stdout_tail": "boom", "stderr_tail": "",
        },
    ]
    monkeypatch.setattr(maint_tools, "run_verify_captured", lambda root: fake_steps)
    out = await maint_tools.release_verify()
    assert out["ok"] is False  # one step failed -> aggregate fails
    assert out["steps"] == fake_steps


async def test_release_verify_all_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        maint_tools,
        "run_verify_captured",
        lambda root: [
            {
                "name": "ruff", "cmd": [], "cwd": "x", "returncode": 0,
                "ok": True, "stdout_tail": "", "stderr_tail": "",
            }
        ],
    )
    out = await maint_tools.release_verify()
    assert out["ok"] is True


# --- release_bump (dry-run only — never writes) ----------------------------------


async def test_release_bump_previews_without_writing(tmp_path, monkeypatch) -> None:
    root = _mini_repo(tmp_path)
    monkeypatch.setattr(maint_tools, "find_repo_root", lambda: root)
    before_pyproject = (root / "pyproject.toml").read_text()
    before_changelog = (root / "CHANGELOG.md").read_text()

    out = await maint_tools.release_bump("1.1.0", date="2020-06-01")

    assert out["dry_run"] is True
    assert (out["old"], out["new"]) == ("1.0.0", "1.1.0")
    assert out["when"] == "2020-06-01"
    assert any(c["path"] == "pyproject.toml" and c["replacements"] == 1 for c in out["changes"])
    # the preview wrote nothing
    assert (root / "pyproject.toml").read_text() == before_pyproject
    assert (root / "CHANGELOG.md").read_text() == before_changelog


async def test_release_bump_bad_version_returns_error(tmp_path, monkeypatch) -> None:
    root = _mini_repo(tmp_path)
    monkeypatch.setattr(maint_tools, "find_repo_root", lambda: root)
    out = await maint_tools.release_bump("not-a-version")
    assert "error" in out
    assert "semantic version" in out["error"]
    assert (root / "pyproject.toml").read_text() == '[project]\nname = "x"\nversion = "1.0.0"\n'
