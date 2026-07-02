"""Unified install-time configuration: load / merge / validate.

The single ``install.config.yaml`` schema covers every interactive decision
point of both installers (``framework/install/bootstrap.py`` and the
``2real-team`` CLI). This module owns the stdlib-only loading pipeline:

    built-in fallback  <  shipped defaults (framework/config/install.config.default.yaml)
                       <  user YAML (--install-config)
                       <  CLI flags (applied by the caller via :func:`set_key`)

Schema (v1) — every key, with the shipped default:

    version: 1
    repo.expect:         fresh | existing | any          (fresh)
    project.name:        str | null                      (null -> target dir name)
    project.model:       standalone | meta | child       (standalone)
    project.flavor:      product | infra                 (product; child model only)
    scm.provider:        github                          (github)
    scm.owner:           str | null                      (null)
    ci.provider:         github-actions                  (github-actions)
    ticketing.provider:  github-issues                   (github-issues)
    pre_push.mode:       noop | enforce | none           (noop)
    ontology.enabled:    bool                            (true)
    team.enabled:        bool                            (true)
    team.preset:         str | null                      (null)
    team.size:           int | null                      (null)
    parent.path:         str | null                      (null; REQUIRED for model: child)
    children:            list of {path: str, flavor: product|infra}   ([])

``repo.expect`` (fresh-vs-existing gate), ``project.model: meta`` (per-child
installs from ``children``), and ``project.model: child`` (a standalone child
install pointing at ``parent.path``) are enforced by the bootstrapper, and
``pre_push.mode`` drives its pre-push hook installer. The resolved config is
written to ``.claude/install.config.json`` so downstream consumers read one
canonical record of the install-time decisions.

Stdlib only (uses the sibling ``miniyaml`` parser).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import miniyaml  # noqa: E402  (sibling module in install/)

# framework/install/install_config.py -> framework/
_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
DEFAULTS_PATH = _FRAMEWORK_ROOT / "config" / "install.config.default.yaml"

#: Where the resolved install config is recorded inside the target repo.
SNAPSHOT_REL = "install.config.json"

CHILD_FLAVORS = ("product", "infra")

ENUMS: dict[str, tuple[str, ...]] = {
    "repo.expect": ("fresh", "existing", "any"),
    "project.model": ("standalone", "meta", "child"),
    "project.flavor": CHILD_FLAVORS,
    "scm.provider": ("github",),
    "ci.provider": ("github-actions",),
    "ticketing.provider": ("github-issues",),
    "pre_push.mode": ("noop", "enforce", "none"),
}

#: install-config project.model -> runtime framework.config.json project.model.
#: ``child`` is FIRST-CLASS in the runtime schema (not folded into single-repo),
#: so a child repo's runtime config is recoverable as what it is.
RUNTIME_MODEL_MAP = {"standalone": "single-repo", "meta": "meta-and-children", "child": "child"}
#: runtime project.model -> install-config project.model (for flag reverse-mapping)
INSTALL_MODEL_MAP = {"single-repo": "standalone", "meta-and-children": "meta", "child": "child"}


class InstallConfigError(ValueError):
    """A fatal problem loading/validating the install config."""


def builtin_defaults() -> dict:
    """In-code mirror of the shipped default file (safety net if it is missing)."""
    return {
        "version": 1,
        "repo": {"expect": "fresh"},
        "project": {"name": None, "model": "standalone", "flavor": "product"},
        "scm": {"provider": "github", "owner": None},
        "ci": {"provider": "github-actions"},
        "ticketing": {"provider": "github-issues"},
        "pre_push": {"mode": "noop"},
        "ontology": {"enabled": True},
        "team": {"enabled": True, "preset": None, "size": None},
        "parent": {"path": None},
        "children": [],
    }


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def dotted_keys(node: Any, prefix: str = "") -> set[str]:
    """All leaf key-paths of a nested dict (lists count as leaves)."""
    if not isinstance(node, dict):
        return {prefix} if prefix else set()
    keys: set[str] = set()
    for k, v in node.items():
        path = f"{prefix}.{k}" if prefix else str(k)
        keys |= dotted_keys(v, path)
    return keys


def get_key(cfg: dict, dotted: str, default: Any = None) -> Any:
    node: Any = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def set_key(cfg: dict, dotted: str, value: Any) -> None:
    node = cfg
    parts = dotted.split(".")
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value


def load(user_path: str | Path | None = None) -> tuple[dict, set[str]]:
    """Resolve the install config: builtin < shipped defaults < user YAML.

    Returns ``(config, user_keys)`` where ``user_keys`` is the set of dotted
    key-paths the USER explicitly provided (used for precedence decisions and
    for prompt-skipping). Raises :class:`InstallConfigError` on unreadable or
    structurally invalid input.
    """
    cfg = builtin_defaults()
    if DEFAULTS_PATH.is_file():
        try:
            shipped = miniyaml.load(DEFAULTS_PATH)
        except (OSError, miniyaml.MiniYamlError) as e:
            raise InstallConfigError(f"shipped default install config is unreadable: {e}")
        if isinstance(shipped, dict):
            cfg = deep_merge(cfg, shipped)

    user_keys: set[str] = set()
    if user_path is not None:
        p = Path(user_path)
        try:
            data = miniyaml.load(p)
        except OSError as e:
            raise InstallConfigError(f"install config could not be read: {e}")
        except miniyaml.MiniYamlError as e:
            raise InstallConfigError(f"install config is not valid YAML ({p}): {e}")
        if not isinstance(data, dict):
            raise InstallConfigError(f"install config must be a YAML mapping ({p})")
        cfg = deep_merge(cfg, data)
        user_keys = dotted_keys(data)
    return cfg, user_keys


def validate(cfg: dict) -> tuple[list[str], list[str]]:
    """Validate the resolved config. Returns ``(problems, warnings)``.

    Problems are fatal (bad enum values / types); warnings are advisory
    (unknown keys — kept for forward compatibility, they are carried as-is).
    """
    problems: list[str] = []
    warnings: list[str] = []

    if cfg.get("version") != 1:
        problems.append("version: must be 1")

    for dotted, allowed in ENUMS.items():
        value = get_key(cfg, dotted)
        if value is not None and value not in allowed:
            problems.append(f"{dotted}: {value!r} is not one of {list(allowed)}")

    for dotted in ("ontology.enabled", "team.enabled"):
        value = get_key(cfg, dotted)
        if not isinstance(value, bool):
            problems.append(f"{dotted}: must be true or false (got {value!r})")

    size = get_key(cfg, "team.size")
    if size is not None and (not isinstance(size, int) or isinstance(size, bool) or size < 1):
        problems.append(f"team.size: must be a positive integer or null (got {size!r})")

    for dotted in ("project.name", "scm.owner", "team.preset", "parent.path"):
        value = get_key(cfg, dotted)
        if value is not None and not isinstance(value, str):
            problems.append(f"{dotted}: must be a string or null (got {value!r})")

    model = get_key(cfg, "project.model")
    parent_path = get_key(cfg, "parent.path")
    if model == "child" and not (isinstance(parent_path, str) and parent_path.strip()):
        problems.append(
            "parent.path: required for project.model: child "
            "(the relative path from this repo to its parent meta-repo, e.g. `..`)"
        )
    if isinstance(parent_path, str) and parent_path.startswith(("/", "~")):
        problems.append(
            f"parent.path: must be RELATIVE (portable — no machine-specific "
            f"absolute paths): got {parent_path!r}"
        )
    if parent_path and model != "child":
        warnings.append(
            f"parent.path: set but project.model is {model!r} — only the child model uses it"
        )

    children = cfg.get("children")
    if children is None:
        cfg["children"] = []
    elif not isinstance(children, list):
        problems.append(f"children: must be a list (got {type(children).__name__})")
    else:
        for idx, child in enumerate(children):
            loc = f"children[{idx}]"
            if not isinstance(child, dict):
                problems.append(f"{loc}: must be a mapping with a `path` key")
                continue
            path = child.get("path")
            if not isinstance(path, str) or not path.strip():
                problems.append(f"{loc}.path: required non-empty string")
            elif path.startswith(("/", "~")) or ".." in path.replace("\\", "/").split("/"):
                problems.append(
                    f"{loc}.path: must be a relative path INSIDE the meta repo "
                    f"(portable, no absolutes / `..`): got {path!r}"
                )
            flavor = child.setdefault("flavor", "product")
            if flavor not in CHILD_FLAVORS:
                problems.append(f"{loc}.flavor: {flavor!r} is not one of {list(CHILD_FLAVORS)}")
            for extra in sorted(set(child) - {"path", "flavor"}):
                warnings.append(f"{loc}: unknown key {extra!r} (carried as-is)")
        if children and get_key(cfg, "project.model") != "meta":
            warnings.append(
                "children: listed but project.model is not `meta` — per-child installs "
                "run only under the meta model (the list is recorded as-is)"
            )

    known_top = set(builtin_defaults())
    for extra in sorted(set(cfg) - known_top):
        warnings.append(f"unknown top-level key {extra!r} (carried as-is)")

    return problems, warnings


def runtime_overlay(cfg: dict, user_keys: set[str]) -> dict:
    """The slice of the install config that flows into framework.config.json.

    Only keys the user explicitly decided (or that carry a real value) are
    overlaid, so an untouched install default never clobbers a ``--config``
    JSON runtime seed.
    """
    overlay: dict = {}
    owner = get_key(cfg, "scm.owner")
    if owner:
        overlay.setdefault("scm", {})["owner"] = owner
    name = get_key(cfg, "project.name")
    if name:
        overlay.setdefault("project", {})["name"] = name
    if "project.model" in user_keys:
        model = get_key(cfg, "project.model")
        if model in RUNTIME_MODEL_MAP:
            overlay.setdefault("project", {})["model"] = RUNTIME_MODEL_MAP[model]
    return overlay


HELP_EPILOG = """\
install config keys (--install-config YAML; precedence: flags > user YAML > shipped defaults):
  version              config schema version (must be 1)
  repo.expect          fresh | existing | any        target-repo expectation (default: fresh)
                       enforced: non-interactive installs REFUSE on a mismatch (`any` always
                       proceeds); interactive installs confirm before touching an existing repo
  project.name         str | null                    display name (default: target dir name)
  project.model        standalone | meta | child     project shape (default: standalone)
  project.flavor       product | infra               THIS repo's flavor (child model; default: product)
  scm.provider         github                        SCM host (default: github)
  scm.owner            str | null                    GitHub org/user (replaces the owner prompt)
  ci.provider          github-actions                CI system (default: github-actions)
  ticketing.provider   github-issues                 tracker (default: github-issues)
  pre_push.mode        noop | enforce | none         pre-push hook mode (default: noop)
  ontology.enabled     bool                          lay the ontology seed (default: true)
  team.enabled         bool                          generate the team layer (default: true)
  team.preset          str | null                    team preset (used by `2real-team init`)
  team.size            int | null                    target headcount (replaces the roster prompt)
  parent.path          str | null                    child model: relative path to the parent
                       meta-repo (REQUIRED for project.model: child, e.g. `..`)
  children             [{path, flavor: product|infra}]  meta model: child repos to install
                       (non-interactive uses this list VERBATIM — no detection surprises;
                       interactive multi-selects from detected subdir git repos)

Shipped defaults: framework/config/install.config.default.yaml. The resolved
config is recorded at <target>/.claude/install.config.json. With
--non-interactive the install is fully prompt-free on every path.
"""
