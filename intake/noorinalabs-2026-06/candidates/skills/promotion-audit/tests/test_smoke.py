#!/usr/bin/env python3
"""Smoke test: run classification against the current repo state.

Per issue #152 acceptance criteria:
  - `feedback_enforcement_hierarchy.md` -> KEPT/SUPERSEDED
    (status=enforced-elsewhere; the audit recognizes this)
  - All other memories with `promotion_target: none` -> KEPT
  - The librarian rule is recognized as already-promoted (via Hook 15's
    Promotion provenance: block)
  - **Net: zero AUTO, zero DECIDE on first run** — backfill state.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import helpers as h  # noqa: E402

# Resolve repo paths. The smoke test runs against the actual working
# tree (worktree during dev, main after merge).
# Walk up from .claude/skills/promotion-audit/tests/ to repo root.
_REPO_ROOT = _HERE.parent.parent.parent.parent
# Memory is now in-repo (#732 relocation), not under ~/.claude/projects/.
_MEMORY_DIR = str(_REPO_ROOT / ".claude" / "memory")
_CHARTER_ROOT = _REPO_ROOT / ".claude" / "team"
_SKILLS_DIR = _REPO_ROOT / ".claude" / "skills"
_FEEDBACK_LOG = _CHARTER_ROOT / "feedback_log.md"


@unittest.skipUnless(
    os.path.isdir(_MEMORY_DIR),
    "Smoke test requires the project's memory directory",
)
class SmokeTests(unittest.TestCase):
    """End-to-end smoke test against current repo state."""

    memories: list[h.Memory]
    sections: list[h.CharterSection]
    skills: list[h.Skill]
    already: set[str]

    @classmethod
    def setUpClass(cls) -> None:
        cls.memories = h.read_all_memories(_MEMORY_DIR)
        cls.sections = h.read_all_charter_sections(str(_CHARTER_ROOT))
        cls.skills = h.read_all_skills(str(_SKILLS_DIR))
        cls.already = h.find_already_promoted_in_charter(str(_CHARTER_ROOT))

    def test_at_least_one_memory_found(self) -> None:
        self.assertGreater(len(self.memories), 0)

    def test_hook15_provenance_recognized(self) -> None:
        """Confirms the Q5 already-handled detection works on real state."""
        self.assertIn("feedback_enforcement_hierarchy.md", self.already)
        self.assertIn("CLAUDE.md § Ontology", self.already)

    def test_feedback_enforcement_hierarchy_not_auto(self) -> None:
        """Per spec: this memory is status=enforced-elsewhere; audit must
        classify it as SUPERSEDED or ALREADY-PROMOTED — NEVER AUTO/DECIDE."""
        target = [m for m in self.memories if m.filename == "feedback_enforcement_hierarchy.md"]
        self.assertEqual(len(target), 1, "memory must exist in repo")
        m = target[0]
        citations = h.count_retro_citations(m, str(_FEEDBACK_LOG))
        d = h.classify_memory(m, {"retro_citations": citations}, self.already)
        self.assertIn(d.kind, ("SUPERSEDED", "ALREADY-PROMOTED"))

    def test_zero_auto_zero_decide_on_first_run(self) -> None:
        """The core spec outcome: no AUTO, no DECIDE on current repo state.

        If this test fails, something has drifted — either a memory was
        tagged for promotion and crossed the threshold, or a section was
        marked with a promotion target and signal. The failure message
        should guide the reviewer to the offending item.
        """
        decisions: list[h.Decision] = []

        for m in self.memories:
            cites = h.count_retro_citations(m, str(_FEEDBACK_LOG))
            decisions.append(h.classify_memory(m, {"retro_citations": cites}, self.already))

        for s in self.sections:
            # Charter sections — we intentionally pass zero invocation
            # signal for the smoke run; a separate future enhancement may
            # wire up `count_skill_invocations` once the signal matures.
            decisions.append(h.classify_section(s, {"skill_invocations": 0, "threshold": 5}))

        for sk in self.skills:
            decisions.append(
                h.classify_skill(
                    sk,
                    {"skill_invocations": 0, "threshold": 5},
                    self.already,
                )
            )

        auto = [d for d in decisions if d.kind == "AUTO"]
        decide = [d for d in decisions if d.kind == "DECIDE"]

        self.assertEqual(
            len(auto),
            0,
            f"Expected zero AUTO decisions on first run, got: {[d.item_id for d in auto]}",
        )
        self.assertEqual(
            len(decide),
            0,
            f"Expected zero DECIDE decisions on first run, got: {[d.item_id for d in decide]}",
        )

    def test_render_is_deterministic(self) -> None:
        """Core spec: same inputs, byte-identical output."""
        decisions: list[h.Decision] = []
        for m in self.memories:
            cites = h.count_retro_citations(m, str(_FEEDBACK_LOG))
            decisions.append(h.classify_memory(m, {"retro_citations": cites}, self.already))

        a = h.render_audit_table(decisions, "wave-9", "2026-04-19")
        b = h.render_audit_table(decisions, "wave-9", "2026-04-19")
        self.assertEqual(a, b, "render_audit_table must be deterministic")

    def test_librarian_rule_not_re_promoted(self) -> None:
        """Q5 worked-example confirmation: the librarian RULE (memory
        `feedback_enforcement_hierarchy.md` -> CLAUDE.md § Ontology -> Hook 15)
        must be recognized via Hook 15's `Promotion provenance:` block and
        NOT scheduled for re-promotion.

        Semantic note: Hook 15 promotes the *rule* ("consult librarian
        before code edits"), not the `/ontology-librarian` skill itself.
        The skill is the reader-side tool that satisfies the rule; it
        stays KEPT with `promotion_target: none`. What we assert here is
        that the audit recognizes Hook 15's provenance block and:
          (a) marks `feedback_enforcement_hierarchy.md` as
              ALREADY-PROMOTED or SUPERSEDED (both are acceptable — the
              memory also has `status: enforced-elsewhere`), AND
          (b) does NOT try to re-promote `CLAUDE.md § Ontology`."""
        # (a) Memory recognition.
        mem = [m for m in self.memories if m.filename == "feedback_enforcement_hierarchy.md"]
        self.assertEqual(len(mem), 1)
        d = h.classify_memory(
            mem[0],
            {"retro_citations": h.count_retro_citations(mem[0], str(_FEEDBACK_LOG))},
            self.already,
        )
        self.assertIn(d.kind, ("ALREADY-PROMOTED", "SUPERSEDED"))

        # (b) The provenance block's source references are in the
        # already-promoted set.
        self.assertIn("CLAUDE.md § Ontology", self.already)
        self.assertIn("feedback_enforcement_hierarchy.md", self.already)


if __name__ == "__main__":
    unittest.main(verbosity=2)
