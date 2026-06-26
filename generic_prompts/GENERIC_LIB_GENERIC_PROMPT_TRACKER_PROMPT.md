# Generic Lib Prompt: Batched Decision-Checkpoint Ledger

## Purpose

Replace a noisy, never-closed **per-event nudge** with a **batched, tracked
checkpoint** that runs once per cycle and remembers its decisions forever. The
failure it fixes is classic enforcement-hierarchy decay: a hook that fired a
non-binding suggestion on every relevant edit, wrote no state, had no dedup, and
never closed the loop — so the suggested work accumulated zero output despite the
nudge firing constantly.

The pattern moves the concern *up* the hierarchy (memory → charter → skill →
hook): the demoted hook silently records candidates into a ledger and returns
nothing (no mid-task noise); a once-per-cycle checkpoint lists the *undecided*
candidates in one deliberate pass and records a decision for each; decided items
never resurface.

## Reusable Pattern

- **Two ledgers, two lifetimes:**
  - a **pending** file — volatile, gitignored, per-machine: the candidate set fed
    by the silent hook (and, at checkpoint time, optionally by a diff sweep). Safe
    to delete; it rebuilds.
  - a **decisions** file — *version-controlled*: durable cross-cycle verdicts keyed
    by candidate id. This is the dedup memory and MUST be committed (decisions are
    durable team state).
- **Silent recording.** The hook entry point upserts a candidate and returns a
  bool; it never raises for ordinary state issues (it runs inside an advisory hook
  that must not crash dispatch). Already-decided candidates are NOT re-added.
- **Normalize the candidate id** to something stable across absolute paths,
  nested/worktree paths, and bare relative paths. Drop known churn (tool state
  files, the ledgers themselves) and whole noise subtrees (worktrees, private
  notes, scratch) at normalization time.
- **Counterpart semantics anchored on the decisions ledger**, not on filename
  matching to the output dir (outputs often have no deterministic name mapping
  back). A candidate "has a live counterpart" iff the ledger records it as
  *done* AND the referenced output still exists; any other state surfaces. Err
  toward surfacing if state drifts — the safe direction for an omission-catcher.
- **Corrupt/missing state heals** to a default rather than crashing.

## Algorithm

- `record_candidate(path)`: normalize → drop if not a candidate → drop if already
  in decisions → upsert into pending (first_seen/last_seen/count).
- `record_decision(id, verdict, detail, cycle)`: write to decisions ledger; remove
  from pending so it never resurfaces. Verdict ∈ {done, skipped} — both settle it.
- `undecided_candidates()`: pending entries not in decisions and lacking a live
  counterpart, sorted for stable presentation — the checkpoint worklist.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Batched decision-checkpoint ledger: a pending set (volatile) + a decisions
ledger (version-controlled) so a once-per-cycle checkpoint never re-surfaces a
settled item."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = ROOT / "decisions_ledger.json"      # version-controlled
PENDING_PATH = ROOT / "decisions_pending.json"    # gitignored, per-machine
OUTPUT_DIR = ROOT.parent / "outputs"

SKIP_SUBSTRINGS = ("tool_state.json",)
SKIP_PREFIXES = ("worktrees/", "notes/", "scratch")
_VALID = ("done", "skipped")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_id(path: str) -> str | None:
    if not path:
        return None
    marker = "/work/"  # collapse nested/worktree paths to the inner rel path
    rel = path.rsplit(marker, 1)[-1] if marker in path else path
    if any(s in rel for s in SKIP_SUBSTRINGS):
        return None
    if any(rel.startswith(p) for p in SKIP_PREFIXES):
        return None
    if rel in ("decisions_pending.json", "decisions_ledger.json"):
        return None
    return rel or None


def _load(path: Path, default: dict) -> dict:
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(default)
    return data if isinstance(data, dict) else dict(default)


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def load_pending() -> dict:
    d = _load(PENDING_PATH, {"candidates": {}})
    d.setdefault("candidates", {})
    return d


def load_ledger() -> dict:
    d = _load(LEDGER_PATH, {"decisions": {}})
    d.setdefault("decisions", {})
    return d


def record_candidate(path: str) -> bool:
    rel = normalize_id(path)
    if rel is None or rel in load_ledger()["decisions"]:
        return False
    p = load_pending()
    e = p["candidates"].get(rel)
    if e is None:
        p["candidates"][rel] = {"first_seen": _now(), "last_seen": _now(), "count": 1}
    else:
        e["last_seen"] = _now()
        e["count"] = int(e.get("count", 0)) + 1
    _save(PENDING_PATH, p)
    return True


def record_decision(rel: str, verdict: str, detail: str = "", cycle: str = "") -> dict:
    if verdict not in _VALID:
        raise ValueError(f"verdict must be one of {_VALID}")
    rel = normalize_id(rel) or rel
    led = load_ledger()
    rec = {"decision": verdict, "detail": detail, "cycle": cycle, "decided_at": _now()}
    led["decisions"][rel] = rec
    _save(LEDGER_PATH, led)
    p = load_pending()
    p["candidates"].pop(rel, None)
    _save(PENDING_PATH, p)
    return rec


def _has_live_counterpart(rel: str, led: dict) -> bool:
    rec = led["decisions"].get(rel)
    if not rec or rec.get("decision") != "done":
        return False
    detail = (rec.get("detail") or "").strip()
    if not detail:
        return True
    cand = Path(detail)
    return (cand if cand.is_absolute() else OUTPUT_DIR / detail).exists()


def undecided_candidates() -> list[dict]:
    p, led = load_pending(), load_ledger()
    out = []
    for rel, e in p["candidates"].items():
        if rel in led["decisions"] or _has_live_counterpart(rel, led):
            continue
        out.append({"id": rel, "count": int(e.get("count", 0)),
                    "first_seen": e.get("first_seen", "")})
    out.sort(key=lambda c: c["id"])
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("record-candidate"); a.add_argument("path")
    b = sub.add_parser("list"); b.add_argument("--json", action="store_true")
    c = sub.add_parser("record"); c.add_argument("id")
    c.add_argument("decision", choices=_VALID)
    c.add_argument("--detail", default=""); c.add_argument("--cycle", default="")
    args = parser.parse_args(argv)
    if args.cmd == "record-candidate":
        print(f"recorded: {record_candidate(args.path)} ({args.path})")
    elif args.cmd == "list":
        cands = undecided_candidates()
        print(json.dumps(cands, indent=2) if args.json else
              ("nothing undecided" if not cands else
               "\n".join(f"  {c['id']} (seen {c['count']}x)" for c in cands)))
    else:
        rec = record_decision(args.id, args.decision, args.detail, args.cycle)
        print(f"recorded decision for {args.id}: {rec['decision']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

## Adaptation Notes

- **Pick what gets tracked and what is noise.** The normalization + skip lists are
  domain-specific; the principle is to collapse nested/worktree paths to a stable
  inner id and drop ephemeral subtrees so the worklist stays signal.
- **Commit the decisions ledger; gitignore the pending file.** This split is the
  point: durable verdicts travel with the repo, volatile candidate state is
  per-machine and disposable.
- **Both verdicts settle.** "done" and "skipped" each suppress re-surfacing; only
  *undecided* items appear at the checkpoint. That is the closing loop the
  per-event nudge never had.
- **Run the checkpoint from your cycle-end skill** (wrap-up / retro), feeding the
  worklist to a human (or agent) who records one decision per item.
```
