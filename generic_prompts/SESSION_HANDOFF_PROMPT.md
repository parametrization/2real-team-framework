# Session Handoff System

**Purpose:** Paste this prompt into a Claude Code session to set up automatic session handoff — a system that captures project state on every response and makes it available to the next session automatically.

---

## What you're building

A session continuity system with two parts:

1. **Auto-handoff (Stop hook):** A Python script that fires after every Claude response (throttled to 5-minute intervals). It captures machine-readable project state and writes it to project memory, which is auto-loaded at the next session start.

2. **Manual handoff (skill):** A `/handoff` skill for richer summaries that include conversational context (what was discussed, decisions made, next steps). The auto version covers essentials; the manual version is for when context matters.

## Step 1: Create the Stop hook

Create `.claude/hooks/session_handoff.py`:

```python
#!/usr/bin/env python3
"""Stop hook: Auto-generate session handoff.

Fires after every Claude response (throttled to 5-min intervals).
Captures git state, open PRs, open issues, and project status.
Writes to project memory for auto-loading at next session start.

Exit codes:
  0 — always (advisory, never blocks)
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# --- CUSTOMIZE THESE FOR YOUR PROJECT ---
# Project memory path — derived from the working directory
# Claude Code stores project memory at ~/.claude/projects/{encoded-path}/memory/
# The encoded path replaces / with - and strips the leading -
_cwd = str(REPO_ROOT.resolve())
_encoded = _cwd.replace("/", "-")
MEMORY_DIR = Path.home() / ".claude" / "projects" / _encoded / "memory"
HANDOFF_FILE = MEMORY_DIR / "session_handoff.md"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"

# GitHub org/owner for PR and issue queries (set to "" to skip GitHub queries)
GH_OWNER = ""

# Repos to check for open PRs (set to [] to skip)
GH_REPOS = []

# Main repo for issue queries (set to "" to skip)
GH_ISSUES_REPO = ""

# Project status file path (set to None if you don't have one)
STATUS_FILE = None

# Throttle interval — only regenerate if file is older than this many seconds
THROTTLE_SECONDS = 300
# --- END CUSTOMIZATION ---


def _run(cmd, cwd=None, timeout=10):
    """Run a shell command and return stdout, or empty string on failure."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=cwd or str(REPO_ROOT),
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _get_git_state():
    return {
        "branch": _run("git branch --show-current"),
        "recent_commits": _run("git log --oneline -10"),
        "status": _run("git status --short"),
        "uncommitted": bool(_run("git status --porcelain")),
    }


def _get_open_prs():
    if not GH_OWNER or not GH_REPOS:
        return []
    prs = []
    for repo in GH_REPOS:
        raw = _run(
            f"gh pr list --repo {GH_OWNER}/{repo} --state open --json number,title --limit 5",
            timeout=15,
        )
        if raw:
            try:
                for item in json.loads(raw):
                    prs.append(f"  - {repo}#{item['number']}: {item['title']}")
            except (json.JSONDecodeError, KeyError):
                pass
    return prs


def _get_open_issues():
    if not GH_ISSUES_REPO:
        return []
    raw = _run(
        f"gh issue list --repo {GH_OWNER}/{GH_ISSUES_REPO} --state open --limit 10 "
        f"--json number,title,labels",
        timeout=15,
    )
    issues = []
    if raw:
        try:
            for item in json.loads(raw):
                label_names = [l["name"] for l in item.get("labels", [])]
                label_str = f" [{', '.join(label_names)}]" if label_names else ""
                issues.append(f"  - #{item['number']}: {item['title']}{label_str}")
        except (json.JSONDecodeError, KeyError):
            pass
    return issues


def _get_project_status():
    if not STATUS_FILE:
        return "No project status file configured"
    sf = REPO_ROOT / STATUS_FILE
    if not sf.exists():
        return f"{STATUS_FILE} not found"
    try:
        with open(sf) as f:
            data = json.load(f)
        # Adapt this to your status file format
        return json.dumps(data, indent=2)[:500]
    except (json.JSONDecodeError, OSError):
        return "Could not read status file"


def main():
    # Throttle: skip if handoff was written recently
    if HANDOFF_FILE.exists():
        age = datetime.now(timezone.utc).timestamp() - HANDOFF_FILE.stat().st_mtime
        if age < THROTTLE_SECONDS:
            sys.exit(0)

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d %H:%M UTC")
    date_short = now.strftime("%Y-%m-%d")

    git = _get_git_state()
    prs = _get_open_prs()
    issues = _get_open_issues()
    status = _get_project_status()

    # Build handoff content
    lines = [
        "---",
        "name: Session handoff",
        "description: Auto-generated pickup prompt from previous session — read this first to resume work",
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
        "### Project status",
        f"- {status}",
        "",
    ]

    if prs:
        lines.extend(["### Open PRs", *prs, ""])
    else:
        lines.extend(["### Open PRs", "  - None", ""])

    if issues:
        lines.extend(["### Open issues", *issues, ""])
    else:
        lines.extend(["### Open issues", "  - None", ""])

    lines.extend([
        "### Notes",
        "This handoff was auto-generated on session exit. For conversational context,",
        "check the git log above — commit messages capture what was done.",
    ])

    content = "\n".join(lines) + "\n"

    # Write handoff file
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(HANDOFF_FILE, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError:
        sys.exit(0)

    # Update memory index
    try:
        if MEMORY_INDEX.exists():
            index_content = MEMORY_INDEX.read_text(encoding="utf-8")
            index_lines = index_content.splitlines()
            new_lines = []
            found = False
            for line in index_lines:
                if "session_handoff.md" in line.lower() or "Session handoff" in line:
                    new_lines.append(
                        f"- [Session handoff](session_handoff.md) — Pickup from {date_short}: auto-generated project state snapshot"
                    )
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(
                    f"- [Session handoff](session_handoff.md) — Pickup from {date_short}: auto-generated project state snapshot"
                )
            MEMORY_INDEX.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except OSError:
        pass

    # Print compact summary as systemMessage (appears in conversation)
    display_lines = [
        f"[Session Handoff — {date_str}]",
        f"Branch: {git['branch']} | Uncommitted: {'Yes' if git['uncommitted'] else 'No'}",
    ]
    if prs:
        display_lines.append(f"Open PRs: {len(prs)}")
        display_lines.extend(prs[:5])
    if issues:
        display_lines.append(f"Open issues: {len(issues)}")
        display_lines.extend(issues[:5])
    display_lines.append("Handoff saved to project memory — next session will auto-load it.")

    result = {"decision": "allow", "systemMessage": "\n".join(display_lines)}
    print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
```

