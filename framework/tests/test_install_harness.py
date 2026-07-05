"""Tests for the install/test/teardown quality harness (issue #105).

Covers the harness engine (snapshot, record schema + the #138 record_id fix, rollup, the #139
manifest fail-open bridge, run-over-run comparison, teardown residue, the flavor/portability
metric logic) plus a fast end-to-end run of a hermetic bucket + the B12 dogfood leg through the
REAL installer so the harness itself is regression-covered. Stdlib + pytest only.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _FRAMEWORK_ROOT.parent
sys.path.insert(0, str(_REPO_ROOT))  # make `framework.harness` importable (namespace package)
sys.path.insert(0, str(_FRAMEWORK_ROOT / "install"))  # install_config / manifest siblings

import install_config  # noqa: E402  (framework/install sibling — the resolved-config accessors)

from framework.harness import buckets, compare, manifest, metrics, snapshot, teardown  # noqa: E402
from framework.harness.records import (  # noqa: E402
    MetricRecord,
    RunEnvelope,
    compute_rollup,
    make_record_id,
)
from framework.harness.runner import DEFAULT_HERMETIC, run_matrix  # noqa: E402


# --------------------------------------------------------------- snapshot


def test_snapshot_hashes_files_and_skips_git_internals(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / ".git" / "objects").mkdir(parents=True)
    (tmp_path / ".git" / "objects" / "deadbeef").write_text("blob\n")
    (tmp_path / ".git" / "hooks").mkdir()
    (tmp_path / ".git" / "hooks" / "pre-push").write_text("#!/bin/sh\n")
    snap = snapshot.snapshot(tmp_path)
    assert "a.py" in snap
    assert ".git/hooks/pre-push" in snap          # framework-owned git hook IS captured
    assert ".git/objects/deadbeef" not in snap     # volatile git plumbing is skipped


def test_snapshot_skips_nested_child_git(tmp_path: Path) -> None:
    (tmp_path / "api" / ".git" / "objects").mkdir(parents=True)
    (tmp_path / "api" / ".git" / "objects" / "x").write_text("o\n")
    (tmp_path / "api" / ".git" / "hooks").mkdir()
    (tmp_path / "api" / ".git" / "hooks" / "pre-push").write_text("#!/bin/sh\n")
    snap = snapshot.snapshot(tmp_path)
    assert "api/.git/hooks/pre-push" in snap
    assert "api/.git/objects/x" not in snap


def test_symmetric_diff_and_unexpected_paths() -> None:
    before = {"a": "1", "keep": "9"}
    after = {"keep": "9", ".claude/x": "2", "api/.claude/y": "3", "stray.txt": "4"}
    assert snapshot.added_paths(before, after) == [".claude/x", "api/.claude/y", "stray.txt"]
    # a removed b modified -> symmetric diff picks up a (removed) and the new paths
    assert "a" in snapshot.symmetric_diff(before, after)
    # only stray.txt is outside the framework-owned namespace (child .claude IS owned)
    assert snapshot.unexpected_paths(before, after) == ["stray.txt"]


def test_is_owned_recognises_children_and_claude_md() -> None:
    assert snapshot.is_owned(".claude/settings.json")
    assert snapshot.is_owned("api/.claude/settings.json")
    assert snapshot.is_owned("web/CLAUDE.md.bak")
    assert snapshot.is_owned("svc/ontology/domain.yaml")
    assert not snapshot.is_owned("src/main.py")


# --------------------------------------------------------------- records + #138


def test_record_id_carries_permutation_discriminant() -> None:
    """#138: two legs of the same bucket+metric MUST NOT collide."""
    refuse = make_record_id("B4", "bootstrap", "refuse", "repo_state_gate_correct")
    proceed = make_record_id("B4", "bootstrap", "proceed", "repo_state_gate_correct")
    assert refuse == "B4/bootstrap/refuse/repo_state_gate_correct"
    assert refuse != proceed  # the colliding 3-part key is never produced


def _mk(metric: str, category: str, kind: str, value, passed, *, bucket="B1",
        perm="default", installer="bootstrap") -> MetricRecord:
    return MetricRecord(bucket, "fx", installer, perm, {}, metric, category, kind, value,
                        passed, {}, {}, 0.1, "t", "sha")


def test_rollup_metric_level_success_rate_and_parity() -> None:
    recs = [
        _mk("install_exit_status", "A", "pass_fail", True, True),
        _mk("no_unexpected_files", "B", "pass_fail", 0, True),
        _mk("settings_hooks_wired", "C", "pass_fail", False, False),
        _mk("install_duration_s", "I", "trend", 0.5, None),       # excluded from rate
        _mk("reinstall_parity_clean", "J", "pass_fail", True, True, bucket="B12"),
    ]
    roll = compute_rollup(recs)
    # 4 graded pass_fail across the matrix (settings_hooks_wired fails) -> 3/4; trend excluded.
    assert roll["install_success_rate"] == pytest.approx(3 / 4, abs=1e-3)
    assert roll["reinstall_parity_clean"] is True
    # B1 alone has 3 graded (one fails) -> 2/3
    assert roll["per_bucket_pass_rate"]["B1"] == pytest.approx(2 / 3, abs=1e-3)
    assert roll["trend"]["install_duration_s"]["B1"] == 0.5


