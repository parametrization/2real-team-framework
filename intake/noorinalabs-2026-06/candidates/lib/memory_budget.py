#!/usr/bin/env python3
"""Enforce a size/count budget on the project-memory corpus (#733, P6 W1).

Second deliverable of P6 criterion #1 (memory leanness, epic #725): the
*enforcement* half. After the corpus was consolidated (sibling audit issue),
this check keeps it lean going forward — it caps how large the version-controlled
memory corpus (``.claude/memory/MEMORY.md`` + the topic files beside it) may grow
so that growth is a deliberate, surfaced decision rather than silent drift.

Per the enforcement hierarchy (``feedback_enforcement_hierarchy.md`` — hook >
skill > charter > memory), a budget expressed only as prose decays; it has to be
machine-enforced. This module is that machine: a CLI that exits non-zero when the
corpus is over budget, mirrored into ``.pre-commit-config.yaml`` and wired as a
CI job (``Memory budget gate``) so local and CI agree (the full local⇄CI parity
rule, ``feedback_local_ci_parity_no_force.md`` / #684).

Three dimensions, one threshold each (single source of truth)
=============================================================
The budget is the three module constants below — the ONLY place a limit is
defined. Each is enforced independently; the corpus is over budget if ANY one is
exceeded.

- ``MAX_INDEX_ENTRIES`` — index lines in ``MEMORY.md`` (``^- \\[`` rows, one per
  recallable memory). This is the primary, most meaningful dimension: it counts
  the things a session has to scan at startup.
- ``MAX_MEMORY_FILES`` — topic ``*.md`` files in ``.claude/memory/`` excluding
  ``MEMORY.md`` itself and the gitignored, machine-local ``session_handoff.md``
  (see below). Roughly tracks the index-entry count and catches an orphaned
  file that was added without an index row.
- ``MAX_MEMORY_BYTES`` — byte size of ``MEMORY.md``. A backstop against the
  pathological "few but enormous" index lines that the entry count alone would
  not catch.

Why the index count (102) and the file count (101) differ by one
================================================================
``MEMORY.md`` carries a committed pointer line for ``session_handoff.md``, but
that file is gitignored (per-session machine-local churn — see ``.gitignore``)
and is absent in a CI checkout. To keep the *file* count identical on a
developer machine (where the handoff exists) and in CI (where it does not), the
handoff is excluded from the file count. The index therefore legitimately counts
one more (the committed handoff pointer line) than the file count. Both budgets
have independent headroom, so the off-by-one is harmless.

Threshold calibration (headroom rationale — owner directive 2026-06-19 "tighten")
=================================================================================
Measured against the *post-consolidation* corpus at #733 time:
    index entries = 102,  topic files = 101,  MEMORY.md = 17,989 bytes (~17.6 KiB).

    MAX_INDEX_ENTRIES = 120  → ~18 entries / ~18% headroom over 102.
    MAX_MEMORY_FILES  = 120  → ~19 files   / ~19% headroom over 101.
    MAX_MEMORY_BYTES  = 24576 (24 KiB)  → ~37% headroom over 17,989 bytes; sits
        just under the ~24.4 KB ceiling a prior retro cited for MEMORY.md before
        the consolidation (it had bloated to ~38 KB). The byte cap is the loosest
        of the three on purpose — the entry/file caps bind first in the common
        growth pattern (adding memories); the byte cap only catches the rare
        case of fewer-but-bloated index lines.

The headroom is deliberately modest: enough that a normal wave's memory intake
does not trip the gate, but tight enough that it forces a consolidate/retire
decision before the corpus drifts back toward its pre-audit bloat. Raising a cap
is a one-line, reviewed change here — which is exactly the "deliberate, surfaced
decision" #725 wants, rather than silent growth.

Block, not advisory (``feedback_safety_direction_over_ux_friction.md``)
=======================================================================
A budget overflow CANNOT be auto-fixed — it needs a human consolidate/retire
judgment about which memories to merge or drop. So the right posture is a HARD
BLOCK with an actionable diagnostic (current vs. budget, by how much it is over,
and that the fix is to consolidate/retire in ``.claude/memory/``), never a silent
advisory that scrolls past. Exit 1 on overflow; the pre-commit/CI gate then stops
the push.

Exit codes (CLI):
    0 — corpus is within budget on all three dimensions.
    1 — over budget on at least one dimension (HARD BLOCK).
    2 — usage / corpus directory or MEMORY.md not found (cannot evaluate).
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
MAX_MEMORY_BYTES = 24_576  # 24 KiB

# Files under .claude/memory/ that are NOT counted as topic files: the index
# itself, and the gitignored per-session handoff (absent in CI — see module
# docstring). Compared case-sensitively against the file name.
_NON_TOPIC_FILES = frozenset({"MEMORY.md", "session_handoff.md"})

# An index entry is a top-level list row linking a memory: `- [Title](file.md) …`.
_INDEX_ENTRY_RE = re.compile(r"^- \[")


class Metric(NamedTuple):
    """One budgeted dimension and its current reading."""

    label: str  # human label, e.g. "index entries"
    current: int
    limit: int
    unit: str  # "" for counts, "bytes" for the size metric

    @property
    def over(self) -> bool:
        return self.current > self.limit

    @property
    def overage(self) -> int:
        return max(0, self.current - self.limit)


def count_index_entries(memory_md: Path) -> int:
    """Count `- [...]` index rows in MEMORY.md."""
    text = memory_md.read_text(encoding="utf-8")
    return sum(1 for line in text.splitlines() if _INDEX_ENTRY_RE.match(line))


def count_memory_files(memory_dir: Path) -> int:
    """Count topic `*.md` files in the memory dir, excluding non-topic files."""
    return sum(1 for p in memory_dir.glob("*.md") if p.name not in _NON_TOPIC_FILES)


def memory_md_bytes(memory_md: Path) -> int:
    """Byte size of MEMORY.md on disk."""
    return memory_md.stat().st_size


def gather_metrics(memory_dir: Path) -> list[Metric]:
    """Read the corpus and return the three budgeted metrics.

    Raises FileNotFoundError if the memory dir or MEMORY.md is absent — the
    caller turns that into exit 2 (cannot evaluate), never a silent pass.
    """
    if not memory_dir.is_dir():
        raise FileNotFoundError(f"memory directory not found: {memory_dir}")
    memory_md = memory_dir / "MEMORY.md"
    if not memory_md.is_file():
        raise FileNotFoundError(f"MEMORY.md not found: {memory_md}")
    return [
        Metric("index entries", count_index_entries(memory_md), MAX_INDEX_ENTRIES, ""),
        Metric("memory files", count_memory_files(memory_dir), MAX_MEMORY_FILES, ""),
        Metric("MEMORY.md size", memory_md_bytes(memory_md), MAX_MEMORY_BYTES, "bytes"),
    ]


def _fmt(metric: Metric) -> str:
    unit = f" {metric.unit}" if metric.unit else ""
    status = f"OVER by {metric.overage}{unit}" if metric.over else "ok"
    return f"  {metric.label:<14}: {metric.current} / {metric.limit}{unit}  ({status})"


def format_report(metrics: list[Metric]) -> str:
    """Render the metric table; identical shape whether over or under budget."""
    return "\n".join(_fmt(m) for m in metrics)


def over_budget_message(metrics: list[Metric]) -> str:
    """The HARD-BLOCK diagnostic printed when over budget."""
    over = [m for m in metrics if m.over]
    dims = ", ".join(m.label for m in over)
    return (
        "MEMORY BUDGET EXCEEDED — the project-memory corpus is over budget "
        f"on: {dims}.\n\n"
        f"{format_report(metrics)}\n\n"
        "A budget overflow cannot be auto-fixed: it needs a human "
        "consolidate/retire decision about which memories to merge or drop.\n"
        "To get back under budget, CONSOLIDATE related entries or RETIRE stale "
        "ones under .claude/memory/ (delete the file AND its line in MEMORY.md), "
        "then re-run.\n"
        "See CLAUDE.md § Project Memory and the /wave-retro memory curation step. "
        "If the corpus has genuinely outgrown the budget, raise the cap "
        "deliberately in .claude/lib/memory_budget.py (one reviewed line) — that "
        "is the surfaced decision this gate exists to force."
    )


def evaluate(memory_dir: Path) -> int:
    """Evaluate the corpus and print a report. Return the process exit code."""
    metrics = gather_metrics(memory_dir)
    if any(m.over for m in metrics):
        print(over_budget_message(metrics), file=sys.stderr)
        return 1
    print("OK: project-memory corpus is within budget.")
    print(format_report(metrics))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repo_root",
        nargs="?",
        default=".",
        help="Repo root to check (default: cwd). The corpus is <repo_root>/.claude/memory.",
    )
    parser.add_argument(
        "--memory-dir",
        help="Path to the memory dir directly (overrides <repo_root>/.claude/memory).",
    )
    args = parser.parse_args(argv[1:])

    memory_dir = (
        Path(args.memory_dir)
        if args.memory_dir
        else Path(args.repo_root).resolve() / ".claude" / "memory"
    )

    try:
        return evaluate(memory_dir)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
