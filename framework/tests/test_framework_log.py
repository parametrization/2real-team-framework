"""Tests for _framework_log test-mode suppression (the events-log isolation guard)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))

import _framework_log as fl  # noqa: E402


def test_is_test_mode_detects_pytest(monkeypatch) -> None:
    # Even with the explicit env knobs cleared, running under pytest is detected.
    monkeypatch.delenv("FRAMEWORK_HOOK_TEST_MODE", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert "PYTEST_CURRENT_TEST" in os.environ
    assert fl._is_test_mode() is True


def test_append_jsonl_suppressed_in_test_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRAMEWORK_HOOK_TEST_MODE", "1")
    p = tmp_path / "events.jsonl"
    fl.append_jsonl_record(p, {"type": "x"})
    assert not p.exists()


def test_append_jsonl_writes_when_not_test_mode(tmp_path: Path, monkeypatch) -> None:
    # With every suppression signal removed the record IS written — proves the gate suppresses,
    # rather than the writer being a no-op.
    monkeypatch.delenv("FRAMEWORK_HOOK_TEST_MODE", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    p = tmp_path / "events.jsonl"
    fl.append_jsonl_record(p, {"type": "x"})
    assert p.is_file() and "x" in p.read_text()
