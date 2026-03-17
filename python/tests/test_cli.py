"""Comprehensive tests for the 2real-team CLI — targeting >90% coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from real_team.bootstrap import (
    COMMUNICATION_STYLES,
    FIRST_NAMES,
    LAST_NAMES,
    _assign_reports_to,
    bootstrap_project,
    generate_name,
    generate_team,
    make_email,
)
from real_team.cli import _extract_field, _replace_field, app
from real_team.models import (
    PresetConfig,
    RoleSpec,
    TeamConfig,
    TeamMember,
)
from real_team.presets import get_preset, list_presets, load_preset_from_file
from real_team.templates import (
    list_skills,
    list_templates,
    render_skill,
    render_template,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------


class TestPresets:
    def test_list_presets(self):
        presets = list_presets()
        assert len(presets) >= 3
        names = {p.name for p in presets}
        assert "fullstack-monorepo" in names
        assert "data-pipeline" in names
        assert "library" in names

    def test_get_preset_valid(self):
        preset = get_preset("library")
        assert preset.name == "library"
        assert preset.default_team_size > 0
        assert len(preset.roles) > 0

    def test_get_preset_invalid(self):
        with pytest.raises(ValueError, match="Unknown preset"):
            get_preset("nonexistent-preset")

    @pytest.mark.parametrize("preset_name", ["library", "data-pipeline", "fullstack-monorepo"])
    def test_all_presets_load(self, preset_name: str):
        preset = get_preset(preset_name)
        assert preset.name == preset_name
        assert preset.default_team_size > 0
        assert len(preset.skills) > 0
        assert any(r.required for r in preset.roles)

    def test_load_preset_from_file(self, tmp_path: Path):
        preset_data = {
            "name": "custom",
            "description": "Custom preset",
            "default_team_size": 3,
            "roles": [{"role": "Engineer", "level": "Senior", "count": 1, "required": True}],
            "skills": ["retro"],
            "default_ci": "github-actions",
        }
        p = tmp_path / "custom.json"
        p.write_text(json.dumps(preset_data))
        loaded = load_preset_from_file(str(p))
        assert loaded.name == "custom"

    def test_preset_listing_returns_sorted(self):
        presets = list_presets()
        names = [p.name for p in presets]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# Name generation
# ---------------------------------------------------------------------------


class TestNameGeneration:
    def test_generate_unique_names(self):
        used: set[str] = set()
        for _ in range(10):
            first, last = generate_name(used)
            full = f"{first} {last}"
            assert full not in used
            used.add(full)

    def test_generate_name_exhaustion(self):
        """Should raise when no unique name can be generated."""
        used = {f"{f} {l}" for f in FIRST_NAMES for l in LAST_NAMES}
        with pytest.raises(RuntimeError, match="Could not generate"):
            generate_name(used)

    def test_name_pools_not_empty(self):
        assert len(FIRST_NAMES) > 0
        assert len(LAST_NAMES) > 0
        assert len(COMMUNICATION_STYLES) > 0


# ---------------------------------------------------------------------------
# Email generation
# ---------------------------------------------------------------------------


class TestEmail:
    def test_make_email_basic(self):
        assert make_email("Carolina", "Méndez-Ríos") == "Carolina.Mendez-Rios@gmail.com"

    def test_make_email_with_prefix(self):
        assert make_email("Tomasz", "Wójcik", "org") == "org+Tomasz.Wojcik@gmail.com"

    def test_make_email_no_prefix(self):
        email = make_email("John", "Doe")
        assert email == "John.Doe@gmail.com"
        assert "+" not in email


# ---------------------------------------------------------------------------
# Team generation
# ---------------------------------------------------------------------------


class TestTeamGeneration:
    @pytest.fixture()
    def small_preset(self) -> PresetConfig:
        return PresetConfig(
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

    def test_generate_team_size(self, small_preset: PresetConfig):
        members = generate_team(small_preset, 4)
        assert len(members) == 4

    def test_generate_team_required_roles(self, small_preset: PresetConfig):
        members = generate_team(small_preset, 4)
        roles = [m.role for m in members]
        assert "Manager" in roles
        assert "Tech Lead" in roles

    def test_generate_team_default_size(self, small_preset: PresetConfig):
        members = generate_team(small_preset)
        assert len(members) == small_preset.default_team_size

    def test_generate_team_with_override_size(self, small_preset: PresetConfig):
        members = generate_team(small_preset, 2)
        assert len(members) == 2

    def test_reports_to_set(self, small_preset: PresetConfig):
        members = generate_team(small_preset, 3)
        manager = next(m for m in members if m.role == "Manager")
        assert manager.reports_to == "User (project owner)"
        tech_lead = next(m for m in members if m.role == "Tech Lead")
        assert tech_lead.reports_to == manager.name

    @pytest.mark.parametrize("preset_name", ["library", "data-pipeline", "fullstack-monorepo"])
    def test_generate_from_real_preset(self, preset_name: str):
        preset = get_preset(preset_name)
        members = generate_team(preset)
        assert len(members) == preset.default_team_size
        assert all(m.email for m in members)
        assert all(m.personality for m in members)


# ---------------------------------------------------------------------------
# assign_reports_to
# ---------------------------------------------------------------------------


class TestAssignReportsTo:
    def test_no_manager(self):
        members = [
            TeamMember(name="A B", role="Software Engineer", level="Senior", email="a@b.com"),
        ]
        _assign_reports_to(members)
        assert members[0].reports_to == ""

    def test_with_data_roles(self):
        members = [
            TeamMember(name="Boss", role="Manager", level="Senior VP", email="b@b.com"),
            TeamMember(name="Data", role="Data Engineer", level="Staff", email="d@d.com"),
            TeamMember(name="Sci", role="Data Scientist", level="Principal", email="s@s.com"),
        ]
        _assign_reports_to(members)
        assert members[0].reports_to == "User (project owner)"
        assert members[1].reports_to == "Boss"  # Staff reports to manager
        assert members[2].reports_to == "Data"  # Data Scientist reports to Data Engineer lead

    def test_devops_reports_to_architect(self):
        members = [
            TeamMember(name="Boss", role="Manager", level="Senior VP", email="b@b.com"),
            TeamMember(name="Arch", role="DevOps Architect", level="Staff", email="a@a.com"),
            TeamMember(name="Dev", role="DevOps Engineer", level="Senior", email="d@d.com"),
        ]
        _assign_reports_to(members)
        assert members[2].reports_to == "Arch"

    def test_devops_no_architect_falls_to_manager(self):
        members = [
            TeamMember(name="Boss", role="Manager", level="Senior VP", email="b@b.com"),
            TeamMember(name="Dev", role="DevOps Engineer", level="Senior", email="d@d.com"),
        ]
        _assign_reports_to(members)
        assert members[1].reports_to == "Boss"

    def test_security_reports_to_devops_architect(self):
        members = [
            TeamMember(name="Boss", role="Manager", level="Senior VP", email="b@b.com"),
            TeamMember(name="Arch", role="DevOps Architect", level="Staff", email="a@a.com"),
            TeamMember(name="Sec", role="Security Engineer", level="Senior", email="s@s.com"),
        ]
        _assign_reports_to(members)
        assert members[2].reports_to == "Arch"

    def test_data_scientist_no_data_lead_falls_to_manager(self):
        members = [
            TeamMember(name="Boss", role="Manager", level="Senior VP", email="b@b.com"),
            TeamMember(name="Sci", role="Data Scientist", level="Senior", email="s@s.com"),
        ]
        _assign_reports_to(members)
        assert members[1].reports_to == "Boss"

    def test_data_engineer_staff_as_lead_for_data_scientist(self):
        """When no Data Engineer in leads dict, falls back to Staff-level Data member."""
        members = [
            TeamMember(name="Boss", role="Manager", level="Senior VP", email="b@b.com"),
            TeamMember(name="TL", role="Tech Lead", level="Staff", email="t@t.com"),
            TeamMember(name="DStaff", role="Data Scientist", level="Staff", email="ds@d.com"),
            TeamMember(name="DSenior", role="Data Scientist", level="Senior", email="dss@d.com"),
        ]
        _assign_reports_to(members)
        # DStaff is Staff level, reports to manager
        assert members[2].reports_to == "Boss"
        # DSenior should find DStaff as a Staff-level Data member
        assert members[3].reports_to == "DStaff"

    def test_no_manager_no_leads(self):
        members = [
            TeamMember(name="A", role="Software Engineer", level="Senior", email="a@a.com"),
            TeamMember(name="B", role="Software Engineer", level="Senior", email="b@b.com"),
        ]
        _assign_reports_to(members)
        assert members[0].reports_to == ""
        assert members[1].reports_to == ""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestModels:
    def test_role_spec_frozen(self):
        r = RoleSpec(role="Eng", level="Sr")
        with pytest.raises(Exception):
            r.role = "Mgr"  # type: ignore[misc]

    def test_preset_config_frozen(self):
        p = PresetConfig(
            name="x",
            description="y",
            default_team_size=1,
            roles=[],
            skills=[],
        )
        with pytest.raises(Exception):
            p.name = "z"  # type: ignore[misc]

    def test_team_member_optional_fields(self):
        m = TeamMember(name="A", role="E", level="S", email="e@e.com")
        assert m.reports_to == ""
        assert m.personality == ""

    def test_team_config_defaults(self):
        tc = TeamConfig(
            project_name="test",
            preset="library",
            team_members=[],
            skills=[],
        )
        assert tc.git_email_domain == "gmail.com"
        assert tc.git_email_prefix == ""

    def test_role_spec_defaults(self):
        r = RoleSpec(role="Eng", level="Sr")
        assert r.count == 1
        assert r.required is True

    def test_preset_config_default_ci(self):
        p = PresetConfig(
            name="x", description="y", default_team_size=1, roles=[], skills=[],
        )
        assert p.default_ci == "github-actions"


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


class TestTemplates:
    def test_render_template_charter(self):
        ctx = {
            "project_name": "test",
            "team_members": [{"name": "A", "role": "E", "level": "S"}],
        }
        result = render_template("charter.md.mustache", ctx)
        assert "test" in result

    def test_render_template_not_found(self):
        with pytest.raises(FileNotFoundError):
            render_template("nonexistent.mustache", {})

    def test_render_roster_card(self):
        ctx = {
            "name": "Test User",
            "role": "Engineer",
            "level": "Senior",
            "email": "test@test.com",
            "personality": "Focused.",
        }
        result = render_template("roster-card.md.mustache", ctx)
        assert "Test User" in result
        assert "Engineer" in result

    def test_render_skill(self):
        ctx = {"project_name": "test", "team_members": []}
        result = render_skill("retro.md.mustache", ctx)
        assert len(result) > 0

    def test_render_skill_not_found(self):
        with pytest.raises(FileNotFoundError):
            render_skill("nonexistent.md.mustache", {})

    def test_list_templates(self):
        templates = list_templates()
        assert len(templates) >= 5
        assert "charter.md.mustache" in templates

    def test_list_skills(self):
        skills = list_skills()
        assert len(skills) >= 1
        assert "retro.md.mustache" in skills

    def test_render_all_templates(self):
        ctx = {
            "project_name": "test",
            "team_members": [
                {
                    "name": "Test",
                    "agent_name": "test",
                    "role": "Eng",
                    "level": "Sr",
                    "email": "t@t.com",
                    "reports_to": "User",
                    "personality": "Nice.",
                }
            ],
        }
        for tmpl in list_templates():
            if tmpl == "roster-card.md.mustache":
                result = render_template(tmpl, ctx["team_members"][0])
            elif tmpl == "skill.md.mustache":
                result = render_template(tmpl, {"skill_name": "test"})
            else:
                result = render_template(tmpl, ctx)
            assert isinstance(result, str)
            assert len(result) > 0


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


class TestCLIHelpers:
    def test_extract_field(self):
        content = "- **Name:** John Doe\n- **Role:** Engineer\n"
        assert _extract_field(content, "Name") == "John Doe"
        assert _extract_field(content, "Role") == "Engineer"
        assert _extract_field(content, "Missing") is None

    def test_replace_field(self):
        content = "- **Role:** Engineer\n- **Level:** Senior\n"
        result = _replace_field(content, "Role", "Manager")
        assert "**Role:** Manager" in result
        assert "**Level:** Senior" in result

    def test_replace_field_not_found(self):
        content = "- **Name:** Test"
        result = _replace_field(content, "Role", "Manager")
        assert result == content


# ---------------------------------------------------------------------------
# CLI commands — init
# ---------------------------------------------------------------------------


class TestInitCommand:
    def test_init_noninteractive(self, tmp_path: Path):
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

    def test_init_missing_preset_noninteractive(self, tmp_path: Path):
        result = runner.invoke(app, [
            "init",
            "--target", str(tmp_path),
            "--no-interactive",
        ])
        assert result.exit_code == 1
        assert "required" in result.output.lower()

    def test_init_invalid_preset(self, tmp_path: Path):
        result = runner.invoke(app, [
            "init",
            "--preset", "nonexistent",
            "--target", str(tmp_path),
            "--no-interactive",
        ])
        assert result.exit_code != 0

    def test_init_with_config_yaml(self, tmp_path: Path):
        import yaml

        cfg = tmp_path / "config.yaml"
        cfg.write_text(yaml.dump({
            "preset": "library",
            "project_name": "config-test",
            "team_size": 3,
        }))
        target = tmp_path / "output"
        target.mkdir()
        result = runner.invoke(app, [
            "init",
            "--config", str(cfg),
            "--target", str(target),
            "--no-interactive",
        ])
        assert result.exit_code == 0
        assert (target / ".claude" / "team" / "charter.md").exists()
        cards = list((target / ".claude" / "team" / "roster").glob("*.md"))
        assert len(cards) == 3

    def test_init_with_config_yaml_git_email_prefix(self, tmp_path: Path):
        import yaml

        cfg = tmp_path / "config.yaml"
        cfg.write_text(yaml.dump({
            "preset": "library",
            "project_name": "prefix-test",
            "team_size": 2,
            "git_email_prefix": "myorg",
        }))
        target = tmp_path / "output"
        target.mkdir()
        result = runner.invoke(app, [
            "init",
            "--config", str(cfg),
            "--target", str(target),
            "--no-interactive",
        ])
        assert result.exit_code == 0

    def test_init_project_name_defaults_to_dirname(self, tmp_path: Path):
        result = runner.invoke(app, [
            "init",
            "--preset", "library",
            "--team-size", "2",
            "--no-interactive",
            "--target", str(tmp_path),
        ])
        assert result.exit_code == 0

    @pytest.mark.parametrize("preset", ["library", "data-pipeline", "fullstack-monorepo"])
    def test_init_all_presets(self, tmp_path: Path, preset: str):
        target = tmp_path / preset
        target.mkdir()
        result = runner.invoke(app, [
            "init",
            "--preset", preset,
            "--team-size", "3",
            "--project-name", f"test-{preset}",
            "--target", str(target),
            "--no-interactive",
        ])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# CLI commands — validate
# ---------------------------------------------------------------------------


class TestValidateCommand:
    def test_validate_after_init(self, tmp_path: Path):
        runner.invoke(app, [
            "init", "--preset", "library", "--team-size", "3",
            "--project-name", "validate-test", "--target", str(tmp_path),
            "--no-interactive",
        ])
        result = runner.invoke(app, ["validate", "--target", str(tmp_path)])
        assert result.exit_code == 0
        assert "passed" in result.output.lower()

    def test_validate_no_team_dir(self, tmp_path: Path):
        result = runner.invoke(app, ["validate", "--target", str(tmp_path)])
        assert result.exit_code == 1

    def test_validate_missing_charter(self, tmp_path: Path):
        roster_dir = tmp_path / ".claude" / "team" / "roster"
        roster_dir.mkdir(parents=True)
        (tmp_path / ".claude" / "team" / "trust_matrix.md").touch()
        (tmp_path / ".claude" / "team" / "feedback_log.md").touch()
        (roster_dir / "test.md").write_text("- **Name:** Test\n")
        result = runner.invoke(app, ["validate", "--target", str(tmp_path)])
        assert result.exit_code == 1
        assert "charter" in result.output.lower()

    def test_validate_no_active_members(self, tmp_path: Path):
        team_dir = tmp_path / ".claude" / "team"
        roster_dir = team_dir / "roster"
        roster_dir.mkdir(parents=True)
        (team_dir / "charter.md").touch()
        (team_dir / "trust_matrix.md").touch()
        (team_dir / "feedback_log.md").touch()
        result = runner.invoke(app, ["validate", "--target", str(tmp_path)])
        assert result.exit_code == 1
        assert "no active" in result.output.lower()

    def test_validate_missing_roster_dir(self, tmp_path: Path):
        team_dir = tmp_path / ".claude" / "team"
        team_dir.mkdir(parents=True)
        (team_dir / "charter.md").touch()
        (team_dir / "trust_matrix.md").touch()
        (team_dir / "feedback_log.md").touch()
        result = runner.invoke(app, ["validate", "--target", str(tmp_path)])
        assert result.exit_code == 1
        assert "roster" in result.output.lower()

    def test_validate_missing_trust_and_feedback(self, tmp_path: Path):
        team_dir = tmp_path / ".claude" / "team"
        roster_dir = team_dir / "roster"
        roster_dir.mkdir(parents=True)
        (team_dir / "charter.md").touch()
        (roster_dir / "engineer_alice.md").write_text("- **Name:** Alice\n")
        result = runner.invoke(app, ["validate", "--target", str(tmp_path)])
        assert result.exit_code == 1
        assert "trust_matrix" in result.output.lower()
        assert "feedback_log" in result.output.lower()

    def test_validate_with_skills(self, tmp_path: Path):
        """validate should report skill count when skills dir exists."""
        runner.invoke(app, [
            "init", "--preset", "library", "--team-size", "3",
            "--project-name", "skill-validate", "--target", str(tmp_path),
            "--no-interactive",
        ])
        result = runner.invoke(app, ["validate", "--target", str(tmp_path)])
        assert result.exit_code == 0
        assert "skills" in result.output.lower()


# ---------------------------------------------------------------------------
# CLI commands — status
# ---------------------------------------------------------------------------


class TestStatusCommand:
    def test_status_after_init(self, tmp_path: Path):
        runner.invoke(app, [
            "init", "--preset", "library", "--team-size", "3",
            "--project-name", "status-test", "--target", str(tmp_path),
            "--no-interactive",
        ])
        result = runner.invoke(app, ["status", "--target", str(tmp_path)])
        assert result.exit_code == 0
        assert "Active" in result.output

    def test_status_no_team(self, tmp_path: Path):
        result = runner.invoke(app, ["status", "--target", str(tmp_path)])
        assert result.exit_code == 1

    def test_status_with_departed(self, tmp_path: Path):
        runner.invoke(app, [
            "init", "--preset", "library", "--team-size", "3",
            "--project-name", "dep-test", "--target", str(tmp_path),
            "--no-interactive",
        ])
        roster_dir = tmp_path / ".claude" / "team" / "roster"
        cards = list(roster_dir.glob("*.md"))
        card = cards[0]
        archived = card.parent / f"_departed_{card.name}"
        card.rename(archived)
        result = runner.invoke(app, ["status", "--target", str(tmp_path)])
        assert result.exit_code == 0
        assert "Archived" in result.output

    def test_status_with_skills(self, tmp_path: Path):
        runner.invoke(app, [
            "init", "--preset", "library", "--team-size", "2",
            "--project-name", "skill-status", "--target", str(tmp_path),
            "--no-interactive",
        ])
        result = runner.invoke(app, ["status", "--target", str(tmp_path)])
        assert result.exit_code == 0
        assert "Skills installed" in result.output


# ---------------------------------------------------------------------------
# CLI commands — add-member
# ---------------------------------------------------------------------------


class TestAddMemberCommand:
    def test_add_named_member(self, tmp_path: Path):
        runner.invoke(app, [
            "init", "--preset", "library", "--team-size", "3",
            "--project-name", "add-test", "--target", str(tmp_path),
            "--no-interactive",
        ])
        result = runner.invoke(app, [
            "add-member", "Jane Doe",
            "--role", "DevOps Engineer",
            "--level", "Senior",
            "--target", str(tmp_path),
        ])
        assert result.exit_code == 0
        assert "Jane Doe" in result.output

    def test_add_random_member(self, tmp_path: Path):
        runner.invoke(app, [
            "init", "--preset", "library", "--team-size", "3",
            "--project-name", "add-test", "--target", str(tmp_path),
            "--no-interactive",
        ])
        result = runner.invoke(app, [
            "add-member",
            "--role", "QA Engineer",
            "--target", str(tmp_path),
        ])
        assert result.exit_code == 0
        assert "Added" in result.output

    def test_add_member_no_roster(self, tmp_path: Path):
        result = runner.invoke(app, [
            "add-member", "Test",
            "--role", "Engineer",
            "--target", str(tmp_path),
        ])
        assert result.exit_code == 1

    def test_add_member_single_name(self, tmp_path: Path):
        """add-member with a single name (no space) should handle gracefully."""
        runner.invoke(app, [
            "init", "--preset", "library", "--team-size", "2",
            "--project-name", "single-test", "--target", str(tmp_path),
            "--no-interactive",
        ])
        result = runner.invoke(app, [
            "add-member", "Mononym",
            "--role", "Engineer",
            "--target", str(tmp_path),
        ])
        assert result.exit_code == 0
        assert "Mononym" in result.output


# ---------------------------------------------------------------------------
# CLI commands — remove-member
# ---------------------------------------------------------------------------


class TestRemoveMemberCommand:
    def _get_first_member_name(self, tmp_path: Path) -> str:
        roster_dir = tmp_path / ".claude" / "team" / "roster"
        cards = list(roster_dir.glob("*.md"))
        content = cards[0].read_text()
        for line in content.splitlines():
            if "**Name:**" in line:
                return line.split("**Name:**")[1].strip()
        raise AssertionError("No name found in roster card")

    def test_remove_member(self, tmp_path: Path):
        runner.invoke(app, [
            "init", "--preset", "library", "--team-size", "3",
            "--project-name", "remove-test", "--target", str(tmp_path),
            "--no-interactive",
        ])
        name = self._get_first_member_name(tmp_path)
        result = runner.invoke(app, [
            "remove-member", name,
            "--target", str(tmp_path),
        ])
        assert result.exit_code == 0
        assert "Archived" in result.output

    def test_remove_nonexistent_member(self, tmp_path: Path):
        runner.invoke(app, [
            "init", "--preset", "library", "--team-size", "3",
            "--project-name", "remove-test", "--target", str(tmp_path),
            "--no-interactive",
        ])
        result = runner.invoke(app, [
            "remove-member", "Nobody Here",
            "--target", str(tmp_path),
        ])
        assert result.exit_code == 1

    def test_remove_member_no_roster(self, tmp_path: Path):
        result = runner.invoke(app, [
            "remove-member", "Test",
            "--target", str(tmp_path),
        ])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# CLI commands — update-member
# ---------------------------------------------------------------------------


class TestUpdateMemberCommand:
    def _get_first_member_name(self, tmp_path: Path) -> str:
        roster_dir = tmp_path / ".claude" / "team" / "roster"
        cards = list(roster_dir.glob("*.md"))
        content = cards[0].read_text()
        for line in content.splitlines():
            if "**Name:**" in line:
                return line.split("**Name:**")[1].strip()
        raise AssertionError("No name found")

    def test_update_role(self, tmp_path: Path):
        runner.invoke(app, [
            "init", "--preset", "library", "--team-size", "3",
            "--project-name", "update-test", "--target", str(tmp_path),
            "--no-interactive",
        ])
        name = self._get_first_member_name(tmp_path)
        result = runner.invoke(app, [
            "update-member", name,
            "--role", "Principal Architect",
            "--target", str(tmp_path),
        ])
        assert result.exit_code == 0
        assert "Updated" in result.output

    def test_update_level_only(self, tmp_path: Path):
        runner.invoke(app, [
            "init", "--preset", "library", "--team-size", "3",
            "--project-name", "update-test", "--target", str(tmp_path),
            "--no-interactive",
        ])
        name = self._get_first_member_name(tmp_path)
        result = runner.invoke(app, [
            "update-member", name,
            "--level", "Partner",
            "--target", str(tmp_path),
        ])
        assert result.exit_code == 0

    def test_update_nonexistent(self, tmp_path: Path):
        runner.invoke(app, [
            "init", "--preset", "library", "--team-size", "3",
            "--project-name", "update-test", "--target", str(tmp_path),
            "--no-interactive",
        ])
        result = runner.invoke(app, [
            "update-member", "Nobody",
            "--role", "Manager",
            "--target", str(tmp_path),
        ])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# CLI commands — randomize-member
# ---------------------------------------------------------------------------


class TestRandomizeMemberCommand:
    def _get_first_member_name(self, tmp_path: Path) -> str:
        roster_dir = tmp_path / ".claude" / "team" / "roster"
        cards = list(roster_dir.glob("*.md"))
        content = cards[0].read_text()
        for line in content.splitlines():
            if "**Name:**" in line:
                return line.split("**Name:**")[1].strip()
        raise AssertionError("No name found")

    def test_randomize_member(self, tmp_path: Path):
        runner.invoke(app, [
            "init", "--preset", "library", "--team-size", "3",
            "--project-name", "rand-test", "--target", str(tmp_path),
            "--no-interactive",
        ])
        name = self._get_first_member_name(tmp_path)
        result = runner.invoke(app, [
            "randomize-member", name,
            "--target", str(tmp_path),
        ])
        assert result.exit_code == 0
        assert "Archived" in result.output
        assert "Created" in result.output

    def test_randomize_nonexistent(self, tmp_path: Path):
        runner.invoke(app, [
            "init", "--preset", "library", "--team-size", "3",
            "--project-name", "rand-test", "--target", str(tmp_path),
            "--no-interactive",
        ])
        result = runner.invoke(app, [
            "randomize-member", "Nobody",
            "--target", str(tmp_path),
        ])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# End-to-end lifecycle
# ---------------------------------------------------------------------------


class TestE2ELifecycle:
    def test_full_lifecycle(self, tmp_path: Path):
        """init -> add-member -> update-member -> remove-member -> validate -> status"""
        # 1. Init
        result = runner.invoke(app, [
            "init", "--preset", "library", "--team-size", "3",
            "--project-name", "lifecycle-test", "--target", str(tmp_path),
            "--no-interactive",
        ])
        assert result.exit_code == 0

        # 2. Add member
        result = runner.invoke(app, [
            "add-member", "E2E Tester",
            "--role", "QA Engineer",
            "--level", "Senior",
            "--target", str(tmp_path),
        ])
        assert result.exit_code == 0

        # 3. Update member
        result = runner.invoke(app, [
            "update-member", "E2E Tester",
            "--role", "QA Lead",
            "--level", "Staff",
            "--target", str(tmp_path),
        ])
        assert result.exit_code == 0

        # 4. Remove member
        result = runner.invoke(app, [
            "remove-member", "E2E Tester",
            "--target", str(tmp_path),
        ])
        assert result.exit_code == 0

        # 5. Validate
        result = runner.invoke(app, ["validate", "--target", str(tmp_path)])
        assert result.exit_code == 0

        # 6. Status
        result = runner.invoke(app, ["status", "--target", str(tmp_path)])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# bootstrap_project direct tests
# ---------------------------------------------------------------------------


class TestBootstrapProject:
    def test_creates_all_files(self, tmp_path: Path):
        preset = get_preset("library")
        members = generate_team(preset, 3)
        config = TeamConfig(
            project_name="direct-test",
            preset="library",
            team_members=members,
            skills=preset.skills,
        )
        created = bootstrap_project(tmp_path, config)
        assert len(created) > 0
        assert any("charter.md" in f for f in created)
        assert any("trust_matrix.md" in f for f in created)
        assert any("feedback_log.md" in f for f in created)
        assert any("CLAUDE.md" in f for f in created)

    def test_creates_skills(self, tmp_path: Path):
        preset = get_preset("library")
        members = generate_team(preset, 3)
        config = TeamConfig(
            project_name="skills-test",
            preset="library",
            team_members=members,
            skills=["retro"],
        )
        created = bootstrap_project(tmp_path, config)
        skill_files = [f for f in created if "skills" in f]
        assert len(skill_files) >= 1

    def test_missing_skill_template_skipped(self, tmp_path: Path):
        members = [
            TeamMember(
                name="Test", role="Eng", level="Sr",
                email="t@t.com",
            ),
        ]
        config = TeamConfig(
            project_name="test",
            preset="library",
            team_members=members,
            skills=["nonexistent-skill"],
        )
        created = bootstrap_project(tmp_path, config)
        assert all("nonexistent" not in f for f in created)

    def test_creates_roster_cards(self, tmp_path: Path):
        members = [
            TeamMember(name="Alice Smith", role="Manager", level="Senior VP", email="a@b.com"),
            TeamMember(name="Bob Jones", role="Engineer", level="Senior", email="b@b.com"),
        ]
        config = TeamConfig(
            project_name="roster-test",
            preset="library",
            team_members=members,
            skills=[],
        )
        created = bootstrap_project(tmp_path, config)
        roster_files = [f for f in created if "roster/" in f]
        assert len(roster_files) == 2
