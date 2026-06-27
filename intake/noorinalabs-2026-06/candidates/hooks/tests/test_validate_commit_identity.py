#!/usr/bin/env python3
"""Tests for validate_commit_identity hook.

Covers the W9 parent+child roster merge feature (issue #112 part a) plus
regression coverage for the pre-existing cross-repo `cd <path>` detection.

Run: python3 -m pytest .claude/hooks/tests/test_validate_commit_identity.py -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_commit_identity as hook  # noqa: E402


def _git_init(path: Path) -> None:
    """Init a bare git repo at `path` by creating `.git` as a dir stub.

    We don't need `git` to work — the hook only checks `(path / ".git").exists()`.
    Creating `.git` as a directory satisfies the check deterministically and
    without spawning subprocesses.
    """
    (path / ".git").mkdir(parents=True, exist_ok=True)


def _write_roster(repo_path: Path, roster: dict[str, str]) -> None:
    team_dir = repo_path / ".claude" / "team"
    team_dir.mkdir(parents=True, exist_ok=True)
    (team_dir / "roster.json").write_text(json.dumps(roster), encoding="utf-8")


class LoadMergedRosterTests(unittest.TestCase):
    """Unit tests for `_load_merged_roster` — parent+child merge semantics."""

    def test_child_only_no_parent(self):
        """Parent roster missing → returns child roster unchanged."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)  # parent IS a git repo, but has no roster
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            merged = hook._load_merged_roster(child)
            self.assertEqual(merged, {"Alice": "alice@example.com"})

    def test_parent_not_a_git_repo(self):
        """Parent dir exists but is NOT a git repo → parent ignored."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            # Intentionally do NOT `_git_init(outer)` — parent has no `.git`
            _write_roster(outer, {"ShouldNotAppear": "nope@example.com"})
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            merged = hook._load_merged_roster(child)
            self.assertEqual(merged, {"Alice": "alice@example.com"})
            self.assertNotIn("ShouldNotAppear", merged)

    def test_parent_is_git_repo_without_roster(self):
        """Parent is a git repo but has no `.claude/team/roster.json` → ignored."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            # no roster written for outer
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            merged = hook._load_merged_roster(child)
            self.assertEqual(merged, {"Alice": "alice@example.com"})

    def test_child_plus_parent_merge_union(self):
        """Parent + child with disjoint names → union of both."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {"Nadia": "nadia@example.com"})
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            merged = hook._load_merged_roster(child)
            self.assertEqual(
                merged,
                {
                    "Nadia": "nadia@example.com",
                    "Alice": "alice@example.com",
                },
            )

    def test_child_wins_on_name_collision(self):
        """Same name in both with different emails → child email wins."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {"Alice": "alice-parent@example.com"})
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice-child@example.com"})

            merged = hook._load_merged_roster(child)
            self.assertEqual(merged, {"Alice": "alice-child@example.com"})

    def test_walk_only_one_level_grandparent_ignored(self):
        """Grandparent has roster, parent does not → grandparent NOT loaded."""
        with tempfile.TemporaryDirectory() as td:
            grand = Path(td)
            _git_init(grand)
            _write_roster(grand, {"Grandparent": "gp@example.com"})
            parent = grand / "parent"
            parent.mkdir()
            # parent is NOT a git repo and has no roster
            child = parent / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            merged = hook._load_merged_roster(child)
            self.assertEqual(merged, {"Alice": "alice@example.com"})
            self.assertNotIn("Grandparent", merged)

    def test_malformed_parent_roster_does_not_block(self):
        """A broken parent roster.json must fail-open — child roster is returned."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            team_dir = outer / ".claude" / "team"
            team_dir.mkdir(parents=True)
            (team_dir / "roster.json").write_text("{ this is not valid json", encoding="utf-8")
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            merged = hook._load_merged_roster(child)
            self.assertEqual(merged, {"Alice": "alice@example.com"})


class DetectTargetRosterTests(unittest.TestCase):
    """Regression tests for `cd <path> && git commit` target-roster detection."""

    def test_cd_target_returns_merged_roster(self):
        """`cd <child> && git commit` loads child+parent merged roster."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {"Nadia": "nadia@example.com"})
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            command = f"cd {child} && git commit -m 'x'"
            detected = hook._detect_target_roster(command)
            self.assertIsNotNone(detected)
            assert detected is not None  # for type-narrowing
            self.assertEqual(
                detected,
                {
                    "Nadia": "nadia@example.com",
                    "Alice": "alice@example.com",
                },
            )

    def test_cd_target_with_no_roster_returns_none(self):
        """`cd <dir>` where dir has no roster → None (fall back to local)."""
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "nonroster"
            target.mkdir()
            # no .claude/team/roster.json

            command = f"cd {target} && git commit -m 'x'"
            self.assertIsNone(hook._detect_target_roster(command))

    def test_no_cd_returns_none(self):
        """Command without `cd` → None (use local ROSTER)."""
        self.assertIsNone(hook._detect_target_roster("git commit -m 'x'"))


