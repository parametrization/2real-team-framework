# Generic Lib Prompt: PR CI-Readiness Oracle

## Purpose

Provide a **query-time** answer to one question: "Is this pull request's CI
actually green and ready to merge — right now?" — without waiting for the merge
gate to run.

In most workflows, the authority on merge-readiness is a **merge-time gate**
(e.g. a pre-merge hook that blocks `<cli> pr merge` when CI is red). That gate
only fires at merge time. There is no way to *ask* the same question earlier —
before asserting "this PR is ready" in a status update, a board move, or a
reviewer hand-off. This tool fills that gap by **reusing the gate's own
classifier verbatim**, so the read-time oracle and the merge-time gate can never
drift apart.

## Reusable Pattern

**Reader and writer share one module.** Do not reimplement the
pass/fail/pending/empty taxonomy in the oracle — import the gate's classifier
functions and call them. A vendored fork would silently diverge from the gate,
and that divergence is the exact failure the reuse exists to prevent. If the
import fails, fail loudly (a distinct exit code), never silently guess.

The load-bearing policy this oracle pins:

> An **empty** check-rollup ("no checks reported") is a **HARD not-ready**
> state — never green. Merge-readiness requires the rollup to be **non-empty
> AND all-success.**

The motivation: a silently-dropped CI trigger event (e.g. a re-push that never
spawned a workflow run) produces *zero* check runs. A naive "no failing checks"
readiness test would wave that through as green. Treating "zero checks" as
not-ready closes that hole.

Keep the responsibilities split:
- The **query-time oracle** (this tool) treats an empty rollup as not-ready
  **unconditionally** — it is a readiness assertion, not a merge decision.
- The **merge-time gate** may additionally discriminate a legitimate
  docs-only / fully-path-filtered empty so it does not deadlock those repos.
  That discrimination is a property of the gate, not of the readiness claim.

## Algorithm

1. Fetch the PR's status-check rollup via the host CLI (reuse the gate's
   `fetch_checks`). If it cannot be fetched → raise → exit code 2
   (undeterminable, distinct from a determinate "not ready").
2. Classify the rollup with the gate's classifier (reuse `classify_rollup`),
   yielding one of: `empty` | `failing` | `pending` | `ready`.
3. Collect the names of failing and pending checks for the report.
4. `ready` iff the verdict is `ready` (non-empty AND every check success).
5. Exit `0` if ready, `1` if not ready, `2` if undeterminable.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Query a PR's CI-readiness by REUSING the merge gate's own classifier.

Exit codes:
    0 — CI is READY to merge (non-empty rollup, every check passes)
    1 — CI is NOT READY (empty rollup, or any failing/pending check)
    2 — readiness could not be determined (PR fetch failed)
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

# Reuse the merge gate's canonical classifier. Put the gate's directory on
# sys.path and import its functions directly. There is intentionally NO local
# fallback copy — a vendored fork would drift from the gate.
_GATE_DIR = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(_GATE_DIR))
import validate_pr_ci_status as gate  # noqa: E402  (rename to your gate module)


@dataclasses.dataclass
class CiState:
    pr_number: str
    repo: str | None
    verdict: str           # "empty" | "failing" | "pending" | "ready"
    check_count: int
    failing: list[str]
    pending: list[str]

    def ready(self) -> bool:
        # Empty rollup is NEVER ready — classify_rollup returns "empty", not
        # "ready", for a zero-check rollup.
        return self.verdict == "ready"


class CiStateError(Exception):
    """CI readiness could not be determined (maps to exit code 2)."""


def compute_ci_state(pr_number: str, repo: str | None = None) -> CiState:
    rollup = gate.fetch_checks(pr_number, repo)
    if rollup is None:
        raise CiStateError(
            f"could not fetch CI status for PR #{pr_number}"
            + (f" in {repo}" if repo else "")
        )
    verdict = gate.classify_rollup(rollup)
    failing = [gate.check_name(c) for c in rollup if gate.classify_check(c) == "fail"]
    pending = [gate.check_name(c) for c in rollup if gate.classify_check(c) == "pending"]
    return CiState(str(pr_number), repo, verdict, len(rollup), failing, pending)


def _render_text(s: CiState) -> str:
    lines = [f"PR #{s.pr_number} — CI is {'READY' if s.ready() else 'NOT READY'}"]
    lines.append(f"  verdict: {s.verdict}")
    lines.append(f"  checks reported: {s.check_count}")
    if s.verdict == "empty":
        lines.append("  NOTE: an empty rollup ('no checks reported') is a HARD not-ready state.")
    if s.failing:
        lines.append(f"  failing: {', '.join(s.failing)}")
    if s.pending:
        lines.append(f"  pending: {', '.join(s.pending)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pr_ci_state")
    p.add_argument("pr_number")
    p.add_argument("--repo", default=None, help="OWNER/NAME; default uses cwd repo")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        state = compute_ci_state(args.pr_number, repo=args.repo)
    except CiStateError as exc:
        print(f"pr_ci_state: {exc}", file=sys.stderr)
        return 2
    if args.json:
        payload = dataclasses.asdict(state)
        payload["ready"] = state.ready()
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_text(state))
    return 0 if state.ready() else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

## Adaptation Notes

- **Swap `import validate_pr_ci_status as gate`** for your project's merge-gate
  module. The gate must expose: `fetch_checks(pr, repo)`, `classify_rollup(rollup)`
  (returning the 4-value taxonomy), and per-check helpers `classify_check(c)`
  and `check_name(c)`. If your gate's API differs, adapt names but keep the
  **reuse**, not a copy.
- **Three exit codes are deliberate.** Distinguish "determinately not ready" (1)
  from "couldn't determine" (2). Callers wiring this into automation need that
  difference: a fetch failure is a tooling problem, not a red PR.
- The **empty-rollup = not-ready** rule is the heart of this tool. If your host
  CLI reports zero checks for a dropped trigger event, do not let any caller
  interpret "no failing checks" as green.
- For a host without a "rollup" concept, substitute whatever aggregate
  check-status the platform exposes (commit-status API, checks API, pipeline
  status) — the taxonomy (empty/failing/pending/ready) is platform-agnostic.
