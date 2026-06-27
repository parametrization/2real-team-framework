#!/usr/bin/env python3
"""Deterministic PR review-state query over the merge gate's own logic (#707).

`validate_pr_review.py` (Hook 4) is the canonical authority on whether a PR
satisfies the 2-reviewer / TechDebt / wave-bootstrap-exception requirements
before `gh pr merge`. But that authority only runs AT merge time, as a
PreToolUse block. There was no way to ASK the same question ahead of time:

  - before spawning reviewers — is this PR already reviewed, and by whom?
  - before `gh pr merge`   — will the gate pass, or who is missing TechDebt?

This CLI answers that question by REUSING the hook's functions verbatim —
`get_pr_data`, `extract_branch_author_lastname`, `check_comment_reviews`,
`_load_roster_names`, and `is_single_reviewer_exception`. It deliberately does
NOT reimplement the charter-comment parsing: a fork would silently drift from
the gate, and that drift is the exact failure #707 exists to prevent. The
PASS/FAIL verdict computed here mirrors `validate_pr_review.check()` step for
step (formal + roster-filtered comment reviewers, the wave-merge head-ref
sentinel, the single-reviewer exception, and the missing-TechDebt block).

Usage:
    python3 .claude/lib/pr_review_state.py <pr_number> --repo <owner/repo>
    python3 .claude/lib/pr_review_state.py <pr_number> --repo <owner/repo> --json

Exit codes:
    0 — the merge gate would PASS (>=2 distinct Approved reviewers, or exactly
        one with the wave-bootstrap exception, and no verdict missing TechDebt)
    1 — the merge gate would BLOCK (too few reviewers, or a verdict missing the
        TechDebt line)
    2 — review state could not be determined (PR fetch failed, or a named child
        repo's roster could not be resolved — mirrors the hook's hard-block)
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

# Reuse the merge gate's canonical logic. The hook lives at
# .claude/hooks/validate_pr_review.py; this driver lives at .claude/lib/. Put
# the hooks dir on sys.path and import the gate functions directly (same
# reader/writer-share-one-module pattern annunaki_parse.py uses for
# annunaki_log). There is intentionally NO local fallback copy: a vendored fork
# of check_comment_reviews would drift from the gate, which is the whole bug
# #707 closes. If the import fails the tool should fail loudly, not guess.
_HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))

import validate_pr_review as gate  # noqa: E402

# The two-distinct-reviewer threshold the gate enforces (charter line 36).
REVIEW_THRESHOLD = 2


@dataclasses.dataclass
class ReviewState:
    """Computed review state for a single PR — the gate's verdict, surfaced."""

    pr_number: str
    repo: str | None
    head_ref: str
    branch_author_lastname: str | None
    # Distinct Approved reviewers (full names, lowercased — the gate's dedup key).
    formal_reviewers: list[str]
    comment_reviewers: list[str]  # roster-valid comment-based Approved reviewers
    non_roster_requestors: list[str]  # Approved Requestors filtered out as non-roster
    distinct_reviewer_count: int  # formal | roster comment, the gate's count
    wave_bootstrap_exception: bool
    reviews_missing_tech_debt: list[str]
    tech_debt_issue_numbers: list[str]

    def passes(self) -> bool:
        """True iff `validate_pr_review` would ALLOW the merge.

        Mirrors `check()`: pass when there are >=2 distinct reviewers, OR
        exactly one reviewer who qualifies for the wave-bootstrap single-
        reviewer exception — AND no verdict is missing its TechDebt line.
        """
        if self.reviews_missing_tech_debt:
            return False
        if self.distinct_reviewer_count >= REVIEW_THRESHOLD:
            return True
        return self.distinct_reviewer_count == 1 and self.wave_bootstrap_exception


class ReviewStateError(Exception):
    """Review state could not be determined (maps to CLI exit code 2)."""


