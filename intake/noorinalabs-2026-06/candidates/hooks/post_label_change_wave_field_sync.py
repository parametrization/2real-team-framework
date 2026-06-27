#!/usr/bin/env python3
"""PostToolUse hook: Auto-sync project 2 Wave field when a wave label is added/removed.

When a `gh issue edit <num> --add-label "p{N}-wave-{M}"` or
`--remove-label "p{N}-wave-{M}"` command succeeds, this hook PATCHes the
issue's `Wave` single-select field on project 2 (Cross-Repo Wave Plan
board) to match the post-edit label state via GraphQL
`updateProjectV2ItemFieldValue`.

Closes the label-EDIT gap that Hook 13 (`auto_add_issue_to_board.py`,
which only catches `gh issue create`) doesn't cover. Same invariant as
Hook 13 — wave-labeled issues belong on the board with their Wave field
set — applied at the EDIT surface instead of the CREATE surface. 5
drifts caught by `/board-audit` in P3W10 retro motivated this hook.

Input Language:
  Fires on:      PostToolUse Bash
  Matches:       Bash commands whose `gh issue edit <num>` segment
                 includes at least one `--add-label "p{N}-wave-{M}"` or
                 `--remove-label "p{N}-wave-{M}"` flag-value pair, where
                 the label value matches the canonical wave-label regex
                 `^p\\d+-wave-\\d+$` (fully anchored).
  Does NOT match: any non-Bash tool; Bash without `gh issue edit`;
                  `gh issue create` (Hook 13's surface);
                  `gh pr edit ... --add-label ...` (PR labels don't
                  drive the Wave field — the Wave field lives on issues
                  in project 2); commands with non-wave labels (e.g.
                  `--add-label "bug"`); suffixed labels (e.g.
                  `p3-wave-10-special` does NOT match — anchored regex
                  excludes them).
  Flag pass-through:
    --repo            → identifies the owner/name; the short name is used
                        as the project content lookup key
                        (`https://github.com/noorinalabs/<repo>/issues/<num>`)
    --add-label       → wave label is set as the new Wave-field value
    --remove-label    → if the removed value matches the current Wave-field
                        value, the Wave field is CLEARED;
                        else no-op
    --add-label + --remove-label (compound) → POST-edit state is what
                        matters; add wins (set to the added value)

Exit codes:
  0 — always (PostToolUse hooks are advisory; failures log to Annunaki
      and silently skip the field-sync without affecting the user-visible
      tool call which has already succeeded)

Kill-switch
===========

Set environment variable `NOORIN_DISABLE_LABEL_SYNC_HOOK=1` to bypass
the hook entirely (no GraphQL call, no error, silent skip). Only the
literal string `1` skips; `=0`, empty, unset → hook proceeds normally
(Unix-tradition truthy-only). Use during debugging or incident response
when auto-mutation of the project board would interfere.

Auth-scope pre-flight
=====================

GraphQL `updateProjectV2ItemFieldValue` requires `project` scope on the
gh CLI auth token; the default scope is `repo`-only. The hook pre-flights
via `gh auth status -h github.com` and, if the project scope is missing,
skips silently and logs ONE annunaki entry per session (debounced via
the cache file's existence) instructing the user to run `gh auth refresh
-s project`. This is the fail-soft shape per
`feedback_runtime_gate_scoping.md`; surprising a user with a hook that
needs extra auth setup is the failure mode this avoids.

Project ID cache
================

Three IDs are required for the GraphQL mutation: the project node ID,
the Wave field ID, and the per-wave option ID (e.g. `P3W11`'s option ID).
Resolving all three on every label-edit would be ~3 GraphQL round-trips
of latency per hook fire. Instead, the hook introspects on the first
fire of a session and caches the result to
`.claude/.consulted/post_label_change_wave_field_sync/project_ids.json`
with a 1-hour TTL. The cache file is mode-0600 (owner-only read/write).
On `field-not-found` errors from the mutation (e.g., field was recreated
between cache write and mutation), the cache is busted and one
re-introspect + retry is performed before giving up.

Design choices documented for reviewer pickup
=============================================

- **No per-issue opt-out.** "All wave-labeled issues are board-tracked"
  is treated as a wave-scope invariant (per
  `feedback_wave_planning_from_board.md`). Adding an opt-out label like
  `noorin-no-board-sync` would silently drop wave-labeled issues off the
  board — contradicting `/wave-scope` and `/board-audit` semantics. If a
  wave-labeled issue genuinely should not be board-tracked, the right
  fix is to remove the wave label, not to add a sync-skip label.
  Additive escape hatches (denylist constant, opt-out label) can be
  added in a follow-up PR if real cases emerge — strictly additive, no
  breaking-semantic change.

- **No `addProjectV2ItemById` pre-flight.** The hook assumes the issue
  is already on project 2 (Hook 13 added it on create). If the issue
  is NOT on the board, the GraphQL mutation returns a "no matching
  item" error which the hook treats as a graceful skip — board-audit
  is the periodic compensating control for that case.

- **PostToolUse-ordering vs Hook 13.** Hook 13 (`auto_add_issue_to_board`)
  is registered BEFORE this hook in `post_dispatcher.py`'s Bash matcher
  list, so on a `gh issue create` flow that immediately edits the issue
  label, Hook 13's board-add lands first. But this hook does NOT fire
  on `gh issue create` (input language above); the ordering matters
  only for a hypothetical compound command that creates AND edits in
  one Bash call — out of pattern.

Promotion provenance
====================

P3W10 retro PR #441 § Proposed Process Changes #3. Owner-decided
2026-05-16; charter adoption via PR #444 (ccc7edf); this hook
implementation via PR #446 (issue #445). 5-drift evidence base
from W10 /board-audit run (all label-edit-class drifts that Hook 13
didn't catch). Companion to Hook 13 (`auto_add_issue_to_board.py`)
which catches CREATE-time only; this hook closes the label-EDIT gap.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import re  # noqa: E402

from _shell_parse import resolve_repo_short_name  # noqa: E402
from _wave_label_parse import (  # noqa: E402
    WaveLabelChange,
    parse_wave_label_changes,
    wave_label_to_option_name,
)
from annunaki_log import log_posttooluse_event  # noqa: E402

# Heuristic: command "looks like" it should have parsed as a wave-label change
# but `parse_wave_label_changes` returned empty. Used by the parser-skip logger
# to distinguish "no gh issue edit at all" (silent OK) from "had gh issue edit
# AND a canonical wave-label" (worth logging per #455). The regex matches every
# accepted wave-label shape (#810) inside a flag value (quoted, equals-form, or
# spaced-bare): the legacy `p{N}-wave-{M}`, the phase-agnostic `wave-{X}`, and
# the `wave-x` placeholder. Bounded so suffixed labels like `p3-wave-10-special`
# or `wave-10-frozen` do NOT match. Right anchor accepts a closing quote,
# whitespace, OR end-of-string so spaced-bare values at command-EOF (e.g.
# `--add-label p3-wave-11<EOF>`) still trigger the parser-skip detection — #463.
_CANONICAL_WAVE_LABEL_IN_CMD = re.compile(r'["= ](?:p\d+-wave-\d+|wave-(?:\d+|x))(?:["\s]|$)')

ORG = "noorinalabs"
PROJECT_NUMBER = 2

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = REPO_ROOT / ".claude" / ".consulted" / "post_label_change_wave_field_sync"
CACHE_PATH = CACHE_DIR / "project_ids.json"
CACHE_TTL_SECONDS = 3600  # 1 hour

KILL_SWITCH_ENV = "NOORIN_DISABLE_LABEL_SYNC_HOOK"

# Sentinel marker file used to debounce per-session auth-scope warnings —
# ensures we annunaki-log the "project scope missing" advisory only ONCE
# per session, not on every label-edit.
AUTH_WARN_SENTINEL = CACHE_DIR / "auth_scope_warned.marker"


def _kill_switch_active() -> bool:
    """True iff `NOORIN_DISABLE_LABEL_SYNC_HOOK=1` is set in the env.

    Literal `1` only. Empty / unset / `0` / any other value → False.
    Unix-tradition truthy-only.
    """
    return os.environ.get(KILL_SWITCH_ENV, "") == "1"


def _has_project_scope(auth_status_runner=None) -> bool:
    """True iff `gh auth status -h github.com` reports `project` scope.

    The output of `gh auth status -h github.com` includes a line like:
        - Token scopes: 'gist', 'project', 'read:org', 'repo', 'workflow'
    We check for `project` as a complete token (between quotes/commas)
    to avoid `read:project` substring false-positives.

    `auth_status_runner` returns the stdout of the gh-auth-status call
    (tests inject a fake); the default invokes gh directly. Returns
    False if the runner raises (network/auth error) — fail-closed for
    auth-scope.
    """
    if auth_status_runner is None:
        auth_status_runner = _default_auth_status_runner

    try:
        stdout = auth_status_runner()
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False
    if not stdout:
        return False
    # gh auth status writes scope to stderr historically; the runner combines.
    # Match `'project'` (single-quoted, complete token).
    return "'project'" in stdout


def _default_auth_status_runner() -> str:
    """Run `gh auth status -h github.com` and return stdout+stderr combined.

    gh writes the Token-scopes line to stderr; we combine both streams so
    the parser sees it.
    """
    result = subprocess.run(
        ["gh", "auth", "status", "-h", "github.com"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return (result.stdout or "") + (result.stderr or "")


def _read_cache() -> dict | None:
    """Read the cached project-IDs blob if it exists and is fresh.

    Returns the cached dict (with keys: `project_id`, `field_id`,
    `option_ids`, `cached_at`) if the cache file exists and is within
    TTL. Returns None on missing / stale / unreadable cache.
    """
    if not CACHE_PATH.is_file():
        return None
    try:
        blob = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    cached_at = blob.get("cached_at", 0)
    if not isinstance(cached_at, (int, float)):
        return None
    if time.time() - cached_at > CACHE_TTL_SECONDS:
        return None
    return blob


def _write_cache(blob: dict) -> None:
    """Write the project-IDs blob atomically with mode 0600.

    `os.replace` is atomic on POSIX so partial writes never leave a
    truncated cache file. Mode 0600 keeps the cache owner-only.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    blob = {**blob, "cached_at": time.time()}
    tmp = CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(blob, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, CACHE_PATH)


