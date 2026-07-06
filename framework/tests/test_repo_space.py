"""Tests for repo-level consent + backup/archive/restore (#108) and atomic writes (#145).

Everything runs under ``tmp_path`` — the real repo is never touched. Covers:

* archive: existing repo Claude assets are MOVED out of Claude's load scope
  (``.claude-backups/<UTC>/``, NOT under ``.claude/``), with a restore manifest.
* restore: archived assets come back byte-identical; a present target is a conflict
  unless ``overwrite=True``.
* the KEY round-trip AC: install → archive existing → assert out-of-scope → restore
  → original state byte-identical.
* disposition + consent: non-interactive / non-TTY take the safe non-destructive
  (amend) path; archive is only reached on explicit interactive consent.
* #145 atomic write: the shared write path is temp-file + ``os.replace``; an interrupt
  mid-write can never leave a truncated target (proven for BOTH repo_space and the
  reused user_space path).

Stdlib + pytest only.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_INSTALL = _FRAMEWORK_ROOT / "install"
if str(_INSTALL) not in sys.path:
    sys.path.insert(0, str(_INSTALL))

import atomic_io  # noqa: E402
import consent as consent_mod  # noqa: E402
import repo_space  # noqa: E402
import user_space  # noqa: E402


# ------------------------------------------------------------------- helpers / fixtures


def _seed_repo(root: Path) -> dict[str, bytes]:
    """Create a repo with existing .claude/ (nested) + CLAUDE.md; return a byte snapshot."""
    claude = root / ".claude"
    (claude / "team").mkdir(parents=True)
    (claude / "settings.json").write_text('{"hooks": {"old": 1}}\n', encoding="utf-8")
    (claude / "team" / "charter.md").write_text("# my charter\n", encoding="utf-8")
    (root / "CLAUDE.md").write_text("# repo instructions\n", encoding="utf-8")
    return _snapshot(root, (".claude", "CLAUDE.md"))


def _snapshot(root: Path, names: tuple[str, ...]) -> dict[str, bytes]:
    """Map every file under each named asset -> its bytes (deep, order-independent)."""
    snap: dict[str, bytes] = {}
    for name in names:
        p = root / name
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file():
                    snap[f.relative_to(root).as_posix()] = f.read_bytes()
        elif p.is_file():
            snap[name] = p.read_bytes()
    return snap


# --------------------------------------------------------------------------- detection


def test_has_existing_assets(tmp_path: Path) -> None:
    assert repo_space.has_existing_assets(tmp_path) is False
    (tmp_path / "CLAUDE.md").write_text("x", encoding="utf-8")
    assert repo_space.has_existing_assets(tmp_path) is True


# ----------------------------------------------------------------------------- archive


def test_archive_moves_assets_out_of_claude_scope(tmp_path: Path) -> None:
    """Existing assets are relocated OUT of Claude's scope, with a manifest; originals gone."""
    _seed_repo(tmp_path)
    result = repo_space.archive_assets(tmp_path)

    assert result.archived is True
    assert set(result.moved) == {".claude", "CLAUDE.md"}
    # Originals are gone from the repo root (moved, not copied).
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / "CLAUDE.md").exists()
    # The archive is under .claude-backups/, NOT under .claude/ and not named .claude*.
    assert result.archive_dir.parent.name == repo_space.BACKUPS_DIRNAME
    assert repo_space.BACKUPS_DIRNAME != ".claude"
    assert ".claude/" not in result.archive_dir.as_posix().replace(
        f"{repo_space.BACKUPS_DIRNAME}/", ""
    )
    # Archived content is intact + a manifest describes what to restore.
    assert (result.archive_dir / ".claude" / "settings.json").read_text() == '{"hooks": {"old": 1}}\n'
    manifest = json.loads(result.manifest_path.read_text())
    assert {e["name"] for e in manifest["entries"]} == {".claude", "CLAUDE.md"}
    assert {e["type"] for e in manifest["entries"]} == {"dir", "file"}


def test_archive_noop_when_nothing_present(tmp_path: Path) -> None:
    result = repo_space.archive_assets(tmp_path)
    assert result.archived is False
    assert result.archive_dir is None
    assert not (tmp_path / repo_space.BACKUPS_DIRNAME).exists()


