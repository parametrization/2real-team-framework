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
or the complete new file, never a truncated in-between. After the replace we also
fsync the *parent directory* so the rename's new directory entry is durable across a
power loss — fsyncing the temp file persists its bytes, but not the entry that names
them under the target, so a crash right after the rename could otherwise lose the
file on some filesystems. The dir-fsync is best-effort / fail-open: platforms that
cannot open a directory for fsync (notably Windows) skip it silently and never crash
the install. Stdlib-only.

Public API
==========
``atomic_write_text(path, text, *, encoding="utf-8") -> None``
    Create ``path``'s parent if needed, write ``text`` to a temp file in the same
    directory (so the final rename stays on one filesystem and is therefore
    atomic), then ``os.replace`` it into place and fsync the parent directory so the
    rename is durable. The temp file is removed on any error before the replace, so a
    failed write leaves neither a stray temp nor a damaged target.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _fsync_dir(directory: Path) -> None:
    """Best-effort fsync of ``directory`` so a rename into it survives a power loss.

    ``os.replace`` puts the new name in the directory, but that directory entry may live
    only in the OS cache until the *directory itself* is fsynced; a crash in that window can
    lose the rename even though the file's bytes were fsynced. Opening the dir and fsyncing
    its fd flushes the entry. Fail-open by contract: platforms/filesystems that cannot open a
    directory for reading (notably Windows) or cannot fsync one are a silent no-op — hard
    durability is best-effort and must never crash the install.
    """
    try:
        dir_fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return  # e.g. Windows: cannot open a directory as a file descriptor
    try:
        os.fsync(dir_fd)
    except OSError:
        pass  # some filesystems reject fsync on a directory fd — durability stays best-effort
    finally:
        os.close(dir_fd)


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
    # Durably persist the rename's directory entry (best-effort; never crashes the install).
    _fsync_dir(path.parent)
