"""Tests for the meta/child install modes + the fresh-vs-existing gate (issue #65).

End-to-end (subprocess, stdin CLOSED so any prompt would EOFError): a meta
install with two fake child git repos (flavors, PORTABLE parent-relative paths),
the standalone child install, repo.expect enforcement, and idempotent re-runs.
Unit: the child settings/template derivation, the expectation-gate decision
table, and the interactive children multi-select (input stubbed).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_BOOTSTRAP = _FRAMEWORK_ROOT / "install" / "bootstrap.py"
sys.path.insert(0, str(_FRAMEWORK_ROOT / "install"))
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "lib"))

import bootstrap  # noqa: E402
import child_install  # noqa: E402
import roster_gen  # noqa: E402
from ontology_gen.generate import generate as _generate_index  # noqa: E402


def _seed_child_index(repo_root: Path, name: str) -> dict[str, int]:
    """Pre-generate a child's per-repo structural index (simulating a COMMITTED
    child index). During a meta install the parent aggregates whatever per-repo
    indices are present on disk; children do not self-generate at install time,
    so this is how a real child index reaches the roll-up.
    """
    out = repo_root / "ontology" / "structural"
    out.mkdir(parents=True, exist_ok=True)
    return _generate_index(repo_root, out, name)


def _run(*argv: str) -> subprocess.CompletedProcess:
    """Run bootstrap.py with stdin closed — any prompt would EOFError/hang."""
    return subprocess.run(
        [sys.executable, str(_BOOTSTRAP), *argv],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120,
    )


def _git_repo(path: Path, *, commit: bool = False) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True, capture_output=True)
    if commit:
        (path / "README.md").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(path), "-c", "user.name=T", "-c", "user.email=t@e.com",
             "commit", "-q", "-m", "init"],
            check=True, capture_output=True,
        )
    return path


def _meta_yaml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "install.yaml"
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------- meta install


class TestMetaInstall:
    def _install_meta(self, tmp_path: Path) -> tuple[Path, subprocess.CompletedProcess]:
        meta = tmp_path / "meta"
        meta.mkdir()
        _git_repo(meta / "api")
        (meta / "api" / "pyproject.toml").write_text("[project]\nname='api'\n", encoding="utf-8")
        _git_repo(meta / "infra" / "tf")
        yaml = _meta_yaml(tmp_path, (
            "repo:\n  expect: any\n"
            "scm:\n  owner: acme\n"
            "project:\n  model: meta\n"
            "children:\n"
            "  - path: api\n"
            "  - path: infra/tf\n    flavor: infra\n"
        ))
        r = _run(str(meta), "--install-config", str(yaml), "--non-interactive")
        return meta, r

    def test_e2e_two_children_flavors_and_portable_paths(self, tmp_path: Path) -> None:
        meta, r = self._install_meta(tmp_path)
        assert r.returncode == 0, r.stderr or r.stdout

        # -- product child: full harness, parent one level up --
        api_settings_text = (meta / "api" / ".claude" / "settings.json").read_text(encoding="utf-8")
        api_settings = json.loads(api_settings_text)
        assert set(api_settings["hooks"]) == {"SessionStart", "PreToolUse", "PostToolUse", "Stop"}
        assert '$CLAUDE_PROJECT_DIR/../.claude/hooks/dispatcher.py' in api_settings_text
        api_matchers = {b.get("matcher") for b in api_settings["hooks"]["PreToolUse"]}
        assert api_matchers == {"Bash", "Agent"}  # Agent dispatch reaches product children
        # PORTABLE: no machine-specific absolute path anywhere in a child settings.
        assert str(tmp_path) not in api_settings_text

        # -- infra child (nested two deep): commit-safety + CI subset only --
        tf_settings_text = (meta / "infra" / "tf" / ".claude" / "settings.json").read_text(encoding="utf-8")
        tf_settings = json.loads(tf_settings_text)
        assert set(tf_settings["hooks"]) == {"PreToolUse", "PostToolUse"}
        matchers = {b.get("matcher") for blocks in tf_settings["hooks"].values() for b in blocks}
        assert matchers == {"Bash"}  # no SessionStart / Stop / Agent / file-edit extras
        assert '$CLAUDE_PROJECT_DIR/../../.claude/hooks/dispatcher.py' in tf_settings_text
        assert str(tmp_path) not in tf_settings_text

        # -- child runtime configs: first-class model=child + parent + flavor --
        api_cfg = json.loads((meta / "api" / ".claude" / "framework.config.json").read_text())
        assert api_cfg["project"]["model"] == "child"
        assert api_cfg["project"]["parent"] == ".."
        assert api_cfg["project"]["flavor"] == "product"
        assert api_cfg["scm"]["owner"] == "acme"  # inherited from the meta config
        assert api_cfg["identity"]["enforce"] is True
        tf_cfg = json.loads((meta / "infra" / "tf" / ".claude" / "framework.config.json").read_text())
        assert tf_cfg["project"]["parent"] == "../.."
        assert tf_cfg["project"]["flavor"] == "infra"

        # -- roster subsets + child CLAUDE.md; org artifacts stay at the meta --
        assert (meta / "api" / ".claude" / "team" / "roster.json").is_file()
        assert not (meta / "api" / ".claude" / "team" / "trust_matrix.md").exists()
        assert (meta / ".claude" / "team" / "trust_matrix.md").is_file()
        api_md = (meta / "api" / "CLAUDE.md").read_text(encoding="utf-8")
        assert "$CLAUDE_PROJECT_DIR/../.claude/hooks/" in api_md
        assert str(tmp_path) not in api_md

        # -- children recorded: meta runtime project.repos + install snapshot --
        meta_cfg = json.loads((meta / ".claude" / "framework.config.json").read_text())
        assert meta_cfg["project"]["model"] == "meta-and-children"
        assert {"api", "tf"} <= set(meta_cfg["project"]["repos"])
        snapshot = json.loads((meta / ".claude" / "install.config.json").read_text())
        assert snapshot["children"] == [
            {"path": "api", "flavor": "product"},
            {"path": "infra/tf", "flavor": "infra"},
        ]
        # No hook code in the children — the parent holds the single copy.
        assert not (meta / "api" / ".claude" / "hooks").exists()
        assert (meta / ".claude" / "hooks" / "dispatcher.py").is_file()

        # #187: each child is its own git repo and inherits the parent's
        # hooks.post_file (incl. suggest_generic_prompt) verbatim, so each gets
        # its OWN gitignore entry for the transient ledger — same as the meta.
        meta_gitignore = (meta / ".gitignore").read_text(encoding="utf-8")
        assert ".claude/generic_prompt_ledger.json" in meta_gitignore.splitlines()
        api_gitignore = (meta / "api" / ".gitignore").read_text(encoding="utf-8")
        assert ".claude/generic_prompt_ledger.json" in api_gitignore.splitlines()
        tf_gitignore = (meta / "infra" / "tf" / ".gitignore").read_text(encoding="utf-8")
        assert ".claude/generic_prompt_ledger.json" in tf_gitignore.splitlines()

    def test_e2e_meta_rerun_is_idempotent(self, tmp_path: Path) -> None:
        meta, r1 = self._install_meta(tmp_path)
        assert r1.returncode == 0, r1.stderr or r1.stdout
        before = (meta / "api" / ".claude" / "settings.json").read_text(encoding="utf-8")
        gitignore_before = (meta / "api" / ".gitignore").read_text(encoding="utf-8")

        yaml = tmp_path / "install.yaml"
        r2 = _run(str(meta), "--install-config", str(yaml), "--non-interactive")
        assert r2.returncode == 0, r2.stderr or r2.stdout
        assert "idempotent re-run" in r2.stdout  # gate skipped: already installed
        assert "child api [product]: settings already wired" in r2.stdout
        assert "CLAUDE.md up to date" in r2.stdout
        assert (meta / "api" / ".claude" / "settings.json").read_text(encoding="utf-8") == before
        assert not list((meta / "api").glob("CLAUDE.md.bak*"))  # no backup churn
        # #187: re-run never duplicates the gitignore entry.
        assert (meta / "api" / ".gitignore").read_text(encoding="utf-8") == gitignore_before

    def test_missing_configured_child_is_fatal(self, tmp_path: Path) -> None:
        meta = tmp_path / "meta"
        meta.mkdir()
        yaml = _meta_yaml(tmp_path, (
            "project:\n  model: meta\nchildren:\n  - path: nope\n"
        ))
        r = _run(str(meta), "--install-config", str(yaml), "--non-interactive")
        assert r.returncode == 1
        assert "nope" in r.stderr
        assert not (meta / ".claude" / "framework.config.json").exists()

    def test_child_claude_md_conflict_is_backed_up(self, tmp_path: Path) -> None:
        meta = tmp_path / "meta"
        meta.mkdir()
        _git_repo(meta / "api")
        (meta / "api" / "CLAUDE.md").write_text("my own notes\n", encoding="utf-8")
        yaml = _meta_yaml(tmp_path, (
            "repo:\n  expect: any\nproject:\n  model: meta\nchildren:\n  - path: api\n"
        ))
        r = _run(str(meta), "--install-config", str(yaml), "--non-interactive")
        assert r.returncode == 0, r.stderr or r.stdout
        assert (meta / "api" / "CLAUDE.md.bak").read_text(encoding="utf-8") == "my own notes\n"
        assert "child repo" in (meta / "api" / "CLAUDE.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------- child install


class TestChildInstall:
    def test_e2e_standalone_child_mode(self, tmp_path: Path) -> None:
        parent = tmp_path / "meta"
        parent.mkdir()
        r = _run(str(parent), "--owner", "acme", "--non-interactive", "--no-team")
        assert r.returncode == 0, r.stderr or r.stdout

        child = _git_repo(parent / "svc")
        yaml = _meta_yaml(tmp_path, (
            "project:\n  model: child\n  flavor: infra\nparent:\n  path: ..\n"
        ))
        r = _run(str(child), "--install-config", str(yaml), "--non-interactive")
        assert r.returncode == 0, r.stderr or r.stdout

        text = (child / ".claude" / "settings.json").read_text(encoding="utf-8")
        settings = json.loads(text)
        assert set(settings["hooks"]) == {"PreToolUse", "PostToolUse"}
        assert '$CLAUDE_PROJECT_DIR/../.claude/hooks/dispatcher.py' in text
        assert str(tmp_path) not in text  # portable
        cfg = json.loads((child / ".claude" / "framework.config.json").read_text())
        assert cfg["project"] == {
            "name": "svc", "model": "child", "parent": "..", "flavor": "infra",
        }
        assert cfg["scm"]["owner"] == "acme"  # inherited from the parent config
        assert (child / ".claude" / "team" / "roster.json").is_file()
        assert not (child / ".claude" / "team" / "trust_matrix.md").exists()
        assert not (child / ".claude" / "hooks").exists()  # no hook code in a child
        assert "child repo" in (child / "CLAUDE.md").read_text(encoding="utf-8")
        snapshot = json.loads((child / ".claude" / "install.config.json").read_text())
        assert snapshot["project"]["model"] == "child"
        assert snapshot["parent"]["path"] == ".."
        # #187: a standalone child is its own git repo — gets its own gitignore entry.
        child_gitignore = (child / ".gitignore").read_text(encoding="utf-8")
        assert ".claude/generic_prompt_ledger.json" in child_gitignore.splitlines()

        # Idempotent re-run.
        r2 = _run(str(child), "--install-config", str(yaml), "--non-interactive")
        assert r2.returncode == 0, r2.stderr or r2.stdout
        assert "already wired" in r2.stdout
        assert "up to date" in r2.stdout
        assert (child / ".gitignore").read_text(encoding="utf-8") == child_gitignore

    def test_child_mode_without_installed_parent_is_fatal(self, tmp_path: Path) -> None:
        parent = tmp_path / "bare-parent"
        child = _git_repo(parent / "svc")
        yaml = _meta_yaml(tmp_path, "project:\n  model: child\nparent:\n  path: ..\n")
        r = _run(str(child), "--install-config", str(yaml), "--non-interactive")
        assert r.returncode == 1
        assert "does not have the framework installed" in r.stderr
        assert not (child / ".claude" / "settings.json").exists()

    def test_child_mode_requires_parent_path(self, tmp_path: Path) -> None:
        yaml = _meta_yaml(tmp_path, "project:\n  model: child\n")
        target = tmp_path / "svc"
        target.mkdir()
        r = _run(str(target), "--install-config", str(yaml), "--non-interactive")
        assert r.returncode == 1
        assert "parent.path" in r.stderr

    def test_absolute_parent_path_is_rejected(self, tmp_path: Path) -> None:
        yaml = _meta_yaml(
            tmp_path, f"project:\n  model: child\nparent:\n  path: {tmp_path}\n"
        )
        target = tmp_path / "svc"
        target.mkdir()
        r = _run(str(target), "--install-config", str(yaml), "--non-interactive")
        assert r.returncode == 1
        assert "RELATIVE" in r.stderr


# ------------------------------------------------------ fresh-vs-existing gate


class TestFreshVsExisting:
    def test_non_interactive_mismatch_is_fatal(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path / "estab", commit=True)
        r = _run(str(repo), "--non-interactive", "--no-team")  # default expect: fresh
        assert r.returncode == 1
        assert "looks EXISTING" in r.stderr
        assert "repo.expect" in r.stderr
        assert not (repo / ".claude" / "framework.config.json").exists()

    def test_expect_existing_and_any_proceed(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path / "estab", commit=True)
        r = _run(str(repo), "--non-interactive", "--no-team", "--expect", "existing")
        assert r.returncode == 0, r.stderr or r.stdout
        repo2 = _git_repo(tmp_path / "estab2", commit=True)
        r2 = _run(str(repo2), "--non-interactive", "--no-team", "--expect", "any")
        assert r2.returncode == 0, r2.stderr or r2.stdout

    def test_expect_existing_on_fresh_target_is_fatal(self, tmp_path: Path) -> None:
        r = _run(str(tmp_path), "--non-interactive", "--no-team", "--expect", "existing")
        assert r.returncode == 1
        assert "looks FRESH" in r.stderr

    def test_detection_is_reported(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path / "estab", commit=True)
        r = _run(str(repo), "--non-interactive", "--no-team", "--expect", "existing")
        assert "-- target repo state --" in r.stdout
        assert "git repo:      yes (with commits)" in r.stdout
        assert "verdict:       existing" in r.stdout

    def test_rerun_after_install_skips_gate(self, tmp_path: Path) -> None:
        r1 = _run(str(tmp_path), "--non-interactive", "--no-team")
        assert r1.returncode == 0, r1.stderr
        # Target is nonempty now (framework-owned files only) — still proceeds.
        r2 = _run(str(tmp_path), "--non-interactive", "--no-team")
        assert r2.returncode == 0, r2.stderr or r2.stdout
        assert "idempotent re-run" in r2.stdout

    def test_dry_run_reports_but_never_refuses(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path / "estab", commit=True)
        r = _run(str(repo), "--non-interactive", "--no-team", "--dry-run")
        assert r.returncode == 0, r.stderr or r.stdout
        assert "would refuse" in r.stdout
        assert not (repo / ".claude").exists()

    # -- gate decision table (unit) --

    @staticmethod
    def _state(**over) -> dict:
        base = {"has_git": False, "has_commits": False, "nonempty": False,
                "installed": False, "classification": "fresh"}
        base.update(over)
        return base

    def test_gate_interactive_confirmation_yes_and_no(self) -> None:
        existing = self._state(has_git=True, has_commits=True, classification="existing")
        ok, _ = bootstrap.repo_expectation_gate(
            existing, "fresh", non_interactive=False, interactive_tty=True, ask=lambda _: "y")
        assert ok is True
        ok, notes = bootstrap.repo_expectation_gate(
            existing, "fresh", non_interactive=False, interactive_tty=True, ask=lambda _: "")
        assert ok is False  # default answer is No
        assert any("aborted" in n for n in notes)

    def test_gate_explicit_expect_answers_the_prompt(self) -> None:
        existing = self._state(has_commits=True, classification="existing")

        def boom(_prompt: str) -> str:
            raise AssertionError("must not prompt when the config matches")

        ok, _ = bootstrap.repo_expectation_gate(
            existing, "existing", non_interactive=False, interactive_tty=True, ask=boom)
        assert ok is True
        ok, _ = bootstrap.repo_expectation_gate(
            existing, "any", non_interactive=False, interactive_tty=True, ask=boom)
        assert ok is True

    def test_gate_plain_mode_notes_and_proceeds(self) -> None:
        existing = self._state(nonempty=True, classification="existing")
        ok, notes = bootstrap.repo_expectation_gate(
            existing, "fresh", non_interactive=False, interactive_tty=False)
        assert ok is True
        assert any("advisory" in n for n in notes)


# ---------------------------------------------------------------- unit: child assets


class TestChildAssets:
    _TEMPLATE = {
        "permissions": {"allow": ["Read(.claude/**)", "Bash(python3 .claude/hooks/*)"]},
        "hooks": {
            "SessionStart": [{"hooks": [
                {"type": "command", "command": 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/start_dispatcher.py"'}]}],
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [
                    {"type": "command", "command": 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/dispatcher.py"'}]},
                {"matcher": "Agent", "hooks": [
                    {"type": "command", "command": 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/dispatcher.py"'}]},
            ],
            "PostToolUse": [
                {"matcher": "Bash", "hooks": [
                    {"type": "command", "command": 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/post_dispatcher.py"'}]},
                {"matcher": "Edit|Write", "hooks": [
                    {"type": "command", "command": 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/post_dispatcher.py"'}]},
            ],
            "Stop": [{"hooks": [
                {"type": "command", "command": 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/stop_dispatcher.py"'}]}],
        },
    }

    def test_parent_rel_depth(self) -> None:
        assert child_install.parent_rel_for_child("api") == ".."
        assert child_install.parent_rel_for_child("services/api") == "../.."
        assert child_install.parent_rel_for_child("./services/api/") == "../.."

    def test_product_keeps_all_events_and_rewrites(self) -> None:
        out = child_install.build_child_settings(self._TEMPLATE, "..", "product")
        assert set(out["hooks"]) == {"SessionStart", "PreToolUse", "PostToolUse", "Stop"}
        cmds = [h["command"] for blocks in out["hooks"].values() for b in blocks for h in b["hooks"]]
        assert all("$CLAUDE_PROJECT_DIR/../.claude/hooks/" in c for c in cmds)
        # hook/lib permission rules point at the parent; child-local ones don't move
        assert "Bash(python3 ../.claude/hooks/*)" in out["permissions"]["allow"]
        assert "Read(.claude/**)" in out["permissions"]["allow"]
        # the source template is untouched (pure function)
        assert "$CLAUDE_PROJECT_DIR/.claude/" in json.dumps(self._TEMPLATE)

    def test_infra_is_bash_only_subset(self) -> None:
        out = child_install.build_child_settings(self._TEMPLATE, "../..", "infra")
        assert set(out["hooks"]) == {"PreToolUse", "PostToolUse"}
        for blocks in out["hooks"].values():
            assert all(b.get("matcher") == "Bash" for b in blocks)
        cmds = [h["command"] for blocks in out["hooks"].values() for b in blocks for h in b["hooks"]]
        assert all("$CLAUDE_PROJECT_DIR/../../.claude/hooks/" in c for c in cmds)

    def test_child_runtime_config_inherits_shared_sections(self) -> None:
        parent = {"version": 1, "scm": {"owner": "acme"}, "identity": {"enforce": True},
                  "policy": {"reviewers_required": 2}, "hooks": {"pre_bash": ["x"]},
                  "paths": {"team": ".claude/team"}}
        cfg = child_install.child_runtime_config(parent, "api", "..", "product")
        assert cfg["project"] == {"name": "api", "model": "child", "parent": "..", "flavor": "product"}
        assert cfg["scm"] == {"owner": "acme"}
        assert cfg["policy"] == {"reviewers_required": 2}
        assert "paths" not in cfg  # path layout is per-repo, not inherited
        cfg["scm"]["owner"] = "other"
        assert parent["scm"]["owner"] == "acme"  # deep copy, no aliasing

    def test_interactive_multi_select(self, monkeypatch, tmp_path: Path) -> None:
        for name in ("api", "web"):
            _git_repo(tmp_path / name)
        answers = iter(["2", "i"])  # pick #2 (web), flavor infra
        monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
        selected = bootstrap.select_children({"children": []}, set(), tmp_path, interactive_tty=True)
        assert selected == [{"path": "web", "flavor": "infra"}]

    def test_config_first_children_skip_prompt(self, tmp_path: Path) -> None:
        _git_repo(tmp_path / "api")

        # user_keys says children came from YAML — must not prompt (input would EOFError).
        selected = bootstrap.select_children(
            {"children": [{"path": "api", "flavor": "product"}]},
            {"children"}, tmp_path, interactive_tty=True,
        )
        assert selected == [{"path": "api", "flavor": "product"}]

    def test_write_child_claude_md_is_idempotent_with_backup(self, tmp_path: Path) -> None:
        content = child_install.child_claude_md(
            meta_name="meta", rel="..", flavor="product",
            members=[("Tech Lead", "Staff", "Aria Okafor")],
        )
        assert "| Tech Lead | Staff | Aria Okafor |" in content
        assert bootstrap.child_install.write_child_claude_md(tmp_path, content, dry_run=False) == "written"
        assert child_install.write_child_claude_md(tmp_path, content, dry_run=False) == "up to date"
        assert not (tmp_path / "CLAUDE.md.bak").exists()
        (tmp_path / "CLAUDE.md").write_text("user content\n", encoding="utf-8")
        status = child_install.write_child_claude_md(tmp_path, content, dry_run=False)
        assert "preserved as CLAUDE.md.bak" in status
        assert (tmp_path / "CLAUDE.md.bak").read_text(encoding="utf-8") == "user content\n"


# ---------------------------------------------------------------- roster model


def test_child_model_roster_has_no_org_artifacts(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    p = roster_gen.plan(
        tmp_path, email_pattern="t+{First}.{Last}@e.com", declared_model="child", declared_repos=[]
    )
    assert p.intro.model == "child"
    rep = roster_gen.write_roster(tmp_path / ".claude" / "team", p, force=False, dry_run=False)
    assert any(w.endswith("roster.json") for w in rep["written"])
    assert not (tmp_path / ".claude" / "team" / "trust_matrix.md").exists()
    assert not (tmp_path / ".claude" / "team" / "feedback_log.md").exists()


def test_declared_empty_repo_list_never_falls_back_to_detection(tmp_path: Path) -> None:
    _git_repo(tmp_path / "stray")  # would be detected — must NOT be
    intro = roster_gen.introspect(
        tmp_path, declared_model="meta-and-children", declared_repos=[]
    )
    assert [r.name for r in intro.repos] == [tmp_path.name]


# ------------------------------------------------ meta ontology at install time
#
# Issue #75: generate_structural() threads project.model through to
# ontology_gen.refresh, which handles the meta-and-children cross-repo
# aggregation — but coverage existed only for single-repo installs. These
# end-to-end tests exercise the meta path at install time and assert the
# cross-repo aggregate artifact + the "cross-repo N nodes across M repo(s)"
# report line.

_CROSS_REPO_RE = re.compile(r"cross-repo\s+(\d+)\s+nodes across\s+(\d+)\s+repo\(s\)")


class TestMetaOntologyInstall:
    def _install_meta_with_seeded_children(
        self, tmp_path: Path
    ) -> tuple[Path, subprocess.CompletedProcess]:
        meta = tmp_path / "meta"
        meta.mkdir()
        # The parent's OWN source, so its per-repo index (generated during the
        # install's refresh) contributes nodes to the roll-up too.
        (meta / "core.py").write_text("def parent_fn():\n    return 1\n", encoding="utf-8")
        # Two child git repos, each with source AND a pre-seeded per-repo index.
        for child, fn in (("api", "api_fn"), ("web", "web_fn")):
            _git_repo(meta / child)
            (meta / child / f"{child}.py").write_text(
                f"def {fn}():\n    return 2\n", encoding="utf-8"
            )
            _seed_child_index(meta / child, child)
        yaml = _meta_yaml(tmp_path, (
            "repo:\n  expect: any\n"
            "scm:\n  owner: acme\n"
            "project:\n  model: meta\n"
            "children:\n"
            "  - path: api\n"
            "  - path: web\n"
        ))
        r = _run(str(meta), "--install-config", str(yaml), "--non-interactive")
        return meta, r

    def test_meta_install_emits_cross_repo_aggregate(self, tmp_path: Path) -> None:
        meta, r = self._install_meta_with_seeded_children(tmp_path)
        assert r.returncode == 0, r.stderr or r.stdout

        # -- the config carried model=meta-and-children into generate_structural --
        meta_cfg = json.loads((meta / ".claude" / "framework.config.json").read_text())
        assert meta_cfg["project"]["model"] == "meta-and-children"

        # -- the install reports the cross-repo roll-up on the structural line --
        m = _CROSS_REPO_RE.search(r.stdout)
        assert m, f"missing 'cross-repo … nodes across … repo(s)' line:\n{r.stdout}"
        nodes, repos = int(m.group(1)), int(m.group(2))
        # parent + api + web = 3 in-scope repos, all with indices present.
        assert repos == 3, r.stdout
        assert nodes > 0, r.stdout

        # -- the central aggregate artifact is on disk at the meta root --
        central = meta / "ontology" / "structural" / "cross-repo-graph.json"
        assert central.is_file(), "cross-repo aggregate was not written"
        graph = json.loads(central.read_text())
        assert isinstance(graph.get("nodes"), list) and graph["nodes"]

        # -- every id is namespaced by its repo; both children AND the parent
        #    (keyed by its dir name) appear in the roll-up --
        namespaces = {n["path"].split("/", 1)[0] for n in graph["nodes"]}
        assert {"api", "web"} <= namespaces, namespaces
        assert "meta" in namespaces, namespaces  # parent, keyed by root.name
        # The aggregate node count matches the reported count.
        assert len(graph["nodes"]) == nodes

    def test_meta_install_aggregate_is_idempotent(self, tmp_path: Path) -> None:
        meta, r1 = self._install_meta_with_seeded_children(tmp_path)
        assert r1.returncode == 0, r1.stderr or r1.stdout
        central = meta / "ontology" / "structural" / "cross-repo-graph.json"
        first = central.read_text()

        # Re-run: the per-repo index is fresh, so the structural line reports
        # "fresh" and the aggregate is not rewritten differently (deterministic).
        r2 = _run(str(meta), "--install-config", str(meta.parent / "install.yaml"),
                  "--non-interactive")
        assert r2.returncode == 0, r2.stderr or r2.stdout
        assert "structural index:  fresh" in r2.stdout
        assert central.read_text() == first

    def test_meta_install_missing_child_index_degrades_gracefully(
        self, tmp_path: Path
    ) -> None:
        # A child git repo with NO per-repo index must not abort the meta install
        # nor the aggregate — it is simply skipped and not counted.
        meta = tmp_path / "meta"
        meta.mkdir()
        (meta / "core.py").write_text("def p():\n    return 1\n", encoding="utf-8")
        _git_repo(meta / "api")
        (meta / "api" / "api.py").write_text("def a():\n    return 2\n", encoding="utf-8")
        _seed_child_index(meta / "api", "api")
        _git_repo(meta / "web")  # NO index seeded for web → absent, skipped
        (meta / "web" / "web.py").write_text("def w():\n    return 3\n", encoding="utf-8")
        yaml = _meta_yaml(tmp_path, (
            "repo:\n  expect: any\n"
            "scm:\n  owner: acme\n"
            "project:\n  model: meta\n"
            "children:\n"
            "  - path: api\n"
            "  - path: web\n"
        ))
        r = _run(str(meta), "--install-config", str(yaml), "--non-interactive")
        assert r.returncode == 0, r.stderr or r.stdout
        m = _CROSS_REPO_RE.search(r.stdout)
        assert m, r.stdout
        # parent + api have indices; web is absent → 2 repos, not 3.
        assert int(m.group(2)) == 2, r.stdout
        namespaces = {
            n["path"].split("/", 1)[0]
            for n in json.loads((meta / "ontology" / "structural" / "cross-repo-graph.json").read_text())["nodes"]
        }
        assert "web" not in namespaces, namespaces


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
