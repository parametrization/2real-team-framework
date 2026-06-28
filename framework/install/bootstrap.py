#!/usr/bin/env python3
"""Deterministic bootstrapper: install the 2real framework hooks into a repo.

Lays down the genericised hook/lib assets, writes a ``framework.config.json``,
and wires the dispatchers into the target repo's ``.claude/settings.json`` — for
either a NEW or an EXISTING repo. Determinism is the priority: the whole install
is driven by flags + an optional config file and is fully idempotent, so re-running
changes nothing. Interactive prompts are an opt-in convenience, never required.

Stdlib only (no deps), so it runs anywhere ``python3`` does.

Usage
=====

  # Deterministic (no prompts) — minimal:
  python3 bootstrap.py /path/to/repo --owner my-org

  # From a prepared config file (recommended for reproducible installs):
  python3 bootstrap.py /path/to/repo --config my.framework.config.json

  # Preview without writing anything:
  python3 bootstrap.py /path/to/repo --owner my-org --dry-run

  # Interactive fill of any still-missing required fields (TTY only):
  python3 bootstrap.py /path/to/repo --interactive

Flags
=====
  target                 Target repo root (default: current directory).
  --config PATH          JSON config to seed from (overlaid on schema defaults).
  --owner NAME           scm.owner (GitHub org/user). Overlays --config.
  --project-name NAME    project.name.
  --model {single-repo,meta-and-children}
  --shell {bash,zsh}
  --reviewers N          policy.reviewers_required.
  --merge-model {wave-branch,direct-to-main}
  --interactive          Prompt for missing required fields (scm.owner) if a TTY.
  --force                Overwrite existing hook/lib files and framework.config.json.
  --dry-run              Print the plan; write nothing.

Exit codes: 0 ok / dry-run, 1 on a hard error (e.g. assets missing).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
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
    """
    return {
        "version": 1,
        "scm": {"provider": "github", "default_branch": "main", "allow_force": False},
        "shell": "bash",
        "hooks": {
            "pre_bash": [
                "block_no_verify",
                "block_git_config",
                "no_worktree_self_delete",
                "warn_zsh_wordsplit",
                "validate_workflow_paths_coverage",
                "validate_pr_ci_status",
            ],
            "post_bash": ["warn_pipe_mask_rc"],
            "post_file": ["ontology_tracker"],
            "session_start": ["ontology_refresh"],
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


def build_config(args: argparse.Namespace) -> dict:
    cfg = _schema_defaults()
    if args.config:
        try:
            loaded = json.loads(Path(args.config).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise SystemExit(f"ERROR: --config could not be read: {e}")
        if not isinstance(loaded, dict):
            raise SystemExit("ERROR: --config must be a JSON object")
        cfg = _deep_merge(cfg, loaded)

    # Individual flags overlay the config file.
    if args.owner:
        _set_path(cfg, "scm.owner", args.owner)
    if args.project_name:
        _set_path(cfg, "project.name", args.project_name)
    if args.model:
        _set_path(cfg, "project.model", args.model)
    if args.shell:
        _set_path(cfg, "shell", args.shell)
    if args.reviewers is not None:
        _set_path(cfg, "policy.reviewers_required", args.reviewers)
    if args.merge_model:
        _set_path(cfg, "policy.merge_model", args.merge_model)

    # Interactive fill of still-missing required-ish fields (TTY only).
    if args.interactive and sys.stdin.isatty():
        if not cfg.get("scm", {}).get("owner"):
            ans = input("GitHub owner (org or user) [leave blank to skip]: ").strip()
            if ans:
                _set_path(cfg, "scm.owner", ans)

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


def _script_id(command: str) -> str:
    """Stable identity for a hook command = its ``.py`` script basename (else the command).

    Lets the merge recognise an already-wired hook regardless of the ``$CLAUDE_PROJECT_DIR``
    prefix or quoting, so re-running bootstrap is idempotent for every event (Pre/Post/Session).
    """
    for token in command.replace('"', " ").split():
        if token.endswith(".py"):
            return Path(token).name
    return command.strip()


def merge_settings(target_claude: Path, *, dry_run: bool) -> str:
    """Idempotently merge the template hook wiring into <target>/.claude/settings.json.

    Generic over events (PreToolUse / PostToolUse / SessionStart / …): blocks match by
    ``matcher`` (which may be absent — e.g. SessionStart), and each template hook is added only
    if no existing hook in that block already references the same script. Re-running is a no-op.
    """
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

    if not changed:
        return "already wired"
    if dry_run:
        return "would update"
    target_claude.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    return "updated"


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


# ---------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description="Install the 2real framework hooks into a repo.")
    ap.add_argument("target", nargs="?", default=".", help="Target repo root (default: cwd)")
    ap.add_argument("--config", help="JSON config to seed from")
    ap.add_argument("--owner", help="scm.owner (GitHub org/user)")
    ap.add_argument("--project-name", help="project.name")
    ap.add_argument("--model", choices=["single-repo", "meta-and-children"])
    ap.add_argument("--shell", choices=["bash", "zsh"])
    ap.add_argument("--reviewers", type=int)
    ap.add_argument("--merge-model", choices=["wave-branch", "direct-to-main"])
    ap.add_argument("--interactive", action="store_true", help="Prompt for missing fields + review the proposed team (TTY only)")
    ap.add_argument("--no-team", action="store_true", help="Skip roster generation (install hooks only)")
    ap.add_argument("--team-size", type=int, help="Target headcount for the generated roster")
    ap.add_argument("--no-enforce-identity", action="store_true", help="Generate the roster but do NOT enable the commit-identity gate")
    ap.add_argument("--with-ontology", action="store_true", help="Lay down the seed semantic-overlay template (activates the ontology hooks)")
    ap.add_argument("--force", action="store_true", help="Overwrite existing files")
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
    if not (target / ".git").exists():
        print("note:          no .git here — installing anyway (new repo / pre-init).")

    cfg = build_config(args)

    # --- introspect the repo + plan the roster (the team layer) ---
    team_enabled = not args.no_team
    roster_plan = None
    if team_enabled:
        email_pattern = cfg.get("identity", {}).get("email_pattern") or "team+{First}.{Last}@example.com"
        roster_plan = roster_gen.plan(
            target,
            email_pattern=email_pattern,
            declared_model=cfg.get("project", {}).get("model"),
            declared_repos=cfg.get("project", {}).get("repos"),
            team_size=args.team_size,
        )
        # Record what introspection found back into the config.
        cfg.setdefault("project", {})["model"] = roster_plan.intro.model
        if roster_plan.intro.model == "meta-and-children":
            cfg["project"]["repos"] = [r.name for r in roster_plan.intro.repos]

        print("\n-- repo introspection + proposed team --")
        print(roster_plan.summary())

        if args.interactive and sys.stdin.isatty():
            ans = input("\nProceed with this team? [Y]es / [s]ize N / [n]o team: ").strip().lower()
            if ans.startswith("n"):
                team_enabled = False
                roster_plan = None
            elif ans.startswith("s"):
                try:
                    size = int(ans.split()[-1])
                    roster_plan = roster_gen.plan(target, email_pattern=email_pattern,
                                                  declared_model=cfg["project"]["model"],
                                                  declared_repos=cfg.get("project", {}).get("repos"),
                                                  team_size=size)
                    print(roster_plan.summary())
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
    settings_status = merge_settings(target_claude, dry_run=args.dry_run)

    overlay = None
    if args.with_ontology:
        ontology_rel = cfg.get("paths", {}).get("ontology", "ontology")
        overlay = install_overlay_template(target, ontology_rel, force=args.force, dry_run=args.dry_run)

    roster_status = "skipped (--no-team)"
    if team_enabled and roster_plan is not None:
        rep = roster_gen.write_roster(target_claude / "team", roster_plan, force=args.force, dry_run=args.dry_run)
        n_children = max(0, len(roster_plan.intro.repos) - 1) if roster_plan.intro.model == "meta-and-children" else 0
        child_note = f"; {n_children} per-child roster(s)" if n_children else ""
        if args.dry_run:
            roster_status = f"would write {len(rep['would_write'])} file(s) for {len(roster_plan.personas)} member(s){child_note}"
        else:
            roster_status = f"wrote {len(rep['written'])} file(s) ({len(roster_plan.personas)} member(s){child_note}); {len(rep['skipped'])} skipped"

    print("\n-- plan --" if args.dry_run else "\n-- result --")
    print(f"hooks/lib copied:  {len(assets['copied'])}")
    if assets["would_copy"]:
        print(f"would copy:        {len(assets['would_copy'])} ({', '.join(assets['would_copy'][:6])}{' …' if len(assets['would_copy'])>6 else ''})")
    if assets["skipped"]:
        print(f"skipped (exists):  {len(assets['skipped'])} (use --force to overwrite)")
    print(f"framework.config:  {cfg_status}")
    print(f"settings.json:     {settings_status}")
    if overlay is not None:
        laid = overlay["would_copy"] if args.dry_run else overlay["copied"]
        print(f"ontology overlay:  {len(laid)} file(s) {'would be laid' if args.dry_run else 'laid'}; {len(overlay['skipped'])} skipped")
    print(f"team roster:       {roster_status}")
    if team_enabled and roster_plan is not None and not args.no_enforce_identity:
        print("identity gate:     ENABLED (commits must use -c user.name/-c user.email from the roster)")

    print("\nNext:")
    print("  1. Review .claude/framework.config.json (scm.owner / policy / ci.tooling) and .claude/team/roster.json.")
    print("  2. Flesh out the persona cards in .claude/team/roster/ (or generate personalities).")
    print("  3. Restart Claude Code in the repo so the new settings.json hooks load.")
    print("  4. Try a blocked action (e.g. `git commit --no-verify`) to confirm the gate fires.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
