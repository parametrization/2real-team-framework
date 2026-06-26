# Generic Library Prompt: Verify Post-Merge-Only CI Workflows Went Green

## Purpose

A pull request's pre-merge CI is not the whole story. Some CI workflows are
**push-to-default-branch only** — they never run on pull requests, so they give
NO pre-merge signal and only execute *after* the merge lands. The canonical
example is a container-publish workflow whose image vulnerability scan runs on
`push: branches: [main]` but not on `pull_request`: every per-change PR can be
green while the post-merge publish goes red on a freshly-published base-image CVE.

When a merge is *deployable* (it integrates work to the default branch and may
trigger a publish/release), there must be a deterministic, scriptable way to
assert "the merge I just performed actually went green across the post-merge-only
workflows too" — instead of relying on an operator remembering to eyeball the
Actions list, which is exactly the manual step that rots.

## Reusable algorithm

Given a repo and a merge commit SHA:

1. **Resolve the expected workflow set.** Either an explicit caller-supplied list,
   or (default) read `.github/workflows/*` at that SHA and select workflows that
   trigger on push-to-default-branch (or tags). With a `--require-deployable`
   flag, narrow to the **post-merge-only** subset: merge-triggered AND NOT
   `pull_request` — the genuinely blind ones.
2. **Poll** the Actions runs for that exact `head_sha` until every expected
   workflow has a *completed* run (or a timeout elapses).
3. **Assert** every expected run concluded success/skipped/neutral. A FAILED run,
   OR an expected workflow that produced **no run at all** (the silent-drop case —
   an empty result is a hard not-verified, never a pass), fails the check.

Key it off the **real run records for the SHA**, not the merge command's own exit
status: a merge command returns 0 the instant the merge commit is created, long
before push-triggered workflows even start.

### Two layers (pure logic vs. I/O)

- **Pure (unit-tested directly, no network):** trigger classification from the
  `on:` block, display-name derivation, single-run bucketing, and the aggregate
  verdict over the expected set + a no-red safety net.
- **I/O (mocked in tests):** fetch workflow files at a ref, fetch run records for
  a SHA — both via an explicit-arg-list CLI subprocess (never a shell string).

### Trigger classification subtleties (carry these into any port)

- **The `on:` / YAML-boolean trap:** YAML 1.1 parses the bare key `on` as boolean
  `True`, so the trigger block can hide under `data[True]` instead of `data["on"]`.
  Check both spellings. This is the single most common GitHub-Actions YAML bug.
- **`on:` may be a string, a list, or a mapping** — normalize all three to an
  event-keyed dict.
- **A push trigger that names ONLY tags (no `branches`)** does not fire on a
  branch merge — treat it as a separate release path, not merge-triggered.
- **A push-to-default trigger carrying a `paths:`/`paths-ignore:` filter is
  *conditional*** — it may legitimately not run for a given merge, so exclude it
  from the *required* set (its absence is not a silent drop). If it does run and
  fails, the no-red safety net still catches it.
- **Match runs by the same label GitHub uses:** the workflow's top-level `name:`
  if present, else the bare filename.

### Aggregate verdict

- **Required set:** every expected workflow must be present AND pass; a missing one
  is the silent-drop case (hard not-verified).
- **No-red safety net:** any run that executed for this SHA but is *not* in the
  required set (e.g. a path-filtered push workflow that did fire) must not be red,
  and we wait for it to settle. This catches failures the required-set detection
  would miss without over-requiring conditional workflows.
- `verified = not any_fail and not pending`. "Nothing required" resolves to
  verified iff nothing that ran went red.

### Exit codes

- `0` VERIFIED — every required workflow ran and passed, and nothing for the SHA
  went red (includes the "nothing required" case, verified by the safety net).
- `1` NOT VERIFIED — a failed run, a required workflow with no run (silent drop),
  or still pending at timeout.
- `2` UNDETERMINED — a CLI/API call failed; cannot determine.

## Code template (stdlib + a YAML parser + an issue/CI CLI)

```python
"""Verify a deployable merge's post-merge-only workflows concluded green."""
from __future__ import annotations
import dataclasses, yaml

_PASS = frozenset({"success", "skipped", "neutral"})


def _coerce_on_block(parsed):
    if not isinstance(parsed, dict):
        return None
    return parsed.get("on", parsed.get(True))   # YAML-boolean `on:` trap


def _branches_include_main(node, default_branch="main"):
    if not isinstance(node, dict):
        return True
    branches = node.get("branches")
    if branches is None:
        return True
    if isinstance(branches, str):
        branches = [branches]
    return any(b in (default_branch, "*", "**") for b in branches)


@dataclasses.dataclass(frozen=True)
class WorkflowTrigger:
    name: str
    on_push_main: bool
    push_path_filtered: bool
    on_pull_request: bool

    @property
    def is_merge_triggered(self):       # runs UNCONDITIONALLY on a merge
        return self.on_push_main and not self.push_path_filtered

    @property
    def is_post_merge_only(self):       # merge-triggered AND invisible pre-merge
        return self.is_merge_triggered and not self.on_pull_request


def classify_run(status, conclusion):
    if status != "completed":
        return "pending"
    return "pass" if conclusion in _PASS else "fail"


def aggregate(expected, runs):
    by_name = {}
    for r in runs:
        by_name.setdefault(r["name"], r)        # API newest-first → keep first
    any_fail = any_pending = False
    missing = []
    for name in expected:
        found = by_name.get(name)
        if found is None:
            missing.append(name); continue
        b = classify_run(found["status"], found["conclusion"])
        any_fail |= (b == "fail"); any_pending |= (b == "pending")
    for r in runs:                              # no-red safety net
        if r["name"] in set(expected):
            continue
        b = classify_run(r["status"], r["conclusion"])
        any_fail |= (b == "fail"); any_pending |= (b == "pending")
    pending = any_pending or bool(missing)
    return {"verified": not any_fail and not pending, "pending": pending, "missing": missing}
```

`verify(...)` resolves the expected set, then polls `aggregate(expected,
fetch_runs_for_sha(...))` with injectable `sleep`/`clock` (so tests drive the loop
without real time) until not pending or the deadline.

## Adaptation notes

- Default-branch name is a parameter; don't hard-code `main`.
- If the host CI is not GitHub Actions, the pure layer (trigger semantics, verdict
  bucketing) still applies — only the file-fetch + run-fetch I/O changes.
- The classification deliberately treats tag-only and path-filtered pushes as
  *not required* — tune this if your release model differs.
- Pair this with the merge step in any "deployable merge" finalize flow; a green PR
  is not proof that the post-merge-only workflow stayed green.
