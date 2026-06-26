# Command-Failure Monitor (PostToolUse hook)

**Purpose:** Automatically capture command failures so they can be triaged later (and turned into hooks/skills/automation). After every `Bash` tool call, inspect the result for error signals — non-zero exit, stderr content, or known error-shaped patterns in output — and append a record to the error log. The hard part, and the entire transferable value, is **precision**: distinguishing a real failure from error-shaped *content* a command merely displayed, and from idioms that exit non-zero by design.

This is a PostToolUse `Bash` hook with a `check(input_data) -> dict | None` entry point. It writes via the error-log helper (`GENERIC_HOOK_ANNUNAKI_LOG_PROMPT.md`). It never blocks.

---

## The rule it enforces

Log a failure when: exit code is non-zero, OR a stderr line matches an error pattern, OR a stdout line matches one. THEN suppress the well-known false-positive classes, and **tag every surviving record with a `confidence` ∈ {high, low} and a `category`** so the reading skill counts only high-confidence records but keeps everything for forensics.

False-positive classes to suppress or demote (each is a real lesson):

| Class | Signal | Action |
|-------|--------|--------|
| **Searching for "error"** | command itself contains `grep … error`, `--error`, `error.log` | ignore |
| **Silent boolean tests** | `[ … ]`, `test`, `grep -q`, `pgrep/pkill`, `which`/`command -v` whose ONLY signal is a non-zero exit | ignore |
| **By-design exit codes** | `diff --quiet` / `<vcs> diff --quiet` exit 1 = "differs" | ignore only for the by-design code |
| **Probe-with-fallback** | exit 0 + `2>&1` + (`\|\|` or `\| head/tail`) and the ONLY match is "No such file or directory" | ignore |
| **Content display** | exit 0, stdout-only matches, leading verb is `cat/head/tail/less`, a contents-API read, or a read of the error log itself | ignore |
| **Echoed source/JSON** | exit 0 stdout match whose matched line is displayed source (`except`/`raise`/regex) or a JSON body line | demote to **low** |
| **Pipe-mask suspect** | exit 0, stdout-only, no strong signal, not recognized echoed content | demote to **low** |
| **Masked failure (keep!)** | exit 0 but output shows a real masked failure (`[rejected]`, `failed to push`, `exit status [1-9]`, a real `Traceback`) | keep **high** |

Precedence rule throughout: **any hard signal (non-zero exit OR a stderr-pattern match) wins** — a suppression only applies when the sole signal is the benign one it targets.

## Code skeleton (stdlib only — `re`, `hashlib`, `json`, `datetime`)

