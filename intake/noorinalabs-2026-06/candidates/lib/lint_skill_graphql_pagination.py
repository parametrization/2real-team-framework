#!/usr/bin/env python3
"""Lint skill markdown for the GraphQL `first: > 100` over-cap footgun.

GitHub's GraphQL API caps every *connection* `first:` at **100** — a query that asks
for more (e.g. `items(first: 500)`) errors with *"Requesting 500 records on the
connection exceeds the `first` limit of 100 records"* and returns **zero** rows. In
`/board-audit` (noorinalabs-main#888) that silent zero read as "every issue is an
orphan". The fix is always cursor pagination (`first: 100` + `pageInfo`/`$endCursor` +
`--paginate`); this lint is the cheap regression guard the issue asked for.

What it flags
=============
Inside any fenced code block that contains a `gh api graphql` invocation, any
`first: <n>` whose integer value is **strictly greater than 100**. `first: 100` is the
legal maximum and is NOT flagged; `first: 30` (e.g. a small inner `fieldValues`
connection) is fine. Restricting to `gh api graphql` blocks avoids flagging an unrelated
`first:` that happens to appear in prose or a non-GraphQL recipe.

Today only `.claude/skills/board-audit/SKILL.md` is in scope; the lint exists so a future
skill author can't reintroduce the over-cap.

CLI
===
    python3 .claude/lib/lint_skill_graphql_pagination.py <file.md> [<file.md> ...]

Glob over the skills tree (zsh recursive glob; bash needs `shopt -s globstar`):

    python3 .claude/lib/lint_skill_graphql_pagination.py .claude/skills/**/*.md

Exit codes:
    0 — no over-cap `first:` found in any file
    1 — at least one violation (each printed as `path:line: first: <n> — <why>`)
    2 — usage / file-not-found error

Same CLI/exit-code shape as `.claude/lib/check_dockerfile_base_pin.py` so it wires
identically into pre-commit + CI when promoted to a blocking gate (a #888 follow-up).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# A fenced code block opens/closes on a line that is only a ``` (optionally with an info
# string like ```bash). We track open/close to scope the scan to code, not prose.
_FENCE_RE = re.compile(r"^\s*```")
# `gh api graphql` anywhere in the block marks it as a GraphQL recipe.
_GRAPHQL_RE = re.compile(r"\bgh\s+api\s+graphql\b")
# `first:` followed by an integer literal — capture the number to compare numerically.
_FIRST_RE = re.compile(r"\bfirst:\s*(\d+)")

CONNECTION_CAP = 100


class Violation:
    """One over-cap `first:` occurrence."""

    def __init__(self, path: str, lineno: int, value: int) -> None:
        self.path = path
        self.lineno = lineno
        self.value = value

    def __str__(self) -> str:
        return (
            f"{self.path}:{self.lineno}: first: {self.value} — exceeds the GraphQL "
            f"connection cap of {CONNECTION_CAP}; use first: 100 + cursor pagination "
            f"(pageInfo/endCursor + --paginate)"
        )


def check_markdown_text(path: str, text: str) -> list[Violation]:
    """Return over-cap `first:` violations inside `gh api graphql` code blocks."""
    violations: list[Violation] = []
    lines = text.splitlines()

    in_block = False
    block_start = 0  # 0-based index of the first content line of the open block
    for idx, raw in enumerate(lines):
        if _FENCE_RE.match(raw):
            if not in_block:
                in_block = True
                block_start = idx + 1
            else:
                # Block closed — scan it if it was a GraphQL recipe.
                block_lines = lines[block_start:idx]
                violations.extend(_scan_block(path, block_start, block_lines))
                in_block = False
    # An unterminated block (no closing fence) still gets scanned to EOF.
    if in_block:
        block_lines = lines[block_start:]
        violations.extend(_scan_block(path, block_start, block_lines))

    return violations


def _scan_block(path: str, start_idx: int, block_lines: list[str]) -> list[Violation]:
    """Scan one fenced block; flag over-cap `first:` only if it is a GraphQL recipe."""
    block_text = "\n".join(block_lines)
    if not _GRAPHQL_RE.search(block_text):
        return []
    found: list[Violation] = []
    for offset, line in enumerate(block_lines):
        for m in _FIRST_RE.finditer(line):
            value = int(m.group(1))
            if value > CONNECTION_CAP:
                # start_idx is 0-based content start; +offset for the line, +1 to 1-base.
                found.append(Violation(path, start_idx + offset + 1, value))
    return found


def check_file(path: Path) -> list[Violation]:
    return check_markdown_text(str(path), path.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    paths = argv[1:]
    if not paths:
        print(
            "usage: lint_skill_graphql_pagination.py <file.md> [<file.md> ...]",
            file=sys.stderr,
        )
        return 2

    all_violations: list[Violation] = []
    for p in paths:
        path = Path(p)
        if not path.is_file():
            print(f"ERROR: not a file: {p}", file=sys.stderr)
            return 2
        all_violations.extend(check_file(path))

    if all_violations:
        print("GraphQL connection over-cap violations (first: > 100, noorinalabs-main#888):")
        for v in all_violations:
            print(f"  {v}")
        print(
            "\nGraphQL connections cap first: at 100. Page with first: 100 + "
            "pageInfo { hasNextPage endCursor } + a $endCursor var + gh api graphql "
            "--paginate, then merge pages with jq -s."
        )
        return 1

    print("OK: no GraphQL connection over-cap (first: > 100) found.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