def test_archive_dir_is_non_clobbering(tmp_path: Path) -> None:
    """Two archives at the same UTC second never overwrite each other."""
    from datetime import datetime, timezone

    fixed = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)
    (tmp_path / "CLAUDE.md").write_text("v1", encoding="utf-8")
    a1 = repo_space.archive_assets(tmp_path, now=fixed)
    (tmp_path / "CLAUDE.md").write_text("v2", encoding="utf-8")
    a2 = repo_space.archive_assets(tmp_path, now=fixed)
    assert a1.archive_dir != a2.archive_dir
    assert (a1.archive_dir / "CLAUDE.md").read_text() == "v1"  # first archive intact
    assert (a2.archive_dir / "CLAUDE.md").read_text() == "v2"


# ----------------------------------------------------------------------------- restore


def test_restore_brings_assets_back_byte_identical(tmp_path: Path) -> None:
    original = _seed_repo(tmp_path)
    archived = repo_space.archive_assets(tmp_path)

    result = repo_space.restore_assets(tmp_path, archived.archive_dir)

    assert set(result.restored) == {".claude", "CLAUDE.md"}
    assert not result.conflicts
    assert _snapshot(tmp_path, (".claude", "CLAUDE.md")) == original  # byte-for-byte


def test_restore_refuses_to_clobber_without_overwrite(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    archived = repo_space.archive_assets(tmp_path)
    # A fresh install lays down a NEW CLAUDE.md at the original location.
    (tmp_path / "CLAUDE.md").write_text("FRESH install\n", encoding="utf-8")

    result = repo_space.restore_assets(tmp_path, archived.archive_dir)

    assert "CLAUDE.md" in result.conflicts  # present target left untouched
    assert (tmp_path / "CLAUDE.md").read_text() == "FRESH install\n"
    assert ".claude" in result.restored  # the non-conflicting member still restored


def test_restore_overwrite_replaces_present_target(tmp_path: Path) -> None:
    original = _seed_repo(tmp_path)
    archived = repo_space.archive_assets(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("FRESH\n", encoding="utf-8")

    result = repo_space.restore_assets(tmp_path, archived.archive_dir, overwrite=True)

    assert not result.conflicts
    assert (tmp_path / "CLAUDE.md").read_bytes() == original["CLAUDE.md"]


# -------------------------------------------------------- KEY round-trip acceptance test


def test_round_trip_install_archive_out_of_scope_restore_identical(tmp_path: Path) -> None:
    """install → archive existing → OUT of Claude's scope → restore → byte-identical original."""
    repo = tmp_path / "repo"
    repo.mkdir()
    original = _seed_repo(repo)

    # 1. archive the existing assets (relocate out of Claude's scope).
    archived = repo_space.archive_assets(repo)

    # 2. assert the OLD assets are OUT of Claude's load scope: not under repo/.claude,
    #    and the archive container is a sibling that Claude does not load.
    assert not (repo / ".claude").exists()
    assert not (repo / "CLAUDE.md").exists()
    assert archived.archive_dir.is_relative_to(repo / repo_space.BACKUPS_DIRNAME)
    assert not archived.archive_dir.is_relative_to(repo / ".claude")

    # 3. a fresh install lands a clean, DIFFERENT .claude/ + CLAUDE.md.
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text('{"hooks": {"fresh": true}}\n', encoding="utf-8")
    (repo / "CLAUDE.md").write_text("# fresh framework install\n", encoding="utf-8")
    assert _snapshot(repo, (".claude", "CLAUDE.md")) != original  # genuinely changed

    # 4. restore → original state byte-identical (fresh install cleared).
    result = repo_space.restore_assets(repo, archived.archive_dir, overwrite=True)
    assert not result.conflicts
    assert _snapshot(repo, (".claude", "CLAUDE.md")) == original


# ------------------------------------------------------------ disposition + consent gate


def test_choose_disposition_non_interactive_is_amend(tmp_path: Path) -> None:
    assert repo_space.choose_disposition(tmp_path, non_interactive=True) == "amend"


def test_choose_disposition_non_tty_is_amend(tmp_path: Path) -> None:
    assert repo_space.choose_disposition(tmp_path, non_interactive=False, _isatty=False) == "amend"


def test_choose_disposition_interactive_parses_choices(tmp_path: Path) -> None:
    for answer, expected in [
        ("a", "archive"), ("archive", "archive"),
        ("k", "amend"), ("", "amend"), ("huh", "amend"),
        ("c", "cancel"), ("cancel", "cancel"), ("n", "cancel"),
    ]:
        got = repo_space.choose_disposition(
            tmp_path, non_interactive=False, _isatty=True, _input=lambda _p, v=answer: v
        )
        assert got == expected, answer


def test_prepare_fresh_repo_is_noop(tmp_path: Path) -> None:
    prep = repo_space.prepare_for_install(tmp_path, non_interactive=False)
    assert prep.action == "fresh"
    assert prep.archive is None


def test_prepare_non_interactive_amends_never_archives(tmp_path: Path) -> None:
    """--non-interactive with existing assets: amend in place, nothing moved (CI-safe)."""
    _seed_repo(tmp_path)
    prep = repo_space.prepare_for_install(tmp_path, non_interactive=True)
    assert prep.action == "amend"
    assert (tmp_path / ".claude").exists()  # untouched
    assert not (tmp_path / repo_space.BACKUPS_DIRNAME).exists()


def test_prepare_archive_requires_explicit_consent(tmp_path: Path) -> None:
    """Choosing archive but DECLINING the destructive consent moves nothing."""
    _seed_repo(tmp_path)
    prep = repo_space.prepare_for_install(
        tmp_path, non_interactive=False,
        chooser=lambda: "archive", consent_fn=lambda _s: False,
    )
    assert prep.action == "cancel"
    assert (tmp_path / ".claude").exists()  # nothing moved without consent
    assert not (tmp_path / repo_space.BACKUPS_DIRNAME).exists()


def test_prepare_archive_on_consent_relocates(tmp_path: Path) -> None:
    original = _seed_repo(tmp_path)
    prep = repo_space.prepare_for_install(
        tmp_path, non_interactive=False,
        chooser=lambda: "archive", consent_fn=lambda _s: True,
    )
    assert prep.action == "archived"
    assert not (tmp_path / ".claude").exists()  # relocated out of scope
    # Still fully restorable.
    repo_space.restore_assets(tmp_path, prep.archive.archive_dir)
    assert _snapshot(tmp_path, (".claude", "CLAUDE.md")) == original


def test_prepare_cancel_disposition_aborts(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    prep = repo_space.prepare_for_install(
        tmp_path, non_interactive=False, chooser=lambda: "cancel"
    )
    assert prep.action == "cancel"
    assert (tmp_path / ".claude").exists()


# --------------------------------------------------------------- consent prompt override


def test_consent_prompt_override_is_repo_scoped() -> None:
    """prompt_consent still fail-safe, and the repo prompt line replaces the ~/.claude one."""
    seen: dict[str, str] = {}

    def _capture(prompt: str) -> str:
        seen["prompt"] = prompt
        return "y"

    ok = consent_mod.prompt_consent(
        "summary", non_interactive=False, prompt="ARCHIVE now? [y/N]: ",
        _isatty=True, _input=_capture,
    )
    assert ok is True
    assert seen["prompt"] == "ARCHIVE now? [y/N]: "
    # Default (no prompt) keeps the user-space wording (#107 unchanged).
    consent_mod.prompt_consent(
        "s", non_interactive=False, _isatty=True, _input=lambda p: seen.setdefault("d", p) and "n"
    )
    assert "~/.claude" in seen["d"]


# ------------------------------------------------------------------ #145 atomic writes


def test_atomic_write_success_leaves_no_temp(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "out.json"
    atomic_io.atomic_write_text(target, '{"a": 1}\n')
    assert target.read_text() == '{"a": 1}\n'
    assert list(target.parent.iterdir()) == [target]  # no stray temp file


def test_atomic_write_uses_same_dir_temp_and_replace(tmp_path: Path, monkeypatch) -> None:
    """The rename source is a temp file in the SAME directory as the target (atomic rename)."""
    target = tmp_path / "out.json"
    captured: dict[str, Path] = {}
    real_replace = atomic_io.os.replace

    def _spy(src, dst):
        captured["src"] = Path(src)
        captured["dst"] = Path(dst)
        return real_replace(src, dst)

    monkeypatch.setattr(atomic_io.os, "replace", _spy)
    atomic_io.atomic_write_text(target, "data")
    assert captured["dst"] == target
    assert captured["src"].parent == target.parent  # temp lived beside the target
    assert target.read_text() == "data"


def test_atomic_write_interrupt_never_truncates_target(tmp_path: Path, monkeypatch) -> None:
    """A crash at the replace step leaves the OLD target intact — never a partial write."""
    target = tmp_path / "out.json"
    target.write_text("OLD-COMPLETE", encoding="utf-8")

    def _boom(src, dst):
        raise RuntimeError("simulated interrupt at replace")

    monkeypatch.setattr(atomic_io.os, "replace", _boom)
    with pytest.raises(RuntimeError):
        atomic_io.atomic_write_text(target, "NEW-PARTIAL")

    assert target.read_text() == "OLD-COMPLETE"  # untouched: never truncated
    # And no temp file was left stranded.
    assert list(target.parent.iterdir()) == [target]


def test_user_space_write_is_atomic_and_crash_safe(tmp_path: Path, monkeypatch) -> None:
    """The reused user-space merge (#107) shares the hardened atomic write (#145)."""
    home = tmp_path / "home"
    path = user_space.user_settings_path(home)
    path.parent.mkdir(parents=True)
    path.write_text('{"model": "opus"}\n', encoding="utf-8")  # valid; the flag WILL be added
    before = path.read_bytes()

    monkeypatch.setattr(
        atomic_io.os, "replace",
        lambda *a: (_ for _ in ()).throw(RuntimeError("crash")),
    )
    with pytest.raises(RuntimeError):
        user_space.install_user_space(home=home, non_interactive=False, consent_fn=lambda _s: True)

    assert path.read_bytes() == before  # settings.json never truncated by the failed write


# ---------------------------------------------- #149 finding 2: parent-dir fsync durability


def test_atomic_write_fsyncs_parent_dir_after_replace(tmp_path: Path, monkeypatch) -> None:
    """After the atomic rename, the target's PARENT DIR is fsynced so the rename is durable.

    Fsyncing only the temp file persists its bytes but not the directory entry that names
    them under the target; a crash right after ``os.replace`` could lose the rename. The fix
    (#149 finding 2) fsyncs the parent dir — force that path and assert it fires on the
    target's parent, and that it happens AFTER the replace.
    """
    target = tmp_path / "sub" / "out.json"
    events: list[tuple[str, Path]] = []
    real_replace = atomic_io.os.replace

    def _replace_spy(src, dst):
        events.append(("replace", Path(dst)))
        return real_replace(src, dst)

    def _fsync_dir_spy(directory):
        events.append(("fsync_dir", Path(directory)))

    monkeypatch.setattr(atomic_io.os, "replace", _replace_spy)
    monkeypatch.setattr(atomic_io, "_fsync_dir", _fsync_dir_spy)
    atomic_io.atomic_write_text(target, '{"a": 1}\n')

    assert ("fsync_dir", target.parent) in events  # the parent dir was fsynced
    # ...and strictly after the rename (durability of the entry, not the bytes).
    assert events.index(("replace", target)) < events.index(("fsync_dir", target.parent))
    assert target.read_text() == '{"a": 1}\n'


def test_atomic_write_dir_fsync_is_fail_open(tmp_path: Path, monkeypatch) -> None:
    """Hard durability is best-effort: a dir that can't be opened/fsynced never crashes the write."""
    target = tmp_path / "out.json"

    # Simulate a platform where opening a directory fd is unsupported (e.g. Windows).
    real_open = atomic_io.os.open

    def _open_raising(path, *a, **k):
        if Path(path) == target.parent:
            raise OSError("cannot open directory as fd")
        return real_open(path, *a, **k)

    monkeypatch.setattr(atomic_io.os, "open", _open_raising)
    atomic_io.atomic_write_text(target, "data")  # must not raise
    assert target.read_text() == "data"  # write still succeeded


def _dir_fsync_supported(directory: Path) -> bool:
    """True iff this platform can open+fsync a directory fd (fail-open guard, mirrors the code)."""
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return False
    try:
        os.fsync(fd)
    except OSError:
        return False
    finally:
        os.close(fd)
    return True


def test_atomic_write_really_fsyncs_the_parent_directory(tmp_path: Path, monkeypatch) -> None:
    """The success path fsyncs a fd that REALLY refers to the parent dir — not just 'some fsync'.

    Non-tautological guard for #149 finding 2 (the durability syscall itself, not its wiring):
    a spy on ``os.fsync`` records the inode behind every fsynced fd and correlates it to the
    parent directory's inode. Gutting the ``os.fsync(dir_fd)`` line inside ``_fsync_dir`` makes
    THIS test fail (the parent-dir inode is never fsynced). Skips cleanly on platforms that
    cannot fsync a directory fd, matching the code's own fail-open behaviour.
    """
    target = tmp_path / "sub" / "out.json"
    parent = target.parent
    parent.mkdir(parents=True)
    if not _dir_fsync_supported(parent):
        pytest.skip("platform cannot fsync a directory fd (dir-fsync unsupported)")

    parent_ino = os.stat(str(parent)).st_ino
    fsynced_inodes: list[int] = []
    real_fsync = atomic_io.os.fsync

    def _fsync_spy(fd):
        try:
            fsynced_inodes.append(os.fstat(fd).st_ino)
        except OSError:
            pass
        return real_fsync(fd)  # delegate to the real syscall — durability still happens

    monkeypatch.setattr(atomic_io.os, "fsync", _fsync_spy)
    atomic_io.atomic_write_text(target, '{"a": 1}\n')

    # The PARENT DIRECTORY's fd was fsynced (correlated by inode), not merely the temp file.
    assert parent_ino in fsynced_inodes, "parent-dir fd was never fsynced (durability syscall dropped)"
    assert target.read_text() == '{"a": 1}\n'


# ------------------------------------------- #149 finding 3: interrupted archive is recoverable


def test_archive_writes_manifest_before_moving_and_is_recoverable(tmp_path: Path, monkeypatch) -> None:
    """A crash MID-move leaves a manifested, fully-restorable archive — never a stranded half.

    The manifest is written before the first ``shutil.move``, so if the process dies after
    moving ``.claude`` but before ``CLAUDE.md``, restore reads the (complete) manifest, moves
    ``.claude`` back, and skips the member still sitting untouched at the repo root — restoring
    the original state byte-for-byte.
    """
    original = _seed_repo(tmp_path)
    real_move = repo_space.shutil.move
    calls = {"n": 0}

    def _move_then_boom(src, dst):
        calls["n"] += 1
        if calls["n"] >= 2:  # move the first asset, crash on the second
            raise RuntimeError("simulated interrupt mid-archive")
        return real_move(src, dst)

    monkeypatch.setattr(repo_space.shutil, "move", _move_then_boom)
    with pytest.raises(RuntimeError):
        repo_space.archive_assets(tmp_path)

    # The manifest exists and names EVERY intended member despite the crash (written first).
    archive_dirs = list((tmp_path / repo_space.BACKUPS_DIRNAME).iterdir())
    assert len(archive_dirs) == 1
    archive_dir = archive_dirs[0]
    manifest = json.loads((archive_dir / repo_space.MANIFEST_NAME).read_text())
    assert {e["name"] for e in manifest["entries"]} == {".claude", "CLAUDE.md"}

    # Recovery: restore off the manifest reconstructs the original repo byte-for-byte.
    monkeypatch.setattr(repo_space.shutil, "move", real_move)  # undo the fault injection
    repo_space.restore_assets(tmp_path, archive_dir)
    assert _snapshot(tmp_path, (".claude", "CLAUDE.md")) == original


# ---------------------------- #149 finding 4: restore scope is exactly the managed assets


def test_restore_scope_is_exactly_managed_assets(tmp_path: Path) -> None:
    """Restore touches ONLY .claude/ + CLAUDE.md; out-of-scope residue is intentionally left.

    Restore is deliberately not a "return to globally pristine" op: a fresh install's
    ``.git/hooks/pre-push`` and the emptied ``.claude-backups/`` container remain by design
    (#149 finding 4). This asserts the exact managed boundary.
    """
    _seed_repo(tmp_path)
    # Out-of-scope artifacts that a fresh install / the archive itself would leave behind.
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "pre-push").write_text("#!/bin/sh\n", encoding="utf-8")
    sibling = tmp_path / "README.md"
    sibling.write_text("unrelated\n", encoding="utf-8")

    archived = repo_space.archive_assets(tmp_path)
    result = repo_space.restore_assets(tmp_path, archived.archive_dir)

    # The managed assets came back...
    assert set(result.restored) == {".claude", "CLAUDE.md"}
    # ...and the out-of-scope artifacts are untouched (neither pruned nor clobbered).
    assert (hooks / "pre-push").read_text() == "#!/bin/sh\n"
    assert sibling.read_text() == "unrelated\n"
    # The archive container is intentionally left in place (emptied, not removed).
    assert (tmp_path / repo_space.BACKUPS_DIRNAME).is_dir()
