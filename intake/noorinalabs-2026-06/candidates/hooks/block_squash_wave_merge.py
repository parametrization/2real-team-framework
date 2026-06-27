#!/usr/bin/env python3
"""PreToolUse hook: Block `gh pr merge <N> --squash` when the PR's base is a
wave branch (`deployments/phase-{P}/wave-{M}`).

GitHub squash-merge re-authors the single squash commit to the **bare gh
principal** (every persona email `parametrization+First.Last@gmail.com` is a
Gmail +alias of the one `parametrization@gmail.com` account, so GitHub stamps
that account as the squash author and demotes the persona to a `Co-authored-by`
trailer). The persona-authored content commits are lost, and at wave-wrapup the
wave→main integration PR fails the `Verify commit authors are roster members`
gate (`verify_commit_identity.py`, main#627): it runs `git log --no-merges
base..head` and the single-parent squash commit authored as `parametrization`
is NOT carved out by `--no-merges`.

The fix is trivial and unambiguous — use `--merge`, which preserves the
persona content-commit authorship verbatim and lets the bare-principal merge
commit be excluded by `--no-merges`. Because the fix is clean and the failure
mode is real (a red gate at wrapup), this is a **hard block** with a diagnostic
rather than an advisory warning (memory feedback_safety_direction_over_ux_friction).

Scope is narrow: it only blocks when the resolved base is a wave branch, so a
normal `gh pr merge <N> --squash` into `main` (the standard GitHub-flow squash
for feature work) is untouched. Resolving the base requires a `gh pr view`
network call, so this check is ordered LAST in the dispatcher and fails **open**
on any resolution error (offline, gh failure, non-numeric PR token).

Canonical rule: charter `pull-requests.md` § One Merge Model Per Wave +
memory feedback_wave_branch_merge_not_squash (P7W19 #898/#222).

Exit codes:
  0 — allow (not a squash wave-branch merge, or base unresolvable → fail-open)
  2 — block (squash merge into a wave branch)
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shell_parse import (
    find_gh_subcommand,
    iter_command_segments,
    strip_heredocs,
    tokenize,
    walk_flag_values,
)
from annunaki_log import log_pretooluse_block

# A wave branch is exactly `deployments/phase-<P>/wave-<M>` — anchored so a
# feature branch that merely contains the substring does not match.
WAVE_BRANCH_RE = re.compile(r"^deployments/phase-\d+/wave-\d+$")


def _iter_squash_merges(command):
    """Yield ``(pr_number, repo_or_None)`` for each command-position
    ``gh pr merge <N> --squash`` segment in ``command``.

    Routes through the shared `_shell_parse` primitives (main#663 gh-command
    parser invariant) so heredoc bodies, line continuations, and env-prefixes
    are handled identically to the other gh-command hooks. A non-digit PR token
    (e.g. a ``$pr`` loop variable) is skipped — it cannot be resolved to a base
    ref, and the batch-loop merge shape is already guarded by `validate_pr_review`
    (memory feedback_batch_loop_merge_evades).
    """
    body = strip_heredocs(command)
    tokens = tokenize(body)
    if tokens is None:
        return
    for seg in iter_command_segments(tokens):
        gh = find_gh_subcommand(seg)
        if gh is None:
            continue
        _globals, rest = gh
        if rest[:2] != ["pr", "merge"]:
            continue
        # gh accepts both the long `--squash` and the documented short `-s`
        # (cover-all-syntactic-forms, memory feedback_lint_gate_cover_all_syntactic_forms).
        if not ({"--squash", "-s"} & set(rest)):
            continue
        # PR number is the first bare-digit positional after `pr merge`.
        pr = next((t for t in rest[2:] if t.isdigit()), None)
        if pr is None:
            continue
        repo_vals = walk_flag_values(rest, {"--repo", "-R"})
        yield pr, (repo_vals[0] if repo_vals else None)


def _resolve_base_ref(pr, repo, *, runner=None):
    """Return the PR's base branch name, or ``None`` if unresolvable.

    ``runner`` is an injection seam for tests: a callable ``(pr, repo) -> str |
    None``. In production it shells out to ``gh pr view``. Any failure (gh
    missing, network error, non-zero exit, timeout) returns ``None`` so the
    caller fails **open**.
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


def _reason(pr, repo):
    repo_hint = f" --repo {repo}" if repo else ""
    return (
        f"BLOCKED: `gh pr merge {pr} --squash` targets a **wave branch** "
        f"(`deployments/phase-*/wave-*`).\n"
        "Squash-merge re-authors the squash commit to the bare gh principal "
        "(`parametrization`), dropping persona content-commit authorship — the "
        "wave→main integration PR then fails the `Verify commit authors are "
        "roster members` gate at wrapup (main#627).\n\n"
        f"Use `--merge` instead:\n"
        f"  gh pr merge {pr} --merge{repo_hint}\n\n"
        "`--merge` preserves the persona-authored content commits (they pass the "
        "gate) and the bare-principal merge commit is excluded by `--no-merges`.\n"
        "Charter § One Merge Model Per Wave / memory "
        "feedback_wave_branch_merge_not_squash (P7W19 #898/#222)."
    )


def check(input_data, *, base_runner=None):
    """Return a block result dict if a squash-merge into a wave branch is
    detected, else ``None``. ``base_runner`` is forwarded to
    ``_resolve_base_ref`` for tests.
    """
    if input_data.get("tool_name") != "Bash":
        return None
    command = input_data.get("tool_input", {}).get("command", "")
    # Cheap pre-filter: skip all parsing AND the network call unless the command
    # even mentions `merge`. This hook runs on every Bash call, so the common
    # case must be a single substring test. Gating on `merge` (not `--squash`)
    # is required to also catch the short `-s` form of `--squash` — `-s` is too
    # generic to substring-match safely, but every `gh pr merge` contains
    # `merge`. A non-merge command that happens to contain `merge` (e.g.
    # `git merge`) parses cheaply and yields no `gh pr merge` segment → allow,
    # with no network call.
    if "merge" not in command:
        return None
    for pr, repo in _iter_squash_merges(command):
        base = _resolve_base_ref(pr, repo, runner=base_runner)
        if base and WAVE_BRANCH_RE.match(base):
            reason = _reason(pr, repo)
            log_pretooluse_block("block_squash_wave_merge", command, reason)
            return {"decision": "block", "reason": reason}
    return None


def main():
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