def _bust_cache() -> None:
    """Remove the cache file. Used after a field-not-found error to force
    re-introspection on the next fire."""
    try:
        CACHE_PATH.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass  # best-effort


def _gh_graphql(query: str, variables: dict, runner=None) -> dict | None:
    """Run a GraphQL query via gh. Returns parsed JSON `.data` or None on error.

    `runner(query, variables) -> stdout` is the injection point for tests.
    The default invokes `gh api graphql -F ... -f query=...`.
    """
    if runner is None:
        runner = _default_graphql_runner
    try:
        raw = runner(query, variables)
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed


def _default_graphql_runner(query: str, variables: dict) -> str:
    """Default `gh api graphql` runner. Builds the argv from variables.

    String values pass via `-f key=value`; integer values pass via
    `-F key=value` (gh's typed-int form). Per memory
    `feedback_gh_pr_edit_silent_noop` — use `-F`/`-f` explicitly rather
    than `--input -` for these mutations.
    """
    argv = ["gh", "api", "graphql"]
    for k, v in variables.items():
        if isinstance(v, bool):
            argv += ["-F", f"{k}={'true' if v else 'false'}"]
        elif isinstance(v, int):
            argv += ["-F", f"{k}={v}"]
        else:
            argv += ["-f", f"{k}={v}"]
    argv += ["-f", f"query={query}"]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        return ""
    return result.stdout


