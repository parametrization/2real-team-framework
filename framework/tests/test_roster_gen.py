"""Tests for the repo-introspecting roster generator + its bootstrap integration.

Asserts: stack sniffing, single-repo vs meta+children detection, role derivation
reflecting detected stacks, deterministic persona assignment, the written roster
artifacts, and the end-to-end install → generated-roster → identity-gate loop.
Stdlib + pytest only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "install"))
import roster_gen  # noqa: E402

_BOOTSTRAP = _FRAMEWORK_ROOT / "install" / "bootstrap.py"


def _mk_repo(path: Path, *files: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    for f in files:
        fp = path / f
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text("{}" if f.endswith(".json") else "", encoding="utf-8")
    return path


def test_sniff_stacks_python_and_frontend(tmp_path: Path) -> None:
    repo = _mk_repo(tmp_path / "r", "pyproject.toml")
    assert "python" in roster_gen.sniff_stacks(repo)
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text(json.dumps({"dependencies": {"react": "18"}}))
    stacks = roster_gen.sniff_stacks(web)
    assert "node" in stacks and "frontend" in stacks


def test_single_repo_detection_and_small_team(tmp_path: Path) -> None:
    _mk_repo(tmp_path, "pyproject.toml")
    p = roster_gen.plan(tmp_path, email_pattern="team+{First}.{Last}@example.com")
    assert p.intro.model == "single-repo"
    roles = {r for r, _ in (((per.role, per.level)) for per in p.personas)}
    assert "Tech Lead" in roles and "QA Engineer" in roles
    assert 3 <= len(p.personas) <= 6  # focused team


def test_meta_children_detection_and_domain_roles(tmp_path: Path) -> None:
    _mk_repo(tmp_path)  # meta
    _mk_repo(tmp_path / "api", "pyproject.toml")
    web = _mk_repo(tmp_path / "web")
    (web / "package.json").write_text(json.dumps({"dependencies": {"react": "18"}}))
    _mk_repo(tmp_path / "deploy", "main.tf")
    _mk_repo(tmp_path / "user-service", "go.mod")

    p = roster_gen.plan(tmp_path, email_pattern="team+{First}.{Last}@example.com")
    assert p.intro.model == "meta-and-children"
    roles = [per.role for per in p.personas]
    assert "Program Director" in roles
    assert "Frontend Engineer" in roles      # from web/react
    assert "DevOps Engineer" in roles        # from deploy/terraform
    assert "Security Engineer" in roles      # from user-service name


def test_persona_assignment_is_deterministic(tmp_path: Path) -> None:
    _mk_repo(tmp_path, "pyproject.toml")
    a = roster_gen.plan(tmp_path, email_pattern="x+{First}.{Last}@e.com")
    b = roster_gen.plan(tmp_path, email_pattern="x+{First}.{Last}@e.com")
    assert [(p.name, p.role, p.email) for p in a.personas] == [
        (p.name, p.role, p.email) for p in b.personas
    ]


def test_team_size_override(tmp_path: Path) -> None:
    _mk_repo(tmp_path, "pyproject.toml")
    p = roster_gen.plan(tmp_path, email_pattern="t+{First}.{Last}@e.com", team_size=4)
    assert len(p.personas) == 4


def test_bootstrap_writes_roster_and_enforces_identity(tmp_path: Path) -> None:
    _mk_repo(tmp_path, "pyproject.toml")
    r = subprocess.run(
        [sys.executable, str(_BOOTSTRAP), str(tmp_path), "--owner", "acme"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    team = tmp_path / ".claude" / "team"
    roster = json.loads((team / "roster.json").read_text())
    assert len(roster) >= 3
    assert (team / "trust_matrix.md").is_file()
    assert (team / "feedback_log.md").is_file()
    assert list((team / "roster").glob("*.md"))  # persona cards

    cfg = json.loads((tmp_path / ".claude" / "framework.config.json").read_text())
    assert cfg["identity"]["enforce"] is True
    assert "validate_commit_identity" in cfg["hooks"]["pre_bash"]

    # End-to-end: a roster member's commit passes; an unknown identity blocks.
    name, email = next(iter(roster.items()))
    dispatcher = tmp_path / ".claude" / "hooks" / "dispatcher.py"

    def fire(cmd: str) -> int:
        payload = json.dumps({"tool_name": "Bash", "cwd": str(tmp_path), "tool_input": {"command": cmd}})
        return subprocess.run([sys.executable, str(dispatcher)], input=payload, capture_output=True, text=True).returncode

    assert fire(f'git -c user.name="{name}" -c user.email={email} commit -m x') == 0
    assert fire('git -c user.name="Nobody Random" -c user.email=x@y.z commit -m x') == 2


def test_no_team_flag_skips_roster(tmp_path: Path) -> None:
    _mk_repo(tmp_path, "pyproject.toml")
    r = subprocess.run(
        [sys.executable, str(_BOOTSTRAP), str(tmp_path), "--owner", "acme", "--no-team"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert not (tmp_path / ".claude" / "team").exists()
    cfg = json.loads((tmp_path / ".claude" / "framework.config.json").read_text())
    assert cfg.get("identity", {}).get("enforce", False) is False
