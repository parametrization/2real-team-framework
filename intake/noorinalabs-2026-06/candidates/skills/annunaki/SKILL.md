---
name: annunaki
description: View Annunaki error monitor status — shows recent captured errors and monitoring health
---

Display the current state of the Annunaki error monitor. This skill is the **status viewer** for the always-on error monitor (`annunaki_monitor`, dispatched on every `PostToolUse` Bash call via `post_dispatcher.py` — see § 1).

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149).

## How it works

The Annunaki system has two parts:
1. **Monitor (hook):** A `PostToolUse` hook on Bash that fires after every command, detects errors via exit codes and pattern matching, and logs them to `.claude/annunaki/errors.jsonl`
2. **This skill:** Reads and summarizes the error log

### Two streams — errors vs traces (#625)

The hooks write to **two** files under `.claude/annunaki/`:

- **`errors.jsonl`** — genuine signals: command-failure records, `pretooluse_block` (a real prevented command), and `posttooluse_event` (a hook reporting a follow-up condition). **This is the file this skill counts.**
- **`traces.jsonl`** — benign forensic traces (`posttooluse_dispatch`, `pretooluse_diagnostic`). Informational only; **never counted as errors**. Gitignored. Read it only when debugging the dispatcher itself.

Pre-#625 both kinds shared `errors.jsonl` and dispatch traces (76% of the P4W1 log) were mis-counted as errors. Use the shared reader `.claude/lib/annunaki_parse.py` — it skips blank/corrupt lines AND any benign-trace record (defending against historical mixed logs), so counts are correct on old and new logs alike.

## Instructions

### 1. Verify the hook is active

Confirm that `annunaki_monitor` runs on `PostToolUse` Bash. **Post-#625 it is NOT wired directly in `settings.json`** — it is a module dispatched by `post_dispatcher.py` (the single PostToolUse entry point), registered in that file's `_REGISTRY["Bash"]`. `settings.json` only references `post_dispatcher.py`. So a bare `grep annunaki_monitor settings.json` returns `0` and **falsely** reports the monitor inactive. Check both legs of the indirection instead:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
if grep -q post_dispatcher "$REPO_ROOT/.claude/settings.json" \
   && grep -q '"annunaki_monitor"' "$REPO_ROOT/.claude/hooks/post_dispatcher.py"; then
  echo "active"
else
  echo "NOT ACTIVE"
fi
```

`active` requires BOTH legs: the dispatcher must be wired on `PostToolUse` Bash in `settings.json` AND `annunaki_monitor` must be present in its `_REGISTRY`. If it prints `NOT ACTIVE`, warn the user that monitoring is not active and offer to wire it up. (Do not collapse this back to a single `grep` of `settings.json` — that is the #788 false-negative.)

### 2. Read the error log

Use the shared reader so benign traces and blank/corrupt lines are excluded automatically (#625). The genuine-error count:

```bash
python3 "$REPO_ROOT/.claude/lib/annunaki_parse.py" "$REPO_ROOT/.claude/annunaki/errors.jsonl" --count
```

**Parsing note:** the log is JSONL but may contain blank or whitespace-only lines from historical manual edits, AND — in historical/not-yet-cleared logs — benign-trace records (`type` in `posttooluse_dispatch` / `pretooluse_diagnostic`) that are NOT errors. Any parser you write MUST skip both. Prefer `annunaki_parse.iter_records()`; the canonical inline pattern (if you must hand-roll) is:

```python
import sys
sys.path.insert(0, f"{REPO_ROOT}/.claude/lib")
from annunaki_parse import iter_records, count_errors  # skips blanks, corrupt, AND benign traces

for rec in iter_records(path):   # genuine errors only
    ...
n = count_errors(path)           # genuine-error count
```

### 3. Show recent errors

Display the last 20 errors with timestamps and commands:

```bash
tail -20 "$REPO_ROOT/.claude/annunaki/errors.jsonl" 2>/dev/null
```

Parse and present them in a readable table:

```
**Annunaki Error Monitor — Status**

**Hook:** {active | NOT ACTIVE}
**Total errors logged:** {count}
**Log file:** .claude/annunaki/errors.jsonl

**Recent Errors (last 20):**

| # | Timestamp | Command (truncated) | Exit Code | Pattern |
|---|-----------|---------------------|-----------|---------|
| 1 | ...       | ...                 | ...       | ...     |
```

### 4. Show error frequency

Use the shared trace-filtering reader from § 2 when building the breakdown so benign traces never inflate the counts (#625). A one-liner Bash recipe:

```bash
python3 - <<PY "$REPO_ROOT/.claude/annunaki/errors.jsonl" "$REPO_ROOT/.claude/lib"
import sys
from collections import Counter
sys.path.insert(0, sys.argv[2])
from annunaki_parse import iter_records
from pathlib import Path
by_hook = Counter()
for rec in iter_records(Path(sys.argv[1])):   # genuine errors only
    by_hook[rec.get("hook", "unknown")] += 1
for h, c in by_hook.most_common():
    print(f"{c:4d}  {h}")
PY
```

If there are more than 10 errors, show a breakdown:

```
**Error Frequency:**
- Errors in last hour: {N}
- Errors in last 24h: {N}
- Most common pattern: {pattern} ({count} occurrences)
- Most error-prone command prefix: {prefix} ({count} occurrences)
```

### 5. Suggest /annunaki-attack if warranted

If there are 5+ unprocessed errors, suggest running `/annunaki-attack` to analyze and fix them.

## What this skill does NOT do

- It does not fix errors — use `/annunaki-attack` for that
- It does not modify the error log
- It does not create issues or PRs