_INTROSPECT_QUERY = """
query($org: String!, $project: Int!) {
  organization(login: $org) {
    projectV2(number: $project) {
      id
      field(name: "Wave") {
        ... on ProjectV2SingleSelectField {
          id
          options { id name }
        }
      }
    }
  }
}
"""


def _introspect_project_ids(graphql_runner=None) -> dict | None:
    """Look up `project_id`, `field_id`, and Wave option_ids via GraphQL.

    Returns a dict with the cache-blob shape on success; None on failure.
    """
    data = _gh_graphql(
        _INTROSPECT_QUERY,
        {"org": ORG, "project": PROJECT_NUMBER},
        runner=graphql_runner,
    )
    if not data:
        return None
    proj = (data.get("data") or {}).get("organization", {}).get("projectV2")
    if not proj:
        return None
    project_id = proj.get("id")
    field = proj.get("field") or {}
    field_id = field.get("id")
    options = {opt["name"]: opt["id"] for opt in (field.get("options") or [])}
    if not project_id or not field_id:
        return None
    return {
        "project_id": project_id,
        "field_id": field_id,
        "option_ids": options,
    }


def _get_project_ids(graphql_runner=None) -> dict | None:
    """Return cached IDs if fresh; else introspect, cache, and return."""
    cached = _read_cache()
    if cached:
        return cached
    fresh = _introspect_project_ids(graphql_runner=graphql_runner)
    if fresh:
        _write_cache(fresh)
    return fresh


