"""Child-repo install layout for the meta/child project models.

Children carry NO hook code. A child repo's ``.claude/settings.json`` invokes
the PARENT meta-repo's installed dispatchers, so there is exactly one copy of
the hook/lib assets per project tree (at the meta root) and every child stays
on the same version automatically.

Portable hook-command form
==========================

The child's hook commands are anchored at ``$CLAUDE_PROJECT_DIR`` (which Claude
Code sets to the CHILD's root at runtime) plus a *relative* traversal up to the
parent::

    python3 "$CLAUDE_PROJECT_DIR/../.claude/hooks/dispatcher.py"

The reference design this is drawn from used machine-absolute paths; we require
portability instead — **no machine-specific absolute path ever appears in a
child settings.json**. Trade-off of the relative form: it assumes the child
keeps its position relative to the parent (e.g. stays an immediate subdir).
That is exactly the meta-and-children contract — the parent .gitignores its
children in place — and in exchange the whole tree can be cloned to any path on
any machine and the wiring keeps working. The traversal depth is derived from
the child's configured path (``api`` -> ``..``; ``services/api`` -> ``../..``).

Flavors
=======

``product``  — the full harness: every event in ``settings.template.json``
               (SessionStart ontology refresh, pre/post Bash dispatchers, file-edit
               tracking), rewritten to the parent-relative form.
``infra``    — the commit-safety + CI subset: ONLY the ``Bash``-matched
               PreToolUse/PostToolUse dispatcher blocks (identity/safety gates,
               CI/pipe-mask checks). No SessionStart, no file-edit ontology
               extras — an infra child is plumbing, not a product surface.

Both flavors get a child ``framework.config.json`` (``project.model: child`` +
``project.parent`` + ``project.flavor``, with ``scm``/``identity``/``policy``/
``hooks`` inherited from the parent config) so the dispatchers — which resolve
their config by walking up from the invocation cwd — read child-correct
settings, and the commit-identity gate can union this child's roster with the
meta roster (parent ∪ child).

Stdlib only. Used by ``bootstrap.py`` for both the meta install (lay out each
selected child) and the standalone child install (``project.model: child``).
"""

from __future__ import annotations

import json
from pathlib import Path

#: Events an ``infra``-flavor child wires (matcher -> event); everything else
#: (SessionStart, file-edit matchers) is product-only.
_INFRA_EVENTS = ("PreToolUse", "PostToolUse")
_INFRA_MATCHER = "Bash"

_PROJECT_DIR_PREFIX = "$CLAUDE_PROJECT_DIR/.claude/"


def normalize_rel(path: str) -> list[str]:
    """Split a config-supplied relative path into clean posix parts."""
    return [p for p in path.replace("\\", "/").split("/") if p not in ("", ".")]


def parent_rel_for_child(child_rel_path: str) -> str:
    """Traversal from a child (at ``child_rel_path`` under the meta root) back up
    to the meta root: ``api`` -> ``..``; ``services/api`` -> ``../..``."""
    depth = len(normalize_rel(child_rel_path))
    return "/".join([".."] * depth) if depth else "."


def _rewrite_command(command: str, rel: str) -> str:
    """Re-anchor a template hook command at the parent: the child's
    ``$CLAUDE_PROJECT_DIR`` plus the relative traversal ``rel``."""
    return command.replace(_PROJECT_DIR_PREFIX, f"$CLAUDE_PROJECT_DIR/{rel}/.claude/")


def _rewrite_permission(rule: str, rel: str) -> str:
    """Point hook/lib permission rules at the parent's assets; child-local
    ``.claude`` rules (team files, settings) are left alone."""
    if ".claude/hooks" in rule or ".claude/lib" in rule:
        return rule.replace(".claude/hooks", f"{rel}/.claude/hooks").replace(
            ".claude/lib", f"{rel}/.claude/lib"
        )
    return rule


def build_child_settings(template: dict, rel: str, flavor: str) -> dict:
    """Derive a child settings template (parent-relative, flavor-filtered) from
    the shipped ``settings.template.json`` dict. Pure — returns a new dict."""
    out: dict = json.loads(json.dumps(template))  # deep copy

    hooks = out.get("hooks", {})
    if flavor == "infra":
        hooks = {
            event: [b for b in blocks if b.get("matcher") == _INFRA_MATCHER]
            for event, blocks in hooks.items()
            if event in _INFRA_EVENTS
        }
        hooks = {event: blocks for event, blocks in hooks.items() if blocks}
    for blocks in hooks.values():
        for block in blocks:
            for hook in block.get("hooks", []):
                if "command" in hook:
                    hook["command"] = _rewrite_command(hook["command"], rel)
    out["hooks"] = hooks

    perms = out.get("permissions")
    if isinstance(perms, dict):
        for key, rules in perms.items():
            if isinstance(rules, list):
                perms[key] = [
                    _rewrite_permission(r, rel) if isinstance(r, str) else r for r in rules
                ]
    return out


