#!/usr/bin/env python3
"""PreToolUse hook: enforce the charter verdict-comment grammar on gh comments.

Gates ``gh pr comment`` / ``gh issue comment`` invocations. When the comment
body is *attempting* the charter verdict-comment shape (it carries at least one
of the header labels) but the shape is malformed, the command is blocked with an
actionable message. A comment that carries none of the header labels is a plain
free-form comment and passes untouched.

Why this exists (companion to #98)
==================================

``trust_signals.py`` scores review quality by parsing the verdict-comment shape
out of a PR's comment bodies: the ``Requestor:`` line (reviewer identity), the
``RequestOrReplied:`` line (the verdict state), and the body ``Must-fix:`` tally
(severity). If a reviewer posts a comment whose header is malformed — a missing
``RequestOrReplied:`` line, a mistyped verdict token, an empty field — the parser
silently skips it and the whole review-quality half of trust scoring reads as
**zero** (#98). This gate makes the format reliable at write time so those
signals cannot silently go dark.

Canonical verdict-comment grammar (the vocabulary #98 parses)
=============================================================

The single source of truth is ``.claude/team/charter/issues.md`` § Comment
Format / § Verdict-Comment Grammar. Restated here as the enforced contract:

  Header block — all three lines required, bare OR ``**bold**`` form accepted::

      Requestor: Firstname.Lastname          # the comment author (the reviewer)
      Requestee: Firstname.Lastname          # who is addressed (N/A for status)
      RequestOrReplied: Request              # Request (posting) | Replied (reply)

  Body severity markers — where the *severity* lives (NOT in the verdict token)::

      Must-fix: <enumerated items, or None>   # enumerated => changes requested
      Tech-debt: <items, or None>             # non-blocking

Vocabulary constants exported for #98 to align against:

  * ``HEADER_FIELDS``   — the three required header labels, in order.
  * ``VERDICT_STATES``  — the recognized ``RequestOrReplied`` tokens
    (``request`` | ``replied``, compared lower-cased).
  * ``SEVERITY_MARKERS`` — the body severity labels; a ``Must-fix:`` line with
    enumerated items is the "changes requested" signal, ``None`` / absent is the
    clean signal.

The header-extraction regexes in ``_STRICT_FIELD_RE`` are kept **byte-identical**
to ``trust_signals._FIELD_RE`` so this gate enforces exactly what the scorer
parses. ``test_validate_review_comment_format`` pins that equality.

Two tiers: block (grammar) vs warn (semantics) — issue #118
===========================================================

The gate separates a *structural* failure (which blocks) from a *semantic*
misuse (which only warns, fail-open):

  * **Block** — a malformed header (missing/mistyped field, unknown verdict
    token). The comment cannot be parsed by the scorer at all, so it is stopped
    at write time. This is the #111 contract, unchanged.

  * **Warn** — the header is well-formed but the Request-vs-Replied /
    Must-fix-vs-Tech-debt *semantics* are misused. Phase 4 Wave 1 surfaced two
    patterns that contaminated trust deltas (issue #118):

      1. ``RequestOrReplied: Request`` with an empty/``None`` Must-fix — an
         approval filed as a posting turn. It reads clean to the scorer, but the
         charter reserves ``Request`` for a turn that carries blocking findings;
         an approval with none should be ``Replied``.
      2. A ``Must-fix:`` item phrased as *non-blocking* ("non-blocking", "do not
         hold", "accept as-is", …) — a Tech-debt note filed under the blocking
         label. ``trust_signals.py`` counts it as ``must_fix_received``, a
         phantom negative signal.

    Both only *warn* (``{"decision": "allow", "systemMessage": ...}``): the
    author's intent may be legitimate, and blocking a well-formed comment over a
    phrasing judgment would be too aggressive. The dispatcher surfaces the
    systemMessage and still allows the command.

Fail-open posture (matches the dispatcher)
==========================================

The check is pure grammar — it needs no config, roster, or network, so it
trivially works whether or not those are present. It returns ``None`` (allow) on
every ambiguous edge: not a comment command, no extractable body, an unreadable
``--body-file``, or a body with no header labels at all. Only a genuine,
attempted-but-malformed charter comment is blocked; a well-formed comment with a
semantic misuse is *warned*, never blocked.

Exit codes:
  0 — allow (not a comment command, no body, free-form comment, well-formed, or
      a well-formed comment carrying only a semantic warning)
  2 — block (a charter verdict-comment attempt whose header grammar is malformed)
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _framework_log import log_pretooluse_block  # noqa: E402
from _shell_parse import (  # noqa: E402
    find_gh_subcommand,
    iter_command_segments,
    resolve_tool_cwd,
    strip_heredocs,
    tokenize,
    walk_flag_values,
)

# --------------------------------------------------------------------------- #
# Canonical grammar — the vocabulary #98 aligns against.
# --------------------------------------------------------------------------- #

#: The three required header labels, in charter order.
HEADER_FIELDS = ("Requestor", "Requestee", "RequestOrReplied")

#: Recognized ``RequestOrReplied`` tokens (compared lower-cased). Severity does
#: NOT live here — no ``Approved`` / ``ChangesRequested``; that goes in the body.
VERDICT_STATES = frozenset({"request", "replied"})

#: Body severity labels. ``Must-fix:`` with enumerated items => changes
#: requested; ``None`` / absent => clean. ``Tech-debt:`` is non-blocking.
SEVERITY_MARKERS = ("Must-fix", "Tech-debt")

# --------------------------------------------------------------------------- #
# Body-severity parsing for the SEMANTIC warn tier (#118).
#
# These mirror ``trust_signals._has_must_fix_items`` byte-for-byte (the coupling
# test pins the equality) so the gate's warn aligns with exactly what the scorer
# counts as a Must-fix. They are re-declared here rather than imported so the
# hook keeps its zero-dependency, fail-open posture: ``trust_signals`` lives in
# ``assets/lib`` which is not on the hook runtime's ``sys.path``, and importing
# it would make the gate crash (and silently skip) in a real install.
# --------------------------------------------------------------------------- #

#: The ``Must-fix:`` label line; group 1 captures any same-line remainder.
_MUST_FIX_LABEL_RE = re.compile(r"^\s*\**must[\s-]?fix\**:\s*(.*?)\s*$", re.IGNORECASE)
#: An enumerated / bulleted list item (``1.`` / ``2)`` / ``-`` / ``*`` / ``+``).
_LIST_ITEM_RE = re.compile(r"^\s*(?:\d+[.)]|[-*+])\s+\S")
#: An explicit "no findings" value (``None`` / ``N/A`` / ``-`` / ``0``).
_EMPTY_MUST_FIX_RE = re.compile(r"^(none|n/?a|-+|0)(?:\W|$)", re.IGNORECASE)

#: Non-blocking phrasing that does NOT belong under ``Must-fix:`` — it belongs
#: under ``Tech-debt:``. A ``Must-fix`` item carrying any of these is the Wave-1
#: misuse pattern that produced a phantom ``must_fix_received``.
_NON_BLOCKING_PHRASE_RE = re.compile(
    r"\bnon[\s-]?blocking\b"
    r"|\bnot\s+(?:a\s+)?block(?:er|ing)?\b"
    r"|\bdo(?:es)?\s*n['’o]?t\s+(?:block|hold)\b"
    r"|\bdon['’]t\s+(?:block|hold)\b"
    r"|\bno\s+need\s+to\s+(?:block|hold)\b"
    r"|\bwo?n['’]?t\s+(?:block|hold)\b"
    r"|\bwill\s+not\s+(?:block|hold)\b"
    r"|\baccept\s+as[\s-]?is\b"
    r"|\bnot\s+a\s+merge\s+blocker\b",
    re.IGNORECASE,
)

#: Fenced / inline code stripping, so the ``must-fix`` token or the non-blocking
#: vocabulary inside a code span or test name is never counted (mirrors
#: ``trust_signals._strip_code_markup``).
_FENCED_CODE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")

# The shared header grammar — byte-identical to trust_signals._FIELD_RE. This is
# what the SCORER (#98) parses; the coupling test pins the equality so the two
# never drift. Note the ``\s*`` after the colon can span a newline, so an *empty*
# field silently swallows the next line — which is exactly the "reads as zero"
# failure mode this gate exists to prevent. The gate therefore validates with the
# stricter, newline-safe ``_LINE_FIELD_RE`` below (a superset of the scorer's
# requirements: everything the gate accepts, the scorer also parses).
_STRICT_FIELD_RE = {
    "Requestor": re.compile(r"^\**Requestor\**:\**\s*(.+?)\**\s*$", re.MULTILINE),
    "Requestee": re.compile(r"^\**Requestee\**:\**\s*(.+?)\**\s*$", re.MULTILINE),
    "RequestOrReplied": re.compile(r"^\**RequestOrReplied\**:\**\s*(\w+)", re.MULTILINE),
}

# Newline-safe enforcement matcher (gate side). Each field must appear on its OWN
# line with a **non-empty same-line value** — ``[ \t]`` (never ``\s``) around the
# colon so the value capture cannot cross into the next line, and ``(\S.*?)``
# requires at least one non-space character. Bare and ``**bold**`` forms both
# accepted.
_LINE_FIELD_RE = {
    name: re.compile(rf"^\**{name}\**:\**[ \t]*(\S.*?)\s*$", re.MULTILINE)
    for name in HEADER_FIELDS
}

# Fuzzy trigger — case-insensitive detection of an *attempted* header line, so a
# near-miss (wrong casing, missing field) still trips validation rather than
# slipping through as "not a charter comment". `\b` after the label keeps the
# `Requestor` alternative from matching inside `RequestOrReplied`.
_TRIGGER_RE = re.compile(
    r"^\s*\**\s*(?:Requestor|Requestee|RequestOrReplied)\b\s*\**\s*:",
    re.IGNORECASE | re.MULTILINE,
)

# Heredoc body: `<<EOF ... EOF` (and the quoted / `<<-` variants). Group 2 is the
# body between the opener line and the closing delimiter.
_HEREDOC_BODY_RE = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n(.*?)\n[ \t]*\1\b",
    re.DOTALL,
)

_BODY_FLAGS = {"--body", "-b"}
_BODY_FILE_FLAGS = {"--body-file", "-F"}


# --------------------------------------------------------------------------- #
# Command / body extraction.
# --------------------------------------------------------------------------- #


def is_comment_command(command: str) -> bool:
    """True if *command* invokes ``gh pr comment`` or ``gh issue comment``."""
    tokens = tokenize(strip_heredocs(command))
    if tokens is None:
        # Malformed quoting defeated the tokenizer — fall back to a conservative
        # regex so a heredoc-heavy command is still recognized.
        return bool(re.search(r"\bgh\s+(?:pr|issue)\s+comment\b", command))
    for seg in iter_command_segments(tokens):
        gh = find_gh_subcommand(seg)
        if gh is None:
            continue
        _globals, rest = gh
        if rest[:2] in (["pr", "comment"], ["issue", "comment"]):
            return True
    return False


def _read_body_file(path_str: str, input_data: dict | None) -> str | None:
    """Best-effort read of a ``--body-file`` path. None on any failure (fail-open).

    A relative path is resolved against the tool's working directory so a
    comment posted with ``--body-file relative/path.md`` is still inspectable.
    """
    try:
        p = Path(path_str)
        if not p.is_absolute() and input_data is not None:
            cwd = resolve_tool_cwd(input_data)
            if cwd:
                p = Path(cwd) / p
        return p.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None


def extract_comment_body(command: str, input_data: dict | None = None) -> str | None:
    """Extract the comment body from a ``gh ... comment`` command, or None.

    Resolution order: a heredoc body (``--body "$(cat <<'EOF' ... EOF)"`` and
    friends) first, then an inline ``--body``/``-b`` value, then a best-effort
    read of a ``--body-file``/``-F`` path. Returns None when nothing is
    extractable — the caller fails open.
    """
    heredoc = _HEREDOC_BODY_RE.search(command)
    if heredoc:
        return heredoc.group(2)

    tokens = tokenize(command)
    if tokens is not None:
        inline = walk_flag_values(tokens, _BODY_FLAGS)
        if inline:
            return inline[0]
        files = walk_flag_values(tokens, _BODY_FILE_FLAGS)
        if files:
            return _read_body_file(files[0], input_data)
    return None


# --------------------------------------------------------------------------- #
# Grammar validation (pure).
# --------------------------------------------------------------------------- #


def looks_like_charter_comment(body: str) -> bool:
    """True if *body* carries at least one (fuzzy) header label — i.e. it is an
    *attempt* at the charter verdict-comment shape."""
    return bool(_TRIGGER_RE.search(body))


_MISSING_REASON = (
    "BLOCKED: charter verdict-comment is malformed — missing or misformatted "
    "header field(s): {fields}.\n\n"
    "Every PR/issue verdict comment MUST open with all three header lines "
    "(bare or **bold** form both accepted):\n\n"
    "  Requestor: Firstname.Lastname        # the reviewer (comment author)\n"
    "  Requestee: Firstname.Lastname        # the PR author (N/A for status)\n"
    "  RequestOrReplied: Request            # Request (posting) | Replied (reply)\n\n"
    "Severity is carried in the BODY, not the verdict token:\n"
    "  Must-fix: <enumerated items, or None>   # enumerated = changes requested\n"
    "  Tech-debt: <items, or None>             # non-blocking\n\n"
    "trust_signals.py (#98) parses this exact shape to score review quality; a "
    "malformed header makes those signals read as zero."
)

_VERDICT_REASON = (
    "BLOCKED: RequestOrReplied value {got!r} is not a recognized verdict state.\n"
    "Use exactly one of:  Request  (posting)  |  Replied  (responding).\n\n"
    "Do NOT put severity in the verdict token (no 'Approved' / "
    "'ChangesRequested') — severity belongs in the body as 'Must-fix:' items "
    "(enumerated = changes requested, 'None' = clean). trust_signals.py (#98) "
    "reads Request/Replied plus the body Must-fix tally; an unrecognized token "
    "makes the review signals read as zero."
)


def validate_grammar(body: str) -> str | None:
    """Return a block reason if the charter comment is malformed, else None."""
    matches = {name: _LINE_FIELD_RE[name].search(body) for name in HEADER_FIELDS}
    missing = [name for name in HEADER_FIELDS if not matches[name]]
    if missing:
        return _MISSING_REASON.format(fields=", ".join(missing))

    # The verdict value may carry a trailing annotation (e.g. "Request (re-review)");
    # the token is the first word.
    verdict = matches["RequestOrReplied"].group(1).split()[0].strip("*").strip()
    if verdict.lower() not in VERDICT_STATES:
        return _VERDICT_REASON.format(got=verdict)

    return None


# --------------------------------------------------------------------------- #
# Semantic warnings (pure) — the WARN tier (#118). Fail-open: never blocks.
# --------------------------------------------------------------------------- #


def _strip_code_markup(text: str) -> str:
    """Blank out fenced blocks and inline code spans (positions preserved)."""
    text = _FENCED_CODE_RE.sub(lambda m: " " * len(m.group()), text)
    text = _INLINE_CODE_RE.sub(lambda m: " " * len(m.group()), text)
    return text


def _must_fix_items(body: str) -> list[str]:
    """Return the text of each ``Must-fix:`` item, or ``[]`` when the section is
    empty / ``None`` / absent.

    Mirrors ``trust_signals._has_must_fix_items``: an inline value on the label
    line counts as one item (unless it's an explicit "no findings" marker); a
    bare label takes the following enumerated/bulleted lines. Code spans are
    stripped first. Only the first ``Must-fix:`` section is read.
    """
    lines = _strip_code_markup(body).splitlines()
    for i, line in enumerate(lines):
        label_m = _MUST_FIX_LABEL_RE.match(line)
        if not label_m:
            continue
        items: list[str] = []
        inline = label_m.group(1).strip()
        if inline and not _EMPTY_MUST_FIX_RE.match(inline):
            items.append(inline)
        # Collect following enumerated/bulleted item lines (skipping blanks).
        j = i + 1
        while j < len(lines):
            nxt = lines[j]
            if not nxt.strip():
                j += 1
                continue
            if _LIST_ITEM_RE.match(nxt):
                items.append(nxt.strip())
                j += 1
                continue
            break
        return items
    return []


_WARN_REQUEST_NO_MUSTFIX = (
    "WARNING (not blocking): RequestOrReplied is `Request` but there are no "
    "blocking `Must-fix:` items ({detail}). The charter reserves `Request` for a "
    "turn that carries blocking findings; an approval / response with no "
    "must-fix should be `RequestOrReplied: Replied` (or add the blocking items "
    "under `Must-fix:`). Filed as `Request`, trust_signals reads this as a clean "
    "posting — harmless to the score, but it muddies the Request/Replied "
    "distinction the charter draws."
)

_WARN_NONBLOCKING_MUSTFIX = (
    "WARNING (not blocking): a `Must-fix:` item is phrased as non-blocking "
    "({quoted}). `Must-fix:` is blocking-only — anything you would NOT hold the "
    "merge for belongs under `Tech-debt:`. trust_signals counts every Must-fix "
    "item as a `must_fix_received` negative signal against the author, so a "
    "non-blocking note filed here becomes a phantom blocking signal (the exact "
    "Wave-1 contamination this gate now flags)."
)


def semantic_warnings(body: str) -> str | None:
    """Return a fail-open advisory for a well-formed comment whose Request/Replied
    or Must-fix/Tech-debt *semantics* are misused, else None.

    Precondition: the header grammar is already valid (``validate_grammar``
    returned None), so the verdict token parses cleanly. Two patterns warn:

      1. ``Request`` + empty/``None`` Must-fix  -> should be ``Replied``.
      2. a ``Must-fix:`` item phrased non-blocking -> should be ``Tech-debt:``.

    The two are effectively mutually exclusive (pattern 1 needs an empty
    Must-fix, pattern 2 needs an item present); the join is kept as a defensive
    no-op so adding a future pattern needs no rewiring.
    """
    verdict_m = _LINE_FIELD_RE["RequestOrReplied"].search(body)
    if verdict_m is None:  # defensive — grammar was validated upstream
        return None
    verdict = verdict_m.group(1).split()[0].strip("*").strip().lower()

    items = _must_fix_items(body)
    warnings: list[str] = []

    if verdict == "request" and not items:
        detail = "the `Must-fix:` section is `None`/empty or absent"
        warnings.append(_WARN_REQUEST_NO_MUSTFIX.format(detail=detail))

    non_blocking = [it for it in items if _NON_BLOCKING_PHRASE_RE.search(it)]
    if non_blocking:
        quoted = "; ".join(f'"{it[:80]}"' for it in non_blocking)
        warnings.append(_WARN_NONBLOCKING_MUSTFIX.format(quoted=quoted))

    if not warnings:
        return None
    return "\n\n".join(warnings)


def check(input_data: dict) -> dict | None:
    """Block result dict if a malformed charter verdict-comment is detected, an
    allow+warning dict if it is well-formed but semantically misused (#118), else
    None. Fails open on every ambiguous edge (see module docstring)."""
    if input_data.get("tool_name") != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    if not is_comment_command(command):
        return None

    body = extract_comment_body(command, input_data)
    if not body:
        return None  # nothing inspectable (e.g. unreadable --body-file) → allow

    if not looks_like_charter_comment(body):
        return None  # free-form comment, not a charter verdict-comment attempt

    reason = validate_grammar(body)
    if reason is not None:
        log_pretooluse_block(
            "validate_review_comment_format", command, reason, input_data=input_data
        )
        return {"decision": "block", "reason": reason}

    # Grammar is well-formed. Evaluate the SEMANTIC warn tier (#118): never
    # blocks, only surfaces an advisory the dispatcher relays.
    warning = semantic_warnings(body)
    if warning is not None:
        return {"decision": "allow", "systemMessage": warning}

    return None


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result and result.get("decision") == "block":
        print(json.dumps(result))
        sys.exit(2)
    if result and result.get("systemMessage"):
        # Well-formed but semantically misused (#118): surface the advisory and
        # still allow (fail-open) — matches the dispatcher's warn contract.
        print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
