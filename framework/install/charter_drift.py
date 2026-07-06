#!/usr/bin/env python3
"""Charter-tree drift gate — closes the reinstall.py ``_MANAGED_TREES`` hole (#189).

Self-hosting rule (#116). ``reinstall.py`` dual-deploys ``framework/assets/skills/`` because
it is byte-mirrored: canonical == live, always. ``team/charter/**`` was deliberately excluded
from ``_MANAGED_TREES`` because it is NOT byte-mirrored — it is template-rendered (``{{key}}``
substitution driven by ``install_charter`` in ``bootstrap.py``, per-repo config values baked
in) — so a naive byte-diff against canonical would flag every ``{{placeholder}}`` as drift.
That gap let a canonical charter edit (new hook doc, a norm change) go out without a matching
runtime update, passing CI (#180 / #181).

This module closes it without fighting the template layer: it renders every canonical charter
module (``framework/assets/team/charter/*.md``) with THIS repo's OWN
``.claude/framework.config.json`` — the exact substitution ``install_charter`` would apply —
and asserts the rendered text is byte-identical to the live ``.claude/team/charter/*.md``
copy. Rendering both sides through the same substitution map before comparing means an
expected ``{{feature_branch_scheme}}`` -> value difference is never mistaken for drift; only
genuine content divergence (a canonical doc update not propagated, or a hand-edited runtime
copy) is reported.

Read-only by design (approach (a) from issue #189): this never writes. A reported drift is
fixed by re-rendering the affected module(s) from canonical for the current config (see
``install_charter`` in ``bootstrap.py``; a scoped one-off call with ``force=True`` re-renders
every module — mind that this also overwrites any deliberately hand-evolved module, so this
gate applies to THIS repo's own dual-deployed runtime copy, not to a downstream consumer's
charter, which the template layer's three-way ``--refresh-charter`` is designed to keep
hand-evolvable).

Usage
=====
  python3 framework/install/charter_drift.py           # report drift, write nothing
  python3 framework/install/charter_drift.py --check    # same check; exit 1 if any drift

Wired into CI the same way as ``reinstall.py`` / ``manifest.py``: not a standalone
``.github/workflows/`` step but a pytest gate
(``framework/tests/test_charter_drift.py::test_repo_charter_in_sync_with_canonical``) that
``plan()``-checks this repo and is already covered by the existing
``pytest framework/tests/ -v`` CI step.

Stdlib only; no deps.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap  # noqa: E402  (sibling; reuse the charter renderer so this can't drift)

# framework/install/charter_drift.py -> framework/
_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _FRAMEWORK_ROOT.parent
_DEFAULT_CLAUDE_ROOT = _REPO_ROOT / ".claude"


def _load_runtime_config(claude_root: Path) -> dict:
    """Read ``<claude_root>/framework.config.json``. Fail loud — an unreadable/missing
    runtime config means the check cannot mean anything (there is nothing to render
    against), unlike the fail-open manifest baseline in ``install_charter``."""
    path = claude_root / "framework.config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"ERROR: charter-drift: cannot read {path}: {e}")
    if not isinstance(data, dict):
        raise SystemExit(f"ERROR: charter-drift: {path} is not a JSON object")
    return data


def render_canonical_charter(cfg: dict) -> dict[str, str]:
    """Render every canonical charter module with ``cfg``'s ``{{key}}`` substitution map.

    Returns ``{module filename -> fully-substituted text}`` — exactly what a fresh
    ``install_charter`` write/refresh would put on disk for this config. Reuses
    ``bootstrap``'s own context builder + file iterator, so the render here cannot
    silently disagree with what the installer actually produces.
    """
    context = bootstrap._charter_context(cfg)
    rendered: dict[str, str] = {}
    for src in bootstrap._iter_charter_files():
        text = src.read_text(encoding="utf-8")
        for key, value in context.items():
            text = text.replace("{{" + key + "}}", value)
        rendered[src.name] = text
    return rendered


def plan(claude_root: Path = _DEFAULT_CLAUDE_ROOT, cfg: dict | None = None) -> list[str]:
    """Live ``.claude/team/charter/*.md`` paths that differ from the canonical render.

    ``cfg`` defaults to ``<claude_root>/framework.config.json`` (this repo's own runtime
    config when called with no arguments). Both sides are rendered/read as plain text
    before comparison, so an expected ``{{placeholder}}`` -> value substitution is never
    itself flagged — only genuine content drift (a canonical update not propagated, a
    missing module, or a hand-edited runtime copy) appears in the result.
    """
    if cfg is None:
        cfg = _load_runtime_config(claude_root)
    rendered = render_canonical_charter(cfg)
    charter_dir = claude_root / "team" / "charter"
    drift: list[str] = []
    for name in sorted(rendered):
        expected_text = rendered[name]
        dest = charter_dir / name
        rel = f".claude/team/charter/{name}"
        if not dest.is_file():
            drift.append(rel)
            continue
        try:
            actual_text = dest.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            drift.append(rel)
            continue
        if actual_text != expected_text:
            drift.append(rel)
    return drift


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Check the runtime team charter (.claude/team/charter/) for drift against "
            "the canonical template (framework/assets/team/charter/) rendered with this "
            "repo's own framework.config.json."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="Same check as the default action; kept for parity with reinstall.py/manifest.py "
             "--check. This tool never writes, so it always just checks.",
    )
    ap.add_argument(
        "--claude-root",
        metavar="PATH",
        help="Override the .claude/ root to check (default: this repo's own .claude/).",
    )
    args = ap.parse_args(argv)
    del args.check  # accepted for CLI-idiom parity only; behaviour never differs

    claude_root = Path(args.claude_root).resolve() if args.claude_root else _DEFAULT_CLAUDE_ROOT
    drift = plan(claude_root=claude_root)
    if drift:
        print(
            "charter-drift: DRIFT — these runtime charter modules differ from the canonical "
            f"template rendered with {claude_root}/framework.config.json:"
        )
        for d in drift:
            print(f"  {d}")
        print(
            "Fix: re-render the drifted module(s) from canonical for the current config "
            "(install_charter(..., force=True) in framework/install/bootstrap.py), then "
            "re-run this check."
        )
        return 1
    print(f"charter-drift: {claude_root}/team/charter/ matches canonical for this config.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
