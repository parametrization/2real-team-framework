#!/usr/bin/env python3
"""One-merge-model-per-wave + mid-wave wave-branch reachability (main#801).

Adopted from the P6W1 retro. That wave *mixed* merge models: #704/#706/#734/#735
were merged to the ``deployments/phase-6/wave-1`` branch while the doc batch +
cspell/mermaid work went **direct to main**, and the wave→main PR was never
opened. Five net-new deliverables therefore sat stranded off ``main`` and were
caught only at ``/wave-wrapup`` Step 11.5 — hours/days after they should have
surfaced.

Two durable fixes live here, both as deterministic, testable code (charter
``enforcement_hierarchy`` — prefer code over prose):

1. **One merge model per wave, declared at kickoff.** A wave is EITHER
   ``direct-to-main`` (every PR bases on ``main``; the wave branch stays at the
   kickoff point and never accumulates work) OR ``wave-branch`` (every PR bases
   on ``deployments/phase-{P}/wave-{M}`` and the wave→main integration PR is
   opened at wrapup). Mixing the two within one wave is prohibited. The chosen
   model is recorded in ``cross-repo-status.json`` under ``wave_{M}_merge_model``
   at ``/wave-kickoff`` (subcommand ``set``).

2. **Mid-wave reachability check** (subcommand ``reachability``, wired into
   ``/session-start``). For every in-scope repo it compares the wave branch
   against ``origin/main`` and classifies the gap **against the declared
   model**, so stranding (or model-mixing) surfaces within hours rather than
   only at wrapup:

     * ``direct-to-main`` + wave branch ahead of main  → **violation** (someone
       merged to the wave branch under a direct-to-main wave — the exact P6W1
       mixing).
     * ``wave-branch`` + ahead + an OPEN wave→main PR   → **ok** (healthy: the
       integration PR is tracking the work).
     * ``wave-branch`` + ahead + NO open wave→main PR   → **advisory** (normal
       mid-wave, but it WILL strand unless ``/wave-wrapup`` opens the PR).

The classification is a pure function (:func:`classify_reachability`) so every
model×state combination is unit-tested without touching the network; the thin
``gh`` I/O layer mirrors :mod:`wave_status` (explicit arg-list ``_run_gh``, no
shell, no word-splitting — main#688).

CLI:
  wave_merge_model.py model        <P> <M> [--status PATH]
  wave_merge_model.py set          <P> <M> <model> [--status PATH]
  wave_merge_model.py reachability <P> <M> [--status PATH] [--json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Repo root = two parents above .claude/lib/ (lib -> .claude -> root). Resolved
# from this file so the default is correct from any cwd or worktree, with no
# `git rev-parse` subprocess (which would re-introduce a shell dependency).
# Same anchor as wave_status.py.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_STATUS = _REPO_ROOT / "cross-repo-status.json"

# The two permitted merge models. A wave is exactly one of these for its whole
# lifetime; mixing is the bug this module exists to prevent.
DIRECT_TO_MAIN = "direct-to-main"
WAVE_BRANCH = "wave-branch"
MERGE_MODELS = (DIRECT_TO_MAIN, WAVE_BRANCH)

# Severities returned by classify_reachability. "violation" is a model breach
# (hard signal); "advisory" is an expected-but-watch-it state; "ok" is healthy.
OK = "ok"
ADVISORY = "advisory"
VIOLATION = "violation"


def _run_gh(args: list[str]) -> str:
    """Run ``gh <args>`` with an explicit arg list and return stdout.

    Never a shell string and never ``shell=True`` — no shell means no
    word-splitting, the main#688 contract shared with wave_status.py.
    """
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def _load_status(status_path: Path) -> dict:
    return json.loads(status_path.read_text())


def validate_merge_model(model: str) -> str:
    """Return ``model`` if it is one of :data:`MERGE_MODELS`, else raise.

    Centralised so both ``set`` (write-time) and ``read_merge_model``
    (read-time) reject a typo the same way rather than silently persisting or
    trusting an unknown value.
    """
    if model not in MERGE_MODELS:
        raise ValueError(
            f"invalid merge model {model!r}; expected one of {', '.join(MERGE_MODELS)}"
        )
    return model


def read_merge_model(wave: str, status_path: Path) -> str | None:
    """Return the declared ``wave_{M}_merge_model`` or None if absent.

    None means the model was never recorded (a legacy wave, or a wave kicked
    off before this feature existed). Callers degrade gracefully rather than
    hard-failing on legacy waves — see :func:`classify_reachability`. A *present
    but invalid* value is an error to surface, so it is validated here.
    """
    data = _load_status(status_path)
    val = data.get(f"wave_{wave}_merge_model")
    if val is None:
        return None
    return validate_merge_model(str(val))


def read_repos(wave: str, status_path: Path) -> list[str]:
    """Return ``wave_{M}_repos_in_scope`` as a list of repo names.

    Raises KeyError if absent — by the time the reachability check runs the
    wave's scope must already be recorded (same contract as wave_status.py).
    """
    data = _load_status(status_path)
    key = f"wave_{wave}_repos_in_scope"
    if key not in data:
        raise KeyError(key)
    repos = data[key]
    if not isinstance(repos, list):
        raise TypeError(f"{key} is not a list: {repos!r}")
    return [str(r) for r in repos]


def classify_reachability(
    model: str | None,
    *,
    branch_exists: bool,
    ahead_by: int,
    status: str,
    open_wave_main_pr: bool,
) -> tuple[str, str]:
    """Classify one repo's wave-branch-vs-main state against the declared model.

    Pure — no I/O. ``ahead_by`` is the compare API's ``ahead_by`` for
    ``main...<wave-branch>`` (commits on the wave branch not on main); ``status``
    is its ``status`` (``identical``/``ahead``/``behind``/``diverged``).
    ``open_wave_main_pr`` is whether an OPEN ``<wave-branch>``→``main`` PR exists.

    Returns ``(severity, human-readable message)`` where severity is one of
    :data:`OK`, :data:`ADVISORY`, :data:`VIOLATION`.
    """
    if not branch_exists:
        # Scope-drop / not-yet-created: nothing on the wave branch to strand.
        return OK, "no wave branch — nothing to reconcile (scope-drop or not yet created)"

    ahead = ahead_by > 0 or status == "diverged"
    if not ahead:
        return OK, f"wave branch reachable from main (ahead_by={ahead_by}, status={status})"

    # From here the wave branch carries commits not on main.
    if model == DIRECT_TO_MAIN:
        # Under direct-to-main NOTHING should land on the wave branch. Any
        # commits ahead are the P6W1 mixing failure — flag hard, even if a
        # wave→main PR happens to be open (an open PR means the wave drifted
        # into the wave-branch model it did not declare).
        pr_note = (
            " (a wave→main PR is open — the wave has drifted to the wave-branch model)"
            if open_wave_main_pr
            else ""
        )
        return (
            VIOLATION,
            f"merge-model violation: {ahead_by} commit(s) on the wave branch under "
            f"declared '{DIRECT_TO_MAIN}' model — work was merged to the wave branch "
            f"instead of main (mixing prohibited, #801){pr_note}",
        )

    if model == WAVE_BRANCH:
        if open_wave_main_pr:
            return (
                OK,
                f"{ahead_by} commit(s) ahead, tracked by an open wave→main PR — "
                f"healthy under '{WAVE_BRANCH}' model",
            )
        return (
            ADVISORY,
            f"{ahead_by} commit(s) on the wave branch not reachable from main and "
            f"NO open wave→main PR — normal mid-wave under '{WAVE_BRANCH}' model, but "
            f"these WILL strand unless /wave-wrapup opens the wave→main PR (#801)",
        )

    # model is None / unrecorded — a legacy wave or one kicked off before #801.
    # Do not hard-fail; apply the conservative wave-branch reading (advisory)
    # and nudge to declare the model. Avoids false VIOLATIONs on legacy waves
    # while still surfacing the stranding risk.
    base = (
        f"{ahead_by} commit(s) on the wave branch not reachable from main; "
        f"merge model NOT declared at kickoff — record wave_merge_model via "
        f"/wave-kickoff (#801)"
    )
    if open_wave_main_pr:
        return ADVISORY, base + " (a wave→main PR is open)"
    return ADVISORY, base + " — these may strand if no wave→main PR is opened at wrapup"


def _gather_repo_state(repo: str, branch: str, run_gh) -> dict:
    """Collect the wave-branch-vs-main facts for one repo via ``gh`` at origin.

    Thin I/O wrapper around the compare + ref + PR-list endpoints. Compares at
    origin (NOT a local clone) per charter ``pull-requests.md § Origin > Local
    Clone``. Returns the keyword args :func:`classify_reachability` consumes.
    A missing wave branch (404 on the ref lookup) yields ``branch_exists:
    False`` rather than raising.
    """
    try:
        run_gh(["api", f"repos/noorinalabs/{repo}/git/refs/heads/{branch}", "--jq", ".object.sha"])
    except subprocess.CalledProcessError:
        return {
            "branch_exists": False,
            "ahead_by": 0,
            "status": "absent",
            "open_wave_main_pr": False,
        }

    compare = json.loads(
        run_gh(
            [
                "api",
                f"repos/noorinalabs/{repo}/compare/main...{branch}",
                "--jq",
                "{ahead_by, behind_by, status}",
            ]
        )
    )
    open_count = int(
        run_gh(
            [
                "pr",
                "list",
                "--repo",
                f"noorinalabs/{repo}",
                "--base",
                "main",
                "--head",
                branch,
                "--state",
                "open",
                "--json",
                "number",
                "--jq",
                "length",
            ]
        ).strip()
        or 0
    )
    return {
        "branch_exists": True,
        "ahead_by": int(compare.get("ahead_by") or 0),
        "status": str(compare.get("status") or ""),
        "open_wave_main_pr": open_count > 0,
    }


def check_reachability(
    phase: str,
    wave: str,
    status_path: Path,
    run_gh=None,
    gather=None,
) -> list[dict]:
    """Run the mid-wave reachability classification for every in-scope repo.

    ``gather`` is injectable so tests exercise the per-repo classification
    without any network (mirrors wave_status.py's mocked ``_run_gh``). Defaults
    are resolved at call time (NOT bound in the signature) so a test that
    monkeypatches the module-level ``_gather_repo_state`` is honoured. Returns
    one result dict per repo: ``{repo, severity, message, **state}``.
    """
    run_gh = run_gh or _run_gh
    gather = gather or _gather_repo_state
    model = read_merge_model(wave, status_path)
    repos = read_repos(wave, status_path)
    branch = f"deployments/phase-{phase}/wave-{wave}"

    results: list[dict] = []
    for repo in repos:
        state = gather(repo, branch, run_gh)
        severity, message = classify_reachability(model, **state)
        results.append({"repo": repo, "severity": severity, "message": message, **state})
    return results


def _set_merge_model(wave: str, model: str, status_path: Path) -> int:
    """Validate + upsert ``wave_{M}_merge_model`` via upsert_status_keys.main.

    Reuses the shared helper so the compact-inline shape of
    cross-repo-status.json is preserved and the write is JSON-validated before
    AND after (same path wave_status.py uses for the counter keys).
    """
    validate_merge_model(model)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from upsert_status_keys import main as upsert_main

    # upsert_status_keys.main treats argv[0] as the program name and argv[1] as
    # the status path. The value is a self-contained JSON literal — a string, so
    # it carries its own quotes. `model` is validated against a fixed enum above,
    # so embedding it directly is injection-safe.
    return upsert_main(
        [
            "wave_merge_model",
            str(status_path),
            f'wave_{wave}_merge_model="{model}"',
        ]
    )


def _cmd_model(args: argparse.Namespace) -> int:
    model = read_merge_model(args.wave, args.status)
    if model is None:
        print(
            f"ERROR: wave_{args.wave}_merge_model not recorded in {args.status}. "
            f"Declare it at /wave-kickoff (one of: {', '.join(MERGE_MODELS)}).",
            file=sys.stderr,
        )
        return 1
    print(model)
    return 0


def _cmd_set(args: argparse.Namespace) -> int:
    return _set_merge_model(args.wave, args.model, args.status)


def _format_report(wave: str, model: str | None, results: list[dict]) -> str:
    lines: list[str] = []
    model_label = model if model is not None else "NOT DECLARED (#801)"
    lines.append(f"Wave {wave} merge model: {model_label}")
    for r in results:
        marker = {OK: "OK", ADVISORY: "ADVISORY", VIOLATION: "VIOLATION"}[r["severity"]]
        lines.append(f"  [{marker}] {r['repo']}: {r['message']}")
    return "\n".join(lines)


def _cmd_reachability(args: argparse.Namespace) -> int:
    model = read_merge_model(args.wave, args.status)
    results = check_reachability(args.phase, args.wave, args.status)

    if args.json:
        print(json.dumps({"wave": args.wave, "merge_model": model, "results": results}, indent=2))
    else:
        print(_format_report(args.wave, model, results))

    # Exit non-zero ONLY on a hard model violation. Advisories are expected
    # mid-wave states and must not fail the (non-fatal) /session-start step.
    return 1 if any(r["severity"] == VIOLATION for r in results) else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_status(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--status",
            type=Path,
            default=_DEFAULT_STATUS,
            help="path to cross-repo-status.json (default: repo-root copy)",
        )

    p_model = sub.add_parser("model", help="print the declared wave merge model")
    p_model.add_argument("phase", help="phase number (P)")
    p_model.add_argument("wave", help="wave number (M)")
    _add_status(p_model)
    p_model.set_defaults(func=_cmd_model)

    p_set = sub.add_parser("set", help="record the wave merge model at kickoff")
    p_set.add_argument("phase", help="phase number (P)")
    p_set.add_argument("wave", help="wave number (M)")
    p_set.add_argument("model", help=f"one of: {', '.join(MERGE_MODELS)}")
    _add_status(p_set)
    p_set.set_defaults(func=_cmd_set)

    p_reach = sub.add_parser(
        "reachability", help="mid-wave wave-branch reachability check (model-aware)"
    )
    p_reach.add_argument("phase", help="phase number (P)")
    p_reach.add_argument("wave", help="wave number (M)")
    p_reach.add_argument("--json", action="store_true", help="emit results as JSON")
    _add_status(p_reach)
    p_reach.set_defaults(func=_cmd_reachability)

    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except KeyError as exc:
        print(f"ERROR: missing key in cross-repo-status.json: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(
            f"ERROR: gh call failed (exit {exc.returncode}): {' '.join(exc.cmd)}\n{exc.stderr}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
