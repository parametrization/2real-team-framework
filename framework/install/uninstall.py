#!/usr/bin/env python3
"""Reverse a framework install — restore a repo to byte-identical pre-install state (#142/#222).

The counterpart to ``bootstrap.py``: where the bootstrapper lays a deterministic, idempotent
install, this tears exactly that install back out. The #105 harness's manifest-driven uninstall
leg (``framework/harness/teardown.py``) is the reference for "complete + reversible"; this is the
user-facing PRODUCT command that leg deferred (``# No product uninstall exists (deferred #142)``).

What a correct install writes (and this reverses)
=================================================
* The ``.claude/**`` install set — enumerated by the SAME golden manifest the harness checks
  (``manifest.expected_install_set``): the config trio, hooks/lib/skills assets, rendered charter,
  team org-artifacts. Plus the data-driven persona cards under ``.claude/team/roster/`` the
  manifest declines to enumerate (removed by directory sweep — that dir is fully framework-owned).
* Out-of-``.claude`` framework artifacts: the generated ontology (seed overlay + structural index),
  the ``.gitignore`` ledger-policy managed block (#187), and the ``.git/hooks/pre-push`` hook.

Two dispositions, both round-trip-provable
==========================================
The bootstrapper's consent flow (#108, ``repo_space``) resolves a pre-existing repo's Claude
assets to one of two dispositions; uninstall reverses each to a byte-identical pre-install state:

* **fresh** (no pre-existing assets) — surgical removal of the enumerated framework-owned set
  returns the repo to its pre-install tree (the install's own files, gone).
* **archive** (existing assets consented-archived to ``.claude-backups/<UTC>/``) — the archived
  originals are MOVED back via ``repo_space.restore_assets``, restoring the pre-install ``.claude/``
  + ``CLAUDE.md`` byte-for-byte, and the emptied backup container is pruned.

The **amend** disposition (existing assets kept in place, deliberately NOT snapshotted by the
installer) is inherently non-recoverable byte-for-byte — so uninstall does the honest thing: it
attributes every removal to the framework and touches nothing else. ``settings.json`` and
``.gitignore`` are UN-MERGED (only the hook wiring + permission rules / the managed block the
installer added are pruned), and the enumerated ``.claude/**`` set is removed only where the
on-disk bytes still MATCH what the framework produces (:func:`_derivable_asset_bytes`) — a
consumer's pre-existing file the installer's skip-if-exists kept at a framework path (and never
archived) has diverging bytes and is PRESERVED, not deleted. This is the same framework-provenance
guard every sibling reverser uses (``remove_ontology``/``remove_pre_push``), and it is what makes
"remove EXACTLY the install set, nothing else" true for the amend disposition too (#227 fix).

Idempotent + fail-safe
======================
A non-installed repo is a clean no-op (``not-installed`` status, exit 0). Re-running after a
successful uninstall sees no ``framework.config.json`` and does nothing. ``--dry-run`` writes
nothing; ``--non-interactive`` never prompts (the automation contract); a destructive run on a
non-TTY without ``--non-interactive`` REFUSES rather than acting without consent.

Stdlib only (no deps), so it runs anywhere ``python3`` does. Reuses the installer's own iterators,
manifest, and ``repo_space`` restore so the teardown set cannot drift from what the install wrote.

Usage
=====
  python3 uninstall.py /path/to/repo                 # interactive confirm, then remove
  python3 uninstall.py /path/to/repo --non-interactive
  python3 uninstall.py /path/to/repo --dry-run       # preview; write nothing

Exit codes: 0 ok / dry-run / not-installed, 1 on a refused/aborted destructive run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap  # noqa: E402  (sibling; reuse its iterators/constants so we can't drift)
import install_config  # noqa: E402  (sibling; resolved-config accessors)
import manifest  # noqa: E402  (sibling; the golden install-set derivation)
import repo_space  # noqa: E402  (sibling; consented archive restore, #108)

_CLAUDE = ".claude"
_SETTINGS_REL = f"{_CLAUDE}/settings.json"


# ---------------------------------------------------------------- install detection / config


def is_installed(target: Path) -> bool:
    """True iff the framework is installed here (its canonical marker file is present)."""
    return (target / _CLAUDE / "framework.config.json").is_file()


def load_runtime_config(target: Path) -> dict:
    """Read ``.claude/framework.config.json`` (the runtime config). Fail-open to ``{}``."""
    try:
        cfg = json.loads((target / _CLAUDE / "framework.config.json").read_text(encoding="utf-8"))
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def load_install_snapshot(target: Path) -> dict:
    """Return the RESOLVED install-config dict the install recorded — fallback: shipped defaults.

    ``.claude/install.config.json`` is the installer's canonical record of the install-time
    decisions (``project.model``, ``team.enabled``, ``ontology.enabled``, children). A
    missing/corrupt snapshot degrades to the shipped defaults so an old or hand-tampered install
    still tears down sanely; where possible ``project.model`` is backfilled from the runtime
    ``framework.config.json`` so the manifest branch still matches what was actually laid down.
    """
    snap_path = target / _CLAUDE / install_config.SNAPSHOT_REL
    try:
        cfg = json.loads(snap_path.read_text(encoding="utf-8"))
        if isinstance(cfg, dict):
            return cfg
    except (OSError, ValueError):
        pass
    cfg, _ = install_config.load()  # builtin < shipped default YAML
    run = load_runtime_config(target)
    model = (run.get("project") or {}).get("model")
    if model in install_config.INSTALL_MODEL_MAP:
        install_config.set_key(cfg, "project.model", install_config.INSTALL_MODEL_MAP[model])
    team = run.get("identity")
    if isinstance(team, dict) and team.get("enforce") is False:
        # A no-team install left identity enforcement off; reflect that so we don't expect
        # team org-artifacts that were never written.
        install_config.set_key(cfg, "team.enabled", False)
    return cfg


def _template() -> dict:
    """The shipped ``settings.template.json`` — the source of the framework's own hook wiring."""
    return json.loads((bootstrap._ASSETS / "settings.template.json").read_text(encoding="utf-8"))


