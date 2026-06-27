#!/usr/bin/env python3
"""Tests for post_wave_kickoff_comment PostToolUse hook.

Two test surfaces:

1. **Fixture-driven scenarios** — `.claude/hooks/fixtures/post_wave_kickoff_comment/`
   contains JSON test cases with this shape:

       {
           "description": "<human label>",
           "command": "<raw bash command string>",
           "status": <cross-repo-status.json dict>,
           "existing_comments": [<comment dicts>],
           "post_succeeds": <bool>,
           "expect_action": "post" | "skip_*" | null,
           "expect_body_contains": [<substrings>]   # only meaningful for "post"
       }

   The injectors in `post_wave_kickoff_comment.check()` (`status_loader`,
   `comment_fetcher`, `comment_poster`, `body_writer`) let each test mock
   the four external interactions (status JSON read, gh comments fetch,
   gh comment post, body file write) without monkeypatching subprocess.

2. **Direct unit tests** — `parse_label_apply_command`,
   `find_assignment_row`, `render_kickoff_comment`,
   `kickoff_already_posted`. These pin behaviors that don't fit cleanly
   into fixture form (regex shapes, table-driven row lookups).

Run:  python3 -m pytest .claude/hooks/tests/test_post_wave_kickoff_comment.py -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
_FIXTURES_DIR = _HOOKS_DIR / "fixtures" / "post_wave_kickoff_comment"

sys.path.insert(0, str(_HOOKS_DIR))

import post_wave_kickoff_comment as hook  # noqa: E402


def _load_fixtures() -> list[tuple[str, dict]]:
    fixtures = []
    for path in sorted(_FIXTURES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        fixtures.append((path.stem, data))
    return fixtures


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class FixtureDrivenScenarioTests(unittest.TestCase):
    """One test per fixture file — generated dynamically."""


def _add_fixture_test(name: str, fixture: dict) -> None:
    description = fixture.get("description", name)
    command = fixture["command"]
    status = fixture.get("status")
    existing_comments = fixture.get("existing_comments", [])
    post_succeeds = fixture.get("post_succeeds", True)
    expect_action = fixture.get("expect_action")
    expect_body_contains = fixture.get("expect_body_contains", [])

    def test_method(self: unittest.TestCase) -> None:
        captured: dict = {}

        def fake_status():
            return status

        def fake_fetch(repo, num):
            return existing_comments

        def fake_post(repo, num, body_path):
            captured["repo"] = repo
            captured["num"] = num
            captured["body_path"] = body_path
            captured["body"] = Path(body_path).read_text(encoding="utf-8")
            return post_succeeds

        with tempfile.TemporaryDirectory() as td:

            def fake_writer(body, repo, num):
                path = Path(td) / f"body-{repo}-{num}.md"
                path.write_text(body, encoding="utf-8")
                return path

            result = hook.check(
                _bash(command),
                status_loader=fake_status,
                comment_fetcher=fake_fetch,
                comment_poster=fake_post,
                body_writer=fake_writer,
            )

            if expect_action is None:
                self.assertIsNone(
                    result,
                    f"{description!r}: expected hook to not apply (None), got: {result}",
                )
                return

            self.assertIsNotNone(
                result,
                f"{description!r}: expected action={expect_action!r}, got None",
            )
            assert result is not None
            self.assertEqual(
                result.get("action"),
                expect_action,
                f"{description!r}: action mismatch: {result}",
            )

            if expect_action == "post":
                for needle in expect_body_contains:
                    self.assertIn(
                        needle,
                        captured.get("body", ""),
                        f"{description!r}: missing expected substring {needle!r} in body:\n"
                        f"{captured.get('body', '(no body captured)')}",
                    )

    test_method.__name__ = f"test_{name}"
    test_method.__doc__ = description
    setattr(FixtureDrivenScenarioTests, test_method.__name__, test_method)


for _fixture_name, _fixture_data in _load_fixtures():
    _add_fixture_test(_fixture_name, _fixture_data)


class ParseLabelApplyCommandTests(unittest.TestCase):
    """Direct coverage of the bash-command parser."""

    def test_canonical_form(self):
        self.assertEqual(
            hook.parse_label_apply_command(
                'gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-9"'
            ),
            ("noorinalabs-main", "123", "p3-wave-9"),
        )

    def test_flag_order_swapped(self):
        self.assertEqual(
            hook.parse_label_apply_command(
                'gh issue edit 456 --add-label "p3-wave-9" --repo noorinalabs/noorinalabs-deploy'
            ),
            ("noorinalabs-deploy", "456", "p3-wave-9"),
        )

    def test_equals_form(self):
        self.assertEqual(
            hook.parse_label_apply_command(
                "gh issue edit 789 --repo=noorinalabs/noorinalabs-isnad-graph --add-label=p3-wave-8"
            ),
            ("noorinalabs-isnad-graph", "789", "p3-wave-8"),
        )

    def test_multiple_add_label_picks_wave_label(self):
        """When the command applies BOTH a wave label and an implementer
        label, only the wave label matters for hook trigger."""
        self.assertEqual(
            hook.parse_label_apply_command(
                "gh issue edit 100 --repo noorinalabs/noorinalabs-main "
                '--add-label "Aino_Virtanen" --add-label "p3-wave-9"'
            ),
            ("noorinalabs-main", "100", "p3-wave-9"),
        )

    def test_non_wave_label_returns_none(self):
        self.assertIsNone(
            hook.parse_label_apply_command(
                'gh issue edit 100 --repo noorinalabs/noorinalabs-main --add-label "tech-debt"'
            )
        )

    def test_non_issue_edit_command_returns_none(self):
        self.assertIsNone(
            hook.parse_label_apply_command(
                'gh pr edit 42 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-9"'
            )
        )

    def test_unrelated_command_returns_none(self):
        self.assertIsNone(hook.parse_label_apply_command("echo hello"))

    def test_empty_command_returns_none(self):
        self.assertIsNone(hook.parse_label_apply_command(""))

    def test_compound_command_picks_label_segment(self):
        """`true && gh issue edit ... --add-label "p3-wave-9"` still matches."""
        self.assertEqual(
            hook.parse_label_apply_command(
                "true && gh issue edit 999 --repo noorinalabs/noorinalabs-main "
                '--add-label "p3-wave-9"'
            ),
            ("noorinalabs-main", "999", "p3-wave-9"),
        )

    # --- #467 between-wave relabel filter ---

    def test_between_wave_relabel_returns_none(self):
        """Issue #467: `--add-label "p3-wave-11" --remove-label "p3-wave-10"`
        is the carry-forward (between-wave relabel) shape. The kickoff hook
        must NOT fire on these commands — they were generating a 36-event
        annunaki noise burst in P3W11 (all `skip_no_scope`)."""
        self.assertIsNone(
            hook.parse_label_apply_command(
                "gh issue edit 262 --repo noorinalabs/noorinalabs-main "
                '--add-label "p3-wave-11" --remove-label "p3-wave-10"'
            )
        )

    def test_between_wave_relabel_flag_order_swapped_returns_none(self):
        """Same as above but `--remove-label` first → still skipped."""
        self.assertIsNone(
            hook.parse_label_apply_command(
                "gh issue edit 262 --repo noorinalabs/noorinalabs-main "
                '--remove-label "p3-wave-10" --add-label "p3-wave-11"'
            )
        )

    def test_between_wave_relabel_equals_form_returns_none(self):
        """Equals-form flags on a relabel also skip."""
        self.assertIsNone(
            hook.parse_label_apply_command(
                "gh issue edit 262 --repo=noorinalabs/noorinalabs-main "
                "--add-label=p3-wave-11 --remove-label=p3-wave-10"
            )
        )

    def test_add_with_non_wave_remove_still_matches(self):
        """`--add-label "p3-wave-11" --remove-label "tech-debt"` should still
        fire the hook — removing a non-wave label doesn't make this a
        between-wave relabel. The `parse_wave_label_change` helper only
        populates `remove_label` for canonical wave labels, so a non-wave
        remove leaves `remove_label=None` and the filter doesn't trigger."""
        self.assertEqual(
            hook.parse_label_apply_command(
                "gh issue edit 100 --repo noorinalabs/noorinalabs-main "
                '--add-label "p3-wave-11" --remove-label "tech-debt"'
            ),
            ("noorinalabs-main", "100", "p3-wave-11"),
        )

    def test_initial_add_without_remove_still_matches(self):
        """Regression guard: the common initial-kickoff shape — bare
        `--add-label "p3-wave-11"` with no `--remove-label` — must still
        return the tuple so the hook proceeds to render + post the kickoff
        comment. This pins acceptance criterion #2 from issue #467."""
        self.assertEqual(
            hook.parse_label_apply_command(
                'gh issue edit 200 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'
            ),
            ("noorinalabs-main", "200", "p3-wave-11"),
        )

    def test_no_repo_returns_none_repo_field(self):
        """#650: a label-apply run from inside the repo omits --repo; the pure
        parser returns repo=None (the caller resolves it from cwd)."""
        self.assertEqual(
            hook.parse_label_apply_command('gh issue edit 601 --add-label "p4-wave-7"'),
            (None, "601", "p4-wave-7"),
        )


