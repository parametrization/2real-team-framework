"""B11 upgrade-over-live-install study (#109): archive + fresh + restore, byte-identical.

Dev tooling (NOT an installed asset; #116 dual-deploy does not apply). Exercises the #108
repo-level consent + archive + restore flow OVER a repo that ALREADY carries its own diverged
2real install, and proves the restore returns the managed Claude assets (``.claude/`` +
``CLAUDE.md``) byte-identical to their pre-existing state.

It is the archive/restore companion to the ``B11`` harness bucket. The bucket measures the
*amend-in-place* upgrade (bootstrap ``--expect existing`` merges over the live install); this
script measures the *archive-then-fresh-then-restore* disposition — the reversible path #108
adds — and captures the symmetric-diff proof of a byte-identical restore.

Read-only w.r.t. the live source: it reuses :func:`real_provision.provision_real` to clone the
source at a pinned SHA into scratch (``git clone --no-local`` + detached checkout) and asserts
the source ``{head, porcelain}`` is byte-unchanged across the run. It NEVER writes to the live
tree — all archive/fresh/restore happens on the throwaway clone, torn down at the end.

No hardcoded source path lives here (#155 item 2): the source/pin come from ``--source`` /
``--pin``, else a ``--real-config`` sidecar (see
``framework/tests/install_quality/real-config.botfarm.example.json``), else the ``B11`` entry
of :data:`real_provision.DEFAULT_REAL_FIXTURES`. Stdlib only.

    python3 -m framework.harness.botfarm_upgrade_study \
        --source /path/to/botfarm_inc --out study.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .real_provision import (
    RealFixtureSpec,
    provision_real,
    real_registry,
    resolve_pin,
    source_fingerprint,
)
from .snapshot import snapshot, symmetric_diff

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_BOOTSTRAP = _FRAMEWORK_ROOT / "install" / "bootstrap.py"
_INSTALL_DIR = _FRAMEWORK_ROOT / "install"

#: The managed Claude assets #108 archives/restores (mirror of repo_space.REPO_CLAUDE_ASSETS).
_MANAGED = (".claude", "CLAUDE.md")


def _load_repo_space():
    """Import ``framework/install/repo_space.py`` (its relative imports need the dir on path)."""
    if str(_INSTALL_DIR) not in sys.path:
        sys.path.insert(0, str(_INSTALL_DIR))
    import repo_space  # noqa: E402  (path-dependent import, by design)

    return repo_space


def _managed_scope(snap: dict) -> dict:
    """Restrict a full-tree snapshot to the #108-managed assets (``.claude/**`` + ``CLAUDE.md``)."""
    return {
        rel: h
        for rel, h in snap.items()
        if rel == "CLAUDE.md" or rel.startswith(".claude/")
    }


def _roster_members(root: Path) -> list[str]:
    p = root / ".claude" / "team" / "roster.json"
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return sorted(data) if isinstance(data, dict) else []


