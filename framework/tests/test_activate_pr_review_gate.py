"""Load-bearing integration test for the ACTIVATED PR-review gate (#202, W6/S1).

Unlike ``test_validate_pr_review.py`` (which hand-builds fixture policy values),
this test wires the gate against **this repo's ACTUAL runtime config**
(``.claude/framework.config.json``): it reads the shipped ``policy`` block and
drives ``validate_pr_review.check`` + the ``pr_review_state`` oracle with those
exact values. That makes it break if the activation is reverted — it is the
mutation bar for the config edit this story ships.

What it pins (all against the real config, no hand-built policy fixture):

* ``test_repo_config_is_activated`` — the shipped values ARE the activation
  (``pr_review_gate_enabled=true``, ``reviewers_required=2``). A revert of either
  fails here directly.
* ``test_enabled_not_approved_blocks_gh_pr_merge`` — armed by the REAL flag, a
  not-approved oracle state ⇒ the gate returns a ``block`` decision on
  ``gh pr merge``, and the reason names ``approvals X/N`` with N = the real
  ``reviewers_required`` (``0/2``).
* ``test_two_distinct_clean_requestor_verdicts_approve`` — the oracle's real
  ``compute_state`` over TWO distinct clean ``Requestor:`` verdicts, at the real
  ``reviewers_required``, reports ``approved`` — and the gate then ALLOWS the
  merge. ONE clean verdict does not (``pending``); a standing ``Must-fix:`` does
  not (``changes_requested``).
* ``test_mutation_bar_reverting_config_flips_the_block`` — the SAME not-approved
  oracle state that BLOCKS under the real (activated) config ALLOWS once the two
  config values are reverted in a copy (``enabled=false``, ``reviewers_required=1``).
  This is the explicit revert→fail simulation for the two-line config change.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _FRAMEWORK_ROOT.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "lib"))

import pr_review_state as oracle  # noqa: E402
import trust_signals as ts  # noqa: E402
import validate_pr_review as hook  # noqa: E402

#: This repo's live runtime config — the file the gate actually loads in anger.
_CONFIG_PATH = _REPO_ROOT / ".claude" / "framework.config.json"


def _real_policy() -> dict:
    """The ACTUAL shipped ``policy`` block (not a hand-built fixture)."""
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))["policy"]


class _RealCfg:
    """Dotted-get config shim over a real ``policy`` dict.

    Matches the surface both consumers use: the hook reads
    ``config(...).get("policy.pr_review_gate_enabled")`` and the oracle reads
    ``cfg.get("policy.reviewers_required")``. Fed the SHIPPED policy so the gate
    is exercised with this repo's real activation values.
    """

    def __init__(self, policy: dict) -> None:
        self._policy = policy

    def get(self, key: str, default=None):
        if key.startswith("policy."):
            return self._policy.get(key[len("policy.") :], default)
        return default


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _arm_with(monkeypatch, policy: dict) -> None:
    """Point the hook's config at a ``_RealCfg`` over *policy*."""
    monkeypatch.setattr(
        hook, "config", lambda input_data=None, **kw: _RealCfg(policy)
    )


def _stub_oracle(monkeypatch, state: dict) -> None:
    """Replace the oracle's I/O so no real ``gh``/network is touched."""
    monkeypatch.setattr(hook, "review_state", lambda repo, pr, **kw: state)


def _clean_verdict_body(requestor: str, requestee: str = "Paloma.Gupta") -> str:
    """A charter-grammar clean approval (``Replied`` / ``Must-fix: None``)."""
    return (
        f"Requestor: {requestor}\n"
        f"Requestee: {requestee}\n"
        "RequestOrReplied: Replied\n\n"
        "**Review: LGTM**\n"
        "Must-fix: None\n"
        "Tech-debt: None\n"
    )


def _must_fix_body(requestor: str, requestee: str = "Paloma.Gupta") -> str:
    """A charter-grammar changes-requested verdict (one blocking Must-fix)."""
    return (
        f"Requestor: {requestor}\n"
        f"Requestee: {requestee}\n"
        "RequestOrReplied: Request\n\n"
        "**Review: one blocker**\n"
        "Must-fix:\n"
        "1. Config value must be reverted before merge.\n"
        "Tech-debt: None\n"
    )


# An explicit --repo + literal PR so resolve_repo/resolve_pr never shell out.
_MERGE = "gh pr merge 202 --repo parametrization/2real-team-framework --squash"


# --------------------------------------------------------------- activation is live


def test_repo_config_is_activated() -> None:
    """The shipped runtime config carries the activation this story delivers."""
    policy = _real_policy()
    assert policy["pr_review_gate_enabled"] is True, (
        "gate must be ARMED on this repo (pr_review_gate_enabled=true)"
    )
    assert policy["reviewers_required"] == 2, (
        "this repo requires 2 distinct clean approvals to merge"
    )


