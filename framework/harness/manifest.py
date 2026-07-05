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

#: Harness runtime model token -> canonical install-config ``project.model`` token. This MUST
#: match ``install_config.INSTALL_MODEL_MAP`` (guarded by
#: ``test_harness_model_map_matches_install_config``); #139's ``expected_install_set`` branches
#: on the install-config spelling (``standalone`` / ``meta`` / ``child``), NOT the harness's
#: runtime spelling (``single-repo`` / ``meta-and-children`` / ``child``).
_HARNESS_MODEL_TO_INSTALL = {
    "single-repo": "standalone",
    "meta-and-children": "meta",
    "child": "child",
}


def permutation_to_install_config(permutation: dict) -> dict:
    """Convert a harness leg's FLAT permutation into the NESTED resolved install-config shape.

    #139's ``expected_install_set`` reads its input with dotted
    ``install_config.get_key(config, "project.model")`` / ``"team.enabled"`` — i.e. it expects a
    nested dict (the ``.claude/install.config.json`` shape), not the harness's flat permutation.
    Passing the flat dict silently resolved EVERY cell to the ``standalone`` / team-enabled
    default (the discriminant was ignored), so a child/meta/no-team cell would be mis-graded.
    This maps the permutation's ``model``/``team`` into ``project.model`` (canonical install
    token) + ``team.enabled`` so the manifest branch matches the cell's actual install mode.
    """
    model = permutation.get("model", "standalone")
    canonical = _HARNESS_MODEL_TO_INSTALL.get(model, model)  # identity if already canonical
    team_enabled = bool(permutation.get("team", True))
    config: dict = {"project": {"model": canonical}, "team": {"enabled": team_enabled}}
    if "flavor" in permutation:
        config["project"]["flavor"] = permutation["flavor"]
    return config


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


def expected_install_set(permutation: dict) -> set[str] | None:
    """Expected ``.claude/**`` relpaths for a cell's PERMUTATION; ``None`` when #139 is absent.

    Takes the harness leg's FLAT permutation, converts it to the nested install-config shape
    #139 consumes (see ``permutation_to_install_config``), and delegates to
    #139's ``expected_install_set``. Converting here — the single seam — is what makes the
    permutation discriminant actually reach the manifest (the #139 config-shape fix).
    """
    mod = _load()
    if mod is None or not hasattr(mod, "expected_install_set"):
        return None
    config = permutation_to_install_config(permutation)
    try:
        result = mod.expected_install_set(config)
        return set(result) if result is not None else None
    except Exception:  # noqa: BLE001 — treat a manifest error as "unavailable", skip the metric
        return None
