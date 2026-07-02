"""Dispatch routing tests for the Agent and Stop events (issue #87).

Installs the framework into a tmp repo via bootstrap.py, drops purpose-built
hook modules into the installed ``.claude/hooks/``, points the config's
``hooks.agent`` / ``hooks.stop`` lists at them, and fires JSON payloads through
the INSTALLED dispatchers as subprocesses — asserting PreToolUse semantics for
Agent (first block wins, exit 2), never-block semantics for Stop (always exit
0, advisories aggregated, block decisions downgraded), and fail-open behaviour
for missing/raising modules on both. Stdlib + pytest only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_BOOTSTRAP = _FRAMEWORK_ROOT / "install" / "bootstrap.py"

sys.path.insert(0, str(_FRAMEWORK_ROOT / "install"))
import bootstrap  # noqa: E402


def _install(target: Path) -> None:
    r = subprocess.run(
        [sys.executable, str(_BOOTSTRAP), str(target), "--owner", "test-org", "--no-team"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr


def _write_hook(target: Path, name: str, body: str) -> None:
    (target / ".claude" / "hooks" / f"{name}.py").write_text(body, encoding="utf-8")


def _set_hooks(target: Path, key: str, modules: list[str]) -> None:
    p = target / ".claude" / "framework.config.json"
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg.setdefault("hooks", {})[key] = modules
    p.write_text(json.dumps(cfg), encoding="utf-8")


def _fire(target: Path, dispatcher: str, payload: dict) -> subprocess.CompletedProcess:
    payload = {"cwd": str(target), **payload}
    return subprocess.run(
        [sys.executable, str(target / ".claude" / "hooks" / dispatcher)],
        input=json.dumps(payload), capture_output=True, text=True,
    )


_BLOCKER = 'def check(input_data):\n    return {"decision": "block", "reason": "agent gate says no"}\n'
_WARNER = 'def check(input_data):\n    return {"decision": "allow", "systemMessage": "heads up"}\n'
_RAISER = 'def check(input_data):\n    raise RuntimeError("boom")\n'
_STOP_NOTE = 'def check(input_data):\n    return {"systemMessage": "stop note"}\n'
_STOP_BLOCKER = 'def check(input_data):\n    return {"decision": "block", "reason": "do not stop"}\n'


# ------------------------------------------------------------------ Agent event


def test_agent_block_wins(tmp_path: Path) -> None:
    _install(tmp_path)
    _write_hook(tmp_path, "agent_blocker", _BLOCKER)
    _write_hook(tmp_path, "agent_warner", _WARNER)
    _set_hooks(tmp_path, "agent", ["agent_blocker", "agent_warner"])
    r = _fire(tmp_path, "dispatcher.py", {"tool_name": "Agent", "tool_input": {"prompt": "x"}})
    assert r.returncode == 2
    assert "agent gate says no" in r.stdout


def test_agent_allow_aggregates_warnings(tmp_path: Path) -> None:
    _install(tmp_path)
    _write_hook(tmp_path, "agent_warner", _WARNER)
    _set_hooks(tmp_path, "agent", ["agent_warner"])
    r = _fire(tmp_path, "dispatcher.py", {"tool_name": "Agent", "tool_input": {"prompt": "x"}})
    assert r.returncode == 0
    assert "heads up" in r.stdout


def test_agent_legacy_task_name_routes_to_same_gate(tmp_path: Path) -> None:
    _install(tmp_path)
    _write_hook(tmp_path, "agent_blocker", _BLOCKER)
    _set_hooks(tmp_path, "agent", ["agent_blocker"])
    r = _fire(tmp_path, "dispatcher.py", {"tool_name": "Task", "tool_input": {"prompt": "x"}})
    assert r.returncode == 2


def test_agent_hooks_do_not_run_for_bash(tmp_path: Path) -> None:
    _install(tmp_path)
    _write_hook(tmp_path, "agent_blocker", _BLOCKER)
    _set_hooks(tmp_path, "agent", ["agent_blocker"])
    r = _fire(tmp_path, "dispatcher.py", {"tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert r.returncode == 0  # Bash routes to hooks.pre_bash, not hooks.agent


def test_unrouted_tool_exits_zero(tmp_path: Path) -> None:
    _install(tmp_path)
    r = _fire(tmp_path, "dispatcher.py", {"tool_name": "WebFetch", "tool_input": {}})
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_agent_default_is_empty_and_allows(tmp_path: Path) -> None:
    _install(tmp_path)  # written config carries "agent": []
    r = _fire(tmp_path, "dispatcher.py", {"tool_name": "Agent", "tool_input": {"prompt": "x"}})
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_agent_fail_open_on_import_error_and_raise(tmp_path: Path) -> None:
    _install(tmp_path)
    _write_hook(tmp_path, "agent_raiser", _RAISER)
    _set_hooks(tmp_path, "agent", ["not_installed_module", "agent_raiser"])
    r = _fire(tmp_path, "dispatcher.py", {"tool_name": "Agent", "tool_input": {"prompt": "x"}})
    assert r.returncode == 0  # missing module skipped; raising module swallowed


# ------------------------------------------------------------------- Stop event


def test_stop_aggregates_advisories(tmp_path: Path) -> None:
    _install(tmp_path)
    _write_hook(tmp_path, "stop_note", _STOP_NOTE)
    _set_hooks(tmp_path, "stop", ["stop_note"])
    r = _fire(tmp_path, "stop_dispatcher.py", {"hook_event_name": "Stop"})
    assert r.returncode == 0
    assert "stop note" in r.stdout


def test_stop_never_blocks_even_on_block_decision(tmp_path: Path) -> None:
    _install(tmp_path)
    _write_hook(tmp_path, "stop_blocker", _STOP_BLOCKER)
    _set_hooks(tmp_path, "stop", ["stop_blocker"])
    r = _fire(tmp_path, "stop_dispatcher.py", {"hook_event_name": "Stop"})
    assert r.returncode == 0  # block downgraded, never exit 2
    assert "do not stop" in r.stdout  # ... but the reason is surfaced as advisory
    assert '"decision"' not in r.stdout  # no block decision leaks to the harness


def test_stop_fail_open_on_import_error_and_raise(tmp_path: Path) -> None:
    _install(tmp_path)
    _write_hook(tmp_path, "stop_raiser", _RAISER)
    _set_hooks(tmp_path, "stop", ["not_installed_module", "stop_raiser"])
    r = _fire(tmp_path, "stop_dispatcher.py", {"hook_event_name": "Stop"})
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_stop_garbage_stdin_exits_zero(tmp_path: Path) -> None:
    _install(tmp_path)
    r = subprocess.run(
        [sys.executable, str(tmp_path / ".claude" / "hooks" / "stop_dispatcher.py")],
        input="not json", capture_output=True, text=True, cwd=str(tmp_path),
    )
    assert r.returncode == 0


# --------------------------------------------------- merge_settings (new blocks)


def test_merge_settings_upgrades_old_install_with_agent_and_stop(tmp_path: Path) -> None:
    """A settings.json from a pre-#87 install gains the Agent + Stop blocks on
    re-merge; existing blocks (and user hooks inside them) are untouched."""
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    old = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [
                    {"type": "command",
                     "command": 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/dispatcher.py"',
                     "timeout": 30},
                    {"type": "command", "command": "python3 my_custom_hook.py"},
                ]}
            ]
        }
    }
    (claude / "settings.json").write_text(json.dumps(old), encoding="utf-8")

    assert bootstrap.merge_settings(claude, dry_run=False) == "updated"
    merged = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
    matchers = {b.get("matcher") for b in merged["hooks"]["PreToolUse"]}
    assert matchers == {"Bash", "Agent"}
    stop_blocks = merged["hooks"]["Stop"]
    assert len(stop_blocks) == 1 and "matcher" not in stop_blocks[0]  # no-matcher shape kept
    assert "stop_dispatcher.py" in stop_blocks[0]["hooks"][0]["command"]
    bash_cmds = [h["command"] for b in merged["hooks"]["PreToolUse"]
                 if b.get("matcher") == "Bash" for h in b["hooks"]]
    assert "python3 my_custom_hook.py" in bash_cmds  # user's own hook preserved

    # Second merge is a strict no-op (idempotent for the new event shapes too).
    before = (claude / "settings.json").read_text(encoding="utf-8")
    assert bootstrap.merge_settings(claude, dry_run=False) == "already wired"
    assert (claude / "settings.json").read_text(encoding="utf-8") == before


def test_merge_settings_stop_block_not_duplicated_across_reruns(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    for _ in range(3):
        bootstrap.merge_settings(claude, dry_run=False)
    merged = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
    assert len(merged["hooks"]["Stop"]) == 1
    assert len(merged["hooks"]["Stop"][0]["hooks"]) == 1
    agent_blocks = [b for b in merged["hooks"]["PreToolUse"] if b.get("matcher") == "Agent"]
    assert len(agent_blocks) == 1 and len(agent_blocks[0]["hooks"]) == 1
