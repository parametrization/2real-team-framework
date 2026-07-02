"""Three-way sync test for the hook-module default lists (issue #84).

The same defaults live in three places by design:

1. ``framework/config/framework.config.schema.json`` — the documented contract
   (``hooks.*`` ``default:`` values);
2. ``framework/assets/hooks/_framework_config.py`` ``_DEFAULTS`` — the runtime
   shadow the loader falls back to when a key is absent;
3. ``framework/install/bootstrap.py`` ``_schema_defaults()`` — what the
   bootstrapper WRITES into a target's ``framework.config.json``.

Drift between them is silent breakage: a module present in the schema but
missing from ``_schema_defaults()`` never runs in deployed repos, because the
written config carries the key and the runtime fallback only fills MISSING
keys. This module compares the three sources programmatically so the class of
drift found in #84 (``validate_labels`` / ``block_squash_wave_merge`` absent
from the bootstrap copy) cannot recur, for today's keys and any added later.
Stdlib + pytest only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))
sys.path.insert(0, str(_FRAMEWORK_ROOT / "install"))

import _framework_config  # noqa: E402
import bootstrap  # noqa: E402

_SCHEMA = _FRAMEWORK_ROOT / "config" / "framework.config.schema.json"


def _schema_hook_defaults() -> dict[str, list]:
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    props = schema["properties"]["hooks"]["properties"]
    return {key: spec["default"] for key, spec in props.items() if "default" in spec}


def _sources() -> dict[str, dict[str, list]]:
    return {
        "schema": _schema_hook_defaults(),
        "_framework_config._DEFAULTS": dict(_framework_config._DEFAULTS["hooks"]),
        "bootstrap._schema_defaults()": dict(bootstrap._schema_defaults()["hooks"]),
    }


def test_every_schema_hook_key_has_a_default() -> None:
    """Each hooks.* schema property carries an explicit default (the contract)."""
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    props = schema["properties"]["hooks"]["properties"]
    missing = [k for k, spec in props.items() if "default" not in spec]
    assert not missing, f"schema hooks keys without a default: {missing}"


def test_three_copies_agree_on_keys() -> None:
    """All three sources define exactly the same set of hooks keys."""
    sources = _sources()
    key_sets = {name: set(hooks) for name, hooks in sources.items()}
    reference = key_sets["schema"]
    for name, keys in key_sets.items():
        assert keys == reference, (
            f"{name} hooks keys {sorted(keys)} != schema keys {sorted(reference)}"
        )


@pytest.mark.parametrize("key", sorted(_schema_hook_defaults()))
def test_three_copies_agree_on_module_lists(key: str) -> None:
    """Per key: identical module lists (same modules, same ORDER) in all three."""
    sources = _sources()
    reference = sources["schema"][key]
    for name, hooks in sources.items():
        assert hooks.get(key) == reference, (
            f"hooks.{key} drift: {name} has {hooks.get(key)!r}, schema has {reference!r} "
            "— sync framework.config.schema.json, _framework_config._DEFAULTS and "
            "bootstrap._schema_defaults() (see issue #84)."
        )


def test_default_modules_exist_as_hook_files() -> None:
    """Every defaulted module name resolves to a shipped hooks/*.py asset."""
    hooks_dir = _FRAMEWORK_ROOT / "assets" / "hooks"
    for key, modules in _schema_hook_defaults().items():
        if key == "pre_push_commands":
            continue  # shell commands, not module names
        for module in modules:
            assert (hooks_dir / f"{module}.py").is_file(), (
                f"hooks.{key} default names module {module!r} but "
                f"assets/hooks/{module}.py does not exist"
            )
