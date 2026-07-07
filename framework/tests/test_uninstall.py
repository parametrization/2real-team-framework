"""Tests for the product uninstall / ``bootstrap.py --teardown`` (issue #142/#222).

Two layers, mirroring the golden-manifest strategy:

* **Round-trip coupling** — a REAL ``bootstrap.py`` install into a tmp git repo followed by a REAL
  ``uninstall.py`` run must leave the working tree byte-identical to its pre-install snapshot
  (the harness ``snapshot`` module is the ground truth). This is the AC's headline proof and runs
  across the fresh / no-ontology / no-team / pre-existing-.gitignore / amend / consented-archive
  dispositions.
* **Unit** — the reversible primitives (settings un-merge, gitignore un-append, pre-push
  removal+restore, ontology preservation, the confirm gate, idempotency) in isolation, so a
  regression points at the exact seam.

Stdlib + pytest only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _FRAMEWORK_ROOT.parent
_BOOTSTRAP = _FRAMEWORK_ROOT / "install" / "bootstrap.py"
_UNINSTALL = _FRAMEWORK_ROOT / "install" / "uninstall.py"
sys.path.insert(0, str(_REPO_ROOT))  # make `framework.harness` importable (namespace package)
sys.path.insert(0, str(_FRAMEWORK_ROOT / "install"))  # sibling modules (uninstall / repo_space)

import repo_space  # noqa: E402
import uninstall  # noqa: E402

from framework.harness import snapshot as snap  # noqa: E402


# --------------------------------------------------------------------------- helpers


def _git_init_repo(d: Path) -> None:
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    (d / "README.md").write_text("# repo\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(d), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"],
        check=True, capture_output=True,
    )


def _install(d: Path, *args: str) -> subprocess.CompletedProcess:
    r = subprocess.run(
        [sys.executable, str(_BOOTSTRAP), str(d), *args],
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    assert r.returncode == 0, r.stderr
    return r


def _run_uninstall(d: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_UNINSTALL), str(d), *args],
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )


# --------------------------------------------------------------- round-trip coupling


@pytest.mark.parametrize(
    "install_args",
    [
        pytest.param(("--owner", "test-org", "--with-ontology"), id="fresh+ontology"),
        pytest.param(("--owner", "test-org", "--no-ontology"), id="fresh-no-ontology"),
        pytest.param(("--owner", "test-org", "--no-team", "--no-ontology"), id="no-team"),
    ],
)
def test_install_uninstall_is_byte_identical(tmp_path: Path, install_args: tuple[str, ...]) -> None:
    """The AC headline: install → uninstall returns the repo to byte-identical pre-install state."""
    _git_init_repo(tmp_path)
    pre = snap.snapshot(tmp_path)

    _install(tmp_path, *install_args)
    assert snap.added_paths(pre, snap.snapshot(tmp_path)), "install added nothing — test is inert"

    r = _run_uninstall(tmp_path, "--non-interactive")
    assert r.returncode == 0, r.stderr

    residue = snap.symmetric_diff(pre, snap.snapshot(tmp_path))
    assert residue == [], f"non-reversible residue: {residue}"


def test_uninstall_preserves_pre_existing_gitignore(tmp_path: Path) -> None:
    """The managed #187 block is stripped but the operator's own .gitignore lines survive intact."""
    _git_init_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("node_modules/\n*.log\n", encoding="utf-8")
    pre = snap.snapshot(tmp_path)

    _install(tmp_path, "--owner", "test-org", "--no-ontology")
    assert (tmp_path / ".gitignore").read_text() != "node_modules/\n*.log\n"  # block appended

    _run_uninstall(tmp_path, "--non-interactive")
    assert snap.symmetric_diff(pre, snap.snapshot(tmp_path)) == []
    assert (tmp_path / ".gitignore").read_text() == "node_modules/\n*.log\n"


def test_amend_disposition_unmerges_settings_byte_identical(tmp_path: Path) -> None:
    """A pre-existing settings.json (amend disposition) is un-merged back to byte-identical."""
    _git_init_repo(tmp_path)
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text(
        json.dumps(
            {"hooks": {"PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 my_own_hook.py"}]}
            ]}},
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    pre = snap.snapshot(tmp_path)

    _install(tmp_path, "--owner", "test-org", "--no-ontology")
    _run_uninstall(tmp_path, "--non-interactive")

    assert snap.symmetric_diff(pre, snap.snapshot(tmp_path)) == []
    # The user's own hook is preserved verbatim.
    assert "my_own_hook.py" in (claude / "settings.json").read_text()


