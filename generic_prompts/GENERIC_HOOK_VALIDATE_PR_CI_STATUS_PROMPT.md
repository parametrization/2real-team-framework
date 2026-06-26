# Generic Hook: Validate PR CI Status Before Merge

## Purpose

A `PreToolUse` hook that blocks a PR-merge command (e.g. `gh pr merge`) when the
PR's CI is **not green**. It queries the PR's status-check rollup and classifies
the result, blocking on failing checks, blocking (or warning) on pending checks,
and treating an **empty rollup** (no checks reported) as *not green* rather than
silently passing.

It exists because "no failing checks" is not the same as "all checks passed": a
dropped CI trigger can produce zero check-runs, which a naive gate waves through.

## Rule

For a merge command targeting a PR:

1. Fetch the status-check rollup for the PR.
2. Classify each check: **fail** (failure/cancelled/timed-out/action-required),
   **pending** (queued/in-progress/not-yet-complete), or **pass**.
3. **Fail** present → BLOCK.
4. **Pending** present → BLOCK, unless an auto-merge flag (`--auto`) lets the
   platform merge on green (then warn-allow).
5. **Empty rollup** → discriminate:
   - If a check *should* have run (the repo has an always-on PR workflow with no
     path filter) → BLOCK (anomalous dropped trigger).
   - If the repo is fully path-filtered (a docs-only PR legitimately runs zero
     checks) → warn-allow (no deadlock).
6. **All pass, non-empty** → allow.

Exit `0` = allow, `2` = block. Fail in the safe direction: when CI state can't be
verified at all, warn-allow rather than hard-deadlock — but never treat *unknown*
as *green* in an assertion oracle.

### Admin-override discipline (optional)

An `--admin` override should NOT short-circuit unconditionally. Require it to name
a declared exception class plus a non-empty rationale (e.g. via an env var
`ADMIN_MERGE_EXCEPTION=<class>:<rationale>`), and **log** every authorized use so
it is auditable. An absent/unrecognized exception blocks.

### NEUTRAL-conclusion nuance (optional)

Most services use a `NEUTRAL` conclusion to mean "no opinion" → treat as pass.
A few (e.g. some visual-regression services) use `NEUTRAL` to mean "review
pending" → treat as pending. Keep a small allowlist of check-name prefixes whose
`NEUTRAL` is pending; everything else keeps `NEUTRAL → pass`.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""PreToolUse hook: block PR merge unless CI is green."""
import json
import os
import re
import subprocess
import sys

_FAIL = {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"}
_PENDING = {"QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "REQUESTED"}
_NEUTRAL_PENDING_PREFIXES = ()  # e.g. ("visual-regression",) — service-specific

def is_merge_command(command: str) -> bool:
    for seg in re.split(r"\s*(?:&&|\|\||\||;)\s*", command):
        s = seg.lstrip()
        while re.match(r"[A-Za-z_]\w*=\S*\s+", s):
            s = re.sub(r"^[A-Za-z_]\w*=\S*\s+", "", s)
        if re.match(r"gh\s+pr\s+merge\b", s):   # adapt to your merge CLI
            return True
    return False

def extract_pr(command: str) -> str | None:
    m = re.search(r"\bgh\s+pr\s+merge\s+(\d+)", command) or re.search(r"/pull/(\d+)", command)
    return m.group(1) if m else None

def fetch_rollup(pr: str | None) -> list[dict] | None:
    cmd = ["gh", "pr", "view"] + ([pr] if pr else []) + ["--json", "statusCheckRollup"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            return None
        rollup = json.loads(r.stdout).get("statusCheckRollup", [])
        return rollup if isinstance(rollup, list) else None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None

def classify(check: dict) -> str:
    conclusion = (check.get("conclusion") or "").upper()
    status = (check.get("status") or check.get("state") or "").upper()
    if conclusion in _FAIL:
        return "fail"
    if status in _PENDING or conclusion == "":
        return "pass" if status == "COMPLETED" else "pending"
    if conclusion == "NEUTRAL":
        name = (check.get("name") or "").lower()
        if any(name.startswith(p) for p in _NEUTRAL_PENDING_PREFIXES):
            return "pending"
    return "pass"

def check(data: dict) -> dict | None:
    if data.get("tool_name") != "Bash":
        return None
    command = data.get("tool_input", {}).get("command", "")
    if not is_merge_command(command):
        return None

    if "--admin" in command:
        raw = os.environ.get("ADMIN_MERGE_EXCEPTION", "").strip()
        cls, sep, rationale = raw.partition(":")
        if not sep or not cls.strip() or not rationale.strip():
            return {"decision": "block",
                    "reason": "BLOCKED: --admin merge needs ADMIN_MERGE_EXCEPTION=<class>:<rationale>."}
        return None  # authorized — log this for audit

    rollup = fetch_rollup(extract_pr(command))
    if rollup is None:
        return {"decision": "allow",
                "systemMessage": "WARNING: could not verify CI; ensure green before merge."}
    if not rollup:
        # Empty rollup: discriminate via your repo's workflow path-filter signal.
        # If an always-on PR workflow exists -> block; else warn-allow.
        return {"decision": "allow",
                "systemMessage": "WARNING: empty rollup — no checks reported. Verify CI ran."}

    failing = [c for c in rollup if classify(c) == "fail"]
    pending = [c for c in rollup if classify(c) == "pending"]
    if failing:
        return {"decision": "block",
                "reason": f"BLOCKED: {len(failing)} failing CI check(s)."}
    if pending:
        if "--auto" in command:
            return {"decision": "allow",
                    "systemMessage": f"{len(pending)} pending; --auto will merge on green."}
        return {"decision": "block",
                "reason": f"BLOCKED: {len(pending)} pending check(s). Wait, or pass --auto."}
    return None

def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    result = check(data)
    if result is None:
        sys.exit(0)
    print(json.dumps(result))
    sys.exit(2 if result.get("decision") == "block" else 0)

if __name__ == "__main__":
    main()
```

## Adaptation Notes

- **Merge CLI** (`gh pr merge`) and the **rollup query** are platform-specific.
  Swap them for your host's equivalent JSON status API.
- **Empty-rollup discrimination** needs a signal for "should a check have run?"
  The robust version reuses a sibling workflow-path-coverage parser so the
  discriminator and the orphan-workflow gate share one path-filter reader and
  cannot drift. A simpler project may just warn-allow on empty.
- **Admin exception classes** map to your own policy doc; keep the hook list in
  lockstep with that doc, and log every authorized override for retro audit.
- **NEUTRAL allowlist** starts empty — add prefixes only for services you know
  use `NEUTRAL` to mean "review pending". Fail safe: a false pend blocks a merge
  an operator then inspects; a false pass slips an unreviewed change through.
```
