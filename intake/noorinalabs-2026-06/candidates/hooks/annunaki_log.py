#!/usr/bin/env python3
"""Shared Annunaki error logging utility.

Called by PreToolUse hooks when they block a command, so that blocked
commands appear in the Annunaki error log alongside PostToolUse errors.

Two streams (#625)
==================
This module writes to TWO files under `.claude/annunaki/`:

  - `errors.jsonl`  — genuine signals: command-failure records (from
    `annunaki_monitor`), `pretooluse_block` (a real prevented command), and
    `posttooluse_event` (a hook reporting a follow-up condition). This is what
    `/annunaki` counts and `/annunaki-attack` processes.
  - `traces.jsonl`  — benign forensic traces: `posttooluse_dispatch` (the
    dispatcher's per-check() view) and `pretooluse_diagnostic` forensics.
    Informational only; NEVER counted as errors.

Pre-#625 both kinds shared `errors.jsonl`; dispatch traces were 76% of the
P4W1 log and `/annunaki` over-counted them as errors. `TRACE_RECORD_TYPES` is
the single source of truth for which record types are benign traces.

Usage in any blocking hook:
    from annunaki_log import log_pretooluse_block
    log_pretooluse_block(hook_name="validate_commit_identity", command=command, reason=reason)

Test-mode suppression (issue #452)
==================================

When `ENVIRONMENT=test` or `NOORIN_HOOK_TEST_MODE=1` is set in the env,
`append_jsonl_record` returns without writing. This prevents the hook
test suite (which exercises matchers against synthetic fixtures like
`gh pr review 42`, `gh issue create --label does-not-exist`) from
polluting the production `.claude/annunaki/errors.jsonl` with hundreds
of fake error entries — pre-#452 a single test-suite run produced ~293
entries (76% of the log's content as captured 2026-05-16).

`ENVIRONMENT=test` is the charter-required env var for pytest (set by
`auto_set_env_test.py` PreToolUse hook); using it as the suppression
signal means no conftest.py setup is needed — every existing test
invocation already sets it. `NOORIN_HOOK_TEST_MODE` is provided as an
explicit opt-in for non-pytest harnesses (CI matrix jobs, ad-hoc shell
fixtures) that need annunaki suppression without claiming `ENVIRONMENT=test`.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ERRORS_FILE = REPO_ROOT / ".claude" / "annunaki" / "errors.jsonl"

# Benign-trace stream separation (#625)
# =====================================
# Pre-#625, every annunaki record — genuine command-failure errors AND benign
# forensic dispatch traces — was appended to the single `errors.jsonl`. The
# PostToolUse dispatcher emits a `posttooluse_dispatch` trace for EVERY
# interesting check() call (every genuine error logged by annunaki_monitor
# returns an action dict, so each real error spawns a companion trace), plus
# `pretooluse_diagnostic` forensics. In the P4W1 window these benign traces were
# 137 of 181 records (76%) and `/annunaki` counted all of them as "errors",
# wildly over-reporting (#625).
#
# Fix: route the two informational-by-design record kinds to a SEPARATE
# `traces.jsonl`. `errors.jsonl` now holds only genuine signals — the
# annunaki_monitor command-failure records, `pretooluse_block` (a real
# prevented error), and `posttooluse_event` (a hook reporting a follow-up
# condition). `/annunaki` + `/annunaki-attack` count `errors.jsonl` as before
# and additionally defend against historical mixed logs by skipping any record
# whose `type` is in TRACE_RECORD_TYPES.
TRACES_FILE = REPO_ROOT / ".claude" / "annunaki" / "traces.jsonl"

# Record `type` values that are benign forensic traces, NOT errors. The
# annunaki parsers treat these as non-counting. Kept here as the single source
# of truth so writers and readers agree.
TRACE_RECORD_TYPES = frozenset({"posttooluse_dispatch", "pretooluse_diagnostic"})


def _is_test_mode() -> bool:
    """True iff annunaki should suppress writes (test harness running).

    Returns True when EITHER:
      - `ENVIRONMENT=test` is set (charter-required for pytest)
      - `NOORIN_HOOK_TEST_MODE=1` is set (explicit non-pytest opt-in)

    Empty / unset / any other value → False (production fall-through).
    """
    if os.environ.get("ENVIRONMENT", "") == "test":
        return True
    if os.environ.get("NOORIN_HOOK_TEST_MODE", "") == "1":
        return True
    return False


def append_jsonl_record(path: Path, record: dict) -> None:
    """Append one JSONL record. Skips empty records and guarantees exactly
    one trailing newline per line — never a bare blank line. Shared by
    annunaki_log.py and annunaki_monitor.py so writer hardening stays in
    one place.

    Test-mode suppression: when `_is_test_mode()` is True (ENVIRONMENT=test
    or NOORIN_HOOK_TEST_MODE=1), the write is skipped entirely. This is the
    #452 fix — the hook test suite pollutes the production error log with
    ~293 fixture entries per run otherwise.
    """
    if not isinstance(record, dict) or not record:
        return
    if _is_test_mode():
        return
    # json.dumps with default settings does not emit newlines, so the
    # serialized form is guaranteed single-line. Strip any stray ones
    # defensively anyway.
    line = json.dumps(record, ensure_ascii=False).replace("\n", " ").strip()
    if not line:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # Never fail the hook


def log_pretooluse_block(
    hook_name: str, command: str, reason: str, tool_name: str = "Bash"
) -> None:
    """Append a PreToolUse block event to the Annunaki error log."""
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "type": "pretooluse_block",
        "hook": hook_name,
        "tool_name": tool_name,
        "command": command[:500],
        "exit_code": None,
        "matched_patterns": [f"hook_block:{hook_name}"],
        "error_lines": [reason[:500]],
        "stderr_excerpt": "",
    }
    append_jsonl_record(ERRORS_FILE, record)


def log_pretooluse_diagnostic(
    hook_name: str,
    command: str,
    diagnostic: dict,
    tool_name: str = "Bash",
) -> None:
    """Append a structured diagnostic record alongside a PreToolUse block.

    Distinct from `log_pretooluse_block` because the block-record schema is
    pinned by /annunaki and downstream parsers; this side-channel carries
    per-hook structured forensics without touching that contract. Used
    today by `enforce_librarian_consulted` to capture cwd / sentinel path /
    sentinel mtime / transcript path on every block so #429-style
    "why did it block?" questions are answerable from logs alone.

    Keys in `diagnostic` are hook-specific; values must be JSON-safe
    primitives (no datetime, no Path — stringify upstream). The record's
    top-level `type` is `pretooluse_diagnostic`; it is written to
    `traces.jsonl` (NOT `errors.jsonl`) so it never inflates /annunaki error
    counts (#625).
    """
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "type": "pretooluse_diagnostic",
        "hook": hook_name,
        "tool_name": tool_name,
        "command": command[:500],
        "diagnostic": diagnostic,
    }
    # Benign forensic trace → traces.jsonl, not errors.jsonl (#625).
    append_jsonl_record(TRACES_FILE, record)


def log_posttooluse_dispatch(
    module_name: str,
    command: str,
    outcome: dict,
    tool_name: str = "Bash",
) -> None:
    """Append a per-hook dispatch trace from `post_dispatcher`.

    Distinct from `log_posttooluse_event` (which is hooks self-reporting
    their own non-actionable conditions) because this records the
    DISPATCHER's view of every check() call: did it return None / a
    structured action dict / raise. Critical for #425-class debugging
    where the harness sees only `stdout=""` and the operator concludes
    "dispatcher dead" even when the chain is firing perfectly. Type is
    `posttooluse_dispatch`; the record is written to `traces.jsonl` (NOT
    `errors.jsonl`) so it never inflates /annunaki error counts (#625) — it's
    informational unless `outcome.raised` is set.

    `outcome` shape (all JSON-safe primitives):
      - returned: stringified repr of what check() returned (or "None")
      - raised: exception type name, or null
      - traceback_excerpt: first 500 chars of traceback if raised, else null
      - elapsed_ms: optional, round-trip duration of the check() call
    """
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "type": "posttooluse_dispatch",
        "module": module_name,
        "tool_name": tool_name,
        "command": command[:500],
        "outcome": outcome,
    }
    # Benign forensic trace → traces.jsonl, not errors.jsonl (#625).
    append_jsonl_record(TRACES_FILE, record)


def log_posttooluse_event(
    hook_name: str, command: str, reason: str, tool_name: str = "Bash"
) -> None:
    """Append a PostToolUse non-blocking event to the Annunaki error log.

    PostToolUse hooks cannot block the tool call (it has already run), so
    they don't "block" — they record events that need follow-up. Used by
    hooks like `post_wave_kickoff_comment` when they cannot complete their
    post-action work (e.g., scope row missing, gh CLI failure) and want a
    visible signal in the Annunaki sweep without raising a failure on the
    underlying tool call.
    """
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "type": "posttooluse_event",
        "hook": hook_name,
        "tool_name": tool_name,
        "command": command[:500],
        "exit_code": None,
        "matched_patterns": [f"hook_event:{hook_name}"],
        "error_lines": [reason[:500]],
        "stderr_excerpt": "",
    }
    append_jsonl_record(ERRORS_FILE, record)