def _framework_hook_ids(template: dict) -> set[str]:
    """The stable script-id set of every hook the framework wires (inverts ``merge_settings``)."""
    ids: set[str] = set()
    for blocks in (template.get("hooks") or {}).values():
        for block in blocks:
            for h in block.get("hooks", []):
                ids.add(bootstrap._script_id(h.get("command", "")))
    return ids


# ---------------------------------------------------------------- settings.json un-merge


def unmerge_settings(target_claude: Path, template: dict, *, dry_run: bool) -> str:
    """Invert ``bootstrap.merge_settings``: strip the framework wiring, preserve user settings.

    Removes every hook entry whose script-id is a framework dispatcher and every framework
    ``permissions.allow`` rule, dropping blocks/events/keys that become empty. If nothing but the
    framework's own content remains (a fresh install wrote settings.json from ``{}``), the file is
    removed outright — that is what makes the fresh round-trip byte-identical. Otherwise the pruned
    document (the user's own hooks/rules) is written back. A non-framework or malformed file is
    left untouched. Returns a one-line status.
    """
    dest = target_claude / "settings.json"
    if not dest.is_file():
        return "absent"
    try:
        doc = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "left untouched (not valid JSON)"
    if not isinstance(doc, dict):
        return "left untouched (unexpected shape)"

    fw_ids = _framework_hook_ids(template)
    changed = False

    hooks = doc.get("hooks")
    if isinstance(hooks, dict):
        for event in list(hooks.keys()):
            blocks = hooks.get(event)
            if not isinstance(blocks, list):
                continue
            kept_blocks = []
            for block in blocks:
                bl_hooks = block.get("hooks") if isinstance(block, dict) else None
                if isinstance(bl_hooks, list):
                    remaining = [
                        h for h in bl_hooks
                        if bootstrap._script_id(h.get("command", "")) not in fw_ids
                    ]
                    if len(remaining) != len(bl_hooks):
                        changed = True
                    block["hooks"] = remaining
                    if not remaining:
                        continue  # block held only framework hooks — drop it
                kept_blocks.append(block)
            if kept_blocks:
                hooks[event] = kept_blocks
            elif blocks:  # every block was framework-owned — drop the event
                del hooks[event]
                changed = True
        if not hooks:
            doc.pop("hooks", None)

    fw_rules = set((template.get("permissions") or {}).get("allow") or [])
    perms = doc.get("permissions")
    if isinstance(perms, dict):
        allow = perms.get("allow")
        if isinstance(allow, list):
            pruned = [r for r in allow if r not in fw_rules]
            if len(pruned) != len(allow):
                changed = True
            if pruned:
                perms["allow"] = pruned
            else:
                perms.pop("allow", None)
        if not perms:
            doc.pop("permissions", None)

    if not doc:
        if dry_run:
            return "would remove (fully framework-owned)"
        dest.unlink()
        return "removed (fully framework-owned)"
    if not changed:
        return "no framework wiring found (left untouched)"
    if dry_run:
        return "would prune framework wiring (user settings preserved)"
    dest.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return "pruned framework wiring (user settings preserved)"