_ITEM_LOOKUP_QUERY = """
query($org: String!, $repo: String!, $num: Int!) {
  repository(owner: $org, name: $repo) {
    issue(number: $num) {
      projectItems(first: 10) {
        nodes {
          id
          project { number }
        }
      }
    }
  }
}
"""


def _lookup_item_id(repo: str, issue_number: str, graphql_runner=None) -> str | None:
    """Find the project 2 item ID for `noorinalabs/<repo>` issue `<issue_number>`.

    Uses a direct repository→issue→projectItems traversal, which avoids the
    100-item pagination limitation of the old org→projectV2→items scan and
    eliminates the variableNotUsed GraphQL error ($repo/$num were declared
    but never referenced in the old query body).

    PROJECT_NUMBER filtering is done Python-side since the projectItems field
    has no server-side project-number filter argument; the `first: 10` ceiling
    is safe because issues are rarely on more than a handful of projects.
    """
    data = _gh_graphql(
        _ITEM_LOOKUP_QUERY,
        {
            "org": ORG,
            "repo": repo,
            "num": int(issue_number),
        },
        runner=graphql_runner,
    )
    if not data:
        return None
    issue = (data.get("data") or {}).get("repository", {}).get("issue")
    if not issue:
        return None
    nodes = (issue.get("projectItems") or {}).get("nodes") or []
    for node in nodes:
        if (node.get("project") or {}).get("number") == PROJECT_NUMBER:
            return node.get("id")
    return None


_SET_FIELD_MUTATION = """
mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $project,
    itemId: $item,
    fieldId: $field,
    value: { singleSelectOptionId: $option }
  }) {
    projectV2Item { id }
  }
}
"""

_CLEAR_FIELD_MUTATION = """
mutation($project: ID!, $item: ID!, $field: ID!) {
  clearProjectV2ItemFieldValue(input: {
    projectId: $project,
    itemId: $item,
    fieldId: $field
  }) {
    projectV2Item { id }
  }
}
"""


