#!/usr/bin/env python3
"""Tests for `post_label_change_wave_field_sync` PostToolUse hook.

Nine semantic buckets covered (per `skills.md § Acceptance-Criteria-Bucketing-In-Reports`):

ACTIONABLE buckets
==================
1. **Regex match cases** — commands that SHOULD trigger the field-sync:
   - `--add-label "p3-wave-11"` → set.
   - `--remove-label "p3-wave-10"` → clear.
   - Multi-flag `--add-label "p3-wave-11" --remove-label "p3-wave-10"` → set
     (post-edit state wins).
2. **Kill-switch env var coverage**:
   - `NOORIN_DISABLE_LABEL_SYNC_HOOK=1` → killed.
   - `=0` → proceeds.
   - empty/unset → proceeds.

INFORMATIONAL buckets
=====================
3. **Regex no-match cases** — commands that should NOT trigger:
   - Non-wave label (`--add-label "bug"`).
   - Different subcommand (`gh issue create`).
   - PR not issue (`gh pr edit ... --add-label "p3-wave-11"`).
   - Suffixed label (`p3-wave-10-special`).
4. **Auth-scope pre-flight**:
   - `gh auth status` reports no `project` scope → skip_no_auth_scope.
   - Reports project scope → proceeds.
5. **ID-cache behavior**:
   - First fire introspects + writes cache (mode 0600).
   - Second fire within TTL reads cache (no introspection).
   - Stale cache (past TTL) re-introspects.
   - Field-not-found mutation error busts cache + retries once.
6. **GraphQL no-op cases**:
   - Issue not on project 2 → skip_no_item (graceful).
   - Missing Wave option (e.g. `P3W11` not in field options) → skip_no_option.

Run from the repo root:
    ENVIRONMENT=test python3 -m pytest \
        .claude/hooks/tests/test_post_label_change_wave_field_sync.py -v
"""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import post_label_change_wave_field_sync as hook  # noqa: E402


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


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


def _introspect_response() -> str:
    return json.dumps(
        {
            "data": {
                "organization": {
                    "projectV2": {
                        "id": "PROJ_NODE_ID",
                        "field": {
                            "id": "WAVE_FIELD_ID",
                            "options": [
                                {"id": "OPT_P3W10", "name": "P3W10"},
                                {"id": "OPT_P3W11", "name": "P3W11"},
                            ],
                        },
                    }
                }
            }
        }
    )


def _item_lookup_response(repo: str, num: int) -> str:
    return json.dumps(
        {
            "data": {
                "repository": {
                    "issue": {
                        "projectItems": {
                            "nodes": [
                                {
                                    "id": "ITEM_ID_123",
                                    "project": {"number": 2},
                                }
                            ]
                        }
                    }
                }
            }
        }
    )


def _item_lookup_empty_response() -> str:
    return json.dumps({"data": {"repository": {"issue": {"projectItems": {"nodes": []}}}}})


def _mutation_success_response(_variables=None) -> str:
    return json.dumps(
        {"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "ITEM_ID_123"}}}}
    )


def _mutation_field_not_found_response(_variables=None) -> str:
    return json.dumps(
        {
            "data": None,
            "errors": [{"message": "Field with id WAVE_FIELD_ID not found on project."}],
        }
    )


class FakeGraphQLRouter:
    """Stateful fake that routes GraphQL calls by query content.

    Each test composes a router by passing it a dict of responders:
    one for each query shape (introspect / item-lookup / mutation).
    Call counts are tracked for assertion.
    """

    def __init__(
        self,
        introspect=None,
        item_lookup=None,
        mutation=None,
    ):
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
        if "updateProjectV2ItemFieldValue" in query or "clearProjectV2ItemFieldValue" in query:
            self.calls["mutation"] += 1
            r = self.mutation(variables) if callable(self.mutation) else self.mutation
            return r or ""
        return ""


def _wipe_cache():
    """Remove the cache file + auth-warn marker between tests for isolation."""
    for p in (hook.CACHE_PATH, hook.AUTH_WARN_SENTINEL):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


class RegexMatchTests(unittest.TestCase):
    """Bucket 1 (ACTIONABLE) — commands that SHOULD trigger field-sync.

    Tests use the project ID cache shortcut (write the cache directly so
    we don't need to mock the introspect responder).
    """

    def setUp(self):
        _wipe_cache()
        hook.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        hook._write_cache(_ids_blob())

    def tearDown(self):
        _wipe_cache()

    def test_add_label_p3_wave_11(self):
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "set")
        self.assertEqual(result["option_name"], "P3W11")
        self.assertEqual(result["issue"], "123")
        self.assertEqual(router.calls["mutation"], 1)

    def test_remove_label_p3_wave_10(self):
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash(
                'gh issue edit 123 --repo noorinalabs/noorinalabs-main --remove-label "p3-wave-10"'
            ),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "cleared")
        self.assertEqual(result["issue"], "123")
        self.assertEqual(router.calls["mutation"], 1)

    def test_compound_add_and_remove_post_edit_state_wins(self):
        """`--remove "p3-wave-10" --add "p3-wave-11"` → post-edit state is the
        added value; we set Wave to P3W11 (not clear)."""
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash(
                "gh issue edit 123 --repo noorinalabs/noorinalabs-main "
                '--remove-label "p3-wave-10" --add-label "p3-wave-11"'
            ),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "set")
        self.assertEqual(result["option_name"], "P3W11")


