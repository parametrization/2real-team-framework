"""Tests for validate_review_comment_format (issue #111).

The hook enforces the charter verdict-comment grammar on ``gh pr comment`` /
``gh issue comment`` invocations. Tests cover:

* the pure grammar validator over the **real Phase 3 comment corpus** (PRs #96,
  #93, #79 — accepted verbatim) plus a Reply and the bold header form;
* malformed attempts (missing field, empty field, unknown verdict token) — all
  rejected with an actionable reason;
* body extraction from heredoc / ``--body`` / ``--body-file`` command shapes;
* command detection and the fail-open edges (non-comment command, no body,
  unreadable body-file, free-form comment with no header);
* a coupling guard pinning the header-extraction grammar to
  ``trust_signals._FIELD_RE`` so the gate (#111) and the scorer (#98) never
  drift apart.

Stdlib + pytest only.
"""

from __future__ import annotations

import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "lib"))

import trust_signals as ts  # noqa: E402
import validate_review_comment_format as hook  # noqa: E402


# --------------------------------------------------------------------------- #
# Real Phase 3 corpus (headers verbatim; bodies trimmed). These MUST all pass.
# --------------------------------------------------------------------------- #

CORPUS_PR96 = """Requestor: Tariq Morales (QA)
Requestee: Ibrahim El-Amin
RequestOrReplied: Request

**Review: issues — two release-notes wording corrections; everything else is release-ready**

Must-fix:
1. **Permissions-allowlist claim is factually wrong.** ...
2. **Ontology meta/child wording overstates.** ...

Tech-debt: None."""

CORPUS_PR93 = """Requestor: Nia.Rossi
Requestee: Tariq.Morales
RequestOrReplied: Request

**Review: LGTM with one must-fix (PR-body record correction)**

**Must-fix:**
1. Edit the PR body's QA-evidence line ...

**Tech-debt:** filed as #94 ..."""

CORPUS_PR79 = """Requestor: Tariq Morales (QA)
Requestee: Paloma Gupta
RequestOrReplied: Request

**Review: issues (one must-fix — merge conflict with the moved base)**

Must-fix:
1. **Rebase required — PR is CONFLICTING against the base** ...

Tech-debt: None filed."""

CORPUS_REPLY = """Requestor: Ibrahim El-Amin
Requestee: Nia.Rossi
RequestOrReplied: Replied

Rebased and pushed; conflicts resolved semantically per your note."""

BOLD_FORM = """**Requestor:** Nia.Rossi
**Requestee:** Tariq.Morales
**RequestOrReplied:** Request

**Review: LGTM**
Must-fix: None
Tech-debt: None"""

VALID_BODIES = {
    "pr96": CORPUS_PR96,
    "pr93": CORPUS_PR93,
    "pr79": CORPUS_PR79,
    "reply": CORPUS_REPLY,
    "bold": BOLD_FORM,
}

# Semantically CLEAN bodies: well-formed AND correct Request/Replied +
# Must-fix/Tech-debt usage, so ``check`` returns None (no block, no warn).
# BOLD_FORM is intentionally excluded — it is a `Request` with `Must-fix: None`
# (an approval filed as a posting turn), which the #118 warn tier now flags.
CLEAN_BODIES = {
    "pr96": CORPUS_PR96,
    "pr93": CORPUS_PR93,
    "pr79": CORPUS_PR79,
    "reply": CORPUS_REPLY,
}


def _bash(command: str, cwd: str | None = None) -> dict:
    d: dict = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        d["cwd"] = cwd
    return d


def _comment_cmd(body: str, pr: int = 1, sub: str = "pr") -> str:
    """A ``gh <sub> comment`` command carrying *body* via a heredoc (quote-safe)."""
    return f"gh {sub} comment {pr} --body \"$(cat <<'EOF'\n{body}\nEOF\n)\""


# --------------------------------------------------------------------------- #
# Pure grammar: the real corpus is accepted.
# --------------------------------------------------------------------------- #


def test_grammar_accepts_every_real_corpus_body() -> None:
    for name, body in VALID_BODIES.items():
        assert hook.validate_grammar(body) is None, f"{name} should be well-formed"
        assert hook.looks_like_charter_comment(body) is True


