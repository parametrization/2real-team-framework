#!/usr/bin/env python3
"""PreToolUse hook: gate `gh pr ready` / `gh pr merge` on N-reviewer approval.

SHIPS DORMANT (owner decision, #195)
====================================
`policy.reviewers_required=1` is already live on this repo, so a *live* review
gate would block THIS team's own merges during the very wave that ships it.
Therefore the whole gate is behind a new **`policy.pr_review_gate_enabled` flag
defaulting `false`**: with the flag unset/false this hook is a pure no-op — it
ALLOWS every `gh pr ready` / `gh pr merge` unconditionally. Activation is a
deliberate later follow-up; nothing here enables it.

Thin over S1's oracle
=====================
When the flag is `true`, the gate is deliberately THIN over `lib/pr_review_state`
(#194): it does NOT re-parse review comments (that is `trust_signals`' single
verdict grammar, consumed by the oracle). It just asks the oracle for the PR's
N-reviewer approval state and blocks a `ready`/`merge` when
``state != "approved"`` — i.e. `approvals < reviewers_required` OR an unresolved
`Must-fix:` verdict stands. The block reason names the failed criterion
(approvals X/N, or the enumerated unresolved Must-fix list).

FAIL_OPEN posture (Wave-3 dispatcher convention, #175)
======================================================
Declared ``FAIL_OPEN = True``: an uncaught error must never hard-block the
team's own workflow. `check()` additionally catches oracle / repo-PR-resolution
errors itself and ALLOWS (returns None) rather than relying only on the
dispatcher's crash handling — an inability to *evaluate* the gate is never a
block. An error must never manufacture a false "not approved" that stops a merge.

Exit codes:
  0 — allow (not a gated command, gate dormant, approved, or a fail-open
      degradation: unresolvable repo/PR or an oracle error)
  2 — block (gate enabled AND the oracle reports the PR is not approved)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# The oracle lives in the sibling canonical lib tree (framework/assets/lib in
# place; .claude/lib when deployed). Both hooks/ and lib/ go on sys.path so this
# gate can consume S1's oracle wherever the framework is installed.
_LIB = os.path.join(os.path.dirname(_HERE), "lib")
for _p in (_HERE, _LIB):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _framework_config import config  # noqa: E402
from _framework_log import log_pretooluse_block  # noqa: E402
from _repo_flag_parse import extract_repo  # noqa: E402
from pr_review_state import APPROVED, review_state  # noqa: E402  (consume the oracle; no re-parse)

#: Declares this hook's fail-direction to the dispatcher (#175): an uncaught
#: exception allows the command rather than blocking on the hook's own bug. The
#: gate's whole point is to never hard-block the team on its own infrastructure.
FAIL_OPEN = True

#: The config flag that arms the gate. Unset/false => dormant no-op (ship state).
GATE_FLAG = "policy.pr_review_gate_enabled"

# `gh pr ready` and `gh pr merge` are the two state transitions this gate covers
# (marking a draft ready-for-review, and merging). Matched per shell segment so a
# chained command (`... && gh pr merge`) is still caught, and a leading
# VAR=val env prefix is stripped first.
_GATED_VERB_RE = re.compile(r"gh\s+pr\s+(ready|merge)\b")
_SEGMENT_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||\||;)\s*")
_ENV_PREFIX_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+")


def gated_verb(command: str) -> str | None:
    """Return 'ready' or 'merge' if *command* runs a gated gh verb, else None."""
    for segment in _SEGMENT_SPLIT_RE.split(command):
        stripped = segment.lstrip()
        while _ENV_PREFIX_RE.match(stripped):
            stripped = _ENV_PREFIX_RE.sub("", stripped)
        m = _GATED_VERB_RE.match(stripped)
        if m:
            return m.group(1)
    return None


def extract_pr_number(command: str) -> str | None:
    """Best-effort literal PR number from a gated command (positional or URL)."""
    m = re.search(r"\bgh\s+pr\s+(?:ready|merge)\s+(\d+)", command)
    if m:
        return m.group(1)
    m = re.search(r"/pull/(\d+)", command)
    if m:
        return m.group(1)
    return None


def _gh_json_value(args: list[str], jq: str) -> str | None:
    """Run `gh <args> --jq <jq>` and return the trimmed stdout, or None on any error."""
    try:
        result = subprocess.run(
            ["gh", *args, "--jq", jq],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def resolve_repo(command: str) -> str | None:
    """OWNER/NAME for the command: an explicit --repo/-R, else the cwd default."""
    repo = extract_repo(command)
    if repo:
        return repo
    return _gh_json_value(["repo", "view", "--json", "nameWithOwner"], ".nameWithOwner")


def resolve_pr(command: str, repo: str | None) -> str | None:
    """Literal PR number: an explicit positional/URL, else the current branch's PR."""
    pr = extract_pr_number(command)
    if pr:
        return pr
    args = ["pr", "view"]
    if repo:
        args += ["--repo", repo]
    args += ["--json", "number"]
    return _gh_json_value(args, ".number")


def _block_reason(verb: str, pr_display: str, state: dict) -> str:
    """Human reason naming the criterion that failed (Must-fix list, or X/N)."""
    approvals = state.get("approvals", 0)
    required = state.get("reviewers_required", 0)
    unresolved = state.get("unresolved_must_fix") or []
    lines = [
        f"BLOCKED: PR {pr_display} is not approved (review state: "
        f"{str(state.get('state', 'pending')).upper()}); `gh pr {verb}` is gated by "
        f"{GATE_FLAG}=true.",
    ]
    if unresolved:
        lines.append(
            f"Unresolved Must-fix verdict(s): {len(unresolved)} must be resolved before merge —"
        )
        for entry in unresolved:
            who = entry.get("requestor") or "(unknown reviewer)"
            lines.append(f"  - changes requested by {who}")
        lines.append(
            "Amend each blocking review in place to a clean verdict "
            "(RequestOrReplied: Replied / Must-fix: None) once the fix lands, then retry."
        )
    else:
        needed = max(required - approvals, 0)
        lines.append(
            f"Approvals: {approvals}/{required} required — needs {needed} more distinct "
            "approving reviewer(s) (a clean verdict comment per charter issues.md) before merge."
        )
    return "\n".join(lines)


def check(input_data: dict) -> dict | None:
    """Gate a `gh pr ready`/`merge`. None => allow; block dict => deny (exit 2)."""
    if input_data.get("tool_name") != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    verb = gated_verb(command)
    if verb is None:
        return None

    # SHIP-DORMANT (#195): the whole gate is opt-in. Unset/false => no-op ALLOW.
    if not config(input_data).get(GATE_FLAG, False):
        return None

    # Enabled: evaluate. Any resolution/oracle error fail-opens to ALLOW — an
    # inability to evaluate the gate must never hard-block the team's workflow.
    try:
        repo = resolve_repo(command)
        pr = resolve_pr(command, repo)
        if not repo or not pr:
            return None  # cannot identify the PR → fail-open allow
        state = review_state(repo, int(pr))
    except Exception:  # noqa: BLE001 — fail-open: degrade to allow, never block on our bug
        return None

    if state.get("state") == APPROVED:
        return None

    reason = _block_reason(verb, f"#{pr}", state)
    result = {"decision": "block", "reason": reason}
    log_pretooluse_block("validate_pr_review", command, reason, input_data=input_data)
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