# ---------------------------------------------------------------- .gitignore un-append


def undo_gitignore(target: Path, entries: tuple[str, ...], *, dry_run: bool) -> str:
    """Invert ``bootstrap.ensure_gitignore_entries``: drop the installer-managed block.

    Removes the stable header line and the framework entries, then collapses any trailing blank
    left behind. If nothing survives (the installer CREATED the file), the ``.gitignore`` is
    removed — making a fresh round-trip byte-identical. Otherwise the operator's own content is
    written back. A file with no managed block is left untouched.
    """
    gi = target / ".gitignore"
    if not gi.is_file():
        return "absent"
    lines = gi.read_text(encoding="utf-8").splitlines()
    drop = set(entries) | {bootstrap._GITIGNORE_HEADER}
    kept = [ln for ln in lines if ln not in drop]
    if len(kept) == len(lines):
        return "no managed block found"
    while kept and kept[-1] == "":
        kept.pop()
    if not kept:
        if dry_run:
            return "would remove (framework-created)"
        gi.unlink()
        return "removed (framework-created)"
    if dry_run:
        return "would strip managed block"
    gi.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return "stripped managed block"


# ---------------------------------------------------------------- pre-push hook


def remove_pre_push(target: Path, *, dry_run: bool) -> str:
    """Remove the framework ``pre-push`` hook and restore any backup the install preserved.

    Only a hook whose body is one the installer writes (``noop``/``enforce``) is removed — a hook
    the operator later replaced is left untouched. A ``pre-push.bak`` the install left when it
    displaced a pre-existing hook is moved back, restoring the operator's original.
    """
    hooks_dir, _note = bootstrap._git_hooks_dir(target)
    if hooks_dir is None:
        return "skipped (no git hooks dir)"
    dest = hooks_dir / "pre-push"
    parts: list[str] = []
    if dest.is_file():
        try:
            body = dest.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            body = None
        if body in (bootstrap._NOOP_PRE_PUSH, bootstrap._ENFORCE_PRE_PUSH):
            if dry_run:
                parts.append("would remove framework pre-push")
            else:
                dest.unlink()
                parts.append("removed framework pre-push")
        else:
            return "left untouched (non-framework pre-push)"
    bak = dest.with_name(dest.name + ".bak")
    if bak.exists():
        if dry_run:
            parts.append("would restore pre-push.bak")
        else:
            if dest.exists():
                dest.unlink()
            bak.replace(dest)
            parts.append("restored pre-push.bak")
    return "; ".join(parts) if parts else "absent"


# ---------------------------------------------------------------- ontology


