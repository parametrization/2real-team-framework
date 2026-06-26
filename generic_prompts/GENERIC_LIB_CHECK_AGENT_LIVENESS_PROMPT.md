# Generic Lib Prompt: Deterministic Agent-Liveness Sweep

## Purpose

Mechanize the orchestrator's "is this spawned agent actually making progress?"
judgment into a deterministic, unit-testable check. Two stall shapes recur and
are easy to miss by eyeball until hours later:

1. A spawned implementer with **zero artifacts** (no branch pushed, no PR
   opened, no commit landed) after repeated idle notifications.
2. A mid-task agent **idle past a cadence** (e.g. 30 / 45 / 60 minutes) while it
   still has pending uncommitted work — a throttle-stall.

There is no clean tool-call boundary to hang a pre/post-tool hook on: the
signals are *artifact counts* and *elapsed/notification time*, observable only by
reconciling the task ledger against the set of spawned agents. So the
enforcement surface is a **checker the orchestrator runs at a status sweep**,
fed a snapshot it assembles from tools it already calls. This is the same
reader-side-oracle pattern as a CI-readiness oracle: a deterministic core turns
a state you *could* eyeball into a verdict you *cannot silently skip*.

## Reusable Pattern

- **Pure function of a snapshot.** `evaluate(snapshot) -> report`. All
  non-determinism (which agents exist, commit counts, idle time) lives in the
  snapshot the orchestrator hands in; the checker itself does no I/O. Fully
  unit-testable.
- **Thresholds as named module constants** (idle-notification flag count;
  ping/ping/takeover minute cadence) — one place to tune.
- **Role-scoped exclusion.** Reviewers carry no uncommitted work and are not
  task-per-implementer scoped, so exclude them from every check.
- **Artifact vs. pending-work distinction.** A *forward-progress artifact* is a
  branch pushed / PR opened / commit landed. A *dirty worktree alone is NOT an
  artifact* — it is the pending-work signal that arms the throttle cadence.
- **Findings carry an action and severity**, so the sweep names the next move
  (re-probe, auto-flag for takeover, first/second ping, auto-takeover) rather
  than just flagging.
- **Three exit codes:** 0 all live, 1 at least one finding, 2 parse error.

## Algorithm

Per implementer (skipping reviewers):

