#!/usr/bin/env python3
"""Tests for the canonical promotion-audit CLI driver (run.py, main#690).

Two layers:
  - hermetic fixture tests (a synthetic repo tree built in a tempdir) that
    pin the driver's wiring + the empty-slug regression that caused the
    P5W4 24-spurious-AUTO mis-fire, with no dependency on the live repo;
  - a steady-state test against the real working tree asserting the driver
    still yields ~0 AUTO / 0 DECIDE (the same invariant test_smoke.py
    asserts for the hand-driven path, now asserted THROUGH the driver).
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import helpers as h  # noqa: E402
import run  # noqa: E402

_REPO_ROOT = _HERE.parent.parent.parent.parent
# Memory is now in-repo (#732 relocation), not under ~/.claude/projects/.
_MEMORY_DIR = str(_REPO_ROOT / ".claude" / "memory")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _make_fixture_repo(tmp: Path) -> tuple[run.AuditPaths, str]:
    """Build a minimal repo tree + git history; return (paths, repo_root)."""
    repo = tmp / "repo"
    mem = tmp / "memory"
    mem.mkdir(parents=True)

    # A charter with one skill-target section that has NOT been promoted
    # (no `promoted-to` back-reference). Under the old hand-rolled path this
    # section's empty `promoted_to` slug reached count_skill_invocations and
    # matched every commit -> spurious AUTO. The driver must keep it KEPT.
    _write(
        repo / ".claude" / "team" / "charter.md",
        "# Charter\n\n"
        "## Some Procedure <!-- promotion-target: skill -->\n\n"
        "Body of a procedure that has not been promoted yet.\n",
    )
    # One skill, not opted into hook promotion.
    _write(
        repo / ".claude" / "skills" / "demo-skill" / "SKILL.md",
        "---\nname: demo-skill\ndescription: demo\n---\n\nbody\n",
    )
    _write(repo / ".claude" / "team" / "feedback_log.md", "# Feedback Log\n")
    _write(
        repo / "cross-repo-status.json",
        '{"current_phase": 5, "current_wave": "wave-5", '
        '"wave_5_started_at": "2026-06-16T22:51:14Z"}\n',
    )
    # A memory that opts out of promotion -> KEPT.
    _write(
        mem / "project_demo.md",
        "---\nname: demo\ndescription: d\nmetadata:\n  type: project\n"
        "promotion_target: none\n---\n\nbody\n",
    )

    # Real git history whose commit messages contain slashes, so an empty
    # `--grep=/` slug WOULD match them (the bug condition).
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "f.txt").write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: run /some-thing and a/b path")

    paths = run.resolve_paths(repo, memory_dir=str(mem))
    return paths, str(repo)


class WaveNameResolution(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.status = Path(self._tmp.name) / "status.json"
        self.status.write_text('{"current_phase": 5, "current_wave": "wave-5"}')

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_legacy_form_normalized_to_global(self) -> None:
        # #810: legacy p{N}-wave-{M} input normalizes to phase-agnostic wave-{X}.
        self.assertEqual(run.resolve_wave_name("p3-wave-11", str(self.status)), "wave-11")

    def test_bare_wave_passthrough(self) -> None:
        self.assertEqual(run.resolve_wave_name("wave-5", str(self.status)), "wave-5")

    def test_bare_number_becomes_global(self) -> None:
        self.assertEqual(run.resolve_wave_name("7", str(self.status)), "wave-7")

    def test_no_arg_reads_status(self) -> None:
        self.assertEqual(run.resolve_wave_name(None, str(self.status)), "wave-5")

    def test_output_is_phase_agnostic_global(self) -> None:
        # #810 (retires #442): canonical output is the phase-agnostic wave-{X}.
        self.assertRegex(run.resolve_wave_name(None, str(self.status)), r"^wave-\d+$")

    def test_missing_phase_no_longer_required(self) -> None:
        # #810: current_phase is not needed to build the (phase-agnostic) name.
        self.status.write_text('{"current_wave": "wave-5"}')
        self.assertEqual(run.resolve_wave_name("wave-5", str(self.status)), "wave-5")
        self.assertEqual(run.resolve_wave_name(None, str(self.status)), "wave-5")


class AuditDateResolution(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.status = Path(self._tmp.name) / "status.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_prefers_kicked_off_at(self) -> None:
        self.status.write_text(
            '{"wave_5_kicked_off_at": "2026-06-10T00:00:00Z", '
            '"wave_5_started_at": "2026-06-16T00:00:00Z"}'
        )
        self.assertEqual(run.resolve_audit_date("p5-wave-5", str(self.status)), "2026-06-10")

    def test_falls_back_to_started_at(self) -> None:
        self.status.write_text('{"wave_5_started_at": "2026-06-16T22:51:14Z"}')
        self.assertEqual(run.resolve_audit_date("p5-wave-5", str(self.status)), "2026-06-16")

    def test_unknown_when_no_keys(self) -> None:
        self.status.write_text("{}")
        self.assertEqual(run.resolve_audit_date("p5-wave-5", str(self.status)), "unknown-date")


class EmptySlugRegression(unittest.TestCase):
    """The P5W4 root cause: an empty slug must never count all commits."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_empty_slug_counts_zero(self) -> None:
        self.assertEqual(h.count_skill_invocations("", str(_REPO_ROOT)), 0)
        self.assertEqual(h.count_skill_invocations("   ", str(_REPO_ROOT)), 0)

    def test_section_signal_slug_is_heading_when_unpromoted(self) -> None:
        sec = h.CharterSection(
            path="charter.md",
            heading="Some Procedure",
            promotion_target="skill",
            body="b",
            promoted_to="",
        )
        # Never empty -> never the all-commits count.
        self.assertEqual(run._section_signal_slug(sec), "some-procedure")

    def test_section_signal_slug_strips_skills_prefix(self) -> None:
        sec = h.CharterSection(
            path="charter.md",
            heading="X",
            promotion_target="skill",
            body="b",
            promoted_to="skills/my-skill",
        )
        self.assertEqual(run._section_signal_slug(sec), "my-skill")

    def test_unpromoted_section_is_kept_not_auto(self) -> None:
        # The end-to-end regression: in a repo whose commits contain
        # slashes, the unpromoted skill-target section must be KEPT.
        paths, _ = _make_fixture_repo(self.tmp)
        result = run.run_audit(paths, wave_name="p5-wave-5", audit_date="2026-06-16")
        sec_decisions = [d for d in result.decisions if d.from_tier == "charter"]
        self.assertEqual(len(sec_decisions), 1)
        self.assertEqual(sec_decisions[0].kind, "KEPT")
        self.assertEqual(result.counts()["AUTO"], 0)
        self.assertEqual(result.counts()["DECIDE"], 0)