def test_consented_archive_is_restored_byte_identical(tmp_path: Path) -> None:
    """AC bullet 2: a consented-archive install (#108) is restored to byte-identical pre-install."""
    _git_init_repo(tmp_path)
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text('{"my":"stuff"}\n', encoding="utf-8")
    (claude / "notes.md").write_text("keep me\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("my project rules\n", encoding="utf-8")
    pre = snap.snapshot(tmp_path)

    # Simulate the consented archive disposition (the installer's #108 path).
    repo_space.archive_assets(tmp_path)
    _install(tmp_path, "--owner", "test-org", "--with-ontology")

    _run_uninstall(tmp_path, "--non-interactive")
    residue = snap.symmetric_diff(pre, snap.snapshot(tmp_path))
    assert residue == [], f"archive not fully restored: {residue}"
    assert (claude / "notes.md").read_text() == "keep me\n"
    assert not (tmp_path / repo_space.BACKUPS_DIRNAME).exists(), "spent backup container not pruned"


# ----------------------------------------------------------------- idempotency / safety


def test_not_installed_repo_is_clean_noop(tmp_path: Path) -> None:
    """A repo with no framework.config.json is a clean no-op (exit 0), not an error."""
    _git_init_repo(tmp_path)
    before = snap.snapshot(tmp_path)
    report = uninstall.uninstall(tmp_path)
    assert report["status"] == "not-installed"
    assert snap.snapshot(tmp_path) == before

    r = _run_uninstall(tmp_path, "--non-interactive")
    assert r.returncode == 0
    assert "nothing to do" in r.stdout


def test_uninstall_is_idempotent(tmp_path: Path) -> None:
    """A second uninstall after a successful one does nothing and stays clean."""
    _git_init_repo(tmp_path)
    _install(tmp_path, "--owner", "test-org", "--no-ontology")
    assert _run_uninstall(tmp_path, "--non-interactive").returncode == 0
    after_first = snap.snapshot(tmp_path)

    r2 = _run_uninstall(tmp_path, "--non-interactive")
    assert r2.returncode == 0
    assert "nothing to do" in r2.stdout
    assert snap.snapshot(tmp_path) == after_first


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    """--dry-run reports a plan but leaves the installed tree exactly as it was."""
    _git_init_repo(tmp_path)
    _install(tmp_path, "--owner", "test-org", "--no-ontology")
    installed = snap.snapshot(tmp_path)

    r = _run_uninstall(tmp_path, "--dry-run", "--non-interactive")
    assert r.returncode == 0
    assert snap.snapshot(tmp_path) == installed, "dry-run mutated the tree"


def test_non_tty_without_non_interactive_refuses(tmp_path: Path) -> None:
    """Destructive run on a non-TTY without --non-interactive refuses rather than acting blind."""
    _git_init_repo(tmp_path)
    _install(tmp_path, "--owner", "test-org", "--no-ontology")
    installed = snap.snapshot(tmp_path)

    # No --non-interactive; the subprocess has no TTY (stdin is DEVNULL).
    r = _run_uninstall(tmp_path)
    assert r.returncode == 1
    assert snap.snapshot(tmp_path) == installed, "refused run still mutated the tree"


# ------------------------------------------------------------------------ unit: seams


def _template() -> dict:
    return uninstall._template()


def test_unmerge_settings_removes_fully_owned_file(tmp_path: Path) -> None:
    """A settings.json holding only framework wiring (fresh install) is removed outright."""
    claude = tmp_path / ".claude"
    claude.mkdir()
    template = _template()
    # Reproduce a fresh install's settings.json via the installer's own merge.
    sys.path.insert(0, str(_FRAMEWORK_ROOT / "install"))
    import bootstrap  # noqa: E402

    bootstrap.merge_settings(claude, dry_run=False)
    assert (claude / "settings.json").is_file()

    status = uninstall.unmerge_settings(claude, template, dry_run=False)
    assert status.startswith("removed")
    assert not (claude / "settings.json").exists()


def test_unmerge_settings_preserves_user_content(tmp_path: Path) -> None:
    """When the operator has their own hooks/keys, un-merge prunes only the framework wiring."""
    claude = tmp_path / ".claude"
    claude.mkdir()
    template = _template()
    import bootstrap  # noqa: E402

    doc = {"env": {"MY": "1"}, "hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 mine.py"}]}
    ]}}
    (claude / "settings.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    bootstrap.merge_settings(claude, dry_run=False)  # adds framework dispatchers alongside

    uninstall.unmerge_settings(claude, template, dry_run=False)
    result = json.loads((claude / "settings.json").read_text())
    assert result["env"] == {"MY": "1"}
    cmds = [h["command"] for b in result["hooks"]["PreToolUse"] for h in b["hooks"]]
    assert "python3 mine.py" in cmds
    assert not any("dispatcher.py" in c for c in cmds), "framework hook not pruned"


def test_undo_gitignore_created_file_is_removed(tmp_path: Path) -> None:
    """A .gitignore the installer CREATED is deleted (round-trips to no file)."""
    import bootstrap  # noqa: E402

    bootstrap.ensure_gitignore_entries(tmp_path, (".claude/generic_prompt_ledger.json",), dry_run=False)
    assert (tmp_path / ".gitignore").is_file()

    status = uninstall.undo_gitignore(tmp_path, (".claude/generic_prompt_ledger.json",), dry_run=False)
    assert status.startswith("removed")
    assert not (tmp_path / ".gitignore").exists()


def test_undo_gitignore_leaves_file_without_managed_block(tmp_path: Path) -> None:
    """A .gitignore with no framework block is left untouched."""
    (tmp_path / ".gitignore").write_text("dist/\n", encoding="utf-8")
    status = uninstall.undo_gitignore(tmp_path, (".claude/generic_prompt_ledger.json",), dry_run=False)
    assert status == "no managed block found"
    assert (tmp_path / ".gitignore").read_text() == "dist/\n"


def test_remove_pre_push_restores_displaced_backup(tmp_path: Path) -> None:
    """Uninstalling our pre-push restores the operator's original hook the install preserved."""
    _git_init_repo(tmp_path)
    import bootstrap  # noqa: E402

    hooks_dir, _ = bootstrap._git_hooks_dir(tmp_path)
    original = "#!/bin/sh\necho custom\n"
    (hooks_dir / "pre-push").write_text(original, encoding="utf-8")
    bootstrap.install_pre_push(tmp_path, "noop", None, dry_run=False)  # displaces -> pre-push.bak
    assert (hooks_dir / "pre-push").read_text() == bootstrap._NOOP_PRE_PUSH

    uninstall.remove_pre_push(tmp_path, dry_run=False)
    assert (hooks_dir / "pre-push").read_text() == original
    assert not (hooks_dir / "pre-push.bak").exists()


def test_remove_pre_push_leaves_foreign_hook(tmp_path: Path) -> None:
    """A pre-push the operator replaced (not one we wrote) is never removed."""
    _git_init_repo(tmp_path)
    import bootstrap  # noqa: E402

    hooks_dir, _ = bootstrap._git_hooks_dir(tmp_path)
    foreign = "#!/bin/sh\n# hand-written\nexit 0\n"
    (hooks_dir / "pre-push").write_text(foreign, encoding="utf-8")

    status = uninstall.remove_pre_push(tmp_path, dry_run=False)
    assert "left untouched" in status
    assert (hooks_dir / "pre-push").read_text() == foreign


def test_remove_ontology_preserves_hand_edited_overlay(tmp_path: Path) -> None:
    """Generated structural files go; a hand-edited seed overlay file is preserved."""
    _git_init_repo(tmp_path)
    _install(tmp_path, "--owner", "test-org", "--with-ontology")
    import bootstrap  # noqa: E402

    overlay_files = [tmp_path / "ontology" / rel for rel, _ in bootstrap._iter_overlay_files()]
    edited = overlay_files[0]
    edited.write_text("HAND EDITED\n", encoding="utf-8")
    structural = tmp_path / "ontology" / "structural"
    assert any(structural.rglob("*"))

    uninstall.remove_ontology(tmp_path, "ontology", dry_run=False)
    assert edited.read_text() == "HAND EDITED\n", "hand-edited overlay was clobbered"
    assert not (structural.is_dir() and any(structural.rglob("*"))), "generated index not removed"


def test_confirm_gate_policy(tmp_path: Path) -> None:
    """The confirm gate: dry-run and non-interactive proceed; a non-TTY plain run refuses."""
    assert uninstall._confirm(tmp_path, non_interactive=False, dry_run=True) is True
    assert uninstall._confirm(tmp_path, non_interactive=True, dry_run=False) is True
    # pytest captures stdin -> not a TTY -> plain destructive run must refuse.
    assert uninstall._confirm(tmp_path, non_interactive=False, dry_run=False) is False


def test_teardown_via_bootstrap_entrypoint(tmp_path: Path) -> None:
    """``bootstrap.py --teardown`` dispatches to the same uninstall product."""
    _git_init_repo(tmp_path)
    pre = snap.snapshot(tmp_path)
    _install(tmp_path, "--owner", "test-org", "--no-ontology")

    r = subprocess.run(
        [sys.executable, str(_BOOTSTRAP), str(tmp_path), "--teardown", "--non-interactive"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    assert r.returncode == 0, r.stderr
    assert snap.symmetric_diff(pre, snap.snapshot(tmp_path)) == []
