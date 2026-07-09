#!/usr/bin/env python3
"""PreToolUse hook: stop a PR *body* from silently auto-closing an issue it only quotes.

Story: Phase 7 Wave 2 S4, issue #304. GitHub auto-closes an issue when a PR body
contains a *closing keyword* bound to an issue reference — ``Fix #296``,
``Closes #123``, ``Resolves #7`` — the instant the PR merges. That is intended for
a PR that genuinely implements the fix. It is a TRAP for a PR whose body merely
*quotes* such a phrase: retro PRs are pure prose *about* issues, so they are the
most likely place to reproduce the phrase and the least likely place anyone
expects an issue to close.

It already happened (the reason this hook exists)
=================================================
PR #299 (Wave 22 retro artifacts) reproduced a retro proposal verbatim in its
body::

    1. Fix #296 by deriving `gaps` from `has_negative()`'s field set.

GitHub parsed ``Fix #296`` and closed #296 one second after #299 merged — even
though no commit on ``main`` carried a closing trailer for #296 and the defect it
tracks was never touched. It stayed wrongly closed ~78 minutes and needed a manual
reopen. See :func:`framework/tests/test_validate_pr_body.py` for the verbatim
regression replay.

The asymmetry that makes this quiet
====================================
An auto-close from a **commit trailer** is intentional and visible in the merge
commit — ``git log --grep`` finds it. An auto-close from a **PR body** leaves NO
trace in ``git log`` at all. That invisibility is exactly why #296's closure was
first misdiagnosed as operator error. This gate makes the invisible case loud, at
the one moment it is cheapest to fix: when the body is being written.

Team convention this enforces (charter/commits.md, pull-requests.md)
====================================================================
Under this team's charter a closing keyword belongs in the **commit message**
(the visible, ``git log``-greppable authority), NEVER in the PR body. So ANY
closing keyword bound to an issue reference in a PR body is, by policy, the thing
to stop — regardless of whether a commit also closes that issue. If a commit
legitimately closes it, the body keyword is redundant and should simply be dropped
from the body (kept only in the commit trailer). This is strictly stronger than
"block only when the issue is not already in the diff's closing set" (#304's
acceptance phrasing): the body-only, git-log-invisible case is a subset of what
this blocks, and the stronger rule needs no network and cannot be defeated by a
redundant commit trailer.

Detection — LOCAL, deterministic, stdlib-only, rate-limit-immune
================================================================
The check reads the PR body straight from the gated command (``--body`` / ``-b``
inline, or ``--body-file`` / ``-F`` from disk). No GitHub API call, so it is
immune to the GraphQL rate limits that routinely throttle ``gh`` and cannot be
neutered by a transient network failure at the moment it matters most.

Smarter than the naive grep (the crux, #304)
---------------------------------------------
A naive ``grep -iE '\\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\\b\\s*:?\\s*#[0-9]+'``
false-positives on backticked / code-fenced text — confirmed on the Wave 23
assignment comments. Before matching, this hook MASKS every markdown code span
(`` `#123` ``, ``` ``x`` ```) and fenced code block (```` ``` ```` / ``~~~``), so a
backticked reference and any keyword inside code never trip the check. GitHub
itself does not auto-close from inside a code span, so the mask mirrors GitHub's
own parser. Blockquotes are NOT masked — GitHub DOES auto-close from a blockquote
(that is precisely how #299 closed #296), so the check must still fire there.
Prose forms with no closing keyword ("Address #123", "per #123", a bare
``#123``) never match, because the matcher is anchored on the keyword.

Gated commands
==============
``gh pr create`` and ``gh pr edit`` — the two commands that SET a PR body from a
local string. A body must be set by one of these before it can auto-close anything
at merge time, so gating them catches every body-authored close at its source with
zero network. ``gh pr ready`` / ``gh pr merge`` are deliberately not gated: they
carry no new body, and re-fetching the already-vetted body over the network would
reintroduce exactly the rate-limit-fragile dependency this local design avoids.
(A body set through the web UI or a raw ``gh api`` PATCH is out of scope — the same
"team uses gh-cli" boundary the sibling ``validate_workflow_paths_coverage`` hook
documents.)

Override — deliberate, documented, always available offline
===========================================================
Mirrors the ``LOAD_BEARING_TEST_EXCEPTION`` convention. When a PR genuinely must
carry a closing keyword in its body::

    PR_BODY_CLOSING_KEYWORD_EXCEPTION="<rationale>" gh pr create ...

A non-empty ``<rationale>`` allows the command; the block message enumerates the
exact references being confirmed. This escape hatch needs no network, so the gate
is never a wedge even under a total ``gh`` outage — which is what makes fail-open
safe here (see below).

FAIL_OPEN posture (#175)
========================
Declared ``FAIL_OPEN = True``: this gate's ground-truth signal (a closing keyword
in the body) is a positive local observation, but an *inability to observe* it —
a command that will not tokenize, a ``--body-file`` that cannot be read, any
unexpected crash — must never block. A body the hook cannot read is not evidence
of a closing keyword, so degrade to ALLOW. The block only ever fires on a body the
hook successfully read AND found a keyword in; that block is always resolvable
locally (drop the keyword, backtick the reference, move it to the commit trailer,
or set the override), so it never wedges the team.

Exit codes:
  0 — allow (not a gated command, no closing keyword in the body, a fail-open
      degradation, or a valid override)
  2 — block (the read body carries a closing keyword bound to an issue reference)
"""

