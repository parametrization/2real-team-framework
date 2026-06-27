"""Tests for lint_skill_graphql_pagination — the GraphQL `first: > 100` guard (#888).

Verifies the lint flags an over-cap `first:` inside a `gh api graphql` code block, treats
`first: 100` (the legal maximum) and small inner connections as compliant, and ignores a
`first:` that appears outside a GraphQL recipe block.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lint_skill_graphql_pagination import (  # noqa: E402
    check_markdown_text,
    main,
)

_GRAPHQL_BLOCK = """### Step 2

```bash
gh api graphql -f query='
query {{
  organization(login: "noorinalabs") {{
    projectV2(number: 2) {{
      items(first: {n}) {{
        nodes {{ id }}
      }}
    }}
  }}
}}'
```
"""


class OverCapIsFlagged(unittest.TestCase):
    def test_first_500_in_graphql_block_flagged(self) -> None:
        v = check_markdown_text("SKILL.md", _GRAPHQL_BLOCK.format(n=500))
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0].value, 500)
        # Line points at the `items(first: 500)` line inside the fenced block.
        self.assertEqual(v[0].lineno, 8)

    def test_first_101_is_over_cap(self) -> None:
        v = check_markdown_text("SKILL.md", _GRAPHQL_BLOCK.format(n=101))
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0].value, 101)

    def test_first_1394_flagged(self) -> None:
        v = check_markdown_text("SKILL.md", _GRAPHQL_BLOCK.format(n=1394))
        self.assertEqual(len(v), 1)


class CompliantIsNotFlagged(unittest.TestCase):
    def test_first_100_is_the_legal_max(self) -> None:
        self.assertEqual(check_markdown_text("SKILL.md", _GRAPHQL_BLOCK.format(n=100)), [])

    def test_small_inner_connection_ok(self) -> None:
        self.assertEqual(check_markdown_text("SKILL.md", _GRAPHQL_BLOCK.format(n=30)), [])

    def test_paginated_block_with_first_100_and_inner_30(self) -> None:
        md = """```bash
gh api graphql --paginate -f query='
query($endCursor: String) {
  organization(login: "noorinalabs") {
    projectV2(number: 2) {
      items(first: 100, after: $endCursor) {
        pageInfo { hasNextPage endCursor }
        nodes { fieldValues(first: 30) { nodes { id } } }
      }
    }
  }
}'
```
"""
        self.assertEqual(check_markdown_text("SKILL.md", md), [])

    def test_first_500_outside_graphql_block_ignored(self) -> None:
        # A `first: 500` in a non-GraphQL recipe (no `gh api graphql`) is out of scope.
        md = """```bash
gh issue list --repo noorinalabs/x --limit 500 --json url
echo "first: 500 widgets"
```
"""
        self.assertEqual(check_markdown_text("SKILL.md", md), [])

    def test_first_500_in_prose_outside_any_block_ignored(self) -> None:
        md = "Some prose mentioning items(first: 500) but no code block.\n"
        self.assertEqual(check_markdown_text("SKILL.md", md), [])


class MultipleAndUnterminated(unittest.TestCase):
    def test_two_over_cap_in_one_block(self) -> None:
        md = """```bash
gh api graphql -f query='query { a(first: 200) { b(first: 300) { id } } }'
```
"""
        v = check_markdown_text("SKILL.md", md)
        self.assertEqual([x.value for x in v], [200, 300])

    def test_unterminated_block_scanned_to_eof(self) -> None:
        md = "```bash\ngh api graphql -f query='query { a(first: 500) { id } }'\n"
        v = check_markdown_text("SKILL.md", md)
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0].value, 500)


class CliExitCodes(unittest.TestCase):
    def test_usage_error_no_args(self) -> None:
        self.assertEqual(main(["lint_skill_graphql_pagination.py"]), 2)

    def test_missing_file_errors(self) -> None:
        self.assertEqual(main(["lint_skill_graphql_pagination.py", "/no/such/file.md"]), 2)

    def test_clean_file_passes(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
            fh.write(_GRAPHQL_BLOCK.format(n=100))
            name = fh.name
        try:
            self.assertEqual(main(["lint_skill_graphql_pagination.py", name]), 0)
        finally:
            Path(name).unlink()

    def test_violating_file_returns_1(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
            fh.write(_GRAPHQL_BLOCK.format(n=500))
            name = fh.name
        try:
            self.assertEqual(main(["lint_skill_graphql_pagination.py", name]), 1)
        finally:
            Path(name).unlink()

    def test_real_skill_file_is_clean(self) -> None:
        # The board-audit skill must itself be free of the over-cap after the #888 fix.
        repo_root = Path(__file__).resolve().parents[3]
        skill = repo_root / ".claude" / "skills" / "board-audit" / "SKILL.md"
        if skill.is_file():
            self.assertEqual(main(["lint_skill_graphql_pagination.py", str(skill)]), 0)


if __name__ == "__main__":
    unittest.main()
