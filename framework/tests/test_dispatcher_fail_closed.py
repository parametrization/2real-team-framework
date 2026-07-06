"""Tests for the dispatcher's per-hook fail-direction guard (#175).

Before this fix, `dispatcher.py` had no top-level try/except around a hook's
`check()`: any uncaught exception was silently swallowed and treated as
ALLOW — the opposite of a fail-closed hook's intent (e.g.
`require_load_bearing_test`, #167). These tests exercise `dispatcher.main()`
directly (stdin + config monkeypatched, no subprocess) and assert:

  - A hook that does NOT declare `FAIL_OPEN = True` (the dispatcher's default,
    and `require_load_bearing_test`'s deliberate posture) BLOCKS the tool call
    when its `check()` raises. `test_undeclared_hook_crash_blocks` is the
    load-bearing case: it fails if the fix is reverted back to a bare
    `except Exception: continue` (verified manually — see PR description).
  - A hook that DOES declare `FAIL_OPEN = True` still allows the tool call
    through when its `check()` raises, preserving the pre-#175 behavior for
    every hook that documents itself as fail-open.

A third test covers the sibling bug in the same issue: `_added_substantive_lines`
in `require_load_bearing_test.py` crashing on a non-str `patch` value.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))

import dispatcher  # noqa: E402
import require_load_bearing_test as rlbt  # noqa: E402
import validate_labels as vl  # noqa: E402


class _FakeCfg:
    """Minimal stand-in for `_framework_config._Config` — just `.get(key, default)`."""

    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def get(self, dotted: str, default=None):
        return self._mapping.get(dotted, default)


def _run_dispatcher(monkeypatch, capsys, *, pre_bash: list[str], tool_input: dict):
    """Drive `dispatcher.main()` for a synthetic Bash call, returning (exit_code, stdout)."""
    monkeypatch.setattr(
        dispatcher, "config", lambda input_data=None: _FakeCfg({"hooks.pre_bash": pre_bash})
    )
    payload = json.dumps({"tool_name": "Bash", "tool_input": tool_input})
    monkeypatch.setattr(dispatcher.sys, "stdin", io.StringIO(payload))
    with pytest.raises(SystemExit) as exc_info:
        dispatcher.main()
    out = capsys.readouterr().out
    return exc_info.value.code, out


def test_undeclared_hook_crash_blocks(monkeypatch, capsys) -> None:
    """Load-bearing: a hook with no FAIL_OPEN declaration that raises must BLOCK.

    require_load_bearing_test is the repo's documented fail-closed hook (#167)
    and intentionally does not set FAIL_OPEN — this is exactly the gap #175
    reported: previously this crash would have been swallowed as allow (exit 0).
    """

    def _boom(_input_data):
        raise RuntimeError("simulated crash inside a fail-closed hook")

    monkeypatch.setattr(rlbt, "check", _boom)
    assert getattr(rlbt, "FAIL_OPEN", False) is False  # sanity: not declared fail-open

    code, out = _run_dispatcher(
        monkeypatch,
        capsys,
        pre_bash=["require_load_bearing_test"],
        tool_input={"command": "gh pr create --repo acme/demo --head feat"},
    )

    assert code == 2
    result = json.loads(out)
    assert result["decision"] == "block"
    assert "require_load_bearing_test" in result["reason"]
    assert "fail-closed" in result["reason"].lower()


def test_declared_fail_open_hook_crash_still_allows(monkeypatch, capsys) -> None:
    """A hook that declares FAIL_OPEN = True keeps the pre-#175 behavior: a crash
    inside it is skipped rather than blocking the tool call."""

    def _boom(_input_data):
        raise RuntimeError("simulated crash inside a fail-open hook")

    monkeypatch.setattr(vl, "check", _boom)
    assert getattr(vl, "FAIL_OPEN", False) is True  # sanity: declared fail-open

    code, out = _run_dispatcher(
        monkeypatch,
        capsys,
        pre_bash=["validate_labels"],
        tool_input={"command": "gh issue create -t x -b y --label bug"},
    )

    assert code == 0
    assert out == ""  # no warnings, no block — the crash was swallowed as allow


def test_mixed_order_fail_closed_hook_still_blocks_after_fail_open_hook(monkeypatch, capsys) -> None:
    """A crashing fail-open hook earlier in the list must not short-circuit a
    later fail-closed hook's normal (non-crash) block decision."""
    monkeypatch.setattr(vl, "check", lambda _d: (_ for _ in ()).throw(RuntimeError("boom")))

    code, out = _run_dispatcher(
        monkeypatch,
        capsys,
        pre_bash=["validate_labels", "require_load_bearing_test"],
        # Not a gh pr create/ready command -> require_load_bearing_test.check() returns
        # None (allow) rather than needing network access; this just proves the loop
        # continues past the crashed fail-open hook to evaluate the next one at all.
        tool_input={"command": "echo hi"},
    )

    assert code == 0
    assert out == ""


# --------------------------------------------------------- non-str patch guard


def test_added_substantive_lines_rejects_non_str_patch() -> None:
    """Load-bearing: a non-str `patch` (e.g. an unexpected JSON shape from the
    compare API) must not crash `_added_substantive_lines` — it should be
    treated as "no substantive lines" instead of raising AttributeError on
    `.splitlines()`. Fails if the `isinstance(patch, str)` guard is reverted."""
    assert rlbt._added_substantive_lines(None) == []
    assert rlbt._added_substantive_lines(123) == []
    assert rlbt._added_substantive_lines(["+not", "+a-string"]) == []
    assert rlbt._added_substantive_lines({"unexpected": "shape"}) == []


def test_added_substantive_lines_still_parses_real_patch() -> None:
    patch = "@@ -1,2 +1,3 @@\n+import os\n+\n+# just a comment\n"
    assert rlbt._added_substantive_lines(patch) == ["import os"]
