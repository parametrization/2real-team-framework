#!/usr/bin/env python3
"""Tests for `auto_add_issue_to_board` PostToolUse hook (Hook 13).

Coverage focuses on the issue #450 enhancement (set project 2 Wave field
when `gh issue create --label "p{N}-wave-{M}"` lands) without regressing
the original board-add behavior.

Run from the repo root:
    ENVIRONMENT=test python3 -m pytest \\
        .claude/hooks/tests/test_auto_add_issue_to_board.py -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import auto_add_issue_to_board as hook  # noqa: E402
import post_label_change_wave_field_sync as field_sync_hook  # noqa: E402


def _bash_create(command: str, stdout: str = "") -> dict:
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"stdout": stdout, "stderr": "", "exit_code": 0},
    }


def _scopes_with_project() -> str:
    return "  - Token scopes: 'gist', 'project', 'read:org', 'repo', 'workflow'\n"


def _scopes_without_project() -> str:
    return "  - Token scopes: 'gist', 'read:org', 'repo', 'workflow'\n"


def _ids_blob() -> dict:
    return {
        "project_id": "PROJ_NODE_ID",
        "field_id": "WAVE_FIELD_ID",
        "option_ids": {"P3W10": "OPT_P3W10", "P3W11": "OPT_P3W11"},
    }


def _item_lookup_response(repo: str, num: int) -> str:
    return json.dumps(
        {
            "data": {
                "repository": {
                    "issue": {
                        "projectItems": {
                            "nodes": [
                                {
                                    "id": "ITEM_ID_FROM_CREATE",
                                    "project": {"number": 2},
                                }
                            ]
                        }
                    }
                }
            }
        }
    )


def _item_lookup_empty_response(repo=None, num=None) -> str:
    return json.dumps({"data": {"repository": {"issue": {"projectItems": {"nodes": []}}}}})


def _mutation_success_response(_variables=None) -> str:
    return json.dumps(
        {
            "data": {
                "updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "ITEM_ID_FROM_CREATE"}}
            }
        }
    )


class FakeGraphQLRouter:
    def __init__(self, introspect=None, item_lookup=None, mutation=None):
        self.introspect = introspect
        self.item_lookup = item_lookup
        self.mutation = mutation
        self.calls = {"introspect": 0, "item_lookup": 0, "mutation": 0}

    def __call__(self, query: str, variables: dict) -> str:
        if "projectV2(number:" in query and "field(name:" in query:
            self.calls["introspect"] += 1
            r = self.introspect() if callable(self.introspect) else self.introspect
            return r or ""
        if "repository(owner:" in query and "projectItems" in query:
            self.calls["item_lookup"] += 1
            r = (
                self.item_lookup(variables.get("repo"), variables.get("num"))
                if callable(self.item_lookup)
                else self.item_lookup
            )
            return r or ""
        if "updateProjectV2ItemFieldValue" in query:
            self.calls["mutation"] += 1
            r = self.mutation(variables) if callable(self.mutation) else self.mutation
            return r or ""
        return ""


def _wipe_field_sync_cache():
    """Clear the shared Hook 21 cache + auth sentinel between tests."""
    for p in (field_sync_hook.CACHE_PATH, field_sync_hook.AUTH_WARN_SENTINEL):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


class NonMatchingInputTests(unittest.TestCase):
    """Hook should return None on inputs that don't fit `gh issue create`."""

    def test_non_bash_tool_returns_none(self):
        result = hook.check({"tool_name": "Edit", "tool_input": {"file_path": "/tmp/x"}})
        self.assertIsNone(result)

    def test_non_create_command_returns_none(self):
        result = hook.check(_bash_create("gh issue list", stdout="some output"))
        self.assertIsNone(result)

    def test_empty_stdout_returns_none(self):
        result = hook.check(_bash_create("gh issue create --title foo", stdout=""))
        self.assertIsNone(result)

    def test_no_url_in_stdout_returns_none(self):
        """Stdout that doesn't contain a parseable issue URL → None."""
        result = hook.check(
            _bash_create("gh issue create --title foo", stdout="something went wrong")
        )
        self.assertIsNone(result)


