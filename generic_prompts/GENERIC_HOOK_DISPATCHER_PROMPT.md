# PreToolUse Hook Dispatcher (single entry point)

**Purpose:** Run all your PreToolUse `Bash` checks in ONE process instead of registering N separate hooks that each spawn a Python interpreter per tool call. The dispatcher imports each hook module once and calls its `check()` function in order, so adding a hook is appending one name to a list — not editing `settings.json` and paying another subprocess startup on every command.

This is the single PreToolUse `Bash` hook wired into `settings.json`. Every individual check is a plain module exposing `check(input_data) -> dict | None`.

---

## The rule it enforces

For each registered module, in order: import it, call `check(input_data)`. If any returns a `{"decision": "block", ...}`, **first blocker wins** — print it and exit 2 immediately. Otherwise collect any `systemMessage` advisories from allow-decisions, emit them aggregated, and exit 0. A hook that fails to import or raises must NOT take down the chain — skip it (fail-open) so one broken check can't block every command.

Ordering convention: cheap/local checks first, network-calling checks last, so a fast local block short-circuits before any latency is paid.

## Code template (stdlib only — `importlib`, `json`, `sys`, `pathlib`)

```python
#!/usr/bin/env python3
"""PreToolUse dispatcher: single entry point for all Bash PreToolUse hooks.

Imports each hook module and calls check(input_data) -> dict | None.
First block wins; advisories aggregate. A hook that raises/can't import
is skipped (fail-open) so one broken check never blocks everything.

Exit codes: 0 allow (or aggregated warnings) | 2 block.
"""
import importlib, json, sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

# Ordered: cheap/local first, network-calling last. Add a hook = add a name.
_BASH_HOOKS = [
    "validate_commit_identity",
    "block_no_verify",
    "block_vcs_config",
    "block_pr_review",
    "block_stale_tmp_message_file",
    # ... your local checks ...
    "validate_labels",          # network: queries the VCS
    "validate_pr_review",       # network
]


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    if input_data.get("tool_name") != "Bash":
        sys.exit(0)

    warnings: list[str] = []
    for module_name in _BASH_HOOKS:
        try:
            mod = importlib.import_module(module_name)
        except ImportError:
            continue  # missing module — skip gracefully
        check_fn = getattr(mod, "check", None)
        if check_fn is None:
            continue
        try:
            result = check_fn(input_data)
        except Exception:
            continue  # never let a hook crash block everything
        if result is None:
            continue
        if result.get("decision", "allow") == "block":
            print(json.dumps(result))  # first blocker wins
            sys.exit(2)
        msg = result.get("systemMessage", "")
        if msg:
            warnings.append(msg)

    if warnings:
        print(json.dumps({"decision": "allow", "systemMessage": "\n\n".join(warnings)}))
    sys.exit(0)


if __name__ == "__main__":
    main()
```

## How to adapt

- **The list is your config.** Order matters: local before network. New checks append a module name; they need only a `check(input_data) -> dict | None`.
- **Fail-open on hook errors is deliberate** for a PreToolUse gate: a crashing check should not wedge every command. (If a specific check is security-critical, make *that check* fail closed internally — return a block on its own uncertainty — rather than making the dispatcher fail closed globally.)
- **First-block-wins** keeps semantics simple and makes ordering meaningful. Advisories (`systemMessage` on an allow) aggregate so multiple non-blocking nudges surface together.
- **One `settings.json` entry** points at this dispatcher for the `Bash` matcher. The mirror for other tools (Edit/Write/etc.) is a separate PostToolUse dispatcher — see `GENERIC_HOOK_POST_DISPATCHER_PROMPT.md`.
