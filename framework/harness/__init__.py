"""Install / test / teardown quality harness (issue #105).

The integration/quality-trend layer on top of the unit suite: it provisions each
repo-type fixture from the #103 taxonomy (``INSTALL_QUALITY_HARNESS.md``), runs the
real installer(s) with the bucket's flag permutation, asserts the #103 metric
vocabulary, tears the fixture down with a residue proof, and emits the #104
metric-record schema (``INSTALL_TEST_METHODOLOGY.md``) plus a human + machine rollup.

This package is **dev/test tooling** — it is NOT part of the installed ``.claude/``
runtime and never ships to a target repo, so it does not affect
``reinstall.py --check`` parity.

Entrypoint::

    python3 -m framework.harness            # default: hermetic B1-B9 + B12 dogfood
    python3 -m framework.harness --include-real   # opt-in B10/B11 (owner-gated, flag off by default)

See ``framework/recipes/INSTALL_QUALITY_HARNESS.md`` and
``framework/recipes/INSTALL_TEST_METHODOLOGY.md``.
"""

from __future__ import annotations

HARNESS_VERSION = "0.1.0"
SCHEMA_VERSION = 1

__all__ = ["HARNESS_VERSION", "SCHEMA_VERSION"]