def _fresh_install(clone: Path) -> subprocess.CompletedProcess:
    """Lay a CLEAN install over the archived (now Claude-empty) repo.

    ``--expect any``: the repo still carries all of botfarm's source, so it classifies as
    EXISTING even with ``.claude`` archived away — ``any`` keeps the repo-state gate out of the
    way so the fresh write proceeds. Team ON so we can show the old roster is no longer loaded.
    """
    return subprocess.run(
        [sys.executable, str(_BOOTSTRAP), str(clone), "--expect", "any",
         "--owner", "acme", "--no-ontology", "--non-interactive"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )


def _spec_for(opts: dict, source: str | None, pin: str | None) -> RealFixtureSpec:
    base = real_registry(opts).get("B11")
    if base is None and source is None:
        raise SystemExit("no B11 fixture in the registry and no --source given")
    src = source or base.source
    ref = base.ref if base else "refs/heads/main"
    return RealFixtureSpec(bucket="B11", source=src, pin=pin, ref=ref, model="single-repo")


def run_study(source: str | None, pin: str | None, opts: dict | None = None) -> dict:
    """Clone at pin, archive, fresh-install, restore; return a JSON-able evidence record."""
    opts = dict(opts or {})
    repo_space = _load_repo_space()
    spec = _spec_for(opts, source, pin)
    resolved_pin = resolve_pin(spec.source, spec.ref, spec.pin)

    scratch = Path(tempfile.mkdtemp(prefix="b11-upgrade-study-"))
    clone = scratch / "clone"
    ev: dict = {"source": spec.source, "ref": spec.ref, "pin": resolved_pin}
    try:
        fp_before = source_fingerprint(spec.source)
        ctx = provision_real(spec, clone, opts)
        ev["source_unchanged_after_provision"] = ctx["extra"]["source_unchanged"]

        # BEFORE: the pre-existing (diverged) install, in full + managed scope.
        before_full = snapshot(clone)
        before_managed = _managed_scope(before_full)
        ev["before"] = {
            "managed_file_count": len(before_managed),
            "present_assets": [n for n in _MANAGED if (clone / n).exists()],
            "roster_members": _roster_members(clone),
        }

        # ARCHIVE (consent-gated) — chooser/consent_fn are the documented #108 seams.
        prep = repo_space.prepare_for_install(
            clone, non_interactive=False,
            chooser=lambda: "archive", consent_fn=lambda _s: True,
        )
        arc = prep.archive
        ev["archive"] = {
            "action": prep.action,
            "moved": list(arc.moved) if arc else [],
            "archive_dir": str(arc.archive_dir) if arc and arc.archive_dir else None,
        }
        # Assets are demonstrably OUT of Claude scope now.
        ev["post_archive"] = {
            "root_assets_present": [n for n in _MANAGED if (clone / n).exists()],
            "archived_assets_present": (
                [n for n in _MANAGED if arc and arc.archive_dir and (arc.archive_dir / n).exists()]
            ),
            "roster_members_at_root": _roster_members(clone),  # must be [] (archived away)
        }

        # FRESH install over the cleaned slate.
        fresh = _fresh_install(clone)
        ev["fresh_install"] = {
            "returncode": fresh.returncode,
            "roster_members": _roster_members(clone),  # our team, NOT botfarm's
        }
        fresh_managed = _managed_scope(snapshot(clone))
        ev["fresh_install"]["differs_from_before"] = bool(
            symmetric_diff(before_managed, fresh_managed)
        )

        # RESTORE (overwrite the fresh install that was laid down after the archive).
        res = repo_space.restore_assets(clone, arc.archive_dir, overwrite=True)
        ev["restore"] = {"restored": list(res.restored), "conflicts": list(res.conflicts)}

        # AFTER: prove byte-identical restore of the managed assets.
        after_full = snapshot(clone)
        after_managed = _managed_scope(after_full)
        managed_diff = symmetric_diff(before_managed, after_managed)
        ev["restore"]["managed_symmetric_diff"] = managed_diff
        ev["restore"]["byte_identical"] = not managed_diff

        # Honest out-of-scope accounting: what the fresh install left that restore does not own.
        full_diff = symmetric_diff(before_full, after_full)
        ev["out_of_scope_residue"] = [p for p in full_diff if p not in managed_diff]

        # Read-only invariant re-check.
        fp_after = source_fingerprint(spec.source)
        ev["source_unchanged"] = fp_before == fp_after
        return ev
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        # Teardown proof: drop-the-copy => zero residue by construction.
        ev["teardown_scratch_removed"] = not scratch.exists()


def _parse(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="python3 -m framework.harness.botfarm_upgrade_study",
        description="B11 upgrade-over-live-install archive/restore study (#109).",
    )
    ap.add_argument("--source", help="source repo path/URL (default: B11 registry entry)")
    ap.add_argument("--pin", help="explicit SHA to clone (default: resolve --ref live)")
    ap.add_argument("--real-config", type=Path, default=None,
                    help="sidecar JSON overriding the B11 fixture source/pin")
    ap.add_argument("--out", type=Path, default=None, help="write the evidence JSON here")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    opts: dict = {}
    if args.real_config is not None:
        opts["real_config"] = str(args.real_config)
    ev = run_study(args.source, args.pin, opts)

    if args.out:
        args.out.write_text(json.dumps(ev, indent=2) + "\n", encoding="utf-8")

    ok = ev.get("restore", {}).get("byte_identical") and ev.get("source_unchanged")
    print(json.dumps(ev, indent=2))
    print(f"\nRESTORE byte-identical: {ev.get('restore', {}).get('byte_identical')}   "
          f"source unchanged: {ev.get('source_unchanged')}   "
          f"teardown clean: {ev.get('teardown_scratch_removed')}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
