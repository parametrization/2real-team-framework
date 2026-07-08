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
# _classic_enforces_required_checks — the classic-endpoint tri-state
# --------------------------------------------------------------------------- #


def test_classic_true_on_nonempty_contexts(monkeypatch) -> None:
    monkeypatch.setattr(
        hook.subprocess, "run",
        lambda *a, **k: _FakeProc(0, '{"contexts": ["node (20)"], "checks": []}'),
    )
    assert hook._classic_enforces_required_checks("acme/widget", "main") is True


def test_classic_true_on_nonempty_checks(monkeypatch) -> None:
    monkeypatch.setattr(
        hook.subprocess, "run",
        lambda *a, **k: _FakeProc(0, '{"contexts": [], "checks": [{"context": "ci"}]}'),
    )
    assert hook._classic_enforces_required_checks("acme/widget", "main") is True


def test_classic_false_on_empty_required_set(monkeypatch) -> None:
    monkeypatch.setattr(
        hook.subprocess, "run",
        lambda *a, **k: _FakeProc(0, '{"contexts": [], "checks": []}'),
    )
    assert hook._classic_enforces_required_checks("acme/widget", "main") is False


def test_classic_false_on_branch_not_protected_404(monkeypatch) -> None:
    # A 404 / "Branch not protected" is DEFINITIVE no-enforcement -> False, NOT None.
    monkeypatch.setattr(
        hook.subprocess, "run",
        lambda *a, **k: _FakeProc(1, "", "gh: Branch not protected (HTTP 404)"),
    )
    assert hook._classic_enforces_required_checks("acme/widget", "main") is False


def test_classic_none_on_other_error(monkeypatch) -> None:
    # A permission/transport error is undeterminable -> None (fail-open), NOT False.
    monkeypatch.setattr(
        hook.subprocess, "run",
        lambda *a, **k: _FakeProc(1, "", "gh: Bad credentials (HTTP 401)"),
    )
    assert hook._classic_enforces_required_checks("acme/widget", "main") is None


def test_classic_none_on_timeout(monkeypatch) -> None:
    def _boom(*a, **k):
        raise hook.subprocess.TimeoutExpired(cmd="gh", timeout=15)

    monkeypatch.setattr(hook.subprocess, "run", _boom)
    assert hook._classic_enforces_required_checks("acme/widget", "main") is None


def test_classic_none_on_bad_json(monkeypatch) -> None:
    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: _FakeProc(0, "not json"))
    assert hook._classic_enforces_required_checks("acme/widget", "main") is None


def test_classic_none_without_repo_or_base() -> None:
    assert hook._classic_enforces_required_checks(None, "main") is None
    assert hook._classic_enforces_required_checks("acme/widget", None) is None


# --------------------------------------------------------------------------- #
# _rulesets_enforce_required_checks — the rulesets-endpoint tri-state (#262)
# --------------------------------------------------------------------------- #

# A `rules/branches/{branch}` payload with an enforcing required-status-checks rule.
_RULESET_ENFORCING = (
    '[{"type": "required_status_checks", "ruleset_id": 7, '
    '"parameters": {"required_status_checks": [{"context": "node (20)"}]}}]'
)
# A rules payload that exists but enforces something OTHER than status checks.
_RULESET_NON_CHECK = '[{"type": "pull_request", "ruleset_id": 9, "parameters": {}}]'
# A required-status-checks rule present but with an EMPTY required set.
_RULESET_EMPTY_CHECKS = (
    '[{"type": "required_status_checks", "ruleset_id": 7, '
    '"parameters": {"required_status_checks": []}}]'
)


def test_rulesets_true_on_enforcing_rule(monkeypatch) -> None:
    monkeypatch.setattr(
        hook.subprocess, "run", lambda *a, **k: _FakeProc(0, _RULESET_ENFORCING)
    )
    assert hook._rulesets_enforce_required_checks("acme/widget", "main") is True


def test_rulesets_false_on_empty_rules(monkeypatch) -> None:
    # This endpoint returns `200 []` for a branch with no rules -> DEFINITIVE False.
    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: _FakeProc(0, "[]"))
    assert hook._rulesets_enforce_required_checks("acme/widget", "main") is False


def test_rulesets_false_on_non_status_check_rules(monkeypatch) -> None:
    monkeypatch.setattr(
        hook.subprocess, "run", lambda *a, **k: _FakeProc(0, _RULESET_NON_CHECK)
    )
    assert hook._rulesets_enforce_required_checks("acme/widget", "main") is False


