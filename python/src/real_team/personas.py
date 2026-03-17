"""AI persona generation via Claude API (optional feature)."""

from __future__ import annotations

import json
import warnings
from typing import Any

from .models import PresetConfig


def _check_anthropic() -> bool:
    """Check if the anthropic SDK is available."""
    try:
        import anthropic  # noqa: F401

        return True
    except ImportError:
        return False


def _check_api_key() -> str | None:
    """Return ANTHROPIC_API_KEY from environment, or None."""
    import os

    return os.environ.get("ANTHROPIC_API_KEY")


def generate_personas(
    preset: PresetConfig,
    roles: list[dict[str, str]],
    team_size: int,
    seed: int | None = None,
) -> list[dict[str, str]]:
    """Generate team member personas using the Claude API.

    Each persona dict has keys: name, personality, expertise.
    Falls back to empty list on any API error (caller uses local pool).

    Parameters
    ----------
    preset:
        The preset config (provides project context).
    roles:
        List of {"role": ..., "level": ...} for each member to generate.
    team_size:
        Total team size.
    seed:
        Optional seed for reproducibility (included in prompt).
    """
    if not _check_anthropic():
        warnings.warn(
            "anthropic package not installed. Install with: "
            "pip install '2real-team-framework[ai]'",
            stacklevel=2,
        )
        return []

    api_key = _check_api_key()
    if not api_key:
        warnings.warn(
            "ANTHROPIC_API_KEY not set. AI persona generation requires "
            "an API key in the environment.",
            stacklevel=2,
        )
        return []

    import anthropic

    prompt = _build_prompt(preset, roles, team_size, seed)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        return _parse_response(text, len(roles))
    except Exception as exc:
        warnings.warn(
            f"AI persona generation failed, using local pool: {exc}",
            stacklevel=2,
        )
        return []


def _build_prompt(
    preset: PresetConfig,
    roles: list[dict[str, str]],
    team_size: int,
    seed: int | None = None,
) -> str:
    """Build the prompt for Claude API."""
    role_descriptions = "\n".join(
        f"  {i + 1}. {r['role']} ({r['level']})" for i, r in enumerate(roles)
    )

    seed_note = ""
    if seed is not None:
        seed_note = (
            f"\nUse seed {seed} for deterministic generation"
            " — always produce the same names and personalities"
            " for this seed value."
        )

    return f"""Generate {len(roles)} team member personas for a software project team.

Project type: {preset.name} — {preset.description}
Team size: {team_size}
{seed_note}

Roles to fill:
{role_descriptions}

For each team member, generate:
1. A culturally diverse full name (first and last)
2. A personality/communication style (1-2 sentences describing how they communicate)
3. Areas of expertise relevant to their role (1 sentence)

IMPORTANT: Names should be culturally diverse — mix of ethnicities,
backgrounds, and naming conventions. Avoid common Anglo-Saxon defaults.

Return ONLY a JSON array with objects having these exact keys:
- "name": full name
- "personality": communication style description
- "expertise": areas of expertise

Example format:
[
  {{"name": "Yuki Tanaka", "personality": "Analytical and precise.",
"expertise": "Distributed systems and API design."}}
]

Return exactly {len(roles)} objects in the array. No other text."""


def _parse_response(text: str, expected_count: int) -> list[dict[str, str]]:
    """Parse the Claude API response into persona dicts."""
    # Extract JSON array from response
    text = text.strip()

    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        result: Any = json.loads(text)
    except json.JSONDecodeError:
        return []

    if not isinstance(result, list):
        return []

    personas = []
    for item in result[:expected_count]:
        if not isinstance(item, dict):
            continue
        persona = {
            "name": str(item.get("name", "")),
            "personality": str(item.get("personality", "")),
            "expertise": str(item.get("expertise", "")),
        }
        if persona["name"] and persona["personality"]:
            personas.append(persona)

    return personas