def test_run_envelope_serialises_schema() -> None:
    env = RunEnvelope("rid", "sha", "s", "f", "0.1.0", 1, "ci", ["bootstrap"], ["B1"],
                      [_mk("install_exit_status", "A", "pass_fail", True, True)])
    doc = env.to_dict()
    assert doc["schema_version"] == 1
    assert doc["records"][0]["record_id"] == "B1/bootstrap/default/install_exit_status"
    assert "rollup" in doc and "install_success_rate" in doc["rollup"]


# --------------------------------------------------------------- #139 manifest bridge


def test_manifest_bridge_fail_open_when_139_absent() -> None:
    """Until #139 lands, the bridge returns None (metric SKIPS) rather than crashing."""
    if manifest.available():
        # #139 has landed — the real contract must return a set.
        result = manifest.expected_install_set({"model": "single-repo"})
        assert result is None or isinstance(result, set)
    else:
        assert manifest.expected_install_set({"model": "single-repo"}) is None
        assert "pending #139" in manifest.PENDING_NOTE


def test_files_installed_complete_skips_without_manifest(tmp_path: Path) -> None:
    ctx = metrics.CellContext(workdir=tmp_path, installer="bootstrap", permutation={})
    m = metrics.m_files_installed_complete(ctx)
    if not manifest.available():
        assert m.passed is None and "pending #139" in m.notes  # neutral skip, not a fail


# --------------------------------------------------- #139 config-shape seam (the mis-grade fix)


def test_harness_model_map_matches_install_config() -> None:
    """The bridge's model map MUST equal the installer's canonical map (drift guard)."""
    assert manifest._HARNESS_MODEL_TO_INSTALL == install_config.INSTALL_MODEL_MAP


def test_permutation_to_install_config_honors_discriminant() -> None:
    """Regression for the silent mis-grade: the flat permutation must resolve to the NESTED
    install-config shape #139 reads via ``get_key`` — with the discriminant actually applied,
    NOT collapsed to the standalone+team default."""
    default = manifest.permutation_to_install_config({"model": "single-repo", "team": True})
    # read through the EXACT accessor #139 uses:
    assert install_config.get_key(default, "project.model") == "standalone"
    assert install_config.get_key(default, "team.enabled") is True

    child = manifest.permutation_to_install_config({"model": "child", "team": True})
    assert install_config.get_key(child, "project.model") == "child"

    meta = manifest.permutation_to_install_config({"model": "meta-and-children", "team": True})
    assert install_config.get_key(meta, "project.model") == "meta"

    no_team = manifest.permutation_to_install_config({"model": "single-repo", "team": False})
    assert install_config.get_key(no_team, "team.enabled") is False

    # the whole point — a child / no-team permutation is DISTINCT from the standalone+team default
    assert child != default and no_team != default


def test_files_installed_complete_real_wiring_child_differs_from_standalone(tmp_path: Path) -> None:
    """End-to-end through #139's ACTUAL manifest code: prove the nested shape drives distinct
    expected sets per mode (child installs no hooks/lib; no-team drops org-artifacts). Uses the
    real ``framework/install/manifest.py`` if merged, else vendors #139's source from its branch
    so the wiring is proven now — before #139 lands on the base."""
    target = _FRAMEWORK_ROOT / "install" / "manifest.py"
    wrote = False
    if not target.exists():
        src = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "show",
             "origin/N.Rossi/0139-golden-manifest-metric-vocab:framework/install/manifest.py"],
            capture_output=True, text=True,
        )
        if src.returncode != 0:
            pytest.skip("#139 branch not fetched and manifest.py not merged — mapping unit-tested above")
        target.write_text(src.stdout, encoding="utf-8")
        wrote = True
    try:
        importlib.invalidate_caches()
        assert manifest.available()
        standalone = manifest.expected_install_set({"model": "single-repo", "team": True})
        child = manifest.expected_install_set({"model": "child", "team": True})
        no_team = manifest.expected_install_set({"model": "single-repo", "team": False})
        assert standalone and child and no_team
        # a child installs NO hooks of its own; standalone does — the discriminant reaches #139
        assert ".claude/hooks/dispatcher.py" in standalone
        assert ".claude/hooks/dispatcher.py" not in child
        assert child < standalone      # strict subset
        assert no_team < standalone     # team org-artifacts dropped
    finally:
        if wrote:
            target.unlink()
            importlib.invalidate_caches()


# --------------------------------------------------------------- comparison (§4)


def _doc(records, isr, parity=None):
    return {
        "records": [r if isinstance(r, dict) else r.to_dict() for r in records],
        "rollup": {"install_success_rate": isr, "reinstall_parity_clean": parity},
        "run": {"run_id": "r", "finished_at": "2026-01-01T00:00:00Z"},
    }