def child_runtime_config(parent_cfg: dict, name: str, rel: str, flavor: str) -> dict:
    """Build a child ``framework.config.json``: first-class ``model: child`` with
    the portable parent pointer, inheriting the parent's shared sections."""
    cfg: dict = {
        "version": 1,
        "project": {"name": name, "model": "child", "parent": rel, "flavor": flavor},
    }
    for section in ("scm", "identity", "policy", "hooks"):
        value = parent_cfg.get(section)
        if isinstance(value, dict):
            cfg[section] = json.loads(json.dumps(value))  # deep copy
    return cfg


def parent_install_error(parent_root: Path) -> str | None:
    """Human-readable reason the parent cannot serve children, or None if it can."""
    if not (parent_root / ".claude" / "framework.config.json").is_file():
        return (
            f"parent repo at {parent_root} does not have the framework installed "
            "(missing .claude/framework.config.json). Bootstrap the parent meta-repo "
            "first, then re-run this child install."
        )
    if not (parent_root / ".claude" / "hooks" / "dispatcher.py").is_file():
        return (
            f"parent repo at {parent_root} has a framework config but no installed "
            "hooks (missing .claude/hooks/dispatcher.py). Re-run the framework "
            "bootstrap at the parent, then re-run this child install."
        )
    return None


# ---------------------------------------------------------------- child CLAUDE.md

_CLAUDE_MD_TEMPLATE = """\
# CLAUDE.md

## Team Workflow — child repo of `{meta_name}`

This repository is a **{flavor} child** in a meta-and-children project. The
parent meta-repo lives at `{rel}` (relative to this repo's root) and holds the
single installed copy of the framework: hooks, libs, charter, trust matrix,
and feedback log.

- **No hook code lives here.** `.claude/settings.json` invokes the parent's
  dispatchers via portable `$CLAUDE_PROJECT_DIR/{rel}/.claude/hooks/...`
  commands — never machine-absolute paths.
- **Charter & rules:** `{rel}/.claude/team/charter/` (at the meta-repo)
- **This repo's roster:** `.claude/team/roster/` (one file per member);
  allowlist at `.claude/team/roster.json`. The commit-identity gate accepts
  this roster PLUS the meta roster (parent ∪ child union), so org leads can
  commit here but another child's engineers cannot.
{composition}
### Key Rules

- **Commit identity:** each team member commits using per-commit
  `-c user.name="..." -c user.email="..."` flags with two `Co-Authored-By`
  trailers (team member + Claude) — **never** set global/repo git config.
- **Worktrees** are the preferred isolation method for all code-writing agents.
- Cross-repo coordination (waves, releases, trust/feedback) happens at the
  meta-repo — this file covers only work scoped to this child.
"""


def child_claude_md(
    *, meta_name: str, rel: str, flavor: str, members: list[tuple[str, str, str]]
) -> str:
    """Render the child CLAUDE.md (team section only). ``members`` rows are
    ``(role, level, name)``; an empty list omits the composition table."""
    composition = ""
    if members:
        rows = "\n".join(f"| {role} | {level} | {name} |" for role, level, name in members)
        composition = (
            "\n### Team Composition\n\n"
            "| Role | Level | Name |\n|------|-------|------|\n" + rows + "\n"
        )
    return _CLAUDE_MD_TEMPLATE.format(
        meta_name=meta_name, rel=rel, flavor=flavor, composition=composition
    )


def next_backup_path(path: Path) -> Path:
    """Non-clobbering backup path: ``<name>.bak``, else ``<name>.bak.1``, … —
    the same pattern the ``2real-team`` CLI uses for its root CLAUDE.md."""
    backup = path.with_name(path.name + ".bak")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.bak.{counter}")
        counter += 1
    return backup


def write_child_claude_md(child_root: Path, content: str, *, dry_run: bool) -> str:
    """Write the child CLAUDE.md with backup-on-conflict. Idempotent: identical
    content is a no-op; different pre-existing content is preserved as a .bak."""
    dest = child_root / "CLAUDE.md"
    if dest.exists():
        try:
            existing = dest.read_text(encoding="utf-8")
        except OSError:
            existing = None
        if existing == content:
            return "up to date"
        backup = next_backup_path(dest)
        if dry_run:
            return f"would write (existing would be preserved as {backup.name})"
        dest.rename(backup)
        dest.write_text(content, encoding="utf-8")
        return f"written (existing preserved as {backup.name})"
    if dry_run:
        return "would write"
    child_root.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return "written"
