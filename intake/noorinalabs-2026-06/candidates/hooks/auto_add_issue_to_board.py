#!/usr/bin/env python3
"""PostToolUse hook: Auto-add newly created GitHub issues to the project board.

When a `gh issue create` command produces output containing a GitHub issue URL,
this hook automatically adds that issue to the Cross-Repo Wave Plan board
(org project #2). When the create call included a canonical wave-label
(`--label "p{N}-wave-{M}"`), the hook also sets the project's Wave
single-select field to match — closing the create-time gap that Hook 21
(`post_label_change_wave_field_sync`) only covered for label-EDIT operations
(issue #450).

This enforces charter § Cross-Repo Wave Plan: "New issues created during a wave
must be added to the board immediately."

Input Language:
  Fires on:      PostToolUse Bash
  Matches:       Bash commands containing `gh issue create` with a noorinalabs
                 issue URL in stdout. If the command's tokenized form has a
                 canonical wave-label `--label "p{N}-wave-{M}"` value, the
                 Wave field sync is ALSO attempted (additive — board-add
                 still happens for non-wave-labeled issues).
  Does NOT match: any non-Bash tool, Bash without `gh issue create`, or
                  `gh issue create` whose output lacks a parseable issue URL
  Flag pass-through: stdin JSON is forwarded verbatim to `check()` by the
                     PostToolUse dispatcher (`post_dispatcher.py`)

Exit codes:
  0 — success or not applicable (not a gh issue create, or already handled)
  Non-zero exit does NOT block (PostToolUse hooks are advisory)

Wave-field sync (issue #450):
==============================

When the command included a wave label and the issue lands on the board,
this hook delegates Wave-field setting to the same GraphQL helpers used by
Hook 21 (`post_label_change_wave_field_sync`). Sharing the helpers means:

  - One auth-scope pre-flight (gh `project` scope required)
  - One project-ID cache (shared with Hook 21 — same TTL, same cache file)
  - Same option-name conversion (`p3-wave-11` → `P3W11`)
  - Same field-not-found retry-after-cache-bust logic

If the wave-label was on the create command but the field-sync fails
(auth-scope missing, mutation error, etc.), the hook still returns the
board-add result and logs the field-sync failure via annunaki. The board
add is the primary action; field sync is secondary.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Delegate field-sync to the Hook 21 helpers — same cache, same auth, same retry.
import post_label_change_wave_field_sync as field_sync_hook  # noqa: E402
from _wave_label_parse import parse_wave_label_create  # noqa: E402
from annunaki_log import log_posttooluse_event  # noqa: E402

# noorinalabs org project number
PROJECT_NUMBER = 2
ORG = "noorinalabs"

_ISSUE_URL_RE = re.compile(r"(https://github\.com/noorinalabs/[^/]+/issues/(\d+))")


def _extract_issue_url_and_number(stdout: str) -> tuple[str, str] | None:
    """Pull the FIRST issue URL out of `gh issue create` stdout.

    Returns `(url, issue_number)` or None when no URL is present. The
    issue number is captured by the regex group so callers don't need to
    re-parse the URL.
    """
    m = _ISSUE_URL_RE.search(stdout)
    if not m:
        return None
    return m.group(1), m.group(2)


def _sync_wave_field_for_create(
    repo: str,
    issue_number: str,
    wave_label: str,
    command: str,
    auth_status_runner=None,
    graphql_runner=None,
) -> dict:
    """Set project 2's Wave field for `<repo>#<issue_number>` to `wave_label`'s
    P{N}W{M} option. Uses the Hook 21 helper surface for cache/auth/mutation.

    Returns a small dict describing the outcome (`set` / various skip
    reasons). All failure paths log via annunaki — see Hook 21 §
    skip-path logging coverage (#451).

    This is the create-time analogue of Hook 21's edit-time `_apply_one_change`
    function. Implemented separately rather than calling `_apply_one_change`
    because the create-time path doesn't have a WaveLabelChange dataclass to
    pass; we construct the equivalent inline so a future extraction can
    consolidate both call sites without changing the helper contract.
    """
    if not field_sync_hook._has_project_scope(auth_status_runner=auth_status_runner):
        field_sync_hook._ensure_auth_warned_once(
            "auto_add_issue_to_board skipped Wave-field sync: gh project scope required; "
            "run 'gh auth refresh -s project' to enable."
        )
        return {"action": "skip_no_auth_scope", "repo": repo, "issue": issue_number}

    ids = field_sync_hook._get_project_ids(graphql_runner=graphql_runner)
    if not ids:
        log_posttooluse_event(
            "auto_add_issue_to_board",
            command,
            f"skip_no_project_ids: failed to introspect project 2 IDs while "
            f"syncing Wave field for {repo}#{issue_number}.",
        )
        return {"action": "skip_no_project_ids", "repo": repo, "issue": issue_number}

    option_name = field_sync_hook._wave_label_to_option_name(wave_label)
    if option_name is None:
        return {"action": "skip_no_option", "repo": repo, "issue": issue_number}
    option_id = ids.get("option_ids", {}).get(option_name)
    if option_id is None:
        log_posttooluse_event(
            "auto_add_issue_to_board",
            command,
            f"skip_no_option: project 2 Wave field has no option {option_name!r} "
            f"for {repo}#{issue_number}; add via Project Settings then re-fire.",
        )
        return {
            "action": "skip_no_option",
            "repo": repo,
            "issue": issue_number,
            "option_name": option_name,
        }

    # gh project item-add returns BEFORE the projectItems query sees the new
    # item in some cases (eventual consistency on the GraphQL side). Retry the
    # item lookup a few times before giving up — Hook 21's edit-time path
    # doesn't need this because by the time `gh issue edit` lands the item
    # has been on the board for some time.
    item_id = None
    for _ in range(3):
        item_id = field_sync_hook._lookup_item_id(repo, issue_number, graphql_runner=graphql_runner)
        if item_id is not None:
            break

    if item_id is None:
        log_posttooluse_event(
            "auto_add_issue_to_board",
            command,
            f"skip_no_item: {repo}#{issue_number} not visible on project 2 "
            f"after item-add + 3 lookup retries. Board-audit will sweep.",
        )
        return {"action": "skip_no_item", "repo": repo, "issue": issue_number}

    result = field_sync_hook._gh_graphql(
        field_sync_hook._SET_FIELD_MUTATION,
        {
            "project": ids["project_id"],
            "item": item_id,
            "field": ids["field_id"],
            "option": option_id,
        },
        runner=graphql_runner,
    )
    if not result or "errors" in (result or {}):
        errors_str = json.dumps(result.get("errors") if result else [])
        log_posttooluse_event(
            "auto_add_issue_to_board",
            command,
            f"GraphQL set-field mutation failed for {repo}#{issue_number} "
            f"(option={option_name}); errors: {errors_str[:300]}",
        )
        return {"action": "skip_mutation_failed", "repo": repo, "issue": issue_number}
    return {
        "action": "set",
        "repo": repo,
        "issue": issue_number,
        "option_name": option_name,
    }


def check(
    input_data: dict,
    auth_status_runner=None,
    graphql_runner=None,
) -> dict | None:
    """Dispatcher-compatible entry point for PostToolUse Bash.

    Returns None when the hook is not applicable; returns a small advisory
    dict (`{"action": "added", "issue_url": ..., "wave_field_sync": {...}}`)
    when the project-board add was attempted. The dispatcher treats non-None
    as advisory only.

    Injection points (mirror Hook 21): `auth_status_runner()` returns the
    gh-auth-status output; `graphql_runner(query, variables)` returns the
    gh-api-graphql output. Tests inject these to avoid hitting the network.
    """
    if input_data.get("tool_name", "") != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    if "gh issue create" not in command and "gh issue create" not in command.replace("  ", " "):
        return None

    # Claude Code's PostToolUse contract passes `tool_response`. Legacy hook
    # fixtures used `tool_output`; we accept both so old tests still pass.
    tool_response = input_data.get("tool_response") or input_data.get("tool_output", {})
    stdout = tool_response.get("stdout", "")
    if not stdout:
        return None

    extracted = _extract_issue_url_and_number(stdout)
    if not extracted:
        return None
    issue_url, issue_number = extracted

    try:
        subprocess.run(
            [
                "gh",
                "project",
                "item-add",
                str(PROJECT_NUMBER),
                "--owner",
                ORG,
                "--url",
                issue_url,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # Don't block on failure — advisory hook

    result: dict = {"action": "added", "issue_url": issue_url}

    # Wave-field sync (#450) — additive, never replaces the board-add result.
    creates = parse_wave_label_create(command)
    if creates:
        # Match the create-segment whose repo agrees with the issue URL. The
        # parser may return multiple create-segments for compound commands;
        # pick the one whose repo matches the URL's repo to avoid mis-syncing
        # in `gh issue create --repo A ... && gh issue create --repo B ...`
        # shapes. A create issued WITHOUT `--repo` (in-repo, ambient
        # resolution — #659) parses with `repo=None`; it cannot match the URL
        # repo by equality, so fall back to the first `repo is None` segment
        # (the ambient create targets exactly the repo the URL reports) and
        # finally `creates[0]`.
        url_repo_match = re.search(r"noorinalabs/([^/]+)/issues/", issue_url)
        url_repo = url_repo_match.group(1) if url_repo_match else None
        chosen = next(
            (c for c in creates if c.repo == url_repo),
            next((c for c in creates if c.repo is None), creates[0]),
        )
        # `chosen.repo` is None for an ambient (#659) create; the created-issue
        # URL is the authoritative repo the issue actually landed in, so prefer
        # it. (No cwd-based `resolve_repo_short_name` is needed on this surface
        # — unlike the EDIT path #650 — because PostToolUse already has the URL.)
        effective_repo = chosen.repo or url_repo
        if not effective_repo:
            # Defensive: PostToolUse only reaches here with a parsed issue URL,
            # so url_repo is normally present. Log rather than silently drop.
            log_posttooluse_event(
                "auto_add_issue_to_board",
                command,
                "skip_no_repo_context: wave-labeled create has no --repo and the "
                f"issue URL {issue_url!r} yielded no repo; cannot sync Wave field.",
            )
            result["wave_field_sync"] = {"action": "skip_no_repo_context"}
        else:
            sync_result = _sync_wave_field_for_create(
                repo=effective_repo,
                issue_number=issue_number,
                wave_label=chosen.add_label,
                command=command,
                auth_status_runner=auth_status_runner,
                graphql_runner=graphql_runner,
            )
            result["wave_field_sync"] = sync_result

    return result


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
                "auto_add_issue_to_board",
                "",
                f"Unexpected hook error: {type(e).__name__}: {e}",
            )
        except Exception:
            pass
    sys.exit(0)


if __name__ == "__main__":
    main()
