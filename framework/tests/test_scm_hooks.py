"""Tests for the SCM-hygiene hooks: validate_labels + block_squash_wave_merge.

validate_labels is exercised via check() with get_existing_labels monkeypatched
(no network). block_squash_wave_merge is exercised via check() with a tmp config
(identity gate + integration pattern) and an injected base_runner. Stdlib +
pytest only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))

import _framework_config  # noqa: E402
import block_squash_wave_merge as bsq  # noqa: E402
import validate_labels as vl  # noqa: E402


def _bash(command: str, cwd: str | None = None) -> dict:
    d: dict = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        d["cwd"] = cwd
    return d


# --------------------------------------------------------------- validate_labels


def test_labels_not_issue_create_is_ignored(monkeypatch) -> None:
    monkeypatch.setattr(vl, "get_existing_labels", lambda repo=None: {"bug"})
    assert vl.check(_bash("gh issue list --label bug")) is None
    assert vl.check(_bash("gh label create bug")) is None


def test_labels_existing_passes(monkeypatch) -> None:
    monkeypatch.setattr(vl, "get_existing_labels", lambda repo=None: {"bug", "wave-16"})
    assert vl.check(_bash('gh issue create -t x -b y --label bug --label wave-16')) is None


def test_labels_missing_blocks(monkeypatch) -> None:
    monkeypatch.setattr(vl, "get_existing_labels", lambda repo=None: {"bug"})
    r = vl.check(_bash('gh issue create -t x -b y --label nope'))
    assert r and r["decision"] == "block" and "nope" in r["reason"]


def test_labels_inside_body_not_extracted(monkeypatch) -> None:
    # `--label` appears only inside the --body value → must not be treated as a flag.
    monkeypatch.setattr(vl, "get_existing_labels", lambda repo=None: {"bug"})
    cmd = 'gh issue create -t x -b "use --label foo to tag" --label bug'
    assert vl.check(_bash(cmd)) is None  # only the real --label bug is checked


def test_labels_unverifiable_warns(monkeypatch) -> None:
    monkeypatch.setattr(vl, "get_existing_labels", lambda repo=None: set())
    r = vl.check(_bash('gh issue create -t x -b y --label bug'))
    assert r and r["decision"] == "allow" and "systemMessage" in r


# --------------------------------------------------------------- integration regex


def test_integration_regex_matches_tokens() -> None:
    rx = bsq._integration_regex("deployments/phase-{phase}/wave-{wave}")
    assert rx.match("deployments/phase-7/wave-19")
    assert not rx.match("main")
    assert not rx.match("feature/deployments/phase-1/wave-2")  # anchored
    rx2 = bsq._integration_regex("deployments/wave-{wave}")
    assert rx2.match("deployments/wave-16")
    assert not rx2.match("deployments/wave-x")


# --------------------------------------------------------------- block_squash


def _write_config(tmp: Path, *, enforce: bool, integration: str) -> Path:
    claude = tmp / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "framework.config.json").write_text(json.dumps({
        "version": 1,
        "scm": {"provider": "github", "owner": "acme"},
        "identity": {"enforce": enforce},
        "branch": {"integration": integration},
    }))
    _framework_config.clear_cache()
    return tmp


def test_squash_blocked_into_integration_when_identity_on(tmp_path: Path) -> None:
    _write_config(tmp_path, enforce=True, integration="deployments/phase-{phase}/wave-{wave}")
    r = bsq.check(
        _bash("gh pr merge 42 --squash", cwd=str(tmp_path)),
        base_runner=lambda pr, repo: "deployments/phase-7/wave-19",
    )
    assert r and r["decision"] == "block" and "--merge" in r["reason"]


def test_squash_into_default_branch_allowed(tmp_path: Path) -> None:
    _write_config(tmp_path, enforce=True, integration="deployments/phase-{phase}/wave-{wave}")
    r = bsq.check(
        _bash("gh pr merge 42 --squash", cwd=str(tmp_path)),
        base_runner=lambda pr, repo: "main",
    )
    assert r is None


def test_squash_allowed_when_identity_off(tmp_path: Path) -> None:
    _write_config(tmp_path, enforce=False, integration="deployments/phase-{phase}/wave-{wave}")
    r = bsq.check(
        _bash("gh pr merge 42 --squash", cwd=str(tmp_path)),
        base_runner=lambda pr, repo: "deployments/phase-7/wave-19",
    )
    assert r is None  # gate off → never blocks


def test_merge_flag_into_integration_allowed(tmp_path: Path) -> None:
    _write_config(tmp_path, enforce=True, integration="deployments/phase-{phase}/wave-{wave}")
    r = bsq.check(
        _bash("gh pr merge 42 --merge", cwd=str(tmp_path)),
        base_runner=lambda pr, repo: "deployments/phase-7/wave-19",
    )
    assert r is None  # not a squash → allowed
    _framework_config.clear_cache()  # leave cache clean for other tests
