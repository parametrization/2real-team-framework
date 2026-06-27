#!/usr/bin/env python3
"""Tests for the shared wave-label parser `_wave_label_parse` (#810).

Covers the three accepted label forms across the public surface:
  - legacy phase-prefixed `p{N}-wave-{M}` (grandfathered)
  - phase-agnostic global `wave-{X}`
  - placeholder `wave-x`

Run: python3 -m pytest .claude/hooks/tests/test__wave_label_parse.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HOOKS_DIR))

import _wave_label_parse as p  # noqa: E402


class IsWaveLabel(unittest.TestCase):
    def test_legacy_form_true(self) -> None:
        self.assertTrue(p.is_wave_label("p6-wave-16"))
        self.assertTrue(p.is_wave_label("p3-wave-10"))

    def test_global_form_true(self) -> None:
        self.assertTrue(p.is_wave_label("wave-16"))
        self.assertTrue(p.is_wave_label("wave-1"))

    def test_placeholder_true(self) -> None:
        self.assertTrue(p.is_wave_label("wave-x"))

    def test_suffixed_false(self) -> None:
        """Anchored: a trailing segment defeats the match for every form."""
        self.assertFalse(p.is_wave_label("p3-wave-10-special"))
        self.assertFalse(p.is_wave_label("wave-10-frozen"))
        self.assertFalse(p.is_wave_label("wave-x-tbd"))

    def test_junk_false(self) -> None:
        for v in (
            "",
            "wave-",
            "wave",
            "wave-X",
            "Wave-16",
            "WAVE-16",
            "p6-wave-",
            "bug",
            "wave-1x",
        ):
            with self.subTest(v=v):
                self.assertFalse(p.is_wave_label(v))


class ParseWaveLabelSpec(unittest.TestCase):
    def test_legacy(self) -> None:
        spec = p.parse_wave_label_spec("p6-wave-16")
        assert spec is not None
        self.assertEqual((spec.phase, spec.wave, spec.is_placeholder), (6, 16, False))
        self.assertEqual(spec.raw, "p6-wave-16")

    def test_global(self) -> None:
        spec = p.parse_wave_label_spec("wave-16")
        assert spec is not None
        self.assertEqual((spec.phase, spec.wave, spec.is_placeholder), (None, 16, False))

    def test_placeholder(self) -> None:
        spec = p.parse_wave_label_spec("wave-x")
        assert spec is not None
        self.assertEqual((spec.phase, spec.wave, spec.is_placeholder), (None, None, True))

    def test_invalid_returns_none(self) -> None:
        for v in ("", "wave-X", "p6-wave-16-x", "bug"):
            with self.subTest(v=v):
                self.assertIsNone(p.parse_wave_label_spec(v))


class ParseWaveLabelLegacyOnly(unittest.TestCase):
    """parse_wave_label is legacy-form-only by contract (its tuple has no None phase)."""

    def test_legacy_returns_tuple(self) -> None:
        self.assertEqual(p.parse_wave_label("p6-wave-16"), (6, 16))

    def test_new_forms_return_none(self) -> None:
        self.assertIsNone(p.parse_wave_label("wave-16"))
        self.assertIsNone(p.parse_wave_label("wave-x"))


class WaveLabelToOptionName(unittest.TestCase):
    def test_legacy_maps_to_PNWM(self) -> None:
        self.assertEqual(p.wave_label_to_option_name("p6-wave-16"), "P6W16")
        self.assertEqual(p.wave_label_to_option_name("p3-wave-10"), "P3W10")

    def test_global_maps_to_WX(self) -> None:
        self.assertEqual(p.wave_label_to_option_name("wave-16"), "W16")

    def test_placeholder_maps_to_WX_literal(self) -> None:
        self.assertEqual(p.wave_label_to_option_name("wave-x"), "WX")

    def test_invalid_returns_none(self) -> None:
        self.assertIsNone(p.wave_label_to_option_name("bug"))
        self.assertIsNone(p.wave_label_to_option_name("wave-10-frozen"))


class ParseChangesAcceptsNewForms(unittest.TestCase):
    """The gh-command parsers accept new label forms via the shared grammar."""

    def test_edit_add_global_form(self) -> None:
        changes = p.parse_wave_label_changes(
            'gh issue edit 42 --repo noorinalabs/noorinalabs-main --add-label "wave-16"'
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].add_label, "wave-16")
        self.assertEqual(changes[0].issue_number, "42")

    def test_edit_remove_placeholder(self) -> None:
        changes = p.parse_wave_label_changes(
            'gh issue edit 42 --repo noorinalabs/noorinalabs-main --remove-label "wave-x"'
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].remove_label, "wave-x")

    def test_relabel_both_new_forms(self) -> None:
        change = p.parse_wave_label_change(
            "gh issue edit 42 --repo noorinalabs/noorinalabs-main "
            '--add-label "wave-16" --remove-label "wave-15"'
        )
        assert change is not None
        self.assertEqual(change.add_label, "wave-16")
        self.assertEqual(change.remove_label, "wave-15")

    def test_create_global_form(self) -> None:
        creates = p.parse_wave_label_create(
            'gh issue create --repo noorinalabs/noorinalabs-main --title t --label "wave-16"'
        )
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0].add_label, "wave-16")

    def test_create_placeholder_form(self) -> None:
        creates = p.parse_wave_label_create(
            'gh issue create --repo noorinalabs/noorinalabs-main --title t --label "wave-x"'
        )
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0].add_label, "wave-x")

    def test_legacy_still_parses(self) -> None:
        """Grandfather: legacy form still parses unchanged."""
        changes = p.parse_wave_label_changes(
            'gh issue edit 42 --repo noorinalabs/noorinalabs-main --add-label "p6-wave-16"'
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].add_label, "p6-wave-16")


if __name__ == "__main__":
    unittest.main()
