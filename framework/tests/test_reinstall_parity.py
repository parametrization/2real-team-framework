"""Reinstall-on-change enforcement (issue #116).

This repo is both the framework SOURCE and a live consumer of it. When a Claude asset is
edited in the canonical install source (``framework/assets/**``), the live ``.claude/**``
copy must be regenerated from it via ``framework/install/reinstall.py`` so the two never
drift.

The headline test (`test_repo_in_sync_with_canonical`) is the CI gate: it fails a PR that
edited a canonical mirrored asset (or its live copy) without running reinstall — the
automated enforcement AC #116 asks for, generalising the hardcoded-list skill-parity test
to *every* file under a managed tree. The rest exercise the reinstall engine itself.

Stdlib + pytest only.
"""

from __future__ import annotations

import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "install"))

import reinstall  # noqa: E402


# --------------------------------------------------------------- the CI gate


def test_repo_in_sync_with_canonical() -> None:
    """Every managed live copy is byte-identical to its canonical source (no drift)."""
    drift = reinstall.plan()
    assert drift == [], (
        "live .claude/ copies have drifted from canonical framework/assets/ — run "
        "`python3 framework/install/reinstall.py` to reinstall:\n  " + "\n  ".join(drift)
    )


def test_managed_trees_are_present() -> None:
    """The managed canonical trees exist (guards against a silently empty reinstall)."""
    for canon_sub, _live_sub in reinstall._MANAGED_TREES:
        assert (_FRAMEWORK_ROOT / "assets" / canon_sub).is_dir(), (
            f"managed canonical tree missing: framework/assets/{canon_sub}"
        )


# --------------------------------------------------------------- engine behaviour


def _fake_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Build a tiny (assets_root, claude_root) pair with one managed 'skills' tree."""
    assets = tmp_path / "assets"
    claude = tmp_path / ".claude"
    (assets / "skills" / "demo").mkdir(parents=True)
    (assets / "skills" / "demo" / "SKILL.md").write_text("canonical body\n", encoding="utf-8")
    return assets, claude


def test_plan_flags_missing_live_copy(tmp_path: Path) -> None:
    assets, claude = _fake_repo(tmp_path)
    assert reinstall.plan(assets, claude) == [".claude/skills/demo/SKILL.md"]


def test_apply_materializes_and_then_plan_is_clean(tmp_path: Path) -> None:
    assets, claude = _fake_repo(tmp_path)
    written = reinstall.apply(assets, claude)
    assert written == [".claude/skills/demo/SKILL.md"]
    assert (claude / "skills" / "demo" / "SKILL.md").read_text() == "canonical body\n"
    # In sync now, and re-applying is a no-op (idempotent).
    assert reinstall.plan(assets, claude) == []
    assert reinstall.apply(assets, claude) == []


def test_plan_flags_hand_edited_live_copy(tmp_path: Path) -> None:
    assets, claude = _fake_repo(tmp_path)
    reinstall.apply(assets, claude)
    # Someone edits the LIVE copy without updating canonical → drift in the other direction.
    (claude / "skills" / "demo" / "SKILL.md").write_text("hand edit\n", encoding="utf-8")
    assert reinstall.plan(assets, claude) == [".claude/skills/demo/SKILL.md"]


def test_apply_leaves_live_only_assets_untouched(tmp_path: Path) -> None:
    """A live-only skill (no canonical counterpart) is never deleted by reinstall."""
    assets, claude = _fake_repo(tmp_path)
    reinstall.apply(assets, claude)
    local = claude / "skills" / "repo-local" / "SKILL.md"
    local.parent.mkdir(parents=True)
    local.write_text("local only\n", encoding="utf-8")
    reinstall.apply(assets, claude)
    assert local.is_file()  # untouched
    assert reinstall.plan(assets, claude) == []  # live-only extras are not drift
