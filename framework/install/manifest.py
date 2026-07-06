#!/usr/bin/env python3
"""Golden install manifest — the single source of truth for the *expected* install set.

Why this exists
===============
The install-quality harness (#105) and the ``files_installed_complete`` /
``no_unexpected_files`` metrics (#103/#104) need to know **exactly** which files a correct
install produces, so drift between "what the installer writes" and "what the harness checks"
is caught mechanically. Historically that expectation lived as prose literals in
``INSTALL_QUALITY_HARNESS.md`` ("23 hook modules", "14 skills") — which silently rot when the
asset set changes. This module replaces those literals with ONE derived source.

The expected set is **derived from** ``framework/assets/**`` + the resolved install config —
never a hand-listed literal. It reuses ``bootstrap.py``'s own asset iterators, so the manifest
cannot disagree with what the installer actually copies. The coupling test
``framework/tests/test_golden_manifest.py`` performs a real ``bootstrap.py`` install into a
tmp dir and asserts the produced ``.claude/**`` tree equals this manifest — that test is what
keeps the manifest honest.

CONTRACT (stable — #105 codes against this)
===========================================
    expected_install_set(config: dict) -> set[str]

* ``config`` is a RESOLVED install config dict (``install_config`` shape — i.e. the exact
  content the installer records at ``<target>/.claude/install.config.json``). Read
  ``project.model`` and ``team.enabled`` from it; unknown/missing keys fall back to the
  shipped defaults (``standalone`` / team enabled).
* Returns a ``set[str]`` of **repo-root-relative POSIX paths, all under ``.claude/``**, that a
  correct install of that config produces into the *target's own* ``.claude/`` tree. Meta-mode
  per-child files (which land under ``<child>/.claude/``) are out of scope — they are a
  different repo's tree.
* The set respects install mode:
    - ``project.model == "child"`` → only ``settings.json``, ``framework.config.json``,
      ``install.config.json`` (+ ``team/roster.json`` when ``team.enabled``). A child installs
      NO hooks/lib/skills/charter of its own — it invokes the parent's.
    - ``standalone`` / ``meta`` → the full hooks + lib + skills + charter set, plus the config
      trio, plus the team org-artifacts (``roster.json``, ``trust_matrix.md``,
      ``feedback_log.md``) when ``team.enabled``.

BOUNDARY — what the manifest deliberately does NOT enumerate
============================================================
* **Persona cards** under ``.claude/team/roster/`` (``ROSTER_CARDS_PREFIX``). Their names and
  count are DATA-DRIVEN (repo introspection + ``team.size``), not a pure function of
  assets+config, so they cannot be enumerated deterministically. A consumer asserts the roster
  directory is non-empty in team mode separately (the coupling test does exactly this). Every
  OTHER installed ``.claude/**`` path IS enumerated.
* Files **outside ``.claude/``**: the seed ontology overlay + generated structural index
  (``ontology/**``), the root ``CLAUDE.md``, and the resolved ``.git/hooks/pre-push``. Those
  belong to the harness's broader ``files_installed_complete`` namespace, but this manifest is
  scoped to ``.claude/**`` by contract.

If the shape of ``expected_install_set`` ever has to change, say so loudly — #105 codes against
this exact signature.

Regenerate / check the checked-in snapshot
==========================================
    python3 framework/install/manifest.py            # regenerate golden-manifest.json
    python3 framework/install/manifest.py --check     # verify it is in sync (exit 1 on drift)

Stdlib only; no deps.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap  # noqa: E402  (sibling; reuse its asset iterators so we can't drift)
import install_config  # noqa: E402  (sibling; resolved-config accessors)

# framework/install/manifest.py -> framework/install/golden-manifest.json
GOLDEN_PATH = Path(__file__).resolve().parent / "golden-manifest.json"

#: Prefix (repo-root-relative, POSIX) of the data-driven persona-card files that the manifest
#: intentionally does NOT enumerate. Consumers assert this directory is non-empty in team mode.
ROSTER_CARDS_PREFIX = ".claude/team/roster/"

_CLAUDE = ".claude"


def _p(*parts: str) -> str:
    """Repo-root-relative POSIX path under ``.claude/``."""
    return "/".join((_CLAUDE, *parts))


def _asset_files() -> set[str]:
    """Hooks + lib + skills paths, derived from the SAME iterators bootstrap copies with."""
    files: set[str] = set()
    for src in bootstrap._iter_asset_files("hooks"):
        files.add(_p("hooks", src.name))
    for rel, _src in bootstrap._iter_lib_files():
        files.add(_p("lib", rel.as_posix()))
    for rel, _src in bootstrap._iter_skill_files():
        files.add(_p("skills", rel.as_posix()))
    return files


def _charter_files() -> set[str]:
    """Rendered charter modules + the render manifest (bootstrap lays these unconditionally)."""
    files = {_p("team", "charter", src.name) for src in bootstrap._iter_charter_files()}
    files.add(_p("team", ".charter-manifest.json"))
    return files


def expected_install_set(config: dict) -> set[str]:
    """Return the expected ``.claude/**`` relpaths a correct install of ``config`` produces.

    See the module docstring for the full contract. ``config`` is a resolved install-config
    dict; ``project.model`` and ``team.enabled`` drive the branches.
    """
    model = install_config.get_key(config, "project.model", "standalone")
    team_enabled = bool(install_config.get_key(config, "team.enabled", True))

    # The config trio every install mode records into the target's own .claude/.
    files: set[str] = {
        _p("framework.config.json"),
        _p("settings.json"),
        _p(install_config.SNAPSHOT_REL),  # install.config.json (resolved snapshot)
    }

    if model == "child":
        # A child installs no hooks/lib/skills/charter of its own (it invokes the parent's);
        # trust/feedback are org-wide and live at the parent meta-repo.
        if team_enabled:
            files.add(_p("team", "roster.json"))
        return files

    # standalone / meta (the parent's OWN .claude/** — per-child trees are separate repos).
    files |= _asset_files()
    files |= _charter_files()
    if team_enabled:
        files.add(_p("team", "roster.json"))
        files.add(_p("team", "trust_matrix.md"))
        files.add(_p("team", "feedback_log.md"))
    return files


def manifest_document(config: dict) -> dict:
    """Reviewable JSON document wrapping :func:`expected_install_set` for a given config."""
    return {
        "schema_version": 1,
        "note": (
            "Generated by framework/install/manifest.py -- DO NOT hand-edit. Regenerate with "
            "`python3 framework/install/manifest.py`. Persona cards under "
            f"'{ROSTER_CARDS_PREFIX}' are data-driven and intentionally not enumerated."
        ),
        "config": {
            "project.model": install_config.get_key(config, "project.model", "standalone"),
            "team.enabled": bool(install_config.get_key(config, "team.enabled", True)),
        },
        "roster_cards_prefix": ROSTER_CARDS_PREFIX,
        "files": sorted(expected_install_set(config)),
    }


def default_document() -> dict:
    """The manifest document for the shipped default install config (standalone + team)."""
    config, _user_keys = install_config.load()  # builtin < shipped default YAML
    return manifest_document(config)


def _serialize(doc: dict) -> str:
    return json.dumps(doc, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate / check the golden install manifest for the default config.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="Verify golden-manifest.json matches the derived set; exit 1 on drift, write nothing.",
    )
    args = ap.parse_args(argv)
    doc = default_document()
    serialized = _serialize(doc)

    if args.check:
        current = GOLDEN_PATH.read_text(encoding="utf-8") if GOLDEN_PATH.is_file() else ""
        if current != serialized:
            print(
                "manifest: DRIFT — golden-manifest.json is stale vs the derived install set.\n"
                "Run: python3 framework/install/manifest.py",
                file=sys.stderr,
            )
            return 1
        print("manifest: golden-manifest.json is in sync with the derived install set.")
        return 0

    GOLDEN_PATH.write_text(serialized, encoding="utf-8")
    print(f"manifest: wrote {GOLDEN_PATH} ({len(doc['files'])} files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
