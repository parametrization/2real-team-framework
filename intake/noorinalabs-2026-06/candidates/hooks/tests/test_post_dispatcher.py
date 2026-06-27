#!/usr/bin/env python3
"""Tests for post_dispatcher.py — PostToolUse single-entry dispatcher.

Mirrors the structure of the PreToolUse `dispatcher.py` invariants but for
PostToolUse semantics: hooks are advisory (no `block` decision), the
dispatcher aggregates `systemMessage` returns, individual-hook exceptions
are swallowed, and the registry must cover every PostToolUse entry in
`settings.json` at HEAD.

Run:  python3 -m pytest .claude/hooks/tests/test_post_dispatcher.py -v
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
_REPO_ROOT = _HOOKS_DIR.parent.parent

sys.path.insert(0, str(_HOOKS_DIR))

import post_dispatcher as pd  # noqa: E402


def _run_dispatcher(input_data: dict) -> tuple[int, str]:
    """Run `post_dispatcher.main()` against the given stdin dict.

    Returns (exit_code, stdout_text). `SystemExit` is captured so the test
    can assert exit code without terminating the test runner.
    """
    stdin = io.StringIO(json.dumps(input_data))
    stdout = io.StringIO()
    with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", stdout):
        try:
            pd.main()
        except SystemExit as e:
            code = int(e.code) if e.code is not None else 0
            return code, stdout.getvalue()
    return 0, stdout.getvalue()


class RegistryCompletenessTests(unittest.TestCase):
    """Every PostToolUse entry in settings.json must be in _REGISTRY."""

    def test_settings_post_tool_use_entries_all_registered(self):
        """If settings.json registered foo.py for matcher M, _REGISTRY[M] must
        list 'foo' (or the entry must already be `post_dispatcher.py`, the
        consolidation entry).
        """
        settings_path = _REPO_ROOT / ".claude" / "settings.json"
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
        post = settings.get("hooks", {}).get("PostToolUse", [])

        per_matcher: dict[str, list[str]] = {}
        for entry in post:
            matcher = entry.get("matcher", "")
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                # Extract the module basename from the path
                last = cmd.rsplit("/", 1)[-1]
                module = last.replace(".py", "")
                per_matcher.setdefault(matcher, []).append(module)

        for matcher, registered in per_matcher.items():
            # Allow either: every entry IS the dispatcher itself, OR every
            # individual hook is listed in _REGISTRY for that matcher.
            if all(m == "post_dispatcher" for m in registered):
                self.assertIn(
                    matcher,
                    pd._REGISTRY,
                    f"settings.json registers post_dispatcher for matcher "
                    f"{matcher!r} but _REGISTRY has no entry for it",
                )
                continue
            for module in registered:
                if module == "post_dispatcher":
                    continue
                self.assertIn(
                    module,
                    pd._REGISTRY.get(matcher, []),
                    f"settings.json registers {module!r} for matcher "
                    f"{matcher!r} but _REGISTRY[{matcher!r}] does not include it",
                )

    def test_registry_modules_all_importable(self):
        """Every module in _REGISTRY must be importable from .claude/hooks/."""
        import importlib

        for matcher, modules in pd._REGISTRY.items():
            for module_name in modules:
                try:
                    importlib.import_module(module_name)
                except ImportError as e:
                    self.fail(
                        f"_REGISTRY[{matcher!r}] lists {module_name!r} but it failed to import: {e}"
                    )

    def test_registry_modules_expose_check(self):
        """Every module in _REGISTRY must expose a `check(input_data)` function."""
        import importlib

        for matcher, modules in pd._REGISTRY.items():
            for module_name in modules:
                mod = importlib.import_module(module_name)
                self.assertTrue(
                    callable(getattr(mod, "check", None)),
                    f"{module_name} (registered for {matcher}) has no callable check()",
                )

    def test_edit_write_share_module_list(self):
        """Edit and Write should reference the same module sequence today."""
        self.assertEqual(pd._REGISTRY["Edit"], pd._REGISTRY["Write"])


class DispatchPerMatcherTests(unittest.TestCase):
    """For each matcher, verify every registered module's check() is called."""

    def _assert_all_called(self, matcher: str, extra_input: dict | None = None) -> None:
        input_data = {
            "tool_name": matcher,
            "hook_event_name": "PostToolUse",
            "tool_input": {},
            "tool_response": {},
        }
        if extra_input:
            input_data.update(extra_input)

        mocks: list[mock.MagicMock] = []
        modules = pd._REGISTRY[matcher]

        # Patch each module's `check` so we can assert call counts without
        # exercising real side effects.
        patches = []
        for module_name in modules:
            m = mock.MagicMock(return_value=None)
            mocks.append(m)
            patches.append(mock.patch(f"{module_name}.check", m))

        for p in patches:
            p.start()
        try:
            code, _out = _run_dispatcher(input_data)
        finally:
            for p in patches:
                p.stop()

        self.assertEqual(code, 0, f"matcher {matcher!r} should always exit 0")
        for module_name, m in zip(modules, mocks):
            self.assertEqual(
                m.call_count,
                1,
                f"check() for {module_name!r} ({matcher!r}) called {m.call_count} times",
            )

    def test_bash_dispatches_all_bash_modules(self):
        self._assert_all_called("Bash", {"tool_input": {"command": "echo hi"}})

    def test_edit_dispatches_all_edit_modules(self):
        self._assert_all_called("Edit", {"tool_input": {"file_path": "/tmp/x.py"}})

    def test_write_dispatches_all_write_modules(self):
        self._assert_all_called("Write", {"tool_input": {"file_path": "/tmp/x.py"}})

    def test_notebook_edit_dispatches_all_modules(self):
        self._assert_all_called("NotebookEdit", {"tool_input": {"notebook_path": "/tmp/x.ipynb"}})

    def test_unknown_matcher_dispatches_nothing(self):
        # No matcher → no module calls, clean exit 0
        input_data = {
            "tool_name": "Read",
            "hook_event_name": "PostToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
            "tool_response": {},
        }
        code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


