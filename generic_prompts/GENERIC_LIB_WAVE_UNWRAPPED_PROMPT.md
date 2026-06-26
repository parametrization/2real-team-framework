# Generic Library Prompt: Detect a Merged-But-Never-Wrapped Iteration

## Purpose

Detect the failure mode where an iteration's PRs all merged to the default branch
but the iteration was never *formally wrapped*: the wrapup marker stayed null, the
`active` flag stayed true, and the post-iteration housekeeping (retro, error
sweep, memory updates) never ran — because nothing at session-start surfaced the
gap.

This helper is the deterministic, **NON-FATAL** detector that a session-start step
turns into a nudge toward the wrapup command. It must never raise and never gate.

## Reusable design

### The signal (a three-part conjunction)

Fire the nudge when ALL of:

- `iteration_{M}_active == true`, AND
- no wrapup marker present for iteration M, AND
- 0 open iteration PRs across the iteration's in-scope repos.

**Scope to the CURRENT iteration only.** This is load-bearing: when iteration keys
in the status file are NOT phase-namespaced, the file legitimately retains stale
`iteration_4_active: true` rows from a *prior* phase's same-ordinal iteration. A
naive "any active+unwrapped iteration" scan false-fires on those cross-phase
ghosts. Derive M from the live `current_iteration` pointer (`iteration-2 → 2`) and
look only at that.

### Wrapup-marker handling

Treat several historical key spellings as "wrapped" (`wrapped_up_at` /
`wrapup_completed_at` / `wrapped_at`). **`completed_at` is deliberately NOT a
wrapup marker** — it is set at an earlier lifecycle point, so counting it would
mask the very merge-to-wrapup gap this detector exists to find.

### Graceful degradation (every path)

A missing `current_iteration`, missing status keys, or a failed CLI call yields a
benign verdict (`ok` or the softer `unwrapped_unverified`) and never raises —
session-start must never break on this. A best-effort open-PR count returns `None`
("undetermined") on any CLI failure rather than a false `0` (a false `0` would fire
a spurious "merged but unwrapped" nudge mid-iteration).

### Verdicts

| verdict | condition | action |
|---|---|---|
| `ok` | no current iteration, or inactive, or already wrapped | none |
| `in_flight` | active, unwrapped, open iteration PRs remain | none (normal) |
| `unwrapped` | active, unwrapped, **0** open iteration PRs | FIRE the wrapup nudge |
| `unwrapped_unverified` | active, unwrapped, open-PR count undetermined | softer nudge |

Always exit 0 — the nudge is informational, not a gate.

## Code template (stdlib + an issue/CI CLI)

```python
"""Detect an iteration that merged to the default branch but was never wrapped."""
from __future__ import annotations
import json, subprocess
from pathlib import Path

_WRAPUP_MARKERS = ("wrapped_up_at", "wrapup_completed_at", "wrapped_at")  # NOT completed_at


def current_iteration_number(data: dict) -> str | None:
    raw = data.get("current_iteration")
    if not isinstance(raw, str):
        return None
    num = raw[len("iteration-"):] if raw.startswith("iteration-") else raw
    return num if num.isdigit() else None


def is_active(data, it):   return bool(data.get(f"iteration_{it}_active"))
def is_wrapped(data, it):  return any(data.get(f"iteration_{it}_{m}") for m in _WRAPUP_MARKERS)


def count_open_prs(repos, base, run_cli) -> int | None:
    total = 0
    for repo in repos:
        try:
            out = run_cli(["pr", "list", "--repo", repo, "--state", "open",
                           "--base", base, "--json", "number"])
            total += len(json.loads(out or "[]"))
        except (subprocess.CalledProcessError, json.JSONDecodeError, OSError):
            return None        # undetermined — never a false 0
    return total


def evaluate(data, *, iteration=None, base=None, repos=None, run_cli=None) -> dict:
    it = iteration or current_iteration_number(data)
    res = {"iteration": it, "verdict": "ok", "message": ""}
    if it is None:
        res["message"] = "No current iteration — nothing to check."; return res
    if not is_active(data, it):
        res["message"] = f"Iteration {it} is not active."; return res
    if is_wrapped(data, it):
        res["message"] = f"Iteration {it} is already wrapped."; return res
    open_count = count_open_prs(repos, base, run_cli) if (base and repos and run_cli) else None
    if open_count == 0:
        res.update(verdict="unwrapped",
                   message=f"Iteration {it} active, unwrapped, 0 open PRs — run wrapup.")
    elif open_count is None:
        res.update(verdict="unwrapped_unverified",
                   message=f"Iteration {it} active, unwrapped; open-PR count undetermined.")
    else:
        res.update(verdict="in_flight",
                   message=f"Iteration {it} active with {open_count} open PR(s) — in flight.")
    return res
```

`base_branch` resolution should prefer the exact branch recorded under
`iteration_{M}_branches.branch` (it carries the real phase even when a top-level
phase key is stale), falling back to a constructed `deployments/<phase>/<iteration>`
only when an explicit phase is supplied.

## Adaptation notes

- "iteration/wave" → your cadence unit; `current_iteration`,
  `iteration_{M}_active`, the wrapup-marker spellings, and
  `iteration_{M}_repos_in_scope` are the status-file keys to map.
- The detector is read-only and non-fatal by contract — keep every error path
  returning a benign verdict.
- A `--no-gh`/key-only mode (skip the open-PR probe) is useful for offline runs:
  it yields `unwrapped_unverified` instead of probing.
- Wire the `unwrapped` / `unwrapped_unverified` verdicts to a printed `NUDGE:` line
  in the session-start step; do not auto-run wrapup.
