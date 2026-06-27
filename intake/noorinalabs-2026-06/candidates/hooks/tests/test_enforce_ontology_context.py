#!/usr/bin/env python3
"""Tests for enforce_ontology_context — covers #466 coordinator-class exemption.

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_enforce_ontology_context.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import enforce_ontology_context as hook  # noqa: E402


def _spawn(prompt: str, isolation: str = "worktree") -> dict:
    return {
        "tool_name": "Agent",
        "tool_input": {"isolation": isolation, "prompt": prompt},
    }


class NonAgentCallAllowed(unittest.TestCase):
    def test_bash_tool_pass_through(self):
        self.assertIsNone(hook.check({"tool_name": "Bash", "tool_input": {"command": "ls"}}))

    def test_edit_tool_pass_through(self):
        self.assertIsNone(hook.check({"tool_name": "Edit", "tool_input": {}}))


class NonWorktreeIsolationAllowed(unittest.TestCase):
    def test_no_isolation_allowed(self):
        self.assertIsNone(hook.check(_spawn("Random prompt without markers", isolation="")))

    def test_other_isolation_value_allowed(self):
        self.assertIsNone(hook.check(_spawn("Random prompt", isolation="container")))


class WorktreeImplementerWithoutContextBlocked(unittest.TestCase):
    def test_engineer_blocked(self):
        prompt = "You are **Mateo Salazar**, Engineer for noorinalabs-user-service. Implement #123."
        result = hook.check(_spawn(prompt))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_tech_lead_blocked(self):
        prompt = (
            "You are **Anya Kowalczyk**, Tech Lead for noorinalabs-isnad-graph. Implement #500."
        )
        result = hook.check(_spawn(prompt))
        self.assertIsNotNone(result)

    def test_security_engineer_blocked(self):
        prompt = "You are **Idris Yusuf**, Security Engineer. Review the auth code."
        result = hook.check(_spawn(prompt))
        self.assertIsNotNone(result)


class WorktreeImplementerWithContextAllowed(unittest.TestCase):
    def test_ontology_context_heading_allowed(self):
        prompt = (
            "## Ontology Context\nServices: user-service\n\n"
            "You are **Mateo**, Engineer. Implement #123."
        )
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_status_marker_allowed(self):
        prompt = "You are Mateo. Ontology Status: ontology is current. Implement #123."
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_yaml_path_marker_allowed(self):
        prompt = "You are Mateo. See ontology/services.yaml for context. Implement #123."
        self.assertIsNone(hook.check(_spawn(prompt)))


class CoordinatorClassExempt(unittest.TestCase):
    """Manager / Program Director / TPM / Release Coordinator spawn briefs are
    exempt from ontology-context enforcement even with worktree isolation.

    Reproduces the 8-block burst captured 2026-05-17 03:54Z (#466)."""

    def test_manager_for_deploy_exempt(self):
        prompt = "You are **Bereket Tadesse**, Manager for noorinalabs-deploy. Roster card: ..."
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_manager_for_isnad_graph_exempt(self):
        prompt = (
            "You are **Nadia Boukhari**, Manager for noorinalabs-isnad-graph "
            "(NOT Nadia Khoury the parent Program Director — different person)."
        )
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_manager_for_ingest_platform_exempt(self):
        prompt = (
            "You are **Adaeze Okonkwo**, Manager for noorinalabs-isnad-ingest-platform. "
            "Roster card: ..."
        )
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_program_director_exempt(self):
        prompt = "You are **Nadia Khoury**, Program Director for noorinalabs. Coordinate the wave."
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_tpm_exempt(self):
        prompt = "You are **Wanjiku Mwangi**, TPM for noorinalabs. Track timelines."
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_technical_program_manager_full_title_exempt(self):
        prompt = (
            "You are **Wanjiku Mwangi**, Technical Program Manager for noorinalabs. "
            "Track timelines."
        )
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_release_coordinator_exempt(self):
        prompt = (
            "You are **Santiago Ferreira**, Release Coordinator for noorinalabs. Sequence rollouts."
        )
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_manager_without_repo_suffix_exempt(self):
        prompt = "You are **Bereket Tadesse**, Manager. Coordinate the deploy wave."
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_manager_without_bold_markdown_exempt(self):
        prompt = "You are Bereket Tadesse, Manager for noorinalabs-deploy. Coordinate the wave."
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_project_lead_exempt_marcia(self):
        # Marcia Vasquez-Paredes (landing-page) — composer flattens
        # "Project Lead / Manager" roster title to ", Project Lead".
        # Was 1 of the 8 captured blocks (#466) that the initial regex missed.
        prompt = (
            "You are **Marcia Vasquez-Paredes**, Project Lead for noorinalabs-landing-page. "
            "Coordinate the wave."
        )
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_pipeline_manager_exempt_dilara(self):
        # Dilara (data-acquisition) — Senior VP coordinator with the
        # "Pipeline Manager" composer-output. Surfaced by Santiago's #469
        # roster-grep during PR #468 review.
        prompt = (
            "You are **Dilara Aydin**, Pipeline Manager for noorinalabs-data-acquisition. "
            "Coordinate the wave."
        )
        self.assertIsNone(hook.check(_spawn(prompt)))


class CoordinatorExemptHandlesPrependedHeader(unittest.TestCase):
    """Coordinator-class exemption must match when the spawn brief prepends
    content (header, task framing, role-card excerpt) before the canonical
    "You are X, Role" opener — `re.MULTILINE` enables `^` to match at line
    starts beyond char 0. Caught by Aino's review blocker #2 on PR #468."""

    def test_coordinator_after_markdown_header_exempt(self):
        prompt = (
            "# Wave-tail re-spawn brief\n\n"
            "You are **Bereket Tadesse**, Manager for noorinalabs-deploy. Coordinate the wave."
        )
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_coordinator_after_task_context_exempt(self):
        prompt = (
            "Task context: P3W11 wave-tail cleanup.\n"
            "\n"
            "You are **Adaeze Okonkwo**, Manager for noorinalabs-isnad-ingest-platform. "
            "Coordinate the wave."
        )
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_coordinator_after_role_card_excerpt_exempt(self):
        prompt = (
            "Roster card excerpt:\n"
            "  Role: Manager for noorinalabs-landing-page\n"
            "  Reports to: Nadia Khoury\n"
            "\n"
            "You are **Marcia Vasquez-Paredes**, Project Lead for noorinalabs-landing-page. "
            "Coordinate the wave."
        )
        self.assertIsNone(hook.check(_spawn(prompt)))


class IndentedCoordinatorOpenerNotExempt(unittest.TestCase):
    """The opener must sit at an EXACT line start to exempt. An indented
    `You are X, Manager` line — inside a 4-space code block, a YAML-indented
    example, or a blockquote — is NOT the coordinator's own opener; it's
    prompt-body content. The old `^\\s*` + re.MULTILINE matched these and
    falsely exempted implementer spawns. The `(?:\\A|\\n)You are` anchor
    blocks them (#471). The opener tested here belongs to an Engineer spawn
    with NO ontology context, so the correct outcome is a block."""

    def test_four_space_indented_opener_not_exempt(self):
        prompt = (
            "You are **Mateo Salazar**, Engineer. Implement #123. Example brief shape:\n"
            "    You are **Bereket Tadesse**, Manager for noorinalabs-deploy.\n"
        )
        result = hook.check(_spawn(prompt))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_yaml_indented_opener_not_exempt(self):
        prompt = (
            "You are **Mateo Salazar**, Engineer. Implement #123. YAML example:\n"
            "brief:\n"
            "  opener: You are **Bereket Tadesse**, Manager for noorinalabs-deploy\n"
        )
        result = hook.check(_spawn(prompt))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_blockquote_indented_opener_not_exempt(self):
        # Defensive: a blockquote-prefixed opener (`> You are ...`) already
        # wouldn't match a column-0 anchor; this pins that it stays blocked.
        prompt = (
            "You are **Mateo Salazar**, Engineer. Implement #123. Quoted brief:\n"
            "> You are **Bereket Tadesse**, Manager for noorinalabs-deploy\n"
        )
        result = hook.check(_spawn(prompt))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")


class CheckIsCrashSafeOnMalformedInput(unittest.TestCase):
    """PreToolUse hooks that raise get surfaced to the user as
    block-with-error, which is worse than silently allowing a malformed
    shape (the tool itself will reject it). `check()` must return None on
    any non-conforming input. Covers Aino's non-blocking concern on #468."""

    def test_none_prompt_does_not_crash(self):
        self.assertIsNone(hook.check({"tool_name": "Agent", "tool_input": {"prompt": None}}))

    def test_int_prompt_does_not_crash(self):
        self.assertIsNone(hook.check({"tool_name": "Agent", "tool_input": {"prompt": 42}}))

    def test_dict_prompt_does_not_crash(self):
        self.assertIsNone(hook.check({"tool_name": "Agent", "tool_input": {"prompt": {"x": 1}}}))

    def test_none_tool_input_does_not_crash(self):
        self.assertIsNone(hook.check({"tool_name": "Agent", "tool_input": None}))

    def test_list_tool_input_does_not_crash(self):
        self.assertIsNone(hook.check({"tool_name": "Agent", "tool_input": []}))

    def test_none_isolation_does_not_crash(self):
        self.assertIsNone(
            hook.check(
                {
                    "tool_name": "Agent",
                    "tool_input": {"isolation": None, "prompt": "You are X, Engineer."},
                }
            )
        )

    def test_missing_tool_input_does_not_crash(self):
        self.assertIsNone(hook.check({"tool_name": "Agent"}))


class CoordinatorExemptIsBoundaryStrict(unittest.TestCase):
    """The exemption matches the canonical opener shape and NOT incidental
    mentions of coordinator role names later in the prompt."""

    def test_engineer_mentioning_manager_in_body_still_blocked(self):
        prompt = (
            "You are **Mateo Salazar**, Engineer. Your Manager Bereket asked for #123. "
            "Implement it."
        )
        result = hook.check(_spawn(prompt))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_tech_lead_not_exempted_by_lead_substring(self):
        prompt = "You are **Anya Kowalczyk**, Tech Lead. Implement #500."
        result = hook.check(_spawn(prompt))
        self.assertIsNotNone(result)

    def test_engineering_manager_role_does_not_match_simple_manager(self):
        # "Engineering Manager" (a doer-manager title) won't match because
        # the regex requires the coordinator word immediately after `, `.
        prompt = "You are **Sam**, Engineering Manager. Implement #200."
        result = hook.check(_spawn(prompt))
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
