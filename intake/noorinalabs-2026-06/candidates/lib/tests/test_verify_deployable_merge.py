"""Tests for verify_deployable_merge — post-merge deployable verification (main#864).

Network is never touched: the gh-shelling functions (fetch_workflow_files,
fetch_runs_for_sha) are monkeypatched, and the poll loop's sleep/clock are
injected so the time-based logic runs instantly. Coverage maps to the gap the
tool closes:

  1. the GHA-YAML ``on: True`` boolean gotcha is handled
  2. push-to-main / tag / pull_request triggers classify correctly
  3. post-merge-only = deployable AND not pull_request
  4. a FAILED post-merge run -> NOT verified (exit 1)
  5. a MISSING expected workflow (silent drop) -> NOT verified, never a pass
  6. pending resolves to verified once runs complete across polls
  7. no expected workflows resolved -> GhError (exit 2)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import verify_deployable_merge as vdm  # noqa: E402

# A publish workflow: push-to-main + tags, NO pull_request → post-merge-only.
PUBLISH_YAML = """
name: Publish to GHCR
on:
  push:
    branches: [main]
    tags:
      - "v*"
  workflow_dispatch:
jobs:
  build:
    runs-on: ubuntu-latest
    steps: [{run: "echo hi"}]
"""

# A standard CI workflow: push AND pull_request → deployable but NOT post-merge-only.
CI_YAML = """
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps: [{run: "pytest"}]
"""

# A PR-only workflow: never deployable.
PR_ONLY_YAML = """
name: Lint
on: pull_request
jobs:
  lint: {runs-on: ubuntu-latest, steps: [{run: "ruff"}]}
"""

# A tag-only workflow (like isnad-graph's "Pipeline"): runs on a data-v* tag
# push, NOT on a branch merge to main. Must NOT be merge-triggered.
TAG_ONLY_YAML = """
name: Pipeline
on:
  workflow_dispatch:
  push:
    tags:
      - 'data-v*'
jobs:
  run: {runs-on: ubuntu-latest, steps: [{run: "make"}]}
"""

# A push-to-main workflow with a paths filter: conditional, so NOT required
# (it may legitimately skip a merge that doesn't touch those paths).
PATH_FILTERED_YAML = """
name: Docs
on:
  push:
    branches: [main]
    paths: ["docs/**"]
jobs:
  build: {runs-on: ubuntu-latest, steps: [{run: "mkdocs"}]}
