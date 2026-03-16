"""Tests for the 2real-team CLI."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from real_team.bootstrap import (
    generate_name,
    generate_team,
    make_email,
)
from real_team.cli import app
from real_team.models import PresetConfig, RoleSpec
from real_team.presets import list_presets
from real_team.templates import render_template

runner = CliRunner()


def test_list_presets():
    """Built-in presets should be loadable."""
    presets = list_presets()
    assert len(presets) >= 3
    names = {p.name for p in presets}
    assert "fullstack-monorepo" in names
    assert "data-pipeline" in names
    assert "library" in names


def test_generate_name():
    """Name generation should produce unique names."""
    used: set[str] = set()
    for _ in range(10):
        first, last = generate_name(used)
        full = f"{first} {last}"
        assert full not in used
        used.add(full)


def test_make_email():
    """Email generation should handle diacritics."""
    assert make_email("Carolina", "Méndez-Ríos") == "Carolina.Mendez-Rios@gmail.com"
    assert make_email("Tomasz", "Wójcik", "org") == "org+Tomasz.Wojcik@gmail.com"


def test_generate_team():
    """Team generation should respect preset constraints."""
    preset = PresetConfig(
        name="test",
        description="Test preset",
        default_team_size=5,
        roles=[
            RoleSpec(role="Manager", level="Senior VP", count=1, required=True),
            RoleSpec(role="Tech Lead", level="Staff", count=1, required=True),
            RoleSpec(role="Software Engineer", level="Senior", count=3, required=False),
        ],
        skills=["retro"],
    )
    members = generate_team(preset, 4)
    assert len(members) == 4
    roles = [m.role for m in members]
    assert "Manager" in roles
    assert "Tech Lead" in roles


def test_init_noninteractive(tmp_path: Path):
    """Init command should create files in non-interactive mode."""
    result = runner.invoke(app, [
        "init",
        "--preset", "fullstack-monorepo",
        "--team-size", "5",
        "--project-name", "test-project",
        "--target", str(tmp_path),
        "--no-interactive",
    ])
    assert result.exit_code == 0
    assert (tmp_path / ".claude" / "team" / "charter.md").exists()
    assert (tmp_path / ".claude" / "team" / "trust_matrix.md").exists()
    assert (tmp_path / ".claude" / "team" / "feedback_log.md").exists()
    roster_dir = tmp_path / ".claude" / "team" / "roster"
    assert roster_dir.exists()
    cards = list(roster_dir.glob("*.md"))
    assert len(cards) == 5


def test_validate_after_init(tmp_path: Path):
    """Validate should pass on a freshly initialized project."""
    runner.invoke(app, [
        "init",
        "--preset", "library",
        "--team-size", "3",
        "--project-name", "validate-test",
        "--target", str(tmp_path),
        "--no-interactive",
    ])
    result = runner.invoke(app, ["validate", "--target", str(tmp_path)])
    assert result.exit_code == 0
    assert "passed" in result.output.lower()


def test_status_after_init(tmp_path: Path):
    """Status should show team members after init."""
    runner.invoke(app, [
        "init",
        "--preset", "library",
        "--team-size", "3",
        "--project-name", "status-test",
        "--target", str(tmp_path),
        "--no-interactive",
    ])
    result = runner.invoke(app, ["status", "--target", str(tmp_path)])
    assert result.exit_code == 0
    assert "Active" in result.output


# --- Template rendering tests ---


def test_render_charter_template():
    """Charter template should include project name."""
    result = render_template("charter.md.mustache", {
        "project_name": "my-test-project",
        "team_members": [{"name": "Alice", "role": "Engineer", "level": "Senior"}],
    })
    assert "my-test-project" in result


def test_render_roster_card_template():
    """Roster card template should include member details."""
    result = render_template("roster-card.md.mustache", {
        "name": "Alice Smith",
        "role": "Engineer",
        "level": "Senior",
        "email": "alice@test.com",
        "personality": "Direct and structured.",
    })
    assert "Alice Smith" in result
    assert "Engineer" in result
    assert "Senior" in result
    assert "alice@test.com" in result


# --- Member management tests ---


def test_add_member(tmp_path: Path):
    """add-member should create a new roster card."""
    runner.invoke(app, [
        "init",
        "--preset", "library",
        "--team-size", "2",
        "--project-name", "add-test",
        "--target", str(tmp_path),
        "--no-interactive",
    ])
    result = runner.invoke(app, [
        "add-member", "Test Person",
        "--role", "QA Engineer",
        "--level", "Mid",
        "--target", str(tmp_path),
    ])
    assert result.exit_code == 0
    assert "Added" in result.output

    roster_dir = tmp_path / ".claude" / "team" / "roster"
    cards = list(roster_dir.glob("*.md"))
    assert len(cards) == 3
    assert any("test_person" in c.name for c in cards)


def test_add_member_random_name(tmp_path: Path):
    """add-member without name should generate a random name."""
    runner.invoke(app, [
        "init",
        "--preset", "library",
        "--team-size", "2",
        "--project-name", "add-rand-test",
        "--target", str(tmp_path),
        "--no-interactive",
    ])
    result = runner.invoke(app, [
        "add-member",
        "--role", "QA Engineer",
        "--target", str(tmp_path),
    ])
    assert result.exit_code == 0
    assert "Added" in result.output

    roster_dir = tmp_path / ".claude" / "team" / "roster"
    cards = list(roster_dir.glob("*.md"))
    assert len(cards) == 3


def test_remove_member(tmp_path: Path):
    """remove-member should archive a roster card."""
    runner.invoke(app, [
        "init",
        "--preset", "library",
        "--team-size", "2",
        "--project-name", "remove-test",
        "--target", str(tmp_path),
        "--no-interactive",
    ])
    roster_dir = tmp_path / ".claude" / "team" / "roster"
    cards = list(roster_dir.glob("*.md"))
    first_card = cards[0]
    content = first_card.read_text()

    # Extract the member's name from the card
    for line in content.splitlines():
        if "**Name:**" in line:
            member_name = line.split("**Name:**")[1].strip()
            break

    result = runner.invoke(app, [
        "remove-member", member_name,
        "--target", str(tmp_path),
    ])
    assert result.exit_code == 0
    assert "Archived" in result.output

    active = [p for p in roster_dir.glob("*.md") if not p.name.startswith("_departed_")]
    departed = [p for p in roster_dir.glob("*.md") if p.name.startswith("_departed_")]
    assert len(active) == 1
    assert len(departed) == 1


def test_update_member(tmp_path: Path):
    """update-member should modify role and level."""
    runner.invoke(app, [
        "init",
        "--preset", "library",
        "--team-size", "2",
        "--project-name", "update-test",
        "--target", str(tmp_path),
        "--no-interactive",
    ])
    roster_dir = tmp_path / ".claude" / "team" / "roster"
    cards = list(roster_dir.glob("*.md"))
    content = cards[0].read_text()

    for line in content.splitlines():
        if "**Name:**" in line:
            member_name = line.split("**Name:**")[1].strip()
            break

    result = runner.invoke(app, [
        "update-member", member_name,
        "--role", "Principal Engineer",
        "--level", "Staff",
        "--target", str(tmp_path),
    ])
    assert result.exit_code == 0
    assert "Updated" in result.output

    updated_content = cards[0].read_text()
    assert "Principal Engineer" in updated_content
    assert "Staff" in updated_content


def test_randomize_member(tmp_path: Path):
    """randomize-member should archive old and create new card."""
    runner.invoke(app, [
        "init",
        "--preset", "library",
        "--team-size", "2",
        "--project-name", "randomize-test",
        "--target", str(tmp_path),
        "--no-interactive",
    ])
    roster_dir = tmp_path / ".claude" / "team" / "roster"
    cards = list(roster_dir.glob("*.md"))
    content = cards[0].read_text()

    for line in content.splitlines():
        if "**Name:**" in line:
            member_name = line.split("**Name:**")[1].strip()
            break

    result = runner.invoke(app, [
        "randomize-member", member_name,
        "--target", str(tmp_path),
    ])
    assert result.exit_code == 0
    assert "Archived" in result.output
    assert "Created" in result.output

    active = [p for p in roster_dir.glob("*.md") if not p.name.startswith("_departed_")]
    departed = [p for p in roster_dir.glob("*.md") if p.name.startswith("_departed_")]
    assert len(active) == 2
    assert len(departed) == 1
