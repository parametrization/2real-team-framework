#!/usr/bin/env python3
"""PreToolUse dispatcher: Single entry point for all Bash PreToolUse hooks.

Instead of 12 separate subprocess invocations per Bash tool call, this
dispatcher runs all hook checks in-process by importing each hook module
and calling its `check()` function.

Each hook module exposes:
    check(input_data: dict) -> dict | None
        Returns None to allow, or a dict with "decision" and "reason"/"systemMessage".

Exit codes:
  0 — allow (all hooks passed, or aggregated warnings)
  2 — block (first blocking hook wins)
"""

import importlib
import json
import sys
from pathlib import Path

# Ensure the hooks directory is on sys.path for imports
_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

# Ordered list of hook modules to run for Bash PreToolUse.
# Order matters: cheap/fast checks first, network-calling checks last.
_BASH_HOOKS = [
    "validate_commit_identity",
    "block_no_verify",
    "block_git_config",
    "block_gh_pr_review",
    "block_stale_tmp_message_file",
    "no_worktree_self_delete",
    "validate_edit_completion",
    "auto_set_env_test",
    "validate_lockfile_paths",
    "validate_labels",
    "validate_wave_label_evidence",
    "validate_review_comment_format",
    "validate_pr_review",
    "validate_pr_ci_status",
    "validate_branch_freshness",
    "validate_workflow_paths_coverage",
    "validate_vps_host",
    "warn_ghcr_image",
    "warn_zsh_wordsplit",
    # Network-calling checks LAST: resolves a PR's base ref via `gh pr view`.
    # Cheap-prefiltered on `--squash` and fails open on any gh error. P7W19.
    "block_squash_wave_merge",
]


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    warnings: list[str] = []

    for module_name in _BASH_HOOKS:
        try:
            mod = importlib.import_module(module_name)
        except ImportError:
            continue  # Skip missing modules gracefully

        check_fn = getattr(mod, "check", None)
        if check_fn is None:
            continue

        try:
            result = check_fn(input_data)
        except Exception:
            continue  # Never let a hook crash block everything

        if result is None:
            continue

        decision = result.get("decision", "allow")

        if decision == "block":
            # First blocker wins — print and exit immediately
            print(json.dumps(result))
            sys.exit(2)

        # Collect warnings/systemMessages from allow decisions
        msg = result.get("systemMessage", "")
        if msg:
            warnings.append(msg)

    # No blockers — emit aggregated warnings if any
    if warnings:
        result = {
            "decision": "allow",
            "systemMessage": "\n\n".join(warnings),
        }
        print(json.dumps(result))

    sys.exit(0)


if __name__ == "__main__":
    main()
