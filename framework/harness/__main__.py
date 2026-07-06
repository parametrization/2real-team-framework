"""CLI entrypoint: ``python3 -m framework.harness``.

Runs the install/test/teardown matrix, emits the #104 metric-record JSON to a harness-owned
results dir, prints a human + machine-readable rollup (per-bucket / per-category pass rates,
``install_success_rate``, ``reinstall_parity_clean``, and — when a baseline exists — the
run-over-run verdict), and exits non-zero on any failed graded metric or a REGRESSION verdict
so CI can gate on it. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import HARNESS_VERSION
from .compare import compare, load_baseline
from .records import RunEnvelope
from .runner import run_matrix

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_RUNS_DIR = _FRAMEWORK_ROOT / "tests" / "install_quality" / "runs"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="python3 -m framework.harness",
        description="Install / test / teardown quality harness (#105).",
    )
    ap.add_argument("--buckets", help="comma-separated bucket ids (default: hermetic B1-B9 + B12)")
    ap.add_argument("--installers", default="bootstrap,cli",
                    help="comma-separated installers to run (bootstrap,cli)")
    ap.add_argument("--include-real", action="store_true",
                    help="opt in to the [real] B10/B11 buckets (owner-gated; OFF by default)")
    ap.add_argument("--real-config", type=Path, default=None,
                    help="sidecar JSON overriding the B10/B11 real-fixture source/pin registry "
                         "(see framework.harness.real_provision.RealFixtureSpec)")
    ap.add_argument("--no-dogfood", action="store_true", help="skip the B12 reinstall --check leg")
    ap.add_argument("--scale", type=int, default=None, help="B9 file count (default: 300)")
    ap.add_argument("--out", type=Path, default=_DEFAULT_RUNS_DIR,
                    help="results dir for the run envelope JSON")
    ap.add_argument("--no-write", action="store_true", help="do not persist the run JSON")
    ap.add_argument("--compare", action="store_true",
                    help="diff against the newest prior run in --out and gate on the verdict")
    ap.add_argument("--json", action="store_true", help="print the machine JSON to stdout too")
    ap.add_argument("--quick", action="store_true",
                    help="fast subset (B1,B2,B4,B8b) through bootstrap only — for CI smoke")
    return ap.parse_args(argv)


def _opts(args: argparse.Namespace) -> dict:
    if args.quick:
        buckets = ["B1", "B2", "B4", "B8b"]
        installers = ["bootstrap"]
        dogfood = not args.no_dogfood
    else:
        buckets = [b.strip() for b in args.buckets.split(",")] if args.buckets else None
        installers = [i.strip() for i in args.installers.split(",") if i.strip()]
        dogfood = not args.no_dogfood
    opts: dict = {
        "buckets": buckets,
        "installers": installers,
        "include_real": args.include_real,
        "dogfood": dogfood,
        "host_kind": "local",
    }
    if args.scale is not None:
        opts["scale"] = args.scale
    if args.real_config is not None:
        opts["real_config"] = str(args.real_config)
    return opts


def _fmt_rate(v) -> str:
    return "  -  " if v is None else f"{v:5.2f}"


def print_rollup(env: RunEnvelope) -> None:
    doc = env.to_dict()
    rollup = doc["rollup"]
    graded = [r for r in env.records if r.passed is not None and r.kind in ("pass_fail", "scored")]
    passed = sum(1 for r in graded if r.passed)
    failed = [r for r in graded if not r.passed]
    skipped = [r for r in env.records if r.passed is None and r.kind != "trend"]

    print("\n==================== 2real install-quality harness ====================")
    print(f" run_id: {env.run_id}   harness: v{HARNESS_VERSION}   sha: {env.git_sha[:7]}")
    print(f" buckets: {', '.join(env.buckets)}")
    print(f" installers: {', '.join(env.installers)}")
    print("-----------------------------------------------------------------------")
    print(" per-bucket pass rate:")
    for b, v in rollup["per_bucket_pass_rate"].items():
        print(f"   {b:5s} {_fmt_rate(v)}")
    print(" per-category pass rate (A-J):")
    cats = "  ".join(f"{c}:{_fmt_rate(v).strip()}" for c, v in rollup["per_category_pass_rate"].items())
    print(f"   {cats}")
    print("-----------------------------------------------------------------------")
    isr = rollup["install_success_rate"]
    print(f" install_success_rate : {_fmt_rate(isr).strip()}  ({passed}/{len(graded)} graded metrics)")
    print(f" reinstall_parity_clean: {rollup['reinstall_parity_clean']}")
    if rollup["trend"]:
        print(" trend (seconds):")
        for metric, series in rollup["trend"].items():
            pairs = ", ".join(f"{b}={s}" for b, s in series.items())
            print(f"   {metric}: {pairs}")
    if failed:
        print("-----------------------------------------------------------------------")
        print(f" FAILURES ({len(failed)}):")
        for r in failed:
            print(f"   FAIL  {r.record_id}")
            print(f"         observed: {json.dumps(r.observed)[:300]}")
    if skipped:
        print(f" skipped/pending: {len(skipped)} "
              f"(e.g. {', '.join(sorted({r.metric for r in skipped}))[:120]})")
    print("=======================================================================")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    opts = _opts(args)

    env = run_matrix(opts)
    doc = env.to_dict()

    out_path = None
    if not args.no_write:
        args.out.mkdir(parents=True, exist_ok=True)
        out_path = args.out / f"{env.run_id}.json"
        out_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    print_rollup(env)
    if out_path:
        print(f" wrote: {out_path}")

    verdict = None
    if args.compare:
        baseline = load_baseline(args.out, exclude=out_path)
        cmp = compare(doc, baseline)
        verdict = cmp["verdict"]
        print(f" run-over-run verdict: {verdict}"
              + (f"  (baseline {cmp['baseline_run_id']})" if cmp.get("baseline_run_id") else ""))
        for t in cmp.get("transitions", []):
            print(f"   {t.get('class')}: {t['record_id']}")

    if args.json:
        print(json.dumps(doc, indent=2))

    graded = [r for r in env.records if r.passed is not None and r.kind in ("pass_fail", "scored")]
    any_fail = any(not r.passed for r in graded)
    if verdict == "REGRESSION":
        return 1
    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
