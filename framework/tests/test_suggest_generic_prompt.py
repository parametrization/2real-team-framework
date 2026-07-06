"""Tests for suggest_generic_prompt.py — the silent promotion-candidate PostToolUse hook (#102).

Stdlib + pytest only; no network. Exercises INERT-by-default (no config found), the
candidate-path scoping (memory/skills/hooks/lib/team-charter vs. everything else), the
silent contract (check() always returns None — no systemMessage, ever), and that a
first-touch writes a pending ledger entry while a re-touch of an already-decided artifact
leaves it alone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "lib"))

import _framework_config  # noqa: E402
import generic_prompt_tracker as gpt  # noqa: E402
import suggest_generic_prompt as sgp  # noqa: E402


def _repo_with_config(tmp_path: Path) -> Path:
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    (claude / "framework.config.json").write_text(json.dumps({"version": 1}), encoding="utf-8")
    _framework_config.clear_cache()
    return tmp_path


def _edit(file_path: Path, cwd: Path) -> dict:
    return {"tool_name": "Edit", "tool_input": {"file_path": str(file_path)}, "cwd": str(cwd)}


def _ledger_path(root: Path) -> Path:
    return root / ".claude" / "generic_prompt_ledger.json"


# --------------------------------------------------------------- inert / scoping


def test_inert_without_framework_config(tmp_path: Path) -> None:
    _framework_config.clear_cache()
    target = tmp_path / ".claude" / "memory" / "foo.md"
    target.parent.mkdir(parents=True)
    target.write_text("hello", encoding="utf-8")
    assert sgp.check(_edit(target, tmp_path)) is None
    assert not _ledger_path(tmp_path).exists()


def test_ignores_wrong_tool_name(tmp_path: Path) -> None:
    root = _repo_with_config(tmp_path)
    target = root / ".claude" / "memory" / "foo.md"
    target.parent.mkdir(parents=True)
    target.write_text("hello", encoding="utf-8")
    data = {"tool_name": "Read", "tool_input": {"file_path": str(target)}, "cwd": str(root)}
    assert sgp.check(data) is None
    assert not _ledger_path(root).exists()


def test_records_candidate_under_memory(tmp_path: Path) -> None:
    root = _repo_with_config(tmp_path)
    target = root / ".claude" / "memory" / "foo.md"
    target.parent.mkdir(parents=True)
    target.write_text("hello", encoding="utf-8")

    result = sgp.check(_edit(target, root))
    assert result is None  # silent — never surfaces anything

    ledger = gpt.load_ledger(_ledger_path(root))
    assert ".claude/memory/foo.md" in ledger["candidates"]
    assert ledger["candidates"][".claude/memory/foo.md"]["decision"] == gpt.PENDING


def test_records_candidate_under_team_charter(tmp_path: Path) -> None:
    root = _repo_with_config(tmp_path)
    target = root / ".claude" / "team" / "charter" / "widgets.md"
    target.parent.mkdir(parents=True)
    target.write_text("hello", encoding="utf-8")

    sgp.check(_edit(target, root))
    ledger = gpt.load_ledger(_ledger_path(root))
    assert ".claude/team/charter/widgets.md" in ledger["candidates"]


def test_skips_non_candidate_dir(tmp_path: Path) -> None:
    root = _repo_with_config(tmp_path)
    # team/roster.json is under .claude/team/ but NOT under team/charter/ — not a candidate.
    target = root / ".claude" / "team" / "roster.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}", encoding="utf-8")

    sgp.check(_edit(target, root))
    assert not _ledger_path(root).exists()


def test_skips_file_outside_claude_dir(tmp_path: Path) -> None:
    root = _repo_with_config(tmp_path)
    target = root / "README.md"
    target.write_text("hello", encoding="utf-8")

    sgp.check(_edit(target, root))
    assert not _ledger_path(root).exists()


def test_skips_the_ledger_file_itself(tmp_path: Path) -> None:
    root = _repo_with_config(tmp_path)
    ledger = _ledger_path(root)
    ledger.write_text(json.dumps({"version": 1, "candidates": {}}), encoding="utf-8")

    result = sgp.check(_edit(ledger, root))
    assert result is None
    # Unchanged — the hook must not treat its own state file as a candidate.
    assert json.loads(ledger.read_text(encoding="utf-8")) == {"version": 1, "candidates": {}}


# --------------------------------------------------------------- silent contract + no-clobber


def test_never_returns_a_system_message(tmp_path: Path) -> None:
    root = _repo_with_config(tmp_path)
    target = root / ".claude" / "skills" / "demo" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("---\nname: demo\n---\n", encoding="utf-8")
    for _ in range(3):
        result = sgp.check(_edit(target, root))
        assert result is None


def test_retouch_does_not_reset_a_decided_candidate(tmp_path: Path) -> None:
    root = _repo_with_config(tmp_path)
    target = root / ".claude" / "hooks" / "demo_hook.py"
    target.parent.mkdir(parents=True)
    target.write_text("print(1)\n", encoding="utf-8")

    sgp.check(_edit(target, root))
    ledger_path = _ledger_path(root)
    gpt.record_candidate(
        ledger_path, ".claude/hooks/demo_hook.py", decision=gpt.SKIP, at="T1"
    )

    # A second edit (the hook firing again) must not reset the decision to pending.
    sgp.check(_edit(target, root))
    ledger = gpt.load_ledger(ledger_path)
    entry = ledger["candidates"][".claude/hooks/demo_hook.py"]
    assert entry["decision"] == gpt.SKIP
    assert entry["decided_at"] == "T1"
