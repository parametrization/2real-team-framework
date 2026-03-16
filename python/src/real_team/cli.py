"""2real-team CLI — AI agent team framework for Claude Code projects."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .bootstrap import bootstrap_project, generate_team
from .models import TeamConfig
from .presets import get_preset, list_presets

app = typer.Typer(name="2real-team", help="AI agent team framework for Claude Code projects")
console = Console()


@app.command()
def init(
    preset: str = typer.Option(
        None, help="Project preset (fullstack-monorepo, data-pipeline, library)"
    ),
    team_size: int = typer.Option(None, help="Override default team size"),
    config: str = typer.Option(None, help="Path to config YAML file"),
    project_name: str = typer.Option(None, help="Project name"),
    target: str = typer.Option(".", help="Target directory"),
    interactive: bool = typer.Option(True, help="Interactive mode"),
    git_email_prefix: str = typer.Option(
        "", help="Email prefix (e.g., 'myorg' -> myorg+First.Last@gmail.com)"
    ),
) -> None:
    """Bootstrap a new project with the team framework."""
    target_path = Path(target).resolve()

    if config:
        import yaml

        with open(config) as f:
            data = yaml.safe_load(f)
        preset = data.get("preset", preset)
        team_size = data.get("team_size", team_size)
        project_name = data.get("project_name", project_name)
        git_email_prefix = data.get("git_email_prefix", git_email_prefix)

    if not preset and interactive:
        available = list_presets()
        console.print("\n[bold]Available presets:[/bold]")
        for p in available:
            console.print(
                f"  [cyan]{p.name}[/cyan] — {p.description}"
                f" (default size: {p.default_team_size})"
            )
        preset = typer.prompt("\nChoose a preset", type=str)

    if not preset:
        console.print("[red]Error:[/red] --preset is required in non-interactive mode")
        raise typer.Exit(1)

    if not project_name and interactive:
        project_name = typer.prompt("Project name", default=target_path.name)
    elif not project_name:
        project_name = target_path.name

    preset_config = get_preset(preset)

    if not team_size and interactive:
        team_size = typer.prompt(
            "Team size",
            default=preset_config.default_team_size,
            type=int,
        )

    console.print(f"\n[bold]Generating team for [cyan]{project_name}[/cyan]...[/bold]")
    members = generate_team(preset_config, team_size)

    team_config = TeamConfig(
        project_name=project_name,
        preset=preset,
        team_members=members,
        skills=preset_config.skills,
        git_email_prefix=git_email_prefix,
    )

    created = bootstrap_project(target_path, team_config)

    console.print(f"\n[green]Created {len(created)} files:[/green]")
    for f in created:
        console.print(f"  {f}")

    console.print(f"\n[bold green]Team framework bootstrapped for '{project_name}'![/bold green]")
    console.print("Next steps:")
    console.print("  1. Review .claude/team/charter.md")
    console.print("  2. Customize roster cards in .claude/team/roster/")
    console.print("  3. Add team section to your CLAUDE.md")


@app.command()
def add_member(
    name: str = typer.Argument(None, help="Member name (random if omitted)"),
    role: str = typer.Option(..., help="Role (e.g., 'Software Engineer')"),
    level: str = typer.Option("Senior", help="Level"),
    target: str = typer.Option(".", help="Target directory"),
) -> None:
    """Add a team member to the roster."""
    from .bootstrap import generate_name, make_email
    from .templates import render_template

    target_path = Path(target).resolve()
    roster_dir = target_path / ".claude" / "team" / "roster"

    if not roster_dir.exists():
        console.print("[red]Error:[/red] No roster directory found. Run `2real-team init` first.")
        raise typer.Exit(1)

    if not name:
        used = {p.stem.replace("_", " ") for p in roster_dir.glob("*.md")}
        first, last = generate_name(used)
        name = f"{first} {last}"

    parts = name.split(" ", 1)
    first, last = parts[0], parts[1] if len(parts) > 1 else ""
    email = make_email(first, last)

    context = {
        "name": name,
        "role": role,
        "level": level,
        "email": email,
        "personality": "To be defined.",
    }

    card = render_template("roster-card.md.mustache", context)
    safe_name = name.lower().replace(" ", "_").replace("-", "_")
    role_prefix = role.lower().replace(" ", "_")
    card_path = roster_dir / f"{role_prefix}_{safe_name}.md"
    card_path.write_text(card)

    rel = card_path.relative_to(target_path)
    console.print(f"[green]Added:[/green] {name} ({role}, {level}) -> {rel}")


@app.command()
def remove_member(
    name: str = typer.Argument(..., help="Member name to archive"),
    target: str = typer.Option(".", help="Target directory"),
) -> None:
    """Archive a team member (prefix with _departed_)."""
    target_path = Path(target).resolve()
    roster_dir = target_path / ".claude" / "team" / "roster"

    if not roster_dir.exists():
        console.print("[red]Error:[/red] No roster directory found.")
        raise typer.Exit(1)

    # Find the matching file
    safe_name = name.lower().replace(" ", "_").replace("-", "_")
    matches = list(roster_dir.glob(f"*{safe_name}*"))
    matches = [m for m in matches if not m.name.startswith("_departed_")]

    if not matches:
        console.print(f"[red]Error:[/red] No active roster card found for '{name}'")
        raise typer.Exit(1)

    for match in matches:
        archived = match.parent / f"_departed_{match.name}"
        match.rename(archived)
        console.print(f"[yellow]Archived:[/yellow] {match.name} → {archived.name}")


@app.command()
def update_member(
    name: str = typer.Argument(..., help="Member name to update"),
    role: str = typer.Option(None, help="New role"),
    level: str = typer.Option(None, help="New level"),
    target: str = typer.Option(".", help="Target directory"),
) -> None:
    """Update a team member's configuration."""
    target_path = Path(target).resolve()
    roster_dir = target_path / ".claude" / "team" / "roster"

    safe_name = name.lower().replace(" ", "_").replace("-", "_")
    matches = list(roster_dir.glob(f"*{safe_name}*"))
    matches = [m for m in matches if not m.name.startswith("_departed_")]

    if not matches:
        console.print(f"[red]Error:[/red] No active roster card found for '{name}'")
        raise typer.Exit(1)

    card_path = matches[0]
    content = card_path.read_text()

    if role:
        content = _replace_field(content, "Role", role)
    if level:
        content = _replace_field(content, "Level", level)

    card_path.write_text(content)
    console.print(f"[green]Updated:[/green] {name}")


