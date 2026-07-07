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