def remove_ontology(target: Path, ontology_rel: str, *, dry_run: bool) -> list[str]:
    """Remove the framework-laid ontology: the generated structural index + the UNMODIFIED seed.

    The generated ``structural/**`` index is always the installer's own output → removed. Seed
    overlay files are removed only when still byte-identical to the shipped template — a
    hand-curated overlay the operator has since edited is preserved (mirrors the skip-if-exists
    install semantics). Returns the repo-root-relative paths removed.
    """
    base = target / ontology_rel
    if not base.is_dir():
        return []
    owned: set[Path] = set()
    for rel, src in bootstrap._iter_overlay_files():
        dest = base / rel
        try:
            if dest.is_file() and dest.read_bytes() == src.read_bytes():
                owned.add(dest)
        except OSError:
            pass
    structural = base / "structural"
    if structural.is_dir():
        for p in structural.rglob("*"):
            if p.is_file():
                owned.add(p)
    removed: list[str] = []
    for p in sorted(owned):
        if p.is_file():
            if not dry_run:
                p.unlink()
            removed.append(p.relative_to(target).as_posix())
    return removed


# ---------------------------------------------------------------- .claude tree removal


def _derivable_asset_bytes(run_cfg: dict) -> dict[str, bytes]:
    """The exact bytes the framework produces for every BYTE-DERIVABLE manifest path.

    Built from the SAME iterators/rendering the installer copies with, so it cannot drift from
    what a correct install writes:

    * ``hooks/`` + ``lib/`` + ``skills/`` — static assets copied verbatim (``shutil.copy2``), so
      the shipped source bytes are the framework's fingerprint.
    * ``team/charter/*.md`` — rendered from the modular template with the ``{{key}}`` substitution
      (reproduced here from the RUNTIME config the install recorded), so an unmodified rendered
      module reproduces byte-for-byte.

    Paths NOT in this map (the config trio, ``.charter-manifest.json``, the team org-artifacts,
    and the data-driven persona cards) are framework-GENERATED output whose names are proprietary
    to the framework — a foreign repo being amended never carries them — so they are treated like
    ``remove_ontology`` treats the generated ``structural/**`` index: framework-owned by origin.
    """
    out: dict[str, bytes] = {}
    for src in bootstrap._iter_asset_files("hooks"):
        out[f"{_CLAUDE}/hooks/{src.name}"] = src.read_bytes()
    for rel, src in bootstrap._iter_lib_files():
        out[f"{_CLAUDE}/lib/{rel.as_posix()}"] = src.read_bytes()
    for rel, src in bootstrap._iter_skill_files():
        out[f"{_CLAUDE}/skills/{rel.as_posix()}"] = src.read_bytes()
    context = bootstrap._charter_context(run_cfg)
    for src in bootstrap._iter_charter_files():
        text = src.read_text(encoding="utf-8")
        for key, value in context.items():
            text = text.replace("{{" + key + "}}", value)
        out[f"{_CLAUDE}/team/charter/{src.name}"] = text.encode("utf-8")
    return out


