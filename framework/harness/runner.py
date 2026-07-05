"""Orchestration: provision → install → assert → teardown per cell (#104 §1).

Drives every (bucket, installer, permutation) cell mechanically: mint a disposable tmp
workdir, synthesize the fixture, capture the pre-install snapshot, run the real installer,
run whatever auxiliary invocations the applicable metrics require (a second run for
idempotency, a --dry-run leg, fired-hook payloads, a manifest-driven teardown proof),
measure each metric into a record, then drop the copy. Failures are isolated per cell — a
crash in one fixture becomes failing/error records, never a harness abort. Stdlib only.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import HARNESS_VERSION, SCHEMA_VERSION, installers
from .buckets import B12_METRIC, Bucket, Leg, build_buckets
from .metrics import REGISTRY, CellContext, Measurement
from .records import MetricRecord, RunEnvelope
from .snapshot import snapshot, symmetric_diff
from .teardown import manifest_driven_uninstall

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _FRAMEWORK_ROOT.parent

#: Metrics that are meaningful only for the standalone bootstrap installer, not the CLI bridge
#: (the CLI forwards --no-team so identity is off; it fixes shell=bash; and re-running it
#: re-scaffolds the team, so idempotency/dry-run/teardown are asserted through bootstrap).
_CLI_SKIP = frozenset({
    "identity_gate_active", "reinstall_idempotent", "dry_run_writes_nothing",
    "teardown_residue_zero", "shell_gate_respected", "config_module_lists_complete",
})

DEFAULT_HERMETIC = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B7b", "B8", "B8b", "B9"]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def _claude_only(snap: dict) -> dict:
    return {k: v for k, v in snap.items() if k.startswith(".claude/")}


def _install(installer: str, target: Path, flags: list[str]) -> installers.RunResult:
    if installer == "cli":
        return installers.run_cli(target, flags)
    return installers.run_bootstrap(target, flags)


def _collect_child_settings(target: Path, children: list[dict]) -> None:
    """Read each child's post-install settings.json into its descriptor (for the G metrics)."""
    for c in children:
        sp = target / c["path"] / ".claude" / "settings.json"
        c["settings_text"] = sp.read_text(encoding="utf-8") if sp.is_file() else ""


