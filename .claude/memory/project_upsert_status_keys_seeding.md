---
name: project_upsert_status_keys_seeding
description: upsert_status_keys can't seed an empty {} state file — the first write must be seeded directly in compact multi-line shape.
metadata:
  type: project
---

`upsert_status_keys.main([prog, path, "key=jsonvalue", ...])` does a **text-level** upsert that
preserves the compact-inline shape of the JSON file and validates JSON before AND after. But it
**cannot seed an empty or `{}` file** — it errors "could not locate opening `{` line" / trips a
trailing-comma issue, because it expects the `{\n  "k": v,\n}` multi-line shape with at least
one existing line to anchor against.

**Why it matters:** lifecycle's `persist(path, pairs)` and any first-write to a fresh state
file must handle this — they seed the first write **directly** (via `lifecycle._initial_text(pairs)`,
which emits the compact multi-line shape) and only call the upsert helper once the file is
non-empty (`persist` checks `not load_state(path)` to decide).

**How to apply:** when adding a new caller that may hit a fresh state file, seed-direct on
empty, upsert thereafter. When writing tests, seed the fixture in the multi-line shape — a bare
`{}` will fail the upsert path. Read-back-verify after any upsert (the gh-silent-no-op family:
a silently-failed upsert produces zero diff but exit 0).

Used by [[reference_lifecycle_state_machine]].
