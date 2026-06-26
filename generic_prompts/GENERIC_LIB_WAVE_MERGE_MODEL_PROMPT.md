# Generic Library Prompt: One Merge Model Per Iteration + Mid-Iteration Branch Reachability

## Purpose

When a delivery framework batches work into iterations and each iteration may have
its own integration branch, a dangerous failure mode is **mixing merge models**
within one iteration: some PRs merge to the iteration's integration branch while
others go straight to the default branch, and the integration→default branch PR is
never opened. Net-new deliverables then sit stranded off the default branch and are
discovered only at iteration-wrapup — hours or days after they should have
surfaced.

Two durable, deterministic fixes live in this module:

1. **One merge model per iteration, declared at kickoff.** An iteration is EITHER
   `direct-to-main` (every PR bases on the default branch; the integration branch
   stays at the kickoff point and never accumulates work) OR `integration-branch`
   (every PR bases on the iteration branch and the integration→default PR is
   opened at wrapup). Mixing the two within one iteration is prohibited. The chosen
   model is recorded in the central status file under a per-iteration key at
   kickoff.

2. **Mid-iteration reachability check**, wired into session-start. For every
   in-scope repo it compares the iteration branch against the default branch and
   classifies the gap **against the declared model**, so stranding (or
   model-mixing) surfaces within hours instead of only at wrapup.

## Reusable design

The classification is a **pure function** so every model×state combination is
unit-testable without the network; a thin CLI I/O layer does the branch-compare
and PR-list calls at origin (never a local clone), using an explicit-arg-list
subprocess (no shell, no word-splitting).

### Classification matrix (`classify_reachability`, pure)

Inputs: declared `model` (or `None`), `branch_exists`, `ahead_by` (commits on the
iteration branch not on default), compare `status`, and whether an OPEN
integration→default PR exists. Output: `(severity, message)` where severity is
`ok` / `advisory` / `violation`.

| Model | Branch state | Open integration PR | Severity | Why |
|---|---|---|---|---|
| any | branch absent | — | `ok` | nothing to strand |
| any | not ahead | — | `ok` | already reachable from default |
| `direct-to-main` | ahead | either | **`violation`** | work merged to the iteration branch under a direct-to-main iteration — the prohibited mixing |
| `integration-branch` | ahead | yes | `ok` | healthy: the integration PR tracks the work |
| `integration-branch` | ahead | no | `advisory` | normal mid-iteration, but WILL strand unless wrapup opens the PR |
| `None` (legacy/undeclared) | ahead | either | `advisory` | conservative reading + nudge to declare the model; never a false violation |

`ahead` means `ahead_by > 0 OR status == "diverged"`.

### Exit-code contract

The reachability subcommand exits non-zero **only** on a hard model violation.
Advisories are expected mid-iteration states and must not fail the (non-fatal)
session-start step.

## Code template (stdlib + an issue/CI CLI)

```python
"""One-merge-model-per-iteration + mid-iteration branch reachability."""
from __future__ import annotations
import json, subprocess
from pathlib import Path

DIRECT_TO_MAIN, INTEGRATION_BRANCH = "direct-to-main", "integration-branch"
MERGE_MODELS = (DIRECT_TO_MAIN, INTEGRATION_BRANCH)
OK, ADVISORY, VIOLATION = "ok", "advisory", "violation"


def validate_merge_model(model: str) -> str:
    if model not in MERGE_MODELS:
        raise ValueError(f"invalid merge model {model!r}; expected one of {MERGE_MODELS}")
    return model


def classify_reachability(model, *, branch_exists, ahead_by, status, open_integration_pr):
    if not branch_exists:
        return OK, "no iteration branch — nothing to reconcile"
    if not (ahead_by > 0 or status == "diverged"):
        return OK, f"branch reachable from default (ahead_by={ahead_by})"
    if model == DIRECT_TO_MAIN:
        return VIOLATION, (
            f"merge-model violation: {ahead_by} commit(s) on the iteration branch "
            f"under declared '{DIRECT_TO_MAIN}' model — mixing prohibited")
    if model == INTEGRATION_BRANCH:
        if open_integration_pr:
            return OK, f"{ahead_by} commit(s) ahead, tracked by an open integration PR — healthy"
        return ADVISORY, (
            f"{ahead_by} commit(s) not reachable from default and NO open integration PR — "
            f"WILL strand unless wrapup opens it")
    base = f"{ahead_by} commit(s) not reachable; merge model NOT declared at kickoff"
    return ADVISORY, base + (" (an integration PR is open)" if open_integration_pr
                             else " — may strand if no integration PR is opened at wrapup")
```

The I/O wrapper (`gather_repo_state`) calls, at origin: a ref lookup (404 →
`branch_exists=False`), a `compare/<default>...<iteration-branch>` for `ahead_by` +
`status`, and an open-PR list filtered by base=default head=iteration-branch. The
declared model is read from the central status file; persist it via the shape-
preserving upsert helper so the status file's compact-inline shape is kept and the
write is JSON-validated either side. Defaults for injectable seams are resolved at
*call time* (not bound in the signature) so a test that monkeypatches the
module-level gatherer is honored.

## Adaptation notes

- "iteration/wave" → your cadence unit; "integration branch" naming →
  `deployments/<phase>/<iteration>` or whatever your branch convention is.
- Declare the model at the kickoff step (a `set` subcommand validating against the
  fixed enum, then upserting the per-iteration key) and check reachability at
  session-start (a `reachability` subcommand iterating in-scope repos).
- A legacy/undeclared iteration must degrade to `advisory`, never `violation` —
  don't punish iterations that predate the model.
- Compare at origin, not a local clone, so the check reflects pushed reality.
