#!/usr/bin/env python3
"""PreToolUse hook: Validate labels before gh issue create.

Extracts --label values from `gh issue create` commands and verifies each
label exists in the repository. Blocks execution if any label is missing.

Input Language:
  Fires on:      PreToolUse Bash
  Matches:       gh issue create [--repo {OWNER/REPO} | -R {OWNER/REPO}]
                                 [--label {NAME} | -l {NAME}]... [other flags]
  Does NOT match: gh issue list, gh issue view, gh issue edit, gh label create,
                  gh pr create. Also does NOT match `--label` substrings that
                  appear INSIDE the value of another flag (e.g. inside `--body`)
                  — see Bug 2 below.
  Flag pass-through:
    --repo / -R   → forwarded to `gh label list` so we query the same repo
                    the user is creating the issue in (Bug 1 fix). Without
                    this, cwd determines which repo's labels are checked,
                    which rejects valid labels when cwd != target repo.
    --label / -l  → only the actual flag values are extracted as labels;
                    comma-separated values inside one flag are split. Body
                    content is NEVER scanned for labels (Bug 2 fix).

Tokenization:
  The command is split with `shlex.split(..., posix=True)` so quoted argument
  values become single tokens. We then walk the token list and only treat a
  token as a label/repo if the PRECEDING token is the corresponding flag.
  This guarantees that text appearing inside a `--body "..."` heredoc/string
  cannot leak into label or repo extraction.

Exit codes:
  0 — allow (not gh issue create, or all labels exist)
  2 — block (missing labels detected)
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo_flag_parse import extract_repo  # noqa: E402
from _shell_parse import (  # noqa: E402
    is_gh_subcommand,
    tokenize,
    walk_flag_values,
)
from annunaki_log import log_pretooluse_block  # noqa: E402

# Flags whose VALUE is a label list (comma-separated allowed by gh).
_LABEL_FLAGS = {"--label", "-l"}


def get_existing_labels(repo: str | None = None) -> set[str]:
    """Fetch all existing labels from the repository.

    When `repo` is provided (OWNER/REPO), forward it to `gh label list` so we
    query the same repo the user is creating the issue in (Bug 1 fix).
    """
    try:
        cmd = ["gh", "label", "list", "--limit", "500", "--json", "name"]
        if repo:
            cmd.extend(["--repo", repo])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return set()
        labels_data = json.loads(result.stdout)
        return {label["name"] for label in labels_data}
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return set()


def extract_labels(command: str) -> list[str]:
    """Extract label names from --label / -l flags ONLY.

    Uses `shlex.split` to tokenize, then walks tokens. Quoted body content,
    code blocks, and any text that is part of another flag's value are
    treated as opaque single tokens and cannot leak into the label set
    (Bug 2 fix). Comma-separated values within a single flag are split.

    Returns an empty list (→ the gate ALLOWS) when shlex tokenization fails
    (e.g. a malformed/unbalanced quote — typically an apostrophe such as
    "gh's" inside a single-quoted `--body`). This is the #661 fix: the prior
    fallback ran a `(?:--label|-l)`-anchored regex over the WHOLE command,
    which scooped label-shaped tokens out of `--body`/`--title` prose (e.g. a
    documented ``--label `p{N}-wave-{M}` `` pattern) and FALSE-BLOCKED a
    legitimate `gh issue create`. Without reliable token boundaries we cannot
    tell a real `--label` flag from one quoted inside body text, so we
    deliberately fail OPEN here: the label-existence check is a best-effort
    pre-flight and `gh` itself rejects a genuinely-missing label server-side,
    whereas a false block stops valid work. We therefore prefer skipping
    validation over over-matching. Comma-separated values within a single
    flag are split.
    """
    tokens = tokenize(command)
    if tokens is None:
        return []

    labels = []
    for raw in walk_flag_values(tokens, _LABEL_FLAGS):
        for label in raw.split(","):
            label = label.strip()
            if label:
                labels.append(label)
    return labels


def check(input_data: dict) -> dict | None:
    """Check labels on gh issue create. Returns result dict if blocking/warning, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    tokens = tokenize(command)
    if tokens is not None:
        if not is_gh_subcommand(tokens, "issue", "create"):
            return None
    else:
        if not re.search(r"\bgh\s+issue\s+create\b", command):
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
                "WARNING: Could not fetch existing labels to validate. "
                "Proceeding without validation. Run `gh label list` to verify."
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
            f"BLOCKED: The following label(s) do not exist{repo_note}: "
            f"{', '.join(missing)}\n"
            f"Create them first:\n{suggestions}\n\n"
            "See charter § GitHub Label Hygiene: verify labels exist before creating issues."
        ),
    }
    log_pretooluse_block("validate_labels", command, result["reason"])
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
    if result.get("decision") == "block":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
