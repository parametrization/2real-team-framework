"""Metric-record schema + rollup (#104 §3) with the #138 record_id fix.

A run emits one **run envelope** containing one **metric record per
(fixture, installer, permutation, metric)** plus a computed **rollup**.

#138 FIX — the join key was ``<bucket>/<installer>/<metric>``, which collides when a single
bucket asserts the same metric across multiple installer permutations (e.g. B4's gate matrix
records ``repo_state_gate_correct`` on both the *refuse* leg and the *proceed* leg). This
harness adds the **permutation discriminant** to the key:

    record_id = "<bucket>/<installer>/<permutation>/<metric>"

so run-over-run diffs (§4) never collide. The colliding 3-part key is never emitted.
Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Metric measurement kinds (#104 §3b).
KIND_PASS_FAIL = "pass_fail"
KIND_SCORED = "scored"   # a number that also carries a pass threshold
KIND_TREND = "trend"     # a number with NO pass/fail, tracked only over time


def make_record_id(bucket: str, installer: str, permutation: str, metric: str) -> str:
    """The stable run-over-run join key WITH the #138 permutation discriminant."""
    return f"{bucket}/{installer}/{permutation}/{metric}"


@dataclass
class MetricRecord:
    """One (fixture × installer × permutation × metric) result — #104 §3b."""

    bucket: str
    fixture: str
    installer: str
    permutation_label: str
    permutation: dict
    metric: str
    category: str
    kind: str
    value: object          # bool for pass_fail; number for scored/trend
    passed: object         # bool for pass_fail/scored; None for pure-trend
    expected: object
    observed: object
    duration_s: float
    timestamp: str
    git_sha: str
    notes: str = ""

    @property
    def record_id(self) -> str:
        return make_record_id(self.bucket, self.installer, self.permutation_label, self.metric)

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "bucket": self.bucket,
            "fixture": self.fixture,
            "installer": self.installer,
            "permutation": self.permutation,
            "metric": self.metric,
            "category": self.category,
            "kind": self.kind,
            "value": self.value,
            "pass": self.passed,
            "expected": self.expected,
            "observed": self.observed,
            "duration_s": round(self.duration_s, 4),
            "timestamp": self.timestamp,
            "git_sha": self.git_sha,
            "notes": self.notes,
        }


def _is_graded(rec: MetricRecord) -> bool:
    """True for pass_fail/scored records (they have a pass/fail); False for pure-trend."""
    return rec.kind in (KIND_PASS_FAIL, KIND_SCORED) and rec.passed is not None


def compute_rollup(records: list[MetricRecord]) -> dict:
    """The §3c/§4a rollup: per-bucket & per-category pass rates, the top-line
    ``install_success_rate`` (metric-level denominator, §4a), ``reinstall_parity_clean``,
    and the scored trend series.
    """
    graded = [r for r in records if _is_graded(r)]

    def _rate(subset: list[MetricRecord]) -> float | None:
        graded_sub = [r for r in subset if _is_graded(r)]
        if not graded_sub:
            return None
        passed = sum(1 for r in graded_sub if r.passed)
        return round(passed / len(graded_sub), 4)

    buckets = sorted({r.bucket for r in records})
    categories = sorted({r.category for r in records})
    per_bucket = {b: _rate([r for r in records if r.bucket == b]) for b in buckets}
    per_category = {c: _rate([r for r in records if r.category == c]) for c in categories}

    install_success_rate = None
    if graded:
        install_success_rate = round(sum(1 for r in graded if r.passed) / len(graded), 4)

    parity = None
    for r in records:
        if r.metric == "reinstall_parity_clean":
            parity = bool(r.passed)

    trend: dict[str, dict[str, float]] = {}
    for r in records:
        if r.kind == KIND_TREND:
            trend.setdefault(r.metric, {})[r.bucket] = round(float(r.value), 4)

    return {
        "per_bucket_pass_rate": per_bucket,
        "per_category_pass_rate": per_category,
        "install_success_rate": install_success_rate,
        "reinstall_parity_clean": parity,
        "trend": trend,
    }


@dataclass
class RunEnvelope:
    """The one-JSON-document-per-run container (#104 §3a)."""

    run_id: str
    git_sha: str
    started_at: str
    finished_at: str
    harness_version: str
    schema_version: int
    host_kind: str
    installers: list[str]
    buckets: list[str]
    records: list[MetricRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "run": {
                "run_id": self.run_id,
                "git_sha": self.git_sha,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "harness_version": self.harness_version,
                "host_kind": self.host_kind,
                "installers": self.installers,
                "buckets": self.buckets,
            },
            "records": [r.to_dict() for r in self.records],
            "rollup": compute_rollup(self.records),
        }
