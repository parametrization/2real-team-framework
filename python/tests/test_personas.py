"""Tests for AI persona generation module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from real_team.models import PresetConfig, RoleSpec
from real_team.personas import _build_prompt, _parse_response, generate_personas


@pytest.fixture
def library_preset() -> PresetConfig:
    return PresetConfig(
        name="library",
        description="Open source library",
        default_team_size=3,
        roles=[
            RoleSpec(role="Manager", level="Senior VP", count=1, required=True),
            RoleSpec(role="Tech Lead", level="Staff", count=1, required=True),
        ],
        skills=["retro"],
    )


class TestBuildPrompt:
    def test_includes_role_info(self, library_preset: PresetConfig):
        roles = [{"role": "Tech Lead", "level": "Staff"}]
        prompt = _build_prompt(library_preset, roles, 3)
        assert "Tech Lead" in prompt
        assert "Staff" in prompt
        assert "library" in prompt

    def test_includes_seed(self, library_preset: PresetConfig):
        roles = [{"role": "Engineer", "level": "Senior"}]
        prompt = _build_prompt(library_preset, roles, 3, seed=42)
        assert "seed 42" in prompt

    def test_no_seed_note_without_seed(self, library_preset: PresetConfig):
        roles = [{"role": "Engineer", "level": "Senior"}]
        prompt = _build_prompt(library_preset, roles, 3)
        assert "seed" not in prompt.lower()


class TestParseResponse:
    def test_valid_json_array(self):
        response = json.dumps([
            {"name": "Yuki Tanaka", "personality": "Analytical.", "expertise": "APIs"},
            {"name": "Ada Chen", "personality": "Direct.", "expertise": "Testing"},
        ])
        result = _parse_response(response, 2)
        assert len(result) == 2
        assert result[0]["name"] == "Yuki Tanaka"
        assert result[1]["name"] == "Ada Chen"

    def test_code_block_wrapping(self):
        response = "```json\n" + json.dumps([
            {"name": "Test User", "personality": "Friendly.", "expertise": "Code"}
        ]) + "\n```"
        result = _parse_response(response, 1)
        assert len(result) == 1
        assert result[0]["name"] == "Test User"

    def test_invalid_json(self):
        result = _parse_response("not json at all", 1)
        assert result == []

    def test_non_array(self):
        result = _parse_response('{"name": "test"}', 1)
        assert result == []

    def test_truncates_to_expected_count(self):
        response = json.dumps([
            {"name": "A", "personality": "X.", "expertise": "Y"},
            {"name": "B", "personality": "X.", "expertise": "Y"},
            {"name": "C", "personality": "X.", "expertise": "Y"},
        ])
        result = _parse_response(response, 2)
        assert len(result) == 2

    def test_skips_items_missing_name(self):
        response = json.dumps([
            {"name": "", "personality": "X.", "expertise": "Y"},
            {"name": "Valid", "personality": "Good.", "expertise": "Z"},
        ])
        result = _parse_response(response, 2)
        assert len(result) == 1
        assert result[0]["name"] == "Valid"


class TestGeneratePersonas:
    def test_returns_empty_without_anthropic(self, library_preset: PresetConfig):
        with patch("real_team.personas._check_anthropic", return_value=False):
            result = generate_personas(
                library_preset,
                [{"role": "Engineer", "level": "Senior"}],
                3,
            )
            assert result == []

    def test_returns_empty_without_api_key(self, library_preset: PresetConfig):
        with (
            patch("real_team.personas._check_anthropic", return_value=True),
            patch("real_team.personas._check_api_key", return_value=None),
        ):
            result = generate_personas(
                library_preset,
                [{"role": "Engineer", "level": "Senior"}],
                3,
            )
            assert result == []

    def test_successful_generation(self, library_preset: PresetConfig):
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps([
            {
                "name": "Kenji Sato",
                "personality": "Direct and clear.",
                "expertise": "Backend systems",
            },
        ])

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with (
            patch("real_team.personas._check_anthropic", return_value=True),
            patch("real_team.personas._check_api_key", return_value="sk-test"),
            patch.dict("sys.modules", {"anthropic": mock_anthropic}),
        ):
            result = generate_personas(
                library_preset,
                [{"role": "Engineer", "level": "Senior"}],
                3,
            )
            assert len(result) == 1
            assert result[0]["name"] == "Kenji Sato"

    def test_api_error_returns_empty(self, library_preset: PresetConfig):
        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value.messages.create.side_effect = RuntimeError("API down")

        with (
            patch("real_team.personas._check_anthropic", return_value=True),
            patch("real_team.personas._check_api_key", return_value="sk-test"),
            patch.dict("sys.modules", {"anthropic": mock_anthropic}),
        ):
            result = generate_personas(
                library_preset,
                [{"role": "Engineer", "level": "Senior"}],
                3,
            )
            assert result == []