class CreateWithoutWaveLabelTests(unittest.TestCase):
    """`gh issue create` without a wave label: only board-add fires, no
    Wave-field sync attempt. Verifies the additive nature of #450."""

    def test_create_without_wave_label_adds_to_board_only(self):
        cmd = 'gh issue create --repo noorinalabs/noorinalabs-main --title "bug" --body "x"'
        stdout = "https://github.com/noorinalabs/noorinalabs-main/issues/123\n"
        with patch.object(hook.subprocess, "run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            result = hook.check(_bash_create(cmd, stdout=stdout))
        self.assertEqual(result["action"], "added")
        self.assertEqual(
            result["issue_url"], "https://github.com/noorinalabs/noorinalabs-main/issues/123"
        )
        self.assertNotIn("wave_field_sync", result)


class CreateWithWaveLabelTests(unittest.TestCase):
    """#450 — Wave field SHOULD be set when `--label "p{N}-wave-{M}"` is on
    the create command and the issue lands on the board."""

    def setUp(self):
        _wipe_field_sync_cache()
        field_sync_hook.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        field_sync_hook._write_cache(_ids_blob())

    def tearDown(self):
        _wipe_field_sync_cache()

    def test_create_with_wave_label_sets_field(self):
        cmd = (
            "gh issue create --repo noorinalabs/noorinalabs-main "
            '--title "bug" --body "x" --label "p3-wave-11"'
        )
        stdout = "https://github.com/noorinalabs/noorinalabs-main/issues/456\n"
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        with patch.object(hook.subprocess, "run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            result = hook.check(
                _bash_create(cmd, stdout=stdout),
                auth_status_runner=_scopes_with_project,
                graphql_runner=router,
            )
        self.assertEqual(result["action"], "added")
        sync = result["wave_field_sync"]
        self.assertEqual(sync["action"], "set")
        self.assertEqual(sync["repo"], "noorinalabs-main")
        self.assertEqual(sync["issue"], "456")
        self.assertEqual(sync["option_name"], "P3W11")
        self.assertEqual(router.calls["mutation"], 1)

    def test_create_with_wave_label_equals_form_sets_field(self):
        """`--label=p3-wave-11` (equals form) must also be parsed."""
        cmd = (
            "gh issue create --repo=noorinalabs/noorinalabs-main "
            "--title bug --body x --label=p3-wave-11"
        )
        stdout = "https://github.com/noorinalabs/noorinalabs-main/issues/789\n"
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        with patch.object(hook.subprocess, "run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            result = hook.check(
                _bash_create(cmd, stdout=stdout),
                auth_status_runner=_scopes_with_project,
                graphql_runner=router,
            )
        sync = result["wave_field_sync"]
        self.assertEqual(sync["action"], "set")
        self.assertEqual(sync["option_name"], "P3W11")

    def test_create_with_non_wave_label_skips_sync(self):
        """`--label "bug"` is not a wave label → no sync attempt, but board-add
        still fires."""
        cmd = "gh issue create --repo noorinalabs/noorinalabs-main --title x --body y --label bug"
        stdout = "https://github.com/noorinalabs/noorinalabs-main/issues/100\n"
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        with patch.object(hook.subprocess, "run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            result = hook.check(
                _bash_create(cmd, stdout=stdout),
                auth_status_runner=_scopes_with_project,
                graphql_runner=router,
            )
        self.assertEqual(result["action"], "added")
        self.assertNotIn("wave_field_sync", result)
        self.assertEqual(router.calls["mutation"], 0)

    def test_create_missing_auth_scope_skips_sync_gracefully(self):
        """When gh lacks `project` scope, the sync is skipped but the
        board-add result is still returned with the skip recorded."""
        cmd = (
            "gh issue create --repo noorinalabs/noorinalabs-main "
            '--title x --body y --label "p3-wave-11"'
        )
        stdout = "https://github.com/noorinalabs/noorinalabs-main/issues/200\n"
        with patch.object(hook.subprocess, "run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            result = hook.check(
                _bash_create(cmd, stdout=stdout),
                auth_status_runner=_scopes_without_project,
            )
        self.assertEqual(result["action"], "added")
        self.assertEqual(result["wave_field_sync"]["action"], "skip_no_auth_scope")

    def test_create_with_item_not_visible_logs_and_skips(self):
        """When item-add lands but the item isn't yet visible via projectItems
        (eventual consistency), the hook retries a few times then logs+skips."""
        cmd = (
            "gh issue create --repo noorinalabs/noorinalabs-main "
            '--title x --body y --label "p3-wave-11"'
        )
        stdout = "https://github.com/noorinalabs/noorinalabs-main/issues/300\n"
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_empty_response,
            mutation=_mutation_success_response,
        )
        with patch.object(hook.subprocess, "run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            result = hook.check(
                _bash_create(cmd, stdout=stdout),
                auth_status_runner=_scopes_with_project,
                graphql_runner=router,
            )
        sync = result["wave_field_sync"]
        self.assertEqual(sync["action"], "skip_no_item")
        self.assertEqual(router.calls["item_lookup"], 3, "Should retry 3 times before giving up")
        self.assertEqual(router.calls["mutation"], 0)

    def test_create_with_missing_wave_option_skips(self):
        """When the cached option_ids dict has no entry for the requested
        wave (e.g., P3W12 not yet added to project settings), skip."""
        cmd = (
            "gh issue create --repo noorinalabs/noorinalabs-main "
            '--title x --body y --label "p3-wave-12"'  # P3W12 not in _ids_blob()
        )
        stdout = "https://github.com/noorinalabs/noorinalabs-main/issues/400\n"
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        with patch.object(hook.subprocess, "run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            result = hook.check(
                _bash_create(cmd, stdout=stdout),
                auth_status_runner=_scopes_with_project,
                graphql_runner=router,
            )
        sync = result["wave_field_sync"]
        self.assertEqual(sync["action"], "skip_no_option")
        self.assertEqual(sync["option_name"], "P3W12")


