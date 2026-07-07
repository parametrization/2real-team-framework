"""Charter-tree drift gate (issue #189) — closes the reinstall.py `_MANAGED_TREES` hole.

``team/charter/**`` is template-rendered (``{{key}}`` substitution, not byte-mirrored like
``skills/``), so ``reinstall.py`` deliberately excludes it — see
``framework/tests/test_reinstall_parity.py`` for the byte-mirror gate. That left a real hole:
a canonical charter edit (new hook doc, a norm change) could go out without a matching runtime
update and CI would stay green (#180 / #181).

``framework/install/charter_drift.py`` closes it WITHOUT fighting the template layer: it
renders the canonical template with THIS repo's own ``framework.config.json`` (the exact
substitution ``install_charter`` applies) and diffs that against the live
``.claude/team/charter/*.md`` copy. Two layers of protection, mirroring the
``test_reinstall_parity.py`` / ``test_golden_manifest.py`` idiom:

* **The headline test** (`test_repo_charter_in_sync_with_canonical`) is the actual CI gate:
  it checks THIS repo and is picked up by the existing ``pytest framework/tests/ -v`` CI step
  (no separate ``.github/workflows/`` step needed, same as the reinstall/manifest gates).
* **Engine tests** exercise ``plan()`` against real ``bootstrap.py`` installs into ``tmp_path``,
  including the load-bearing case: a hand-edit to runtime charter CONTENT (not a placeholder)
  must be caught, and a legitimate placeholder-driven difference must not be.

Stdlib + pytest only.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_BOOTSTRAP = _FRAMEWORK_ROOT / "install" / "bootstrap.py"
sys.path.insert(0, str(_FRAMEWORK_ROOT / "install"))

import charter_drift  # noqa: E402


def _install(target: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_BOOTSTRAP), str(target), "--owner", "test-org", "--no-team", *extra],
        capture_output=True,
        text=True,
    )


# --------------------------------------------------------------- the CI gate


def test_repo_charter_in_sync_with_canonical() -> None:
    """This repo's OWN dual-deployed charter must match canonical (#116 self-hosting).

    A regression here means someone edited framework/assets/team/charter/** (or the live
    .claude/team/charter/** copy) without propagating the other side.
    """
    drift = charter_drift.plan()
    assert drift == [], (
        "live .claude/team/charter/ has drifted from the canonical template rendered with "
        "this repo's framework.config.json — re-render the affected module(s) "
        "(install_charter(..., force=True) in framework/install/bootstrap.py):\n  "
        + "\n  ".join(drift)
    )


# --------------------------------------------------------------- engine behaviour


def test_freshly_installed_charter_has_no_drift(tmp_path: Path) -> None:
    r = _install(tmp_path)
    assert r.returncode == 0, r.stderr
    assert charter_drift.plan(claude_root=tmp_path / ".claude") == []


def test_drifted_module_content_is_caught(tmp_path: Path) -> None:
    """Load-bearing (revert -> fail): a hand-edit to runtime charter CONTENT (not a
    placeholder) is caught. Reverting charter_drift.plan()'s comparison to a no-op (e.g.
    always returning []) makes this drift no longer caught — that is exactly the gap #189
    closes."""
    r = _install(tmp_path)
    assert r.returncode == 0, r.stderr
    issues = tmp_path / ".claude" / "team" / "charter" / "issues.md"
    issues.write_text(
        issues.read_text(encoding="utf-8") + "\n## drifted hand edit\n", encoding="utf-8"
    )

    drift = charter_drift.plan(claude_root=tmp_path / ".claude")
    assert ".claude/team/charter/issues.md" in drift

    rc = charter_drift.main(["--check", "--claude-root", str(tmp_path / ".claude")])
    assert rc == 1


def test_check_cli_exits_zero_when_in_sync(tmp_path: Path) -> None:
    r = _install(tmp_path)
    assert r.returncode == 0, r.stderr
    rc = charter_drift.main(["--check", "--claude-root", str(tmp_path / ".claude")])
    assert rc == 0


def test_template_placeholder_substitution_is_not_flagged(tmp_path: Path) -> None:
    """Different config values legitimately render different text at every
    {{placeholder}} site (owner, merge model, reviewer count, …) — that alone must
    never be mistaken for drift."""
    r = _install(tmp_path, "--merge-model", "direct-to-main", "--reviewers", "3")
    assert r.returncode == 0, r.stderr
    texts = {
        p.name: p.read_text(encoding="utf-8")
        for p in (tmp_path / ".claude" / "team" / "charter").glob("*.md")
    }
    assert "direct-to-main" in texts["charter.md"]
    assert "3" in texts["pull-requests.md"]
    assert charter_drift.plan(claude_root=tmp_path / ".claude") == []


def test_missing_runtime_module_is_drift(tmp_path: Path) -> None:
    r = _install(tmp_path)
    assert r.returncode == 0, r.stderr
    (tmp_path / ".claude" / "team" / "charter" / "commits.md").unlink()
    drift = charter_drift.plan(claude_root=tmp_path / ".claude")
    assert ".claude/team/charter/commits.md" in drift


def test_stale_manifest_checksum_is_caught_even_when_content_matches_canonical(
    tmp_path: Path,
) -> None:
    """Load-bearing (#216): a module whose on-disk text still matches canonical, but whose
    ``team/.charter-manifest.json`` checksum entry is stale/wrong, must be flagged as drift.

    This is the gap a plain canonical-vs-live text diff cannot see: someone (or some other
    tool) writes the correct rendered text straight to ``.claude/team/charter/*.md`` without
    going through ``install_charter``, so the manifest is never regenerated. The live file
    looks perfectly in sync — until the render manifest is consulted.

    Mutation bar: revert the checksum cross-check in ``charter_drift.plan()`` (e.g. drop the
    ``recorded_checksum`` block) and this test fails, because the content-only comparison
    sees no drift here.
    """
    import json

    r = _install(tmp_path)
    assert r.returncode == 0, r.stderr

    manifest_path = tmp_path / ".claude" / "team" / ".charter-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Corrupt the recorded checksum for one module WITHOUT touching its .md content —
    # simulating a charter edit that skipped manifest regeneration.
    manifest["files"]["issues.md"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    # The .md content itself still matches canonical exactly.
    drift = charter_drift.plan(claude_root=tmp_path / ".claude")
    assert ".claude/team/charter/issues.md" in drift

    rc = charter_drift.main(["--check", "--claude-root", str(tmp_path / ".claude")])
    assert rc == 1


def test_missing_manifest_entry_is_caught(tmp_path: Path) -> None:
    """A module present in canonical + on disk but absent from the render manifest
    (e.g. a manifest predating this module, or hand-deleted) is also drift."""
    import json

    r = _install(tmp_path)
    assert r.returncode == 0, r.stderr

    manifest_path = tmp_path / ".claude" / "team" / ".charter-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["files"]["commits.md"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    drift = charter_drift.plan(claude_root=tmp_path / ".claude")
    assert ".claude/team/charter/commits.md" in drift


def test_render_canonical_charter_matches_iter_charter_files() -> None:
    """render_canonical_charter reuses bootstrap's own iterator/context — same module set."""
    import bootstrap

    cfg = {"scm": {"owner": "x"}}
    rendered = charter_drift.render_canonical_charter(cfg)
    expected_names = {src.name for src in bootstrap._iter_charter_files()}
    assert set(rendered) == expected_names
    for text in rendered.values():
        assert "{{" not in text and "}}" not in text
