"""Run-over-run comparison / heuristics (#104 §4).

Joins the current run envelope to a baseline (the previous run for the same matrix, by newest
``finished_at``) on ``record_id`` and classifies each record REGRESSION / IMPROVEMENT / STABLE,
then computes an overall run verdict. Trend metrics use a per-metric budget
``max(0.5s, 0.20 × baseline)`` (§4b proposed default). Stdlib only.
"""

from __future__ import annotations

import json
from pathlib import Path

TREND_ABS_FLOOR_S = 0.5
TREND_REL_FRACTION = 0.20


def _budget(baseline_value: float) -> float:
    return max(TREND_ABS_FLOOR_S, TREND_REL_FRACTION * abs(baseline_value))


def load_baseline(runs_dir: Path, exclude: Path | None = None) -> dict | None:
    """The newest prior run envelope in ``runs_dir`` (by ``run.finished_at``), or None."""
    candidates = []
    for p in sorted(runs_dir.glob("*.json")):
        if exclude and p.resolve() == exclude.resolve():
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        fin = doc.get("run", {}).get("finished_at", "")
        candidates.append((fin, doc))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[-1][1]


def _index(doc: dict) -> dict[str, dict]:
    return {r["record_id"]: r for r in doc.get("records", [])}


def compare(current: dict, baseline: dict | None) -> dict:
    """Classify transitions and return the verdict + per-record diff (#104 §4b/§4c)."""
    cur = _index(current)
    if baseline is None:
        return {
            "verdict": "BASELINE",
            "baseline_run_id": None,
            "transitions": [],
            "new_records": sorted(cur),
            "dropped_records": [],
            "note": "no prior run to compare against — this run becomes the baseline",
        }

    base = _index(baseline)
    transitions: list[dict] = []
    regressions = improvements = 0

    for rid in sorted(set(cur) & set(base)):
        c, b = cur[rid], base[rid]
        kind = c.get("kind")
        if kind == "trend":
            cv, bv = c.get("value"), b.get("value")
            if isinstance(cv, (int, float)) and isinstance(bv, (int, float)):
                delta = cv - bv
                budget = _budget(bv)
                if delta > budget:
                    transitions.append({"record_id": rid, "kind": "trend", "class": "REGRESSION",
                                        "delta": round(delta, 4), "budget": round(budget, 4)})
                    regressions += 1
                elif delta < -budget:
                    transitions.append({"record_id": rid, "kind": "trend", "class": "IMPROVEMENT",
                                        "delta": round(delta, 4), "budget": round(budget, 4)})
                    improvements += 1
            continue
        cp, bp = c.get("pass"), b.get("pass")
        if cp is None or bp is None:
            continue
        if bp and not cp:
            transitions.append({"record_id": rid, "class": "REGRESSION", "from": bp, "to": cp})
            regressions += 1
        elif cp and not bp:
            transitions.append({"record_id": rid, "class": "IMPROVEMENT", "from": bp, "to": cp})
            improvements += 1
        else:
            # scored soft-regression: value degraded even though pass held.
            cv, bv = c.get("value"), b.get("value")
            if c.get("kind") == "scored" and isinstance(cv, (int, float)) and isinstance(bv, (int, float)):
                if (rid.endswith("teardown_residue_zero") and cv > bv) or (
                    rid.endswith("files_installed_complete") and cv < bv
                ):
                    transitions.append({"record_id": rid, "class": "SOFT_REGRESSION",
                                        "from": bv, "to": cv})
                    regressions += 1

    cur_rate = current.get("rollup", {}).get("install_success_rate")
    base_rate = baseline.get("rollup", {}).get("install_success_rate")
    rate_dropped = (
        isinstance(cur_rate, (int, float)) and isinstance(base_rate, (int, float))
        and cur_rate < base_rate
    )
    parity_flipped = (
        baseline.get("rollup", {}).get("reinstall_parity_clean") is True
        and current.get("rollup", {}).get("reinstall_parity_clean") is False
    )

    if regressions or rate_dropped or parity_flipped:
        verdict = "REGRESSION"
    elif improvements:
        verdict = "IMPROVEMENT"
    else:
        verdict = "STABLE"

    return {
        "verdict": verdict,
        "baseline_run_id": baseline.get("run", {}).get("run_id"),
        "install_success_rate": {"current": cur_rate, "baseline": base_rate},
        "regressions": regressions,
        "improvements": improvements,
        "transitions": transitions,
        "new_records": sorted(set(cur) - set(base)),
        "dropped_records": sorted(set(base) - set(cur)),
    }
