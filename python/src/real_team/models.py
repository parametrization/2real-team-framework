"""Pydantic models for team configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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
