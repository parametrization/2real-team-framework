# Session-Start Protocol Directives (SessionStart hook)

**Purpose:** At the beginning of every session (startup and resume), print a checklist of startup-protocol directives to stdout so the agent sees them immediately and executes them before responding to the user. The hook reads cheap local state (handoff file, knowledge-base staleness, captured-error count, project/iteration status) and tailors the directives — turning "you should run X" into "DIRTY: 7 files — run /rebuild NOW" only when X is actually needed.

This is a `SessionStart` hook (a standalone script). Informational; always exits 0. It does not perform the steps — it instructs the agent to.

---

## The rule it enforces

Render a fixed, numbered protocol (worktree cleanup, team orientation, handoff check, knowledge-base freshness, captured-error review, iteration/status orientation, charter/convention freshness — adapt to your steps), but make each step **state-aware**: read the relevant artifact, and either say "no action needed" or emit a concrete ACTION line. End with an "ACTIONS REQUIRED (in order)" summary listing only the steps that actually need doing. The point is a deterministic, can't-skip startup that surfaces the day's real work.

## Code skeleton (stdlib only — `json`, `re`, `pathlib`)

```python
#!/usr/bin/env python3
"""SessionStart hook: emit state-aware startup-protocol directives. Exit 0."""
import json, re, sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent.parent
_CHECKSUMS = _PROJECT / "knowledge" / "checksums.json"
_ERRORS_LOG = _PROJECT / ".claude" / "errors" / "errors.jsonl"
_STATUS = _PROJECT / "project-status.json"
# Handoff read from the SAME path the Stop hook writes (avoid split-brain).
_HANDOFF = _PROJECT / ".claude" / "memory" / "session_handoff.md"


def _staleness() -> tuple[int, int]:
    try:
        data = json.loads(_CHECKSUMS.read_text(encoding="utf-8"))
        data = data.get("files", data)
        dirty = sum(1 for v in data.values()
                    if isinstance(v, dict)
                    and v.get("last_tracked") != v.get("last_resolved"))
        return dirty, len(data)
    except (OSError, json.JSONDecodeError):
        return -1, 0


def _error_count() -> int:
    try:
        text = _ERRORS_LOG.read_text(encoding="utf-8").strip()
        return len(text.splitlines()) if text else 0
    except OSError:
        return -1


def _handoff() -> str | None:
    try:
        text = _HANDOFF.read_text(encoding="utf-8").strip()
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                text = parts[2].strip()
        return text or None
    except OSError:
        return None


def _status() -> str | None:
    try:
        d = json.loads(_STATUS.read_text(encoding="utf-8"))
        # Read canonical lifecycle keys (not flat keys that lag).
        return f"Phase {d.get('current_phase', '?')}, {d.get('current_iteration', '?')}"
    except (OSError, json.JSONDecodeError):
        return None


def main() -> None:
    L = ["=" * 60, "SESSION START PROTOCOL — MANDATORY", "=" * 60, "",
         "Complete ALL steps below BEFORE responding to the user.", ""]
    actions = []

    L += ["STEP 0 — WORKTREE CLEANUP: prune merged worktrees; flag locked/unmerged.", ""]
    actions.append("Run worktree cleanup (Step 0)")

    L += ["STEP 1 — TEAM ORIENTATION: confirm the single implicit team; spawn via "
          "the Agent tool (orchestrator is sole spawner).", ""]

    handoff = _handoff()
    L.append("STEP 2 — HANDOFF CHECK:")
    if handoff:
        L += ["  Handoff found. Read and summarize to user:", "", handoff, ""]
        actions.append("Summarize handoff (Step 2)")
    else:
        L += ["  No handoff found. Skip.", ""]

    dirty, total = _staleness()
    L.append("STEP 3 — KNOWLEDGE-BASE CHECK:")
    if dirty < 0:
        L.append("  checksums.json not found — run /rebuild")
    elif dirty == 0:
        L.append(f"  Current ({dirty}/{total} dirty). No action.")
    else:
        L.append(f"  DIRTY: {dirty}/{total} — ACTION: run /rebuild NOW.")
        actions.append("Run /rebuild (Step 3)")
    L.append("")

    errs = _error_count()
    L.append("STEP 4 — CAPTURED-ERROR CHECK:")
    if errs < 0:
        L.append("  Error log not found. No action.")
    elif errs == 0:
        L.append("  No errors logged.")
    elif errs < 5:
        L.append(f"  {errs} error(s) logged. Review briefly.")
    else:
        L.append(f"  {errs} errors — ACTION: run /error-review.")
        actions.append("Run /error-review (Step 4)")
    L.append("")

    status = _status()
    L += ["STEP 5 — ITERATION ORIENTATION:",
          f"  {status}" if status else "  status file not found.", ""]
    actions.append("Complete iteration orientation (Step 5)")

    L += ["STEP 6 — CHARTER/CONVENTION FRESHNESS: check for unapplied "
          "retro proposals or undocumented automation.", ""]
    actions.append("Complete charter freshness (Step 6)")

    L += ["=" * 60, "ACTIONS REQUIRED (in order):"]
    L += [f"  {i}. {a}" for i, a in enumerate(actions, 1)]
    L += ["", "Do NOT respond to the user until all steps are complete.", "=" * 60]
    print("\n".join(L))
    sys.exit(0)


if __name__ == "__main__":
    main()
```

## How to adapt

- **Your steps, your order.** The seven steps above are illustrative; keep whatever startup protocol your team runs. The transferable pattern is *state-aware directives + an actions-required summary*.
- **State-aware, not static.** Read each artifact and only emit an ACTION when one is genuinely needed (dirty > 0, errors ≥ threshold, handoff present). Static "always run X" directives get ignored.
- **Same handoff path as the Stop hook.** Read where the Stop hook wrote, or the handoff silently never loads.
- **The hook instructs; it does not act.** It prints directives; the agent performs them. Pair it with a `/session-start` skill that executes the steps for richer handling.
- **Fail soft.** Missing/unreadable artifacts degrade to a neutral line, never a crash.
