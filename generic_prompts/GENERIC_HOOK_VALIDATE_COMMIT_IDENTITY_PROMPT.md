# Generic Hook: Validate Commit Identity

## Purpose

A `PreToolUse` hook that enforces **per-commit author identity** on every
`git commit`. Each team member commits under a distinct, declared identity using
per-invocation `-c user.name=` / `-c user.email=` flags (never global/repo git
config). The hook validates that those flags are present and that the
name/email pair matches a known roster entry, then blocks the commit if not.

It exists because identity must be attributable per commit, and because an
agent can hide a `git commit` from a naive outer-command inspector by wrapping it
in a shell indirection. The hook therefore also detects **indirect-exec
wrappers** that smuggle a commit past the literal-command check.

## Rule

For any `Bash` tool call whose command runs `git commit` in command position:

1. The commit MUST carry both `-c user.name=<value>` and `-c user.email=<value>`.
2. `<value>` for name MUST match a known roster member.
3. The email MUST equal the roster's expected email for that name.
4. Any **indirect-exec wrapper** carrying a hidden `git commit` is BLOCKED
   outright with a directive to run the commit directly so flags are inspectable.

Exit code `0` = allow, `2` = block (a malformed-but-commit-shaped command should
**fail closed** = block; a non-commit command fails open = allow).

### Roster source

The roster is a mapping `{full_name: expected_email}` loaded from a
version-controlled file (e.g. JSON). Support an optional **parent/child merge**:
when committing inside a nested repo that has its own roster, merge it over a
parent repo's roster (child wins on key collision), so org-level identities work
in sub-repos without duplication. Resolve the target repo from a literal
`cd <path>` prefix, else from the tool-call `cwd`.

### Indirect-exec shapes to detect (each carrying an inner `git commit`)

- `printf '<cmd>' | sh` / `echo '<cmd>' | bash` (pipe-to-shell)
- `bash -c '<cmd>'` (shell `-c` string)
- `bash <(echo '<cmd>')` (process substitution)
- `bash <<EOF … git commit … EOF` (heredoc body fed to a shell)
- `bash <<<'git commit …'` (here-string)
- `eval 'git commit …'` (shell builtin)
- `sh <scriptfile>` (read the script's content and scan it; extension-agnostic,
  size-capped, fail-open on read error)

Detection is intentionally narrow: require BOTH `git` and `commit` in the inner
payload so innocent wrappers (`bash -c 'ls'`) pass through. Anchor on a known set
of interpreters (`bash|sh|zsh|dash|ksh`).

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""PreToolUse hook: validate per-commit git identity flags + block indirect-exec
wrappers hiding a git commit."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# --- roster loading -------------------------------------------------------
def _read_roster(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}

def _load_merged_roster(repo_root: Path) -> dict[str, str]:
    """Child roster merged over a one-level-up parent roster (child wins)."""
    rel = Path(".claude") / "team" / "roster.json"   # adapt path to your project
    child = _read_roster(repo_root / rel)
    parent = {}
    up = repo_root.parent
    if up != repo_root and (up / ".git").exists() and (up / rel).is_file():
        parent = _read_roster(up / rel)
    return {**parent, **child}

ROSTER = _load_merged_roster(Path(__file__).resolve().parents[2])

# --- indirect-exec detection ---------------------------------------------
_INTERP = r"(?:bash|sh|zsh|dash|ksh)"
_INNER_COMMIT = re.compile(r"\bgit\b[^;&|]*?\bcommit\b(?!\S*/)", re.DOTALL)

def _looks_like_commit(payload: str) -> bool:
    return bool(payload) and bool(_INNER_COMMIT.search(payload))

