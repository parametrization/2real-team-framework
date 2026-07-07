"""Regression tests for the ontology freshness REPORT — the regeneration barrier
in ``ontology_gen.refresh.refresh`` (#141 / #223).

``is_stale`` is a deliberately cheap mtime heuristic: under coarse-granularity or
same-tick filesystem timing (a full-suite run) a source can read as newer than the
just-written index even though nothing changed. The barrier keeps ``is_stale`` cheap
but confirms the *report* against content — a deterministic regenerate that reproduces
the committed index byte-for-byte is reported ``fresh``, not a phantom ``regenerated``.

Stdlib + pytest only; no network. Exercised on a tiny tmp git tree.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "lib"))

from ontology_gen.generate import generate  # noqa: E402
from ontology_gen.refresh import is_stale, refresh  # noqa: E402


def _git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)


def _bump_past_index(src: Path, out: Path, seconds: int = 100) -> None:
    """Force the flaky condition deterministically: make ``src`` land strictly
    newer than the index without touching its content — what a coarse-granularity
    / same-tick mtime collapse looks like under full-suite load."""
    future = (out / "code-graph.json").stat().st_mtime + seconds
    os.utime(src, (future, future))


def test_refresh_reports_fresh_when_regenerate_is_byte_identical(tmp_path: Path) -> None:
    # #141 regression: a source's mtime is newer than the index (so the cheap
    # staleness guard fires) but its content is unchanged. The barrier must report
    # fresh — the deterministic regenerate reproduces the index byte-for-byte.
    _git_init(tmp_path)
    src = tmp_path / "a.py"
    src.write_text("def f():\n    return 1\n", encoding="utf-8")
    out = tmp_path / "ontology" / "structural"
    generate(tmp_path, out, tmp_path.name)
    first = (out / "code-graph.json").read_text(encoding="utf-8")

    _bump_past_index(src, out)
    assert is_stale(tmp_path, out) is True  # cheap heuristic (correctly) sees "newer"

    result = refresh(tmp_path, ontology_path="ontology")
    assert result == {"regenerated": False, "status": "fresh"}
    assert (out / "code-graph.json").read_text(encoding="utf-8") == first


def test_refresh_barrier_does_not_blind_real_staleness(tmp_path: Path) -> None:
    # The barrier must not suppress a GENUINE change: a new symbol alters the graph,
    # so refresh regenerates even though the same mtime signal fired.
    _git_init(tmp_path)
    src = tmp_path / "a.py"
    src.write_text("def f():\n    return 1\n", encoding="utf-8")
    out = tmp_path / "ontology" / "structural"
    generate(tmp_path, out, tmp_path.name)

    src.write_text("def f():\n    return 1\n\n\ndef g():\n    return 2\n", encoding="utf-8")
    _bump_past_index(src, out)

    result = refresh(tmp_path, ontology_path="ontology")
    assert result["regenerated"] is True
    assert result["status"] == "regenerated"


def test_refresh_force_still_reports_regenerated_when_unchanged(tmp_path: Path) -> None:
    # A forced refresh bypasses the barrier: it always reports a regeneration even
    # though the deterministic output is byte-identical.
    _git_init(tmp_path)
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    out = tmp_path / "ontology" / "structural"
    generate(tmp_path, out, tmp_path.name)

    result = refresh(tmp_path, ontology_path="ontology", force=True)
    assert result["regenerated"] is True
