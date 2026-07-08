"""Tests for the git-native ``install_branch`` staging mode (#279).

``install_branch`` stages a framework install onto a throwaway branch off HEAD so the operator can
``git merge`` it when satisfied or ``git branch -D`` to walk away clean. It is the git-native sibling
of ``restore`` (the git-independent, manifest-driven undo). Coverage:

* **Branch creation + commit** — the headline AC: a clean git repo gets a new install branch with
  the install committed as one commit; the operator is left on that branch to try it.
* **--return parks the install** — with ``keep_checkout=False`` the tree returns to the original
  branch (clean) and the install lives only on the install branch.
* **Composes with manifest-restore** — the installer's manifest/``.bak`` are committed on the branch
  AND ``restore`` still sees them there (the two undo paths coexist, don't conflict).
* **Degrades by refusing** — a dirty tree, a non-git repo, and a pre-existing branch each refuse
  with an actionable message and create nothing.
* **dry-run creates nothing**; **a failed install rolls the branch back**; **a non-TTY refuses**.

Stdlib + pytest only; everything runs under ``tmp_path``. Git identity is supplied per-command via
``-c`` flags so tests never touch global git config.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_INSTALL = _FRAMEWORK_ROOT / "install"
_INSTALL_BRANCH = _INSTALL / "install_branch.py"
if str(_INSTALL) not in sys.path:
    sys.path.insert(0, str(_INSTALL))

import install_branch  # noqa: E402
import repo_space  # noqa: E402
import restore  # noqa: E402


# --------------------------------------------------------------------------- helpers


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root),
         "-c", "user.name=Test", "-c", "user.email=test@test.local", *args],
        capture_output=True, text=True,
    )


def _init_repo(root: Path) -> None:
    """A git repo with one commit (a real HEAD to branch off), no global config touched."""
    _git(root, "init", "-q")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed")


def _write_file_action(rel: str, body: bytes) -> install_branch.InstallAction:
    def _action(target: Path) -> None:
        p = target / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
    return _action


def _current_branch(root: Path) -> str:
    return _git(root, "symbolic-ref", "--short", "HEAD").stdout.strip()


# --------------------------------------------------------------- branch creation + commit


def test_stage_creates_branch_and_commits(tmp_path: Path):
    """The headline AC: a clean git repo gets an install branch with the install committed on it."""
    _init_repo(tmp_path)
    orig = _current_branch(tmp_path)

    report = install_branch.stage_install(
        tmp_path, _write_file_action(".claude/marker", b"installed\n"), non_interactive=True
    )

    assert report.staged is True, report.notes
    assert report.on_branch is True
    assert report.branch == install_branch.DEFAULT_BRANCH
    # We are on the new install branch, which exists and differs from the original.
    assert _current_branch(tmp_path) == install_branch.DEFAULT_BRANCH
    assert install_branch.branch_exists(tmp_path, install_branch.DEFAULT_BRANCH)
    # The install landed and was COMMITTED (working tree is clean, file present).
    assert (tmp_path / ".claude" / "marker").read_bytes() == b"installed\n"
    assert not install_branch.is_dirty(tmp_path)
    # The original branch has no marker — the install lives only on the install branch.
    _git(tmp_path, "checkout", "-q", orig)
    assert not (tmp_path / ".claude" / "marker").exists()


def test_stage_return_parks_install_on_branch(tmp_path: Path):
    """--return leaves the tree on the original branch (clean); the install lives on the branch."""
    _init_repo(tmp_path)
    orig = _current_branch(tmp_path)

    report = install_branch.stage_install(
        tmp_path, _write_file_action(".claude/marker", b"x\n"),
        non_interactive=True, keep_checkout=False,
    )

    assert report.staged is True
    assert report.on_branch is False
    assert _current_branch(tmp_path) == orig
    # Working tree is back to pristine — the marker is NOT here...
    assert not (tmp_path / ".claude" / "marker").exists()
    assert not install_branch.is_dirty(tmp_path)
    # ...but it IS on the install branch.
    show = _git(tmp_path, "show", f"{install_branch.DEFAULT_BRANCH}:.claude/marker")
    assert show.returncode == 0 and show.stdout == "x\n"


# --------------------------------------------------------------- composes with manifest-restore


def test_composes_with_manifest_restore(tmp_path: Path):
    """The installer's manifest/.bak are committed on the branch AND restore still sees them there."""
    _init_repo(tmp_path)

    def _installer_like(target: Path) -> None:
        # A pre-existing .claude/ archived (moved) + a fresh one laid where it stood, plus an
        # in-place-modified CLAUDE.md whose original is kept as CLAUDE.md.bak — exactly the two
        # reversible dispositions restore reverses.
        claude = target / ".claude"
        (claude / "team").mkdir(parents=True)
        (claude / "team" / "charter.md").write_bytes(b"# ORIGINAL\n")
        repo_space.archive_assets(target)  # MOVES .claude/ into .claude-backups/<UTC>/ + manifest
        (claude / "team").mkdir(parents=True)
        (claude / "team" / "charter.md").write_bytes(b"# FRESH\n")
        (target / "CLAUDE.md.bak").write_bytes(b"# ORIGINAL md\n")
        (target / "CLAUDE.md").write_bytes(b"# FRESH md\n")

    report = install_branch.stage_install(tmp_path, _installer_like, non_interactive=True)
    assert report.staged is True

    # The manifest + .bak were captured in the branch commit (tree is clean, artifacts present).
    assert not install_branch.is_dirty(tmp_path)
    assert repo_space.find_latest_archive(tmp_path) is not None
    assert (tmp_path / "CLAUDE.md.bak").is_file()

    # And restore — the OTHER undo path — still sees both directions on the staged branch: the two
    # compose rather than conflict.
    plan = restore.plan_restore(tmp_path)
    assert plan.archived == [".claude"]
    assert [rev.target_rel for rev in plan.reverts] == ["CLAUDE.md"]