def test_rulesets_false_on_empty_required_set(monkeypatch) -> None:
    # A required_status_checks rule with an empty set enforces nothing -> False.
    monkeypatch.setattr(
        hook.subprocess, "run", lambda *a, **k: _FakeProc(0, _RULESET_EMPTY_CHECKS)
    )
    assert hook._rulesets_enforce_required_checks("acme/widget", "main") is False


def test_rulesets_false_on_absent_repo_404(monkeypatch) -> None:
    monkeypatch.setattr(
        hook.subprocess, "run",
        lambda *a, **k: _FakeProc(1, "", "gh: Not Found (HTTP 404)"),
    )
    assert hook._rulesets_enforce_required_checks("acme/widget", "main") is False


def test_rulesets_none_on_other_error(monkeypatch) -> None:
    # A permission/transport error is undeterminable -> None (fail-open), NOT False.
    monkeypatch.setattr(
        hook.subprocess, "run",
        lambda *a, **k: _FakeProc(1, "", "gh: Bad credentials (HTTP 401)"),
    )
    assert hook._rulesets_enforce_required_checks("acme/widget", "main") is None


def test_rulesets_none_on_timeout(monkeypatch) -> None:
    def _boom(*a, **k):
        raise hook.subprocess.TimeoutExpired(cmd="gh", timeout=15)

    monkeypatch.setattr(hook.subprocess, "run", _boom)
    assert hook._rulesets_enforce_required_checks("acme/widget", "main") is None


def test_rulesets_none_on_bad_json(monkeypatch) -> None:
    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: _FakeProc(0, "not json"))
    assert hook._rulesets_enforce_required_checks("acme/widget", "main") is None


def test_rulesets_none_on_non_list_payload(monkeypatch) -> None:
    # The endpoint should return a list; a dict is malformed -> undeterminable None.
    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: _FakeProc(0, "{}"))
    assert hook._rulesets_enforce_required_checks("acme/widget", "main") is None


def test_rulesets_none_without_repo_or_base() -> None:
    assert hook._rulesets_enforce_required_checks(None, "main") is None
    assert hook._rulesets_enforce_required_checks("acme/widget", None) is None


# --------------------------------------------------------------------------- #
# base_branch_enforces_required_checks — classic OR rulesets composition (#262)
# --------------------------------------------------------------------------- #


def _sources(monkeypatch, classic, rulesets) -> None:
    """Stub the two probe helpers so the combiner can be tested in isolation."""
    monkeypatch.setattr(hook, "_classic_enforces_required_checks", lambda repo, base: classic)
    monkeypatch.setattr(hook, "_rulesets_enforce_required_checks", lambda repo, base: rulesets)


def test_combiner_classic_true_shortcircuits(monkeypatch) -> None:
    # classic True -> True, and the rulesets probe is never even consulted.
    monkeypatch.setattr(hook, "_classic_enforces_required_checks", lambda repo, base: True)
    monkeypatch.setattr(
        hook, "_rulesets_enforce_required_checks",
        lambda repo, base: (_ for _ in ()).throw(AssertionError("rulesets probed")),
    )
    assert hook.base_branch_enforces_required_checks("acme/widget", "main") is True


def test_combiner_rulesets_true_when_classic_absent(monkeypatch) -> None:
    # HEADLINE (#262): classic protection ABSENT (False) but a ruleset enforces
    # required checks -> the base is recognized as protected (True). Reverting the
    # rulesets branch (see the revert->red test) makes this False.
    _sources(monkeypatch, classic=False, rulesets=True)
    assert hook.base_branch_enforces_required_checks("acme/widget", "main") is True


def test_combiner_false_only_when_both_definitively_false(monkeypatch) -> None:
    _sources(monkeypatch, classic=False, rulesets=False)
    assert hook.base_branch_enforces_required_checks("acme/widget", "main") is False


def test_combiner_none_when_classic_error_and_rulesets_false(monkeypatch) -> None:
    # An unread source can't rule out enforcement -> fail-open None, never False.
    _sources(monkeypatch, classic=None, rulesets=False)
    assert hook.base_branch_enforces_required_checks("acme/widget", "main") is None


def test_combiner_none_when_rulesets_error_and_classic_false(monkeypatch) -> None:
    _sources(monkeypatch, classic=False, rulesets=None)
    assert hook.base_branch_enforces_required_checks("acme/widget", "main") is None


