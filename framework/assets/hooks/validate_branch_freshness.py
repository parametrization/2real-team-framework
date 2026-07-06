#!/usr/bin/env python3
"""PreToolUse hook: warn/block on a `gh pr create` whose branch has fallen behind base.

Generic, config-driven port of a P1 donor identified by the noorinalabs
reconciliation audit (`framework/recipes/NOORINALABS_RECONCILE.md` §3d) — 2real's
own memory has long carried "branch-freshness" as deferred tech-debt; this closes
that gap with a genericised, fail-open implementation (not the donor's
noorinalabs-flavored hardcodes).

Input Language
==============
  Fires on:      PreToolUse Bash
  Matches:       gh pr create [--repo {OWNER/REPO} | -R {OWNER/REPO}]
                              [--base {BASE} | -B {BASE}]
                              [--head {[OWNER:]HEAD} | -H {[OWNER:]HEAD}]
                              [other flags]
  Does NOT match: gh pr list/view/checks/edit/merge, gh issue create, or a
                  --base/--head/--repo-shaped substring living INSIDE the value
                  of another flag (e.g. inside --body) — matched via the shared
                  `_shell_parse` tokenizer, not raw regex over the command string.

Flag handling
=============
  --repo / -R   -> when present, freshness is checked via the GitHub API
                   compare endpoint against that repo (cwd-independent). This
                   is required for cross-repo / worktree-subagent invocations
                   where the tool-call cwd is NOT the PR's target repo.
  --base / -B   -> base branch (defaults to `scm.default_branch`, itself
                   defaulting to "main").
  --head / -H   -> feature branch. Accepts the `OWNER:branch` cross-fork form;
                   only the branch part is used. When omitted with --repo, the
                   check is skipped (head cannot be reliably inferred from cwd
                   for a different repo).

Opt-in, config-driven staleness thresholds (policy.*)
=====================================================
  The whole gate is OFF BY DEFAULT: with BOTH knobs at their default 0 the
  hook returns None immediately (no git fetch, no gh API call) — a fresh
  framework install never blocks a downstream adopter's ordinary `gh pr
  create`. Branch-freshness enforcement is opt-in: an operator sets one (or
  both) knobs > 0 to turn it on.

  policy.branch_freshness_max_commits_behind (default 0 = DISABLED)
      When > 0, a branch is stale once it is behind base by MORE than this many
      commits. 0 (the default) DISABLES the commits-behind dimension — matching
      the sibling max_age_days semantics below (both "0"s mean disabled).
  policy.branch_freshness_max_age_days (default 0 = DISABLED)
      When > 0, additionally treat a branch as stale when its merge-base with
      `base` is older than this many days — i.e. it has not synced with base in
      a long time, even if the raw commit-count delta looks small. Only
      evaluated when the branch is behind at all (commits_behind > 0); a branch
      fully caught up with base is never flagged on age alone. Applied on BOTH
      the local (cwd git) and remote (gh API compare) paths.

Fail-open posture
==================
  This is a workflow-hygiene warning, not a security gate: any failure to
  determine freshness (no network, detached HEAD, git/gh missing, malformed
  API response, timeout, ...) ALLOWS the command. Only a POSITIVELY observed
  "behind by more than the threshold" (or "merge-base older than the threshold")
  blocks.

Exit codes:
  0 -- allow (not the matched command, branch is fresh enough, or the check
       could not be performed)
  2 -- block (branch is behind base beyond the configured threshold)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _framework_config import config  # noqa: E402
from _framework_log import log_pretooluse_block  # noqa: E402
from _repo_flag_parse import extract_repo  # noqa: E402
from _shell_parse import (  # noqa: E402
    first_flag_value,
    is_gh_subcommand,
    resolve_invocation_cwd,
    tokenize,
)

_BASE_FLAGS = {"--base", "-B"}
_HEAD_FLAGS = {"--head", "-H"}

_SECONDS_PER_DAY = 86400


def extract_base(command: str, default: str = "main") -> str:
    """Extract --base / -B value, falling back to `default`."""
    return first_flag_value(command, _BASE_FLAGS) or default


def extract_head(command: str) -> str | None:
    """Extract --head / -H value. Strips an OWNER: cross-fork prefix if present."""
    raw = first_flag_value(command, _HEAD_FLAGS)
    if raw and ":" in raw:
        return raw.split(":", 1)[1]
    return raw


def _parse_iso8601(raw: str) -> float | None:
    """Parse a GitHub API ISO-8601 timestamp to a Unix epoch, or None on failure."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _age_days(epoch: float) -> float:
    return max(0.0, (time.time() - epoch) / _SECONDS_PER_DAY)