def _wave_label_to_option_name(label: str) -> str | None:
    """Convert a wave label to its project-2 Wave option name.

    Thin wrapper over the shared `_wave_label_parse.wave_label_to_option_name`
    so the EDIT-path (here) and CREATE-path (`auto_add_issue_to_board`, which
    calls this private name) stay on one grammar. Mapping (#810):
    `p3-wave-11` → `P3W11`, `wave-11` → `W11`, `wave-x` → `WX`. Returns None if
    `label` is not a recognized wave label (defensive — callers have already
    validated the shape, but a None here is safer than a wrong option name).
    """
    return wave_label_to_option_name(label)


def _ensure_auth_warned_once(reason: str) -> None:
    """Annunaki-log the auth-scope advisory ONCE per session (debounced)."""
    if AUTH_WARN_SENTINEL.exists():
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    AUTH_WARN_SENTINEL.touch()
    log_posttooluse_event(
        "post_label_change_wave_field_sync",
        "",
        reason,
    )


def _apply_one_change(
    change: WaveLabelChange,
    command: str,
    ids: dict,
    graphql_runner,
) -> dict:
    """Apply a single WaveLabelChange against project 2. Returns a result dict.

    Pre-condition: caller has verified auth scope + ids are present AND has
    resolved `change.repo` to a concrete repo name (the ambient-repo
    resolution loop in `check()` replaces a None repo or drops the change).
    This function is invoked once per change in the multi-cmd loop in
    `check()`.
    """
    # `check()` guarantees repo is resolved before dispatch (see pre-condition).
    assert change.repo is not None
    # POST-edit state semantics: if BOTH add and remove fired in one
    # command, the added value is the post-edit Wave field value.
    target_label: str = change.add_label or change.remove_label or ""
    action_kind = "set" if change.add_label else "clear"

    option_name = _wave_label_to_option_name(target_label)
    if option_name is None:
        # Caller already validated the shape; defensive only.
        log_posttooluse_event(
            "post_label_change_wave_field_sync",
            command,
            f"Internal: wave label {target_label!r} failed option-name conversion "
            f"for {change.repo}#{change.issue_number}.",
        )
        return {
            "action": "skip_no_option",
            "repo": change.repo,
            "issue": change.issue_number,
        }
    option_id = ids.get("option_ids", {}).get(option_name)
    if action_kind == "set" and option_id is None:
        # Missing option → log + skip (board-audit pre-req: option must be
        # pre-created in Project Settings).
        log_posttooluse_event(
            "post_label_change_wave_field_sync",
            command,
            f"Project 2 Wave field has no option {option_name!r} for "
            f"{change.repo}#{change.issue_number}; "
            f"add via Project Settings then re-fire.",
        )
        return {
            "action": "skip_no_option",
            "repo": change.repo,
            "issue": change.issue_number,
            "option_name": option_name,
        }

    item_id = _lookup_item_id(change.repo, change.issue_number, graphql_runner=graphql_runner)
    if item_id is None:
        # Issue not on project 2 — graceful skip; board-audit will sweep.
        # Per #451: log this so /annunaki-attack can pattern-match the skip.
        log_posttooluse_event(
            "post_label_change_wave_field_sync",
            command,
            f"skip_no_item: {change.repo}#{change.issue_number} is not on project 2; "
            f"board-audit will sweep. Hook 13 should have added it on create — "
            f"investigate if recurring.",
        )
        return {
            "action": "skip_no_item",
            "repo": change.repo,
            "issue": change.issue_number,
        }

    if action_kind == "set":
        result = _gh_graphql(
            _SET_FIELD_MUTATION,
            {
                "project": ids["project_id"],
                "item": item_id,
                "field": ids["field_id"],
                "option": option_id,
            },
            runner=graphql_runner,
        )
        if not result or "errors" in (result or {}):
            # Try cache-bust + retry once (field may have been recreated).
            errors_str = json.dumps(result.get("errors") if result else [])
            if "field" in errors_str.lower() or "not found" in errors_str.lower():
                _bust_cache()
                ids2 = _get_project_ids(graphql_runner=graphql_runner)
                option_id2 = (ids2 or {}).get("option_ids", {}).get(option_name)
                if ids2 and option_id2:
                    result2 = _gh_graphql(
                        _SET_FIELD_MUTATION,
                        {
                            "project": ids2["project_id"],
                            "item": item_id,
                            "field": ids2["field_id"],
                            "option": option_id2,
                        },
                        runner=graphql_runner,
                    )
                    if result2 and "errors" not in result2:
                        return {
                            "action": "set",
                            "repo": change.repo,
                            "issue": change.issue_number,
                            "option_name": option_name,
                            "retried_after_cache_bust": True,
                        }
            log_posttooluse_event(
                "post_label_change_wave_field_sync",
                command,
                f"GraphQL set-field mutation failed for {change.repo}#{change.issue_number} "
                f"(option={option_name}); see errors: {errors_str[:300]}",
            )
            return {
                "action": "skip_mutation_failed",
                "repo": change.repo,
                "issue": change.issue_number,
            }
        return {
            "action": "set",
            "repo": change.repo,
            "issue": change.issue_number,
            "option_name": option_name,
        }

    # action_kind == "clear"
    result = _gh_graphql(
        _CLEAR_FIELD_MUTATION,
        {
            "project": ids["project_id"],
            "item": item_id,
            "field": ids["field_id"],
        },
        runner=graphql_runner,
    )
    if not result or "errors" in (result or {}):
        log_posttooluse_event(
            "post_label_change_wave_field_sync",
            command,
            f"GraphQL clear-field mutation failed for {change.repo}#{change.issue_number}.",
        )
        return {
            "action": "skip_mutation_failed",
            "repo": change.repo,
            "issue": change.issue_number,
        }
    return {
        "action": "cleared",
        "repo": change.repo,
        "issue": change.issue_number,
    }


