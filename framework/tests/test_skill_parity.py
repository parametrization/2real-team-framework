"""Dual-deploy parity for team skills (issues #85, #86).

Every skill that ships in BOTH ``framework/assets/skills/`` (canonical) and this repo's
``.claude/skills/`` (dogfood) must be byte-identical in the two locations, and the skills
ported in #85 (team-reset, wave-audit, wave-start) and enriched in #86 (close-stale-issues,
plan-phase, retro, wave-retro, phase-review) must be present in both. Asset skills are
generic framework artifacts, so they must carry no org names or hardcoded owners.
Stdlib + pytest only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _FRAMEWORK_ROOT.parent
_ASSET_SKILLS = _FRAMEWORK_ROOT / "assets" / "skills"
_DOGFOOD_SKILLS = _REPO_ROOT / ".claude" / "skills"

# Skills that MUST exist in both locations (dual-deploy requirement).
DUAL_DEPLOY_REQUIRED = (
    "team-reset",
    "wave-audit",
    "wave-start",
    # Lifecycle skills (#86)
    "close-stale-issues",
    "plan-phase",
    "retro",
    "wave-retro",
    "phase-review",
)

# Strings that must never appear in a canonical (assets) skill.
FORBIDDEN = ("noorinalabs", "parametrization", "2real-team-framework")


def _asset_skill_dirs() -> list[Path]:
    return sorted(p for p in _ASSET_SKILLS.iterdir() if (p / "SKILL.md").is_file())


def test_asset_skills_exist() -> None:
    names = {p.name for p in _asset_skill_dirs()}
    for required in DUAL_DEPLOY_REQUIRED:
        assert required in names, f"missing canonical skill: assets/skills/{required}/SKILL.md"


def test_required_skills_present_in_dogfood() -> None:
    for required in DUAL_DEPLOY_REQUIRED:
        dogfood = _DOGFOOD_SKILLS / required / "SKILL.md"
        assert dogfood.is_file(), f"missing dogfood copy: .claude/skills/{required}/SKILL.md"


@pytest.mark.parametrize("skill_dir", _asset_skill_dirs(), ids=lambda p: p.name)
def test_shared_skills_byte_identical(skill_dir: Path) -> None:
    """Any skill present in both trees must match byte-for-byte."""
    dogfood = _DOGFOOD_SKILLS / skill_dir.name / "SKILL.md"
    if not dogfood.is_file():
        pytest.skip(f"{skill_dir.name} has no dogfood copy (assets-only skill)")
    canonical_bytes = (skill_dir / "SKILL.md").read_bytes()
    assert canonical_bytes == dogfood.read_bytes(), (
        f"assets/skills/{skill_dir.name}/SKILL.md and .claude/skills/{skill_dir.name}/SKILL.md "
        "have diverged — copy the canonical assets version over the dogfood copy"
    )


@pytest.mark.parametrize("skill_dir", _asset_skill_dirs(), ids=lambda p: p.name)
def test_asset_skills_are_parameterized(skill_dir: Path) -> None:
    """Canonical skills carry no org names / hardcoded owners."""
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8").lower()
    for token in FORBIDDEN:
        assert token not in text, f"assets/skills/{skill_dir.name}/SKILL.md contains '{token}'"
