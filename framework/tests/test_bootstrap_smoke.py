"""End-to-end smoke test for the framework bootstrap + dispatcher chain.

Installs the framework into a tmp repo via bootstrap.py, then fires JSON tool
inputs through the INSTALLED dispatcher to assert the gate actually works:
a `--no-verify` commit blocks (exit 2), a benign command passes (exit 0), the
config-driven shell gate flips the zsh advisory on/off, and `scm.allow_force`
relaxes the no-verify block. Stdlib + pytest only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_BOOTSTRAP = _FRAMEWORK_ROOT / "install" / "bootstrap.py"


def _install(target: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_BOOTSTRAP), str(target), "--owner", "test-org", *extra],
        capture_output=True,
        text=True,
    )


def _fire(target: Path, command: str, *, post: bool = False) -> subprocess.CompletedProcess:
    dispatcher = "post_dispatcher.py" if post else "dispatcher.py"
    payload = json.dumps(
        {"tool_name": "Bash", "cwd": str(target), "tool_input": {"command": command}}
    )
    return subprocess.run(
        [sys.executable, str(target / ".claude" / "hooks" / dispatcher)],
        input=payload,
        capture_output=True,
        text=True,
    )


def _set_config(target: Path, dotted: str, value) -> None:
    p = target / ".claude" / "framework.config.json"
    cfg = json.loads(p.read_text())
    node = cfg
    parts = dotted.split(".")
    for k in parts[:-1]:
        node = node.setdefault(k, {})
    node[parts[-1]] = value
    p.write_text(json.dumps(cfg))


def test_install_is_complete_and_idempotent(tmp_path: Path) -> None:
    r1 = _install(tmp_path, "--shell", "zsh")
    assert r1.returncode == 0, r1.stderr
    claude = tmp_path / ".claude"
    assert (claude / "framework.config.json").is_file()
    assert (claude / "settings.json").is_file()
    assert (claude / "hooks" / "dispatcher.py").is_file()
    assert (claude / "lib" / "upsert_status_keys.py").is_file()

    settings = json.loads((claude / "settings.json").read_text())
    pre = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "dispatcher.py" in pre

    # Re-run: nothing copied, config not clobbered.
    r2 = _install(tmp_path, "--shell", "zsh")
    assert r2.returncode == 0
    assert "skipped (exists)" in r2.stdout


def test_no_verify_blocks(tmp_path: Path) -> None:
    _install(tmp_path)
    r = _fire(tmp_path, "git commit --no-verify -m x")
    assert r.returncode == 2
    assert "no-verify" in r.stdout.lower()


def test_benign_command_passes(tmp_path: Path) -> None:
    _install(tmp_path)
    r = _fire(tmp_path, "ls -la")
    assert r.returncode == 0
    assert r.stdout.strip() == ""  # no warnings


def test_allow_force_relaxes_no_verify(tmp_path: Path) -> None:
    _install(tmp_path)
    _set_config(tmp_path, "scm.allow_force", True)
    r = _fire(tmp_path, "git commit --no-verify -m x")
    assert r.returncode == 0  # force allowed → not blocked


def test_zsh_advisory_respects_shell_gate(tmp_path: Path) -> None:
    _install(tmp_path, "--shell", "zsh")
    bashism = 'for k in "${!arr[@]}"; do echo $k; done'
    r_zsh = _fire(tmp_path, bashism)
    assert r_zsh.returncode == 0
    assert "ZSH-SAFETY" in r_zsh.stdout  # advisory surfaced

    _set_config(tmp_path, "shell", "bash")
    r_bash = _fire(tmp_path, bashism)
    assert r_bash.returncode == 0
    assert r_bash.stdout.strip() == ""  # gate off under bash
