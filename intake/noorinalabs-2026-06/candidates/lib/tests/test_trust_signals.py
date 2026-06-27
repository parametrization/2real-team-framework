"""Tests for trust_signals — per-engineer mechanical trust signals + the
evidence-anchored scoring model (main#842, persona Option B §4b / Finding D).

Covers:
  * Extraction maps author identity (commit author) → prs_merged / ci_red /
    rework, and reviewer identity (Requestor field) → must_fix_caught, reusing
    wave_status.merged_prs with its no-shell list-arg-vector contract.
  * Verdict parsing accepts bare AND bold Requestor/RequestOrReplied forms and
    detects self-marked false-positives.
  * score_delta is bidirectional and clamped to [-2, +2].
  * decay drifts unsignalled scores one step toward NEUTRAL after N waves.
  * distribution discipline reserves 5 for the top relative performer.
  * the forced negative-signal pass bans bare "None".
  * the performance-triggered retirement trigger fires on sustained bottom-tier
    or repeated CI-red merges, and not before K waves of evidence.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

# Helper lives at .claude/lib/trust_signals.py; this test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import trust_signals as ts  # noqa: E402
import wave_status  # noqa: E402

_REPOS = ["noorinalabs-isnad-graph", "noorinalabs-user-service"]


def _verdict(requestor: str, requestee: str, verdict: str, *, bold: bool = False) -> str:
    if bold:
        return (
            f"**Requestor:** {requestor}\n"
            f"**Requestee:** {requestee}\n"
            f"**RequestOrReplied:** {verdict}\n"
        )
    return f"Requestor: {requestor}\nRequestee: {requestee}\nRequestOrReplied: {verdict}\n"


class _FakeGh:
    """subprocess.run side_effect emulating the gh calls trust_signals makes,
    driven by a flat PR fixture. Each PR dict carries: repo, number, sha,
    mergedAt, commit_author, comments (list of bodies), ci_red (bool)."""

    def __init__(self, prs: list[dict]) -> None:
        self.prs = prs
        self.calls: list[list[str]] = []

    def __call__(self, cmd, *args, **kwargs):  # noqa: ANN001
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
                    "author": {"login": "octocat"},
                }
                for p in self.prs
                if p["repo"] == repo
            ]
            return SimpleNamespace(stdout=json.dumps(listed), returncode=0, stderr="")

        if cmd[1:3] == ["pr", "view"]:
            number = int(cmd[3])
            p = next(x for x in self.prs if x["number"] == number)
            rollup = [{"conclusion": "FAILURE"}] if p.get("ci_red") else [{"conclusion": "SUCCESS"}]
            return SimpleNamespace(stdout=json.dumps(rollup), returncode=0, stderr="")

        if cmd[1] == "api":
            path = cmd[2]
            parts = path.split("/")
            if "/commits/" in path:
                sha = parts[4]
                name = next(p["commit_author"] for p in self.prs if p["sha"] == sha)
                return SimpleNamespace(stdout=name + "\n", returncode=0, stderr="")
            if path.endswith("/comments"):
                number = int(parts[4])
                bodies = next(p.get("comments", []) for p in self.prs if p["number"] == number)
                return SimpleNamespace(stdout=json.dumps(bodies), returncode=0, stderr="")

        raise AssertionError(f"unexpected gh call: {cmd!r}")


def _write_status(path: Path, *, repos: list[str], wave: str) -> None:
    path.write_text(
        json.dumps({"current_wave": int(wave), f"wave_{wave}_repos_in_scope": repos}) + "\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# Verdict parsing (pure)
# --------------------------------------------------------------------------- #
class ParseVerdicts(unittest.TestCase):
    def test_bare_and_bold_forms(self) -> None:
        bodies = [
            _verdict("Aino Virtanen", "Nadia Khoury", "ChangesRequested"),
            _verdict("Santiago Ferreira", "Nadia Khoury", "Approved", bold=True),
            "just a normal comment, no verdict here",
        ]
        verdicts = ts.parse_verdicts(bodies)
        self.assertEqual(len(verdicts), 2)
        self.assertEqual(verdicts[0].requestor, "Aino Virtanen")
        self.assertEqual(verdicts[0].requestee, "Nadia Khoury")
        self.assertEqual(verdicts[0].verdict, "ChangesRequested")
        self.assertEqual(verdicts[1].requestor, "Santiago Ferreira")
        self.assertEqual(verdicts[1].verdict, "Approved")

    def test_false_positive_detected(self) -> None:
        body = (
            _verdict("Aino Virtanen", "Nadia Khoury", "ChangesRequested")
            + "\nUpdate: this was a false-positive, withdrawing."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertTrue(v.false_positive)

    # -- Regression: #881 -- Approving verdicts must never score as FP even when
    # the prose mentions "false-positive" (real evidence from PR #873).

    def test_approved_verdict_with_fp_prose_is_not_a_fp(self) -> None:
        """Aino's #873 body: approval praising a false-positive test — must score 0."""
        body = (
            _verdict("Aino Virtanen", "Santiago Ferreira", "Approved")
            + "\nThe false-positive test (`type` keyword inside a function param list…)"
            " validates the anchor correctly rejects it."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertFalse(v.false_positive)

    def test_approved_verdict_with_fp_in_identifier_is_not_a_fp(self) -> None:
        """Bereket's #873 body: 'No false-positive on type in non-declaration contexts'."""
        body = (
            _verdict("Bereket Tadesse", "Santiago Ferreira", "Approved")
            + "\nNo false-positive on `type` in non-declaration contexts."
            " test_no_false_positive_type_in_non_decl_context passes cleanly."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertFalse(v.false_positive)

    def test_fp_in_code_span_is_not_a_fp(self) -> None:
        """FP keyword inside an inline code span in a non-approving verdict is ignored."""
        body = (
            _verdict("Idris Yusuf", "Nadia Khoury", "Reply")
            + "\nSee `test_no_false_positive_case` for coverage."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertFalse(v.false_positive)

    def test_fp_in_fenced_block_is_not_a_fp(self) -> None:
        """FP keyword inside a fenced code block is ignored."""
        body = (
            _verdict("Aino Virtanen", "Nadia Khoury", "ChangesRequested")
            + "\n```\n# test_no_false_positive_type passes\nretracted = False\n```\n"
            "Looks good otherwise."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertFalse(v.false_positive)

    def test_genuine_withdrawal_on_changes_requested_still_counts(self) -> None:
        """A real self-retraction on a ChangesRequested verdict must still score 1."""
        body = (
            _verdict("Idris Yusuf", "Mateo Salazar", "ChangesRequested")
            + "\nOn reflection this was invalid — withdrawn, my mistake."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertTrue(v.false_positive)

    def test_withdrawal_keyword_in_plain_prose_on_non_approval_counts(self) -> None:
        """'retracted' outside any code markup on a non-Approved verdict counts."""
        body = (
            _verdict("Wanjiku Mwangi", "Nadia Khoury", "Reply")
            + "\nI retracted my earlier finding after re-reading the spec."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertTrue(v.false_positive)


# --------------------------------------------------------------------------- #
# Extraction (gh-mocked)
# --------------------------------------------------------------------------- #
class Extract(unittest.TestCase):
    def _run(self, prs: list[dict]) -> dict[str, ts.Signals]:
        fake = _FakeGh(prs)
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="17")
            with mock.patch.object(wave_status.subprocess, "run", fake):
                sigs = ts.extract_signals("6", "17", status)
        self.fake = fake
        return sigs

    def test_author_and_reviewer_attribution(self) -> None:
        prs = [
            {
                "repo": _REPOS[0],
                "number": 901,
                "sha": "s901",
                "mergedAt": "2026-06-24T02:00:00Z",
                "commit_author": "Nadia Khoury",
                "comments": [_verdict("Aino Virtanen", "Nadia Khoury", "ChangesRequested")],
                "ci_red": False,
            },
            {
                "repo": _REPOS[1],
                "number": 902,
                "sha": "s902",
                "mergedAt": "2026-06-24T03:00:00Z",
                "commit_author": "Nadia Khoury",
                "comments": [_verdict("Aino Virtanen", "Nadia Khoury", "Approved")],
                "ci_red": True,
            },
        ]
        sigs = self._run(prs)
        nadia = sigs["Nadia Khoury"]
        self.assertEqual(nadia.prs_merged, 2)
        self.assertEqual(nadia.authored_prs, [901, 902])
        self.assertEqual(nadia.must_fix_received, 1)
        self.assertEqual(nadia.rework_cycles, 1)  # one PR needed a rework round
        self.assertEqual(nadia.ci_red_merges, 1)  # PR 902 merged red
        # Reviewer credit lands on the Requestor, not the gh principal.
        self.assertEqual(sigs["Aino Virtanen"].must_fix_caught, 1)

    def test_false_positive_dings_reviewer(self) -> None:
        prs = [
            {
                "repo": _REPOS[0],
                "number": 903,
                "sha": "s903",
                "mergedAt": "2026-06-24T02:00:00Z",
                "commit_author": "Mateo Salazar",
                "comments": [
                    _verdict("Idris Yusuf", "Mateo Salazar", "ChangesRequested")
                    + "\nOn reflection this finding was invalid finding — withdrawn."
                ],
                "ci_red": False,
            },
        ]
        sigs = self._run(prs)
        self.assertEqual(sigs["Idris Yusuf"].review_false_positives, 1)
        self.assertEqual(sigs["Idris Yusuf"].must_fix_caught, 1)

    def test_gh_calls_are_list_vectors_no_shell(self) -> None:
        prs = [
            {
                "repo": _REPOS[0],
                "number": 904,
                "sha": "s904",
                "mergedAt": "2026-06-24T02:00:00Z",
                "commit_author": "Nadia Khoury",
                "comments": [],
                "ci_red": False,
            }
        ]
        self._run(prs)
        self.assertTrue(self.fake.calls)
        self.assertTrue(all(isinstance(c, list) and c[0] == "gh" for c in self.fake.calls))

    def test_approved_with_fp_prose_does_not_ding_reviewer(self) -> None:
        """Regression #881: Aino + Bereket both Approved on PR #873 with FP prose.

        Both bodies mention 'false-positive' but in the context of praising the
        PR's own test coverage — neither is a retraction.  review_false_positives
        must remain 0 for both reviewers.
        """
        aino_body = (
            _verdict("Aino Virtanen", "Santiago Ferreira", "Approved")
            + "\nThe false-positive test (`type` keyword inside a function param list…)"
            " validates the … anchor correctly rejects it."
        )
        bereket_body = (
            _verdict("Bereket Tadesse", "Santiago Ferreira", "Approved")
            + "\nNo false-positive on `type` in non-declaration contexts."
            " test_no_false_positive_type_in_non_decl_context passes."
        )
        prs = [
            {
                "repo": _REPOS[0],
                "number": 873,
                "sha": "s873",
                "mergedAt": "2026-06-24T02:00:00Z",
                "commit_author": "Santiago Ferreira",
                "comments": [aino_body, bereket_body],
                "ci_red": False,
            },
        ]
        sigs = self._run(prs)
        aino_sig = sigs.get("Aino Virtanen", ts.Signals())
        bereket_sig = sigs.get("Bereket Tadesse", ts.Signals())
        self.assertEqual(aino_sig.review_false_positives, 0)
        self.assertEqual(bereket_sig.review_false_positives, 0)


# --------------------------------------------------------------------------- #
# Scoring (pure)
# --------------------------------------------------------------------------- #
class ScoreDelta(unittest.TestCase):
    def test_clean_multi_pr_plus_one(self) -> None:
        s = ts.Signals(prs_merged=3)
        self.assertEqual(ts.score_delta(s), 1)

    def test_strong_reviewer_and_author_capped_at_two(self) -> None:
        s = ts.Signals(prs_merged=3, must_fix_caught=4)
        self.assertEqual(ts.score_delta(s), 2)

    def test_ci_red_is_negative(self) -> None:
        s = ts.Signals(prs_merged=2, ci_red_merges=1)
        self.assertEqual(ts.score_delta(s), -1)

    def test_false_positive_is_negative(self) -> None:
        s = ts.Signals(prs_merged=1, must_fix_caught=3, review_false_positives=1)
        self.assertEqual(ts.score_delta(s), -1)

    def test_clamped_to_minus_two(self) -> None:
        s = ts.Signals(prs_merged=1, ci_red_merges=5)
        self.assertEqual(ts.score_delta(s), -2)

    def test_no_signal_zero_delta(self) -> None:
        self.assertEqual(ts.score_delta(ts.Signals()), 0)

    def test_one_clean_pr_no_increase(self) -> None:
        # A single clean PR is not "exceptional" — no bump.
        self.assertEqual(ts.score_delta(ts.Signals(prs_merged=1)), 0)


class Decay(unittest.TestCase):
    def test_no_decay_before_threshold(self) -> None:
        self.assertEqual(ts.decay(5, 2), 5)
        self.assertEqual(ts.decay(1, 2), 1)

    def test_decays_high_down(self) -> None:
        self.assertEqual(ts.decay(5, 3), 4)

    def test_decays_low_up(self) -> None:
        self.assertEqual(ts.decay(2, 3), 3)

    def test_neutral_stays(self) -> None:
        self.assertEqual(ts.decay(3, 9), 3)


class DistributionDiscipline(unittest.TestCase):
    def test_five_reserved_for_top_performer(self) -> None:
        proposals = {
            "Top": (5, ts.Signals(prs_merged=5, must_fix_caught=3)),
            "AlsoFive": (5, ts.Signals(prs_merged=2)),
        }
        out = ts.apply_distribution_discipline(proposals)
        self.assertEqual(out["Top"], 5)
        self.assertEqual(out["AlsoFive"], 4)  # capped — not the top performer

    def test_four_passes_through(self) -> None:
        proposals = {"X": (4, ts.Signals(prs_merged=2))}
        self.assertEqual(ts.apply_distribution_discipline(proposals)["X"], 4)

    def test_no_five_when_top_is_not_positive(self) -> None:
        proposals = {"X": (5, ts.Signals())}
        self.assertEqual(ts.apply_distribution_discipline(proposals)["X"], 4)


class NegativeSignalPass(unittest.TestCase):
    def test_clean_line_shows_numbers_not_none(self) -> None:
        line = ts.negative_signal_line("Nadia Khoury", ts.Signals(prs_merged=2, must_fix_caught=3))
        self.assertIn("metrics clean", line)
        self.assertNotEqual(line.strip().lower(), "none")
        self.assertIn("prs_merged=2", line)

    def test_negative_line_cites_gap(self) -> None:
        line = ts.negative_signal_line("X", ts.Signals(prs_merged=1, ci_red_merges=2))
        self.assertIn("2 CI-red merge", line)

    def test_validate_flags_bare_none(self) -> None:
        lines = ["None", "- none", "N/A", "Aino: metrics clean: prs_merged=1"]
        offenders = ts.validate_negative_signal_pass(lines)
        self.assertEqual(len(offenders), 3)

    def test_validate_clean_pass_returns_empty(self) -> None:
        lines = ["Aino: metrics clean: prs_merged=1", "X: 1 CI-red merge(s)"]
        self.assertEqual(ts.validate_negative_signal_pass(lines), [])


class RetirementTrigger(unittest.TestCase):
    def test_sustained_bottom_tier_fires(self) -> None:
        fired, reason = ts.retirement_trigger([3, 2, 2, 1], [0, 0, 0, 0])
        self.assertTrue(fired)
        self.assertIn("bottom-tier", reason)

    def test_repeated_ci_red_fires(self) -> None:
        fired, reason = ts.retirement_trigger([3, 3, 3], [1, 2, 1])
        self.assertTrue(fired)
        self.assertIn("CI-red", reason)

    def test_not_enough_history_never_fires(self) -> None:
        fired, _ = ts.retirement_trigger([1, 1], [1, 1])
        self.assertFalse(fired)

    def test_healthy_does_not_fire(self) -> None:
        fired, _ = ts.retirement_trigger([4, 4, 5], [0, 0, 0])
        self.assertFalse(fired)


if __name__ == "__main__":
    unittest.main()
