"""Tests for roster_consistency_check -- roster.json <-> roster/*.md drift gate.

Verifies:
  1. Consistent card: identity fields match roster.json exactly -> exit 0.
  2. Intra-file mismatch: Identity Name != Git Identity user.name -> exit 1.
  3. Missing from json: user.name not in roster.json -> exit 1.
  4. Email mismatch: user.email in .md differs from roster.json email -> exit 1.
  5. Missing field: .md lacks ## Git Identity user.name -> exit 1.
  6. No .md files: nothing to check -> exit 0 (clean by definition).
  7. Mixed: one clean card + one drifted card -> only drifted card reported.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roster_consistency_check import check_consistency, main  # noqa: E402

# ---------------------------------------------------------------------------
# Fixture card templates
# ---------------------------------------------------------------------------

CONSISTENT_MD = """\
# Team Member Roster Card

## Identity
- **Name:** Aino Virtanen
- **Role:** Standards & Quality Lead

## Git Identity
- **user.name:** Aino Virtanen
- **user.email:** parametrization+Aino.Virtanen@gmail.com
"""

# Identity Name uses unhyphenated form; Git Identity user.name is hyphenated.
# Mirrors the Mei-Lin Chang incident that motivated this check.
INTRA_NAME_MISMATCH_MD = """\
# Team Member Roster Card

## Identity
- **Name:** Mei Lin Chang
- **Role:** Data Engineer

## Git Identity
- **user.name:** Mei-Lin Chang
- **user.email:** parametrization+Mei-Lin.Chang@gmail.com
"""

# user.name exists in the card but is absent from roster.json.
MISSING_FROM_JSON_MD = """\
# Team Member Roster Card

## Identity
- **Name:** Ghost Member
- **Role:** Phantom

## Git Identity
- **user.name:** Ghost Member
- **user.email:** parametrization+Ghost.Member@gmail.com
"""

# user.name is in roster.json but the .md email differs.
EMAIL_MISMATCH_MD = """\
# Team Member Roster Card

## Identity
- **Name:** Aino Virtanen
- **Role:** Standards & Quality Lead

## Git Identity
- **user.name:** Aino Virtanen
- **user.email:** wrong+typo@example.com
"""

# .md is missing the user.name field entirely.
MISSING_GIT_NAME_MD = """\
# Team Member Roster Card

## Identity
- **Name:** Aino Virtanen

## Git Identity
- **user.email:** parametrization+Aino.Virtanen@gmail.com
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_repo(
    tmp: Path,
    roster_json: dict[str, str],
    md_files: dict[str, str],
) -> Path:
    """Write roster.json and roster/*.md files under a tmp repo root."""
    team_dir = tmp / ".claude" / "team"
    team_dir.mkdir(parents=True)
    (team_dir / "roster.json").write_text(json.dumps(roster_json), encoding="utf-8")
    roster_dir = team_dir / "roster"
    roster_dir.mkdir()
    for filename, content in md_files.items():
        (roster_dir / filename).write_text(content, encoding="utf-8")
    return tmp


# ---------------------------------------------------------------------------
# check_consistency unit tests
# ---------------------------------------------------------------------------


class CheckConsistencyTests(unittest.TestCase):
    def test_consistent_card_returns_no_drift(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = _setup_repo(
                Path(tmp),
                {"Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com"},
                {"standards_lead_aino.md": CONSISTENT_MD},
            )
            self.assertEqual(check_consistency(repo), [])

    def test_intra_name_mismatch_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            # roster.json matches the git-identity name (with hyphen)
            repo = _setup_repo(
                Path(tmp),
                {"Mei-Lin Chang": "parametrization+Mei-Lin.Chang@gmail.com"},
                {"mei_lin_chang.md": INTRA_NAME_MISMATCH_MD},
            )
            drift = check_consistency(repo)
            self.assertTrue(
                any("Identity Name" in d and "user.name" in d for d in drift),
                msg=f"Expected intra-name mismatch in drift; got: {drift}",
            )

    def test_missing_from_json_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = _setup_repo(
                Path(tmp),
                {"Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com"},
                {"ghost.md": MISSING_FROM_JSON_MD},
            )
            drift = check_consistency(repo)
            self.assertTrue(
                any("not found in roster.json" in d for d in drift),
                msg=f"Expected missing-from-json in drift; got: {drift}",
            )

    def test_email_mismatch_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = _setup_repo(
                Path(tmp),
                {"Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com"},
                {"standards_lead_aino.md": EMAIL_MISMATCH_MD},
            )
            drift = check_consistency(repo)
            self.assertTrue(
                any("user.email" in d and "roster.json" in d for d in drift),
                msg=f"Expected email mismatch in drift; got: {drift}",
            )

    def test_missing_git_name_field_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = _setup_repo(
                Path(tmp),
                {"Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com"},
                {"standards_lead_aino.md": MISSING_GIT_NAME_MD},
            )
            drift = check_consistency(repo)
            self.assertTrue(
                any("user.name" in d for d in drift),
                msg=f"Expected missing-field report in drift; got: {drift}",
            )

    def test_no_md_files_returns_no_drift(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = _setup_repo(
                Path(tmp),
                {"Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com"},
                {},  # no .md files -- nothing to check
            )
            self.assertEqual(check_consistency(repo), [])

    def test_mixed_cards_only_drifted_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = _setup_repo(
                Path(tmp),
                {
                    "Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com",
                    "Mei-Lin Chang": "parametrization+Mei-Lin.Chang@gmail.com",
                },
                {
                    "standards_lead_aino.md": CONSISTENT_MD,
                    "mei_lin_chang.md": INTRA_NAME_MISMATCH_MD,
                },
            )
            drift = check_consistency(repo)
            # Aino is clean; Mei-Lin has the intra-name mismatch.
            self.assertTrue(
                any("mei_lin_chang.md" in d for d in drift),
                msg=f"Expected mei_lin_chang drift; got: {drift}",
            )
            self.assertFalse(
                any("standards_lead_aino.md" in d for d in drift),
                msg=f"Aino should be clean; got unexpected entry: {drift}",
            )


# ---------------------------------------------------------------------------
# CLI (main) tests
# ---------------------------------------------------------------------------


class MainTests(unittest.TestCase):
    def test_consistent_exits_0(self) -> None:
        with TemporaryDirectory() as tmp:
            _setup_repo(
                Path(tmp),
                {"Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com"},
                {"standards_lead_aino.md": CONSISTENT_MD},
            )
            self.assertEqual(main(["--repo-root", tmp]), 0)

    def test_drift_exits_1(self) -> None:
        with TemporaryDirectory() as tmp:
            _setup_repo(
                Path(tmp),
                {"Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com"},
                {"ghost.md": MISSING_FROM_JSON_MD},
            )
            self.assertEqual(main(["--repo-root", tmp]), 1)


if __name__ == "__main__":
    unittest.main()
