#!/usr/bin/env python3
"""Sync-drift gate: the committed parent roster must cover every child persona.

Generic, config-driven port of a P1 donor identified by the noorinalabs
reconciliation audit (`framework/recipes/NOORINALABS_RECONCILE.md` §3c). The
donor hardcoded a fixed tuple of noorinalabs's own child-repo names and always
fetched them via the GitHub API; this port instead resolves the child set from
the framework config (`project.repos` / `scm.owner`, the SAME knobs
`framework/install/roster_gen.py` reads) and prefers a LOCAL read of a child's
roster.json when the child is checked out on disk, falling back to the GitHub
API only when it is not -- covering both the "meta+children all cloned
locally" shape (e.g. the install-quality harness's real-repo provisioner) and
the "CI checked out only the meta repo" shape the donor targeted.

Why this exists
================
`validate_commit_identity.py` resolves "known roster names" via a LIVE
one-level parent-merge off the local filesystem (`_load_merged_roster`): when
the target repo has its own roster.json, it is merged with its immediate
parent's roster.json on disk, child wins. That live merge works perfectly when
both directories are present in the SAME checkout. It does NOT help a CI job
that only checks out the meta repo (or the child repo) alone -- the sibling
directory simply is not there, so the merge silently degrades to "whichever
roster exists locally", and a persona onboarded in one child roster can be
invisible to a commit-identity check running against just the meta repo.

This module is the drift GATE that keeps the meta roster.json honest as an
org-wide union manifest: it reads (or fetches) each child's roster.json and
asserts the parent's committed roster.json is a SUPERSET of every observed
child persona, naming any name the parent is missing.

Reconciliation with roster_gen.py / roster_consistency_check.py
=================================================================
`framework/install/roster_gen.py` (`partition_for_children`) computes the
meta ∪ child union AT INSTALL TIME and writes each child's own roster.json
plus the meta roster's allowlist so that `meta ∪ child` covers the org from
day one (see memory `reference_per_child_union_rosters`). This module verifies
that contract keeps holding AFTER install: a child onboarding a new persona
later (or a hand-edit to the meta roster.json that drops a name a child still
uses) is caught as drift here. It does not reimplement or duplicate the
partition/write logic -- it is a read-only checker over whatever committed
manifests exist, complementing (not replacing) roster_gen's write-time model.
`roster_consistency_check.py` is the sibling check for the ORTHOGONAL axis:
roster.json <-> roster/*.md intra-repo consistency (not cross-repo coverage).

Non-blocking by design (continue-on-error)
============================================
A single PR to the meta repo cannot deterministically reconcile a persona a
SIBLING child repo just added, and the GitHub-API fetch is non-hermetic (rate
limits, private-repo auth). The CI job that runs this script should be wired
`continue-on-error: true` -- a drift finding surfaces as an advisory check
naming the missing personas to fold into the parent roster; it does not
hard-block the PR.

Fetch is fail-open per child: a child with no roster.json, a repo the token
cannot read, or a transient API error contributes no names and is reported as
SKIPPED -- never a drift failure on its own. Drift is only ever asserted on
names positively observed in a child roster (local or remote).

Input Language
==============
CLI: roster_union_sync.py [--repo-root <dir>] [--owner <org>] [--repos a,b,c]

`--repos` overrides child-repo resolution (also used by tests to avoid the
filesystem/network). Without it, children are resolved from the framework
config's `project.repos` (minus the repo's own directory name), falling back
to local subdirectories that are themselves git repos (mirrors
`roster_gen.detect_child_repos`'s "child = immediate subdir with its own
.git" rule) when no config is found. `--owner` defaults to `scm.owner` from
the framework config; remote fallback is skipped (not attempted) for any
child when no owner can be resolved.

Exit codes (CLI):
    0 -- no drift (parent roster covers every observed child persona), or
         every child lookup was skipped (nothing positively observed)
    1 -- drift: at least one observed child persona is missing from the parent
    2 -- usage / parent-roster load error

Stdlib only; no deps.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

# lib/roster_union_sync.py -> hooks/ (sibling dir) for the shared config loader.
_HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))

from _framework_config import config  # noqa: E402

ROSTER_PATH_IN_REPO = ".claude/team/roster.json"


def parent_roster_names(repo_root: Path) -> set[str]:
    """Names in the committed parent roster -- the union manifest under test."""
    roster = repo_root / ROSTER_PATH_IN_REPO
    try:
        data = json.loads(roster.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return set()
    return set(data.keys()) if isinstance(data, dict) else set()


def default_child_repos(repo_root: Path) -> list[str]:
    """Local child-repo names: immediate subdirs that are their own git repo.

    Mirrors `roster_gen.detect_child_repos`'s definition without importing it
    (this module ships standalone to installed repos, which do not carry
    `framework/install/`). Used only when neither `--repos` nor a configured
    `project.repos` list is available.
    """
    children: list[str] = []
    if not repo_root.is_dir():
        return children
    for child in sorted(repo_root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if (child / ".git").exists():
            children.append(child.name)
    return children


def resolve_child_repos(repo_root: Path, cfg) -> list[str]:
    """Resolve the child-repo name list absent an explicit `--repos` override.

    Priority: `project.repos` (config), minus the repo root's own directory
    name (the meta repo is repos[0] in that list, per roster_gen's model) →
    local subdirectory detection (`default_child_repos`).
    """
    declared = cfg.get("project.repos", None)
    if declared:
        return [r for r in declared if r != repo_root.name]
    return default_child_repos(repo_root)


def local_child_roster(repo_root: Path, child: str) -> dict[str, str] | None:
    """Read a child's roster.json directly off disk, or None if not present/valid."""
    path = repo_root / child / ROSTER_PATH_IN_REPO
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def fetch_child_roster_remote(owner: str, repo: str) -> dict[str, str] | None:
    """Fetch a child repo's roster.json via `gh api`, or None if unavailable.

    Returns the parsed name->email mapping, or None when the file does not
    exist, the repo is unreadable by the CI token, or the response cannot be
    parsed (fail-open -- the caller treats None as SKIPPED, never as drift).
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
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if proc.returncode != 0:
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


def resolve_child_roster(
    repo_root: Path, owner: str | None, child: str
) -> tuple[dict[str, str] | None, str]:
    """Resolve one child's roster: local file first, remote API fallback.

    Returns (roster_or_None, source) where source is "local", "remote", or
    "skipped" (for reporting only -- callers treat a None roster as SKIPPED
    regardless of source).
    """
    local = local_child_roster(repo_root, child)
    if local is not None:
        return local, "local"
    if owner:
        remote = fetch_child_roster_remote(owner, child)
        if remote is not None:
            return remote, "remote"
    return None, "skipped"


def compute_drift(
    parent_names: set[str], child_rosters: dict[str, dict[str, str]]
) -> dict[str, list[str]]:
    """Return {missing_name: [child repos that have it]} for names absent from parent.

    Pure: the network/IO lives in resolve_child_roster, so this is fully
    testable with injected rosters. A name present in several child repos
    lists them all.
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
        "--owner", default=None, help="GitHub org/owner of the child repos (default: scm.owner)"
    )
    parser.add_argument(
        "--repos",
        help="comma-separated child repo list (default: project.repos, else local subdirs)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).expanduser().resolve()
    cfg = config(start_dir=repo_root)
    owner = args.owner or cfg.get("scm.owner", None)

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
        else resolve_child_repos(repo_root, cfg)
    )

    if not repos:
        print("No child repos to check (nothing declared, nothing detected locally). Passing.")
        return 0

    child_rosters: dict[str, dict[str, str]] = {}
    skipped: list[str] = []
    for repo in repos:
        roster, source = resolve_child_roster(repo_root, owner, repo)
        if roster is None:
            skipped.append(repo)
            print(f"SKIPPED {repo}: no readable {ROSTER_PATH_IN_REPO} (fail-open).")
        else:
            child_rosters[repo] = roster
            print(f"OK      {repo}: {len(roster)} persona(s) (source: {source}).")

    drift = compute_drift(parent_names, child_rosters)
    if drift:
        print(
            "\nDRIFT: the committed parent roster .claude/team/roster.json is MISSING "
            "child-repo persona(s) below. Fold each into the parent roster so the "
            "commit-identity gate (validate_commit_identity.py) recognizes them on a "
            "cross-repo commit:",
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
