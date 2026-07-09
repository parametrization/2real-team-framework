"""Tests for validate_pr_body (issue #304).

The hook stops a `gh pr create` / `gh pr edit` whose PR body carries a GitHub
closing keyword (`Fix`/`Closes`/`Resolves` + `#N`) bound to an issue reference —
the trap that silently closed #296 when PR #299 merely quoted a retro proposal.

Load-bearing assertions (the mutation bar — each FAILS when the behavior is
reverted):

* ``test_regression_pr299_line39_blocks`` replays PR #299's body line 39 VERBATIM
  and asserts the block fires. Revert the matcher and #296 auto-closes again.
* ``test_backticked_reference_allowed`` / ``test_prose_reference_allowed`` pin the
  "smarter than the naive grep" requirement: a backticked ``\\`#123\\``` and prose
  ("per #123", "Address #123") must NOT trip. Delete the code-mask / keyword
  anchor and these regress to false positives.
* ``test_code_fence_allowed`` — a keyword inside a ``` fence is not a real close
  (GitHub does not close from code), so it must not block.
* ``test_blockquote_still_blocks`` — GitHub DOES close from a blockquote (that is
  literally how #296 closed), so a blockquoted keyword MUST still block. Guards
  against an over-eager mask that treats `>` like code.

Stdlib + pytest only.
"""

from __future__ import annotations

import shlex
import sys
import textwrap
from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))

import validate_pr_body as hook  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _bash(command: str, env: dict | None = None) -> dict:
    data: dict = {"tool_name": "Bash", "tool_input": {"command": command}}
    if env is not None:
        data["env"] = env
    return data


def _create(body: str) -> dict:
    """A `gh pr create` whose body is *body*, passed inline (shell-quoted safely)."""
    return _bash(f"gh pr create --base main --title T --body {shlex.quote(body)}")


def _create_body_file(body: str, tmp_path: Path) -> dict:
    """A `gh pr create --body-file <path>` whose file holds *body* (the realistic
    path for a large retro body — no inline shell-quoting fragility)."""
    body_file = tmp_path / "body.md"
    body_file.write_text(body, encoding="utf-8")
    data = _bash(f"gh pr create --base main --body-file {body_file}")
    data["cwd"] = str(tmp_path)
    return data


def _is_block(result) -> bool:
    return bool(result) and result.get("decision") == "block"


# The exact text of PR #299's body, line 39 — the phrase that closed #296.
# Kept byte-verbatim (backticks around `gaps` / `has_negative()` included) so the
# regression genuinely replays the real incident, not a paraphrase of it.
PR299_LINE39 = "1. Fix #296 by deriving `gaps` from `has_negative()`'s field set."


# --------------------------------------------------------------------------- #
# The regression: the real incident must be caught                            #
# --------------------------------------------------------------------------- #
def test_regression_pr299_line39_matcher() -> None:
    """The matcher, applied to PR #299 line 39 verbatim, reports the `Fix #296` hit —
    even though the line also contains backticked `gaps` / `has_negative()` spans."""
    assert hook.find_closing_refs(PR299_LINE39) == [("Fix", "#296")]


def test_regression_pr299_line39_blocks(tmp_path: Path) -> None:
    """PR #299 body line 39, verbatim, must block end-to-end (it closed #296).

    Routed through `--body-file` — the realistic path for a multi-line retro body,
    and free of the inline-quoting fragility the apostrophe in `has_negative()'s`
    would otherwise introduce."""
    result = hook.check(_create_body_file(PR299_LINE39, tmp_path))
    assert _is_block(result), "PR #299's `Fix #296` line must be blocked"
    assert "#296" in result["reason"]


def test_regression_pr299_line39_full_body_blocks(tmp_path: Path) -> None:
    """The same line embedded in a realistic multi-line retro body still blocks —
    the surrounding backticked spans (`gaps`, `has_negative()`) must not hide the
    unbackticked `Fix #296` that precedes them."""
    body = textwrap.dedent(
        """\
        ## Process proposals (4, recorded in the feedback log, none applied)
        1. Fix #296 by deriving `gaps` from `has_negative()`'s field set.
        2. `/wave-end` must recompute counters from `trust_signals.py extract`.
        3. Reconcile the reserved-5 tie rule.
        """
    )
    assert _is_block(hook.check(_create_body_file(body, tmp_path)))


# --------------------------------------------------------------------------- #
# Positive matches: every closing keyword / form GitHub honors                 #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "body",
    [
        "Fix #123",
        "Fixes #123",
        "Fixed #123",
        "Close #123",
        "Closes #123",
        "Closed #123",
        "Resolve #123",
        "Resolves #123",
        "Resolved #123",
        "Fixes: #123",          # colon separator
        "FIXES #123",           # case-insensitive
        "Closes owner/repo#123",  # cross-repo reference
        "Some work here. Fixes #123 as a side effect.",  # mid-body
    ],
)
def test_closing_keywords_block(body: str) -> None:
    assert _is_block(hook.check(_create(body))), f"expected block for: {body!r}"


