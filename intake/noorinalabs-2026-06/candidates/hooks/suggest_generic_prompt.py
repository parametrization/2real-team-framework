#!/usr/bin/env python3
"""PostToolUse hook: silently track .claude/ changes as generic-prompt candidates.

Fires after Edit or Write on files under .claude/. Historically this hook emitted
a `[Generic Prompt Suggestion]` systemMessage on *every* such edit. That nudge was
never actioned (main#716): a systemMessage is non-binding background the harness
passes over mid-task, the hook wrote no state and had no dedup, and the framework's
`generic_prompts/` gained zero files across every wave despite the nudge firing
constantly — classic enforcement-hierarchy decay.

Per main#716 the concern moved UP the hierarchy from a per-edit nudge to a batched,
tracked **wave-lifecycle checkpoint** (`/wave-wrapup`). This hook is now the silent
state-tracking feeder for that checkpoint: it records the touched artifact into the
pending ledger via `generic_prompt_tracker.record_candidate` and returns None — NO
systemMessage, no mid-task noise. The deliberate genericize/skip decision happens
once per wave at the checkpoint, and decisions are durably recorded so the same
artifact is never re-surfaced.

Input Language:
  Fires on:      PostToolUse Edit, Write
  Matches:       Edit/Write whose `file_path` is a tracked `.claude/` artifact
                 (not checksums.json / annunaki/errors.jsonl / the tracker's own
                 state files) AND not already decided in the ledger
  Does NOT match: any other tool, missing file_path, paths outside `.claude/`,
                  skip-listed tracker artifacts
  Side effect:   upserts the artifact rel-path into
                 `.claude/generic_prompt_pending.json` (gitignored volatile state)
  Returns:       None ALWAYS — this hook no longer surfaces any systemMessage.

Exit codes:
  0 — always (advisory/silent hook, never blocks)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# .claude/hooks/suggest_generic_prompt.py -> hooks -> .claude -> lib
_LIB = Path(__file__).resolve().parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry point for PostToolUse Edit/Write.

    Silently records the touched `.claude/` artifact as a generic-prompt
    candidate and returns None (no systemMessage). The return type matches the
    dispatcher's uniform `dict | None` check contract, but this hook returns
    None ALWAYS at runtime — it never surfaces a systemMessage (main#716). Any
    state error is swallowed — this is an advisory feeder hook and must never
    crash PostToolUse dispatch.
    """
    tool_name = input_data.get("tool_name", "")
    if tool_name not in ("Edit", "Write"):
        return None

    file_path = input_data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return None

    try:
        import generic_prompt_tracker

        generic_prompt_tracker.record_candidate(file_path)
    except Exception:  # noqa: BLE001 — advisory feeder; never break dispatch
        return None
    return None


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    # check() always returns None now; nothing is ever printed (no systemMessage).
    check(input_data)
    sys.exit(0)


if __name__ == "__main__":
    main()
