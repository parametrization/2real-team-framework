#!/usr/bin/env python3
"""Deterministic agent-liveness sweep over a spawn/task/artifact snapshot.

Mechanizes the two Tier-1 liveness rules carried from noorinalabs-main#735 to
the #745 follow-up (epic #726). The #735 charter→code pass converted the two
clean *tool-boundary* rules (Dockerfile base-pin, fixture-realism); these two
were flagged `deterministic-able` but `harder` (inventory caveat #4) because
they are **orchestrator-side timers with no clean tool boundary** to hang a
PreToolUse hook on:

  * `agents.md § Agent Liveness Checkpoint`
      (a) a `TaskCreate` must exist per spawned implementer, and
      (b) a spawned implementer with **zero artifacts** (no branch pushed, no
          PR opened, no commit landed) after **2** idle notifications is a stall
          to auto-flag for takeover.
  * `agents.md § Throttle-Stall Recovery — Trigger Thresholds`
      a mid-task-with-pending-work idle that crosses the **30 / 45 / 60-min**
      cadence is a throttle-stall: ping, ping, auto-takeover.

Why a lib, not a hook
=====================
Neither rule has a tool call to intercept. Part (a) fires at spawn time, but the
*violation* (a spawn with no matching task) is only observable by comparing the
live `TaskList` ledger against the set of spawned implementers — a cross-tool
reconciliation, not a single tool's arguments. Parts (b) and the throttle
cadence are driven off **artifact counts and elapsed/notification time**, not
off message activity, so there is no PreToolUse/PostToolUse event whose payload
carries the signal. The closest deterministic enforcement surface is therefore a
checker the orchestrator runs at a **status sweep** (e.g. each `/retro`,
`/wave-wrapup` open-item pass, or any time it reviews in-flight agents), feeding
it a snapshot it assembles from the tools it already calls:

  * `tasks`        — the `TaskList` ledger (subject / owner / status).
  * `implementers` — one entry per spawned agent, with the artifact counts the
                     orchestrator reads via `gh`/`git` (branch pushed? PR open?
                     commits?), the worktree-dirty signal, the count of
                     consecutive zero-progress idle notifications, and minutes
                     idle since the last observed progress.

The check is a **pure function of that snapshot** (`evaluate`), so it is fully
deterministic and unit-testable; the only non-determinism (which agents exist,
how many commits, how long idle) lives in the snapshot the orchestrator hands
in. This mirrors the reader-side oracle pattern of `pr_ci_state.py` /
`pr_review_state.py`: a deterministic core the orchestrator invokes to turn a
state it could *eyeball* into a verdict it *cannot silently skip*.

The two failure shapes this surfaces both recurred two consecutive waves
needing manual rescue: P5W2 #1024 (narrators-500 dispatch — zero branch/PR/
commit across the whole wave) and P5W3 #1038 (silent idle, undetected until
takeover); the throttle gap is W12 ig#931 (a 9h37m undetected stall). The point
of mechanizing is that the next sweep names the stall instead of the orchestrator
discovering it by accident hours later.

Snapshot schema (JSON, from a file arg or stdin)
================================================
    {
      "tasks": [
        {"subject": "main#745 — mechanize liveness",
         "owner": "Nadia Khoury", "status": "in_progress"}
      ],
      "implementers": [
        {
          "name": "Nadia Khoury",
          "issue_ref": "main#745",
          "role": "implementer",          # "reviewer" -> excluded (see below)
          "idle_notifications": 2,         # consecutive zero-progress idles
          "idle_minutes": 65,              # since last observed progress
          "worktree_dirty": false,
          "artifacts": {"branch_pushed": false,
                        "pr_opened": false,
                        "commits": 0}
        }
      ]
    }

`role` defaults to `"implementer"`. A `"reviewer"` entry is **excluded** from
every check — reviewers don't carry uncommitted work, so the worktree-dirty
signal doesn't apply (charter § Throttle-Stall § Out of scope), and the
TaskCreate-per-implementer rule is implementer-scoped.

CLI
===
    python3 .claude/lib/check_agent_liveness.py <snapshot.json>
    cat snapshot.json | python3 .claude/lib/check_agent_liveness.py
    python3 .claude/lib/check_agent_liveness.py <snapshot.json> --json

Exit codes:
    0 — every spawned implementer is live (has a task AND no stall signal)
    1 — at least one liveness finding (missing task, zero-artifact stall, or a
        throttle-cadence crossing) needs orchestrator attention
    2 — usage / parse error (bad JSON, missing required field)
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

# --- Thresholds (charter agents.md § Agent Liveness Checkpoint / Throttle) ---

# Part (b): a SECOND successive zero-artifact idle notification is a stall, not
# "still working" — auto-flag for takeover at this count.
IDLE_NOTIFICATION_FLAG_THRESHOLD = 2

# Throttle-Stall cadence, in minutes idle since last observed progress.
THROTTLE_FIRST_PING_MIN = 30
THROTTLE_SECOND_PING_MIN = 45
THROTTLE_TAKEOVER_MIN = 60


class SnapshotError(Exception):
    """The snapshot could not be parsed/validated (maps to CLI exit code 2)."""


@dataclasses.dataclass(frozen=True)
class Finding:
    """One liveness signal for one implementer."""

    implementer: str
    issue_ref: str
    rule: str  # "missing-task" | "zero-artifact" | "throttle-stall"
    action: str  # what the orchestrator must do, e.g. "auto-takeover"
    severity: str  # "low" | "moderate" | "high"
    detail: str


@dataclasses.dataclass
class LivenessReport:
    """Result of one sweep: findings plus who was checked / excluded."""

    findings: list[Finding]
    checked: list[str]
    excluded: list[str]

    def ok(self) -> bool:
        """True iff no implementer surfaced a liveness finding."""
        return not self.findings


def _normalize(name: str) -> str:
    """Case/space-insensitive key for owner-name matching."""
    return " ".join(name.split()).casefold()


def has_artifact(artifacts: dict) -> bool:
    """True iff any forward-progress artifact exists.

    Per charter: a branch pushed, a PR opened, or a commit landed. A dirty
    worktree alone is NOT an artifact — modified-but-uncommitted files are the
    throttle signal, not evidence of forward motion.
    """
    return bool(
        artifacts.get("branch_pushed")
        or artifacts.get("pr_opened")
        or int(artifacts.get("commits", 0) or 0) > 0
    )


def has_pending_work(impl: dict) -> bool:
    """True iff the implementer is mid-task with pending work (throttle scope).

    Charter § Throttle-Stall § Trigger scope signals:
      * worktree is dirty (modified files since session start), OR
      * branch pushed but no PR opened, OR
      * committed but branch not pushed.
    """
    artifacts = impl.get("artifacts", {})
    if impl.get("worktree_dirty"):
        return True
    if artifacts.get("branch_pushed") and not artifacts.get("pr_opened"):
        return True
    if int(artifacts.get("commits", 0) or 0) > 0 and not artifacts.get("branch_pushed"):
        return True
    return False


def task_exists_for(impl: dict, tasks: list[dict]) -> bool:
    """True iff a task in the ledger belongs to this implementer.

    Match = owner name matches (case/space-insensitive) AND the implementer's
    `issue_ref` appears in the task subject. A `deleted` task does not count as
    a live ledger entry; any other status (pending/in_progress/completed) does —
    the rule asserts the TaskCreate *happened*, not that it is still open.
    """
    name_key = _normalize(impl.get("name", ""))
    ref = (impl.get("issue_ref") or "").strip()
    for task in tasks:
        if task.get("status") == "deleted":
            continue
        if _normalize(task.get("owner", "")) != name_key:
            continue
        if ref and ref in (task.get("subject") or ""):
            return True
    return False


def _evaluate_one(impl: dict, tasks: list[dict]) -> list[Finding]:
    """All findings for a single implementer (empty list = live)."""
    name = impl.get("name", "<unnamed>")
    ref = impl.get("issue_ref", "")
    artifacts = impl.get("artifacts", {})
    findings: list[Finding] = []

    # Part (a): a TaskCreate must exist per spawned implementer.
    if not task_exists_for(impl, tasks):
        findings.append(
            Finding(
                implementer=name,
                issue_ref=ref,
                rule="missing-task",
                action="recreate-task",
                severity="moderate",
                detail=(
                    "no TaskList entry matches this implementer "
                    f"(owner={name!r}, ref={ref!r}); a zero-output stall would be "
                    "invisible at the next sweep — recreate the task."
                ),
            )
        )

    # Part (b): zero artifact after N idle notifications.
    idle_notifs = int(impl.get("idle_notifications", 0) or 0)
    if not has_artifact(artifacts) and idle_notifs >= 1:
        if idle_notifs >= IDLE_NOTIFICATION_FLAG_THRESHOLD:
            findings.append(
                Finding(
                    implementer=name,
                    issue_ref=ref,
                    rule="zero-artifact",
                    action="auto-flag-takeover",
                    severity="moderate",
                    detail=(
                        f"{idle_notifs} idle notifications, still zero artifact "
                        "(no branch/PR/commit); a 2nd zero-artifact idle is a "
                        "stall, not progress — auto-flag for takeover/reassignment."
                    ),
                )
            )
        else:
            findings.append(
                Finding(
                    implementer=name,
                    issue_ref=ref,
                    rule="zero-artifact",
                    action="reprobe",
                    severity="low",
                    detail=(
                        "1 idle notification with zero artifact; re-probe via "
                        "SendMessage and verify the task exists in TaskList."
                    ),
                )
            )

    # Throttle-Stall cadence: mid-task-with-pending-work idle crossing 30/45/60.
    idle_min = int(impl.get("idle_minutes", 0) or 0)
    if has_pending_work(impl):
        if idle_min >= THROTTLE_TAKEOVER_MIN:
            findings.append(
                Finding(
                    implementer=name,
                    issue_ref=ref,
                    rule="throttle-stall",
                    action="auto-takeover",
                    severity="high",
                    detail=(
                        f"idle {idle_min}min with pending work "
                        f"(>= {THROTTLE_TAKEOVER_MIN}min) — initiate "
                        "feedback_throttle_takeover with the implementer's commit "
                        "identity; record in the wave decisions log."
                    ),
                )
            )
        elif idle_min >= THROTTLE_SECOND_PING_MIN:
            findings.append(
                Finding(
                    implementer=name,
                    issue_ref=ref,
                    rule="throttle-stall",
                    action="second-ping",
                    severity="moderate",
                    detail=(
                        f"idle {idle_min}min with pending work "
                        f"(>= {THROTTLE_SECOND_PING_MIN}min) — second status ping; "
                        f"auto-takeover at {THROTTLE_TAKEOVER_MIN}min."
                    ),
                )
            )
        elif idle_min >= THROTTLE_FIRST_PING_MIN:
            findings.append(
                Finding(
                    implementer=name,
                    issue_ref=ref,
                    rule="throttle-stall",
                    action="first-ping",
                    severity="low",
                    detail=(
                        f"idle {idle_min}min with pending work "
                        f"(>= {THROTTLE_FIRST_PING_MIN}min) — first status ping "
                        "naming the observed state."
                    ),
                )
            )

    return findings


def evaluate(snapshot: dict) -> LivenessReport:
    """Run the liveness sweep over a snapshot. Pure; no I/O.

    Raises SnapshotError if the snapshot is structurally invalid.
    """
    if not isinstance(snapshot, dict):
        raise SnapshotError("snapshot must be a JSON object")
    implementers = snapshot.get("implementers", [])
    tasks = snapshot.get("tasks", [])
    if not isinstance(implementers, list) or not isinstance(tasks, list):
        raise SnapshotError("'implementers' and 'tasks' must be JSON arrays")

    findings: list[Finding] = []
    checked: list[str] = []
    excluded: list[str] = []

    for impl in implementers:
        if not isinstance(impl, dict):
            raise SnapshotError("each implementer must be a JSON object")
        if "name" not in impl:
            raise SnapshotError("each implementer requires a 'name'")
        role = (impl.get("role") or "implementer").strip().casefold()
        if role == "reviewer":
            # Reviewers don't carry uncommitted work and are not
            # TaskCreate-per-implementer scoped (charter § Out of scope).
            excluded.append(impl["name"])
            continue
        checked.append(impl["name"])
        findings.extend(_evaluate_one(impl, tasks))

    return LivenessReport(findings=findings, checked=checked, excluded=excluded)


def _render_text(report: LivenessReport) -> str:
    lines: list[str] = []
    if report.ok():
        lines.append("OK: all spawned implementers are live (task present, no stall signal).")
    else:
        lines.append(
            f"Agent-liveness findings ({len(report.findings)}) — "
            "agents.md § Agent Liveness Checkpoint / § Throttle-Stall Recovery:"
        )
        for f in report.findings:
            ref = f" [{f.issue_ref}]" if f.issue_ref else ""
            lines.append(
                f"  - {f.implementer}{ref}: {f.rule} ({f.severity}) -> {f.action}\n      {f.detail}"
            )
    if report.checked:
        lines.append(f"  checked: {', '.join(report.checked)}")
    if report.excluded:
        lines.append(f"  excluded (reviewers): {', '.join(report.excluded)}")
    return "\n".join(lines)


def _render_json(report: LivenessReport) -> str:
    payload = {
        "ok": report.ok(),
        "findings": [dataclasses.asdict(f) for f in report.findings],
        "checked": report.checked,
        "excluded": report.excluded,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="check_agent_liveness",
        description=(
            "Deterministic agent-liveness sweep. Reads a snapshot (TaskList "
            "ledger + per-implementer artifact/idle state) and reports "
            "spawned-but-zero-artifact stalls, missing TaskCreate entries, and "
            "throttle-stall cadence crossings. Exit 0 if all live, 1 if any "
            "finding, 2 on parse error."
        ),
    )
    p.add_argument(
        "snapshot",
        nargs="?",
        help="path to the JSON snapshot; omit to read from stdin",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON instead of the text report",
    )
    return p


def _load_snapshot(path: str | None) -> dict:
    try:
        raw = sys.stdin.read() if path is None else open(path, encoding="utf-8").read()
    except OSError as exc:
        raise SnapshotError(f"could not read snapshot: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SnapshotError(f"snapshot is not valid JSON: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        snapshot = _load_snapshot(args.snapshot)
        report = evaluate(snapshot)
    except SnapshotError as exc:
        print(f"check_agent_liveness: {exc}", file=sys.stderr)
        return 2

    print(_render_json(report) if args.json else _render_text(report))
    return 0 if report.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
