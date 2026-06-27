#!/usr/bin/env python3
"""CI gate: verify a wave-PR's commit author names are known roster members.

Why this exists (noorinalabs-main#627, P4W1 retro change #2)
===========================================================
The per-commit `-c user.name=`/`-c user.email=` convention is enforced at
*commit time* by the `validate_commit_identity.py` PreToolUse hook. But that
hook only sees the literal Bash `git commit` command the agent runs in THIS
harness. Two real evasions still landed commits whose author is NOT a valid
roster persona:

  1. deploy#409 — the PR head commit was authored as the bare gh principal
     `parametrization` (no roster identity). This happens when a commit is
     created outside the hooked Bash path: a GitHub-side merge/squash, a
     `gh` API commit, a web-UI edit, or any tooling that doesn't go through
     `git -c user.name=… commit`. The PreToolUse hook never fired, so an
     unattributed commit reached the branch.
  2. `Kofi Mensah` vs `Kofi Mensah-Williams` — a cross-repo persona
     divergence. The PreToolUse hook accepts BOTH (both are in the parent
     roster), so it cannot catch "the wrong one of two near-identical names
     was used in this repo." That is a roster-canonicalization concern, but
     the *first* line of defence is still "every author name resolves to
     SOME known roster member" — a typo'd or stale persona that is in
     NEITHER form fails here.

This module is the *landed-state* gate that closes the gap the commit-time
hook structurally cannot: it inspects the author name of every non-merge
content commit a PR introduces and asserts each is a recognized roster name
(merge commits are excluded — GitHub authors them as the bare principal by
design; see `authors_in_range`). It runs in CI on the
PR, where the actual committed author metadata — not the intended `-c` flag —
is the ground truth.

What "known roster name" means
==============================
The authoritative name set is the **committed parent roster**
`<repo_root>/.claude/team/roster.json`, maintained as the org-wide UNION
manifest: it carries the parent (`noorinalabs-main`) team PLUS every
child-repo persona, since a cross-repo wave PR may legitimately carry an
author who is canonical in a sibling repo (charter
`child_repo_implementer_rule`). We assert membership of the *name* only, not
the name→email pairing (the commit-time hook already gates the email pairing
for hook-path commits, and this gate must accept child-repo personas whose
email canonically lives in the child roster).

Why the committed parent roster — not a live sibling scan (#634)
----------------------------------------------------------------
An earlier version merged the parent roster with a filesystem scan of sibling
child-repo `roster.json` files. That scan is **inert in CI**: the workflow does
a single-repo checkout of `noorinalabs-main` only, so no sibling directories
exist and the CI-effective set silently collapsed to the parent roster — while
passing LOCALLY (where siblings are checked out), a local-vs-CI divergence that
gave false confidence (#634). The fix makes the committed parent roster the
single hermetic source of truth, so the gate behaves identically locally and in
CI. A separate **continue-on-error** sync-drift gate
(`.claude/lib/roster_union_sync.py`) fetches each child `roster.json` via the
GitHub API and fails (advisorily) when the committed union has fallen behind a
child roster — that is the mechanism that keeps this manifest complete over
time, mirroring the `pre_commit_ci_sync.py` committed-mirror + sync-gate
pattern.

`parametrization` / `Steven French` handling
=============================================
The bare gh principal author shows up as the git author name `parametrization`
(the GitHub account login) — NOT a roster *name*. `Steven French` (the owner)
IS a roster name and is allowed. So a commit authored literally as
`parametrization` fails (that is exactly the deploy#409 evasion), while the
owner committing as `Steven French` passes.

Input Language
==============
CLI:  verify_commit_identity.py --base <ref> --head <ref> [--repo-root <dir>]
      verify_commit_identity.py --authors "Name A,Name B" [--repo-root <dir>]

`--base`/`--head` resolve the commit range `base..head` via `git log
--no-merges` and collect the distinct non-merge author names. `--authors`
accepts a pre-resolved
comma-separated list (used by CI when the range is computed by the workflow,
and by tests). Exactly one of (`--base`+`--head`) or `--authors` is required.

Exit codes (CLI):
    0 — every author name is a known roster member
    1 — at least one author name is NOT a known roster member
    2 — usage / git / roster-load error
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# The git author name the bare gh principal commits as. It is the GitHub
# account LOGIN, not a roster persona, so it must never be treated as valid
# even though `Steven French` (the human owner) is a roster name. Listed
# explicitly so the failure message can name it as the canonical evasion.
GH_PRINCIPAL_LOGIN = "parametrization"


def _read_roster(roster_path: Path) -> dict[str, str]:
    """Read one roster.json, returning {} on any failure (fail-open).

    A malformed or unreadable roster must never crash the gate; it just
    contributes no names. The parent roster yielding an empty set is the only
    consequential case, handled by the caller (an empty name set is treated as
    a load error, not a pass).
    """
    try:
        data = json.loads(roster_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def load_known_names(repo_root: Path) -> set[str]:
    """Return the known author NAMES from the committed parent roster.

    The single hermetic source of truth is `<repo_root>/.claude/team/roster.json`,
    maintained as the org-wide UNION manifest (parent team + every child-repo
    persona — see the module docstring). We deliberately do NOT scan sibling
    child-repo rosters from the filesystem: that scan is inert in CI's
    single-repo checkout while passing locally, a divergence that gave false
    confidence (#634). The committed parent roster reads identically in both
    environments; `roster_union_sync.py` is the continue-on-error gate that
    keeps it complete as child rosters evolve.

    Returns the set of all known author NAMES (roster keys).
    """
    parent_roster = repo_root / ".claude" / "team" / "roster.json"
    return set(_read_roster(parent_roster).keys())


def authors_in_range(base: str, head: str, repo_root: Path) -> list[str]:
    """Return the distinct author names of the NON-MERGE commits in `base..head`.

    Uses `git log --no-merges base..head --format=%an` so every introduced
    content commit is covered — not just the single head commit. This is
    strictly stronger than the issue's "head-commit" framing: a non-roster
    author ANYWHERE in the PR's introduced content commits is a violation,
    which catches a mid-stack bad author that a head-only check would miss.

    Why `--no-merges` (PR #630 review, Santiago Ferreira)
    ----------------------------------------------------
    Under this org's merge strategy (`allow_merge_commit: true`), every
    GitHub-side merge commit is authored by the bare gh principal
    `parametrization` BY GITHUB'S DESIGN — the merger has no roster identity to
    stamp. Counting merge commits would false-block every legitimate
    wave-branch→main PR (the every-wave-merges-to-main flow), every per-issue
    merge into a wave branch, and any feature PR brought up to date via
    "Update with merge commit". A merge commit's tree is the only thing GitHub
    controls; the actual INTRODUCED CONTENT always lives in the non-merge
    commits, which is exactly where a bad author must be caught. `--no-merges`
    therefore drops the false positives without reopening the gap — the
    deploy#409 evasion was a CONTENT (non-merge) head commit authored as
    `parametrization`, which `--no-merges` still catches.

    Order is preserved (newest first) and de-duplicated.
    """
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "log", "--no-merges", f"{base}..{head}", "--format=%an"],
        capture_output=True,
        text=True,
        check=True,
    )
    seen: set[str] = set()
    ordered: list[str] = []
    for line in proc.stdout.splitlines():
        name = line.strip()
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def check_authors(authors: list[str], known_names: set[str]) -> list[str]:
    """Return the list of author names that are NOT known roster members.

    The bare gh principal login is rejected even if it somehow appeared in a
    roster, because it is the unattributed-commit signature (#627 case 1); we
    treat it as never-valid by removing it from the accepted set.
    """
    accepted = known_names - {GH_PRINCIPAL_LOGIN}
    return [a for a in authors if a not in accepted]


def _resolve_authors(args: argparse.Namespace, repo_root: Path) -> list[str]:
    """Resolve the author list from either --authors or the --base/--head range."""
    if args.authors is not None:
        return [a.strip() for a in args.authors.split(",") if a.strip()]
    return authors_in_range(args.base, args.head, repo_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="base ref of the PR commit range")
    parser.add_argument("--head", help="head ref of the PR commit range")
    parser.add_argument(
        "--authors",
        help="comma-separated pre-resolved author names (alternative to --base/--head)",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="repo root hosting the parent roster.json (default: cwd)",
    )
    args = parser.parse_args(argv)

    if args.authors is None and not (args.base and args.head):
        parser.error("provide either --authors or both --base and --head")

    repo_root = Path(args.repo_root).expanduser().resolve()

    known_names = load_known_names(repo_root)
    if not known_names:
        print(
            f"ERROR: no roster names loaded from {repo_root}/.claude/team/roster.json "
            "(or it is empty/malformed). Cannot verify commit identity.",
            file=sys.stderr,
        )
        return 2

    try:
        authors = _resolve_authors(args, repo_root)
    except subprocess.CalledProcessError as exc:
        print(
            f"ERROR: git log failed resolving the commit range: {exc.stderr.strip()}",
            file=sys.stderr,
        )
        return 2

    if not authors:
        # No introduced commits (e.g. an empty range). Nothing to verify;
        # a no-op PR is not an identity violation.
        print("No commits in range to verify; passing.")
        return 0

    unknown = check_authors(authors, known_names)
    if unknown:
        print(
            "BLOCKED: the following commit author name(s) are NOT recognized roster members:",
            file=sys.stderr,
        )
        for name in unknown:
            if name == GH_PRINCIPAL_LOGIN:
                print(
                    f"  - {name!r}  (bare gh principal — an unattributed commit "
                    "that bypassed the per-commit `-c user.name=` identity convention; "
                    "this is the deploy#409 evasion)",
                    file=sys.stderr,
                )
            else:
                print(
                    f"  - {name!r}  (not in any parent or child roster.json — a "
                    "typo'd, stale, or cross-repo-divergent persona)",
                    file=sys.stderr,
                )
        print(
            "\nEvery commit author in a wave PR must be a known roster name. "
            "Re-author the offending commit(s) with a roster identity, e.g.:\n"
            '  git -c user.name="Aino Virtanen" '
            '-c user.email="parametrization+Aino.Virtanen@gmail.com" commit --amend\n'
            "See noorinalabs-main#627 for the rationale and the two evasions "
            "this gate closes.",
            file=sys.stderr,
        )
        return 1

    print(f"All {len(authors)} commit author name(s) are known roster members.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