@app.command()
def randomize_member(
    name: str = typer.Argument(..., help="Member name to regenerate"),
    target: str = typer.Option(".", help="Target directory"),
) -> None:
    """Regenerate a team member's name, background, and personality."""
    import random

    from .bootstrap import COMMUNICATION_STYLES, generate_name, make_email
    from .templates import render_template

    target_path = Path(target).resolve()
    roster_dir = target_path / ".claude" / "team" / "roster"

    safe_name = name.lower().replace(" ", "_").replace("-", "_")
    matches = list(roster_dir.glob(f"*{safe_name}*"))
    matches = [m for m in matches if not m.name.startswith("_departed_")]

    if not matches:
        console.print(f"[red]Error:[/red] No active roster card found for '{name}'")
        raise typer.Exit(1)

    old_path = matches[0]
    content = old_path.read_text()

    # Extract role and level from existing card
    role = _extract_field(content, "Role") or "Software Engineer"
    level = _extract_field(content, "Level") or "Senior"

    # Archive old
    archived = old_path.parent / f"_departed_{old_path.name}"
    old_path.rename(archived)

    # Generate new identity
    used = {p.stem.replace("_", " ") for p in roster_dir.glob("*.md")}
    first, last = generate_name(used)
    new_name = f"{first} {last}"
    email = make_email(first, last)

    context = {
        "name": new_name,
        "role": role,
        "level": level,
        "email": email,
        "personality": random.choice(COMMUNICATION_STYLES),
    }

    card = render_template("roster-card.md.mustache", context)
    new_safe = new_name.lower().replace(" ", "_").replace("-", "_")
    role_prefix = role.lower().replace(" ", "_")
    new_path = roster_dir / f"{role_prefix}_{new_safe}.md"
    new_path.write_text(card)

    console.print(f"[yellow]Archived:[/yellow] {name} → {archived.name}")
    console.print(f"[green]Created:[/green] {new_name} ({role}, {level}) → {new_path.name}")


