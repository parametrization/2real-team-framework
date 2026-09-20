"""Custom hatch build hook to bundle shared data directories into the wheel.

Shared templates, presets, and skills live at the repo root (one level above
the ``python/`` package directory).  When building a wheel directly from the
repo checkout the parent-relative paths work fine, but when pip builds a wheel
*from an sdist* the extraction directory layout changes.  This hook resolves
the correct source for each directory and adds it to the wheel under
``real_team/_bundled/``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


def _sync_readme() -> None:
    """Mirror the repo-root README into ``python/`` so it can be packaged.

    A single README at the repo root serves PyPI, npm and GitHub, so the Python
    package has none of its own.  ``readme = "../README.md"`` used to paper over
    that, but hatchling >=1.32 rejects a readme outside the project directory,
    and older versions "honoured" it by writing an sdist member that escaped the
    archive root (``<name>-<version>/../README.md``).  ``pyproject.toml`` now
    names a local ``README.md`` and we put one there.

    This runs at import time rather than from ``initialize`` below because
    hatchling reads project metadata -- the readme included -- before it builds
    any build hook, so the file has to exist before the hook is ever called.
    """
    here = Path(__file__).parent
    source = here.parent / "README.md"
    # Missing when building from an sdist, which already carries its own copy.
    if source.is_file():
        shutil.copyfile(source, here / "README.md")


_sync_readme()


class BundleSharedDataHook(BuildHookInterface):
    """Copy shared data dirs into the wheel package."""

    PLUGIN_NAME = "bundle-shared-data"

    # "framework" carries the config-driven runtime (install/ + assets/ + config/)
    # that `2real-team init --with-hooks` installs via framework/install/bootstrap.py.
    _DIRS = ("templates", "presets", "skills", "framework")

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
