# Error-Log Writer (shared hook helper)

**Purpose:** Give all your hooks one place to append structured records to a JSONL error/event log, so blocked commands (PreToolUse), auto-detected command failures (PostToolUse), and hook self-reported follow-ups all land in the same corpus a later "review my errors" skill processes. Centralizing the writer keeps test-mode suppression, atomic single-line appends, and the **genuine-signal vs. benign-trace stream split** in one place instead of scattered across every hook.

This is a **library module** (no `check()`). Other hooks import its `log_*` functions.

---

## The rule it enforces

1. **Two streams.** Genuine signals (real command failures, real prevented commands, real follow-up events) go to `errors.jsonl` — what the review skill counts. Benign forensic traces (per-dispatch diagnostics) go to a **separate** `traces.jsonl` and are NEVER counted as errors. Without this split, dispatch traces drown the genuine signal and the error count balloons.
2. **Test-mode suppression.** When a test sentinel env var is set, writes are skipped entirely. Otherwise the hook test suite (which fires synthetic failing commands at matchers) pollutes the production log with hundreds of fake entries per run.
3. **Never fail the hook.** Writes are best-effort: swallow `OSError`, guarantee exactly one trailing newline per line, skip empty records.

## Code template (stdlib only — `json`, `os`, `datetime`, `pathlib`)

```python
#!/usr/bin/env python3
"""Shared error-log writer for hooks.

Two streams under .claude/<logdir>/:
  errors.jsonl  — genuine signals (counted by the review skill)
  traces.jsonl  — benign forensic dispatch traces (never counted)

Test-mode suppression keeps the hook test suite from polluting the log.
"""
import json
import os
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ERRORS_FILE = REPO_ROOT / ".claude" / "errors" / "errors.jsonl"
TRACES_FILE = REPO_ROOT / ".claude" / "errors" / "traces.jsonl"

# Single source of truth: record `type` values that are benign traces.
TRACE_RECORD_TYPES = frozenset({"posttooluse_dispatch", "pretooluse_diagnostic"})

# Test-mode env signals — set by your test harness / a pre-test hook.
_TEST_ENV = "ENVIRONMENT"          # == "test"
_TEST_OPT_IN = "HOOK_TEST_MODE"    # == "1"


def _is_test_mode() -> bool:
    if os.environ.get(_TEST_ENV, "") == "test":
        return True
    if os.environ.get(_TEST_OPT_IN, "") == "1":
        return True
    return False


def append_jsonl_record(path: Path, record: dict) -> None:
    """Append one JSONL record. Skips empties; one trailing newline; never raises."""
    if not isinstance(record, dict) or not record:
        return
    if _is_test_mode():
        return
    line = json.dumps(record, ensure_ascii=False).replace("\n", " ").strip()
    if not line:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # Never fail the hook


def log_pretooluse_block(hook_name, command, reason, tool_name="Bash") -> None:
    """A real prevented command → genuine signal."""
    append_jsonl_record(ERRORS_FILE, {
        "timestamp": datetime.now(UTC).isoformat(),
        "type": "pretooluse_block",
        "hook": hook_name,
        "tool_name": tool_name,
        "command": command[:500],
        "exit_code": None,
        "matched_patterns": [f"hook_block:{hook_name}"],
        "error_lines": [reason[:500]],
        "stderr_excerpt": "",
    })


def log_posttooluse_event(hook_name, command, reason, tool_name="Bash") -> None:
    """A PostToolUse hook reporting a non-blocking follow-up → genuine signal."""
    append_jsonl_record(ERRORS_FILE, {
        "timestamp": datetime.now(UTC).isoformat(),
        "type": "posttooluse_event",
        "hook": hook_name,
        "tool_name": tool_name,
        "command": command[:500],
        "exit_code": None,
        "matched_patterns": [f"hook_event:{hook_name}"],
        "error_lines": [reason[:500]],
        "stderr_excerpt": "",
    })


def log_posttooluse_dispatch(module_name, command, outcome, tool_name="Bash") -> None:
    """The dispatcher's per-check() view → benign trace (traces.jsonl)."""
    append_jsonl_record(TRACES_FILE, {
        "timestamp": datetime.now(UTC).isoformat(),
        "type": "posttooluse_dispatch",
        "module": module_name,
        "tool_name": tool_name,
        "command": command[:500],
        "outcome": outcome,  # {returned, raised, traceback_excerpt, elapsed_ms}
    })


def log_pretooluse_diagnostic(hook_name, command, diagnostic, tool_name="Bash") -> None:
    """Structured per-hook forensics alongside a block → benign trace."""
    append_jsonl_record(TRACES_FILE, {
        "timestamp": datetime.now(UTC).isoformat(),
        "type": "pretooluse_diagnostic",
        "hook": hook_name,
        "tool_name": tool_name,
        "command": command[:500],
        "diagnostic": diagnostic,  # hook-specific, JSON-safe primitives only
    })
```

## How to adapt

- **Stream split is the load-bearing idea.** Keep genuine signals and benign traces in separate files, and keep `TRACE_RECORD_TYPES` as the single list both writers and the reading skill consult. Readers should additionally skip any record whose `type` is a trace, to defend against historical mixed logs.
- **Pick your test-mode signal.** Reuse whatever env var your test harness already sets (so no `conftest.py` wiring is needed) plus one explicit opt-in for non-pytest harnesses.
- **Record schema is a contract.** The `errors.jsonl` block/event schema is consumed by your review skill — keep `hook`, `command`, `matched_patterns`, `error_lines` stable. Put hook-specific extras in the diagnostic trace channel, not the block record.
- **Truncate.** Cap `command`/`reason` lengths so one runaway record can't bloat the log.
