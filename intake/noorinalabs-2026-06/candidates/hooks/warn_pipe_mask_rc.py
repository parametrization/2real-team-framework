#!/usr/bin/env python3
"""PostToolUse hook: flag rc-masking pipes on `git push` / `gh pr merge`.

Background
==========

`git push … | tail` / `gh pr merge … | head` (or `| cat`, `| tee`, `| grep`,
…) return the PIPELINE's exit code — which, absent `set -o pipefail`, is the
LAST stage's rc, not git's/gh's. So a REJECTED push or a failed merge exits 0
through the pipe and reads as SUCCESS. This is the
[[feedback_push_pipe_masks_rejection]] class (ig#1044). P6W16 annunaki data is
direct evidence the class recurs: 40 rc=0 captures were `stdout:^FAILED`
surfacing through `… | tail`. This hook is owner-ratified P6W16 retro process
change #3 (#838).

What it flags
=============

A `git push` or `gh pr merge` invocation that is a NON-FINAL stage of a
pipeline — i.e. its rc is swallowed by a downstream stage. The masker can be
ANY downstream command (`tail`, `head`, `cat`, `tee`, `grep`, …); the footgun
is the position (left of a `|`), not a specific masker name.

What it does NOT flag (false-positive guards)
=============================================
  - `git push origin <branch>`            — no pipe; rc preserved. THE common
                                            case all wave agents use; must stay
                                            silent so this hook never blocks the
                                            other in-flight wave PRs.
  - `git push … ; echo rc=$?`             — the RECOMMENDED fix (statement
                                            separator, not a pipe). Never flag.
  - `git push … && echo done`            — `&&` short-circuits on git's rc;
                                            not masked.
  - `… | git push`                        — git push is the LAST stage; its rc
                                            IS the pipeline rc. Not masked.
  - any pipeline when `set -o pipefail`   — pipefail propagates the failing
    is present in the command               stage's rc, so it is not masked.
  - `git log | head`, `gh pr view | cat`  — not push/merge.
  - the phrase inside a heredoc body, a    — command-position aware via the
    quoted string, or a `--body` value      shared bashlex/shlex parser, not a
                                            raw substring match.

Block vs. warn (deliberate decision — #838)
===========================================

This is a PostToolUse hook: the command has ALREADY run, so it cannot block
(per `post_dispatcher.py`'s contract, PostToolUse hooks are advisory and the
exit code is always 0). The genuine footgun is the masked OUTCOME, and
PostToolUse is the only phase with access to the actual rc + output to detect
it. We therefore surface TWO severity tiers:

  TIER 1 — CONFIRMED MASKED FAILURE: the rc-masking shape is present AND the
           captured output carries a real push/merge failure signal (or the
           pipeline itself exited non-zero). This is the footgun actually
           firing — a rejection read as success. We surface a HARD, prominent
           diagnostic so it cannot pass unnoticed (per
           [[feedback_safety_direction_over_ux_friction]]: when a hook cannot
           auto-fix, surface a hard diagnostic, never silently allow).

  TIER 2 — FOOTGUN SHAPE ONLY: the rc-masking shape is present but the output
           shows no failure this time. A lighter nudge to drop the pipe / use
           `; echo rc=$?` / `set -o pipefail`, kept soft to avoid
           false-positive friction on a benign pipe that masked nothing.

A PreToolUse hard block was deliberately NOT added: the issue scopes this to
PostToolUse, and a pre-block over every `git push … |` risks blocking the 7
other wave-17 agents on benign pipes. Surfacing the real masked failure is the
in-scope, low-collateral fix.

Input Language
==============
  Fires on:      PostToolUse Bash
  Matches:       a `git push` / `gh pr merge` command in a non-final pipeline
                 stage (rc-masked), when `pipefail` is NOT set
  Does NOT match: any non-Bash tool; no-pipe pushes/merges; push/merge as the
                  pipeline's last stage; pipefail-guarded pipelines; the phrase
                  in heredoc/quoted/data position
  Flag pass-through: stdin JSON is forwarded verbatim to `check()` by the
                     PostToolUse dispatcher (`post_dispatcher.py`)

Exit codes:
  0 — always (PostToolUse advisory; never blocks)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Ensure the hooks directory is importable when run standalone (the dispatcher
# already puts it on sys.path; this covers `python3 warn_pipe_mask_rc.py`).
_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from _shell_parse import (  # noqa: E402
    find_gh_subcommand,
    find_git_subcommand,
    iter_command_segments,
    strip_heredocs,
    tokenize,
)

# bashlex is the preferred (command-position-correct) parser, mirroring
# _shell_parse's degraded-mode contract: when it is unavailable OR a command
# fails to parse, we fall back to the shlex/regex path. bashlex is the ENFORCED
# parser in CI + pre-commit (the dependency is declared there).
try:
    import bashlex
    from bashlex import ast as bashlex_ast

    _BASHLEX_AVAILABLE = True
except Exception:  # noqa: BLE001 — any import failure → degraded fallback
    bashlex = None  # type: ignore[assignment]
    bashlex_ast = None  # type: ignore[assignment]
    _BASHLEX_AVAILABLE = False


# `set -o pipefail` (or `set -eo pipefail`, `set -euo pipefail`, …) makes the
# pipeline return the FIRST failing stage's rc, so a left-of-pipe push/merge is
# no longer masked. A plain substring check is intentionally conservative: if
# the author took the trouble to type pipefail anywhere in the command, do not
# nag them.
_PIPEFAIL_RE = re.compile(r"\bpipefail\b")

# Real push/merge failure signals that can surface on captured output even when
# the pipeline exited 0 (the masked case). Used to escalate TIER 2 → TIER 1.
_FAILURE_MARKERS = re.compile(
    r"!\s*\[rejected\]"
    r"|\[remote rejected\]"
    r"|\[remote rejected:"
    r"|failed to push some refs"
    r"|failed to push"
    r"|non-fast-forward"
    r"|Updates were rejected"
    r"|protected branch"
    r"|push declined"
    r"|pre-receive hook declined"
    r"|not mergeable"
    r"|not in a mergeable state"
    r"|merge cannot be performed"
    r"|failed to merge"
    r"|Pull request is not mergeable"
    r"|required status check"
    r"|Base branch was modified"
    r"|GraphQL:\s"
    r"|^fatal:"
    r"|^error:",
    re.IGNORECASE | re.MULTILINE,
)


def _tokens_push_merge_label(tokens: list[str]) -> str | None:
    """Return 'git push' / 'gh pr merge' if `tokens` is that invocation, else None."""
    git = find_git_subcommand(tokens)
    if git is not None:
        _globals, rest = git
        if rest and rest[0] == "push":
            return "git push"
    gh = find_gh_subcommand(tokens)
    if gh is not None:
        _g, rest = gh
        if len(rest) >= 2 and rest[0] == "pr" and rest[1] == "merge":
            return "gh pr merge"
    return None


def _stage_label_ast(stage: object) -> str | None:
    """Extract a push/merge label from a single bashlex command-stage node."""
    if getattr(stage, "kind", None) != "command":
        return None
    parts = getattr(stage, "parts", []) or []
    tokens = [p.word for p in parts if getattr(p, "kind", None) == "word"]
    if not tokens:
        return None
    return _tokens_push_merge_label(tokens)


def _masked_labels_ast(command: str) -> list[str] | None:
    """Find rc-masked push/merge stages via the bashlex AST.

    Returns a list of labels ('git push' / 'gh pr merge') for every push/merge
    that sits in a NON-FINAL pipeline stage. Returns None when bashlex is
    unavailable OR the command fails to parse, signalling the caller to fall
    back to the shlex/regex path (a None is NEVER treated as "no match").
    """
    if not _BASHLEX_AVAILABLE:
        return None
    try:
        trees = bashlex.parse(command)
    except Exception:  # noqa: BLE001 — parse failure → fall back
        return None

    labels: list[str] = []

    class _PipelineVisitor(bashlex_ast.nodevisitor):  # type: ignore[misc]
        def visitpipeline(self, n, parts):  # noqa: ANN001, ANN201
            # `parts` interleaves command/compound stages with 'pipe' nodes.
            stages = [p for p in parts if getattr(p, "kind", None) != "pipe"]
            # Every stage EXCEPT the last has its rc swallowed by the pipe.
            for stage in stages[:-1]:
                label = _stage_label_ast(stage)
                if label:
                    labels.append(label)
            return True  # keep descending (nested pipelines, $(...), compounds)

    visitor = _PipelineVisitor()
    for tree in trees:
        visitor.visit(tree)
    return labels


# Fallback path: statement-split, then pipeline-split, command-position check.
# shlex keeps `;`, `&&`, `||`, `|` as standalone tokens only when whitespace-
# separated, so we first space-pad bare pipe operators that abut a word
# (`git push|tail` → `git push | tail`) WITHOUT splitting `||`. Heredocs are
# stripped by the caller before this runs.
_BARE_PIPE_PAD_RE = re.compile(r"(?<![|&])\|(?!\|)")
_STATEMENT_SEP = {";", "&&", "||", "\n"}


def _masked_labels_fallback(command: str) -> list[str]:
    """Degraded shlex/regex detection of rc-masked push/merge stages.

    Active only when bashlex is unavailable or could not parse. Splits the
    command into statements (on `;`, `&&`, `||`, newline), then each statement
    into pipeline stages (on `|`), and flags a push/merge that is not the last
    stage of its statement's pipeline.
    """
    padded = _BARE_PIPE_PAD_RE.sub(" | ", command)
    tokens = tokenize(padded)
    if tokens is None:
        return []

    labels: list[str] = []
    statement: list[str] = []

    def _flush(stmt_tokens: list[str]) -> None:
        if not stmt_tokens:
            return
        # Split the statement into pipeline stages on `|`.
        stages: list[list[str]] = []
        cur: list[str] = []
        for tok in stmt_tokens:
            if tok == "|":
                stages.append(cur)
                cur = []
            else:
                cur.append(tok)
        stages.append(cur)
        # Every stage but the last has its rc masked. iter_command_segments is
        # reused to strip leading `KEY=val` env-var assignments per stage.
        for stage in stages[:-1]:
            for seg in iter_command_segments(stage):
                label = _tokens_push_merge_label(seg)
                if label:
                    labels.append(label)

    for tok in tokens:
        if tok in _STATEMENT_SEP:
            _flush(statement)
            statement = []
        else:
            statement.append(tok)
    _flush(statement)
    return labels


def _detect_masked(command: str) -> list[str]:
    """Return de-duplicated push/merge labels that are rc-masked in `command`."""
    stripped = strip_heredocs(command)
    if _PIPEFAIL_RE.search(stripped):
        return []  # pipefail propagates the failing rc — not masked
    labels = _masked_labels_ast(stripped)
    if labels is None:  # bashlex unavailable / parse failure → degraded path
        labels = _masked_labels_fallback(stripped)
    # De-dup while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for label in labels:
        if label not in seen:
            seen.add(label)
            out.append(label)
    return out


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry point for PostToolUse Bash.

    Returns None when the command has no rc-masking push/merge pipe. Otherwise
    returns `{"systemMessage": ...}` with a TIER 1 (confirmed masked failure)
    or TIER 2 (footgun shape only) advisory. The dispatcher surfaces the
    systemMessage and never blocks (PostToolUse is advisory).
    """
    if input_data.get("tool_name", "") != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    # Cheap pre-filter: rc-masking needs a pipe AND a push/merge verb somewhere.
    # Match on the bare verbs (`push`/`merge`) rather than `git push`/`gh pr
    # merge` so global-option forms (`git -c k=v push …`) are not missed; the
    # command-position check happens in _detect_masked.
    if not command or "|" not in command:
        return None
    if "push" not in command and "merge" not in command:
        return None

    labels = _detect_masked(command)
    if not labels:
        return None

    # PostToolUse contract passes `tool_response`; older fixtures used
    # `tool_output`. Accept both (mirrors annunaki_monitor).
    tool_output = input_data.get("tool_response") or input_data.get("tool_output", {}) or {}
    stdout = tool_output.get("stdout", "") or ""
    stderr = tool_output.get("stderr", "") or ""
    exit_code = tool_output.get("exit_code", 0) or 0
    combined = f"{stdout}\n{stderr}"

    label_str = " / ".join(f"`{label}`" for label in labels)
    masker_hint = "`| tail` / `| head` / `| cat` / `| tee`"

    failure_detected = bool(exit_code) or bool(_FAILURE_MARKERS.search(combined))

    if failure_detected:
        which = f"exit code {exit_code}" if exit_code else "a failure signal in the output"
        message = (
            f"MASKED PUSH/MERGE FAILURE — {label_str} was piped into a downstream "
            f"command ({masker_hint}), so the pipeline returned that command's exit "
            f"code instead of git's/gh's, and the captured output shows {which}. The "
            f"step may read as SUCCESS while the push/merge ACTUALLY FAILED "
            f"(feedback_push_pipe_masks_rejection, ig#1044). VERIFY the push/merge "
            f"landed before proceeding — re-run without the rc-masking pipe, or append "
            f"`; echo rc=$?`, or `set -o pipefail`. (#838)"
        )
        return {"systemMessage": message, "action": "masked_failure", "labels": labels}

    message = (
        f"rc-masking pipe on {label_str}: the pipeline's exit code is the downstream "
        f"command's ({masker_hint}), not git's/gh's — a REJECTED push or failed merge "
        f"would read as success (feedback_push_pipe_masks_rejection, ig#1044). Prefer "
        f"`git push …; echo rc=$?`, drop the masking pipe, or `set -o pipefail`. (#838)"
    )
    return {"systemMessage": message, "action": "footgun_shape", "labels": labels}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    result = check(input_data)
    if result and result.get("systemMessage"):
        print(json.dumps({"systemMessage": result["systemMessage"]}))
    sys.exit(0)


if __name__ == "__main__":
    main()
