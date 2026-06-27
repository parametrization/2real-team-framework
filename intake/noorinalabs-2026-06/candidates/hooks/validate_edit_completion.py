#!/usr/bin/env python3
"""Validate Edit Completion: block state-sensitive actions after unhandled Edit errors.

This hook addresses the **tool-error-soft-accept** failure class that surfaced
≥2× during P2W10 (Marcia walkback + Bereket Contract-revert false-status).
Pattern: Edit/Write/NotebookEdit returns an error (e.g., "File has not been
read yet"), agent does not explicitly verify, then emits downstream actions
(SendMessage, git commit, gh comment) as if the edit succeeded — and state
drifts from what the agent reports.

Architecture
============

Two-phase design across one hook script with mode dispatch:

**PostToolUse phase** — fires on Edit/Write/NotebookEdit tool calls. If the
tool_response carries `is_error: true`, the hook records the file path +
short error excerpt to a session-scoped sentinel file at
`<repo_root>/.claude/.edit-error-sentinel/<session-id>.jsonl`. Always exits 0
(advisory; never blocks the post-call return).

**PreToolUse phase** — fires on subsequent state-sensitive actions:
  - Edit/Write/NotebookEdit on the same file_path
  - SendMessage (status-claim risk)
  - Bash commands matching `git commit`, `gh pr comment`, `gh issue comment`

Reads the sentinel file, checks each unhandled-error entry for an
acknowledgment-since-the-error in the session transcript:

  (a) A `Read` tool_use on the errored file path
  (b) A `Bash` tool_use that `cat`/`head`/`tail`/`grep`/`less`/`ls`-es the
      errored file path
  (c) A SendMessage whose body contains the literal phrase
      "edit-error acknowledged" plus the file path

Acknowledged entries are PRUNED from the sentinel (so they don't re-block).
Unacknowledged entries that match the action's risk profile BLOCK with a
remediation message naming the file path.

Input Language
==============

Fires on:
    PostToolUse Edit | Write | NotebookEdit  (record-on-error)
    PreToolUse  Edit | Write | NotebookEdit  (block-if-unack-and-same-path)
    PreToolUse  SendMessage                  (block-if-any-unack)
    PreToolUse  Bash                         (block-if-unack-and-state-sensitive)

Matches (PreToolUse Bash; record-on-Edit-error path is structural):
    git [globals] commit [args]
    gh pr comment ...
    gh issue comment ...
    (any compound-command segment containing the above forms)

Does NOT match:
    - Edit/Write/NotebookEdit calls with `is_error: false` (no state drift to track)
    - Bash commands that are NOT git-commit / gh-comment forms
    - Edit/Write/NotebookEdit on a DIFFERENT file_path than the errored one
    - SendMessage when the sentinel is empty

Acknowledgment forms (any ONE of these, in the transcript AFTER the error):
    - Read on the errored file_path
    - Bash containing one of: cat / head / tail / less / grep / ls -la / wc
      where the errored file path is an argument
    - SendMessage body containing both the file path AND the literal string
      "edit-error acknowledged"

Sentinel design
===============

  File:    <repo_root>/.claude/.edit-error-sentinel/<session-id>.jsonl
  Format:  one JSON object per line:
    {"path": "<abs path>", "tool": "Edit|Write|NotebookEdit",
     "error": "<short>", "ts": "<ISO>"}
  Pruning:  acknowledged entries are removed atomically on the next PreToolUse
            evaluation that finds them satisfied. Sentinels are session-scoped;
            a stale sentinel from a prior crashed session has TTL of 24 hours
            (longer than enforce_librarian_consulted because edit-state recovery
            can span session restarts).
  Gitignore: `.claude/.edit-error-sentinel/` is added to `.gitignore`.

Charter promotion
=================

Promotion-target: hook (per `feedback_enforcement_hierarchy.md` — charter
rules without enforcement decay; Edit-error-soft-accept is mechanical,
detectable, low-overhead-to-comply, so hook-tier is correct).

Provenance: P2W10 retro-mandated, 2 data points (Marcia, Bereket).

Exit codes:
    0 — allow (no unhandled error, error already acknowledged, or
        state-sensitive trigger does not apply)
    2 — block (PreToolUse only; unhandled error matches a state-sensitive
        action and acknowledgment is missing)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annunaki_log import log_pretooluse_block  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SENTINEL_DIR = REPO_ROOT / ".claude" / ".edit-error-sentinel"
SENTINEL_TTL_SECONDS = 24 * 3600  # 24 hours

# Tools that this hook records errors on (PostToolUse) and gates re-edits of
# the same file (PreToolUse).
_EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}

# Bash-command shapes that count as state-sensitive actions (artifact-state
# claims downstream of an edit). These match command-position git/gh
# invocations within any compound-command segment.
_BASH_GIT_COMMIT_RE = re.compile(
    r"(?:^|[;&|]\s*|&&\s*|\|\|\s*)\s*git\b[^;&|]*?\bcommit\b",
    re.MULTILINE,
)
_BASH_GH_COMMENT_RE = re.compile(
    r"(?:^|[;&|]\s*|&&\s*|\|\|\s*)\s*gh\s+(?:pr|issue)\s+comment\b",
    re.MULTILINE,
)

# Commands that count as a Bash-side acknowledgment of an Edit error.
# Each command, when followed by the errored path, satisfies the verification
# requirement. We require the path to appear as a token in the command, not
# just as substring of an unrelated arg.
_ACK_BASH_VERBS = ("cat", "head", "tail", "less", "grep", "ls", "wc")

# Literal acknowledgment marker in a SendMessage body or comment text.
_ACK_MARKER = "edit-error acknowledged"


# -------- Phase: response inspection (Post + Pre) -------------------------


def _is_error_response(tool_response) -> bool:
    """Return True if the tool_response indicates the call failed.

    Handles three observed shapes:
      - Top-level dict with `is_error: true`
      - Dict with `content` list; any item has `is_error: true`
      - Bash-style dict with `exit_code` non-zero (defensive; primarily this
        hook fires on Edit/Write where exit_code is irrelevant)

    Any unexpected shape returns False (advisory hook; we don't block on our
    own parse failure).
    """
    if not isinstance(tool_response, dict):
        return False
    if tool_response.get("is_error") is True:
        return True
    content = tool_response.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("is_error") is True:
                return True
    exit_code = tool_response.get("exit_code")
    if isinstance(exit_code, int) and exit_code != 0:
        return True
    return False


def _short_error_excerpt(tool_response) -> str:
    """Return up to ~200 chars of the error message for logging."""
    if not isinstance(tool_response, dict):
        return str(tool_response)[:200]
    parts: list[str] = []
    content = tool_response.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                txt = item.get("content") or item.get("text") or ""
                if isinstance(txt, str):
                    parts.append(txt)
    elif isinstance(content, str):
        parts.append(content)
    if not parts:
        for key in ("stderr", "error", "message"):
            v = tool_response.get(key)
            if isinstance(v, str) and v:
                parts.append(v)
                break
    joined = " | ".join(p for p in parts if p)
    return joined[:200] if joined else "<no error message>"


# -------- Phase: sentinel I/O ---------------------------------------------


def _session_id(input_data: dict) -> str:
    """Resolve a stable session identifier for the sentinel filename.

    Priority:
      1. `input_data["session_id"]` (Claude Code agent SDK convention)
      2. Filename stem of `input_data["transcript_path"]`
      3. Constant fallback `default` (last-resort grouping; rare)
    """
    sid = input_data.get("session_id")
    if isinstance(sid, str) and sid:
        return sid
    tpath = input_data.get("transcript_path")
    if isinstance(tpath, str) and tpath:
        try:
            return Path(tpath).stem or "default"
        except (OSError, ValueError):
            return "default"
    return "default"


def _sentinel_path(input_data: dict) -> Path:
    return SENTINEL_DIR / f"{_session_id(input_data)}.jsonl"


def _read_sentinel(path: Path) -> list[dict]:
    """Read sentinel JSONL, dropping entries older than TTL or malformed."""
    if not path.is_file():
        return []
    now = time.time()
    out: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_str = obj.get("ts", "")
                try:
                    # Parse ISO timestamp (drop Z if present).
                    iso = ts_str.replace("Z", "+00:00")
                    from datetime import datetime

                    obj_ts = datetime.fromisoformat(iso).timestamp()
                except (ValueError, ImportError):
                    obj_ts = now  # treat malformed timestamps as fresh
                if now - obj_ts > SENTINEL_TTL_SECONDS:
                    continue
                out.append(obj)
    except OSError:
        return []
    return out


def _write_sentinel(path: Path, entries: list[dict]) -> None:
    """Write entries to sentinel atomically. Empty list → remove the file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    if not entries:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        tmp.replace(path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _append_sentinel(path: Path, entry: dict) -> None:
    """Append a single entry. Used in PostToolUse fast path."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


# -------- Phase: acknowledgment scan --------------------------------------


def _bash_acks_path(command: str, path: str) -> bool:
    """True if `command` is a Bash invocation that reads/lists `path`.

    The path appears as a whitespace-bounded token (or as a quoted token's
    content) in the command, AND the command contains one of the
    acknowledgment verbs as a command-position word. Conservative: false
    positives are fine (extra ack), false negatives are fine (agent re-acks).
    """
    # Verb must appear as a word boundary token.
    if not any(re.search(rf"\b{re.escape(v)}\b", command) for v in _ACK_BASH_VERBS):
        return False
    # Path must appear (literal substring is sufficient — paths are typically
    # absolute and unlikely to false-positive in unrelated commands).
    return path in command


def _scan_transcript_for_acks(
    transcript_path: str,
    sentinel_entries: list[dict],
) -> set[int]:
    """Return indices of sentinel entries acknowledged in the transcript.

    Walks the transcript JSONL and, for each entry, looks for any of:
      - A `Read` tool_use whose `file_path` matches
      - A `Bash` tool_use whose `command` reads/lists the path
      - A SendMessage / comment-style text containing the path AND the
        literal _ACK_MARKER

    Returns a set of indices into `sentinel_entries`.
    """
    acked: set[int] = set()
    if not transcript_path:
        return acked
    p = Path(transcript_path)
    if not p.is_file():
        return acked
    # Build path → indices map for O(N+M) scanning.
    by_path: dict[str, list[int]] = {}
    for i, entry in enumerate(sentinel_entries):
        ep = entry.get("path", "")
        if ep:
            by_path.setdefault(ep, []).append(i)
    if not by_path:
        return acked
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or len(acked) == len(sentinel_entries):
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = obj.get("message") or {}
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type", "")
                    if btype == "tool_use":
                        name = block.get("name", "")
                        binput = block.get("input") or {}
                        if name == "Read":
                            fp = binput.get("file_path", "")
                            for idx in by_path.get(fp, []):
                                acked.add(idx)
                        elif name == "Bash":
                            cmd = binput.get("command", "") or ""
                            for ep, idxs in by_path.items():
                                if _bash_acks_path(cmd, ep):
                                    for idx in idxs:
                                        acked.add(idx)
                    elif btype == "text":
                        text = block.get("text", "") or ""
                        if _ACK_MARKER in text:
                            for ep, idxs in by_path.items():
                                if ep in text:
                                    for idx in idxs:
                                        acked.add(idx)
    except OSError:
        return acked
    return acked


# -------- Phase: PostToolUse handler --------------------------------------


def _post_tool_use(input_data: dict) -> None:
    """Record an Edit/Write/NotebookEdit error to the sentinel. Always exits 0."""
    tool_name = input_data.get("tool_name", "")
    if tool_name not in _EDIT_TOOLS:
        return
    tool_response = input_data.get("tool_response", {})
    if not _is_error_response(tool_response):
        return
    tool_input = input_data.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not file_path:
        return
    # Resolve to absolute path for stable matching.
    try:
        abs_path = str(Path(file_path).expanduser().resolve())
    except (OSError, RuntimeError):
        abs_path = file_path
    from datetime import datetime, timezone

    entry = {
        "path": abs_path,
        "tool": tool_name,
        "error": _short_error_excerpt(tool_response),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _append_sentinel(_sentinel_path(input_data), entry)


# -------- Phase: PreToolUse handler ---------------------------------------


def _pre_tool_use_blocks(input_data: dict) -> dict | None:
    """Decide whether to block the in-flight tool call. None to allow."""
    tool_name = input_data.get("tool_name", "")
    sentinel_path = _sentinel_path(input_data)
    entries = _read_sentinel(sentinel_path)
    if not entries:
        return None  # Fast-path: no unhandled errors, allow.

    # Prune acknowledged entries first (transcript scan). This persists across
    # tool calls so future invocations don't re-evaluate already-acked errors.
    transcript_path = input_data.get("transcript_path", "")
    acked_idxs = _scan_transcript_for_acks(transcript_path, entries)
    if acked_idxs:
        kept = [e for i, e in enumerate(entries) if i not in acked_idxs]
        _write_sentinel(sentinel_path, kept)
        entries = kept
        if not entries:
            return None

    # Determine whether THIS tool call is a state-sensitive action.
    tool_input = input_data.get("tool_input") or {}
    matching: list[dict] = []
    if tool_name in _EDIT_TOOLS:
        # Edit/Write/NotebookEdit on the same file_path → block.
        target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        if not target:
            return None
        try:
            target_abs = str(Path(target).expanduser().resolve())
        except (OSError, RuntimeError):
            target_abs = target
        matching = [e for e in entries if e.get("path") == target_abs]
    elif tool_name == "SendMessage":
        # SendMessage is a status-claim risk regardless of which file errored;
        # block on ANY unhandled error in the sentinel.
        matching = list(entries)
    elif tool_name == "Bash":
        command = tool_input.get("command", "") or ""
        if _BASH_GIT_COMMIT_RE.search(command) or _BASH_GH_COMMENT_RE.search(command):
            matching = list(entries)

    if not matching:
        return None

    paths = ", ".join(e.get("path", "?") for e in matching)
    tools = ", ".join(sorted({e.get("tool", "?") for e in matching}))
    reason = (
        f"BLOCKED: prior {tools} on {paths} returned an error that has not been "
        f"verified.\n"
        f"Verify-landed state before continuing. Any ONE of these acknowledges:\n"
        f"  1. `Read` the file at the errored path\n"
        f"  2. Bash `cat`/`head`/`tail`/`grep`/`less`/`ls`/`wc` of the errored path\n"
        f"  3. SendMessage / comment containing the path AND literal "
        f'"edit-error acknowledged"\n'
        f"\nThis hook prevents tool-error-soft-accept (W10 retro-mandated). "
        f"Sentinel: {sentinel_path}"
    )
    return {"decision": "block", "reason": reason}


# -------- Phase: dispatch --------------------------------------------------


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry point for Bash and Edit/Write/NotebookEdit.

    Both the PreToolUse Bash dispatcher (`dispatcher.py`) and the PostToolUse
    dispatcher (`post_dispatcher.py`) route tool calls through this function.

    Dispatch is `hook_event_name`-aware (with a tool_response-presence
    fallback for inputs that omit the field):

      - PreToolUse Bash             → `_pre_tool_use_blocks` (may return a block)
      - PostToolUse Edit/Write/
        NotebookEdit                → `_post_tool_use` (records sentinel)

    Other matcher/event pairs return None.

    Returns None to allow, or a block dict for PreToolUse Bash. For
    PostToolUse the return is always None (side-effect only: sentinel append).
    """
    tool_name = input_data.get("tool_name", "")
    event = input_data.get("hook_event_name", "")
    if not event:
        event = "PostToolUse" if "tool_response" in input_data else "PreToolUse"

    if event == "PostToolUse":
        if tool_name in _EDIT_TOOLS:
            _post_tool_use(input_data)
        return None

    # PreToolUse path — only Bash goes through the dispatcher for this hook
    if tool_name != "Bash":
        return None
    return _pre_tool_use_blocks(input_data)


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    # The harness signals phase via `hook_event_name` (PreToolUse / PostToolUse)
    # — fall back to detecting based on presence of `tool_response` (PostToolUse
    # always carries it; PreToolUse never does).
    event = input_data.get("hook_event_name", "")
    if not event:
        event = "PostToolUse" if "tool_response" in input_data else "PreToolUse"

    if event == "PostToolUse":
        _post_tool_use(input_data)
        sys.exit(0)

    # PreToolUse path
    result = _pre_tool_use_blocks(input_data)
    if result is None:
        sys.exit(0)
    print(json.dumps(result))
    if result.get("decision") == "block":
        log_pretooluse_block(
            "validate_edit_completion",
            (input_data.get("tool_input") or {}).get("command", "")
            or (input_data.get("tool_input") or {}).get("file_path", "")
            or (input_data.get("tool_input") or {}).get("message", ""),
            result["reason"],
            tool_name=input_data.get("tool_name", ""),
        )
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
