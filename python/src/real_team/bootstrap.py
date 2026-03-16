"""Core bootstrap logic — reads presets, renders templates, writes files."""

from __future__ import annotations

import random
from pathlib import Path

from rich.console import Console

from .models import PresetConfig, TeamConfig, TeamMember
from .presets import get_preset
from .templates import render_skill, render_template

console = Console()

# Name pools for random team member generation
FIRST_NAMES = [
    "Aisha", "Amara", "Andrei", "Björk", "Carolina", "Chen", "Dmitri",
    "Elena", "Fatima", "Hiro", "Ibrahim", "Jada", "Kai", "Kwame", "Lena",
    "Mei-Lin", "Nadia", "Omar", "Priya", "Ravi", "Renaud", "Sakura",
    "Sunita", "Tariq", "Tomasz", "Yara", "Zara", "Alejandro", "Beatriz",
    "Ciro", "Dalia", "Elio", "Femi", "Greta", "Hugo", "Ingrid", "Jun",
    "Kofi", "Lila", "Marco", "Nia", "Oscar", "Paloma", "Qasim", "Rosa",
    "Sven", "Tara", "Umar", "Vera", "Wei", "Xena", "Yuki", "Zuri",
]

LAST_NAMES = [
    "Asante", "Al-Rashidi", "Bianchi", "Chang", "Diallo", "Eriksson",
    "Fernández", "García", "Hadid", "Inoue", "Jensen", "Krishnamurthy",
    "López", "Méndez-Ríos", "Nakamura", "Okonkwo", "Petrova", "Qureshi",
    "Rossi", "Singh", "Tanaka", "Ueda", "Volkov", "Wójcik", "Xu",
    "Yamamoto", "Zhang", "Abubakar", "Bjornsson", "Costa", "Devi",
    "El-Amin", "Fischer", "Gupta", "Hassan", "Ito", "Johansson", "Kim",
    "Li", "Morales", "Nair", "Osei", "Park", "Rahman", "Sato",
    "Tremblay", "Uchida", "Vargas", "Wang", "Yamada", "Zhao",
]

COMMUNICATION_STYLES = [
    "Direct and structured. Prefers bullet points and numbered lists over prose.",
    "Deliberate and thorough. Reads the entire thread before responding.",
    "Enthusiastic and collaborative. Brings energy to discussions.",
    "Analytical and precise. Favors data-driven decisions.",
    "Pragmatic and concise. Focuses on what needs to get done.",
    "Thoughtful and empathetic. Considers team dynamics in every decision.",
    "Crisp and action-oriented. Every message ends with a clear next step.",
    "Measured and diplomatic. Navigates disagreements with tact.",
]


def generate_name(used_names: set[str]) -> tuple[str, str]:
    """Generate a unique random name."""
    for _ in range(100):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        full = f"{first} {last}"
        if full not in used_names:
            return first, last
    raise RuntimeError("Could not generate a unique name after 100 attempts")


def make_email(first: str, last: str, prefix: str = "") -> str:
    """Generate a git email from a name."""
    # Strip diacritics for email (simple approach)
    import unicodedata

    def strip_diacritics(s: str) -> str:
        return "".join(
            c for c in unicodedata.normalize("NFD", s)
            if unicodedata.category(c) != "Mn"
        )

    clean_first = strip_diacritics(first).replace(" ", ".")
    clean_last = strip_diacritics(last).replace(" ", ".")
    if prefix:
        return f"{prefix}+{clean_first}.{clean_last}@gmail.com"
    return f"{clean_first}.{clean_last}@gmail.com"


def generate_team(preset: PresetConfig, team_size: int | None = None) -> list[TeamMember]:
    """Generate team members from a preset."""
    size = team_size or preset.default_team_size
    used_names: set[str] = set()
    members: list[TeamMember] = []

    # First pass: required roles
    for role_spec in preset.roles:
        if not role_spec.required:
            continue
        for _ in range(role_spec.count):
            if len(members) >= size:
                break
            first, last = generate_name(used_names)
            full_name = f"{first} {last}"
            used_names.add(full_name)
            style = random.choice(COMMUNICATION_STYLES)
            members.append(TeamMember(
                name=full_name,
                role=role_spec.role,
                level=role_spec.level,
                email=make_email(first, last),
                personality=style,
            ))

    # Second pass: optional roles to fill up to team_size
    optional_roles = [r for r in preset.roles if not r.required]
    for role_spec in optional_roles:
        for _ in range(role_spec.count):
            if len(members) >= size:
                break
            first, last = generate_name(used_names)
            full_name = f"{first} {last}"
            used_names.add(full_name)
            style = random.choice(COMMUNICATION_STYLES)
            members.append(TeamMember(
                name=full_name,
                role=role_spec.role,
                level=role_spec.level,
                email=make_email(first, last),
                personality=style,
            ))

    # Assign reporting relationships
    _assign_reports_to(members)
    return members


