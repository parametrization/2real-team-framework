"""Golden install manifest (#139) — the single source of truth for the expected install set.

Two layers of protection:

* **Unit** — ``expected_install_set`` respects install mode (standalone / meta / child) and
  the ``team.enabled`` toggle, and never enumerates the data-driven persona cards.
* **Coupling** — ``test_expected_install_set_matches_real_install`` performs a REAL
  ``bootstrap.py`` install into ``tmp_path`` and asserts the produced ``.claude/**`` tree
  equals ``expected_install_set`` (persona cards separated out and asserted non-empty). This is
  the test that keeps the manifest honest: change the installed footprint without updating the
  derivation and it goes red.
* **Drift guard** — the checked-in ``golden-manifest.json`` matches the freshly derived set, so
  a footprint change that forgets to regenerate the snapshot is caught in review.

Stdlib + pytest only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_BOOTSTRAP = _FRAMEWORK_ROOT / "install" / "bootstrap.py"
sys.path.insert(0, str(_FRAMEWORK_ROOT / "install"))

import manifest  # noqa: E402


def _claude_files(target: Path) -> set[str]:
    """Every produced ``.claude/**`` file as a repo-root-relative POSIX path."""
    claude = target / ".claude"
    return {
        ".claude/" + p.relative_to(claude).as_posix()
        for p in claude.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


# --------------------------------------------------------------------- unit


def test_standalone_team_set_shape() -> None:
    files = manifest.expected_install_set({"project": {"model": "standalone"}, "team": {"enabled": True}})
    # Config trio + a representative asset from each class + team org-artifacts.
    assert ".claude/framework.config.json" in files
    assert ".claude/install.config.json" in files
    assert ".claude/settings.json" in files
    assert ".claude/hooks/dispatcher.py" in files
    assert ".claude/lib/lifecycle.py" in files
    assert ".claude/lib/ontology_gen/refresh.py" in files
    assert ".claude/skills/wave-lifecycle/SKILL.md" in files
    assert ".claude/team/charter/charter.md" in files
    assert ".claude/team/.charter-manifest.json" in files
    assert ".claude/team/roster.json" in files
    assert ".claude/team/trust_matrix.md" in files
    assert ".claude/team/feedback_log.md" in files
    # Persona cards are data-driven — never enumerated.
    assert not any(f.startswith(manifest.ROSTER_CARDS_PREFIX) for f in files)


def test_no_team_drops_only_org_artifacts() -> None:
    team = manifest.expected_install_set({"project": {"model": "standalone"}, "team": {"enabled": True}})
    no_team = manifest.expected_install_set({"project": {"model": "standalone"}, "team": {"enabled": False}})
    # Only the team org-artifacts differ; charter + assets are laid regardless of the team layer.
    assert team - no_team == {
        ".claude/team/roster.json",
        ".claude/team/trust_matrix.md",
        ".claude/team/feedback_log.md",
    }
    assert ".claude/team/charter/charter.md" in no_team
    assert ".claude/hooks/dispatcher.py" in no_team


def test_child_set_has_no_hooks_or_charter() -> None:
    files = manifest.expected_install_set({"project": {"model": "child"}, "team": {"enabled": True}})
    assert files == {
        ".claude/framework.config.json",
        ".claude/settings.json",
        ".claude/install.config.json",
        ".claude/team/roster.json",
    }


def test_child_no_team_is_config_trio_only() -> None:
    files = manifest.expected_install_set({"project": {"model": "child"}, "team": {"enabled": False}})
    assert files == {
        ".claude/framework.config.json",
        ".claude/settings.json",
        ".claude/install.config.json",
    }


def test_defaults_when_keys_missing() -> None:
    # Empty config falls back to shipped defaults (standalone + team enabled).
    empty = manifest.expected_install_set({})
    default = manifest.expected_install_set({"project": {"model": "standalone"}, "team": {"enabled": True}})
    assert empty == default


# ------------------------------------------------------------------ coupling


def test_expected_install_set_matches_real_install(tmp_path: Path) -> None:
    """A real default install into tmp_path must equal the derived manifest.

    Ontology is disabled to keep the run fast; it writes only under ``ontology/`` (outside
    ``.claude/**``), so it never affects the manifest's scope.
    """
    r = subprocess.run(
        [sys.executable, str(_BOOTSTRAP), str(tmp_path), "--owner", "test-org", "--no-ontology"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    assert r.returncode == 0, r.stderr

    # The installer records its RESOLVED config here — feed that exact config to the manifest.
    config = json.loads((tmp_path / ".claude" / "install.config.json").read_text())
    expected = manifest.expected_install_set(config)

    produced = _claude_files(tmp_path)
    cards = {f for f in produced if f.startswith(manifest.ROSTER_CARDS_PREFIX)}

    # Everything deterministic must match EXACTLY; the variable persona cards are separated out.
    assert produced - cards == expected
    # Team mode: the roster directory is populated (the part the manifest declines to enumerate).
    assert cards, "team-mode install produced no persona cards under the roster dir"


def test_golden_snapshot_in_sync() -> None:
    """The checked-in golden-manifest.json equals the freshly derived default document."""
    on_disk = json.loads(manifest.GOLDEN_PATH.read_text())
    assert on_disk == manifest.default_document()
