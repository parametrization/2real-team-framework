"""Tests for the check-mermaid raw-angle footgun heuristic (#797).

The mermaid render gate (`scripts/check-mermaid.py`) prints an advisory warning
when a fenced block carries a raw `<`/`>` in a label (which renders degraded —
the #786 `<unset>` class). #797: the heuristic false-warned on valid HTML break
tags (`<br/>`), which mermaid renders fine inside multi-line labels, because the
closing `>` of the break tag matched. These tests pin both directions:

  (a) a label with `<br>`/`<br/>`/`<br />` does NOT warn;
  (b) a genuinely raw/unescaped angle bracket still warns; and
  (c) mermaid edge tokens (`-->`, `<--`, `==>`) never warn.

The script is loaded by file path because its name is hyphenated (not an
importable module) and it lives under scripts/, not .claude/lib/.
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check-mermaid.py"
_spec = importlib.util.spec_from_file_location("check_mermaid", _SCRIPT)
assert _spec is not None and _spec.loader is not None
check_mermaid = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_mermaid)

_has_raw_angle = check_mermaid._has_raw_angle


class WorkdirBaseIsSnapReadable(unittest.TestCase):
    """#817: the render scratch dir must be anchored under a snap-readable base
    ($HOME), never cwd-relative. A cwd under /tmp put the old `dir="."` scratch
    tree inside the mmdc snap's private /tmp namespace → "Input file doesn't
    exist" for every block. These tests pin that the base is absolute, under
    $HOME when HOME is set, and never the cwd marker `.`.
    """

    def _with_home(self, home: str | None) -> str:
        old = os.environ.get("HOME")
        if home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = home
        try:
            return check_mermaid._workdir_base()
        finally:
            if old is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old

    def test_anchors_under_home_not_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            base = self._with_home(home)
            self.assertEqual(os.path.realpath(base), os.path.realpath(home))

    def test_base_is_absolute_never_cwd_relative(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            base = self._with_home(home)
        self.assertTrue(os.path.isabs(base))
        self.assertNotEqual(base, ".")
        self.assertFalse(base.startswith("."))


class BreakTagsDoNotWarn(unittest.TestCase):
    def test_self_closing_br(self) -> None:
        self.assertFalse(_has_raw_angle("flowchart TD\n  A[line one<br/>line two]"))

    def test_bare_br(self) -> None:
        self.assertFalse(_has_raw_angle("flowchart TD\n  A[line one<br>line two]"))

    def test_spaced_br(self) -> None:
        self.assertFalse(_has_raw_angle("flowchart TD\n  A[line one<br />line two]"))

    def test_uppercase_br(self) -> None:
        self.assertFalse(_has_raw_angle("flowchart TD\n  A[line one<BR/>line two]"))

    def test_multiple_brs_in_one_label(self) -> None:
        self.assertFalse(_has_raw_angle("flowchart TD\n  A[a<br/>b<br/>c]"))


class GenuineRawAngleStillWarns(unittest.TestCase):
    def test_unset_class_opening_angle(self) -> None:
        # The #786 footgun: a literal `<` in a label renders as a degraded HTML tag.
        self.assertTrue(_has_raw_angle("flowchart TD\n  A[state: <unset>]"))

    def test_raw_angle_alongside_a_valid_br(self) -> None:
        # A break tag must not mask a genuine raw bracket elsewhere in the block.
        self.assertTrue(_has_raw_angle("flowchart TD\n  A[ok<br/>then <unset>]"))

    def test_lone_greater_than(self) -> None:
        self.assertTrue(_has_raw_angle("flowchart TD\n  A[count > 5]"))


class EdgeTokensDoNotWarn(unittest.TestCase):
    def test_forward_arrow(self) -> None:
        self.assertFalse(_has_raw_angle("flowchart TD\n  A --> B"))

    def test_reverse_arrow(self) -> None:
        self.assertFalse(_has_raw_angle("flowchart TD\n  A <-- B"))

    def test_thick_arrow(self) -> None:
        self.assertFalse(_has_raw_angle("flowchart TD\n  A ==> B"))

    def test_dotted_arrow(self) -> None:
        self.assertFalse(_has_raw_angle("flowchart TD\n  A -.-> B"))


if __name__ == "__main__":
    unittest.main()