# --------------------------------------------------------------------------- #
# Negative matches: smarter than the naive grep (the crux of #304)             #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "body",
    [
        "`#123`",                 # bare backticked reference
        "`Fix #123`",             # whole phrase backticked
        "Fix `#123`",             # keyword prose, reference backticked
        "See ``Closes #123`` in the log.",  # double-backtick span
        "per #123",               # prose, no keyword
        "Address #123",           # prose, no keyword
        "Related to #123",        # prose, no keyword
        "See #123 for context.",  # bare autolink, no keyword
        "This is a prefix #123 test.",   # 'prefix' contains 'fix' but not as a word
        "The door was disclosed #123.",  # 'disclosed' contains 'closed' but not as a word
        "Fix#123",                # run-together: GitHub does not close on this
    ],
)
def test_non_closing_forms_allowed(body: str) -> None:
    assert hook.check(_create(body)) is None, f"expected ALLOW for: {body!r}"


def test_backticked_reference_allowed() -> None:
    """Explicit AC: a backticked `#123` must not trip (naive grep false-positives)."""
    assert hook.check(_create("Fix `#296` — tracked, not closed here.")) is None


def test_prose_reference_allowed() -> None:
    """Explicit AC: prose 'per #123' / 'Address #123' must not trip."""
    assert hook.check(_create("Address #296 in a follow-up; see #297 per #298.")) is None


def test_code_fence_allowed() -> None:
    """A closing keyword inside a fenced code block is not a real GitHub close."""
    body = textwrap.dedent(
        """\
        Here is the offending line we are documenting:
        ```
        Fixes #296
        ```
        which GitHub would parse outside a fence.
        """
    )
    assert hook.check(_create(body)) is None


def test_blockquote_still_blocks() -> None:
    """GitHub DOES auto-close from a blockquote (how #296 closed) — must block."""
    body = "> 1. Fix #296 by deriving gaps from the field set."
    assert _is_block(hook.check(_create(body)))


# --------------------------------------------------------------------------- #
# Command gating                                                               #
# --------------------------------------------------------------------------- #
def test_gh_pr_edit_gated() -> None:
    assert _is_block(hook.check(_bash("gh pr edit 5 --body 'Fixes #123'")))


def test_short_body_flag_gated() -> None:
    assert _is_block(hook.check(_bash("gh pr create -b 'Closes #123'")))


def test_chained_command_gated() -> None:
    """A `cd ... && gh pr create` segment is still detected."""
    assert _is_block(hook.check(_bash("cd /tmp && gh pr create --body 'Fixes #123'")))


def test_non_gated_commands_allowed() -> None:
    for command in (
        "gh pr merge 7",                       # carries no new body
        "gh pr ready 7",                       # carries no new body
        "gh pr view 7",
        "gh issue create --body 'Fixes #123'",  # issue body does not auto-close on PR merge
        "echo 'Fixes #123'",
        "git commit -m 'Closes #123'",         # commit trailer is the CORRECT place
    ):
        assert hook.check(_bash(command)) is None, f"expected ALLOW for: {command!r}"


def test_no_body_flag_allowed() -> None:
    """`--fill` / interactive create carries no local body to scan → fail-open allow."""
    assert hook.check(_bash("gh pr create --fill --base main")) is None


def test_non_bash_tool_allowed() -> None:
    assert hook.check({"tool_name": "Edit", "tool_input": {}}) is None


# --------------------------------------------------------------------------- #
# Override + body-file + fail-open                                             #
# --------------------------------------------------------------------------- #
def test_override_via_env_allows() -> None:
    """A non-empty PR_BODY_CLOSING_KEYWORD_EXCEPTION is the audited escape hatch."""
    data = _create("Fixes #123")
    data["env"] = {"PR_BODY_CLOSING_KEYWORD_EXCEPTION": "genuinely implements #123"}
    assert hook.check(data) is None


def test_empty_override_still_blocks() -> None:
    data = _create("Fixes #123")
    data["env"] = {"PR_BODY_CLOSING_KEYWORD_EXCEPTION": "   "}
    assert _is_block(hook.check(data))


def test_body_file_scanned(tmp_path: Path) -> None:
    """`--body-file <path>` is read from disk and scanned."""
    body_file = tmp_path / "body.md"
    body_file.write_text("Retro notes.\nFixes #296 verbatim.\n", encoding="utf-8")
    data = _bash(
        f"gh pr create --base main --body-file {body_file}",
        env=None,
    )
    data["cwd"] = str(tmp_path)
    assert _is_block(hook.check(data))


def test_missing_body_file_fails_open(tmp_path: Path) -> None:
    """An unreadable --body-file is not evidence of a keyword → allow (#175)."""
    data = _bash(f"gh pr create --base main --body-file {tmp_path / 'nope.md'}")
    data["cwd"] = str(tmp_path)
    assert hook.check(data) is None


def test_fail_open_declared() -> None:
    """The module must declare FAIL_OPEN so the dispatcher allows on its own crash."""
    assert hook.FAIL_OPEN is True


# --------------------------------------------------------------------------- #
# Pure-function units for the matcher                                          #
# --------------------------------------------------------------------------- #
def test_find_closing_refs_dedupes() -> None:
    refs = hook.find_closing_refs("Fixes #1 and again Fixes #1 and Closes #2.")
    assert refs == [("Fixes", "#1"), ("Closes", "#2")]


def test_mask_code_removes_spans_keeps_prose() -> None:
    masked = hook.mask_code("before `Fix #1` after Fix #2")
    assert "#1" not in masked      # inside the code span → masked
    assert "Fix #2" in masked      # outside → preserved
