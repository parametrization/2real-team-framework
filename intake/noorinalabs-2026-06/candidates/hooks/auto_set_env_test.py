#!/usr/bin/env python3
"""PreToolUse hook: Auto-set ENVIRONMENT=test before pytest/make test.

Ensures ENVIRONMENT=test is present in the environment for any pytest or
`make test` command. If not already set, blocks with a corrected command
that prepends ENVIRONMENT=test to the test-bearing segment(s).

Input Language
==============

Fires on:
    PreToolUse Bash

Matches (blocks if ENVIRONMENT=test missing on the test segment):
    Any Bash command containing a real test-runner invocation detected
    by the regexes `\\bpytest\\b` or `\\bmake\\s+test\\b`. The command is
    split on shell separators (`&&`, `||`, `;`, `|`, `\\n`) into segments;
    each test-bearing segment is checked independently for a leading
    `ENVIRONMENT=test` env-block. An unescaped newline acts as a statement
    terminator equivalent to `;` (#537).

    Typical matched forms:
        pytest tests/
        uv run pytest
        python -m pytest
        make test
        DEBUG=1 pytest tests/                  (env prefix preserved)
        cd /path && pytest tests/              (chain — env must be on pytest segment)
        pytest tests/ && pytest tests-other/   (chain — env required on BOTH segments)
        (ENVIRONMENT=test pytest tests/)       (subshell — env recognised inside parens)

Does NOT match (short-circuit skips — #114 fix):
    1. Command whose effective argv[0] is `gh` — `gh` is a GitHub API
       client, never a test runner. `ENVIRONMENT=test gh pr comment ...`
       is nonsensical. Skip even if pytest/make-test text appears inside
       the command (almost always inside --body / --title content).
    2. Command containing a `--body` or `--body-file` flag — structured
       body content almost always contains user-supplied text that may
       mention pytest or `make test` without invoking them. This skip is
       intentionally broad: a non-gh tool like
       `some-tool --body "$(cat pytest.txt)"` is also skipped. The cost
       of a rare false negative on an exotic non-gh tool is lower than
       the cost of blocking every review / issue / comment that
       references pytest.

Both short-circuits run BEFORE the pytest/make-test segment scan and
apply to the WHOLE command (not per-segment).

Detection order:
    1. Strip leading `VAR=value` tokens from the command for argv[0] check.
    2. If the next token is `gh`, ALLOW (return None).
    3. If the command contains `--body` or `--body-file`, ALLOW.
    4. Split on `&&`/`||`/`;`/`|`/`\\n` into segments using a quote-aware
       state-machine scanner — separators inside `'...'`, `"..."`, or
       `\\`-escaped positions are NOT recognised. (A `\\`-then-newline
       line-continuation is consumed by `in_escape` and so does NOT split.)
    5. For each segment containing `\\bpytest\\b` or `\\bmake\\s+test\\b`,
       require `\\bENVIRONMENT=test\\b` in that segment's leading env-block
       (subshell-aware: a segment that opens with `(` peeks inside the
       parens for the env-block); else BLOCK with a per-segment-rewritten
       suggestion. When the test segment is inside a shell control-flow
       construct (`for|while|until|if ... ; do pytest ...`) where
       splicing would produce invalid shell, HARD BLOCK with an
       operator-readable diagnostic that names the construct and offers
       both inline-env (`do ENVIRONMENT=test pytest`) and pull-out
       (`ENVIRONMENT=test pytest a b`) alternatives. Allow-with-log
       would silently bypass the protection (#420 prod-data-wipe class),
       so we trade UX friction for safety.

Per-segment env-block check (the #476 silent-bypass fix):
    `ENVIRONMENT=test cd /x && pytest tests/` does NOT pass — even though
    the env var appears in the command, it lives on the `cd` segment, not
    on the pytest segment. Shell semantics apply env assignments only to
    the immediately-following program in the same segment.

Shell-syntax-awareness scope (#478):
    The state-machine split handles single quotes, double quotes, and
    backslash-escapes at the top level. It does NOT recurse into
    `$(...)` or backtick command substitutions — separators inside
    `$(... && ...)` will still split, which is acceptable because the
    inner command would only fire if the substitution were executed and
    the segment scan would catch any pytest invocation regardless.
    Subshell-recognition is one-deep: `(((pytest)))` is correctly
    parsed; nested-with-other-content edge cases fall through to the
    control-flow HARD BLOCK path with manual-edit diagnostic rather
    than emit a mangled suggestion.

Decision on subshell + control-flow coverage (#478):
    Both are handled in this PR, NOT punted. Once the state machine is
    in place for quote-awareness (case #1), subshell detection is a
    leading-`(` peek and control-flow detection is a sibling-segment
    keyword check — both cheap. Splitting into separate commits would
    risk leaving the hook in a half-fixed state where mangled
    suggestions still ship for cases #2 and #3.

Exit codes:
    0 — allow (not a Bash tool, or skip condition met, or every test
        segment already has ENVIRONMENT=test in its leading env-block)
    2 — block (at least one test segment is missing ENVIRONMENT=test,
        whether splice-able with a corrected suggestion or inside a
        control-flow body that requires a manual edit per the diagnostic)

Enforcement artifact for: noorinalabs/noorinalabs-main#114, #476, #478
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annunaki_log import log_pretooluse_block  # noqa: E402

# Matches a leading `VAR=value` token (simple unquoted value).
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+")

# `--body` or `--body-file` as a standalone flag. The trailing lookahead
# prevents matching `--body-foo` but still matches both `--body x`,
# `--body=x`, and `--body-file path`.
_BODY_FLAG = re.compile(r"(?<![\w-])--body(?:-file)?(?=[\s=]|$)")

# Test-runner detection: pytest OR `make test`.
_TEST_RUNNER = re.compile(r"\bpytest\b|\bmake\s+test\b")

# Heredoc operator: `<<` (optionally `<<-`) followed by an optionally
# quoted delimiter word. The delimiter is captured so we can find its
# terminating line. Examples matched:
#     <<EOF        <<-EOF        << EOF
#     <<'EOF'      <<"EOF"       <<-'EOF'
# We do NOT match `<<<` (here-string) — that has no body lines, its
# operand is on the same line and is handled by ordinary quote/word
# scanning. The negative lookahead `(?!<)` after the second `<` excludes
# the here-string form.
_HEREDOC_OPEN = re.compile(r"<<(?!<)-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")

# The literal env-var we require.
_ENV_TOKEN = re.compile(r"\bENVIRONMENT=test\b")

# Shell control-flow keywords that appear as standalone tokens between
# segment separators. When a test-bearing segment is bracketed by these,
# splicing `ENVIRONMENT=test` between the separator and the next program
# produces invalid shell (e.g. `for f in a; ENVIRONMENT=test do pytest`).
# Used by the bail-with-diagnostic path in `_rewrite_command` (#478).
_CONTROL_FLOW_OPENERS = frozenset({"for", "while", "until", "if", "case"})
_CONTROL_FLOW_BODY_KEYWORDS = frozenset({"do", "done", "then", "else", "elif", "fi", "esac", "in"})


def _strip_leading_env(command: str) -> str:
    """Remove leading `VAR=value ` assignments, return the remainder."""
    while True:
        m = _ENV_ASSIGN.match(command)
        if not m:
            return command
        command = command[m.end() :]


def _is_gh_invocation(command: str) -> bool:
    """True if the effective argv[0] (after env assignments) is `gh`.

    Also handles a single leading `env` wrapper (#181):
        env FOO=bar gh pr comment ...
        env FOO=1 BAR=2 gh pr comment ...
        FOO=1 env BAR=2 gh pr comment ...   (env after shell VAR prefix)

    Does NOT recurse into `env -i`, `env -u`, `env --` flag forms (out of
    scope per #181 — `env -i` clears the inherited environment which is an
    operator-explicit "I want a clean slate" signal; treating it the same
    as the bare `env` wrapper would let an `env -i gh ...` shape mask a
    pytest invocation hidden in its later args). The flag-form is rare in
    operator commands and the `--body` short-circuit covers the common gh
    case regardless.
    """
    stripped = _strip_leading_env(command).lstrip()
    if not stripped:
        return False
    token = stripped.split(None, 1)[0]
    if token == "gh":
        return True
    if token == "env":
        # Peek at the next token. If it's a flag (starts with `-`), bail —
        # we don't recurse into `env -i` / `env -u` / `env --` shapes.
        remainder = stripped[len("env") :].lstrip()
        next_token = remainder.split(None, 1)[0] if remainder else ""
        if next_token.startswith("-"):
            return False
        # Strip env's own leading VAR=val assignments, then re-check argv[0].
        after_env = _strip_leading_env(remainder).lstrip()
        if not after_env:
            return False
        return after_env.split(None, 1)[0] == "gh"
    return False


def _has_body_flag(command: str) -> bool:
    """True if the command contains a --body or --body-file flag."""
    return bool(_BODY_FLAG.search(command))


def _split_segments(command: str) -> list[str]:
    """Split command on `&&`/`||`/`;`/`|`/`\\n`, preserving separators as
    alternating list entries: [seg0, sep0, seg1, sep1, ..., segN].

    Quote-aware (#478): separators inside `'...'`, `"..."`, or
    `\\`-escaped positions are NOT recognised. The previous regex-only
    implementation tripped on `git log --grep='fix && pytest'` by
    treating the `&&` inside the grep pattern as a real separator and
    classifying the quoted `pytest` token as a test-runner invocation.

    The result always has odd length: segments at even indices, separators
    at odd indices. A command with no separators returns a single-element
    list [command]. Surrounding whitespace around separators is preserved
    in the separator entry so segments + separators concat back to the
    original command byte-for-byte.

    State machine:
        - quote_char: None | "'" | '"'  (current quoting context)
        - in_escape:  True after a `\\` outside single quotes (POSIX rule)
        - Separators only fire when quote_char is None.
        - Inside `'...'` backslashes are literal (POSIX); inside `"..."`
          they escape `$` `` ` `` `"` `\\`. We treat `\\` as a generic
          escape outside single quotes — close enough for the hook's
          purpose, which is to avoid mis-splitting on quoted operators.
    """
    parts: list[str] = []
    buf: list[str] = []
    quote_char: str | None = None
    in_escape = False
    i = 0
    n = len(command)
    while i < n:
        ch = command[i]
        if in_escape:
            buf.append(ch)
            in_escape = False
            i += 1
            continue
        if quote_char is not None:
            if ch == "\\" and quote_char == '"':
                buf.append(ch)
                in_escape = True
                i += 1
                continue
            buf.append(ch)
            if ch == quote_char:
                quote_char = None
            i += 1
            continue
        # Unquoted context.
        if ch == "\\":
            buf.append(ch)
            in_escape = True
            i += 1
            continue
        if ch in ("'", '"'):
            buf.append(ch)
            quote_char = ch
            i += 1
            continue
        # Separator detection — only fires outside quotes.
        sep = _match_separator_at(command, i)
        if sep is not None:
            # Look back over the buffer to find the trailing whitespace
            # that belongs to the separator group, mirroring the old
            # regex `\s*(...)\s*` capture.
            seg = "".join(buf)
            trailing_ws_len = len(seg) - len(seg.rstrip())
            parts.append(seg[: len(seg) - trailing_ws_len])
            ws_before = seg[len(seg) - trailing_ws_len :]
            j = i + len(sep)
            ws_after_len = 0
            while j < n and command[j] in (" ", "\t"):
                ws_after_len += 1
                j += 1
            parts.append(ws_before + sep + command[i + len(sep) : i + len(sep) + ws_after_len])
            buf = []
            i = j
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _match_separator_at(command: str, i: int) -> str | None:
    """Return the longest separator token at position `i`, or None.

    Order is significant: `&&` and `||` must be matched before single
    `&`/`|` would (we don't recognise bare `&`, but `||` must match
    before `|`).
    """
    if command.startswith("&&", i):
        return "&&"
    if command.startswith("||", i):
        return "||"
    if command[i] == ";":
        return ";"
    if command[i] == "|":
        return "|"
    if command[i] == "\n":
        return "\n"
    return None


def _segment_has_env_in_leading_block(segment: str) -> bool:
    """True if `ENVIRONMENT=test` is in the LEADING env-block of segment.

    The leading env-block is the sequence of `VAR=value ` tokens at the
    start of the segment (after stripping surrounding whitespace). This
    is the only position where a shell env assignment applies to the
    segment's program.

    Subshell-aware (#478): if the segment opens with `(`, peek inside
    the parens at the leading env-block of the subshell contents. This
    handles `(ENVIRONMENT=test pytest tests/)` — the env is on the
    correct (sub-)segment's program. We strip the leading `(` and any
    interior whitespace before re-checking; we do NOT need to find the
    closing `)` because the env-block check only cares about leading
    tokens. Nested subshells (`((ENVIRONMENT=test pytest))`) are handled
    by recursion.
    """
    stripped = segment.lstrip()
    if stripped.startswith("("):
        # Strip one layer of subshell parens + interior whitespace, then
        # recurse. This lets the env-block check see through one or more
        # nested subshells uniformly.
        return _segment_has_env_in_leading_block(stripped[1:])
    consumed = stripped[: len(stripped) - len(_strip_leading_env(stripped))]
    return bool(_ENV_TOKEN.search(consumed))


def _is_test_segment(segment: str) -> bool:
    """True if segment contains pytest or `make test` as a real invocation.

    Quote-aware (#478): a `pytest` token inside `'...'` or `"..."`
    quoting is NOT a test-runner invocation — it's argument data. The
    `_split_segments` quote-aware tokenizer already protects against
    quoted separators triggering bogus segment splits, but a single
    segment can still contain a quoted `pytest` substring (e.g.
    `git log --grep='fix pytest'` with no separators at all). This
    function strips quoted regions before applying the test-runner
    regex.
    """
    return bool(_TEST_RUNNER.search(_strip_quoted_regions(segment)))


def _strip_quoted_regions(s: str) -> str:
    """Return `s` with single-quoted and double-quoted regions replaced
    by empty strings. Backslash-escapes outside single quotes consume
    their following char.

    Used by `_is_test_segment` to avoid false-positive matches on
    `pytest` / `make test` text that appears inside argument quoting.
    """
    out: list[str] = []
    quote_char: str | None = None
    in_escape = False
    for ch in s:
        if in_escape:
            in_escape = False
            if quote_char is None:
                out.append(ch)
            continue
        if quote_char is not None:
            if ch == "\\" and quote_char == '"':
                in_escape = True
                continue
            if ch == quote_char:
                quote_char = None
            continue
        if ch == "\\":
            in_escape = True
            out.append(ch)
            continue
        if ch in ("'", '"'):
            quote_char = ch
            continue
        out.append(ch)
    return "".join(out)


def _strip_heredoc_bodies(command: str) -> str:
    """Return `command` with heredoc *body* characters blanked to spaces,
    preserving every newline and the total length so the result is a
    positional mirror of the original.

    Heredoc bodies are command *input data* (a commit message, an API
    request payload), never a program invocation. The token `pytest` or
    `make test` inside a heredoc body is therefore not a test runner —
    blanking the body before the test-runner scan prevents the #564
    false-positive (e.g. `git commit -F- <<'EOF'\\n...make test...\\nEOF`
    or a `--input` payload built with a heredoc). It is the heredoc-body
    sibling of `_strip_quoted_regions` (quoted-arg data) and the same
    safety tradeoff: data passed to a command is not the command.

    Length- and newline-preserving so callers can run the existing
    quote-aware `_split_segments` on the blanked view and get segment
    boundaries identical to the original command — the body lines become
    runs of spaces between unchanged separators, so a real test
    invocation OUTSIDE any heredoc still lands in its own segment at the
    same index and can be rewritten against the original text.

    Scope notes:
        - The opening operator line (everything up to and including the
          newline that ends the line bearing `<<DELIM`) is preserved, so
          a real `pytest` on the *same line as* a heredoc redirect is not
          masked.
        - Quoted (`<<'EOF'`) and unquoted (`<<EOF`) delimiters are both
          handled; the closing line must equal the delimiter exactly
          after optional leading tabs (the `<<-` indent-strip form).
        - A heredoc opened but never closed (no terminating delimiter
          line) blanks to end-of-string — matching shell behaviour where
          the rest of the input is the body.
        - Multiple heredocs and heredocs not at end-of-command are
          handled by resuming the scan after each closing delimiter.
    """
    lines = command.split("\n")
    out_lines: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        out_lines.append(line)
        # Find the LAST heredoc operator on this line (a line may open
        # several: `cmd <<A <<B`; bash collects bodies in order, but for
        # detection we only need to know a body region begins — using the
        # last delimiter keeps the close-scan simple and conservative).
        matches = list(_HEREDOC_OPEN.finditer(line))
        if not matches:
            i += 1
            continue
        delimiter = matches[-1].group(2)
        # Blank body lines (preserving each as an all-space line of equal
        # length) until we hit the closing delimiter line or run out.
        i += 1
        while i < n:
            body = lines[i]
            # `<<-` strips leading TABS from the closing delimiter; accept
            # the closer with optional leading tabs regardless, since a
            # plain `<<` body line equal to the delimiter also closes.
            if body.lstrip("\t") == delimiter:
                out_lines.append(body)
                i += 1
                break
            out_lines.append(" " * len(body))
            i += 1
    return "\n".join(out_lines)


def _prepend_env_to_segment(segment: str) -> str:
    """Return segment with `ENVIRONMENT=test ` inserted before its first
    real (non-env-assignment, non-whitespace) token.

    Preserves any existing leading env-block (e.g. `DEBUG=1 pytest` →
    `DEBUG=1 ENVIRONMENT=test pytest`) and preserves the segment's
    leading whitespace exactly so splicing back into the chain doesn't
    re-shape the original command's formatting.

    Subshell-aware (#478): if segment opens with `(`, the env is
    inserted INSIDE the parens (after the opening `(` and any interior
    whitespace). This produces `(ENVIRONMENT=test pytest)` rather than
    the syntactically-incorrect `ENVIRONMENT=test (pytest)`.
    """
    leading_ws_len = len(segment) - len(segment.lstrip())
    leading_ws = segment[:leading_ws_len]
    body = segment[leading_ws_len:]
    if body.startswith("("):
        # Insert inside the subshell. Find the run of whitespace after
        # the `(` so the env sits flush against the first real token.
        inner = body[1:]
        inner_ws_len = len(inner) - len(inner.lstrip())
        inner_after_ws = inner[inner_ws_len:]
        # Recurse the env-prepend onto the inner so DEBUG=1 etc. is
        # preserved inside the subshell.
        inner_with_env = _prepend_env_to_segment(inner_after_ws)
        return f"{leading_ws}({inner[:inner_ws_len]}{inner_with_env}"
    body_after_env = _strip_leading_env(body)
    env_block = body[: len(body) - len(body_after_env)]
    return f"{leading_ws}{env_block}ENVIRONMENT=test {body_after_env}"


def _is_control_flow_bracketed(parts: list[str], idx: int) -> bool:
    """True if the segment at `parts[idx]` is part of a shell control-
    flow construct where splicing `ENVIRONMENT=test` at the segment's
    leading position would produce invalid shell.

    Three invalid shapes we're guarding against:

    1. **Body-keyword leading segment** —
       `for f in a b; do pytest $f; done`
       Splicing onto the `do pytest $f` segment yields
       `; ENVIRONMENT=test do pytest $f` which is invalid (the `do`
       keyword must immediately follow the separator).

    2. **Opener-keyword leading segment** (this segment) —
       `while pytest --quick; do echo ok; done`
       The leading token is `while` (a control-flow opener); env
       assignments can only precede simple commands, not compound
       commands. Splicing yields `ENVIRONMENT=test while pytest ...`
       which is invalid.

    3. **Body-segment of a prior opener** —
       `for f in a b; do pytest $f; done`
       The test segment (`do pytest $f`) follows an opener segment
       (`for f in a b`). Even after stripping the `do` keyword the
       splice can't be placed safely without re-tokenising the body.

    Detection:
       - Segment-leading token is a body keyword (`do`/`then`/...) → bail
       - Segment-leading token is an opener keyword (`for`/`while`/...) → bail
       - A PRIOR segment leads with an opener and no closer (`done`/`fi`/...)
         has intervened → segment is inside a body → bail

    Per the hook docstring decision (#478), control-flow detection
    triggers a HARD BLOCK with operator-readable diagnostic — never an
    allow-with-log. Allow-with-log would silently bypass the very
    protection this hook exists for (the #420 prod-data-wipe class).
    The diagnostic names the construct family and offers both inline-env
    and pull-out alternatives; operator picks the right shape and
    re-issues the command. The opener-segment case (#2) could in
    principle be handled by splicing inside the compound (`while
    ENVIRONMENT=test pytest --quick`) but that requires a token-level
    rewrite — out of scope for this PR.
    """
    seg = parts[idx].lstrip()
    first_token = seg.split(None, 1)[0] if seg else ""
    if first_token in _CONTROL_FLOW_BODY_KEYWORDS:
        return True
    if first_token in _CONTROL_FLOW_OPENERS:
        return True
    # Look backwards through prior segments for a control-flow opener.
    # If we find one before another opener-or-body-closing keyword
    # interrupts the run, treat the current segment as inside its body.
    for j in range(idx - 2, -1, -2):
        prior = parts[j].lstrip()
        prior_first = prior.split(None, 1)[0] if prior else ""
        if prior_first in _CONTROL_FLOW_OPENERS:
            return True
        if prior_first in ("done", "fi", "esac"):
            # Closer of a previous construct — current segment is OUTSIDE.
            return False
    return False


def _rewrite_command(command: str) -> tuple[str, list[int]]:
    """Splice ENVIRONMENT=test onto each test-bearing segment that lacks it.

    Returns (rewritten_command, control_flow_bail_indices). The bail
    indices are segment positions where the test segment is inside a
    control-flow body — those are NOT rewritten (the splice would
    produce invalid shell), and the caller uses the list to emit the
    bail-with-diagnostic ALLOW path instead of a BLOCK.

    Heredoc-aware (#564): test-segment detection and control-flow
    bracketing run against a heredoc-body-blanked *view* of the command
    (same length/boundaries as the original), so a `pytest` token inside
    a heredoc body is never treated as a runner to splice onto. The
    splice itself rewrites the ORIGINAL segment text — the view is a
    detection mask only.
    """
    parts = _split_segments(command)
    parts_view = _split_segments(_strip_heredoc_bodies(command))
    bail_indices: list[int] = []
    for i in range(0, len(parts), 2):
        if not _is_test_segment(parts_view[i]):
            continue
        if _segment_has_env_in_leading_block(parts[i]):
            continue
        if _is_control_flow_bracketed(parts_view, i):
            bail_indices.append(i)
            continue
        parts[i] = _prepend_env_to_segment(parts[i])
    return "".join(parts), bail_indices


def check(input_data: dict) -> dict | None:
    """Check for ENVIRONMENT=test on test commands.

    Returns result dict if blocking, None if allowed.
    """
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    # Short-circuit 1: gh subcommands are never test runners.
    if _is_gh_invocation(command):
        return None

    # Short-circuit 2: --body/--body-file flag implies structured content.
    if _has_body_flag(command):
        return None

    # Detection view: blank heredoc bodies (command *input data*, never a
    # program invocation) before the test-runner scan so a `pytest` /
    # `make test` token inside a commit-message or --input heredoc does
    # not register as a test segment (#564). The view is length- and
    # newline-preserving, so its segment boundaries are identical to the
    # original command's — `parts_view[i]` and `parts[i]` cover the same
    # byte range. We detect on the view but check env-blocks / rewrite on
    # the original (where the real ENVIRONMENT=test, if any, lives).
    detection_view = _strip_heredoc_bodies(command)
    parts = _split_segments(command)
    parts_view = _split_segments(detection_view)
    test_segment_indices = [
        i for i in range(0, len(parts_view), 2) if _is_test_segment(parts_view[i])
    ]
    if not test_segment_indices:
        return None

    # Per-segment env-block + control-flow + subshell evaluation.
    # Three buckets:
    #   - satisfied: env-prefixed, no action needed
    #   - control-flow: can't splice cleanly → HARD BLOCK + diagnostic
    #     (safety direction: never silently allow a pytest run without
    #     ENVIRONMENT=test even when our rewriter can't produce a valid
    #     suggestion — #478 hard-block discipline. Allow-with-log would
    #     bypass the very protection this hook exists for, exactly the
    #     #420 prod-data-wipe class of failure.)
    #   - missing-env splice-able: BLOCK with corrected-command suggestion
    needs_splice_block = False
    saw_control_flow_block = False
    for i in test_segment_indices:
        # env-block lives in the ORIGINAL segment (a real ENVIRONMENT=test
        # prefix); control-flow bracketing is detected on the heredoc-
        # blanked VIEW so keywords inside a heredoc body don't count.
        if _segment_has_env_in_leading_block(parts[i]):
            continue
        if _is_control_flow_bracketed(parts_view, i):
            saw_control_flow_block = True
            continue
        needs_splice_block = True
    if needs_splice_block:
        rewritten, _ = _rewrite_command(command)
        # If the same command also has a control-flow segment we
        # couldn't rewrite cleanly, surface BOTH so the operator
        # understands the suggestion may not cover every test segment.
        reason = (
            "ENVIRONMENT=test is required for test commands but was not found in "
            "the leading env-block of each test-bearing segment. Shell env "
            "assignments only apply to the immediately-following program in the "
            "same segment, so chains like `cd /x && pytest` need the env on the "
            "pytest segment, not at the start of the whole command. Suggested "
            "command:\n"
            f"  {rewritten}"
        )
        if saw_control_flow_block:
            reason += (
                "\n\nNote: at least one pytest invocation is inside a shell "
                "control-flow construct (for/while/until/if) that "
                "auto_set_env_test cannot safely rewrite. Add ENVIRONMENT=test "
                "manually inside the body for those segments."
            )
        return {"decision": "block", "reason": reason}
    if saw_control_flow_block:
        # Every offending test segment is inside a control-flow body.
        # HARD BLOCK with operator-readable diagnostic — splicing would
        # produce invalid shell, but allowing would silently bypass the
        # hook's purpose (#420-class silent-prod-write). Trade UX
        # friction for safety. Diagnostic names the construct family
        # and offers both inline-env and pull-out alternatives.
        return {
            "decision": "block",
            "reason": (
                "pytest detected inside a shell control-flow body "
                "(for/while/until/if) that auto_set_env_test cannot safely "
                "rewrite — splicing ENVIRONMENT=test between the separator "
                "and a control-flow keyword would produce invalid shell. "
                "Add ENVIRONMENT=test manually inside the body. Example:\n"
                "  for f in a b; do ENVIRONMENT=test pytest $f; done\n"
                "Or pull the loop variable outside:\n"
                "  ENVIRONMENT=test pytest a b\n"
                f"Original command: {command}"
            ),
        }
    return None


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result and result.get("decision") == "block":
        print(json.dumps(result))
        command = input_data.get("tool_input", {}).get("command", "")
        log_pretooluse_block(
            "auto_set_env_test",
            command,
            result["reason"],
            tool_name="Bash",
        )
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
