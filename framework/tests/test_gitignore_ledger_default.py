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


# ------------------------------------------------------ #216 normalization


def test_duplicate_entries_in_a_single_call_are_deduped(tmp_path: Path) -> None:
    """Load-bearing (#216): a caller-supplied ``entries`` tuple with repeats must
    never append the same path more than once.

    Mutation bar: drop the input-dedup step (``deduped_entries``/``seen`` loop) in
    ``ensure_gitignore_entries`` and this fails, since the un-deduped tuple would
    make ``missing`` contain ``LEDGER`` twice.
    """
    bootstrap.ensure_gitignore_entries(tmp_path, (LEDGER, LEDGER), dry_run=False)
    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count(LEDGER) == 1


def test_appended_entries_are_order_independent(tmp_path: Path) -> None:
    """Load-bearing (#216): the SAME set of missing entries, passed in different
    orders across two independent targets, must produce byte-identical
    ``.gitignore`` output — the appended block is a function of the entry SET,
    not of caller argument order.

    Mutation bar: remove the ``sorted(...)`` around ``missing`` and this fails,
    since the two targets would then differ only in entry order.
    """
    entry_a, entry_b = LEDGER, ".claude-backups/"
    target1, target2 = tmp_path / "repo1", tmp_path / "repo2"
    target1.mkdir()
    target2.mkdir()

    bootstrap.ensure_gitignore_entries(target1, (entry_a, entry_b), dry_run=False)
    bootstrap.ensure_gitignore_entries(target2, (entry_b, entry_a), dry_run=False)

    text1 = (target1 / ".gitignore").read_text(encoding="utf-8")
    text2 = (target2 / ".gitignore").read_text(encoding="utf-8")
    assert text1 == text2


def test_preexisting_trailing_blank_lines_are_collapsed_not_duplicated(tmp_path: Path) -> None:
    """Load-bearing (#216): a hand-authored ``.gitignore`` that already ends in a
    blank line must get exactly ONE blank separator before the newly-stamped
    managed block, not two.

    Mutation bar: drop the trailing-blank-line collapse (the
    ``while existing_lines and existing_lines[-1] == "": existing_lines.pop()``
    loop) in ``ensure_gitignore_entries`` and this fails — the old
    ``existing_lines[-1] != ""`` guard this loop replaces would see the file
    already ends blank and skip adding a separator, but the SECOND blank line
    already on disk would remain, producing a double blank before the header.
    """
    gi = tmp_path / ".gitignore"
    gi.write_text("node_modules/\n\n", encoding="utf-8")

    bootstrap.ensure_gitignore_entries(tmp_path, (LEDGER,), dry_run=False)

    text = gi.read_text(encoding="utf-8")
    assert "\n\n\n" not in text
    assert text.splitlines() == ["node_modules/", "", bootstrap._GITIGNORE_HEADER, LEDGER]
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_repeated_calls_never_accumulate_blank_line_separators(tmp_path: Path) -> None:
    """Two SEPARATE calls that each add a genuinely new entry must not grow the
    blank-line gap between installer-managed entries — the header is stamped
    once (with a single leading blank separator from the pre-existing
    hand-authored content) and entries stay contiguous underneath it.
    """
    gi = tmp_path / ".gitignore"
    gi.write_text("node_modules/\n", encoding="utf-8")

    bootstrap.ensure_gitignore_entries(tmp_path, (LEDGER,), dry_run=False)
    bootstrap.ensure_gitignore_entries(tmp_path, (".claude-backups/",), dry_run=False)

    text = gi.read_text(encoding="utf-8")
    assert "\n\n\n" not in text
    lines = text.splitlines()
    assert lines == [
        "node_modules/",
        "",
        bootstrap._GITIGNORE_HEADER,
        LEDGER,
        ".claude-backups/",
    ]
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_running_twice_with_same_entries_produces_no_diff(tmp_path: Path) -> None:
    """The literal ask: run the same install step twice -> zero diff on the
    second run, starting from a pre-existing hand-authored .gitignore (the
    realistic reinstall scenario, not just a from-empty install)."""
    gi = tmp_path / ".gitignore"
    gi.write_text("node_modules/\n*.pyc\n", encoding="utf-8")

    bootstrap.ensure_gitignore_entries(tmp_path, (LEDGER, ".claude-backups/"), dry_run=False)
    first = gi.read_text(encoding="utf-8")

    status = bootstrap.ensure_gitignore_entries(tmp_path, (LEDGER, ".claude-backups/"), dry_run=False)
    second = gi.read_text(encoding="utf-8")

    assert status == "up to date (0 added)"
    assert first == second
