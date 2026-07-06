"""Tests for generic_prompt_tracker.py — the durable promotion-candidate ledger (#102).

Stdlib + pytest only; no network. Exercises the fail-open reader, the seeding-on-first-write
path (mirrors ``project_upsert_status_keys_seeding``), the silent-touch vs. always-overwrite
write modes, and the pure classification helpers a caller (e.g. promotion-audit's helpers.py)
would use against a hand-built ledger.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "lib"))

import generic_prompt_tracker as gpt  # noqa: E402


# --------------------------------------------------------------- load_ledger (fail-open)


def test_load_ledger_missing_file_returns_seeded_shape(tmp_path: Path) -> None:
    ledger = gpt.load_ledger(tmp_path / "does-not-exist.json")
    assert ledger == {"version": 1, "candidates": {}}


def test_load_ledger_empty_file_returns_seeded_shape(tmp_path: Path) -> None:
    p = tmp_path / "ledger.json"
    p.write_text("", encoding="utf-8")
    assert gpt.load_ledger(p) == {"version": 1, "candidates": {}}


def test_load_ledger_corrupt_json_fails_open(tmp_path: Path) -> None:
    p = tmp_path / "ledger.json"
    p.write_text("{not json", encoding="utf-8")
    assert gpt.load_ledger(p) == {"version": 1, "candidates": {}}


def test_load_ledger_non_object_fails_open(tmp_path: Path) -> None:
    p = tmp_path / "ledger.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    assert gpt.load_ledger(p) == {"version": 1, "candidates": {}}


def test_load_ledger_missing_candidates_key_is_backfilled(tmp_path: Path) -> None:
    p = tmp_path / "ledger.json"
    p.write_text(json.dumps({"version": 1}), encoding="utf-8")
    assert gpt.load_ledger(p) == {"version": 1, "candidates": {}}


# --------------------------------------------------------------- record_candidate (seeding)


def test_record_candidate_seeds_first_write_and_round_trips(tmp_path: Path) -> None:
    p = tmp_path / "ledger.json"
    ledger = gpt.record_candidate(p, ".claude/memory/foo.md", at="2026-01-01T00:00:00Z")
    assert ledger["candidates"][".claude/memory/foo.md"]["decision"] == gpt.PENDING
    assert ledger["candidates"][".claude/memory/foo.md"]["decided_at"] == "2026-01-01T00:00:00Z"

    # Round-trip: valid JSON on disk, re-readable, matches what was returned.
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    assert on_disk["candidates"][".claude/memory/foo.md"]["decision"] == gpt.PENDING


def test_record_candidate_second_write_upserts_via_seeded_file(tmp_path: Path) -> None:
    p = tmp_path / "ledger.json"
    gpt.record_candidate(p, "a.md", at="2026-01-01T00:00:00Z")
    ledger = gpt.record_candidate(
        p, "b.md", decision=gpt.SKIP, detail="project-specific", at="2026-01-02T00:00:00Z"
    )
    assert set(ledger["candidates"]) == {"a.md", "b.md"}
    assert ledger["candidates"]["b.md"]["decision"] == gpt.SKIP
    assert ledger["candidates"]["b.md"]["detail"] == "project-specific"
    # Still valid JSON.
    json.loads(p.read_text(encoding="utf-8"))


def test_record_candidate_defaults_bad_decision_to_pending(tmp_path: Path) -> None:
    p = tmp_path / "ledger.json"
    ledger = gpt.record_candidate(p, "x.md", decision="bogus")
    assert ledger["candidates"]["x.md"]["decision"] == gpt.PENDING


# --------------------------------------------------------------- skip_if_present (silent touch)


def test_skip_if_present_creates_pending_when_absent(tmp_path: Path) -> None:
    p = tmp_path / "ledger.json"
    ledger = gpt.record_candidate(p, "new.md", skip_if_present=True, at="T1")
    assert ledger["candidates"]["new.md"] == {
        "decided_at": "T1",
        "decision": gpt.PENDING,
        "detail": "",
        "wave": None,
    }


def test_skip_if_present_never_clobbers_existing_decision(tmp_path: Path) -> None:
    p = tmp_path / "ledger.json"
    gpt.record_candidate(p, "done.md", decision=gpt.GENERICIZED, wave="7", at="T1")
    # A later "silent touch" (e.g. the hook firing again on a re-edit) must not reset it.
    ledger = gpt.record_candidate(p, "done.md", skip_if_present=True, at="T2")
    entry = ledger["candidates"]["done.md"]
    assert entry["decision"] == gpt.GENERICIZED
    assert entry["decided_at"] == "T1"  # untouched


# --------------------------------------------------------------- pure filters


def test_pending_and_decided_candidates_partition() -> None:
    ledger = {
        "version": 1,
        "candidates": {
            "a.md": {"decision": gpt.PENDING},
            "b.md": {"decision": gpt.GENERICIZED},
            "c.md": {"decision": gpt.SKIP},
            "d.md": {"decision": gpt.PENDING},
        },
    }
    assert set(gpt.pending_candidates(ledger)) == {"a.md", "d.md"}
    assert set(gpt.decided_candidates(ledger)) == {"b.md", "c.md"}


def test_pending_candidates_empty_ledger_is_empty() -> None:
    assert gpt.pending_candidates({"version": 1, "candidates": {}}) == {}


# --------------------------------------------------------------- default_ledger_path


def test_default_ledger_path_none_without_config() -> None:
    import _framework_config

    _framework_config.clear_cache()
    cfg = _framework_config.config(start_dir=str(Path("/nonexistent-root-xyz")))
    assert gpt.default_ledger_path(cfg) is None


def test_default_ledger_path_resolves_relative_to_repo_root(tmp_path: Path) -> None:
    import _framework_config

    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "framework.config.json").write_text(json.dumps({"version": 1}), encoding="utf-8")
    _framework_config.clear_cache()
    cfg = _framework_config.config(start_dir=str(tmp_path))
    resolved = gpt.default_ledger_path(cfg)
    assert resolved == tmp_path / ".claude" / "generic_prompt_ledger.json"
