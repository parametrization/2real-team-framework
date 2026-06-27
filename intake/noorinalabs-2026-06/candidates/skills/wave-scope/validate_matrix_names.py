#!/usr/bin/env python3
"""Validate implementer/reviewer names in a wave-scope matrix against rosters.

Pre-#319 `/wave-scope` did not validate names in the matrix — a stale alias
like "Anya Volkov" (canonical: "Anya Kowalczyk") propagated through scope
and only surfaced at first-spawn time. P3W7 logged both substitutions in
`wave_7_decisions.implementer_substitutions`. This script runs at scope
time and surfaces unknown names BEFORE `/wave-kickoff` fan-out.

Usage:
    validate_matrix_names.py <scope-json-path>

Where `<scope-json-path>` is a JSON file with the shape:

    {
        "noorinalabs-isnad-graph": {
            "implementer": "Anya Kowalczyk",
            "reviewer": "Idris Diallo",
            "reviewer_2": "Marcia Vieira"
        },
        "noorinalabs-deploy": {
            "implementer": "Bereket Tesfaye",
            "reviewer": "Lucas Pham",
            "reviewer_2": "Aino Virtanen"
        }
    }

Exit codes:
    0 — all names resolve to a canonical roster entry
    1 — one or more names don't resolve; suggested matches printed to stderr
    2 — invalid input

Resolution:
    - For each per-repo entry, read `<parent>/<repo>/.claude/team/roster/*.md`
      and extract the `**Name:**` field.
    - For parent-repo entries (repo == "noorinalabs-main" or no repo), fall
      back to the parent's own `.claude/team/roster/`.
    - Case-insensitive exact match wins.
    - On miss: fuzzy-match (difflib SequenceMatcher) and print the top-3
      closest matches as suggestions.

The script is read-only — it never modifies the matrix or rosters. The
operator makes the substitution decision and re-runs.
"""

from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path


def _find_org_dir() -> Path:
    """Find the directory that contains all `noorinalabs-*` repo checkouts.

    Org layout: `~/code/noorinalabs-main/` contains both the parent repo
    (itself, called `noorinalabs-main` at the org level) AND sibling-repo
    checkouts (`noorinalabs-deploy`, `noorinalabs-isnad-graph`, ...). So
    `noorinalabs-deploy` etc. live at `<org_dir>/noorinalabs-deploy/`, and
    the parent repo's own roster lives at `<org_dir>/.claude/team/roster/`.

    When invoked from a worktree (`<org_dir>/.claude/worktrees/<name>/`),
    walk up to the org_dir.
    """
    cwd = Path.cwd().resolve()
    for ancestor in [cwd, *cwd.parents]:
        if (ancestor / "noorinalabs-deploy").is_dir() and (
            ancestor / ".claude" / "team" / "roster"
        ).is_dir():
            return ancestor
    return cwd


def _load_roster_names(roster_dir: Path) -> set[str]:
    """Parse `**Name:** Foo Bar` lines from every .md file in roster_dir."""
    names: set[str] = set()
    if not roster_dir.is_dir():
        return names
    name_re = re.compile(r"\*\*Name:\*\*\s+(.+?)\s*$", re.MULTILINE)
    for md_file in roster_dir.glob("*.md"):
        try:
            text = md_file.read_text()
        except OSError:
            continue
        for match in name_re.finditer(text):
            name = match.group(1).strip()
            # Trim role/status parentheticals (`Foo Bar (Tech Lead)`).
            name = re.sub(r"\s*\(.*?\)\s*$", "", name)
            if name:
                names.add(name)
    return names


def _load_repo_roster(org_dir: Path, repo: str) -> set[str]:
    """Load roster names for a given repo.

    `repo == "noorinalabs-main"` or empty → org_dir's own `.claude/team/roster/`
    (the parent repo's roster is at org-dir root, not under a sibling subdir).
    Else `<org_dir>/<repo>/.claude/team/roster/`.
    """
    if not repo or repo == "noorinalabs-main":
        return _load_roster_names(org_dir / ".claude" / "team" / "roster")
    return _load_roster_names(org_dir / repo / ".claude" / "team" / "roster")


def _suggest(name: str, candidates: set[str], top: int = 3) -> list[str]:
    """Return up to `top` closest matches from candidates via difflib."""
    if not candidates:
        return []
    return difflib.get_close_matches(name, sorted(candidates), n=top, cutoff=0.5)


def validate(
    matrix: dict[str, dict[str, str]],
    org_dir: Path,
) -> dict[str, list[dict[str, object]]]:
    """Return a per-repo report of name → resolution status.

    Result shape:
        {
            "noorinalabs-isnad-graph": [
                {"role": "implementer", "declared": "Anya Volkov",
                 "resolved": False, "suggestions": ["Anya Kowalczyk"]},
                ...
            ],
            ...
        }
    """
    report: dict[str, list[dict[str, object]]] = {}
    for repo, slots in matrix.items():
        # Parent rosters are always loaded — org-level coordinators
        # (Nadia, Wanjiku, Aino, Santiago) can appear in per-repo matrix
        # slots when reviewing parent-flavored work.
        parent_roster = _load_repo_roster(org_dir, "noorinalabs-main")
        repo_roster = _load_repo_roster(org_dir, repo)
        combined = parent_roster | repo_roster
        repo_findings: list[dict[str, object]] = []
        for role, declared in slots.items():
            if not declared:
                continue
            declared_clean = re.sub(r"\s*\(.*?\)\s*$", "", declared).strip()
            resolved = any(declared_clean.lower() == known.lower() for known in combined)
            entry: dict[str, object] = {
                "role": role,
                "declared": declared,
                "resolved": resolved,
            }
            if not resolved:
                entry["suggestions"] = _suggest(declared_clean, combined)
            repo_findings.append(entry)
        report[repo] = repo_findings
    return report


def _print_report_to_stderr(report: dict[str, list[dict[str, object]]]) -> int:
    """Pretty-print the report to stderr; return exit code."""
    total = 0
    unresolved = 0
    for repo, findings in report.items():
        for f in findings:
            total += 1
            if not f["resolved"]:
                unresolved += 1
    if unresolved == 0:
        print(
            f"validate_matrix_names: all {total} names resolved across {len(report)} repos.",
            file=sys.stderr,
        )
        return 0
    print(
        f"validate_matrix_names: {unresolved}/{total} names UNRESOLVED across {len(report)} repos.",
        file=sys.stderr,
    )
    for repo, findings in report.items():
        bad = [f for f in findings if not f["resolved"]]
        if not bad:
            continue
        print(f"\n  {repo}:", file=sys.stderr)
        for f in bad:
            raw_suggestions = f.get("suggestions")
            suggestions = raw_suggestions if isinstance(raw_suggestions, list) else []
            sug_str = ", ".join(suggestions) if suggestions else "(no close matches)"
            print(
                f"    - {f['role']}: {f['declared']!r}  →  suggestions: {sug_str}",
                file=sys.stderr,
            )
    print(
        "\n  Resolve each unknown name before /wave-kickoff fan-out.\n"
        "  Approved substitutions: record under wave_{M}_decisions.implementer_substitutions"
        " in cross-repo-status.json with rationale.",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        matrix = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR reading {path}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(matrix, dict):
        print("ERROR: top-level must be an object mapping repo → role-slots", file=sys.stderr)
        return 2
    org_dir = _find_org_dir()
    report = validate(matrix, org_dir)
    return _print_report_to_stderr(report)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
