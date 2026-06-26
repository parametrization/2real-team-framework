# Iteration-Label Command Parser (shared hook helper)

**Purpose:** When your workflow tags issues with a structured "iteration" label (a sprint/wave/milestone identifier) and you want hooks to react to label changes, you need to recognize the label-mutation command shape — `<cli> issue edit <num> --add-label "<iter-label>"` / `--remove-label "<iter-label>"` and `<cli> issue create --label "<iter-label>"` — across arbitrary multi-command Bash. This helper consolidates that domain-specific shape on top of the general shell parser so each consuming hook does not re-implement (and re-regress) the tokenization.

This is a **library module** layered on the shell parser. See `GENERIC_HOOK_SHELL_PARSE_PROMPT.md`.

---

## The rule it enforces

Given a Bash command, return every iteration-label change/create it contains — one result per matching `issue edit`/`issue create` segment, across `&&`-chains, `;`/newline separators, and pipelines. Only **canonical** iteration labels (matching an anchored grammar) drive the result; arbitrary suffixed variants are out of scope. The `--repo` flag is **optional**: an in-repo invocation omits it and relies on ambient VCS resolution, so the parser returns `repo=None` rather than dropping the change — the consuming hook resolves the ambient repo from cwd.

The label grammar is **the** thing you customize. The reference supports three cooperating forms so an identifier scheme can evolve without breaking grandfathered labels:

- a **legacy compound** form (e.g. a phase-prefixed `p{N}-iter-{M}`),
- a **flat global** form (e.g. `iter-{X}` with a monotonic id), and
- a **placeholder** for undecided scope (e.g. the literal `iter-x`).

## Code template (stdlib only)

```python
#!/usr/bin/env python3
"""Shared parser for iteration-label `<cli> issue edit/create` commands.

Recognizes the canonical iteration-label grammar inside add/remove/label
flags across multi-command Bash. Built on the shared shell parser so the
tokenization fixes (heredoc strip, line-continuation, env-prefix strip,
flag-value walk) are inherited, not re-implemented.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shell_parse import (  # noqa: E402
    find_tool_subcommand, iter_command_segments, strip_heredocs, tokenize,
)

# --- CUSTOMIZE: your iteration-label grammar -------------------------------
_LEGACY_RE = re.compile(r"^p(\d+)-iter-(\d+)$")   # compound form (grandfathered)
_GLOBAL_RE = re.compile(r"^iter-(\d+)$")          # flat monotonic form
_PLACEHOLDER = "iter-x"                            # scope-undecided literal
_CLI = "gh"                                        # your VCS CLI name
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LabelSpec:
    raw: str
    major: int | None       # e.g. phase — None for flat/placeholder forms
    minor: int | None       # e.g. iteration number — None for placeholder
    is_placeholder: bool


@dataclass(frozen=True)
class LabelChange:
    repo: str | None        # short repo name, or None for in-repo invocation
    issue_number: str
    add_label: str | None
    remove_label: str | None


def parse_label_spec(value: str) -> LabelSpec | None:
    """Single source of truth for the label grammar. None if not a label."""
    if value == _PLACEHOLDER:
        return LabelSpec(value, None, None, True)
    m = _LEGACY_RE.match(value)
    if m:
        return LabelSpec(value, int(m.group(1)), int(m.group(2)), False)
    m = _GLOBAL_RE.match(value)
    if m:
        return LabelSpec(value, None, int(m.group(1)), False)
    return None


def is_label(value: str) -> bool:
    return parse_label_spec(value) is not None


def label_to_field_option(value: str) -> str | None:
    """Map a label to a board single-select option name (customize)."""
    s = parse_label_spec(value)
    if s is None:
        return None
    if s.is_placeholder:
        return "TBD"
    if s.major is None:
        return f"W{s.minor}"
    return f"P{s.major}W{s.minor}"


def _flag_value(rest, i, n):
    """Return (value, next_i) for `--flag value` or split off `--flag=value`."""
    return rest[i + 1], i + 2


def _parse_edit_segment(rest: list[str]) -> LabelChange | None:
    if len(rest) < 3 or rest[0] != "issue" or rest[1] != "edit":
        return None
    issue_number = repo = add_label = remove_label = None
    i, n = 2, len(rest)
    while i < n:
        tok = rest[i]
        if issue_number is None and re.fullmatch(r"\d+", tok):
            issue_number = tok; i += 1; continue
        for flag, setter in (("--repo", "repo"),
                              ("--add-label", "add"),
                              ("--remove-label", "remove")):
            val = None
            if tok == flag and i + 1 < n:
                val = rest[i + 1]; i += 2
            elif tok.startswith(flag + "="):
                val = tok[len(flag) + 1:]; i += 1
            if val is not None:
                if setter == "repo":
                    repo = val.split("/")[-1]
                elif setter == "add" and add_label is None and is_label(val):
                    add_label = val
                elif setter == "remove" and remove_label is None and is_label(val):
                    remove_label = val
                break
        else:
            i += 1
    if issue_number and (add_label or remove_label):
        return LabelChange(repo, issue_number, add_label, remove_label)
    return None


def parse_label_changes(command: str) -> list[LabelChange]:
    """All iteration-label changes in a (possibly multi-command) Bash string."""
    tokens = tokenize(strip_heredocs(command))
    if tokens is None:
        return []
    out = []
    for segment in iter_command_segments(tokens):
        gh = find_tool_subcommand(segment, _CLI, value_globals=set(), bool_globals=set())
        if gh is None:
            continue
        change = _parse_edit_segment(gh[1])
        if change is not None:
            out.append(change)
    return out


def parse_label_change(command: str) -> LabelChange | None:
    """Back-compat singular: first change or None (single-cmd consumers)."""
    changes = parse_label_changes(command)
    return changes[0] if changes else None
```

## How to adapt

- **Grammar is the whole point.** Replace `_LEGACY_RE` / `_GLOBAL_RE` / `_PLACEHOLDER` with your label scheme. **Fully anchor** them (`^...$`) so a suffixed variant like `iter-10-frozen` does NOT match and silently mutate board state.
- **Optional `--repo`.** Keep `repo=None` valid. Requiring `--repo` silently drops every in-repo invocation — the exact bug this guards against. The consumer resolves the ambient repo (from cwd for edits, from the created-issue URL for creates).
- **Add a `parse_label_create` twin** for `issue create --label` if a create-time hook (board-add) needs the label before the issue number exists; extract the number from the create's stdout.
- **Multi-command is mandatory:** batch label ops commonly arrive as `edit 1 …; edit 2 …` or `&&`-chains. Returning a list (plural) is the correct default; keep a singular shim only for genuinely single-shot consumers.
- **Keep this separate from the general shell parser.** It knows domain shapes (`issue edit`, your label grammar, short-name extraction); the general parser stays domain-free.
