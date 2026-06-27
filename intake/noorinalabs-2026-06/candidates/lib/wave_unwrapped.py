#!/usr/bin/env python3
"""Detect a wave that merged to main but was never formally wrapped (main#730).

P5W5 merged all 45 of its PRs to ``main`` days before the wave was formally
wrapped — ``wave_5_wrapped_up_at`` stayed null, ``wave_5_active`` stayed true,
and the post-wave audits (annunaki-attack, memory) never ran — because nothing
at session-start surfaced the gap. This helper provides the deterministic,
NON-FATAL detection /session-start (Step 5b) turns into a nudge toward
``/wave-wrapup``.

The signal (issue #730 acceptance criteria) is the conjunction:

    wave_{M}_active == true
      AND no wrapup marker present for wave M
      AND 0 open wave PRs across the wave's in-scope repos

scoped to the **current** wave only. Scoping to ``current_wave`` is load-bearing:
wave keys in cross-repo-status.json are NOT phase-namespaced (memory
``project_wave_key_cross_phase_collision`` / main#683), so the file legitimately
retains stale ``wave_4_active: true`` rows from a *prior* phase's W4. A naive
"any active+unwrapped wave" scan would false-fire on those cross-phase ghosts;
deriving M from ``current_wave`` ("wave-2" -> "2") looks only at the live wave.

Wrapup is recorded under one of several historical key spellings
(``wrapped_up_at`` / ``wrapup_completed_at`` / ``wrapped_at``) — all three are
treated as "wrapped". ``completed_at`` is deliberately NOT a wrapup marker: it
is set at an earlier lifecycle point (e.g. wave_1 ``completed_at`` predates its
``wrapup_completed_at`` by ~12 days), so counting it would mask the very
merge-to-wrapup gap this detector exists to find.

Everything degrades gracefully: a missing ``current_wave``, missing status keys,
or a failed ``gh`` call yields a benign verdict (``ok`` or the softer
``unwrapped_unverified``) and never raises — session-start must never break on
this.

CLI:
  wave_unwrapped.py check [--status PATH] [--phase P] [--wave M]
                          [--no-gh] [--json]

Always exits 0 (the nudge is informational, not a gate).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Repo root = two parents above .claude/lib/ (lib -> .claude -> root). Resolved
# from this file so the default is correct from any cwd or worktree.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_STATUS = _REPO_ROOT / "cross-repo-status.json"

# Wrapup-marker key spellings, oldest-to-newest. ANY present-and-non-null value
# means the wave was wrapped. ``completed_at`` is intentionally absent — see the
# module docstring (it marks an earlier point and would mask the gap).
_WRAPUP_MARKERS = ("wrapped_up_at", "wrapup_completed_at", "wrapped_at")


def _run_gh(args: list[str]) -> str:
    """Run ``gh <args>`` with an explicit arg list and return stdout.

    Explicit arg list (never a shell string, never ``shell=True``) so a
    multi-word value can never word-split under zsh — same contract as
    ``wave_status._run_gh`` (main#688).
    """
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def _load_status(status_path: Path) -> dict:
    return json.loads(Path(status_path).read_text())


def current_wave_number(data: dict) -> str | None:
    """The live wave number from the ``current_wave`` pointer ("wave-2" -> "2").

    Returns None when the pointer is absent or malformed — the caller treats
    that as "nothing to check" rather than guessing a wave.
    """
    raw = data.get("current_wave")
    if not isinstance(raw, str):
        return None
    num = raw[len("wave-") :] if raw.startswith("wave-") else raw
    return num if num.isdigit() else None


def is_active(data: dict, wave: str) -> bool:
    """Truthy ``wave_{M}_active`` (absent -> not active)."""
    return bool(data.get(f"wave_{wave}_active"))


def is_wrapped(data: dict, wave: str) -> bool:
    """True if any wrapup-marker variant for wave M is present and non-null."""
    return any(data.get(f"wave_{wave}_{m}") for m in _WRAPUP_MARKERS)


def base_branch(data: dict, wave: str, phase: str | None) -> str | None:
    """The wave's deployment branch — the PR base used to count open wave PRs.

    Prefers the exact branch recorded under ``wave_{M}_branches.branch`` (most
    reliable: it carries the real phase even when the top-level ``phase`` key is
    stale). Falls back to ``deployments/phase-{P}/wave-{M}`` only when an
    explicit phase is supplied. Returns None when neither source is available.
    """
    branches = data.get(f"wave_{wave}_branches")
    if isinstance(branches, dict):
        branch = branches.get("branch")
        if isinstance(branch, str) and branch:
            return branch
    if phase:
        return f"deployments/phase-{phase}/wave-{wave}"
    return None


def _read_repos(data: dict, wave: str) -> list[str] | None:
    """``wave_{M}_repos_in_scope`` as a list, or None if absent/malformed."""
    repos = data.get(f"wave_{wave}_repos_in_scope")
    if not isinstance(repos, list) or not repos:
        return None
    return [str(r) for r in repos]


def count_open_prs(repos: list[str], base: str) -> int | None:
    """Total open PRs targeting ``base`` across ``repos``.

    Best-effort: any ``gh`` failure (auth, rate-limit, unknown repo) returns
    None ("undetermined") rather than raising or reporting a false 0 — a false 0
    would fire a spurious "merged but unwrapped" nudge mid-wave.
    """
    total = 0
    for repo in repos:
        try:
            out = _run_gh(
                [
                    "pr",
                    "list",
                    "--repo",
                    f"noorinalabs/{repo}",
                    "--state",
                    "open",
                    "--base",
                    base,
                    "--json",
                    "number",
                ]
            )
            total += len(json.loads(out or "[]"))
        except (subprocess.CalledProcessError, json.JSONDecodeError, OSError):
            return None
    return total


def evaluate(
    data: dict,
    *,
    wave: str | None = None,
    phase: str | None = None,
    check_prs: bool = True,
) -> dict:
    """Classify the current (or given) wave's wrap state.

    Returns a dict with ``wave``, ``active``, ``wrapped``, ``open_pr_count``
    (int or None), ``base_branch``, ``verdict`` and a human ``message``.

    verdict:
      * ``ok``                  — nothing to nudge (no current wave, or the wave
                                  is inactive / already wrapped).
      * ``in_flight``           — active, unwrapped, but open wave PRs remain:
                                  a normal in-progress wave, no nudge.
      * ``unwrapped``           — active, unwrapped, 0 open wave PRs: merged but
                                  not wrapped — FIRE the /wave-wrapup nudge.
      * ``unwrapped_unverified``— active, unwrapped, open-PR count undetermined
                                  (gh failed / scope keys missing): softer nudge.
    """
    wave = wave or current_wave_number(data)
    result: dict = {
        "wave": wave,
        "active": False,
        "wrapped": False,
        "open_pr_count": None,
        "base_branch": None,
        "verdict": "ok",
        "message": "",
    }
    if wave is None:
        result["message"] = "No current wave recorded — nothing to check."
        return result

    active = is_active(data, wave)
    wrapped = is_wrapped(data, wave)
    result["active"] = active
    result["wrapped"] = wrapped

    if not active:
        result["message"] = f"Wave {wave} is not active."
        return result
    if wrapped:
        result["message"] = f"Wave {wave} is already wrapped."
        return result

    # Active and unwrapped — the open-PR count discriminates "merged but
    # unwrapped" from a still-in-flight wave.
    base = base_branch(data, wave, phase)
    result["base_branch"] = base
    repos = _read_repos(data, wave)

    open_count: int | None = None
    if check_prs and base and repos:
        open_count = count_open_prs(repos, base)
    result["open_pr_count"] = open_count

    if open_count == 0:
        result["verdict"] = "unwrapped"
        result["message"] = (
            f"Wave {wave} is active and unwrapped with 0 open wave PRs — "
            "merged but not wrapped. Run /wave-wrapup."
        )
    elif open_count is None:
        result["verdict"] = "unwrapped_unverified"
        why = "open-PR count undetermined (gh unavailable or wave scope not recorded)"
        result["message"] = (
            f"Wave {wave} is active and unwrapped; {why}. If its PRs are merged, run /wave-wrapup."
        )
    else:
        result["verdict"] = "in_flight"
        result["message"] = f"Wave {wave} is active with {open_count} open wave PR(s) — in flight."
    return result


def _cmd_check(args: argparse.Namespace) -> int:
    try:
        data = _load_status(args.status)
    except (OSError, json.JSONDecodeError) as exc:
        # Cannot read status -> degrade to a benign no-op so session-start lives.
        print(f"wave-unwrapped: status unreadable ({exc}); skipping check.")
        return 0

    result = evaluate(
        data,
        wave=args.wave,
        phase=args.phase,
        check_prs=not args.no_gh,
    )

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    if result["verdict"] in ("unwrapped", "unwrapped_unverified"):
        print(f"NUDGE: {result['message']}")
    else:
        print(result["message"])
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="classify the current wave's wrap state")
    p_check.add_argument(
        "--status",
        type=Path,
        default=_DEFAULT_STATUS,
        help="path to cross-repo-status.json (default: repo-root copy)",
    )
    p_check.add_argument("--phase", default=None, help="phase number (fallback for base branch)")
    p_check.add_argument("--wave", default=None, help="override the current-wave number")
    p_check.add_argument(
        "--no-gh",
        action="store_true",
        help="skip the open-PR gh probe (key-only verdict)",
    )
    p_check.add_argument("--json", action="store_true", help="emit the full result as JSON")
    p_check.set_defaults(func=_cmd_check)
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
