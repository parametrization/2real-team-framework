#!/usr/bin/env python3
"""Generic wave/iteration lifecycle state machine for the 2real framework.

The product-neutral extraction of the source project's wave orchestration
(``wave_seq`` + ``wave_merge_model`` + the wave-status counter writes). It owns
the **lifecycle state file** — the config'd ``paths.state_file`` (default
``.claude/state.json``) — and drives an iteration ("wave") through its phases:

    allocate -> start -> scope -> kickoff -> (work) -> wrapup

Three cooperating concerns, all persisted to the state file via the shared
``upsert_status_keys`` helper (so the file's compact-inline shape is preserved
and every write is JSON-validated before AND after):

  1. **Monotonic wave allocator** — a never-resetting ``global_wave_seq`` counter
     so two same-ordinal waves in different phases never collide on a
     ``wave_{N}_*`` key (the source project's main#804 design, genericised: no
     migration floor — a fresh project's first wave is 1). Reservation-aware: a
     ``wave_{N}_meta_issue`` written ahead of the counter is claimed, not
     skipped.
  2. **Lifecycle transitions** — ``start`` / ``scope`` / ``kickoff`` / ``wrapup``
     stamp the canonical ``wave_{W}_*`` keys + advance the ``current_wave`` /
     ``last_completed_wave`` pointers, each with an ISO-8601 UTC timestamp.
  3. **Merge model** — one model per wave (``direct-to-main`` | ``wave-branch``),
     declared at kickoff, plus a pure ``classify_reachability`` for the mid-wave
     stranding check.

State keys are bare ``wave_{W}_*`` (phase is a derived display attribute, never
part of the key) so the read side stays a simple top-level lookup.

Stdlib only. Pure helpers (allocator math, ``classify_reachability``) are I/O-
free and unit-tested directly; the thin SCM layer mirrors ``trust_signals`` /
``wave_status`` (explicit arg-list ``gh`` calls — no shell, no word-splitting).

CLI::

  lifecycle.py wave peek            [--state PATH]
  lifecycle.py wave allocate --phase P [--write] [--state PATH] [--floor N]
  lifecycle.py wave start    <W> [--at TS] [--state PATH]
  lifecycle.py wave scope    <W> --repos a,b,c [--phase P] [--at TS] [--state PATH]
  lifecycle.py wave kickoff  <W> [--merge-model M] [--at TS] [--state PATH]
  lifecycle.py wave assert-kickoff <W> [--state PATH]
  lifecycle.py wave wrapup   <W> [--pr-count N] [--cr-cycles N]
                                  [--concentration P] [--at TS] [--state PATH]
  lifecycle.py merge-model get <W> [--state PATH]
  lifecycle.py merge-model set <W> <model> [--state PATH]
  lifecycle.py state path   [--state PATH]
  lifecycle.py state show   [--state PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Shared helpers live in the framework's hooks/ + lib/ dirs. Mirror the
# lib->hooks import bridge that trust_signals.py / pr_ci_state.py use so the
# state machine stays importable wherever the framework is deployed.
_LIB_DIR = Path(__file__).resolve().parent
_HOOKS_DIR = _LIB_DIR.parent / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))
sys.path.insert(0, str(_LIB_DIR))

from _framework_config import config  # noqa: E402
from upsert_status_keys import main as _upsert_main  # noqa: E402

_GH_TIMEOUT = 60

# The two permitted merge models — a wave is exactly one for its whole lifetime.
DIRECT_TO_MAIN = "direct-to-main"
WAVE_BRANCH = "wave-branch"
MERGE_MODELS = (DIRECT_TO_MAIN, WAVE_BRANCH)

# Reachability severities (see classify_reachability).
OK = "ok"
ADVISORY = "advisory"
VIOLATION = "violation"

# Bare top-level ``wave_{X}_`` key. Trailing ``_`` so ``wave_4_`` matches
# ``wave_4_active`` but never ``wave_42_active``.
_WAVE_KEY_RE = re.compile(r"^wave_(\d+)_")


# ============================================================================
# State file resolution + persistence
# ============================================================================


def resolve_state_path(state_arg: str | Path | None = None) -> Path:
    """Resolve the lifecycle state file path.

    Explicit ``--state`` wins. Otherwise read ``paths.state_file`` from the
    framework config and resolve it relative to the config root (the dir holding
    ``.claude/framework.config.json``). Falls back to ``<cwd>/.claude/state.json``
    when no config is found (fail-open, matching the loader's posture).
    """
    if state_arg is not None:
        return Path(state_arg).expanduser()
    cfg = config()
    rel = cfg.get("paths.state_file", ".claude/state.json")
    if cfg.path is not None:
        root = cfg.path.parent.parent
    else:
        root = Path.cwd()
    return (root / rel).resolve()


def load_state(path: Path) -> dict:
    """Read the state file, returning {} if it is missing or empty."""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return {}
    if not text:
        return {}
    return json.loads(text)


def _json_literal(value) -> str:
    """Render a Python value as the compact JSON literal upsert expects."""
    return json.dumps(value, separators=(",", ":"))


def _initial_text(pairs: dict) -> str:
    """Render the FIRST write of an empty state file in the compact-inline shape.

    The ``upsert_status_keys`` helper extends an object that already has the
    ``{\\n  "k": v,\\n}`` one-key-per-line shape — it cannot seed an empty
    object (it would leave a trailing comma before ``}``). So the first write is
    rendered here directly, producing exactly that shape for later upserts.
    """
    items = list(pairs.items())
    lines = ["{"]
    for i, (k, v) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        lines.append(f'  "{k}": {_json_literal(v)}{comma}')
    lines.append("}")
    return "\n".join(lines) + "\n"


def persist(path: Path, pairs: dict) -> int:
    """Upsert ``pairs`` (key -> python value) into the state file.

    On the first write (missing or empty state file) the file is seeded directly
    in the compact-inline shape. Afterwards each write delegates to
    ``upsert_status_keys.main`` so that shape is preserved and the rewrite is
    JSON-validated before AND after. A no-op when ``pairs`` is empty.
    """
    if not pairs:
        return 0
    if not load_state(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_initial_text(pairs), encoding="utf-8")
        return 0
    argv = ["lifecycle", str(path)]
    for key, value in pairs.items():
        argv.append(f"{key}={_json_literal(value)}")
    return _upsert_main(argv)


def _now_iso(at: str | None = None) -> str:
    """An ISO-8601 UTC timestamp; ``at`` overrides for deterministic tests."""
    if at:
        return at
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ============================================================================
# Monotonic wave allocator (genericised wave_seq)
# ============================================================================


def existing_wave_numbers(state: dict) -> set[int]:
    """Every wave id appearing in a top-level ``wave_{X}_*`` key name."""
    out: set[int] = set()
    for key in state:
        m = _WAVE_KEY_RE.match(key)
        if m:
            out.add(int(m.group(1)))
    return out


def seed_value(state: dict, floor: int = 0) -> int:
    """Counter seed when ``global_wave_seq`` is absent.

    ``max(floor, highest existing wave id)`` — clears both the floor and any
    wave already recorded. A fresh project (floor 0, no waves) seeds 0, so the
    first allocated id is 1.
    """
    return max([floor, *existing_wave_numbers(state)])


def current_seq(state: dict, floor: int = 0) -> int:
    """Highest global id allocated so far (explicit scalar, else the seed)."""
    val = state.get("global_wave_seq")
    if isinstance(val, int):
        return max(val, seed_value(state, floor))
    return seed_value(state, floor)


def next_global_wave(state: dict, floor: int = 0) -> int:
    """Next monotonic wave id to allocate (never reused)."""
    return current_seq(state, floor) + 1


def reserved_wave(state: dict) -> int | None:
    """A wave id reserved (``wave_{N}_meta_issue``) ahead of the committed counter.

    A retro can reserve the next id by writing ``wave_{N}_meta_issue`` while the
    committed ``global_wave_seq`` is still N-1. A naive ``+1`` would skip it
    (the seed counts N as allocated). Detect: id one above the *explicit*
    counter whose meta-issue key already exists. Only the explicit scalar is
    consulted (using the seed would re-introduce the skip).
    """
    committed = state.get("global_wave_seq")
    if not isinstance(committed, int):
        return None
    candidate = committed + 1
    if f"wave_{candidate}_meta_issue" in state:
        return candidate
    return None


def allocation_target(state: dict, floor: int = 0) -> int:
    """The id ``peek`` / ``allocate`` will claim (reservation-aware)."""
    reserved = reserved_wave(state)
    return reserved if reserved is not None else next_global_wave(state, floor)


def phase_of(state: dict, wave: int) -> int | None:
    """Phase a recorded wave belongs to (``wave_{X}_phase``), or None."""
    direct = state.get(f"wave_{wave}_phase")
    if isinstance(direct, int):
        return direct
    return None


def phase_ordinal(state: dict, phase: int) -> int:
    """1-based position of the next wave WITHIN ``phase`` (count + 1)."""
    count = sum(1 for w in existing_wave_numbers(state) if phase_of(state, w) == phase)
    return count + 1


# ============================================================================
# Merge model (genericised wave_merge_model)
# ============================================================================


def validate_merge_model(model: str) -> str:
    """Return ``model`` if valid, else raise ValueError (typo-proofing)."""
    if model not in MERGE_MODELS:
        raise ValueError(
            f"invalid merge model {model!r}; expected one of {', '.join(MERGE_MODELS)}"
        )
    return model


def read_merge_model(state: dict, wave: str) -> str | None:
    """Return the declared ``wave_{W}_merge_model`` or None if absent."""
    val = state.get(f"wave_{wave}_merge_model")
    if val is None:
        return None
    return validate_merge_model(str(val))


def classify_reachability(
    model: str | None,
    *,
    branch_exists: bool,
    ahead_by: int,
    status: str,
    open_integration_pr: bool,
) -> tuple[str, str]:
    """Classify one repo's wave-branch-vs-main state against the declared model.

    Pure — no I/O. ``ahead_by`` / ``status`` come from the compare API for
    ``main...<wave-branch>``; ``open_integration_pr`` is whether an OPEN
    wave-branch->main PR exists. Returns ``(severity, message)``.
    """
    if not branch_exists:
        return OK, "no wave branch — nothing to reconcile (scope-drop or not yet created)"

    ahead = ahead_by > 0 or status == "diverged"
    if not ahead:
        return OK, f"wave branch reachable from main (ahead_by={ahead_by}, status={status})"

    if model == DIRECT_TO_MAIN:
        pr_note = (
            " (an integration PR is open — the wave has drifted to the wave-branch model)"
            if open_integration_pr
            else ""
        )
        return (
            VIOLATION,
            f"merge-model violation: {ahead_by} commit(s) on the wave branch under "
            f"declared '{DIRECT_TO_MAIN}' model — work was merged to the wave branch "
            f"instead of main (mixing prohibited){pr_note}",
        )

    if model == WAVE_BRANCH:
        if open_integration_pr:
            return (
                OK,
                f"{ahead_by} commit(s) ahead, tracked by an open integration PR — "
                f"healthy under '{WAVE_BRANCH}' model",
            )
        return (
            ADVISORY,
            f"{ahead_by} commit(s) on the wave branch not reachable from main and NO "
            f"open integration PR — normal mid-wave under '{WAVE_BRANCH}', but these "
            f"WILL strand unless the integration PR is opened at wrapup",
        )

    # model unrecorded — conservative wave-branch reading (advisory), nudge to declare.
    base = (
        f"{ahead_by} commit(s) on the wave branch not reachable from main; merge model "
        f"NOT declared at kickoff — record it via `lifecycle.py merge-model set`"
    )
    if open_integration_pr:
        return ADVISORY, base + " (an integration PR is open)"
    return ADVISORY, base + " — these may strand if no integration PR is opened at wrapup"


# ============================================================================
# Lifecycle transitions
# ============================================================================


def _wave_label(wave: str) -> str:
    return f"wave-{wave}"


def start_wave(path: Path, wave: str, *, at: str | None = None) -> int:
    """Mark a wave active and point ``current_wave`` at it."""
    ts = _now_iso(at)
    return persist(
        path,
        {
            "current_wave": _wave_label(wave),
            f"wave_{wave}_active": True,
            f"wave_{wave}_started_at": ts,
        },
    )


def scope_wave(
    path: Path, wave: str, repos: list[str], *, phase: int | None = None, at: str | None = None
) -> int:
    """Record the wave's in-scope repo list + a scope-reconciled timestamp."""
    pairs: dict = {
        f"wave_{wave}_repos_in_scope": repos,
        f"wave_{wave}_scope_reconciled_at": _now_iso(at),
    }
    if phase is not None:
        pairs[f"wave_{wave}_phase"] = phase
    return persist(path, pairs)


