#!/usr/bin/env python3
"""Timestamped, restorable backups for consent-gated installer writes.

Part of the reusable user-space install toolkit introduced for #107 (consented
user-level install) and reused by #108 (repo-level pattern). Stdlib-only, no deps.

Public API
==========
``backup_file(path) -> Optional[Path]``
    Copy ``path`` to a timestamped sibling ``<name>.<UTC-stamp>.bak`` and return the
    backup path. **No-op returning ``None`` if ``path`` does not exist** — there is
    nothing to back up before a first-time write. The copy preserves mode + mtime
    (``shutil.copy2``), so restoring is a plain copy of the ``.bak`` back over the
    original. If a backup for the same second already exists, a numeric suffix is
    added so an existing backup is never clobbered.

Contract notes for callers (#108)
---------------------------------
* Deliberately **strict**: a real ``OSError`` while copying propagates, so a failed
  backup surfaces *before* the amend write rather than leaving the caller to write
  over an un-backed-up file. Guard the missing-source case with the ``None`` return,
  not with a try/except around this call.
* The returned path is stable and self-describing; nothing here deletes or prunes
  old backups (restorability over tidiness).
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path


def backup_file(path: Path | str, *, now: datetime | None = None) -> Path | None:
    """Back up ``path`` to a timestamped ``.bak`` sibling; ``None`` if it is absent.

    ``now`` is injectable purely for deterministic tests; production callers omit it
    and get a UTC wall-clock stamp.
    """
    path = Path(path)
    if not path.exists():
        return None
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    candidate = path.with_name(f"{path.name}.{stamp}.bak")
    n = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.{stamp}.{n}.bak")
        n += 1
    shutil.copy2(path, candidate)
    return candidate
