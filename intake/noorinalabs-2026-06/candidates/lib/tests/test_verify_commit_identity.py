"""Tests for verify_commit_identity — the landed-state commit-author gate (#627).

Verifies:
  1. Roster-name loading from the COMMITTED parent roster only — the org union
     manifest. Sibling child-repo rosters are NOT scanned (#634: that scan was
     inert in CI's single-repo checkout); cross-repo personas are recognized by
     being folded into the parent roster.
  2. The two real evasions the gate exists to catch:
       - bare gh principal `parametrization` as author (deploy#409);
       - a persona in NEITHER `Kofi Mensah` / `Kofi Mensah-Williams` form
         (an unknown / typo'd / stale name).
  3. A valid roster name (incl. the owner `Steven French`) passes.
  4. `git log base..head` range author extraction over a real temp repo.
  5. CLI exit codes: 0 clean, 1 violation, 2 load error.
  6. The real parent roster loads a non-empty name set (smoke).
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Helper lives at .claude/lib/verify_commit_identity.py; test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verify_commit_identity import (  # noqa: E402
    GH_PRINCIPAL_LOGIN,
    authors_in_range,
    check_authors,
    load_known_names,
    main,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _write_roster(repo_dir: Path, roster: dict[str, str]) -> None:
    """Write a .claude/team/roster.json under repo_dir."""
    roster_path = repo_dir / ".claude" / "team" / "roster.json"
    roster_path.parent.mkdir(parents=True, exist_ok=True)
    roster_path.write_text(json.dumps(roster), encoding="utf-8")


class LoadKnownNames(unittest.TestCase):
    def test_parent_roster_names_loaded(self) -> None:
        with TemporaryDirectory() as td:
            org = Path(td)
            main_repo = org / "noorinalabs-main"
            main_repo.mkdir()
            _write_roster(main_repo, {"Aino Virtanen": "a@x", "Steven French": "s@x"})

            names = load_known_names(main_repo)
            self.assertEqual(names, {"Aino Virtanen", "Steven French"})

    def test_sibling_child_rosters_NOT_scanned(self) -> None:
        # #634: the gate reads ONLY the committed parent roster (the org union
        # manifest). A sibling child-repo roster on disk must NOT be merged —
        # that filesystem scan was inert in CI's single-repo checkout while
        # passing locally, the divergence that gave false confidence. A child
        # persona is recognized only by being folded INTO the parent roster.
        with TemporaryDirectory() as td:
            org = Path(td)
            main_repo = org / "noorinalabs-main"
            child = org / "noorinalabs-isnad-graph"
            main_repo.mkdir()
            child.mkdir()
            _write_roster(main_repo, {"Aino Virtanen": "a@x"})
            _write_roster(child, {"Aisling Brennan": "b@x"})

            names = load_known_names(main_repo)
            self.assertEqual(names, {"Aino Virtanen"})
            self.assertNotIn("Aisling Brennan", names)

    def test_child_persona_folded_into_parent_is_recognized(self) -> None:
        # The supported path for cross-repo personas: present in the parent
        # roster (kept honest by roster_union_sync.py).
        with TemporaryDirectory() as td:
            org = Path(td)
            main_repo = org / "noorinalabs-main"
            main_repo.mkdir()
            _write_roster(main_repo, {"Aino Virtanen": "a@x", "Imelda Santos": "i@x"})

            names = load_known_names(main_repo)
            self.assertIn("Imelda Santos", names)

    def test_malformed_parent_roster_yields_empty_not_fatal(self) -> None:
        with TemporaryDirectory() as td:
            org = Path(td)
            main_repo = org / "noorinalabs-main"
            roster = main_repo / ".claude" / "team" / "roster.json"
            roster.parent.mkdir(parents=True)
            roster.write_text("{not json", encoding="utf-8")

            # An empty set is the caller's load-error signal (CLI exit 2), not a
            # crash.
            self.assertEqual(load_known_names(main_repo), set())


class CheckAuthors(unittest.TestCase):
    def setUp(self) -> None:
        self.known = {"Aino Virtanen", "Steven French", "Kofi Mensah-Williams"}

    def test_valid_roster_name_passes(self) -> None:
        self.assertEqual(check_authors(["Aino Virtanen"], self.known), [])

    def test_owner_steven_french_passes(self) -> None:
        # The owner IS a roster name and must pass.
        self.assertEqual(check_authors(["Steven French"], self.known), [])

    def test_bare_gh_principal_fails_even_if_in_roster(self) -> None:
        # The bare login is the unattributed-commit signature (deploy#409). It
        # must fail even if it somehow appears as a roster key.
        known_with_login = self.known | {GH_PRINCIPAL_LOGIN}
        self.assertEqual(
            check_authors([GH_PRINCIPAL_LOGIN], known_with_login),
            [GH_PRINCIPAL_LOGIN],
        )

    def test_unknown_persona_fails(self) -> None:
        # `Kofi Mensah` is NOT in this known set (only the -Williams form is) —
        # stands in for the cross-repo divergence / typo case.
        self.assertEqual(check_authors(["Kofi Mensah"], self.known), ["Kofi Mensah"])

    def test_mixed_range_reports_only_offenders(self) -> None:
        authors = ["Aino Virtanen", GH_PRINCIPAL_LOGIN, "Ghost Persona"]
        self.assertEqual(
            check_authors(authors, self.known),
            [GH_PRINCIPAL_LOGIN, "Ghost Persona"],
        )


class AuthorsInRange(unittest.TestCase):
    def _git(self, repo: Path, *args: str, **env: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
            env={**_BASE_GIT_ENV, **env},
        )

    def test_range_collects_distinct_authors_newest_first(self) -> None:
        with TemporaryDirectory() as td:
            repo = Path(td)
            self._git(repo, "init", "-q")
            (repo / "f").write_text("0", encoding="utf-8")
            self._git(repo, "add", "f")
            self._git(
                repo,
                "-c",
                "user.name=Aino Virtanen",
                "-c",
                "user.email=a@x",
                "commit",
                "-q",
                "-m",
                "base",
            )
            base = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            (repo / "f").write_text("1", encoding="utf-8")
            self._git(repo, "add", "f")
            self._git(
                repo,
                "-c",
                "user.name=Santiago Ferreira",
                "-c",
                "user.email=s@x",
                "commit",
                "-q",
                "-m",
                "c1",
            )
            (repo / "f").write_text("2", encoding="utf-8")
            self._git(repo, "add", "f")
            self._git(
                repo,
                "-c",
                f"user.name={GH_PRINCIPAL_LOGIN}",
                "-c",
                "user.email=p@x",
                "commit",
                "-q",
                "-m",
                "c2",
            )

            authors = authors_in_range(base, "HEAD", repo)
            # Newest first, base excluded (base..head is exclusive of base).
            self.assertEqual(authors, [GH_PRINCIPAL_LOGIN, "Santiago Ferreira"])

    def _make_principal_merge(self, repo: Path) -> str:
        """Build a repo with a principal-authored MERGE commit in `base..HEAD`.

        Returns the base sha. Layout after this runs:
          base (Aino) ← advance (Aino) ← MERGE (parametrization, 2 parents)
                     \\── feat (Santiago) ─────────┘
        The merge is the GitHub-merge shape: authored by the bare principal,
        two parents, forced via --no-ff.
        """
        self._git(repo, "init", "-q")
        (repo / "f").write_text("0", encoding="utf-8")
        self._git(repo, "add", "f")
        self._git(
            repo,
            "-c",
            "user.name=Aino Virtanen",
            "-c",
            "user.email=a@x",
            "commit",
            "-q",
            "-m",
            "base",
        )
        base = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        self._git(repo, "checkout", "-q", "-b", "feature")
        (repo / "g").write_text("1", encoding="utf-8")
        self._git(repo, "add", "g")
        self._git(
            repo,
            "-c",
            "user.name=Santiago Ferreira",
            "-c",
            "user.email=s@x",
            "commit",
            "-q",
            "-m",
            "feat content",
        )

        # Advance the base branch so the merge is a true 2-parent merge.
        self._git(repo, "checkout", "-q", "-")
        (repo / "f").write_text("0b", encoding="utf-8")
        self._git(repo, "add", "f")
        self._git(
            repo,
            "-c",
            "user.name=Aino Virtanen",
            "-c",
            "user.email=a@x",
            "commit",
            "-q",
            "-m",
            "advance",
        )
        self._git(
            repo,
            "-c",
            f"user.name={GH_PRINCIPAL_LOGIN}",
            "-c",
            "user.email=p@x",
            "merge",
            "--no-ff",
            "-q",
            "-m",
            "Merge pull request",
            "feature",
        )
        return base

    def test_merge_commit_by_principal_excluded_but_nonmerge_caught(self) -> None:
        """PR #630 regression: a `parametrization`-authored MERGE commit in the
        range must NOT be flagged (GitHub authors merges as the bare principal
        by design), while a `parametrization`-authored NON-merge content commit
        in the same range IS still caught (the deploy#409 evasion)."""
        with TemporaryDirectory() as td:
            repo = Path(td)
            base = self._make_principal_merge(repo)

            # Add a NON-merge content commit authored as the bare principal —
            # the evasion that MUST still be caught after --no-merges.
            (repo / "h").write_text("2", encoding="utf-8")
            self._git(repo, "add", "h")
            self._git(
                repo,
                "-c",
                f"user.name={GH_PRINCIPAL_LOGIN}",
                "-c",
                "user.email=p@x",
                "commit",
                "-q",
                "-m",
                "sneaky content",
            )

            authors = authors_in_range(base, "HEAD", repo)
            # Santiago's content commit is present; the principal appears ONLY
            # because of the non-merge sneaky commit (the merge is excluded).
            self.assertIn("Santiago Ferreira", authors)
            self.assertIn(GH_PRINCIPAL_LOGIN, authors)
            # check_authors must flag the principal (the sneaky non-merge), proving
            # --no-merges did not silence the real evasion.
            unknown = check_authors(authors, {"Aino Virtanen", "Santiago Ferreira"})
            self.assertEqual(unknown, [GH_PRINCIPAL_LOGIN])

    def test_merge_only_range_by_principal_is_clean(self) -> None:
        """A range whose ONLY principal-authored commit is a merge yields no
        principal violation — the core #630 false-positive case in isolation
        (the exact wave-branch→main shape Santiago reproduced against #622)."""
        with TemporaryDirectory() as td:
            repo = Path(td)
            base = self._make_principal_merge(repo)
            authors = authors_in_range(base, "HEAD", repo)
            self.assertNotIn(
                GH_PRINCIPAL_LOGIN,
                authors,
                "a principal-authored MERGE commit must not appear in the author set",
            )
            # Only the two real content authors remain (Santiago's feat, the
            # Aino advance); the merge contributed nothing.
            self.assertEqual(set(authors), {"Aino Virtanen", "Santiago Ferreira"})


class CliExitCodes(unittest.TestCase):
    def _setup_roster(self, td: str) -> Path:
        org = Path(td)
        main_repo = org / "noorinalabs-main"
        main_repo.mkdir()
        _write_roster(main_repo, {"Aino Virtanen": "a@x", "Steven French": "s@x"})
        return main_repo

    def test_clean_authors_exit_0(self) -> None:
        with TemporaryDirectory() as td:
            repo = self._setup_roster(td)
            rc = main(["--repo-root", str(repo), "--authors", "Aino Virtanen,Steven French"])
            self.assertEqual(rc, 0)

    def test_violation_exit_1(self) -> None:
        with TemporaryDirectory() as td:
            repo = self._setup_roster(td)
            rc = main(["--repo-root", str(repo), "--authors", f"{GH_PRINCIPAL_LOGIN}"])
            self.assertEqual(rc, 1)

    def test_empty_authors_exit_0(self) -> None:
        with TemporaryDirectory() as td:
            repo = self._setup_roster(td)
            rc = main(["--repo-root", str(repo), "--authors", ""])
            self.assertEqual(rc, 0)

    def test_no_roster_exit_2(self) -> None:
        with TemporaryDirectory() as td:
            empty = Path(td) / "no-roster"
            empty.mkdir()
            rc = main(["--repo-root", str(empty), "--authors", "Aino Virtanen"])
            self.assertEqual(rc, 2)


class RealRosterSmoke(unittest.TestCase):
    def test_parent_roster_loads_known_personas(self) -> None:
        names = load_known_names(_REPO_ROOT)
        self.assertIn("Aino Virtanen", names)
        self.assertIn("Steven French", names)
        # A child-repo persona must be folded into the parent union manifest
        # (#634: ingest-platform's Imelda Santos was previously omitted).
        self.assertIn("Imelda Santos", names)
        # The bare gh login is NOT a roster name.
        self.assertNotIn(GH_PRINCIPAL_LOGIN, names)


# git refuses to commit without an identity in some CI images; pin a base env
# so the per-commit -c flags in tests are the only identity source.
_BASE_GIT_ENV: dict[str, str] = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "PATH": __import__("os").environ.get("PATH", ""),
    "HOME": __import__("os").environ.get("HOME", ""),
}


if __name__ == "__main__":
    unittest.main()
