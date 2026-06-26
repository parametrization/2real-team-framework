# PostToolUse Hook Dispatcher (single entry point)

**Purpose:** The PostToolUse mirror of the PreToolUse dispatcher. Route by tool name (`Bash`, `Edit`, `Write`, …) to an ordered list of advisory modules, run each `check()` in-process, and aggregate any `systemMessage` outputs. PostToolUse hooks CANNOT block (the tool already ran), so this dispatcher's job is advisory aggregation plus **per-check dispatch tracing** for debuggability — the common failure mode is "the harness shows `stdout=""` and the operator wrongly concludes the hook chain is dead" when a hook actually fired and returned a skip.

This is the single PostToolUse hook wired into `settings.json` for the matchers it serves.

---

## The rule it enforces

For the invoked tool, look up its module list; for each module run `check(input_data)` wrapped so an exception is captured (type + traceback excerpt) rather than propagated. Aggregate `systemMessage` fields into one advisory output; exit 0 always. Emit a dispatch-trace record (to the benign `traces.jsonl`, via the error-log helper) when a check raised OR returned a non-None dict — so silent skips and swallowed exceptions are recoverable from logs. None-returns stay silent (the overwhelming common case). Optionally let a module opt into a synthesized human-readable summary of its action-shaped return via an `EMIT_DISPATCH_SUMMARY = True` module attribute.

## Code template (stdlib only — `importlib`, `json`, `time`, `traceback`)

```python
#!/usr/bin/env python3
"""PostToolUse dispatcher: route by tool name to advisory modules.

PostToolUse cannot block. Runs each module's check() in-process, aggregates
systemMessages, and emits a dispatch-trace per interesting outcome so a
silent skip / swallowed exception is recoverable. Exit code always 0.
"""
import importlib, json, os, sys, time, traceback
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))
from annunaki_log import log_posttooluse_dispatch  # noqa: E402

_TRACE_EVERY = os.environ.get("POST_DISPATCHER_TRACE_ALL", "").lower() in ("1", "true", "yes")

# Edit and Write usually share a module set — define once, reference twice.
_EDIT_WRITE = ["ontology_tracker", "validate_edit_completion"]

# tool_name -> ordered module list (cheap/local first, network last).
_REGISTRY: dict[str, list[str]] = {
    "Bash": ["command_failure_monitor", "auto_sync_main",
             "post_label_change_field_sync"],
    "Edit": _EDIT_WRITE,
    "Write": _EDIT_WRITE,
    "NotebookEdit": ["validate_edit_completion"],
}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    modules = _REGISTRY.get(input_data.get("tool_name", ""))
    if not modules:
        sys.exit(0)

    tool_input = input_data.get("tool_input") or {}
    excerpt = str(tool_input.get("command")
                  or tool_input.get("file_path")
                  or tool_input.get("notebook_path") or tool_input)[:500]

    messages: list[str] = []
    for module_name in modules:
        try:
            mod = importlib.import_module(module_name)
        except ImportError:
            continue
        check_fn = getattr(mod, "check", None)
        if check_fn is None:
            continue

        start = time.perf_counter_ns()
        raised = None
        result = None
        try:
            result = check_fn(input_data)
        except Exception as e:  # noqa: BLE001 — advisory; never propagate
            raised = (f"{type(e).__name__}: {e}", traceback.format_exc()[:500])
        elapsed_ms = round((time.perf_counter_ns() - start) / 1_000_000, 2)

        if _TRACE_EVERY or raised is not None or isinstance(result, dict):
            try:
                log_posttooluse_dispatch(module_name, excerpt, {
                    "returned": repr(result)[:500] if result is not None else "None",
                    "raised": raised[0] if raised else None,
                    "traceback_excerpt": raised[1] if raised else None,
                    "elapsed_ms": elapsed_ms,
                }, tool_name=input_data.get("tool_name", ""))
            except Exception:
                pass  # logging must never crash the dispatcher

        if raised is not None or not isinstance(result, dict):
            continue
        msg = result.get("systemMessage")
        if msg:
            messages.append(str(msg)); continue
        if getattr(mod, "EMIT_DISPATCH_SUMMARY", False) and result.get("action"):
            parts = [f"{module_name}: action={result['action']}"]
            parts += [f"{k}={v}" for k, v in sorted(result.items())
                      if k not in ("action", "systemMessage")]
            messages.append(" ".join(parts))

    if messages:
        print(json.dumps({"systemMessage": "\n\n".join(messages)}))
    sys.exit(0)


if __name__ == "__main__":
    main()
```

## How to adapt

- **Registry by tool name.** List modules per matcher; share a list (like Edit/Write) when the sets are identical so they stay in lock-step.
- **Tracing is the debugging lifeline.** Trace every raised exception and every non-None dict return by default; gate full-verbosity (None-returns too) behind an env flag. Route traces to the *benign* log stream so they never inflate the error count.
- **Swallow, but record.** Never let a PostToolUse hook crash propagate, but capture the exception type + traceback excerpt so the swallow is recoverable — a bare `except: continue` hides real bugs.
- **`EMIT_DISPATCH_SUMMARY` opt-in** surfaces "did it post or skip?" only for the hooks where that visibility matters; keep it off by default so high-frequency hooks don't spam the UI.