class AggregationTests(unittest.TestCase):
    """systemMessage returns from N hooks aggregate into one output."""

    def test_two_messages_joined(self):
        input_data = {
            "tool_name": "Edit",
            "hook_event_name": "PostToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
            "tool_response": {},
        }
        with (
            mock.patch("ontology_tracker.check", return_value=None),
            mock.patch("suggest_generic_prompt.check", return_value={"systemMessage": "MSG_A"}),
            mock.patch("validate_edit_completion.check", return_value={"systemMessage": "MSG_B"}),
        ):
            code, out = _run_dispatcher(input_data)

        self.assertEqual(code, 0)
        self.assertNotEqual(out, "")
        parsed = json.loads(out)
        self.assertIn("MSG_A", parsed["systemMessage"])
        self.assertIn("MSG_B", parsed["systemMessage"])
        # Confirm separator
        self.assertIn("\n\n", parsed["systemMessage"])

    def test_all_none_yields_no_output(self):
        input_data = {
            "tool_name": "Edit",
            "hook_event_name": "PostToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
            "tool_response": {},
        }
        with (
            mock.patch("ontology_tracker.check", return_value=None),
            mock.patch("suggest_generic_prompt.check", return_value=None),
            mock.patch("validate_edit_completion.check", return_value=None),
        ):
            code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_non_systemmessage_returns_ignored(self):
        # `{"action": "tracked", ...}` style returns don't surface to harness
        input_data = {
            "tool_name": "Edit",
            "hook_event_name": "PostToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
            "tool_response": {},
        }
        with (
            mock.patch("ontology_tracker.check", return_value={"action": "tracked", "path": "x"}),
            mock.patch("suggest_generic_prompt.check", return_value=None),
            mock.patch("validate_edit_completion.check", return_value=None),
        ):
            code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


class FailOpenTests(unittest.TestCase):
    """Individual hook exceptions must not propagate."""

    def test_hook_raises_does_not_block_others(self):
        input_data = {
            "tool_name": "Edit",
            "hook_event_name": "PostToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
            "tool_response": {},
        }
        sibling = mock.MagicMock(return_value={"systemMessage": "SIBLING_FIRED"})
        with (
            mock.patch("ontology_tracker.check", side_effect=RuntimeError("boom")),
            mock.patch("suggest_generic_prompt.check", sibling),
            mock.patch("validate_edit_completion.check", return_value=None),
        ):
            code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 0, "exception must not propagate")
        self.assertEqual(sibling.call_count, 1, "sibling hooks must still run")
        self.assertIn("SIBLING_FIRED", out)

    def test_malformed_stdin_exits_zero(self):
        # Not valid JSON → exit 0 quietly
        stdin = io.StringIO("not json at all")
        stdout = io.StringIO()
        with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", stdout):
            try:
                pd.main()
                code = 0
            except SystemExit as e:
                code = int(e.code) if e.code is not None else 0
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "")

    def test_missing_check_attr_skipped(self):
        # If a registered module somehow lacks `check`, the dispatcher skips
        # it (mirrors PreToolUse dispatcher) rather than crashing.
        input_data = {
            "tool_name": "Edit",
            "hook_event_name": "PostToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
            "tool_response": {},
        }
        with (
            # Replace .check with None to simulate missing attribute (the
            # dispatcher uses getattr(..., None), so None and absent are
            # equivalent paths).
            mock.patch("ontology_tracker.check", new=None),
            mock.patch("suggest_generic_prompt.check", return_value={"systemMessage": "OK"}),
            mock.patch("validate_edit_completion.check", return_value=None),
        ):
            code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 0)
        self.assertIn("OK", out)


