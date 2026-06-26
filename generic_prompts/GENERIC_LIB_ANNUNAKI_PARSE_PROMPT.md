# Generic Lib Prompt: Filtered Error-Log Reader (genuine-error filter)

## Purpose

Provide a single shared reader over an append-only JSONL **error log** so that
every consumer (a status viewer, an error-processing skill, a metrics counter)
agrees on what counts as a *genuine* error. The raw log accumulates noise:
benign forensic traces, and exit-0 "looks like a failure but isn't" records
where a trigger word merely appeared in echoed output. If each consumer applies
its own ad-hoc filter, the counts diverge and the log over-reports.

The fix is a **reader-side guard** that composes with any writer-side cleanup:
new logs are clean by construction, and historical/mixed logs are cleaned at
read time. Both effects compose, so a consumer never has to know which era a
line came from.

## Reusable Pattern

- **One reader, many consumers.** All tools that read the log import this module
  instead of re-parsing the file. This is the same reader/writer-share-one-module
  discipline used elsewhere to stop classifiers drifting.
- **Single source of truth for the noise taxonomy.** The set of benign-trace
  record *types* is owned by the writer; the reader imports it so writer and
  reader never drift. Keep a small local fallback copy for when the module is
  vendored without the writer present.
- **Two independent exclusion classes**, each individually overridable:
  1. *traces* — records whose `type` is a known benign-trace type.
  2. *low-confidence* — records the monitor tagged `confidence: "low"` (an
     exit-0 match where the signal was in displayed source/output, not a real
     failure). Records with **no** `confidence` field (legacy) are treated as
     genuine and kept — never silently drop history.
- **Defensive parsing.** `.strip()` each line before `json.loads` (manual edits
  leave blank lines), skip corrupt lines, skip non-dict records. The reader must
  never raise on a malformed log.
- **Read-only summarizer always exits 0** — it never fails its caller.

## Algorithm

1. Open the file; a missing file yields nothing (return, don't raise).
2. For each line: strip; skip if empty; `json.loads`; skip on `JSONDecodeError`;
   skip if not a dict.
3. Unless `include_traces`, skip records whose `type` is in the trace-type set.
4. Unless `include_low_confidence`, skip records with `confidence == "low"`.
5. Yield the survivors. `count_errors` is `sum(1 for _ in iter_records(...))`.
6. Provide predicate helpers (`is_trace`, `is_low_confidence`, and any
   sub-category predicate) so a processor can triage a specific class.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Shared reader for an append-only JSONL error log — the genuine-error filter.

Skips blank/corrupt lines, benign forensic traces, and low-confidence
(echoed-output) false positives, so every consumer sees the same genuine-error
set. Read-only; always exits 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path

# The benign-trace record types are owned by the WRITER module; import them so
# reader and writer never drift. Fall back to a local copy if vendored alone.
try:
    _WRITER_DIR = Path(__file__).resolve().parent.parent / "hooks"
    sys.path.insert(0, str(_WRITER_DIR))
    from error_log_writer import TRACE_RECORD_TYPES  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001 — vendored-without-writer fallback
    TRACE_RECORD_TYPES = frozenset({"dispatch_trace", "diagnostic_trace"})


def iter_records(
    path: Path, *, include_traces: bool = False, include_low_confidence: bool = False
) -> Iterator[dict]:
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
                continue
            if not isinstance(rec, dict):
                continue
            if not include_traces and rec.get("type") in TRACE_RECORD_TYPES:
                continue
            if not include_low_confidence and rec.get("confidence") == "low":
                continue
            yield rec


def count_errors(path: Path) -> int:
    return sum(1 for _ in iter_records(path))


def is_trace(record: dict) -> bool:
    return record.get("type") in TRACE_RECORD_TYPES


def is_low_confidence(record: dict) -> bool:
    return record.get("confidence") == "low"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", nargs="?", default="errors.jsonl")
    p.add_argument("--include-traces", action="store_true")
    p.add_argument("--include-low-confidence", action="store_true")
    p.add_argument("--count", action="store_true")
    args = p.parse_args(argv)
    path = Path(args.path)
    if args.count:
        print(count_errors(path))
        return 0
    for rec in iter_records(
        path, include_traces=args.include_traces,
        include_low_confidence=args.include_low_confidence,
    ):
        print(json.dumps(rec, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## Adaptation Notes

- **Define your own noise taxonomy.** The two example trace types are
  placeholders — set them to whatever benign records your writer emits, and own
  that set in ONE place (the writer), imported by the reader.
- **Keep the legacy carve-out.** Records lacking a `confidence` field predate the
  low-confidence tagging; treat them as genuine so historical errors are never
  dropped. This is the safe direction for a count people trust.
- **Add sub-category predicates as the log evolves.** When you introduce a new
  low-confidence sub-class (e.g. a "suspect" category), keep it inside the
  existing low-confidence filter for counting, but expose a predicate so a
  processor can batch-triage just that sub-class.
- **Never let the reader fail the caller.** It is a summarizer wired into status
  views and startup checks; a parse problem must degrade to "skip that line",
  not crash.
```