class CheckIntegrationTests(unittest.TestCase):
    """Integration: `check()` accepts a name present only in the parent roster.

    Verifies the end-to-end merge path: an org-level coordinator defined ONLY
    in the parent repo's roster is accepted when committing in a child repo.
    """

    def test_parent_only_name_accepted_in_child_commit(self):
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {"Nadia": "nadia@example.com"})
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            command = (
                f'cd {child} && git -c user.name="Nadia" '
                f'-c user.email="nadia@example.com" commit -m "x"'
            )
            result = hook.check({"tool_name": "Bash", "tool_input": {"command": command}})
            self.assertIsNone(result, f"expected allow, got block: {result}")

    def test_child_email_override_blocks_parent_email(self):
        """When child overrides a name's email, the parent email is rejected."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {"Alice": "alice-parent@example.com"})
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice-child@example.com"})

            command = (
                f'cd {child} && git -c user.name="Alice" '
                f'-c user.email="alice-parent@example.com" commit -m "x"'
            )
            result = hook.check({"tool_name": "Bash", "tool_input": {"command": command}})
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.get("decision"), "block")


class MatcherRobustnessTests(unittest.TestCase):
    """Negative-match coverage for the substring-bug cluster (#226, #188, #216)."""

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def test_unquoted_email_value_bounded_by_whitespace(self):
        """#226 repro: bare `-c user.email=val` does NOT slurp to EOL.

        Pre-fix: the regex `-c\\s+user\\.email=["']?([^"']+)["']?` slurped
        from `user.email=` to the next `"` or end-of-line. With a bare value
        and no closing quote, the entire rest of the command was captured
        into the email field. Tokenization via shlex bounds at whitespace.
        """
        # Use a name that exists in the local roster so we can verify the
        # email comparison hits the correct value, not the slurped one.
        valid_name = next(iter(hook.ROSTER), None)
        if not valid_name:
            self.skipTest("local roster is empty")
        valid_email = hook.ROSTER[valid_name]
        cmd = (
            f'git -c user.name="{valid_name}" -c user.email={valid_email} '
            f"commit -F /tmp/commit-msg.txt 2>&1 | tail -20"
        )
        result = hook.check(self._input(cmd))
        self.assertIsNone(
            result,
            "#226: unquoted bare email should be allowed, not slurp to EOL",
        )

    def test_nested_heredoc_in_command_substitution(self):
        """#188 repro: `git commit -m "$(cat <<'EOF' ... EOF)"` mangles the parser.

        Pre-fix: `_strip_heredocs` + `_strip_quoted_strings` interaction on
        nested `$(cat <<'EOF' ... EOF)` inside a double-quoted outer string
        broke the parser's view of `user.name=...`. shlex tokenization
        treats the entire `"$(cat <<'EOF' ... EOF)"` as one token (the outer
        quotes are absorbed; the heredoc body is part of the token's value).
        """
        valid_name = next(iter(hook.ROSTER), None)
        if not valid_name:
            self.skipTest("local roster is empty")
        valid_email = hook.ROSTER[valid_name]
        # The nested form: a heredoc inside a command-substitution inside a
        # double-quoted -m argument.
        cmd = (
            f'git -c user.name="{valid_name}" -c user.email="{valid_email}" '
            "commit -m \"$(cat <<'EOF'\nmulti\nline\nmessage\nEOF\n)\""
        )
        result = hook.check(self._input(cmd))
        self.assertIsNone(
            result,
            "#188: nested heredoc-in-command-sub-in-double-quote should not block",
        )

    def test_heredoc_body_with_git_commit_phrase_does_not_match(self):
        """#216 sibling: heredoc body containing 'git commit' is not a real commit."""
        cmd = (
            "cat > /tmp/x.md <<'EOF'\n"
            "Here is how to git commit with -c flags:\n"
            'git -c user.name="X" commit -m "..."\n'
            "EOF"
        )
        # Not a real commit invocation — should not require identity.
        self.assertIsNone(hook.check(self._input(cmd)))

    def test_alembic_heredoc_body_via_command_substitution(self):
        """user-service#99 claim 1: alembic-shape heredoc body via `-m "$(cat <<EOF...)"`.

        Defensive coverage on top of `test_nested_heredoc_in_command_substitution`
        (#188): the existing test pins the SHAPE; this test pins an alembic-
        specific BODY containing the literal strings the user-service `make
        migrate-new` workflow emits — `heads`, `head`, `revision = '<sha>'`,
        `down_revision`. None of those substrings are hook tokens, but the
        fixture exists so any future tightening of the parser cannot
        accidentally treat alembic-emitted strings as identity-flag keywords.

        Memory ref: `project_w10_user_service_alembic.md` (P2W10 #63 alembic
        heads→head discipline).
        """
        valid_name = next(iter(hook.ROSTER), None)
        if not valid_name:
            self.skipTest("local roster is empty")
        valid_email = hook.ROSTER[valid_name]
        # Alembic-emitted strings inside a heredoc body inside command-sub.
        cmd = (
            f'git -c user.name="{valid_name}" -c user.email="{valid_email}" '
            "commit -m \"$(cat <<'EOF'\n"
            "migrate(P3W8 user-service#63): merge alembic heads -> head\n"
            "\n"
            "revision = 'a1b2c3d4e5f6'\n"
            "down_revision = ('aaaa1111', 'bbbb2222')\n"
            "branch_labels = None\n"
            "depends_on = None\n"
            'EOF\n)"'
        )
        self.assertIsNone(
            hook.check(self._input(cmd)),
            "us#99 claim 1: alembic-shape heredoc body should not false-block",
        )

    def test_label_validator_filename_no_longer_blocks(self):
        """#226 meta-instance: --body-file path inside --label list.

        The label validator (separate hook) can mistake a file path that
        appears between `--body-file` and `--label` for a label value. This
        hook isn't directly affected — covered for adjacency only.
        """
        # validate_commit_identity is on git, not gh. Just confirm gh
        # invocations are not flagged here.
        cmd = 'gh issue create --body-file /tmp/issue-body.txt --label "tech-debt,infrastructure"'
        self.assertIsNone(hook.check(self._input(cmd)))


class ParseFailureFailClosedTests(unittest.TestCase):
    """`tokenize` returns None on shlex parse failure. For commit-identity
    validation this MUST fail-closed: a malformed-but-commit-shaped command
    should block, not silently allow. (Per `_shell_parse.tokenize` caller
    contract pinned with Linh.)
    """

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def test_unbalanced_quote_with_commit_blocks(self):
        """Unterminated quote + git commit shape → block (don't silently allow)."""
        cmd = 'git -c user.name="Aino Virtanen -c user.email="a@b.c" commit -m "x"'
        # Above has an unbalanced quote (the `"Aino Virtanen ` opens and
        # is never closed before the next `"`, so shlex raises).
        result = hook.check(self._input(cmd))
        self.assertIsNotNone(
            result,
            "parse failure on a commit-shaped command must block, not allow",
        )
        assert result is not None
        self.assertEqual(result["decision"], "block")
        # Reason must indicate parse failure and actionable guidance
        # (message updated in #287 to be more precise than "shlex parsing").
        self.assertIn("unbalanced quotes", result["reason"])

    def test_block_message_points_at_F_file_fix(self):
        """Parse-failure block message MUST cite the -F file fix and the
        heredoc-as-cause framing. Codified by #345 after 8 occurrences in
        P3W7-W8 of agents repeating the heredoc pattern despite the memory
        pointer existing — the message itself must surface the fix.
        """
        cmd = 'git -c user.name="Aino Virtanen -c user.email="a@b.c" commit -m "x"'
        result = hook.check(self._input(cmd))
        assert result is not None
        reason = result["reason"]
        # Cause framing: the heredoc-inside--m pattern is named.
        self.assertIn("heredoc", reason.lower())
        self.assertIn('-m "$(cat <<EOF', reason)
        # Fix: -F file pattern is shown.
        self.assertIn("-F /path/to/msg.txt", reason)
        self.assertIn("/tmp/msg-issue-N.txt", reason)
        # Memory pointer: the canonical reference is named so the operator
        # can read full context after applying the fix.
        self.assertIn("feedback_heredoc_in_git_commit.md", reason)

    def test_unbalanced_quote_without_commit_allows(self):
        """Parse failure on a non-commit command → allow (no commit to validate)."""
        cmd = 'echo "unterminated'
        # Not a git commit; allow.
        self.assertIsNone(hook.check(self._input(cmd)))

    def test_repeated_dash_c_user_name_uses_last_value(self):
        """Repeated -c user.name → last value wins (matches git semantics).

        `dict(extract_dash_c_pairs(...))` overwrites earlier entries with
        later ones, mirroring how git itself resolves repeated -c flags.
        """
        valid_name = next(iter(hook.ROSTER), None)
        if not valid_name:
            self.skipTest("local roster is empty")
        valid_email = hook.ROSTER[valid_name]
        # First name is bogus, last is valid → must allow (last wins).
        cmd = (
            f'git -c user.name="NotInRoster" -c user.name="{valid_name}" '
            f'-c user.email="{valid_email}" commit -m "x"'
        )
        self.assertIsNone(
            hook.check(self._input(cmd)),
            "last-wins semantics: bogus earlier value should be overridden",
        )


class HyphenatedNameFixtures(unittest.TestCase):
    """data-acquisition#43: hyphenated names in roster.json must round-trip
    cleanly through shlex tokenization and roster lookup.

    Pins names with hyphens in the first-name slot, last-name slot, and the
    Spanish/West-African/Senegalese double-barrelled-surname patterns that
    show up in noorinalabs-data-acquisition, noorinalabs-landing-page, and
    noorinalabs-user-service rosters. Each name uses the LOCAL parent roster
    (which already contains the merged entries) — no synthetic child repo
    setup needed; the parent roster is the union of all child rosters.
    """

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    # (name, email) tuples that MUST be present in the local roster for the
    # fixture to be meaningful. Skipping on missing keeps the test stable if
    # the roster is trimmed in a future cleanup; the WHY is then surfaced as
    # a skip reason rather than a misleading pass.
    HYPHENATED_NAMES = [
        ("Jean-Claude Habimana", "parametrization+Jean-Claude.Habimana@gmail.com"),
        ("Marcia Vasquez-Paredes", "parametrization+Marcia.Vasquez-Paredes@gmail.com"),
        ("Kofi Mensah-Williams", "parametrization+Kofi.Mensah-Williams@gmail.com"),
        ("Anika Diop-Sarr", "parametrization+Anika.Diop-Sarr@gmail.com"),
        ("Marisol Vega-Cruz", "parametrization+Marisol.Vega-Cruz@gmail.com"),
        ("Jun-Seo Park", "parametrization+Jun-Seo.Park@gmail.com"),
        ("Alejandra Reyes-Fuentes", "parametrization+Alejandra.Reyes-Fuentes@gmail.com"),
        ("Rashid Osei-Mensah", "parametrization+Rashid.Osei-Mensah@gmail.com"),
        ("Mei-Lin Chang", "parametrization+Mei-Lin.Chang@gmail.com"),
        ("Sable Nakamura-Whitfield", "parametrization+Sable.Nakamura-Whitfield@gmail.com"),
    ]

    def test_hyphenated_name_local_commit_allowed(self):
        """Each hyphenated roster name → local commit with matching email allowed."""
        for name, email in self.HYPHENATED_NAMES:
            with self.subTest(name=name):
                if name not in hook.ROSTER:
                    self.skipTest(f"{name} not in local roster — fixture stale")
                self.assertEqual(
                    hook.ROSTER[name],
                    email,
                    f"roster email for {name} drifted from fixture",
                )
                cmd = f'git -c user.name="{name}" -c user.email="{email}" commit -m "test"'
                self.assertIsNone(
                    hook.check(self._input(cmd)),
                    f"hyphenated name {name!r} should pass identity validation",
                )

    def test_hyphenated_name_wrong_email_blocks(self):
        """Hyphenated name with email-local-part stripped of hyphens → blocks.

        Realistic operator mistake: typing `Jean-Claude.Habimana@...` but
        backspacing the hyphen to `JeanClaude.Habimana@...`. The hook must
        catch the email mismatch, not silently accept.
        """
        for name, email in self.HYPHENATED_NAMES:
            with self.subTest(name=name):
                if name not in hook.ROSTER:
                    self.skipTest(f"{name} not in local roster — fixture stale")
                wrong_email = email.replace("-", "")
                if wrong_email == email:
                    continue  # no hyphen in email local-part — nothing to test
                cmd = f'git -c user.name="{name}" -c user.email="{wrong_email}" commit -m "test"'
                result = hook.check(self._input(cmd))
                self.assertIsNotNone(
                    result,
                    f"de-hyphenated email for {name} should not pass identity validation",
                )
                assert result is not None
                self.assertEqual(result.get("decision"), "block")
                self.assertIn("does not match roster", result["reason"])

    def test_unicode_hyphen_carolina_mendez_rios(self):
        """`Carolina Méndez-Ríos` — Unicode (é, í) + hyphen in name; ASCII email.

        ingestion-platform roster pattern. The shlex tokenizer handles UTF-8
        transparently because the bytes are inside quoted strings; the
        roster lookup is a Python dict comparison which is Unicode-safe.
        """
        name = "Carolina Méndez-Ríos"
        if name not in hook.ROSTER:
            self.skipTest(f"{name} not in local roster — fixture stale")
        email = hook.ROSTER[name]
        cmd = f'git -c user.name="{name}" -c user.email="{email}" commit -m "test"'
        self.assertIsNone(
            hook.check(self._input(cmd)),
            f"Unicode+hyphen name {name!r} should pass identity validation",
        )

    def test_tomasz_wojcik_unicode_in_name_ascii_in_email(self):
        """`Tomasz Wójcik` — name has `ó`, email local-part is ASCII `Wojcik`.

        Common Slavic-name handling pattern: display-name retains diacritic,
        email folds to ASCII. The hook compares email STRING equality so a
        mismatch (e.g. `Wójcik` in email) must block.
        """
        name = "Tomasz Wójcik"
        if name not in hook.ROSTER:
            self.skipTest(f"{name} not in local roster — fixture stale")
        ascii_email = hook.ROSTER[name]
        self.assertNotIn("ó", ascii_email, "roster email for Tomasz must be ASCII-folded")
        # Positive: ASCII-folded email allowed.
        cmd_ok = f'git -c user.name="{name}" -c user.email="{ascii_email}" commit -m "test"'
        self.assertIsNone(hook.check(self._input(cmd_ok)))
        # Negative: someone hand-types the diacritic into the email-local-part.
        unfolded_email = ascii_email.replace("Wojcik", "Wójcik")
        cmd_bad = f'git -c user.name="{name}" -c user.email="{unfolded_email}" commit -m "test"'
        result = hook.check(self._input(cmd_bad))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")


class CrossRepoCommitIdentityFixtures(unittest.TestCase):
    """data-acquisition#43: `cd <child-repo> && git commit` shapes that
    real data-acquisition agents emit. Builds a synthetic child repo per
    test using the existing `_git_init`/`_write_roster` helpers so the
    `_detect_target_roster` path is exercised end-to-end against names
    that exist ONLY in the child (not the local parent roster).

    Why this matters: in production the parent roster.json IS the union
    of all child rosters (org-level merge), so a local-only commit would
    succeed for any hyphenated name listed there. The cross-repo `cd`
    path is the one place where the child roster is loaded fresh from
    disk and merged with the parent — and is the codepath that would
    silently miss a tokenization bug for hyphens in `cd <path>`.
    """

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def test_cross_repo_dilara_data_acq_commit_allowed(self):
        """`cd <data-acq-clone> && git -c user.name="Dilara Erdogan" commit`."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            # Parent roster intentionally lacks Dilara to prove the child
            # roster supplies her identity.
            _write_roster(outer, {"Nadia Khoury": "parametrization+Nadia.Khoury@gmail.com"})
            child = outer / "noorinalabs-data-acquisition"
            child.mkdir()
            _git_init(child)
            _write_roster(
                child,
                {"Dilara Erdogan": "parametrization+Dilara.Erdogan@gmail.com"},
            )
            cmd = (
                f'cd {child} && git -c user.name="Dilara Erdogan" '
                f'-c user.email="parametrization+Dilara.Erdogan@gmail.com" '
                f'commit -m "x"'
            )
            self.assertIsNone(
                hook.check(self._input(cmd)),
                "data-acq child roster member must be accepted in cross-repo commit",
            )

    def test_cross_repo_jean_claude_hyphenated_first_name_allowed(self):
        """`cd <data-acq-clone> && git -c user.name="Jean-Claude Habimana" commit`.

        Hyphenated first name through the `cd <path>` codepath. This is the
        canonical fixture flagged in noorinalabs/noorinalabs-data-acquisition#43.
        """
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {})
            child = outer / "noorinalabs-data-acquisition"
            child.mkdir()
            _git_init(child)
            _write_roster(
                child,
                {
                    "Jean-Claude Habimana": "parametrization+Jean-Claude.Habimana@gmail.com",
                },
            )
            cmd = (
                f'cd {child} && git -c user.name="Jean-Claude Habimana" '
                f'-c user.email="parametrization+Jean-Claude.Habimana@gmail.com" '
                f'commit -m "x"'
            )
            self.assertIsNone(
                hook.check(self._input(cmd)),
                "hyphenated first name must round-trip through cross-repo cd",
            )

    def test_cross_repo_vasquez_paredes_hyphenated_surname_allowed(self):
        """`cd <ingest-clone> && git -c user.name="Marcia Vasquez-Paredes" commit`."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {})
            child = outer / "noorinalabs-isnad-ingest-platform"
            child.mkdir()
            _git_init(child)
            _write_roster(
                child,
                {
                    "Marcia Vasquez-Paredes": "parametrization+Marcia.Vasquez-Paredes@gmail.com",
                },
            )
            cmd = (
                f'cd {child} && git -c user.name="Marcia Vasquez-Paredes" '
                f'-c user.email="parametrization+Marcia.Vasquez-Paredes@gmail.com" '
                f'commit -m "x"'
            )
            self.assertIsNone(
                hook.check(self._input(cmd)),
                "Spanish double-barrelled surname must round-trip through cross-repo cd",
            )

    def test_cross_repo_mensah_williams_hyphenated_surname_allowed(self):
        """`cd <ingest-clone> && git -c user.name="Kofi Mensah-Williams" commit`."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {})
            child = outer / "noorinalabs-isnad-ingest-platform"
            child.mkdir()
            _git_init(child)
            _write_roster(
                child,
                {
                    "Kofi Mensah-Williams": "parametrization+Kofi.Mensah-Williams@gmail.com",
                },
            )
            cmd = (
                f'cd {child} && git -c user.name="Kofi Mensah-Williams" '
                f'-c user.email="parametrization+Kofi.Mensah-Williams@gmail.com" '
                f'commit -m "x"'
            )
            self.assertIsNone(
                hook.check(self._input(cmd)),
                "West-African double-barrelled surname must round-trip through cross-repo cd",
            )

    def test_cross_repo_diop_sarr_hyphenated_surname_allowed(self):
        """`cd <ingest-clone> && git -c user.name="Anika Diop-Sarr" commit`."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {})
            child = outer / "noorinalabs-isnad-ingest-platform"
            child.mkdir()
            _git_init(child)
            _write_roster(
                child,
                {
                    "Anika Diop-Sarr": "parametrization+Anika.Diop-Sarr@gmail.com",
                },
            )
            cmd = (
                f'cd {child} && git -c user.name="Anika Diop-Sarr" '
                f'-c user.email="parametrization+Anika.Diop-Sarr@gmail.com" '
                f'commit -m "x"'
            )
            self.assertIsNone(
                hook.check(self._input(cmd)),
                "Senegalese double-barrelled surname must round-trip through cross-repo cd",
            )

    def test_cross_repo_design_system_maeve_callahan_allowed(self):
        """`cd <design-system-clone> && git -c user.name="Maeve Callahan" commit`.

        Pins `Maeve Callahan` (canonical design-system manager identity) as
        the expected name — NOT `Maeve O'Sullivan`. Apostrophe-in-name was
        considered for this fixture during issue triage but rejected: the
        design-system roster uses Callahan; adding an apostrophe fixture for
        a name no roster actually contains would misrepresent the spec.
        """
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {})
            child = outer / "noorinalabs-design-system"
            child.mkdir()
            _git_init(child)
            _write_roster(
                child,
                {"Maeve Callahan": "parametrization+Maeve.Callahan@gmail.com"},
            )
            cmd = (
                f'cd {child} && git -c user.name="Maeve Callahan" '
                f'-c user.email="parametrization+Maeve.Callahan@gmail.com" '
                f'commit -m "x"'
            )
            self.assertIsNone(
                hook.check(self._input(cmd)),
                "design-system manager Maeve Callahan must be accepted",
            )

    def test_cross_repo_hyphenated_wrong_email_blocks(self):
        """Cross-repo + hyphenated + email drops hyphen → block with mismatch reason.

        Combines the cross-repo `cd` codepath with a realistic typo (operator
        omits the hyphen from email local-part). Without this fixture, a
        future regression in `_detect_target_roster` could swap to the local
        roster (where the de-hyphenated email also doesn't match) and
        produce a misleading error message. By pinning the child-roster
        path explicitly, we ensure the block reason cites the CHILD roster
        expectation, not the parent.
        """
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {})
            child = outer / "noorinalabs-data-acquisition"
            child.mkdir()
            _git_init(child)
            _write_roster(
                child,
                {
                    "Jean-Claude Habimana": "parametrization+Jean-Claude.Habimana@gmail.com",
                },
            )
            wrong_email = "parametrization+JeanClaude.Habimana@gmail.com"
            cmd = (
                f'cd {child} && git -c user.name="Jean-Claude Habimana" '
                f'-c user.email="{wrong_email}" commit -m "x"'
            )
            result = hook.check(self._input(cmd))
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.get("decision"), "block")
            self.assertIn("does not match roster", result["reason"])
            self.assertIn("Jean-Claude.Habimana", result["reason"])