class CreateWithoutRepoFlagWaveLabelTests(unittest.TestCase):
    """#659 — in-repo `gh issue create` WITHOUT `--repo` (ambient resolution)
    must still sync the Wave field; the concrete repo is recovered from the
    created-issue URL. Before the fix the parser dropped the create (gated on
    `--repo`) and the board Wave field was left unset — the create-surface
    sibling of the EDIT-path #650 silent-drop.
    """

    def setUp(self):
        _wipe_field_sync_cache()
        field_sync_hook.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        field_sync_hook._write_cache(_ids_blob())

    def tearDown(self):
        _wipe_field_sync_cache()

    def test_in_repo_create_without_repo_flag_resolves_repo_from_url(self):
        cmd = 'gh issue create --title "bug" --body "x" --label "p3-wave-11"'
        stdout = "https://github.com/noorinalabs/noorinalabs-main/issues/659\n"
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        with patch.object(hook.subprocess, "run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            result = hook.check(
                _bash_create(cmd, stdout=stdout),
                auth_status_runner=_scopes_with_project,
                graphql_runner=router,
            )
        self.assertEqual(result["action"], "added")
        sync = result["wave_field_sync"]
        self.assertEqual(sync["action"], "set")
        self.assertEqual(sync["repo"], "noorinalabs-main")  # recovered from the URL
        self.assertEqual(sync["issue"], "659")
        self.assertEqual(sync["option_name"], "P3W11")
        self.assertEqual(router.calls["mutation"], 1)

    def test_equals_form_without_repo_also_resolves(self):
        """`--label=p3-wave-11` with no `--repo` (equals form) also syncs."""
        cmd = "gh issue create --title bug --body x --label=p3-wave-11"
        stdout = "https://github.com/noorinalabs/noorinalabs-isnad-graph/issues/77\n"
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        with patch.object(hook.subprocess, "run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            result = hook.check(
                _bash_create(cmd, stdout=stdout),
                auth_status_runner=_scopes_with_project,
                graphql_runner=router,
            )
        sync = result["wave_field_sync"]
        self.assertEqual(sync["action"], "set")
        self.assertEqual(sync["repo"], "noorinalabs-isnad-graph")


class ParseWaveLabelCreateTests(unittest.TestCase):
    """#659 parser-level coverage for the `--repo`-Optional create path."""

    def test_create_without_repo_returns_change_with_repo_none(self):
        from _wave_label_parse import parse_wave_label_create

        creates = parse_wave_label_create('gh issue create --title "bug" --label "p5-wave-3"')
        self.assertEqual(len(creates), 1)
        self.assertIsNone(creates[0].repo)
        self.assertEqual(creates[0].add_label, "p5-wave-3")

    def test_create_with_repo_still_captures_short_name(self):
        from _wave_label_parse import parse_wave_label_create

        creates = parse_wave_label_create(
            "gh issue create --repo noorinalabs/noorinalabs-main --label p5-wave-3"
        )
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0].repo, "noorinalabs-main")

    def test_create_without_wave_label_returns_empty(self):
        from _wave_label_parse import parse_wave_label_create

        self.assertEqual(parse_wave_label_create("gh issue create --label bug"), [])


class ExtractIssueUrlTests(unittest.TestCase):
    """Pure-function coverage for the URL+number extractor."""

    def test_canonical_url(self):
        result = hook._extract_issue_url_and_number(
            "https://github.com/noorinalabs/noorinalabs-main/issues/42\n"
        )
        self.assertEqual(
            result, ("https://github.com/noorinalabs/noorinalabs-main/issues/42", "42")
        )

    def test_url_with_surrounding_text(self):
        result = hook._extract_issue_url_and_number(
            "Issue created!\n"
            "Visit: https://github.com/noorinalabs/noorinalabs-deploy/issues/9001\n"
            "Done.\n"
        )
        self.assertEqual(
            result, ("https://github.com/noorinalabs/noorinalabs-deploy/issues/9001", "9001")
        )

    def test_no_url_returns_none(self):
        self.assertIsNone(hook._extract_issue_url_and_number("nothing here"))

    def test_non_noorinalabs_url_returns_none(self):
        """URLs from other orgs must not match — hook is noorinalabs-scoped."""
        self.assertIsNone(
            hook._extract_issue_url_and_number("https://github.com/some-other-org/repo/issues/1")
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
