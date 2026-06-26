# Knowledge-Base Change Tracker (PostToolUse hook)

**Purpose:** Keep a checksum ledger of your hand-curated knowledge-base files so a "rebuild" skill knows exactly which ones drifted since they were last reconciled. After every `Edit`/`Write`, the hook hashes the touched file and records the new hash as `last_tracked`. When `last_tracked != last_resolved`, that file is "dirty" and needs reconciliation. The transferable value is the **scoping discipline**: track only the files a human curates, and rigorously skip everything that would inflate the dirty count without representing real drift.

This is a PostToolUse `Edit`/`Write` hook with `check(input_data) -> dict | None`. Advisory; always exits 0.

---

## The rule it enforces

On an Edit/Write whose `file_path` is non-empty, inside the repo tree, and NOT skip-matched: compute SHA-256, update `checksums.json` `files[<rel-path>]` with `{last_tracked, last_resolved (preserved), tracked_at, resolved_at (preserved)}`, written atomically. Skip aggressively:

- the checksums file itself (don't track the tracker),
- any **generated** layer of the knowledge base (it is current-by-regeneration, so checksum-tracking it is meaningless churn),
- build/VCS noise (`__pycache__/`, `.pyc`, `node_modules/`, `.git/`, `.DS_Store`),
- ephemeral scratch (`/tmp/` prefix),
- **worktree-isolation copies** (any path with a worktree dir component — these never reconcile and have aborted fast-forward merges),
- anything outside the repo root (e.g. user-space auto-memory files).

## Code skeleton (stdlib only — `hashlib`, `json`, `datetime`, `pathlib`)

```python
#!/usr/bin/env python3
"""PostToolUse Edit/Write: knowledge-base change tracker.

Hashes the edited file and records last_tracked in checksums.json. Dirty =
last_tracked != last_resolved. Tracks the HAND-CURATED layer only.
Advisory; always exits 0.
"""
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKSUMS_FILE = REPO_ROOT / "knowledge" / "checksums.json"

SKIP_SUBSTRINGS = [
    "knowledge/checksums.json", "knowledge/generated/",  # generated layer
    ".claude/errors/", "__pycache__/", ".pyc", "node_modules/", ".git/",
    ".DS_Store", ".claude/worktrees/",
]
SKIP_PREFIXES = ("/tmp/",)
WORKTREE_DIR_NAMES = frozenset({".worktrees", "worktrees"})


def _is_worktree_path(file_path: str) -> bool:
    parts = Path(file_path).parts
    for i, part in enumerate(parts):
        if part == ".worktrees":
            return True
        if part == "worktrees" and i > 0 and parts[i - 1] == ".claude":
            return True
    return False


def _should_skip(file_path: str) -> bool:
    if any(s in file_path for s in SKIP_SUBSTRINGS):
        return True
    if _is_worktree_path(file_path):
        return True
    try:
        resolved = Path(file_path).resolve()
    except (OSError, RuntimeError):
        return True  # unresolvable (broken symlink) — be conservative
    if any(str(resolved).startswith(p) for p in SKIP_PREFIXES):
        return True
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        return True  # outside the repo tree
    return False


def _sha256(p: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def check(input_data: dict) -> dict | None:
    if input_data.get("tool_name") not in ("Edit", "Write"):
        return None
    file_path = (input_data.get("tool_input") or {}).get("file_path", "")
    if not file_path or _should_skip(file_path):
        return None
    sha = _sha256(Path(file_path))
    if sha is None:
        return None
    try:
        rel = str(Path(file_path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        rel = file_path
    now = datetime.now(timezone.utc).isoformat()
    try:
        data = json.loads(CHECKSUMS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {"version": 1, "files": {}}
    files = data.setdefault("files", {})
    existing = files.get(rel, {})
    files[rel] = {
        "last_tracked": sha,
        "last_resolved": existing.get("last_resolved", ""),
        "tracked_at": now,
        "resolved_at": existing.get("resolved_at", ""),
    }
    try:
        CHECKSUMS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CHECKSUMS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(CHECKSUMS_FILE)
    except OSError:
        pass  # never fail the hook
    return {"action": "tracked", "path": rel}
```

## How to adapt

- **Track only what humans curate.** A generated/derived layer should be skipped — it's rebuilt wholesale, so a dirty flag on it is noise. Skip it exactly like the checksums file skips itself.
- **Worktree skipping prevents ledger rot.** A path recorded through a worktree copy never reconciles and accumulates stale entries; segment-match the worktree dir names (not substring, so `notes.worktrees.md` survives).
- **Out-of-repo guard.** Resolve the path and require it under the repo root; user-space auto-memory and `/tmp` files are not the knowledge base's source of truth.
- **`last_resolved` is owned by the rebuild skill**, not this hook — preserve it on every write. The hook only ever advances `last_tracked`.
- **Atomic write** (`tmp` then `replace`) so a crashed write never truncates the ledger.
