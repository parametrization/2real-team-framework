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

Fail-open posture (matches the dispatcher)
==========================================

The check is pure grammar — it needs no config, roster, or network, so it
trivially works whether or not those are present. It returns ``None`` (allow) on
every ambiguous edge: not a comment command, no extractable body, an unreadable
``--body-file``, or a body with no header labels at all. Only a genuine,
attempted-but-malformed charter comment is blocked.

Exit codes:
  0 — allow (not a comment command, no body, free-form comment, or well-formed)
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


def check(input_data: dict) -> dict | None:
    """Block result dict if a malformed charter verdict-comment is detected, else
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
    if reason is None:
        return None

    log_pretooluse_block(
        "validate_review_comment_format", command, reason, input_data=input_data
    )
    return {"decision": "block", "reason": reason}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result and result.get("decision") == "block":
        print(json.dumps(result))
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
