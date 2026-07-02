"""Tests for the shipped permissions allowlist in settings.template.json (#68).

Covers: the merge is idempotent (union, no duplicates, re-run no-op), user-added rules
survive a re-install, `--no-permissions` leaves the permissions block out entirely, and a
lint-style sweep asserting the template ships no absolute-path or machine-specific rule.
Stdlib + pytest only.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_BOOTSTRAP = _FRAMEWORK_ROOT / "install" / "bootstrap.py"
_TEMPLATE = _FRAMEWORK_ROOT / "assets" / "settings.template.json"


def _install(target: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_BOOTSTRAP), str(target), "--owner", "test-org", "--no-team", *extra],
        capture_output=True,
        text=True,
    )


def _settings(target: Path) -> dict:
    return json.loads((target / ".claude" / "settings.json").read_text(encoding="utf-8"))


def _template_allow() -> list[str]:
    return json.loads(_TEMPLATE.read_text(encoding="utf-8"))["permissions"]["allow"]


def test_install_ships_allowlist_and_rerun_is_noop(tmp_path: Path) -> None:
    r1 = _install(tmp_path)
    assert r1.returncode == 0, r1.stderr
    allow = _settings(tmp_path)["permissions"]["allow"]
    assert allow == _template_allow()
    assert len(allow) == len(set(allow))  # no duplicates on first write

    before = (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    r2 = _install(tmp_path)
    assert r2.returncode == 0, r2.stderr
    assert "already wired" in r2.stdout  # merge reported a no-op
    after = (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    assert after == before  # byte-identical: idempotent


def test_user_added_rules_are_preserved(tmp_path: Path) -> None:
    _install(tmp_path)
    dest = tmp_path / ".claude" / "settings.json"
    settings = json.loads(dest.read_text(encoding="utf-8"))
    settings["permissions"]["allow"].insert(0, "Bash(npm run test:*)")  # user's own rule, first
    settings["permissions"]["deny"] = ["WebFetch"]  # user's own OTHER rule list
    dest.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    r = _install(tmp_path)
    assert r.returncode == 0, r.stderr
    merged = _settings(tmp_path)["permissions"]
    assert merged["allow"][0] == "Bash(npm run test:*)"  # preserved, position untouched
    assert merged["deny"] == ["WebFetch"]  # untouched
    for rule in _template_allow():
        assert merged["allow"].count(rule) == 1  # template rules present exactly once


def test_partial_existing_allow_is_unioned_without_duplicates(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    (claude / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Read(.claude/**)", "Bash(git status)"]}}) + "\n",
        encoding="utf-8",
    )
    r = _install(tmp_path)
    assert r.returncode == 0, r.stderr
    allow = _settings(tmp_path)["permissions"]["allow"]
    assert allow.count("Read(.claude/**)") == 1  # already-present template rule not duplicated
    assert "Bash(git status)" in allow  # pre-existing user rule kept
    assert set(_template_allow()) <= set(allow)  # full template union present


def test_no_permissions_flag_leaves_permissions_absent(tmp_path: Path) -> None:
    r = _install(tmp_path, "--no-permissions")
    assert r.returncode == 0, r.stderr
    settings = _settings(tmp_path)
    assert "permissions" not in settings
    assert "PreToolUse" in settings["hooks"]  # hook wiring still merged

    # Re-run with the flag stays permission-free (no leak on re-install).
    r2 = _install(tmp_path, "--no-permissions")
    assert r2.returncode == 0, r2.stderr
    assert "permissions" not in _settings(tmp_path)


def test_no_permissions_does_not_touch_existing_user_permissions(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    (claude / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Bash(git status)"]}}) + "\n", encoding="utf-8"
    )
    r = _install(tmp_path, "--no-permissions")
    assert r.returncode == 0, r.stderr
    assert _settings(tmp_path)["permissions"]["allow"] == ["Bash(git status)"]


def test_template_rules_are_generic_relative_and_claude_scoped() -> None:
    """Lint sweep: no absolute paths, no machine/user-specific strings, no over-broad rules."""
    allow = _template_allow()
    assert allow, "template must ship a non-empty permissions.allow"
    for rule in allow:
        # No absolute or home-anchored paths (POSIX or Windows), no user-relative paths.
        assert "/home/" not in rule, rule
        assert not re.search(r"[A-Za-z]:\\", rule), rule
        assert "~" not in rule, rule
        assert not re.search(r"\((\s)*/", rule), rule  # rule content must not start at fs root
        # No machine/user/repo-specific strings from the audited global config.
        for needle in ("parameterization", "parametrization", "noorinalabs", "Users"):
            assert needle not in rule, rule
        # Minimal + justifiable: every rule is scoped to .claude/, and no bare wildcards.
        assert ".claude/" in rule, rule
        assert rule != "Bash(*)"