class IndirectExecBypassTests(unittest.TestCase):
    """Issue #475 fix 2: PreToolUse hooks only see the outer Bash command,
    so wrappers like `printf '…git commit…' | bash` and `bash <script>`
    hide the actual git invocation. Each shape below must BLOCK with the
    canonical-shape hint, and the matching innocent variant must ALLOW
    (the detector requires both `git` AND `commit` in the inner payload).
    """

    @staticmethod
    def _input(command: str, cwd: str | None = None) -> dict:
        d: dict = {"tool_name": "Bash", "tool_input": {"command": command}}
        if cwd is not None:
            d["cwd"] = cwd
        return d

    def _assert_blocked_as_indirect(self, result):
        self.assertIsNotNone(result, "indirect-exec bypass must block")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("indirect-exec", result["reason"])
        self.assertIn("#475", result["reason"])

    # --- printf | bash family ---------------------------------------------

    def test_printf_pipe_bash_with_git_commit_blocks(self):
        """POS: `printf '<git commit ...>' | bash` — the headline #475 repro."""
        cmd = (
            'printf \'git -c user.name="Bjørn Henriksen" '
            '-c user.email="..." commit -F /tmp/msg.txt\\n\' | bash'
        )
        self._assert_blocked_as_indirect(hook.check(self._input(cmd)))

    def test_printf_pipe_sh_with_git_commit_blocks(self):
        """POS: `printf '…' | sh` — sh is also a shell interpreter."""
        cmd = "printf 'git -c user.name=X -c user.email=Y commit -m z\\n' | sh"
        self._assert_blocked_as_indirect(hook.check(self._input(cmd)))

    def test_printf_pipe_zsh_with_git_commit_blocks(self):
        """POS: `printf '…' | zsh` — zsh is also a shell interpreter."""
        cmd = "printf 'git -c user.name=X -c user.email=Y commit -m z\\n' | zsh"
        self._assert_blocked_as_indirect(hook.check(self._input(cmd)))

    def test_echo_pipe_bash_with_git_commit_blocks(self):
        """POS: `echo '…git commit…' | bash` — same shape as printf."""
        cmd = 'echo "git -c user.name=X -c user.email=Y commit -m z" | bash'
        self._assert_blocked_as_indirect(hook.check(self._input(cmd)))

    def test_printf_pipe_bash_without_git_commit_allows(self):
        """NEG: `printf 'echo hello' | bash` — innocent pipe-to-shell.

        The detector requires `git` AND `commit` in the inner payload.
        This is the #475 acceptance bullet "printf 'echo hello' | bash → ALLOWED".
        """
        self.assertIsNone(hook.check(self._input("printf 'echo hello' | bash")))

    def test_echo_pipe_bash_without_git_commit_allows(self):
        """NEG: `echo ls | bash` — innocent pipe-to-shell."""
        self.assertIsNone(hook.check(self._input("echo ls | bash")))

    # --- shell -c family --------------------------------------------------

    def test_bash_dash_c_with_git_commit_blocks(self):
        """POS: `bash -c '…git commit…'` — direct -c invocation."""
        cmd = 'bash -c \'git -c user.name="X" -c user.email="Y" commit -m "z"\''
        self._assert_blocked_as_indirect(hook.check(self._input(cmd)))

    def test_sh_dash_c_with_git_commit_blocks(self):
        """POS: `sh -c '…git commit…'`."""
        cmd = "sh -c 'cd /repo && git -c user.name=X -c user.email=Y commit -m z'"
        self._assert_blocked_as_indirect(hook.check(self._input(cmd)))

    def test_bash_dash_c_double_quoted_payload_blocks(self):
        """POS: `bash -c "…git commit…"` — double-quoted payload form."""
        cmd = 'bash -c "git -c user.name=X -c user.email=Y commit -m z"'
        self._assert_blocked_as_indirect(hook.check(self._input(cmd)))

    def test_bash_dash_c_without_git_commit_allows(self):
        """NEG: `bash -c 'ls -la'` — innocent -c invocation."""
        self.assertIsNone(hook.check(self._input("bash -c 'ls -la'")))

    def test_bash_dash_c_with_git_but_no_commit_allows(self):
        """NEG: `bash -c 'git status'` — git, but not git commit."""
        self.assertIsNone(hook.check(self._input("bash -c 'git status'")))

    # --- bash <script> family ---------------------------------------------

    def test_bash_script_containing_git_commit_blocks(self):
        """POS: `bash /tmp/script.sh` where script content contains git commit.

        Script content is read from disk; if it matches the git-commit shape
        the wrapper is blocked. This closes the `bash <script-file>` bypass
        path explicitly called out in #475.
        """
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", delete=False, encoding="utf-8"
        ) as f:
            f.write('git -c user.name="X" -c user.email="Y" commit -F /tmp/msg.txt\n')
            script_path = f.name
        try:
            self._assert_blocked_as_indirect(hook.check(self._input(f"bash {script_path}")))
        finally:
            Path(script_path).unlink(missing_ok=True)

    def test_bash_script_without_git_commit_allows(self):
        """NEG: `bash some-script.sh` whose content does NOT contain git commit.

        #475 acceptance bullet: "Plain bash some-script.sh where the script
        does NOT contain git commit → ALLOWED".
        """
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", delete=False, encoding="utf-8"
        ) as f:
            f.write("#!/usr/bin/env bash\nls -la\necho done\n")
            script_path = f.name
        try:
            self.assertIsNone(hook.check(self._input(f"bash {script_path}")))
        finally:
            Path(script_path).unlink(missing_ok=True)

    def test_bash_script_unreadable_allows(self):
        """NEG: `bash /nonexistent/path.sh` — unreadable script. Allow rather
        than block on disk errors; the operator will get a real shell error
        immediately when bash tries to execute the missing file."""
        self.assertIsNone(hook.check(self._input("bash /nonexistent/never/exists.sh")))

    # --- process substitution ---------------------------------------------

    def test_bash_process_sub_with_git_commit_blocks(self):
        """POS: `bash <(echo '…git commit…')` — process substitution bypass."""
        cmd = 'bash <(echo "git -c user.name=X -c user.email=Y commit -m z")'
        self._assert_blocked_as_indirect(hook.check(self._input(cmd)))

    def test_bash_process_sub_without_git_commit_allows(self):
        """NEG: `bash <(echo "ls -la")` — innocent process substitution."""
        self.assertIsNone(hook.check(self._input('bash <(echo "ls -la")')))

    # --- bare interpreter and pass-through cases --------------------------

    def test_plain_bash_no_args_allows(self):
        """NEG: bare `bash` (interactive shell) — no inline cmd to inspect.

        #475 acceptance bullet: "Plain bash (interactive shell) with no
        inline cmd → ALLOWED (no git commit detected)".
        """
        self.assertIsNone(hook.check(self._input("bash")))

    def test_direct_git_commit_still_validates_identity(self):
        """NEG/regression: a direct `git -c ... commit` is still validated
        through the existing parser — must allow when identity is valid.

        #475 acceptance bullet: existing behavior preserved (still allowed
        because identity flags present + roster name valid).
        """
        valid_name = next(iter(hook.ROSTER), None)
        if not valid_name:
            self.skipTest("local roster is empty")
        valid_email = hook.ROSTER[valid_name]
        cmd = (
            f'git -c user.name="{valid_name}" -c user.email="{valid_email}" commit -F /tmp/msg.txt'
        )
        self.assertIsNone(hook.check(self._input(cmd)))

    def test_direct_git_commit_missing_identity_still_blocks(self):
        """NEG/regression: `git commit -m msg` (no identity flags) still blocks.

        #475 acceptance bullet: existing behavior preserved (BLOCKED — current
        rule). Indirect-exec detection must not bypass the existing
        identity-validation path for direct invocations.
        """
        result = hook.check(self._input('git commit -m "x"'))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        # Should be the missing-name block, not the indirect-exec block.
        self.assertNotIn("indirect-exec", result["reason"])
        self.assertIn("user.name", result["reason"])

    # --- cross-check: indirect-exec runs BEFORE segment parser ------------

    def test_indirect_wrapper_wins_over_outer_innocent_commit_pattern(self):
        """POS: a command that BOTH has an outer non-commit shape AND an
        inner-via-wrapper git commit blocks on the wrapper, not silently
        allows. Otherwise the wrapper detection is structurally redundant
        with the existing parser."""
        # Outer command does not contain a real `git commit` at the
        # tokenize level (just `printf` and `bash`); inner payload does.
        cmd = "printf 'git -c user.name=X -c user.email=Y commit -m z\\n' | bash"
        result = hook.check(self._input(cmd))
        assert result is not None
        self.assertIn("indirect-exec", result["reason"])