def test_compare_baseline_then_regression_and_improvement() -> None:
    base = _doc([_mk("settings_hooks_wired", "C", "pass_fail", True, True)], 1.0)
    assert compare.compare(base, None)["verdict"] == "BASELINE"

    worse = _doc([_mk("settings_hooks_wired", "C", "pass_fail", False, False)], 0.0)
    v = compare.compare(worse, base)
    assert v["verdict"] == "REGRESSION" and v["regressions"] == 1

    better = _doc([_mk("settings_hooks_wired", "C", "pass_fail", True, True)], 1.0)
    v2 = compare.compare(better, worse)
    assert v2["verdict"] == "IMPROVEMENT"


def test_compare_trend_budget() -> None:
    base = _doc([_mk("install_duration_s", "I", "trend", 1.0, None)], None)
    slow = _doc([_mk("install_duration_s", "I", "trend", 2.0, None)], None)  # +1.0 > max(.5,.2)
    assert compare.compare(slow, base)["verdict"] == "REGRESSION"
    noise = _doc([_mk("install_duration_s", "I", "trend", 1.1, None)], None)  # +0.1 within budget
    assert compare.compare(noise, base)["verdict"] == "STABLE"


# --------------------------------------------------------------- teardown residue (§2b)


def test_manifest_driven_uninstall_is_zero_residue(tmp_path: Path) -> None:
    (tmp_path / "keep.py").write_text("x = 1\n")
    pre = snapshot.snapshot(tmp_path)
    # simulate an install footprint
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / ".claude" / "hooks" / "dispatcher.py").write_text("# hook\n")
    (tmp_path / "ontology").mkdir()
    (tmp_path / "ontology" / "domain.yaml").write_text("x\n")
    residue = teardown.manifest_driven_uninstall(tmp_path, pre)
    assert residue == []
    assert (tmp_path / "keep.py").is_file()  # untouched


def test_manifest_driven_uninstall_flags_residue_when_backup_missing(tmp_path: Path) -> None:
    (tmp_path / "keep.py").write_text("x = 1\n")
    pre = snapshot.snapshot(tmp_path)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "f").write_text("a\n")
    (tmp_path / "keep.py").write_text("MUTATED\n")  # install clobbered a tracked file
    residue = teardown.manifest_driven_uninstall(tmp_path, pre)
    assert "keep.py" in residue  # modified content is residue vs the pre-install snapshot


# --------------------------------------------------------------- buckets matrix


def test_buckets_matrix_shape_and_real_gating() -> None:
    bs = {b.id: b for b in buckets.build_buckets()}
    assert set(DEFAULT_HERMETIC) <= set(bs)
    assert bs["B10"].real and bs["B11"].real            # real buckets flag-gated
    assert not bs["B1"].real
    # B4 has the two-leg gate matrix with DISTINCT permutation labels (#138 driver)
    labels = {leg.perm_label for leg in bs["B4"].legs}
    assert labels == {"refuse", "proceed"}
    # every metric id referenced by a leg exists in the registry (vocabulary is #103-verbatim)
    for b in bs.values():
        for leg in b.legs:
            for mid in leg.metrics:
                assert mid in metrics.REGISTRY, f"{b.id}/{leg.perm_label}: unknown metric {mid}"


def test_provisioners_synthesize_expected_layout(tmp_path: Path) -> None:
    # The runner mints the workdir (mkdtemp) before calling provision; mirror that here.
    for name, prov in (("b3", buckets._prov_single_lang), ("b8", buckets._prov_adversarial),
                       ("b8b", buckets._prov_invalid_config)):
        (tmp_path / name).mkdir()
        prov(tmp_path / name, {})
    assert (tmp_path / "b3" / "module.py").is_file()
    assert (tmp_path / "b3" / "cli.yaml").is_file()
    assert (tmp_path / "b8" / "ontology" / "structural").is_file()  # a FILE, not a dir
    assert (tmp_path / "b8b" / "bad.config.json").is_file()


def test_real_bucket_provisioner_is_a_guarded_stub(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError, match="pinned SHA"):
        buckets._prov_real_stub(tmp_path, {})


# --------------------------------------------------------------- end-to-end (real installer)


@pytest.mark.parametrize("bucket_id", ["B1", "B8b"])
def test_run_matrix_hermetic_bucket_all_green(bucket_id: str) -> None:
    """A fast hermetic cell driven through the REAL bootstrap installer passes every metric."""
    env = run_matrix({"buckets": [bucket_id], "installers": ["bootstrap"], "dogfood": False})
    doc = env.to_dict()
    graded = [r for r in doc["records"] if r["pass"] is not None
              and r["kind"] in ("pass_fail", "scored")]
    assert graded, "no graded metrics produced"
    failed = [r for r in graded if not r["pass"]]
    assert not failed, f"unexpected failures: {[r['record_id'] for r in failed]}"
    assert doc["rollup"]["install_success_rate"] == 1.0


def test_run_matrix_dogfood_parity_clean() -> None:
    """B12 inline: reinstall --check on this repo is clean and read-only (dual-deploy #116)."""
    env = run_matrix({"buckets": ["B12"], "installers": ["bootstrap"], "dogfood": True})
    b12 = [r for r in env.records if r.bucket == "B12"]
    assert len(b12) == 1
    assert b12[0].metric == "reinstall_parity_clean"
    assert b12[0].passed is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
