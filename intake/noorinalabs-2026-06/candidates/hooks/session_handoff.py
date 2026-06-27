#!/usr/bin/env python3
"""Stop hook: Auto-generate session handoff on exit.

Fires when Claude finishes its final response. Captures machine-readable
project state (git, PRs, issues, ontology staleness) and writes a handoff
file to project memory for the next session to pick up.

This replaces the need to manually run /handoff before exiting. The handoff
won't include conversational context (what was discussed), but the next
session can infer that from git log and the state captured here.

Exit codes:
  0 — always (advisory, never blocks)
"""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Project memory is version-controlled in-repo (#732 relocation) so it travels
# with a git pull. The handoff file itself stays gitignored — it's per-session
# machine-local churn — but it MUST live alongside the corpus so the SessionStart
# hook (session_start.py) and the /session-start skill read the same file. When
# this lived under the user-space ~/.claude/projects/ auto-memory dir while the
# skill read in-repo, the two diverged (split-brain, #741).
#
# We deliberately do NOT auto-rewrite the tracked MEMORY.md index line from this
# Stop hook: mutating a version-controlled file on every session exit is exactly
# the churn the gitignore on the handoff file avoids. The /handoff skill owns the
# committed index line (a deliberate, intentional write).
MEMORY_DIR = REPO_ROOT / ".claude" / "memory"
HANDOFF_FILE = MEMORY_DIR / "session_handoff.md"


def _run(cmd: str, cwd: str | None = None, timeout: int = 10) -> str:
    """Run a shell command and return stdout, or empty string on failure."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or str(REPO_ROOT),
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _get_git_state() -> dict:
    """Capture current git state."""
    return {
        "branch": _run("git branch --show-current"),
        "recent_commits": _run("git log --oneline -10"),
        "status": _run("git status --short"),
        "uncommitted": bool(_run("git status --porcelain")),
    }


def _get_open_prs() -> list[str]:
    """Get open PRs across all repos."""
    repos = [
        "noorinalabs-main",
        "noorinalabs-isnad-graph",
        "noorinalabs-user-service",
        "noorinalabs-deploy",
        "noorinalabs-design-system",
        "noorinalabs-landing-page",
        "noorinalabs-data-acquisition",
    ]
    prs = []
    for repo in repos:
        raw = _run(
            f"gh pr list --repo noorinalabs/{repo} --state open --json number,title --limit 5",
            timeout=15,
        )
        if raw:
            try:
                items = json.loads(raw)
                for item in items:
                    prs.append(f"  - {repo}#{item['number']}: {item['title']}")
            except (json.JSONDecodeError, KeyError):
                pass
    return prs


def _get_open_issues() -> list[str]:
    """Get open issues on main repo."""
    raw = _run(
        "gh issue list --repo noorinalabs/noorinalabs-main"
        " --state open --limit 10 --json number,title,labels",
        timeout=15,
    )
    issues = []
    if raw:
        try:
            items = json.loads(raw)
            for item in items:
                label_names = [lb["name"] for lb in item.get("labels", [])]
                label_str = f" [{', '.join(label_names)}]" if label_names else ""
                issues.append(f"  - #{item['number']}: {item['title']}{label_str}")
        except (json.JSONDecodeError, KeyError):
            pass
    return issues


def _get_ontology_staleness() -> str:
    """Check ontology checksums for dirty files."""
    checksums_file = REPO_ROOT / "ontology" / "checksums.json"
    if not checksums_file.exists():
        return "No ontology checksums found"
    try:
        with open(checksums_file) as f:
            data = json.load(f)
        files = data.get("files", {})
        dirty = [k for k, v in files.items() if v.get("last_tracked") != v.get("last_resolved")]
        if not dirty:
            return "Ontology is current (0 dirty files)"
        suffix = "..." if len(dirty) > 5 else ""
        return f"Ontology has {len(dirty)} dirty files: {', '.join(dirty[:5])}{suffix}"
    except (json.JSONDecodeError, OSError):
        return "Could not read checksums"


def _wave_phase_started(data: dict) -> tuple[str, str, str]:
    """Resolve (phase, wave, started) from a cross-repo-status.json dict.

    Reads the canonical lifecycle keys maintained by the wave skills:
      - phase   ← ``current_phase``
      - wave    ← ``current_wave`` (e.g. "wave-5")
      - started ← ``wave_<N>_started_at`` for N parsed from ``current_wave``,
                  falling back to ``wave_<N>_kicked_off_at``, then "unknown".

    The flat ``phase``/``wave``/``started``/``last_updated`` keys are NOT used
    as the source of truth — ``phase`` lags a phase behind (cross-phase key
    collision, #683) and ``wave``/``started`` do not exist (#708).
    """
    phase = data.get("current_phase", "unknown")
    wave = data.get("current_wave", "unknown")
    started = "unknown"
    if isinstance(wave, str):
        match = re.search(r"(\d+)", wave)
        if match:
            n = match.group(1)
            # `or` chains past both missing keys AND present-but-null values.
            started = (
                data.get(f"wave_{n}_started_at") or data.get(f"wave_{n}_kicked_off_at") or "unknown"
            )
    return str(phase), str(wave), started


def _get_wave_status() -> str:
    """Read cross-repo status for the active phase/wave."""
    status_file = REPO_ROOT / "cross-repo-status.json"
    if not status_file.exists():
        return "No cross-repo-status.json found"
    try:
        with open(status_file) as f:
            data = json.load(f)
        phase, wave, started = _wave_phase_started(data)
        return f"Phase {phase}, Wave {wave} (started {started})"
    except (json.JSONDecodeError, OSError):
        return "Could not read status file"


THROTTLE_SECONDS = 300  # Only regenerate if file is older than 5 minutes


def main() -> None:
    # Throttle: skip if handoff was written recently (avoids gh API spam)
    if HANDOFF_FILE.exists():
        age = datetime.now(timezone.utc).timestamp() - HANDOFF_FILE.stat().st_mtime
        if age < THROTTLE_SECONDS:
            sys.exit(0)

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d %H:%M UTC")

    git = _get_git_state()
    prs = _get_open_prs()
    issues = _get_open_issues()
    ontology = _get_ontology_staleness()
    wave = _get_wave_status()

    # Build handoff content
    lines = [
        "---",
        "name: Session handoff",
        "description: Auto-generated pickup prompt — read this first to resume work",
        "type: project",
        "---",
        "",
        f"## Last session: {date_str}",
        "",
        "### Git state",
        f"- **Branch:** {git['branch']}",
        f"- **Uncommitted changes:** {'Yes' if git['uncommitted'] else 'No'}",
        "",
        "**Recent commits:**",
        "```",
        git["recent_commits"],
        "```",
        "",
        "### Wave/phase status",
        f"- {wave}",
        "",
        "### Ontology",
        f"- {ontology}",
        "",
    ]

    if prs:
        lines.extend(["### Open PRs", *prs, ""])
    else:
        lines.extend(["### Open PRs", "  - None", ""])

    if issues:
        lines.extend(["### Open issues (noorinalabs-main)", *issues, ""])
    else:
        lines.extend(["### Open issues (noorinalabs-main)", "  - None", ""])

    lines.extend(
        [
            "### Notes",
            "This handoff was auto-generated on session exit. For conversational context,",
            "check the git log above — commit messages capture what was done.",
        ]
    )

    content = "\n".join(lines) + "\n"

    # Write handoff file
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(HANDOFF_FILE, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError:
        sys.exit(0)

    # Note: the tracked MEMORY.md index line is intentionally NOT updated here —
    # see the MEMORY_DIR comment above. The committed index line is owned by the
    # /handoff skill so this Stop hook never dirties a version-controlled file.

    # Build a compact display version for the conversation
    display_lines = [
        f"[Session Handoff — {date_str}]",
        f"Branch: {git['branch']} | Uncommitted: {'Yes' if git['uncommitted'] else 'No'}",
        f"Wave: {wave} | Ontology: {ontology}",
    ]
    if prs:
        display_lines.append(f"Open PRs: {len(prs)}")
        display_lines.extend(prs[:5])
    if issues:
        display_lines.append(f"Open issues (main): {len(issues)}")
        display_lines.extend(issues[:5])
    display_lines.append("Handoff saved to project memory — next session will auto-load it.")

    result = {
        "systemMessage": "\n".join(display_lines),
    }
    print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
