#!/usr/bin/env python3
"""Enforce a governed-headcount budget on a repo's persona roster (#841, P6 W17).

Execution half of P6 criterion #3 / persona Option B (epic #819, spike
`.claude/team/spikes/p6w2-persona-model-evaluation.md`): the roster grew to
~2.5x the headcount the owner believed (Finding A — ungoverned drift, no budget,
no gate). This is the *enforcement* mechanism that keeps it bounded going
forward — a CLI that exits non-zero when a roster's persona-card count is over
budget, so growth becomes a deliberate, surfaced decision rather than silent
drift.

It is the roster analogue of ``memory_budget.py`` (P6 W1 / criterion #1, #733):
same shape (single-source-of-truth constant, HARD-BLOCK diagnostic, mirrored
into ``.pre-commit-config.yaml`` and a CI job, classified by the sync-drift gate
``pre_commit_ci_sync.py``) applied to a different corpus — the per-member
``.claude/team/roster/*.md`` identity cards instead of the memory corpus.

Per the enforcement hierarchy (``feedback_enforcement_hierarchy.md`` — hook >
skill > charter > memory), a headcount cap expressed only as charter prose
decays; it has to be machine-enforced. This module is that machine.

The budget — single source of truth
====================================
The two module constants below are the ONLY place the caps are defined:

- ``PARENT_ROSTER_BUDGET`` — max persona cards in the parent
  (``noorinalabs-main``) roster. This repo's pre-commit/CI run uses it (the
  default).
- ``CHILD_ROSTER_BUDGET`` — max persona cards in a child-repo roster. A child
  repo vendoring this gate wires its hook/CI to invoke with ``--budget 6`` (the
  same reusable-template pattern ``memory_budget.py`` follows for child rollout).

Calibration (spike ground-truth, 2026-06-21): per-repo roster sizes were
parent 10, isnad-graph 16, ingest 11, data-acquisition 10, design-system 8,
deploy 6, landing-page 5, user-service 4. The owner-set caps (parent <=9,
child <=6) bind first where the drift is worst. The parent roster is slimmed to
9 in this change (merge the duplicate SRE role — Aisha Idrissi into Lucas
Ferreira; the two personas first slated for retirement on a "0 parent commits"
premise were KEPT once that premise proved stale — both authored merged parent
PRs this wave), sitting AT the 9 cap. The cap is inclusive (at-limit passes),
so the roster has zero headroom: any further growth forces a deliberate
retire/merge decision before the roster drifts back up.

What counts as a persona card
=============================
Every ``*.md`` file directly under ``.claude/team/roster/`` is one persona card
(the roster dir holds nothing else; ``roster.json`` — the union manifest — lives
one level up under ``.claude/team/`` and is intentionally NOT counted). Each
card is one named identity. The roster dir, not ``roster.json``, is the budgeted
corpus on purpose: ``roster.json`` is the org-wide UNION of every repo's
personas for the commit-identity gate (``roster_union_sync.py``) and must list
retired/child personas; the per-repo *cards* are what carry the per-spawn tax
(card-read + reviewer-naming) the budget governs.

Block, not advisory (``feedback_safety_direction_over_ux_friction.md``)
=======================================================================
An over-budget roster CANNOT be auto-fixed — it needs a human judgment about
which personas to retire (no commits in the last N waves) or which near-duplicate
roles to merge, plus archiving their trust-matrix entries (preserve history).
So the posture is a HARD BLOCK with an actionable diagnostic (current vs. budget,
by how much, and the retire/merge/archive fix), never a silent advisory. Exit 1
on overflow; the pre-commit/CI gate then stops the push.

Exit codes (CLI):
    0 — roster is within budget.
    1 — over budget (HARD BLOCK).
    2 — usage / roster directory not found (cannot evaluate).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NamedTuple

# --- Budget: the single source of truth. Edit a number here and nowhere else. ---
PARENT_ROSTER_BUDGET = 9
CHILD_ROSTER_BUDGET = 6

# Roster cards live under <repo_root>/.claude/team/roster/. roster.json is one
# level up (under .claude/team/) so a "*.md" glob of the roster dir never
# accidentally counts it.
ROSTER_DIR_PARTS = (".claude", "team", "roster")


class Metric(NamedTuple):
    """The budgeted dimension and its current reading."""

    label: str  # human label, e.g. "persona cards"
    current: int
    limit: int

    @property
    def over(self) -> bool:
        return self.current > self.limit

    @property
    def overage(self) -> int:
        return max(0, self.current - self.limit)


def count_persona_cards(roster_dir: Path) -> int:
    """Count `*.md` persona-card files directly under the roster dir."""
    return sum(1 for _ in roster_dir.glob("*.md"))


def persona_card_names(roster_dir: Path) -> list[str]:
    """Sorted card filenames — used only to enrich the report/diagnostic."""
    return sorted(p.name for p in roster_dir.glob("*.md"))


def gather_metric(roster_dir: Path, budget: int) -> Metric:
    """Read the roster and return the budgeted metric.

    Raises FileNotFoundError if the roster dir is absent — the caller turns that
    into exit 2 (cannot evaluate), never a silent pass.
    """
    if not roster_dir.is_dir():
        raise FileNotFoundError(f"roster directory not found: {roster_dir}")
    return Metric("persona cards", count_persona_cards(roster_dir), budget)


def format_report(metric: Metric) -> str:
    """Render the metric line; identical shape whether over or under budget."""
    status = f"OVER by {metric.overage}" if metric.over else "ok"
    return f"  {metric.label:<14}: {metric.current} / {metric.limit}  ({status})"


def over_budget_message(metric: Metric, roster_dir: Path) -> str:
    """The HARD-BLOCK diagnostic printed when over budget."""
    cards = ", ".join(persona_card_names(roster_dir))
    return (
        "HEADCOUNT BUDGET EXCEEDED — the persona roster is over budget.\n\n"
        f"{format_report(metric)}\n"
        f"  roster dir    : {roster_dir}\n"
        f"  cards         : {cards}\n\n"
        "An over-budget roster cannot be auto-fixed: it needs a human decision "
        "about which personas to retire or which roles to merge.\n"
        "To get back under budget: RETIRE personas with no commits in the last N "
        "waves, or MERGE near-duplicate roles — delete the roster/*.md card(s) and "
        "ARCHIVE (don't delete) their trust-matrix entries to preserve history "
        "(keep the name in roster.json so the commit-identity gate still resolves "
        "it). See the persona-model spike "
        "(.claude/team/spikes/p6w2-persona-model-evaluation.md) and "
        "charter/agents.md § Governed headcount.\n"
        "If the roster has genuinely outgrown the budget, raise the cap "
        "deliberately in .claude/lib/headcount_budget.py (one reviewed line) — "
        "that is the surfaced decision this gate exists to force."
    )


def evaluate(roster_dir: Path, budget: int) -> int:
    """Evaluate the roster and print a report. Return the process exit code."""
    metric = gather_metric(roster_dir, budget)
    if metric.over:
        print(over_budget_message(metric, roster_dir), file=sys.stderr)
        return 1
    print("OK: persona roster is within budget.")
    print(format_report(metric))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repo_root",
        nargs="?",
        default=".",
        help="Repo root to check (default: cwd). Roster is <repo_root>/.claude/team/roster.",
    )
    parser.add_argument(
        "--roster-dir",
        help="Path to the roster dir directly (overrides <repo_root>/.claude/team/roster).",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=PARENT_ROSTER_BUDGET,
        help=(
            "Max persona cards (default: PARENT_ROSTER_BUDGET=%(default)s). "
            f"A child-repo roster passes --budget {CHILD_ROSTER_BUDGET}."
        ),
    )
    args = parser.parse_args(argv[1:])

    roster_dir = (
        Path(args.roster_dir)
        if args.roster_dir
        else Path(args.repo_root).resolve().joinpath(*ROSTER_DIR_PARTS)
    )

    try:
        return evaluate(roster_dir, args.budget)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