def _valid_commit_prefix(target: Path) -> str:
    """A ``git -c user.name=.. -c user.email=..`` prefix using a roster identity, if the
    identity gate is active — so the no-verify SCM gate (not the identity gate) is what a
    ``--no-verify`` commit trips. Empty when there is no roster (identity off)."""
    import json as _json

    roster = target / ".claude" / "team" / "roster.json"
    if not roster.is_file():
        return ""
    try:
        data = _json.loads(roster.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if isinstance(data, dict) and data:
        name, email = next(iter(data.items()))
        return f'git -c user.name="{name}" -c user.email="{email}" '
    return ""


def _fire_hooks(target: Path, metric_ids: set[str]) -> dict:
    fired: dict = {}
    if "gate_blocks_no_verify" in metric_ids:
        prefix = _valid_commit_prefix(target)
        cmd = (prefix + "commit --no-verify -m x") if prefix else "git commit --no-verify -m x"
        fired["no_verify"] = installers.fire_hook(target, cmd)
    if "gate_passes_benign" in metric_ids:
        fired["benign"] = installers.fire_hook(target, "ls -la")
    if "shell_gate_respected" in metric_ids:
        fired["bashism"] = installers.fire_hook(
            target, 'for k in "${!arr[@]}"; do echo $k; done'
        )
    if "identity_gate_active" in metric_ids:
        fired["foreign_commit"] = installers.fire_hook(
            target, 'git commit -m "unattributed"'
        )
    return fired


def _measure(metric_id: str, ctx: CellContext) -> Measurement:
    spec = REGISTRY[metric_id]
    try:
        return spec.fn(ctx)
    except Exception as exc:  # noqa: BLE001 — a metric bug must not abort the run
        return Measurement(None, False, {"measured": True},
                           {"error": f"{type(exc).__name__}: {exc}"},
                           notes="metric raised — see observed.error")


def _record(bucket: Bucket, leg: Leg, installer: str, metric_id: str, m: Measurement,
            ctx: CellContext, git_sha: str, duration_s: float) -> MetricRecord:
    spec = REGISTRY[metric_id]
    return MetricRecord(
        bucket=bucket.id, fixture=bucket.label, installer=installer,
        permutation_label=leg.perm_label, permutation=leg.permutation, metric=metric_id,
        category=spec.category, kind=spec.kind, value=m.value, passed=m.passed,
        expected=m.expected, observed=m.observed, duration_s=duration_s,
        timestamp=_now(), git_sha=git_sha, notes=m.notes,
    )


def run_cell(bucket: Bucket, leg: Leg, installer: str, opts: dict, scratch: Path,
             git_sha: str) -> list[MetricRecord]:
    """Provision → install → (aux) → assert → teardown one cell; return its metric records."""
    metric_ids = [m for m in leg.metrics if not (installer == "cli" and m in _CLI_SKIP)]
    metric_set = set(metric_ids)

    workdir = Path(tempfile.mkdtemp(prefix=f"harness-{bucket.id}-{installer}-", dir=str(scratch)))
    try:
        fixture = bucket.provision(workdir, opts)
        target = workdir / leg.target_subdir
        target.mkdir(parents=True, exist_ok=True)

        before = snapshot(target)
        flags = (leg.cli_flags or leg.build_flags)(workdir) if installer == "cli" \
            else leg.build_flags(workdir)
        primary = _install(installer, target, flags)
        after = snapshot(target)

        ctx = CellContext(
            workdir=target, installer=installer, permutation=leg.permutation,
            expect_exit=leg.expect_exit, gate_expect=leg.gate_expect, primary=primary,
            before=before, after=after,
            preexisting=fixture.get("preexisting", {}),
            child=fixture.get("child", {}), extra=fixture.get("extra", {}),
        )

        # child settings (G metrics)
        if ctx.child.get("children"):
            _collect_child_settings(target, ctx.child["children"])

        # aux: second run for idempotency (byte-diff of .claude), bootstrap only
        if "reinstall_idempotent" in metric_set and installer == "bootstrap":
            claude1 = _claude_only(after)
            ctx.reinstall = _install(installer, target, flags)
            claude2 = _claude_only(snapshot(target))
            ctx.reinstall_diff = symmetric_diff(claude1, claude2)

        # aux: dry-run leg on a FRESH copy (target must be byte-identical after)
        if "dry_run_writes_nothing" in metric_set and installer == "bootstrap":
            ctx.dry_run, ctx.dry_run_unchanged = _dry_run_leg(bucket, leg, opts, scratch)

        # aux: fired-hook payloads
        if metric_set & {"gate_blocks_no_verify", "gate_passes_benign",
                         "shell_gate_respected", "identity_gate_active"}:
            ctx.fired = _fire_hooks(target, metric_set)

        # aux: manifest-driven teardown PROOF on a fresh copy (bootstrap only)
        if "teardown_residue_zero" in metric_set and leg.teardown_proof and installer == "bootstrap":
            ctx.teardown_residue = _teardown_proof_leg(bucket, leg, opts, scratch)

        records: list[MetricRecord] = []
        for mid in metric_ids:
            if mid not in REGISTRY:
                continue
            dur = primary.duration_s if mid in ("install_duration_s", "ontology_gen_duration_s") else 0.0
            m = _measure(mid, ctx)
            records.append(_record(bucket, leg, installer, mid, m, ctx, git_sha, dur))
        return records
    except NotImplementedError as exc:
        # A flag-gated / stubbed provisioner (B10/B11). Emit one skipped record, do not crash.
        spec_metric = leg.metrics[0]
        return [MetricRecord(
            bucket.id, bucket.label, installer, leg.perm_label, leg.permutation, spec_metric,
            REGISTRY.get(spec_metric).category if spec_metric in REGISTRY else "A",
            REGISTRY.get(spec_metric).kind if spec_metric in REGISTRY else "pass_fail",
            None, None, {"stub": True}, {"reason": str(exc)}, 0.0, _now(), git_sha,
            notes="flag-gated / stubbed provisioner",
        )]
    except Exception as exc:  # noqa: BLE001 — isolate a provisioning/install failure to this cell
        return [MetricRecord(
            bucket.id, bucket.label, installer, leg.perm_label, leg.permutation,
            "install_exit_status", "A", "pass_fail", None, False,
            {"cell_ran": True},
            {"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-800:]},
            0.0, _now(), git_sha, notes="cell raised during provision/install",
        )]
    finally:
        shutil.rmtree(workdir, ignore_errors=True)  # drop-the-copy teardown (§2a)


def _dry_run_leg(bucket: Bucket, leg: Leg, opts: dict, scratch: Path):
    wd = Path(tempfile.mkdtemp(prefix=f"harness-{bucket.id}-dry-", dir=str(scratch)))
    try:
        bucket.provision(wd, opts)
        target = wd / leg.target_subdir
        target.mkdir(parents=True, exist_ok=True)
        before = snapshot(target)
        flags = [*leg.build_flags(wd), "--dry-run"]
        r = installers.run_bootstrap(target, flags)
        unchanged = snapshot(target) == before
        return r, unchanged
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def _teardown_proof_leg(bucket: Bucket, leg: Leg, opts: dict, scratch: Path) -> list[str]:
    wd = Path(tempfile.mkdtemp(prefix=f"harness-{bucket.id}-teardown-", dir=str(scratch)))
    try:
        bucket.provision(wd, opts)
        target = wd / leg.target_subdir
        target.mkdir(parents=True, exist_ok=True)
        pre = snapshot(target)
        installers.run_bootstrap(target, leg.build_flags(wd))
        return manifest_driven_uninstall(target, pre)
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def _run_b12(git_sha: str) -> MetricRecord:
    """B12 dogfood: read-only reinstall --check on THIS repo (no fixture, no teardown)."""
    before = subprocess.run(["git", "-C", str(_REPO_ROOT), "status", "--porcelain"],
                            capture_output=True, text=True).stdout
    r = installers.run_reinstall_check()
    after = subprocess.run(["git", "-C", str(_REPO_ROOT), "status", "--porcelain"],
                           capture_output=True, text=True).stdout
    ctx = CellContext(workdir=_REPO_ROOT, installer="bootstrap",
                      permutation={"dogfood": True, "read_only": True}, primary=r)
    m = _measure(B12_METRIC, ctx)
    if before != after:  # the read-only guard: --check must not touch the working tree
        m = Measurement(False, False, {"working_tree": "unchanged"},
                        {"working_tree": "MUTATED by --check", **(m.observed or {})})
    spec = REGISTRY[B12_METRIC]
    return MetricRecord(
        bucket="B12", fixture="self-host-dogfood", installer="bootstrap",
        permutation_label="dogfood", permutation={"dogfood": True, "read_only": True},
        metric=B12_METRIC, category=spec.category, kind=spec.kind, value=m.value,
        passed=m.passed, expected=m.expected, observed=m.observed, duration_s=r.duration_s,
        timestamp=_now(), git_sha=git_sha, notes=m.notes,
    )


def run_matrix(opts: dict | None = None) -> RunEnvelope:
    """Run the full matrix and return the populated run envelope."""
    opts = dict(opts or {})
    started = _now()
    git_sha = _git_sha()
    scratch = Path(opts.get("scratch") or tempfile.mkdtemp(prefix="harness-scratch-"))
    scratch.mkdir(parents=True, exist_ok=True)

    want_buckets = opts.get("buckets") or DEFAULT_HERMETIC
    want_installers = opts.get("installers") or ["bootstrap", "cli"]
    include_real = bool(opts.get("include_real"))

    all_buckets = {b.id: b for b in build_buckets()}
    records: list[MetricRecord] = []
    ran_buckets: list[str] = []
    ran_installers: set[str] = set()

    for bid in want_buckets:
        bucket = all_buckets.get(bid)
        if bucket is None:
            continue
        if bucket.real and not include_real:
            continue  # flag-gated OFF by default (owner-decision 1)
        ran_buckets.append(bid)
        for leg in bucket.legs:
            for installer in leg.installers:
                if installer not in want_installers:
                    continue
                ran_installers.add(installer)
                records.extend(run_cell(bucket, leg, installer, opts, scratch, git_sha))

    # B12 dogfood inline (read-only reinstall --check on this repo), unless excluded.
    if opts.get("dogfood", True) and (not opts.get("buckets") or "B12" in want_buckets):
        records.append(_run_b12(git_sha))
        ran_buckets.append("B12")

    if opts.get("cleanup_scratch", True) and not opts.get("scratch"):
        shutil.rmtree(scratch, ignore_errors=True)

    return RunEnvelope(
        run_id=f"{started}-{git_sha[:7]}", git_sha=git_sha, started_at=started,
        finished_at=_now(), harness_version=HARNESS_VERSION, schema_version=SCHEMA_VERSION,
        host_kind=opts.get("host_kind", "local"),
        installers=sorted(ran_installers) or list(want_installers),
        buckets=ran_buckets, records=records,
    )
