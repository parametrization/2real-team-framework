#!/usr/bin/env python3
"""Shared reader for the Annunaki error log — the genuine-error filter (#625).

`/annunaki` (status viewer) and `/annunaki-attack` (processor) both read
`.claude/annunaki/errors.jsonl`. Pre-#625 that file also carried benign
forensic traces (`posttooluse_dispatch`, `pretooluse_diagnostic`) — 76% of the
P4W1 log — and both skills counted them as errors, wildly over-reporting.

The #625 writer-side fix routes those benign traces to a separate
`traces.jsonl`, so a freshly-written `errors.jsonl` is already clean. This
reader is the READER-side guard: it skips blank/corrupt lines AND any record
whose `type` is a benign-trace type, so HISTORICAL logs (mixed pre-#625
content, the `.bak` rotations, a not-yet-cleared live log) are also counted
correctly. Both effects compose: new logs are clean by construction, old logs
are cleaned at read time.

The benign-trace type set is owned by `annunaki_log.TRACE_RECORD_TYPES`; this
module imports it so the writer and reader never drift. If that import fails
(e.g. the lib is vendored without the hook), a local fallback copy keeps the
reader working.

#729 adds a second reader-side exclusion: records the monitor tagged
`confidence: "low"` — exit-0 stdout-only matches where the trigger word is in
echoed output (displayed source `except ImportError:`, a `gh pr view --json`
body), not a real failure. These are excluded from the genuine-error count but
retained in the log for forensics (pass `include_low_confidence=True`). The
genuine exit-0-failure carve-out (a `git push | tail` masking a REJECTED push)
is tagged `confidence: "high"` by the monitor and so is still counted.

#835 widens the low-confidence class (same reader machinery, no change here) to
include the `category: "pipe-mask-suspect"` records — exit-0 stdout-only matches
with no STRONG masked-failure signal that are NOT positively recognized as
echoed content (e.g. a pytest `FAILED` surfacing through `… | tail` rc-masking,
or benign demo output). The P6W16 retro measured that class at 85% false
positive, so the monitor now tags it `confidence: "low"`; it is excluded from
the count by the existing low-confidence filter and retained for forensics. The
`is_pipe_mask_suspect` helper lets callers triage that sub-class specifically.

Exit codes (CLI):
    0 — always (this is a read-only summarizer; it never fails the caller)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path

# Single source of truth for benign-trace record types lives with the writer
# (annunaki_log.py under .claude/hooks/). Import it so reader and writer stay
# in lock-step; fall back to a local copy if the hooks dir isn't importable.
try:
    _HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
    sys.path.insert(0, str(_HOOKS_DIR))
    from annunaki_log import TRACE_RECORD_TYPES  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001 — vendored-without-hooks fallback
    TRACE_RECORD_TYPES = frozenset({"posttooluse_dispatch", "pretooluse_diagnostic"})


def iter_records(
    path: Path, *, include_traces: bool = False, include_low_confidence: bool = False
) -> Iterator[dict]:
    """Yield parsed JSONL records from `path`, skipping blank/corrupt lines.

    By default two sub-classes are skipped so the caller sees only genuine
    errors:
      - records whose `type` is in `TRACE_RECORD_TYPES` (the #625 benign-trace
        filter) — pass `include_traces=True` to keep them;
      - records whose `confidence` is "low" (the #729 exit-0 echoed-output
        false-positive class — a trigger word matched in displayed source/body
        at exit 0) — pass `include_low_confidence=True` to keep them for
        forensics. Records with no `confidence` field (legacy logs written
        before #729) are treated as genuine and kept, so historical errors are
        never silently dropped.

    A missing file yields nothing. Each line is `.strip()`-ed before parsing,
    because the log has historically contained blank lines from manual edits;
    `json.loads("")` would otherwise raise.
    """
    try:
        handle = path.open("r", encoding="utf-8")
    except (FileNotFoundError, OSError):
        return
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # skip corrupt lines
            if not isinstance(rec, dict):
                continue
            if not include_traces and rec.get("type") in TRACE_RECORD_TYPES:
                continue
            if not include_low_confidence and rec.get("confidence") == "low":
                continue
            yield rec


def count_errors(path: Path) -> int:
    """Return the genuine-error count (benign traces AND #729 low-confidence
    echoed-output records excluded)."""
    return sum(1 for _ in iter_records(path))


def is_trace(record: dict) -> bool:
    """True iff `record` is a benign forensic trace, not a genuine error."""
    return record.get("type") in TRACE_RECORD_TYPES


def is_low_confidence(record: dict) -> bool:
    """True iff `record` is a low-confidence class (#729 echoed-output OR #835
    pipe-mask-suspect).

    These are retained in the log for forensics but excluded from the
    genuine-error count by `iter_records`/`count_errors`.
    """
    return record.get("confidence") == "low"


def is_pipe_mask_suspect(record: dict) -> bool:
    """True iff `record` is the #835 exit-0 pipe-mask-suspect class.

    A subset of the low-confidence records: an exit-0 stdout-only match with no
    STRONG masked-failure signal that the monitor could not positively classify
    as echoed content (e.g. a pytest `FAILED` surfacing through `… | tail`
    rc-masking, or benign demo output). Excluded from the genuine-error count
    like all low-confidence records; this helper lets `/annunaki-attack` triage
    the suspect sub-class specifically (e.g. batch-dismiss, or promote a true
    masked failure that slipped through).
    """
    return record.get("category") == "pipe-mask-suspect"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        default=".claude/annunaki/errors.jsonl",
        help="path to errors.jsonl (default: .claude/annunaki/errors.jsonl)",
    )
    parser.add_argument(
        "--include-traces",
        action="store_true",
        help="include benign-trace records in the output/count",
    )
    parser.add_argument(
        "--include-low-confidence",
        action="store_true",
        help="include #729 low-confidence echoed-output records in the output",
    )
    parser.add_argument(
        "--count",
        action="store_true",
        help="print only the genuine-error count and exit",
    )
    args = parser.parse_args(argv)

    path = Path(args.path)
    if args.count:
        print(count_errors(path))
        return 0

    for rec in iter_records(
        path,
        include_traces=args.include_traces,
        include_low_confidence=args.include_low_confidence,
    ):
        print(json.dumps(rec, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
