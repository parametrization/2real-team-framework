# Generic Hook: Flag Exit-Code-Masking Pipes on push / merge

## Purpose

A `PostToolUse` hook that flags a `git push` or PR-merge command sitting as a
**non-final stage of a pipeline** (`git push … | tail`, `merge … | head`, etc.).
Absent `set -o pipefail`, a pipeline returns the LAST stage's exit code — so a
**rejected push or failed merge exits 0 through the pipe and reads as success**.

It exists because this footgun recurs and silently hides real failures: a
rejected push followed by `| tail` looks like it landed. PostToolUse is the only
phase with access to the actual exit code + captured output, so it can confirm
whether the mask actually fired this time.

## Rule

Fires on a `PostToolUse` `Bash` result. Flags a `git push` / merge invocation
that is NOT the last stage of its pipeline (its rc is swallowed downstream), when
`pipefail` is NOT set. Two severity tiers:

- **TIER 1 — confirmed masked failure**: the masking shape is present AND the
  captured output carries a real push/merge failure signal (or the pipeline exit
  code is non-zero). Surface a HARD, prominent diagnostic to verify the operation
  actually landed.
- **TIER 2 — footgun shape only**: the shape is present but the output shows no
  failure this time. A lighter nudge to drop the pipe / use `; echo rc=$?` /
  `set -o pipefail`.

Does NOT flag: a no-pipe push/merge (rc preserved — the common case, must stay
silent); `push … ; echo rc=$?` (statement separator, the recommended fix);
`push … && …` (`&&` short-circuits on rc); `… | git push` (push is the LAST
stage); any pipeline with `pipefail` set; non-push/merge pipelines; and the
phrase inside a heredoc body / quoted string / `--body` value (command-position
aware).

PostToolUse is **advisory** — it can never block; exit code is always `0`. The
output is a `systemMessage`.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""PostToolUse hook: flag rc-masking pipes on git push / PR merge."""
from __future__ import annotations

import json
import re
import sys

_PIPEFAIL_RE = re.compile(r"\bpipefail\b")
_BARE_PIPE_PAD = re.compile(r"(?<![|&])\|(?!\|)")     # pad single `|`, not `||`
_STATEMENT_SEP = {";", "&&", "||", "\n"}

_FAILURE_MARKERS = re.compile(
    r"!\s*\[rejected\]|\[remote rejected|failed to push|non-fast-forward"
    r"|Updates were rejected|protected branch|pre-receive hook declined"
    r"|not mergeable|not in a mergeable state|failed to merge"
    r"|required status check|^fatal:|^error:",
    re.IGNORECASE | re.MULTILINE,
)

def _push_merge_label(tokens: list[str]) -> str | None:
    """'git push' / 'gh pr merge' if `tokens` is that invocation, else None.
    Skip leading `KEY=val` env assignments and `git -c k=v` globals."""
    t = [x for x in tokens if "=" not in x or not re.match(r"[A-Za-z_]\w*=", x)]
    if "git" in t:
        i = t.index("git")
        rest = [x for x in t[i + 1:] if not x.startswith("-")]
        if rest and rest[0] == "push":
            return "git push"
    if "gh" in t:
        i = t.index("gh")
        rest = t[i + 1:]
        if len(rest) >= 2 and rest[0] == "pr" and rest[1] == "merge":
            return "gh pr merge"
    return None

def _detect_masked(command: str) -> list[str]:
    """Labels for push/merge stages whose rc is masked (non-final pipe stage).
    A real Bash-AST parser (e.g. bashlex) is preferred; this is the shlex/regex
    fallback: split into statements, then pipeline stages, flag non-last stages."""
    if _PIPEFAIL_RE.search(command):
        return []
    import shlex
    padded = _BARE_PIPE_PAD.sub(" | ", command)
    try:
        tokens = shlex.split(padded)
    except ValueError:
        return []
    labels, statement = [], []
    def flush(stmt):
        stages, cur = [], []
        for tok in stmt:
            if tok == "|":
                stages.append(cur); cur = []
            else:
                cur.append(tok)
        stages.append(cur)
        for stage in stages[:-1]:           # every stage but the last is masked
            lbl = _push_merge_label(stage)
            if lbl:
                labels.append(lbl)
    for tok in tokens:
        if tok in _STATEMENT_SEP:
            flush(statement); statement = []
        else:
            statement.append(tok)
    flush(statement)
    seen, out = set(), []
    for l in labels:
        if l not in seen:
            seen.add(l); out.append(l)
    return out

def check(data: dict) -> dict | None:
    if data.get("tool_name") != "Bash":
        return None
    command = data.get("tool_input", {}).get("command", "")
    if not command or "|" not in command:
        return None
    if "push" not in command and "merge" not in command:
        return None
    labels = _detect_masked(command)
    if not labels:
        return None

    out = data.get("tool_response") or data.get("tool_output", {}) or {}
    combined = f"{out.get('stdout', '')}\n{out.get('stderr', '')}"
    exit_code = out.get("exit_code", 0) or 0
    label_str = " / ".join(f"`{l}`" for l in labels)

    if exit_code or _FAILURE_MARKERS.search(combined):
        return {"systemMessage": f"MASKED PUSH/MERGE FAILURE — {label_str} was piped into a "
                                 "downstream command, so the pipeline returned that command's "
                                 "exit code and the output shows a failure. VERIFY it landed; "
                                 "re-run without the pipe, or append `; echo rc=$?`."}
    return {"systemMessage": f"rc-masking pipe on {label_str}: the pipeline's exit code is the "
                             "downstream command's, not git's/gh's — a rejected push would read "
                             "as success. Prefer `…; echo rc=$?`, drop the pipe, or `set -o pipefail`."}

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

- **PostToolUse is advisory by contract** — never block. The genuine footgun is
  the masked *outcome*, and only PostToolUse has the rc + output to detect it.
- **Command-position awareness** is essential: prefer a real Bash-AST parser to
  distinguish a real `git push | tail` from the phrase inside a `--body` value or
  heredoc; fall back to the shlex/regex statement→stage split shown here.
- **The footgun is the POSITION** (left of a `|`), not a specific masker name —
  match any non-final stage, not just `tail`/`head`.
- **Two tiers** keep false-positive friction low: a benign pipe that masked
  nothing gets a soft nudge; a confirmed masked failure gets a hard diagnostic.
- **Failure markers** are git/host-specific strings — extend the set for your
  push/merge tooling.
- Pre-block was deliberately rejected: a hard pre-block over every `push …|` would
  block concurrent benign pipes. Surfacing the real masked failure post-hoc is
  the low-collateral fix.
```
