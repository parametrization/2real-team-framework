"""Tests for doc_freshness — the advisory PR-time doc-freshness gate (#768).

Verifies the pure decision core (no git): surface firing, status scoping
(new-module rules fire on A, not M), doc-satisfaction, opt-out detection,
rename folding, and that the CLI always exits 0 (advisory).
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doc_freshness import (  # noqa: E402
    Surface,
    _normalize_status,
    evaluate,
    has_opt_out,
    main,
    render,
)

_RULES = (
    Surface(
        name="new-module",
        code=(r"^\.claude/(hooks|lib)/[^/]+\.py$",),
        docs=(r"^ontology/conventions\.md$", r"^docs/TOOLCHAIN\.md$"),
        hint="register it",
        statuses=frozenset({"A"}),
    ),
    Surface(
        name="ci-topology",
        code=(r"^\.github/workflows/.*\.ya?ml$", r"^\.pre-commit-config\.yaml$"),
        docs=(r"^CLAUDE\.md$", r"^ontology/conventions\.md$"),
        hint="reflect it",
    ),
)


class StatusNormalization(unittest.TestCase):
    def test_plain_codes(self) -> None:
        self.assertEqual(_normalize_status("A"), "A")
        self.assertEqual(_normalize_status("M"), "M")
        self.assertEqual(_normalize_status("D"), "D")

    def test_rename_and_copy_fold_to_m(self) -> None:
        self.assertEqual(_normalize_status("R100"), "M")
        self.assertEqual(_normalize_status("C075"), "M")

    def test_empty(self) -> None:
        self.assertEqual(_normalize_status(""), "")


class SurfaceFiring(unittest.TestCase):
    def test_new_module_without_doc_fires(self) -> None:
        findings = evaluate([("A", ".claude/lib/foo.py")], _RULES)
        names = {f.surface for f in findings}
        self.assertIn("new-module", names)

    def test_new_module_with_conventions_update_is_satisfied(self) -> None:
        findings = evaluate(
            [("A", ".claude/lib/foo.py"), ("M", "ontology/conventions.md")],
            _RULES,
        )
        self.assertNotIn("new-module", {f.surface for f in findings})

    def test_modified_module_does_not_fire_new_module_rule(self) -> None:
        # Status M on an existing module must NOT trip the A-scoped rule.
        findings = evaluate([("M", ".claude/lib/foo.py")], _RULES)
        self.assertNotIn("new-module", {f.surface for f in findings})

    def test_test_file_in_subdir_does_not_fire(self) -> None:
        # .claude/lib/tests/x.py has a `/tests/` segment, so [^/]+ excludes it.
        findings = evaluate([("A", ".claude/lib/tests/test_x.py")], _RULES)
        self.assertEqual(findings, [])

    def test_ci_topology_fires_on_modify(self) -> None:
        findings = evaluate([("M", ".github/workflows/ci.yml")], _RULES)
        self.assertIn("ci-topology", {f.surface for f in findings})

    def test_ci_topology_satisfied_by_claude_md(self) -> None:
        findings = evaluate([("M", ".github/workflows/ci.yml"), ("M", "CLAUDE.md")], _RULES)
        self.assertNotIn("ci-topology", {f.surface for f in findings})

    def test_precommit_change_fires_ci_topology(self) -> None:
        findings = evaluate([("M", ".pre-commit-config.yaml")], _RULES)
        self.assertIn("ci-topology", {f.surface for f in findings})

    def test_unrelated_change_no_findings(self) -> None:
        self.assertEqual(evaluate([("M", "README.md")], _RULES), [])

    def test_finding_carries_code_paths_and_docs(self) -> None:
        findings = evaluate([("A", ".claude/hooks/bar.py")], _RULES)
        f = next(x for x in findings if x.surface == "new-module")
        self.assertIn(".claude/hooks/bar.py", f.code_paths)
        # expected_docs carries the rule's doc patterns verbatim.
        self.assertIn(r"^ontology/conventions\.md$", f.expected_docs)


class OptOut(unittest.TestCase):
    def test_docs_na_marker(self) -> None:
        self.assertTrue(has_opt_out(["chore: refactor\n\nDocs-N/A: pure rename"]))

    def test_skip_token_case_insensitive(self) -> None:
        self.assertTrue(has_opt_out(["fix bug\n\nSKIP-DOC-CHECK: trivial"]))

    def test_no_marker(self) -> None:
        self.assertFalse(has_opt_out(["feat: add a hook"]))

    def test_bare_token_without_colon_is_not_optout(self) -> None:
        # Prose that merely NAMES the marker must not self-trigger the opt-out —
        # the colon is required. This is the footgun the colon form closes (a
        # commit that documents the gate mentions "Docs-N/A" / "[skip-doc-check]").
        self.assertFalse(
            has_opt_out(["docs: explain the Docs-N/A and [skip-doc-check] opt-out markers"])
        )

    def test_empty(self) -> None:
        self.assertFalse(has_opt_out([]))


class Render(unittest.TestCase):
    def test_clean_message_when_no_findings(self) -> None:
        self.assertIn("no documented code surface", render([]))

    def test_report_lists_surface_and_optout_hint(self) -> None:
        out = render(evaluate([("A", ".claude/lib/foo.py")], _RULES))
        self.assertIn("new-module", out)
        self.assertIn("Docs-N/A", out)


class CliAlwaysExitsZero(unittest.TestCase):
    def test_injected_findings_exit_zero(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["doc_freshness.py", "--changed", "A:.claude/lib/foo.py"])
        self.assertEqual(rc, 0)

    def test_injected_optout_exit_zero_and_skips(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(
                [
                    "doc_freshness.py",
                    "--changed",
                    "A:.claude/lib/foo.py",
                    "--opt-out-text",
                    "Docs-N/A: scaffolding only",
                ]
            )
        self.assertEqual(rc, 0)
        self.assertIn("opt-out", buf.getvalue())


class RealRules(unittest.TestCase):
    """The shipped SURFACE_RULES classify this repo's own paths sensibly."""

    def test_real_rules_fire_on_new_lib_without_doc(self) -> None:
        from doc_freshness import SURFACE_RULES

        findings = evaluate([("A", ".claude/lib/doc_freshness.py")], SURFACE_RULES)
        self.assertIn("new-org-hook-or-lib-module", {f.surface for f in findings})

    def test_real_rules_satisfied_when_conventions_also_changed(self) -> None:
        from doc_freshness import SURFACE_RULES

        findings = evaluate(
            [
                ("A", ".claude/lib/doc_freshness.py"),
                ("M", "ontology/conventions.md"),
            ],
            SURFACE_RULES,
        )
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
