# Phase 4 — Self-hosting & quality machinery

created: 2026-07-05

## Goal
Make the framework trustworthy when run on itself. Phase 3 shipped the installer (v0.4.0),
but the reconstructed Phase 3 retro (2026-07-05) proved the quality machinery is broken:
trust scoring is blind to the project's own review vocabulary, and the lifecycle state
machine was never dogfooded (no `state.json` — the retro required a manual backfill). Phase 4
closes that gap and drains the tech-debt backlog before phase exit.

## Exit criteria
1. A wave can be scored mechanically end-to-end with **zero manual tally**.
2. `state.json` is written **live** by the wave skills (/wave-start, /wave-end).
3. Retros need no backfill.
4. Tech-debt backlog drained to ≤ the configured exit ratio (`policy.tech_debt_exit_ratio_pct`).

## Wave structure
Tech-debt intake: Wave 1 is theme-aligned (the machinery fixes *are* tech-debt). Wave 2 is the
last wave of the phase → the intake percentage becomes a **floor**: pull the entire remaining
tech-debt backlog to clear it before exit.

### Wave 1 — Trustworthy scoring & lifecycle (foundational machinery)
| Issue | Title | Assignee | Type | Dependencies |
|-------|-------|----------|------|--------------|
| #100 | `branch.integration` phase-aware (`{phase}` token) | Ibrahim El-Amin | tech-debt | None (foundational) |
| #98 | Fix `trust_signals.py` verdict vocabulary ↔ charter | Paloma Gupta | tech-debt | soft: #111 (canonical shape) |
| #111 | Port `validate_review_comment_format` hook | Tariq Morales | enhancement | None (defines the shape) |
| #99 | Dogfood lifecycle: wire `lifecycle.py` into /wave-start + /wave-end | Nia Rossi | tech-debt | None |

### Wave 2 — Self-consistency & tech-debt floor (last wave of phase)
| Issue | Title | Assignee | Type | Dependencies |
|-------|-------|----------|------|--------------|
| #94 | Reconcile `merge_model` config vs wave-branch practice | Tariq Morales | tech-debt | soft: #99 |
| #90 | wave-audit: zero-padded issue-number matching | Ibrahim El-Amin | tech-debt | None |
| #77 | Charter `--force` refresh clobbers hand-evolved edits | Nia Rossi | tech-debt | None |
| #82 | `copy-shared.js` skip-if-exists ships stale bundle | Nia Rossi | tech-debt | None |
| #74 | `ontology_gen` indexes installed runtime (index noise) | Ibrahim El-Amin | tech-debt | None |
| #75 | Test coverage for meta+children ontology gen at install | Tariq Morales | tech-debt | None |

**Total:** 11 issues (1 net-new: #111) · **Waves:** 2
**Load:** Ibrahim 3, Nia 3, Tariq 3, Paloma 1 (#98 is the deepest single item).

## Origin of scope
- Retro findings (2026-07-05): #98, #99, #100 — see `feedback_log.md` Wave 1 retro entry.
- Carried-forward Phase 3 tech-debt: #74, #75, #77, #82, #90, #94.
- #111: targeted pull from the deferred review-gate tranche (companion to #98).

## Deferred / out of scope for Phase 4
Created 2026-07-05 as unscheduled backlog (to be planned in a later phase) — six exploratory
threads + follow-ups: #101/#102 (reverse-map noorinalabs-main process), #103/#104/#105
(installation testing on representative repos), #109 (botfarm_inc before/after), #106/#107
(user-space audit + consented user-level install), #108 (repo-level consent/backup/restore
pattern), #110 (publish/install as a Claude Code skill). The full review-gate tranche and
`validate_branch_freshness` remain deferred.