class BackwardCompatTests(unittest.TestCase):
    """Hooks that were refactored to expose check() must still work via main().

    These are sanity checks that the in-place refactor preserved the
    pre-refactor direct-invocation behavior. Detailed per-hook behavior is
    covered by each hook's own test file.
    """

    def test_auto_add_issue_to_board_main_handles_non_bash(self):
        import auto_add_issue_to_board as h

        stdin = io.StringIO(json.dumps({"tool_name": "Read"}))
        with mock.patch.object(sys, "stdin", stdin):
            try:
                h.main()
                code = 0
            except SystemExit as e:
                code = int(e.code) if e.code is not None else 0
        self.assertEqual(code, 0)

    def test_annunaki_monitor_check_returns_none_on_clean_bash(self):
        import annunaki_monitor as h

        result = h.check(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "echo ok"},
                "tool_output": {"stdout": "ok\n", "stderr": "", "exit_code": 0},
            }
        )
        self.assertIsNone(result)

    def test_annunaki_monitor_reads_tool_response_production_shape(self):
        # Regression for #453: production passes `tool_response`; legacy code
        # read `tool_output` and silently bailed (`combined_output = ""`).
        import annunaki_monitor as h

        # Force a fresh module-level dedup set so prior fixtures don't suppress.
        h._seen_hashes.clear()

        result = h.check(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "false"},
                "tool_response": {
                    "stdout": "",
                    "stderr": "fatal: simulated production failure\n",
                    "exit_code": 1,
                },
            }
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.get("action"), "logged")

    def test_auto_add_issue_to_board_reads_tool_response_production_shape(self):
        # Regression for #453: same field-name bug class. The hook short-circuits
        # at `stdout = tool_response.get("stdout","")` if reading the wrong key.
        # Mock subprocess.run so we never hit the network during the test.
        import auto_add_issue_to_board as h

        with mock.patch.object(h.subprocess, "run") as mock_run:
            mock_run.return_value.returncode = 0
            result = h.check(
                {
                    "tool_name": "Bash",
                    "tool_input": {
                        "command": "gh issue create --repo noorinalabs/noorinalabs-main --title T",
                    },
                    "tool_response": {
                        "stdout": "https://github.com/noorinalabs/noorinalabs-main/issues/999\n",
                        "stderr": "",
                        "exit_code": 0,
                    },
                }
            )
        self.assertIsNotNone(result)
        # The hook attempted to add; URL was parsed from stdout.
        mock_run.assert_called_once()

    def test_ontology_tracker_check_skips_non_edit_tool(self):
        import ontology_tracker as h

        result = h.check({"tool_name": "Read", "tool_input": {"file_path": "/tmp/x.py"}})
        self.assertIsNone(result)

    def test_suggest_generic_prompt_check_skips_non_claude_paths(self):
        import suggest_generic_prompt as h

        result = h.check({"tool_name": "Edit", "tool_input": {"file_path": "/tmp/x.py"}})
        self.assertIsNone(result)

    def test_validate_edit_completion_check_routes_posttooluse_edit(self):
        # PostToolUse Edit with no error → None (no sentinel side-effect)
        import validate_edit_completion as h

        result = h.check(
            {
                "tool_name": "Edit",
                "hook_event_name": "PostToolUse",
                "tool_input": {"file_path": "/tmp/x.py"},
                "tool_response": {"is_error": False},
            }
        )
        self.assertIsNone(result)