```python
#!/usr/bin/env python3
"""PostToolUse Bash hook: command-failure monitor. Advisory; never blocks."""
import hashlib, json, re, sys
from datetime import datetime, timezone
from annunaki_log import append_jsonl_record, ERRORS_FILE

_seen_hashes: set = set()  # session-level dedup

ERROR_PATTERNS = [
    re.compile(r"^error\b", re.I | re.M), re.compile(r"^fatal:", re.I | re.M),
    re.compile(r"^FAILED", re.M), re.compile(r"Traceback \(most recent call last\)", re.M),
    re.compile(r"^E\s+\w+Error:", re.M), re.compile(r"command not found", re.I | re.M),
    re.compile(r"No such file or directory", re.M), re.compile(r"Permission denied", re.M),
    re.compile(r"(Module|Import|Syntax|Type|Value|Key|Attribute)Error:", re.M),
    re.compile(r"exit status [1-9]", re.M), re.compile(r"failed with exit code", re.I | re.M),
]
IGNORE_PATTERNS = [re.compile(r"grep.*error", re.I), re.compile(r"--error", re.I),
                   re.compile(r"error_log|error\.log", re.I)]
SILENT_BOOL = [re.compile(r"^\s*\["), re.compile(r"^\s*test\b"),
               re.compile(r"\bgrep\s+(?:-[a-zA-Z]+\s+)*-[a-zA-Z]*q"),
               re.compile(r"^\s*(pgrep|pkill)\b"), re.compile(r"^\s*(which|command\s+-v)\b")]
SILENT_BY_CODE = [(re.compile(r"\bdiff\s+--quiet\b"), {1}), (re.compile(r"\b\w+\s+diff\s+--quiet\b"), {1})]
PROBE_MERGE, PROBE_TRAIL = re.compile(r"2>&1"), re.compile(r"\|\||\|\s*head\b|\|\s*tail\b")
PROBE_ONLY = "stdout:No such file or directory"
DISPLAY_VERBS = re.compile(r"^\s*(cat|head|tail|less|more|bat|\w+\s+show|\w+\s+log)\b")
STRONG_MASK = re.compile(r"failed to push|\[rejected\]|non-fast-forward|exit status [1-9]"
                         r"|failed with exit code|\(exit [1-9][0-9]*\)"
                         r"|Traceback \(most recent call last\)", re.I)
SOURCE_LINE = re.compile(r"^\s*[+-]?\s*(?:except|raise)\s+[\w.(]|^\s*[+-]?\s*re\.compile\(")
JSON_LINE = re.compile(r'^\s*[+-]?\s*[{\[]\s*["{]')


def _classify(exit_code, matched, error_lines):
    if exit_code and exit_code != 0:
        return "high", "nonzero-exit"
    if any(p.startswith("stderr:") for p in matched):
        return "high", "stderr-match"
    if STRONG_MASK.search("\n".join(error_lines)):
        return "high", "masked-failure"
    if any(SOURCE_LINE.search(l) or JSON_LINE.search(l) for l in error_lines):
        return "low", "echoed-content"
    return "low", "pipe-mask-suspect"


def check(input_data: dict) -> dict | None:
    if input_data.get("tool_name") != "Bash":
        return None
    command = (input_data.get("tool_input") or {}).get("command", "")
    out = input_data.get("tool_response") or input_data.get("tool_output", {})
    stdout, stderr = out.get("stdout", ""), out.get("stderr", "")
    exit_code = out.get("exit_code", 0)
    if any(p.search(command) for p in IGNORE_PATTERNS):
        return None

    matched: list[str] = []
    if exit_code and exit_code != 0:
        matched.append(f"exit_code={exit_code}")
    if stderr.strip():
        for p in ERROR_PATTERNS:
            if p.search(stderr):
                matched.append(f"stderr:{p.pattern}"); break
    for p in ERROR_PATTERNS:
        if p.search(stdout):
            matched.append(f"stdout:{p.pattern}"); break
    if not matched:
        return None

    # Suppressions (each requires the benign signal to be the ONLY signal).
    only_exit = matched == [f"exit_code={exit_code}"]
    if only_exit and (any(p.search(command) for p in SILENT_BOOL)
                      or any(p.search(command) and exit_code in codes for p, codes in SILENT_BY_CODE)):
        return None
    if (exit_code == 0 and matched == [PROBE_ONLY]
            and PROBE_MERGE.search(command) and PROBE_TRAIL.search(command)):
        return None
    if (exit_code == 0 and matched and all(m.startswith("stdout:") for m in matched)
            and not PROBE_MERGE.search(command) and PROBE_ONLY not in matched
            and DISPLAY_VERBS.search(command)):
        return None

    error_lines = _extract_error_lines(f"{stdout}\n{stderr}".strip())
    confidence, category = _classify(exit_code, matched, error_lines)
    dedup = hashlib.md5((command[:200] + "|||" + "\n".join(error_lines)[:500]).encode()).hexdigest()
    if dedup in _seen_hashes:
        return None
    _seen_hashes.add(dedup)
    append_jsonl_record(ERRORS_FILE, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hook": "command_failure_monitor", "command": command[:500],
        "exit_code": exit_code, "matched_patterns": matched[:5],
        "confidence": confidence, "category": category, "error_lines": error_lines,
        "stderr_excerpt": stderr[:300], "_dedup_hash": dedup,
    })
    return {"action": "logged", "confidence": confidence, "category": category}
```
(`_extract_error_lines` grabs each matching line plus ~2 lines of trailing context, capped.)

## How to adapt

- **Start permissive, add suppressions from evidence.** Each false-positive class above came from observed noise. Add yours the same way; don't pre-invent filters.
- **Precedence is non-negotiable.** A suppression must check that its benign signal is the *only* signal. A `[ -f x ]` that somehow emits a real Traceback must still log.
- **Confidence preserves recall.** Only demote matches you can *positively* recognize as benign. An unrecognized exit-0 stdout match defaults to the lower-noise class your evidence supports, but a non-zero exit / stderr / strong-mask phrase always stays high and counted.
- **Session dedup** prevents the same loop firing N identical records.
- **Hook attribution:** stamp a `hook` field so the review skill's by-hook breakdown doesn't bucket auto-captures as "unknown".
