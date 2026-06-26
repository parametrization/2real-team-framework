# Generic Lib Prompt: Markdown Code-Block API-Cap Lint (GraphQL `first:` over-cap)

## Purpose

Catch a specific silent-failure footgun in documentation/recipe markdown: a
GraphQL **connection** `first:` argument greater than the API's hard cap of
**100**. A query that asks for more (`items(first: 500)`) doesn't truncate — it
**errors and returns zero rows**. When such a recipe lives in a skill/runbook that
an agent executes, that silent zero is read as a real (empty) result — e.g. "every
item is an orphan." The fix is always cursor pagination (`first: 100` +
`pageInfo`/`endCursor` + `--paginate`); this lint is the cheap regression guard.

More generally: this is a template for **linting embedded code recipes in markdown
for a known API limit**, scoping the scan to the relevant fenced blocks so prose
mentions don't false-trigger.

## Reusable Pattern

- **Track fenced code blocks** (open/close on a ``` line) so the scan is scoped to
  code, not prose. Scan an unterminated trailing block to EOF too.
- **Gate each block by a recipe signature** — only scan blocks that actually
  contain the invocation in question (here, a `gh api graphql` call). This avoids
  flagging an unrelated `first:` that happens to appear in a non-GraphQL snippet.
- **Numeric comparison, not pattern presence.** Capture the integer after the
  argument and flag only values strictly over the cap; the legal maximum and any
  smaller value pass.
- **One `path:line: <found> — <why>` violation per occurrence**, with a fix hint.
- **Standard `0/1/2` exit shape** so it wires into pre-commit + CI identically to
  the other lints when promoted to a blocking gate.

## Algorithm

1. Split into lines; toggle `in_block` on each fence line, recording the block's
   content start.
2. On block close (and at EOF for an open block), if the block text matches the
   recipe signature, scan its lines for the argument regex.
3. For each match, parse the integer; if `> CAP`, record a violation at the
   correct 1-based line number.
4. Exit 1 if any violations, 0 if none, 2 on usage/file-not-found.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Lint markdown recipes for an over-cap connection `first:` value (cap 100).

Exit codes: 0 clean, 1 violation(s), 2 usage/file-not-found.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_FENCE_RE = re.compile(r"^\s*```")
_RECIPE_RE = re.compile(r"\bgh\s+api\s+graphql\b")   # the invocation that scopes the scan
_ARG_RE = re.compile(r"\bfirst:\s*(\d+)")            # the capped argument
CAP = 100


class Violation:
    def __init__(self, path: str, lineno: int, value: int):
        self.path, self.lineno, self.value = path, lineno, value

    def __str__(self) -> str:
        return (f"{self.path}:{self.lineno}: first: {self.value} — exceeds the cap "
                f"of {CAP}; use first: 100 + cursor pagination (pageInfo/endCursor + --paginate)")


def _scan_block(path: str, start_idx: int, block_lines: list[str]) -> list[Violation]:
    if not _RECIPE_RE.search("\n".join(block_lines)):
        return []
    found = []
    for offset, line in enumerate(block_lines):
        for m in _ARG_RE.finditer(line):
            if int(m.group(1)) > CAP:
                found.append(Violation(path, start_idx + offset + 1, int(m.group(1))))
    return found


def check_markdown_text(path: str, text: str) -> list[Violation]:
    lines, violations, in_block, start = text.splitlines(), [], False, 0
    for idx, raw in enumerate(lines):
        if _FENCE_RE.match(raw):
            if not in_block:
                in_block, start = True, idx + 1
            else:
                violations += _scan_block(path, start, lines[start:idx])
                in_block = False
    if in_block:
        violations += _scan_block(path, start, lines[start:])
    return violations


def main(argv: list[str]) -> int:
    paths = argv[1:]
    if not paths:
        print("usage: lint_graphql_pagination.py <file.md> ...", file=sys.stderr)
        return 2
    all_v = []
    for p in paths:
        path = Path(p)
        if not path.is_file():
            print(f"ERROR: not a file: {p}", file=sys.stderr)
            return 2
        all_v += check_markdown_text(str(path), path.read_text(encoding="utf-8"))
    if all_v:
        print("Connection over-cap violations (first: > 100):")
        for v in all_v:
            print(f"  {v}")
        return 1
    print("OK: no over-cap first: found.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

## Adaptation Notes

- **Swap the three regexes for your API limit.** `_RECIPE_RE` scopes which blocks
  to scan, `_ARG_RE` captures the capped argument's integer, `CAP` is the limit.
  The fenced-block tracking is reusable verbatim.
- **Always scope by a recipe signature.** Linting every `first:` in all prose
  produces noise; only blocks containing the real invocation matter.
- **Compare numerically.** The legal maximum must pass; only strictly-over values
  flag. A naive "any large number" match would catch legitimate values.
- **Same CLI/exit shape as your other markdown/code lints** so promotion to a
  blocking pre-commit + CI gate is mechanical.
```
