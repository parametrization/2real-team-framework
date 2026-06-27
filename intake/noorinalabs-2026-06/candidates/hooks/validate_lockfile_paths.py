#!/usr/bin/env python3
"""PreToolUse hook: Block commits with local paths in package-lock.json.

Scans staged package-lock.json files for /tmp/ or file:/ references that are
local worktree artifacts and break CI.

Exit codes:
  0 — allow (not a git commit, or no local paths found)
  2 — block (local paths detected in staged lockfiles)
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annunaki_log import log_pretooluse_block


def get_staged_lockfiles() -> list[str]:
    """Return paths of staged package-lock.json files."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        return [f for f in result.stdout.strip().splitlines() if f.endswith("package-lock.json")]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def check_lockfile(path: str) -> list[str]:
    """Check a staged lockfile for local path references. Returns offending lines."""
    offending = []
    try:
        result = subprocess.run(
            ["git", "show", f":{path}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        for i, line in enumerate(result.stdout.splitlines(), 1):
            if re.search(r"/tmp/|file:/", line):
                offending.append(f"  {path}:{i}: {line.strip()}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return offending


def check(input_data: dict) -> dict | None:
    """Check lockfiles for local paths. Returns result dict if blocking, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    if not re.search(r"\bgit\b.*\bcommit\b", command):
        return None

    lockfiles = get_staged_lockfiles()
    if not lockfiles:
        return None

    all_offending = []
    for lf in lockfiles:
        all_offending.extend(check_lockfile(lf))

    if not all_offending:
        return None

    details = "\n".join(all_offending)
    result = {
        "decision": "block",
        "reason": (
            "BLOCKED: Staged package-lock.json contains local path references "
            "(/tmp/ or file:/) that will break CI.\n"
            f"Offending lines:\n{details}\n\n"
            "Fix: Remove the local dependency references and regenerate the lockfile "
            "with `npm install` using the published package version."
        ),
    }
    log_pretooluse_block("validate_lockfile_paths", command, result["reason"])
    return result


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result and result.get("decision") == "block":
        print(json.dumps(result))
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
