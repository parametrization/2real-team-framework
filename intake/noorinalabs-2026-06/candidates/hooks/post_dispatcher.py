#!/usr/bin/env python3
"""PostToolUse dispatcher: Single entry point for all PostToolUse hooks.

Mirrors `dispatcher.py` (the PreToolUse Bash dispatcher) for the
PostToolUse phase. Routes by matcher (Bash, Edit, Write, NotebookEdit) so
all PostToolUse hooks run in-process per tool call instead of via N
separate `python3` subprocess invocations.

Each PostToolUse hook module exposes:
    check(input_data: dict) -> dict | None
        Returns None for no-op (hook didn't apply or had no advisory to
        emit). Returns a dict with `systemMessage` to surface an advisory
        message through the harness. Other keys (`action`, etc.) are
        recorded for diagnostics but not surfaced — UNLESS the module
        sets `EMIT_DISPATCH_SUMMARY = True` at module scope, in which
        case the dispatcher synthesizes a `systemMessage` summary from
        the action-shaped return so operators see what happened in the
        harness UI (per-hook opt-in, default False; see #425).

Unlike PreToolUse, PostToolUse hooks CANNOT block the tool — it already
ran. The dispatcher runs every registered module for the matcher and
aggregates any `systemMessage` fields into a single advisory output.
Exit code is always 0; the dispatcher never blocks. If an individual hook
raises an unhandled exception, the dispatcher swallows it (fail-open,
mirroring `dispatcher.py`).

Input Language:
  Fires on:      PostToolUse Bash | Edit | Write | NotebookEdit
  Matches:       any tool invocation whose `tool_name` is a key in
                 `_REGISTRY` (Bash, Edit, Write, NotebookEdit)
  Does NOT match: tool invocations whose matcher has no registered modules
  Flag pass-through: stdin JSON is read once and passed verbatim to each
                     registered module's `check()` function

Exit codes:
  0 — always (PostToolUse hooks are advisory; aggregated systemMessages
      are emitted as JSON on stdout but the exit code stays 0)
"""

import importlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

# Ensure the hooks directory is on sys.path for imports
_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from annunaki_log import log_posttooluse_dispatch  # noqa: E402

# Per-check dispatch tracing (#425). When `POST_DISPATCHER_TRACE_ALL=1` is
# set, the dispatcher emits an annunaki `posttooluse_dispatch` record for
# every check() call regardless of outcome. By default, only "interesting"
# outcomes are recorded: raised exceptions OR non-None dict returns (the
# action-shaped `{"action": "post|skip_*", ...}` returns that PostToolUse
# hooks like post_wave_kickoff_comment use). None returns from hooks
# legitimately not applying (overwhelming common case) stay silent so the
# log doesn't drown in no-op entries.
_TRACE_EVERY = os.environ.get("POST_DISPATCHER_TRACE_ALL", "").lower() in ("1", "true", "yes")

# Edit and Write share the same module set today (every module that runs on
# Edit also runs on Write). Defining it once keeps the two matcher entries
# in lock-step.
_EDIT_WRITE_MODULES = [
    "ontology_tracker",
    "suggest_generic_prompt",
    "validate_edit_completion",
]