"""


class ClassifyTriggerTests(unittest.TestCase):
    def test_on_boolean_gotcha_is_handled(self) -> None:
        # PyYAML parses the bare `on` key as the boolean True; the publish YAML
        # must still classify as push-triggered despite that.
        trig = vdm.classify_trigger("Publish to GHCR", ".github/workflows/p.yml", PUBLISH_YAML)
        self.assertIsNotNone(trig)
        assert trig is not None
        self.assertTrue(trig.on_push_main)
        self.assertTrue(trig.on_tag)
        self.assertFalse(trig.on_pull_request)

    def test_publish_is_post_merge_only(self) -> None:
        trig = vdm.classify_trigger("Publish to GHCR", "p.yml", PUBLISH_YAML)
        assert trig is not None
        self.assertTrue(trig.is_merge_triggered)
        self.assertTrue(trig.is_post_merge_only)

    def test_ci_is_merge_triggered_but_not_post_merge_only(self) -> None:
        trig = vdm.classify_trigger("CI", "ci.yml", CI_YAML)
        assert trig is not None
        self.assertTrue(trig.is_merge_triggered)
        self.assertFalse(trig.is_post_merge_only)  # also runs on PRs

    def test_pr_only_is_not_merge_triggered(self) -> None:
        trig = vdm.classify_trigger("Lint", "lint.yml", PR_ONLY_YAML)
        assert trig is not None
        self.assertFalse(trig.is_merge_triggered)

    def test_tag_only_is_not_merge_triggered(self) -> None:
        # The "Pipeline" false-positive: tag push ≠ branch merge to main.
        trig = vdm.classify_trigger("Pipeline", "pipeline.yml", TAG_ONLY_YAML)
        assert trig is not None
        self.assertFalse(trig.on_push_main)
        self.assertTrue(trig.on_tag)
        self.assertFalse(trig.is_merge_triggered)

    def test_path_filtered_push_is_not_required(self) -> None:
        trig = vdm.classify_trigger("Docs", "docs.yml", PATH_FILTERED_YAML)
        assert trig is not None
        self.assertTrue(trig.on_push_main)
        self.assertTrue(trig.push_path_filtered)
        self.assertFalse(trig.is_merge_triggered)  # conditional → not required

    def test_list_form_on(self) -> None:
        trig = vdm.classify_trigger("L", "l.yml", "on: [push, pull_request]\njobs: {}\n")
        assert trig is not None
        self.assertTrue(trig.on_push_main)  # no branch filter → all branches incl main
        self.assertTrue(trig.on_pull_request)

    def test_string_form_on(self) -> None:
        trig = vdm.classify_trigger("S", "s.yml", "on: push\njobs: {}\n")
        assert trig is not None
        self.assertTrue(trig.on_push_main)
        self.assertFalse(trig.on_pull_request)

    def test_push_to_non_main_branch_only(self) -> None:
        text = "on:\n  push:\n    branches: [develop]\njobs: {}\n"
        trig = vdm.classify_trigger("D", "d.yml", text)
        assert trig is not None
        self.assertFalse(trig.on_push_main)  # only develop, not main

    def test_unparseable_returns_none(self) -> None:
        self.assertIsNone(vdm.classify_trigger("X", "x.yml", "::: not yaml :::\n\t- bad"))


class DisplayNameTests(unittest.TestCase):
    def test_uses_name_field(self) -> None:
        self.assertEqual(vdm.workflow_display_name("p.yml", PUBLISH_YAML), "Publish to GHCR")

    def test_falls_back_to_filename(self) -> None:
        text = "on: push\njobs: {}\n"
        self.assertEqual(vdm.workflow_display_name(".github/workflows/anon.yml", text), "anon.yml")


class ClassifyRunTests(unittest.TestCase):
    def test_pending_when_not_completed(self) -> None:
        self.assertEqual(vdm.classify_run("in_progress", "").bucket, "pending")
        self.assertEqual(vdm.classify_run("queued", "").bucket, "pending")

    def test_pass_buckets(self) -> None:
        self.assertEqual(vdm.classify_run("completed", "success").bucket, "pass")
        self.assertEqual(vdm.classify_run("completed", "skipped").bucket, "pass")

    def test_fail_buckets(self) -> None:
        self.assertEqual(vdm.classify_run("completed", "failure").bucket, "fail")
        self.assertEqual(vdm.classify_run("completed", "cancelled").bucket, "fail")
        # Completed with a null conclusion must NOT pass.
        self.assertEqual(vdm.classify_run("completed", "").bucket, "fail")


class AggregateTests(unittest.TestCase):
    def test_all_pass_verified(self) -> None:
        runs = [
            {
                "name": "Publish to GHCR",
                "status": "completed",
                "conclusion": "success",
                "html_url": "u",
            },
            {"name": "CI", "status": "completed", "conclusion": "success", "html_url": "u"},
        ]
        agg = vdm.aggregate(["CI", "Publish to GHCR"], runs)
        self.assertTrue(agg.verified)
        self.assertFalse(agg.pending)

    def test_one_failure_not_verified(self) -> None:
        runs = [
            {
                "name": "Publish to GHCR",
                "status": "completed",
                "conclusion": "failure",
                "html_url": "u",
            },
        ]
        agg = vdm.aggregate(["Publish to GHCR"], runs)
        self.assertFalse(agg.verified)
        self.assertFalse(agg.pending)

    def test_missing_expected_is_not_verified(self) -> None:
        # Expected a workflow that produced no run for the SHA → silent drop.
        agg = vdm.aggregate(["Publish to GHCR"], [])
        self.assertFalse(agg.verified)
        self.assertTrue(agg.pending)
        self.assertEqual(agg.missing, ["Publish to GHCR"])

    def test_rerun_keeps_newest(self) -> None:
        # API order is newest-first; the first record per name wins.
        runs = [
            {"name": "CI", "status": "completed", "conclusion": "success", "html_url": "new"},
            {"name": "CI", "status": "completed", "conclusion": "failure", "html_url": "old"},
        ]
        agg = vdm.aggregate(["CI"], runs)
        self.assertTrue(agg.verified)

    def test_no_red_net_catches_unexpected_failure(self) -> None:
        # A path-filtered workflow that DID run and failed is not in `expected`,
        # but the no-red safety net must still fail the verification.
        runs = [
            {"name": "CI", "status": "completed", "conclusion": "success", "html_url": "u"},
            {"name": "Docs", "status": "completed", "conclusion": "failure", "html_url": "dx"},
        ]
        agg = vdm.aggregate(["CI"], runs)
        self.assertFalse(agg.verified)
        self.assertTrue(any(r["name"] == "Docs" and r["bucket"] == "fail" for r in agg.rows))

    def test_no_red_net_waits_on_unexpected_pending(self) -> None:
        runs = [
            {"name": "CI", "status": "completed", "conclusion": "success", "html_url": "u"},
            {"name": "Docs", "status": "in_progress", "conclusion": "", "html_url": "dx"},
        ]
        agg = vdm.aggregate(["CI"], runs)
        self.assertTrue(agg.pending)
        self.assertFalse(agg.verified)


class VerifyPollLoopTests(unittest.TestCase):
    def test_resolves_pending_across_polls(self) -> None:
        # First poll: still running. Second poll: completed success.
        responses = [
            [
                {
                    "name": "Publish to GHCR",
                    "status": "in_progress",
                    "conclusion": "",
                    "html_url": "u",
                }
            ],
            [
                {
                    "name": "Publish to GHCR",
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": "u",
                }
            ],
        ]

        def fake_runs(repo: str, sha: str) -> list[dict]:
            return responses.pop(0)

        self._patch(vdm, "fetch_runs_for_sha", fake_runs)
        clock_vals = iter([0.0, 1.0, 2.0, 3.0, 4.0])

        result = vdm.verify(
            "o/r",
            "deadbeef",
            explicit_workflows=["Publish to GHCR"],
            timeout=100,
            poll=5,
            sleep=lambda _s: None,
            clock=lambda: next(clock_vals),
        )
        self.assertTrue(result.verified)

    def test_times_out_pending(self) -> None:
        def fake_runs(repo: str, sha: str) -> list[dict]:
            return [{"name": "P", "status": "queued", "conclusion": "", "html_url": "u"}]

        self._patch(vdm, "fetch_runs_for_sha", fake_runs)
        # clock jumps past the deadline immediately after the first read.
        clock_vals = iter([0.0, 999.0, 1000.0])
        result = vdm.verify(
            "o/r",
            "sha",
            explicit_workflows=["P"],
            timeout=10,
            poll=1,
            sleep=lambda _s: None,
            clock=lambda: next(clock_vals),
        )
        self.assertFalse(result.verified)
        self.assertTrue(result.pending)

    def test_no_required_verifies_when_nothing_red(self) -> None:
        # A repo with no post-merge-only workflow (only PR-visible CI) and a
        # clean run set: "nothing required" → verified, NOT an error.
        def only_pr(repo: str, ref: str) -> dict[str, str]:
            return {"pr.yml": PR_ONLY_YAML, "tag.yml": TAG_ONLY_YAML}

        def clean_runs(repo: str, sha: str) -> list[dict]:
            return []

        self._patch(vdm, "fetch_workflow_files", only_pr)
        self._patch(vdm, "fetch_runs_for_sha", clean_runs)
        result = vdm.verify("o/r", "sha", timeout=1, poll=1, sleep=lambda _s: None)
        self.assertTrue(result.verified)
        self.assertEqual(result.expected, [])

    def test_no_required_but_red_run_is_caught_by_net(self) -> None:
        # Even with nothing "required", a run that executed and failed must fail
        # verification via the no-red safety net.
        def only_pr(repo: str, ref: str) -> dict[str, str]:
            return {"pr.yml": PR_ONLY_YAML}

        def red_run(repo: str, sha: str) -> list[dict]:
            return [
                {"name": "Deploy", "status": "completed", "conclusion": "failure", "html_url": "u"}
            ]

        self._patch(vdm, "fetch_workflow_files", only_pr)
        self._patch(vdm, "fetch_runs_for_sha", red_run)
        result = vdm.verify("o/r", "sha", timeout=1, poll=1, sleep=lambda _s: None)
        self.assertFalse(result.verified)
        self.assertEqual(result.expected, [])

    # -- helper: monkeypatch a module attr for the duration of one test --
    def _patch(self, mod: object, attr: str, value) -> None:
        original = getattr(mod, attr)
        setattr(mod, attr, value)
        self.addCleanup(setattr, mod, attr, original)


class ResolveExpectedTests(unittest.TestCase):
    def test_require_deployable_narrows_to_post_merge_only(self) -> None:
        files = {
            "p.yml": PUBLISH_YAML,  # post-merge-only
            "ci.yml": CI_YAML,  # merge-triggered but also PR
            "lint.yml": PR_ONLY_YAML,  # not merge-triggered (PR only)
            "pipeline.yml": TAG_ONLY_YAML,  # tag-only, not a branch merge
            "docs.yml": PATH_FILTERED_YAML,  # conditional (paths) → not required
        }
        original = vdm.fetch_workflow_files
        vdm.fetch_workflow_files = lambda repo, ref: files  # type: ignore[assignment]
        self.addCleanup(setattr, vdm, "fetch_workflow_files", original)

        all_deployable = vdm.resolve_expected("o/r", "sha", None, require_deployable=False)
        self.assertEqual(all_deployable, ["CI", "Publish to GHCR"])

        post_only = vdm.resolve_expected("o/r", "sha", None, require_deployable=True)
        self.assertEqual(post_only, ["Publish to GHCR"])


if __name__ == "__main__":
    unittest.main()
