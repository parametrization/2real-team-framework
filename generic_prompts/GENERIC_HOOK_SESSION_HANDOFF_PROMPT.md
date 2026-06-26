# Auto Session-Handoff (Stop hook)

**Purpose:** Capture machine-readable project state on session exit so the next session can pick up without a manual handoff. Fires when the agent finishes its final response, snapshots git state, open PRs, open issues, and any project status/knowledge-base staleness, and writes a handoff file to project memory that the SessionStart hook auto-loads.

This is a `Stop` hook (a standalone script run by the harness, not a `check()` module). Advisory; always exits 0.

---

## The rule it enforces

On Stop, **throttled** to once per N minutes (avoid hammering the VCS API on chatty sessions): gather state, render a frontmatter'd Markdown handoff, and write it to the project-memory directory that SessionStart reads. Also print a compact display summary to stdout so the operator sees it. Crucially: write the handoff file where the SessionStart hook and any `/session-start` skill both look — keep them on the SAME path or they diverge (split-brain).

## Code skeleton (stdlib only — `json`, `re`, `subprocess`, `datetime`, `pathlib`)

```python
#!/usr/bin/env python3
"""Stop hook: auto-generate a session handoff file. Advisory; exit 0."""
import json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Handoff lives ALONGSIDE the project-memory corpus the SessionStart hook reads,
# so both sides see the same file. Keep it gitignored (per-session churn) but in
# the same dir as the committed memory — do NOT split it into a user-space dir.
MEMORY_DIR = REPO_ROOT / ".claude" / "memory"
HANDOFF_FILE = MEMORY_DIR / "session_handoff.md"

THROTTLE_SECONDS = 300  # regenerate only if older than 5 minutes

# --- CUSTOMIZE: VCS owner + repos to scan (set to [] / "" to skip VCS calls) ---
GH_OWNER = "your-org"
GH_REPOS = ["repo-a", "repo-b"]
GH_ISSUES_REPO = "repo-a"
STATUS_FILE = REPO_ROOT / "project-status.json"  # or None
CHECKSUMS_FILE = REPO_ROOT / "knowledge" / "checksums.json"  # or None


def _run(cmd: str, timeout: int = 10) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=timeout, cwd=str(REPO_ROOT))
        return r.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _git_state() -> dict:
    return {
        "branch": _run("git branch --show-current"),
        "recent_commits": _run("git log --oneline -10"),
        "uncommitted": bool(_run("git status --porcelain")),
    }


def _open_prs() -> list[str]:
    prs = []
    for repo in GH_REPOS:
        raw = _run(f"gh pr list --repo {GH_OWNER}/{repo} --state open "
                   "--json number,title --limit 5", timeout=15)
        if raw:
            try:
                for it in json.loads(raw):
                    prs.append(f"  - {repo}#{it['number']}: {it['title']}")
            except (json.JSONDecodeError, KeyError):
                pass
    return prs


def _staleness() -> str:
    if not CHECKSUMS_FILE or not CHECKSUMS_FILE.exists():
        return "No knowledge-base checksums found"
    try:
        data = json.loads(CHECKSUMS_FILE.read_text(encoding="utf-8")).get("files", {})
        dirty = [k for k, v in data.items()
                 if v.get("last_tracked") != v.get("last_resolved")]
        return ("Knowledge base current (0 dirty)" if not dirty
                else f"{len(dirty)} dirty: {', '.join(dirty[:5])}"
                     f"{'...' if len(dirty) > 5 else ''}")
    except (json.JSONDecodeError, OSError):
        return "Could not read checksums"
# _open_issues() and _status() follow the same shape (omitted)


def main() -> None:
    # Throttle: skip if handoff was written recently.
    if HANDOFF_FILE.exists():
        age = datetime.now(timezone.utc).timestamp() - HANDOFF_FILE.stat().st_mtime
        if age < THROTTLE_SECONDS:
            sys.exit(0)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    git, prs, stale = _git_state(), _open_prs(), _staleness()

    lines = [
        "---", "name: Session handoff",
        "description: Auto-generated pickup prompt — read this first to resume",
        "type: project", "---", "",
        f"## Last session: {now}", "", "### Git state",
        f"- **Branch:** {git['branch']}",
        f"- **Uncommitted changes:** {'Yes' if git['uncommitted'] else 'No'}", "",
        "**Recent commits:**", "```", git["recent_commits"], "```", "",
        "### Knowledge base", f"- {stale}", "",
        "### Open PRs", *(prs or ["  - None"]), "",
        "### Notes",
        "Auto-generated on session exit. For conversational context, read the git",
        "log above — commit messages capture what was done.",
    ]
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        HANDOFF_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        sys.exit(0)

    display = [f"[Session Handoff — {now}]",
               f"Branch: {git['branch']} | Uncommitted: "
               f"{'Yes' if git['uncommitted'] else 'No'}",
               f"Knowledge base: {stale}"]
    if prs:
        display.append(f"Open PRs: {len(prs)}"); display.extend(prs[:5])
    display.append("Handoff saved — next session will auto-load it.")
    print(json.dumps({"systemMessage": "\n".join(display)}))
    sys.exit(0)


if __name__ == "__main__":
    main()
```

## How to adapt

- **Same path on both sides.** The Stop hook writing and the SessionStart hook reading MUST agree on the handoff path, or you get split-brain. Keep it next to the project-memory corpus, gitignored.
- **Do NOT auto-rewrite tracked index files.** Mutating a version-controlled memory index on every exit is churn; let a manual `/handoff` skill own any committed index line. The Stop hook only writes the gitignored handoff.
- **Throttle** so a busy session doesn't spam the VCS API every response.
- **Degrade gracefully.** Every `_run` returns `""` on failure; set `GH_REPOS=[]`/`STATUS_FILE=None` to drop sections you don't have. Read canonical lifecycle keys for phase/iteration rather than flat keys that can lag.
- **A richer manual `/handoff` skill** complements this for conversational context (decisions, next steps); the auto version covers the machine-readable essentials.