def _detect_indirect(command: str) -> str | None:
    patterns = [
        ("pipe-to-shell", re.compile(r"\b(?:printf|echo)\b(.+?)\|\s*" + _INTERP, re.DOTALL)),
        ("shell -c",      re.compile(r"\b" + _INTERP + r"\s+-c\s+((?P<q>['\"]).*?(?P=q)|\S+)", re.DOTALL)),
        ("process-sub",   re.compile(r"\b" + _INTERP + r"\s+<\(\s*([^)]+?)\s*\)", re.DOTALL)),
        ("here-string",   re.compile(r"\b" + _INTERP + r"\s+<<<\s*((?P<q>['\"]).*?(?P=q)|\S+)", re.DOTALL)),
        ("eval",          re.compile(r"\beval\s+((?P<q>['\"]).*?(?P=q)|\S+)", re.DOTALL)),
    ]
    for label, rx in patterns:
        for m in rx.finditer(command):
            inner = m.group(1)
            if inner and inner[0] == inner[-1] and inner[0] in "'\"":
                inner = inner[1:-1]
            if _looks_like_commit(inner):
                return label
    # `sh <scriptfile>`: read file content, scan it (size-capped, fail-open).
    return None

# --- direct commit detection ---------------------------------------------
_COMMIT_RE = re.compile(r"(?:^|[;&|])\s*git\b[^;&|]*?(?<!\S)\bcommit\b(?!\S*/)", re.MULTILINE)

def _extract_dash_c(command: str) -> dict[str, str]:
    """Collect `-c key=value` pairs. Prefer a real tokenizer (shlex) over regex."""
    import shlex
    try:
        toks = shlex.split(command)
    except ValueError:
        return {}
    out, i = {}, 0
    while i < len(toks) - 1:
        if toks[i] == "-c" and "=" in toks[i + 1]:
            k, _, v = toks[i + 1].partition("=")
            out[k] = v
            i += 2
        else:
            i += 1
    return out

def check(data: dict) -> dict | None:
    if data.get("tool_name") != "Bash":
        return None
    command = data.get("tool_input", {}).get("command", "")

    shape = _detect_indirect(command)
    if shape:
        return {"decision": "block",
                "reason": f"BLOCKED: indirect-exec wrapper ({shape}) hides a git commit. "
                          "Run git commit directly so identity flags are inspectable."}

    if not _COMMIT_RE.search(command):
        return None

    pairs = _extract_dash_c(command)
    name, email = pairs.get("user.name"), pairs.get("user.email")
    if not name:
        return {"decision": "block", "reason": "BLOCKED: commit missing -c user.name="}
    if not email:
        return {"decision": "block", "reason": "BLOCKED: commit missing -c user.email="}
    if name not in ROSTER:
        return {"decision": "block",
                "reason": f"BLOCKED: user.name={name!r} not a roster member. "
                          f"Valid: {', '.join(sorted(ROSTER))}"}
    if email != ROSTER[name]:
        return {"decision": "block",
                "reason": f"BLOCKED: user.email={email!r} != roster for {name} ({ROSTER[name]})"}
    return None

def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    result = check(data)
    if result and result.get("decision") == "block":
        print(json.dumps(result))
        sys.exit(2)
    sys.exit(0)

if __name__ == "__main__":
    main()
```

## Adaptation Notes

- **Tokenize, don't regex, the command.** Unquoted `-c user.email=val` will
  slurp to end-of-line under a naive regex. Prefer `shlex` (or a real Bash-AST
  parser such as `bashlex` when available) and fall back to a regex only on parse
  failure — and on that fallback, **fail closed** for commit-shaped commands.
- **Roster path / email convention** are project-specific. Replace the path and
  the `{name: email}` scheme with your own.
- **Parent/child merge** is optional; drop it for single-repo setups.
- **Indirect-exec coverage** is security-relevant: each new shape is a bypass.
  Keep detection narrow (require both `git` and `commit`) to avoid false blocks.
- The email convention itself (e.g. a `+tag` per member on one shared mailbox) is
  a deployment detail — do not hard-code any real address into the generic hook.
```
