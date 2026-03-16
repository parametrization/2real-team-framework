"""Tests for the 2real-team CLI."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from real_team.bootstrap import generate_name, generate_team, make_email
from real_team.cli import app
from real_team.models import PresetConfig, RoleSpec
from real_team.presets import list_presets

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
