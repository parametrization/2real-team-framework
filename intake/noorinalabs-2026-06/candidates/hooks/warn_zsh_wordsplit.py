#!/usr/bin/env python3
"""PreToolUse hook: advisory warning for bash-ism word-splitting under zsh.

Background
==========

The dev environment's interactive shell AND the agent Bash tool run under
**zsh**, not bash. Several bash-only idioms that rely on word-splitting of
unquoted scalar variables work in bash but silently misbehave under zsh.
Prose guidance in ``feedback_zsh_shell_environment`` (memory) and
``ontology/conventions.md`` § Shell environment (zsh) has not been sufficient
to prevent recurrence — this is the memory→hook promotion for that feedback
class (per [[feedback_enforcement_hierarchy]]: hook > skill > charter).

What it flags
=============

1. ``set -- $name``
   Unquoted plain scalar in positional-parameter reset. Under bash the shell
   word-splits ``$name`` on IFS; under zsh it is treated as a single field.
   zsh-safe alternative: populate an explicit array, e.g.
   ``parts=("${(@s: :)name}")`` or use a ``while IFS= read -r`` loop.

2. ``for VAR in $name`` (unquoted plain scalar)
   Same word-splitting divergence. NOT flagged: ``"$name"``, ``$@`` / ``"$@"``,
   glob patterns (``*.py``), command substitutions (``$(...)`` / backticks), or
   brace/seq expansions (``{1..5}``, ``a b c`` literals).
   zsh-safe alternative: ``while IFS= read -r VAR; do …; done <<< "$name"``

3. ``${!var}`` / ``${!arr[@]}`` / ``${!arr[*]}``
   Bash indirect expansion / array-keys expansion. zsh equivalents:
   ``${(P)var}`` (indirect) and ``${(k)arr}`` (keys).

4. ``mapfile`` / ``readarray``
   Bash-only builtins absent in zsh.
   zsh-safe alternative: ``while IFS= read -r line; do arr+=("$line"); done``

What it does NOT flag (false-positive guards)
=============================================

- Quoted forms: ``set -- "$@"``, ``for x in "$list"``, ``"${arr[@]}"``
- ``for x in *.py``, ``for x in $(ls)``, ``for x in {1..5}``, ``for x in a b c``
- Path/glob/concat prefixes where ``$NAME`` is only PART of a word:
  ``for f in $HOME/*.py``, ``for w in $REPO_ROOT/.claude/*/``,
  ``for f in $dir/known_hosts``, ``set -- $dir/*.txt`` — in zsh ``$VAR/...`` is
  a single scalar path component (no word-splitting), so it is SAFE (#879). The
  scalar must be a STANDALONE word to fire.
- Any occurrence inside a heredoc body (stripped before scanning)
- ``declare -A`` / ``typeset`` — zsh supports these; NOT flagged

Block vs. warn (deliberate decision — #879)
==========================================

This is an ADVISORY (warn) hook. Word-splitting reliance is sometimes
intentional and a hard block over every match would create false-positive
friction (mirrors warn_pipe_mask_rc's deliberate warn-not-block stance).
The dispatcher returns ``{"decision": "allow", "systemMessage": ...}`` for any
non-blocking hook result — returning ``{"systemMessage": ...}`` (no decision
key) is treated identically (decision defaults to allow).

Input Language
==============
  Fires on:      PreToolUse Bash
  Matches:       bash-ism word-splitting constructs in command position
  Does NOT match: non-Bash tool; constructs inside heredoc bodies; false-
                  positive cases enumerated above
  Action:        advisory systemMessage — never blocks

Exit codes:
  0 — always (advisory; never blocks)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Ensure the hooks directory is importable when run standalone (the dispatcher
# already puts it on sys.path; this covers ``python3 warn_zsh_wordsplit.py``).
_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from _shell_parse import strip_heredocs  # noqa: E402

# ---------------------------------------------------------------------------
# Pattern 3: ${!var} / ${!arr[@]} / ${!arr[*]} — bash indirect/keys expansion
# ---------------------------------------------------------------------------
# Matches inside a raw command string (before tokenizing) because shlex strips
# the braces — we must scan the original text. We intentionally look for the
# ``${!`` sigil; ``${#`` (length) is NOT indirect and is fine under zsh.
_INDIRECT_EXPANSION_RE = re.compile(r"\$\{!")

# Pattern 4: mapfile / readarray as a standalone command (word-boundary check)
_MAPFILE_RE = re.compile(r"\b(mapfile|readarray)\b")

# ---------------------------------------------------------------------------
# Scalar reference + standalone-word boundary (#879 FP fix).
#
# The canonical gotcha is a BARE scalar reference standing as its OWN word in
# the list: ``for x in $list`` / ``set -- $spec``. The fire condition is
# therefore: ``$NAME`` (or ``${NAME}``) immediately followed by a WORD
# BOUNDARY — end-of-string, whitespace, or one of ``; | & )`` / backtick.
#
# If the char immediately after the identifier is anything else
# (``/ . * ? [ ] { } : @ % = + ,`` …), the ``$NAME`` is only a PREFIX of a
# compound word (a path/glob/concatenation like ``$dir/*.py`` or
# ``$HOME/.config``). In zsh ``$VAR/...`` is a single scalar path component —
# NO word-splitting — so it is SAFE and must NOT fire. This silences the
# path/glob-prefix false positives reported on PR #880 while keeping the bare
# ``$list`` / ``$a $b $c`` cases firing.
#
# ``${NAME}`` (braced, no subscript/operator) is the same standalone scalar and
# is matched; ``${arr[@]}`` / ``${!x}`` / ``$@`` / ``$*`` / ``$(...)`` are NOT
# (the alternation only accepts a bare identifier, with or without braces, and
# the lexer/array forms fail the boundary or the identifier class).
# ---------------------------------------------------------------------------
# A bare scalar reference: ``$NAME`` or ``${NAME}`` (identifier only — no
# subscript, no ``!``/``#`` operator, no ``@``/``*``).
_SCALAR_REF = r"\$(?:\{[A-Za-z_]\w*\}|[A-Za-z_]\w*)"

# Standalone-word boundary lookahead: the scalar ref must be the WHOLE word.
# ``\s`` already covers space/tab/newline; the explicit set adds the shell
# control/grouping operators that also terminate a word.
_STANDALONE_BOUNDARY = r"(?=$|[\s;|&)`])"

# Pattern 2: ``for VAR in $scalar`` (standalone bare scalar in the list).
_FOR_UNQUOTED_RE = re.compile(
    r"\bfor\s+\w+\s+in\s+"  # for VAR in
    + _SCALAR_REF  # $NAME or ${NAME}
    + _STANDALONE_BOUNDARY  # … as its own word
)

# Pattern 1: ``set -- $scalar`` (standalone bare scalar after ``--``).
# Quoted forms (``set -- "$@"`` / ``set -- "$scalar"``) never match because the
# ``"`` sits between ``--`` and the ``$``, breaking the ``\s+\$`` adjacency.
_SET_DASHDASH_RE = re.compile(
    r"\bset\s+--\s+"  # set --
    + _SCALAR_REF  # $NAME or ${NAME}
    + _STANDALONE_BOUNDARY  # … as its own word
)


def _has_indirect_expansion(command: str) -> bool:
    """Return True if the command contains bash-only ``${!...}`` expansion."""
    return bool(_INDIRECT_EXPANSION_RE.search(command))


def _has_mapfile(command: str) -> bool:
    """Return True if the command calls ``mapfile`` or ``readarray``."""
    return bool(_MAPFILE_RE.search(command))


def _scan_for_wordsplit(command: str) -> list[tuple[str, str]]:
    """Scan ``command`` for patterns 1 & 2 using the regex pre-filter.

    Returns a list of ``(pattern_id, matched_text)`` pairs. The caller decides
    how to compose the advisory.

    Scans the heredoc-stripped string. The match is fully decided by the
    regexes themselves: ``_SCALAR_REF`` accepts only a bare ``$NAME`` /
    ``${NAME}`` identifier (so ``$@`` / ``$*`` / ``${arr[@]}`` / ``$(...)`` are
    excluded by construction), and ``_STANDALONE_BOUNDARY`` requires the scalar
    to be its OWN word (so path/glob prefixes like ``$dir/*.py`` are excluded,
    #879 FP fix). No secondary safe-form filter is needed — the previous
    ``_SAFE_DOLLAR_FORMS_RE`` guard was unreachable once the regex enforced both
    constraints, so it was removed.
    """
    findings: list[tuple[str, str]] = []

    # Pattern 1: set -- $scalar
    for m in _SET_DASHDASH_RE.finditer(command):
        findings.append(("set_dashdash", m.group(0).strip()))

    # Pattern 2: for VAR in $scalar
    for m in _FOR_UNQUOTED_RE.finditer(command):
        findings.append(("for_unquoted", m.group(0).strip()))

    return findings


def _build_message(
    wordsplit: list[tuple[str, str]],
    has_indirect: bool,
    has_mapfile: bool,
) -> str:
    """Compose the advisory systemMessage from detected patterns."""
    parts: list[str] = []

    for pid, text in wordsplit:
        if pid == "set_dashdash":
            parts.append(
                f"`{text}` — bash-ism: zsh does NOT word-split an unquoted `$var` "
                f"in `set --`. Under zsh this sets ONE positional parameter, not "
                f"many. zsh-safe fix: build an explicit array first, e.g. "
                f'`parts=("${{(@s: :)var}}")` then `set -- "${{parts[@]}}"`, '
                f"or use a `while IFS= read -r` loop over a newline-delimited list."
            )
        elif pid == "for_unquoted":
            parts.append(
                f"`{text}` — bash-ism: zsh does NOT word-split an unquoted `$var` "
                f"in `for … in`. Under zsh the loop iterates over ONE value. "
                f"zsh-safe fix: use "
                f'`while IFS= read -r x; do …; done <<< "$var"` '
                f"(for newline-separated lists) or an explicit array "
                f'`for x in "${{arr[@]}}"`. (feedback_zsh_shell_environment)'
            )

    if has_indirect:
        parts.append(
            "`${!var}` / `${!arr[@]}` — bash-only indirect/keys expansion. "
            "zsh equivalents: `${(P)var}` (indirect dereference) and "
            "`${(k)assoc}` (associative-array keys). "
            "(feedback_zsh_shell_environment)"
        )

    if has_mapfile:
        parts.append(
            "`mapfile` / `readarray` — bash-only builtins; absent in zsh. "
            "zsh-safe alternative: "
            '`while IFS= read -r line; do arr+=("$line"); done` '
            'or `arr=(${(f)"$(command)"})`.'
        )

    header = (
        "ZSH-SAFETY ADVISORY: bash-ism detected — this shell is zsh, "
        "not bash, and the following construct(s) will silently misbehave:\n\n"
    )
    return header + "\n\n".join(f"• {p}" for p in parts)


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry point for PreToolUse Bash.

    Returns None when no bash-ism word-splitting construct is found.
    Returns ``{"systemMessage": ...}`` (advisory, never blocking) when one or
    more risky constructs are detected.
    """
    if input_data.get("tool_name", "") != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return None

    # ------------------------------------------------------------------
    # Cheap pre-filter: bail early if none of the trigger tokens appear.
    # This is the primary performance gate — the expensive scanning only
    # runs when there is at least one candidate in the raw string.
    # ------------------------------------------------------------------
    has_set_dashdash = "set --" in command and "$" in command
    has_for = "for " in command and "$" in command
    has_indirect = "${!" in command
    has_mapfile_token = "mapfile" in command or "readarray" in command

    if not (has_set_dashdash or has_for or has_indirect or has_mapfile_token):
        return None

    # Strip heredoc bodies before scanning (command-position aware).
    stripped = strip_heredocs(command)

    # Re-check after stripping — the trigger tokens may live only in a heredoc.
    if not (
        ("set --" in stripped and "$" in stripped)
        or ("for " in stripped and "$" in stripped)
        or ("${!" in stripped)
        or ("mapfile" in stripped or "readarray" in stripped)
    ):
        return None

    # ------------------------------------------------------------------
    # Pattern 3 & 4: simple substring/regex scans on the stripped command.
    # These are checked on the full stripped command (not per-segment) because
    # shlex/bashlex tokenize strips braces/sigils so we'd lose the signal.
    # ------------------------------------------------------------------
    found_indirect = _has_indirect_expansion(stripped) if has_indirect else False
    found_mapfile = _has_mapfile(stripped) if has_mapfile_token else False

    # ------------------------------------------------------------------
    # Patterns 1 & 2: regex scan on stripped command.
    # ------------------------------------------------------------------
    wordsplit_findings: list[tuple[str, str]] = []
    if has_set_dashdash or has_for:
        wordsplit_findings = _scan_for_wordsplit(stripped)

    if not wordsplit_findings and not found_indirect and not found_mapfile:
        return None

    message = _build_message(wordsplit_findings, found_indirect, found_mapfile)
    return {"systemMessage": message}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    result = check(input_data)
    if result and result.get("systemMessage"):
        print(json.dumps({"systemMessage": result["systemMessage"]}))
    sys.exit(0)


if __name__ == "__main__":
    main()