class RegexNoMatchTests(unittest.TestCase):
    """Bucket 3 (INFORMATIONAL) — commands that should NOT trigger.

    For these, we do NOT mock the GraphQL runner — if the hook tries to
    call it, the test would fail (None default → no mutation).
    """

    def setUp(self):
        _wipe_cache()

    def tearDown(self):
        _wipe_cache()

    def test_non_wave_label(self):
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "bug"'),
        )
        self.assertIsNone(result)

    def test_gh_issue_create_not_match(self):
        result = hook.check(_bash("gh issue create --title 'foo' --body 'bar'"))
        self.assertIsNone(result)

    def test_gh_pr_edit_not_match(self):
        """PR edits don't drive the Wave field; only issue edits do."""
        result = hook.check(
            _bash('gh pr edit 42 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"')
        )
        self.assertIsNone(result)

    def test_suffixed_label_not_match(self):
        """`p3-wave-10-special` is not a canonical wave label."""
        result = hook.check(
            _bash(
                "gh issue edit 123 --repo noorinalabs/noorinalabs-main "
                '--add-label "p3-wave-10-special"'
            )
        )
        self.assertIsNone(result)

    def test_non_bash_tool_not_match(self):
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/tmp/x.py"},
            }
        )
        self.assertIsNone(result)

    def test_empty_command_not_match(self):
        result = hook.check(_bash(""))
        self.assertIsNone(result)


class KillSwitchTests(unittest.TestCase):
    """Bucket 2 (ACTIONABLE) — kill-switch env var coverage."""

    def setUp(self):
        _wipe_cache()
        # Ensure env is clean between tests
        os.environ.pop(hook.KILL_SWITCH_ENV, None)

    def tearDown(self):
        _wipe_cache()
        os.environ.pop(hook.KILL_SWITCH_ENV, None)

    def test_kill_switch_value_1_skips(self):
        os.environ[hook.KILL_SWITCH_ENV] = "1"
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
        )
        self.assertEqual(result["action"], "killed")

    def test_kill_switch_value_0_proceeds(self):
        """=0 does NOT skip (Unix-tradition truthy-only)."""
        os.environ[hook.KILL_SWITCH_ENV] = "0"
        hook._write_cache(_ids_blob())
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertNotEqual(result.get("action"), "killed")

    def test_kill_switch_empty_proceeds(self):
        os.environ[hook.KILL_SWITCH_ENV] = ""
        hook._write_cache(_ids_blob())
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertNotEqual(result.get("action"), "killed")

    def test_kill_switch_unset_proceeds(self):
        # Already popped in setUp; just verify behavior
        hook._write_cache(_ids_blob())
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertNotEqual(result.get("action"), "killed")


