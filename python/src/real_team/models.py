"""Pydantic models for team configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


class RoleSpec(BaseModel):
    """A role specification within a preset."""

    model_config = ConfigDict(frozen=True)

    role: str
    level: str
    count: int = 1
    required: bool = True


class PresetConfig(BaseModel):
    """A project preset defining team shape and defaults."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    default_team_size: int
    roles: list[RoleSpec]
    skills: list[str]
    default_ci: str = "github-actions"


class TeamMember(BaseModel):
    """A generated team member."""

    name: str
    agent_name: str = ""
    role: str
    level: str
    email: str
    reports_to: str = ""
    personality: str = ""


class TeamConfig(BaseModel):
    """Full team configuration for bootstrap."""

    project_name: str
    preset: str
    team_members: list[TeamMember]
    skills: list[str]
    git_email_domain: str = "gmail.com"
    git_email_prefix: str = ""


# ---------------------------------------------------------------------------
# YAML Config Schema (used by ``--config`` flag)
# ---------------------------------------------------------------------------


class MemberOverride(BaseModel):
    """Per-member override in a YAML config file."""

    name: str | None = None
    role: str | None = None
    level: str | None = None
    personality: str | None = None


class YamlConfig(BaseModel):
    """Schema for a YAML configuration file used with ``2real-team init --config``."""

    preset: str
    project_name: str | None = None
    team_size: int | None = None
    git_email_prefix: str = ""
    target: str = "."
    skills: list[str] | None = None
    members: list[MemberOverride] | None = None

    @field_validator("preset")
    @classmethod
    def preset_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("preset must not be empty")
        return v

    @classmethod
    def from_yaml(cls, path: str | Path) -> "YamlConfig":
        """Load and validate a YAML config file.

        Raises ``ValueError`` with a human-readable message on validation
        failure, and ``FileNotFoundError`` when the file does not exist.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(p) as f:
            try:
                raw: Any = yaml.safe_load(f)
            except yaml.YAMLError as exc:
                raise ValueError(f"Invalid YAML in config file ({path}): {exc}") from exc

        if not isinstance(raw, dict):
            raise ValueError(f"Config file must be a YAML mapping, got {type(raw).__name__}")

        try:
            return cls(**raw)
        except ValidationError as exc:
            lines = [f"Invalid config file ({path}):"]
            for err in exc.errors():
                loc = " -> ".join(str(l) for l in err["loc"])
                lines.append(f"  {loc}: {err['msg']}")
            raise ValueError("\n".join(lines)) from exc
