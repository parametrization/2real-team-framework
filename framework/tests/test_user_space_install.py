"""Tests for the consented user-level install step (#107, closes #106 G1).

Covers BOTH acceptance cases with a FAKE HOME (``tmp_path``) — the real ``~/.claude`` is
never read or written:

* fresh-user  — no ``~/.claude/settings.json`` (and an existing-file-missing-the-flag
  variant): the consent path writes the desired keys correctly and, when a prior file
  exists, a restorable timestamped backup is created.
* existing-user — the flag already set: **no-op, no write, no prompt**; a divergent value
  is surfaced as a conflict and **never clobbered**.
* ``--non-interactive`` guarantees ZERO writes on every path.

Also unit-tests the reusable primitives (``backup_file`` / ``prompt_consent``) and the
merge/idempotency contract #108 will build on. Stdlib + pytest only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_INSTALL = _FRAMEWORK_ROOT / "install"
if str(_INSTALL) not in sys.path:
    sys.path.insert(0, str(_INSTALL))

import backup as backup_mod  # noqa: E402
import consent as consent_mod  # noqa: E402
import user_space  # noqa: E402
from user_space import DESIRED_USER_SETTINGS, Result, merge_settings  # noqa: E402

_YES = lambda summary: True  # noqa: E731 — test consent seam (opt-in)
_NO = lambda summary: False  # noqa: E731 — test consent seam (declined)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ fresh-user cases


def test_fresh_user_no_settings_consented_write_creates_file(tmp_path: Path) -> None:
    """Fresh user, no settings.json: consent path writes every desired key correctly."""
    home = tmp_path / "home"
    path = user_space.user_settings_path(home)
    assert not path.exists()

    result = user_space.install_user_space(home=home, non_interactive=False, consent_fn=_YES)

    assert result.status == "written"
    assert result.written is True
    assert result.backup is None  # nothing existed to back up
    data = _read(path)
    assert data["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "1"
    assert data["teammateMode"] == "auto"
    assert data["worktree"]["baseRef"] == "fresh"
    for glob in DESIRED_USER_SETTINGS["permissions"]["allow"]:
        assert glob in data["permissions"]["allow"]


def test_fresh_user_existing_file_missing_flag_amended_and_backed_up(tmp_path: Path) -> None:
    """Existing settings without the flag: amend in place, back up, preserve other keys."""
    home = tmp_path / "home"
    path = user_space.user_settings_path(home)
    path.parent.mkdir(parents=True)
    original = {"model": "opus[1m]", "effortLevel": "high", "env": {"FOO": "bar"}}
    path.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")
    original_bytes = path.read_bytes()

    result = user_space.install_user_space(home=home, non_interactive=False, consent_fn=_YES)

    assert result.status == "written"
    # backup created, timestamped, and RESTORABLE (byte-identical to the original).
    assert result.backup is not None and result.backup.exists()
    assert result.backup.read_bytes() == original_bytes
    assert result.backup.name.startswith("settings.json.")
    # amended in place: new keys added, user's own keys untouched.
    data = _read(path)
    assert data["model"] == "opus[1m]"  # personal pref preserved
    assert data["effortLevel"] == "high"  # personal pref preserved
    assert data["env"]["FOO"] == "bar"  # existing env key preserved
    assert data["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "1"  # G1 added
    assert data["worktree"]["baseRef"] == "fresh"


# --------------------------------------------------------------- existing-user cases


def test_existing_user_flag_already_set_is_noop_no_write_no_prompt(tmp_path: Path) -> None:
    """Existing user with every desired key already present: no-op, no write, NO prompt."""
    home = tmp_path / "home"
    path = user_space.user_settings_path(home)
    path.parent.mkdir(parents=True)
    seed = json.loads(json.dumps(DESIRED_USER_SETTINGS))
    seed["model"] = "opus[1m]"  # plus some unrelated user prefs
    path.write_text(json.dumps(seed, indent=2) + "\n", encoding="utf-8")
    before = path.read_bytes()

    def _explode(summary: str) -> bool:  # consent must NOT be called on a full match
        raise AssertionError("prompt_consent must not be called when already configured")

    result = user_space.install_user_space(home=home, non_interactive=False, consent_fn=_explode)

    assert result.status == "already-configured"
    assert result.written is False
    assert not result.added
    assert path.read_bytes() == before  # byte-identical: nothing written


def test_divergent_value_surfaces_conflict_and_never_clobbers(tmp_path: Path) -> None:
    """A user-set divergent value is surfaced as a conflict and left exactly as-is."""
    home = tmp_path / "home"
    path = user_space.user_settings_path(home)
    path.parent.mkdir(parents=True)
    # user chose split-panes; the desired teammateMode is "auto" -> divergence.
    seed = {"teammateMode": "split-panes", "worktree": {"baseRef": "fresh"}}
    path.write_text(json.dumps(seed, indent=2) + "\n", encoding="utf-8")

    result = user_space.install_user_space(home=home, non_interactive=False, consent_fn=_YES)

    conflict_paths = {c.path for c in result.conflicts}
    assert "teammateMode" in conflict_paths
    conflict = next(c for c in result.conflicts if c.path == "teammateMode")
    assert conflict.existing == "split-panes" and conflict.desired == "auto"
    # the flag (an ADD) still went in, but the user's teammateMode was NOT clobbered.
    data = _read(path)
    assert data["teammateMode"] == "split-panes"  # untouched
    assert data["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "1"  # added alongside


# --------------------------------------------------------- --non-interactive & consent


def test_non_interactive_never_writes_fresh(tmp_path: Path) -> None:
    """--non-interactive on a fresh user: skip, zero writes, file stays absent."""
    home = tmp_path / "home"
    path = user_space.user_settings_path(home)

    result = user_space.install_user_space(home=home, non_interactive=True)

    assert result.status == "skipped"
    assert result.written is False
    assert not path.exists()  # never created


def test_non_interactive_never_writes_existing(tmp_path: Path) -> None:
    """--non-interactive with a divergent existing file: skip, byte-identical, no backup."""
    home = tmp_path / "home"
    path = user_space.user_settings_path(home)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"teammateMode": "split-panes"}) + "\n", encoding="utf-8")
    before = path.read_bytes()

    result = user_space.install_user_space(home=home, non_interactive=True)

    assert result.status == "skipped"
    assert path.read_bytes() == before
    # no backup file was produced by a skipped run.
    assert not any(p.name.startswith("settings.json.") for p in path.parent.iterdir())


def test_consent_declined_writes_nothing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    path = user_space.user_settings_path(home)

    result = user_space.install_user_space(home=home, non_interactive=False, consent_fn=_NO)

    assert result.status == "skipped"
    assert result.added  # there WAS something to add...
    assert not path.exists()  # ...but consent was declined -> no write


def test_rerun_after_write_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    path = user_space.user_settings_path(home)
    user_space.install_user_space(home=home, non_interactive=False, consent_fn=_YES)
    after_first = path.read_bytes()

    second = user_space.install_user_space(home=home, non_interactive=False, consent_fn=_NO)

    assert second.status == "already-configured"
    assert path.read_bytes() == after_first  # re-run changed nothing


def test_invalid_json_is_left_untouched(tmp_path: Path) -> None:
    home = tmp_path / "home"
    path = user_space.user_settings_path(home)
    path.parent.mkdir(parents=True)
    path.write_text("{ not valid json", encoding="utf-8")

    result = merge_settings(path, DESIRED_USER_SETTINGS, non_interactive=False, consent_fn=_YES)

    assert result.status == "error"
    assert path.read_text(encoding="utf-8") == "{ not valid json"  # untouched


# ---------------------------------------------------------- reusable primitives (unit)


def test_backup_file_absent_source_is_noop() -> None:
    assert backup_mod.backup_file(Path("/nonexistent/does/not/exist.json")) is None


def test_backup_file_is_restorable_and_non_clobbering(tmp_path: Path) -> None:
    src = tmp_path / "settings.json"
    src.write_text("v1", encoding="utf-8")
    b1 = backup_mod.backup_file(src)
    assert b1 is not None and b1.read_text() == "v1"
    src.write_text("v2", encoding="utf-8")
    b2 = backup_mod.backup_file(src)  # same second must not clobber b1
    assert b2 is not None and b2 != b1
    assert b1.read_text() == "v1"  # first backup intact -> restorable


def test_prompt_consent_non_interactive_is_false() -> None:
    assert consent_mod.prompt_consent("x", non_interactive=True) is False


def test_prompt_consent_non_tty_is_false() -> None:
    assert consent_mod.prompt_consent("x", non_interactive=False, _isatty=False) is False


def test_prompt_consent_yes_only_on_explicit_yes() -> None:
    assert consent_mod.prompt_consent(
        "x", non_interactive=False, _isatty=True, _input=lambda _p: "y"
    ) is True
    assert consent_mod.prompt_consent(
        "x", non_interactive=False, _isatty=True, _input=lambda _p: "yes"
    ) is True
    for no in ("", "n", "no", "nope", "Y E S"):
        assert consent_mod.prompt_consent(
            "x", non_interactive=False, _isatty=True, _input=lambda _p, v=no: v
        ) is False


# --------------------------------------------------------------- CLI entrypoint (safe)


def test_cli_non_interactive_skips_and_never_touches_real_home(tmp_path: Path) -> None:
    """The standalone CLI with --non-interactive writes nothing under a fake HOME."""
    home = tmp_path / "home"
    rc = user_space.main(["--non-interactive", "--home", str(home)])
    assert rc == 0
    assert not (home / ".claude" / "settings.json").exists()


def test_result_dataclass_shape() -> None:
    r = Result(status="written")
    assert r.added == [] and r.matched == [] and r.conflicts == [] and r.backup is None
