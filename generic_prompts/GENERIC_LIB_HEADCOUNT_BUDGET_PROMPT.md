# Generic Lib Prompt: Roster Headcount Budget Gate

## Purpose

Cap the number of persona/identity cards in a team roster so headcount growth is
a **deliberate, surfaced decision** rather than silent drift. The failure it
prevents: a roster quietly grows to many times the size anyone believes, with no
budget and no gate, because every individual addition felt reasonable. Per the
enforcement hierarchy (hook > skill > charter > memory), a cap expressed only as
prose decays — it has to be machine-enforced.

This is the roster instance of a general **budget gate** (see also the
memory-corpus budget): a single-source-of-truth limit, a HARD-BLOCK diagnostic,
mirrored into pre-commit + CI, classifiable by a sync-drift gate.

## Reusable Pattern

- **The budget is one (or two) module constants** — the ONLY place a cap is
  defined. A parent cap and a child-repo cap, the child passed via `--budget`,
  is the same reusable-template shape used to roll a gate out across repos.
- **Count the right corpus.** Each `*.md` directly under the roster dir is one
  card; a union-manifest file that lives one level up is intentionally NOT counted
  (it must list retired/other-repo identities, so it is not the budgeted thing).
  Count the per-repo *cards* — what carry the per-spawn tax the budget governs.
- **Block, not advisory.** An over-budget roster cannot be auto-fixed — it needs a
  human judgment about which identities to retire or which near-duplicate roles to
  merge. So: HARD BLOCK with an actionable diagnostic (current vs. budget, the
  overage, and the retire/merge/archive fix), never a silent advisory.
- **Inclusive cap** (at-limit passes); zero headroom means any further growth
  forces a deliberate decision.
- **Raising the cap is a one-line reviewed change** here — which *is* the surfaced
  decision the gate exists to force.
- **Exit codes:** 0 within budget, 1 over (hard block), 2 cannot evaluate
  (corpus dir absent — never a silent pass).

## Algorithm

1. Resolve the roster dir (`<repo_root>/.../roster` or an explicit override).
2. If absent → exit 2.
3. Count `*.md` cards directly under it.
4. Compare to the budget. Over → print the hard-block diagnostic to stderr, exit
   1. Otherwise print the metric line, exit 0.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Enforce a governed-headcount budget on a roster of identity cards.

Exit codes: 0 within budget, 1 over (HARD BLOCK), 2 cannot evaluate.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NamedTuple

# --- Budget: the single source of truth. Edit a number here and nowhere else. ---
PARENT_ROSTER_BUDGET = 9
CHILD_ROSTER_BUDGET = 6

ROSTER_DIR_PARTS = (".team", "roster")  # adapt to your layout


class Metric(NamedTuple):
    label: str
    current: int
    limit: int

    @property
    def over(self) -> bool:
        return self.current > self.limit

    @property
    def overage(self) -> int:
        return max(0, self.current - self.limit)


def count_cards(roster_dir: Path) -> int:
    return sum(1 for _ in roster_dir.glob("*.md"))


def card_names(roster_dir: Path) -> list[str]:
    return sorted(p.name for p in roster_dir.glob("*.md"))


def gather_metric(roster_dir: Path, budget: int) -> Metric:
    if not roster_dir.is_dir():
        raise FileNotFoundError(f"roster directory not found: {roster_dir}")
    return Metric("persona cards", count_cards(roster_dir), budget)


def _fmt(m: Metric) -> str:
    return f"  {m.label:<14}: {m.current} / {m.limit}  ({'OVER by ' + str(m.overage) if m.over else 'ok'})"


def over_budget_message(m: Metric, roster_dir: Path) -> str:
    return (
        "HEADCOUNT BUDGET EXCEEDED — the roster is over budget.\n\n"
        f"{_fmt(m)}\n  cards: {', '.join(card_names(roster_dir))}\n\n"
        "Cannot be auto-fixed: RETIRE identities with no recent activity, or MERGE "
        "near-duplicate roles — delete the card(s) and ARCHIVE (don't delete) their "
        "history. If the roster has genuinely outgrown the budget, raise the cap "
        "deliberately in this file (one reviewed line) — the surfaced decision this "
        "gate exists to force."
    )


def evaluate(roster_dir: Path, budget: int) -> int:
    m = gather_metric(roster_dir, budget)
    if m.over:
        print(over_budget_message(m, roster_dir), file=sys.stderr)
        return 1
    print("OK: roster is within budget.")
    print(_fmt(m))
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("repo_root", nargs="?", default=".")
    p.add_argument("--roster-dir")
    p.add_argument("--budget", type=int, default=PARENT_ROSTER_BUDGET,
                   help=f"max cards (default parent={PARENT_ROSTER_BUDGET}; child passes {CHILD_ROSTER_BUDGET})")
    args = p.parse_args(argv[1:])
    roster_dir = (Path(args.roster_dir) if args.roster_dir
                  else Path(args.repo_root).resolve().joinpath(*ROSTER_DIR_PARTS))
    try:
        return evaluate(roster_dir, args.budget)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

## Adaptation Notes

- **Calibrate the cap from ground truth, then leave a little headroom.** Set the
  number against the current real corpus so it binds where drift is worst, with
  just enough headroom that a normal cycle doesn't trip it.
- **Count cards, not the union manifest.** If you maintain an org-wide identity
  list for some other gate (e.g. commit-identity resolution), keep it OUT of the
  budgeted count — it must include retired/other identities by design.
- **Same gate shape as your other budgets** (memory, etc.) so child-repo rollout
  is a copy with a different `--budget`, and a sync-drift gate recognizes the kind.
- **Archive, don't delete, history when retiring** — the diagnostic should say so,
  so trust/contribution history survives a roster trim.
```
