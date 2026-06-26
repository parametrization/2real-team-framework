# Generic Lib Prompt: Memory-Corpus Budget Gate (multi-dimension)

## Purpose

Cap how large a version-controlled **project-memory corpus** (an always-loaded
index file plus the topic files beside it) may grow, so growth is a deliberate,
surfaced decision rather than silent drift back toward bloat. The corpus is read
at every session start, so an unbounded index directly taxes startup. Per the
enforcement hierarchy (hook > skill > charter > memory), a budget expressed only
as prose decays; this is the machine that enforces it.

It is the multi-dimension sibling of the roster headcount budget: same gate shape
(single-source-of-truth constants, HARD-BLOCK diagnostic, mirrored into pre-commit
+ CI, classifiable by a sync-drift gate), applied to a corpus measured on three
independent axes.

## Reusable Pattern

- **Three dimensions, one threshold each, all single-source-of-truth constants:**
  1. **index entries** — count of recallable-memory rows in the index file (the
     primary, most meaningful dimension: what a session scans at startup);
  2. **topic files** — count of topic `*.md` files, excluding the index itself and
     any gitignored per-session/machine-local file (so the count is identical on a
     dev machine and in CI);
  3. **index byte size** — a backstop against the "few but enormous" rows the entry
     count alone misses.
- **Over budget if ANY dimension is exceeded** (independent caps).
- **Exclude machine-local files from the file count** so CI (where they are
  absent) and a dev checkout agree — this legitimately makes the index-entry count
  one higher than the file count (the index carries a committed pointer for the
  excluded file). Independent headroom keeps that off-by-one harmless.
- **Block, not advisory** — an overflow needs a human consolidate/retire judgment
  about which memories to merge or drop; HARD BLOCK with an actionable diagnostic.
- **Exit codes:** 0 within budget, 1 over (hard block), 2 cannot evaluate.

## Algorithm

1. Resolve the memory dir; if it or the index file is absent → exit 2.
2. Count index rows (`^- \[` lines), count topic files (excluding non-topic
   names), stat the index byte size.
3. If any metric is over its cap → print the multi-dimension hard-block
   diagnostic to stderr, exit 1. Else print the table, exit 0.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Enforce a size/count budget on a version-controlled memory corpus.

Exit codes: 0 within budget, 1 over (HARD BLOCK), 2 cannot evaluate.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple

# --- Budget: the single source of truth. Edit a number here and nowhere else. ---
MAX_INDEX_ENTRIES = 120
MAX_MEMORY_FILES = 120
MAX_MEMORY_BYTES = 24_576  # 24 KiB backstop

# Files NOT counted as topic files: the index, and any gitignored per-session file.
_NON_TOPIC_FILES = frozenset({"MEMORY.md", "session_handoff.md"})
_INDEX_ENTRY_RE = re.compile(r"^- \[")  # `- [Title](file.md) …`


class Metric(NamedTuple):
    label: str
    current: int
    limit: int
    unit: str

    @property
    def over(self) -> bool:
        return self.current > self.limit

    @property
    def overage(self) -> int:
        return max(0, self.current - self.limit)


def count_index_entries(index_md: Path) -> int:
    return sum(1 for line in index_md.read_text(encoding="utf-8").splitlines()
               if _INDEX_ENTRY_RE.match(line))


def count_memory_files(memory_dir: Path) -> int:
    return sum(1 for p in memory_dir.glob("*.md") if p.name not in _NON_TOPIC_FILES)


def gather_metrics(memory_dir: Path) -> list[Metric]:
    if not memory_dir.is_dir():
        raise FileNotFoundError(f"memory directory not found: {memory_dir}")
    index_md = memory_dir / "MEMORY.md"
    if not index_md.is_file():
        raise FileNotFoundError(f"index not found: {index_md}")
    return [
        Metric("index entries", count_index_entries(index_md), MAX_INDEX_ENTRIES, ""),
        Metric("memory files", count_memory_files(memory_dir), MAX_MEMORY_FILES, ""),
        Metric("index size", index_md.stat().st_size, MAX_MEMORY_BYTES, "bytes"),
    ]


def _fmt(m: Metric) -> str:
    unit = f" {m.unit}" if m.unit else ""
    status = f"OVER by {m.overage}{unit}" if m.over else "ok"
    return f"  {m.label:<14}: {m.current} / {m.limit}{unit}  ({status})"


def over_budget_message(metrics: list[Metric]) -> str:
    dims = ", ".join(m.label for m in metrics if m.over)
    body = "\n".join(_fmt(m) for m in metrics)
    return (
        f"MEMORY BUDGET EXCEEDED — over budget on: {dims}.\n\n{body}\n\n"
        "Cannot be auto-fixed: CONSOLIDATE related entries or RETIRE stale ones "
        "(delete the file AND its index line), then re-run. If the corpus has "
        "genuinely outgrown the budget, raise the cap deliberately in this file "
        "(one reviewed line) — the surfaced decision this gate exists to force."
    )


def evaluate(memory_dir: Path) -> int:
    metrics = gather_metrics(memory_dir)
    if any(m.over for m in metrics):
        print(over_budget_message(metrics), file=sys.stderr)
        return 1
    print("OK: memory corpus is within budget.")
    print("\n".join(_fmt(m) for m in metrics))
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("repo_root", nargs="?", default=".")
    p.add_argument("--memory-dir")
    args = p.parse_args(argv[1:])
    memory_dir = (Path(args.memory_dir) if args.memory_dir
                  else Path(args.repo_root).resolve() / ".memory")
    try:
        return evaluate(memory_dir)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

## Adaptation Notes

- **Calibrate against the post-consolidation corpus** and leave modest headroom —
  enough that a normal cycle's intake doesn't trip the gate, tight enough that it
  forces a consolidate/retire before bloat returns. Make the byte cap the loosest
  of the three so the entry/file caps bind first in the common growth pattern.
- **Exclude machine-local files from the file count.** Any per-session, gitignored
  file (a handoff, a scratch note) must be excluded so CI and a dev checkout
  produce the same number. Document the resulting off-by-one with the index count.
- **The index-entry count is the primary axis** — it is what a session actually
  scans at startup. The file count catches an orphaned file added without an index
  row; the byte cap catches few-but-huge rows.
- **Same gate shape as the roster budget** so the pre-commit/CI/sync-drift wiring
  and the child-repo rollout are uniform across budget gates.
```