def _assign_reports_to(members: list[TeamMember]) -> None:
    """Assign reports_to based on role hierarchy."""
    manager = next((m for m in members if m.role == "Manager"), None)
    leads = {m.role: m for m in members if m.level in ("Partner", "Staff")}

    for member in members:
        if member.role == "Manager":
            member.reports_to = "User (project owner)"
        elif member.level in ("Partner", "Staff"):
            if manager:
                member.reports_to = manager.name
        elif member.role in ("DevOps Engineer", "Security Engineer"):
            devops_arch = leads.get("DevOps Architect")
            member.reports_to = devops_arch.name if devops_arch else (manager.name if manager else "")
        elif member.role in ("Data Engineer", "Data Scientist"):
            data_lead = leads.get("Data Engineer")
            if not data_lead:
                data_lead = next((m for m in members if "Data" in m.role and m.level == "Staff"), None)
            member.reports_to = data_lead.name if data_lead else (manager.name if manager else "")
        else:
            tech_lead = leads.get("Tech Lead")
            member.reports_to = tech_lead.name if tech_lead else (manager.name if manager else "")


def bootstrap_project(
    target_dir: Path,
    config: TeamConfig,
) -> list[str]:
    """Bootstrap the team framework into a target project directory.

    Returns a list of created file paths (relative to target_dir).
    """
    created_files: list[str] = []
    team_dir = target_dir / ".claude" / "team"
    roster_dir = team_dir / "roster"
    skills_dir = target_dir / ".claude" / "skills"

    roster_dir.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)

    context = {
        "project_name": config.project_name,
        "team_members": [m.model_dump() for m in config.team_members],
    }

    # Render charter
    charter = render_template("charter.md.mustache", context)
    charter_path = team_dir / "charter.md"
    charter_path.write_text(charter)
    created_files.append(str(charter_path.relative_to(target_dir)))

    # Render roster cards
    for member in config.team_members:
        member_context = member.model_dump()
        card = render_template("roster-card.md.mustache", member_context)
        safe_name = member.name.lower().replace(" ", "_").replace("-", "_")
        role_prefix = member.role.lower().replace(" ", "_")
        card_path = roster_dir / f"{role_prefix}_{safe_name}.md"
        card_path.write_text(card)
        created_files.append(str(card_path.relative_to(target_dir)))

    # Render trust matrix
    trust = render_template("trust-matrix.md.mustache", context)
    trust_path = team_dir / "trust_matrix.md"
    trust_path.write_text(trust)
    created_files.append(str(trust_path.relative_to(target_dir)))

    # Render feedback log
    feedback = render_template("feedback-log.md.mustache", context)
    feedback_path = team_dir / "feedback_log.md"
    feedback_path.write_text(feedback)
    created_files.append(str(feedback_path.relative_to(target_dir)))

    # Render CLAUDE.md
    claude_md = render_template("CLAUDE.md.mustache", context)
    claude_path = target_dir / ".claude" / "CLAUDE.md"
    claude_path.write_text(claude_md)
    created_files.append(str(claude_path.relative_to(target_dir)))

    # Render skills
    skill_context = {
        "project_name": config.project_name,
        "team_members": [m.model_dump() for m in config.team_members],
    }
    for skill_name in config.skills:
        template_name = f"{skill_name}.md.mustache"
        try:
            rendered = render_skill(template_name, skill_context)
        except FileNotFoundError:
            continue
        skill_path = skills_dir / f"{skill_name}.md"
        skill_path.write_text(rendered)
        created_files.append(str(skill_path.relative_to(target_dir)))

    return created_files
