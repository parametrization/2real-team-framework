"""Tests for the promotion-audit skill's helpers.py — the deterministic
memory->charter->skill->hook promotion auditor (#102, P0).

Stdlib + pytest only; no network (the gh-issue-filing seam is exercised via an
injected stub runner). Covers the pure classification/render core (byte-identical
determinism), the ledger-mutating auto-promotion step, and the full run_audit
orchestration in both dry-run and --apply modes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_SKILL_DIR = _FRAMEWORK_ROOT / "assets" / "skills" / "promotion-audit"
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "lib"))
sys.path.insert(0, str(_SKILL_DIR))

import _framework_config  # noqa: E402
import generic_prompt_tracker as gpt  # noqa: E402
import helpers as pa  # noqa: E402

MARKED = (
    "<!-- Promoted from memory: reference_widget (#1) -->\n"
    "**Promotion provenance:** because reasons — promoted 2026-01-01.\n"
    "content\n"
)


# --------------------------------------------------------------- has_promotion_markers


def test_has_promotion_markers_requires_both_halves() -> None:
    assert pa.has_promotion_markers(MARKED) is True
    only_comment = "<!-- Promoted from memory: x (#1) -->\ncontent\n"
    only_provenance = "**Promotion provenance:** x\ncontent\n"
    assert pa.has_promotion_markers(only_comment) is False
    assert pa.has_promotion_markers(only_provenance) is False
    assert pa.has_promotion_markers("plain content, no markers") is False


# --------------------------------------------------------------- classify_tier


def test_classify_tier_done_when_already_decided() -> None:
    assert pa.classify_tier({"decision": gpt.GENERICIZED}, MARKED) == pa.TIER_DONE
    assert pa.classify_tier({"decision": gpt.SKIP}, None) == pa.TIER_DONE


def test_classify_tier_auto_when_pending_and_marked() -> None:
    assert pa.classify_tier({"decision": gpt.PENDING}, MARKED) == pa.TIER_AUTO


def test_classify_tier_decide_when_pending_and_unmarked() -> None:
    assert pa.classify_tier({"decision": gpt.PENDING}, "no markers here") == pa.TIER_DECIDE


def test_classify_tier_decide_when_content_unreadable() -> None:
    assert pa.classify_tier({"decision": gpt.PENDING}, None) == pa.TIER_DECIDE


# --------------------------------------------------------------- plan_audit (determinism)


def test_plan_audit_sorts_and_buckets_deterministically() -> None:
    candidates = {
        "z.md": {"decision": gpt.PENDING},
        "a.md": {"decision": gpt.PENDING},
        "m.md": {"decision": gpt.SKIP},
    }
    contents = {"z.md": MARKED, "a.md": "no markers", "m.md": None}
    plan = pa.plan_audit(candidates, contents)
    assert plan == {"auto": ["z.md"], "decide": ["a.md"], "done": ["m.md"]}


def test_plan_audit_is_byte_identical_across_repeated_calls() -> None:
    candidates = {"b.md": {"decision": gpt.PENDING}, "a.md": {"decision": gpt.PENDING}}
    contents = {"b.md": MARKED, "a.md": "plain"}
    first = json.dumps(pa.plan_audit(candidates, contents), sort_keys=True)
    second = json.dumps(pa.plan_audit(candidates, contents), sort_keys=True)
    assert first == second


# --------------------------------------------------------------- render_* (determinism)


def test_render_audit_log_is_deterministic_and_covers_all_tiers() -> None:
    plan = {"auto": ["a.md"], "decide": ["b.md"], "done": []}
    text1 = pa.render_audit_log("3", plan, generated_at="T1")
    text2 = pa.render_audit_log("3", plan, generated_at="T1")
    assert text1 == text2
    assert "a.md" in text1 and "b.md" in text1
    assert "(none)" in text1  # done section, empty


def test_render_draft_issue_body_is_deterministic() -> None:
    entry = {"decided_at": "T1", "detail": "touched twice"}
    body1 = pa.render_draft_issue_body("x.md", entry, wave="3")
    body2 = pa.render_draft_issue_body("x.md", entry, wave="3")
    assert body1 == body2
    assert "x.md" in body1 and "touched twice" in body1 and "wave 3" in body1


# --------------------------------------------------------------- apply_auto_promotions


def test_apply_auto_promotions_flips_ledger_decision(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.json"
    gpt.record_candidate(ledger_path, "a.md", at="T0")
    pa.apply_auto_promotions(ledger_path, ["a.md"], "5", at="T1")
    ledger = gpt.load_ledger(ledger_path)
    entry = ledger["candidates"]["a.md"]
    assert entry["decision"] == gpt.GENERICIZED
    assert entry["wave"] == "5"
    assert entry["decided_at"] == "T1"


# --------------------------------------------------------------- file_draft_issues (injected runner)


def test_file_draft_issues_uses_injected_runner_not_real_gh() -> None:
    calls: list[list[str]] = []

    def fake_runner(args: list[str]) -> str:
        calls.append(args)
        return "https://github.com/o/r/issues/99"

    candidates = {"a.md": {"decided_at": "T0", "detail": "d"}}
    filed = pa.file_draft_issues(candidates, ["a.md"], "5", label="promotion-audit", runner=fake_runner)
    assert len(filed) == 1
    assert filed[0]["artifact"] == "a.md"
    assert filed[0]["result"] == "https://github.com/o/r/issues/99"
    assert calls[0][:2] == ["issue", "create"]
    assert "--label" in calls[0] and "promotion-audit" in calls[0]


# --------------------------------------------------------------- run_audit (full orchestration)


def test_run_audit_dry_run_never_calls_a_runner(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.json"
    (tmp_path / "marked.md").write_text(MARKED, encoding="utf-8")
    (tmp_path / "unmarked.md").write_text("plain", encoding="utf-8")
    gpt.record_candidate(ledger_path, "marked.md", at="T0")
    gpt.record_candidate(ledger_path, "unmarked.md", at="T0")

    def boom(_args):
        raise AssertionError("must not be called in dry-run")

    log_path = tmp_path / "audit.md"
    result = pa.run_audit(
        ledger_path, tmp_path, "9", dry_run=True, at="T1", audit_log_path=log_path, runner=boom
    )
    assert result["plan"] == {"auto": ["marked.md"], "decide": ["unmarked.md"], "done": []}
    assert result["filed"][0]["result"] == "DRY-RUN (not filed)"
    assert log_path.is_file()
    assert "marked.md" in log_path.read_text(encoding="utf-8")

    ledger = gpt.load_ledger(ledger_path)
    assert ledger["candidates"]["marked.md"]["decision"] == gpt.GENERICIZED  # auto still applied
    assert ledger["candidates"]["unmarked.md"]["decision"] == gpt.PENDING  # left for a human


def test_run_audit_apply_mode_files_via_injected_runner(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.json"
    (tmp_path / "unmarked.md").write_text("plain", encoding="utf-8")
    gpt.record_candidate(ledger_path, "unmarked.md", at="T0")

    calls: list[list[str]] = []

    def fake_runner(args: list[str]) -> str:
        calls.append(args)
        return "https://github.com/o/r/issues/1"

    result = pa.run_audit(
        ledger_path,
        tmp_path,
        "9",
        dry_run=False,
        at="T1",
        audit_log_path=tmp_path / "audit.md",
        runner=fake_runner,
    )
    assert len(calls) == 1
    assert result["filed"][0]["result"] == "https://github.com/o/r/issues/1"


def test_run_audit_empty_ledger_is_a_clean_no_op(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.json"
    result = pa.run_audit(ledger_path, tmp_path, "1", dry_run=True, at="T1", audit_log_path=tmp_path / "a.md")
    assert result["plan"] == {"auto": [], "decide": [], "done": []}
    assert result["filed"] == []


# --------------------------------------------------------------- config-path resolution


def test_default_audit_log_path_none_without_config() -> None:
    _framework_config.clear_cache()
    cfg = _framework_config.config(start_dir=str(Path("/nonexistent-root-xyz")))
    assert pa.default_audit_log_path("3", cfg=cfg) is None


def test_default_audit_log_path_resolves_relative_to_repo_root(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "framework.config.json").write_text(json.dumps({"version": 1}), encoding="utf-8")
    _framework_config.clear_cache()
    cfg = _framework_config.config(start_dir=str(tmp_path))
    resolved = pa.default_audit_log_path("3", cfg=cfg)
    assert resolved == tmp_path / ".claude" / "team" / "promotion_audit_log" / "wave_3.md"
