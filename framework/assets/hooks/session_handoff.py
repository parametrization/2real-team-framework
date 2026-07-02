#!/usr/bin/env python3
"""Stop hook: auto-write/refresh a session-handoff note in project memory.

Runs via :mod:`stop_dispatcher` (``hooks.stop``). Captures the mechanical
project state — git branch/commits/dirtiness, and (when ``scm.owner`` is
configured) open PRs + issues via ``gh`` — and writes it to
``<paths.memory>/handoff.md`` so the next session can pick up without
re-deriving context. Adapted from the botfarm_inc reference session_handoff
hook: the hardcoded ``GH_OWNER``/repo lists are replaced by config
(``scm.owner``, ``project.repos``, ``paths.memory``), and the write path is the
framework's version-controlled project memory instead of the per-machine
``~/.claude`` store.

Interplay contract with the ``/handoff`` SKILL (the rich, hand-written note)
=============================================================================

Both write the SAME file (``<paths.memory>/handoff.md``). The skill's note
carries conversational context only a human/agent can write; this hook must
complement it, never clobber it:

- **Manual marker wins, always.** A handoff containing ``handoff: manual``
  (the HTML comment the ``/handoff`` skill writes) is NEVER overwritten. To
  re-enable auto-refresh, delete the file or remove the marker line.
- **Anything written this session wins.** A handoff without our auto marker
  whose mtime is at/after the session start (from the transcript's first
  timestamp) is never overwritten; if the session start cannot be determined,
  we conservatively skip too — an undatable hand-written note is never lost.
- **Only our own notes are refreshed freely.** A handoff carrying the auto
  marker (written by this hook) is refreshed, throttled to one write per
  ``THROTTLE_SECONDS`` (Stop fires after every response — the hook must be a
  cheap no-op almost always).

Config-driven + fail-open + INERT when unconfigured: no
``framework.config.json`` → do nothing; no ``scm.owner`` → the gh sections are
omitted (git-only note); any subprocess/IO failure degrades to a partial note
or a silent skip, never an error. NEVER blocks the Stop event.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from _framework_config import config  # noqa: E402

#: Marker this hook writes into its own notes — marks the file as auto-owned
#: (safe to refresh). Checked by substring.
AUTO_MARKER = "handoff: auto"
#: Marker the /handoff skill writes into hand-written notes — protects the file
#: from this hook until removed. Checked by substring.
MANUAL_MARKER = "handoff: manual"
#: Minimum seconds between refreshes of an auto-owned note.
THROTTLE_SECONDS = 300
#: Cap on gh-queried repos in the meta-and-children model (Stop must stay cheap).
_MAX_REPOS = 5


def _run(cmd: list[str], cwd: Path, timeout: int = 10) -> str:
    """Run a command, return stdout ('' on any failure). Fail-open by contract."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(cwd))
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _session_start_epoch(input_data: dict) -> float | None:
    """Best-effort session start time: the first timestamp in the transcript JSONL."""
    path = input_data.get("transcript_path") if isinstance(input_data, dict) else None
    if not isinstance(path, str) or not path:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            first = fh.readline()
        ts = json.loads(first).get("timestamp")
        if not isinstance(ts, str):
            return None
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (OSError, ValueError, AttributeError):
        return None


def _skip_reason(handoff: Path, input_data: dict) -> str | None:
    """Return why the existing handoff must be left alone, or None to proceed."""
    try:
        text = handoff.read_text(encoding="utf-8")
        mtime = handoff.stat().st_mtime
    except OSError:
        return "unreadable existing handoff"  # conservative: never clobber blind
    if MANUAL_MARKER in text:
        return "manual note (skill marker)"
    if AUTO_MARKER in text:
        now = datetime.now(timezone.utc).timestamp()
        if now - mtime < THROTTLE_SECONDS:
            return "throttled"
        return None  # our own note, stale enough — refresh
    # Unmarked (hand-written / pre-marker) note: only replace if it provably
    # predates this session; otherwise it may be this session's work — keep it.
    started = _session_start_epoch(input_data)
    if started is None or mtime >= started:
        return "unmarked note not older than this session"
    return None


