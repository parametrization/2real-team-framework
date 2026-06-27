"""Tests for generic_prompt_tracker — the state backbone for the batched
wave-lifecycle genericize checkpoint (main#716).

Coverage maps to the issue's three acceptance criteria:

  AC1 (checkpoint enumerates changed .claude/ artifacts lacking a counterpart)
      → undecided_candidates returns undecided genericizable artifacts, and
        classify/normalize_rel_path feed it the right shape.
  AC2 (per-edit systemMessage no longer fires; demoted to silent tracking)
      → exercised in test_suggest_generic_prompt.py; here we verify the
        record_candidate feeder writes pending state silently.
  AC3 (decisions recorded so the same artifact isn't re-surfaced every wave)
      → record_decision settles an artifact; undecided_candidates excludes
        both skipped and genericized paths thereafter.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Helper lives at .claude/lib/generic_prompt_tracker.py; this test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generic_prompt_tracker as gpt  # noqa: E402


class NormalizeRelPathTest(unittest.TestCase):
    def test_absolute_path_under_claude(self) -> None:
        self.assertEqual(
            gpt.normalize_rel_path("/home/u/repo/.claude/hooks/foo.py"),
            "hooks/foo.py",
        )

    def test_worktree_nested_splits_on_last_marker(self) -> None:
        # A worktree lives under .claude/worktrees/<wt>/.claude/... — the LAST
        # /.claude/ yields the artifact path inside the worktree's own repo.
        p = "/home/u/repo/.claude/worktrees/0716-x/.claude/skills/wave-wrapup/SKILL.md"
        self.assertEqual(gpt.normalize_rel_path(p), "skills/wave-wrapup/SKILL.md")

    def test_bare_claude_relative(self) -> None:
        self.assertEqual(gpt.normalize_rel_path(".claude/settings.json"), "settings.json")

    def test_outside_claude_returns_none(self) -> None:
        self.assertIsNone(gpt.normalize_rel_path("/home/u/repo/src/app.py"))
        self.assertIsNone(gpt.normalize_rel_path(""))

    def test_skip_listed_tracker_churn_returns_none(self) -> None:
        self.assertIsNone(gpt.normalize_rel_path("/r/.claude/ontology/checksums.json"))
        self.assertIsNone(gpt.normalize_rel_path("/r/.claude/annunaki/errors.jsonl"))

    def test_noise_subtree_rel_prefixes_return_none(self) -> None:
        # worktrees/ memory/ scratch are whole-subtree noise — a path that
        # NORMALIZES to one of these rel prefixes is not a genericize candidate.
        self.assertIsNone(gpt.normalize_rel_path("/r/.claude/worktrees/agent-x/foo.txt"))
        self.assertIsNone(gpt.normalize_rel_path(".claude/memory/feedback_x.md"))
        self.assertIsNone(gpt.normalize_rel_path("/r/.claude/scratch/tmp.md"))
        self.assertIsNone(gpt.normalize_rel_path(".claude/scratch_pr_768.md"))

    def test_real_artifact_edited_inside_worktree_still_tracked(self) -> None:
        # The rel-prefix skip is checked against the NORMALIZED rel, not the raw
        # path, so a real artifact edited in a worktree (collapses to its inner
        # rel) is still tracked — the worktrees/ prefix must not over-match it.
        p = "/home/u/repo/.claude/worktrees/0716-x/.claude/hooks/foo.py"
        self.assertEqual(gpt.normalize_rel_path(p), "hooks/foo.py")

    def test_tracker_own_state_files_not_tracked(self) -> None:
        self.assertIsNone(gpt.normalize_rel_path("/r/.claude/generic_prompt_pending.json"))
        self.assertIsNone(gpt.normalize_rel_path("/r/.claude/generic_prompt_ledger.json"))


class ClassifyTest(unittest.TestCase):
    def test_categories(self) -> None:
        self.assertEqual(gpt.classify("hooks/foo.py")["category"], "hook")
        self.assertEqual(gpt.classify("skills/wave-wrapup/SKILL.md")["category"], "skill")
        self.assertEqual(gpt.classify("team/charter/agents.md")["category"], "charter")
        self.assertEqual(gpt.classify("settings.json")["category"], "settings")

    def test_fallback_category(self) -> None:
        info = gpt.classify("ontology/domain.yaml")
        self.assertEqual(info["category"], "configuration")
        self.assertIn("suggestion", info)


class _TmpStateMixin(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        self.pending = root / "pending.json"
        self.ledger = root / "ledger.json"
        self.framework = root / "generic_prompts"
        self.framework.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()


class RecordCandidateTest(_TmpStateMixin):
    def test_new_candidate_creates_entry(self) -> None:
        ok = gpt.record_candidate(
            "/r/.claude/hooks/foo.py", pending_path=self.pending, ledger_path=self.ledger, now="T1"
        )
        self.assertTrue(ok)
        data = json.loads(self.pending.read_text())
        entry = data["candidates"]["hooks/foo.py"]
        self.assertEqual(entry["category"], "hook")
        self.assertEqual(entry["count"], 1)
        self.assertEqual(entry["first_seen"], "T1")

    def test_repeat_increments_count_and_updates_last_seen(self) -> None:
        for t in ("T1", "T2", "T3"):
            gpt.record_candidate(
                "/r/.claude/hooks/foo.py", pending_path=self.pending, ledger_path=self.ledger, now=t
            )
        entry = json.loads(self.pending.read_text())["candidates"]["hooks/foo.py"]
        self.assertEqual(entry["count"], 3)
        self.assertEqual(entry["first_seen"], "T1")
        self.assertEqual(entry["last_seen"], "T3")

    def test_skip_listed_not_recorded(self) -> None:
        ok = gpt.record_candidate(
            "/r/.claude/ontology/checksums.json", pending_path=self.pending, ledger_path=self.ledger
        )
        self.assertFalse(ok)
        self.assertFalse(self.pending.exists())

    def test_already_decided_not_readded(self) -> None:
        gpt.record_decision(
            "hooks/foo.py",
            "skipped",
            detail="too project-specific",
            ledger_path=self.ledger,
            pending_path=self.pending,
        )
        ok = gpt.record_candidate(
            "/r/.claude/hooks/foo.py", pending_path=self.pending, ledger_path=self.ledger
        )
        self.assertFalse(ok)


class RecordDecisionTest(_TmpStateMixin):
    def test_writes_ledger_and_removes_from_pending(self) -> None:
        gpt.record_candidate(
            "/r/.claude/hooks/foo.py", pending_path=self.pending, ledger_path=self.ledger
        )
        rec = gpt.record_decision(
            "hooks/foo.py",
            "genericized",
            detail="GENERIC_HOOK.md",
            wave="P5W5",
            ledger_path=self.ledger,
            pending_path=self.pending,
            now="TD",
        )
        self.assertEqual(rec["decision"], "genericized")
        ledger = json.loads(self.ledger.read_text())
        self.assertEqual(ledger["decisions"]["hooks/foo.py"]["wave"], "P5W5")
        self.assertEqual(ledger["decisions"]["hooks/foo.py"]["decided_at"], "TD")
        pending = json.loads(self.pending.read_text())
        self.assertNotIn("hooks/foo.py", pending["candidates"])

    def test_invalid_decision_raises(self) -> None:
        with self.assertRaises(ValueError):
            gpt.record_decision(
                "hooks/foo.py", "maybe", ledger_path=self.ledger, pending_path=self.pending
            )


class UndecidedCandidatesTest(_TmpStateMixin):
    def _seed(self, *rel_paths: str) -> None:
        for rp in rel_paths:
            gpt.record_candidate(
                f"/r/.claude/{rp}", pending_path=self.pending, ledger_path=self.ledger
            )

    def test_returns_undecided_sorted(self) -> None:
        self._seed("skills/wave-wrapup/SKILL.md", "hooks/foo.py", "team/charter/agents.md")
        out = gpt.undecided_candidates(
            pending_path=self.pending, ledger_path=self.ledger, framework_dir=self.framework
        )
        cats = [(c["category"], c["rel_path"]) for c in out]
        # sorted by (category, rel_path): charter < hook < skill
        self.assertEqual(
            cats,
            [
                ("charter", "team/charter/agents.md"),
                ("hook", "hooks/foo.py"),
                ("skill", "skills/wave-wrapup/SKILL.md"),
            ],
        )

    def test_skipped_decision_excludes_from_worklist(self) -> None:
        self._seed("hooks/foo.py", "hooks/bar.py")
        gpt.record_decision(
            "hooks/foo.py",
            "skipped",
            detail="project-coupled",
            ledger_path=self.ledger,
            pending_path=self.pending,
        )
        rels = [
            c["rel_path"]
            for c in gpt.undecided_candidates(
                pending_path=self.pending, ledger_path=self.ledger, framework_dir=self.framework
            )
        ]
        self.assertEqual(rels, ["hooks/bar.py"])

    def test_genericized_with_existing_counterpart_excluded(self) -> None:
        # Re-seed pending directly (record_candidate would refuse a decided path)
        # to prove undecided_candidates ALSO filters on a live counterpart file.
        (self.framework / "GENERIC_HOOK.md").write_text("generic\n")
        gpt.save_pending(
            {"version": 1, "candidates": {"hooks/foo.py": {"category": "hook", "count": 1}}},
            self.pending,
        )
        gpt.save_ledger(
            {
                "version": 1,
                "decisions": {
                    "hooks/foo.py": {
                        "decision": "genericized",
                        "detail": "GENERIC_HOOK.md",
                        "wave": "P5W5",
                        "decided_at": "TD",
                    }
                },
            },
            self.ledger,
        )
        out = gpt.undecided_candidates(
            pending_path=self.pending, ledger_path=self.ledger, framework_dir=self.framework
        )
        self.assertEqual(out, [])

    def test_empty_pending_returns_empty(self) -> None:
        self.assertEqual(
            gpt.undecided_candidates(
                pending_path=self.pending, ledger_path=self.ledger, framework_dir=self.framework
            ),
            [],
        )


class HasLiveCounterpartTest(_TmpStateMixin):
    def test_missing_counterpart_file_is_not_live(self) -> None:
        ledger = {"decisions": {"hooks/foo.py": {"decision": "genericized", "detail": "NOPE.md"}}}
        self.assertFalse(gpt._has_live_counterpart("hooks/foo.py", ledger, self.framework))

    def test_skipped_is_never_a_counterpart(self) -> None:
        ledger = {"decisions": {"hooks/foo.py": {"decision": "skipped", "detail": ""}}}
        self.assertFalse(gpt._has_live_counterpart("hooks/foo.py", ledger, self.framework))


class CorruptStateTest(_TmpStateMixin):
    def test_corrupt_pending_heals_to_default(self) -> None:
        self.pending.write_text("{ not json")
        # Should not raise; record starts fresh.
        ok = gpt.record_candidate(
            "/r/.claude/hooks/foo.py", pending_path=self.pending, ledger_path=self.ledger
        )
        self.assertTrue(ok)
        self.assertIn("hooks/foo.py", json.loads(self.pending.read_text())["candidates"])


class CliTest(_TmpStateMixin):
    def test_main_requires_subcommand(self) -> None:
        with self.assertRaises(SystemExit):
            gpt.main([])

    def test_record_rejects_bad_decision_via_argparse(self) -> None:
        with self.assertRaises(SystemExit):
            gpt.main(["record", "hooks/foo.py", "bogus"])


if __name__ == "__main__":
    unittest.main()
