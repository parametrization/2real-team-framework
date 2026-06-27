# LIB: lifecycle.py — wave/iteration state machine

## Purpose

Own the lifecycle **state file** (config'd `paths.state_file`, default
`.claude/state.json`) and drive an iteration ("wave") through its phases —
allocate → start → scope → kickoff → wrapup. The product-neutral extraction of
the source project's `wave_seq` + `wave_merge_model` + wave-status counter
writes, collapsed into one stdlib-only lib.

## What it provides

- **Monotonic wave allocator** — a never-resetting `global_wave_seq` so two
  same-ordinal waves in different phases never collide on a `wave_{N}_*` key.
  Genericised: no migration floor (a fresh project's first wave is 1; pass
  `--floor N` to seed higher). Reservation-aware (a `wave_{N}_meta_issue` written
  ahead of the counter is claimed, not skipped).
- **Lifecycle transitions** — `start` / `scope` / `kickoff` / `wrapup` stamp the
  canonical `wave_{W}_*` keys (`_active`, `_started_at`, `_repos_in_scope`,
  `_scope_reconciled_at`, `_phase`, `_kicked_off_at`, `_merge_model`,
  `_final_pr_count`, `_changes_requested_cycles`, `_top_concentration_pct`,
  `_completed_at`) + advance `current_wave` / `last_completed_wave`. Each carries
  an ISO-8601 UTC timestamp (`--at` overrides for determinism).
- **Merge model** — one model per wave (`direct-to-main` | `wave-branch`), with
  `validate_merge_model` (typo-proof) + a pure `classify_reachability` for the
  mid-wave stranding check.

## Commands

```bash
lifecycle.py wave peek                         # next id (no write)
lifecycle.py wave allocate --phase P --write   # advance counter + phase stamps
lifecycle.py wave start    W
lifecycle.py wave scope    W --repos a,b --phase P
lifecycle.py wave kickoff  W --merge-model wave-branch
lifecycle.py wave wrapup   W --pr-count N --cr-cycles C --concentration PCT
lifecycle.py merge-model get|set W [model]
lifecycle.py state path|show
```

## Config keys used

`paths.state_file` (where state lives). The skill layer reads the rest
(`scm.*`, `branch.*`, `labels.wave`, `policy.*`) — the lib itself only touches
the state file, keeping it network-free and unit-testable.

## Persistence contract

Writes go through `upsert_status_keys` (preserving the compact-inline file shape,
JSON-validated before AND after). The FIRST write to an empty/missing file is
seeded directly in that shape (upsert can't seed an empty object — it would leave
a trailing comma), so later upserts extend it cleanly.

## How it composes

`lifecycle.py` is the deterministic core; the `wave-lifecycle` skill is the thin
human-decision layer (theme, repo list, merge model) on top. At wrapup it hands
off to `trust_signals.py` (`extract` → `score`) for the per-engineer mechanical
trust deltas the retro applies.

## Adaptation notes

- **State-file location** — change `paths.state_file` in config; the lib resolves
  it relative to the config root.
- **Phase model** — phase is a *derived display attribute* (`wave_{W}_phase` +
  `_phase_ordinal`), never part of the key. Drop the `--phase` args if your
  project has no phase concept; the allocator still works on bare waves.
- **Reachability I/O** — `classify_reachability` is pure; wrap it with your SCM's
  compare API (`<default>...<wave-branch>` ahead_by/status + open-integration-PR)
  for a mid-wave check. The source project's `wave_merge_model.py` is the
  worked example of that gh wrapper.
