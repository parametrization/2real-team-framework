"""Tests for headcount_budget -- the persona-roster headcount budget (#841).

Verifies:
  1. Under budget -> exit 0, "within budget".
  2. Exactly AT the cap -> exit 0 (the cap is inclusive; at-limit is allowed).
  3. One-over -> exit 1, HARD-BLOCK diagnostic.
  4. The over-budget diagnostic is actionable (current/limit, "OVER by N",
     retire/merge/archive guidance, names the offending cards).
  5. Only *.md files directly under the roster dir count; roster.json (one level
     up) and non-md files never count.
  6. --budget overrides the default (child repos pass 6); --roster-dir override.
  7. Missing roster dir -> exit 2 (cannot evaluate).
  8. The budget lives in ONE place: the module constants drive the caps.
  9. The shipped parent roster is within the parent budget (the gate must PASS
     on the very corpus that ships it).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import headcount_budget  # noqa: E402
from headcount_budget import (  # noqa: E402
    CHILD_ROSTER_BUDGET,
    PARENT_ROSTER_BUDGET,
    count_persona_cards,
    evaluate,
    gather_metric,
    main,
)


def _build_roster(root: Path, *, cards: int, extra_files: bool = False) -> Path:
    """Create a .claude/team/roster dir with `cards` *.md persona cards.

    `extra_files` adds a non-md file in the roster dir and a roster.json one
    level up — neither must be counted.
    """
    roster_dir = root / ".claude" / "team" / "roster"
    roster_dir.mkdir(parents=True)
    for i in range(cards):
        (roster_dir / f"member_{i}.md").write_text(f"- **Name:** Member {i}\n", encoding="utf-8")
    if extra_files:
        (roster_dir / "NOTES.txt").write_text("not a card\n", encoding="utf-8")
        (roster_dir.parent / "roster.json").write_text("{}\n", encoding="utf-8")
    return roster_dir


class CountingTests(unittest.TestCase):
    def test_counts_only_md_files_in_roster_dir(self) -> None:
        with TemporaryDirectory() as d:
            roster_dir = _build_roster(Path(d), cards=5, extra_files=True)
            # 5 cards; NOTES.txt and the parent-level roster.json must NOT count.
            self.assertEqual(count_persona_cards(roster_dir), 5)


class UnderAndAtBudgetTests(unittest.TestCase):
    def test_well_under_budget_exits_zero(self) -> None:
        with TemporaryDirectory() as d:
            roster_dir = _build_roster(Path(d), cards=4)
            self.assertEqual(evaluate(roster_dir, PARENT_ROSTER_BUDGET), 0)

    def test_exactly_at_cap_is_allowed(self) -> None:
        with TemporaryDirectory() as d:
            roster_dir = _build_roster(Path(d), cards=PARENT_ROSTER_BUDGET)
            metric = gather_metric(roster_dir, PARENT_ROSTER_BUDGET)
            self.assertEqual(metric.current, PARENT_ROSTER_BUDGET)
            self.assertFalse(metric.over)
            self.assertEqual(evaluate(roster_dir, PARENT_ROSTER_BUDGET), 0)


class OverBudgetTests(unittest.TestCase):
    def test_one_over_blocks(self) -> None:
        with TemporaryDirectory() as d:
            roster_dir = _build_roster(Path(d), cards=PARENT_ROSTER_BUDGET + 1)
            self.assertEqual(evaluate(roster_dir, PARENT_ROSTER_BUDGET), 1)

    def test_child_budget_binds_tighter(self) -> None:
        # 7 cards passes the parent cap (9) but fails the child cap (6).
        with TemporaryDirectory() as d:
            roster_dir = _build_roster(Path(d), cards=7)
            self.assertEqual(evaluate(roster_dir, PARENT_ROSTER_BUDGET), 0)
            self.assertEqual(evaluate(roster_dir, CHILD_ROSTER_BUDGET), 1)

    def test_over_budget_diagnostic_is_actionable(self) -> None:
        with TemporaryDirectory() as d:
            roster_dir = _build_roster(Path(d), cards=PARENT_ROSTER_BUDGET + 3)
            metric = gather_metric(roster_dir, PARENT_ROSTER_BUDGET)
            msg = headcount_budget.over_budget_message(metric, roster_dir)
            self.assertIn("HEADCOUNT BUDGET EXCEEDED", msg)
            self.assertIn("OVER by 3", msg)
            self.assertIn(str(PARENT_ROSTER_BUDGET), msg)
            # Must tell the human the fix is retire/merge/archive, not auto-fixable.
            self.assertIn("cannot be auto-fixed", msg)
            self.assertIn("RETIRE", msg)
            self.assertIn("MERGE", msg)
            self.assertIn("ARCHIVE", msg)
            # Names a specific offending card so the operator knows the corpus.
            self.assertIn("member_0.md", msg)


class CliAndErrorTests(unittest.TestCase):
    def test_main_repo_root_arg_resolves_roster(self) -> None:
        with TemporaryDirectory() as d:
            _build_roster(Path(d), cards=4)
            self.assertEqual(main(["headcount_budget.py", d]), 0)

    def test_main_budget_flag_override(self) -> None:
        with TemporaryDirectory() as d:
            _build_roster(Path(d), cards=7)
            # Default (parent=9) passes; --budget 6 (child) blocks.
            self.assertEqual(main(["headcount_budget.py", d]), 0)
            self.assertEqual(main(["headcount_budget.py", d, "--budget", "6"]), 1)

    def test_main_roster_dir_override(self) -> None:
        with TemporaryDirectory() as d:
            roster_dir = _build_roster(Path(d), cards=4)
            self.assertEqual(main(["headcount_budget.py", "--roster-dir", str(roster_dir)]), 0)

    def test_missing_roster_dir_exits_two(self) -> None:
        with TemporaryDirectory() as d:
            # No .claude/team/roster created.
            self.assertEqual(main(["headcount_budget.py", d]), 2)


class RealRosterWithinBudgetTests(unittest.TestCase):
    """The check must PASS on the very roster that ships it — i.e. the slimmed
    parent roster sits at or under the parent cap (else the gate red-blocks the
    PR adding it)."""

    def test_parent_roster_is_within_budget(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        roster_dir = repo_root / ".claude" / "team" / "roster"
        if not roster_dir.is_dir():
            self.skipTest("parent roster not present in this checkout")
        self.assertEqual(evaluate(roster_dir, PARENT_ROSTER_BUDGET), 0)


if __name__ == "__main__":
    unittest.main()
