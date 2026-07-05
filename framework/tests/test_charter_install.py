"""Tests for the modular team-charter install (framework/assets/team/charter/).

Verifies bootstrap lays the full charter module set into <target>/.claude/team/charter/,
that ``{{key}}`` substitution is applied from the built config (no unreplaced
placeholders), and that the install is idempotent (skip-if-exists) with ``--force``
as the explicit refresh path. Stdlib + pytest only.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_BOOTSTRAP = _FRAMEWORK_ROOT / "install" / "bootstrap.py"

CHARTER_FILES = (
    "charter.md",
    "agents.md",
    "branching.md",
    "commits.md",
    "pull-requests.md",
    "issues.md",
    "hooks.md",
)


def _install(target: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_BOOTSTRAP), str(target), "--owner", "test-org", "--no-team", *extra],
        capture_output=True,
        text=True,
    )


def _charter_dir(target: Path) -> Path:
    return target / ".claude" / "team" / "charter"


def test_install_lays_all_charter_files(tmp_path: Path) -> None:
    r = _install(tmp_path)
    assert r.returncode == 0, r.stderr
    for name in CHARTER_FILES:
        assert (_charter_dir(tmp_path) / name).is_file(), f"missing charter module {name}"
    # No stray files either — the install mirrors the template set exactly.
    laid = sorted(p.name for p in _charter_dir(tmp_path).glob("*"))
    assert laid == sorted(CHARTER_FILES)


def test_substitution_applied_no_unreplaced_placeholders(tmp_path: Path) -> None:
    r = _install(tmp_path, "--merge-model", "direct-to-main", "--reviewers", "3")
    assert r.returncode == 0, r.stderr
    texts = {name: (_charter_dir(tmp_path) / name).read_text(encoding="utf-8")
             for name in CHARTER_FILES}
    # Config values landed…
    assert "test-org" in texts["charter.md"]  # scm.owner
    assert "direct-to-main" in texts["charter.md"]  # policy.merge_model
    assert "3" in texts["pull-requests.md"]  # policy.reviewers_required
    # …and no double-brace placeholder survived anywhere.
    for name, text in texts.items():
        assert "{{" not in text, f"unreplaced placeholder in {name}"
        assert "}}" not in text, f"unreplaced placeholder in {name}"


def test_generalized_no_org_specific_content(tmp_path: Path) -> None:
    _install(tmp_path)
    for name in CHARTER_FILES:
        text = (_charter_dir(tmp_path) / name).read_text(encoding="utf-8").lower()
        for banned in ("parametrization", "botfarm", "noorinalabs", "2real-team-framework"):
            assert banned not in text, f"org-specific token {banned!r} in {name}"


def test_reinstall_is_idempotent_skip_if_exists(tmp_path: Path) -> None:
    _install(tmp_path)
    marker = "## LOCAL EDIT — must survive re-install\n"
    edited = _charter_dir(tmp_path) / "commits.md"
    edited.write_text(edited.read_text(encoding="utf-8") + marker, encoding="utf-8")

    r2 = _install(tmp_path)
    assert r2.returncode == 0, r2.stderr
    assert "team charter:" in r2.stdout
    assert f"{len(CHARTER_FILES)} skipped" in r2.stdout
    assert marker in edited.read_text(encoding="utf-8")  # hand edit not clobbered


def test_force_refreshes_from_template(tmp_path: Path) -> None:
    _install(tmp_path)
    edited = _charter_dir(tmp_path) / "commits.md"
    edited.write_text("clobbered\n", encoding="utf-8")

    r = _install(tmp_path, "--force")
    assert r.returncode == 0, r.stderr
    text = edited.read_text(encoding="utf-8")
    assert "clobbered" not in text
    assert "Commit Identity" in text
    assert "{{" not in text  # force path substitutes too


def test_pr_creation_wording_is_merge_model_conditional(tmp_path: Path) -> None:
    """Issue #94: the § PR Creation base-branch sentence must NOT render as a
    self-contradiction under direct-to-main ("never `main` directly (merge
    model: `direct-to-main`)"). It must describe BOTH models and cite the
    per-wave kickoff mechanism, so it reads coherently for either config value."""
    r = _install(tmp_path, "--merge-model", "direct-to-main")
    assert r.returncode == 0, r.stderr
    pr = (_charter_dir(tmp_path) / "pull-requests.md").read_text(encoding="utf-8")
    # The old, self-contradictory phrasing is gone.
    assert "directly (merge model:" not in pr
    # Both models are described, and the per-wave declaration is cited.
    assert "Under `wave-branch`" in pr
    assert "Under `direct-to-main`" in pr
    assert "lifecycle.py wave kickoff --merge-model" in pr
    # No unreplaced placeholder survived the conditional rewrite.
    assert "{{" not in pr and "}}" not in pr


def test_ground_rules_merge_model_acknowledges_per_wave_declaration(tmp_path: Path) -> None:
    """Issue #94: the charter.md ground-rules 'Merge model:' line must note that
    the effective model is declared per wave at kickoff, so a `direct-to-main`
    configured default does not mislead a reader in a repo that runs waves."""
    r = _install(tmp_path, "--merge-model", "direct-to-main")
    assert r.returncode == 0, r.stderr
    charter = (_charter_dir(tmp_path) / "charter.md").read_text(encoding="utf-8")
    assert "direct-to-main" in charter  # the configured default still renders
    assert "declared at kickoff" in charter
    assert "lifecycle.py wave kickoff --merge-model" in charter


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    r = _install(tmp_path, "--dry-run")
    assert r.returncode == 0, r.stderr
    assert not _charter_dir(tmp_path).exists()
    assert "would be written" in r.stdout
