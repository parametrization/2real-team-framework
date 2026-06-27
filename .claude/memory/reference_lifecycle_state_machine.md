---
name: reference_lifecycle_state_machine
description: lifecycle.py — the generic wave/iteration state machine (monotonic allocator, merge models, reachability classifier, transitions + CLI).
metadata:
  type: reference
---

`framework/assets/lib/lifecycle.py` (~560 lines, stdlib-only) genericises the essence of
noorinalabs' `wave_seq` + `wave_merge_model` + `wave_status` into one config-driven state
machine over a JSON state file. It imports `_framework_config.config` and
`upsert_status_keys.main` via the lib→hooks bridge.

**Monotonic wave allocator** — `global_wave_seq` never resets; phase is a derived display
attribute (`wave_{X}_phase` / `_phase_ordinal`). Allocation is reservation-aware:
`wave_{N}_meta_issue` is treated as claimed, not skipped. Key fns: `existing_wave_numbers`,
`seed_value(floor=0)`, `current_seq`, `next_global_wave`, `reserved_wave`, `allocation_target`,
`phase_of`, `phase_ordinal`.

**Merge models** — `direct-to-main` | `wave-branch`; `validate_merge_model` /
`read_merge_model`. (Squashing per-author commits into an integration branch loses authorship
under enforced identity — that's why [[reference_per_child_union_rosters]]'s identity gate and
the `block_squash_wave_merge` hook exist.)

**Reachability classifier** — `classify_reachability(model, *, branch_exists, ahead_by, status,
open_integration_pr)` → `OK` | `ADVISORY` | `VIOLATION`. The deferred mid-wave `gh` wrapper
would feed this.

**Transitions:** `start_wave` / `scope_wave` / `kickoff_wave` / `wrapup_wave`.
**Persistence:** `persist(path, pairs)` seeds-direct when the state file is empty, else
upserts — see [[project_upsert_status_keys_seeding]] for why empty `{}` can't be upserted.

**CLI subcommands:** `wave peek|allocate|start|scope|kickoff|wrapup`, `merge-model get|set`,
`state path|show`. Driven by the `wave-lifecycle` skill alongside `trust_signals.py`.