# --------------------------------------------------------------- degradation: refuse, create nothing


def test_dirty_tree_refuses(tmp_path: Path):
    """A dirty working tree refuses (would fold uncommitted work into the install commit)."""
    _init_repo(tmp_path)
    (tmp_path / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")  # untracked -> dirty
    assert install_branch.is_dirty(tmp_path)

    report = install_branch.stage_install(
        tmp_path, _write_file_action(".claude/marker", b"x\n"), non_interactive=True
    )
    assert report.staged is False
    assert not install_branch.branch_exists(tmp_path, install_branch.DEFAULT_BRANCH)
    assert any("uncommitted" in n for n in report.notes)


def test_non_git_repo_refuses(tmp_path: Path):
    """A non-git target refuses with a message pointing at the restore path — and creates nothing."""
    report = install_branch.stage_install(
        tmp_path, _write_file_action(".claude/marker", b"x\n"), non_interactive=True
    )
    assert report.staged is False
    assert not (tmp_path / ".claude").exists()
    assert any("not a git repository" in n for n in report.notes)


def test_branch_collision_refuses(tmp_path: Path):
    """An existing install branch refuses rather than reusing or clobbering it."""
    _init_repo(tmp_path)
    _git(tmp_path, "branch", install_branch.DEFAULT_BRANCH)

    report = install_branch.stage_install(
        tmp_path, _write_file_action(".claude/marker", b"x\n"), non_interactive=True
    )
    assert report.staged is False
    assert any("already exists" in n for n in report.notes)


def test_dry_run_creates_nothing(tmp_path: Path):
    """--dry-run resolves the plan but creates no branch and runs no install."""
    _init_repo(tmp_path)
    report = install_branch.stage_install(
        tmp_path, _write_file_action(".claude/marker", b"x\n"), non_interactive=True, dry_run=True
    )
    assert report.staged is False
    assert not install_branch.branch_exists(tmp_path, install_branch.DEFAULT_BRANCH)
    assert not (tmp_path / ".claude").exists()
    assert any("dry-run" in n for n in report.notes)


def test_failed_install_rolls_back(tmp_path: Path):
    """If the install action raises, the branch is rolled back and the tree left as found."""
    _init_repo(tmp_path)
    orig = _current_branch(tmp_path)

    def _boom(target: Path) -> None:
        (target / ".claude").mkdir()
        (target / ".claude" / "partial").write_text("half\n", encoding="utf-8")
        raise RuntimeError("install blew up")

    with pytest.raises(RuntimeError, match="install blew up"):
        install_branch.stage_install(tmp_path, _boom, non_interactive=True)

    # Rolled back: original branch restored, install branch gone, no partial files left.
    assert _current_branch(tmp_path) == orig
    assert not install_branch.branch_exists(tmp_path, install_branch.DEFAULT_BRANCH)
    assert not (tmp_path / ".claude").exists()
    assert not install_branch.is_dirty(tmp_path)


# --------------------------------------------------------------- CLI consent (no mutation unattended)


def test_cli_non_tty_without_flag_refuses(tmp_path: Path):
    """A non-TTY CLI run without --non-interactive refuses at the consent gate; nothing is created."""
    _init_repo(tmp_path)
    r = subprocess.run(
        [sys.executable, str(_INSTALL_BRANCH), str(tmp_path)],
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    assert r.returncode == 1
    assert "refusing" in r.stderr.lower()
    assert not install_branch.branch_exists(tmp_path, install_branch.DEFAULT_BRANCH)
