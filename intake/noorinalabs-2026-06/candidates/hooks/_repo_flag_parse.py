#!/usr/bin/env python3
"""Shared parser for `--repo OWNER/NAME` / `-R OWNER/NAME` extraction.

Background
==========

Two PreToolUse hooks need to extract the `--repo` value from a `gh` bash
command and forward it to internal `gh` subcalls:

- `validate_labels.py` — forwards `--repo` to `gh label list` so we query
  the same repo the user is creating the issue in.
- `validate_review_comment_format.py` — forwards `--repo` to `gh pr view`
  so the branch we fetch is from the SAME repo the user is commenting
  against (#503 cross-repo skew fix, #509).

Before this helper, the two hooks had divergent parsers:

- `validate_labels.py:extract_repo` already handled ALL FOUR forms via
  `(?:^|\\s)(?:--repo|-R)(?:=|\\s+)(\\S+)` with a tokenizer-first /
  regex-fallback shape.
- `validate_review_comment_format.py:extract_repo_from_command` (added in
  #509) only handled the canonical `--repo <value>` space form via
  `--repo\\s+(\\S+)`. Equals-form, `-R`, and `-R=` were silent fallthroughs
  to cwd-default resolution — same failure direction as the #503 root
  cause, just via alternate flag spellings.

Issue #510 (filed during #509 review) asked for consolidation. This helper
mirrors the `_shell_parse` / `_wave_label_parse` shared-helper pattern.

Public API
==========

    extract_repo(command: str) -> str | None
        Parse a bash command. Returns the `OWNER/NAME` value passed via any
        of `--repo X`, `--repo=X`, `-R X`, `-R=X`, or None if no `--repo` /
        `-R` flag is present.

        Tokenizer-first via `_shell_parse.walk_flag_values`; falls back to
        a conservative regex when shlex tokenization fails (e.g. command
        contains a malformed quote). Both paths recognize all four forms.

Design notes
============

- Returns the value string unchanged for direct pass-through to gh.
- Returns None on absent flag AND on malformed flag (flag present but no
  value); callers fail-open to cwd-default resolution + breadcrumb log.
- `set` is used for `_REPO_FLAGS` to match `walk_flag_values`' expected
  type (set membership lookup); the tuple-style sentinel used elsewhere
  in the codebase would force a wrap inside `walk_flag_values`.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(os.path.abspath(__file__)).parent))

from _shell_parse import (  # noqa: E402
    tokenize,
    walk_flag_values,
)

# Flags whose VALUE is a repo specifier (OWNER/REPO).
_REPO_FLAGS = {"--repo", "-R"}

# Regex covering all 4 surface forms when tokenize() fails:
#   --repo X    --repo=X    -R X    -R=X
# Anchored on a token boundary at the front so `--no-repo` etc. cannot
# false-match. `(\\S+)` is greedy-to-whitespace; matches any non-whitespace
# value form gh accepts (gh itself validates the OWNER/NAME shape).
_REPO_FALLBACK_RE = re.compile(r"(?:^|\s)(?:--repo|-R)(?:=|\s+)(\S+)")


def extract_repo(command: str) -> str | None:
    """Extract the `--repo` / `-R` `OWNER/NAME` value, or None if absent."""
    tokens = tokenize(command)
    if tokens is None:
        match = _REPO_FALLBACK_RE.search(command)
        return match.group(1) if match else None
    values = walk_flag_values(tokens, _REPO_FLAGS)
    return values[0] if values else None