def test_check_accepts_clean_corpus_through_command() -> None:
    # Semantically clean, well-formed comments pass with no block and no warn.
    for name, body in CLEAN_BODIES.items():
        assert hook.check(_bash(_comment_cmd(body))) is None, name


def test_check_accepts_issue_comment_subcommand() -> None:
    assert hook.check(_bash(_comment_cmd(CORPUS_REPLY, sub="issue"))) is None


# --------------------------------------------------------------------------- #
# Pure grammar: malformed attempts are rejected.
# --------------------------------------------------------------------------- #


def test_missing_requestorreplied_blocks() -> None:
    body = "Requestor: A.One\nRequestee: B.Two\n\nsome review text"
    reason = hook.validate_grammar(body)
    assert reason and "RequestOrReplied" in reason


def test_missing_requestor_blocks() -> None:
    body = "Requestee: B.Two\nRequestOrReplied: Request\n\ntext"
    reason = hook.validate_grammar(body)
    assert reason and "Requestor" in reason


def test_empty_field_value_blocks() -> None:
    body = "Requestor:\nRequestee: B.Two\nRequestOrReplied: Request"
    reason = hook.validate_grammar(body)
    assert reason and "Requestor" in reason


def test_lowercase_label_blocks_with_casing_guidance() -> None:
    # Fuzzy trigger fires (case-insensitive) but the strict, trust_signals-aligned
    # matcher is case-sensitive, so a lowercase label is a real malformation:
    # trust_signals would not parse it either.
    body = "requestor: A.One\nRequestee: B.Two\nRequestOrReplied: Request"
    assert hook.looks_like_charter_comment(body) is True
    reason = hook.validate_grammar(body)
    assert reason and "Requestor" in reason


def test_unknown_verdict_token_blocks() -> None:
    for bad in ("Approved", "ChangesRequested", "Requst", "Done"):
        body = f"Requestor: A.One\nRequestee: B.Two\nRequestOrReplied: {bad}"
        reason = hook.validate_grammar(body)
        assert reason and "verdict state" in reason, bad
        assert bad in reason


def test_check_blocks_malformed_through_command() -> None:
    body = "Requestor: A.One\nRequestee: B.Two\nRequestOrReplied: Approved"
    result = hook.check(_bash(_comment_cmd(body)))
    assert result and result["decision"] == "block"
    assert "Request" in result["reason"] and "Replied" in result["reason"]


# --------------------------------------------------------------------------- #
# Semantic WARN tier (#118) — the two Phase 4 Wave 1 misuse patterns. All warn
# (fail-open) rather than block: a well-formed comment is never stopped.
# --------------------------------------------------------------------------- #

# WAVE-1 MISUSE #1: an approving reviewer filed the verdict as `Request` with no
# blocking Must-fix (three Wave-1 approvers did this → phantom clean-Request).
WAVE1_APPROVAL_AS_REQUEST = """Requestor: Nia.Rossi
Requestee: Ibrahim.El-Amin
RequestOrReplied: Request

**Review: LGTM — ships as-is**
Must-fix: None
Tech-debt: None"""

# WAVE-1 MISUSE #2: a non-blocking observation filed under `Must-fix:` instead of
# `Tech-debt:` (→ phantom must_fix_received / review_false_positive in Wave 1).
WAVE1_NONBLOCKING_UNDER_MUSTFIX = """Requestor: Tariq.Morales
Requestee: Paloma.Gupta
RequestOrReplied: Request

**Review: one note**
Must-fix:
1. Reviewer-name reads "Tariq (QA)" not the canonical form — non-blocking, do not hold the merge.

Tech-debt: None"""


def _warn(body: str) -> str | None:
    result = hook.check(_bash(_comment_cmd(body)))
    if result is None:
        return None
    assert result["decision"] == "allow", "semantic misuse must WARN, never block"
    return result["systemMessage"]


def test_wave1_approval_as_request_warns_should_be_replied() -> None:
    msg = _warn(WAVE1_APPROVAL_AS_REQUEST)
    assert msg is not None, "Request + Must-fix:None must warn"
    assert "Replied" in msg
    # It must NOT block: grammar is valid.
    assert hook.validate_grammar(WAVE1_APPROVAL_AS_REQUEST) is None


