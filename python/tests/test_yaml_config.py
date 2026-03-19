"""Unit/edge-case tests for YAML config file mode (issue #33).

Covers edge cases identified during QA review of PR #23 that are not
covered by the existing integration tests in test_cli.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from real_team.models import MemberOverride, YamlConfig


# ---------------------------------------------------------------------------
# YamlConfig.from_yaml — error paths
# ---------------------------------------------------------------------------


class TestYamlConfigFromYaml:
    def test_missing_file_raises_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            YamlConfig.from_yaml(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_syntax_raises_value_error(self, tmp_path: Path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("preset: [\n  invalid yaml here")
        with pytest.raises(ValueError, match="Invalid YAML"):
            YamlConfig.from_yaml(bad_yaml)

    def test_non_mapping_yaml_raises_value_error(self, tmp_path: Path):
        list_yaml = tmp_path / "list.yaml"
        list_yaml.write_text("- item1\n- item2\n")
        with pytest.raises(ValueError, match="YAML mapping"):
            YamlConfig.from_yaml(list_yaml)

    def test_scalar_yaml_raises_value_error(self, tmp_path: Path):
        scalar_yaml = tmp_path / "scalar.yaml"
        scalar_yaml.write_text("just a string\n")
        with pytest.raises(ValueError, match="YAML mapping"):
            YamlConfig.from_yaml(scalar_yaml)

    def test_missing_preset_field_raises_value_error(self, tmp_path: Path):
        no_preset = tmp_path / "no_preset.yaml"
        no_preset.write_text(yaml.dump({"project_name": "test", "team_size": 3}))
        with pytest.raises(ValueError, match="preset"):
            YamlConfig.from_yaml(no_preset)

    def test_empty_preset_raises_value_error(self, tmp_path: Path):
        empty_preset = tmp_path / "empty.yaml"
        empty_preset.write_text(yaml.dump({"preset": ""}))
        with pytest.raises(ValueError, match="preset"):
            YamlConfig.from_yaml(empty_preset)

    def test_whitespace_only_preset_raises_value_error(self, tmp_path: Path):
        ws_preset = tmp_path / "ws.yaml"
        ws_preset.write_text(yaml.dump({"preset": "   "}))
        with pytest.raises(ValueError, match="preset"):
            YamlConfig.from_yaml(ws_preset)

    def test_team_size_as_string_raises_validation_error(self, tmp_path: Path):
        bad_size = tmp_path / "bad_size.yaml"
        bad_size.write_text("preset: library\nteam_size: not_a_number\n")
        with pytest.raises(ValueError, match="team_size"):
            YamlConfig.from_yaml(bad_size)


# ---------------------------------------------------------------------------
# YamlConfig — valid edge cases
# ---------------------------------------------------------------------------


class TestYamlConfigValid:
    def test_minimal_config(self, tmp_path: Path):
        cfg_path = tmp_path / "minimal.yaml"
        cfg_path.write_text(yaml.dump({"preset": "library"}))
        cfg = YamlConfig.from_yaml(cfg_path)
        assert cfg.preset == "library"
        assert cfg.project_name is None
        assert cfg.team_size is None
        assert cfg.git_email_prefix == ""
        assert cfg.target == "."
        assert cfg.skills is None
        assert cfg.members is None

    def test_full_config(self, tmp_path: Path):
        data = {
            "preset": "fullstack-monorepo",
            "project_name": "my-project",
            "team_size": 5,
            "git_email_prefix": "myorg",
            "target": "/tmp/out",
            "skills": ["retro", "wave-start"],
            "members": [
                {"name": "Alice Smith", "role": "Tech Lead", "level": "Staff"},
                {"name": "Bob Jones"},
            ],
        }
        cfg_path = tmp_path / "full.yaml"
        cfg_path.write_text(yaml.dump(data))
        cfg = YamlConfig.from_yaml(cfg_path)
        assert cfg.preset == "fullstack-monorepo"
        assert cfg.project_name == "my-project"
        assert cfg.team_size == 5
        assert cfg.git_email_prefix == "myorg"
        assert cfg.skills == ["retro", "wave-start"]
        assert len(cfg.members) == 2
        assert cfg.members[0].name == "Alice Smith"
        assert cfg.members[1].role is None


# ---------------------------------------------------------------------------
# MemberOverride — optional fields
# ---------------------------------------------------------------------------


class TestMemberOverride:
    def test_all_optional_fields_omitted(self):
        override = MemberOverride()
        assert override.name is None
        assert override.role is None
        assert override.level is None
        assert override.personality is None

    def test_partial_override_name_only(self):
        override = MemberOverride(name="Alice Smith")
        assert override.name == "Alice Smith"
        assert override.role is None
        assert override.level is None
        assert override.personality is None

    def test_partial_override_personality_only(self):
        override = MemberOverride(personality="Very direct and concise.")
        assert override.personality == "Very direct and concise."
        assert override.name is None
        assert override.role is None

    def test_full_override(self):
        override = MemberOverride(
            name="Test User",
            role="Manager",
            level="Senior VP",
            personality="Empathetic leader.",
        )
        assert override.name == "Test User"
        assert override.role == "Manager"
        assert override.level == "Senior VP"
        assert override.personality == "Empathetic leader."


# ---------------------------------------------------------------------------
# Behavioral edge cases — init with member overrides
# ---------------------------------------------------------------------------


class TestYamlConfigBehavioral:
    def test_member_overrides_exceeding_team_size(self, tmp_path: Path):
        """Extras in members array beyond team_size should be silently ignored."""
        from typer.testing import CliRunner

        from real_team.cli import app

        runner = CliRunner()
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(yaml.dump({
            "preset": "library",
            "team_size": 2,
            "members": [
                {"name": "Alice Smith"},
                {"name": "Bob Jones"},
                {"name": "Charlie Brown"},  # exceeds team_size of 2
                {"name": "Diana Prince"},   # exceeds team_size of 2
            ],
        }))
        target = tmp_path / "output"
        target.mkdir()
        result = runner.invoke(app, [
            "init",
            "--config", str(cfg_path),
            "--target", str(target),
            "--no-interactive",
        ])
        assert result.exit_code == 0
        roster_dir = target / ".claude" / "team" / "roster"
        cards = list(roster_dir.glob("*.md"))
        assert len(cards) == 2  # only team_size members created
        card_contents = [c.read_text() for c in cards]
        names_in_cards = " ".join(card_contents)
        assert "Alice Smith" in names_in_cards
        assert "Bob Jones" in names_in_cards
        # Charlie and Diana should NOT appear
        assert "Charlie Brown" not in names_in_cards
        assert "Diana Prince" not in names_in_cards

    def test_partial_member_overrides(self, tmp_path: Path):
        """Override with only personality, no name/role should work."""
        from typer.testing import CliRunner

        from real_team.cli import app

        runner = CliRunner()
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(yaml.dump({
            "preset": "library",
            "team_size": 3,
            "members": [
                {"personality": "Very analytical and detail-oriented."},
            ],
        }))
        target = tmp_path / "output"
        target.mkdir()
        result = runner.invoke(app, [
            "init",
            "--config", str(cfg_path),
            "--target", str(target),
            "--no-interactive",
        ])
        assert result.exit_code == 0
        # The first member should still exist with a generated name
        roster_dir = target / ".claude" / "team" / "roster"
        cards = list(roster_dir.glob("*.md"))
        assert len(cards) == 3

    def test_git_email_prefix_applied_to_overridden_members(self, tmp_path: Path):
        """git_email_prefix should be applied when member names are overridden."""
        from typer.testing import CliRunner

        from real_team.cli import app

        runner = CliRunner()
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(yaml.dump({
            "preset": "library",
            "team_size": 2,
            "git_email_prefix": "myorg",
            "members": [
                {"name": "Alice Smith"},
            ],
        }))
        target = tmp_path / "output"
        target.mkdir()
        result = runner.invoke(app, [
            "init",
            "--config", str(cfg_path),
            "--target", str(target),
            "--no-interactive",
        ])
        assert result.exit_code == 0
        roster_dir = target / ".claude" / "team" / "roster"
        cards = list(roster_dir.glob("*.md"))
        alice_cards = [c for c in cards if "alice" in c.name]
        assert len(alice_cards) == 1
        content = alice_cards[0].read_text()
        assert "myorg+Alice.Smith@gmail.com" in content

    def test_null_yaml_raises_value_error(self, tmp_path: Path):
        """An empty YAML file (parses to None) should raise ValueError."""
        null_yaml = tmp_path / "null.yaml"
        null_yaml.write_text("")
        with pytest.raises(ValueError, match="YAML mapping"):
            YamlConfig.from_yaml(null_yaml)