class FixtureAuditShape(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_audit_covers_all_three_tiers(self) -> None:
        paths, _ = _make_fixture_repo(self.tmp)
        result = run.run_audit(paths, wave_name="p5-wave-5", audit_date="2026-06-16")
        tiers = {d.from_tier for d in result.decisions}
        self.assertEqual(tiers, {"memory", "charter", "skill"})

    def test_run_audit_is_deterministic(self) -> None:
        paths, _ = _make_fixture_repo(self.tmp)
        a = run.run_audit(paths, wave_name="p5-wave-5", audit_date="2026-06-16")
        b = run.run_audit(paths, wave_name="p5-wave-5", audit_date="2026-06-16")
        self.assertEqual(a.table(), b.table())
        self.assertEqual(a.counts(), b.counts())

    def test_summary_line_groups_superseded_and_already(self) -> None:
        paths, _ = _make_fixture_repo(self.tmp)
        result = run.run_audit(paths, wave_name="p5-wave-5", audit_date="2026-06-16")
        self.assertIn("Promotion audit p5-wave-5 complete:", result.summary_line())


class MainEntrypoint(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_main_returns_zero_and_prints_summary(self) -> None:
        # Exercise the argparse wiring + table path against the real repo
        # root (the default memory dir lives outside any tempdir).
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run.main(["p5-wave-5", "--repo-root", str(_REPO_ROOT), "--date", "2026-06-16"])
        self.assertEqual(rc, 0)
        # #810: main normalizes the legacy `p5-wave-5` arg to the phase-agnostic
        # canonical `wave-5` before rendering.
        self.assertIn("Promotion audit wave-5 complete:", buf.getvalue())

    def test_json_flag_emits_parseable_payload(self) -> None:
        import json

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run.main(
                ["p5-wave-5", "--json", "--repo-root", str(_REPO_ROOT), "--date", "2026-06-16"]
            )
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        # #810: legacy arg normalized to phase-agnostic canonical form.
        self.assertEqual(payload["wave_name"], "wave-5")
        self.assertIn("counts", payload)
        self.assertIn("decisions", payload)


@unittest.skipUnless(
    os.path.isdir(_MEMORY_DIR),
    "steady-state test requires the project's memory directory",
)
class SteadyStateThroughDriver(unittest.TestCase):
    """The driver must reproduce the smoke-test invariant: 0 AUTO / 0 DECIDE
    on the real working tree — proving the canonical wiring matches the
    hand-driven expectation while closing the empty-slug mis-fire."""

    def test_zero_auto_zero_decide(self) -> None:
        paths = run.resolve_paths(_REPO_ROOT)
        result = run.run_audit(paths, wave_name="p5-wave-5", audit_date="2026-06-16")
        counts = result.counts()
        auto = [d.item_id for d in result.decisions if d.kind == "AUTO"]
        decide = [d.item_id for d in result.decisions if d.kind == "DECIDE"]
        self.assertEqual(counts["AUTO"], 0, f"unexpected AUTO: {auto}")
        self.assertEqual(counts["DECIDE"], 0, f"unexpected DECIDE: {decide}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