class DispatchTraceTests(unittest.TestCase):
    """#425: every interesting dispatched check() emits an annunaki
    `posttooluse_dispatch` record so /annunaki can show what each hook
    did per Bash call. "Interesting" = raised OR returned a non-None
    dict; None returns stay silent to avoid log spam.
    """

    def setUp(self) -> None:
        import os
        import tempfile

        import annunaki_log

        # #452 test-mode suppression skips ALL annunaki writes when
        # ENVIRONMENT=test / NOORIN_HOOK_TEST_MODE=1. These tests assert that
        # a posttooluse_dispatch record IS written, so clear both env vars for
        # the test body (restored in tearDown) — same pattern test_annunaki_log
        # uses for its production-write assertions.
        self._saved_env = {
            "ENVIRONMENT": os.environ.pop("ENVIRONMENT", None),
            "NOORIN_HOOK_TEST_MODE": os.environ.pop("NOORIN_HOOK_TEST_MODE", None),
        }
        self._tmp_dir = tempfile.mkdtemp(prefix="post_dispatch_trace_")
        # #625: posttooluse_dispatch traces now go to TRACES_FILE, not
        # ERRORS_FILE. Redirect both so the trace assertions read the right
        # stream and a stray error write doesn't leak to the real log.
        self._orig_errors_file = annunaki_log.ERRORS_FILE
        self._orig_traces_file = annunaki_log.TRACES_FILE
        self._errors_file = Path(self._tmp_dir) / "errors.jsonl"
        self._traces_file = Path(self._tmp_dir) / "traces.jsonl"
        annunaki_log.ERRORS_FILE = self._errors_file
        annunaki_log.TRACES_FILE = self._traces_file

    def tearDown(self) -> None:
        import os
        import shutil

        import annunaki_log

        annunaki_log.ERRORS_FILE = self._orig_errors_file
        annunaki_log.TRACES_FILE = self._orig_traces_file
        shutil.rmtree(self._tmp_dir, ignore_errors=True)
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _read_records(self) -> list[dict]:
        # #625: dispatch traces are written to TRACES_FILE, so the trace
        # assertions read from there (not ERRORS_FILE).
        if not self._traces_file.exists():
            return []
        with self._traces_file.open("r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_action_dict_return_records_dispatch_trace(self) -> None:
        """POS (#425 core case): when post_wave_kickoff_comment returns
        `{'action': 'post', ...}` the dispatcher records a trace so the
        action is visible in /annunaki — was previously invisible because
        the dispatcher only surfaces `systemMessage` returns."""
        input_data = {
            "tool_name": "Bash",
            "hook_event_name": "PostToolUse",
            "tool_input": {"command": "gh issue edit 423 --add-label p3-wave-10"},
            "tool_response": {"stdout": "", "stderr": "", "exitCode": 0},
        }
        action_return = {"action": "post", "repo": "noorinalabs-main", "issue": "423"}
        with (
            mock.patch("annunaki_monitor.check", return_value=None),
            mock.patch("auto_add_issue_to_board.check", return_value=None),
            mock.patch("post_wave_kickoff_comment.check", return_value=action_return),
            # post_label_change_wave_field_sync joined the Bash registry via
            # #445 after wave-10; mock it None so only the action return traces.
            mock.patch("post_label_change_wave_field_sync.check", return_value=None),
        ):
            code, _ = _run_dispatcher(input_data)
        self.assertEqual(code, 0)

        traces = [r for r in self._read_records() if r["type"] == "posttooluse_dispatch"]
        # Only the post_wave_kickoff_comment record fires (the other two
        # returned None — those are silent per design).
        self.assertEqual(len(traces), 1, "exactly one trace for the non-None return")
        rec = traces[0]
        self.assertEqual(rec["module"], "post_wave_kickoff_comment")
        self.assertEqual(rec["tool_name"], "Bash")
        self.assertIn("'action': 'post'", rec["outcome"]["returned"])
        self.assertIsNone(rec["outcome"]["raised"])
        self.assertIsNone(rec["outcome"]["traceback_excerpt"])
        self.assertIn("gh issue edit", rec["command"])

    def test_none_returns_silent_by_default(self) -> None:
        """NEG: when every hook returns None (overwhelming common case),
        the dispatcher writes ZERO trace records — keeps the log low-noise.
        """
        input_data = {
            "tool_name": "Bash",
            "hook_event_name": "PostToolUse",
            "tool_input": {"command": "echo hi"},
            "tool_response": {"stdout": "hi\n", "stderr": "", "exitCode": 0},
        }
        with (
            mock.patch("annunaki_monitor.check", return_value=None),
            mock.patch("auto_add_issue_to_board.check", return_value=None),
            mock.patch("post_wave_kickoff_comment.check", return_value=None),
            mock.patch("post_label_change_wave_field_sync.check", return_value=None),
        ):
            code, _ = _run_dispatcher(input_data)
        self.assertEqual(code, 0)
        self.assertEqual(self._read_records(), [])

    def test_raised_exception_records_trace_with_traceback(self) -> None:
        """POS: a raising hook surfaces type + traceback in the trace
        record — was previously a bare `except: continue` with zero
        forensic visibility. Sibling hooks must still run."""
        input_data = {
            "tool_name": "Bash",
            "hook_event_name": "PostToolUse",
            "tool_input": {"command": "echo trace-test"},
            "tool_response": {"stdout": "", "stderr": "", "exitCode": 0},
        }
        sibling = mock.MagicMock(return_value=None)
        with (
            mock.patch("annunaki_monitor.check", side_effect=RuntimeError("simulated crash")),
            mock.patch("auto_add_issue_to_board.check", sibling),
            mock.patch("post_wave_kickoff_comment.check", return_value=None),
            mock.patch("post_label_change_wave_field_sync.check", return_value=None),
        ):
            code, _ = _run_dispatcher(input_data)
        self.assertEqual(code, 0, "exception still swallowed for advisory contract")
        self.assertEqual(sibling.call_count, 1, "sibling still runs after sibling-raise")

        traces = [r for r in self._read_records() if r["type"] == "posttooluse_dispatch"]
        self.assertEqual(len(traces), 1)
        rec = traces[0]
        self.assertEqual(rec["module"], "annunaki_monitor")
        self.assertIn("RuntimeError", rec["outcome"]["raised"])
        self.assertIn("simulated crash", rec["outcome"]["raised"])
        self.assertIsNotNone(rec["outcome"]["traceback_excerpt"])
        # Traceback excerpt is bounded at 500 chars and the unittest.mock
        # frames often consume that budget before the actual exception
        # text appears. The starting "Traceback" sentinel is enough to
        # confirm we captured one; the exception type + message are
        # already asserted via `outcome.raised`.
        self.assertTrue(rec["outcome"]["traceback_excerpt"].startswith("Traceback"))

    def test_trace_all_env_var_forces_none_returns_logged(self) -> None:
        """POS: when POST_DISPATCHER_TRACE_ALL=1, even None returns
        produce a trace record — useful when debugging "did the hook
        even run?" questions (the #425 original symptom)."""
        import importlib

        import post_dispatcher

        input_data = {
            "tool_name": "Bash",
            "hook_event_name": "PostToolUse",
            "tool_input": {"command": "echo trace-all"},
            "tool_response": {"stdout": "", "stderr": "", "exitCode": 0},
        }
        # Derive the expected module set from the registry itself so this test
        # does not rot when the registry grows (it gained
        # post_label_change_wave_field_sync via #445 after wave-10 authored it).
        bash_modules = list(post_dispatcher._REGISTRY["Bash"])
        with mock.patch.dict("os.environ", {"POST_DISPATCHER_TRACE_ALL": "1"}):
            importlib.reload(post_dispatcher)
            try:
                with contextlib.ExitStack() as stack:
                    for mod in bash_modules:
                        stack.enter_context(mock.patch(f"{mod}.check", return_value=None))
                    stdin = io.StringIO(json.dumps(input_data))
                    stdout = io.StringIO()
                    stack.enter_context(mock.patch.object(sys, "stdin", stdin))
                    stack.enter_context(mock.patch.object(sys, "stdout", stdout))
                    try:
                        post_dispatcher.main()
                    except SystemExit:
                        pass
            finally:
                importlib.reload(post_dispatcher)

        traces = [r for r in self._read_records() if r["type"] == "posttooluse_dispatch"]
        self.assertEqual(
            len(traces),
            len(bash_modules),
            "TRACE_ALL must emit one record per registered Bash module",
        )
        modules = {t["module"] for t in traces}
        self.assertEqual(modules, set(bash_modules))

    def test_elapsed_ms_recorded(self) -> None:
        """POS: every trace record carries an `elapsed_ms` field for
        spotting slow check()s. Doesn't pin a value, just presence + type."""
        input_data = {
            "tool_name": "Bash",
            "hook_event_name": "PostToolUse",
            "tool_input": {"command": "echo timing"},
            "tool_response": {"stdout": "", "stderr": "", "exitCode": 0},
        }
        with (
            mock.patch("annunaki_monitor.check", return_value=None),
            mock.patch("auto_add_issue_to_board.check", return_value=None),
            mock.patch(
                "post_wave_kickoff_comment.check",
                return_value={"action": "skip_no_row", "repo": "x", "issue": "0"},
            ),
            mock.patch("post_label_change_wave_field_sync.check", return_value=None),
        ):
            _run_dispatcher(input_data)
        traces = [r for r in self._read_records() if r["type"] == "posttooluse_dispatch"]
        self.assertEqual(len(traces), 1)
        self.assertIsInstance(traces[0]["outcome"]["elapsed_ms"], (int, float))
        self.assertGreaterEqual(traces[0]["outcome"]["elapsed_ms"], 0)


class EmitDispatchSummaryOptInTests(unittest.TestCase):
    """#425 followup — per-hook opt-in surfacing of action-shaped returns
    as systemMessage. Hooks set `EMIT_DISPATCH_SUMMARY = True` at module
    scope to opt in. Default is False; no behavior change for unmarked
    hooks (preserves existing harness UX for annunaki_monitor, etc.)."""

    def _run(self, action_return: dict, opt_in: bool) -> str:
        """Run the dispatcher with post_wave_kickoff_comment returning the
        given action dict and EMIT_DISPATCH_SUMMARY set per `opt_in`.
        Returns the dispatcher's stdout."""
        input_data = {
            "tool_name": "Bash",
            "hook_event_name": "PostToolUse",
            "tool_input": {"command": "gh issue edit 423 --add-label p3-wave-10"},
            "tool_response": {"stdout": "", "stderr": "", "exitCode": 0},
        }
        with (
            mock.patch("annunaki_monitor.check", return_value=None),
            mock.patch("auto_add_issue_to_board.check", return_value=None),
            mock.patch("post_wave_kickoff_comment.check", return_value=action_return),
            mock.patch("post_wave_kickoff_comment.EMIT_DISPATCH_SUMMARY", opt_in, create=True),
        ):
            _, out = _run_dispatcher(input_data)
        return out

    def test_opt_in_synthesizes_systemmessage_from_action(self) -> None:
        """POS (#425 core): opt-in hook with action-return → systemMessage
        appears in dispatcher stdout, with module name + action + extra
        keys formatted for operator visibility."""
        out = self._run({"action": "post", "repo": "noorinalabs-main", "issue": "423"}, opt_in=True)
        self.assertNotEqual(out, "")
        parsed = json.loads(out)
        msg = parsed["systemMessage"]
        self.assertIn("post_wave_kickoff_comment", msg)
        self.assertIn("action=post", msg)
        self.assertIn("issue=423", msg)
        self.assertIn("repo=noorinalabs-main", msg)

    def test_opt_out_default_stays_silent(self) -> None:
        """NEG: default (EMIT_DISPATCH_SUMMARY absent/False) → dispatcher
        stdout stays empty for action-shaped returns. Preserves pre-#425
        UX for hooks that haven't opted in."""
        out = self._run(
            {"action": "post", "repo": "noorinalabs-main", "issue": "423"}, opt_in=False
        )
        self.assertEqual(out, "", "opt-out default must not surface action returns")

    def test_explicit_systemmessage_always_wins_over_synthesis(self) -> None:
        """NEG: when a hook returns BOTH `systemMessage` and `action`, the
        explicit message is used; synthesis is skipped. (Synthesis is a
        fallback for hooks that don't carry their own message.)"""
        out = self._run(
            {
                "systemMessage": "EXPLICIT_MESSAGE",
                "action": "post",
                "repo": "x",
                "issue": "1",
            },
            opt_in=True,
        )
        parsed = json.loads(out)
        msg = parsed["systemMessage"]
        self.assertEqual(msg.strip(), "EXPLICIT_MESSAGE")
        self.assertNotIn("action=post", msg)

    def test_opt_in_with_no_action_key_stays_silent(self) -> None:
        """NEG: opt-in module returning a dict WITHOUT an `action` key →
        no synthesis (synthesis requires an action-shaped dict)."""
        out = self._run({}, opt_in=True)
        self.assertEqual(out, "")

    def test_post_wave_kickoff_comment_opts_in(self) -> None:
        """POS contract: the real post_wave_kickoff_comment module sets
        EMIT_DISPATCH_SUMMARY = True. Locks the opt-in attestation so a
        future edit removing it has to update this test."""
        import post_wave_kickoff_comment

        self.assertIs(getattr(post_wave_kickoff_comment, "EMIT_DISPATCH_SUMMARY", False), True)


if __name__ == "__main__":
    unittest.main()
