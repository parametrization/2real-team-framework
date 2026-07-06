#!/usr/bin/env python3
"""PreToolUse hook: Validate labels before `gh issue create`.

Extracts ``--label`` / ``-l`` values from a ``gh issue create`` command and
verifies each label exists in the target repository before the issue is filed —
so a typo'd / not-yet-created label fails fast with a `gh label create`
suggestion instead of a server-side rejection mid-flow.

Generic + config-light: it has no project-specific values. It reads nothing from
the framework config; the only seam is the shared `_framework_log` audit sink.

Input language:
  Fires on:      PreToolUse Bash
  Matches:       gh issue create [--repo OWNER/REPO | -R OWNER/REPO]
                                 [--label NAME | -l NAME]... [other flags]
  Does NOT match: gh issue list/view/edit, gh label create, gh pr create. Also
                  does NOT treat a `--label` substring INSIDE another flag's
                  value (e.g. inside `--body`) as a label.

Tokenization:
  ``shlex``-tokenized so quoted values are single tokens; a token is only a
  label/repo when the PRECEDING token is the matching flag, so `--body` prose
  cannot leak into the label set. On a tokenize failure (unbalanced quote) the
  gate fails OPEN — `gh` rejects a genuinely-missing label server-side, whereas
  a false block stops valid work.

Exit codes:
  0 — allow (not gh issue create, or all labels exist, or unverifiable)
  2 — block (one or more labels do not exist in the repo)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _framework_log import log_pretooluse_block  # noqa: E402
from _repo_flag_parse import extract_repo  # noqa: E402
from _shell_parse import (  # noqa: E402
    is_gh_subcommand,
    tokenize,
    walk_flag_values,
)

#: Declares this hook's fail-direction to the dispatcher (#175): an uncaught
#: exception from `check()` allows the command rather than blocking on the
#: hook's own bug.
FAIL_OPEN = True

# Flags whose VALUE is a label (comma-separated allowed by gh).
_LABEL_FLAGS = {"--label", "-l"}


def get_existing_labels(repo: str | None = None) -> set[str]:
    """Fetch all existing labels from the repository (empty set on any failure).

    When ``repo`` is provided (OWNER/REPO) it is forwarded to ``gh label list``
    so the labels of the repo the issue is being created in are checked — not the
    cwd-resolved repo.
    """
    try:
        cmd = ["gh", "label", "list", "--limit", "500", "--json", "name"]
        if repo:
            cmd.extend(["--repo", repo])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return set()
        return {label["name"] for label in json.loads(result.stdout)}
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, OSError):
        return set()


def extract_labels(command: str) -> list[str]:
    """Extract label names from ``--label`` / ``-l`` flags only.

    Returns [] (→ allow) when tokenization fails, so quoted `--label` text inside
    `--body`/`--title` prose can never false-block a legitimate create.
    """
    tokens = tokenize(command)
    if tokens is None:
        return []
    labels: list[str] = []
    for raw in walk_flag_values(tokens, _LABEL_FLAGS):
        for label in raw.split(","):
            label = label.strip()
            if label:
                labels.append(label)
    return labels


def check(input_data: dict) -> dict | None:
    """Check labels on gh issue create. Block dict if missing, else None."""
    if input_data.get("tool_name") != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    tokens = tokenize(command)
    if tokens is not None:
        if not is_gh_subcommand(tokens, "issue", "create"):
            return None
    elif not re.search(r"\bgh\s+issue\s+create\b", command):
        return None

    labels = extract_labels(command)
    if not labels:
        return None

    repo = extract_repo(command)
    existing = get_existing_labels(repo=repo)
    if not existing:
        return {
            "decision": "allow",
            "systemMessage": (
                "WARNING: could not fetch existing labels to validate. "
                "Proceeding without validation — run `gh label list` to verify."
            ),
        }

    missing = [label for label in labels if label not in existing]
    if not missing:
        return None

    create_repo_flag = f" --repo {repo}" if repo else ""
    suggestions = "\n".join(f'  gh label create "{label}"{create_repo_flag}' for label in missing)
    repo_note = f" in {repo}" if repo else ""
    result = {
        "decision": "block",
        "reason": (
            f"BLOCKED: the following label(s) do not exist{repo_note}: "
            f"{', '.join(missing)}\n"
            f"Create them first:\n{suggestions}\n\n"
            "Label hygiene: verify labels exist before creating issues."
        ),
    }
    log_pretooluse_block("validate_labels", command, result["reason"], input_data=input_data)
    return result


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result is None:
        sys.exit(0)
    print(json.dumps(result))
    sys.exit(2 if result.get("decision") == "block" else 0)


if __name__ == "__main__":
    main()
