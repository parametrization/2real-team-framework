#!/usr/bin/env python3
"""Per-reviewer review-load counts for a wave (W11/W12/W13 proposal; #231).

Backs the ``/wave-end`` skill's review-load step: emit how the wave's review
verdicts were spread across reviewers, so lopsided load (one reviewer carrying
most of the verdicts) is a *tracked number* recorded next to concentration —
not something the orchestrator eyeballs by hand.

Layering mirrors ``trust_signals.py`` (and ``promotion-audit/helpers.py``): a
pure counting/render core, callable standalone on hand-built verdict data; a
thin SCM/I-O layer that wires it to the live merged-PR set via ``gh``; a CLI.
The pure core is what the tests mutation-prove — the arithmetic (one verdict
comment per review turn, one distinct PR per reviewer) is the whole value.

Reuse, not re-implementation: verdict parsing and roster identity-folding live
in ``trust_signals`` and are imported here (read-only) so the two never drift on
what a "verdict" is or how ``Nia.Rossi`` / ``Nia Rossi (Staff)`` fold to one
identity. This module never mutates ``trust_signals`` state — it only reads.

A "verdict" is any comment carrying the charter's ``RequestOrReplied:`` line
(see ``team/charter/issues.md``); both ``Request`` and the amended-in-place
``Replied`` forms count as one review turn by that ``Requestor:``. Because the
count is over the *comment*, a reviewer who posts a ``Request`` and later amends
it in place to ``Replied`` is still one verdict on that PR — the amendment
convention (see ``pull-requests.md``) does not inflate the load count.

CLI:
  review_load.py counts <wave> [--label L] [--status PATH]
      Emit per-reviewer review-load as JSON: ``{reviewer: {verdicts,
      prs_reviewed}}``, roster-canonicalized, sorted by reviewer name. Reads the
      live merged-PR set + their verdict comments over ``gh`` — read-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# The skill dir (assets/skills/wave-end or .claude/skills/wave-end) is a sibling of
# hooks/ and lib/ under a common parent (assets/ or .claude/) in BOTH the source tree
# and an installed tree — the same lib->hooks bridge trust_signals.py / helpers.py use.
_SKILL_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _SKILL_DIR.parent.parent
_HOOKS_DIR = _ROOT_DIR / "hooks"
_LIB_DIR = _ROOT_DIR / "lib"
sys.path.insert(0, str(_HOOKS_DIR))
sys.path.insert(0, str(_LIB_DIR))

import trust_signals as ts  # noqa: E402
from _framework_config import config  # noqa: E402


# ---------------------------------------------------------------------------
# Pure counting / rendering core (no I/O)
# ---------------------------------------------------------------------------


@dataclass
class ReviewLoad:
    """One reviewer's load over a wave.

    ``verdicts`` = review turns they authored (each verdict comment counts once,
    whether ``Request`` or the amended ``Replied``). ``prs_reviewed`` = distinct
    PRs they posted at least one verdict on — the load-balance measure.
    """

    verdicts: int = 0
    prs_reviewed: int = 0


def review_load(prs, *, canon=None) -> dict[str, ReviewLoad]:
    """Pure: fold a wave's verdict comments into ``{reviewer: ReviewLoad}``.

    ``prs`` is an iterable of ``(pr_key, author, comment_bodies)`` — ``pr_key``
    any hashable PR identity, ``author`` that PR's author identity (the head
    commit author name the scorer buckets by; may be ``None`` when unknown),
    ``comment_bodies`` the list of that PR's issue-comment body strings.
    ``canon`` is an optional ``name -> canonical_name`` mapper (default
    identity); pass ``trust_signals._canonicalizer(cfg)`` to fold name variants
    to their roster identity exactly as the scorer does.

    Verdicts with no ``Requestor:`` are skipped (nobody to attribute the load
    to). A verdict whose ``Requestor:`` resolves to the PR's own ``author`` is
    author-excluded (#288): the author wearing reviewer grammar on their own PR
    is not a review turn and must not add to anyone's load — the same exclusion
    ``trust_signals`` applies to the scoring signals, via the shared
    :func:`trust_signals.is_author_self_review` helper. Ordering of ``prs`` never
    affects the counts — the result is a pure function of the multiset of
    (reviewer, pr) pairs.
    """
    canon = canon or (lambda n: n)
    out: dict[str, ReviewLoad] = {}
    for pr_key, author, comment_bodies in prs:
        seen_this_pr: set[str] = set()
        for v in ts.parse_verdicts(comment_bodies):
            if not v.requestor:
                continue
            if ts.is_author_self_review(v.requestor, author, canon):
                continue
            name = canon(v.requestor)
            load = out.setdefault(name, ReviewLoad())
            load.verdicts += 1
            if name not in seen_this_pr:
                load.prs_reviewed += 1
                seen_this_pr.add(name)
    return out


def render_counts_line(loads: dict[str, ReviewLoad]) -> str:
    """Pure: a compact one-line review-load summary, sorted by reviewer name.

    e.g. ``review-load (verdicts): Ibrahim El-Amin 1 / Nia Rossi 2 / Paloma
    Gupta 2 / Tariq Morales 1`` — the tracked number the wrapup records next to
    concentration. Empty input yields an explicit ``(no reviewer verdicts)`` so
    the line is never blank.
    """
    if not loads:
        return "review-load (verdicts): (no reviewer verdicts)"
    parts = [f"{name} {loads[name].verdicts}" for name in sorted(loads)]
    return "review-load (verdicts): " + " / ".join(parts)


# ---------------------------------------------------------------------------
# I/O layer (live merged-PR set + verdict comments over gh). Reuses
# trust_signals' gh-backed helpers so the merged-PR set is defined identically
# to the scorer's. Everything above is reusable standalone.
# ---------------------------------------------------------------------------


def extract_review_load(
    wave: str,
    status_path: Path | None = None,
    *,
    label: str | None = None,
    cfg=None,
) -> dict[str, ReviewLoad]:
    """Build ``{reviewer: ReviewLoad}`` for one wave from the live merged-PR set.

    The merged-PR set and identity-folding are exactly ``trust_signals``' — this
    reads its ``merged_prs`` / ``_pr_comment_bodies`` / ``_canonicalizer`` (never
    writes). Reviewer identity is the verdict comment's ``Requestor:`` field,
    canonicalized against the roster.
    """
    cfg = cfg or config()
    prs = ts.merged_prs(wave, status_path, label=label, cfg=cfg)
    canon = ts._canonicalizer(cfg)
    rows = [
        (
            pr["number"],
            pr.get("commit_author_name"),
            ts._pr_comment_bodies(pr["repo"], pr["number"]),
        )
        for pr in prs
    ]
    return review_load(rows, canon=canon)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _default_status() -> Path | None:
    raw = config().get("paths.state_file")
    return Path(raw) if raw else None


def _cmd_counts(args: argparse.Namespace) -> int:
    loads = extract_review_load(args.wave, args.status, label=args.label)
    print(
        json.dumps(
            {name: asdict(load) for name, load in loads.items()},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_counts = sub.add_parser(
        "counts", help="emit per-reviewer review-load (verdicts, prs_reviewed) as JSON"
    )
    p_counts.add_argument("wave", help="iteration / wave id")
    p_counts.add_argument(
        "--label",
        default=None,
        help="optional issue/PR label to additionally filter the merged-PR set",
    )
    p_counts.add_argument(
        "--status",
        type=Path,
        default=_default_status(),
        help="path to the project state file (default: config paths.state_file)",
    )
    p_counts.set_defaults(func=_cmd_counts)
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