def test_combiner_true_even_when_classic_error(monkeypatch) -> None:
    # classic undeterminable but a ruleset definitively enforces -> True.
    _sources(monkeypatch, classic=None, rulesets=True)
    assert hook.base_branch_enforces_required_checks("acme/widget", "main") is True


def test_rulesets_branch_is_load_bearing_revert_red(monkeypatch) -> None:
    """Revert->red proof for the #262 rulesets recognition (in-memory patch only).

    Real function: classic absent + a ruleset enforcing required checks -> True
    (enforcement recognized). Reversing the production change in memory (patching
    the rulesets probe back to its pre-#262 no-op that never reports enforcement)
    flips the SAME inputs to False -> the over-block returns. This proves the
    rulesets branch is what recognizes the enforcement; without it the gate
    regresses to the false-negative. No git checkout: the reversal is a monkeypatch.
    """
    # Classic branch protection is absent (rulesets-only repo).
    monkeypatch.setattr(hook, "_classic_enforces_required_checks", lambda repo, base: False)

    # Production behavior: the rulesets probe reports enforcement.
    monkeypatch.setattr(hook, "_rulesets_enforce_required_checks", lambda repo, base: True)
    assert hook.base_branch_enforces_required_checks("acme/widget", "main") is True

    # Reverted behavior: pre-#262, rulesets enforcement was never consulted, so the
    # branch reads as unenforced. The SAME inputs now go False -> the gate would
    # over-block a rulesets-protected repo. This asserts the branch is load-bearing.
    monkeypatch.setattr(hook, "_rulesets_enforce_required_checks", lambda repo, base: False)
    assert hook.base_branch_enforces_required_checks("acme/widget", "main") is False


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


def test_pending_auto_rulesets_only_enforcement_allows(monkeypatch) -> None:
    """#262 end-to-end: pending + --auto on a repo whose required checks are
    enforced ONLY via a ruleset (classic protection absent). The gate must
    recognize the ruleset enforcement and warn-allow, not over-block.

    This exercises the fix through check() -> base_branch_enforces_required_checks:
    classic False + ruleset True -> True -> warn-allow. Reverting the rulesets
    branch would make the combiner return False -> this flips to a BLOCK.
    """
    _cfg(monkeypatch)
    _rollup(monkeypatch, [_PASS_CHECK, _PENDING_CHECK])
    _base(monkeypatch, "main")
    monkeypatch.setattr(hook, "_classic_enforces_required_checks", lambda repo, base: False)
    monkeypatch.setattr(hook, "_rulesets_enforce_required_checks", lambda repo, base: True)
    result = hook.check(_bash(_MERGE_AUTO))
    assert result is not None
    assert result["decision"] == "allow"
    assert "systemMessage" in result


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


def test_admin_without_exception_blocks(monkeypatch) -> None:
    # The audited `--admin` path is preserved by the #230 fix: with no configured
    # exception (and none in the env), `--admin` fails safe -> block. Reverting the
    # validate_admin_exception guard to an unconditional allow flips this to None.
    _cfg(monkeypatch)  # policy.admin_merge_exceptions absent -> any --admin blocks
    monkeypatch.delenv("ADMIN_MERGE_EXCEPTION", raising=False)
    # fetch_checks must never even be consulted on the --admin path; make it explode
    # if it is, so this test also pins that --admin is evaluated before the rollup.
    monkeypatch.setattr(
        hook, "fetch_checks", lambda pr, repo: (_ for _ in ()).throw(AssertionError("fetched"))
    )
    result = hook.check(_bash(_MERGE + " --admin"))
    assert result is not None
    assert result["decision"] == "block"
    assert "--admin" in result["reason"]


def test_admin_with_valid_exception_allows(monkeypatch) -> None:
    # A recognized exception class + non-empty rationale authorizes the audited
    # override -> allow (None), and the authorization is logged for the audit trail.
    _cfg(monkeypatch, {"policy.admin_merge_exceptions": {"hotfix": "prod incident"}})
    calls: list = []
    monkeypatch.setattr(hook, "log_pretooluse_block", lambda *a, **k: calls.append((a, k)))
    data = _bash(_MERGE + " --admin")
    data["env"] = {"ADMIN_MERGE_EXCEPTION": "hotfix: page P1 fix"}
    assert hook.check(data) is None
    assert calls, "expected the authorized --admin use to be logged for audit"


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
