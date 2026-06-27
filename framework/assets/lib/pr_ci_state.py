#!/usr/bin/env python3
"""Deterministic PR CI-readiness query over the merge gate's own classifier.

`validate_pr_ci_status.py` (the gh-pr-merge CI gate) is the canonical authority
on whether a PR's CI is green before `gh pr merge`. But that authority only runs
AT merge time, as a PreToolUse block. There was no query-time way to ASK the
same question — "is this PR's CI actually ready to merge?" — before asserting
merge-readiness in a status message, a board update, or a reviewer hand-off.

This CLI answers that question by REUSING the gate's functions verbatim —
`fetch_checks`, `classify_rollup`, `classify_check`, `check_name` — so the oracle
and the gate cannot drift (the reader and writer share one module). It
deliberately does NOT reimplement the pass/fail/pending/empty taxonomy: a fork
would silently diverge from the gate, and that drift is the exact failure this
reuse exists to prevent. The same config-driven `ci.neutral_pending_check_prefixes`
the gate honours is threaded into the classifier here so a NEUTRAL-means-pending
check is classified identically by both.

The load-bearing rule it pins: an EMPTY `statusCheckRollup` ("no checks
reported") is a HARD not-ready state — NEVER green. Merge-readiness requires the
rollup to be **non-empty AND all-success**. (A silently-dropped workflow trigger
can produce zero runs that a naive "no failing checks" test would wave through.)

Note this oracle treats an empty rollup as not-ready UNCONDITIONALLY — it is the
query-time readiness assertion. The hard PreToolUse merge gate additionally
discriminates the legitimate docs-only empty on fully path-filtered repos so it
does not deadlock their merges; that repo-shape discrimination is a property of
the gate, not of the readiness claim.

Usage:
    python3 lib/pr_ci_state.py <pr_number> --repo <owner/repo>
    python3 lib/pr_ci_state.py <pr_number> --repo <owner/repo> --json

Exit codes:
    0 — CI is READY to merge (non-empty rollup, every check passes)
    1 — CI is NOT READY (empty rollup, or any failing/pending check)
    2 — readiness could not be determined (PR fetch failed)
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

# Reuse the merge gate's canonical classifier. The hook lives at
# <root>/hooks/validate_pr_ci_status.py; this driver lives at <root>/lib/. Put
# the hooks dir on sys.path and import the gate functions directly. There is
# intentionally NO local fallback copy of fetch_checks/classify_rollup: a
# vendored fork would drift from the gate. If the import fails the tool fails
# loudly (exit 2), not silently guesses. (Lower-risk than copying the classifier
# into a shared module — the import keeps a single source of truth.)
_HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))

import validate_pr_ci_status as gate  # noqa: E402
from _framework_config import config  # noqa: E402


def _neutral_pending_prefixes() -> tuple[str, ...]:
    """Configured neutral-means-pending prefixes (same source the gate reads)."""
    raw = config().get("ci.neutral_pending_check_prefixes", []) or []
    return tuple(str(p).lower() for p in raw)


@dataclasses.dataclass
class CiState:
    """Computed CI-readiness for a single PR — the gate's verdict, surfaced."""

    pr_number: str
    repo: str | None
    # One of the gate's taxonomy values: "empty" | "failing" | "pending" | "ready".
    verdict: str
    check_count: int
    failing: list[str]
    pending: list[str]

    def ready(self) -> bool:
        """True iff CI is merge-ready: non-empty rollup AND every check passes.

        An empty rollup ("no checks reported") is NEVER ready — that is the rule
        this oracle exists to pin. Equivalent to verdict == "ready"
        (classify_rollup returns "empty" for an empty rollup, never "ready").
        """
        return self.verdict == "ready"


class CiStateError(Exception):
    """CI readiness could not be determined (maps to CLI exit code 2)."""


def compute_ci_state(pr_number: str, repo: str | None = None) -> CiState:
    """Compute a PR's CI-readiness by replaying the merge gate's classifier.

    Reuses `gate.fetch_checks`, `gate.classify_rollup`, and `gate.classify_check`
    (with the same config-driven neutral-pending prefixes the gate uses) so this
    oracle and the merge gate cannot drift. Raises `CiStateError` when the PR's
    rollup cannot be fetched (exit code 2), distinct from a determinate not-ready
    verdict (exit code 1).
    """
    rollup = gate.fetch_checks(pr_number, repo)
    if rollup is None:
        raise CiStateError(
            f"could not fetch CI status for PR #{pr_number}"
            + (f" in {repo}" if repo else "")
            + " — check the PR number, --repo value, and `gh auth status`."
        )

    prefixes = _neutral_pending_prefixes()
    verdict = gate.classify_rollup(rollup, prefixes)
    failing = [gate.check_name(c) for c in rollup if gate.classify_check(c, prefixes) == "fail"]
    pending = [gate.check_name(c) for c in rollup if gate.classify_check(c, prefixes) == "pending"]

    return CiState(
        pr_number=str(pr_number),
        repo=repo,
        verdict=verdict,
        check_count=len(rollup),
        failing=failing,
        pending=pending,
    )


def _render_text(state: CiState) -> str:
    """Human-readable CI-readiness report."""
    lines: list[str] = []
    pr_label = f"PR #{state.pr_number}" + (f" ({state.repo})" if state.repo else "")
    lines.append(f"{pr_label} — CI is {'READY' if state.ready() else 'NOT READY'}")
    lines.append(f"  verdict: {state.verdict}")
    lines.append(f"  checks reported: {state.check_count}")
    if state.verdict == "empty":
        lines.append(
            "  NOTE: an empty statusCheckRollup ('no checks reported') is a HARD "
            "not-ready state — never green."
        )
    if state.failing:
        lines.append(f"  failing: {', '.join(state.failing)}")
    if state.pending:
        lines.append(f"  pending: {', '.join(state.pending)}")
    return "\n".join(lines)


def _render_json(state: CiState) -> str:
    payload = dataclasses.asdict(state)
    payload["ready"] = state.ready()
    return json.dumps(payload, indent=2, sort_keys=True)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pr_ci_state",
        description=(
            "Query a PR's CI-readiness using the merge gate's own classifier "
            "(validate_pr_ci_status.classify_rollup). Exit 0 if CI is ready "
            "(non-empty rollup, all checks pass), 1 if not ready (empty rollup "
            "or any failing/pending check), 2 if undeterminable."
        ),
    )
    p.add_argument("pr_number", help="PR number to query")
    p.add_argument(
        "--repo",
        default=None,
        help="target repo as OWNER/NAME (e.g. acme/widget); "
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
        state = compute_ci_state(args.pr_number, repo=args.repo)
    except CiStateError as exc:
        print(f"pr_ci_state: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(_render_json(state))
    else:
        print(_render_text(state))
    return 0 if state.ready() else 1


if __name__ == "__main__":
    raise SystemExit(main())