class AuthScopeTests(unittest.TestCase):
    """Bucket 4 (ACTIONABLE) — auth-scope pre-flight."""

    def setUp(self):
        _wipe_cache()

    def tearDown(self):
        _wipe_cache()

    def test_missing_project_scope_skips(self):
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_without_project,
        )
        self.assertEqual(result["action"], "skip_no_auth_scope")

    def test_present_project_scope_proceeds(self):
        hook._write_cache(_ids_blob())
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "set")

    def test_read_project_substring_does_not_count(self):
        """`read:project` substring must NOT count as `project` scope."""
        runner = lambda: "  - Token scopes: 'read:project', 'repo'\n"  # noqa: E731
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=runner,
        )
        self.assertEqual(result["action"], "skip_no_auth_scope")

    def test_auth_warn_debounce_only_logs_once(self):
        """Second fire in same session should not re-log auth-scope warning."""
        # First fire — should create the sentinel
        hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_without_project,
        )
        self.assertTrue(hook.AUTH_WARN_SENTINEL.exists())
        mtime1 = hook.AUTH_WARN_SENTINEL.stat().st_mtime

        # Second fire — sentinel exists, no new log
        time.sleep(0.01)  # ensure mtime would change if file were re-touched
        hook.check(
            _bash('gh issue edit 124 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_without_project,
        )
        mtime2 = hook.AUTH_WARN_SENTINEL.stat().st_mtime
        self.assertEqual(mtime1, mtime2, "Sentinel should NOT be re-touched on second fire")


class IDCacheTests(unittest.TestCase):
    """Bucket 5 (ACTIONABLE) — ID-cache behavior."""

    def setUp(self):
        _wipe_cache()

    def tearDown(self):
        _wipe_cache()

    def test_first_fire_introspects_and_caches_mode_0600(self):
        router = FakeGraphQLRouter(
            introspect=_introspect_response,
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "set")
        self.assertEqual(router.calls["introspect"], 1, "Should introspect on first fire")
        self.assertTrue(hook.CACHE_PATH.is_file())
        # Mode 0600 check
        mode = hook.CACHE_PATH.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600, f"Cache should be mode 0600, got 0o{mode:o}")

    def test_second_fire_within_ttl_uses_cache(self):
        router = FakeGraphQLRouter(
            introspect=_introspect_response,
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        # First fire — populates cache
        hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        # Second fire — should NOT re-introspect
        hook.check(
            _bash('gh issue edit 124 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(router.calls["introspect"], 1, "Cache should prevent second introspect")

    def test_stale_cache_re_introspects(self):
        # Pre-populate a stale cache (cached_at far in the past)
        hook.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        stale = {**_ids_blob(), "cached_at": time.time() - hook.CACHE_TTL_SECONDS - 60}
        hook.CACHE_PATH.write_text(json.dumps(stale), encoding="utf-8")

        router = FakeGraphQLRouter(
            introspect=_introspect_response,
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(router.calls["introspect"], 1, "Stale cache should trigger re-introspect")

    def test_field_not_found_busts_cache_and_retries(self):
        """If the first mutation reports 'field not found', the cache should
        be busted and the mutation retried once after re-introspection."""
        hook._write_cache(_ids_blob())

        # First mutation call returns field-not-found; second call (post-bust)
        # returns success. Use a list-pop pattern for the responder.
        mutation_responses = [
            _mutation_field_not_found_response(),
            _mutation_success_response(),
        ]
        introspect_responses = [_introspect_response()]

        def mutation_fn(_variables):
            return mutation_responses.pop(0)

        def introspect_fn():
            return introspect_responses.pop(0) if introspect_responses else ""

        router = FakeGraphQLRouter(
            introspect=introspect_fn,
            item_lookup=_item_lookup_response,
            mutation=mutation_fn,
        )
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "set")
        self.assertTrue(result.get("retried_after_cache_bust"))
        self.assertEqual(router.calls["mutation"], 2, "Should retry mutation once after cache-bust")
        self.assertEqual(router.calls["introspect"], 1, "Should re-introspect once after bust")


class GraphQLNoOpTests(unittest.TestCase):
    """Bucket 6 (INFORMATIONAL) — GraphQL graceful-handle cases."""

    def setUp(self):
        _wipe_cache()
        hook._write_cache(_ids_blob())

    def tearDown(self):
        _wipe_cache()

    def test_issue_not_on_project_skips(self):
        """`items(first:100)` returns empty → skip_no_item gracefully."""
        router = FakeGraphQLRouter(
            item_lookup=lambda repo, num: _item_lookup_empty_response(),
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 999 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "skip_no_item")
        self.assertEqual(router.calls["mutation"], 0, "Should not mutate when item not on board")

    def test_missing_wave_option_skips(self):
        """When the Wave field has no option for the requested wave, skip."""
        # Write a cache with NO P3W12 option present
        ids = _ids_blob()
        hook._write_cache(ids)  # has P3W10 + P3W11 only
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-12"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "skip_no_option")
        self.assertEqual(result["option_name"], "P3W12")
        self.assertEqual(router.calls["mutation"], 0)


class WaveLabelToOptionNameTests(unittest.TestCase):
    """Pure-function coverage for the label→option-name conversion."""

    def test_canonical_conversion(self):
        self.assertEqual(hook._wave_label_to_option_name("p3-wave-11"), "P3W11")

    def test_double_digit_wave(self):
        self.assertEqual(hook._wave_label_to_option_name("p3-wave-10"), "P3W10")

    def test_invalid_label_returns_none(self):
        self.assertIsNone(hook._wave_label_to_option_name("p3-wave-10-special"))
        self.assertIsNone(hook._wave_label_to_option_name("bug"))

    def test_global_form_maps_to_WX(self):
        """#810: phase-agnostic `wave-16` → `W16`."""
        self.assertEqual(hook._wave_label_to_option_name("wave-16"), "W16")

    def test_placeholder_maps_to_WX_literal(self):
        """#810: the `wave-x` placeholder → `WX`."""
        self.assertEqual(hook._wave_label_to_option_name("wave-x"), "WX")

    def test_suffixed_global_form_returns_none(self):
        """#810 anchor guard: `wave-10-frozen` is out of pattern."""
        self.assertIsNone(hook._wave_label_to_option_name("wave-10-frozen"))


class KillSwitchPureTests(unittest.TestCase):
    """Pure-function coverage for the kill-switch helper."""

    def setUp(self):
        os.environ.pop(hook.KILL_SWITCH_ENV, None)

    def tearDown(self):
        os.environ.pop(hook.KILL_SWITCH_ENV, None)

    def test_unset(self):
        self.assertFalse(hook._kill_switch_active())

    def test_value_1(self):
        os.environ[hook.KILL_SWITCH_ENV] = "1"
        self.assertTrue(hook._kill_switch_active())

    def test_value_0(self):
        os.environ[hook.KILL_SWITCH_ENV] = "0"
        self.assertFalse(hook._kill_switch_active())

    def test_value_empty(self):
        os.environ[hook.KILL_SWITCH_ENV] = ""
        self.assertFalse(hook._kill_switch_active())

    def test_value_true_string(self):
        os.environ[hook.KILL_SWITCH_ENV] = "true"
        self.assertFalse(hook._kill_switch_active())


class GraphQLVariableUsageTests(unittest.TestCase):
    """Static analysis: every declared GraphQL variable must be referenced in the body.

    Catches the variableNotUsed class of bug that caused the first-production-fire
    on Hook 21 (issue #448). The old _ITEM_LOOKUP_QUERY declared $repo and $num
    but never used them — GitHub's GraphQL rejected with variableNotUsed errors,
    gh exited non-zero, and the hook silently skipped with skip_no_item.

    This test is intentionally query-string-level (no subprocess / network) so
    it runs in the default suite and catches the bug class at authoring time.
    Sibling pattern to issue #175 (Hook 15 sentinel-fallback shell-vs-Python
    hash test gap) — same shape, different query.
    """

    _QUERIES_UNDER_TEST = [
        ("_ITEM_LOOKUP_QUERY", hook._ITEM_LOOKUP_QUERY),
        ("_INTROSPECT_QUERY", hook._INTROSPECT_QUERY),
        ("_SET_FIELD_MUTATION", hook._SET_FIELD_MUTATION),
        ("_CLEAR_FIELD_MUTATION", hook._CLEAR_FIELD_MUTATION),
    ]

    @staticmethod
    def _declared_vars(query: str) -> set[str]:
        """Return the set of variable names declared in `query(...)` / `mutation(...)`.

        Matches `$varname` inside the leading `query(...)` or `mutation(...)` signature
        (i.e. before the first `{`), which is where GraphQL variable declarations live.
        """
        import re

        # Everything up to (and including) the opening brace of the operation body.
        header_match = re.match(r"[^{]*\(([^)]*)\)", query, re.DOTALL)
        if not header_match:
            return set()
        return set(re.findall(r"\$(\w+)", header_match.group(1)))

    def _assert_all_declared_vars_used(self, name: str, query: str) -> None:
        declared = self._declared_vars(query)
        # Each declared var must appear in the query body (i.e., at least twice
        # in the full string — once in the signature, once in the body).
        import re

        for var in declared:
            count = len(re.findall(rf"\${re.escape(var)}\b", query))
            self.assertGreaterEqual(
                count,
                2,
                f"{name}: declared variable ${var} is never referenced in the query body "
                f"(variableNotUsed — same class as issue #448). "
                f"Either use it in the body or remove it from the signature.",
            )

    def test_item_lookup_query_all_vars_used(self):
        self._assert_all_declared_vars_used("_ITEM_LOOKUP_QUERY", hook._ITEM_LOOKUP_QUERY)

    def test_introspect_query_all_vars_used(self):
        self._assert_all_declared_vars_used("_INTROSPECT_QUERY", hook._INTROSPECT_QUERY)

    def test_set_field_mutation_all_vars_used(self):
        self._assert_all_declared_vars_used("_SET_FIELD_MUTATION", hook._SET_FIELD_MUTATION)

    def test_clear_field_mutation_all_vars_used(self):
        self._assert_all_declared_vars_used("_CLEAR_FIELD_MUTATION", hook._CLEAR_FIELD_MUTATION)

    def test_old_buggy_query_would_have_failed(self):
        """Regression guard: the old _ITEM_LOOKUP_QUERY shape fails this check.

        Ensures the test catches the exact bug class from issue #448 — if someone
        accidentally reverts to the old query, this test turns red.
        """
        old_buggy_query = """
query($org: String!, $project: Int!, $repo: String!, $num: Int!) {
  organization(login: $org) {
    projectV2(number: $project) {
      items(first: 100) {
        nodes {
          id
          content {
            ... on Issue { number repository { name } }
          }
        }
      }
    }
  }
}
"""
        import re

        declared = self._declared_vars(old_buggy_query)
        unused = []
        for var in declared:
            count = len(re.findall(rf"\${re.escape(var)}\b", old_buggy_query))
            if count < 2:
                unused.append(var)
        self.assertIn(
            "repo",
            unused,
            "Old buggy query should have $repo as unused — test regression guard failed",
        )
        self.assertIn(
            "num",
            unused,
            "Old buggy query should have $num as unused — test regression guard failed",
        )


class MultiCmdBashTests(unittest.TestCase):
    """Bucket 7 (ACTIONABLE) — multi-cmd Bash dispatching, issue #455.

    A single Bash tool call may contain multiple `gh issue edit` invocations
    via `;`, `&&`, or newline separators. The hook must dispatch ONE Wave
    field sync per change, not silent-skip the whole batch.

    Tests pin both the parser (returns N WaveLabelChange objects) AND the
    dispatch (`check()` returns `{"action": "multi", "results": [...]}` with
    N entries).
    """

    def setUp(self):
        _wipe_cache()
        hook.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        hook._write_cache(_ids_blob())

    def tearDown(self):
        _wipe_cache()

    def test_semicolon_chain_dispatches_per_segment(self):
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        cmd = (
            "gh issue edit 100 --repo noorinalabs/noorinalabs-deploy "
            '--add-label "p3-wave-11" ; '
            "gh issue edit 101 --repo noorinalabs/noorinalabs-deploy "
            '--add-label "p3-wave-11" ; '
            "gh issue edit 102 --repo noorinalabs/noorinalabs-deploy "
            '--add-label "p3-wave-11"'
        )
        result = hook.check(
            _bash(cmd),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "multi")
        self.assertEqual(result["count"], 3)
        self.assertEqual(len(result["results"]), 3)
        for r in result["results"]:
            self.assertEqual(r["action"], "set")
            self.assertEqual(r["option_name"], "P3W11")
        self.assertEqual(router.calls["mutation"], 3, "Should dispatch one mutation per change")

    def test_ampersand_chain_dispatches_per_segment(self):
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        cmd = (
            "gh issue edit 200 --repo noorinalabs/noorinalabs-main "
            '--add-label "p3-wave-11" && '
            "gh issue edit 201 --repo noorinalabs/noorinalabs-main "
            '--add-label "p3-wave-11"'
        )
        result = hook.check(
            _bash(cmd),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "multi")
        self.assertEqual(result["count"], 2)
        self.assertEqual(router.calls["mutation"], 2)

    def test_newline_separated_commands_dispatch_per_segment(self):
        """Newline + `\\` line-continuation is normalized by the shared
        tokenizer (_LINE_CONTINUATION_RE); plain newline acts like `;`."""
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        cmd = (
            'gh issue edit 300 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"\n'
            'gh issue edit 301 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'
        )
        # shlex.split tokenizes newline as whitespace by default — segment
        # operators `;`/`&&`/`||`/`|` are what split commands. Plain newlines
        # do NOT segment, so this command tokenizes as a single segment with
        # two `gh issue edit` invocations concatenated. The realistic shape
        # is `;`-separated; the newline-only shape is rare in practice.
        # Pin the realistic semicolon-newline shape:
        cmd = (
            'gh issue edit 300 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11" ;\n'
            'gh issue edit 301 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'
        )
        result = hook.check(
            _bash(cmd),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "multi")
        self.assertEqual(result["count"], 2)
        self.assertEqual(router.calls["mutation"], 2)

    def test_mixed_set_and_clear_in_multi_cmd(self):
        """`gh issue edit X --add p3-wave-11; gh issue edit Y --remove p3-wave-10`
        dispatches one set + one clear."""
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        cmd = (
            "gh issue edit 400 --repo noorinalabs/noorinalabs-main "
            '--add-label "p3-wave-11" ; '
            "gh issue edit 401 --repo noorinalabs/noorinalabs-main "
            '--remove-label "p3-wave-10"'
        )
        result = hook.check(
            _bash(cmd),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "multi")
        actions = [r["action"] for r in result["results"]]
        self.assertEqual(actions, ["set", "cleared"])

    def test_single_cmd_preserves_legacy_shape(self):
        """Single-cmd return MUST still be the flat dict (not wrapped in `multi`)
        so existing callers and tests are unaffected."""
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 500 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "set")
        self.assertNotIn("results", result, "Single-cmd must not return multi-shape dict")

    def test_parser_skip_logs_for_unparseable_wave_label_cmd(self):
        """When the command CONTAINS `gh issue edit` + canonical wave-label
        but the parser extracts nothing, the hook emits a parser-skip
        annunaki event per #455 acceptance criterion.

        #650 update: a missing `--repo` is NO LONGER the unparseable shape —
        the parser now returns the change (repo=None) and the hook resolves
        the ambient repo from cwd. The remaining genuinely-unparseable shape
        is an UNEXPANDED shell variable as the issue number
        (`gh issue edit $ISSUE ...`): `$ISSUE` is not a digit so no change is
        extracted, yet the command clearly intended a wave-label edit."""
        cmd = (
            # Unexpanded `$ISSUE` → issue_number not a digit → parser returns
            # empty, but the command clearly intended a wave-label edit.
            'gh issue edit $ISSUE --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'
        )
        result = hook.check(_bash(cmd))
        self.assertEqual(result["action"], "skip_parser_returned_empty")

    def test_parser_skip_does_not_fire_on_unrelated_command(self):
        """A command with NO `gh issue edit` at all returns None, not skip."""
        result = hook.check(_bash("echo hello world"))
        self.assertIsNone(result)

    def test_parser_skip_does_not_fire_on_suffixed_label(self):
        """`p3-wave-10-special` is not canonical; should NOT trigger parser-skip
        log (would be noise). This is the regression guard for the bounded
        regex anchor in _CANONICAL_WAVE_LABEL_IN_CMD."""
        cmd = (
            'gh issue edit 700 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-10-special"'
        )
        result = hook.check(_bash(cmd))
        self.assertIsNone(result)


class SkipPathLoggingTests(unittest.TestCase):
    """Bucket 8 (ACTIONABLE) — issue #451 skip-path annunaki coverage.

    skip_no_item, skip_no_auth_scope, skip_no_project_ids, skip_no_option,
    and skip_mutation_failed must all emit log_posttooluse_event so
    /annunaki and /annunaki-attack can sweep them.
    """

    def setUp(self):
        _wipe_cache()

    def tearDown(self):
        _wipe_cache()

    def _make_log_capture(self):
        """Patch annunaki_log.log_posttooluse_event to capture calls.

        Patches BOTH the source-of-truth module attribute AND the hook
        module's already-bound reference (Python imports the name at
        import time; subsequent module attribute changes don't propagate).
        """
        captured = []
        orig_hook_logger = hook.log_posttooluse_event

        def fake_logger(hook_name, command, reason, tool_name="Bash"):
            captured.append({"hook": hook_name, "command": command, "reason": reason})

        hook.log_posttooluse_event = fake_logger

        def restore():
            hook.log_posttooluse_event = orig_hook_logger

        return captured, restore

    def test_skip_no_item_logs(self):
        """skip_no_item must produce an annunaki log entry per #451."""
        hook._write_cache(_ids_blob())
        captured, restore = self._make_log_capture()
        try:
            router = FakeGraphQLRouter(
                item_lookup=lambda repo, num: _item_lookup_empty_response(),
                mutation=_mutation_success_response,
            )
            result = hook.check(
                _bash(
                    'gh issue edit 999 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'
                ),
                auth_status_runner=_scopes_with_project,
                graphql_runner=router,
            )
            self.assertEqual(result["action"], "skip_no_item")
            self.assertTrue(
                any("skip_no_item" in c["reason"] for c in captured),
                f"skip_no_item path must log; captured: {captured}",
            )
        finally:
            restore()

    def test_skip_no_auth_scope_logs(self):
        """skip_no_auth_scope is already covered by the auth-warn-debounce
        sentinel. Pin that path still produces a log entry (via the
        debounced sentinel-creation path, which calls log_posttooluse_event)."""
        captured, restore = self._make_log_capture()
        try:
            result = hook.check(
                _bash(
                    'gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'
                ),
                auth_status_runner=_scopes_without_project,
            )
            self.assertEqual(result["action"], "skip_no_auth_scope")
            self.assertTrue(
                any("project scope" in c["reason"] for c in captured),
                f"skip_no_auth_scope path must log; captured: {captured}",
            )
        finally:
            restore()

    def test_skip_no_project_ids_logs(self):
        """skip_no_project_ids fires when introspection returns no data."""
        captured, restore = self._make_log_capture()
        try:
            # Empty introspect response → no ids → skip
            router = FakeGraphQLRouter(introspect=lambda: "")
            result = hook.check(
                _bash(
                    'gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'
                ),
                auth_status_runner=_scopes_with_project,
                graphql_runner=router,
            )
            self.assertEqual(result["action"], "skip_no_project_ids")
            self.assertTrue(
                any("skip_no_project_ids" in c["reason"] for c in captured),
                f"skip_no_project_ids must log; captured: {captured}",
            )
        finally:
            restore()

    def test_skip_no_option_logs(self):
        """skip_no_option fires when the requested wave's option is not in
        the cached option_ids dict."""
        hook._write_cache(_ids_blob())  # has P3W10 + P3W11 only
        captured, restore = self._make_log_capture()
        try:
            router = FakeGraphQLRouter(
                item_lookup=_item_lookup_response,
                mutation=_mutation_success_response,
            )
            result = hook.check(
                _bash(
                    'gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-12"'
                ),
                auth_status_runner=_scopes_with_project,
                graphql_runner=router,
            )
            self.assertEqual(result["action"], "skip_no_option")
            self.assertTrue(
                any(
                    "skip_no_option" in c["reason"] or "no option" in c["reason"] for c in captured
                ),
                f"skip_no_option must log; captured: {captured}",
            )
        finally:
            restore()

    def test_skip_mutation_failed_logs(self):
        """skip_mutation_failed fires when the set-field GraphQL mutation
        returns empty (gh exit non-zero) and the field-not-found retry path
        does not apply — covers the 5th skip path from the bucket docstring
        (closes #462). Symmetric to the other 4 tests in this class.
        """
        hook._write_cache(_ids_blob())
        captured, restore = self._make_log_capture()
        try:
            # Mutation responder returns empty → _gh_graphql returns None →
            # `not result` branch in _apply_one_change → skip_mutation_failed.
            # No "field not found" string in the (empty) errors blob, so the
            # cache-bust retry path is not taken.
            router = FakeGraphQLRouter(
                item_lookup=_item_lookup_response,
                mutation=lambda _vars: "",
            )
            result = hook.check(
                _bash(
                    'gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'
                ),
                auth_status_runner=_scopes_with_project,
                graphql_runner=router,
            )
            self.assertEqual(result["action"], "skip_mutation_failed")
            self.assertTrue(
                any("set-field mutation failed" in c["reason"] for c in captured),
                f"skip_mutation_failed must log set-field-mutation-failed; captured: {captured}",
            )
        finally:
            restore()


class CanonicalWaveLabelRegexTests(unittest.TestCase):
    """Issue #463 — `_CANONICAL_WAVE_LABEL_IN_CMD` defense-in-depth anchor
    must match canonical wave labels in ALL plausible flag-value shapes:
    quoted, equals-form, spaced-bare, AND spaced-bare at end-of-string
    (the gap the original `["\\s]` right-anchor missed).

    The regex powers the parser-skip log path (line 664-672 in the hook):
    if `parse_wave_label_changes` returns empty but the command contains
    `gh issue edit` AND this regex matches, we annunaki-log a
    `skip_parser_returned_empty` event so silent multi-cmd misses are
    visible to /annunaki-attack. A regex miss here turns into a silent
    silent-bypass, so the spaced-bare-EOF gap is a defense-in-depth bug.

    Acceptance criteria from #463:
      - `--add-label p3-wave-11<EOF>` (spaced bare EOF) → match
      - `--add-label=p3-wave-11<EOF>` (equals EOF)      → match
      - `--add-label "p3-wave-10-special"` (suffixed)   → NOT match
      - `--add-label p3-wave-10-special` (suffixed EOF) → NOT match
    """

    # All four #463 acceptance cases use a command that the parser
    # actually CAN'T parse (missing --repo), so the parser-skip log
    # path is the one exercised by check(). The first two MUST log;
    # the last two MUST NOT log.

    def setUp(self):
        _wipe_cache()

    def tearDown(self):
        _wipe_cache()

    def test_spaced_bare_eof_matches(self):
        """The #463 headline gap: `--add-label p3-wave-11` at command end."""
        self.assertIsNotNone(
            hook._CANONICAL_WAVE_LABEL_IN_CMD.search("gh issue edit 1 --add-label p3-wave-11"),
            "spaced-bare canonical wave-label at EOF must match",
        )

    def test_equals_bare_eof_matches(self):
        """The other EOF shape: `--add-label=p3-wave-11` at command end."""
        self.assertIsNotNone(
            hook._CANONICAL_WAVE_LABEL_IN_CMD.search("gh issue edit 1 --add-label=p3-wave-11"),
            "equals-form canonical wave-label at EOF must match",
        )

    def test_quoted_with_surrounding_still_matches(self):
        """Regression: pre-existing matched form must still match."""
        self.assertIsNotNone(
            hook._CANONICAL_WAVE_LABEL_IN_CMD.search(
                'gh issue edit 1 --add-label "p3-wave-11" --remove-label "p3-wave-10"'
            )
        )

    def test_suffixed_label_quoted_does_not_match(self):
        """Regression guard from issue #463: suffixed labels like
        `p3-wave-10-special` must NOT match even in quoted form."""
        self.assertIsNone(
            hook._CANONICAL_WAVE_LABEL_IN_CMD.search(
                'gh issue edit 1 --add-label "p3-wave-10-special"'
            ),
            "suffixed label must NOT match canonical regex (would log false-positive)",
        )

    def test_suffixed_label_spaced_eof_does_not_match(self):
        """New guard from issue #463: suffixed label at spaced-bare EOF
        must also NOT match. With the widened right-anchor it's tempting
        for the regex to match `p3-wave-10` and leave `-special` trailing,
        but the right-anchor requires `["\\s]` or `$` — `-` satisfies
        neither, so the regex backtracks and ultimately fails to match.
        """
        self.assertIsNone(
            hook._CANONICAL_WAVE_LABEL_IN_CMD.search(
                "gh issue edit 1 --add-label p3-wave-10-special"
            ),
            "suffixed label at spaced-bare EOF must NOT match — widened right-anchor "
            "regression guard",
        )

    def test_parser_skip_logs_for_spaced_bare_eof_cmd(self):
        """End-to-end via check(): a spaced-bare-EOF wave-label on a command
        the parser still can't resolve must produce a skip_parser_returned_empty
        event so /annunaki-attack catches the silent miss.

        #650 update: missing-`--repo` is now resolved from cwd, so the
        unparseable shape here uses an unexpanded `$N` issue number while
        keeping the spaced-bare-EOF `--add-label p3-wave-11` form that
        exercises the #463 right-anchor.
        """
        # `gh issue edit $N --add-label p3-wave-11` — unexpanded var, no quotes.
        # `$N` is not a digit → parser returns empty; the spaced-bare-EOF
        # canonical label still matches _CANONICAL_WAVE_LABEL_IN_CMD (#463).
        result = hook.check(_bash("gh issue edit $N --add-label p3-wave-11"))
        self.assertEqual(
            result.get("action") if result else None,
            "skip_parser_returned_empty",
            "spaced-bare-EOF wave-label must trigger parser-skip log path post-#463",
        )

    def test_parser_skip_does_not_fire_on_suffixed_label_spaced_eof(self):
        """End-to-end regression guard: suffixed label at spaced-bare EOF
        must NOT trigger the parser-skip log (would be noise). Companion
        to `test_parser_skip_does_not_fire_on_suffixed_label` in the
        MultiCmdBashTests bucket (which covers the quoted suffixed case).
        """
        result = hook.check(_bash("gh issue edit 1 --add-label p3-wave-10-special"))
        self.assertIsNone(
            result,
            "suffixed label at spaced-bare EOF must NOT trigger parser-skip log",
        )

    def test_global_form_quoted_matches(self):
        """#810: phase-agnostic `wave-16` must match the heuristic regex."""
        self.assertIsNotNone(
            hook._CANONICAL_WAVE_LABEL_IN_CMD.search('gh issue edit 1 --add-label "wave-16"')
        )

    def test_global_form_spaced_eof_matches(self):
        """#810: `--add-label wave-16` at command end must match."""
        self.assertIsNotNone(
            hook._CANONICAL_WAVE_LABEL_IN_CMD.search("gh issue edit 1 --add-label wave-16")
        )

    def test_placeholder_form_matches(self):
        """#810: the `wave-x` placeholder must match the heuristic regex."""
        self.assertIsNotNone(
            hook._CANONICAL_WAVE_LABEL_IN_CMD.search('gh issue edit 1 --add-label "wave-x"')
        )

    def test_suffixed_global_form_does_not_match(self):
        """#810: `wave-10-frozen` must NOT match (anchor regression guard)."""
        self.assertIsNone(
            hook._CANONICAL_WAVE_LABEL_IN_CMD.search('gh issue edit 1 --add-label "wave-10-frozen"')
        )


class MultiCmdNoMatchPreservedTests(unittest.TestCase):
    """Regression: ensure multi-cmd refactor did NOT regress the existing
    no-match cases (suffixed labels, wrong subcommand, etc.). Verifies the
    parser-skip log is silent on these too."""

    def test_suffixed_label_in_multi_cmd_does_not_match(self):
        cmd = (
            "echo hello ; "
            "gh issue edit 1 --repo noorinalabs/noorinalabs-main "
            '--add-label "p3-wave-10-special" ; '
            "echo world"
        )
        result = hook.check(_bash(cmd))
        self.assertIsNone(result)

    def test_pr_edit_in_multi_cmd_does_not_match(self):
        cmd = (
            'gh pr edit 1 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11" && '
            'gh pr edit 2 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'
        )
        result = hook.check(_bash(cmd))
        self.assertIsNone(result)


class AmbientRepoResolutionTests(unittest.TestCase):
    """Bucket 9 (ACTIONABLE) — issue #650 ambient `--repo` resolution.

    A `gh issue edit <num> --remove-label "p4-wave-5"` run from INSIDE the
    target repo carries no `--repo`; gh resolves it from the ambient git
    context. The parser now returns the change with repo=None and the hook
    recovers the repo from the invocation cwd via the injected git_runner.
    Before #650 this produced a `skip_parser_returned_empty` and the board
    Wave field silently went unsynced.
    """

    _ORIGIN = "git@github.com:noorinalabs/noorinalabs-main.git\n"

    def setUp(self):
        _wipe_cache()
        hook.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        hook._write_cache(_ids_blob())

    def tearDown(self):
        _wipe_cache()

    def _git_runner(self, url=None):
        """Return a (runner, calls) pair; calls[0] counts invocations."""
        calls = [0]
        resolved = self._ORIGIN if url is None else url

        def runner(_cwd):
            calls[0] += 1
            return resolved

        return runner, calls

    def test_exact_issue_650_reproducer_clears_field(self):
        """The exact `comment ; echo ; edit --remove-label ; echo ; view`
        shape from issue #650 (no --repo) must resolve repo from cwd and
        CLEAR the Wave field — not skip_parser_returned_empty."""
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        runner, _ = self._git_runner()
        cmd = (
            'gh issue comment 601 -b "P4W5 close-out" ; '
            "echo done ; "
            'gh issue edit 601 --remove-label "p4-wave-5" ; '
            "echo ok ; "
            "gh issue view 601"
        )
        # P4W5 option must exist for the (cleared) lookup path; clear doesn't
        # need the option but item-lookup runs regardless.
        hook._write_cache(
            {
                "project_id": "PROJ_NODE_ID",
                "field_id": "WAVE_FIELD_ID",
                "option_ids": {"P4W5": "OPT_P4W5"},
            }
        )
        result = hook.check(
            _bash(cmd),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
            git_runner=runner,
        )
        self.assertEqual(result["action"], "cleared")
        self.assertEqual(result["repo"], "noorinalabs-main")
        self.assertEqual(result["issue"], "601")

    def test_single_no_repo_add_label_resolves_and_sets(self):
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        runner, _ = self._git_runner()
        result = hook.check(
            _bash('gh issue edit 123 --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
            git_runner=runner,
        )
        self.assertEqual(result["action"], "set")
        self.assertEqual(result["repo"], "noorinalabs-main")
        self.assertEqual(result["option_name"], "P3W11")

    def test_https_origin_url_strips_dotgit(self):
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        runner, _ = self._git_runner(url="https://github.com/noorinalabs/noorinalabs-deploy\n")
        result = hook.check(
            _bash('gh issue edit 123 --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
            git_runner=runner,
        )
        self.assertEqual(result["action"], "set")
        self.assertEqual(result["repo"], "noorinalabs-deploy")

    def test_multi_cmd_no_repo_resolves_once(self):
        """Two `--repo`-less edits in one compound command share one cwd; the
        git origin should be resolved at most once."""
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        runner, calls = self._git_runner()
        cmd = (
            'gh issue edit 100 --add-label "p3-wave-11" ; '
            'gh issue edit 101 --add-label "p3-wave-11"'
        )
        result = hook.check(
            _bash(cmd),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
            git_runner=runner,
        )
        self.assertEqual(result["action"], "multi")
        self.assertEqual(result["count"], 2)
        self.assertTrue(all(r["repo"] == "noorinalabs-main" for r in result["results"]))
        self.assertEqual(calls[0], 1, "ambient repo should be resolved once for a shared cwd")

    def test_explicit_repo_does_not_invoke_git_runner(self):
        """When `--repo` IS present, the ambient resolver must not be called."""
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        runner, calls = self._git_runner()
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
            git_runner=runner,
        )
        self.assertEqual(result["action"], "set")
        self.assertEqual(calls[0], 0, "explicit --repo must not trigger ambient resolution")

    def test_unresolvable_repo_skips_no_repo_context(self):
        """No --repo AND no git origin → skip_no_repo_context (not a crash,
        not a silent skip_parser_returned_empty)."""
        result = hook.check(
            _bash('gh issue edit 123 --remove-label "p3-wave-10"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=FakeGraphQLRouter(),
            git_runner=lambda _cwd: None,
        )
        self.assertEqual(result["action"], "skip_no_repo_context")
        self.assertEqual(result["issue"], "123")

    def test_unresolvable_repo_logs(self):
        """skip_no_repo_context must emit an annunaki log entry."""
        captured = []
        orig = hook.log_posttooluse_event
        hook.log_posttooluse_event = lambda *a, **k: captured.append(a)
        try:
            hook.check(
                _bash('gh issue edit 123 --remove-label "p3-wave-10"'),
                auth_status_runner=_scopes_with_project,
                git_runner=lambda _cwd: None,
            )
            self.assertTrue(
                any("skip_no_repo_context" in str(a) for a in captured),
                f"skip_no_repo_context must log; captured: {captured}",
            )
        finally:
            hook.log_posttooluse_event = orig


if __name__ == "__main__":
    unittest.main()