def kickoff_wave(
    path: Path, wave: str, *, merge_model: str | None = None, at: str | None = None
) -> int:
    """Record kickoff: timestamp, active+pointer, and (optionally) merge model."""
    pairs: dict = {
        "current_wave": _wave_label(wave),
        f"wave_{wave}_active": True,
        f"wave_{wave}_kicked_off_at": _now_iso(at),
    }
    if merge_model is not None:
        validate_merge_model(merge_model)
        pairs[f"wave_{wave}_merge_model"] = merge_model
    return persist(path, pairs)


def kickoff_persisted(state: dict, wave: str) -> tuple[bool, str]:
    """Verify ``kickoff_wave``'s state write actually landed (issue #168).

    Guards the exact Wave 1 failure mode: a wave can be officially kicked off
    (team spawned, branch cut, work underway) while the ``kickoff_wave`` state
    write is skipped or lost — so ``current_wave`` never advances and
    ``state.json`` sits un-stamped for the wave's entire life, discovered only
    at retro/wrapup reconciliation. Checks the three facts ``kickoff_wave``
    persists together: the ``current_wave`` pointer, the wave's ``_active``
    flag, and its ``_kicked_off_at`` timestamp. Pure — no I/O — so it is a real
    unit-testable guard; the CLI (``wave assert-kickoff``) and the wave-start
    skill's kickoff step both call it to fail loudly rather than silently
    proceeding un-stamped. Returns ``(ok, message)``; never raises.
    """
    label = _wave_label(wave)
    key_active = f"wave_{wave}_active"
    key_kicked = f"wave_{wave}_kicked_off_at"

    current = state.get("current_wave")
    active = state.get(key_active)
    kicked_at = state.get(key_kicked)

    problems = []
    if current != label:
        problems.append(f"current_wave is {current!r}, expected {label!r}")
    if active is not True:
        problems.append(f"{key_active} is {active!r}, expected true")
    if not kicked_at:
        problems.append(f"{key_kicked} is missing")

    if problems:
        return False, (
            f"wave {wave} kickoff was NOT persisted to state.json: "
            + "; ".join(problems)
            + ". A wave cannot proceed un-stamped (this is the Wave 1 failure mode — "
            "officially kicked off while state.json never advanced). Re-run "
            f"`lifecycle.py wave kickoff {wave}` and re-check with `wave assert-kickoff`."
        )
    return True, (
        f"wave {wave} kickoff persisted "
        f"(current_wave={label}, {key_active}=true, {key_kicked}={kicked_at})"
    )


