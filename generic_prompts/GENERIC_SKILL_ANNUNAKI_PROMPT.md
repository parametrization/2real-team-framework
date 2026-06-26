# Generic Skill: Error-Monitor Status Viewer

## Purpose

A read-only status viewer for an **always-on error monitor**. A `PostToolUse`
hook fires after every shell command, detects failures (via exit codes + pattern
matching), and appends them to a structured error log. This skill reads and
summarizes that log — it never fixes errors, modifies the log, or files issues.
(The companion **action** skill that processes and fixes the errors is the
attack/triage workflow — see `GENERIC_SKILL_ANNUNAKI_ATTACK_PROMPT.md`.)

> Adapt: name the monitor whatever you like ("error monitor", "watchtower").
> All file paths below are illustrative — root them at your repo top-level to
> avoid cwd drift when invoked from a worktree or sub-directory.

## How it works

The system has two parts:
1. **Monitor (hook):** a `PostToolUse` hook on the shell tool that logs failures.
2. **This skill:** reads and summarizes the log.

**Two log streams (recommended split):** keep genuine signals separate from
benign forensic traces.
- **`errors.jsonl`** — genuine signals: command-failure records, prevented-command
  (pre-exec block) records, and follow-up-condition events. **This is the file the
  skill counts.**
- **`traces.jsonl`** — benign forensic traces (dispatch/diagnostic records).
  Informational only, never counted as errors, gitignored.

Use a shared reader helper that skips blank/corrupt lines AND any benign-trace
record, so counts stay correct even on historical mixed logs.

## Workflow

### 1. Verify the hook is active

Confirm the monitor actually runs on `PostToolUse`. If the monitor is dispatched
**indirectly** (registered inside a single dispatcher entry point rather than
wired directly in settings), a naive `grep <monitor-name> settings` returns 0 and
**falsely** reports it inactive. Check BOTH legs of the indirection:

- the dispatcher is wired on `PostToolUse` for the shell tool in settings, AND
- the monitor module is present in the dispatcher's registry.

Report `active` only when both hold; otherwise warn and offer to wire it up.

### 2. Read the error log (genuine-error count)

Use the shared trace-filtering reader so benign traces and blank/corrupt lines
are excluded automatically. Emit the genuine-error count.

### 3. Show recent errors

Display the last ~20 errors with timestamps and commands in a readable table
(columns: #, timestamp, truncated command, exit code, matched pattern).

### 4. Show error frequency

Using the same trace-filtering reader, build a breakdown when there are enough
errors: errors in the last hour / 24h, most common pattern, most error-prone
command prefix.

### 5. Suggest the attack/triage skill if warranted

If there are 5+ unprocessed errors, suggest running the action/attack skill to
analyze and fix them.

## What this skill does NOT do

- It does not fix errors — that is the action/attack skill.
- It does not modify the error log.
- It does not create issues or PRs.

## Adaptation Notes

- The **two-stream split** (genuine errors vs benign traces) is the key reusable
  idea: without it, dispatch/diagnostic traces inflate the error count (in one
  real deployment they were ~76% of the log).
- Always count through the shared reader, never a raw `wc -l` — historical logs
  may contain blanks, corrupt lines, and mis-filed traces.
- The **indirect-dispatch false-negative** in Step 1 is the classic footgun:
  if your monitor is registered in a dispatcher, grepping settings alone lies.
