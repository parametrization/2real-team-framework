"""Load-bearing wiring test for _framework_config._DEFAULTS (issue #196).

The runtime default-config shadow (`_framework_config._DEFAULTS`) is one of the
three copies of the `hooks.pre_bash` list that `test_defaults_sync.py` keeps in
sync. This module pins the specific wiring added for #196: `block_gh_pr_review`
is present in the runtime default list, positioned immediately after its
companion `validate_review_comment_format` (cheap/local parsing gates grouped
together, network gates last).

Load-bearing (revert -> fail): drop the `block_gh_pr_review` entry from
`_framework_config._DEFAULTS["hooks"]["pre_bash"]` and `test_hook_wired_into_defaults`
fails — a deployed repo whose written config omits the module would never run the
verdict-submission guard.

Stdlib + pytest only.
"""

from __future__ import annotations

import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))

import _framework_config  # noqa: E402


def _pre_bash() -> list[str]:
    return list(_framework_config._DEFAULTS["hooks"]["pre_bash"])


def test_hook_wired_into_defaults() -> None:
    """block_gh_pr_review is in the runtime default pre_bash list."""
    assert "block_gh_pr_review" in _pre_bash()


def test_hook_ordered_after_verdict_grammar_gate() -> None:
    """It sits immediately after validate_review_comment_format (grouped parsing
    gates; the two share the verdict-comment parsing layer)."""
    pre = _pre_bash()
    assert pre.index("block_gh_pr_review") == pre.index("validate_review_comment_format") + 1