1. **Missing-task:** if no task-ledger entry matches this agent (owner name
   matches case/space-insensitively AND the issue ref appears in the subject;
   a `deleted` task doesn't count) → finding `missing-task`.
2. **Zero-artifact:** if no forward-progress artifact AND ≥1 idle notification →
   finding; severity escalates once the idle-notification count crosses the flag
   threshold (re-probe → auto-flag-takeover).
3. **Throttle-stall:** only if the agent `has_pending_work` (dirty worktree, or
   branch-pushed-but-no-PR, or committed-but-not-pushed), compare idle minutes to
   the cadence constants and emit first-ping / second-ping / auto-takeover.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Deterministic agent-liveness sweep over a spawn/task/artifact snapshot.

Exit codes: 0 all implementers live, 1 at least one finding, 2 parse error.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys

IDLE_NOTIFICATION_FLAG_THRESHOLD = 2
THROTTLE_FIRST_PING_MIN = 30
THROTTLE_SECOND_PING_MIN = 45
THROTTLE_TAKEOVER_MIN = 60


class SnapshotError(Exception):
    """Snapshot could not be parsed/validated (CLI exit 2)."""


@dataclasses.dataclass(frozen=True)
class Finding:
    implementer: str
    ref: str
    rule: str       # missing-task | zero-artifact | throttle-stall
    action: str
    severity: str   # low | moderate | high
    detail: str


@dataclasses.dataclass
class Report:
    findings: list[Finding]
    checked: list[str]
    excluded: list[str]

    def ok(self) -> bool:
        return not self.findings


def _norm(name: str) -> str:
    return " ".join(name.split()).casefold()


def has_artifact(a: dict) -> bool:
    return bool(a.get("branch_pushed") or a.get("pr_opened")
                or int(a.get("commits", 0) or 0) > 0)


def has_pending_work(impl: dict) -> bool:
    a = impl.get("artifacts", {})
    if impl.get("worktree_dirty"):
        return True
    if a.get("branch_pushed") and not a.get("pr_opened"):
        return True
    if int(a.get("commits", 0) or 0) > 0 and not a.get("branch_pushed"):
        return True
    return False


def task_exists_for(impl: dict, tasks: list[dict]) -> bool:
    key, ref = _norm(impl.get("name", "")), (impl.get("ref") or "").strip()
    for t in tasks:
        if t.get("status") == "deleted":
            continue
        if _norm(t.get("owner", "")) == key and ref and ref in (t.get("subject") or ""):
            return True
    return False


def _evaluate_one(impl: dict, tasks: list[dict]) -> list[Finding]:
    name, ref, a = impl.get("name", "?"), impl.get("ref", ""), impl.get("artifacts", {})
    out: list[Finding] = []
    if not task_exists_for(impl, tasks):
        out.append(Finding(name, ref, "missing-task", "recreate-task", "moderate",
                           "no task-ledger entry matches this implementer"))
    idle_n = int(impl.get("idle_notifications", 0) or 0)
    if not has_artifact(a) and idle_n >= 1:
        if idle_n >= IDLE_NOTIFICATION_FLAG_THRESHOLD:
            out.append(Finding(name, ref, "zero-artifact", "auto-flag-takeover",
                               "moderate", f"{idle_n} idle notifications, zero artifact"))
        else:
            out.append(Finding(name, ref, "zero-artifact", "reprobe", "low",
                               "1 idle notification, zero artifact; re-probe"))
    idle_m = int(impl.get("idle_minutes", 0) or 0)
    if has_pending_work(impl):
        if idle_m >= THROTTLE_TAKEOVER_MIN:
            out.append(Finding(name, ref, "throttle-stall", "auto-takeover", "high",
                               f"idle {idle_m}min with pending work"))
        elif idle_m >= THROTTLE_SECOND_PING_MIN:
            out.append(Finding(name, ref, "throttle-stall", "second-ping", "moderate",
                               f"idle {idle_m}min with pending work"))
        elif idle_m >= THROTTLE_FIRST_PING_MIN:
            out.append(Finding(name, ref, "throttle-stall", "first-ping", "low",
                               f"idle {idle_m}min with pending work"))
    return out


def evaluate(snapshot: dict) -> Report:
    if not isinstance(snapshot, dict):
        raise SnapshotError("snapshot must be a JSON object")
    impls, tasks = snapshot.get("implementers", []), snapshot.get("tasks", [])
    if not isinstance(impls, list) or not isinstance(tasks, list):
        raise SnapshotError("'implementers' and 'tasks' must be arrays")
    findings, checked, excluded = [], [], []
    for impl in impls:
        if not isinstance(impl, dict) or "name" not in impl:
            raise SnapshotError("each implementer requires a 'name'")
        if (impl.get("role") or "implementer").strip().casefold() == "reviewer":
            excluded.append(impl["name"])
            continue
        checked.append(impl["name"])
        findings.extend(_evaluate_one(impl, tasks))
    return Report(findings, checked, excluded)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="check_agent_liveness")
    p.add_argument("snapshot", nargs="?", help="JSON path; omit for stdin")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        raw = sys.stdin.read() if not args.snapshot else open(args.snapshot, encoding="utf-8").read()
        report = evaluate(json.loads(raw))
    except (OSError, json.JSONDecodeError, SnapshotError) as exc:
        print(f"check_agent_liveness: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"ok": report.ok(),
                          "findings": [dataclasses.asdict(f) for f in report.findings],
                          "checked": report.checked, "excluded": report.excluded},
                         indent=2, sort_keys=True))
    else:
        print("OK: all live" if report.ok() else
              "\n".join(f"  - {f.implementer}: {f.rule} ({f.severity}) -> {f.action}"
                        for f in report.findings))
    return 0 if report.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

## Adaptation Notes

- **Snapshot schema is the contract.** The orchestrator builds
  `{"tasks": [{subject, owner, status}], "implementers": [{name, ref, role,
  idle_notifications, idle_minutes, worktree_dirty, artifacts:{branch_pushed,
  pr_opened, commits}}]}` from the tools it already calls (task list + git/host
  CLI). The checker never reaches out itself.
- **Tune the thresholds to your cadence.** The flag count and the minute
  triggers are policy; keep them as the only place those numbers live.
- **`has_artifact` defines "progress" for your workflow.** If your definition of
  forward motion differs (e.g. a draft PR counts, a stacked branch counts),
  adjust that one predicate — the rest of the sweep follows.
- **Exit 1 is actionable, not fatal.** Wire it into a periodic sweep so each pass
  *names* a stall; the orchestrator decides whether to ping or take over.
```
