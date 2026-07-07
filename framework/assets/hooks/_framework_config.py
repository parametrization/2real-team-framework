#!/usr/bin/env python3
"""Shared config loader for framework hooks/libs.

Every genericised artifact reads its opinionated values through this module
instead of hard-coding them. The config lives at ``<repo>/.claude/framework.config.json``
(written by the bootstrapper); this loader finds it by walking up from the
invocation cwd, parses it, and exposes a dotted-path getter merged over the
schema defaults.

Design contract
===============

- **Stdlib only.** No PyYAML / pydantic dependency — a hook must run in a
  freshly-pulled checkout with zero install step. Config is JSON for the same
  reason (``json`` is stdlib; YAML is not).
- **Fail-open to defaults.** A missing/unreadable/malformed config never raises
  and never blocks — :func:`config` returns the defaults so a hook degrades to
  generic-but-safe behaviour rather than crashing the tool call.
- **Defaults live here**, mirroring ``framework/config/framework.config.schema.json``
  ``default:`` values. Keep the two in sync (the schema is the documented
  contract; ``_DEFAULTS`` is its runtime shadow).

Usage
=====

    from _framework_config import config
    cfg = config(input_data)                       # input_data optional
    if cfg.get("scm.allow_force", False): ...
    owner = cfg.get("scm.owner")                   # None if unset
    pre = cfg.get("hooks.pre_bash", [])

``config()`` caches per resolved config-file path, so repeated calls within one
hook invocation are cheap.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "framework.config.json"

# Runtime shadow of the schema `default:` values. Dotted lookups fall back here
# when the loaded config omits a key. Keep in sync with
# framework/config/framework.config.schema.json.
_DEFAULTS: dict[str, Any] = {
    "version": 1,
    # model enum: single-repo | meta-and-children | child (child repos carry
    # project.parent + project.flavor; the DEFAULT stays single-repo).
    "project": {"model": "single-repo"},
    "scm": {"provider": "github", "default_branch": "main", "allow_force": False},
    "branch": {"feature": "{initials}/{issue}-{slug}", "integration": "deployments/wave-{wave}"},
    "labels": {"wave": "wave-{id}", "tech_debt": "tech-debt"},
    "board": {"enabled": False, "wave_field": "Wave"},
    "identity": {
        "enforce": False,
        "email_pattern": "team+{First}.{Last}@example.com",
        "roster_source": ".claude/team/roster.json",
        "allow_emails": [],
    },
    "policy": {
        "reviewers_required": 1,
        "merge_model": "direct-to-main",
        "admin_merge_exceptions": {},
        # Load-bearing-test pre-review gate (#167): map of <class> -> rationale
        # naming the bypass classes require_load_bearing_test.py accepts via
        # LOAD_BEARING_TEST_EXCEPTION=<class>:<rationale>. Pre-seeded with one
        # class, `refactor` (#176), so a pure-refactor PR (no new behavior, so
        # no test to pair) is not hard-blocked with zero configured bypass. A
        # repo may add more classes; removing this key entirely is NOT
        # sufficient to disable the seed (dict-valued config keys merge over
        # these runtime defaults rather than replacing them — see
        # _deep_merge) — a repo that wants zero classes must fork this default.
        "load_bearing_test_exceptions": {
            "refactor": (
                "Pure refactor / no external behavior change (renames, "
                "extraction, dead-code removal, formatting) - nothing new to "
                "test. State exactly what was restructured and confirm no "
                "observable behavior changed."
            ),
        },
        # Lifecycle-skill knobs (#86): per-wave tech-debt intake (/plan-phase),
        # phase-exit tech-debt gate (/phase-review), retro counter-drift
        # tolerances (/wave-retro).
        "tech_debt_intake_pct": 20,
        "tech_debt_exit_ratio_pct": 10,
        "retro_counter_drift_abs": 2,
        "retro_counter_drift_pct": 5,
        # Branch-freshness gate (#179): commits-behind (+ optional age) staleness
        # thresholds read by validate_branch_freshness.py. Both 0 == DISABLED
        # (opt-in, off by default); the gate does nothing until a knob is set > 0.
        "branch_freshness_max_commits_behind": 0,
        "branch_freshness_max_age_days": 0,
    },
    "ci": {
        "merge_requires_green": True,
        "empty_rollup_is_blocking": True,
        "neutral_pending_check_prefixes": [],
        "tooling": [],
    },
    "shell": "bash",
    "paths": {
        "team": ".claude/team",
        "memory": ".claude/memory",
        "ontology": "ontology",
        "state_file": ".claude/state.json",
        "events_log": ".claude/framework/events.jsonl",
        "generic_prompt_ledger": ".claude/generic_prompt_ledger.json",
        "promotion_audit_log": ".claude/team/promotion_audit_log",
    },
    "hooks": {
        "pre_bash": [
            "block_no_verify",
            "block_git_config",
            "no_worktree_self_delete",
            "warn_zsh_wordsplit",
            "validate_labels",
            "validate_review_comment_format",
            "block_gh_pr_review",
            "validate_workflow_paths_coverage",
            "require_load_bearing_test",
            "validate_branch_freshness",
            "validate_pr_ci_status",
            "block_squash_wave_merge",
        ],
        "post_bash": ["warn_pipe_mask_rc"],
        "post_file": ["ontology_tracker", "suggest_generic_prompt"],
        "session_start": ["ontology_refresh", "session_start"],
        "agent": [],
        "stop": ["session_handoff"],
        "pre_push_commands": [],
    },
}

# Cache: resolved-config-path -> merged dict. Keyed by path so different repos in
# one process (rare) don't collide; the None key caches "not found → defaults".
_CACHE: dict[str | None, dict[str, Any]] = {}


def _find_config_file(start: Path) -> Path | None:
    """Walk up from ``start`` looking for ``.claude/framework.config.json``."""
    cur = start.resolve()
    for d in (cur, *cur.parents):
        candidate = d / ".claude" / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """Return ``base`` deep-merged with ``over`` (over wins; dicts merge recursively)."""
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _resolve_start_dir(input_data: dict | None) -> Path:
    """Best-effort cwd for the tool call (mirrors _shell_parse.resolve_tool_cwd)."""
    if input_data:
        cwd = input_data.get("cwd")
        if isinstance(cwd, str) and cwd:
            return Path(cwd)
    return Path(os.getcwd())


class _Config:
    """Thin wrapper exposing :meth:`get` with dotted-path access over a merged dict."""

    __slots__ = ("_data", "path")

    def __init__(self, data: dict[str, Any], path: Path | None) -> None:
        self._data = data
        self.path = path

    def get(self, dotted: str, default: Any = None) -> Any:
        """Return the value at ``dotted`` (e.g. ``"ci.tooling"``), or ``default``.

        ``default`` is returned only when the key is absent from BOTH the loaded
        config and ``_DEFAULTS`` — so callers can omit ``default`` for keys that
        always have a schema default, and pass one for genuinely-optional keys.
        """
        node: Any = self._data
        for part in dotted.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)


def config(input_data: dict | None = None, *, start_dir: str | Path | None = None) -> _Config:
    """Load the framework config merged over defaults. Never raises.

    Resolution order for the config file: explicit ``start_dir`` → ``input_data["cwd"]``
    → ``os.getcwd()``, walking up to the filesystem root. If no config file is
    found (or it is unreadable/invalid JSON), the pure defaults are returned.
    """
    start = Path(start_dir) if start_dir else _resolve_start_dir(input_data)
    path = _find_config_file(start)
    key = str(path) if path else None
    if key in _CACHE:
        return _Config(_CACHE[key], path)

    merged = dict(_DEFAULTS)
    if path is not None:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                merged = _deep_merge(_DEFAULTS, loaded)
        except (OSError, json.JSONDecodeError, ValueError):
            merged = dict(_DEFAULTS)  # fail-open

    _CACHE[key] = merged
    return _Config(merged, path)


def clear_cache() -> None:
    """Drop the memoized config (tests that write a config mid-run call this)."""
    _CACHE.clear()
