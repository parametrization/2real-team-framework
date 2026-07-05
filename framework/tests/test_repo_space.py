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
