"""Tests for the standalone ``restore`` command (#265/#273).

``restore`` recovers a repo's PRE-INSTALL originals that an install displaced/overwrote, driven
by the reversible manifest (#108) and the installer's ``.bak`` backups — WITHOUT removing the
framework's own install set (that is ``uninstall``'s job). Coverage:

* **Round-trip, BOTH directions** — the headline AC: a moved/backed-up file (an archived
  ``.claude/`` under ``.claude-backups/<UTC>/``) AND a modified file (a rewritten ``CLAUDE.md``
  whose original the installer kept as ``CLAUDE.md.bak``) both come back byte-identical.
* **Dry-run preview accuracy** — the plan lists EXACTLY what a live run restores/reverts, and
  writes nothing.
* **No mutation without consent** — a non-TTY run without ``--non-interactive`` refuses and leaves
  the tree untouched.
* Idempotency / clean no-op on a repo with nothing to recover.

Stdlib + pytest only; everything runs under ``tmp_path``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_INSTALL = _FRAMEWORK_ROOT / "install"
_RESTORE = _INSTALL / "restore.py"
if str(_INSTALL) not in sys.path:
    sys.path.insert(0, str(_INSTALL))

import repo_space  # noqa: E402
import restore  # noqa: E402


# --------------------------------------------------------------------------- helpers


def _run_restore(d: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_RESTORE), str(d), *args],
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )


def _seed_moved_asset(root: Path) -> bytes:
    """Simulate the *archive* disposition: an original ``.claude/`` MOVED to a backup dir.

    Creates a pre-existing ``.claude/`` with distinctive content, archives it via
    ``repo_space.archive_assets`` (the exact install path), then lays a fresh framework-ish
    ``.claude/`` where it stood. Returns the original charter bytes for a byte-identity assert.
    """
    claude = root / ".claude"
    (claude / "team").mkdir(parents=True)
    original = b"# ORIGINAL charter (pre-install)\n"
    (claude / "team" / "charter.md").write_bytes(original)
    repo_space.archive_assets(root)  # MOVES .claude/ into .claude-backups/<UTC>/ + manifest
    assert not claude.exists()
    # A fresh install now sits where the original was.
    (claude / "team").mkdir(parents=True)
    (claude / "team" / "charter.md").write_bytes(b"# FRESH framework charter\n")
    return original


def _seed_modified_file(root: Path) -> bytes:
    """Simulate an in-place *modified* file: original kept as ``CLAUDE.md.bak``, fresh written."""
    original = b"# ORIGINAL repo instructions (pre-install)\n"
    (root / "CLAUDE.md.bak").write_bytes(original)  # what the installer's rename left behind
    (root / "CLAUDE.md").write_bytes(b"# FRESH framework CLAUDE.md\n")
    return original


# --------------------------------------------------------------- round-trip, both directions


def test_round_trip_restores_both_directions(tmp_path: Path):
    """The headline AC: a moved/backed-up file AND a modified file both restore byte-identical."""
    moved_original = _seed_moved_asset(tmp_path)
    modified_original = _seed_modified_file(tmp_path)

    r = _run_restore(tmp_path, "--non-interactive")
    assert r.returncode == 0, r.stderr

    # (a) moved/backed-up: the archived original .claude/ is back, byte-identical.
    assert (tmp_path / ".claude" / "team" / "charter.md").read_bytes() == moved_original
    # (b) modified: CLAUDE.md reverted to the pre-install original from its .bak.
    assert (tmp_path / "CLAUDE.md").read_bytes() == modified_original
    # the spent .bak original was moved back (not left as a stray sibling).
    assert not (tmp_path / "CLAUDE.md.bak").exists()
    # the emptied backup container was pruned.
    assert not (tmp_path / repo_space.BACKUPS_DIRNAME).exists()


def test_plan_sees_both_directions(tmp_path: Path):
    """The resolved plan enumerates the archived member AND the .bak revert before any mutation."""
    _seed_moved_asset(tmp_path)
    _seed_modified_file(tmp_path)

    plan = restore.plan_restore(tmp_path)
    assert plan.archived == [".claude"]
    assert [rev.target_rel for rev in plan.reverts] == ["CLAUDE.md"]
    assert not plan.is_empty


# ---------------------------------------------------------------------- dry-run preview accuracy


def test_dry_run_previews_and_writes_nothing(tmp_path: Path):
    """--dry-run names exactly what a live run would restore/revert and mutates nothing."""
    _seed_moved_asset(tmp_path)
    _seed_modified_file(tmp_path)
    fresh_charter = (tmp_path / ".claude" / "team" / "charter.md").read_bytes()
    fresh_claude = (tmp_path / "CLAUDE.md").read_bytes()

    r = _run_restore(tmp_path, "--dry-run")
    assert r.returncode == 0, r.stderr
    assert ".claude" in r.stdout and "CLAUDE.md" in r.stdout

    # Nothing changed: the fresh files and the backups are all still in place.
    assert (tmp_path / ".claude" / "team" / "charter.md").read_bytes() == fresh_charter
    assert (tmp_path / "CLAUDE.md").read_bytes() == fresh_claude
    assert (tmp_path / "CLAUDE.md.bak").exists()
    assert repo_space.find_latest_archive(tmp_path) is not None


# ------------------------------------------------------------------- no mutation without consent


def test_non_tty_without_flag_refuses(tmp_path: Path):
    """A non-TTY run without --non-interactive refuses and leaves everything untouched."""
    _seed_moved_asset(tmp_path)
    modified_original = _seed_modified_file(tmp_path)
    fresh_claude = (tmp_path / "CLAUDE.md").read_bytes()

    r = _run_restore(tmp_path)  # stdin is DEVNULL -> not a TTY, no --non-interactive
    assert r.returncode == 1
    assert "refusing" in r.stderr.lower()

    # Untouched: fresh CLAUDE.md still present, original still parked in its .bak, archive intact.
    assert (tmp_path / "CLAUDE.md").read_bytes() == fresh_claude
    assert (tmp_path / "CLAUDE.md.bak").read_bytes() == modified_original
    assert repo_space.find_latest_archive(tmp_path) is not None


# ------------------------------------------------------------------------------- no-op / idempotent


def test_nothing_to_restore_is_clean_noop(tmp_path: Path):
    """A repo with no archive and no .bak originals is a clean exit-0 no-op."""
    r = _run_restore(tmp_path, "--non-interactive")
    assert r.returncode == 0, r.stderr
    assert "nothing to restore" in r.stdout.lower()


def test_restore_is_idempotent(tmp_path: Path):
    """Re-running after a successful restore finds nothing left to do (clean no-op)."""
    _seed_moved_asset(tmp_path)
    _seed_modified_file(tmp_path)
    assert _run_restore(tmp_path, "--non-interactive").returncode == 0

    r2 = _run_restore(tmp_path, "--non-interactive")
    assert r2.returncode == 0, r2.stderr
    assert "nothing to restore" in r2.stdout.lower()
