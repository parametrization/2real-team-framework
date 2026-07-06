"""Tests for roster_consistency_check -- roster.json <-> roster/*.md drift gate.

Generic port of a noorinalabs P1 donor (framework/recipes/NOORINALABS_RECONCILE.md
§3c); the module under test is already generic (no source-repo hardcodes), so
these tests exercise it unchanged aside from import path + pytest style.

Load-bearing coverage: test_intra_name_mismatch_reported, test_missing_from_
json_reported, test_email_mismatch_reported, and test_missing_git_name_field_
reported each assert a SPECIFIC drift string tied to the exact check under
test (not merely "drift is non-empty") -- reverting any one of the four
`check_consistency` checks to a no-op fails its corresponding test. Stdlib +
pytest only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "lib"))

from roster_consistency_check import check_consistency, main  # noqa: E402

# --------------------------------------------------------------- fixture cards

CONSISTENT_MD = """\
# Team Member Roster Card

## Identity
- **Name:** Aino Virtanen
- **Role:** Standards & Quality Lead

## Git Identity
- **user.name:** Aino Virtanen
- **user.email:** parametrization+Aino.Virtanen@gmail.com
"""

# Identity Name uses unhyphenated form; Git Identity user.name is hyphenated.
INTRA_NAME_MISMATCH_MD = """\
# Team Member Roster Card

## Identity
- **Name:** Mei Lin Chang
- **Role:** Data Engineer

## Git Identity
- **user.name:** Mei-Lin Chang
- **user.email:** parametrization+Mei-Lin.Chang@gmail.com
"""

# user.name exists in the card but is absent from roster.json.
MISSING_FROM_JSON_MD = """\
# Team Member Roster Card

## Identity
- **Name:** Ghost Member
- **Role:** Phantom

## Git Identity
- **user.name:** Ghost Member
- **user.email:** parametrization+Ghost.Member@gmail.com
"""

# user.name is in roster.json but the .md email differs.
EMAIL_MISMATCH_MD = """\
# Team Member Roster Card

## Identity
- **Name:** Aino Virtanen
- **Role:** Standards & Quality Lead

## Git Identity
- **user.name:** Aino Virtanen
- **user.email:** wrong+typo@example.com
"""

# .md is missing the user.name field entirely.
MISSING_GIT_NAME_MD = """\
# Team Member Roster Card

## Identity
- **Name:** Aino Virtanen

## Git Identity
- **user.email:** parametrization+Aino.Virtanen@gmail.com
"""


def _setup_repo(tmp: Path, roster_json: dict[str, str], md_files: dict[str, str]) -> Path:
    """Write roster.json and roster/*.md files under a tmp repo root."""
    team_dir = tmp / ".claude" / "team"
    team_dir.mkdir(parents=True)
    (team_dir / "roster.json").write_text(json.dumps(roster_json), encoding="utf-8")
    roster_dir = team_dir / "roster"
    roster_dir.mkdir()
    for filename, content in md_files.items():
        (roster_dir / filename).write_text(content, encoding="utf-8")
    return tmp


# --------------------------------------------------------------- check_consistency


def test_consistent_card_returns_no_drift(tmp_path: Path) -> None:
    repo = _setup_repo(
        tmp_path,
        {"Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com"},
        {"standards_lead_aino.md": CONSISTENT_MD},
    )
    assert check_consistency(repo) == []


def test_intra_name_mismatch_reported(tmp_path: Path) -> None:
    repo = _setup_repo(
        tmp_path,
        {"Mei-Lin Chang": "parametrization+Mei-Lin.Chang@gmail.com"},
        {"mei_lin_chang.md": INTRA_NAME_MISMATCH_MD},
    )
    drift = check_consistency(repo)
    assert any("Identity Name" in d and "user.name" in d for d in drift), drift


def test_missing_from_json_reported(tmp_path: Path) -> None:
    repo = _setup_repo(
        tmp_path,
        {"Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com"},
        {"ghost.md": MISSING_FROM_JSON_MD},
    )
    drift = check_consistency(repo)
    assert any("not found in roster.json" in d for d in drift), drift


def test_email_mismatch_reported(tmp_path: Path) -> None:
    repo = _setup_repo(
        tmp_path,
        {"Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com"},
        {"standards_lead_aino.md": EMAIL_MISMATCH_MD},
    )
    drift = check_consistency(repo)
    assert any("user.email" in d and "roster.json" in d for d in drift), drift


def test_missing_git_name_field_reported(tmp_path: Path) -> None:
    repo = _setup_repo(
        tmp_path,
        {"Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com"},
        {"standards_lead_aino.md": MISSING_GIT_NAME_MD},
    )
    drift = check_consistency(repo)
    assert any("user.name" in d for d in drift), drift


def test_no_md_files_returns_no_drift(tmp_path: Path) -> None:
    repo = _setup_repo(
        tmp_path, {"Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com"}, {}
    )
    assert check_consistency(repo) == []


def test_mixed_cards_only_drifted_reported(tmp_path: Path) -> None:
    repo = _setup_repo(
        tmp_path,
        {
            "Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com",
            "Mei-Lin Chang": "parametrization+Mei-Lin.Chang@gmail.com",
        },
        {
            "standards_lead_aino.md": CONSISTENT_MD,
            "mei_lin_chang.md": INTRA_NAME_MISMATCH_MD,
        },
    )
    drift = check_consistency(repo)
    assert any("mei_lin_chang.md" in d for d in drift), drift
    assert not any("standards_lead_aino.md" in d for d in drift), drift


def test_missing_roster_json_is_error(tmp_path: Path) -> None:
    drift = check_consistency(tmp_path)
    assert len(drift) == 1
    assert "could not load" in drift[0]


# --------------------------------------------------------------- CLI (main)


def test_main_consistent_exits_0(tmp_path: Path) -> None:
    _setup_repo(
        tmp_path,
        {"Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com"},
        {"standards_lead_aino.md": CONSISTENT_MD},
    )
    assert main(["--repo-root", str(tmp_path)]) == 0


def test_main_drift_exits_1(tmp_path: Path) -> None:
    _setup_repo(
        tmp_path,
        {"Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com"},
        {"ghost.md": MISSING_FROM_JSON_MD},
    )
    assert main(["--repo-root", str(tmp_path)]) == 1


def test_main_missing_roster_exits_2(tmp_path: Path) -> None:
    assert main(["--repo-root", str(tmp_path)]) == 2