def test_wave1_nonblocking_under_mustfix_warns_should_be_tech_debt() -> None:
    msg = _warn(WAVE1_NONBLOCKING_UNDER_MUSTFIX)
    assert msg is not None, "non-blocking item under Must-fix must warn"
    assert "Tech-debt" in msg
    assert hook.validate_grammar(WAVE1_NONBLOCKING_UNDER_MUSTFIX) is None


def test_bold_request_with_none_mustfix_warns() -> None:
    # BOLD_FORM is a bold-header `Request` + `Must-fix: None` — same misuse #1.
    msg = _warn(BOLD_FORM)
    assert msg is not None and "Replied" in msg


def test_request_with_real_mustfix_does_not_warn() -> None:
    # The correct use of `Request`: it carries blocking items. No warn.
    for name in ("pr96", "pr93", "pr79"):
        assert hook.semantic_warnings(VALID_BODIES[name]) is None, name


def test_replied_with_none_mustfix_does_not_warn() -> None:
    # A `Replied` turn with no must-fix is exactly correct — no warn.
    assert hook.semantic_warnings(CORPUS_REPLY) is None


def test_multiple_nonblocking_phrasings_flagged() -> None:
    for phrase in ("non-blocking", "do not hold", "accept as-is", "not a blocker",
                   "won't block", "no need to block"):
        body = (
            "Requestor: A.One\nRequestee: B.Two\nRequestOrReplied: Request\n\n"
            f"Must-fix:\n1. Some note — {phrase}, just tracking it.\n"
        )
        assert hook.semantic_warnings(body), phrase


def test_must_fix_items_parsing() -> None:
    assert hook._must_fix_items("Must-fix: None") == []
    assert hook._must_fix_items("Must-fix: N/A (all resolved)") == []
    assert hook._must_fix_items("Must-fix:\n1. real item\n2. another") == [
        "1. real item",
        "2. another",
    ]
    assert hook._must_fix_items("Must-fix: an inline blocking item") == [
        "an inline blocking item"
    ]
    # Code spans are stripped, so a `must-fix` token in code is not a section.
    assert hook._must_fix_items("see `Must-fix: None` in the parser") == []


def test_semantic_code_span_not_flagged() -> None:
    # Non-blocking vocabulary inside a code span must not trip the warn.
    body = (
        "Requestor: A.One\nRequestee: B.Two\nRequestOrReplied: Request\n\n"
        "Must-fix:\n1. Rename `do_not_hold_flag` to a clearer name.\n"
    )
    # The only 'do not hold' is inside a code span → not a non-blocking phrase;
    # the item itself is a real blocking rename, so no non-blocking warn.
    msg = hook.semantic_warnings(body)
    assert msg is None or "Tech-debt" not in msg


# --------------------------------------------------------------------------- #
# Fail-open edges.
# --------------------------------------------------------------------------- #


def test_free_form_comment_with_no_header_is_allowed() -> None:
    assert hook.check(_bash(_comment_cmd("LGTM, merging now."))) is None


def test_non_comment_commands_ignored() -> None:
    assert hook.check(_bash("gh pr view 5 --json headRefName")) is None
    assert hook.check(_bash("git commit -m 'RequestOrReplied: nope'")) is None
    assert hook.check(_bash("gh pr merge 5 --merge")) is None


def test_non_bash_tool_ignored() -> None:
    assert hook.check({"tool_name": "Agent", "tool_input": {}}) is None


def test_prose_mentioning_label_not_treated_as_header() -> None:
    # "the Requestor is ..." — label not at a line-start-then-colon position.
    body = "Reminder: the Requestor is always the reviewer, never the author."
    assert hook.looks_like_charter_comment(body) is False


def test_requestor_alternative_does_not_match_inside_requestorreplied() -> None:
    # A comment with ONLY the RequestOrReplied header (no Requestor/Requestee)
    # must still trigger — and then fail as missing the other two.
    body = "RequestOrReplied: Request\n\ntext"
    assert hook.looks_like_charter_comment(body) is True
    reason = hook.validate_grammar(body)
    assert reason and "Requestor" in reason and "Requestee" in reason


# --------------------------------------------------------------------------- #
# Body extraction: heredoc / --body / -F.
# --------------------------------------------------------------------------- #


def test_extract_body_heredoc() -> None:
    cmd = _comment_cmd(CORPUS_REPLY)
    assert hook.extract_comment_body(cmd) == CORPUS_REPLY


