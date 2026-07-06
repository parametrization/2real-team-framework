"""Unit tests for ``bootstrap.ensure_gitignore_entries`` (#187).

Settles the generic-prompt-ledger git-tracking policy: the live ledger
(``.claude/generic_prompt_ledger.json``) is a transient per-repo working queue
and is gitignored by policy (see ``generic_prompt_tracker.py``'s module
docstring). This repo's own ``.gitignore`` carried that entry by hand as a
stopgap (commit ``0873fea``); this dual-deploys the same default into every
OTHER repo the installer touches, so downstream adopters don't hit the same
untracked-noise surprise. End-to-end coverage (the entry actually lands in a
real bootstrap install, standalone/meta/child) lives in
``test_bootstrap_smoke.py`` / ``test_meta_child_install.py``; this file
isolates the pure file-mutation logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "install"))

import bootstrap  # noqa: E402

LEDGER = ".claude/generic_prompt_ledger.json"


def test_creates_gitignore_when_absent(tmp_path: Path) -> None:
    status = bootstrap.ensure_gitignore_entries(tmp_path, (LEDGER,), dry_run=False)
    assert "added 1" in status
    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert LEDGER in text.splitlines()
    assert text.endswith("\n")


def test_appends_to_existing_gitignore_without_disturbing_it(tmp_path: Path) -> None:
    gi = tmp_path / ".gitignore"
    gi.write_text("node_modules/\n*.pyc\n", encoding="utf-8")
    bootstrap.ensure_gitignore_entries(tmp_path, (LEDGER,), dry_run=False)
    lines = gi.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "node_modules/"
    assert lines[1] == "*.pyc"
    assert LEDGER in lines


def test_second_call_is_a_no_op_never_duplicates(tmp_path: Path) -> None:
    bootstrap.ensure_gitignore_entries(tmp_path, (LEDGER,), dry_run=False)
    first = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    status = bootstrap.ensure_gitignore_entries(tmp_path, (LEDGER,), dry_run=False)
    second = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert status == "up to date (0 added)"
    assert first == second
    assert first.count(LEDGER) == 1
    # The header is stamped once even across repeated calls.
    assert first.count(bootstrap._GITIGNORE_HEADER) == 1


def test_entry_already_hand_authored_is_left_alone(tmp_path: Path) -> None:
    """A repo that already gitignores the ledger by hand (this repo's own
    stopgap, commit 0873fea) gets no duplicate — the installer defers to
    whatever is already present."""
    gi = tmp_path / ".gitignore"
    gi.write_text(f"# my own notes\n{LEDGER}\n", encoding="utf-8")
    status = bootstrap.ensure_gitignore_entries(tmp_path, (LEDGER,), dry_run=False)
    assert status == "up to date (0 added)"
    assert gi.read_text(encoding="utf-8") == f"# my own notes\n{LEDGER}\n"


def test_dry_run_reports_without_writing(tmp_path: Path) -> None:
    status = bootstrap.ensure_gitignore_entries(tmp_path, (LEDGER,), dry_run=True)
    assert "would add 1" in status
    assert LEDGER in status
    assert not (tmp_path / ".gitignore").exists()


def test_dry_run_up_to_date_when_already_present(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(f"{LEDGER}\n", encoding="utf-8")
    status = bootstrap.ensure_gitignore_entries(tmp_path, (LEDGER,), dry_run=True)
    assert status == "up to date (0 added)"


def test_multiple_entries_only_missing_ones_added(tmp_path: Path) -> None:
    gi = tmp_path / ".gitignore"
    gi.write_text(f"{LEDGER}\n", encoding="utf-8")
    status = bootstrap.ensure_gitignore_entries(
        tmp_path, (LEDGER, ".claude-backups/"), dry_run=False
    )
    assert "added 1" in status
    assert ".claude-backups/" in status
    lines = gi.read_text(encoding="utf-8").splitlines()
    assert lines.count(LEDGER) == 1
    assert ".claude-backups/" in lines
