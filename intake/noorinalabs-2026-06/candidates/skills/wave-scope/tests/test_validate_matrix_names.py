"""Tests for /wave-scope validate_matrix_names roster check (#319).

The P3W7 retro surfaced an "Anya Volkov" alias in the scope matrix that
doesn't exist in any roster (canonical isnad-graph Tech Lead is "Anya
Kowalczyk"). Substitution worked in-flight but wasn't caught at scope time.
This test pins that the validator surfaces such aliases with a suggestion.

Tests use isolated tmpdir-based rosters to avoid coupling to the real
org-dir state (which changes wave-to-wave).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validate_matrix_names import validate  # noqa: E402


def _write_roster_card(roster_dir: Path, role_slug: str, name: str) -> None:
    """Mimic the in-repo roster card shape: `**Name:** <name>` field."""
    roster_dir.mkdir(parents=True, exist_ok=True)
    (roster_dir / f"{role_slug}.md").write_text(
        "# Team Member Roster Card\n\n"
        "## Identity\n"
        f"- **Name:** {name}\n"
        "- **Role:** Engineer\n"
        "- **Status:** Active\n"
    )


def _build_fake_org_dir(tmp: Path) -> Path:
    """Build a fake org-dir with parent + 2 child rosters for testing."""
    # Parent roster — org-level coordinators.
    parent_roster = tmp / ".claude" / "team" / "roster"
    _write_roster_card(parent_roster, "pd_nadia", "Nadia Khoury")
    _write_roster_card(parent_roster, "tpm_wanjiku", "Wanjiku Mwangi")
    _write_roster_card(parent_roster, "sql_aino", "Aino Virtanen")
    # Child: noorinalabs-deploy
    deploy_roster = tmp / "noorinalabs-deploy" / ".claude" / "team" / "roster"
    _write_roster_card(deploy_roster, "lead_bereket", "Bereket Tadesse")
    _write_roster_card(deploy_roster, "eng_lucas", "Lucas Ferreira")
    # Child: noorinalabs-isnad-graph
    graph_roster = tmp / "noorinalabs-isnad-graph" / ".claude" / "team" / "roster"
    _write_roster_card(graph_roster, "tl_anya", "Anya Kowalczyk")
    _write_roster_card(graph_roster, "eng_idris", "Idris Yusuf")
    _write_roster_card(graph_roster, "eng_marisol", "Marisol Vega-Cruz")
    return tmp


class HappyPathTests(unittest.TestCase):
    """All declared names resolve to canonical roster entries."""

    def test_all_resolved_returns_no_unresolved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {
                    "implementer": "Anya Kowalczyk",
                    "reviewer": "Idris Yusuf",
                },
            }
            report = validate(matrix, org)
            findings = report["noorinalabs-isnad-graph"]
            self.assertEqual(len(findings), 2)
            for f in findings:
                self.assertTrue(f["resolved"], f"{f['declared']} should be resolved")

    def test_org_level_coordinator_resolves_in_child_slot(self):
        """Parent-roster coordinators (Aino, Nadia, etc.) can fill child-repo slots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {
                    "implementer": "Anya Kowalczyk",
                    "reviewer": "Aino Virtanen",  # parent-org-level
                }
            }
            report = validate(matrix, org)
            findings = report["noorinalabs-isnad-graph"]
            for f in findings:
                self.assertTrue(f["resolved"], f"{f['declared']} should be resolved")

    def test_parenthetical_role_stripped_for_match(self):
        """`Aino Virtanen (Standards Lead)` should resolve to `Aino Virtanen`."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {
                    "reviewer": "Aino Virtanen (Standards & Quality Lead)",
                }
            }
            report = validate(matrix, org)
            self.assertTrue(report["noorinalabs-isnad-graph"][0]["resolved"])


class UnresolvedNameTests(unittest.TestCase):
    """Names that don't match any roster — must surface + suggest."""

    def test_anya_volkov_alias_surfaces_with_suggestion(self):
        """P3W7 reproducer: Anya Volkov is a stale alias; canonical = Anya Kowalczyk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {
                    "implementer": "Anya Volkov",
                }
            }
            report = validate(matrix, org)
            finding = report["noorinalabs-isnad-graph"][0]
            self.assertFalse(finding["resolved"])
            self.assertIn("Anya Kowalczyk", finding["suggestions"])

    def test_completely_unknown_name_surfaces_with_best_guess(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-deploy": {
                    "implementer": "Nonexistent Person",
                }
            }
            report = validate(matrix, org)
            finding = report["noorinalabs-deploy"][0]
            self.assertFalse(finding["resolved"])
            # Suggestions list may be empty for very-distant names — that's fine.
            self.assertIn("suggestions", finding)

    def test_case_insensitive_resolution(self):
        """`anya kowalczyk` (lowercase) must resolve to `Anya Kowalczyk`."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {
                    "implementer": "anya kowalczyk",
                }
            }
            report = validate(matrix, org)
            self.assertTrue(report["noorinalabs-isnad-graph"][0]["resolved"])

    def test_empty_slot_skipped(self):
        """An empty string slot is ignored (TBD-pending placeholder)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-deploy": {
                    "implementer": "Bereket Tadesse",
                    "reviewer_2": "",
                }
            }
            report = validate(matrix, org)
            # Only 1 finding (reviewer_2 empty was skipped)
            self.assertEqual(len(report["noorinalabs-deploy"]), 1)


class ParentRosterFallbackTests(unittest.TestCase):
    """`noorinalabs-main` (parent) repo entries resolve via parent roster only."""

    def test_parent_repo_entry_resolves_against_parent_roster(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-main": {
                    "implementer": "Nadia Khoury",
                    "reviewer": "Wanjiku Mwangi",
                }
            }
            report = validate(matrix, org)
            for f in report["noorinalabs-main"]:
                self.assertTrue(f["resolved"], f"{f['declared']} should be resolved")

    def test_empty_repo_string_treated_as_parent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "": {
                    "implementer": "Nadia Khoury",
                }
            }
            report = validate(matrix, org)
            self.assertTrue(report[""][0]["resolved"])


class MissingRosterTests(unittest.TestCase):
    """Repos with no roster dir → fall back to parent-only lookup."""

    def test_missing_repo_roster_still_resolves_org_level_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-design-system": {  # No roster created for this repo.
                    "reviewer": "Aino Virtanen",  # Parent-org-level — should resolve.
                }
            }
            report = validate(matrix, org)
            self.assertTrue(report["noorinalabs-design-system"][0]["resolved"])

    def test_missing_repo_roster_with_only_per_repo_name_unresolved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-design-system": {
                    "implementer": "Bereket Tadesse",  # Lives in deploy roster, not DS.
                }
            }
            report = validate(matrix, org)
            # Bereket only exists in deploy roster — design-system lookup
            # combines parent + design-system rosters, not deploy.
            self.assertFalse(report["noorinalabs-design-system"][0]["resolved"])


if __name__ == "__main__":
    unittest.main()
