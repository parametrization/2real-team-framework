"""Sync guard for the policy config knobs across the three default copies (#86).

``framework.config.schema.json`` ``default:`` values are the documented contract;
``_framework_config._DEFAULTS`` is its runtime shadow; ``bootstrap._schema_defaults()``
is what a fresh install writes. Issue #84 documents pre-existing drift in
``hooks.pre_bash`` between these copies — this suite pins the ``policy`` block (fully
synced today) so the lifecycle-skill knobs added by #86 (tech-debt intake/exit, retro
counter-drift tolerances) cannot drift the same way.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))
sys.path.insert(0, str(_FRAMEWORK_ROOT / "install"))

import _framework_config  # noqa: E402
import bootstrap  # noqa: E402

# The #86 knobs and their documented defaults.
NEW_POLICY_KEYS = {
    "tech_debt_intake_pct": 20,
    "tech_debt_exit_ratio_pct": 10,
    "retro_counter_drift_abs": 2,
    "retro_counter_drift_pct": 5,
}


def _schema_policy_defaults() -> dict:
    schema = json.loads(
        (_FRAMEWORK_ROOT / "config" / "framework.config.schema.json").read_text(encoding="utf-8")
    )
    props = schema["properties"]["policy"]["properties"]
    return {k: v["default"] for k, v in props.items() if "default" in v}


def _example_policy() -> dict:
    example = json.loads(
        (_FRAMEWORK_ROOT / "config" / "framework.config.example.json").read_text(encoding="utf-8")
    )
    return example["policy"]


def test_schema_and_runtime_defaults_agree_on_policy() -> None:
    """Every schema policy default == the runtime _DEFAULTS shadow, key for key."""
    assert _schema_policy_defaults() == _framework_config._DEFAULTS["policy"]


def test_bootstrap_written_policy_is_a_synced_subset_of_schema() -> None:
    """Whatever policy keys bootstrap writes must carry the schema-default values."""
    written = bootstrap._schema_defaults()["policy"]
    schema = _schema_policy_defaults()
    for key, value in written.items():
        assert key in schema, f"bootstrap writes policy.{key} absent from the schema"
        assert value == schema[key], f"policy.{key}: bootstrap={value!r} schema={schema[key]!r}"


def test_new_lifecycle_keys_present_in_all_three_copies() -> None:
    schema = _schema_policy_defaults()
    runtime = _framework_config._DEFAULTS["policy"]
    written = bootstrap._schema_defaults()["policy"]
    for key, default in NEW_POLICY_KEYS.items():
        assert schema.get(key) == default
        assert runtime.get(key) == default
        assert written.get(key) == default


def test_example_reviewers_required_matches_schema_default() -> None:
    """#208: the shipped (dormant) example must not silently carry a stricter bar.

    ``framework.config.example.json`` ships with ``pr_review_gate_enabled: false`` — the
    gate is off, so ``reviewers_required`` is inert today. But an adopter who copies the
    example and later flips the gate on inherits whatever ``reviewers_required`` value the
    example happened to carry. It must equal the schema/``_DEFAULTS`` default (1), not this
    repo's deliberately-armed runtime value (2, see ``.claude/framework.config.json``),
    else the adopter silently inherits a 2-reviewer bar they never chose.
    """
    schema_default = _schema_policy_defaults()["reviewers_required"]
    assert _example_policy()["reviewers_required"] == schema_default
    assert _example_policy()["pr_review_gate_enabled"] is False


def test_skills_read_the_keys_from_config_not_hardcoded() -> None:
    """The lifecycle skills reference the config keys via the dotted jq path."""
    skills = _FRAMEWORK_ROOT / "assets" / "skills"
    plan = (skills / "plan-phase" / "SKILL.md").read_text(encoding="utf-8")
    assert ".policy.tech_debt_intake_pct" in plan
    review = (skills / "phase-review" / "SKILL.md").read_text(encoding="utf-8")
    assert ".policy.tech_debt_exit_ratio_pct" in review
    retro = (skills / "wave-retro" / "SKILL.md").read_text(encoding="utf-8")
    assert ".policy.retro_counter_drift_abs" in retro
    assert ".policy.retro_counter_drift_pct" in retro
