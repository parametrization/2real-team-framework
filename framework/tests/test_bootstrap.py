"""Load-bearing wiring test for bootstrap._schema_defaults() (issue #196).

`bootstrap._schema_defaults()` is what the installer WRITES into a target repo's
`framework.config.json` — the third of the three `hooks.pre_bash` copies
`test_defaults_sync.py` keeps in sync. This module pins the #196 wiring from the
installer's side: a freshly bootstrapped repo's written config activates
`block_gh_pr_review` (a module present in the schema but missing from the written
config would never run in a deployed repo — the exact #84 drift class).

Load-bearing (revert -> fail): drop the `block_gh_pr_review` entry from
`bootstrap._schema_defaults()["hooks"]["pre_bash"]` and
`test_installer_writes_hook_into_pre_bash` fails.

Complements `test_bootstrap_smoke.py` (end-to-end install) with a targeted unit
assertion on the written-defaults source. Stdlib + pytest only.
"""

from __future__ import annotations

import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "install"))

import bootstrap  # noqa: E402


def _written_pre_bash() -> list[str]:
    return list(bootstrap._schema_defaults()["hooks"]["pre_bash"])


def test_installer_writes_hook_into_pre_bash() -> None:
    """A bootstrapped repo's written config activates block_gh_pr_review."""
    assert "block_gh_pr_review" in _written_pre_bash()


def test_written_order_groups_hook_with_verdict_grammar_gate() -> None:
    """block_gh_pr_review follows validate_review_comment_format in the written
    order (matches the schema/runtime copies test_defaults_sync pins equal)."""
    pre = _written_pre_bash()
    assert pre.index("block_gh_pr_review") == pre.index("validate_review_comment_format") + 1


# --------------------------------------------------------------------------
# ensure_gitignore_entries() normalization pairing (#216).
#
# Full coverage (dedup / stable-order / blank-collapse / run-twice-no-diff,
# each mutation-verified) lives in test_gitignore_ledger_default.py, which
# pre-dates and is dedicated to this helper. This test pins the same
# load-bearing contract directly against bootstrap.py so the file-pairing
# gate (charter/pull-requests.md § Pre-Review Self-Check) has a same-stem
# test for THIS file's own new behavior.


def test_ensure_gitignore_entries_dedupes_and_orders_deterministically(tmp_path: Path) -> None:
    """Load-bearing (revert -> fail): calling with a duplicated/unordered entries
    tuple must still produce a single, alphabetically-stable set of appended
    lines. Reverting either the input-dedup step or the ``sorted(...)`` around
    the missing entries in ``ensure_gitignore_entries`` makes this fail."""
    # Deliberately passed in the REVERSE of sorted order (with a repeat), so this
    # catches both a dropped dedup step and a dropped `sorted(...)` independently.
    bootstrap.ensure_gitignore_entries(
        tmp_path, (".claude/x.json", ".claude-backups/", ".claude-backups/"), dry_run=False
    )
    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count(".claude-backups/") == 1
    # sorted(...) output is deterministic regardless of call-site argument order.
    assert lines.index(".claude-backups/") < lines.index(".claude/x.json")
