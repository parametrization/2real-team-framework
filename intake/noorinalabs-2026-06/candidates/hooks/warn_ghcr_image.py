#!/usr/bin/env python3
"""PreToolUse hook: Warn if GHCR image may not exist before deploy.

Warns (does not block) when `gh workflow run` triggers a deploy-related workflow
and the expected GHCR image might not exist.

gh-command parser invariant (charter `hooks.md` § 7, main#663)
=============================================================
This hook reads the incoming `gh workflow run` command and resolves the target
repo from its `-R`/`--repo` VALUE. Per the invariant it MUST route both the
shape detection and the flag-value extraction through the shared parsers
(`_shell_parse`, `_repo_flag_parse`) rather than ad-hoc regexes:

  * `is_gh_subcommand(tokens, "workflow", "run")` for command-position shape
    detection (a `gh workflow run` inside a quoted arg or heredoc body is not a
    real invocation), and
  * `_repo_flag_parse.extract_repo` for the `-R OWNER/NAME` / `--repo` value
    (handles all four `-R X` / `-R=X` / `--repo X` / `--repo=X` forms and does
    NOT leak an `-R`-shaped token out of a quoted `--field` value — the
    #650/#659/#661 bug class), and
  * `_shell_parse.resolve_repo_short_name` to resolve the flag-OMITTED ambient
    git-context case (mirroring gh) instead of silently dropping it.

main#663 closed the `gh workflow`/`gh api` follow-up that the original
`gh issue`/`gh pr`-scoped invariant deferred.

Exit codes:
  0 — always allow (this is a warning-only hook)
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
    resolve_repo_short_name,
    tokenize,
)

# Deploy-related workflow names/files
DEPLOY_PATTERNS = re.compile(r"deploy|release|cd[.-]|deliver", re.IGNORECASE)

# Map of repo short names to GHCR image paths
REPO_IMAGE_MAP = {
    "noorinalabs-isnad-graph": "ghcr.io/noorinalabs/noorinalabs-isnad-graph",
    "noorinalabs-landing-page": "ghcr.io/noorinalabs/noorinalabs-landing-page",
    "noorinalabs-design-system": "ghcr.io/noorinalabs/noorinalabs-design-system",
    "noorinalabs-data-acquisition": "ghcr.io/noorinalabs/noorinalabs-data-acquisition",
}


def check_ghcr_image(image: str, tag: str = "latest") -> bool:
    """Check if a GHCR image exists via gh api."""
    # Extract org and package name from image path
    # ghcr.io/noorinalabs/noorinalabs-isnad-graph -> noorinalabs/noorinalabs-isnad-graph
    parts = image.replace("ghcr.io/", "").split("/")
    if len(parts) < 2:
        return True  # Can't determine — assume exists

    org = parts[0]
    package = parts[1]

    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"orgs/{org}/packages/container/{package}/versions",
                "--jq",
                ".[0].metadata.container.tags[]",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return True  # API error — don't warn on transient failures
        tags = result.stdout.strip().splitlines()
        return tag in tags or len(tags) > 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return True


def _short_name(repo: str | None) -> str | None:
    """Normalize an `OWNER/NAME` (or bare `NAME`) repo specifier to `NAME`."""
    if not repo:
        return None
    return repo.split("/")[-1] if "/" in repo else repo


def resolve_target_repo(input_data: dict, command: str) -> str | None:
    """Resolve the target repo short-name for a `gh workflow run` command.

    Flag-value first (`-R`/`--repo` via the shared `_repo_flag_parse.extract_repo`,
    which scopes to the actual flag VALUE and ignores `-R`-shaped tokens inside a
    quoted `--field` value), then the flag-OMITTED ambient git-context case
    (`resolve_repo_short_name`, mirroring gh). Returns the bare repo NAME or
    None when neither path resolves — the caller fails open to a generic
    warning rather than silently dropping the command (invariant requirement 2).
    """
    flag_repo = _short_name(extract_repo(command))
    if flag_repo:
        return flag_repo
    return resolve_repo_short_name(input_data)


def check(input_data: dict) -> dict | None:
    """Check GHCR image availability. Returns result dict if warning, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    tokens = tokenize(command)
    if tokens is None or not is_gh_subcommand(tokens, "workflow", "run"):
        return None

    if not DEPLOY_PATTERNS.search(command):
        return None

    repo = resolve_target_repo(input_data, command)
    if not repo:
        return {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Triggering a deploy workflow. Verify the GHCR image "
                "exists before deploying. Run the service's build workflow first "
                "if the image hasn't been published."
            ),
        }

    image = REPO_IMAGE_MAP.get(repo)
    if not image:
        return None

    if not check_ghcr_image(image):
        return {
            "decision": "allow",
            "systemMessage": (
                f"WARNING: GHCR image {image}:latest may not exist. "
                "The deploy may fail. Run the service's build workflow first.\n"
                f"Check: gh api orgs/noorinalabs/packages/container/{repo}/versions"
            ),
        }

    return None


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result is None:
        sys.exit(0)
    print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