class IndirectExecExtensionTests(unittest.TestCase):
    """Issue #482: extend indirect-exec detection from the original 4 shapes
    (#475) to 5 more — heredoc, here-string, eval, dash/ksh -c (via the
    widened `_INTERPRETERS` alternation), and extension-agnostic script
    read (the highest-severity #482 change, since operators could trivially
    rename a bypass script to circumvent the prior `.sh\\b` restriction).

    Each new shape gets a paired BLOCK / ALLOW test to pin both halves of
    the detection contract:
      - BLOCK: inner payload contains git-commit-shape
      - ALLOW: same wrapper shape but inner payload is innocent

    All existing 46 tests in this file continue to pass — the extensions
    are strictly additive to `_detect_indirect_commit`'s dispatcher.
    """

    @staticmethod
    def _input(command: str, cwd: str | None = None) -> dict:
        d: dict = {"tool_name": "Bash", "tool_input": {"command": command}}
        if cwd is not None:
            d["cwd"] = cwd
        return d

    def _assert_blocked_with_shape(self, result, shape_label: str) -> None:
        """Assert the result is an indirect-exec block and the reason
        contains the expected shape label (e.g. 'heredoc', 'here-string').
        Also asserts the unified #475/#482 cite is present."""
        self.assertIsNotNone(result, f"indirect-exec bypass must block ({shape_label})")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("indirect-exec", result["reason"])
        self.assertIn(shape_label, result["reason"])
        # Both citations should be present in the unified post-#482 block message.
        self.assertIn("#475", result["reason"])
        self.assertIn("#482", result["reason"])

    # --- heredoc shape -----------------------------------------------------

    def test_bash_heredoc_with_git_commit_blocks(self):
        """POS: `bash <<EOF\\ngit commit ...\\nEOF` — heredoc body fed as
        stdin to a shell. Without #482 detection the outer tokenizer sees
        only `['bash', '<<EOF', '...', 'EOF']`-style decomposition and
        `_find_commit_segment` returns None → silent allow."""
        cmd = 'bash <<EOF\ngit -c user.name="X" -c user.email="Y" commit -F /tmp/msg.txt\nEOF'
        self._assert_blocked_with_shape(hook.check(self._input(cmd)), "heredoc")

    def test_bash_heredoc_quoted_delim_with_git_commit_blocks(self):
        """POS: `bash <<'EOF'...` — quoted-delim heredoc (no var expansion).
        Same exec semantics; detector must match this variant too."""
        cmd = 'bash <<\'EOF\'\ngit -c user.name="X" -c user.email="Y" commit -m z\nEOF'
        self._assert_blocked_with_shape(hook.check(self._input(cmd)), "heredoc")

    def test_bash_heredoc_dash_form_with_git_commit_blocks(self):
        """POS: `bash <<-EOF...` — tab-stripping heredoc form."""
        cmd = "bash <<-EOF\n\tgit -c user.name=X -c user.email=Y commit -m z\n\tEOF"
        self._assert_blocked_with_shape(hook.check(self._input(cmd)), "heredoc")

    def test_bash_heredoc_no_git_commit_allows(self):
        """NEG: `bash <<EOF\\necho hi\\nEOF` — innocent heredoc body."""
        cmd = "bash <<EOF\necho hello\nls -la\nEOF"
        self.assertIsNone(hook.check(self._input(cmd)))

    def test_cat_heredoc_mentioning_git_commit_allows(self):
        """NEG: `cat <<EOF\\ngit commit is a phrase\\nEOF` — `cat` is NOT
        a shell interpreter so the heredoc body is data, not code. Must
        not false-block. This is the principal false-positive guard for
        heredoc detection — prose containing 'git commit' inside a doc
        being piped to `cat` (or `tee`, `bat`, etc.) is everywhere."""
        cmd = "cat <<EOF > /tmp/doc.md\nHow to git commit:\ngit commit -m foo\nEOF"
        self.assertIsNone(hook.check(self._input(cmd)))

    # --- here-string shape -------------------------------------------------

    def test_bash_herestring_with_git_commit_blocks(self):
        """POS: `bash <<<'git commit ...'` — here-string body."""
        cmd = "bash <<<'git -c user.name=X -c user.email=Y commit -m z'"
        self._assert_blocked_with_shape(hook.check(self._input(cmd)), "here-string")

    def test_bash_herestring_double_quoted_with_git_commit_blocks(self):
        """POS: `bash <<<"..."` — double-quoted here-string."""
        cmd = 'bash <<<"git -c user.name=X -c user.email=Y commit -m z"'
        self._assert_blocked_with_shape(hook.check(self._input(cmd)), "here-string")

    def test_bash_herestring_no_git_commit_allows(self):
        """NEG: `bash <<<'echo hi'` — innocent here-string."""
        self.assertIsNone(hook.check(self._input("bash <<<'echo hello'")))

    def test_cat_herestring_mentioning_git_commit_allows(self):
        """NEG: `cat <<<'git commit is a phrase'` — `cat` is not a shell;
        body is data not code. Must not false-block."""
        self.assertIsNone(hook.check(self._input("cat <<<'git commit is a phrase'")))

    # --- eval shape --------------------------------------------------------

    def test_eval_with_git_commit_blocks(self):
        """POS: `eval 'git commit ...'` — shell builtin re-parses and
        executes its argument. Outer tokenizer sees `eval` as argv[0]
        and skips identity validation."""
        cmd = "eval 'git -c user.name=X -c user.email=Y commit -m foo'"
        self._assert_blocked_with_shape(hook.check(self._input(cmd)), "eval")

    def test_eval_double_quoted_payload_blocks(self):
        """POS: `eval "git commit ..."` — double-quoted payload form."""
        cmd = 'eval "git -c user.name=X -c user.email=Y commit -m foo"'
        self._assert_blocked_with_shape(hook.check(self._input(cmd)), "eval")

    def test_eval_no_git_commit_allows(self):
        """NEG: `eval 'echo hello'` — innocent eval."""
        self.assertIsNone(hook.check(self._input("eval 'echo hello'")))

    def test_eval_variable_substitution_documented_punt(self):
        """NEG: `eval "$CMD"` — variable-substituted eval body. Documented
        punt per the hook docstring: substitution happens at shell-runtime,
        after the hook fires, so we can't inspect the actual command. Must
        ALLOW (otherwise every legitimate `eval $cmd` use would false-block)."""
        self.assertIsNone(hook.check(self._input('eval "$CMD"')))
        self.assertIsNone(hook.check(self._input("eval $cmd")))

    def test_eval_no_quotes_no_commit_allows(self):
        """NEG: `eval echo hello` — bareword eval, no commit shape."""
        self.assertIsNone(hook.check(self._input("eval echo hello")))

    # --- dash / ksh extended interpreter alternation -----------------------

    def test_dash_dash_c_with_git_commit_blocks(self):
        """POS: `dash -c 'git commit ...'` — `dash` is a POSIX shell.
        Pre-#482 `_INTERPRETERS` was `(?:bash|sh|zsh)` and missed dash;
        #482 extended to `(?:bash|sh|zsh|dash|ksh)`."""
        cmd = "dash -c 'git -c user.name=X -c user.email=Y commit -m z'"
        self._assert_blocked_with_shape(hook.check(self._input(cmd)), "shell -c")

    def test_ksh_dash_c_with_git_commit_blocks(self):
        """POS: `ksh -c 'git commit ...'` — Korn shell, also POSIX."""
        cmd = "ksh -c 'git -c user.name=X -c user.email=Y commit -m z'"
        self._assert_blocked_with_shape(hook.check(self._input(cmd)), "shell -c")

    def test_dash_dash_c_no_git_commit_allows(self):
        """NEG: `dash -c 'ls -la'` — innocent dash invocation."""
        self.assertIsNone(hook.check(self._input("dash -c 'ls -la'")))

    def test_dash_piped_with_git_commit_blocks(self):
        """POS: `printf '...' | dash` — pipe-to-shell with dash interpreter."""
        cmd = "printf 'git -c user.name=X -c user.email=Y commit -m z\\n' | dash"
        self._assert_blocked_with_shape(hook.check(self._input(cmd)), "printf/echo piped to shell")

    def test_ksh_piped_with_git_commit_blocks(self):
        """POS: `echo '...' | ksh` — same with ksh."""
        cmd = "echo 'git -c user.name=X -c user.email=Y commit -m z' | ksh"
        self._assert_blocked_with_shape(hook.check(self._input(cmd)), "printf/echo piped to shell")

    # --- extension-agnostic script read (highest-severity #482 fix) -------

    def test_bash_script_dot_bash_extension_blocks(self):
        """POS: `bash /tmp/script.bash` — .bash extension was NOT covered
        by the pre-#482 `\\.sh\\b` restriction. Now extension-agnostic,
        any readable file under the 256 KiB cap is inspected."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".bash", delete=False, encoding="utf-8"
        ) as f:
            f.write('git -c user.name="X" -c user.email="Y" commit -F /tmp/msg.txt\n')
            script_path = f.name
        try:
            self._assert_blocked_with_shape(
                hook.check(self._input(f"bash {script_path}")),
                "shell script",
            )
        finally:
            Path(script_path).unlink(missing_ok=True)

    def test_bash_script_extensionless_blocks(self):
        """POS: `bash /tmp/script-no-ext` — completely extensionless. The
        rename-bypass that was the highest-severity #482 concern: an
        operator who knew the hook checked `.sh` could rename their
        bypass script to `myscript` and slip through. Now blocked."""
        with tempfile.NamedTemporaryFile(mode="w", suffix="", delete=False, encoding="utf-8") as f:
            f.write('git -c user.name="X" -c user.email="Y" commit -F /tmp/msg.txt\n')
            script_path = f.name
        try:
            self._assert_blocked_with_shape(
                hook.check(self._input(f"bash {script_path}")),
                "shell script",
            )
        finally:
            Path(script_path).unlink(missing_ok=True)

    def test_bash_script_unusual_extension_blocks(self):
        """POS: `bash /tmp/script.ksh` — unusual extension. Content read
        is unconditional on extension; the cap + fail-open OSError discipline
        is preserved from the prior `.sh\\b`-restricted detector."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ksh", delete=False, encoding="utf-8"
        ) as f:
            f.write("git -c user.name=X -c user.email=Y commit -m z\n")
            script_path = f.name
        try:
            self._assert_blocked_with_shape(
                hook.check(self._input(f"bash {script_path}")),
                "shell script",
            )
        finally:
            Path(script_path).unlink(missing_ok=True)

    def test_bash_extensionless_script_no_git_commit_allows(self):
        """NEG: `bash /tmp/script` where content has NO git commit.
        Detection should still try to read (extension-agnostic), find
        nothing matching, and allow."""
        with tempfile.NamedTemporaryFile(mode="w", suffix="", delete=False, encoding="utf-8") as f:
            f.write("#!/usr/bin/env bash\nls -la\necho done\n")
            script_path = f.name
        try:
            self.assertIsNone(hook.check(self._input(f"bash {script_path}")))
        finally:
            Path(script_path).unlink(missing_ok=True)

    def test_bash_script_dash_c_does_not_false_match_as_script(self):
        """NEG/regression: `bash -c '...'` must continue to match as
        `shell -c`, NOT as a script-path read. The script regex's leading
        char class excludes `-`, so `-c` is correctly skipped."""
        cmd = "bash -c 'git -c user.name=X -c user.email=Y commit -m foo'"
        result = hook.check(self._input(cmd))
        assert result is not None
        # Should be matched by the shell -c detector, not the script detector
        self.assertIn("shell -c", result["reason"])
        # Should NOT have script-shape language in the reason
        self.assertNotIn("shell script", result["reason"])

    def test_bash_script_with_size_cap_still_protected(self):
        """NEG (defensive): a script file >256 KiB is NOT inspected
        (preserves the original #475 fail-open-on-large-file discipline).
        If the script content contains a git commit shape but the file
        exceeds the cap, the detector returns None and the rest of the
        hook handles it normally (ALLOW since outer-command tokenizer
        sees `bash <path>`, not git)."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".bash", delete=False, encoding="utf-8"
        ) as f:
            # Write >256 KiB of padding followed by git commit text
            f.write("# padding\n" * 30000)  # ~300 KiB
            f.write('git -c user.name="X" -c user.email="Y" commit -m z\n')
            script_path = f.name
        try:
            self.assertIsNone(
                hook.check(self._input(f"bash {script_path}")),
                "files >256 KiB must not be inspected (preserves fail-open discipline)",
            )
        finally:
            Path(script_path).unlink(missing_ok=True)

    # --- cross-shape coherence --------------------------------------------

    def test_unified_block_message_cites_both_issues(self):
        """POS: the post-#482 block message MUST cite both #475 (original
        4-shape work) AND #482 (5-shape extension) so operators landing
        on the message can trace the full bypass surface."""
        result = hook.check(self._input("eval 'git -c user.name=X commit -m z'"))
        assert result is not None
        self.assertIn("#475", result["reason"])
        self.assertIn("#482", result["reason"])

    def test_block_message_lists_new_shapes(self):
        """POS: the wrapper-list in the block message MUST include the
        new shape examples so the operator sees them inline. Helps prevent
        operators from re-discovering bypass patterns by trial."""
        result = hook.check(self._input("eval 'git -c user.name=X commit -m z'"))
        assert result is not None
        # New #482 shapes named in the unified message
        self.assertIn("<<EOF", result["reason"])
        self.assertIn("<<<", result["reason"])
        self.assertIn("eval", result["reason"])


class CwdFallbackTests(unittest.TestCase):
    """Issue #475 fix 1: when no literal `cd <path>` prefix is present, fall
    back to the tool-call cwd for roster resolution. Lets operators commit
    from within a child-repo worktree without composing a `cd` prefix."""

    def test_cwd_fallback_loads_child_roster(self):
        """`git -c user.name=<child-only-name> ... commit` from inside the
        child worktree (no `cd` prefix) validates against the child roster."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {"Nadia": "nadia@example.com"})
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            detected = hook._detect_target_roster("git commit -m 'x'", cwd=str(child))
            self.assertIsNotNone(detected)
            assert detected is not None
            self.assertEqual(
                detected,
                {
                    "Nadia": "nadia@example.com",
                    "Alice": "alice@example.com",
                },
            )

    def test_cwd_fallback_when_no_roster_returns_none(self):
        """cwd has no roster.json → return None (caller uses local ROSTER)."""
        with tempfile.TemporaryDirectory() as td:
            empty = Path(td) / "no_roster"
            empty.mkdir()
            self.assertIsNone(hook._detect_target_roster("git commit -m 'x'", cwd=str(empty)))

    def test_cd_prefix_wins_over_cwd_fallback(self):
        """Explicit `cd <path>` in the command takes priority over cwd."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            cd_target = outer / "explicit"
            cd_target.mkdir()
            _git_init(cd_target)
            _write_roster(cd_target, {"Explicit": "explicit@example.com"})

            # Different repo for the cwd-fallback; should be ignored.
            cwd_target = outer / "cwd_only"
            cwd_target.mkdir()
            _git_init(cwd_target)
            _write_roster(cwd_target, {"FromCwd": "cwd@example.com"})

            detected = hook._detect_target_roster(
                f"cd {cd_target} && git commit -m 'x'",
                cwd=str(cwd_target),
            )
            assert detected is not None
            self.assertIn("Explicit", detected)
            self.assertNotIn("FromCwd", detected)

    def test_no_cd_no_cwd_returns_none(self):
        """Regression: omitting both still returns None (existing contract)."""
        self.assertIsNone(hook._detect_target_roster("git commit -m 'x'"))

    def test_check_uses_cwd_fallback_to_accept_child_only_name(self):
        """Integration: `check()` with a child-only roster name + cwd
        pointing at the child repo (no `cd` prefix) → ALLOWED.

        Previously this BLOCKED because `_detect_target_roster` returned
        None without a cd prefix, the local ROSTER was used, and the
        child-only name failed lookup. Fix 1 makes the cwd the fallback
        anchor, restoring symmetry with the cd-prefix path.
        """
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {"Nadia": "nadia@example.com"})
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            cmd = 'git -c user.name="Alice" -c user.email="alice@example.com" commit -m "x"'
            result = hook.check(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": cmd},
                    "cwd": str(child),
                }
            )
            self.assertIsNone(result, f"expected allow, got block: {result}")


if __name__ == "__main__":
    unittest.main()