@app.command()
def validate(
    target: str = typer.Option(".", help="Target directory"),
) -> None:
    """Verify charter, roster, and skills consistency."""
    target_path = Path(target).resolve()
    team_dir = target_path / ".claude" / "team"
    skills_dir = target_path / ".claude" / "skills"
    errors: list[str] = []

    if not team_dir.exists():
        console.print(
            "[red]Error:[/red] No .claude/team/ directory found."
            " Run `2real-team init` first."
        )
        raise typer.Exit(1)

    # Check charter exists
    if not (team_dir / "charter.md").exists():
        errors.append("Missing charter.md")

    # Check roster
    roster_dir = team_dir / "roster"
    if not roster_dir.exists():
        errors.append("Missing roster/ directory")
    else:
        active = [p for p in roster_dir.glob("*.md") if not p.name.startswith("_departed_")]
        if not active:
            errors.append("No active roster cards found")
        else:
            console.print(f"[dim]Found {len(active)} active team members[/dim]")

    # Check trust matrix
    if not (team_dir / "trust_matrix.md").exists():
        errors.append("Missing trust_matrix.md")

    # Check feedback log
    if not (team_dir / "feedback_log.md").exists():
        errors.append("Missing feedback_log.md")

    # Check skills
    if skills_dir.exists():
        skills = list(skills_dir.glob("*.md"))
        console.print(f"[dim]Found {len(skills)} skills[/dim]")
    else:
        console.print("[dim]No skills directory found[/dim]")

    if errors:
        console.print(f"\n[red]Validation failed with {len(errors)} error(s):[/red]")
        for e in errors:
            console.print(f"  [red]x[/red] {e}")
        raise typer.Exit(1)
    else:
        console.print("\n[green]Validation passed![/green]")


@app.command()
def status(
    target: str = typer.Option(".", help="Target directory"),
) -> None:
    """Show team composition and project status."""
    target_path = Path(target).resolve()
    roster_dir = target_path / ".claude" / "team" / "roster"

    if not roster_dir.exists():
        console.print("[red]No team found.[/red] Run `2real-team init` first.")
        raise typer.Exit(1)

    table = Table(title="Team Roster")
    table.add_column("Name", style="cyan")
    table.add_column("Role")
    table.add_column("Level")
    table.add_column("Status")

    for card_path in sorted(roster_dir.glob("*.md")):
        content = card_path.read_text()
        name = _extract_field(content, "Name") or card_path.stem
        role = _extract_field(content, "Role") or "?"
        level = _extract_field(content, "Level") or "?"
        is_departed = card_path.name.startswith("_departed_")
        status_str = "[red]Archived[/red]" if is_departed else "[green]Active[/green]"
        table.add_row(name, role, level, status_str)

    console.print(table)

    # Count skills
    skills_dir = target_path / ".claude" / "skills"
    if skills_dir.exists():
        skill_count = len(list(skills_dir.glob("*.md")))
        console.print(f"\nSkills installed: {skill_count}")


def _extract_field(content: str, field: str) -> str | None:
    """Extract a field value from a roster card."""
    for line in content.splitlines():
        if f"**{field}:**" in line:
            return line.split(f"**{field}:**", 1)[1].strip()
    return None


def _replace_field(content: str, field: str, value: str) -> str:
    """Replace a field value in a roster card."""
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if f"**{field}:**" in line:
            prefix = line.split(f"**{field}:**")[0]
            lines[i] = f"{prefix}**{field}:** {value}"
            break
    return "\n".join(lines)


if __name__ == "__main__":
    app()
