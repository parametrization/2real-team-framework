#!/usr/bin/env python3
"""Deterministic bootstrapper: install the 2real framework hooks into a repo.

Lays down the genericised hook/lib assets, writes a ``framework.config.json``,
and wires the dispatchers into the target repo's ``.claude/settings.json`` — for
either a NEW or an EXISTING repo. Determinism is the priority: the whole install
is driven by flags + an optional config file and is fully idempotent, so re-running
changes nothing. Interactive prompts are an opt-in convenience, never required.

Stdlib only (no deps), so it runs anywhere ``python3`` does.

Install-time decisions are driven by the unified YAML install config
(``--install-config``; shipped defaults at ``config/install.config.default.yaml``)
with precedence CLI flags > user YAML > shipped defaults. ``--non-interactive``
guarantees zero prompts on every path. The resolved install config is recorded
at ``<target>/.claude/install.config.json``; the RUNTIME config the hooks read
remains ``<target>/.claude/framework.config.json``.

Project models: ``standalone`` (default) installs everything here; ``meta``
additionally lays a hook-less child layout (parent-relative settings, child
config/roster/CLAUDE.md) into each selected child repo; ``child`` installs ONLY
that child layout, pointing at an already-bootstrapped parent (``parent.path``).
A fresh-vs-existing gate reports the target's state and enforces ``repo.expect``
(non-interactive mismatches refuse; interactive installs confirm before touching
an existing repo; idempotent re-runs skip the gate).

Usage
=====

  # Deterministic (no prompts) — minimal:
  python3 bootstrap.py /path/to/repo --owner my-org

  # Fully declarative, zero prompts (recommended for automation):
  python3 bootstrap.py /path/to/repo --install-config my.install.yaml --non-interactive

  # From a prepared RUNTIME config seed (JSON, framework.config.json shape):
  python3 bootstrap.py /path/to/repo --config my.framework.config.json

  # Preview without writing anything:
  python3 bootstrap.py /path/to/repo --owner my-org --dry-run

  # Interactive fill of any still-missing required fields (TTY only):
  python3 bootstrap.py /path/to/repo --interactive

Flags
=====
  target                 Target repo root (default: current directory).
  --install-config PATH  Unified YAML install config (see --help for the keys).
  --non-interactive      Never prompt; the install config answers everything.
  --config PATH          JSON RUNTIME-config seed (framework.config.json shape).
  --owner NAME           scm.owner (GitHub org/user). Overlays the configs.
  --project-name NAME    project.name.
  --model {single-repo,meta-and-children,child}
  --expect {fresh,existing,any}  repo.expect override (fresh-vs-existing gate).
  --shell {bash,zsh}
  --reviewers N          policy.reviewers_required.
  --merge-model {wave-branch,direct-to-main}
  --no-permissions       Skip installing the curated permissions.allow allowlist.
  --pre-push {noop,enforce,none}
                         Pre-push git hook to install; overrides the
                         install-config key ``pre_push.mode`` (flag > user
                         YAML > shipped default noop). noop = an executable,
                         clearly-commented script that exits 0; enforce runs
                         hooks.pre_push_commands from framework.config.json
                         and blocks push on failure; none installs nothing.
  --interactive          Prompt for missing required fields (scm.owner) if a TTY.
  --with-ontology / --no-ontology   Override ontology.enabled from the config.
  --force                Overwrite existing hook/lib files and framework.config.json.
  --refresh-charter      Re-render the charter with the current config, overwriting
                         only modules you have NOT hand-edited (three-way; hand-
                         evolved modules preserved). Use this — not --force — to
                         refresh a config change into an evolved charter.
  --dry-run              Print the plan; write nothing.

Exit codes: 0 ok / dry-run, 1 on a hard error (e.g. assets missing, invalid config).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import child_install  # noqa: E402  (sibling module in install/)
import install_config  # noqa: E402  (sibling module in install/)
import repo_space  # noqa: E402  (sibling module in install/)
import roster_gen  # noqa: E402  (sibling module in install/)

# framework/install/bootstrap.py  ->  framework/
_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_ASSETS = _FRAMEWORK_ROOT / "assets"
_DEFAULTS_PATH = _FRAMEWORK_ROOT / "config" / "framework.config.example.json"


# ---------------------------------------------------------------- config build


def _schema_defaults() -> dict:
    """Minimal in-code defaults so a bare `--owner X` install is valid.

    Mirrors the schema's required+top-level defaults; the loader fills the rest
    at runtime, so the written file only needs to be valid + carry the operator's
    real choices.

    The ``hooks`` lists here MUST match the schema ``default:`` values and the
    runtime ``_framework_config._DEFAULTS`` exactly — the bootstrapper WRITES
    this dict into the target's ``framework.config.json``, so a module missing
    here simply never runs in deployed repos (issue #84). The three copies are
    kept honest by ``framework/tests/test_defaults_sync.py``.
    """
    return {
        "version": 1,
        "scm": {"provider": "github", "default_branch": "main", "allow_force": False},
        "shell": "bash",
        # Lifecycle-skill policy knobs (#86) — written so a deployed repo can see
        # and tune them. Values MUST match framework.config.schema.json defaults
        # and _framework_config._DEFAULTS (test_config_schema_sync.py pins this).
        "policy": {
            "tech_debt_intake_pct": 20,
            "tech_debt_exit_ratio_pct": 10,
            "retro_counter_drift_abs": 2,
            "retro_counter_drift_pct": 5,
            "branch_freshness_max_commits_behind": 0,
            "branch_freshness_max_age_days": 0,
        },
        "hooks": {
            "pre_bash": [
                "block_no_verify",
                "block_git_config",
                "no_worktree_self_delete",
                "warn_zsh_wordsplit",
                "validate_labels",
                "validate_review_comment_format",
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


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _set_path(cfg: dict, dotted: str, value) -> None:
    node = cfg
    parts = dotted.split(".")
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value


def resolve_install_config(args: argparse.Namespace) -> tuple[dict, set[str]]:
    """Resolve the unified install config: flags > user YAML > shipped defaults.

    Returns ``(install_cfg, user_keys)``; ``user_keys`` are the dotted paths the
    operator explicitly decided (via YAML or flag) — used for precedence into the
    runtime config and for prompt-skipping. Raises SystemExit on invalid input.
    """
    try:
        inst, user_keys = install_config.load(args.install_config)
    except install_config.InstallConfigError as e:
        raise SystemExit(f"ERROR: {e}")

    # CLI flags are the highest-precedence layer of the install config.
    flag_map = {
        "scm.owner": args.owner,
        "project.name": args.project_name,
        "team.size": args.team_size,
        "repo.expect": args.expect,
    }
    if args.model:  # runtime enum -> install enum
        flag_map["project.model"] = install_config.INSTALL_MODEL_MAP[args.model]
    if args.no_team:
        flag_map["team.enabled"] = False
    if args.no_ontology:
        flag_map["ontology.enabled"] = False
    elif args.with_ontology:
        flag_map["ontology.enabled"] = True
    if args.pre_push:  # default=None -> only an EXPLICIT flag beats the YAML
        flag_map["pre_push.mode"] = args.pre_push
    for dotted, value in flag_map.items():
        if value is not None:
            install_config.set_key(inst, dotted, value)
            user_keys.add(dotted)

    problems, warnings = install_config.validate(inst)
    for w in warnings:
        print(f"install-config warn: {w}")
    if problems:
        for p in problems:
            print(f"install-config problem: {p}", file=sys.stderr)
        raise SystemExit("ERROR: refusing to install with an invalid install config.")
    return inst, user_keys


def build_config(args: argparse.Namespace, inst: dict, user_keys: set[str]) -> dict:
    """Build the RUNTIME config (framework.config.json shape).

    Layering: schema defaults < ``--config`` JSON seed < install-config overlay
    (which already has the CLI flags folded in, so flags beat both files).
    """
    cfg = _schema_defaults()
    if args.config:
        try:
            loaded = json.loads(Path(args.config).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise SystemExit(f"ERROR: --config could not be read: {e}")
        if not isinstance(loaded, dict):
            raise SystemExit("ERROR: --config must be a JSON object")
        cfg = _deep_merge(cfg, loaded)

    cfg = _deep_merge(cfg, install_config.runtime_overlay(inst, user_keys))

    # Runtime-only flags (no install-config equivalent) overlay everything.
    if args.shell:
        _set_path(cfg, "shell", args.shell)
    if args.reviewers is not None:
        _set_path(cfg, "policy.reviewers_required", args.reviewers)
    if args.merge_model:
        _set_path(cfg, "policy.merge_model", args.merge_model)

    # Interactive fill of still-missing required-ish fields (TTY only; the
    # config is always consulted first, --non-interactive never reaches here).
    if args.interactive and sys.stdin.isatty():
        if not cfg.get("scm", {}).get("owner"):
            ans = input("GitHub owner (org or user) [leave blank to skip]: ").strip()
            if ans:
                _set_path(cfg, "scm.owner", ans)
                install_config.set_key(inst, "scm.owner", ans)

    return cfg


def validate_config(cfg: dict) -> list[str]:
    """Best-effort validation. Uses jsonschema if available, else a structural check.

    Returns a list of human-readable problems (empty = ok). Never raises.
    """
    problems: list[str] = []
    if cfg.get("version") != 1:
        problems.append("version must be 1")
    schema_path = _FRAMEWORK_ROOT / "config" / "framework.config.schema.json"
    try:
        import jsonschema  # type: ignore

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        for err in sorted(validator.iter_errors(cfg), key=lambda e: e.path):
            loc = ".".join(str(p) for p in err.path) or "(root)"
            problems.append(f"{loc}: {err.message}")
    except ImportError:
        # Deterministic fallback: structural sanity only (jsonschema is optional).
        if not isinstance(cfg.get("scm", {}), dict):
            problems.append("scm must be an object")
    return problems


# ---------------------------------------------------------------- install steps


def _iter_asset_files(subdir: str):
    base = _ASSETS / subdir
    if not base.is_dir():
        return
    for p in sorted(base.glob("*.py")):
        if p.name == "__init__.py" or p.name.endswith("_test.py"):
            continue
        yield p


def _iter_lib_files():
    """Yield (relative-path, source) for every .py under assets/lib/, recursively.

    Unlike :func:`_iter_asset_files`, this preserves subpackage structure (e.g.
    ``ontology_gen/aggregate.py``) and KEEPS ``__init__.py`` so installed subpackages
    remain importable. Skips ``__pycache__`` and ``*_test.py``.
    """
    base = _ASSETS / "lib"
    if not base.is_dir():
        return
    for p in sorted(base.rglob("*.py")):
        if "__pycache__" in p.parts or p.name.endswith("_test.py"):
            continue
        yield p.relative_to(base), p


def _iter_skill_files():
    """Yield (relative-path, source) for every file under assets/skills/."""
    base = _ASSETS / "skills"
    if not base.is_dir():
        return
    for p in sorted(base.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            yield p.relative_to(base), p


def install_assets(target_claude: Path, *, force: bool, dry_run: bool) -> dict[str, list[str]]:
    """Copy hooks/ + lib/ (+ skills/) assets into <target>/.claude/. Idempotent."""
    report: dict[str, list[str]] = {"copied": [], "skipped": [], "would_copy": []}

    def _emit(dest: Path, rel: str, src: Path) -> None:
        if dest.exists() and not force:
            report["skipped"].append(rel)
            return
        if dry_run:
            report["would_copy"].append(rel)
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        report["copied"].append(rel)

    # hooks/ is a flat tree of modules.
    for src in _iter_asset_files("hooks"):
        _emit(target_claude / "hooks" / src.name, f"hooks/{src.name}", src)

    # lib/ may contain subpackages (e.g. ontology_gen/) → copy recursively, preserving paths.
    for relpath, src in _iter_lib_files():
        _emit(target_claude / "lib" / relpath, f"lib/{relpath}", src)

    # Skills are a nested markdown tree (skills/<name>/SKILL.md) → .claude/skills/.
    for relpath, src in _iter_skill_files():
        _emit(target_claude / "skills" / relpath, f"skills/{relpath}", src)

    return report


def write_config(target_claude: Path, cfg: dict, *, force: bool, dry_run: bool) -> str:
    dest = target_claude / "framework.config.json"
    if dest.exists() and not force:
        return "skipped (exists; use --force to overwrite)"
    if dry_run:
        return "would write"
    target_claude.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    return "written"


def write_install_snapshot(target_claude: Path, inst: dict, *, force: bool, dry_run: bool) -> str:
    """Record the RESOLVED install config at .claude/install.config.json.

    This is the carry-point for install-time decisions whose behaviour lands in
    later tranches (repo.expect, meta/child models, children, pre_push): one
    canonical, machine-readable record every downstream consumer reads.
    """
    dest = target_claude / install_config.SNAPSHOT_REL
    if dest.exists() and not force:
        return "skipped (exists; use --force to overwrite)"
    if dry_run:
        return "would write"
    target_claude.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(inst, indent=2) + "\n", encoding="utf-8")
    return "written"


def _script_id(command: str) -> str:
    """Stable identity for a hook command = its ``.py`` script basename (else the command).

    Lets the merge recognise an already-wired hook regardless of the ``$CLAUDE_PROJECT_DIR``
    prefix or quoting, so re-running bootstrap is idempotent for every event (Pre/Post/Session).
    """
    for token in command.replace('"', " ").split():
        if token.endswith(".py"):
            return Path(token).name
    return command.strip()


def _merge_permissions(template: dict, existing: dict) -> bool:
    """Union the template's ``permissions`` rule lists into ``existing``. Returns True if changed.

    Rule identity is the exact rule string, so user-added rules are preserved untouched and
    template rules already present (in any position) are never duplicated — re-running is a
    no-op. Generic over rule lists (``allow`` today; ``deny``/``ask`` would merge the same way).
    """
    tmpl_perms = template.get("permissions")
    if not isinstance(tmpl_perms, dict):
        return False
    changed = False
    perms = existing.setdefault("permissions", {})
    for key, rules in tmpl_perms.items():
        if not isinstance(rules, list):
            continue
        current = perms.setdefault(key, [])
        if not isinstance(current, list):
            continue  # user made it something else — leave their shape alone
        for rule in rules:
            if rule not in current:
                current.append(rule)
                changed = True
    return changed


def merge_settings(
    target_claude: Path,
    *,
    dry_run: bool,
    install_permissions: bool = True,
    template: dict | None = None,
) -> str:
    """Idempotently merge the template hook wiring into <target>/.claude/settings.json.

    Generic over events (PreToolUse / PostToolUse / SessionStart / …): blocks match by
    ``matcher`` (which may be absent — e.g. SessionStart), and each template hook is added only
    if no existing hook in that block already references the same script. Re-running is a no-op.

    Also merges the template's curated ``permissions.allow`` allowlist (union, no duplicates,
    user-added rules preserved) unless ``install_permissions`` is False, in which case the
    template's permissions block is not installed and any existing one is left untouched.

    ``template`` overrides the shipped ``settings.template.json`` — used by the child-repo
    install, whose template is the shipped one rewritten to parent-relative commands (and
    flavor-filtered). The merge/idempotency semantics are identical.
    """
    if template is None:
        template = json.loads((_ASSETS / "settings.template.json").read_text(encoding="utf-8"))
    dest = target_claude / "settings.json"
    existing: dict = {}
    if dest.exists():
        try:
            existing = json.loads(dest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "ERROR: existing settings.json is not valid JSON — left untouched"

    existing.setdefault("hooks", {})
    changed = False
    for event, blocks in template["hooks"].items():
        existing["hooks"].setdefault(event, [])
        for tmpl_block in blocks:
            matcher = tmpl_block.get("matcher")  # absent for matcher-less events (SessionStart)
            same = [b for b in existing["hooks"][event] if b.get("matcher") == matcher]
            if not same:
                existing["hooks"][event].append(json.loads(json.dumps(tmpl_block)))
                changed = True
                continue
            block = same[0]
            block.setdefault("hooks", [])
            wired = {_script_id(h.get("command", "")) for h in block["hooks"]}
            for tmpl_hook in tmpl_block.get("hooks", []):
                if _script_id(tmpl_hook.get("command", "")) not in wired:
                    block["hooks"].append(json.loads(json.dumps(tmpl_hook)))
                    wired.add(_script_id(tmpl_hook.get("command", "")))
                    changed = True

    if install_permissions and _merge_permissions(template, existing):
        changed = True

    if not changed:
        return "already wired"
    if dry_run:
        return "would update"
    target_claude.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    return "updated"


def _charter_context(cfg: dict) -> dict[str, str]:
    """Build the ``{{key}}`` substitution map for the modular charter template.

    Supported keys (all derived from the built config; stdlib-only, no template
    engine — plain ``{{key}}`` string substitution):

    ==========================  =============================  ===========================
    Placeholder                 Config source                  Default
    ==========================  =============================  ===========================
    {{project_name}}            project.name                   "this project"
    {{owner}}                   scm.owner                      "<owner>"
    {{default_branch}}          scm.default_branch             "main"
    {{feature_branch_scheme}}   branch.feature                 "{initials}/{issue}-{slug}"
    {{integration_branch_scheme}}  branch.integration          "deployments/wave-{wave}"
    {{merge_model}}             policy.merge_model             "wave-branch"
    {{reviewers_required}}      policy.reviewers_required      2
    {{email_pattern}}           identity.email_pattern         "team+{First}.{Last}@example.com"
    {{tech_debt_label}}         labels.tech_debt               "tech-debt"
    {{team_dir}}                paths.team                     ".claude/team"
    ==========================  =============================  ===========================

    Note: single-brace tokens (e.g. ``{initials}``) are part of the *content*
    (branch-scheme notation), not placeholders — only double-brace keys substitute.
    """

    def _get(dotted: str, default):
        node = cfg
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node if node not in (None, "") else default

    return {
        "project_name": str(_get("project.name", "this project")),
        "owner": str(_get("scm.owner", "<owner>")),
        "default_branch": str(_get("scm.default_branch", "main")),
        "feature_branch_scheme": str(_get("branch.feature", "{initials}/{issue}-{slug}")),
        "integration_branch_scheme": str(_get("branch.integration", "deployments/wave-{wave}")),
        "merge_model": str(_get("policy.merge_model", "wave-branch")),
        "reviewers_required": str(_get("policy.reviewers_required", 2)),
        "email_pattern": str(_get("identity.email_pattern", "team+{First}.{Last}@example.com")),
        "tech_debt_label": str(_get("labels.tech_debt", "tech-debt")),
        "team_dir": str(_get("paths.team", ".claude/team")),
    }


def _iter_charter_files():
    """Yield every .md file under assets/team/charter/ (the modular charter template)."""
    base = _ASSETS / "team" / "charter"
    if not base.is_dir():
        return
    yield from sorted(base.glob("*.md"))


def _sha256(text: str) -> str:
    """Stable content hash of rendered charter text (used by the refresh manifest)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _charter_manifest_path(target_claude: Path) -> Path:
    """Location of the charter render manifest (dotfile beside the charter dir).

    Kept OUTSIDE ``team/charter/`` so it never appears in the ``*.md`` charter glob
    and never becomes a spurious charter module.
    """
    return target_claude / "team" / ".charter-manifest.json"


