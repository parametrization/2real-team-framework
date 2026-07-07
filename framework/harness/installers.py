"""Real installer invocations (#104 §1 Stage 2) — bootstrap, CLI bridge, fired-hook payloads.

Every install is grounded in the actual installer flags (``framework/install/bootstrap.py``
argparse; ``2real-team init``). Runs are always ``--non-interactive`` with **stdin closed**
so ``non_interactive_zero_prompts`` is exercised on every cell — a hang/``EOFError`` is a
failure. Stdlib only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# framework/harness/installers.py -> framework/
_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_BOOTSTRAP = _FRAMEWORK_ROOT / "install" / "bootstrap.py"
_REINSTALL = _FRAMEWORK_ROOT / "install" / "reinstall.py"

#: Wall-clock ceiling per install invocation. A cell that exceeds this is a hard failure
#: (guards `non_interactive_zero_prompts` against a stdin-blocked hang and B9 pathologies).
INSTALL_TIMEOUT_S = 180


@dataclass
class RunResult:
    """A captured installer invocation — the parseable oracle every metric measures against."""

    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False

    @property
    def out(self) -> str:
        """Combined stdout+stderr (the result block prints across both)."""
        return f"{self.stdout}\n{self.stderr}"


def _run(argv: list[str], *, cwd: Path | None = None, env: dict | None = None) -> RunResult:
    start = time.monotonic()
    try:
        cp = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,  # zero-prompt contract: any prompt EOFErrors
            timeout=INSTALL_TIMEOUT_S,
            cwd=str(cwd) if cwd else None,
            env=env,
        )
        return RunResult(argv, cp.returncode, cp.stdout, cp.stderr, time.monotonic() - start)
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        err = (exc.stderr or "") + f"\nHARNESS: timed out after {INSTALL_TIMEOUT_S}s"
        return RunResult(
            argv,
            124,
            out if isinstance(out, str) else out.decode("utf-8", "replace"),
            err if isinstance(err, str) else err.decode("utf-8", "replace"),
            time.monotonic() - start,
            timed_out=True,
        )


def run_bootstrap(target: Path, flags: list[str]) -> RunResult:
    """``python3 framework/install/bootstrap.py <target> <flags> --non-interactive``."""
    argv = [sys.executable, str(_BOOTSTRAP), str(target), *flags]
    if "--non-interactive" not in flags and "--dry-run" not in flags:
        argv.append("--non-interactive")
    return _run(argv)


def run_cli(target: Path, flags: list[str]) -> RunResult:
    """``2real-team init --target <target> --non-interactive <flags>`` (bundled-bootstrap bridge).

    Invoked as a module (``python3 -m real_team.cli``-equivalent via the installed console
    script) so it works whether or not the ``2real-team`` shim is on PATH.
    """
    argv = [
        sys.executable,
        "-c",
        "import sys; from real_team.cli import app; app()",
        "init",
        "--target",
        str(target),
        "--non-interactive",
        *flags,
    ]
    return _run(argv)


def run_cli_soft_degrade(target: Path, flags: list[str], pkg_src: Path) -> RunResult:
    """``2real-team init`` run from an ISOLATED package copy whose framework payload is
    unreachable — exercises the CLI bridge's **soft-degrade** (#139).

    ``pkg_src`` is a directory on which ``real_team`` is importable but whose ``parents[2]``
    (the resolved repo-root the bridge probes) holds ``presets/templates/skills`` yet **no**
    ``framework/`` and no ``_bundled/framework``. So ``framework_install.resolve_framework_root``
    returns None: the CLI still lays the mustache team scaffolding + root ``CLAUDE.md``, prints
    the soft notice, skips the ``bootstrap.py`` runtime step, and exits 0. Prepending ``pkg_src``
    to ``PYTHONPATH`` shadows any installed ``real_team`` so the copy (not the editable install)
    is what runs.
    """
    argv = [
        sys.executable,
        "-c",
        "import sys; from real_team.cli import app; app()",
        "init",
        "--target",
        str(target),
        "--non-interactive",
        *flags,
    ]
    prior = os.environ.get("PYTHONPATH", "")
    env = {
        **os.environ,
        "PYTHONPATH": str(pkg_src) + (os.pathsep + prior if prior else ""),
    }
    return _run(argv, env=env)


def run_reinstall_check() -> RunResult:
    """``python3 framework/install/reinstall.py --check`` — read-only dogfood parity (B12)."""
    return _run([sys.executable, str(_REINSTALL), "--check"])


def fire_hook(
    target: Path, command: str, *, tool_name: str = "Bash", post: bool = False,
    identity: dict | None = None,
) -> RunResult:
    """Pipe a JSON tool payload into the INSTALLED dispatcher (#103 group D).

    Mirrors ``test_bootstrap_smoke.py``: returns the dispatcher's exit code + stdout.
    ``identity`` lets the caller inject a forged git author for the identity gate.
    """
    dispatcher = "post_dispatcher.py" if post else "dispatcher.py"
    payload_obj: dict = {
        "tool_name": tool_name,
        "cwd": str(target),
        "tool_input": {"command": command},
    }
    if identity:
        payload_obj["tool_input"].update(identity)
    hook = target / ".claude" / "hooks" / dispatcher
    # Suppress the real events-log write into the fixture (mirrors conftest); the fixture is
    # torn down anyway, but this keeps the .claude byte-diff clean for reinstall_idempotent.
    env = {**os.environ, "FRAMEWORK_HOOK_TEST_MODE": "1"}
    start = time.monotonic()
    cp = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(payload_obj),
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    return RunResult(
        [str(hook)], cp.returncode, cp.stdout, cp.stderr, time.monotonic() - start
    )
