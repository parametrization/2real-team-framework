# Repo-Flag Extractor (shared hook helper)

**Purpose:** Several hooks need to read the target repository out of a VCS CLI command — the `--repo OWNER/NAME` (or short `-R OWNER/NAME`) flag — so they forward the SAME repo to their internal sub-calls (e.g. a label-validation hook queries `<cli> label list --repo X`; a review-format hook fetches the PR branch from `--repo X`). If the extractor only handles one of the surface forms, the other forms silently fall through to cwd-default resolution and the hook operates on the wrong repo. This helper recognizes **all four forms** in one place.

This is a tiny **library module** layered on top of the shell parser. See `GENERIC_HOOK_SHELL_PARSE_PROMPT.md`.

---

## The rule it enforces

Extract the repo specifier passed via any of: `--repo X`, `--repo=X`, `-R X`, `-R=X`. Return the value unchanged for pass-through; return `None` when no such flag is present (callers fall open to cwd-default resolution). Recognize all four forms on **both** the tokenizer path and the regex-fallback path so a malformed-quote command does not regress to one-form-only behavior.

## Code template (stdlib only)

```python
#!/usr/bin/env python3
"""Shared parser for `--repo OWNER/NAME` / `-R OWNER/NAME` extraction.

Recognizes all four forms (--repo X, --repo=X, -R X, -R=X) on both the
tokenizer path and a conservative regex fallback. Returns None when no
repo flag is present so callers fall open to cwd-default resolution.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(os.path.abspath(__file__)).parent))
from _shell_parse import tokenize, walk_flag_values  # noqa: E402

# Flags whose VALUE is a repo specifier (OWNER/NAME).
_REPO_FLAGS = {"--repo", "-R"}

# Fallback regex covering all 4 forms when tokenize() fails. Anchored on a
# token boundary so `--no-repo` etc. cannot false-match.
_REPO_FALLBACK_RE = re.compile(r"(?:^|\s)(?:--repo|-R)(?:=|\s+)(\S+)")


def extract_repo(command: str) -> str | None:
    """Extract the --repo / -R OWNER/NAME value, or None if absent."""
    tokens = tokenize(command)
    if tokens is None:
        m = _REPO_FALLBACK_RE.search(command)
        return m.group(1) if m else None
    values = walk_flag_values(tokens, _REPO_FLAGS)
    return values[0] if values else None
```

## How to adapt

- **Flag names.** Swap `--repo`/`-R` for whatever flag identifies the resource your hooks operate on (`--project`, `--namespace`, `--cluster`). Keep both the long and short spellings in `_REPO_FLAGS` and the fallback regex.
- **`set`, not tuple.** `_REPO_FLAGS` is a `set` because `walk_flag_values` does set-membership lookup.
- **Return the value verbatim.** Do not validate the `OWNER/NAME` shape here — the underlying CLI validates it. Returning it unchanged keeps the helper a pure extractor.
- **None means "fall open."** Treat a missing flag and a malformed flag (present but no value) identically: return `None` and let the caller resolve the resource from ambient context (and optionally log a breadcrumb).
