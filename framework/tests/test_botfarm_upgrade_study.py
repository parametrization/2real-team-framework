"""Hermetic test for the #109 B11 upgrade-over-live-install study (archive + fresh + restore).

Proven against a throwaway LOCAL git repo carrying a synthetic *pre-existing* ``.claude`` install
(the stand-in for botfarm's own diverged install) — no network, no real botfarm fixture (that run
is #109 proper). Asserts the load-bearing claim: after archive → fresh install → restore, the
managed Claude assets are byte-identical to their pre-existing state, the old assets are moved out
of Claude scope mid-flow, the live source is untouched, and the scratch clone is torn down clean.
Stdlib + pytest only.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _FRAMEWORK_ROOT.parent
sys.path.insert(0, str(_REPO_ROOT))  # make `framework.harness` importable (namespace package)

from framework.harness.botfarm_upgrade_study import run_study  # noqa: E402


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _repo_with_preexisting_install(path: Path) -> None:
    """A foreign existing project that ALREADY carries its own diverged .claude install."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "src").mkdir()
    (path / "src" / "main.py").write_text("print('app')\n", encoding="utf-8")
    (path / "CLAUDE.md").write_text("# botfarm's own hand-evolved CLAUDE.md\n", encoding="utf-8")
    claude = path / ".claude"
    (claude / "team" / "roster").mkdir(parents=True)
    (claude / "team" / "roster.json").write_text(
        '{"Diverged Owner": "owner", "Diverged Eng": "engineer"}\n', encoding="utf-8"
    )
    (claude / "settings.json").write_text('{"foreignKey": "keep-me"}\n', encoding="utf-8")
    (claude / "hooks").mkdir()
    (claude / "hooks" / "custom_botfarm_hook.py").write_text("# their own hook\n", encoding="utf-8")
    _git(path, "init", "-q")
    _git(path, "add", "-A")
    subprocess.run(
        ["git", "-C", str(path), "-c", "user.name=Fx", "-c", "user.email=fx@e.com",
         "commit", "-q", "-m", "botfarm diverged install"],
        check=True, capture_output=True,
    )
    _git(path, "branch", "-M", "main")


def test_upgrade_study_restores_byte_identical(tmp_path: Path) -> None:
    src = tmp_path / "botfarm-synthetic"
    _repo_with_preexisting_install(src)

    ev = run_study(source=str(src), pin=None)

    # source cloned read-only and left byte-identical
    assert ev["source_unchanged_after_provision"] is True
    assert ev["source_unchanged"] is True

    # BEFORE: the diverged install was present
    assert set(ev["before"]["present_assets"]) == {".claude", "CLAUDE.md"}
    assert ev["before"]["roster_members"] == ["Diverged Eng", "Diverged Owner"]

    # ARCHIVE moved both managed assets out of Claude scope
    assert ev["archive"]["action"] == "archived"
    assert set(ev["archive"]["moved"]) == {".claude", "CLAUDE.md"}
    assert ev["post_archive"]["root_assets_present"] == []
    assert ev["post_archive"]["roster_members_at_root"] == []  # old roster no longer loaded
    assert set(ev["post_archive"]["archived_assets_present"]) == {".claude", "CLAUDE.md"}

    # FRESH install laid down a different (clean) install
    assert ev["fresh_install"]["returncode"] == 0
    assert ev["fresh_install"]["differs_from_before"] is True
    assert ev["fresh_install"]["roster_members"] != ev["before"]["roster_members"]

    # RESTORE returns the managed assets byte-identical
    assert set(ev["restore"]["restored"]) == {".claude", "CLAUDE.md"}
    assert ev["restore"]["conflicts"] == []
    assert ev["restore"]["managed_symmetric_diff"] == []
    assert ev["restore"]["byte_identical"] is True

    # teardown drops the scratch clone -> zero residue by construction
    assert ev["teardown_scratch_removed"] is True
