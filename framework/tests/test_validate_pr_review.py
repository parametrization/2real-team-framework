"""Tests for validate_pr_review — the N-reviewer PR gate that SHIPS DORMANT (#195).

The hook is thin over S1's `lib/pr_review_state.review_state()` oracle: when the
`policy.pr_review_gate_enabled` flag is true it blocks `gh pr ready`/`gh pr merge`
on a not-approved PR; when the flag is unset/false it is a pure no-op ALLOW. The
oracle is monkeypatched in every decision test — no real `gh`, no network.

Load-bearing (revert->fail) coverage — both sides of the flag are pinned:
  - test_enabled_not_approved_blocks / test_enabled_changes_requested_blocks assert
    a specific "block" decision (naming the failed criterion) when the flag is TRUE
    and the oracle reports not-approved. Reverting check()'s gate decision (return
    None instead of the block dict) fails BOTH.
  - test_disabled_same_pr_allows / test_unset_flag_allows assert the SAME
    not-approved oracle result passes when the flag is false/unset — the
    dormant-by-default guarantee. Hard-coding the gate "on" (ignoring the flag)
    fails these.
  - test_enabled_approved_allows pins that an approved PR is not blocked.
  - test_oracle_error_allows pins the FAIL_OPEN posture: an oracle exception ALLOWS.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "lib"))

import validate_pr_review as hook  # noqa: E402


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class _StubCfg:
    """Minimal config stub. Omit the key to exercise the unset (default-false) path."""

    def __init__(self, vals: dict | None = None) -> None:
        self._vals = vals or {}

    def get(self, key, default=None):
        return self._vals.get(key, default)


def _arm(monkeypatch, enabled: bool | None) -> None:
    """Point hook.config at a stub. enabled=None => the flag key is absent."""
    vals = {} if enabled is None else {hook.GATE_FLAG: enabled}
    monkeypatch.setattr(hook, "config", lambda input_data=None, **kw: _StubCfg(vals))


def _stub_oracle(monkeypatch, state: dict) -> None:
    monkeypatch.setattr(hook, "review_state", lambda repo, pr, **kw: state)


# A command with an explicit --repo and literal PR so resolve_repo/resolve_pr
# never shell out to gh during the decision tests.
_MERGE = "gh pr merge 42 --repo acme/widget --squash"
_READY = "gh pr ready 42 --repo acme/widget"

_PENDING = {"state": "pending", "approvals": 0, "reviewers_required": 1, "unresolved_must_fix": []}
_APPROVED = {"state": "approved", "approvals": 2, "reviewers_required": 1, "unresolved_must_fix": []}
_CHANGES = {
    "state": "changes_requested",
    "approvals": 1,
    "reviewers_required": 2,
    "unresolved_must_fix": [
        {"requestor": "Nia.Rossi", "requestee": "Ibrahim.El-Amin", "verdict": "Request"}
    ],
}


# --------------------------------------------------------------- module contract


def test_declares_fail_open() -> None:
    """The dispatcher reads FAIL_OPEN=True to allow (not block) on a hook crash."""
    assert hook.FAIL_OPEN is True


# --------------------------------------------------------------- gated_verb / parsing


def test_gated_verb_merge() -> None:
    assert hook.gated_verb("gh pr merge 5") == "merge"


def test_gated_verb_ready() -> None:
    assert hook.gated_verb("gh pr ready 5") == "ready"


def test_gated_verb_chained() -> None:
    assert hook.gated_verb("git fetch && gh pr merge 5 --squash") == "merge"


def test_gated_verb_env_prefix() -> None:
    assert hook.gated_verb("FOO=bar gh pr merge 5") == "merge"


def test_gated_verb_ignores_unrelated() -> None:
    assert hook.gated_verb("gh pr view 5") is None
    assert hook.gated_verb("gh pr create --title x") is None


def test_extract_pr_number_positional() -> None:
    assert hook.extract_pr_number("gh pr merge 42 --squash") == "42"


def test_extract_pr_number_url() -> None:
    assert hook.extract_pr_number("gh pr merge https://github.com/o/r/pull/77") == "77"


def test_extract_pr_number_absent() -> None:
    assert hook.extract_pr_number("gh pr merge --squash") is None


# --------------------------------------------------------------- dormant-by-default


def test_disabled_same_pr_allows(monkeypatch) -> None:
    """Flag FALSE + a not-approved PR => no-op ALLOW (the ship-dormant guarantee)."""
    _arm(monkeypatch, enabled=False)
    _stub_oracle(monkeypatch, _PENDING)
    assert hook.check(_bash(_MERGE)) is None


def test_unset_flag_allows(monkeypatch) -> None:
    """Flag ABSENT (default false) + a not-approved PR => ALLOW."""
    _arm(monkeypatch, enabled=None)
    _stub_oracle(monkeypatch, _PENDING)
    assert hook.check(_bash(_MERGE)) is None


def test_disabled_does_not_consult_oracle(monkeypatch) -> None:
    """Dormant path must short-circuit BEFORE any oracle/gh work."""
    _arm(monkeypatch, enabled=False)

    def _boom(*a, **k):
        raise AssertionError("oracle must not be consulted while the gate is dormant")

    monkeypatch.setattr(hook, "review_state", _boom)
    assert hook.check(_bash(_MERGE)) is None


# --------------------------------------------------------------- enabled: blocks


def test_enabled_not_approved_blocks(monkeypatch) -> None:
    """Flag TRUE + pending PR => BLOCK naming approvals X/N (mutation anchor)."""
    _arm(monkeypatch, enabled=True)
    _stub_oracle(monkeypatch, _PENDING)
    result = hook.check(_bash(_MERGE))
    assert result is not None
    assert result["decision"] == "block"
    assert "0/1" in result["reason"]
    assert "#42" in result["reason"]


def test_enabled_ready_blocks(monkeypatch) -> None:
    """`gh pr ready` is gated identically to merge."""
    _arm(monkeypatch, enabled=True)
    _stub_oracle(monkeypatch, _PENDING)
    result = hook.check(_bash(_READY))
    assert result is not None
    assert result["decision"] == "block"
    assert "ready" in result["reason"]


def test_enabled_changes_requested_blocks(monkeypatch) -> None:
    """A standing Must-fix blocks and the reason enumerates the blocking reviewer."""
    _arm(monkeypatch, enabled=True)
    _stub_oracle(monkeypatch, _CHANGES)
    result = hook.check(_bash(_MERGE))
    assert result is not None
    assert result["decision"] == "block"
    assert "Must-fix" in result["reason"]
    assert "Nia.Rossi" in result["reason"]


# --------------------------------------------------------------- enabled: allows


def test_enabled_approved_allows(monkeypatch) -> None:
    """Flag TRUE + approved PR => ALLOW."""
    _arm(monkeypatch, enabled=True)
    _stub_oracle(monkeypatch, _APPROVED)
    assert hook.check(_bash(_MERGE)) is None


def test_oracle_error_allows(monkeypatch) -> None:
    """FAIL_OPEN: an oracle exception ALLOWS rather than hard-blocking the merge."""
    _arm(monkeypatch, enabled=True)

    def _raise(*a, **k):
        raise RuntimeError("gh exploded")

    monkeypatch.setattr(hook, "review_state", _raise)
    assert hook.check(_bash(_MERGE)) is None


def test_unresolvable_pr_allows(monkeypatch) -> None:
    """Flag TRUE but no PR/repo resolvable (no gh) => fail-open ALLOW, not block."""
    _arm(monkeypatch, enabled=True)
    _stub_oracle(monkeypatch, _PENDING)
    # No literal PR and no --repo; resolve_* shell out — stub them to "can't tell".
    monkeypatch.setattr(hook, "resolve_repo", lambda command: None)
    monkeypatch.setattr(hook, "resolve_pr", lambda command, repo: None)
    assert hook.check(_bash("gh pr merge --squash")) is None


# --------------------------------------------------------------- routing


def test_non_gated_command_allows(monkeypatch) -> None:
    _arm(monkeypatch, enabled=True)
    _stub_oracle(monkeypatch, _PENDING)
    assert hook.check(_bash("gh pr view 42")) is None


def test_non_bash_tool_allows(monkeypatch) -> None:
    _arm(monkeypatch, enabled=True)
    _stub_oracle(monkeypatch, _PENDING)
    assert hook.check({"tool_name": "Agent", "tool_input": {}}) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