# --------------------------------------------------------------- gate BLOCKS (real config)


def test_enabled_not_approved_blocks_gh_pr_merge(monkeypatch) -> None:
    """Real flag=true + not-approved oracle ⇒ block, reason names approvals 0/N."""
    policy = _real_policy()
    required = policy["reviewers_required"]
    _arm_with(monkeypatch, policy)
    _stub_oracle(
        monkeypatch,
        {
            "state": oracle.PENDING,
            "approvals": 0,
            "reviewers_required": required,
            "unresolved_must_fix": [],
        },
    )
    result = hook.check(_bash(_MERGE))
    assert result is not None, "an activated gate must block a not-approved merge"
    assert result["decision"] == "block"
    assert f"0/{required}" in result["reason"]
    assert "#202" in result["reason"]


def test_standing_must_fix_blocks(monkeypatch) -> None:
    """A standing Must-fix blocks even at/above the approval count; reason names it."""
    policy = _real_policy()
    _arm_with(monkeypatch, policy)
    verdicts = ts.parse_verdicts(
        [
            _clean_verdict_body("Nia.Rossi"),
            _clean_verdict_body("Tariq.Morales"),
            _must_fix_body("Ibrahim.El-Amin"),
        ]
    )
    state = oracle.compute_state(verdicts, policy["reviewers_required"])
    assert state["state"] == oracle.CHANGES_REQUESTED
    _stub_oracle(monkeypatch, state)
    result = hook.check(_bash(_MERGE))
    assert result is not None
    assert result["decision"] == "block"
    assert "Must-fix" in result["reason"]
    assert "Ibrahim.El-Amin" in result["reason"]


# --------------------------------------------------------------- oracle: 2-of-2 approves


def test_two_distinct_clean_requestor_verdicts_approve(monkeypatch) -> None:
    """The real oracle at reviewers_required=2 approves on 2 distinct clean verdicts."""
    required = _real_policy()["reviewers_required"]
    assert required == 2  # the invariant the rest of this test is meaningful under

    # Two distinct clean Requestors -> approved.
    two = oracle.compute_state(
        ts.parse_verdicts(
            [_clean_verdict_body("Nia.Rossi"), _clean_verdict_body("Tariq.Morales")]
        ),
        required,
    )
    assert two["state"] == oracle.APPROVED
    assert two["approvals"] == 2

    # One distinct clean Requestor -> NOT enough (pending).
    one = oracle.compute_state(
        ts.parse_verdicts([_clean_verdict_body("Nia.Rossi")]), required
    )
    assert one["state"] == oracle.PENDING
    assert one["approvals"] == 1

    # Two comments from the SAME reviewer collapse to one approval (distinct-Requestor).
    dup = oracle.compute_state(
        ts.parse_verdicts(
            [_clean_verdict_body("Nia.Rossi"), _clean_verdict_body("Nia.Rossi")]
        ),
        required,
    )
    assert dup["state"] == oracle.PENDING
    assert dup["approvals"] == 1


def test_enabled_approved_allows_merge(monkeypatch) -> None:
    """Real flag=true + an oracle-approved state ⇒ the gate ALLOWS the merge."""
    policy = _real_policy()
    approved = oracle.compute_state(
        ts.parse_verdicts(
            [_clean_verdict_body("Nia.Rossi"), _clean_verdict_body("Tariq.Morales")]
        ),
        policy["reviewers_required"],
    )
    assert approved["state"] == oracle.APPROVED
    _arm_with(monkeypatch, policy)
    _stub_oracle(monkeypatch, approved)
    assert hook.check(_bash(_MERGE)) is None


# --------------------------------------------------------------- mutation bar


def test_mutation_bar_reverting_config_flips_the_block(monkeypatch) -> None:
    """Reverting the two config values flips the BLOCK to an ALLOW (revert→fail sim).

    The SAME not-approved oracle state is evaluated twice: under the real
    (activated) policy it BLOCKS; under a copy with the two values reverted
    (``pr_review_gate_enabled=false``, ``reviewers_required=1``) it ALLOWS. If the
    shipped config ever regresses to the reverted values, the block above stops
    happening — which is exactly what this asserts must NOT be the live state.
    """
    real = _real_policy()
    pending = {
        "state": oracle.PENDING,
        "approvals": 0,
        "reviewers_required": real["reviewers_required"],
        "unresolved_must_fix": [],
    }
    _stub_oracle(monkeypatch, pending)

    # Activated (real) config: BLOCKS.
    _arm_with(monkeypatch, real)
    assert hook.check(_bash(_MERGE)) is not None

    # Reverted copy: same not-approved PR now ALLOWS (dormant no-op).
    reverted = copy.deepcopy(real)
    reverted["pr_review_gate_enabled"] = False
    reverted["reviewers_required"] = 1
    _arm_with(monkeypatch, reverted)
    assert hook.check(_bash(_MERGE)) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
