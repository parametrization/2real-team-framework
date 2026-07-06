"""Tests for require_load_bearing_test — the S2 (#167) hard pre-review gate.

Exercised entirely via check() with `_fetch_compare_files` monkeypatched (no
network) and an injected config (tmp_path/.claude/framework.config.json) for the
override tests. `--repo`/`--head` are passed explicitly on the command so repo/head
resolution never shells out to git. Stdlib + pytest only.

The load-bearing (revert->fail) property for this suite: `test_blocks_new_behavior_
without_test_file` and `test_blocks_when_diff_unverifiable` fail if the core
`check()` gate in require_load_bearing_test.py is neutered to always return None
(verified manually during development — see PR description for the revert
transcript). They are NOT tautological: each asserts a specific `"block"` decision
with reason content tied to the exact code path under test, not merely "no
exception raised".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))

import _framework_config  # noqa: E402
import require_load_bearing_test as rlbt  # noqa: E402


def _bash(command: str, *, cwd: str | None = None, env: dict | None = None) -> dict:
    d: dict = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        d["cwd"] = cwd
    if env is not None:
        d["env"] = env
    return d


def _write_config(tmp: Path, *, exceptions: dict | None = None) -> None:
    claude = tmp / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "framework.config.json").write_text(
        json.dumps(
            {
                "version": 1,
                "scm": {"provider": "github", "owner": "acme"},
                "policy": {"load_bearing_test_exceptions": exceptions or {}},
            }
        )
    )
    _framework_config.clear_cache()


_CREATE_CMD = 'gh pr create --repo acme/demo --base main --head feat --title x --body y'


def _fake_files(entries: list[dict]):
    return lambda repo, base, head: entries


def _behavior_entry(patch: str, filename: str = "framework/assets/hooks/foo.py") -> dict:
    return {"filename": filename, "status": "modified", "patch": patch}


def _test_entry(patch: str, filename: str = "framework/tests/test_foo.py") -> dict:
    return {"filename": filename, "status": "modified", "patch": patch}


_SUBSTANTIVE_PATCH = "@@ -1,2 +1,3 @@\n line1\n+def new_behavior():\n+    return 42\n"
_TRIVIAL_PATCH = "@@ -1,1 +1,3 @@\n line1\n+   \n+# just a comment\n"


# --------------------------------------------------------------- command matching


def test_non_gh_pr_create_ignored(monkeypatch) -> None:
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH)]))
    assert rlbt.check(_bash("gh pr list")) is None
    assert rlbt.check(_bash("gh pr view 5")) is None
    assert rlbt.check(_bash("git push origin feat")) is None


# --------------------------------------------------------------- core diff-substance gate


def test_no_behavior_file_allows(monkeypatch) -> None:
    monkeypatch.setattr(
        rlbt, "_fetch_compare_files", _fake_files([{"filename": "README.md", "status": "modified", "patch": "@@ -1 +1,2 @@\n-old\n+new\n"}])
    )
    assert rlbt.check(_bash(_CREATE_CMD)) is None


def test_blocks_new_behavior_without_test_file(monkeypatch) -> None:
    """The core gate: new behavior, zero test-file changes -> hard block."""
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH)]))
    r = rlbt.check(_bash(_CREATE_CMD))
    assert r is not None
    assert r["decision"] == "block"
    assert "framework/assets/hooks/foo.py" in r["reason"]
    assert "load-bearing" in r["reason"].lower()


def test_allows_when_test_file_touched_alongside(monkeypatch) -> None:
    monkeypatch.setattr(
        rlbt,
        "_fetch_compare_files",
        _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH), _test_entry(_SUBSTANTIVE_PATCH)]),
    )
    assert rlbt.check(_bash(_CREATE_CMD)) is None


def test_trivial_behavior_patch_does_not_trip_gate(monkeypatch) -> None:
    """A behavior file with only blank/comment added lines is not 'new behavior'."""
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_TRIVIAL_PATCH)]))
    assert rlbt.check(_bash(_CREATE_CMD)) is None


def test_trivial_test_patch_does_not_satisfy_gate(monkeypatch) -> None:
    """A test file touched with only blank/comment lines does not count as 'test touched'."""
    monkeypatch.setattr(
        rlbt,
        "_fetch_compare_files",
        _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH), _test_entry(_TRIVIAL_PATCH)]),
    )
    r = rlbt.check(_bash(_CREATE_CMD))
    assert r is not None and r["decision"] == "block"


def test_removed_file_ignored(monkeypatch) -> None:
    monkeypatch.setattr(
        rlbt,
        "_fetch_compare_files",
        _fake_files([{"filename": "framework/assets/hooks/foo.py", "status": "removed", "patch": _SUBSTANTIVE_PATCH}]),
    )
    assert rlbt.check(_bash(_CREATE_CMD)) is None


def test_non_python_and_out_of_scope_paths_ignored(monkeypatch) -> None:
    monkeypatch.setattr(
        rlbt,
        "_fetch_compare_files",
        _fake_files(
            [
                {"filename": "framework/assets/hooks/foo.sh", "status": "modified", "patch": _SUBSTANTIVE_PATCH},
                {"filename": "intake/candidate/foo.py", "status": "modified", "patch": _SUBSTANTIVE_PATCH},
                {"filename": "framework/assets/hooks/__init__.py", "status": "modified", "patch": _SUBSTANTIVE_PATCH},
            ]
        ),
    )
    assert rlbt.check(_bash(_CREATE_CMD)) is None


def test_conftest_and_test_dir_recognized_as_test(monkeypatch) -> None:
    monkeypatch.setattr(
        rlbt,
        "_fetch_compare_files",
        _fake_files(
            [
                _behavior_entry(_SUBSTANTIVE_PATCH),
                {"filename": "framework/tests/conftest.py", "status": "modified", "patch": _SUBSTANTIVE_PATCH},
            ]
        ),
    )
    assert rlbt.check(_bash(_CREATE_CMD)) is None


# --------------------------------------------------------------- fail-closed posture


def test_blocks_when_repo_unresolvable(tmp_path: Path) -> None:
    # tmp_path is not a git repo, so --repo-less resolution via `git remote get-url
    # origin` fails -> repo stays unresolvable -> fail-closed block.
    r = rlbt.check(_bash("gh pr create --head feat --title x --body y", cwd=str(tmp_path)))
    assert r is not None and r["decision"] == "block"
    assert "fail-closed" in r["reason"].lower()


def test_blocks_when_diff_unverifiable(monkeypatch) -> None:
    monkeypatch.setattr(rlbt, "_fetch_compare_files", lambda repo, base, head: None)
    r = rlbt.check(_bash(_CREATE_CMD))
    assert r is not None and r["decision"] == "block"
    assert "fail-closed" in r["reason"].lower()


# --------------------------------------------------------------- override


def test_override_valid_class_allows(monkeypatch, tmp_path: Path) -> None:
    _write_config(tmp_path, exceptions={"tech-debt-cleanup": "pure refactor, no behavior change"})
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH)]))
    r = rlbt.check(
        _bash(
            _CREATE_CMD,
            cwd=str(tmp_path),
            env={"LOAD_BEARING_TEST_EXCEPTION": "tech-debt-cleanup:pure refactor, no behavior change"},
        )
    )
    assert r is not None
    assert r["decision"] == "allow"
    assert "overridden" in r["systemMessage"].lower()
    _framework_config.clear_cache()


def test_override_unknown_class_blocks(monkeypatch, tmp_path: Path) -> None:
    _write_config(tmp_path, exceptions={"tech-debt-cleanup": "rationale"})
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH)]))
    r = rlbt.check(
        _bash(_CREATE_CMD, cwd=str(tmp_path), env={"LOAD_BEARING_TEST_EXCEPTION": "bogus-class:some reason"})
    )
    assert r is not None and r["decision"] == "block"
    assert "not a valid override" in r["reason"]
    _framework_config.clear_cache()


def test_override_empty_rationale_blocks(monkeypatch, tmp_path: Path) -> None:
    _write_config(tmp_path, exceptions={"tech-debt-cleanup": "rationale"})
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH)]))
    r = rlbt.check(
        _bash(_CREATE_CMD, cwd=str(tmp_path), env={"LOAD_BEARING_TEST_EXCEPTION": "tech-debt-cleanup:"})
    )
    assert r is not None and r["decision"] == "block"
    _framework_config.clear_cache()


def test_override_no_exceptions_configured_blocks(monkeypatch, tmp_path: Path) -> None:
    """Default posture (no config at all): zero classes configured -> no bypass exists."""
    _write_config(tmp_path, exceptions={})
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH)]))
    r = rlbt.check(
        _bash(_CREATE_CMD, cwd=str(tmp_path), env={"LOAD_BEARING_TEST_EXCEPTION": "anything:rationale"})
    )
    assert r is not None and r["decision"] == "block"
    assert "none configured" in r["reason"].lower()
    _framework_config.clear_cache()


# --------------------------------------------------------------- pure helpers


def test_is_behavior_path() -> None:
    assert rlbt._is_behavior_path("framework/assets/hooks/foo.py")
    assert rlbt._is_behavior_path("python/src/real_team/cli.py")
    assert not rlbt._is_behavior_path("framework/tests/test_foo.py")
    assert not rlbt._is_behavior_path("framework/assets/hooks/foo.md")
    assert not rlbt._is_behavior_path("docs/README.md")
    assert not rlbt._is_behavior_path("framework/assets/hooks/__init__.py")


def test_is_test_path() -> None:
    assert rlbt._is_test_path("framework/tests/test_foo.py")
    assert rlbt._is_test_path("python/tests/test_cli.py")
    assert rlbt._is_test_path("framework/tests/conftest.py")
    assert rlbt._is_test_path("some/dir/foo_test.py")
    assert not rlbt._is_test_path("framework/assets/hooks/foo.py")


def test_added_substantive_lines() -> None:
    assert rlbt._added_substantive_lines(_SUBSTANTIVE_PATCH) == [
        "def new_behavior():",
        "    return 42",
    ]
    assert rlbt._added_substantive_lines(_TRIVIAL_PATCH) == []
    assert rlbt._added_substantive_lines(None) == []
    assert rlbt._added_substantive_lines("") == []
