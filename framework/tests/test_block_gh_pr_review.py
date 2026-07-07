"""Tests for block_gh_pr_review (issue #196).

The hook guards verdict SUBMISSION — the cases that are always invalid under the
charter no matter any policy gate, so blocking them can never brick the team's
own reviewing:

* a raw ``gh pr review`` invocation (shared-user API approvals always fail);
* a verdict-comment whose body is malformed under the charter grammar
  (delegated to ``validate_review_comment_format.validate_grammar``);
* a self-review — a verdict-comment naming the same person as ``Requestor:``
  (the reviewer) and ``Requestee:`` (the PR author).

Everything else fails open (allow). The load-bearing assertions are the
malformed-blocked / well-formed-passes / self-review-blocked trio (the mutation
bar): reverting the grammar delegation or the self-review comparison lets the
corresponding bad verdict through.

Stdlib + pytest only.
"""

from __future__ import annotations

import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))

import block_gh_pr_review as hook  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures: well-formed cross-person verdict, malformed, self-review.
# --------------------------------------------------------------------------- #

# A well-formed, cross-person changes-requested verdict (reviewer != author).
WELL_FORMED = """Requestor: Nia.Rossi
Requestee: Ibrahim.El-Amin
RequestOrReplied: Request

**Review: changes requested**
Must-fix:
1. Guard the None branch before dereferencing.
Tech-debt: None"""

# A well-formed approval (Replied + Must-fix: None), cross-person.
WELL_FORMED_APPROVAL = """Requestor: Tariq.Morales
Requestee: Paloma.Gupta
RequestOrReplied: Replied

**Review: LGTM**
Must-fix: None
Tech-debt: None"""

# Malformed: unknown RequestOrReplied token (severity smuggled into the token).
MALFORMED = """Requestor: Nia.Rossi
Requestee: Ibrahim.El-Amin
RequestOrReplied: Approved

Must-fix: None
Tech-debt: None"""

# Self-review: Requestor == Requestee (reviewer clearing their own PR).
SELF_REVIEW = """Requestor: Paloma.Gupta
Requestee: Paloma.Gupta
RequestOrReplied: Replied

**Review: LGTM**
Must-fix: None
Tech-debt: None"""

# Self-review across the two accepted spellings (dotted vs spaced + role suffix)
# — the normalizer must fold these to the same identity and still block.
SELF_REVIEW_SPELLING = """Requestor: Paloma Gupta (Principal)
Requestee: Paloma.Gupta
RequestOrReplied: Replied

**Review: LGTM**
Must-fix: None
Tech-debt: None"""


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _comment_cmd(body: str, pr: int = 1, sub: str = "pr") -> str:
    """A ``gh <sub> comment`` command carrying *body* via a heredoc (quote-safe)."""
    return f"gh {sub} comment {pr} --body \"$(cat <<'EOF'\n{body}\nEOF\n)\""


# --------------------------------------------------------------------------- #
# LOAD-BEARING: malformed blocked / well-formed passes / self-review blocked.
# --------------------------------------------------------------------------- #


def test_wellformed_cross_person_verdict_passes() -> None:
    """A well-formed verdict from a DIFFERENT reviewer is allowed (no block)."""
    assert hook.check(_bash(_comment_cmd(WELL_FORMED))) is None
    assert hook.check(_bash(_comment_cmd(WELL_FORMED_APPROVAL))) is None


def test_malformed_verdict_is_blocked() -> None:
    """A malformed verdict (unknown RequestOrReplied token) is blocked.

    Load-bearing: reverting the ``validate_grammar`` delegation in ``check``
    lets this slip through.
    """
    result = hook.check(_bash(_comment_cmd(MALFORMED)))
    assert result is not None and result["decision"] == "block"
    assert "RequestOrReplied" in result["reason"]


def test_self_review_is_blocked() -> None:
    """A verdict whose Requestor == Requestee (self-review) is blocked.

    Load-bearing: reverting the ``_self_review_reason`` call in ``check`` (or the
    identity comparison inside it) lets a reviewer clear their own PR.
    """
    result = hook.check(_bash(_comment_cmd(SELF_REVIEW)))
    assert result is not None and result["decision"] == "block"
    assert "self-review" in result["reason"].lower()


def test_self_review_across_name_spellings_is_blocked() -> None:
    """Dotted vs spaced + role-suffix spellings of one person still self-review."""
    result = hook.check(_bash(_comment_cmd(SELF_REVIEW_SPELLING)))
    assert result is not None and result["decision"] == "block"
    assert "self-review" in result["reason"].lower()


# --------------------------------------------------------------------------- #
# Raw `gh pr review` is blocked (shared-user API approvals always fail).
# --------------------------------------------------------------------------- #


def test_raw_gh_pr_review_is_blocked() -> None:
    result = hook.check(_bash("gh pr review 42 --approve"))
    assert result is not None and result["decision"] == "block"
    assert "gh pr review" in result["reason"]


def test_gh_pr_review_inside_heredoc_body_is_not_blocked() -> None:
    """A `gh pr review` mentioned inside a comment BODY (heredoc) is not a
    command-position invocation, so it must not trip the raw-review block."""
    body = (
        "Requestor: Nia.Rossi\nRequestee: Ibrahim.El-Amin\nRequestOrReplied: Replied\n\n"
        "Do not run `gh pr review` — use a comment.\nMust-fix: None\nTech-debt: None"
    )
    assert hook.check(_bash(_comment_cmd(body))) is None


# --------------------------------------------------------------------------- #
# Fail-open edges: allow.
# --------------------------------------------------------------------------- #


def test_non_bash_tool_allowed() -> None:
    assert hook.check({"tool_name": "Edit", "tool_input": {}}) is None


def test_non_review_command_allowed() -> None:
    assert hook.check(_bash("gh pr merge 7 --squash")) is None


def test_free_form_comment_allowed() -> None:
    """A comment with no charter header is free-form — never blocked."""
    assert hook.check(_bash(_comment_cmd("Nice work, LGTM informally."))) is None


def test_requestee_na_status_not_self_review() -> None:
    """`Requestee: N/A` is a status turn, not a self-review, even if the author's
    name were to normalize oddly — an N/A addressee is never blocked."""
    body = (
        "Requestor: Nia.Rossi\nRequestee: N/A\nRequestOrReplied: Request\n\n"
        "Status update.\nMust-fix:\n1. follow up\nTech-debt: None"
    )
    assert hook.check(_bash(_comment_cmd(body))) is None


def test_declares_fail_open() -> None:
    """The hook must declare fail-open so the dispatcher allows on its own crash."""
    assert getattr(hook, "FAIL_OPEN", False) is True


# --------------------------------------------------------------------------- #
# Reuse guard: the grammar delegation IS validate_review_comment_format's, and
# the self-review comparison reads the SAME header regexes (no reimplementation).
# --------------------------------------------------------------------------- #


def test_reuses_validate_review_comment_format_parsing() -> None:
    import validate_review_comment_format as vrcf

    # The grammar validator is the shared one, not a private copy.
    assert hook.vrcf is vrcf
    # Self-review reads the same header field regexes the grammar layer exports.
    assert set(vrcf._LINE_FIELD_RE) >= {"Requestor", "Requestee"}
