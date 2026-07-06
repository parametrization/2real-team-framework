"""Tests for roster_union_sync -- the parent-roster (superset-of) child-union drift gate.

Generic, config-driven port of a noorinalabs P1 donor
(framework/recipes/NOORINALABS_RECONCILE.md §3c). Unlike the donor (a fixed
tuple of hardcoded repo names, fetched only via the GitHub API), this port
resolves the child set from `project.repos` / local subdirectories and prefers
a LOCAL roster.json read before falling back to a (monkeypatched-in-tests)
remote fetch -- covering both the "children checked out on disk" and the
"CI checked out only the meta repo" shapes.

Load-bearing coverage:
  - test_local_child_roster_used_over_remote / test_remote_fallback_when_no_
    local_file assert resolve_child_roster's local-first / remote-fallback
    ORDER specifically (a swap or a dropped fallback fails these).
  - test_missing_persona_is_reported_with_owning_repos pins compute_drift's
    exact per-name owning-repo attribution.
  - test_drift_exit_1 / test_clean_union_exit_0 / test_all_children_skipped_
    exit_0 / test_missing_parent_roster_exit_2 pin the CLI's exit-code
    contract end to end.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "lib"))
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))

import _framework_config  # noqa: E402
import roster_union_sync  # noqa: E402
from roster_union_sync import (  # noqa: E402
    compute_drift,
    default_child_repos,
    local_child_roster,
    main,
    parent_roster_names,
    resolve_child_repos,
    resolve_child_roster,
)


def _write_parent_roster(repo_root: Path, roster: dict[str, str]) -> None:
    path = repo_root / ".claude" / "team" / "roster.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(roster), encoding="utf-8")


def _write_child_roster(repo_root: Path, child: str, roster: dict[str, str]) -> None:
    path = repo_root / child / ".claude" / "team" / "roster.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(roster), encoding="utf-8")


# --------------------------------------------------------------- compute_drift (pure)


def test_covered_union_has_no_drift() -> None:
    parent = {"Aino Virtanen", "Imelda Santos"}
    children = {"platform": {"Imelda Santos": "i@x"}}
    assert compute_drift(parent, children) == {}


def test_missing_persona_is_reported_with_owning_repos() -> None:
    parent = {"Aino Virtanen"}
    children = {
        "ingest-platform": {"Imelda Santos": "i@x"},
        "user-service": {"Imelda Santos": "i@x", "Aino Virtanen": "a@x"},
    }
    drift = compute_drift(parent, children)
    assert drift == {"Imelda Santos": ["ingest-platform", "user-service"]}


def test_empty_children_no_drift() -> None:
    assert compute_drift({"Aino Virtanen"}, {}) == {}


# --------------------------------------------------------------- parent_roster_names


def test_parent_roster_reads_committed_keys(tmp_path: Path) -> None:
    _write_parent_roster(tmp_path, {"Aino Virtanen": "a@x", "Imelda Santos": "i@x"})
    assert parent_roster_names(tmp_path) == {"Aino Virtanen", "Imelda Santos"}


def test_parent_roster_missing_returns_empty(tmp_path: Path) -> None:
    assert parent_roster_names(tmp_path) == set()


# --------------------------------------------------------------- local-first resolution


def test_local_child_roster_used_over_remote(tmp_path: Path, monkeypatch) -> None:
    """A child present on disk is read locally -- the remote fetch is never called."""
    _write_child_roster(tmp_path, "user-service", {"Imelda Santos": "i@x"})

    def _boom(owner, repo):
        raise AssertionError("remote fetch must not be called when a local file exists")

    monkeypatch.setattr(roster_union_sync, "fetch_child_roster_remote", _boom)
    roster, source = resolve_child_roster(tmp_path, "acme", "user-service")
    assert roster == {"Imelda Santos": "i@x"}
    assert source == "local"


def test_remote_fallback_when_no_local_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        roster_union_sync,
        "fetch_child_roster_remote",
        lambda owner, repo: {"Imelda Santos": "i@x"} if repo == "user-service" else None,
    )
    roster, source = resolve_child_roster(tmp_path, "acme", "user-service")
    assert roster == {"Imelda Santos": "i@x"}
    assert source == "remote"


def test_no_owner_skips_remote_fallback(tmp_path: Path, monkeypatch) -> None:
    def _boom(owner, repo):
        raise AssertionError("remote fetch must not be attempted without an owner")

    monkeypatch.setattr(roster_union_sync, "fetch_child_roster_remote", _boom)
    roster, source = resolve_child_roster(tmp_path, None, "user-service")
    assert roster is None
    assert source == "skipped"


def test_local_child_roster_missing_returns_none(tmp_path: Path) -> None:
    assert local_child_roster(tmp_path, "nope") is None


# --------------------------------------------------------------- child-repo resolution


def test_default_child_repos_detects_git_subdirs(tmp_path: Path) -> None:
    (tmp_path / "child-a" / ".git").mkdir(parents=True)
    (tmp_path / "child-b" / ".git").mkdir(parents=True)
    (tmp_path / "not-a-repo").mkdir()
    assert default_child_repos(tmp_path) == ["child-a", "child-b"]


def test_resolve_child_repos_prefers_configured_project_repos(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "framework.config.json").write_text(
        json.dumps(
            {
                "version": 1,
                "scm": {"owner": "acme"},
                "project": {"model": "meta-and-children", "repos": [tmp_path.name, "api", "web"]},
            }
        )
    )
    _framework_config.clear_cache()
    cfg = _framework_config.config(start_dir=tmp_path)
    # The meta repo's own name is filtered out of the child list.
    assert resolve_child_repos(tmp_path, cfg) == ["api", "web"]
    _framework_config.clear_cache()


def test_resolve_child_repos_falls_back_to_local_detection(tmp_path: Path) -> None:
    (tmp_path / "child-a" / ".git").mkdir(parents=True)
    cfg = _framework_config.config(start_dir=tmp_path)
    assert resolve_child_repos(tmp_path, cfg) == ["child-a"]


# --------------------------------------------------------------- CLI (main), fetch injected


def _run(tmp_path: Path, parent: dict, children: dict[str, dict | None], repos: str, owner=None):
    _write_parent_roster(tmp_path, parent)
    orig = roster_union_sync.fetch_child_roster_remote
    roster_union_sync.fetch_child_roster_remote = lambda o, r: children.get(r)
    try:
        args = ["--repo-root", str(tmp_path), "--repos", repos]
        if owner:
            args += ["--owner", owner]
        return main(args)
    finally:
        roster_union_sync.fetch_child_roster_remote = orig


def test_clean_union_exit_0(tmp_path: Path) -> None:
    rc = _run(
        tmp_path,
        {"Aino Virtanen": "a@x", "Imelda Santos": "i@x"},
        {"ingest-platform": {"Imelda Santos": "i@x"}},
        "ingest-platform",
        owner="acme",
    )
    assert rc == 0


def test_drift_exit_1(tmp_path: Path) -> None:
    rc = _run(
        tmp_path,
        {"Aino Virtanen": "a@x"},
        {"ingest-platform": {"Imelda Santos": "i@x"}},
        "ingest-platform",
        owner="acme",
    )
    assert rc == 1


def test_all_children_skipped_exit_0(tmp_path: Path) -> None:
    # Fail-open: every child unreadable -> nothing to cross-check -> pass.
    rc = _run(tmp_path, {"Aino Virtanen": "a@x"}, {"deploy": None}, "deploy", owner="acme")
    assert rc == 0


def test_missing_parent_roster_exit_2(tmp_path: Path) -> None:
    empty = tmp_path / "no-roster"
    empty.mkdir()
    rc = main(["--repo-root", str(empty), "--repos", "ingest-platform"])
    assert rc == 2


def test_cli_uses_local_child_file_without_owner(tmp_path: Path) -> None:
    """End-to-end: a locally-present child roster is cross-checked with no --owner at all."""
    _write_parent_roster(tmp_path, {"Aino Virtanen": "a@x"})
    _write_child_roster(tmp_path, "ingest-platform", {"Imelda Santos": "i@x"})
    rc = main(["--repo-root", str(tmp_path), "--repos", "ingest-platform"])
    assert rc == 1  # Imelda Santos is missing from the parent roster


def test_cli_no_repos_declared_or_detected_passes(tmp_path: Path) -> None:
    _write_parent_roster(tmp_path, {"Aino Virtanen": "a@x"})
    assert main(["--repo-root", str(tmp_path)]) == 0