# Matcher → ordered list of hook-module import names.
# Order matters: cheap/local checks first, network-calling checks last
# (mirroring `dispatcher.py`'s ordering convention).
_REGISTRY: dict[str, list[str]] = {
    "Bash": [
        "annunaki_monitor",  # local: regex over stdout/stderr, JSONL append
        "warn_pipe_mask_rc",  # local: flag rc-masking `git push|tail`/`gh pr merge|head` (#838)
        "auto_sync_main",  # local: ff local main after a push/merge to origin/main (#713)
        "auto_add_issue_to_board",  # network: runs `gh project item-add`
        "post_wave_kickoff_comment",  # network: gh fetch + post comment
        "post_label_change_wave_field_sync",  # network: GraphQL updateProjectV2ItemFieldValue
    ],
    "Edit": _EDIT_WRITE_MODULES,
    "Write": _EDIT_WRITE_MODULES,
    "NotebookEdit": [
        "validate_edit_completion",  # PostToolUse sentinel write only
    ],
}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    modules = _REGISTRY.get(tool_name)
    if not modules:
        sys.exit(0)

    messages: list[str] = []

    # Command excerpt for dispatch-trace records. Bash hooks see the literal
    # tool_input.command; Edit/Write hooks see the file_path. Other shapes
    # fall back to a JSON-stringified preview.
    tool_input = input_data.get("tool_input") or {}
    if tool_name == "Bash":
        command_excerpt = str(tool_input.get("command", ""))[:500]
    else:
        command_excerpt = str(
            tool_input.get("file_path") or tool_input.get("notebook_path") or tool_input
        )[:500]

    for module_name in modules:
        try:
            mod = importlib.import_module(module_name)
        except ImportError:
            continue  # Skip missing modules gracefully

        check_fn = getattr(mod, "check", None)
        if check_fn is None:
            continue

        start_ns = time.perf_counter_ns()
        raised_excinfo: tuple[str, str] | None = None
        result = None
        try:
            result = check_fn(input_data)
        except Exception as e:  # noqa: BLE001
            # Never let a hook crash propagate — advisory only. But unlike
            # the pre-#425 bare `except: continue`, capture the type +
            # traceback excerpt so the swallow is recoverable via /annunaki.
            tb_text = traceback.format_exc()[:500]
            raised_excinfo = (f"{type(e).__name__}: {e}", tb_text)

        elapsed_ms = round((time.perf_counter_ns() - start_ns) / 1_000_000, 2)

        # Emit a dispatch-trace record when (a) the env-flag forces it,
        # (b) the check raised, or (c) the check returned a non-None dict
        # (action-shape diagnostic). None returns stay silent — those are
        # the legitimate "hook didn't apply" overwhelming-common case.
        should_trace = _TRACE_EVERY or raised_excinfo is not None or isinstance(result, dict)
        if should_trace:
            outcome = {
                "returned": repr(result)[:500] if result is not None else "None",
                "raised": raised_excinfo[0] if raised_excinfo else None,
                "traceback_excerpt": raised_excinfo[1] if raised_excinfo else None,
                "elapsed_ms": elapsed_ms,
            }
            try:
                log_posttooluse_dispatch(
                    module_name=module_name,
                    command=command_excerpt,
                    outcome=outcome,
                    tool_name=tool_name,
                )
            except Exception:  # noqa: BLE001
                pass  # Logging must never crash the dispatcher

        if raised_excinfo is not None:
            continue  # Swallowed-and-logged; move on to the next hook

        if not isinstance(result, dict):
            continue

        msg = result.get("systemMessage")
        if msg:
            messages.append(str(msg))
            continue

        # Per-hook opt-in (#425): when the module sets
        # `EMIT_DISPATCH_SUMMARY = True` AND the result carries an `action`
        # key, the dispatcher synthesizes a short systemMessage from the
        # action-shaped return. Operators then see "post_wave_kickoff_comment:
        # action=post repo=… issue=…" in the harness UI for the specific
        # hooks where that visibility is load-bearing. Default-off keeps
        # hooks like annunaki_monitor (action dicts on every Bash call) from
        # spamming the UI. The annunaki dispatch-trace record fires
        # independently of this flag for full forensic visibility.
        if getattr(mod, "EMIT_DISPATCH_SUMMARY", False) and result.get("action"):
            summary_parts = [f"{module_name}: action={result['action']}"]
            for k, v in sorted(result.items()):
                if k in ("action", "systemMessage"):
                    continue
                summary_parts.append(f"{k}={v}")
            messages.append(" ".join(summary_parts))

    if messages:
        output = {"systemMessage": "\n\n".join(messages)}
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
