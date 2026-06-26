# Advise Knowledge-Base Consult Before Edits (PreToolUse hook)

**Purpose:** Nudge agents to load the project's curated knowledge base (your "librarian" / ontology / context skill) before they start editing code. The hook fires before `Edit`/`Write`/`NotebookEdit`, scans the current session for evidence that the knowledge-base skill was invoked, and — if not — emits an **advisory** `systemMessage` (the edit still proceeds). This is also the canonical template for "detect whether a particular skill/command ran earlier this session," via two complementary signals: a transcript scan and a freshness sentinel file.

This is a PreToolUse hook on `Edit`/`Write`/`NotebookEdit` with `check(input_data) -> dict | None`. Always exits 0.

---

## The rule it enforces

Before an edit, suppress the advisory if ANY holds: (1) the session transcript shows the consult skill was invoked (as a slash-command in user text OR as a `Skill` tool_use block), OR (2) a fresh cwd-keyed sentinel file attests a recent consult. Otherwise emit a one-line advisory. Allow-list paths where no consult is expected (scratch/tmp, memory files, user-level config, the hook-managed error log) so the nudge only fires on real source edits.

**Advisory, not blocking** is a deliberate stance: soften a guard to advisory once the thing it protected against is structurally handled elsewhere (e.g. the always-regenerated layer of your knowledge base), while keeping the nudge for the hand-curated layer.

## Code skeleton (stdlib only — `json`, `os`, `time`, `pathlib`)

```python
#!/usr/bin/env python3
"""PreToolUse Edit/Write/NotebookEdit: advise consulting the knowledge base.

Suppressed by EITHER a transcript signal OR a fresh cwd-keyed sentinel.
Advisory only — always exits 0.
"""
import json, os, sys, time
from pathlib import Path

_MATCHED_TOOLS = {"Edit", "Write", "NotebookEdit"}
_SKILL_NAME = "knowledge-librarian"  # your consult skill's id
_SLASH_MARKERS = (f"/{_SKILL_NAME}", f"<command-name>/{_SKILL_NAME}")
_TTL_SECONDS = 3600

_ALLOW_PREFIXES = ("/tmp/", os.path.expanduser("~/.claude/"))
_ALLOW_SUFFIXES = ("MEMORY.md",)
_ALLOW_CONTAINS = ("/memory/", "/.claude/errors/")

_ADVISORY = (
    f"ADVISORY: /{_SKILL_NAME} was not consulted earlier in this session before "
    "this code edit. Consulting it first loads the hand-curated project context "
    "(domain entities, topology, conventions) for the area you are touching. "
    "This is a non-blocking reminder; the edit will proceed."
)


def _is_allowlisted(p: str) -> bool:
    if not p:
        return False
    try:
        ap = os.path.abspath(os.path.expanduser(p))
    except (OSError, ValueError):
        ap = p
    return (any(ap.startswith(x) for x in _ALLOW_PREFIXES)
            or os.path.basename(ap) in _ALLOW_SUFFIXES
            or any(x in ap for x in _ALLOW_CONTAINS))


def _content_has_signal(content) -> bool:
    if isinstance(content, str):
        return any(m in content for m in _SLASH_MARKERS)
    if isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and any(m in b.get("text", "") for m in _SLASH_MARKERS):
                return True
            if b.get("type") == "tool_use" and b.get("name") == "Skill" \
               and (b.get("input") or {}).get("skill") == _SKILL_NAME:
                return True
    return False


def _transcript_attests(path: str) -> bool:
    if not path:
        return False
    try:
        p = Path(path)
        if not p.exists():
            return False
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") in ("user", "assistant"):
                    if _content_has_signal((obj.get("message") or {}).get("content", "")):
                        return True
    except OSError:
        return True  # cannot read state — do not nag on our own failure
    return False


def _sentinel_path(cwd: str) -> Path:
    import hashlib
    h = hashlib.sha1((os.path.abspath(cwd) + "\n").encode()).hexdigest()[:16]
    return Path(cwd) / ".claude" / ".consulted" / _SKILL_NAME / f"{h}.marker"


def _sentinel_attests(cwd: str) -> bool:
    if not cwd:
        return False
    try:
        s = _sentinel_path(cwd)
        if s.exists():
            age = time.time() - s.stat().st_mtime
            return 0 <= age <= _TTL_SECONDS
        return False
    except OSError:
        return True  # fail open


def check(input_data: dict) -> dict | None:
    if input_data.get("tool_name") not in _MATCHED_TOOLS:
        return None
    ti = input_data.get("tool_input") or {}
    file_path = ti.get("file_path") or ti.get("notebook_path") or ""
    if _is_allowlisted(file_path):
        return None
    if _transcript_attests(input_data.get("transcript_path", "")):
        return None
    if _sentinel_attests(input_data.get("cwd", "")):
        return None
    return {"systemMessage": _ADVISORY}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    result = check(input_data)
    if result and result.get("systemMessage"):
        print(json.dumps({"systemMessage": result["systemMessage"]}))
    sys.exit(0)  # advisory — always allow


if __name__ == "__main__":
    main()
```

## How to adapt

- **Two signals, because transcripts race.** In subagent/worktree sessions the transcript the hook reads can lag the flush or point at the parent's file, so a synchronously-written, cwd-keyed sentinel is the reliable fallback. The consult skill must write the sentinel itself: `<cwd>/.claude/.consulted/<skill>/<sha1(abspath(cwd))[:16]>.marker`. The hash matches the shell idiom `pwd | sha1sum | cut -c1-16`.
- **Cwd-keyed by design.** Each worktree has a distinct cwd → distinct sentinel, preserving "each agent must consult itself" — the orchestrator's consult does not satisfy a subagent's edit.
- **Fail open on read errors.** Don't nag because the hook couldn't stat/read state.
- **Allow-list the non-source paths** so memory/scratch edits don't trip the nudge.
- **Advisory vs. block:** keep it advisory when the protected context is regenerated/current-by-construction; escalate to a hard block (exit 2 + diagnostic) only when stale context would cause real harm.
