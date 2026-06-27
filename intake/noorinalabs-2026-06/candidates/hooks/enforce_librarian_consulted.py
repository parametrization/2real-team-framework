#!/usr/bin/env python3
"""PreToolUse hook: Advise (not block) when /ontology-librarian was not consulted.

Per CLAUDE.md § Ontology:
  "Every agent — orchestrator, team member, or one-off — SHOULD run
   /ontology-librarian {topic} before making code changes."

This hook surfaces that charter guidance. It fires before Edit/Write/NotebookEdit
and scans the current session's transcript (and a cwd-keyed sentinel) for
evidence of a librarian consultation. If none is found, it emits an **advisory**
`systemMessage` warning — the edit is **allowed** to proceed.

Advisory, not blocking (softened in #857)
=========================================

This hook was originally a HARD BLOCK (exit 2, deny the edit) — see #150. It was
softened to advisory by #857 (P6W17, parent #820 / C×T2 decision). Rationale:

  The hard block existed to guarantee an agent had loaded *current ontology
  context* — chiefly the **structural** layer (module/service topology) — before
  editing code. That layer is now **generated** (committed `ontology/structural/`,
  owned generator #855) and therefore *always current by regeneration* rather than
  hand-resolved and potentially stale. The staleness risk the block defended
  against no longer exists for the structural layer, so a hard pre-Edit block is
  heavier than warranted (cf. memory `feedback_safety_direction_over_ux_friction`:
  soften a guard only once the safety it provided is demonstrably redundant — it is
  here, because structural context is regenerated, not stale).

  The hand-curated **semantic overlay** (`domain.yaml` / `services.yaml` /
  `conventions.md` / `*.md`) is still valuable to consult, so the advisory warning
  remains — it nudges without gating. The librarian is still the right first move
  for understanding intent/topology; it is simply no longer a blocking precondition.

Input Language
==============

Fires on:
    PreToolUse Edit
    PreToolUse Write
    PreToolUse NotebookEdit

Matches (tool_input.file_path or tool_input.notebook_path):
    Any file path in the parameters of the above tools, EXCEPT paths
    matching one of the allow-list rules below. The hook reads the
    transcript file whose path is passed as `input_data["transcript_path"]`
    (Claude Code agent SDK convention).

Does NOT warn (allow-listed paths — no librarian expected):
    /tmp/**                — out-of-repo scratch (issue body drafts, etc.)
    **/memory/*.md         — project memory files written by handoff/retro
    **/MEMORY.md           — auto-memory index
    ~/.claude/**           — user-level config, not source code
    .claude/annunaki/*     — error log (hook-managed, not hand-edited code)

Stance on meta-files (.claude/team/feedback_log.md, trust_matrix.md, etc.):
    ADVISES librarian. These ARE project-state artifacts that the ontology
    tracks and conventions describe, so the nudge still fires for them.

Transcript shape expected (JSONL, one object per line):
    Form A (string content):
        {"type": "user",
         "message": {"role": "user",
                     "content": "<command-name>/ontology-librarian</command-name>..."}}
    Form B (list content with text block):
        {"type": "user",
         "message": {"role": "user",
                     "content": [{"type": "text",
                                  "text": "/ontology-librarian ..."}]}}
    Form C (assistant Skill tool_use):
        {"type": "assistant",
         "message": {"role": "assistant",
                     "content": [{"type": "tool_use",
                                  "name": "Skill",
                                  "input": {"skill": "ontology-librarian",
                                            "args": "..."}}]}}

Detection signals (any ONE suppresses the advisory):
    1. A `user` line whose text contains the literal substring
       "/ontology-librarian" OR "<command-name>/ontology-librarian".
    2. An `assistant` `tool_use` block with name == "Skill" and
       input.skill == "ontology-librarian".
    3. A fresh cwd-keyed sentinel file (see below) — fallback for the
       transcript-flush race in subagent worktree sessions.

Sentinel fallback (second acceptance signal, added for #169):
    The librarian skill writes a sentinel file on invocation at:
        <cwd>/.claude/.consulted/ontology-librarian/<hash>.marker
    where <hash> is the first 16 hex chars of sha1(abspath(cwd)). The hook
    accepts the marker if its mtime is within SENTINEL_TTL_SECONDS (1 hour)
    of now AND the cwd reported in `input_data["cwd"]` matches the hashed
    cwd. Either the transcript scan OR a fresh matching sentinel suppresses
    the advisory.

    Rationale (#169): subagents in worktree sessions repeatedly had
    /ontology-librarian Skill tool_use entries ignored by the transcript
    scan — the transcript path the hook reads either lagged the flush or
    pointed at the parent orchestrator's file. The sentinel is written
    synchronously by the skill and doesn't depend on transcript plumbing.

    Cwd-keyed design: each worktree has a distinct cwd, hence a distinct
    sentinel. This preserves the charter requirement that each agent invoke
    the librarian ITSELF — the orchestrator in the main repo cwd and a
    subagent in a worktree cwd do not share a sentinel.

Scope of scan:
    Entire transcript file (a Claude Code session == one transcript). Each
    new session starts a fresh transcript, so a previous session's
    invocation cannot carry over. Sentinel TTL of 1 hour bounds
    cross-session carryover on the sentinel path.

Exit codes (per Claude Code hook convention):
    0 — ALWAYS. This is an advisory hook; it never blocks an edit. When the
        librarian has not been consulted it prints a `systemMessage` warning
        to stdout (and still exits 0).

Enforcement artifact for: noorinalabs/noorinalabs-main#150 (original hard block)
Softened to advisory by:  noorinalabs/noorinalabs-main#857 (#820 / C×T2)
Sentinel fallback for:    noorinalabs/noorinalabs-main#169
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _consultation_sentinel import (  # noqa: E402
    DEFAULT_TTL_SECONDS,
    SENTINEL_PARENT_DIR,
    consultation_sentinel_path,
    cwd_sentinel_hash,
    find_attesting_sentinel,
)

# Sentinel-fallback config — delegated to `_consultation_sentinel` per #176.
# These module-level names are preserved as back-compat shims for tests that
# pre-#176 referenced `hook.SENTINEL_DIR_NAME` / `hook._cwd_sentinel_hash` /
# `hook.SENTINEL_TTL_SECONDS` directly. The values are now derived from the
# shared helper so behavior cannot drift between the two.
_SKILL_KEY = "ontology-librarian"
SENTINEL_DIR_NAME = f"{SENTINEL_PARENT_DIR}/{_SKILL_KEY}"
SENTINEL_TTL_SECONDS = DEFAULT_TTL_SECONDS  # 1 hour, inherits from helper

# Tool matchers this hook advises on.
_MATCHED_TOOLS = {"Edit", "Write", "NotebookEdit"}

# Detection signals in transcript.
_SLASH_CMD_MARKERS = (
    "<command-name>/ontology-librarian",
    "/ontology-librarian",
)
_SKILL_NAME = "ontology-librarian"

# Allow-listed path prefixes / suffix patterns (no librarian advisory).
# Absolute-path globs; matched against the resolved, absolute path.
_ALLOW_ABS_PREFIXES = (
    "/tmp/",
    os.path.expanduser("~/.claude/"),
)

_ALLOW_PATH_SUFFIXES = ("MEMORY.md",)

# Directory segments that mark "not source code".
_ALLOW_PATH_CONTAINS = (
    "/memory/",
    "/.claude/annunaki/",
)


def _is_allowlisted(file_path: str) -> bool:
    """Return True if the path is exempt from the librarian advisory."""
    if not file_path:
        # No file_path means we cannot evaluate; default to advising.
        return False

    try:
        abspath = os.path.abspath(os.path.expanduser(file_path))
    except (OSError, ValueError):
        abspath = file_path

    # Absolute-prefix allow-list.
    for prefix in _ALLOW_ABS_PREFIXES:
        if abspath.startswith(prefix):
            return True

    # Suffix allow-list (exact filename, e.g. MEMORY.md).
    basename = os.path.basename(abspath)
    for suffix in _ALLOW_PATH_SUFFIXES:
        if basename == suffix:
            return True

    # Directory-segment allow-list.
    for seg in _ALLOW_PATH_CONTAINS:
        if seg in abspath:
            return True

    return False


def _content_has_librarian_signal(content) -> bool:
    """Scan a single `message.content` value for librarian signals.

    Content may be:
      - str: look for slash-command markers.
      - list[dict]: iterate blocks; check text blocks and tool_use blocks.
    """
    if isinstance(content, str):
        for marker in _SLASH_CMD_MARKERS:
            if marker in content:
                return True
        return False

    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")
            if btype == "text":
                text = block.get("text", "")
                for marker in _SLASH_CMD_MARKERS:
                    if marker in text:
                        return True
            elif btype == "tool_use":
                if block.get("name") == "Skill":
                    skill = (block.get("input") or {}).get("skill", "")
                    if skill == _SKILL_NAME:
                        return True

    return False


def _transcript_has_librarian(transcript_path: str) -> bool:
    """Return True if the transcript shows a librarian consultation."""
    if not transcript_path:
        return False

    try:
        p = Path(transcript_path)
        if not p.exists():
            return False
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = obj.get("type", "")
                if t not in ("user", "assistant"):
                    continue
                msg = obj.get("message") or {}
                content = msg.get("content", "")
                if _content_has_librarian_signal(content):
                    return True
    except OSError:
        # If we cannot read the transcript, suppress the advisory — do not
        # nag on our own inability to read state. (Mirrors the original
        # fail-open stance; now even cheaper since nothing is blocked.)
        return True

    return False


def _cwd_sentinel_hash(cwd: str) -> str:
    """Return the first 16 hex chars of sha1(abspath(cwd) + "\\n").

    Back-compat shim: delegates to `_consultation_sentinel.cwd_sentinel_hash`.
    The trailing-newline hash matches the shell idiom
    `pwd | sha1sum | cut -c1-16` so the librarian skill (which writes the
    sentinel from shell) and the hook (which reads it from Python) compute
    the same path.
    """
    return cwd_sentinel_hash(cwd)


def _sentinel_attests_librarian(cwd: str) -> bool:
    """Return True if a fresh cwd-keyed sentinel exists for this cwd.

    Fresh = mtime within SENTINEL_TTL_SECONDS of now. Absent, stale, or
    unreadable sentinels return False (do not attest). OSError paths fail
    open (return True) to match the transcript-scan stance.

    Per #176: the path is `.claude/.consulted/ontology-librarian/<hash>.marker`
    (was `.claude/.librarian-consulted/<hash>.marker`); the path move
    namespaces by skill so future transcript-reading hooks can reuse the
    same sentinel directory without colliding. The helper computes the
    canonical path; this function wraps it with Hook 15's specific
    fail-OPEN-on-OSError semantics.

    Per #429: when the canonical-hash marker is absent, falls back to a
    tolerant-read scan (`find_attesting_sentinel`) that accepts any fresh
    marker whose BODY records this same realpath cwd.
    """
    if not cwd:
        return False

    import time

    try:
        sentinel = consultation_sentinel_path(cwd, _SKILL_KEY)
        if sentinel.exists():
            age = time.time() - sentinel.stat().st_mtime
            if 0 <= age <= SENTINEL_TTL_SECONDS:
                return True
        # Canonical-path miss → tolerant body-cwd scan (#429).
        if find_attesting_sentinel(cwd, _SKILL_KEY, SENTINEL_TTL_SECONDS) is not None:
            return True
        return False
    except OSError:
        # Fail open — do not nag on our own inability to stat.
        return True


_ADVISORY_MESSAGE = (
    "ADVISORY: /ontology-librarian was not consulted earlier in this session "
    "before this code edit.\n"
    'Per CLAUDE.md § Ontology: "Every agent — orchestrator, team member, or one-off — '
    'SHOULD run /ontology-librarian {topic} before making code changes."\n'
    "This is a non-blocking reminder (the edit will proceed). Consulting the "
    "librarian first helps you load the hand-curated semantic overlay (domain "
    "entities, service topology, conventions) for the area you are touching."
)


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry point.

    Returns None to allow silently (no advisory needed); returns a dict with a
    `systemMessage` advisory when the librarian was not consulted. The advisory
    NEVER blocks — the caller (`main`) always exits 0.
    """
    tool_name = input_data.get("tool_name", "")
    if tool_name not in _MATCHED_TOOLS:
        return None

    tool_input = input_data.get("tool_input") or {}
    # Edit/Write use file_path; NotebookEdit uses notebook_path.
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""

    if _is_allowlisted(file_path):
        return None

    # Primary signal: transcript scan.
    transcript_path = input_data.get("transcript_path", "")
    if _transcript_has_librarian(transcript_path):
        return None

    # Fallback signal: cwd-keyed sentinel (see docstring § "Sentinel fallback").
    # Survives the transcript-flush race that affected subagents in worktrees (#169).
    cwd = input_data.get("cwd", "")
    if _sentinel_attests_librarian(cwd):
        return None

    return {"systemMessage": _ADVISORY_MESSAGE}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result and result.get("systemMessage"):
        print(json.dumps({"systemMessage": result["systemMessage"]}))
    # Advisory hook: always allow the edit to proceed.
    sys.exit(0)


if __name__ == "__main__":
    main()
