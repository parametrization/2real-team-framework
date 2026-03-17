"""Custom hatch build hook to bundle shared data directories into the wheel.

Shared templates, presets, and skills live at the repo root (one level above
the ``python/`` package directory).  When building a wheel directly from the
repo checkout the parent-relative paths work fine, but when pip builds a wheel
*from an sdist* the extraction directory layout changes.  This hook resolves
the correct source for each directory and adds it to the wheel under
``real_team/_bundled/``.
"""

from __future__ import annotations

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class BundleSharedDataHook(BuildHookInterface):
    """Copy shared data dirs into the wheel package."""

    PLUGIN_NAME = "bundle-shared-data"

    _DIRS = ("templates", "presets", "skills")

    def initialize(self, version: str, build_data: dict) -> None:  # noqa: ARG002
        root = Path(self.root)

        force_include = build_data.setdefault("force_include", {})

        for name in self._DIRS:
            # Try multiple locations where the shared data might be:
            candidates = [
                root.parent / name,                    # Repo checkout: ../templates
                root / name,                           # sdist with top-level dirs
                root / "real_team" / "_bundled" / name, # sdist where hook already bundled
                root / "src" / "real_team" / "_bundled" / name,  # alternate layout
            ]

            src = next((p for p in candidates if p.is_dir()), None)
            if src is not None:
                force_include[str(src)] = f"real_team/_bundled/{name}"
