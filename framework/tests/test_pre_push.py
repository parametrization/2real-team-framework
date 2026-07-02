"""Tests for the pre-push git hook installer (bootstrap.py --pre-push).

Covers the issue's AC: noop install (executable, exits 0), enforce blocks the
push on a failing configured command and passes on success, backup-on-conflict
via the non-clobbering .bak pattern, no-.git skip (fail-open), idempotent
re-run, `none` installs nothing, and core.hooksPath is respected. The enforce
semantics are asserted by executing the installed hook script directly (what
git itself would exec on push). Stdlib + pytest only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_BOOTSTRAP = _FRAMEWORK_ROOT / "install" / "bootstrap.py"


def _install(target: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_BOOTSTRAP), str(target), "--owner", "test-org", "--no-team", *extra],
        capture_output=True,
        text=True,
    )


def _git_init(target: Path) -> None:
    subprocess.run(["git", "init", "-q", str(target)], check=True, capture_output=True)


def _set_pre_push_commands(target: Path, cmds: list[str]) -> None:
    p = target / ".claude" / "framework.config.json"
    cfg = json.loads(p.read_text())
    cfg.setdefault("hooks", {})["pre_push_commands"] = cmds
    p.write_text(json.dumps(cfg))


def _run_hook(target: Path, hook: Path | None = None) -> subprocess.CompletedProcess:
    """Execute the installed pre-push hook the way git would (from the repo)."""
    hook = hook or (target / ".git" / "hooks" / "pre-push")
    return subprocess.run([str(hook)], cwd=str(target), capture_output=True, text=True)


def test_noop_install_is_executable_and_exits_zero(tmp_path: Path) -> None:
    _git_init(tmp_path)
    r = _install(tmp_path)  # noop is the default mode
    assert r.returncode == 0, r.stderr
    assert "pre-push hook:" in r.stdout and "installed (noop)" in r.stdout

    hook = tmp_path / ".git" / "hooks" / "pre-push"
    assert hook.is_file()
    assert os.access(hook, os.X_OK), "hook must be executable"
    text = hook.read_text()
    assert "2real team framework" in text  # says who installed it
    assert "noop" in text and "enforce" in text  # explains itself + how to enable enforcement

    assert _run_hook(tmp_path).returncode == 0  # never blocks a push


def test_enforce_blocks_on_failing_command(tmp_path: Path) -> None:
    _git_init(tmp_path)
    r = _install(tmp_path, "--pre-push", "enforce")
    assert r.returncode == 0, r.stderr
    assert "installed (enforce)" in r.stdout
    # Empty command list at install time earns an advisory.
    assert "pre_push_commands is empty" in r.stdout

    _set_pre_push_commands(tmp_path, ["true", "exit 7"])
    run = _run_hook(tmp_path)
    assert run.returncode == 7, run.stderr
    assert "BLOCKED" in run.stderr


def test_enforce_passes_on_success(tmp_path: Path) -> None:
    _git_init(tmp_path)
    _install(tmp_path, "--pre-push", "enforce")
    _set_pre_push_commands(tmp_path, ["true", "echo ok"])
    run = _run_hook(tmp_path)
    assert run.returncode == 0, run.stderr
    assert "all checks passed" in run.stderr


def test_enforce_fails_open_on_empty_or_missing_config(tmp_path: Path) -> None:
    _git_init(tmp_path)
    _install(tmp_path, "--pre-push", "enforce")
    # Empty command list -> allow the push.
    assert _run_hook(tmp_path).returncode == 0
    # Missing config entirely -> still allow the push.
    (tmp_path / ".claude" / "framework.config.json").unlink()
    run = _run_hook(tmp_path)
    assert run.returncode == 0
    assert "allowing push" in run.stderr


def test_existing_hook_is_backed_up_not_clobbered(tmp_path: Path) -> None:
    _git_init(tmp_path)
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    custom = "#!/bin/sh\necho my custom hook\n"
    (hooks / "pre-push").write_text(custom)

    r = _install(tmp_path)
    assert r.returncode == 0, r.stderr
    assert "preserved as pre-push.bak" in r.stdout  # warned
    assert (hooks / "pre-push.bak").read_text() == custom  # original kept
    assert "2real team framework" in (hooks / "pre-push").read_text()  # ours installed

    # A second conflicting hook backs up to .bak.1 (never overwrites .bak).
    (hooks / "pre-push").write_text(custom + "# v2\n")
    r2 = _install(tmp_path)
    assert r2.returncode == 0
    assert (hooks / "pre-push.bak.1").is_file()
    assert (hooks / "pre-push.bak").read_text() == custom  # first backup untouched


def test_no_git_target_skips_with_notice(tmp_path: Path) -> None:
    r = _install(tmp_path)  # no git init
    assert r.returncode == 0, r.stderr  # fail-open: the install itself succeeds
    assert "pre-push hook:     skipped" in r.stdout
    assert not (tmp_path / ".git").exists()


def test_rerun_is_idempotent(tmp_path: Path) -> None:
    _git_init(tmp_path)
    _install(tmp_path)
    r2 = _install(tmp_path)
    assert r2.returncode == 0
    assert "already installed (noop; unchanged)" in r2.stdout
    hooks = tmp_path / ".git" / "hooks"
    assert not (hooks / "pre-push.bak").exists()  # our own hook is never "backed up"


def test_mode_switch_replaces_framework_hook_with_backup(tmp_path: Path) -> None:
    _git_init(tmp_path)
    _install(tmp_path)  # noop
    r = _install(tmp_path, "--pre-push", "enforce")
    assert r.returncode == 0
    assert "installed (enforce)" in r.stdout
    assert "enforce. Runs every command" in (tmp_path / ".git" / "hooks" / "pre-push").read_text()


def test_none_installs_nothing(tmp_path: Path) -> None:
    _git_init(tmp_path)
    r = _install(tmp_path, "--pre-push", "none")
    assert r.returncode == 0, r.stderr
    assert "skipped (pre_push.mode=none)" in r.stdout
    assert not (tmp_path / ".git" / "hooks" / "pre-push").exists()


def test_install_config_yaml_drives_mode_without_flag(tmp_path: Path) -> None:
    """pre_push.mode from a user install-config YAML drives install_pre_push (no flag)."""
    yaml = tmp_path / "install.yaml"
    yaml.write_text("pre_push:\n  mode: enforce\n", encoding="utf-8")
    target = tmp_path / "repo"
    target.mkdir()
    _git_init(target)
    r = _install(target, "--install-config", str(yaml))
    assert r.returncode == 0, r.stderr
    assert "installed (enforce)" in r.stdout
    hook = target / ".git" / "hooks" / "pre-push"
    assert "MODE: enforce" in hook.read_text()
    # The resolved decision is recorded in the install snapshot.
    snapshot = json.loads((target / ".claude" / "install.config.json").read_text())
    assert snapshot["pre_push"]["mode"] == "enforce"


def test_flag_beats_install_config_yaml(tmp_path: Path) -> None:
    """Precedence: --pre-push flag > user YAML (> shipped default noop)."""
    yaml = tmp_path / "install.yaml"
    yaml.write_text("pre_push:\n  mode: enforce\n", encoding="utf-8")
    target = tmp_path / "repo"
    target.mkdir()
    _git_init(target)
    r = _install(target, "--install-config", str(yaml), "--pre-push", "none")
    assert r.returncode == 0, r.stderr
    assert "skipped (pre_push.mode=none)" in r.stdout
    assert not (target / ".git" / "hooks" / "pre-push").exists()
    # The flag decision (not the YAML's) is what the snapshot records.
    snapshot = json.loads((target / ".claude" / "install.config.json").read_text())
    assert snapshot["pre_push"]["mode"] == "none"


def test_shipped_default_is_noop_without_flag_or_yaml(tmp_path: Path) -> None:
    _git_init(tmp_path)
    r = _install(tmp_path)  # no --pre-push flag, no --install-config
    assert r.returncode == 0, r.stderr
    assert "installed (noop)" in r.stdout
    assert "MODE: noop" in (tmp_path / ".git" / "hooks" / "pre-push").read_text()


def test_core_hookspath_is_respected(tmp_path: Path) -> None:
    _git_init(tmp_path)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "core.hooksPath", ".githooks"],
        check=True, capture_output=True,
    )
    r = _install(tmp_path)
    assert r.returncode == 0, r.stderr
    assert "core.hooksPath is set" in r.stdout
    hook = tmp_path / ".githooks" / "pre-push"
    assert hook.is_file(), "hook must land in the EFFECTIVE hooks dir, not .git/hooks"
    assert not (tmp_path / ".git" / "hooks" / "pre-push").exists()
    assert _run_hook(tmp_path, hook).returncode == 0


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    _git_init(tmp_path)
    r = _install(tmp_path, "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "would write the noop hook" in r.stdout
    assert not (tmp_path / ".git" / "hooks" / "pre-push").exists()
