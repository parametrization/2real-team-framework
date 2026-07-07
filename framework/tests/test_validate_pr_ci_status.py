"""Tests for validate_pr_ci_status — the CI-green `gh pr merge` gate.

Focus of #230 (S2, Wave 9): close the pending + `--auto` slip. `gh pr merge
--auto` only *holds* a merge until CI goes green when the base branch enforces
those checks via branch protection. On an unprotected repo (this repo, most
fresh installs) `--auto` merges IMMEDIATELY, so a still-pending check that later
fails lands AFTER the merge — the W13 `node (20)` slip. This suite pins the
corrected semantics AND locks the pre-existing fail-open / already-red / disabled
behaviors so the fix can't quietly regress them.

Load-bearing (revert->fail) coverage:
  - test_pending_auto_no_branch_protection_blocks is the headline: reverting the
    fix (making pending + `--auto` warn-allow unconditionally, as before) turns
    this BLOCK back into an allow → it fails.
  - test_pending_auto_with_branch_protection_allows /
    test_pending_auto_protection_undeterminable_allows pin the two allow arms;
    hard-blocking every `--auto` pending (ignoring enforcement) fails these.
  - test_pending_no_auto_blocks / test_failing_blocks_even_with_auto /
    test_ready_allows / test_rollup_unreadable_fail_open_allows lock the
    unchanged paths (a red check still blocks even under `--auto`; a fetch error
    still fail-opens).
  - The base_branch_enforces_required_checks unit tests pin the tri-state:
    non-empty required set → True, 404/"not protected" → False (definitive, NOT
    None), other error → None (fail-open).

No real `gh`, no network: the fetchers and `subprocess.run` are monkeypatched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "lib"))

import validate_pr_ci_status as hook  # noqa: E402


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #

# Explicit --repo + literal PR so extract_repo / extract_pr_number never shell out.
_MERGE = "gh pr merge 42 --repo acme/widget --squash"
_MERGE_AUTO = "gh pr merge 42 --repo acme/widget --auto --squash"

_FAIL_CHECK = {"name": "node (20)", "conclusion": "FAILURE", "status": "COMPLETED"}
_PENDING_CHECK = {"name": "node (20)", "conclusion": None, "status": "IN_PROGRESS"}
_PASS_CHECK = {"name": "python (3.10)", "conclusion": "SUCCESS", "status": "COMPLETED"}


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class _StubCfg:
    def __init__(self, vals: dict | None = None) -> None:
        self._vals = vals or {}

    def get(self, key, default=None):
        return self._vals.get(key, default)


def _cfg(monkeypatch, vals: dict | None = None) -> None:
    """Point hook.config at a stub. Default: gate ON (merge_requires_green true)."""
    base = {"ci.merge_requires_green": True}
    if vals:
        base.update(vals)
    monkeypatch.setattr(hook, "config", lambda input_data=None, **kw: _StubCfg(base))


def _rollup(monkeypatch, checks) -> None:
    monkeypatch.setattr(hook, "fetch_checks", lambda pr, repo: checks)


def _base(monkeypatch, ref="main") -> None:
    monkeypatch.setattr(hook, "fetch_pr_base_ref", lambda pr, repo: ref)


def _enforces(monkeypatch, value) -> None:
    monkeypatch.setattr(
        hook, "base_branch_enforces_required_checks", lambda repo, base: value
    )


class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr="") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# --------------------------------------------------------------------------- #
# Module posture
# --------------------------------------------------------------------------- #


def test_declares_fail_open() -> None:
    assert hook.FAIL_OPEN is True


def test_not_a_merge_command_allows(monkeypatch) -> None:
    _cfg(monkeypatch)
    assert hook.check(_bash("gh pr view 42 --repo acme/widget")) is None


def test_gate_disabled_allows(monkeypatch) -> None:
    # merge_requires_green=false => whole gate is a no-op, even with a red check.
    _cfg(monkeypatch, {"ci.merge_requires_green": False})
    _rollup(monkeypatch, [_FAIL_CHECK])
    assert hook.check(_bash(_MERGE)) is None


# --------------------------------------------------------------------------- #
# base_branch_enforces_required_checks — the tri-state
# --------------------------------------------------------------------------- #


def test_enforces_true_on_nonempty_contexts(monkeypatch) -> None:
    monkeypatch.setattr(
        hook.subprocess, "run",
        lambda *a, **k: _FakeProc(0, '{"contexts": ["node (20)"], "checks": []}'),
    )
    assert hook.base_branch_enforces_required_checks("acme/widget", "main") is True


def test_enforces_true_on_nonempty_checks(monkeypatch) -> None:
    monkeypatch.setattr(
        hook.subprocess, "run",
        lambda *a, **k: _FakeProc(0, '{"contexts": [], "checks": [{"context": "ci"}]}'),
    )
    assert hook.base_branch_enforces_required_checks("acme/widget", "main") is True


def test_enforces_false_on_empty_required_set(monkeypatch) -> None:
    monkeypatch.setattr(
        hook.subprocess, "run",
        lambda *a, **k: _FakeProc(0, '{"contexts": [], "checks": []}'),
    )
    assert hook.base_branch_enforces_required_checks("acme/widget", "main") is False


def test_enforces_false_on_branch_not_protected_404(monkeypatch) -> None:
    # A 404 / "Branch not protected" is DEFINITIVE no-enforcement -> False, NOT None.
    monkeypatch.setattr(
        hook.subprocess, "run",
        lambda *a, **k: _FakeProc(1, "", "gh: Branch not protected (HTTP 404)"),
    )
    assert hook.base_branch_enforces_required_checks("acme/widget", "main") is False


def test_enforces_none_on_other_error(monkeypatch) -> None:
    # A permission/transport error is undeterminable -> None (fail-open), NOT False.
    monkeypatch.setattr(
        hook.subprocess, "run",
        lambda *a, **k: _FakeProc(1, "", "gh: Bad credentials (HTTP 401)"),
    )
    assert hook.base_branch_enforces_required_checks("acme/widget", "main") is None


def test_enforces_none_on_timeout(monkeypatch) -> None:
    def _boom(*a, **k):
        raise hook.subprocess.TimeoutExpired(cmd="gh", timeout=15)

    monkeypatch.setattr(hook.subprocess, "run", _boom)
    assert hook.base_branch_enforces_required_checks("acme/widget", "main") is None


def test_enforces_none_on_bad_json(monkeypatch) -> None:
    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: _FakeProc(0, "not json"))
    assert hook.base_branch_enforces_required_checks("acme/widget", "main") is None


def test_enforces_none_without_repo_or_base() -> None:
    assert hook.base_branch_enforces_required_checks(None, "main") is None
    assert hook.base_branch_enforces_required_checks("acme/widget", None) is None


# --------------------------------------------------------------------------- #
# check() — the pending + --auto slip fix (#230)
# --------------------------------------------------------------------------- #


def test_pending_auto_no_branch_protection_blocks(monkeypatch) -> None:
    """HEADLINE (W13 slip fix): pending + --auto + unprotected base -> BLOCK.

    Reverting the fix (unconditional warn-allow of pending under --auto) makes
    this an allow and fails the test.
    """
    _cfg(monkeypatch)
    _rollup(monkeypatch, [_PASS_CHECK, _PENDING_CHECK])
    _base(monkeypatch, "main")
    _enforces(monkeypatch, False)  # unprotected base — nothing holds the merge
    result = hook.check(_bash(_MERGE_AUTO))
    assert result is not None
    assert result["decision"] == "block"
    assert "no branch-protection required" in result["reason"].lower()


def test_pending_auto_with_branch_protection_allows(monkeypatch) -> None:
    _cfg(monkeypatch)
    _rollup(monkeypatch, [_PASS_CHECK, _PENDING_CHECK])
    _base(monkeypatch, "main")
    _enforces(monkeypatch, True)  # base enforces -> GitHub will hold for green
    result = hook.check(_bash(_MERGE_AUTO))
    assert result is not None
    assert result["decision"] == "allow"
    assert "systemMessage" in result


def test_pending_auto_protection_undeterminable_allows(monkeypatch) -> None:
    # Fail-open: can't read protection -> warn-allow, never a manufactured block.
    _cfg(monkeypatch)
    _rollup(monkeypatch, [_PENDING_CHECK])
    _base(monkeypatch, "main")
    _enforces(monkeypatch, None)
    result = hook.check(_bash(_MERGE_AUTO))
    assert result is not None
    assert result["decision"] == "allow"


def test_pending_no_auto_blocks(monkeypatch) -> None:
    # Unchanged: pending WITHOUT --auto blocks unconditionally.
    _cfg(monkeypatch)
    _rollup(monkeypatch, [_PENDING_CHECK])
    result = hook.check(_bash(_MERGE))
    assert result is not None
    assert result["decision"] == "block"


# --------------------------------------------------------------------------- #
# check() — unchanged paths that must stay intact
# --------------------------------------------------------------------------- #


def test_failing_blocks(monkeypatch) -> None:
    _cfg(monkeypatch)
    _rollup(monkeypatch, [_PASS_CHECK, _FAIL_CHECK])
    result = hook.check(_bash(_MERGE))
    assert result is not None
    assert result["decision"] == "block"
    assert "failing" in result["reason"].lower()


def test_failing_blocks_even_with_auto(monkeypatch) -> None:
    # A check already RED at merge time blocks regardless of --auto (the fix does
    # NOT loosen this: --auto only ever affected the pending path).
    _cfg(monkeypatch)
    _rollup(monkeypatch, [_FAIL_CHECK])
    # If check() consulted enforcement here it would be a bug; make it explode.
    _enforces(monkeypatch, None)
    result = hook.check(_bash(_MERGE_AUTO))
    assert result is not None
    assert result["decision"] == "block"
    assert "failing" in result["reason"].lower()


def test_ready_allows(monkeypatch) -> None:
    _cfg(monkeypatch)
    _rollup(monkeypatch, [_PASS_CHECK])
    assert hook.check(_bash(_MERGE)) is None


def test_rollup_unreadable_fail_open_allows(monkeypatch) -> None:
    # fetch_checks None (transport error) -> warn-allow, never a block (fail-open).
    _cfg(monkeypatch)
    _rollup(monkeypatch, None)
    result = hook.check(_bash(_MERGE))
    assert result is not None
    assert result["decision"] == "allow"


def test_pending_auto_no_protection_is_logged(monkeypatch) -> None:
    # The slip-fix block is audited like every other block.
    calls: list = []
    monkeypatch.setattr(
        hook, "log_pretooluse_block",
        lambda *a, **k: calls.append((a, k)),
    )
    _cfg(monkeypatch)
    _rollup(monkeypatch, [_PENDING_CHECK])
    _base(monkeypatch, "main")
    _enforces(monkeypatch, False)
    hook.check(_bash(_MERGE_AUTO))
    assert calls, "expected the pending/--auto/no-protection block to be logged"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
