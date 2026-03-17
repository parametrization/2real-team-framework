"""Load and validate preset configurations."""

from __future__ import annotations

import json
from pathlib import Path

from .models import PresetConfig

_PKG_DIR = Path(__file__).resolve().parent


def _resolve_presets_dir() -> Path:
    """Resolve the presets directory, checking bundled location first."""
    bundled = _PKG_DIR / "_bundled" / "presets"
    if bundled.is_dir():
        return bundled
    # Fallback: repo checkout layout  (src/real_team -> ../../.. -> repo root)
    return _PKG_DIR.parents[2] / "presets"


_PRESETS_DIR = _resolve_presets_dir()

_BUILTIN_PRESETS: dict[str, PresetConfig] = {}


def _load_builtin_presets() -> dict[str, PresetConfig]:
    """Load all built-in presets from the presets directory."""
    if _BUILTIN_PRESETS:
        return _BUILTIN_PRESETS

    if not _PRESETS_DIR.is_dir():
        return _BUILTIN_PRESETS

    for path in sorted(_PRESETS_DIR.glob("*.json")):
        with open(path) as f:
            data = json.load(f)
        preset = PresetConfig(**data)
        _BUILTIN_PRESETS[preset.name] = preset

    return _BUILTIN_PRESETS


def get_preset(name: str) -> PresetConfig:
    """Get a preset by name."""
    presets = _load_builtin_presets()
    if name not in presets:
        available = ", ".join(sorted(presets.keys()))
        raise ValueError(f"Unknown preset '{name}'. Available: {available}")
    return presets[name]


def list_presets() -> list[PresetConfig]:
    """List all available presets."""
    return list(_load_builtin_presets().values())


def load_preset_from_file(path: str) -> PresetConfig:
    """Load a preset from an arbitrary JSON file."""
    with open(path) as f:
        data = json.load(f)
    return PresetConfig(**data)