def wrapup_wave(
    path: Path,
    wave: str,
    *,
    pr_count: int | None = None,
    cr_cycles: int | None = None,
    concentration: int | None = None,
    at: str | None = None,
) -> int:
    """Close a wave: counters, deactivate, completed-at, advance last-completed."""
    pairs: dict = {
        f"wave_{wave}_active": False,
        f"wave_{wave}_completed_at": _now_iso(at),
        "last_completed_wave": _wave_label(wave),
    }
    if pr_count is not None:
        pairs[f"wave_{wave}_final_pr_count"] = pr_count
    if cr_cycles is not None:
        pairs[f"wave_{wave}_changes_requested_cycles"] = cr_cycles
    if concentration is not None:
        pairs[f"wave_{wave}_top_concentration_pct"] = concentration
    return persist(path, pairs)


# ============================================================================
# CLI
# ============================================================================


def _cmd_wave_peek(args: argparse.Namespace) -> int:
    state = load_state(resolve_state_path(args.state))
    print(allocation_target(state, args.floor))
    return 0


def _cmd_wave_allocate(args: argparse.Namespace) -> int:
    path = resolve_state_path(args.state)
    state = load_state(path)
    wave_id = allocation_target(state, args.floor)
    ordinal = phase_ordinal(state, args.phase)
    print(f"wave id: {wave_id}")
    print(f"phase: {args.phase}  ordinal: {ordinal}  (display: Phase {args.phase}, Wave {ordinal})")
    if not args.write:
        print("(dry-run — pass --write to persist global_wave_seq + phase stamps)")
        return 0
    return persist(
        path,
        {
            "global_wave_seq": wave_id,
            f"wave_{wave_id}_phase": args.phase,
            f"wave_{wave_id}_phase_ordinal": ordinal,
        },
    )


