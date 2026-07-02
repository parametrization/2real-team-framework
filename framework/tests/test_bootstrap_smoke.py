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
    # These tests isolate the SCM/CI/safety gates, so install WITHOUT the team
    # layer (identity enforcement is covered by test_roster_gen.py — with it on,
    # a bare `git commit` would be blocked by the identity gate first).
    return subprocess.run(
        [sys.executable, str(_BOOTSTRAP), str(target), "--owner", "test-org", "--no-team", *extra],
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
    assert (claude / "lib" / "lifecycle.py").is_file()
    assert (claude / "skills" / "wave-lifecycle" / "SKILL.md").is_file()

    settings = json.loads((claude / "settings.json").read_text())
    pre = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "dispatcher.py" in pre

    # SessionStart auto-regeneration hook is wired (matcher-less block) + installed.
    assert (claude / "hooks" / "start_dispatcher.py").is_file()
    assert (claude / "hooks" / "ontology_refresh.py").is_file()
    session_cmd = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "start_dispatcher.py" in session_cmd

    # Re-run: nothing copied, config not clobbered.
    r2 = _install(tmp_path, "--shell", "zsh")
    assert r2.returncode == 0
    assert "skipped (exists)" in r2.stdout
    assert "already wired" in r2.stdout  # settings merge is idempotent across all events


def test_with_ontology_lays_overlay_template(tmp_path: Path) -> None:
    r = _install(tmp_path, "--with-ontology")
    assert r.returncode == 0, r.stderr
    for name in ("domain.yaml", "services.yaml", "conventions.md", "README.md"):
        assert (tmp_path / "ontology" / name).is_file(), name
    # Idempotent: re-run skips the existing overlay.
    r2 = _install(tmp_path, "--with-ontology")
    assert r2.returncode == 0
    assert "ontology overlay:" in r2.stdout


def test_with_ontology_generates_structural_index(tmp_path: Path) -> None:
    """A fresh install ends with the GENERATED structural layer on disk immediately."""
    (tmp_path / "app.py").write_text("def hello():\n    return 'world'\n")
    r = _install(tmp_path, "--with-ontology")
    assert r.returncode == 0, r.stderr
    assert "structural index:  generated" in r.stdout

    structural = tmp_path / "ontology" / "structural"
    assert (structural / "code-graph.json").is_file()
    assert (structural / "llms.txt").is_file()
    graph = json.loads((structural / "code-graph.json").read_text())
    paths = {n.get("path") for n in graph["nodes"]}
    assert "app.py" in paths  # generation ran against the TARGET repo

    # Idempotent re-run: index is fresh, regeneration safely skipped, files intact.
    r2 = _install(tmp_path, "--with-ontology")
    assert r2.returncode == 0
    assert "structural index:  fresh" in r2.stdout
    assert (structural / "code-graph.json").is_file()


def test_with_ontology_empty_target_still_valid(tmp_path: Path) -> None:
    """A target with no parseable sources still gets a valid (minimal) structural layer."""
    r = _install(tmp_path, "--with-ontology")
    assert r.returncode == 0, r.stderr
    graph = json.loads((tmp_path / "ontology" / "structural" / "code-graph.json").read_text())
    assert "nodes" in graph and "edges" in graph
    assert (tmp_path / "ontology" / "structural" / "llms.txt").is_file()


def test_with_ontology_generation_failure_is_fail_open(tmp_path: Path) -> None:
    """Generation failure warns and continues — the install itself must not abort."""
    # A regular FILE where the structural dir should go makes generation blow up.
    (tmp_path / "ontology").mkdir()
    (tmp_path / "ontology" / "structural").write_text("not a directory")
    r = _install(tmp_path, "--with-ontology")
    assert r.returncode == 0, r.stderr
    assert "structural index:  SKIPPED" in r.stdout
    assert "install continues" in r.stdout
    # The overlay + runtime were still laid down.
    assert (tmp_path / "ontology" / "domain.yaml").is_file()
    assert (tmp_path / ".claude" / "hooks" / "dispatcher.py").is_file()


def test_with_ontology_dry_run_writes_nothing(tmp_path: Path) -> None:
    r = _install(tmp_path, "--with-ontology", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "structural index:  would generate" in r.stdout
    assert not (tmp_path / "ontology").exists()


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
