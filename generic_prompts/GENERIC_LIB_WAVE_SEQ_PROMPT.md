# Generic Library Prompt: Global Monotonic Iteration-ID Allocator

## Purpose

When a delivery framework groups work into iterations and the central status file
keys operational data under bare `iteration_{X}_*` keys, a **per-phase iteration
number that resets to 1 each phase** causes a cross-phase key collision: a
same-ordinal iteration in a later phase (Phase 5 / Iteration 2 ↔ Phase 6 /
Iteration 2) writes to the SAME `iteration_2_*` key — a prior phase's values
masquerading as the current iteration's. Papering over it with a per-phase *reset*
of stale keys only cleans up after the collision already bit.

This allocator removes the collision **class** instead: an iteration id is a single
**never-resetting monotonic counter**. A number is never reused, so two
same-ordinal iterations in different phases get DISTINCT ids and therefore DISTINCT
keys — collisions are impossible by construction, and the reset step is retired
(nothing to reset).

The **phase** becomes a *derived display attribute*, never part of the key:
`iteration_{X}_phase` and `iteration_{X}_phase_ordinal` (its 1-based position
within that phase, giving the human-friendly "Phase 6, Iteration 2" framing). The
counter itself is a top-level scalar `global_iteration_seq` = the highest id ever
allocated; `next = global_iteration_seq + 1`.

## Reusable design

### Self-seeding migration (no pre-edit of the live file)

When `global_iteration_seq` is absent, derive a seed = `max(HISTORICAL_FLOOR,
highest existing iteration id in any key)`. Set `HISTORICAL_FLOOR` above every
per-phase number the project ever used, so the first allocated global id clears
both the floor AND any grandfathered key — it can never textually collide with a
legacy `iteration_1..N` key. In-flight iterations keep their existing bare keys
(grandfathered); they are inert because no future id is ever ≤ the floor.

### Reservation-awareness (the subtle bit — keep it)

A retrospective step may *reserve* the next id by writing an
`iteration_{N}_meta_issue` key WITHOUT bumping the committed counter (the counter
stays at N−1) — the id is claimed in the keyspace before the counter advances. A
naive `next = current_seq + 1` then SKIPS the reserved id, because the seed
derivation counts the reserved `iteration_{N}_*` key as already-allocated
(`max(seq=N-1, seed=N) + 1 = N+1`). So the allocator is **reservation-aware**: if
the id one above the *explicit committed counter* already carries an
`iteration_{N}_meta_issue` reservation, claim THAT id rather than incrementing past
it. Consult only the explicit committed counter for this check (NOT the
seed-inflated value, which would re-introduce the skip). This makes the tool
correct regardless of caller ordering — keyspace and counter can never disagree by
construction.

### Phase-ordinal derivation

`phase_ordinal(phase) = 1 + (number of existing iterations stamped to that phase)`.
So the first iteration of a phase is ordinal 1 regardless of its (large) global id.
`phase_of(iteration)` reads `iteration_{X}_phase`, falling back to a scope sub-key.

## Code template (stdlib only)

```python
"""Global monotonic iteration-id allocator for the central status file."""
from __future__ import annotations
import json, re
from pathlib import Path

HISTORICAL_FLOOR = 15                       # > every legacy per-phase number
_KEY_RE = re.compile(r"^iteration_(\d+)_")  # trailing _ → iteration_4_ ≠ iteration_42_


def existing_ids(status: dict) -> set[int]:
    return {int(m.group(1)) for k in status if (m := _KEY_RE.match(k))}


def seed_value(status: dict) -> int:
    return max([HISTORICAL_FLOOR, *existing_ids(status)])


def current_seq(status: dict) -> int:
    v = status.get("global_iteration_seq")
    return max(v, seed_value(status)) if isinstance(v, int) else seed_value(status)


def reserved_id(status: dict) -> int | None:
    committed = status.get("global_iteration_seq")
    if not isinstance(committed, int):
        return None
    cand = committed + 1
    return cand if f"iteration_{cand}_meta_issue" in status else None


def allocation_target(status: dict) -> int:
    r = reserved_id(status)
    return r if r is not None else current_seq(status) + 1


def phase_of(status: dict, it: int) -> int | None:
    v = status.get(f"iteration_{it}_phase")
    if isinstance(v, int):
        return v
    scope = status.get(f"iteration_{it}_scope")
    return scope["phase"] if isinstance(scope, dict) and isinstance(scope.get("phase"), int) else None


def phase_ordinal(status: dict, phase: int) -> int:
    return 1 + sum(1 for it in existing_ids(status) if phase_of(status, it) == phase)
```

A `peek` subcommand prints `allocation_target` (no write). An `allocate
--phase P [--write]` subcommand computes the id + ordinal and, with `--write`,
persists `global_iteration_seq`, `iteration_{X}_phase`, and
`iteration_{X}_phase_ordinal` via the shape-preserving upsert helper (so the status
file's compact-inline shape is kept and the write is JSON-validated either side).

## Adaptation notes

- "iteration/wave" → your cadence unit; "phase" → whatever super-grouping you use
  (epic, quarter, milestone). If you have no super-grouping, drop the phase/ordinal
  stamps and keep just the monotonic counter.
- `HISTORICAL_FLOOR` must sit strictly above every legacy id; set it once when you
  migrate off a resetting scheme.
- The reservation key name (`iteration_{N}_meta_issue`) must match whatever your
  retro/planning step writes to claim the next id. If nothing reserves ahead of the
  counter, `reserved_id` always returns `None` and the allocator is just
  `current_seq + 1`.
- The whole point is that an id is **never reused** — never add a reset path.
