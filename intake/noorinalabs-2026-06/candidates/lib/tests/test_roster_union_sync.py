"""Tests for roster_union_sync — the parent-roster ⊇ child-union drift gate (#634).

Verifies:
  1. The pure drift computation: a child persona absent from the parent roster
     is reported (with the child repos that carry it); a covered union is clean.
  2. parent_roster_names reads the committed parent roster keys.
  3. CLI wiring with an injected (monkeypatched) fetcher so tests never touch
     the network: clean union → exit 0, drift → exit 1, all-skipped → exit 0,
     missing parent roster → exit 2.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import roster_union_sync  # noqa: E402
from roster_union_sync import (  # noqa: E402
    compute_drift,
    main,
    parent_roster_names,
)


def _write_parent_roster(repo_root: Path, roster: dict[str, str]) -> None:
    path = repo_root / ".claude" / "team" / "roster.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(roster), encoding="utf-8")


class ComputeDrift(unittest.TestCase):
    def test_covered_union_has_no_drift(self) -> None:
        parent = {"Aino Virtanen", "Imelda Santos"}
        children = {"noorinalabs-isnad-ingest-platform": {"Imelda Santos": "i@x"}}
        self.assertEqual(compute_drift(parent, children), {})

    def test_missing_persona_is_reported_with_owning_repos(self) -> None:
        parent = {"Aino Virtanen"}
        children = {
            "noorinalabs-isnad-ingest-platform": {"Imelda Santos": "i@x"},
            "noorinalabs-user-service": {"Imelda Santos": "i@x", "Aino Virtanen": "a@x"},
        }
        drift = compute_drift(parent, children)
        # Imelda is missing and appears in BOTH child repos (sorted); Aino is
        # covered by the parent so it is not reported.
        self.assertEqual(
            drift,
            {"Imelda Santos": ["noorinalabs-isnad-ingest-platform", "noorinalabs-user-service"]},
        )

    def test_empty_children_no_drift(self) -> None:
        self.assertEqual(compute_drift({"Aino Virtanen"}, {}), {})


class ParentRosterNames(unittest.TestCase):
    def test_reads_committed_parent_keys(self) -> None:
        with TemporaryDirectory() as td:
            repo = Path(td)
            _write_parent_roster(repo, {"Aino Virtanen": "a@x", "Imelda Santos": "i@x"})
            self.assertEqual(parent_roster_names(repo), {"Aino Virtanen", "Imelda Santos"})

    def test_missing_roster_returns_empty(self) -> None:
        with TemporaryDirectory() as td:
            self.assertEqual(parent_roster_names(Path(td)), set())


class CliWithInjectedFetcher(unittest.TestCase):
    """Drive main() with fetch_child_roster monkeypatched — no network."""

    def _run(self, parent: dict[str, str], fetched: dict[str, dict | None], repos: str) -> int:
        with TemporaryDirectory() as td:
            repo = Path(td)
            _write_parent_roster(repo, parent)
            orig = roster_union_sync.fetch_child_roster
            roster_union_sync.fetch_child_roster = lambda owner, r: fetched.get(r)  # type: ignore[assignment]
            try:
                return main(["--repo-root", str(repo), "--repos", repos])
            finally:
                roster_union_sync.fetch_child_roster = orig

    def test_clean_union_exit_0(self) -> None:
        rc = self._run(
            {"Aino Virtanen": "a@x", "Imelda Santos": "i@x"},
            {"noorinalabs-isnad-ingest-platform": {"Imelda Santos": "i@x"}},
            "noorinalabs-isnad-ingest-platform",
        )
        self.assertEqual(rc, 0)

    def test_drift_exit_1(self) -> None:
        rc = self._run(
            {"Aino Virtanen": "a@x"},
            {"noorinalabs-isnad-ingest-platform": {"Imelda Santos": "i@x"}},
            "noorinalabs-isnad-ingest-platform",
        )
        self.assertEqual(rc, 1)

    def test_all_children_skipped_exit_0(self) -> None:
        # Fail-open: every child unreadable (fetch returns None) → nothing to
        # cross-check → pass (advisory), never a drift failure on its own.
        rc = self._run(
            {"Aino Virtanen": "a@x"},
            {"noorinalabs-deploy": None},
            "noorinalabs-deploy",
        )
        self.assertEqual(rc, 0)

    def test_missing_parent_roster_exit_2(self) -> None:
        with TemporaryDirectory() as td:
            empty = Path(td) / "no-roster"
            empty.mkdir()
            rc = main(["--repo-root", str(empty), "--repos", "noorinalabs-isnad-graph"])
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
