# Auto-Sync Board Field on Iteration-Label Change (PostToolUse hook)

**Purpose:** Keep a project-board single-select field (e.g. an "Iteration"/"Sprint"/"Wave" field) in lock-step with an issue's iteration label. When `<cli> issue edit <num> --add-label/--remove-label "<iter-label>"` succeeds, this hook PATCHes the issue's board field to match the post-edit label state via the board API (GraphQL `updateProjectV2ItemFieldValue` / `clearProjectV2ItemFieldValue`). It closes the gap left by a create-time board-add hook, which only fires on issue *creation*. The transferable lessons are fail-soft auth pre-flighting, ID caching, ambient-repo resolution, and post-edit-state semantics.

This is a PostToolUse `Bash` hook with `check(...) -> dict | None`. Advisory; always exits 0. Built on the iteration-label parser (`GENERIC_HOOK_WAVE_LABEL_PARSE_PROMPT.md`) and the error-log helper.

---

## The rule it enforces

For each iteration-label add/remove the command performs: resolve the target repo (from `--repo`, else from the invocation cwd), confirm the board API token has the required scope, look up the issue's board item, then **set** the field to the added label's option (add wins in a compound add+remove — post-edit state is what matters) or **clear** it on a remove. Skip gracefully — and log one event — on every failure mode (no auth scope, no board IDs, no option, issue not on board, mutation error). Never raise; the user-visible label edit already succeeded.

## Key mechanics (each is a real lesson)

- **Kill switch.** An env var (`==1` only, Unix truthy) bypasses the hook entirely for incident response.
- **Auth-scope pre-flight, fail-soft.** The board mutation needs a broader token scope than the default. Pre-flight it; if missing, skip silently and log ONE debounced advisory per session telling the user how to grant it — never surprise them with a hard failure.
- **ID cache.** The mutation needs project id + field id + per-option id (~3 round-trips). Introspect once per session, cache to a mode-0600 JSON file with a 1-hour TTL, atomic-replace. On a `field-not-found` error, bust the cache and retry once (the field may have been recreated).
- **Ambient-repo resolution.** An in-repo `issue edit` omits `--repo`; resolve it from cwd's VCS origin so the sync doesn't silently no-op. All `--repo`-less changes in one compound command share a cwd — resolve at most once.
- **Multi-command.** A single Bash call may carry many label edits (loops, `&&`-chains) — iterate all and aggregate results.

## Code skeleton (stdlib only — `json`, `os`, `subprocess`, `time`)

```python
#!/usr/bin/env python3
"""PostToolUse Bash: sync board single-select field on iteration-label change."""
from __future__ import annotations
import json, os, subprocess, sys, time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shell_parse import resolve_repo_short_name
from _wave_label_parse import LabelChange, parse_label_changes, label_to_field_option
from annunaki_log import log_posttooluse_event

ORG, PROJECT_NUMBER = "your-org", 2
FIELD_NAME = "Iteration"  # the board single-select field to sync
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = REPO_ROOT / ".claude" / ".consulted" / "label_field_sync"
CACHE_PATH = CACHE_DIR / "project_ids.json"
CACHE_TTL = 3600
KILL_SWITCH = "DISABLE_LABEL_SYNC_HOOK"
AUTH_WARN_SENTINEL = CACHE_DIR / "auth_scope_warned.marker"


def _kill_switch() -> bool:
    return os.environ.get(KILL_SWITCH, "") == "1"

def _has_project_scope(runner=None) -> bool:
    try:
        out = (runner or _default_auth_runner)()
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False
    return "'project'" in (out or "")  # complete-token match, not substring

def _default_auth_runner() -> str:
    r = subprocess.run(["gh", "auth", "status", "-h", "github.com"],
                       capture_output=True, text=True, timeout=10)
    return (r.stdout or "") + (r.stderr or "")

# _read_cache / _write_cache(mode 0600, atomic) / _bust_cache,
# _gh_graphql(query, vars) -> data|None, _introspect_project_ids,
# _get_project_ids(cache-or-introspect), _lookup_item_id(repo, num) ... (omitted)

def _ensure_auth_warned_once(reason: str) -> None:
    if AUTH_WARN_SENTINEL.exists():
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    AUTH_WARN_SENTINEL.touch()
    log_posttooluse_event("label_field_sync", "", reason)

def _apply_one(change: LabelChange, command, ids, runner) -> dict:
    assert change.repo is not None  # check() resolves it first
    target = change.add_label or change.remove_label or ""
    kind = "set" if change.add_label else "clear"
    option_name = label_to_field_option(target)
    # ... look up option_id (skip+log if missing), item_id (skip+log if not on board),
    #     then SET (with bust-and-retry once on field-not-found) or CLEAR mutation ...
    return {"action": kind, "repo": change.repo, "issue": change.issue_number}

def check(input_data, auth_status_runner=None, graphql_runner=None, git_runner=None):
    if input_data.get("tool_name") != "Bash":
        return None
    if _kill_switch():
        return {"action": "killed"}
    command = (input_data.get("tool_input") or {}).get("command", "")
    if not command:
        return None
    changes = parse_label_changes(command)
    if not changes:
        return None

    # Ambient-repo resolution for --repo-less changes (resolve once).
    ambient, resolved = None, False
    out_changes = []
    for c in changes:
        if c.repo is None:
            if not resolved:
                ambient = resolve_repo_short_name(input_data, git_runner=git_runner)
                resolved = True
            if ambient is None:
                log_posttooluse_event("label_field_sync", command,
                    f"skip_no_repo_context: issue {c.issue_number} omitted --repo "
                    "and ambient repo unresolvable.")
                continue
            c = replace(c, repo=ambient)
        out_changes.append(c)
    if not out_changes:
        return {"action": "skip_no_repo_context"}

    if not _has_project_scope(auth_status_runner):
        _ensure_auth_warned_once("label_field_sync skipped: board 'project' scope "
                                 "required; run your token-refresh command to enable.")
        return {"action": "skip_no_auth_scope"}
    ids = _get_project_ids(graphql_runner)
    if not ids:
        return {"action": "skip_no_project_ids"}

    if len(out_changes) == 1:
        return _apply_one(out_changes[0], command, ids, graphql_runner)
    results = [_apply_one(c, command, ids, graphql_runner) for c in out_changes]
    return {"action": "multi", "results": results, "count": len(results)}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    try:
        check(input_data)
    except Exception as e:  # noqa: BLE001 — advisory, never raise
        try:
            log_posttooluse_event("label_field_sync",
                (input_data.get("tool_input") or {}).get("command", "")[:500],
                f"Unexpected hook error: {type(e).__name__}: {e}")
        except Exception:
            pass
    sys.exit(0)
```

## How to adapt

- **Post-edit-state semantics:** in a compound add+remove, the *added* value is the new field value; a bare remove clears the field.
- **No per-issue opt-out.** "All iteration-labeled issues are board-tracked" is treated as an invariant; an opt-out label would silently drop issues off the board. The right way to un-track is to remove the iteration label.
- **Inject the runners** (`auth_status_runner`, `graphql_runner`, `git_runner`) so tests mock external state without mocking `subprocess`.
- **A periodic board-audit skill is the compensating control** for the graceful-skip cases (issue not on board, mutation failed) — log each skip so the audit and your error-review skill can pattern-match them.
- **Cache file is owner-only (0600)** and atomically written; bust-and-retry once on a field-not-found error.