class FindAssignmentRowTests(unittest.TestCase):
    """Direct coverage of tier-array row lookup with both shapes."""

    def test_explicit_issue_id_match(self):
        status = {
            "wave_9_scope": {
                "tier_1_x": [
                    {"id": "noorinalabs-main#123", "implementer": "A"},
                    {"id": "noorinalabs-deploy#9", "implementer": "B"},
                ]
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-main", "123", 9)
        self.assertEqual(row["implementer"], "A")

    def test_repo_backlog_match_when_no_explicit_id(self):
        """W6+W7 Tier-1 backlog shape: row has `repo`, no `id`."""
        status = {
            "wave_9_scope": {
                "tier_1_backlog": [
                    {"repo": "noorinalabs-deploy", "implementer": "Santiago Ferreira"}
                ]
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-deploy", "555", 9)
        self.assertEqual(row["implementer"], "Santiago Ferreira")

    def test_explicit_id_wins_over_repo_match(self):
        """If both shapes are present, the explicit-id row wins."""
        status = {
            "wave_9_scope": {
                "tier_1_backlog": [{"repo": "noorinalabs-main", "implementer": "BACKLOG"}],
                "tier_2_explicit": [{"id": "noorinalabs-main#42", "implementer": "EXPLICIT"}],
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-main", "42", 9)
        self.assertEqual(row["implementer"], "EXPLICIT")

    def test_no_match_returns_none(self):
        status = {"wave_9_scope": {"tier_1": [{"id": "other#999", "implementer": "X"}]}}
        self.assertIsNone(hook.find_assignment_row(status, "noorinalabs-main", "1", 9))

    def test_empty_scope_returns_none(self):
        self.assertIsNone(hook.find_assignment_row({}, "noorinalabs-main", "1", 9))

    def test_non_tier_keys_ignored(self):
        """Keys not starting with `tier_` (theme, declared_total, etc.) are skipped."""
        status = {
            "wave_9_scope": {
                "theme": "tech-debt",
                "tier_1": [{"id": "noorinalabs-main#1", "implementer": "Y"}],
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-main", "1", 9)
        self.assertEqual(row["implementer"], "Y")

    def test_dict_row_short_ref_match(self):
        """#586: dict row keyed by `ref` (short form) matches even without `id`."""
        status = {
            "wave_9_scope": {
                "tier_1_x": [
                    {"ref": "main#322", "implementer": "Wanjiku Mwangi"},
                ]
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-main", "322", 9)
        self.assertEqual(row["implementer"], "Wanjiku Mwangi")

    def test_dict_row_full_id_preferred_when_both_present(self):
        """A dict row with both `id` (full) and `ref` (short) is matched on either."""
        status = {
            "wave_9_scope": {
                "tier_1_x": [
                    {"id": "noorinalabs-deploy#393", "ref": "deploy#393", "implementer": "Lucas"},
                ]
            }
        }
        # Full-name caller resolves via id; the synthesized short-ref also resolves.
        row = hook.find_assignment_row(status, "noorinalabs-deploy", "393", 9)
        self.assertEqual(row["implementer"], "Lucas")

    def test_legacy_plain_string_short_ref_fallback(self):
        """#586: bare short-ref string entries (the pre-conversion /wave-scope
        shape) synthesize a placeholder row instead of silently skipping."""
        status = {
            "wave_14_scope": {
                "tier_1_end_state_rollout": ["main#322", "main#329"],
                "tier_4_remainder": ["main#560"],
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-main", "560", 14)
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], "noorinalabs-main#560")
        self.assertEqual(row["ref"], "main#560")
        # No implementer/reviewer in the synthesized row → render shows placeholders.
        self.assertNotIn("implementer", row)

    def test_legacy_plain_string_no_match_returns_none(self):
        """A plain-string tier with no matching short-ref still returns None."""
        status = {"wave_14_scope": {"tier_1": ["main#322", "deploy#393"]}}
        self.assertIsNone(hook.find_assignment_row(status, "noorinalabs-main", "999", 14))

    def test_dict_row_wins_over_plain_string(self):
        """When both a dict row and a plain string could match, the dict (with
        real implementer data) is returned, not the placeholder synthesis."""
        status = {
            "wave_14_scope": {
                "tier_1_strings": ["main#322"],
                "tier_2_dicts": [{"id": "noorinalabs-main#322", "implementer": "REAL"}],
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-main", "322", 14)
        self.assertEqual(row["implementer"], "REAL")

    def test_synthesized_row_renders_with_unassigned_placeholders(self):
        """End-to-end #586: a plain-string match flows through render with
        `(unassigned)` slots rather than producing a silent skip."""
        status = {"wave_14_scope": {"tier_1": ["main#322"]}}
        row = hook.find_assignment_row(status, "noorinalabs-main", "322", 14)
        body = hook.render_kickoff_comment(row, wave_num=14, phase_num=3, repo="noorinalabs-main")
        self.assertIn("Requestee: (unassigned)", body)
        self.assertIn("- Peer reviewer: (unassigned)", body)
        self.assertIn("- Secondary reviewer: (unassigned)", body)


class RenderKickoffCommentTests(unittest.TestCase):
    """Direct coverage of comment body rendering."""

    def test_canonical_render(self):
        row = {
            "implementer": "Aino Virtanen",
            "reviewer": "Nadia Khoury",
            "reviewer_2": "Santiago Ferreira",
            "priority": "tech-debt",
        }
        body = hook.render_kickoff_comment(row, wave_num=9, phase_num=3, repo="noorinalabs-main")
        self.assertIn("Requestor: Fatima Okonkwo", body)
        self.assertIn("Requestee: Aino Virtanen", body)
        self.assertIn("RequestOrReplied: Request", body)
        self.assertIn("**Wave 9 Kickoff — Phase 3**", body)
        self.assertIn("- Peer reviewer: Nadia Khoury", body)
        self.assertIn("- Secondary reviewer: Santiago Ferreira", body)
        self.assertIn("- Branch from: `deployments/phase-3/wave-9`", body)
        self.assertIn("- Priority: tech-debt", body)

    def test_missing_optional_fields_show_unassigned(self):
        """Missing reviewer/reviewer_2 render as `(unassigned)`, not blank."""
        row = {"implementer": "Aino Virtanen"}
        body = hook.render_kickoff_comment(row, wave_num=9, phase_num=3, repo="noorinalabs-main")
        self.assertIn("- Peer reviewer: (unassigned)", body)
        self.assertIn("- Secondary reviewer: (unassigned)", body)
        self.assertIn("- Priority: feature", body)  # default priority

    def test_implementer_missing_shows_unassigned(self):
        body = hook.render_kickoff_comment({}, wave_num=9, phase_num=3, repo="noorinalabs-main")
        self.assertIn("Requestee: (unassigned)", body)


class KickoffAlreadyPostedTests(unittest.TestCase):
    """Idempotency check across various comment shapes."""

    def test_returns_true_on_charter_heading(self):
        def fetch(r, n):
            return [{"body": "**Wave 9 Kickoff — Phase 3**\n\nbody"}]

        self.assertTrue(hook.kickoff_already_posted("x", "1", fetch_comments=fetch))

    def test_returns_true_on_hyphen_form(self):
        """Tolerate a hyphen-surrounded form in case the em-dash got dropped."""

        def fetch(r, n):
            return [{"body": "**Wave 9 Kickoff - Phase 3**"}]

        self.assertTrue(hook.kickoff_already_posted("x", "1", fetch_comments=fetch))

    def test_returns_false_on_no_kickoff_comment(self):
        def fetch(r, n):
            return [{"body": "Some other comment."}]

        self.assertFalse(hook.kickoff_already_posted("x", "1", fetch_comments=fetch))

    def test_returns_false_on_no_comments(self):
        def fetch(r, n):
            return []

        self.assertFalse(hook.kickoff_already_posted("x", "1", fetch_comments=fetch))

    def test_returns_false_on_fetch_failure(self):
        """fetch returning None (gh CLI failed) → don't suppress; let the
        downstream post attempt and annunaki-log on real failure."""

        def fetch(r, n):
            return None

        self.assertFalse(hook.kickoff_already_posted("x", "1", fetch_comments=fetch))

    def test_wave_specific_same_wave_still_idempotent(self):
        """#547: with wave_num=13, a Wave 13 comment still counts as posted."""

        def fetch(r, n):
            return [{"body": "**Wave 13 Kickoff — Phase 3**\n\nbody"}]

        self.assertTrue(hook.kickoff_already_posted("x", "1", wave_num=13, fetch_comments=fetch))

    def test_wave_specific_prior_wave_not_counted(self):
        """#547 core fix: with wave_num=13, a stale Wave 12 carry-forward
        kickoff comment does NOT count as the Wave 13 kickoff → not posted
        yet, so the hook will post a fresh one."""

        def fetch(r, n):
            return [{"body": "**Wave 12 Kickoff — Phase 3**\n\nprior-wave body"}]

        self.assertFalse(hook.kickoff_already_posted("x", "1", wave_num=13, fetch_comments=fetch))

    def test_wave_specific_multi_digit_wave_not_substring_matched(self):
        """#547 edge: wave_num=2 must not match a 'Wave 12 Kickoff' comment
        (the literal-digit interpolation is `\\bWave 2 ` via \\s, but the
        \\s+ boundary + the 'Kickoff' suffix prevent '12' from satisfying
        'Wave 2 Kickoff'). Guards against a naive substring regex."""

        def fetch(r, n):
            return [{"body": "**Wave 12 Kickoff — Phase 3**"}]

        self.assertFalse(hook.kickoff_already_posted("x", "1", wave_num=2, fetch_comments=fetch))

    def test_wave_none_falls_back_to_wave_agnostic(self):
        """#547: wave_num=None preserves legacy any-wave semantics — any
        kickoff heading counts."""

        def fetch(r, n):
            return [{"body": "**Wave 7 Kickoff — Phase 2**"}]

        self.assertTrue(hook.kickoff_already_posted("x", "1", wave_num=None, fetch_comments=fetch))


class NonBashToolTests(unittest.TestCase):
    """tool_name != Bash → early return None."""

    def test_edit_tool_not_matched(self):
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"command": 'gh issue edit 1 --repo r --add-label "p3-wave-9"'},
            }
        )
        self.assertIsNone(result)

    def test_empty_command_not_matched(self):
        result = hook.check({"tool_name": "Bash", "tool_input": {"command": ""}})
        self.assertIsNone(result)


class AmbientRepoResolutionTests(unittest.TestCase):
    """#650: a label-apply run from inside the repo omits --repo; the kickoff
    hook resolves the ambient repo from the invocation cwd before rendering
    and posting the kickoff comment."""

    _ORIGIN = "git@github.com:noorinalabs/noorinalabs-main.git\n"

    def _status(self):
        return {
            "wave_7_scope": {
                "tier_1_close_out": [
                    {
                        "id": "noorinalabs-main#601",
                        "implementer": "Aino Virtanen",
                        "reviewer": "Weronika Zielinska",
                        "reviewer_2": "Nino Kavtaradze",
                    }
                ]
            }
        }

    def test_no_repo_resolves_and_posts(self):
        captured = {}

        def fake_post(repo, num, body_path):
            captured["repo"] = repo
            captured["num"] = num
            return True

        with tempfile.TemporaryDirectory() as td:

            def fake_writer(body, repo, num):
                path = Path(td) / f"body-{repo}-{num}.md"
                path.write_text(body, encoding="utf-8")
                return path

            result = hook.check(
                _bash('gh issue edit 601 --add-label "p4-wave-7"'),
                status_loader=self._status,
                comment_fetcher=lambda repo, num: [],
                comment_poster=fake_post,
                body_writer=fake_writer,
                git_runner=lambda _cwd: self._ORIGIN,
            )
        self.assertEqual(result["action"], "post")
        self.assertEqual(result["repo"], "noorinalabs-main")
        self.assertEqual(captured["repo"], "noorinalabs-main")

    def test_no_repo_unresolvable_skips_no_repo_context(self):
        result = hook.check(
            _bash('gh issue edit 601 --add-label "p4-wave-7"'),
            status_loader=self._status,
            git_runner=lambda _cwd: None,
        )
        self.assertEqual(result["action"], "skip_no_repo_context")
        self.assertEqual(result["issue"], "601")

    def test_explicit_repo_does_not_invoke_git_runner(self):
        calls = [0]

        def runner(_cwd):
            calls[0] += 1
            return self._ORIGIN

        with tempfile.TemporaryDirectory() as td:

            def fake_writer(body, repo, num):
                path = Path(td) / f"body-{repo}-{num}.md"
                path.write_text(body, encoding="utf-8")
                return path

            result = hook.check(
                _bash(
                    'gh issue edit 601 --repo noorinalabs/noorinalabs-main --add-label "p4-wave-7"'
                ),
                status_loader=self._status,
                comment_fetcher=lambda repo, num: [],
                comment_poster=lambda repo, num, path: True,
                body_writer=fake_writer,
                git_runner=runner,
            )
        self.assertEqual(result["action"], "post")
        self.assertEqual(calls[0], 0, "explicit --repo must not trigger ambient resolution")


class PhaseAgnosticLabelForm(unittest.TestCase):
    """#810: the kickoff hook fires on the new `wave-{X}` label form, recovering
    the (derived-display) phase from cross-repo-status.json, and skips the
    `wave-x` placeholder (not a per-issue kickoff)."""

    def _status(self):
        return {
            "current_phase": 4,
            "phase": "phase-4",
            "wave_7_scope": {
                "tier_1_close_out": [
                    {
                        "id": "noorinalabs-main#601",
                        "implementer": "Aino Virtanen",
                        "reviewer": "Weronika Zielinska",
                        "reviewer_2": "Nino Kavtaradze",
                    }
                ]
            },
        }

    def test_global_form_posts_with_phase_from_status(self):
        captured = {}

        def fake_post(repo, num, body_path):
            captured["body"] = Path(body_path).read_text(encoding="utf-8")
            return True

        with tempfile.TemporaryDirectory() as td:

            def fake_writer(body, repo, num):
                path = Path(td) / f"body-{repo}-{num}.md"
                path.write_text(body, encoding="utf-8")
                return path

            result = hook.check(
                _bash('gh issue edit 601 --repo noorinalabs/noorinalabs-main --add-label "wave-7"'),
                status_loader=self._status,
                comment_fetcher=lambda repo, num: [],
                comment_poster=fake_post,
                body_writer=fake_writer,
            )
        self.assertEqual(result["action"], "post")
        # Phase 4 was recovered from status (the new label carries no phase).
        self.assertIn("Phase 4", captured["body"])
        self.assertIn("Wave 7", captured["body"])

    def test_placeholder_form_is_not_a_kickoff(self):
        """`wave-x` carries no wave id → not a per-issue kickoff → None."""
        result = hook.check(
            _bash('gh issue edit 601 --repo noorinalabs/noorinalabs-main --add-label "wave-x"'),
            status_loader=self._status,
        )
        self.assertIsNone(result)

    def test_global_form_no_phase_in_status_skips(self):
        """New-form label but status has no resolvable phase → skip_no_phase."""

        def _status_no_phase():
            return {
                "wave_7_scope": {
                    "tier_1_close_out": [
                        {"id": "noorinalabs-main#601", "implementer": "Aino Virtanen"}
                    ]
                }
            }

        result = hook.check(
            _bash('gh issue edit 601 --repo noorinalabs/noorinalabs-main --add-label "wave-7"'),
            status_loader=_status_no_phase,
        )
        self.assertEqual(result["action"], "skip_no_phase")


if __name__ == "__main__":
    unittest.main()
