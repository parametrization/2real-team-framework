"""Tests for validate_branch_freshness -- generic, config-driven port of a P1
noorinalabs donor (framework/recipes/NOORINALABS_RECONCILE.md §3d) that closes
2real's long-deferred "branch-freshness" tech-debt item.

Exercised entirely via check()/the public helpers with git/gh subprocess calls
monkeypatched or mocked (no network, no real git state). Stdlib + pytest only.

Load-bearing (revert->fail) coverage:
  - test_local_stale_branch_blocks / test_remote_stale_branch_blocks assert a
    specific "block" decision for a behind-by-1-with-zero-threshold branch --
    reverting the block-decision logic in check() to always return None fails
    both.
  - test_local_respects_max_commits_behind_threshold and test_remote_respects_
    max_commits_behind_threshold assert the CONFIG-DRIVEN threshold is actually
    read and applied (not merely present in the schema) -- a threshold of 0
    hardcoded in is_branch_fresh_local/remote instead of read from config would
    fail these.
  - test_local_stale_by_age_when_behind and test_remote_stale_by_age assert the
    age dimension actually flags a branch whose merge-base predates the
    configured max_age_days, independent of the commits-behind threshold.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))

import _framework_config  # noqa: E402
import validate_branch_freshness as hook  # noqa: E402


def _bash(command: str, cwd: str | None = None) -> dict:
    d: dict = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        d["cwd"] = cwd
    return d


# --------------------------------------------------------------- extract_base / extract_head


def test_extract_base_default() -> None:
    assert hook.extract_base("gh pr create") == "main"


def test_extract_base_custom_default() -> None:
    assert hook.extract_base("gh pr create", default="develop") == "develop"


def test_extract_base_long_flag() -> None:
    assert hook.extract_base("gh pr create --base develop") == "develop"


def test_extract_base_short_flag() -> None:
    assert hook.extract_base("gh pr create -B develop") == "develop"


def test_extract_base_equals_form() -> None:
    assert hook.extract_base("gh pr create --base=develop") == "develop"


def test_extract_head_owner_prefix_stripped() -> None:
    assert hook.extract_head("gh pr create --head fork-owner:feature-x") == "feature-x"


def test_extract_head_absent() -> None:
    assert hook.extract_head("gh pr create") is None


def test_body_text_does_not_leak_into_base(monkeypatch) -> None:
    cmd = 'gh pr create --body "rebase onto --base ghost-base first" --base develop'
    assert hook.extract_base(cmd) == "develop"


# --------------------------------------------------------------- gate matching


def test_gh_pr_list_is_ignored() -> None:
    assert hook.check(_bash("gh pr list")) is None


def test_gh_pr_merge_is_ignored() -> None:
    assert hook.check(_bash("gh pr merge 123 --squash")) is None


def test_non_bash_tool_is_ignored() -> None:
    assert hook.check({"tool_name": "Edit", "tool_input": {"command": "gh pr create"}}) is None


def test_unrelated_command_is_ignored() -> None:
    assert hook.check(_bash('echo "gh pr create"')) is None


# --------------------------------------------------------------- local path (default threshold 0)


def test_local_fresh_branch_allows() -> None:
    with (
        mock.patch.object(hook, "_resolve_implicit_repo", return_value=None),
        mock.patch.object(hook, "is_branch_fresh_local", return_value=True) as mocked,
    ):
        result = hook.check(_bash("gh pr create"))
    assert result is None
    mocked.assert_called_once()


def test_local_stale_branch_blocks() -> None:
    with (
        mock.patch.object(hook, "_resolve_implicit_repo", return_value=None),
        mock.patch.object(hook, "is_branch_fresh_local", return_value=False),
    ):
        result = hook.check(_bash("gh pr create"))
    assert result is not None
    assert result["decision"] == "block"
    assert "origin/main" in result["reason"]


def test_local_path_receives_configured_thresholds(tmp_path: Path) -> None:
    _write_config(tmp_path, max_behind=3, max_age_days=7)
    with (
        mock.patch.object(hook, "_resolve_implicit_repo", return_value=None),
        mock.patch.object(hook, "is_branch_fresh_local", return_value=True) as mocked,
    ):
        hook.check(_bash("gh pr create", cwd=str(tmp_path)))
    mocked.assert_called_once()
    assert mocked.call_args.kwargs["max_commits_behind"] == 3
    assert mocked.call_args.kwargs["max_age_days"] == 7
    _framework_config.clear_cache()


# --------------------------------------------------------------- remote path (--repo)


def test_repo_flag_uses_remote_path() -> None:
    cmd = "gh pr create --repo acme/widgets --head feature-x --base main"
    with (
        mock.patch.object(hook, "is_branch_fresh_remote", return_value=True) as remote_mock,
        mock.patch.object(hook, "is_branch_fresh_local") as local_mock,
    ):
        result = hook.check(_bash(cmd))
    assert result is None
    remote_mock.assert_called_once()
    assert remote_mock.call_args.args[:3] == ("acme/widgets", "main", "feature-x")
    local_mock.assert_not_called()


def test_remote_stale_branch_blocks() -> None:
    cmd = "gh pr create --repo acme/widgets --head feature-x --base develop"
    with mock.patch.object(hook, "is_branch_fresh_remote", return_value=False):
        result = hook.check(_bash(cmd))
    assert result is not None
    assert result["decision"] == "block"
    assert "acme/widgets:develop" in result["reason"]


def test_repo_flag_without_head_skips() -> None:
    cmd = "gh pr create --repo acme/widgets"
    with (
        mock.patch.object(hook, "is_branch_fresh_remote") as remote_mock,
        mock.patch.object(hook, "is_branch_fresh_local") as local_mock,
    ):
        result = hook.check(_bash(cmd))
    assert result is None
    remote_mock.assert_not_called()
    local_mock.assert_not_called()


def test_remote_check_failure_allows() -> None:
    cmd = "gh pr create --repo acme/widgets --head feature-x"
    with mock.patch.object(hook, "is_branch_fresh_remote", return_value=None):
        result = hook.check(_bash(cmd))
    assert result is None


# --------------------------------------------------------------- implicit-repo resolution


def test_implicit_repo_routes_to_remote_path() -> None:
    with (
        mock.patch.object(hook, "_resolve_implicit_repo", return_value="acme/widgets"),
        mock.patch.object(hook, "_current_branch", return_value="feat-x"),
        mock.patch.object(hook, "is_branch_fresh_remote", return_value=True) as remote_mock,
        mock.patch.object(hook, "is_branch_fresh_local") as local_mock,
    ):
        result = hook.check(_bash("gh pr create"))
    assert result is None
    remote_mock.assert_called_once()
    assert remote_mock.call_args.args[:3] == ("acme/widgets", "main", "feat-x")
    local_mock.assert_not_called()


def test_gh_repo_env_takes_priority(monkeypatch) -> None:
    monkeypatch.setenv("GH_REPO", "acme/widgets")
    with (
        mock.patch.object(hook, "_resolve_implicit_repo") as resolve_mock,
        mock.patch.object(hook, "_current_branch", return_value="feat-x"),
        mock.patch.object(hook, "is_branch_fresh_remote", return_value=True),
    ):
        result = hook.check(_bash("gh pr create"))
    assert result is None
    resolve_mock.assert_not_called()


def test_gh_repo_env_empty_falls_back(monkeypatch) -> None:
    monkeypatch.delenv("GH_REPO", raising=False)
    assert hook._repo_from_env() is None


def test_gh_repo_host_qualified_form(monkeypatch) -> None:
    monkeypatch.setenv("GH_REPO", "github.com/acme/widgets")
    assert hook._repo_from_env() == "acme/widgets"


# --------------------------------------------------------------- config-driven thresholds (pure)


def test_local_respects_max_commits_behind_threshold(monkeypatch, tmp_path: Path) -> None:
    """behind=2 with threshold=2 is fresh; threshold=1 is stale."""

    def fake_run(args, **kwargs):
        result = mock.Mock()
        result.returncode = 0
        if args[:3] == ["git", "rev-list", "--left-right"]:
            result.stdout = "2\t0\n"  # 2 behind, 0 ahead
        else:
            result.stdout = ""
        return result

    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    assert hook.is_branch_fresh_local("main", max_commits_behind=2) is True
    assert hook.is_branch_fresh_local("main", max_commits_behind=1) is False


def test_local_fresh_when_zero_behind(monkeypatch) -> None:
    def fake_run(args, **kwargs):
        result = mock.Mock()
        result.returncode = 0
        result.stdout = "0\t3\n" if args[:3] == ["git", "rev-list", "--left-right"] else ""
        return result

    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    assert hook.is_branch_fresh_local("main") is True


def test_local_stale_by_age_when_behind(monkeypatch) -> None:
    """behind=1 (<= a generous count threshold) but merge-base is very old -> stale by age."""
    import time

    old_epoch = time.time() - (30 * 86400)  # 30 days ago

    def fake_run(args, **kwargs):
        result = mock.Mock()
        result.returncode = 0
        if args[:3] == ["git", "rev-list", "--left-right"]:
            result.stdout = "1\t0\n"
        elif args[:2] == ["git", "merge-base"]:
            result.stdout = "deadbeef\n"
        elif args[:2] == ["git", "show"]:
            result.stdout = f"{int(old_epoch)}\n"
        else:
            result.stdout = ""
        return result

    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    # Count threshold alone would allow (behind=1 <= 5), but age (30d > 7d) flags it.
    assert hook.is_branch_fresh_local("main", max_commits_behind=5, max_age_days=7) is False
    # With age disabled (0), the same state is fresh under the generous count threshold.
    assert hook.is_branch_fresh_local("main", max_commits_behind=5, max_age_days=0) is True


def test_local_fail_open_on_subprocess_error(monkeypatch) -> None:
    def fake_run(args, **kwargs):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    assert hook.is_branch_fresh_local("main") is True


def test_remote_respects_max_commits_behind_threshold(monkeypatch) -> None:
    def fake_run(args, **kwargs):
        result = mock.Mock()
        result.returncode = 0
        result.stdout = json.dumps({"behind": 2, "mb_date": ""})
        return result

    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    assert hook.is_branch_fresh_remote("acme/widgets", "main", "feat", max_commits_behind=2) is True
    assert hook.is_branch_fresh_remote("acme/widgets", "main", "feat", max_commits_behind=1) is False


def test_remote_stale_by_age(monkeypatch) -> None:
    import time

    old_iso = "2000-01-01T00:00:00Z"
    assert time.time() > 0  # sanity: "now" is long after year 2000

    def fake_run(args, **kwargs):
        result = mock.Mock()
        result.returncode = 0
        result.stdout = json.dumps({"behind": 1, "mb_date": old_iso})
        return result

    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    assert (
        hook.is_branch_fresh_remote(
            "acme/widgets", "main", "feat", max_commits_behind=5, max_age_days=30
        )
        is False
    )


def test_remote_fail_open_on_bad_response(monkeypatch) -> None:
    def fake_run(args, **kwargs):
        result = mock.Mock()
        result.returncode = 1
        result.stdout = ""
        return result

    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    assert hook.is_branch_fresh_remote("acme/widgets", "main", "feat") is None


def test_remote_fail_open_on_malformed_json(monkeypatch) -> None:
    def fake_run(args, **kwargs):
        result = mock.Mock()
        result.returncode = 0
        result.stdout = "not json"
        return result

    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    assert hook.is_branch_fresh_remote("acme/widgets", "main", "feat") is None


# --------------------------------------------------------------- config wiring end-to-end


def _write_config(tmp: Path, *, max_behind: int, max_age_days: int) -> None:
    claude = tmp / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "framework.config.json").write_text(
        json.dumps(
            {
                "version": 1,
                "scm": {"provider": "github", "owner": "acme"},
                "policy": {
                    "branch_freshness_max_commits_behind": max_behind,
                    "branch_freshness_max_age_days": max_age_days,
                },
            }
        )
    )
    _framework_config.clear_cache()


def test_check_reads_threshold_from_config(tmp_path: Path) -> None:
    _write_config(tmp_path, max_behind=10, max_age_days=0)
    with (
        mock.patch.object(hook, "_resolve_implicit_repo", return_value=None),
        mock.patch.object(hook, "is_branch_fresh_local", return_value=False) as mocked,
    ):
        hook.check(_bash("gh pr create", cwd=str(tmp_path)))
    assert mocked.call_args.kwargs["max_commits_behind"] == 10
    _framework_config.clear_cache()


def test_check_default_config_is_strict(tmp_path: Path) -> None:
    """Absent config -> defaults (0, 0), matching the pre-config-knob behavior."""
    with (
        mock.patch.object(hook, "_resolve_implicit_repo", return_value=None),
        mock.patch.object(hook, "is_branch_fresh_local", return_value=False) as mocked,
    ):
        hook.check(_bash("gh pr create", cwd=str(tmp_path)))
    assert mocked.call_args.kwargs["max_commits_behind"] == 0
    assert mocked.call_args.kwargs["max_age_days"] == 0
