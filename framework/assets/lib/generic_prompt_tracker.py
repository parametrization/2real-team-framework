#!/usr/bin/env python3
"""Durable ledger of per-artifact genericize/skip decisions (#102, P0).

The generic extraction of noorinalabs's ``generic_prompt_ledger.json`` +
``lib/generic_prompt_tracker.py`` (see ``framework/recipes/NOORINALABS_RECONCILE.md``
§3a). 2real had nothing equivalent: a record of which touched ``.claude/`` artifacts
have been considered for promotion into ``framework/assets/**`` (genericized),
deliberately skipped, or are still pending a call.

Two cooperating layers, mirroring ``lifecycle.py`` / ``trust_signals.py``:

  * **State** — the ledger file itself (config'd ``paths.generic_prompt_ledger``,
    default ``.claude/generic_prompt_ledger.json``): ``{"version": 1, "candidates":
    {<artifact-relpath>: {"decided_at", "decision", "detail", "wave"}}}``. Writes
    delegate to :func:`lifecycle.persist`, which seeds the FIRST write directly in
    the compact-inline shape (an empty/missing file cannot be upserted into — see
    ``.claude/memory/project_upsert_status_keys_seeding.md``) and JSON-validates
    every write thereafter.
  * **Pure helpers** — :func:`pending_candidates` / :func:`decided_candidates` /
    :func:`load_ledger` operate on an already-loaded ledger dict, no I/O, so the
    ``promotion-audit`` skill's classification logic can unit-test against a
    hand-built ledger without touching disk.

``decision`` is one of ``"pending"`` (default; not yet reviewed), ``"genericized"``
(promoted into ``framework/assets/**``), or ``"skip"`` (deliberately project-
specific — never promoted).

Fail-open: a missing/corrupt/non-object ledger file reads back as the seeded empty
shape rather than raising — this module is invoked from a PostToolUse hook
(:mod:`suggest_generic_prompt`) that must never crash a tool call.

CLI:
  generic_prompt_tracker.py touch  <artifact> [--ledger PATH]
      Silent first-touch record: inserts a ``pending`` entry ONLY if the artifact
      has no existing entry. A no-op (never overwrites) when one is already present
      — used by the PostToolUse hook so re-editing an already-decided artifact
      never resets it back to pending.
  generic_prompt_tracker.py record <artifact> --decision D [--detail T] [--wave W]
                                    [--at TS] [--ledger PATH]
      Upsert (always overwrites) one artifact's decision — used by the
      promotion-audit skill to finalize a call.
  generic_prompt_tracker.py show    [--ledger PATH]
  generic_prompt_tracker.py pending [--ledger PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Shared helpers live in the framework's hooks/ + lib/ dirs. Mirror the lib->hooks
# import bridge that trust_signals.py / lifecycle.py use so this stays importable
# wherever the framework is deployed (source tree AND an installed .claude/ tree).
_LIB_DIR = Path(__file__).resolve().parent
_HOOKS_DIR = _LIB_DIR.parent / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))
sys.path.insert(0, str(_LIB_DIR))

from _framework_config import config  # noqa: E402
from lifecycle import persist as _persist_state  # noqa: E402

# The three permitted decisions. "pending" is the only one a silent touch may write.
PENDING = "pending"
GENERICIZED = "genericized"
SKIP = "skip"
DECISIONS = (PENDING, GENERICIZED, SKIP)


def _empty_ledger() -> dict:
    """A FRESH seeded-shape dict (never a shared reference — see #102 review note:
    a module-level constant here would have its nested ``candidates`` dict mutated
    in place by every caller that hits the fallback path, silently cross-
    contaminating unrelated ledgers)."""
    return {"version": 1, "candidates": {}}


def _now_iso(at: str | None = None) -> str:
    """An ISO-8601 UTC timestamp; ``at`` overrides for deterministic tests."""
    if at:
        return at
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_ledger_path(cfg=None) -> Path | None:
    """The configured ledger path, resolved against the repo root. None if no config."""
    cfg = cfg or config()
    if cfg.path is None:
        return None
    rel = cfg.get("paths.generic_prompt_ledger", ".claude/generic_prompt_ledger.json")
    return cfg.path.parent.parent / rel


def load_ledger(path: str | Path) -> dict:
    """Read the ledger file. Fail-open: missing/corrupt/non-object -> the seeded shape.

    Never raises — a hook that reads this must never crash the tool call.
    """
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return _empty_ledger()
    if not text:
        return _empty_ledger()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return _empty_ledger()
    if not isinstance(data, dict):
        return _empty_ledger()
    data.setdefault("version", 1)
    if not isinstance(data.get("candidates"), dict):
        data["candidates"] = {}
    return data


def pending_candidates(ledger: dict) -> dict:
    """Pure: the subset of ``ledger["candidates"]`` still awaiting a decision."""
    return {k: v for k, v in ledger.get("candidates", {}).items() if v.get("decision") == PENDING}


def decided_candidates(ledger: dict) -> dict:
    """Pure: the subset of ``ledger["candidates"]`` already decided (not pending)."""
    return {
        k: v for k, v in ledger.get("candidates", {}).items() if v.get("decision") != PENDING
    }


def record_candidate(
    ledger_path: str | Path,
    artifact: str,
    *,
    decision: str = PENDING,
    detail: str = "",
    wave: str | int | None = None,
    at: str | None = None,
    skip_if_present: bool = False,
) -> dict:
    """Upsert one artifact's ledger entry. Returns the full updated ledger dict.

    ``skip_if_present=True`` is the silent-touch mode the PostToolUse hook uses: if
    ``artifact`` already carries ANY entry (pending, genericized, or skip), the call
    is a no-op — an already-decided artifact is never reset back to pending, and a
    file edited repeatedly does not keep re-triggering writes.
    """
    if decision not in DECISIONS:
        decision = PENDING
    ledger_path = Path(ledger_path)
    ledger = load_ledger(ledger_path)
    candidates = ledger["candidates"]
    if skip_if_present and artifact in candidates:
        return ledger
    candidates[artifact] = {
        "decided_at": _now_iso(at),
        "decision": decision,
        "detail": detail,
        "wave": wave,
    }
    _persist_state(
        ledger_path, {"version": ledger.get("version", 1), "candidates": candidates}
    )
    return ledger


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli_ledger_path(args: argparse.Namespace) -> Path:
    if args.ledger:
        return Path(args.ledger)
    resolved = default_ledger_path()
    if resolved is None:
        print(
            "ERROR: --ledger (or a resolvable paths.generic_prompt_ledger config) is required",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return resolved


def _cmd_touch(args: argparse.Namespace) -> int:
    ledger = record_candidate(_cli_ledger_path(args), args.artifact, skip_if_present=True)
    print(json.dumps(ledger["candidates"].get(args.artifact, {}), indent=2, sort_keys=True))
    return 0


def _cmd_record(args: argparse.Namespace) -> int:
    ledger = record_candidate(
        _cli_ledger_path(args),
        args.artifact,
        decision=args.decision,
        detail=args.detail or "",
        wave=args.wave,
        at=args.at,
    )
    print(json.dumps(ledger["candidates"][args.artifact], indent=2, sort_keys=True))
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    ledger = load_ledger(_cli_ledger_path(args))
    print(json.dumps(ledger, indent=2, sort_keys=True))
    return 0


def _cmd_pending(args: argparse.Namespace) -> int:
    ledger = load_ledger(_cli_ledger_path(args))
    print(json.dumps(pending_candidates(ledger), indent=2, sort_keys=True))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_ledger_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--ledger",
            default=None,
            help="path to the ledger file (default: configured paths.generic_prompt_ledger)",
        )

    p_touch = sub.add_parser("touch", help="silent first-touch: pending if absent, else no-op")
    p_touch.add_argument("artifact", help="repo-relative artifact path")
    _add_ledger_arg(p_touch)
    p_touch.set_defaults(func=_cmd_touch)

    p_record = sub.add_parser("record", help="upsert (always overwrites) a decision")
    p_record.add_argument("artifact", help="repo-relative artifact path")
    p_record.add_argument("--decision", choices=DECISIONS, default=PENDING)
    p_record.add_argument("--detail", default="")
    p_record.add_argument("--wave", default=None)
    p_record.add_argument("--at", default=None, help="ISO-8601 UTC timestamp override (tests)")
    _add_ledger_arg(p_record)
    p_record.set_defaults(func=_cmd_record)

    p_show = sub.add_parser("show", help="print the full ledger")
    _add_ledger_arg(p_show)
    p_show.set_defaults(func=_cmd_show)

    p_pending = sub.add_parser("pending", help="print only pending candidates")
    _add_ledger_arg(p_pending)
    p_pending.set_defaults(func=_cmd_pending)

    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
