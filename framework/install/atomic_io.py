#!/usr/bin/env python3
"""Atomic text-file writes for consent-gated installer writes (#145).

Shared by the user-level (#107) and repo-level (#108) install paths — the write
primitive both settle on. Writing a settings / manifest file with a plain
``path.write_text`` truncates the target to zero bytes first, so a crash or
interrupt mid-write can leave a corrupt, partially-written file. Recoverable from
a backup, but the write itself should never be able to strand a half-file.

``atomic_write_text`` writes the full contents to a uniquely-named temp file in
the SAME directory, flushes + fsyncs it, then ``os.replace``s it onto the target.
``os.replace`` is an atomic rename on POSIX (and same-volume on Windows), so any
concurrent reader — and any post-crash observer — sees either the old file intact
or the complete new file, never a truncated in-between. Stdlib-only.

Public API
==========
``atomic_write_text(path, text, *, encoding="utf-8") -> None``
    Create ``path``'s parent if needed, write ``text`` to a temp file in the same
    directory (so the final rename stays on one filesystem and is therefore
    atomic), then ``os.replace`` it into place. The temp file is removed on any
    error before the replace, so a failed write leaves neither a stray temp nor a
    damaged target.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path | str, text: str, *, encoding: str = "utf-8") -> None:
    """Atomically write ``text`` to ``path`` (temp file in the same dir + ``os.replace``)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)  # atomic rename onto the target (same filesystem)
    except BaseException:
        # Never leave a stray temp file behind; the target is untouched until replace.
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
