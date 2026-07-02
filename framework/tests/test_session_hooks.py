"""Unit tests for the session_start (SessionStart) and session_handoff (Stop) hooks.

Both are exercised via ``check()`` with a tmp-repo config (no real session).
session_handoff's subprocess seam (``_run``) is monkeypatched so no git/gh ever
runs; the /handoff-skill interplay contract is covered case by case: manual
marker wins, unmarked-note protection (undatable / newer-than-session-start),
auto-note throttle + refresh. Stdlib + pytest only.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))

import _framework_config  # noqa: E402
import session_handoff as sh  # noqa: E402
import session_start as ss  # noqa: E402


def _write_config(tmp: Path, cfg: dict | None = None) -> None:
    claude = tmp / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    base = {"version": 1, "scm": {"provider": "github"}, "project": {"name": "demo"}}
    (claude / "framework.config.json").write_text(
        json.dumps(base if cfg is None else {**base, **cfg}), encoding="utf-8"
    )
    _framework_config.clear_cache()


def _no_subprocess(monkeypatch, outputs: dict[str, str] | None = None) -> list[list[str]]:
    """Stub sh._run; returns the recorded command lists. Keyed by argv[0:2] joined."""
    calls: list[list[str]] = []

    def fake_run(cmd, cwd, timeout=10):
        calls.append(list(cmd))
        return (outputs or {}).get(" ".join(cmd[:2]), "")

    monkeypatch.setattr(sh, "_run", fake_run)
    return calls


def _transcript(tmp: Path, iso_ts: str) -> Path:
    p = tmp / "transcript.jsonl"
    p.write_text(json.dumps({"timestamp": iso_ts}) + "\n", encoding="utf-8")
    return p


# ------------------------------------------------------------------ session_start


def test_session_start_inert_when_unconfigured(tmp_path: Path) -> None:
    _framework_config.clear_cache()
    assert ss.check({"cwd": str(tmp_path)}) is None


def test_session_start_orients_with_memory_and_handoff(tmp_path: Path) -> None:
    _write_config(tmp_path, {"scm": {"provider": "github", "owner": "acme"}})
    memory = tmp_path / ".claude" / "memory"
    memory.mkdir(parents=True)
    (memory / "MEMORY.md").write_text("# index\n", encoding="utf-8")
    (memory / "handoff.md").write_text("# Session Handoff\n", encoding="utf-8")

    result = ss.check({"cwd": str(tmp_path)})
    assert result is not None
    ctx = result["additionalContext"]
    assert "demo" in ctx and "acme" in ctx
    assert "MEMORY.md" in ctx
    assert "READ" in ctx and "handoff.md" in ctx


def test_session_start_omits_absent_subsystems(tmp_path: Path) -> None:
    _write_config(tmp_path)  # no memory dir, no handoff, no owner
    result = ss.check({"cwd": str(tmp_path)})
    assert result is not None
    ctx = result["additionalContext"]
    assert "MEMORY.md" not in ctx and "handoff.md" not in ctx
    assert "scm.owner unset" in ctx


# ---------------------------------------------------------------- session_handoff


def test_handoff_inert_when_unconfigured(tmp_path: Path, monkeypatch) -> None:
    _framework_config.clear_cache()
    calls = _no_subprocess(monkeypatch)
    assert sh.check({"cwd": str(tmp_path)}) is None
    assert calls == []  # truly inert: no git/gh at all


def test_handoff_fresh_write_carries_auto_marker_and_index_pointer(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path)
    memory = tmp_path / ".claude" / "memory"
    memory.mkdir(parents=True)
    (memory / "MEMORY.md").write_text("# Memory Index\n", encoding="utf-8")
    _no_subprocess(monkeypatch, {"git branch": "feature/x"})

    result = sh.check({"cwd": str(tmp_path)})
    assert result is not None and "handoff" in result["systemMessage"]
    text = (memory / "handoff.md").read_text(encoding="utf-8")
    assert sh.AUTO_MARKER in text
    assert sh.MANUAL_MARKER not in text.replace(sh.AUTO_MARKER, "")  # markers are distinct
    assert "feature/x" in text
    assert "handoff.md" in (memory / "MEMORY.md").read_text(encoding="utf-8")


def test_handoff_never_overwrites_manual_skill_note(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path)
    memory = tmp_path / ".claude" / "memory"
    memory.mkdir(parents=True)
    manual = f"<!-- {sh.MANUAL_MARKER} -->\n# Session Handoff — rich note\n"
    (memory / "handoff.md").write_text(manual, encoding="utf-8")
    _no_subprocess(monkeypatch)

    assert sh.check({"cwd": str(tmp_path)}) is None
    assert (memory / "handoff.md").read_text(encoding="utf-8") == manual  # untouched


def test_handoff_auto_note_is_throttled_then_refreshed(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path)
    _no_subprocess(monkeypatch, {"git branch": "one"})
    assert sh.check({"cwd": str(tmp_path)}) is not None  # fresh write

    _no_subprocess(monkeypatch, {"git branch": "two"})
    assert sh.check({"cwd": str(tmp_path)}) is None  # within throttle window

    handoff = tmp_path / ".claude" / "memory" / "handoff.md"
    old = time.time() - sh.THROTTLE_SECONDS - 5
    os.utime(handoff, (old, old))
    assert sh.check({"cwd": str(tmp_path)}) is not None  # stale auto note → refreshed
    assert "two" in handoff.read_text(encoding="utf-8")


def test_handoff_keeps_undatable_unmarked_note(tmp_path: Path, monkeypatch) -> None:
    """No transcript timestamp → an unmarked (hand-written) note is never clobbered."""
    _write_config(tmp_path)
    memory = tmp_path / ".claude" / "memory"
    memory.mkdir(parents=True)
    (memory / "handoff.md").write_text("# hand-written, no markers\n", encoding="utf-8")
    _no_subprocess(monkeypatch)

    assert sh.check({"cwd": str(tmp_path)}) is None


def test_handoff_keeps_unmarked_note_from_this_session(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path)
    memory = tmp_path / ".claude" / "memory"
    memory.mkdir(parents=True)
    (memory / "handoff.md").write_text("# written mid-session\n", encoding="utf-8")
    # Session started an hour ago; the note's mtime (now) is after it.
    started = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - 3600))
    transcript = _transcript(tmp_path, started)
    _no_subprocess(monkeypatch)

    assert sh.check({"cwd": str(tmp_path), "transcript_path": str(transcript)}) is None


def test_handoff_replaces_unmarked_note_older_than_session(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path)
    memory = tmp_path / ".claude" / "memory"
    memory.mkdir(parents=True)
    stale = memory / "handoff.md"
    stale.write_text("# last week's unmarked note\n", encoding="utf-8")
    old = time.time() - 7 * 86400
    os.utime(stale, (old, old))
    # Session started 10 minutes ago — the note provably predates it.
    started = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - 600))
    transcript = _transcript(tmp_path, started)
    _no_subprocess(monkeypatch)

    assert sh.check({"cwd": str(tmp_path), "transcript_path": str(transcript)}) is not None
    assert sh.AUTO_MARKER in stale.read_text(encoding="utf-8")


def test_handoff_gh_sections_require_owner(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path)  # owner unset
    calls = _no_subprocess(monkeypatch)
    assert sh.check({"cwd": str(tmp_path)}) is not None
    assert not any(c[0] == "gh" for c in calls)  # inert gh-wise when unconfigured

    (tmp_path / ".claude" / "memory" / "handoff.md").unlink()
    _write_config(tmp_path, {"scm": {"provider": "github", "owner": "acme"}})
    pr_json = json.dumps([{"number": 7, "title": "Ship it"}])
    calls = _no_subprocess(monkeypatch, {"gh pr": pr_json, "gh issue": "[]"})
    result = sh.check({"cwd": str(tmp_path)})
    assert result is not None
    assert any(c[0] == "gh" for c in calls)
    text = (tmp_path / ".claude" / "memory" / "handoff.md").read_text(encoding="utf-8")
    assert "#7: Ship it" in text


def test_handoff_meta_model_queries_each_child_repo(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, {
        "scm": {"provider": "github", "owner": "acme"},
        "project": {"name": "meta", "model": "meta-and-children", "repos": ["api", "web"]},
    })
    calls = _no_subprocess(monkeypatch)
    assert sh.check({"cwd": str(tmp_path)}) is not None
    repo_args = [c[c.index("--repo") + 1] for c in calls if "--repo" in c]
    assert repo_args == ["acme/api", "acme/web"]
