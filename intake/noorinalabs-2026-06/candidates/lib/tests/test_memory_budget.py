"""Tests for memory_budget -- the project-memory corpus size/count budget (#733).

Verifies:
  1. Under budget on all three dimensions -> exit 0, "within budget".
  2. Exactly AT each cap -> exit 0 (the cap is inclusive; at-limit is allowed).
  3. One-over on EACH dimension independently -> exit 1, names that dimension.
  4. The over-budget diagnostic is a HARD BLOCK with actionable content
     (current/limit, "OVER by N", consolidate/retire guidance).
  5. session_handoff.md and MEMORY.md are excluded from the file count.
  6. Missing memory dir / missing MEMORY.md -> exit 2 (cannot evaluate).
  7. The budget lives in ONE place: the three module constants drive the caps.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import memory_budget  # noqa: E402
from memory_budget import (  # noqa: E402
    MAX_INDEX_ENTRIES,
    MAX_MEMORY_BYTES,
    MAX_MEMORY_FILES,
    count_index_entries,
    count_memory_files,
    evaluate,
    gather_metrics,
    main,
)


def _build_corpus(
    root: Path,
    *,
    entries: int,
    files: int,
    extra_md_bytes: int = 0,
    include_handoff: bool = False,
) -> Path:
    """Create a .claude/memory corpus with the requested shape; return its dir.

    `entries` index rows are written to MEMORY.md; `files` topic *.md files are
    created beside it. `extra_md_bytes` pads MEMORY.md to exercise the byte cap.
    `include_handoff` adds the gitignored session_handoff.md (must NOT count).
    """
    memory_dir = root / ".claude" / "memory"
    memory_dir.mkdir(parents=True)

    lines = [f"- [Entry {i}](topic_{i}.md) — hook line {i}." for i in range(entries)]
    body = "\n".join(lines) + ("\n" if lines else "")
    if extra_md_bytes > 0:
        body += "x" * extra_md_bytes
    (memory_dir / "MEMORY.md").write_text(body, encoding="utf-8")

    for i in range(files):
        (memory_dir / f"topic_{i}.md").write_text(f"topic {i}\n", encoding="utf-8")
    if include_handoff:
        (memory_dir / "session_handoff.md").write_text("handoff\n", encoding="utf-8")
    return memory_dir


class CountingTests(unittest.TestCase):
    def test_index_entries_count_only_list_link_rows(self) -> None:
        with TemporaryDirectory() as d:
            md = Path(d) / "MEMORY.md"
            md.write_text(
                "# heading (not an entry)\n"
                "- [A](a.md) — x\n"
                "- [B](b.md) — y\n"
                "  - nested (not top-level)\n"
                "plain line\n",
                encoding="utf-8",
            )
            self.assertEqual(count_index_entries(md), 2)

    def test_file_count_excludes_memory_md_and_handoff(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = _build_corpus(Path(d), entries=3, files=3, include_handoff=True)
            # 3 topic files; MEMORY.md and session_handoff.md must NOT count.
            self.assertEqual(count_memory_files(memory_dir), 3)


class UnderAndAtBudgetTests(unittest.TestCase):
    def test_well_under_budget_exits_zero(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = _build_corpus(Path(d), entries=10, files=10)
            self.assertEqual(evaluate(memory_dir), 0)

    def test_exactly_at_caps_is_allowed(self) -> None:
        # At-limit on entries AND files simultaneously; size left well under.
        with TemporaryDirectory() as d:
            memory_dir = _build_corpus(Path(d), entries=MAX_INDEX_ENTRIES, files=MAX_MEMORY_FILES)
            metrics = gather_metrics(memory_dir)
            by_label = {m.label: m for m in metrics}
            self.assertEqual(by_label["index entries"].current, MAX_INDEX_ENTRIES)
            self.assertFalse(by_label["index entries"].over)
            self.assertFalse(by_label["memory files"].over)
            self.assertEqual(evaluate(memory_dir), 0)


class OverBudgetTests(unittest.TestCase):
    def test_one_over_entries_blocks(self) -> None:
        with TemporaryDirectory() as d:
            # Push files down so ONLY the entry dimension is over.
            memory_dir = _build_corpus(Path(d), entries=MAX_INDEX_ENTRIES + 1, files=5)
            self.assertEqual(evaluate(memory_dir), 1)

    def test_one_over_files_blocks(self) -> None:
        with TemporaryDirectory() as d:
            # Keep entries low so ONLY the file dimension is over.
            memory_dir = _build_corpus(Path(d), entries=5, files=MAX_MEMORY_FILES + 1)
            self.assertEqual(evaluate(memory_dir), 1)

    def test_one_over_bytes_blocks(self) -> None:
        with TemporaryDirectory() as d:
            # Few entries/files, but pad MEMORY.md past the byte cap.
            memory_dir = _build_corpus(
                Path(d), entries=3, files=3, extra_md_bytes=MAX_MEMORY_BYTES + 1
            )
            metrics = gather_metrics(memory_dir)
            size = next(m for m in metrics if m.label == "MEMORY.md size")
            self.assertTrue(size.over)
            self.assertEqual(evaluate(memory_dir), 1)

    def test_over_budget_diagnostic_is_actionable(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = _build_corpus(Path(d), entries=MAX_INDEX_ENTRIES + 3, files=5)
            metrics = gather_metrics(memory_dir)
            msg = memory_budget.over_budget_message(metrics)
            self.assertIn("MEMORY BUDGET EXCEEDED", msg)
            self.assertIn("index entries", msg)
            self.assertIn("OVER by 3", msg)
            self.assertIn(str(MAX_INDEX_ENTRIES), msg)
            # Must tell the human the fix is consolidate/retire, not auto-fixable.
            self.assertIn("cannot be auto-fixed", msg)
            self.assertIn("CONSOLIDATE", msg)
            self.assertIn("RETIRE", msg)


class CliAndErrorTests(unittest.TestCase):
    def test_main_repo_root_arg_resolves_corpus(self) -> None:
        with TemporaryDirectory() as d:
            _build_corpus(Path(d), entries=4, files=4)
            self.assertEqual(main(["memory_budget.py", d]), 0)

    def test_main_memory_dir_override(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = _build_corpus(Path(d), entries=4, files=4)
            self.assertEqual(main(["memory_budget.py", "--memory-dir", str(memory_dir)]), 0)

    def test_missing_memory_dir_exits_two(self) -> None:
        with TemporaryDirectory() as d:
            # No .claude/memory created.
            self.assertEqual(main(["memory_budget.py", d]), 2)

    def test_missing_memory_md_exits_two(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = Path(d) / ".claude" / "memory"
            memory_dir.mkdir(parents=True)
            (memory_dir / "topic_0.md").write_text("x\n", encoding="utf-8")
            self.assertEqual(main(["memory_budget.py", d]), 2)


class RealCorpusWithinBudgetTests(unittest.TestCase):
    """The check must PASS on the very corpus that ships it — i.e. the caps sit
    above the current consolidated size with headroom (else the gate red-blocks
    the PR adding it)."""

    def test_parent_memory_corpus_is_within_budget(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        memory_dir = repo_root / ".claude" / "memory"
        if not (memory_dir / "MEMORY.md").is_file():
            self.skipTest("parent memory corpus not present in this checkout")
        self.assertEqual(evaluate(memory_dir), 0)


if __name__ == "__main__":
    unittest.main()
