#!/usr/bin/env python3
"""Shared cwd-keyed consultation sentinel helper.

Generalizes the Hook 15 (`enforce_librarian_consulted`) sentinel pattern
for any future transcript-reading enforcement hook. Pattern: a skill
writes a marker file in the agent's cwd recording that it was invoked;
the hook reads the marker as a second acceptance signal beside the
transcript scan.

Background
==========

Hook 15 originally scanned the session transcript JSONL for evidence of
`/ontology-librarian` invocation. In subagent worktree sessions the
transcript-flush race left the marker absent from the file the hook reads
(see issue #169). PR #174 added a synchronous sentinel write from the
skill side so the hook never blocks on stale transcript state.

Issue #176 generalizes that sentinel into a reusable helper because the
same pattern will recur for every future transcript-reading enforcement
hook (e.g., "did /wave-kickoff run before this PR open", "did
/security-review run before merge"). Each new transcript-reading hook
would otherwise reinvent path-keying, hashing, and TTL logic; the helper
centralizes that surface.

Path scheme
===========

Sentinels live under each working directory:

    <cwd>/.claude/.consulted/<skill_name>/<sha1(abspath(cwd)+"\\n")[:16]>.marker

The directory is gitignored at the repo root. The `<skill_name>`
namespace prevents collisions across hooks (an ontology-librarian
sentinel and a wave-kickoff sentinel under the same cwd are distinct
files in distinct subdirectories).

The hash is `sha1(abspath(cwd) + "\\n")[:16]` — the trailing newline
matches the shell idiom `pwd | sha1sum | cut -c1-16` so the skill can
write the sentinel from shell and the hook can read it from Python and
both compute the same path. The 16-char truncation balances filename
brevity against collision resistance (one in 2^64).

API
===

`write_consultation_sentinel(skill_name, cwd=None) -> Path | None`
    Skill-side write. Resolves cwd (defaults to os.getcwd()), creates
    the namespaced directory, writes the marker file with an ISO8601
    timestamp + cwd. Returns the Path written, or None on OSError
    (fail-open: a broken sentinel write must not crash the skill).

`consultation_sentinel_is_fresh(cwd, skill_name, ttl_seconds=3600) -> bool`
    Hook-side read. Recomputes the hash and checks the marker's mtime
    against `ttl_seconds`. Returns False on missing/stale sentinel,
    True if fresh, False on OSError (fail-closed for the freshness
    check itself; callers should fail OPEN on the broader "can we
    even read the filesystem" question per their own policy).

`consultation_sentinel_path(cwd, skill_name) -> Path`
    Pure function returning the canonical path. Same formula on both
    sides. Useful for tests that want to write a sentinel manually
    without going through `write_consultation_sentinel`.

`cwd_sentinel_hash(cwd) -> str`
    The 16-char sha1 prefix. Exported because Hook 15 tests pin the
    shell/Python parity property against the legacy hash name; the
    hook re-exports this under the legacy name for backward
    compatibility.

Promotion provenance
====================

- Hook 15 (#150 + #169) — original sentinel introduction.
- PR #174 — synchronous sentinel write from skill side.
- Issue #176 — extract into reusable helper for future transcript-reading
  hooks. Filed by Nadia Khoury during PR #174 review.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

# Default freshness window. The Hook 15 sentinel uses 1 hour; future hooks
# may want different TTLs (a longer-lived /security-review consultation might
# be 24h; a shorter-lived /pre-merge-check might be 5min). Pass `ttl_seconds`
# explicitly when calling `consultation_sentinel_is_fresh` to override.
DEFAULT_TTL_SECONDS = 3600

# Sentinel directory parent. Skill-side writes and hook-side reads both
# compose this with `<skill_name>/<hash>.marker`. Kept relative so the
# helper is cwd-rooted (each worktree has its own .claude/.consulted/).
SENTINEL_PARENT_DIR = ".claude/.consulted"


def cwd_sentinel_hash(cwd: str) -> str:
    """Return the first 16 hex chars of sha1(abspath(cwd) + "\\n").

    Trailing newline matches the shell idiom `pwd | sha1sum | cut -c1-16`,
    where `pwd` always emits a trailing newline before `sha1sum` consumes
    its stdin. Python's hashlib does not insert that newline, so callers
    that want shell parity must append it explicitly — which we do here.

    OSError / ValueError on path resolution fall back to the raw input so
    the helper never raises on weird inputs (e.g., a cwd that's been
    deleted underneath us).
    """
    try:
        abspath = os.path.abspath(os.path.expanduser(cwd))
    except (OSError, ValueError):
        abspath = cwd
    digest = hashlib.sha1((abspath + "\n").encode("utf-8")).hexdigest()
    return digest[:16]


def consultation_sentinel_path(cwd: str, skill_name: str) -> Path:
    """Return the canonical sentinel path for (cwd, skill_name).

    Path: `<cwd>/.claude/.consulted/<skill_name>/<sha1(cwd)[:16]>.marker`.

    Pure function — no filesystem access. Tests that want to write a
    sentinel manually (without going through `write_consultation_sentinel`)
    should call this to compute the expected path.
    """
    try:
        abspath = os.path.abspath(os.path.expanduser(cwd))
    except (OSError, ValueError):
        abspath = cwd
    return Path(abspath) / SENTINEL_PARENT_DIR / skill_name / f"{cwd_sentinel_hash(abspath)}.marker"


def write_consultation_sentinel(skill_name: str, cwd: str | None = None) -> Path | None:
    """Skill-side: write a sentinel marker for `skill_name` keyed by `cwd`.

    Creates the namespaced directory if missing and writes a single-line
    marker containing an ISO8601 timestamp and the resolved cwd. Returns
    the Path written, or None on OSError (a broken sentinel write must
    not crash the skill — the transcript-scan fallback still applies on
    the hook side).

    `cwd` defaults to `os.getcwd()` when None. Skills writing from a
    specific worktree should pass the worktree path explicitly.
    """
    resolved_cwd = cwd if cwd is not None else os.getcwd()
    sentinel = consultation_sentinel_path(resolved_cwd, skill_name)
    try:
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            abspath = os.path.abspath(os.path.expanduser(resolved_cwd))
        except (OSError, ValueError):
            abspath = resolved_cwd
        sentinel.write_text(f"{timestamp} {abspath}\n", encoding="utf-8")
        return sentinel
    except OSError:
        return None


def consultation_sentinel_is_fresh(
    cwd: str, skill_name: str, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> bool:
    """Hook-side: True iff a fresh sentinel for (cwd, skill_name) exists.

    Fresh = the marker file's mtime is within `ttl_seconds` of now.
    Returns False if the sentinel is absent, stale (older than the TTL),
    or unreadable. Negative-mtime (future-dated) marker files are also
    treated as not-fresh — a future-dated file is either a clock-skew
    bug or a malicious antedate and shouldn't unlock the hook.

    Note: the previous Hook 15 implementation FAIL-OPENed on OSError
    when stat'ing the sentinel (returned True). That behavior is
    preserved by the legacy shim in `enforce_librarian_consulted`
    rather than here — this helper returns False on any read error so
    callers can choose their own fail-open vs fail-closed policy.
    Callers that want the legacy fail-open behavior should catch the
    False return alongside their own OSError tolerance.
    """
    if not cwd or not skill_name:
        return False
    sentinel = consultation_sentinel_path(cwd, skill_name)
    try:
        if not sentinel.exists():
            return False
        age = _now_seconds() - sentinel.stat().st_mtime
        return 0 <= age <= ttl_seconds
    except OSError:
        return False


def find_attesting_sentinel(
    cwd: str, skill_name: str, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> Path | None:
    """Tolerant-read scan: return ANY fresh sentinel whose body cwd matches.

    Distinct from `consultation_sentinel_is_fresh` (which only checks the
    canonical hash-filename path). This function scans every `*.marker`
    file under `<cwd>/.claude/.consulted/<skill_name>/` and accepts any
    fresh marker whose second whitespace-delimited body token resolves
    (via realpath) to the same path as `cwd`.

    Rationale (#429): two real markers found in cedric-0066-dark-mode-tokens
    used inconsistent hash formulas — one with the canonical
    sha1(cwd + "\\n") and one with sha1(cwd) (no newline). The latter is
    a documented-formula deviation by an ad-hoc writer (likely an LLM
    one-liner that forgot the trailing `\\n`). The canonical-hash read
    path ignored it. This function rescues such markers as long as their
    BODY records the correct cwd — defense in depth, not a path-scheme
    fork. The canonical write path stays single-source via
    `consultation_sentinel_path`.

    Returns the Path of the matching marker, or None if no fresh
    body-cwd-matching marker is found. Body-cwd match is exact-realpath:
    we resolve both `cwd` and the body's cwd token through
    `os.path.realpath(os.path.expanduser(...))` so symlink hops and
    `~/` expansions don't mask matches.

    Fail-closed on OSError — returns None rather than raising. Callers
    that want fail-open semantics wrap accordingly (Hook 15 does so).
    """
    if not cwd or not skill_name:
        return None
    try:
        target_real = os.path.realpath(os.path.expanduser(cwd))
    except (OSError, ValueError):
        return None
    try:
        skill_dir = Path(target_real) / SENTINEL_PARENT_DIR / skill_name
        if not skill_dir.is_dir():
            return None
        now = _now_seconds()
        for marker in skill_dir.glob("*.marker"):
            try:
                age = now - marker.stat().st_mtime
                if not (0 <= age <= ttl_seconds):
                    continue
                body = marker.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Body format: "<iso8601> <cwd>\n". Split into at most 2
            # tokens so a cwd containing spaces still resolves cleanly.
            parts = body.strip().split(None, 1)
            if len(parts) < 2:
                continue
            body_cwd = parts[1].strip()
            try:
                body_real = os.path.realpath(os.path.expanduser(body_cwd))
            except (OSError, ValueError):
                continue
            if body_real == target_real:
                return marker
    except OSError:
        return None
    return None


def _now_seconds() -> float:
    """Indirection for test injection. Real time defaults; tests can
    monkeypatch this to control freshness comparisons without touching
    file mtimes."""
    import time

    return time.time()
