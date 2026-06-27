#!/usr/bin/env python3
"""PreToolUse hook: Validate branch freshness before PR creation.

Blocks the gh-pr-create command if the feature branch is behind the base branch.

Input Language:
  Fires on:      PreToolUse Bash
  Matches:       gh-pr-create [--repo {OWNER/REPO} | -R {OWNER/REPO}]
                              [--base {BASE} | -B {BASE}]
                              [--head {[OWNER:]HEAD} | -H {[OWNER:]HEAD}]
                              [other flags]
  (Above shows the literal token sequence: gh, pr, create.)
  Does NOT match: gh pr list, gh pr view, gh pr checks, gh pr edit, gh pr merge,
                  gh issue create. Also does NOT match --base/--head/--repo
                  substrings that appear INSIDE the value of another flag (e.g.
                  inside --body) -- see Bug #118 below.
  Flag pass-through:
    --repo / -R   -> when present, the freshness check uses the GitHub API
                    compare endpoint against that repo (Bug #118 fix). The
                    cwd-based git fetch / merge-base path is bypassed because
                    the cwd repo may be entirely different from the PR target.
    --base / -B   -> base branch on the target repo (defaults to "main").
    --head / -H   -> feature branch on the target repo. Accepts the
                    OWNER:branch cross-fork form; only the branch part is
                    used. When omitted with --repo, the check skips (we
                    cannot infer head reliably from cwd in that case).
                    Without --repo, the cwd path uses HEAD as before.

Tokenization:
  The command is split with shlex.split(..., posix=True) so quoted argument
  values become single tokens. We walk the token list and only treat a token
  as a flag value when the PRECEDING token is the corresponding flag. Same
  pattern as validate_labels (#113) -- guarantees that text inside a
  --body "..." heredoc cannot leak into base/head/repo extraction.

Cwd handling (#144):
  The local-path freshness check (`is_branch_fresh_local`) MUST anchor its
  `git fetch` / `git merge-base` calls in the user's actual cwd at tool-call
  time, not the hook's parent process cwd. The orchestrator commonly runs
  from the parent repo while a worktree subagent's `gh pr create` targets
  the worktree's branch — anchoring on parent cwd evaluates the wrong
  repo's HEAD against origin. `_shell_parse.resolve_tool_cwd(input_data)`
  returns `input_data["cwd"]` (set by the harness) when present, falling
  back to `os.getcwd()`.

Implicit-repo resolution (#227):
  When `--repo` is omitted, the hook still routes through the API path if
  the cwd's `origin` remote resolves to a known `OWNER/REPO` slug. This
  protects against the cross-cwd misattribution case: orchestrator runs
  `gh pr create` (no --repo) from cwd inside parent repo Y while the actual
  feature branch lives in worktree X targeting repo X. Without implicit-repo
  resolution we'd run `git fetch origin main` in repo Y and get a
  false-positive on Y's stale main. With it, we hit the gh compare API for
  X (the worktree's actual remote) and check its branch correctly.

  Implementation: `_resolve_implicit_repo(cwd)` parses `git -C <cwd> remote
  get-url origin` and extracts `OWNER/REPO` from common github URL forms.
  Returns None on any parse failure → falls back to the legacy local check.

Worktree-subagent cwd recovery (#521):
  The #227 implementation anchored on `resolve_tool_cwd`, i.e. the harness
  stdin `cwd` field. For a worktree subagent that field is captured at
  agent-spawn time and points at the ORCHESTRATOR's directory, not the
  subagent's worktree after it `cd`'d in — so `_resolve_implicit_repo`
  resolved the PARENT repo (`noorinalabs/noorinalabs-main`) and false-blocked
  child-repo `gh pr create` on the parent's stale branch. The workaround was
  passing `--repo` explicitly. The fix here: resolve the invocation cwd via
  `resolve_invocation_cwd`, which recovers the real cwd from a leading
  `cd /worktree && gh pr create` in the command string, plus a `GH_REPO`
  env-var fast-path (gh's own canonical repo override). Both are consulted
  before the (possibly-wrong) stdin cwd. See `_shell_parse` for the chain.

Exit codes:
  0 -- allow (not the matched command, branch is up to date, or check could not run)
  2 -- block (branch is behind base)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo_flag_parse import extract_repo  # noqa: E402
from _shell_parse import (  # noqa: E402
    first_flag_value,
    is_gh_subcommand,
    resolve_invocation_cwd,
    tokenize,
)
from annunaki_log import log_pretooluse_block  # noqa: E402

_BASE_FLAGS = {"--base", "-B"}
_HEAD_FLAGS = {"--head", "-H"}

# Match an OWNER/REPO suffix on a git remote URL. Handles:
#   git@github.com:owner/repo.git
#   https://github.com/owner/repo.git
#   https://github.com/owner/repo
#   ssh://git@github.com/owner/repo.git
_REPO_SLUG_RE = re.compile(r"github\.com[/:]([^/]+/[^/.\s]+?)(?:\.git)?/?$")


def extract_base(command: str) -> str:
    """Extract --base / -B value, default to 'main'."""
    return first_flag_value(command, _BASE_FLAGS) or "main"


def extract_head(command: str) -> str | None:
    """Extract --head / -H value. Strips OWNER: prefix if present."""
    raw = first_flag_value(command, _HEAD_FLAGS)
    if raw and ":" in raw:
        return raw.split(":", 1)[1]
    return raw


def is_branch_fresh_local(base: str, cwd: str | None = None) -> bool:
    """cwd-based check: HEAD contains the latest commit from origin/base.

    `cwd` anchors the subprocess calls so worktree subagents inspect their
    own branch state, not the parent process's git state (#144).
    """
    try:
        subprocess.run(
            ["git", "fetch", "origin", base],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd,
        )
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", f"origin/{base}", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=cwd,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return True


def _repo_from_env() -> str | None:
    """Return a valid OWNER/REPO from the `GH_REPO` env var, or None.

    `gh` itself honors `GH_REPO` as the implicit repo when `--repo` is
    omitted, so when the harness or a subagent has it set it is the most
    authoritative implicit target — more reliable than cwd resolution for a
    worktree subagent (#521). Validated against the same slug shape gh
    accepts (OWNER/REPO, optionally HOST/OWNER/REPO).
    """
    raw = (os.environ.get("GH_REPO") or "").strip()
    if not raw:
        return None
    parts = raw.split("/")
    if len(parts) == 2 and all(parts):
        return raw
    # HOST/OWNER/REPO form — gh accepts a host-qualified slug.
    if len(parts) == 3 and all(parts):
        return "/".join(parts[1:])
    return None


def _resolve_implicit_repo(cwd: str | None) -> str | None:
    """Return the OWNER/REPO of `cwd`'s `origin` remote, or None if not on github.

    Used when the user runs `gh pr create` without `--repo`: the implicit
    target is the cwd's tracked github remote. Anchors the subprocess on
    `cwd` (a worktree may have a different `origin` than the parent repo).
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=cwd,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    url = (result.stdout or "").strip()
    if not url:
        return None
    match = _REPO_SLUG_RE.search(url)
    if not match:
        return None
    return match.group(1)


def _current_branch(cwd: str | None) -> str | None:
    """Return the current branch in `cwd`, or None on failure."""
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=cwd,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip() or None


def is_branch_fresh_remote(repo: str, base: str, head: str) -> bool | None:
    """API-based check: behind_by from gh compare endpoint.

    Returns True if head is at-or-ahead of base, False if behind, None if the
    check could not be performed (network error, missing branch, etc.). None
    is treated as "allow" by callers -- same fail-open behavior as the local
    path.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/compare/{base}...{head}",
                "--jq",
                ".behind_by",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        behind = int(result.stdout.strip())
        return behind == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        return None


def check(input_data: dict) -> dict | None:
    """Check branch freshness. Returns result dict if blocking, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    tokens = tokenize(command)
    if tokens is not None:
        if not is_gh_subcommand(tokens, "pr", "create"):
            return None
    else:
        if not re.search(r"\bgh\s+pr\s+create\b", command):
            return None

    cwd = resolve_invocation_cwd(input_data)
    base = extract_base(command)
    repo = extract_repo(command)
    head = extract_head(command)

    if repo:
        # Explicit --repo target: API path requires --head to know what branch
        # to compare. Without --head we cannot reliably infer; skip.
        if not head:
            return None
        fresh = is_branch_fresh_remote(repo, base, head)
        if fresh is None or fresh:
            return None
        target = f"{repo}:{base}"
        rebase_hint = f"Rebase the head branch onto {target} on the target repo."
    else:
        # No --repo: prefer the implicit-repo API path when we can resolve
        # the target repo. Resolution order (#227 cross-cwd misattribution
        # protection, extended for #521 worktree-subagent cwd recovery):
        #   1. GH_REPO env var — gh's own canonical implicit-repo override.
        #   2. The invocation cwd's `origin` remote (cwd already recovered
        #      from a leading `cd` by resolve_invocation_cwd above).
        # Fall back to the local-cwd path if neither yields a github slug.
        implicit_repo = _repo_from_env() or _resolve_implicit_repo(cwd)
        if implicit_repo:
            implicit_head = head or _current_branch(cwd)
            if not implicit_head:
                # Cannot determine the head branch — fail open (same as
                # explicit --repo without --head).
                return None
            fresh = is_branch_fresh_remote(implicit_repo, base, implicit_head)
            if fresh is None or fresh:
                return None
            target = f"{implicit_repo}:{base}"
            rebase_hint = f"Rebase the head branch onto {target} on the target repo."
        else:
            if is_branch_fresh_local(base, cwd=cwd):
                return None
            target = f"origin/{base}"
            rebase_hint = f"Run: git fetch origin && git merge origin/{base}"

    result = {
        "decision": "block",
        "reason": (
            f"BLOCKED: Your branch is behind {target}. "
            f"Merge or rebase before creating a PR.\n"
            f"{rebase_hint}\n\n"
            "This prevents merge conflicts and ensures CI runs against current code."
        ),
    }
    log_pretooluse_block("validate_branch_freshness", command, result["reason"])
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
