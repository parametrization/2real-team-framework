"""Tests for wave_field_option — wave board option auto-create helper (#868).

Covers:
  1. Option-name grammar for all three label forms (#810).
  2. check_wave_option — present, absent, error, bad label.
  3. ensure_wave_option — idempotent no-op, create+verify, missing auth scope,
     introspect failure, mutation failure, read-back verification failure.
  4. Full-list-preserve — existing options are included unchanged in the mutation.
  5. CLI exit codes: ensure exit 0/1, check exit 0/2/1.
  6. ensure_wave_option preserves existing options in the mutation body.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wave_field_option as wfo  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _field_response(options: list[dict]) -> str:
    """Fake GraphQL introspect response with the given options list."""
    return json.dumps(
        {
            "data": {
                "organization": {
                    "projectV2": {
                        "id": "PVT_test123",
                        "field": {
                            "id": "FIELD_test456",
                            "options": options,
                        },
                    }
                }
            }
        }
    )


_EXISTING_OPTIONS = [
    {"id": "OPT_w16", "name": "W16", "color": "BLUE", "description": ""},
    {"id": "OPT_w17", "name": "W17", "color": "GREEN", "description": "Wave 17"},
]


def _runner_present() -> str:
    """Introspect runner: W18 already exists in options."""
    options = _EXISTING_OPTIONS + [
        {"id": "OPT_w18", "name": "W18", "color": "PURPLE", "description": ""}
    ]
    return _field_response(options)


def _runner_absent(query: str, variables: dict) -> str:  # noqa: ARG001
    """Introspect runner: W18 absent, only W16/W17 present."""
    return _field_response(_EXISTING_OPTIONS)


def _runner_absent_then_present() -> object:
    """Returns a runner that yields 'absent' on first call, 'present' on second.

    Used to simulate the read-back-verify step after a successful mutation.
    """
    calls = [0]

    def runner(query: str, variables: dict) -> str:  # noqa: ARG001
        calls[0] += 1
        if calls[0] == 1:
            return _field_response(_EXISTING_OPTIONS)
        # Second call (read-back): include W18
        return _field_response(
            _EXISTING_OPTIONS
            + [{"id": "OPT_w18_new", "name": "W18", "color": "PURPLE", "description": ""}]
        )

    return runner


def _ok_mutation_runner(body: str) -> str:  # noqa: ARG001
    """Stdin runner: mutation succeeds."""
    return json.dumps(
        {
            "data": {
                "updateProjectV2Field": {
                    "projectV2Field": {
                        "id": "FIELD_test456",
                        "options": [
                            {"id": "OPT_w16", "name": "W16"},
                            {"id": "OPT_w17", "name": "W17"},
                            {"id": "OPT_w18_new", "name": "W18"},
                        ],
                    }
                }
            }
        }
    )


def _error_mutation_runner(body: str) -> str:  # noqa: ARG001
    """Stdin runner: mutation returns GraphQL errors."""
    return json.dumps({"errors": [{"message": "Field not found"}]})


def _auth_has_scope() -> str:
    return "Token scopes: 'gist', 'project', 'read:org', 'repo', 'workflow'"


def _auth_no_scope() -> str:
    return "Token scopes: 'gist', 'read:org', 'repo', 'workflow'"


# ---------------------------------------------------------------------------
# Option-name grammar tests
# ---------------------------------------------------------------------------


class TestWaveLabelToOptionName(unittest.TestCase):
    """Grammar: wave-{X} → W{X}, p{N}-wave-{M} → P{N}W{M}, wave-x → WX."""

    def test_global_form(self) -> None:
        self.assertEqual(wfo._wave_label_to_option_name("wave-18"), "W18")

    def test_global_form_large_number(self) -> None:
        self.assertEqual(wfo._wave_label_to_option_name("wave-99"), "W99")

    def test_legacy_form(self) -> None:
        self.assertEqual(wfo._wave_label_to_option_name("p6-wave-17"), "P6W17")

    def test_legacy_form_multi_digit_phase(self) -> None:
        self.assertEqual(wfo._wave_label_to_option_name("p12-wave-5"), "P12W5")

    def test_placeholder(self) -> None:
        self.assertEqual(wfo._wave_label_to_option_name("wave-x"), "WX")

    def test_invalid_returns_none(self) -> None:
        self.assertIsNone(wfo._wave_label_to_option_name("bug"))
        self.assertIsNone(wfo._wave_label_to_option_name("wave-18-special"))
        self.assertIsNone(wfo._wave_label_to_option_name("p6-wave-17-frozen"))
        self.assertIsNone(wfo._wave_label_to_option_name(""))

    def test_anchored_rejects_suffix(self) -> None:
        # "wave-x" placeholder only — "wave-x-draft" must NOT match
        self.assertIsNone(wfo._wave_label_to_option_name("wave-x-draft"))


# ---------------------------------------------------------------------------
# _introspect_field tests
# ---------------------------------------------------------------------------


class TestIntrospectField(unittest.TestCase):
    def test_returns_ids_and_options(self) -> None:
        runner = lambda q, v: _runner_absent(q, v)  # noqa: E731
        result = wfo._introspect_field(runner=runner)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["project_id"], "PVT_test123")
        self.assertEqual(result["field_id"], "FIELD_test456")
        self.assertEqual(len(result["options"]), 2)
        self.assertEqual(result["options"][0]["name"], "W16")

    def test_returns_none_on_runner_error(self) -> None:
        def bad_runner(q: str, v: dict) -> str:
            raise OSError("network down")

        result = wfo._introspect_field(runner=bad_runner)
        self.assertIsNone(result)

    def test_returns_none_on_empty_response(self) -> None:
        result = wfo._introspect_field(runner=lambda q, v: "")
        self.assertIsNone(result)

    def test_returns_none_on_bad_json(self) -> None:
        result = wfo._introspect_field(runner=lambda q, v: "not-json{")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# check_wave_option tests
# ---------------------------------------------------------------------------


class TestCheckWaveOption(unittest.TestCase):
    def test_present_when_option_exists(self) -> None:
        options_with_w18 = _EXISTING_OPTIONS + [
            {"id": "OPT_w18", "name": "W18", "color": "PURPLE", "description": ""}
        ]
        runner = lambda q, v: _field_response(options_with_w18)  # noqa: E731
        res = wfo.check_wave_option("wave-18", runner=runner)
        self.assertEqual(res["status"], "present")
        self.assertEqual(res["option_name"], "W18")
        self.assertEqual(res["option_id"], "OPT_w18")

    def test_absent_when_option_missing(self) -> None:
        res = wfo.check_wave_option("wave-18", runner=_runner_absent)
        self.assertEqual(res["status"], "absent")
        self.assertEqual(res["option_name"], "W18")

    def test_error_on_bad_label(self) -> None:
        res = wfo.check_wave_option("not-a-wave-label", runner=_runner_absent)
        self.assertEqual(res["status"], "error")
        self.assertIn("not-a-wave-label", res["detail"])

    def test_error_on_introspect_failure(self) -> None:
        res = wfo.check_wave_option("wave-18", runner=lambda q, v: "")
        self.assertEqual(res["status"], "error")
        self.assertIn("introspect", res["detail"])

    def test_legacy_label(self) -> None:
        options = [{"id": "OPT_p6w17", "name": "P6W17", "color": "BLUE", "description": ""}]
        runner = lambda q, v: _field_response(options)  # noqa: E731
        res = wfo.check_wave_option("p6-wave-17", runner=runner)
        self.assertEqual(res["status"], "present")
        self.assertEqual(res["option_name"], "P6W17")

    def test_placeholder_label(self) -> None:
        options = [{"id": "OPT_wx", "name": "WX", "color": "GRAY", "description": ""}]
        runner = lambda q, v: _field_response(options)  # noqa: E731
        res = wfo.check_wave_option("wave-x", runner=runner)
        self.assertEqual(res["status"], "present")
        self.assertEqual(res["option_name"], "WX")


# ---------------------------------------------------------------------------
# ensure_wave_option tests
# ---------------------------------------------------------------------------


class TestEnsureWaveOption(unittest.TestCase):
    def test_idempotent_when_already_present(self) -> None:
        options_with_w18 = _EXISTING_OPTIONS + [
            {"id": "OPT_w18", "name": "W18", "color": "PURPLE", "description": ""}
        ]
        runner = lambda q, v: _field_response(options_with_w18)  # noqa: E731
        # stdin_runner should NOT be called (no mutation needed).
        stdin_runner = MagicMock()
        res = wfo.ensure_wave_option("wave-18", runner=runner, stdin_runner=stdin_runner)
        self.assertEqual(res["status"], "present")
        self.assertEqual(res["option_name"], "W18")
        stdin_runner.assert_not_called()

    def test_creates_when_absent(self) -> None:
        two_phase_runner = _runner_absent_then_present()
        res = wfo.ensure_wave_option(
            "wave-18",
            auth_runner=_auth_has_scope,
            runner=two_phase_runner,
            stdin_runner=_ok_mutation_runner,
        )
        self.assertEqual(res["status"], "created")
        self.assertEqual(res["option_name"], "W18")

    def test_error_on_bad_label(self) -> None:
        res = wfo.ensure_wave_option(
            "not-a-label", runner=_runner_absent, stdin_runner=_ok_mutation_runner
        )
        self.assertEqual(res["status"], "error")
        self.assertIn("not-a-label", res["detail"])

    def test_error_when_introspect_fails(self) -> None:
        res = wfo.ensure_wave_option("wave-18", runner=lambda q, v: "")
        self.assertEqual(res["status"], "error")
        self.assertIn("introspect", res["detail"])

    def test_error_when_no_auth_scope(self) -> None:
        res = wfo.ensure_wave_option(
            "wave-18",
            auth_runner=_auth_no_scope,
            runner=_runner_absent,
            stdin_runner=_ok_mutation_runner,
        )
        self.assertEqual(res["status"], "error")
        self.assertIn("project scope", res["detail"])

    def test_error_when_mutation_fails(self) -> None:
        res = wfo.ensure_wave_option(
            "wave-18",
            auth_runner=_auth_has_scope,
            runner=_runner_absent,
            stdin_runner=_error_mutation_runner,
        )
        self.assertEqual(res["status"], "error")
        self.assertIn("mutation failed", res["detail"])

    def test_error_when_readback_fails(self) -> None:
        """Option appears to mutate OK but read-back finds it absent."""
        calls = [0]

        def runner(q: str, v: dict) -> str:
            calls[0] += 1
            if calls[0] == 1:
                return _field_response(_EXISTING_OPTIONS)
            # Read-back still returns W18 absent
            return _field_response(_EXISTING_OPTIONS)

        res = wfo.ensure_wave_option(
            "wave-18",
            auth_runner=_auth_has_scope,
            runner=runner,
            stdin_runner=_ok_mutation_runner,
        )
        self.assertEqual(res["status"], "error")
        self.assertIn("read-back", res["detail"].lower())

    def test_full_list_preserve(self) -> None:
        """The mutation body must include all existing options, not just the new one."""
        captured: list[str] = []

        def stdin_runner(body: str) -> str:
            captured.append(body)
            return _ok_mutation_runner(body)

        # read-back runner: on second call include W18
        two_phase_runner = _runner_absent_then_present()
        wfo.ensure_wave_option(
            "wave-18",
            auth_runner=_auth_has_scope,
            runner=two_phase_runner,
            stdin_runner=stdin_runner,
        )
        self.assertEqual(len(captured), 1)
        body = json.loads(captured[0])
        options_sent = body["variables"]["input"]["singleSelectOptions"]
        names_sent = [o["name"] for o in options_sent]
        # Existing W16, W17 must be preserved; new W18 must be appended.
        self.assertIn("W16", names_sent)
        self.assertIn("W17", names_sent)
        self.assertIn("W18", names_sent)
        # New option color must be PURPLE (wave-label badge colour).
        new_opt = next(o for o in options_sent if o["name"] == "W18")
        self.assertEqual(new_opt["color"], wfo.NEW_OPTION_COLOR)

    def test_existing_option_colors_preserved(self) -> None:
        """Existing option colors/descriptions survive the full-list PUT."""
        captured: list[str] = []

        def stdin_runner(body: str) -> str:
            captured.append(body)
            return _ok_mutation_runner(body)

        two_phase_runner = _runner_absent_then_present()
        wfo.ensure_wave_option(
            "wave-18",
            auth_runner=_auth_has_scope,
            runner=two_phase_runner,
            stdin_runner=stdin_runner,
        )
        body = json.loads(captured[0])
        options_sent = body["variables"]["input"]["singleSelectOptions"]
        w17_sent = next(o for o in options_sent if o["name"] == "W17")
        self.assertEqual(w17_sent["color"], "GREEN")
        self.assertEqual(w17_sent["description"], "Wave 17")

    def test_legacy_label_creates_correct_option(self) -> None:
        options = [{"id": "OPT_w16", "name": "W16", "color": "BLUE", "description": ""}]

        calls = [0]

        def runner(q: str, v: dict) -> str:
            calls[0] += 1
            if calls[0] == 1:
                return _field_response(options)
            # read-back: include P6W17
            return _field_response(
                options
                + [{"id": "OPT_p6w17", "name": "P6W17", "color": "PURPLE", "description": ""}]
            )

        captured: list[str] = []

        def stdin_runner(body: str) -> str:
            captured.append(body)
            return _ok_mutation_runner(body)

        res = wfo.ensure_wave_option(
            "p6-wave-17",
            auth_runner=_auth_has_scope,
            runner=runner,
            stdin_runner=stdin_runner,
        )
        self.assertEqual(res["status"], "created")
        self.assertEqual(res["option_name"], "P6W17")
        body = json.loads(captured[0])
        options_sent = body["variables"]["input"]["singleSelectOptions"]
        names_sent = [o["name"] for o in options_sent]
        self.assertIn("P6W17", names_sent)


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCli(unittest.TestCase):
    def _make_ensure_ok_runners(self) -> tuple:
        """Runners for a successful 'ensure' flow where the option is absent then present."""
        return (
            _auth_has_scope,
            _runner_absent_then_present(),
            _ok_mutation_runner,
        )

    def test_ensure_exits_0_when_present(self) -> None:
        # Monkey-patch the internal functions for CLI routing
        original_ensure = wfo.ensure_wave_option

        def fake_ensure(label: str, org: str, project: int) -> dict:
            return {"status": "present", "option_name": "W18"}

        wfo.ensure_wave_option = fake_ensure  # type: ignore[assignment]
        try:
            rc = wfo.main(["ensure", "wave-18"])
        finally:
            wfo.ensure_wave_option = original_ensure  # type: ignore[assignment]
        self.assertEqual(rc, 0)

    def test_ensure_exits_0_when_created(self) -> None:
        original_ensure = wfo.ensure_wave_option

        def fake_ensure(label: str, org: str, project: int) -> dict:
            return {"status": "created", "option_name": "W18"}

        wfo.ensure_wave_option = fake_ensure  # type: ignore[assignment]
        try:
            rc = wfo.main(["ensure", "wave-18"])
        finally:
            wfo.ensure_wave_option = original_ensure  # type: ignore[assignment]
        self.assertEqual(rc, 0)

    def test_ensure_exits_1_on_error(self) -> None:
        original_ensure = wfo.ensure_wave_option

        def fake_ensure(label: str, org: str, project: int) -> dict:
            return {"status": "error", "detail": "boom"}

        wfo.ensure_wave_option = fake_ensure  # type: ignore[assignment]
        try:
            rc = wfo.main(["ensure", "wave-18"])
        finally:
            wfo.ensure_wave_option = original_ensure  # type: ignore[assignment]
        self.assertEqual(rc, 1)

    def test_check_exits_0_when_present(self) -> None:
        original_check = wfo.check_wave_option

        def fake_check(label: str, org: str, project: int) -> dict:
            return {"status": "present", "option_name": "W18", "option_id": "x"}

        wfo.check_wave_option = fake_check  # type: ignore[assignment]
        try:
            rc = wfo.main(["check", "wave-18"])
        finally:
            wfo.check_wave_option = original_check  # type: ignore[assignment]
        self.assertEqual(rc, 0)

    def test_check_exits_2_when_absent(self) -> None:
        original_check = wfo.check_wave_option

        def fake_check(label: str, org: str, project: int) -> dict:
            return {"status": "absent", "option_name": "W18"}

        wfo.check_wave_option = fake_check  # type: ignore[assignment]
        try:
            rc = wfo.main(["check", "wave-18"])
        finally:
            wfo.check_wave_option = original_check  # type: ignore[assignment]
        self.assertEqual(rc, 2)

    def test_check_exits_1_on_error(self) -> None:
        original_check = wfo.check_wave_option

        def fake_check(label: str, org: str, project: int) -> dict:
            return {"status": "error", "detail": "boom"}

        wfo.check_wave_option = fake_check  # type: ignore[assignment]
        try:
            rc = wfo.main(["check", "wave-18"])
        finally:
            wfo.check_wave_option = original_check  # type: ignore[assignment]
        self.assertEqual(rc, 1)

    def test_ensure_bad_label_exits_1(self) -> None:
        rc = wfo.main(["ensure", "not-a-wave-label"])
        self.assertEqual(rc, 1)

    def test_check_bad_label_exits_1(self) -> None:
        rc = wfo.main(["check", "not-a-wave-label"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
