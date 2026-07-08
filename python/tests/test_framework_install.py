"""Bridge tests for ``framework_install`` — argv threading for the packaged install commands.

These lock the flag-forwarding contract of the bridges without running the (heavy) bootstrapper:
``subprocess.run`` is monkeypatched to capture the argv the bridge builds. The focus here is
:func:`stage_install_framework` (#279) — it must forward the staging flags to ``install_branch.py``
AND pass the install-shape flags through to the bootstrapper that runs on the branch.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _capture(monkeypatch) -> dict:
    import real_team.framework_install as fi

    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(fi.subprocess, "run", fake_run)
    return captured


class TestStageInstallFrameworkBridge:
    def test_targets_install_branch_module(self, monkeypatch, tmp_path: Path):
        from real_team.framework_install import stage_install_framework

        captured = _capture(monkeypatch)
        stage_install_framework(tmp_path)
        cmd = captured["cmd"]
        assert cmd[1].endswith("install_branch.py")
        assert str(tmp_path) in cmd
        # --no-team is always forwarded (the CLI owns roster scaffolding), like install_framework.
        assert "--no-team" in cmd

    def test_non_interactive_default_on(self, monkeypatch, tmp_path: Path):
        """Packaged default never hangs on a prompt: --non-interactive is threaded by default."""
        from real_team.framework_install import stage_install_framework

        captured = _capture(monkeypatch)
        stage_install_framework(tmp_path)
        assert "--non-interactive" in captured["cmd"]

    def test_staging_flags_threaded(self, monkeypatch, tmp_path: Path):
        from real_team.framework_install import stage_install_framework

        captured = _capture(monkeypatch)
        stage_install_framework(
            tmp_path, branch="try/x", dry_run=True, return_to_original=True
        )
        cmd = captured["cmd"]
        assert "--branch" in cmd and "try/x" in cmd
        assert "--dry-run" in cmd
        assert "--return" in cmd

    def test_install_shape_flags_pass_through(self, monkeypatch, tmp_path: Path):
        """owner/merge-model pass THROUGH install_branch.py to the bootstrapper on the branch."""
        from real_team.framework_install import stage_install_framework

        captured = _capture(monkeypatch)
        stage_install_framework(tmp_path, owner="acme", merge_model="wave-branch")
        cmd = captured["cmd"]
        assert "--owner" in cmd and "acme" in cmd
        assert "--merge-model" in cmd and "wave-branch" in cmd

    def test_expect_threaded(self, monkeypatch, tmp_path: Path):
        """``expect`` forwards --expect to the bootstrapper that runs on the staged branch —
        the fix for #283's must-fix (the staged bootstrap used to inherit the shipped default
        repo.expect=fresh, which refuses every realistic install-branch target)."""
        from real_team.framework_install import stage_install_framework

        captured = _capture(monkeypatch)
        stage_install_framework(tmp_path, expect="existing")
        cmd = captured["cmd"]
        assert "--expect" in cmd and "existing" in cmd

    def test_expect_omitted_when_unset(self, monkeypatch, tmp_path: Path):
        """The bridge itself has no expect default (None): the CLI is the one that defaults to
        "any"; leaving expect unset here threads no --expect flag at all."""
        from real_team.framework_install import stage_install_framework

        captured = _capture(monkeypatch)
        stage_install_framework(tmp_path)
        assert "--expect" not in captured["cmd"]

    def test_no_assets_returns_none(self, monkeypatch, tmp_path: Path):
        import real_team.framework_install as fi

        monkeypatch.setattr(fi, "resolve_framework_root", lambda: None)
        assert fi.stage_install_framework(tmp_path) is None
