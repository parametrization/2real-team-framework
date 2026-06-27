#!/usr/bin/env python3
"""Generic-prompt candidate tracker — the state backbone for the batched
wave-lifecycle genericize checkpoint (main#716).

Background — why this exists
----------------------------
The ``suggest_generic_prompt`` PostToolUse hook used to emit a
``[Generic Prompt Suggestion]`` ``systemMessage`` on *every* ``.claude/`` edit.
A ``systemMessage`` is non-binding background the harness (correctly) passes
over mid-task, the hook wrote **no state**, had **no dedup**, and never closed
the loop — classic enforcement-hierarchy decay. Evidence: across every wave
since the framework bootstrap, ``2real-team-framework/generic_prompts/`` gained
**zero** files despite the nudge firing constantly.

This module moves the concern *up* the enforcement hierarchy (memory →
charter → skill → hook), from a per-edit nudge to a **batched, tracked
checkpoint** run once per wave at ``/wave-wrapup``:

1. The demoted hook (:mod:`suggest_generic_prompt`) silently records every
   touched ``.claude/`` artifact into the **pending ledger** and returns
   ``None`` — no mid-task noise.
2. The ``/wave-wrapup`` checkpoint calls :func:`undecided_candidates` to list
   pending artifacts that are genericizable AND not already decided, presents
   them in ONE deliberate pass, and records a genericize/skip verdict for each
   via :func:`record_decision`.
3. Decisions live in the **decisions ledger** (version-controlled) so the same
   artifact is never re-surfaced once decided — the closing loop the
   systemMessage never had.

Two state files (see § Two ledgers)
-----------------------------------
- ``.claude/generic_prompt_pending.json`` — volatile, gitignored, per-machine.
  The candidate set fed by the silent hook (and, at checkpoint time, by a
  git-diff sweep of the wave's ``.claude/`` changes). Safe to delete; it
  rebuilds from edits / the diff sweep.
- ``.claude/generic_prompt_ledger.json`` — **version-controlled**. The durable
  cross-wave genericize/skip decisions, keyed by artifact rel-path. This is the
  dedup memory; it MUST be committed (decisions are durable team state).

"Lacks a counterpart" semantics
--------------------------------
``2real-team-framework/generic_prompts/`` files have no deterministic name
mapping back to a ``.claude/`` artifact, so counterpart detection is anchored on
the **decisions ledger**, not on framework filename matching: an artifact "has a
counterpart" iff the ledger records ``decision == "genericized"`` for it AND the
referenced generic file still exists. Any other state (skipped, or undecided)
means it has no live counterpart. Both ``genericized`` and ``skipped`` suppress
re-surfacing (AC3); only *undecided* genericizable artifacts surface at the
checkpoint (AC1). This errs toward surfacing if framework state drifts, which is
the safe direction for a checkpoint whose whole purpose is to catch omissions.

CLI (used by the /wave-wrapup step)
-----------------------------------
  ``python3 generic_prompt_tracker.py record-candidate <file_path>``
      Silently upsert a touched ``.claude/`` path into the pending ledger.
  ``python3 generic_prompt_tracker.py list [--wave W] [--json]``
      Print undecided genericizable candidates (the checkpoint worklist).
  ``python3 generic_prompt_tracker.py record <rel_path> <genericized|skipped>
        [--detail TEXT] [--wave W]``
      Record a durable decision (removes the path from pending).

Exit codes: 0 on success, 2 on usage error, 1 on unexpected failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# .claude/lib/generic_prompt_tracker.py -> lib -> .claude -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LEDGER_PATH = REPO_ROOT / ".claude" / "generic_prompt_ledger.json"
PENDING_PATH = REPO_ROOT / ".claude" / "generic_prompt_pending.json"
FRAMEWORK_REPO = REPO_ROOT.parent / "2real-team-framework"
GENERIC_PROMPTS_DIR = FRAMEWORK_REPO / "generic_prompts"

# Paths under .claude/ that are tracker-managed churn, never genericize
# candidates. Mirrors the historical suggest_generic_prompt skip-list so the
# silent hook and this module agree on what is noise.
SKIP_PATTERNS = (
    "ontology/checksums.json",
    "annunaki/errors.jsonl",
)

# Rel-path PREFIXES that are never genericize candidates — whole subtrees under
# .claude/ that hold ephemeral or project-private content, not reusable
# framework artifacts. Checked against the NORMALIZED rel-path only (NOT the raw
# file_path), so a real artifact merely *edited inside a worktree*
# (.../worktrees/<wt>/.claude/hooks/foo.py, which collapses to rel "hooks/foo.py")
# is still tracked, while a path that normalizes TO "worktrees/<wt>/..." (a
# transient worktree file), "memory/..." (project-private memory notes), or
# "scratch..." (transient scratch) is dropped. Closes the Step-12.5 noise inflow
# (P7W19: 117 of 270 pending candidates were worktree/memory/scratch churn).
SKIP_REL_PREFIXES = (
    "worktrees/",
    "memory/",
    "scratch",
)

# Artifact classification — the same category taxonomy the per-edit hook used,
# now centralized here so the hook can record minimally and the checkpoint can
# present a meaningful "what kind of generic prompt would this be" hint.
CATEGORY_MAP: dict[str, dict[str, str]] = {
    "hook": {
        "pattern": "/hooks/",
        "prompt_type": "hook",
        "suggestion": "a product-neutral hook that enforces the same pattern",
    },
    "skill": {
        "pattern": "/skills/",
        "prompt_type": "skill",
        "suggestion": "a product-neutral skill prompt that provides the same workflow",
    },
    "charter": {
        "pattern": "/team/charter",
        "prompt_type": "charter section",
        "suggestion": "a product-neutral charter template section",
    },
    "settings": {
        "pattern": "settings.json",
        "prompt_type": "settings template",
        "suggestion": "a product-neutral settings.json snippet or template",
    },
}
_FALLBACK_CATEGORY = {
    "prompt_type": "configuration",
    "suggestion": "a product-neutral version of this configuration",
}

LEDGER_VERSION = 1
_VALID_DECISIONS = ("genericized", "skipped")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_rel_path(file_path: str) -> str | None:
    """Return the path *relative to ``.claude/``* for a tracked artifact, or
    ``None`` when the path is not a genericize candidate.

    ``None`` is returned for: empty paths, paths not under ``.claude/``, and
    skip-listed tracker churn (``ontology/checksums.json`` etc.). A returned
    value is always the rel-path *after* the final ``/.claude/`` segment so it
    is stable across absolute paths, worktree-nested paths, and bare
    ``.claude/...`` paths.
    """
    if not file_path:
        return None
    # Worktrees live under .claude/worktrees/<wt>/.claude/... — splitting on the
    # LAST /.claude/ yields the artifact path inside the (worktree's) repo, not
    # the worktree-relative prefix.
    marker = "/.claude/"
    if marker in file_path:
        rel = file_path.rsplit(marker, 1)[-1]
    elif file_path.startswith(".claude/"):
        rel = file_path[len(".claude/") :]
    else:
        return None
    if not rel:
        return None
    if any(p in rel or p in file_path for p in SKIP_PATTERNS):
        return None
    # Whole-subtree noise (worktrees/ memory/ scratch) — checked against the
    # normalized rel only, so a real artifact edited inside a worktree (which
    # collapses to its inner rel like "hooks/foo.py") is still tracked.
    if any(rel.startswith(pfx) for pfx in SKIP_REL_PREFIXES):
        return None
    # The pending/decisions ledgers themselves are under .claude/ — never track
    # the tracker's own state files, or the checkpoint would surface itself.
    if rel in ("generic_prompt_pending.json", "generic_prompt_ledger.json"):
        return None
    return rel


def classify(rel_path: str) -> dict[str, str]:
    """Classify a ``.claude/`` rel-path into a generic-prompt category.

    Returns a dict with ``category`` (key into :data:`CATEGORY_MAP` or
    ``"configuration"``), ``prompt_type``, and ``suggestion``.
    """
    for name, info in CATEGORY_MAP.items():
        if info["pattern"] in rel_path or info["pattern"] in f"/{rel_path}":
            return {
                "category": name,
                "prompt_type": info["prompt_type"],
                "suggestion": info["suggestion"],
            }
    return {"category": "configuration", **_FALLBACK_CATEGORY}


# --------------------------------------------------------------------------- #
# JSON state I/O
# --------------------------------------------------------------------------- #
def _load_json(path: Path, default: dict) -> dict:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return dict(default)
    except (json.JSONDecodeError, OSError):
        # Corrupt/unreadable state must never crash the silent hook nor the
        # checkpoint — start from the default and let the next write heal it.
        return dict(default)
    if not isinstance(data, dict):
        return dict(default)
    return data


def load_pending(pending_path: Path = PENDING_PATH) -> dict:
    data = _load_json(pending_path, {"version": LEDGER_VERSION, "candidates": {}})
    data.setdefault("candidates", {})
    return data


def save_pending(data: dict, pending_path: Path = PENDING_PATH) -> None:
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def load_ledger(ledger_path: Path = LEDGER_PATH) -> dict:
    data = _load_json(ledger_path, {"version": LEDGER_VERSION, "decisions": {}})
    data.setdefault("decisions", {})
    return data


def save_ledger(data: dict, ledger_path: Path = LEDGER_PATH) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


# --------------------------------------------------------------------------- #
# Recording
# --------------------------------------------------------------------------- #
def record_candidate(
    file_path: str,
    *,
    pending_path: Path = PENDING_PATH,
    ledger_path: Path = LEDGER_PATH,
    now: str | None = None,
) -> bool:
    """Silently upsert a touched ``.claude/`` artifact into the pending ledger.

    This is the entry point the demoted :mod:`suggest_generic_prompt` hook
    calls on every Edit/Write. Returns ``True`` if the path was recorded (a
    tracked, non-skip, not-yet-decided genericize candidate), ``False``
    otherwise. Already-decided artifacts are NOT re-added — once the ledger has
    a verdict the candidate stays settled (AC3).

    Never raises for ordinary state issues; the caller (a PostToolUse hook) is
    advisory and must not crash dispatch.
    """
    rel = normalize_rel_path(file_path)
    if rel is None:
        return False
    # Settled artifacts (genericized or skipped) are not re-surfaced.
    if rel in load_ledger(ledger_path).get("decisions", {}):
        return False

    now = now or _now_iso()
    pending = load_pending(pending_path)
    candidates = pending["candidates"]
    entry = candidates.get(rel)
    info = classify(rel)
    if entry is None:
        candidates[rel] = {
            "category": info["category"],
            "first_seen": now,
            "last_seen": now,
            "count": 1,
        }
    else:
        entry["category"] = info["category"]
        entry["last_seen"] = now
        entry["count"] = int(entry.get("count", 0)) + 1
    save_pending(pending, pending_path)
    return True


def record_decision(
    rel_path: str,
    decision: str,
    *,
    detail: str = "",
    wave: str = "",
    ledger_path: Path = LEDGER_PATH,
    pending_path: Path = PENDING_PATH,
    now: str | None = None,
) -> dict:
    """Record a durable genericize/skip decision for ``rel_path`` and drop it
    from the pending set. ``decision`` must be ``"genericized"`` or
    ``"skipped"``. Returns the stored decision record.
    """
    if decision not in _VALID_DECISIONS:
        raise ValueError(f"decision must be one of {_VALID_DECISIONS}, got {decision!r}")
    rel = normalize_rel_path(rel_path) or rel_path
    now = now or _now_iso()
    ledger = load_ledger(ledger_path)
    record = {
        "decision": decision,
        "detail": detail,
        "wave": wave,
        "decided_at": now,
    }
    ledger["decisions"][rel] = record
    save_ledger(ledger, ledger_path)

    # Settle: remove from pending so it never re-surfaces.
    pending = load_pending(pending_path)
    if rel in pending["candidates"]:
        del pending["candidates"][rel]
        save_pending(pending, pending_path)
    return record


def _has_live_counterpart(
    rel: str,
    ledger: dict,
    framework_dir: Path,
) -> bool:
    """An artifact has a live counterpart iff the ledger records it as
    ``genericized`` AND the referenced generic file still exists. See the
    module docstring § "Lacks a counterpart" semantics."""
    rec = ledger.get("decisions", {}).get(rel)
    if not rec or rec.get("decision") != "genericized":
        return False
    detail = (rec.get("detail") or "").strip()
    if not detail:
        # Genericized but no file pointer recorded — treat as decided (it is in
        # the ledger so it won't surface) but not as a verifiable counterpart.
        return True
    candidate = Path(detail)
    if not candidate.is_absolute():
        candidate = framework_dir / detail
    return candidate.exists()


def undecided_candidates(
    *,
    pending_path: Path = PENDING_PATH,
    ledger_path: Path = LEDGER_PATH,
    framework_dir: Path = GENERIC_PROMPTS_DIR,
) -> list[dict]:
    """The checkpoint worklist: pending candidates that are NOT yet decided in
    the ledger (AC1 — lack a counterpart; AC3 — decided ones are excluded).

    Returns a list of dicts ``{rel_path, category, prompt_type, suggestion,
    count, first_seen}`` sorted by category then rel_path for stable
    presentation.
    """
    pending = load_pending(pending_path)
    ledger = load_ledger(ledger_path)
    decided = ledger.get("decisions", {})

    out: list[dict] = []
    for rel, entry in pending.get("candidates", {}).items():
        if rel in decided:
            # Already settled (covers both skipped and genericized).
            continue
        if _has_live_counterpart(rel, ledger, framework_dir):
            continue
        info = classify(rel)
        out.append(
            {
                "rel_path": rel,
                "category": info["category"],
                "prompt_type": info["prompt_type"],
                "suggestion": info["suggestion"],
                "count": int(entry.get("count", 0)) if isinstance(entry, dict) else 0,
                "first_seen": entry.get("first_seen", "") if isinstance(entry, dict) else "",
            }
        )
    out.sort(key=lambda c: (c["category"], c["rel_path"]))
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _cmd_record_candidate(args: argparse.Namespace) -> int:
    recorded = record_candidate(args.file_path)
    print(f"recorded: {recorded} ({args.file_path})")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    candidates = undecided_candidates()
    if args.json:
        print(json.dumps(candidates, indent=2))
        return 0
    if not candidates:
        print(
            "Generic-prompt checkpoint: no undecided candidates — nothing to genericize this wave."
        )
        return 0
    print(f"Generic-prompt checkpoint — {len(candidates)} undecided artifact(s):")
    print("")
    for c in candidates:
        print(f"  [{c['category']}] .claude/{c['rel_path']}")
        print(f"      → candidate for {c['suggestion']}")
        print(f"      (seen {c['count']}x since {c['first_seen'] or 'unknown'})")
    print("")
    print("For each: decide genericize or skip, then record the decision:")
    print(
        "  python3 .claude/lib/generic_prompt_tracker.py record <rel_path> "
        "<genericized|skipped> --detail <file-or-reason> --wave <W>"
    )
    return 0


def _cmd_record(args: argparse.Namespace) -> int:
    try:
        rec = record_decision(
            args.rel_path,
            args.decision,
            detail=args.detail or "",
            wave=args.wave or "",
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        f"recorded decision for {args.rel_path}: {rec['decision']} "
        f"(detail={rec['detail']!r}, wave={rec['wave']!r})"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generic_prompt_tracker",
        description="Track + decide generic-prompt candidates for the wave checkpoint (main#716).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_rc = sub.add_parser(
        "record-candidate", help="silently upsert a touched .claude/ path into pending"
    )
    p_rc.add_argument("file_path")
    p_rc.set_defaults(func=_cmd_record_candidate)

    p_list = sub.add_parser("list", help="print undecided genericizable candidates")
    p_list.add_argument("--wave", default="", help="wave label (informational)")
    p_list.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    p_list.set_defaults(func=_cmd_list)

    p_rec = sub.add_parser("record", help="record a durable genericize/skip decision")
    p_rec.add_argument("rel_path")
    p_rec.add_argument("decision", choices=_VALID_DECISIONS)
    p_rec.add_argument(
        "--detail", default="", help="generic file path (genericized) or skip reason"
    )
    p_rec.add_argument("--wave", default="", help="wave label this decision was made in")
    p_rec.set_defaults(func=_cmd_record)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
