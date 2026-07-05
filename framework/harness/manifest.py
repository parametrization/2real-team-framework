"""Golden-manifest bridge to Nia's #139 (fail-open until it lands on the wave branch).

#139 delivers ``framework/install/manifest.py`` exposing
``expected_install_set(config) -> set[str]`` (the relpaths the installer should produce for a
given install config) plus a generated ``framework/install/golden-manifest.json`` snapshot.
The ``files_installed_complete`` metric asserts the actual post-install ``.claude`` tree
equals that expected set.

Her PR may not be merged when the harness runs, so the import is guarded: if the module is
not importable yet, ``expected_install_set`` returns ``None`` and the metric is SKIPPED with a
clear "pending #139" note rather than crashing. Once #139 lands this wires automatically — no
harness change needed. Loaded via importlib from the file path so we do not depend on
``framework.install`` being an importable package.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_MANIFEST_PY = _FRAMEWORK_ROOT / "install" / "manifest.py"

PENDING_NOTE = "pending #139 (framework/install/manifest.py not on the wave branch yet)"


def _load():
    """Import the #139 manifest module by path, or return None if it does not exist yet."""
    if not _MANIFEST_PY.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("_harness_golden_manifest", _MANIFEST_PY)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # noqa: BLE001 — fail-open: a broken #139 must not crash the harness
        return None


def available() -> bool:
    """True iff #139's ``expected_install_set`` can be resolved."""
    mod = _load()
    return mod is not None and hasattr(mod, "expected_install_set")


def expected_install_set(config: dict) -> set[str] | None:
    """Delegate to #139's ``expected_install_set(config)``; ``None`` when #139 is absent.

    ``config`` is the resolved install config for the cell (model, team, ontology, …). The
    exact shape is #139's contract; the harness passes the permutation dict through verbatim.
    """
    mod = _load()
    if mod is None or not hasattr(mod, "expected_install_set"):
        return None
    try:
        result = mod.expected_install_set(config)
        return set(result) if result is not None else None
    except Exception:  # noqa: BLE001 — treat a manifest error as "unavailable", skip the metric
        return None
