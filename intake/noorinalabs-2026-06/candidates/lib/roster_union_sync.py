#!/usr/bin/env python3
"""Sync-drift gate: the committed parent roster must cover every child persona.

Why this exists (noorinalabs-main#634)
======================================
The commit-identity gate (`verify_commit_identity.py`) resolves "known roster
names" from the COMMITTED parent roster `.claude/team/roster.json`, which is
maintained as the org-wide UNION manifest (parent team + every child-repo
persona). That manifest is the only thing CI can see — the commit-identity
workflow does a single-repo checkout of `noorinalabs-main`, so sibling child
repos are NOT present (the original bug: a live filesystem scan of sibling
rosters was inert in CI, #634).

A hand-maintained union manifest rots: when a child repo onboards a persona,
nobody is forced to fold that name into the parent roster, and a future
child-persona-authored PR to `main` would be FALSE-BLOCKED by the
commit-identity gate. This module is the drift GATE that keeps the manifest
honest: it fetches each child repo's `roster.json` via the GitHub API and
asserts the committed parent roster is a SUPERSET of the child union, naming
any persona the parent is missing.

It is the roster analogue of `pre_commit_ci_sync.py` — a committed
cross-repo-derived artifact paired with a sync-drift gate that detects when the
artifact has fallen behind its sources.

Non-blocking by design (continue-on-error)
==========================================
Per the org pattern for CI checks over cross-repo-derived artifacts (a single
`noorinalabs-main` PR cannot deterministically reconcile a name that a SIBLING
repo just added, and the GitHub-API fetch is non-hermetic), the CI job that
runs this script is `continue-on-error: true`. A drift finding surfaces as a
red ADVISORY check naming the missing personas to fold into the parent roster;
it does not hard-block the PR. See charter `org_wide_artifact_gate_non_blocking`
(deploy#363/PR396) and `cross_repo_ghcr_registry_auth_proof`.

Fetch is fail-open per child repo: a child with no `roster.json` (e.g. a repo
that keeps only a `roster/` directory of per-member files), a private repo the
CI token cannot read, or a transient API error contributes no names and is
reported as SKIPPED — never a drift failure on its own. Drift is only ever
asserted on names we positively observed in a child roster.

Input Language
==============
CLI:  roster_union_sync.py [--repo-root <dir>] [--repos a,b,c] [--owner <org>]

`--repos` overrides the default child-repo list (used by tests to avoid the
network). `--owner` defaults to `noorinalabs`.

Exit codes (CLI):
    0 — no drift (parent roster covers every observed child persona), or every
        child fetch was skipped (nothing positively observed to compare against)
    1 — drift: at least one observed child persona is missing from the parent
    2 — usage / parent-roster load error
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

# The org's child repos that publish an aggregated `.claude/team/roster.json`.
# Mirrors the repo map in CLAUDE.md. `noorinalabs-deploy` is intentionally
# absent: it keeps only a per-member `roster/` directory (no aggregated
# roster.json), so there is nothing to fetch — its personas are folded into the
# parent roster directly. A child not listed here is simply not cross-checked;
# add it when it grows an aggregated roster.json.
DEFAULT_CHILD_REPOS: tuple[str, ...] = (
    "noorinalabs-isnad-graph",
    "noorinalabs-user-service",
    "noorinalabs-design-system",
    "noorinalabs-data-acquisition",
    "noorinalabs-isnad-ingest-platform",
    "noorinalabs-landing-page",
)

ROSTER_PATH_IN_REPO = ".claude/team/roster.json"


def parent_roster_names(repo_root: Path) -> set[str]:
    """Names in the committed parent roster — the union manifest under test."""
    roster = repo_root / ".claude" / "team" / "roster.json"
    try:
        data = json.loads(roster.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return set()
    return set(data.keys()) if isinstance(data, dict) else set()


def fetch_child_roster(owner: str, repo: str) -> dict[str, str] | None:
    """Fetch a child repo's roster.json via `gh api`, or None if unavailable.

    Returns the parsed name→email mapping, or None when the file does not exist,
    the repo is unreadable by the CI token, or the response cannot be parsed
    (fail-open — the caller treats None as SKIPPED, never as drift).
    """
    try:
        proc = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{owner}/{repo}/contents/{ROSTER_PATH_IN_REPO}",
                "--jq",
                ".content",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    raw = proc.stdout.strip()
    if not raw:
        return None
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        data = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def compute_drift(
    parent_names: set[str], child_rosters: dict[str, dict[str, str]]
) -> dict[str, list[str]]:
    """Return {missing_name: [child repos that have it]} for names absent from parent.

    Pure: the network/IO lives in fetch_child_roster, so this is fully testable
    with injected rosters. A name present in several child repos lists them all.
    """
    missing: dict[str, list[str]] = {}
    for repo, roster in child_rosters.items():
        for name in roster:
            if name not in parent_names:
                missing.setdefault(name, []).append(repo)
    return {name: sorted(repos) for name, repos in sorted(missing.items())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="repo root hosting the parent roster.json")
    parser.add_argument(
        "--owner", default="noorinalabs", help="GitHub org/owner of the child repos"
    )
    parser.add_argument(
        "--repos",
        help="comma-separated child repo list (default: the org's child repos)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).expanduser().resolve()
    parent_names = parent_roster_names(repo_root)
    if not parent_names:
        print(
            f"ERROR: no parent roster names loaded from {repo_root}/{ROSTER_PATH_IN_REPO}.",
            file=sys.stderr,
        )
        return 2

    repos = (
        [r.strip() for r in args.repos.split(",") if r.strip()]
        if args.repos
        else list(DEFAULT_CHILD_REPOS)
    )

    child_rosters: dict[str, dict[str, str]] = {}
    skipped: list[str] = []
    for repo in repos:
        roster = fetch_child_roster(args.owner, repo)
        if roster is None:
            skipped.append(repo)
            print(f"SKIPPED {repo}: no readable {ROSTER_PATH_IN_REPO} (fail-open).")
        else:
            child_rosters[repo] = roster
            print(f"OK      {repo}: {len(roster)} persona(s).")

    drift = compute_drift(parent_names, child_rosters)
    if drift:
        print(
            "\nDRIFT: the committed parent roster .claude/team/roster.json is MISSING "
            "child-repo persona(s) below. Fold each into the parent roster so the "
            "commit-identity gate (verify_commit_identity.py) recognizes them on a "
            "cross-repo main PR (#634):",
            file=sys.stderr,
        )
        for name, owners in drift.items():
            print(f'  - "{name}"  (canonical in: {", ".join(owners)})', file=sys.stderr)
        return 1

    observed = sum(len(r) for r in child_rosters.values())
    if not child_rosters:
        print(
            f"\nNo child roster could be read ({len(skipped)} skipped); "
            "nothing to cross-check. Passing (advisory)."
        )
        return 0
    print(
        f"\nParent roster covers all {observed} observed child persona(s) "
        f"across {len(child_rosters)} repo(s). No drift."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