def _cmd_wave_start(args: argparse.Namespace) -> int:
    return start_wave(resolve_state_path(args.state), args.wave, at=args.at)


def _cmd_wave_scope(args: argparse.Namespace) -> int:
    repos = [r.strip() for r in args.repos.split(",") if r.strip()]
    return scope_wave(resolve_state_path(args.state), args.wave, repos, phase=args.phase, at=args.at)


def _cmd_wave_kickoff(args: argparse.Namespace) -> int:
    return kickoff_wave(
        resolve_state_path(args.state), args.wave, merge_model=args.merge_model, at=args.at
    )


def _cmd_wave_assert_kickoff(args: argparse.Namespace) -> int:
    state = load_state(resolve_state_path(args.state))
    ok, message = kickoff_persisted(state, args.wave)
    if ok:
        print(message)
        return 0
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def _cmd_wave_wrapup(args: argparse.Namespace) -> int:
    return wrapup_wave(
        resolve_state_path(args.state),
        args.wave,
        pr_count=args.pr_count,
        cr_cycles=args.cr_cycles,
        concentration=args.concentration,
        at=args.at,
    )


def _cmd_merge_model_get(args: argparse.Namespace) -> int:
    state = load_state(resolve_state_path(args.state))
    model = read_merge_model(state, args.wave)
    if model is None:
        print(
            f"ERROR: wave_{args.wave}_merge_model not recorded. Declare it at kickoff "
            f"(one of: {', '.join(MERGE_MODELS)}).",
            file=sys.stderr,
        )
        return 1
    print(model)
    return 0


