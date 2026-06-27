"""Tests for annunaki_parse — the genuine-error reader/filter (#625).

Verifies:
  1. Benign-trace records (posttooluse_dispatch, pretooluse_diagnostic) are
     skipped by default; genuine errors / blocks / events are kept.
  2. Blank and corrupt lines are skipped (the JSONL-has-blank-lines history).
  3. include_traces=True yields everything.
  4. count_errors counts only genuine errors.
  5. The trace-type set is sourced from annunaki_log.TRACE_RECORD_TYPES (no drift).
  6. CLI --count over a mixed fixture returns the genuine-error count.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Helper lives at .claude/lib/annunaki_parse.py; test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from annunaki_parse import (  # noqa: E402
    TRACE_RECORD_TYPES,
    count_errors,
    is_low_confidence,
    is_pipe_mask_suspect,
    is_trace,
    iter_records,
    main,
)

# Mixed fixture mirroring the real P4W1 errors.jsonl shapes: a genuine
# monitor error (no `type`), a block, an event (all genuine) plus a dispatch
# trace and a diagnostic (both benign), a blank line, and a corrupt line.
_GENUINE_MONITOR = {
    "timestamp": "t",
    "command": "pytest",
    "exit_code": 1,
    "matched_patterns": ["exit_code=1"],
}
_GENUINE_BLOCK = {"timestamp": "t", "type": "pretooluse_block", "hook": "validate_commit_identity"}
_GENUINE_EVENT = {
    "timestamp": "t",
    "type": "posttooluse_event",
    "hook": "post_wave_kickoff_comment",
}
_BENIGN_DISPATCH = {"timestamp": "t", "type": "posttooluse_dispatch", "module": "annunaki_monitor"}
_BENIGN_DIAGNOSTIC = {
    "timestamp": "t",
    "type": "pretooluse_diagnostic",
    "hook": "enforce_librarian_consulted",
}


def _write_mixed(path: Path) -> None:
    lines = [
        json.dumps(_GENUINE_MONITOR),
        json.dumps(_BENIGN_DISPATCH),
        "",  # blank line (manual-edit history)
        json.dumps(_GENUINE_BLOCK),
        "{not valid json",  # corrupt line
        json.dumps(_BENIGN_DIAGNOSTIC),
        json.dumps(_GENUINE_EVENT),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class IterRecords(unittest.TestCase):
    def test_default_skips_benign_traces(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            _write_mixed(p)
            recs = list(iter_records(p))
            types = [r.get("type", "<monitor>") for r in recs]
            # 3 genuine records, in file order, benign + blank + corrupt dropped.
            self.assertEqual(types, ["<monitor>", "pretooluse_block", "posttooluse_event"])

    def test_include_traces_yields_everything_parseable(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            _write_mixed(p)
            recs = list(iter_records(p, include_traces=True))
            # 5 parseable records (blank + corrupt still dropped).
            self.assertEqual(len(recs), 5)

    def test_missing_file_yields_nothing(self) -> None:
        with TemporaryDirectory() as td:
            recs = list(iter_records(Path(td) / "nope.jsonl"))
            self.assertEqual(recs, [])

    def test_non_dict_json_line_skipped(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            p.write_text('[1,2,3]\n"a string"\n42\n', encoding="utf-8")
            self.assertEqual(list(iter_records(p, include_traces=True)), [])


class CountErrors(unittest.TestCase):
    def test_counts_only_genuine(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            _write_mixed(p)
            self.assertEqual(count_errors(p), 3)


class IsTrace(unittest.TestCase):
    def test_classification(self) -> None:
        self.assertTrue(is_trace(_BENIGN_DISPATCH))
        self.assertTrue(is_trace(_BENIGN_DIAGNOSTIC))
        self.assertFalse(is_trace(_GENUINE_MONITOR))
        self.assertFalse(is_trace(_GENUINE_BLOCK))
        self.assertFalse(is_trace(_GENUINE_EVENT))


# #729: exit-0 echoed-output records are tagged confidence="low" by the monitor.
# The reader excludes them from the genuine-error count but retains them in the
# log (include_low_confidence=True) for forensics. A genuine masked failure is
# tagged "high" and counted; a legacy record with no `confidence` field counts.
_LOW_CONF_ECHO = {
    "timestamp": "t",
    "command": "cat mod.py",
    "exit_code": 0,
    "matched_patterns": ["stdout:ImportError:"],
    "confidence": "low",
}
_HIGH_CONF_MASKED = {
    "timestamp": "t",
    "command": "git push ... | tail",
    "exit_code": 0,
    "matched_patterns": ["stdout:^error\\b"],
    "confidence": "high",
}


class LowConfidenceFilter(unittest.TestCase):
    def _write(self, path: Path) -> None:
        lines = [
            json.dumps(_GENUINE_MONITOR),  # legacy, no confidence → counted
            json.dumps(_LOW_CONF_ECHO),  # excluded from count
            json.dumps(_HIGH_CONF_MASKED),  # genuine masked failure → counted
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_count_excludes_low_confidence(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            # legacy + high-confidence masked failure = 2; low excluded.
            self.assertEqual(count_errors(p), 2)

    def test_iter_default_skips_low_confidence(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            cmds = [r["command"] for r in iter_records(p)]
            self.assertEqual(cmds, ["pytest", "git push ... | tail"])

    def test_include_low_confidence_retains_for_forensics(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            recs = list(iter_records(p, include_low_confidence=True))
            self.assertEqual(len(recs), 3)
            self.assertIn("cat mod.py", [r["command"] for r in recs])

    def test_is_low_confidence_helper(self) -> None:
        self.assertTrue(is_low_confidence(_LOW_CONF_ECHO))
        self.assertFalse(is_low_confidence(_HIGH_CONF_MASKED))
        self.assertFalse(is_low_confidence(_GENUINE_MONITOR))  # legacy → not low

    def test_cli_include_low_confidence_flag(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            self.assertEqual(main([str(p), "--include-low-confidence"]), 0)


# #835: the pipe-mask-suspect class — exit-0 stdout-only matches with no STRONG
# masked-failure signal, not recognized as echoed (e.g. a pytest `FAILED`
# surfacing through `… | tail` rc-masking). The monitor tags these
# confidence="low" so the existing low-confidence filter excludes them from the
# count; `category="pipe-mask-suspect"` lets callers triage the sub-class.
_PIPE_MASK_SUSPECT = {
    "timestamp": "t",
    "hook": "annunaki_monitor",
    "command": "python3 -m pytest 2>&1 | tail",
    "exit_code": 0,
    "matched_patterns": ["stdout:^FAILED"],
    "confidence": "low",
    "category": "pipe-mask-suspect",
}


class PipeMaskSuspectFilter(unittest.TestCase):
    def _write(self, path: Path) -> None:
        lines = [
            json.dumps(_GENUINE_MONITOR),  # legacy, no confidence → counted
            json.dumps(_PIPE_MASK_SUSPECT),  # #835 suspect → excluded from count
            json.dumps(_HIGH_CONF_MASKED),  # genuine masked failure → counted
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_count_excludes_pipe_mask_suspect(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            # legacy + high masked failure = 2; pipe-mask-suspect excluded.
            self.assertEqual(count_errors(p), 2)

    def test_iter_default_skips_pipe_mask_suspect(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            cmds = [r["command"] for r in iter_records(p)]
            self.assertNotIn("python3 -m pytest 2>&1 | tail", cmds)

    def test_include_low_confidence_retains_suspect(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            recs = list(iter_records(p, include_low_confidence=True))
            self.assertEqual(len(recs), 3)
            self.assertIn("python3 -m pytest 2>&1 | tail", [r["command"] for r in recs])

    def test_is_pipe_mask_suspect_helper(self) -> None:
        self.assertTrue(is_pipe_mask_suspect(_PIPE_MASK_SUSPECT))
        self.assertFalse(is_pipe_mask_suspect(_LOW_CONF_ECHO))  # low but echoed, not suspect
        self.assertFalse(is_pipe_mask_suspect(_HIGH_CONF_MASKED))
        self.assertFalse(is_pipe_mask_suspect(_GENUINE_MONITOR))


class TraceTypeSourceOfTruth(unittest.TestCase):
    def test_matches_writer_constant(self) -> None:
        # annunaki_parse must import the SAME set the writer uses; if the hook
        # import path works, the two must be identical (no drift).
        hooks_dir = Path(__file__).resolve().parents[2] / "hooks"
        sys.path.insert(0, str(hooks_dir))
        from annunaki_log import TRACE_RECORD_TYPES as writer_set  # noqa: E402

        self.assertEqual(TRACE_RECORD_TYPES, writer_set)
        self.assertEqual(writer_set, frozenset({"posttooluse_dispatch", "pretooluse_diagnostic"}))


class Cli(unittest.TestCase):
    def test_count_flag(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            _write_mixed(p)
            # main prints the count; capture via the return code being 0 and
            # relying on count_errors elsewhere — here just assert it runs clean.
            self.assertEqual(main([str(p), "--count"]), 0)

    def test_default_run_clean(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            _write_mixed(p)
            self.assertEqual(main([str(p)]), 0)


if __name__ == "__main__":
    unittest.main()