def _gh_lines(cfg, root: Path) -> tuple[list[str], list[str]]:
    """(open PR lines, open issue lines) via gh — only when scm.owner is configured."""
    owner = cfg.get("scm.owner")
    if not owner:
        return [], []
    prs: list[str] = []
    repos = cfg.get("project.repos") or []
    if cfg.get("project.model") == "meta-and-children" and repos:
        targets = [["--repo", f"{owner}/{r}"] for r in repos[:_MAX_REPOS]]
    else:
        targets = [[]]  # current repo, inferred from the git remote
    for extra in targets:
        raw = _run(
            ["gh", "pr", "list", "--state", "open", "--json", "number,title", "--limit", "5",
             *extra],
            root, timeout=15,
        )
        try:
            for item in json.loads(raw) if raw else []:
                repo_tag = f"{extra[1].split('/')[-1]}#" if extra else "#"
                prs.append(f"- {repo_tag}{item['number']}: {item['title']}")
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    raw = _run(
        ["gh", "issue", "list", "--state", "open", "--json", "number,title", "--limit", "10"],
        root, timeout=15,
    )
    issues: list[str] = []
    try:
        for item in json.loads(raw) if raw else []:
            issues.append(f"- #{item['number']}: {item['title']}")
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return prs, issues


def _compose(cfg, root: Path) -> tuple[str, str]:
    """Build (handoff markdown, one-line summary)."""
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%d %H:%M UTC")
    branch = _run(["git", "branch", "--show-current"], root) or "(unknown)"
    dirty = bool(_run(["git", "status", "--porcelain"], root))
    commits = _run(["git", "log", "--oneline", "-10"], root)
    prs, issues = _gh_lines(cfg, root)

    lines = [
        f"<!-- {AUTO_MARKER} — generated by the session_handoff Stop hook; safe to"
        " auto-refresh. Run /handoff to write a protected manual note instead. -->",
        f"# Session Handoff — {stamp} (auto-generated)",
        "",
        "## Pickup (next concrete step)",
        "Auto-generated at session stop — no conversational context captured. Check the",
        "mechanical state below; run /handoff to replace this with a rich hand-written note.",
        "",
        "## Mechanical state",
        f"- Branch: {branch} ({'uncommitted changes' if dirty else 'clean'})",
        "- Open PRs:",
        *([f"  {p}" for p in prs] or ["  (none / gh unavailable)"]),
        "- Open issues:",
        *([f"  {i}" for i in issues] or ["  (none / gh unavailable)"]),
        "",
        "### Recent commits",
        "```",
        commits or "(no commits)",
        "```",
    ]
    summary = (
        f"session_handoff: refreshed handoff.md (auto) — branch {branch}, "
        f"{len(prs)} open PR(s), {len(issues)} open issue(s)."
    )
    return "\n".join(lines) + "\n", summary


def _ensure_index_pointer(memory_dir: Path) -> None:
    """Append a handoff pointer line to MEMORY.md when the index lacks one."""
    index = memory_dir / "MEMORY.md"
    try:
        if not index.is_file():
            return
        text = index.read_text(encoding="utf-8")
        if "handoff.md" in text:
            return
        line = "- [Session handoff](handoff.md) — latest pickup point; read first at session start.\n"
        index.write_text(text + ("" if text.endswith("\n") else "\n") + line, encoding="utf-8")
    except OSError:
        pass  # index update is best-effort


def check(input_data: dict) -> dict | None:
    """Stop entry. None = nothing done (inert/skipped); dict = wrote the handoff."""
    cfg = config(input_data)
    if cfg.path is None:
        return None  # not a bootstrapped repo — inert
    root = cfg.path.parent.parent
    memory_dir = root / cfg.get("paths.memory", ".claude/memory")
    handoff = memory_dir / "handoff.md"

    if handoff.exists() and _skip_reason(handoff, input_data) is not None:
        return None

    content, summary = _compose(cfg, root)
    try:
        memory_dir.mkdir(parents=True, exist_ok=True)
        handoff.write_text(content, encoding="utf-8")
    except OSError:
        return None  # fail-open: an unwritable memory dir never surfaces an error
    _ensure_index_pointer(memory_dir)
    return {"systemMessage": summary}


if __name__ == "__main__":  # manual smoke: run against the cwd repo
    result = check({})
    print(result["systemMessage"] if result else "session_handoff: skipped (nothing to do)")