def _cmd_merge_model_set(args: argparse.Namespace) -> int:
    validate_merge_model(args.model)
    return persist(resolve_state_path(args.state), {f"wave_{args.wave}_merge_model": args.model})


def _cmd_state_path(args: argparse.Namespace) -> int:
    print(resolve_state_path(args.state))
    return 0


def _cmd_state_show(args: argparse.Namespace) -> int:
    print(json.dumps(load_state(resolve_state_path(args.state)), indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    top = parser.add_subparsers(dest="group", required=True)

    def _state_opt(p: argparse.ArgumentParser) -> None:
        p.add_argument("--state", default=None, help="state file path (default: config paths.state_file)")

    # wave ...
    wave = top.add_parser("wave", help="wave allocator + lifecycle transitions")
    wsub = wave.add_subparsers(dest="command", required=True)

    p = wsub.add_parser("peek", help="print the next wave id (no write)")
    p.add_argument("--floor", type=int, default=0, help="minimum wave id (default 0 → first wave is 1)")
    _state_opt(p)
    p.set_defaults(func=_cmd_wave_peek)

    p = wsub.add_parser("allocate", help="allocate the next wave id for a phase")
    p.add_argument("--phase", type=int, required=True)
    p.add_argument("--floor", type=int, default=0)
    p.add_argument("--write", action="store_true", help="persist global_wave_seq + phase stamps")
    _state_opt(p)
    p.set_defaults(func=_cmd_wave_allocate)

    p = wsub.add_parser("start", help="mark a wave active + point current_wave at it")
    p.add_argument("wave")
    p.add_argument("--at", default=None, help="ISO timestamp override (deterministic)")
    _state_opt(p)
    p.set_defaults(func=_cmd_wave_start)

    p = wsub.add_parser("scope", help="record repos_in_scope + scope_reconciled_at")
    p.add_argument("wave")
    p.add_argument("--repos", required=True, help="comma-separated repo list")
    p.add_argument("--phase", type=int, default=None)
    p.add_argument("--at", default=None)
    _state_opt(p)
    p.set_defaults(func=_cmd_wave_scope)

    p = wsub.add_parser("kickoff", help="record kicked_off_at (+ optional merge model)")
    p.add_argument("wave")
    p.add_argument("--merge-model", dest="merge_model", default=None, choices=MERGE_MODELS)
    p.add_argument("--at", default=None)
    _state_opt(p)
    p.set_defaults(func=_cmd_wave_kickoff)

    p = wsub.add_parser(
        "assert-kickoff",
        help="fail loudly (exit 1) if kickoff's state write did not persist (#168)",
    )
    p.add_argument("wave")
    _state_opt(p)
    p.set_defaults(func=_cmd_wave_assert_kickoff)

    p = wsub.add_parser("wrapup", help="close a wave: counters + completed_at")
    p.add_argument("wave")
    p.add_argument("--pr-count", dest="pr_count", type=int, default=None)
    p.add_argument("--cr-cycles", dest="cr_cycles", type=int, default=None)
    p.add_argument("--concentration", type=int, default=None, help="top-author concentration pct")
    p.add_argument("--at", default=None)
    _state_opt(p)
    p.set_defaults(func=_cmd_wave_wrapup)

    # merge-model ...
    mm = top.add_parser("merge-model", help="per-wave merge model get/set")
    msub = mm.add_subparsers(dest="command", required=True)
    p = msub.add_parser("get", help="print the declared merge model")
    p.add_argument("wave")
    _state_opt(p)
    p.set_defaults(func=_cmd_merge_model_get)
    p = msub.add_parser("set", help="record the merge model")
    p.add_argument("wave")
    p.add_argument("model", choices=MERGE_MODELS)
    _state_opt(p)
    p.set_defaults(func=_cmd_merge_model_set)

    # state ...
    st = top.add_parser("state", help="inspect the state file")
    ssub = st.add_subparsers(dest="command", required=True)
    p = ssub.add_parser("path", help="print the resolved state file path")
    _state_opt(p)
    p.set_defaults(func=_cmd_state_path)
    p = ssub.add_parser("show", help="dump the state file")
    _state_opt(p)
    p.set_defaults(func=_cmd_state_show)

    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: subprocess failed (exit {exc.returncode})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