from __future__ import annotations

import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _framework_log import log_pretooluse_block  # noqa: E402
from _shell_parse import (  # noqa: E402
    find_gh_subcommand,
    iter_command_segments,
    resolve_invocation_cwd,
    strip_heredocs,
    tokenize,
    walk_flag_values,
)

#: Fail-open (#175): an inability to *evaluate* the body must never block. See docstring.
FAIL_OPEN = True

#: Env var that arms the deliberate, audited override. Non-empty value == confirmed.
_OVERRIDE_ENV_VAR = "PR_BODY_CLOSING_KEYWORD_EXCEPTION"

#: The `gh pr` actions that SET a body from a local string (create/edit). ready/merge
#: are intentionally excluded (they carry no new body) — see docstring.
_GATED_ACTIONS = ("create", "edit")

#: Flags carrying an inline body string, and flags carrying a path to a body file.
_BODY_INLINE_FLAGS = {"--body", "-b"}
_BODY_FILE_FLAGS = {"--body-file", "-F"}

#: GitHub's closing keywords (case-insensitive): close/closes/closed, fix/fixes/fixed,
#: resolve/resolves/resolved. `\b` anchoring means "prefix #1" / "disclosed #1" do NOT
#: match (the keyword must be a whole word).
_KEYWORDS = r"close[sd]?|fix(?:es|ed)?|resolve[sd]?"

#: keyword <sep> [owner/repo]#N. <sep> is either a colon (optionally spaced) OR at least
#: one space/tab — matching GitHub, which closes on "Fix #1" and "Fixes: #1" but not the
#: run-together "Fix#1". Restricted to [ \t] (not \s) so a keyword and a reference on
#: different lines never bind. The reference group also accepts a cross-repo `owner/repo#N`.
_CLOSING_RE = re.compile(
    r"\b(?P<kw>" + _KEYWORDS + r")"
    r"(?:[ \t]*:[ \t]*|[ \t]+)"
    r"(?P<ref>(?:[\w.-]+/[\w.-]+)?#(?P<num>\d+))\b",
    re.IGNORECASE,
)

#: Fence opener/closer: 3+ backticks or 3+ tildes at (optionally indented) line start.
_FENCE_RE = re.compile(r"^[ \t]*(?P<fence>`{3,}|~{3,})")
#: Inline code span: a run of N backticks, minimal content, closed by the same run.
_INLINE_CODE_RE = re.compile(r"(`+)(?:.+?)\1", re.DOTALL)


def mask_code(text: str) -> str:
    """Blank out markdown code (fenced blocks + inline spans), preserving line count.

    GitHub does not auto-close from inside code, so masking code before the keyword
    scan mirrors GitHub's parser and is the defense against the naive grep's
    backtick false positives (#304). Fenced blocks are tracked line-by-line (a fence
    closes on a same-character run at least as long as the opener); inline spans are
    replaced with spaces so surrounding prose keeps its offsets. Non-code text —
    including blockquotes — is returned untouched, so a blockquoted keyword (the #299
    failure mode) still matches.
    """
    out_lines: list[str] = []
    fence_char: str | None = None
    fence_len = 0
    for line in text.splitlines():
        m = _FENCE_RE.match(line)
        if fence_char is None:
            if m:
                fence = m.group("fence")
                fence_char, fence_len = fence[0], len(fence)
                out_lines.append("")  # drop the opening fence line itself
                continue
            out_lines.append(line)
        else:
            # Inside a fenced block: blank every line, and close on a matching fence.
            out_lines.append("")
            if m:
                fence = m.group("fence")
                if fence[0] == fence_char and len(fence) >= fence_len:
                    fence_char = None
                    fence_len = 0
    masked = "\n".join(out_lines)
    # Inline code spans on the surviving (non-fenced) prose.
    return _INLINE_CODE_RE.sub(lambda mo: " " * len(mo.group(0)), masked)


