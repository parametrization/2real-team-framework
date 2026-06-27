#!/usr/bin/env python3
"""PreToolUse hook: Block wave-lifecycle skills until cross-repo audit clears.

The charter mandates (skills.md § Wave Lifecycle — Open-Item Audit) that any
skill claiming a wave is "concluded" / "complete" / "done" must first prove
the cross-repo open-item count is zero OR enumerate an explicit carry-forward
list. P2W9 emitted a "wave-9 parent-repo workstream concluded" handoff with
~22 items still open across child repos; the owner had to prompt to surface
the truth. Per the enforcement-hierarchy principle (hook > skill > charter),
a charter rule that already failed once becomes a hook.

This hook fires on PreToolUse Skill calls for wave-wrapup, wave-retro, and
handoff. It runs the canonical cross-repo audit unconditionally and blocks
the skill's invocation when open items exist without a carry-forward marker
in the skill's `args` payload. The skill's own narrative cannot rationalize
its way past the gate — the args must encode the carry-forward decision
BEFORE the skill is allowed to render.

PostToolUse output-scan was rejected during design review (issue #195 design
comment): by the time PostToolUse fires, the false claim is already on
screen and in the conversation history, defeating the enforcement-hierarchy
point. PreToolUse with audit-execution is the load-bearing surface.

Input Language
==============

Fires on:
    PreToolUse Skill

Matches:
    {tool_name: "Skill", tool_input: {skill: "<name>", args: "..."}}
    where <name> ∈ {"wave-wrapup", "wave-retro", "handoff"}

Does NOT match:
    Skill calls for /ontology-librarian, /session-start, /annunaki, etc.
        (only wave-lifecycle skills are gated; matcher checks
         tool_input.skill exactly against the gated set)
    Bash commands containing "wave-wrapup" / "handoff" as substrings
        (matcher is Skill, not Bash — `tool_name != "Skill"` short-circuits;
         this is the substring-bug guard, sibling of #216)
    Skill calls when wave_active == false in cross-repo-status.json
        (no active wave → no audit possible → allow with system message)

Carry-forward bypass (warn-but-allow):
    The hook scans `tool_input.args` (case-insensitive) for any of:
      - "carry-forward:" or "carry forward:" inline marker
      - "## Carry-forward" / "## Carry forward" markdown heading
      - "#<N> →" / "#<N> -> " arrow patterns naming a destination
    If matched, the audit is informational only — allow with a system
    message summarizing what's being carried.

Block condition:
    matched_skill AND open_count > 0 AND args lacks carry-forward marker

Allow condition:
    Any of:
      - matched_skill is False (different skill, different tool entirely)
      - open_count == 0
      - args contains a carry-forward marker
      - audit shell-out failed for infrastructure reasons (fail-open with
        system warning — see § Failure modes below)

Audit shell-out:
    Iterates the 8 org-known repos (charter skills.md § Audit command),
    running, for EACH accepted wave-label form (#810):
        gh issue list --repo "noorinalabs/<repo>" --state open \\
            --label "<wave-label>" --json number
    The wave id `<N>` is derived from `cross-repo-status.json` field
    `current_wave` (e.g. "wave-16" → "16"); the audit queries BOTH the legacy
    `p<P>-wave-<N>` and the new phase-agnostic `wave-<N>` form and UNIONS the
    issue numbers per repo (gh ANDs multiple `--label` flags, so the forms are
    queried separately). This grandfathers in-flight legacy-labeled issues
    while counting new-scheme issues. Total open count is the sum across repos.

Merge-ready-PR exemption (issue #664, owner-adopted P4W7 retro):
    The `/wave-wrapup` gate had a chicken-and-egg: the wave's own open
    work-issues only close as part of wrapup's merge steps, but the gate
    counted them and blocked wrapup from running — forcing a merge+close
    first then a re-run. Fix: an open wave-labeled issue does NOT count
    against the blocking total if it has a *merge-ready PR targeting the
    wave branch*. "Merge-ready" is defined narrowly to guard against
    false-exempt (acceptance criterion #3):
        - the PR is OPEN and not a draft,
        - its base branch is EXACTLY the active wave branch
          `deployments/phase-<P>/wave-<M>` (derived from the same
          cross-repo-status.json phase/wave that yields the label) — an
          arbitrary PR into main or another branch does NOT qualify,
        - `mergeable == "MERGEABLE"` (no conflicts; UNKNOWN is treated as
          not-ready — conservative),
        - every status check is green (all checks SUCCESS/NEUTRAL/SKIPPED;
          any FAILURE/ERROR/pending → not-ready), and
        - the PR *declares it closes the issue* via a closing keyword in its
          body/title (`Closes #N` / `Fixes #N` / `Resolves #N`, conjugations,
          case-insensitive) — NOT a bare `#N` mention.
    Linkage caveat — why body text and not `closingIssuesReferences`: GitHub
    only registers a closing reference when the PR's base is the repository
    *default* branch. Wave-branch PRs base on `deployments/phase-<P>/wave-<M>`,
    so the structured `closingIssuesReferences` API field is ALWAYS empty for
    exactly the PRs this exemption targets (same root cause as `Closes #N` not
    auto-closing on wave-branch merges — memory feedback_wave_branch_issue_close).
    So we parse the PR's body/title for GitHub's own closing-keyword grammar
    (the same grammar GitHub parses); restricting to closing keywords keeps a
    passing `#N` mention from false-exempting an unrelated issue.
    Implementation: per repo, list open PRs based on the wave branch
    (`gh pr list --base <wave-branch> --json ...,body,title`), keep the
    merge-ready ones, extract their declared-closes issue numbers, and subtract
    that set from the open-issue list before counting. If the wave branch can't
    be derived, or any of the PR queries fail, NO exemption is applied (fail
    toward the stricter count — never false-exempt).

Failure modes (all fail-open with system warning, never block):
    - `gh` not installed / not authenticated → cannot audit, allow.
    - Network/API failure on a single repo → skip that repo, sum the rest.
    - cross-repo-status.json missing or malformed → cannot determine wave,
      allow with warning.
    - current_wave field missing / not a "wave-<N>" string → cannot derive
      label, allow with warning.
    - Wall-clock budget: 8 gh calls × ~1.5s ≈ 12s. settings.json timeout
      should be 30s.

Bypass policy:
    No in-band override flag. The whole point of the hook is to break the
    "this one's fine, just say concluded" rationalization that put the
    P2W9 incident on owner's desk. If the gate fires, the only paths are
    (a) close the open items, (b) add a carry-forward block to args, or
    (c) emergency override by removing the hook entry from settings.json.
    This matches Hook 15's stance (no in-band override).

Exit codes (per Claude Code hook convention):
    0 — allow (not a matched skill, audit zero, args has carry-forward,
        infra failure fail-open)
    2 — block (matched skill, open count > 0, no carry-forward in args)

Promotion provenance:
    memory feedback_honest_audit_over_conclusion_claim (2026-04-22) →
    charter skills.md § Wave Lifecycle — Open-Item Audit (PR #193) →
    this hook (issue #195). Second worked example of the
    memory→charter→hook promotion pipeline ratified 2026-04-19 (Hook 15
    was the first).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annunaki_log import log_pretooluse_block  # noqa: E402

# Skills gated by this hook. Exact match against tool_input.skill.
_GATED_SKILLS = frozenset({"wave-wrapup", "wave-retro", "handoff"})

# Org-known repos for cross-repo audit. Sourced from charter skills.md
# § Audit command. This list MUST stay in sync with that charter section.
_ORG_REPOS = (
    "noorinalabs-main",
    "noorinalabs-isnad-graph",
    "noorinalabs-user-service",
    "noorinalabs-deploy",
    "noorinalabs-design-system",
    "noorinalabs-landing-page",
    "noorinalabs-data-acquisition",
    "noorinalabs-isnad-ingest-platform",
)

# Carry-forward detection patterns (case-insensitive). Any one suffices.
# Anchored loosely — looking for explicit author intent, not accidental phrasing.
_CARRY_FORWARD_PATTERNS = (
    re.compile(r"carry[\s-]forward\s*:", re.IGNORECASE),
    re.compile(r"^#{1,6}\s+carry[\s-]forward\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"#\d+\s*(?:->|→)\s*[A-Za-z_]", re.IGNORECASE),
)

# PR-body/title closing-keyword → issue linkage for the merge-ready-PR
# exemption (#664). GitHub's documented closing keywords (close/closes/closed,
# fix/fixes/fixed, resolve/resolves/resolved), optional colon, then `#<N>`.
# Requires the keyword (not a bare `#N` mention) so a passing reference can't
# false-exempt an unrelated issue. The mandatory `[\s:]+` separator before `#`
# also excludes cross-repo `owner/repo#N` refs (the `#` there is preceded by a
# repo-name char, not whitespace/colon).
_CLOSING_KEYWORD_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?)\b[\s:]+#(\d+)\b",
    re.IGNORECASE,
)

# Path to cross-repo-status.json relative to this hook file.
_STATUS_PATH = Path(__file__).resolve().parent.parent.parent / "cross-repo-status.json"

# gh subprocess timeout per repo (seconds). 8 repos × this = total budget.
_PER_REPO_TIMEOUT_SECONDS = 3


def _read_phase_num(data: dict) -> int | None:
    """Recover the active phase number from a loaded status dict, or None (#831).

    `current_phase` (the live integer) is the AUTHORITATIVE phase pointer. The
    legacy top-level `phase` ("phase-{N}") string was never advanced past
    phase-4 — deriving the wave branch/label from it yielded a wrong
    `deployments/phase-4/...` (#831), so it is retired from the status file. A
    defensive `phase`-string fallback is retained for robustness and to mirror
    the sibling readers `validate_wave_label_evidence._read_current_phase` and
    `post_wave_kickoff_comment._phase_from_status` (#810).
    """
    cp = data.get("current_phase")
    if cp is not None:
        try:
            return int(cp)
        except (TypeError, ValueError):
            pass
    m = re.fullmatch(r"phase-(\d+)", str(data.get("phase", "")))
    if m:
        return int(m.group(1))
    return None


def _read_phase_wave_nums() -> tuple[int, int] | None:
    """Return the active (phase_num, wave_num) from cross-repo-status.json or None.

    Reads `cross-repo-status.json`, requires `wave_active` truthy, and parses
    the authoritative `current_phase` integer (via `_read_phase_num`) and the
    `current_wave` ("wave-<M>") field. Returns None on any failure (missing
    file, malformed JSON, inactive wave, missing or unparseable fields). Single
    source of truth for both the wave *label* and the wave *branch* derivations
    below so they cannot drift apart.
    """
    try:
        data = json.loads(_STATUS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None

    if not data.get("wave_active"):
        return None

    wave_match = re.fullmatch(r"wave-(\d+)", str(data.get("current_wave", "")))
    phase_num = _read_phase_num(data)
    if not wave_match or phase_num is None:
        return None

    return phase_num, int(wave_match.group(1))


def _read_current_wave_labels() -> list[str] | None:
    """Return the active wave's labels in ALL accepted forms, or None.

    Returns BOTH the legacy phase-prefixed `p{N}-wave-{M}` AND the new
    phase-agnostic `wave-{X}` form (#810). The audit must count issues under
    either label so the transition is seamless: in-flight issues labeled the
    legacy way (e.g. this very wave's `p6-wave-16`) and issues created under the
    new scheme (`wave-16`) both register against the active wave. The two share
    the same global wave id `X == M` (Design B #804). Returns None on any
    failure (missing file, malformed JSON, missing fields, unparseable wave).
    """
    nums = _read_phase_wave_nums()
    if nums is None:
        return None
    phase_num, wave_num = nums
    return [f"p{phase_num}-wave-{wave_num}", f"wave-{wave_num}"]


def _read_current_wave_branch() -> str | None:
    """Return the active wave branch (e.g. 'deployments/phase-2/wave-10') or None.

    Derives the branch from the same cross-repo-status.json phase/wave that
    yields the label (see `_read_phase_wave_nums`), so the merge-ready-PR
    exemption (#664) targets exactly the branch the wave's PRs base on.
    Returns None on any failure.
    """
    nums = _read_phase_wave_nums()
    if nums is None:
        return None
    phase_num, wave_num = nums
    return f"deployments/phase-{phase_num}/wave-{wave_num}"


def _open_issue_numbers_for_label(repo: str, label: str) -> list[int] | None:
    """Return open-issue numbers for `noorinalabs/<repo>` filtered by one `label`.

    Returns the list of issue numbers on success (possibly empty), None on
    subprocess failure (gh missing, network error, auth failure).
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                f"noorinalabs/{repo}",
                "--state",
                "open",
                "--label",
                label,
                "--json",
                "number",
            ],
            capture_output=True,
            text=True,
            timeout=_PER_REPO_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    if result.returncode != 0:
        return None

    out = result.stdout.strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None
    try:
        return [int(item["number"]) for item in data]
    except (TypeError, KeyError, ValueError):
        return None


def _open_issue_numbers_for_repo(repo: str, labels: list[str]) -> list[int] | None:
    """Return the UNION of open-issue numbers across each label form (#810).

    `gh issue list --label A --label B` ANDs the labels, so each accepted wave
    label (legacy `p{N}-wave-{M}` AND new `wave-{X}`) is queried separately and
    the results are unioned — an issue carrying EITHER form counts once. Returns
    None if ANY per-label query fails (so the caller fails open per-repo, the
    pre-existing conservative-toward-allow stance), the deduplicated number list
    otherwise.
    """
    union: set[int] = set()
    for label in labels:
        nums = _open_issue_numbers_for_label(repo, label)
        if nums is None:
            return None
        union.update(nums)
    return sorted(union)


def _checks_green(rollup: list | None) -> bool:
    """Return True iff every status check in `rollup` is passing (or none exist).

    `rollup` is the `statusCheckRollup` array from `gh pr list --json`. Each
    element is either a CheckRun (has `conclusion` once `status == COMPLETED`)
    or a StatusContext (has `state`). Green means:
        - CheckRun: status COMPLETED and conclusion in {SUCCESS, NEUTRAL, SKIPPED}
        - StatusContext: state == SUCCESS
    Any pending (non-COMPLETED / PENDING / EXPECTED) or failing check makes the
    whole rollup not-green. An empty/absent rollup is treated as green (no
    checks configured) — the base-branch + linkage guards carry the
    false-exempt protection in that case.
    """
    if not rollup:
        return True
    for check in rollup:
        if not isinstance(check, dict):
            return False
        if "conclusion" in check or "status" in check:
            # CheckRun shape.
            if str(check.get("status", "")).upper() != "COMPLETED":
                return False
            if str(check.get("conclusion", "")).upper() not in {
                "SUCCESS",
                "NEUTRAL",
                "SKIPPED",
            }:
                return False
        elif "state" in check:
            # StatusContext shape.
            if str(check.get("state", "")).upper() != "SUCCESS":
                return False
        else:
            # Unrecognized shape → conservatively not-green (never false-exempt).
            return False
    return True


def _pr_is_merge_ready(pr: dict, wave_branch: str) -> bool:
    """Return True iff `pr` is a merge-ready PR targeting `wave_branch`.

    Narrow definition to guard against false-exempt (issue #664 acceptance #3):
    open + not draft + base == wave_branch + mergeable (no conflicts, not
    UNKNOWN) + all status checks green. The `--base` filter on `gh pr list`
    already constrains the base; this re-checks `baseRefName` defensively so a
    mis-filtered or future call site can't slip an off-branch PR through.
    """
    if not isinstance(pr, dict):
        return False
    if pr.get("isDraft"):
        return False
    if str(pr.get("state", "OPEN")).upper() != "OPEN":
        return False
    if pr.get("baseRefName") != wave_branch:
        return False
    if str(pr.get("mergeable", "")).upper() != "MERGEABLE":
        return False
    return _checks_green(pr.get("statusCheckRollup"))


def _closing_refs_in_text(text: str) -> set[int]:
    """Return the issue numbers a PR's body/title declares it will close.

    Parses GitHub's documented closing-keyword syntax (`Closes #N`, `Fixes #N`,
    `Resolves #N`, and their conjugations, optional colon, case-insensitive).

    Why text and not the structured `closingIssuesReferences` API field:
    GitHub only *registers* a closing reference when the PR's base is the
    repository default branch. Wave-branch PRs base on
    `deployments/phase-<P>/wave-<M>`, so `closingIssuesReferences` is ALWAYS
    empty for exactly the PRs this exemption targets (the same reason
    `Closes #N` doesn't auto-close on wave-branch merges — see memory
    `feedback_wave_branch_issue_close`). The PR body's closing keyword is the
    actual linkage signal for wave PRs, and we parse the *same* keyword grammar
    GitHub itself parses — restricting to closing keywords (not a bare `#N`
    mention) keeps a passing reference from false-exempting an unrelated issue
    (#664 acceptance #3).

    Bare `owner/repo#N` cross-repo refs are intentionally not matched (a
    different repo's issue isn't in this repo's wave-label set anyway).
    """
    if not text:
        return set()
    # Don't treat `org/repo#N` (cross-repo) as a local close — require the `#`
    # to NOT be immediately preceded by a repo-name character.
    return {int(m.group(1)) for m in _CLOSING_KEYWORD_RE.finditer(text)}


def _mergeready_exempt_issues(repo: str, wave_branch: str) -> set[int]:
    """Return the set of issue numbers exempt via a merge-ready wave-branch PR.

    Lists open PRs based on `wave_branch`, keeps the merge-ready ones
    (`_pr_is_merge_ready`), and unions the issues each declares it closes (via
    `_closing_refs_in_text` over body+title). Returns an empty set on PR-list
    failure — failing toward NO exemption keeps the gate strict (never
    false-exempt; issue #664 acceptance #3).
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                f"noorinalabs/{repo}",
                "--state",
                "open",
                "--base",
                wave_branch,
                "--json",
                "number,isDraft,state,baseRefName,mergeable,statusCheckRollup,body,title",
            ],
            capture_output=True,
            text=True,
            timeout=_PER_REPO_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return set()

    if result.returncode != 0:
        return set()

    out = result.stdout.strip()
    if not out:
        return set()
    try:
        prs = json.loads(out)
    except json.JSONDecodeError:
        return set()
    if not isinstance(prs, list):
        return set()

    exempt: set[int] = set()
    for pr in prs:
        if not _pr_is_merge_ready(pr, wave_branch):
            continue
        text = f"{pr.get('body', '') or ''}\n{pr.get('title', '') or ''}"
        exempt |= _closing_refs_in_text(text)
    return exempt


def _count_open_for_repo(repo: str, labels: list[str], wave_branch: str | None) -> int | None:
    """Return the *blocking* open-issue count for `noorinalabs/<repo>`.

    Counts open issues carrying ANY accepted wave-label form in `labels` (#810),
    minus those exempted by a merge-ready PR targeting `wave_branch` (issue
    #664). Returns the integer count on success, None on issue-list subprocess
    failure (so the caller can fail-open on full infrastructure failure). When
    `wave_branch` is None, no exemption is applied (every open wave issue counts).
    """
    numbers = _open_issue_numbers_for_repo(repo, labels)
    if numbers is None:
        return None
    if not numbers:
        return 0
    if wave_branch is None:
        return len(numbers)

    exempt = _mergeready_exempt_issues(repo, wave_branch)
    return sum(1 for n in numbers if n not in exempt)


def _audit_open_count(
    labels: list[str], wave_branch: str | None
) -> tuple[int | None, dict[str, int]]:
    """Run the cross-repo audit. Returns (total_or_None, per_repo_counts).

    `total_or_None` is None only if EVERY repo's audit failed (full
    infrastructure failure → fail-open). Otherwise it's the sum of all
    successfully-audited repos, even if some individual repos failed
    (partial result is more useful than None).

    Each repo's count excludes wave issues exempted by a merge-ready PR on
    `wave_branch` (issue #664). `per_repo_counts` maps repo name → blocking
    count for repos with a non-zero blocking count. Repos with zero blocking
    issues (none open, or all exempted) or with audit failures are omitted.
    """
    per_repo: dict[str, int] = {}
    successes = 0

    for repo in _ORG_REPOS:
        count = _count_open_for_repo(repo, labels, wave_branch)
        if count is None:
            continue
        successes += 1
        if count > 0:
            per_repo[repo] = count

    if successes == 0:
        return None, per_repo

    total = sum(per_repo.values())
    return total, per_repo


def _has_carry_forward(args: str) -> bool:
    """Return True iff `args` contains an explicit carry-forward marker."""
    if not args:
        return False
    return any(pattern.search(args) for pattern in _CARRY_FORWARD_PATTERNS)


def _format_per_repo(per_repo: dict[str, int]) -> str:
    """Format the per-repo open-item summary for block/warning messages."""
    if not per_repo:
        return "  (no per-repo breakdown — all audited repos returned 0)"
    lines = []
    for repo in sorted(per_repo.keys()):
        lines.append(f"  - noorinalabs/{repo}: {per_repo[repo]} open")
    return "\n".join(lines)


def check(input_data: dict) -> dict | None:
    """Check the wave-audit precondition. Returns result dict if blocking, None if allowed.

    Public API matches the dispatcher convention. Returns None to allow,
    a dict with `decision: "block"` to block, or a dict with
    `decision: "allow"` plus `systemMessage` to allow with a warning.
    """
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Skill":
        return None

    tool_input = input_data.get("tool_input", {})
    skill_name = tool_input.get("skill", "")

    if skill_name not in _GATED_SKILLS:
        return None

    labels = _read_current_wave_labels()
    if labels is None:
        return {
            "decision": "allow",
            "systemMessage": (
                f"WARNING: Wave-audit hook could not determine an active wave label "
                f"from cross-repo-status.json. Allowing /{skill_name} to proceed without "
                "an audit. If you are claiming a wave is concluded, run the canonical "
                "audit manually (charter skills.md § Wave Lifecycle — Audit command)."
            ),
        }

    # Display form for messages: both accepted label forms (#810) are queried.
    label_display = " | ".join(f"`{lbl}`" for lbl in labels)

    # Wave branch drives the merge-ready-PR exemption (#664). Derived from the
    # same status fields as the label, so if the label resolved, the branch
    # does too; None only on a race that mutates the file mid-check, in which
    # case the audit simply applies no exemption (stricter, never false-exempt).
    wave_branch = _read_current_wave_branch()

    total, per_repo = _audit_open_count(labels, wave_branch)

    if total is None:
        return {
            "decision": "allow",
            "systemMessage": (
                f"WARNING: Wave-audit hook could not query any of the {len(_ORG_REPOS)} "
                f"org repos for label(s) {label_display} (gh CLI missing, unauthenticated, "
                f"or all calls failed). Allowing /{skill_name} to proceed without an audit. "
                "Run the canonical audit manually before claiming the wave is concluded."
            ),
        }

    if total == 0:
        return None

    args = tool_input.get("args", "")
    if _has_carry_forward(args):
        return {
            "decision": "allow",
            "systemMessage": (
                f"NOTE: {total} open item(s) for {label_display} across {len(per_repo)} "
                f"repo(s); carry-forward marker detected in args, allowing /{skill_name} "
                f"to proceed.\nPer-repo open counts:\n{_format_per_repo(per_repo)}\n"
                "Verify the carry-forward list in your output names every item above."
            ),
        }

    result = {
        "decision": "block",
        "reason": (
            f"BLOCKED: /{skill_name} cannot claim wave conclusion. "
            f"Charter § Wave Lifecycle — Open-Item Audit requires zero open items "
            f"for the active wave OR an explicit carry-forward list in the skill's args.\n\n"
            f"Active wave label(s): {label_display}\n"
            f"Open items across the org: {total}\n"
            f"Per-repo breakdown:\n{_format_per_repo(per_repo)}\n\n"
            "To proceed, either:\n"
            f"  1. Close the open items above, then re-run /{skill_name}, OR\n"
            f"  2. Pass an explicit carry-forward list in args. Recognized markers:\n"
            "     - 'Carry-forward: #N → next-wave, #M → backlog' inline\n"
            "     - '## Carry-forward' markdown heading followed by item list\n"
            "     - '#N → destination' arrow patterns naming items individually\n\n"
            "Note (#664): an open wave issue is already auto-exempt from this count "
            "if it has a merge-ready PR (open, not draft, mergeable, all checks green) "
            f"based on `{wave_branch or '<wave-branch>'}`. The items above are NOT "
            "exempt — their wave-branch PR is missing, conflicting, red, or still in "
            f"review. Get those PRs merge-ready and re-run /{skill_name}.\n\n"
            "There is no in-band bypass flag — see charter/hooks.md § Hook 17 for "
            "emergency procedure."
        ),
    }
    log_pretooluse_block(
        "validate_wave_audit",
        f"skill={skill_name} args={args[:200] if args else '<empty>'}",
        result["reason"],
        tool_name="Skill",
    )
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
