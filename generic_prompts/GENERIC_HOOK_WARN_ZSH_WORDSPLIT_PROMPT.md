# Generic Hook: Advisory Warning for Bash-isms That Misbehave Under zsh

## Purpose

An advisory (warn-only) `PreToolUse` hook that flags **bash-only shell idioms**
which silently misbehave when the shell is **zsh**. The dev environment's
interactive shell AND the agent's command tool run under zsh, where several
bash idioms that rely on word-splitting of unquoted scalars, or on bash-only
builtins/expansions, do the wrong thing without erroring.

It exists because prose guidance ("write zsh-safe commands") did not stop the
class from recurring — this is the memory→hook promotion for that feedback class
(enforcement hierarchy: hook > skill > charter).

## Rule

Fires on a `Bash` command. Flags (advisory only — never blocks):

1. `set -- $name` — unquoted plain scalar in a positional reset. Bash
   word-splits on IFS; zsh treats it as ONE field.
2. `for VAR in $name` — same word-splitting divergence (unquoted plain scalar).
3. `${!var}` / `${!arr[@]}` / `${!arr[*]}` — bash indirect / array-keys
   expansion. zsh uses `${(P)var}` / `${(k)arr}`.
4. `mapfile` / `readarray` — bash-only builtins absent in zsh.

Does NOT flag (false-positive guards):

- Quoted forms: `set -- "$@"`, `for x in "$list"`, `"${arr[@]}"`.
- `for x in *.py`, `$(...)`, backticks, `{1..5}`, literal `a b c`.
- Path/glob/concat where `$NAME` is only PART of a word: `$HOME/*.py`,
  `$dir/known_hosts`, `set -- $dir/*.txt` — in zsh `$VAR/...` is a single scalar
  path component (no word-splitting), so it is SAFE. The scalar must be a
  STANDALONE word to fire.
- Anything inside a heredoc body (stripped before scanning).
- `declare -A` / `typeset` — zsh supports these; NOT flagged.

The result is a `systemMessage` advisory; the dispatcher treats a result with no
`decision` key as allow. Exit code is always `0`.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""PreToolUse hook: advisory warning for bash-isms that misbehave under zsh."""
from __future__ import annotations

import json
import re
import sys

# A bare scalar reference: $NAME or ${NAME} — identifier only (no subscript,
# no !/# operator, no @/*). So $@, $*, ${arr[@]}, ${!x}, $(...) do NOT match.
_SCALAR_REF = r"\$(?:\{[A-Za-z_]\w*\}|[A-Za-z_]\w*)"
# Standalone-word boundary: the scalar ref must be the WHOLE word. If the next
# char is `/ . * [ {` etc. it is only a prefix of a compound word -> SAFE in zsh.
_BOUNDARY = r"(?=$|[\s;|&)`])"

_SET_DASHDASH_RE = re.compile(r"\bset\s+--\s+" + _SCALAR_REF + _BOUNDARY)
_FOR_UNQUOTED_RE = re.compile(r"\bfor\s+\w+\s+in\s+" + _SCALAR_REF + _BOUNDARY)
_INDIRECT_RE = re.compile(r"\$\{!")            # ${!...}; ${#...} (length) is fine
_MAPFILE_RE = re.compile(r"\b(mapfile|readarray)\b")

def _strip_heredocs(command: str) -> str:
    """Remove heredoc bodies so constructs quoted there don't false-fire.
    Use your shared shell parser; this is a minimal placeholder."""
    return command

def check(data: dict) -> dict | None:
    if data.get("tool_name") != "Bash":
        return None
    command = data.get("tool_input", {}).get("command", "")
    if not command:
        return None

    # Cheap pre-filter: bail unless a trigger token is present.
    if not (("set --" in command and "$" in command)
            or ("for " in command and "$" in command)
            or ("${!" in command)
            or ("mapfile" in command or "readarray" in command)):
        return None

    s = _strip_heredocs(command)
    parts: list[str] = []

    for m in _SET_DASHDASH_RE.finditer(s):
        parts.append(f"`{m.group(0).strip()}` — zsh does NOT word-split an unquoted `$var` "
                     "in `set --` (sets ONE positional). Build an explicit array, e.g. "
                     '`parts=("${(@s: :)var}")` then `set -- "${parts[@]}"`.')
    for m in _FOR_UNQUOTED_RE.finditer(s):
        parts.append(f"`{m.group(0).strip()}` — zsh does NOT word-split an unquoted `$var` "
                     "in `for … in` (iterates ONCE). Use "
                     '`while IFS= read -r x; do …; done <<< "$var"` or `for x in "${arr[@]}"`.')
    if _INDIRECT_RE.search(s):
        parts.append("`${!var}` / `${!arr[@]}` — bash-only indirect/keys expansion. "
                     "zsh: `${(P)var}` (indirect) and `${(k)assoc}` (keys).")
    if _MAPFILE_RE.search(s):
        parts.append("`mapfile` / `readarray` — bash-only builtins absent in zsh. "
                     'Use `while IFS= read -r line; do arr+=("$line"); done`.')

    if not parts:
        return None
    header = ("ZSH-SAFETY ADVISORY: bash-ism detected — this shell is zsh, not bash, "
              "and the following construct(s) will silently misbehave:\n\n")
    return {"systemMessage": header + "\n\n".join(f"• {p}" for p in parts)}

def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    result = check(data)
    if result and result.get("systemMessage"):
        print(json.dumps({"systemMessage": result["systemMessage"]}))
    sys.exit(0)

if __name__ == "__main__":
    main()
```

## Adaptation Notes

- **Only relevant if your shell is zsh** (or another non-bash shell with similar
  divergences). If the team's shell is bash, this hook is inapplicable.
- **The standalone-word boundary is the key false-positive fix.** `$VAR/...` is a
  single scalar path in zsh (no split) and must NOT fire; only a bare `$list` /
  `$a $b $c` standing as its own word does. Match the scalar as the WHOLE word.
- **Scan the raw string** (after heredoc-strip) for `${!...}` and `mapfile` —
  tokenizers strip braces/sigils and lose the signal.
- **Advisory, not blocking.** Word-splitting reliance is sometimes intentional; a
  hard block would create false-positive friction. Surface a `systemMessage`.
- **Cheap pre-filter first** for performance: only run the regex scans when a
  trigger substring is present.
- Use your project's shared shell parser for `strip_heredocs` rather than the
  placeholder above.
```