def compute_review_state(pr_number: str, repo: str | None = None) -> ReviewState:
    """Compute a PR's review state by replaying the merge gate's own logic.

    Reuses `gate.get_pr_data`, `gate.extract_branch_author_lastname`,
    `gate.check_comment_reviews`, `gate._load_roster_names`, and
    `gate.is_single_reviewer_exception` so this driver and Hook 4 cannot drift.

    Raises `ReviewStateError` when the PR cannot be fetched or a named child
    repo's roster cannot be resolved — the determinate-failure cases the gate
    hard-blocks on (exit code 2), distinct from a gate FAIL (exit code 1).
    """
    pr_data = gate.get_pr_data(pr_number, repo=repo)
    if pr_data is None:
        raise ReviewStateError(
            f"could not fetch PR #{pr_number}"
            + (f" in {repo}" if repo else "")
            + " — check the PR number, --repo value, and `gh auth status`."
        )

    author = pr_data["author"]
    reviews = pr_data["reviews"]
    head_ref = pr_data["headRefName"]
    number = pr_data["number"]
    labels = pr_data["labels"]

    # Formal GitHub reviews from non-authors (not roster-filtered — these are
    # platform-authenticated identities, exactly as the gate treats them).
    formal_reviewers: set[str] = set()
    for review in reviews:
        login = review.get("author", {}).get("login", "")
        if login and login != author:
            formal_reviewers.add(login.lower())

    # Resolve head ref -> branch-author lastname, then fetch comment reviews.
    # Mirrors check() lines 845-854: a normal feature branch yields a lastname;
    # a wave-merge head (deployments/phase-N/wave-M) has no implementer author,
    # so the gate passes an empty sentinel that admits any non-empty reviewer.
    comment_result = gate.CommentReviewResult()
    branch_author_lastname = None
    if head_ref:
        branch_author_lastname = gate.extract_branch_author_lastname(head_ref)
        if branch_author_lastname:
            comment_result = gate.check_comment_reviews(number, branch_author_lastname, repo=repo)
        elif head_ref.startswith("deployments/") and "/wave-" in head_ref:
            comment_result = gate.check_comment_reviews(number, "", repo=repo)

    # Filter comment-based Approved reviewers against the roster (gate #498):
    # only real roster personas count toward the threshold. A missing child
    # roster is a hard-block in the gate, surfaced here as ReviewStateError.
    try:
        roster_names = gate._load_roster_names(repo=repo)
    except gate.RosterResolutionError as exc:
        raise ReviewStateError(
            f"child-repo roster could not be resolved for --repo '{repo}': {exc}"
        ) from exc

    non_roster = {r for r in comment_result.reviewers if r not in roster_names}
    roster_comment_reviewers = comment_result.reviewers - non_roster

    distinct = formal_reviewers | roster_comment_reviewers

    wave_bootstrap = gate.is_single_reviewer_exception(labels, distinct, repo=repo)

    return ReviewState(
        pr_number=str(number),
        repo=repo,
        head_ref=head_ref,
        branch_author_lastname=branch_author_lastname,
        formal_reviewers=sorted(formal_reviewers),
        comment_reviewers=sorted(roster_comment_reviewers),
        non_roster_requestors=sorted(non_roster),
        distinct_reviewer_count=len(distinct),
        wave_bootstrap_exception=wave_bootstrap,
        reviews_missing_tech_debt=list(comment_result.reviews_missing_tech_debt),
        tech_debt_issue_numbers=list(comment_result.tech_debt_issue_numbers),
    )


def _render_text(state: ReviewState) -> str:
    """Human-readable review-state report."""
    lines: list[str] = []
    pr_label = f"PR #{state.pr_number}" + (f" ({state.repo})" if state.repo else "")
    verdict = "PASS" if state.passes() else "BLOCK"
    lines.append(f"{pr_label} — merge gate would {verdict}")
    lines.append(f"  head ref: {state.head_ref or '(unknown)'}")
    lastname = state.branch_author_lastname or "(none — wave-merge / unmatched)"
    lines.append(f"  branch-author lastname: {lastname}")

    approved = state.comment_reviewers + state.formal_reviewers
    lines.append(
        f"  distinct Approved reviewers: {state.distinct_reviewer_count}/{REVIEW_THRESHOLD}"
        f" required — {', '.join(approved) if approved else '(none)'}"
    )
    if state.comment_reviewers:
        lines.append(f"    comment-based: {', '.join(state.comment_reviewers)}")
    if state.formal_reviewers:
        lines.append(f"    formal GitHub: {', '.join(state.formal_reviewers)}")
    if state.non_roster_requestors:
        lines.append(
            "    excluded (non-roster Approved Requestors): "
            + ", ".join(state.non_roster_requestors)
        )

    lines.append(
        "  wave-bootstrap single-reviewer exception: "
        + ("APPLIES" if state.wave_bootstrap_exception else "no")
    )

    if state.reviews_missing_tech_debt:
        lines.append(
            "  verdicts MISSING the TechDebt line: " + ", ".join(state.reviews_missing_tech_debt)
        )
    else:
        lines.append("  verdicts missing TechDebt line: none")

    if state.tech_debt_issue_numbers:
        lines.append(
            "  TechDebt issue numbers: " + ", ".join(f"#{n}" for n in state.tech_debt_issue_numbers)
        )
    else:
        lines.append("  TechDebt issue numbers: none")

    return "\n".join(lines)


def _render_json(state: ReviewState) -> str:
    payload = dataclasses.asdict(state)
    payload["passes"] = state.passes()
    payload["threshold"] = REVIEW_THRESHOLD
    return json.dumps(payload, indent=2, sort_keys=True)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pr_review_state",
        description=(
            "Query a PR's review state using the merge gate's own logic "
            "(validate_pr_review.check_comment_reviews). Exit 0 if the gate "
            "would pass, 1 if it would block, 2 if undeterminable."
        ),
    )
    p.add_argument("pr_number", help="PR number to query")
    p.add_argument(
        "--repo",
        default=None,
        help="target repo as OWNER/NAME (e.g. noorinalabs/noorinalabs-main); "
        "default uses the cwd-resolved repo",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON instead of the text report",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        state = compute_review_state(args.pr_number, repo=args.repo)
    except ReviewStateError as exc:
        print(f"pr_review_state: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(_render_json(state))
    else:
        print(_render_text(state))
    return 0 if state.passes() else 1


if __name__ == "__main__":
    raise SystemExit(main())