def is_branch_fresh_local(
    base: str,
    cwd: str | None = None,
    *,
    max_commits_behind: int = 0,
    max_age_days: int = 0,
) -> bool:
    """cwd-based check: is HEAD within the configured staleness threshold of origin/base?

    Both thresholds are OPT-IN: a falsy/0 `max_commits_behind` DISABLES the
    commits-behind dimension (0 == disabled, not zero-tolerance), and a falsy/0
    `max_age_days` disables the age dimension. With both 0 this returns True
    ("fresh enough" / allow) unconditionally. `cwd` anchors the subprocess
    calls so worktree subagents inspect their own branch state, not the parent
    process's git state. Fail-open (returns True) on any subprocess error,
    timeout, or missing git binary.
    """
    try:
        subprocess.run(
            ["git", "fetch", "origin", base],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd,
        )
        counts = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", f"origin/{base}...HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=cwd,
        )
        if counts.returncode != 0:
            return True
        parts = counts.stdout.split()
        if len(parts) != 2:
            return True
        behind = int(parts[0])
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        return True

    if behind == 0:
        return True  # perfectly caught up -- never stale regardless of age

    # 0 == disabled (opt-in), NOT zero-tolerance. Only a POSITIVE threshold
    # arms the commits-behind dimension.
    stale_by_count = max_commits_behind > 0 and behind > max_commits_behind
    stale_by_age = False

    if max_age_days > 0:
        try:
            mb = subprocess.run(
                ["git", "merge-base", f"origin/{base}", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=cwd,
            )
            if mb.returncode == 0 and mb.stdout.strip():
                ts = subprocess.run(
                    ["git", "show", "-s", "--format=%ct", mb.stdout.strip()],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=cwd,
                )
                if ts.returncode == 0 and ts.stdout.strip():
                    epoch = float(ts.stdout.strip())
                    stale_by_age = _age_days(epoch) > max_age_days
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            pass  # age check is best-effort; the count verdict alone still stands

    return not (stale_by_count or stale_by_age)


def _repo_from_env() -> str | None:
    """Return a valid OWNER/REPO from the `GH_REPO` env var, or None.

    `gh` itself honors `GH_REPO` as the implicit repo when `--repo` is omitted,
    so when it is set it is the most authoritative implicit target -- more
    reliable than cwd resolution for a worktree subagent.
    """
    raw = (os.environ.get("GH_REPO") or "").strip()
    if not raw:
        return None
    parts = raw.split("/")
    if len(parts) == 2 and all(parts):
        return raw
    if len(parts) == 3 and all(parts):  # HOST/OWNER/REPO
        return "/".join(parts[1:])
    return None


# OWNER/REPO suffix on a git remote URL:
#   git@github.com:owner/repo.git · https://github.com/owner/repo(.git) ·
#   ssh://git@github.com/owner/repo.git
_REPO_SLUG_RE = re.compile(r"github\.com[/:]([^/]+/[^/.\s]+?)(?:\.git)?/?$")


def _resolve_implicit_repo(cwd: str | None) -> str | None:
    """Return the OWNER/REPO of `cwd`'s `origin` remote, or None if not on github."""
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
    return match.group(1) if match else None


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


def is_branch_fresh_remote(
    repo: str,
    base: str,
    head: str,
    *,
    max_commits_behind: int = 0,
    max_age_days: int = 0,
) -> bool | None:
    """API-based check: behind_by (+ merge-base age) from the gh compare endpoint.

    Both thresholds are OPT-IN (0 == disabled, same as the local path): a
    falsy/0 `max_commits_behind` disables the commits-behind dimension and a
    falsy/0 `max_age_days` disables the age dimension. Returns True if fresh
    enough, False if stale, None if the check could not be performed (network
    error, missing branch, malformed response, ...). None is treated as "allow"
    by callers -- same fail-open posture as the local path.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/compare/{base}...{head}",
                "--jq",
                '{behind: .behind_by, mb_date: .merge_base_commit.commit.committer.date}',
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        behind = int(data["behind"])
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, KeyError, TypeError):
        # ValueError also covers json.JSONDecodeError (a ValueError subclass).
        return None

    if behind == 0:
        return True  # perfectly caught up -- never stale regardless of age

    # 0 == disabled (opt-in), NOT zero-tolerance. Only a POSITIVE threshold
    # arms the commits-behind dimension.
    stale_by_count = max_commits_behind > 0 and behind > max_commits_behind
    stale_by_age = False
    if max_age_days > 0:
        epoch = _parse_iso8601(data.get("mb_date", ""))
        if epoch is not None:
            stale_by_age = _age_days(epoch) > max_age_days

    return not (stale_by_count or stale_by_age)


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

    cfg = config(input_data)
    max_behind = cfg.get("policy.branch_freshness_max_commits_behind", 0) or 0
    max_age_days = cfg.get("policy.branch_freshness_max_age_days", 0) or 0

    # OPT-IN: the gate is OFF by default (both knobs 0 == disabled). When
    # neither dimension is armed, do nothing — no git fetch, no gh API call —
    # so a fresh framework install never blocks an ordinary `gh pr create`.
    if max_behind <= 0 and max_age_days <= 0:
        return None

    default_base = cfg.get("scm.default_branch", "main") or "main"

    cwd = resolve_invocation_cwd(input_data)
    base = extract_base(command, default_base)
    repo = extract_repo(command)
    head = extract_head(command)

    if repo:
        # Explicit --repo target: the API path requires --head to know what
        # branch to compare; without it we cannot reliably infer the head.
        if not head:
            return None
        fresh = is_branch_fresh_remote(
            repo, base, head, max_commits_behind=max_behind, max_age_days=max_age_days
        )
        if fresh is None or fresh:
            return None
        target = f"{repo}:{base}"
        rebase_hint = f"Rebase the head branch onto {target} on the target repo."
    else:
        # No --repo: prefer the implicit-repo API path (GH_REPO env, else the
        # cwd's origin remote) to protect against cross-cwd misattribution
        # (a worktree subagent's real repo differs from the invoking cwd).
        implicit_repo = _repo_from_env() or _resolve_implicit_repo(cwd)
        if implicit_repo:
            implicit_head = head or _current_branch(cwd)
            if not implicit_head:
                return None  # cannot determine head -- fail open
            fresh = is_branch_fresh_remote(
                implicit_repo,
                base,
                implicit_head,
                max_commits_behind=max_behind,
                max_age_days=max_age_days,
            )
            if fresh is None or fresh:
                return None
            target = f"{implicit_repo}:{base}"
            rebase_hint = f"Rebase the head branch onto {target} on the target repo."
        else:
            if is_branch_fresh_local(
                base, cwd=cwd, max_commits_behind=max_behind, max_age_days=max_age_days
            ):
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
    log_pretooluse_block(
        "validate_branch_freshness", command, result["reason"], input_data=input_data
    )
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