## Step 2: Create the /handoff skill

Create `.claude/skills/handoff/SKILL.md`:

```markdown
---
name: handoff
description: Generate a session pickup prompt — summarizes current state so the next session can resume seamlessly
args: notes
---

Generate a handoff summary for the next session. The optional `notes` argument lets the user add specific context (e.g., "was debugging the auth flow").

## Instructions

### 1. Gather current state

Collect in parallel:
- Git state: branch, recent commits, uncommitted changes
- Open PRs (if GitHub repo)
- Open issues (if GitHub repo)
- Any project status files or board state

### 2. Summarize the conversation

Review what was accomplished in this session:
- Tasks completed
- Decisions made
- Things discussed but not acted on
- Blockers or open questions

### 3. Write the handoff

Write to project memory as `session_handoff.md` with frontmatter:

    ---
    name: Session handoff
    description: Pickup prompt from previous session — read this first to resume work
    type: project
    ---

    ## Last session: {date}

    ### What was done
    - {completed work}

    ### Decisions made
    - {key decisions and rationale}

    ### Current state
    - Branch, open PRs, open issues, project status

    ### What's next
    - {prioritized next steps}

    ### User notes
    {notes argument if provided}

Also print the full summary to the conversation so the user can copy/paste it.

### 4. Update memory index

Add or update the handoff entry in MEMORY.md (replace existing — only one handoff at a time).

### 5. Confirm

Tell the user the handoff is saved and will auto-load next session.
```

## Step 3: Register the hook

Add to `.claude/settings.json` under `hooks`:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/.claude/hooks/session_handoff.py",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

## Step 4: Add session-start behavior

Add to `CLAUDE.md`:

```markdown
## Session Continuity

### Session start (MANDATORY — run before any other response)
The FIRST thing you do in every new conversation is run this protocol. Do not answer questions, do work, or engage in discussion until all steps are complete. Present the results as your opening message.

0. **Handoff check** — read `session_handoff.md` from project memory. If it exists, summarize it briefly to the user. This contains the pickup context from the previous session.

### Session end (automatic)
A Stop hook automatically writes a handoff file after every response (throttled to 5-min intervals). It captures git state, open PRs, issues, and project status. The next session auto-loads this.

For a richer handoff with conversational context, manually run `/handoff` before exiting.
```

## Customization

The hook has a customization block at the top. Set these for your project:

| Variable | What it does | Example |
|----------|-------------|---------|
| `GH_OWNER` | GitHub org/user for API queries | `"myorg"` |
| `GH_REPOS` | List of repos to check for open PRs | `["frontend", "backend", "infra"]` |
| `GH_ISSUES_REPO` | Repo to query for open issues | `"frontend"` |
| `STATUS_FILE` | Path to a project status JSON file | `"status.json"` |
| `THROTTLE_SECONDS` | Minimum seconds between regenerations | `300` |

For non-GitHub projects, leave `GH_OWNER` as `""` — the hook will skip API calls and only capture git state.

## How it works

1. **Every response:** Stop hook fires, checks if handoff is older than 5 minutes
2. **If stale:** Gathers git + GitHub state, writes to project memory, prints summary to conversation
3. **If fresh:** Exits immediately (no overhead)
4. **Next session:** Claude auto-loads `session_handoff.md` from project memory at startup
5. **Session start protocol** reads it as step 0, before any other orientation

The manual `/handoff` skill adds conversational context (what was discussed, decisions, rationale) that the auto version can't capture.
