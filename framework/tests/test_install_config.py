"""Tests for the unified install config: loader units, precedence, and the
end-to-end non-interactive install (zero prompts, correct outputs, idempotent)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_BOOTSTRAP = _FRAMEWORK_ROOT / "install" / "bootstrap.py"
sys.path.insert(0, str(_FRAMEWORK_ROOT / "install"))

import install_config  # noqa: E402


def _run(*argv: str, stdin: int = subprocess.DEVNULL) -> subprocess.CompletedProcess:
    """Run bootstrap.py with stdin closed — any prompt would EOFError/hang."""
    return subprocess.run(
        [sys.executable, str(_BOOTSTRAP), *argv],
        capture_output=True,
        text=True,
        stdin=stdin,
        timeout=120,
    )


# ---------------------------------------------------------------- loader units


class TestLoader:
    def test_defaults_resolve_to_shipped_values(self) -> None:
        cfg, user_keys = install_config.load(None)
        assert user_keys == set()
        assert cfg["repo"]["expect"] == "fresh"
        assert cfg["project"]["model"] == "standalone"
        assert cfg["scm"]["provider"] == "github"
        assert cfg["ci"]["provider"] == "github-actions"
        assert cfg["ticketing"]["provider"] == "github-issues"
        assert cfg["pre_push"]["mode"] == "noop"
        assert cfg["ontology"]["enabled"] is True
        assert cfg["team"]["enabled"] is True
        assert cfg["children"] == []
        problems, warnings = install_config.validate(cfg)
        assert problems == []
        assert warnings == []

    def test_user_yaml_overrides_defaults(self, tmp_path: Path) -> None:
        user = tmp_path / "install.yaml"
        user.write_text(
            "scm:\n  owner: acme\npre_push:\n  mode: none\nontology:\n  enabled: false\n",
            encoding="utf-8",
        )
        cfg, user_keys = install_config.load(user)
        assert cfg["scm"]["owner"] == "acme"
        assert cfg["pre_push"]["mode"] == "none"
        assert cfg["ontology"]["enabled"] is False
        # Untouched keys keep the shipped defaults.
        assert cfg["repo"]["expect"] == "fresh"
        assert user_keys == {"scm.owner", "pre_push.mode", "ontology.enabled"}

    def test_children_parsed_and_flavor_defaulted(self, tmp_path: Path) -> None:
        user = tmp_path / "install.yaml"
        user.write_text(
            "project:\n  model: meta\nchildren:\n"
            "  - path: services/api\n    flavor: product\n"
            "  - path: infra/tf\n    flavor: infra\n"
            "  - path: services/web\n",
            encoding="utf-8",
        )
        cfg, _ = install_config.load(user)
        problems, _ = install_config.validate(cfg)
        assert problems == []
        assert cfg["children"] == [
            {"path": "services/api", "flavor": "product"},
            {"path": "infra/tf", "flavor": "infra"},
            {"path": "services/web", "flavor": "product"},  # flavor defaulted
        ]

    @pytest.mark.parametrize(
        ("body", "fragment"),
        [
            ("repo:\n  expect: brand-new\n", "repo.expect"),
            ("project:\n  model: mono\n", "project.model"),
            ("scm:\n  provider: gitlab\n", "scm.provider"),
            ("ci:\n  provider: jenkins\n", "ci.provider"),
            ("ticketing:\n  provider: jira\n", "ticketing.provider"),
            ("pre_push:\n  mode: strict\n", "pre_push.mode"),
            ("ontology:\n  enabled: maybe\n", "ontology.enabled"),
            ("team:\n  size: -2\n", "team.size"),
            ("children:\n  - flavor: product\n", "children[0].path"),
            ("children:\n  - path: a\n    flavor: exotic\n", "children[0].flavor"),
            ("version: 2\n", "version"),
        ],
    )
    def test_validate_rejects_bad_values(self, tmp_path: Path, body: str, fragment: str) -> None:
        user = tmp_path / "install.yaml"
        user.write_text(body, encoding="utf-8")
        cfg, _ = install_config.load(user)
        problems, _ = install_config.validate(cfg)
        assert any(fragment in p for p in problems), problems

    def test_unknown_keys_warn_and_are_carried(self, tmp_path: Path) -> None:
        user = tmp_path / "install.yaml"
        user.write_text("future_section:\n  knob: 1\n", encoding="utf-8")
        cfg, _ = install_config.load(user)
        problems, warnings = install_config.validate(cfg)
        assert problems == []
        assert any("future_section" in w for w in warnings)
        assert cfg["future_section"] == {"knob": 1}  # carried, not dropped

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        user = tmp_path / "install.yaml"
        user.write_text("scm: &anchor\n", encoding="utf-8")
        with pytest.raises(install_config.InstallConfigError):
            install_config.load(user)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(install_config.InstallConfigError):
            install_config.load(tmp_path / "nope.yaml")

    def test_runtime_overlay_respects_user_keys(self) -> None:
        cfg, _ = install_config.load(None)
        # Default model is NOT overlaid (would clobber a --config JSON seed).
        assert install_config.runtime_overlay(cfg, set()) == {}
        install_config.set_key(cfg, "scm.owner", "acme")
        install_config.set_key(cfg, "project.model", "meta")
        overlay = install_config.runtime_overlay(cfg, {"scm.owner", "project.model"})
        assert overlay == {"scm": {"owner": "acme"}, "project": {"model": "meta-and-children"}}


# ---------------------------------------------------------------- e2e install


class TestNonInteractiveInstall:
    def test_e2e_fresh_install_zero_prompts(self, tmp_path: Path) -> None:
        user = tmp_path / "install.yaml"
        user.write_text(
            "scm:\n  owner: acme\nteam:\n  size: 4\n"
            "pre_push:\n  mode: enforce\nchildren: []\n",
            encoding="utf-8",
        )
        target = tmp_path / "repo"
        target.mkdir()
        r = _run(str(target), "--install-config", str(user), "--non-interactive")
        assert r.returncode == 0, r.stderr or r.stdout
        # Zero prompts: no prompt strings ever printed, stdin was closed.
        assert "Proceed with this team?" not in r.stdout
        assert "GitHub owner" not in r.stdout

        claude = target / ".claude"
        assert (claude / "framework.config.json").is_file()
        assert (claude / "settings.json").is_file()
        assert (claude / "hooks" / "dispatcher.py").is_file()
        # Ontology defaults ON per the shipped install defaults.
        assert (target / "ontology" / "domain.yaml").is_file()

        runtime = json.loads((claude / "framework.config.json").read_text())
        assert runtime["scm"]["owner"] == "acme"

        # The resolved install config is recorded and carries every key.
        snapshot = json.loads((claude / "install.config.json").read_text())
        assert snapshot["scm"]["owner"] == "acme"
        assert snapshot["team"]["size"] == 4
        assert snapshot["pre_push"]["mode"] == "enforce"
        assert snapshot["repo"]["expect"] == "fresh"
        assert snapshot["ticketing"]["provider"] == "github-issues"
        assert snapshot["children"] == []

        # Roster generated with the configured size, no proceed-prompt.
        roster = json.loads((claude / "team" / "roster.json").read_text())
        assert len(roster) == 4  # roster.json is the {name: email} allowlist

    def test_e2e_reruns_are_idempotent(self, tmp_path: Path) -> None:
        r1 = _run(str(tmp_path), "--owner", "acme", "--non-interactive", "--no-team")
        assert r1.returncode == 0, r1.stderr
        r2 = _run(str(tmp_path), "--owner", "acme", "--non-interactive", "--no-team")
        assert r2.returncode == 0, r2.stderr
        assert "skipped (exists)" in r2.stdout
        assert "already wired" in r2.stdout
        assert "install snapshot:  skipped" in r2.stdout

    def test_interactive_without_tty_never_prompts(self, tmp_path: Path) -> None:
        # Even with --interactive, a non-TTY stdin must not hang or EOFError.
        r = _run(str(tmp_path), "--interactive", "--no-team")
        assert r.returncode == 0, r.stderr

    def test_interactive_and_non_interactive_are_mutually_exclusive(self, tmp_path: Path) -> None:
        r = _run(str(tmp_path), "--interactive", "--non-interactive")
        assert r.returncode == 2
        assert "not allowed with" in r.stderr

    def test_invalid_install_config_is_fatal(self, tmp_path: Path) -> None:
        user = tmp_path / "install.yaml"
        user.write_text("pre_push:\n  mode: strict\n", encoding="utf-8")
        target = tmp_path / "repo"
        target.mkdir()
        r = _run(str(target), "--install-config", str(user), "--non-interactive")
        assert r.returncode == 1
        assert "pre_push.mode" in r.stderr
        assert not (target / ".claude" / "framework.config.json").exists()

    def test_children_carried_into_snapshot(self, tmp_path: Path) -> None:
        user = tmp_path / "install.yaml"
        user.write_text(
            "project:\n  model: meta\nchildren:\n"
            "  - path: services/api\n  - path: infra/tf\n    flavor: infra\n",
            encoding="utf-8",
        )
        target = tmp_path / "repo"
        target.mkdir()
        r = _run(str(target), "--install-config", str(user), "--non-interactive", "--no-team")
        assert r.returncode == 0, r.stderr or r.stdout
        snapshot = json.loads((target / ".claude" / "install.config.json").read_text())
        assert snapshot["project"]["model"] == "meta"
        assert snapshot["children"] == [
            {"path": "services/api", "flavor": "product"},
            {"path": "infra/tf", "flavor": "infra"},
        ]
        # Explicit meta model flows into the runtime config.
        runtime = json.loads((target / ".claude" / "framework.config.json").read_text())
        assert runtime["project"]["model"] == "meta-and-children"


class TestPrecedence:
    def test_cli_flag_beats_user_yaml(self, tmp_path: Path) -> None:
        user = tmp_path / "install.yaml"
        user.write_text("scm:\n  owner: from-yaml\n", encoding="utf-8")
        target = tmp_path / "repo"
        target.mkdir()
        r = _run(
            str(target), "--install-config", str(user), "--owner", "from-flag",
            "--non-interactive", "--no-team",
        )
        assert r.returncode == 0, r.stderr or r.stdout
        runtime = json.loads((target / ".claude" / "framework.config.json").read_text())
        assert runtime["scm"]["owner"] == "from-flag"
        snapshot = json.loads((target / ".claude" / "install.config.json").read_text())
        assert snapshot["scm"]["owner"] == "from-flag"

    def test_user_yaml_beats_shipped_defaults(self, tmp_path: Path) -> None:
        user = tmp_path / "install.yaml"
        user.write_text("ontology:\n  enabled: false\nrepo:\n  expect: existing\n", encoding="utf-8")
        target = tmp_path / "repo"
        target.mkdir()
        r = _run(str(target), "--install-config", str(user), "--non-interactive", "--no-team")
        assert r.returncode == 0, r.stderr or r.stdout
        assert not (target / "ontology").exists()  # default true overridden
        snapshot = json.loads((target / ".claude" / "install.config.json").read_text())
        assert snapshot["repo"]["expect"] == "existing"

    def test_shipped_defaults_apply_without_user_yaml(self, tmp_path: Path) -> None:
        r = _run(str(tmp_path), "--non-interactive", "--no-team")
        assert r.returncode == 0, r.stderr or r.stdout
        assert (tmp_path / "ontology" / "domain.yaml").is_file()  # ontology on
        snapshot = json.loads((tmp_path / ".claude" / "install.config.json").read_text())
        assert snapshot["pre_push"]["mode"] == "noop"
        assert snapshot["repo"]["expect"] == "fresh"

    def test_ontology_flag_beats_yaml(self, tmp_path: Path) -> None:
        user = tmp_path / "install.yaml"
        user.write_text("ontology:\n  enabled: true\n", encoding="utf-8")
        target = tmp_path / "repo"
        target.mkdir()
        r = _run(
            str(target), "--install-config", str(user), "--no-ontology",
            "--non-interactive", "--no-team",
        )
        assert r.returncode == 0, r.stderr or r.stdout
        assert not (target / "ontology").exists()
        snapshot = json.loads((target / ".claude" / "install.config.json").read_text())
        assert snapshot["ontology"]["enabled"] is False

    def test_team_size_yaml_answers_roster_without_prompt(self, tmp_path: Path) -> None:
        user = tmp_path / "install.yaml"
        user.write_text("team:\n  size: 3\n", encoding="utf-8")
        target = tmp_path / "repo"
        target.mkdir()
        r = _run(str(target), "--install-config", str(user), "--non-interactive")
        assert r.returncode == 0, r.stderr or r.stdout
        roster = json.loads((target / ".claude" / "team" / "roster.json").read_text())
        assert len(roster) == 3