def check(
    input_data: dict,
    auth_status_runner=None,
    graphql_runner=None,
    git_runner=None,
) -> dict | None:
    """Pure decision function. Returns a dict describing the action taken
    (or skipped), or None when the hook does not apply.

    Result shape (always advisory — never blocking). For single-cmd Bash
    the dict is returned as-is. For multi-cmd Bash (#455) the returned
    dict has shape `{"action": "multi", "results": [<per-change result>, ...]}`
    so callers can introspect every dispatched mutation.

    Single-cmd result variants:
      None                                       — hook didn't apply
      {"action": "killed", ...}                  — kill-switch env var set
      {"action": "skip_no_repo_context", ...}    — --repo omitted AND ambient
                                                   repo unresolvable from cwd
      {"action": "skip_no_auth_scope", ...}      — gh missing project scope
      {"action": "skip_no_project_ids", ...}     — introspection failed
      {"action": "skip_no_option", ...}          — wave option missing
      {"action": "skip_no_item", ...}            — issue not on project 2
      {"action": "set", ...}                     — Wave field set
      {"action": "cleared", ...}                 — Wave field cleared
      {"action": "skip_mutation_failed", ...}    — GraphQL mutation error

    Multi-cmd Bash (issue #455):
      {"action": "multi", "results": [...], "count": N}

    Injection points let tests mock external state without mocking
    subprocess: `auth_status_runner()` returns the gh-auth-status output;
    `graphql_runner(query, variables)` returns the gh-api-graphql output;
    `git_runner(cwd)` returns the `origin` remote URL used to resolve the
    ambient repo when a command omits `--repo` (#650).
    """
    if input_data.get("tool_name", "") != "Bash":
        return None

    if _kill_switch_active():
        return {"action": "killed"}

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return None

    changes = parse_wave_label_changes(command)
    if not changes:
        # Per #455 acceptance: if the command "looks like" a wave-label edit
        # (contains `gh issue edit` AND a canonical `p{N}-wave-{M}` flag value)
        # but the parser returned empty, log it as a parser-skip event so
        # silent multi-cmd misses are visible to /annunaki-attack. Suffixed
        # labels (`p3-wave-10-special`) and non-edit `gh` calls are correctly
        # excluded by the regex anchors and substring check.
        if "gh issue edit" in command and _CANONICAL_WAVE_LABEL_IN_CMD.search(command):
            log_posttooluse_event(
                "post_label_change_wave_field_sync",
                command,
                "skip_parser_returned_empty: command contains `gh issue edit` "
                "and a canonical wave-label flag but parser extracted no changes. "
                "Likely an unhandled multi-cmd shape (for-loop with unexpanded "
                "vars, etc.); investigate.",
            )
            return {"action": "skip_parser_returned_empty"}
        return None

    # #650: a `gh issue edit <num> --remove-label "p4-wave-5"` run from inside
    # the target repo carries NO `--repo`; the parser returns the change with
    # repo=None. Mirror gh's own ambient-git-context resolution by recovering
    # the repo from the invocation cwd, otherwise the Wave-field sync silently
    # no-ops (the original #650 symptom). All `--repo`-less changes in one
    # compound command share a single cwd, so resolve at most once.
    ambient_repo: str | None = None
    ambient_resolved = False
    resolved_changes: list[WaveLabelChange] = []
    for change in changes:
        if change.repo is None:
            if not ambient_resolved:
                ambient_repo = resolve_repo_short_name(input_data, git_runner=git_runner)
                ambient_resolved = True
            if ambient_repo is None:
                log_posttooluse_event(
                    "post_label_change_wave_field_sync",
                    command,
                    f"skip_no_repo_context: `gh issue edit {change.issue_number}` omitted "
                    "--repo and the ambient repo could not be resolved from the invocation "
                    "cwd (no git origin); cannot sync Wave field for this change.",
                )
                continue
            change = replace(change, repo=ambient_repo)
        resolved_changes.append(change)

    if not resolved_changes:
        return {
            "action": "skip_no_repo_context",
            "issue": changes[0].issue_number,
            "skipped_count": len(changes),
        }
    changes = resolved_changes

    if not _has_project_scope(auth_status_runner=auth_status_runner):
        _ensure_auth_warned_once(
            "post_label_change_wave_field_sync skipped: gh project scope required; "
            "run 'gh auth refresh -s project' to enable Wave-field auto-sync."
        )
        # Per #451: surface ALL skipped changes' identity in the result.
        return {
            "action": "skip_no_auth_scope",
            "repo": changes[0].repo,
            "issue": changes[0].issue_number,
            "skipped_count": len(changes),
        }

    ids = _get_project_ids(graphql_runner=graphql_runner)
    if not ids:
        log_posttooluse_event(
            "post_label_change_wave_field_sync",
            command,
            f"skip_no_project_ids: failed to introspect project 2 IDs; "
            f"skipping Wave-field sync for {len(changes)} change(s).",
        )
        return {
            "action": "skip_no_project_ids",
            "repo": changes[0].repo,
            "issue": changes[0].issue_number,
            "skipped_count": len(changes),
        }

    # Single-cmd shape: preserve original single-result return for back-compat.
    if len(changes) == 1:
        return _apply_one_change(changes[0], command, ids, graphql_runner)

    # Multi-cmd shape (#455): iterate every change and aggregate results.
    results = [_apply_one_change(c, command, ids, graphql_runner) for c in changes]
    return {"action": "multi", "results": results, "count": len(results)}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    try:
        check(input_data)
    except Exception as e:  # noqa: BLE001
        try:
            log_posttooluse_event(
                "post_label_change_wave_field_sync",
                input_data.get("tool_input", {}).get("command", "")[:500],
                f"Unexpected hook error: {type(e).__name__}: {e}",
            )
        except Exception:
            pass
    sys.exit(0)


if __name__ == "__main__":
    main()