def test_extract_body_inline_flag() -> None:
    cmd = "gh pr comment 3 --body 'Requestor: A.One'"
    assert hook.extract_comment_body(cmd) == "Requestor: A.One"


def test_extract_body_short_flag() -> None:
    cmd = "gh pr comment 3 -b 'hello world'"
    assert hook.extract_comment_body(cmd) == "hello world"


def test_extract_body_file_readable(tmp_path: Path) -> None:
    f = tmp_path / "body.md"
    f.write_text(CORPUS_PR93, encoding="utf-8")
    cmd = f"gh pr comment 3 --body-file {f}"
    assert hook.extract_comment_body(cmd) == CORPUS_PR93


def test_body_file_malformed_blocks(tmp_path: Path) -> None:
    f = tmp_path / "body.md"
    f.write_text("Requestor: A.One\nRequestee: B.Two\nRequestOrReplied: Nope", encoding="utf-8")
    cmd = f"gh pr comment 3 --body-file {f}"
    result = hook.check(_bash(cmd))
    assert result and result["decision"] == "block"


def test_body_file_readable_valid_allowed(tmp_path: Path) -> None:
    f = tmp_path / "body.md"
    f.write_text(CORPUS_PR96, encoding="utf-8")
    cmd = f"gh pr comment 3 -F {f}"
    assert hook.check(_bash(cmd)) is None


def test_unreadable_body_file_fails_open() -> None:
    cmd = "gh pr comment 3 --body-file /nonexistent/path/does/not/exist.md"
    assert hook.extract_comment_body(cmd) is None
    assert hook.check(_bash(cmd)) is None


def test_body_file_relative_resolved_against_cwd(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text(CORPUS_PR79, encoding="utf-8")
    cmd = "gh pr comment 3 --body-file note.md"
    assert hook.extract_comment_body(cmd, {"cwd": str(tmp_path)}) == CORPUS_PR79


# --------------------------------------------------------------------------- #
# Command detection.
# --------------------------------------------------------------------------- #


def test_is_comment_command_variants() -> None:
    assert hook.is_comment_command("gh pr comment 5 --body x") is True
    assert hook.is_comment_command("gh issue comment 5 --body x") is True
    assert hook.is_comment_command("cd repo && gh pr comment 5 -b x") is True
    assert hook.is_comment_command("gh pr view 5") is False
    assert hook.is_comment_command("gh pr create --title x") is False
    # `gh` not at command position (inside echo) is precisely NOT a comment command.
    assert hook.is_comment_command("echo gh pr comment") is False


# --------------------------------------------------------------------------- #
# Coupling guard: the header grammar is shared with trust_signals (#98).
# --------------------------------------------------------------------------- #


def test_field_regexes_match_trust_signals() -> None:
    """The gate (#111) must enforce EXACTLY what the scorer (#98) parses."""
    assert hook._STRICT_FIELD_RE["Requestor"].pattern == ts._FIELD_RE["requestor"].pattern
    assert hook._STRICT_FIELD_RE["Requestee"].pattern == ts._FIELD_RE["requestee"].pattern
    assert hook._STRICT_FIELD_RE["RequestOrReplied"].pattern == ts._FIELD_RE["verdict"].pattern


def test_must_fix_regexes_match_trust_signals() -> None:
    """The gate's Must-fix parsing (#118 warn tier) must mirror the scorer's, so
    the gate warns about exactly what trust_signals counts."""
    assert hook._MUST_FIX_LABEL_RE.pattern == ts._MUST_FIX_LABEL_RE.pattern
    assert hook._LIST_ITEM_RE.pattern == ts._LIST_ITEM_RE.pattern
    assert hook._EMPTY_MUST_FIX_RE.pattern == ts._EMPTY_MUST_FIX_RE.pattern


def test_exported_vocabulary_constants() -> None:
    assert hook.HEADER_FIELDS == ("Requestor", "Requestee", "RequestOrReplied")
    assert hook.VERDICT_STATES == frozenset({"request", "replied"})
    assert hook.SEVERITY_MARKERS == ("Must-fix", "Tech-debt")


def test_wired_into_pre_bash_defaults() -> None:
    import _framework_config

    pre_bash = _framework_config._DEFAULTS["hooks"]["pre_bash"]
    assert "validate_review_comment_format" in pre_bash