def _surgical_claude_removal(
    target: Path, inst_cfg: dict, run_cfg: dict, *, dry_run: bool
) -> tuple[list[str], list[str]]:
    """Remove the framework-owned ``.claude/**`` set + persona cards, GATED on provenance.

    The candidate set is the golden manifest (``manifest.expected_install_set``) minus
    ``settings.json`` (un-merged, not wholesale-deleted), plus every file under
    ``.claude/team/roster/`` (the framework-owned persona-card dir the manifest declines to
    enumerate). But a manifest path is a NECESSARY, not sufficient, condition for removal:
    for a byte-derivable path (:func:`_derivable_asset_bytes`) the on-disk bytes must still match
    what the framework produces. In the *amend* disposition the installer's skip-if-exists keeps a
    consumer's pre-existing file at a framework path (never archived), so deleting it by manifest
    path alone would destroy user data — the exact asymmetry the sibling reversers already avoid
    (``remove_ontology``/``remove_pre_push``/``unmerge_settings``). A path whose bytes diverge is
    PRESERVED (user-modified or foreign); every sibling reverser guards the same way.

    Returns ``(removed, preserved)`` — both repo-root-relative POSIX path lists.
    """
    derivable = _derivable_asset_bytes(run_cfg)
    removed: list[str] = []
    preserved: list[str] = []

    def _consider(rel: str, p: Path) -> None:
        if rel in derivable:
            try:
                on_disk = p.read_bytes()
            except OSError:
                on_disk = None
            if on_disk != derivable[rel]:
                preserved.append(rel)  # user-modified / foreign bytes — never delete
                return
        if not dry_run:
            p.unlink()
        removed.append(rel)

    for rel in sorted(manifest.expected_install_set(inst_cfg)):
        if rel == _SETTINGS_REL:
            continue  # handled by unmerge_settings
        p = target / rel
        if p.is_file():
            _consider(rel, p)
    roster = target / _CLAUDE / "team" / "roster"
    if roster.is_dir():
        for p in sorted(roster.rglob("*")):
            if p.is_file():
                _consider(p.relative_to(target).as_posix(), p)
    return removed, preserved


def _prune_empty_dirs(*roots: Path) -> None:
    """Best-effort removal of now-empty framework-owned dirs (deepest-first, then the root)."""
    for root in roots:
        if not root.is_dir():
            continue
        for d in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if d.is_dir():
                try:
                    d.rmdir()
                except OSError:
                    pass
        try:
            root.rmdir()
        except OSError:
            pass


# ---------------------------------------------------------------- orchestrator


def uninstall(target: Path | str, *, dry_run: bool = False) -> dict:
    """Reverse a framework install. Returns a structured report (no printing).

    See the module docstring for the full contract. Removes out-of-``.claude`` artifacts
    uniformly, then either restores a consented archive (existing-repo disposition) or surgically
    removes the enumerated ``.claude/**`` set (fresh disposition), then prunes emptied containers.
    """
    target = Path(target).resolve()
    report: dict = {
        "target": str(target), "status": None,
        "removed": [], "restored": [], "preserved": [], "notes": [],
    }
    if not is_installed(target):
        report["status"] = "not-installed"
        report["notes"].append("no .claude/framework.config.json here — nothing to uninstall.")
        return report

    inst_cfg = load_install_snapshot(target)
    run_cfg = load_runtime_config(target)
    template = _template()
    paths = run_cfg.get("paths") or {}
    ontology_rel = paths.get("ontology") or "ontology"
    ledger_rel = paths.get("generic_prompt_ledger") or f"{_CLAUDE}/generic_prompt_ledger.json"
    ontology_enabled = bool(install_config.get_key(inst_cfg, "ontology.enabled", True))

    # 1. Out-of-.claude framework artifacts — uniform across every disposition (they sit on top of
    #    the existing repo, so the archive path never captured them either).
    if ontology_enabled:
        report["removed"] += remove_ontology(target, ontology_rel, dry_run=dry_run)
    report["notes"].append(f"gitignore: {undo_gitignore(target, (ledger_rel,), dry_run=dry_run)}")
    report["notes"].append(f"pre-push: {remove_pre_push(target, dry_run=dry_run)}")

    # 2. The .claude tree: restore a consented pre-install archive if one exists (#108), else
    #    surgically remove the enumerated install set + un-merge settings.json.
    archive_dir = repo_space.find_latest_archive(target)
    if archive_dir is not None:
        if dry_run:
            report["notes"].append(f"would restore archived pre-install assets from {archive_dir.name}")
        else:
            res = repo_space.restore_assets(target, archive_dir, overwrite=True)
            report["restored"] += res.restored
            if res.conflicts:
                report["notes"].append(f"archive conflicts (left in archive): {', '.join(res.conflicts)}")
            else:
                # Clean restore — consume the now-spent manifest so the emptied backup container
                # prunes away (repo_space deliberately leaves it; #149 finding 4). Only when there
                # is nothing left to recover from it.
                (archive_dir / repo_space.MANIFEST_NAME).unlink(missing_ok=True)
            report["notes"].append(f"restored pre-install assets from {archive_dir.name}")
        report["status"] = "restored"
    else:
        removed, preserved = _surgical_claude_removal(
            target, inst_cfg, run_cfg, dry_run=dry_run
        )
        report["removed"] += removed
        report["preserved"].extend(preserved)
        if preserved:
            report["notes"].append(
                f"preserved {len(preserved)} user-modified path(s) at framework locations "
                f"(bytes diverged — never framework-owned): {', '.join(preserved)}"
            )
        report["notes"].append(
            f"settings.json: {unmerge_settings(target / _CLAUDE, template, dry_run=dry_run)}"
        )
        report["status"] = "removed"

    # 3. Prune emptied framework-owned containers so zero residue is left behind.
    if not dry_run:
        _prune_empty_dirs(
            target / repo_space.BACKUPS_DIRNAME, target / ontology_rel, target / _CLAUDE
        )
    return report