def find_closing_refs(body: str) -> list[tuple[str, str]]:
    """Return ordered, de-duplicated (keyword, reference) hits in *body*.

    A hit is a GitHub closing keyword bound to an issue reference in NON-code text.
    Backticked / code-fenced references and bare or prose references (no keyword)
    are excluded by construction. De-duplicated on the (lowercased) pair so a
    repeated phrase reports once.
    """
    masked = mask_code(body)
    seen: set[tuple[str, str]] = set()
    hits: list[tuple[str, str]] = []
    for match in _CLOSING_RE.finditer(masked):
        keyword = match.group("kw")
        ref = match.group("ref")
        key = (keyword.lower(), ref.lower())
        if key in seen:
            continue
        seen.add(key)
        hits.append((keyword, ref))
    return hits


def _gated_action(command: str) -> str | None:
    """Return 'create'/'edit' if any segment runs a gated `gh pr` verb, else None."""
    cleaned = strip_heredocs(command)
    tokens = tokenize(cleaned)
    if tokens is None:
        # shlex failure → fail-open: a body we cannot even tokenize is not evidence.
        return None
    for segment in iter_command_segments(tokens):
        result = find_gh_subcommand(segment)
        if result is None:
            continue
        _globals, rest = result
        if len(rest) >= 2 and rest[0] == "pr" and rest[1] in _GATED_ACTIONS:
            return rest[1]
    return None


def _read_body_file(path: str, cwd: str) -> str | None:
    """Read a --body-file path (resolved against *cwd*). None on any read failure."""
    if path == "-":
        return None  # stdin body: not observable in a PreToolUse gate → fail-open
    candidate = path if os.path.isabs(path) else os.path.join(cwd, path)
    try:
        with open(candidate, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except (OSError, ValueError):
        return None


def extract_body(command: str, cwd: str) -> str | None:
    """Concatenate every inline/file body value the gated command carries.

    Returns None when the command carries no body-setting flag (e.g. `--fill`, an
    interactive create): nothing local to scan → fail-open allow. A `--body-file`
    that cannot be read contributes nothing rather than aborting the whole scan.
    """
    tokens = tokenize(strip_heredocs(command))
    if tokens is None:
        return None
    parts: list[str] = []
    for value in walk_flag_values(tokens, _BODY_INLINE_FLAGS):
        parts.append(value)
    for path in walk_flag_values(tokens, _BODY_FILE_FLAGS):
        contents = _read_body_file(path, cwd)
        if contents is not None:
            parts.append(contents)
    if not parts:
        return None
    return "\n".join(parts)


def _override_rationale(input_data: dict) -> str:
    """The override rationale, from the tool's env then the process env. '' if unset."""
    raw = (input_data.get("env", {}) or {}).get(_OVERRIDE_ENV_VAR)
    if raw is None:
        raw = os.environ.get(_OVERRIDE_ENV_VAR, "")
    return (raw or "").strip()


def _block_reason(action: str, hits: list[tuple[str, str]]) -> str:
    """Human reason: what will silently close, and the four ways to make it not."""
    bullets = "\n".join(f"  - `{kw} {ref}`  → would auto-close {ref} on merge" for kw, ref in hits)
    first_ref = hits[0][1]
    return (
        f"BLOCKED: this `gh pr {action}` body contains a GitHub closing keyword bound to an "
        "issue reference. GitHub auto-closes such an issue THE MOMENT THE PR MERGES, leaving no "
        "trace in `git log` — even if the PR implements nothing for it (this is exactly how PR "
        "#299 silently closed #296).\n\n"
        f"Closing keyword(s) found in the PR body:\n{bullets}\n\n"
        "Under this team's charter a closing keyword belongs in the COMMIT MESSAGE (visible and "
        "greppable in `git log`), never in the PR body. Fix by one of:\n"
        f"  1. If the PR really closes it, put `Closes {first_ref}` in the COMMIT MESSAGE and drop "
        "it from the body.\n"
        f"  2. If you are only referencing/quoting it, render it non-keyword: backtick it "
        f"(`` `{first_ref}` ``), or write \"Address {first_ref}\" / \"per {first_ref}\".\n"
        "  3. Move the phrase inside a ``` code fence ``` (GitHub does not auto-close from code).\n"
        f"  4. Deliberate exception (audited): rerun with "
        f"`{_OVERRIDE_ENV_VAR}=\"<rationale>\" gh pr {action} ...`."
    )


def check(input_data: dict) -> dict | None:
    """Dispatcher entry. None => allow; block dict => deny (exit 2)."""
    if input_data.get("tool_name") != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return None

    action = _gated_action(command)
    if action is None:
        return None

    cwd = resolve_invocation_cwd(input_data)
    body = extract_body(command, cwd)
    if not body:
        return None  # no local body to scan → fail-open allow

    hits = find_closing_refs(body)
    if not hits:
        return None

    if _override_rationale(input_data):
        return None  # deliberate, audited exception

    reason = _block_reason(action, hits)
    log_pretooluse_block("validate_pr_body", command, reason, input_data=input_data)
    return {"decision": "block", "reason": reason}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    result = check(input_data)
    if result is None:
        sys.exit(0)
    print(json.dumps(result))
    if result.get("decision") == "block":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
