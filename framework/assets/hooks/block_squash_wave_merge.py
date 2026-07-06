#!/usr/bin/env python3
"""PreToolUse hook: block `gh pr merge <N> --squash` into an integration branch.

When commit identity is enforced (personas commit via per-commit ``-c`` flags),
a **squash** merge collapses every persona-authored content commit into a single
squash commit re-authored to the merging principal — the per-author commits are
demoted to ``Co-authored-by`` trailers. For a ``wave-branch`` merge model the
integration → default-branch PR then fails the commit-author identity gate
(``validate_commit_identity`` runs ``git log --no-merges base..head`` and the
single-parent squash commit, authored as the bare principal, is NOT excluded by
``--no-merges``). The fix is to use ``--merge`` (the merge commit IS excluded by
``--no-merges`` and the persona content commits are preserved verbatim).

Config-driven + narrowly scoped:
  * **GATE** — only active when ``identity.enforce`` is true (the failure mode
    only exists when per-author commits matter). Off otherwise → never blocks a
    normal GitHub-flow squash.
  * **Integration-branch match** — the base branch is matched against a regex
    derived from ``branch.integration`` (its ``{phase}`` / ``{wave}`` tokens →
    ``\\d+``). So a squash into the default branch is untouched; only a squash
    into the wave/iteration integration branch is blocked.

Resolving the base needs a ``gh pr view`` call, so this check is ordered LAST in
the dispatcher and fails **open** on any resolution error (offline, gh failure,
non-numeric PR token).

Exit codes:
  0 — allow (identity off, not a squash, base not an integration branch, or
       base unresolvable → fail-open)
  2 — block (squash merge into an integration branch under enforced identity)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _framework_config import config  # noqa: E402
from _framework_log import log_pretooluse_block  # noqa: E402
from _shell_parse import (  # noqa: E402
    find_gh_subcommand,
    iter_command_segments,
    strip_heredocs,
    tokenize,
    walk_flag_values,
)

#: Declares this hook's fail-direction to the dispatcher (#175): an uncaught
#: exception from `check()` allows the command, matching this module's
#: documented "base unresolvable -> fail-open" posture.
FAIL_OPEN = True


def _integration_regex(template: str) -> re.Pattern[str]:
    """Build an anchored regex from a ``branch.integration`` template.

    ``{phase}`` / ``{wave}`` become ``\\d+``; any other ``{token}`` becomes a
    non-slash segment. Everything else is matched literally. So
    ``deployments/phase-{phase}/wave-{wave}`` matches
    ``deployments/phase-7/wave-19`` but not a feature branch that merely
    contains the substring.
    """
    esc = re.escape(template)
    esc = esc.replace(re.escape("{phase}"), r"\d+").replace(re.escape("{wave}"), r"\d+")
    esc = re.sub(r"\\\{[^}]+\\\}", r"[^/]+", esc)  # any remaining {token}
    return re.compile("^" + esc + "$")


def _iter_squash_merges(command: str):
    """Yield ``(pr_number, repo_or_None)`` per command-position
    ``gh pr merge <N> --squash`` segment. Non-digit PR tokens are skipped (they
    cannot be resolved to a base ref)."""
    tokens = tokenize(strip_heredocs(command))
    if tokens is None:
        return
    for seg in iter_command_segments(tokens):
        gh = find_gh_subcommand(seg)
        if gh is None:
            continue
        _globals, rest = gh
        if rest[:2] != ["pr", "merge"]:
            continue
        if not ({"--squash", "-s"} & set(rest)):
            continue
        pr = next((t for t in rest[2:] if t.isdigit()), None)
        if pr is None:
            continue
        repo_vals = walk_flag_values(rest, {"--repo", "-R"})
        yield pr, (repo_vals[0] if repo_vals else None)


def _resolve_base_ref(pr: str, repo: str | None, *, runner=None) -> str | None:
    """Return the PR's base branch name, or None if unresolvable (fail-open).

    ``runner`` is a test injection seam: a callable ``(pr, repo) -> str | None``.
    """
    if runner is not None:
        return runner(pr, repo)
    cmd = ["gh", "pr", "view", str(pr), "--json", "baseRefName", "--jq", ".baseRefName"]
    if repo:
        cmd += ["--repo", repo]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (subprocess.SubprocessError, OSError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def _reason(pr: str, repo: str | None) -> str:
    repo_hint = f" --repo {repo}" if repo else ""
    return (
        f"BLOCKED: `gh pr merge {pr} --squash` targets an **integration branch**.\n"
        "With commit identity enforced, squash-merge re-authors the squash commit to "
        "the merging principal and drops the per-author content commits — the "
        "integration→default PR then fails the commit-author identity gate at wrapup.\n\n"
        f"Use `--merge` instead:\n"
        f"  gh pr merge {pr} --merge{repo_hint}\n\n"
        "`--merge` preserves the per-author content commits (they pass the gate) and the "
        "merge commit is excluded by `--no-merges`."
    )


def check(input_data: dict, *, base_runner=None) -> dict | None:
    """Block result dict if a squash-merge into an integration branch is detected
    (under enforced identity), else None. ``base_runner`` is forwarded for tests."""
    if input_data.get("tool_name") != "Bash":
        return None

    cfg = config(input_data)
    # GATE: only relevant when per-author commit identity is enforced.
    if not cfg.get("identity.enforce", False):
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    # Cheap pre-filter — skip parsing + the network call unless `merge` appears.
    if "merge" not in command:
        return None

    integration_re = _integration_regex(cfg.get("branch.integration", "deployments/wave-{wave}"))
    for pr, repo in _iter_squash_merges(command):
        base = _resolve_base_ref(pr, repo, runner=base_runner)
        if base and integration_re.match(base):
            reason = _reason(pr, repo)
            log_pretooluse_block("block_squash_wave_merge", command, reason, input_data=input_data)
            return {"decision": "block", "reason": reason}
    return None


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
