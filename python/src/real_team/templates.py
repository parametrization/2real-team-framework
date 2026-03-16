"""Mustache template rendering using chevron."""

from __future__ import annotations

from pathlib import Path

import chevron

_TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"
_SKILLS_DIR = Path(__file__).resolve().parents[3] / "skills"


def render_template(template_name: str, context: dict) -> str:
    """Render a Mustache template with the given context.

    Args:
        template_name: Name of the template file (e.g., "charter.md.mustache").
        context: Dictionary of variables to pass to the template.

    Returns:
        Rendered string.
    """
    template_path = _TEMPLATES_DIR / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    with open(template_path) as f:
        template = f.read()

    return chevron.render(template, context)


def render_skill(skill_name: str, context: dict) -> str:
    """Render a skill template.

    Args:
        skill_name: Name of the skill file (e.g., "retro.md.mustache").
        context: Dictionary of variables.

    Returns:
        Rendered string.
    """
    skill_path = _SKILLS_DIR / skill_name
    if not skill_path.exists():
        raise FileNotFoundError(f"Skill template not found: {skill_path}")

    with open(skill_path) as f:
        template = f.read()

    return chevron.render(template, context)


def list_templates() -> list[str]:
    """List available template names."""
    if not _TEMPLATES_DIR.is_dir():
        return []
    return sorted(p.name for p in _TEMPLATES_DIR.glob("*.mustache"))


def list_skills() -> list[str]:
    """List available skill template names."""
    if not _SKILLS_DIR.is_dir():
        return []
    return sorted(p.name for p in _SKILLS_DIR.glob("*.mustache"))
