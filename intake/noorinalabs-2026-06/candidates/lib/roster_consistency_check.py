#!/usr/bin/env python3
"""Roster consistency check: .claude/team/roster.json <-> .claude/team/roster/*.md

Detects drift between the union-manifest roster.json and the per-member
roster/*.md identity cards, for every team member who has a roster/*.md file.

Checks per roster/*.md (cross-checked against roster.json):
  1. Intra-file consistency — ## Identity "Name:" must equal
     ## Git Identity "user.name:" within the same card.
  2. md->json presence — user.name must exist as a key in roster.json.
  3. Email match — roster.json[user.name] must equal user.email from the card.

Why this is NOT a blocking hook
================================
Blocking PreToolUse hooks that load and parse files on every Edit/Write call
add latency to every agent operation. A buggy blocking hook halts all work
until fixed, which is a higher cost than the drift it prevents. This check is
therefore wired non-blocking:

  * /session-start advisory step: run automatically; reported as a health
    warning in the session-start status table. Operator sees drift
    immediately at session open without being blocked.
  * CI job (continue-on-error: true): fires on PRs that touch roster.*
    files, surfacing drift to reviewers as an advisory check. A single PR
    that adds a roster.json entry but not the .md (or vice-versa) should not
    hard-block the PR, per org pattern for cross-repo-derived artifact gates
    (memory feedback_org_wide_artifact_gate_non_blocking).

Use roster_union_sync.py for the complementary check (parent roster.json
covers every child-repo persona) — this module covers the intra-parent
.md <-> roster.json consistency only.

Invocation:
  roster_consistency_check.py [--repo-root <dir>]

Exit codes:
  0 -- roster consistent (all .md entries agree with roster.json), or no
       roster/*.md files found (nothing to check)
  1 -- drift found (drift list printed to stdout)
  2 -- usage error or roster.json load failure
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROSTER_JSON_PATH = ".claude/team/roster.json"
ROSTER_DIR_PATH = ".claude/team/roster"


def load_roster_json(repo_root: Path) -> dict[str, str] | None:
    """Load name->email mapping from roster.json.

    Returns the parsed dict, or None when the file is missing or malformed
    (caller treats None as a load error -- exit 2).
    """
    path = repo_root / ROSTER_JSON_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def parse_roster_md(path: Path) -> dict[str, str | None]:
    """Extract identity fields from a roster/*.md card.

    Parses the roster card template (## Identity / ## Git Identity sections)
    and returns a dict with three keys:

      identity_name  -- "Name:" line under "## Identity"
      git_user_name  -- "user.name:" line under "## Git Identity"
      git_user_email -- "user.email:" line under "## Git Identity"

    Values are None when the corresponding field is absent from the card.
    """
    text = path.read_text(encoding="utf-8")
    result: dict[str, str | None] = {
        "identity_name": None,
        "git_user_name": None,
        "git_user_email": None,
    }

    # Roster cards follow the template: "- **Name:** <value>" or
    # "- **user.name:** <value>" -- both bullet and bold-key forms.
    name_m = re.search(r"^[-*]\s+\*\*Name:\*\*\s+(.+)$", text, re.MULTILINE)
    if name_m:
        result["identity_name"] = name_m.group(1).strip()

    git_name_m = re.search(r"^[-*]\s+\*\*user\.name:\*\*\s+(.+)$", text, re.MULTILINE)
    if git_name_m:
        result["git_user_name"] = git_name_m.group(1).strip()

    git_email_m = re.search(r"^[-*]\s+\*\*user\.email:\*\*\s+(.+)$", text, re.MULTILINE)
    if git_email_m:
        result["git_user_email"] = git_email_m.group(1).strip()

    return result


def check_consistency(repo_root: Path) -> list[str]:
    """Cross-check every roster/*.md entry against roster.json.

    Pure function given loaded data -- IO lives in load_roster_json and
    parse_roster_md, keeping the drift logic unit-testable without tmp files.

    Returns a (possibly empty) list of human-readable drift strings.
    An empty list means the roster is consistent.
    """
    roster_json = load_roster_json(repo_root)
    if roster_json is None:
        return [
            f"ERROR: could not load {ROSTER_JSON_PATH} -- verify the file exists and is valid JSON"
        ]

    roster_dir = repo_root / ROSTER_DIR_PATH
    md_files: list[Path] = sorted(roster_dir.glob("*.md")) if roster_dir.is_dir() else []

    drift: list[str] = []

    for md_path in md_files:
        fields = parse_roster_md(md_path)
        id_name = fields["identity_name"]
        git_name = fields["git_user_name"]
        git_email = fields["git_user_email"]
        short = md_path.name

        # Missing required fields -- report each independently so the operator
        # can fix them one by one.
        if id_name is None:
            drift.append(f"{short}: missing '## Identity / **Name:**' field")
        if git_name is None:
            drift.append(f"{short}: missing '## Git Identity / **user.name:**' field")
        if git_email is None:
            drift.append(f"{short}: missing '## Git Identity / **user.email:**' field")

        # Check 1 (intra-file): Identity Name must equal Git Identity user.name.
        if id_name is not None and git_name is not None and id_name != git_name:
            drift.append(
                f"{short}: Identity Name ({id_name!r}) != Git Identity user.name ({git_name!r})"
            )

        # Check 2 (md->json): user.name must be a key in roster.json.
        if git_name is not None and git_name not in roster_json:
            drift.append(f"{short}: user.name={git_name!r} not found in roster.json")

        # Check 3 (email match): roster.json[user.name] must equal user.email.
        if git_name is not None and git_email is not None and git_name in roster_json:
            expected = roster_json[git_name]
            if expected != git_email:
                drift.append(
                    f"{short}: user.email={git_email!r} != roster.json[{git_name!r}]={expected!r}"
                )

    return drift


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check roster.json <-> roster/*.md consistency (non-blocking advisory)."
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="path to the repository root containing .claude/team/ (default: .)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).expanduser().resolve()
    drift = check_consistency(repo_root)

    if drift:
        print("ROSTER DRIFT DETECTED -- the following inconsistencies need resolution:")
        for item in drift:
            print(f"  - {item}")
        return 1

    roster_dir = repo_root / ROSTER_DIR_PATH
    md_count = len(list(roster_dir.glob("*.md"))) if roster_dir.is_dir() else 0
    print(
        f"roster consistent -- {md_count} roster/*.md file(s) verified against roster.json,"
        " no drift."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
