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


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    r = _install(tmp_path, "--dry-run")
    assert r.returncode == 0, r.stderr
    assert not _charter_dir(tmp_path).exists()
    assert "would be written" in r.stdout


# --- --refresh-charter three-way behaviour (issue #77) -----------------------

def _manifest(target: Path) -> Path:
    return target / ".claude" / "team" / ".charter-manifest.json"


def test_install_writes_charter_manifest(tmp_path: Path) -> None:
    _install(tmp_path)
    man = _manifest(tmp_path)
    assert man.is_file(), "install should record a charter render manifest"
    import json
    data = json.loads(man.read_text(encoding="utf-8"))
    assert set(data["files"]) == set(CHARTER_FILES)
    # Manifest lives OUTSIDE the charter dir so it is not a charter module.
    assert sorted(p.name for p in _charter_dir(tmp_path).glob("*")) == sorted(CHARTER_FILES)


def test_refresh_charter_preserves_hand_edited_module(tmp_path: Path) -> None:
    _install(tmp_path)
    marker = "\n## LOCAL EDIT — must survive refresh\n"
    edited = _charter_dir(tmp_path) / "commits.md"
    edited.write_text(edited.read_text(encoding="utf-8") + marker, encoding="utf-8")

    r = _install(tmp_path, "--refresh-charter")
    assert r.returncode == 0, r.stderr
    assert marker in edited.read_text(encoding="utf-8")  # hand edit not clobbered
    assert "preserved (hand-evolved)" in r.stdout
    assert "team/charter/commits.md" in r.stdout


def test_refresh_charter_propagates_config_into_unmodified_module(tmp_path: Path) -> None:
    _install(tmp_path)  # owner = test-org
    charter = _charter_dir(tmp_path) / "charter.md"
    assert "test-org" in charter.read_text(encoding="utf-8")

    r = _install(tmp_path, "--refresh-charter", "--owner", "new-org")
    assert r.returncode == 0, r.stderr
    text = charter.read_text(encoding="utf-8")
    assert "new-org" in text  # config change propagated
    assert "test-org" not in text
    assert "refreshed" in r.stdout


def test_refresh_charter_updates_unmodified_but_keeps_hand_edited(tmp_path: Path) -> None:
    """A single refresh both propagates config to clean modules AND preserves edited ones."""
    _install(tmp_path)  # owner = test-org
    edited = _charter_dir(tmp_path) / "commits.md"
    hand = edited.read_text(encoding="utf-8") + "\n## hand edit\n"
    edited.write_text(hand, encoding="utf-8")

    r = _install(tmp_path, "--refresh-charter", "--owner", "new-org")
    assert r.returncode == 0, r.stderr
    # clean module refreshed to new owner…
    assert "new-org" in (_charter_dir(tmp_path) / "charter.md").read_text(encoding="utf-8")
    # …edited module untouched.
    assert edited.read_text(encoding="utf-8") == hand


def test_refresh_without_manifest_preserves_everything(tmp_path: Path) -> None:
    """Fail-open: an install predating the manifest treats every module as hand-evolved."""
    _install(tmp_path)
    _manifest(tmp_path).unlink()  # simulate a pre-feature install

    r = _install(tmp_path, "--refresh-charter", "--owner", "new-org")
    assert r.returncode == 0, r.stderr
    # No baseline => nothing is assumed safe to overwrite.
    assert "new-org" not in (_charter_dir(tmp_path) / "charter.md").read_text(encoding="utf-8")
    assert "preserved (hand-evolved)" in r.stdout


def test_refresh_is_noop_when_nothing_changed(tmp_path: Path) -> None:
    _install(tmp_path)
    before = {n: (_charter_dir(tmp_path) / n).read_text(encoding="utf-8") for n in CHARTER_FILES}
    r = _install(tmp_path, "--refresh-charter")  # same config, no edits
    assert r.returncode == 0, r.stderr
    after = {n: (_charter_dir(tmp_path) / n).read_text(encoding="utf-8") for n in CHARTER_FILES}
    assert before == after
    assert "0 refreshed" in r.stdout or "refreshed" not in r.stdout
