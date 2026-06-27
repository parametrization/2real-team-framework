"""Tests for wave_status — the deterministic wave repo-iteration + counter
helper that replaces the zsh-word-split-fragile bash loops (main#688).

Verifies:
  1. `repos` emits wave_{M}_repos_in_scope one-per-line.
  2. EVERY gh call goes through subprocess.run with a LIST arg vector and
     never `shell=True` — the regression guard that makes word-splitting
     structurally impossible.
  3. merged-prs applies the wave_{M}_kicked_off_at cross-window filter (#423).
  4. Counter math reproduces the P5W4 actuals 19 / 4 / 16.
  5. `--expect N` exits 1 on a count mismatch.
  6. An empty wave yields zeros (no division-by-zero — the original crash).
  7. `--write` upserts the three canonical top-level keys through the shared
     upsert_status_keys helper, preserving the file.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

# Helper lives at .claude/lib/wave_status.py; this test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wave_status  # noqa: E402

_REPOS = [
    "noorinalabs-isnad-graph",
    "noorinalabs-user-service",
    "noorinalabs-deploy",
    "noorinalabs-isnad-ingest-platform",
]


def _p5w4_prs() -> list[dict]:
    """19 PRs whose top commit-author owns 3 (3/19 = 15.78 → 16%) and whose
    ChangesRequested comments sum to 4 — the canonical P5W4 shape."""
    authors = (
        ["Aino Virtanen"] * 3
        + ["Wanjiku Mwangi"] * 3
        + ["Santiago Ferreira"] * 3
        + ["Nadia Khoury"] * 3
        + ["Imelda Okoro"] * 3
        + ["Aisling Brennan"] * 3
        + ["Tariq Mansour"] * 1
    )
    assert len(authors) == 19
    cr_by_index = {0: 2, 5: 1, 10: 1}  # sums to 4
    prs = []
    for i, author in enumerate(authors):
        prs.append(
            {
                "repo": _REPOS[i % len(_REPOS)],
                "number": 100 + i,
                "sha": f"sha{i:02d}",
                "mergedAt": "2026-06-15T02:00:00Z",
                "login": "octocat",
                "commit_author": author,
                "cr": cr_by_index.get(i, 0),
            }
        )
    return prs


class _FakeGh:
    """A subprocess.run side_effect that emulates the gh calls wave_status
    makes, driven by a flat PR fixture. Records every command vector so the
    test can assert the list-args / no-shell contract."""

    def __init__(self, prs: list[dict]) -> None:
        self.prs = prs
        self.calls: list[list[str]] = []

    def __call__(self, cmd, *args, **kwargs):  # noqa: ANN001
        # Contract guard: gh is always invoked with an explicit list vector and
        # NEVER through a shell. This is the structural fix for main#688.
        assert isinstance(cmd, list), f"gh called with non-list cmd: {cmd!r}"
        assert cmd[0] == "gh"
        assert kwargs.get("shell") is not True
        self.calls.append(cmd)

        if cmd[1:3] == ["pr", "list"]:
            repo = cmd[cmd.index("--repo") + 1].removeprefix("noorinalabs/")
            listed = [
                {
                    "number": p["number"],
                    "headRefOid": p["sha"],
                    "mergedAt": p["mergedAt"],
                    "author": {"login": p["login"]},
                }
                for p in self.prs
                if p["repo"] == repo
            ]
            return SimpleNamespace(stdout=json.dumps(listed), returncode=0, stderr="")

        if cmd[1] == "api":
            path = cmd[2]
            parts = path.split("/")
            if "/commits/" in path:
                sha = parts[4]
                name = next(p["commit_author"] for p in self.prs if p["sha"] == sha)
                return SimpleNamespace(stdout=name + "\n", returncode=0, stderr="")
            if path.endswith("/comments"):
                number = int(parts[4])
                cr = next(p["cr"] for p in self.prs if p["number"] == number)
                return SimpleNamespace(stdout=f"{cr}\n", returncode=0, stderr="")

        raise AssertionError(f"unexpected gh call: {cmd!r}")


def _write_status(path: Path, *, repos: list[str], wave: str, kickoff: str | None) -> None:
    data: dict = {"current_wave": int(wave), f"wave_{wave}_repos_in_scope": repos}
    if kickoff is not None:
        data[f"wave_{wave}_kicked_off_at"] = kickoff
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class Repos(unittest.TestCase):
    def test_emits_one_per_line(self) -> None:
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="4", kickoff=None)
            self.assertEqual(wave_status.read_repos("4", status), _REPOS)

    def test_missing_key_raises(self) -> None:
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            status.write_text('{"current_wave": 4}\n', encoding="utf-8")
            with self.assertRaises(KeyError):
                wave_status.read_repos("4", status)


class MergedPrs(unittest.TestCase):
    def test_kickoff_window_filter(self) -> None:
        prs = [
            {
                "repo": _REPOS[0],
                "number": 1,
                "sha": "old",
                "mergedAt": "2026-06-14T00:00:00Z",  # before kickoff → dropped
                "login": "octocat",
                "commit_author": "Aino Virtanen",
                "cr": 0,
            },
            {
                "repo": _REPOS[0],
                "number": 2,
                "sha": "new",
                "mergedAt": "2026-06-15T03:00:00Z",  # after kickoff → kept
                "login": "octocat",
                "commit_author": "Aino Virtanen",
                "cr": 0,
            },
        ]
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=[_REPOS[0]], wave="4", kickoff="2026-06-15T01:52:55Z")
            with mock.patch.object(wave_status.subprocess, "run", _FakeGh(prs)):
                got = wave_status.merged_prs("5", "4", status)
        self.assertEqual([p["number"] for p in got], [2])
        self.assertEqual(got[0]["commit_author_name"], "Aino Virtanen")

    def test_no_kickoff_key_means_no_filter(self) -> None:
        prs = [
            {
                "repo": _REPOS[0],
                "number": 1,
                "sha": "a",
                "mergedAt": "2026-01-01T00:00:00Z",
                "login": "octocat",
                "commit_author": "Aino Virtanen",
                "cr": 0,
            }
        ]
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=[_REPOS[0]], wave="4", kickoff=None)
            with mock.patch.object(wave_status.subprocess, "run", _FakeGh(prs)):
                got = wave_status.merged_prs("5", "4", status)
        self.assertEqual(len(got), 1)


class Counters(unittest.TestCase):
    def test_reproduces_p5w4_19_4_16(self) -> None:
        prs = _p5w4_prs()
        fake = _FakeGh(prs)
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="4", kickoff="2026-06-15T01:52:55Z")
            with mock.patch.object(wave_status.subprocess, "run", fake):
                counters = wave_status.compute_counters("5", "4", status)
        self.assertEqual(
            counters,
            {
                "final_pr_count": 19,
                "changes_requested_cycles": 4,
                "top_concentration_pct": 16,
            },
        )
        # Contract: every recorded gh call was a list vector starting with "gh".
        self.assertTrue(all(c[0] == "gh" and isinstance(c, list) for c in fake.calls))

    def test_changes_requested_jq_filter_double_escapes_backslash(self) -> None:
        # The comments call's --jq arg must carry a DOUBLED backslash (\\s) so
        # jq's string parser yields the regex \s. A single backslash is an
        # "invalid escape sequence" jq error — the mocked fake can't see jq, so
        # assert the literal sequence the helper builds.
        prs = _p5w4_prs()[:1]
        fake = _FakeGh(prs)
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="4", kickoff=None)
            with mock.patch.object(wave_status.subprocess, "run", fake):
                wave_status.compute_counters("5", "4", status)
        comments_calls = [c for c in fake.calls if c[1] == "api" and c[2].endswith("/comments")]
        self.assertTrue(comments_calls)
        self.assertIn("\\\\s", comments_calls[0][-1])

    def test_empty_wave_is_zeros_no_div_by_zero(self) -> None:
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="4", kickoff=None)
            with mock.patch.object(wave_status.subprocess, "run", _FakeGh([])):
                counters = wave_status.compute_counters("5", "4", status)
        self.assertEqual(
            counters,
            {"final_pr_count": 0, "changes_requested_cycles": 0, "top_concentration_pct": 0},
        )

    def test_expect_mismatch_exits_1(self) -> None:
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="4", kickoff="2026-06-15T01:52:55Z")
            with mock.patch.object(wave_status.subprocess, "run", _FakeGh(_p5w4_prs())):
                rc = wave_status.main(
                    ["counters", "5", "4", "--status", str(status), "--expect", "20"]
                )
        self.assertEqual(rc, 1)

    def test_expect_match_exits_0(self) -> None:
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="4", kickoff="2026-06-15T01:52:55Z")
            with mock.patch.object(wave_status.subprocess, "run", _FakeGh(_p5w4_prs())):
                rc = wave_status.main(
                    ["counters", "5", "4", "--status", str(status), "--expect", "19"]
                )
        self.assertEqual(rc, 0)


class Write(unittest.TestCase):
    def test_write_upserts_three_canonical_keys(self) -> None:
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="4", kickoff="2026-06-15T01:52:55Z")
            with mock.patch.object(wave_status.subprocess, "run", _FakeGh(_p5w4_prs())):
                rc = wave_status.main(["counters", "5", "4", "--status", str(status), "--write"])
            self.assertEqual(rc, 0)
            data = json.loads(status.read_text())
            self.assertEqual(data["wave_4_final_pr_count"], 19)
            self.assertEqual(data["wave_4_changes_requested_cycles"], 4)
            self.assertEqual(data["wave_4_top_concentration_pct"], 16)
            # The pre-existing keys must survive the targeted upsert.
            self.assertEqual(data["wave_4_repos_in_scope"], _REPOS)


if __name__ == "__main__":
    unittest.main()