# ---------------------------------------------------------------- CLI


def _confirm(target: Path, *, non_interactive: bool, dry_run: bool) -> bool:
    """Consent gate for the destructive run. Fail-safe: never act without explicit go-ahead.

    ``--dry-run`` writes nothing so it always proceeds; ``--non-interactive`` is the automation
    contract (proceed, no prompt); an interactive TTY is asked ``[y/N]``; a non-TTY without
    ``--non-interactive`` REFUSES rather than tearing an install out unattended.
    """
    if dry_run or non_interactive:
        return True
    if not sys.stdin.isatty():
        print(
            "refusing a destructive uninstall without a TTY — pass --non-interactive to proceed.",
            file=sys.stderr,
        )
        return False
    ans = input(f"Uninstall the 2real framework from {target}? [y/N]: ").strip().lower()
    return ans in ("y", "yes")


def _print_report(report: dict, *, dry_run: bool) -> None:
    verb = "would remove" if dry_run else "removed"
    print("\n-- plan --" if dry_run else "\n-- result --")
    print(f"{verb}:       {len(report['removed'])} file(s)")
    if report.get("preserved"):
        print(f"preserved:     {len(report['preserved'])} user-modified path(s) at framework locations")
    if report["restored"]:
        print(f"restored:      {', '.join(report['restored'])} (pre-install backup)")
    for note in report["notes"]:
        print(f"note:          {note}")
    if dry_run:
        print("\n(dry-run — nothing was changed)")
    else:
        print("\nDone. Restart Claude Code so the removed hooks unload.")


def cli_teardown(target: Path | str, *, dry_run: bool, non_interactive: bool) -> int:
    """The product entry (shared by ``uninstall.py`` and ``bootstrap.py --teardown``)."""
    target = Path(target).resolve()
    print(f"== 2real framework uninstall ({'DRY-RUN' if dry_run else 'REMOVE'}) ==")
    print(f"target repo:   {target}")
    if not is_installed(target):
        print("not installed here (no .claude/framework.config.json) — nothing to do.")
        return 0
    if not _confirm(target, non_interactive=non_interactive, dry_run=dry_run):
        print("aborted — nothing changed.", file=sys.stderr)
        return 1
    report = uninstall(target, dry_run=dry_run)
    _print_report(report, dry_run=dry_run)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Uninstall the 2real framework — restore a repo to pre-install state (#142).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("target", nargs="?", default=".", help="Target repo root (default: cwd)")
    ap.add_argument("--dry-run", action="store_true", help="Print the plan; write nothing")
    ap.add_argument(
        "--non-interactive", action="store_true",
        help="Never prompt (the automation contract); proceed without the [y/N] confirmation",
    )
    args = ap.parse_args(argv)
    return cli_teardown(
        Path(args.target), dry_run=args.dry_run, non_interactive=args.non_interactive
    )


if __name__ == "__main__":
    raise SystemExit(main())