def _load_charter_manifest(target_claude: Path) -> dict[str, str]:
    """Read the per-file checksums of the last-rendered charter. Fail-open to ``{}``.

    Maps ``charter-module-name -> sha256`` of the text this installer last wrote. A
    missing/corrupt manifest (e.g. installs predating this feature) degrades to an
    empty baseline, which makes every existing file look hand-evolved and therefore
    *preserved* on refresh — the safe default.
    """
    path = _charter_manifest_path(target_claude)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        files = data.get("files")
        return files if isinstance(files, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_charter_manifest(target_claude: Path, files: dict[str, str]) -> None:
    path = _charter_manifest_path(target_claude)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "files": files}, indent=2) + "\n", encoding="utf-8"
    )


def install_charter(
    target_claude: Path, cfg: dict, *, force: bool, refresh: bool = False, dry_run: bool
) -> dict[str, list[str]]:
    """Render the modular charter into <target>/.claude/team/charter/. Idempotent.

    Substitutes the ``{{key}}`` placeholders documented in :func:`_charter_context`
    with config-derived values. Three write modes:

    * **default** (skip-if-exists): a consumer's hand-evolved charter is never
      touched once it exists; only missing modules are written.
    * ``refresh=True`` (three-way): re-render every module from the template with
      the *current* config and overwrite **only** modules the consumer has NOT
      hand-edited (on-disk text still matches the last-rendered checksum in the
      manifest). Hand-evolved modules are *preserved* and reported, so a config
      change can be propagated without clobbering local edits (issue #77).
    * ``force=True`` (blanket): overwrite every module unconditionally.

    Every write/refresh records the rendered checksum in ``team/.charter-manifest.json``
    so a later refresh can tell "unmodified since we rendered it" from "hand-evolved".
    """
    report: dict[str, list[str]] = {
        "written": [], "refreshed": [], "preserved": [], "skipped": [], "would_write": []
    }
    context = _charter_context(cfg)
    manifest = _load_charter_manifest(target_claude)
    manifest_dirty = False

    for src in _iter_charter_files():
        dest = target_claude / "team" / "charter" / src.name
        rel = f"team/charter/{src.name}"
        text = src.read_text(encoding="utf-8")
        for key, value in context.items():
            text = text.replace("{{" + key + "}}", value)

        exists = dest.exists()
        current = dest.read_text(encoding="utf-8") if exists else None

        if exists and not force:
            if refresh:
                if current == text:
                    # Already current — nothing to write, but keep the baseline fresh.
                    report["skipped"].append(rel)
                    manifest[src.name] = _sha256(text)
                    manifest_dirty = True
                    continue
                baseline = manifest.get(src.name)
                if baseline is None or _sha256(current or "") != baseline:
                    # No baseline, or on-disk text diverged from what we last rendered
                    # => hand-evolved. Preserve it; leave its baseline untouched.
                    report["preserved"].append(rel)
                    continue
                # Unmodified since our last render => safe to propagate config change.
                if dry_run:
                    report["would_write"].append(rel)
                    continue
                dest.write_text(text, encoding="utf-8")
                report["refreshed"].append(rel)
                manifest[src.name] = _sha256(text)
                manifest_dirty = True
                continue
            # Default skip-if-exists.
            report["skipped"].append(rel)
            continue

        # Missing module, or blanket --force: (re)write from template.
        if dry_run:
            report["would_write"].append(rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        report["written"].append(rel)
        manifest[src.name] = _sha256(text)
        manifest_dirty = True

    if manifest_dirty and not dry_run:
        _write_charter_manifest(target_claude, manifest)
    return report


def _iter_overlay_files():
    """Yield (relative-path, source) for every file under assets/ontology/ (the seed overlay)."""
    base = _ASSETS / "ontology"
    if not base.is_dir():
        return
    for p in sorted(base.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            yield p.relative_to(base), p


def install_overlay_template(
    target_root: Path, ontology_rel: str, *, force: bool, dry_run: bool
) -> dict[str, list[str]]:
    """Lay down the seed semantic-overlay template into <target>/<ontology_rel>/. Idempotent.

    Skip-if-exists by default so a consumer's hand-curated overlay is never clobbered. Creating
    the ontology dir also activates the ontology_refresh / ontology_tracker hooks (both are
    inert until an ontology dir exists).
    """
    report: dict[str, list[str]] = {"copied": [], "skipped": [], "would_copy": []}
    for relpath, src in _iter_overlay_files():
        dest = target_root / ontology_rel / relpath
        rel = f"{ontology_rel}/{relpath}"
        if dest.exists() and not force:
            report["skipped"].append(rel)
            continue
        if dry_run:
            report["would_copy"].append(rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        report["copied"].append(rel)
    return report


def generate_structural(
    target_root: Path, ontology_rel: str, cfg: dict, *, force: bool, dry_run: bool
) -> str:
    """Run the structural generator against the TARGET repo. Fail-open; returns a status line.

    Reuses the same ``ontology_gen.refresh`` path the SessionStart hook uses, so a fresh
    install ends with ``<ontology>/structural/code-graph.json`` + ``llms.txt`` on disk
    immediately (not lazily on the next session). Generation runs against ``target_root``
    (never the framework checkout). Any failure degrades to a warning string — an odd or
    empty target must never abort the install. Deterministic + staleness-guarded, so
    re-running is safe (a fresh index is left untouched).
    """
    if dry_run:
        return "would generate (code-graph.json + llms.txt)"
    lib_dir = _ASSETS / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    try:
        from ontology_gen.refresh import refresh
    except ImportError as e:
        return f"SKIPPED (generator unavailable: {e})"
    project = cfg.get("project", {}) if isinstance(cfg.get("project"), dict) else {}
    model = project.get("model") or "single-repo"
    name = project.get("name") or target_root.name
    try:
        result = refresh(
            target_root, ontology_path=ontology_rel, repo_name=name, model=model, force=force
        )
    except Exception as e:  # noqa: BLE001 — fail-open by contract: install must continue.
        return f"SKIPPED (generation failed: {e}; install continues)"
    if not result.get("regenerated"):
        return "fresh (already current)"
    msg = (
        f"generated ({result.get('files', 0)} files / "
        f"{result.get('nodes', 0)} nodes / {result.get('edges', 0)} edges)"
    )
    agg = result.get("aggregate")
    if agg:
        msg += f"; cross-repo {agg.get('nodes', 0)} nodes across {agg.get('repos', 0)} repo(s)"
    return msg


# ------------------------------------------------------ fresh-vs-existing gate

#: Framework-owned entries that never make a target count as "existing" — the
#: CLI's team scaffolding and our own artifacts must not trip the gate.
_FRAMEWORK_OWNED = {".git", ".claude", "ontology"}


def detect_repo_state(target: Path) -> dict:
    """Detect the target's fresh-vs-existing state. Fail-open (never raises).

    Signals reported: is it a git repo, does it have commits, does it contain
    non-framework files. ``classification`` is ``existing`` when there are
    commits OR foreign files, else ``fresh``. ``installed`` means the framework
    itself is already there (idempotent re-runs skip the gate entirely).
    """
    has_git = (target / ".git").exists()
    has_commits = False
    if has_git:
        try:
            r = subprocess.run(
                ["git", "-C", str(target), "rev-parse", "--verify", "-q", "HEAD"],
                capture_output=True, timeout=10,
            )
            has_commits = r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            pass  # fail-open: git unavailable -> judge by files alone
    nonempty = False
    if target.is_dir():
        for entry in target.iterdir():
            if entry.name in _FRAMEWORK_OWNED or entry.name.startswith("CLAUDE.md"):
                continue
            nonempty = True
            break
    return {
        "has_git": has_git,
        "has_commits": has_commits,
        "nonempty": nonempty,
        "installed": (target / ".claude" / "framework.config.json").is_file(),
        "classification": "existing" if (has_commits or nonempty) else "fresh",
    }


def repo_expectation_gate(
    state: dict,
    expect: str,
    *,
    non_interactive: bool,
    interactive_tty: bool,
    dry_run: bool = False,
    ask=input,
) -> tuple[bool, list[str]]:
    """Decide whether the install may proceed given detection vs ``repo.expect``.

    Returns ``(proceed, notes)``. Rules:

    * already installed        -> proceed (idempotent re-run; gate skipped)
    * ``expect == any`` /match -> proceed
    * mismatch, dry-run        -> proceed (report what a real run would do)
    * mismatch, non-interactive-> REFUSE with a clear message (deliberate: automation
      against an established repo must say so via ``repo.expect: existing|any``)
    * existing repo, interactive TTY -> explicit confirmation prompt ([y/N])
    * otherwise (plain mode / no TTY) -> note and proceed (back-compat)
    """
    notes: list[str] = []
    if state["installed"]:
        notes.append("framework already installed here — idempotent re-run; expectation gate skipped.")
        return True, notes
    actual = state["classification"]
    if expect == "any" or actual == expect:
        if actual == "existing":
            notes.append(f"installing into an EXISTING repo (repo.expect={expect}).")
        return True, notes
    detail = (
        f"repo.expect={expect} but the target looks {actual.upper()} "
        f"(git repo: {'yes' if state['has_git'] else 'no'}, "
        f"commits: {'yes' if state['has_commits'] else 'no'}, "
        f"non-framework files: {'yes' if state['nonempty'] else 'no'})."
    )
    if dry_run:
        notes.append(detail + " Dry-run continues; a non-interactive install would refuse.")
        return True, notes
    if non_interactive:
        notes.append(
            detail + " Refusing: set repo.expect to match the target (or `any`) in the "
            "install config / --expect flag, or run with --interactive to confirm."
        )
        return False, notes
    if interactive_tty and actual == "existing":
        ans = ask(f"{detail}\nInstall into this EXISTING repo anyway? [y/N]: ").strip().lower()
        if ans in ("y", "yes"):
            notes.append("existing repo explicitly confirmed — proceeding.")
            return True, notes
        notes.append("aborted at the existing-repo confirmation.")
        return False, notes
    notes.append(detail + " Proceeding (advisory in this mode).")
    return True, notes


# ------------------------------------------------------ meta/child install modes


def _prompt_children(candidates: list[Path]) -> list[dict]:
    """Interactive multi-select of the meta-repo's children (+ per-child flavor)."""
    if not candidates:
        print("no candidate child repos detected (immediate subdirs with .git).")
        return []
    print("\n-- meta-repo children --")
    print("candidate child repos (immediate subdirs with .git):")
    for i, c in enumerate(candidates, 1):
        print(f"  {i}. {c.name}")
    ans = input(
        "Which are children of this meta-repo? [a]ll / [n]one / numbers (e.g. 1,3) [all]: "
    ).strip().lower()
    if ans in ("", "a", "all"):
        chosen = list(candidates)
    elif ans in ("n", "none"):
        chosen = []
    else:
        picked: set[int] = set()
        for tok in ans.replace(",", " ").split():
            try:
                picked.add(int(tok))
            except ValueError:
                print(f"  (ignored {tok!r} — not a number)")
        chosen = [c for i, c in enumerate(candidates, 1) if i in picked]
    selected: list[dict] = []
    for c in chosen:
        f = input(f"flavor for {c.name}? [p]roduct / [i]nfra [product]: ").strip().lower()
        selected.append({"path": c.name, "flavor": "infra" if f.startswith("i") else "product"})
    return selected


def select_children(
    inst: dict, user_keys: set[str], target: Path, *, interactive_tty: bool
) -> list[dict]:
    """Resolve the meta install's children as ``{path, flavor}`` dicts.

    The config is consulted first: an explicit ``children:`` list (YAML/flags)
    is used VERBATIM — detection never overrides it. Interactive mode (TTY,
    no configured list) multi-selects from ``detect_child_repos`` candidates.
    Non-interactive without a list installs no children (no detection
    surprises). Missing configured paths are fatal.
    """
    if "children" in user_keys or not interactive_tty:
        selected = [dict(c) for c in inst.get("children") or []]
    else:
        selected = _prompt_children(roster_gen.detect_child_repos(target))
    for c in selected:
        c.setdefault("flavor", "product")
    missing = [c["path"] for c in selected if not (target / c["path"]).is_dir()]
    if missing:
        raise SystemExit(
            f"ERROR: configured children not found under {target}: {', '.join(missing)} "
            "— children must exist before the meta install (create/clone them first)."
        )
    for c in selected:
        if not ((target / c["path"]) / ".git").exists():
            print(f"warn:          child {c['path']} is not a git repo (no .git) — installing anyway.")
    return selected


def install_children(
    target: Path,
    meta_cfg: dict,
    selected: list[dict],
    members_by_child: dict[str, list],
    *,
    install_permissions: bool,
    pre_push_mode: str,
    force: bool,
    dry_run: bool,
) -> list[tuple[str, str, dict[str, str]]]:
    """Lay the child layout (parent-relative settings, child runtime config,
    child CLAUDE.md) into each selected child. Roster subsets are written by
    ``roster_gen.write_roster`` (per-child branch). Idempotent throughout."""
    template = json.loads((_ASSETS / "settings.template.json").read_text(encoding="utf-8"))
    reports: list[tuple[str, str, dict[str, str]]] = []
    meta_name = meta_cfg.get("project", {}).get("name") or target.name
    for c in selected:
        rel = child_install.parent_rel_for_child(c["path"])
        child_root = target / c["path"]
        child_tmpl = child_install.build_child_settings(template, rel, c["flavor"])
        settings_status = merge_settings(
            child_root / ".claude", dry_run=dry_run,
            install_permissions=install_permissions, template=child_tmpl,
        )
        ccfg = child_install.child_runtime_config(meta_cfg, child_root.name, rel, c["flavor"])
        cfg_status = write_config(child_root / ".claude", ccfg, force=force, dry_run=dry_run)
        members = [
            (p.role, p.level, p.name) for p in members_by_child.get(child_root.name, [])
        ]
        md = child_install.child_claude_md(
            meta_name=meta_name, rel=rel, flavor=c["flavor"], members=members
        )
        md_status = child_install.write_child_claude_md(child_root, md, dry_run=dry_run)
        statuses = {"settings": settings_status, "config": cfg_status, "CLAUDE.md": md_status}
        if pre_push_mode != "none":  # pushes happen FROM the children — same mode as the meta
            statuses["pre-push"] = install_pre_push(child_root, pre_push_mode, ccfg, dry_run=dry_run)
        reports.append((c["path"], c["flavor"], statuses))
    return reports


def _print_child_reports(reports: list[tuple[str, str, dict[str, str]]]) -> None:
    for path, flavor, statuses in reports:
        detail = "; ".join(f"{k} {v}" for k, v in statuses.items())
        print(f"child {path} [{flavor}]: {detail}")


def install_child_mode(args: argparse.Namespace, inst: dict, user_keys: set[str], target: Path) -> int:
    """The standalone CHILD install (``project.model: child``).

    Installs the child-flavor layout into ``target``, pointing at the parent
    meta-repo from ``parent.path``: parent-relative settings.json, a child
    ``framework.config.json`` (model=child + parent + flavor, shared sections
    inherited from the parent's config), a child-scoped roster, and a child
    CLAUDE.md. No hook/lib assets, charter, or ontology are laid here — those
    live once, at the parent.
    """
    rel = "/".join(child_install.normalize_rel(install_config.get_key(inst, "parent.path"))) or "."
    parent_root = (target / rel).resolve()
    err = child_install.parent_install_error(parent_root)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1
    try:
        parent_cfg = json.loads(
            (parent_root / ".claude" / "framework.config.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: parent framework.config.json is unreadable: {e}", file=sys.stderr)
        return 1

    flavor = install_config.get_key(inst, "project.flavor", "product")
    name = install_config.get_key(inst, "project.name") or target.name
    cfg = child_install.child_runtime_config(parent_cfg, name, rel, flavor)
    cfg = _deep_merge(cfg, install_config.runtime_overlay(inst, user_keys))
    cfg.setdefault("project", {})["model"] = "child"  # never remapped by overlays

    print(f"parent repo:   {parent_root} (framework found)")
    print(f"child flavor:  {flavor}; hook commands anchored at $CLAUDE_PROJECT_DIR/{rel}/.claude/")

    # Child-scoped roster (lead + fitting engineers; org artifacts stay at the meta).
    team_enabled = bool(install_config.get_key(inst, "team.enabled", True))
    roster_plan = None
    if team_enabled:
        email_pattern = cfg.get("identity", {}).get("email_pattern") or "team+{First}.{Last}@example.com"
        roster_plan = roster_gen.plan(
            target, email_pattern=email_pattern, declared_model="child",
            declared_repos=[], team_size=install_config.get_key(inst, "team.size"),
        )
        print("\n-- repo introspection + proposed team --")
        print(roster_plan.summary())
        if not args.no_enforce_identity:
            cfg.setdefault("identity", {})["enforce"] = True
            pre = cfg.setdefault("hooks", {}).setdefault("pre_bash", [])
            if "validate_commit_identity" not in pre:
                pre.insert(0, "validate_commit_identity")
    else:
        # Without a child roster the gate would have nothing to allow — leave
        # enforcement to an explicit later opt-in (mirrors --no-team standalone).
        cfg.setdefault("identity", {})["enforce"] = False

    problems = validate_config(cfg)
    if problems:
        print("config problems:")
        for p in problems:
            print(f"  - {p}")
        if any("version" in p for p in problems):
            print("ERROR: refusing to install an invalid config.", file=sys.stderr)
            return 1
        print("  (continuing; non-fatal)")

    target_claude = target / ".claude"
    template = json.loads((_ASSETS / "settings.template.json").read_text(encoding="utf-8"))
    child_tmpl = child_install.build_child_settings(template, rel, flavor)
    settings_status = merge_settings(
        target_claude, dry_run=args.dry_run,
        install_permissions=not args.no_permissions, template=child_tmpl,
    )
    cfg_status = write_config(target_claude, cfg, force=args.force, dry_run=args.dry_run)
    snapshot_status = write_install_snapshot(target_claude, inst, force=args.force, dry_run=args.dry_run)
    # Pre-push hook: same resolved pre_push.mode contract as a standalone install
    # (a child is its own git repo — pushes happen from here).
    pre_push_mode = install_config.get_key(inst, "pre_push.mode", "noop")
    pre_push_status = install_pre_push(target, pre_push_mode, cfg, dry_run=args.dry_run)

    roster_status = "skipped (team disabled)"
    if roster_plan is not None:
        rep = roster_gen.write_roster(target_claude / "team", roster_plan, force=args.force, dry_run=args.dry_run)
        if args.dry_run:
            roster_status = f"would write {len(rep['would_write'])} file(s) for {len(roster_plan.personas)} member(s)"
        else:
            roster_status = f"wrote {len(rep['written'])} file(s) ({len(roster_plan.personas)} member(s)); {len(rep['skipped'])} skipped"

    members = [(p.role, p.level, p.name) for p in (roster_plan.personas if roster_plan else [])]
    md = child_install.child_claude_md(
        meta_name=parent_root.name, rel=rel, flavor=flavor, members=members
    )
    md_status = child_install.write_child_claude_md(target, md, dry_run=args.dry_run)

    print("\n-- plan --" if args.dry_run else "\n-- result --")
    print("hook assets:       none (child repos invoke the PARENT's hooks)")
    print(f"settings.json:     {settings_status}")
    print(f"framework.config:  {cfg_status} (project.model=child, parent={rel}, flavor={flavor})")
    print(f"install snapshot:  {snapshot_status}")
    print(f"pre-push hook:     {pre_push_status}")
    print(f"team roster:       {roster_status}")
    print(f"CLAUDE.md:         {md_status}")
    if roster_plan is not None and not args.no_enforce_identity:
        print("identity gate:     ENABLED (this roster ∪ the meta roster via the parent-merge)")
    return 0


# ---------------------------------------------------------------- pre-push hook

_NOOP_PRE_PUSH = """\
#!/bin/sh
# pre-push -- installed by the 2real team framework (framework/install/bootstrap.py).
#
# MODE: noop. This hook does nothing and never blocks a push (it exits 0).
# It exists so the enforcement seam is visible: one config edit + reinstall
# turns on real pre-push checks with no further wiring.
#
# To enable enforcement:
#   1. List the checks to run in .claude/framework.config.json:
#        "hooks": { "pre_push_commands": ["ruff check .", "pytest -q"] }
#   2. Re-run the bootstrapper with --pre-push enforce
#      (this hook is replaced; a non-framework hook would be kept as pre-push.bak).
#
# To remove: delete this file. Re-running bootstrap with --pre-push none
# installs nothing (it never deletes an existing hook).
exit 0
"""

_ENFORCE_PRE_PUSH = """\
#!/bin/sh
# pre-push -- installed by the 2real team framework (framework/install/bootstrap.py).
#
# MODE: enforce. Runs every command in hooks.pre_push_commands from
# .claude/framework.config.json (in order, from the repo root) and BLOCKS the
# push on the first nonzero exit. The list is read at push time, so editing the
# config changes the checks with no reinstall.
#
# Fail-open by design: a missing config, missing python3, or an empty command
# list allows the push (with a note) rather than stranding you.
#
# To go back to a do-nothing hook: re-run the bootstrapper with --pre-push noop.
repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cfg="$repo_root/.claude/framework.config.json"
[ -f "$cfg" ] || { echo "pre-push: no framework.config.json - allowing push." >&2; exit 0; }
command -v python3 >/dev/null 2>&1 || { echo "pre-push: python3 not found - allowing push." >&2; exit 0; }
cd "$repo_root" || exit 0
exec python3 - "$cfg" <<'PY'
import json, subprocess, sys

try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        cmds = (json.load(fh).get("hooks") or {}).get("pre_push_commands") or []
except (OSError, ValueError):
    sys.exit(0)  # fail-open: an unreadable config never blocks a push
if not cmds:
    print("pre-push: hooks.pre_push_commands is empty - allowing push.", file=sys.stderr)
    sys.exit(0)
for cmd in cmds:
    print(f"pre-push: running: {cmd}", file=sys.stderr)
    rc = subprocess.run(cmd, shell=True).returncode
    if rc != 0:
        print(f"pre-push: BLOCKED - '{cmd}' failed (exit {rc}).", file=sys.stderr)
        print(
            "pre-push: fix the failure, or edit hooks.pre_push_commands in"
            " .claude/framework.config.json.",
            file=sys.stderr,
        )
        sys.exit(rc)
print("pre-push: all checks passed.", file=sys.stderr)
PY
"""


def _next_backup_path(path: Path) -> Path:
    """Return a non-clobbering backup path for ``path``.

    Prefers ``<name>.bak``; if that already exists, falls back to ``<name>.bak.1``,
    ``<name>.bak.2``, … so an existing backup is never overwritten. (Mirrors the
    CLAUDE.md backup pattern in python/src/real_team/bootstrap.py.)
    """
    backup = path.with_name(path.name + ".bak")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.bak.{counter}")
        counter += 1
    return backup


def _git_hooks_dir(target: Path) -> tuple[Path | None, str | None]:
    """Resolve the EFFECTIVE git hooks dir for ``target``. Returns (dir, note).

    Asks git itself first (``rev-parse --git-path hooks``), which honours
    ``core.hooksPath`` and worktree/submodule ``.git``-file layouts; the note
    reports a non-default ``core.hooksPath`` so the operator knows where the
    hook went. Falls back to a manual ``.git`` walk when the git binary is
    unavailable. Returns ``(None, reason)`` when there is nowhere sane to write
    (fail-open: the caller skips with a notice, never errors).
    """
    git_entry = target / ".git"
    if not git_entry.exists():
        return None, "no .git"
    try:
        r = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "--git-path", "hooks"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            hooks_dir = Path(r.stdout.strip())
            if not hooks_dir.is_absolute():
                hooks_dir = (target / hooks_dir).resolve()
            note = None
            c = subprocess.run(
                ["git", "-C", str(target), "config", "--get", "core.hooksPath"],
                capture_output=True, text=True, timeout=10,
            )
            if c.returncode == 0 and c.stdout.strip():
                note = f"core.hooksPath is set ({c.stdout.strip()})"
            return hooks_dir, note
    except (OSError, subprocess.SubprocessError):
        pass  # git missing/broken -> manual fallback below
    if git_entry.is_dir():
        return git_entry / "hooks", None
    try:  # worktree/submodule: .git is a file containing "gitdir: <path>"
        for line in git_entry.read_text(encoding="utf-8").splitlines():
            if line.startswith("gitdir:"):
                gitdir = Path(line.split(":", 1)[1].strip())
                if not gitdir.is_absolute():
                    gitdir = (target / gitdir).resolve()
                return gitdir / "hooks", None
    except OSError:
        pass
    return None, "unrecognised .git layout"


def install_pre_push(target: Path, mode: str, cfg: dict | None = None, *, dry_run: bool) -> str:
    """Install ``<hooks-dir>/pre-push`` in ``target`` per ``mode``. Idempotent.

    Self-contained (only reads ``cfg`` for an advisory); ``mode`` is the
    RESOLVED install-config ``pre_push.mode`` (--pre-push flag > user YAML >
    shipped default noop). ``noop`` writes an executable, clearly-commented
    exit-0 script; ``enforce`` writes a script that runs
    ``hooks.pre_push_commands`` from framework.config.json and blocks the push
    on failure; ``none`` installs nothing. A pre-existing pre-push with
    different content is never clobbered — it is preserved via the
    non-clobbering ``.bak`` pattern with a warning. No ``.git`` -> skip with a
    notice (fail-open). Returns a one-line status for the report.
    """
    if mode == "none":
        return "skipped (pre_push.mode=none)"
    hooks_dir, note = _git_hooks_dir(target)
    if hooks_dir is None:
        return f"skipped ({note} — nothing to hook; re-run after `git init`)"
    if note:
        print(f"note:          {note} — writing pre-push there")
    if mode == "enforce" and cfg is not None:
        if not (cfg.get("hooks") or {}).get("pre_push_commands"):
            print(
                "warn:          hooks.pre_push_commands is empty — the enforce hook will"
                " allow pushes until you set it in .claude/framework.config.json"
            )
    content = _ENFORCE_PRE_PUSH if mode == "enforce" else _NOOP_PRE_PUSH
    dest = hooks_dir / "pre-push"
    if dest.exists():
        try:
            existing = dest.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            existing = None
        if existing == content:
            return f"already installed ({mode}; unchanged)"
        if dry_run:
            return f"would back up existing pre-push (.bak) and write the {mode} hook"
        backup = _next_backup_path(dest)
        dest.rename(backup)
        print(
            f"warn:          existing pre-push preserved as {backup.name} —"
            " reconcile any custom logic it carried"
        )
    if dry_run:
        return f"would write the {mode} hook"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    dest.chmod(0o755)
    return f"installed ({mode}) at {dest}"


# ---------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Install the 2real framework hooks into a repo.",
        epilog=install_config.HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("target", nargs="?", default=".", help="Target repo root (default: cwd)")
    ap.add_argument("--install-config", metavar="YAML",
                    help="Unified YAML install config (see the key reference below). "
                         "Precedence: CLI flags > this file > shipped defaults.")
    ap.add_argument("--config", help="JSON RUNTIME-config seed (framework.config.json shape)")
    ap.add_argument("--owner", help="scm.owner (GitHub org/user)")
    ap.add_argument("--project-name", help="project.name")
    ap.add_argument("--model", choices=["single-repo", "meta-and-children", "child"])
    ap.add_argument("--expect", choices=["fresh", "existing", "any"],
                    help="repo.expect override: what the target should look like "
                         "(non-interactive installs refuse on a mismatch; `any` always proceeds)")
    ap.add_argument("--shell", choices=["bash", "zsh"])
    ap.add_argument("--reviewers", type=int)
    ap.add_argument("--merge-model", choices=["wave-branch", "direct-to-main"])
    ap.add_argument("--pre-push", choices=["noop", "enforce", "none"], default=None,
                    help="Pre-push git hook to install (install-config key pre_push.mode; "
                         "precedence: this flag > user YAML > shipped default noop). "
                         "enforce runs hooks.pre_push_commands; none installs nothing.")
    mode_group = ap.add_mutually_exclusive_group()
    mode_group.add_argument("--interactive", action="store_true",
                            help="Prompt for missing fields + review the proposed team (TTY only)")
    mode_group.add_argument("--non-interactive", action="store_true",
                            help="Guarantee zero prompts on every path; the install config "
                                 "(flags > YAML > shipped defaults) answers everything")
    ap.add_argument("--no-team", action="store_true", help="Skip roster generation (install hooks only)")
    ap.add_argument("--team-size", type=int, help="Target headcount for the generated roster")
    ap.add_argument("--no-enforce-identity", action="store_true", help="Generate the roster but do NOT enable the commit-identity gate")
    ontology_group = ap.add_mutually_exclusive_group()
    ontology_group.add_argument("--with-ontology", action="store_true",
                                help="Lay down the seed semantic-overlay template AND generate the "
                                     "structural index (ontology.enabled=true; activates the ontology hooks)")
    ontology_group.add_argument("--no-ontology", action="store_true",
                                help="Skip the ontology seed + structural index (ontology.enabled=false)")
    ap.add_argument("--no-permissions", action="store_true", help="Do NOT install the curated permissions.allow allowlist into settings.json (hook wiring still merges)")
    ap.add_argument(
        "--user-space", action="store_true",
        help="Also run the CONSENTED user-level install step: idempotently add the "
             "framework's harness-global settings (agent-teams flag, teammateMode, "
             "worktree baseRef, ~/.claude permission globs) to ~/.claude/settings.json "
             "(closes #106 G1). Opt-in prompt before any write; --non-interactive skips it; "
             "existing/matching keys are a no-op; divergent values are surfaced, never clobbered.",
    )
    ap.add_argument("--force", action="store_true", help="Overwrite existing files")
    ap.add_argument(
        "--refresh-charter", action="store_true",
        help="Re-render the team charter from the template with the current config, overwriting "
             "ONLY modules you have not hand-edited (three-way; hand-evolved modules are preserved). "
             "Use this — not --force — to propagate a config change into an evolved charter.",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print the plan; write nothing")
    args = ap.parse_args()

    if not _ASSETS.is_dir():
        print(f"ERROR: framework assets not found at {_ASSETS}", file=sys.stderr)
        return 1

    target = Path(args.target).resolve()
    target_claude = target / ".claude"
    mode = "DRY-RUN" if args.dry_run else "INSTALL"
    print(f"== 2real framework bootstrap ({mode}) ==")
    print(f"target repo:   {target}")

    inst, user_keys = resolve_install_config(args)
    interactive_tty = args.interactive and sys.stdin.isatty()

    # Fresh-vs-existing gate: detect, REPORT, then enforce repo.expect.
    state = detect_repo_state(target)
    print("\n-- target repo state --")
    print(f"git repo:      {'yes' if state['has_git'] else 'no'}"
          f"{' (with commits)' if state['has_commits'] else ' (no commits yet)' if state['has_git'] else ''}")
    print(f"other files:   {'yes' if state['nonempty'] else 'no'} "
          "(framework-owned .claude/, CLAUDE.md*, ontology/ excluded)")
    print(f"verdict:       {state['classification']} "
          f"(repo.expect: {install_config.get_key(inst, 'repo.expect', 'fresh')})")
    proceed, notes = repo_expectation_gate(
        state, install_config.get_key(inst, "repo.expect", "fresh"),
        non_interactive=args.non_interactive, interactive_tty=interactive_tty,
        dry_run=args.dry_run,
    )
    for n in notes:
        print(f"repo gate:     {n}", file=None if proceed else sys.stderr)
    if not proceed:
        print("ERROR: refusing to install (repo expectation gate).", file=sys.stderr)
        return 1

    # Repo-level disposition (#108): if the target already carries FOREIGN Claude
    # assets (a .claude/ or CLAUDE.md we did NOT install), offer — with explicit
    # consent — to ARCHIVE them out of Claude's scope for a fresh install, or amend
    # them in place. Non-interactive / non-TTY / dry-run take the safe non-destructive
    # path (amend), preserving today's behaviour for CI. Skipped on our own idempotent
    # re-runs (state["installed"]) and when there is nothing existing to touch.
    if not args.dry_run and not state["installed"] and repo_space.has_existing_assets(target):
        prep = repo_space.prepare_for_install(target, non_interactive=args.non_interactive)
        if prep.action == "cancel":
            print(
                "aborted: existing repo Claude assets left untouched "
                "(no consent to archive; nothing written).",
                file=sys.stderr,
            )
            return 1
        if prep.action == "archived":
            print("\n-- repo Claude assets archived (out of Claude's scope; restorable) --")
            print(f"moved:   {', '.join(prep.archive.moved)} -> {prep.archive.archive_dir}")
            print(
                f"restore: python3 framework/install/repo_space.py restore "
                f"{prep.archive.archive_dir}"
            )
        elif prep.action == "amend":
            print(
                "\nexisting repo Claude assets: amending in place "
                "(idempotent; nothing archived)."
            )

    # The CHILD install mode is a different layout (no hook code of its own) —
    # dedicated path.
    if install_config.get_key(inst, "project.model") == "child":
        return install_child_mode(args, inst, user_keys, target)

    cfg = build_config(args, inst, user_keys)

    # META install: resolve which subdir repos are children (config verbatim in
    # non-interactive mode; multi-select from detection in interactive mode).
    install_model = install_config.get_key(inst, "project.model", "standalone")
    selected_children: list[dict] = []
    if install_model == "meta":
        selected_children = select_children(
            inst, user_keys, target, interactive_tty=interactive_tty
        )
        inst["children"] = selected_children  # the snapshot records the SELECTION
        cfg.setdefault("project", {})["model"] = "meta-and-children"
        cfg["project"]["repos"] = [target.name] + [
            (target / c["path"]).name for c in selected_children
        ]

    # --- introspect the repo + plan the roster (the team layer) ---
    team_enabled = bool(install_config.get_key(inst, "team.enabled", True))
    team_size = install_config.get_key(inst, "team.size")
    roster_plan = None
    if team_enabled:
        email_pattern = cfg.get("identity", {}).get("email_pattern") or "team+{First}.{Last}@example.com"
        # A meta SELECTION drives the roster exactly (paths, not detection);
        # otherwise a --config seed's declared repos / detection apply as before.
        declared_repos = (
            [c["path"] for c in selected_children]
            if install_model == "meta"
            else cfg.get("project", {}).get("repos")
        )
        roster_plan = roster_gen.plan(
            target,
            email_pattern=email_pattern,
            declared_model=cfg.get("project", {}).get("model"),
            declared_repos=declared_repos,
            team_size=team_size,
        )
        # Record what introspection found back into the configs.
        cfg.setdefault("project", {})["model"] = roster_plan.intro.model
        if roster_plan.intro.model == "meta-and-children":
            cfg["project"]["repos"] = [r.name for r in roster_plan.intro.repos]
        if "project.model" not in user_keys:
            install_config.set_key(
                inst, "project.model",
                install_config.INSTALL_MODEL_MAP.get(roster_plan.intro.model, "standalone"),
            )

        print("\n-- repo introspection + proposed team --")
        print(roster_plan.summary())

        # The config is consulted first: an explicit team decision (team.size /
        # team.enabled via YAML or flag) answers the proceed-prompt.
        team_answered = bool({"team.size", "team.enabled"} & user_keys)
        if args.interactive and sys.stdin.isatty() and not team_answered:
            ans = input("\nProceed with this team? [Y]es / [s]ize N / [n]o team: ").strip().lower()
            if ans.startswith("n"):
                team_enabled = False
                roster_plan = None
                install_config.set_key(inst, "team.enabled", False)
            elif ans.startswith("s"):
                try:
                    size = int(ans.split()[-1])
                    roster_plan = roster_gen.plan(target, email_pattern=email_pattern,
                                                  declared_model=cfg["project"]["model"],
                                                  declared_repos=declared_repos,
                                                  team_size=size)
                    print(roster_plan.summary())
                    install_config.set_key(inst, "team.size", size)
                except (ValueError, IndexError):
                    print("  (could not parse size; keeping the proposed team)")

        if team_enabled and not args.no_enforce_identity:
            cfg.setdefault("identity", {})["enforce"] = True
            pre = cfg.setdefault("hooks", {}).setdefault("pre_bash", [])
            if "validate_commit_identity" not in pre:
                pre.insert(0, "validate_commit_identity")  # identity check runs first

    problems = validate_config(cfg)
    if problems:
        print("config problems:")
        for p in problems:
            print(f"  - {p}")
        if any("version" in p for p in problems):
            print("ERROR: refusing to install an invalid config.", file=sys.stderr)
            return 1
        print("  (continuing; non-fatal)")
    if not cfg.get("scm", {}).get("owner"):
        print("warn:          scm.owner is unset — gh-calling hooks will be limited until you set it.")

    assets = install_assets(target_claude, force=args.force, dry_run=args.dry_run)
    cfg_status = write_config(target_claude, cfg, force=args.force, dry_run=args.dry_run)
    snapshot_status = write_install_snapshot(target_claude, inst, force=args.force, dry_run=args.dry_run)
    settings_status = merge_settings(
        target_claude, dry_run=args.dry_run, install_permissions=not args.no_permissions
    )
    charter = install_charter(
        target_claude, cfg, force=args.force, refresh=args.refresh_charter, dry_run=args.dry_run
    )
    # Pre-push hook mode is config-driven: the RESOLVED pre_push.mode
    # (flag > user YAML > shipped default noop).
    pre_push_mode = install_config.get_key(inst, "pre_push.mode", "noop")
    pre_push_status = install_pre_push(target, pre_push_mode, cfg, dry_run=args.dry_run)

    # Ontology (seed overlay + generated structural index) is config-driven:
    # the RESOLVED ontology.enabled (flags > user YAML > shipped default ON).
    overlay = None
    structural_status = None
    if install_config.get_key(inst, "ontology.enabled", True):
        ontology_rel = cfg.get("paths", {}).get("ontology", "ontology")
        overlay = install_overlay_template(target, ontology_rel, force=args.force, dry_run=args.dry_run)
        structural_status = generate_structural(
            target, ontology_rel, cfg, force=args.force, dry_run=args.dry_run
        )

    roster_status = "skipped (team disabled)"
    if team_enabled and roster_plan is not None:
        rep = roster_gen.write_roster(target_claude / "team", roster_plan, force=args.force, dry_run=args.dry_run)
        n_children = max(0, len(roster_plan.intro.repos) - 1) if roster_plan.intro.model == "meta-and-children" else 0
        child_note = f"; {n_children} per-child roster(s)" if n_children else ""
        if args.dry_run:
            roster_status = f"would write {len(rep['would_write'])} file(s) for {len(roster_plan.personas)} member(s){child_note}"
        else:
            roster_status = f"wrote {len(rep['written'])} file(s) ({len(roster_plan.personas)} member(s){child_note}); {len(rep['skipped'])} skipped"

    # META model: lay the child layout (parent-relative settings, child runtime
    # config, child CLAUDE.md) into every SELECTED child. Runs after the meta
    # cfg is final so children inherit the real identity/hooks sections.
    child_reports: list[tuple[str, str, dict[str, str]]] = []
    if selected_children:
        members_by_child: dict[str, list] = {}
        if roster_plan is not None and roster_plan.intro.model == "meta-and-children":
            _, members_by_child = roster_gen.partition_for_children(
                roster_plan.personas, roster_plan.intro
            )
        child_reports = install_children(
            target, cfg, selected_children, members_by_child,
            install_permissions=not args.no_permissions,
            pre_push_mode=pre_push_mode, force=args.force,
            dry_run=args.dry_run,
        )

    print("\n-- plan --" if args.dry_run else "\n-- result --")
    print(f"hooks/lib copied:  {len(assets['copied'])}")
    if assets["would_copy"]:
        print(f"would copy:        {len(assets['would_copy'])} ({', '.join(assets['would_copy'][:6])}{' …' if len(assets['would_copy'])>6 else ''})")
    if assets["skipped"]:
        print(f"skipped (exists):  {len(assets['skipped'])} (use --force to overwrite)")
    print(f"framework.config:  {cfg_status}")
    print(f"install snapshot:  {snapshot_status}")
    print(f"settings.json:     {settings_status}")
    charter_laid = charter["would_write"] if args.dry_run else charter["written"]
    charter_line = (
        f"team charter:      {len(charter_laid)} file(s) "
        f"{'would be written' if args.dry_run else 'written'}; "
        f"{len(charter['skipped'])} skipped"
    )
    if charter["refreshed"] or charter["preserved"]:
        charter_line += (
            f"; {len(charter['refreshed'])} refreshed"
            f"; {len(charter['preserved'])} preserved (hand-evolved)"
        )
    print(charter_line)
    if charter["preserved"]:
        print(
            "  note: hand-evolved charter module(s) preserved on refresh — "
            f"{', '.join(charter['preserved'])}. Use --force to overwrite."
        )
    print(f"pre-push hook:     {pre_push_status}")
    children = inst.get("children") or []
    if children:
        print(f"children:          {len(children)} recorded ({', '.join(c.get('path', '?') for c in children[:4])}{' …' if len(children) > 4 else ''})")
    _print_child_reports(child_reports)
    if overlay is not None:
        laid = overlay["would_copy"] if args.dry_run else overlay["copied"]
        print(f"ontology overlay:  {len(laid)} file(s) {'would be laid' if args.dry_run else 'laid'}; {len(overlay['skipped'])} skipped")
    if structural_status is not None:
        print(f"structural index:  {structural_status}")
    print(f"team roster:       {roster_status}")
    if team_enabled and roster_plan is not None and not args.no_enforce_identity:
        print("identity gate:     ENABLED (commits must use -c user.name/-c user.email from the roster)")

    # CONSENTED user-level step (#107, closes #106 G1). Opt-in: only when --user-space
    # is passed. Merge-only, idempotent, consent-gated; --non-interactive skips it and a
    # dry-run never writes. Reads/writes ~/.claude, never the target repo — kept last so
    # a repo install is complete before we touch user space.
    if args.user_space:
        import user_space  # noqa: E402  (sibling module in install/)

        target_settings = user_space.user_settings_path()
        if args.dry_run:
            print("\n-- user-level install (~/.claude/settings.json) --")
            print(f"would offer to add the framework's harness-global settings to {target_settings}")
        else:
            us_result = user_space.install_user_space(non_interactive=args.non_interactive)
            print("\n" + user_space.report(us_result, target_settings))
    elif not args.dry_run:
        print(
            "\nhint: harness-global team settings (agent-teams flag, worktree base) are a "
            "USER-level concern. Re-run with --user-space (or `python3 "
            "framework/install/user_space.py`) to install them into ~/.claude with consent."
        )

    print("\nNext:")
    print("  1. Review .claude/framework.config.json (scm.owner / policy / ci.tooling) and .claude/team/roster.json.")
    print("  2. Flesh out the persona cards in .claude/team/roster/ (or generate personalities).")
    print("  3. Restart Claude Code in the repo so the new settings.json hooks load.")
    print("  4. Try a blocked action (e.g. `git commit --no-verify`) to confirm the gate fires.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
