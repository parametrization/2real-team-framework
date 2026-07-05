<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-05 (Phase 4 COMPLETE; v0.4.2 shipped)

## Pickup (next concrete step)
**Phase 4 is complete and shipped (v0.4.2 live on PyPI + npm).** Next step is the **Phase 5
theme decision** — stub **#133** ("Phase 5 Wave 1 — theme TBD") is drafted and reserved in
lifecycle state (`wave_4_meta_issue="#133"`). Candidate theme (retro carry-forward): *installer
robustness + cross-repo audit + install/test/teardown harness*, folding #131.
- When the owner sets the theme: scope Phase 5 Wave 1 via `lifecycle.py wave allocate/start/scope`
  (next global wave = **4**), then `/wave-start` (approval-gated).
- Deferred backlog to draw from: #101–#110 (installer/consent/audit/harness cluster) + **#131**.

## Decisions made this session (Phase 4 execution)
- **Phase 4 Wave 1 (global 2, `deployments/phase4/wave-1`)** delivered #98/#99/#100/#111 →
  **v0.4.1**. Surfaced 4 defects by dogfooding the retro on itself: #116 (reinstall rule),
  #117 (branch phase-ordinal), #118 (verdict-grammar semantics), #119 (name normalization).
- **Phase 4 Wave 2 (global 3, `deployments/phase4/wave-2`)** delivered **10 issues**
  (#116/#117/#118/#119/#77/#82/#94/#74/#75/#90) → **v0.4.2**. All charter-reviewed
  (cross-assigned, author≠reviewer), 0 must-fix, 0 CR cycles, 373 tests.
- **Wave 1 authoritative re-score CLOSED**: corrected 3 mis-tagged approval comments
  (#113/#114/#115 `Request`→`Replied` per #118, left #112 the real must-fix). 2 of 3
  contamination sources eliminated; 3rd isolated as **#131** (false-positive heuristic fires
  without a raised Must-fix). Durable scores earned, not held.
- **Trust matrix**: team converged at **4 across the board** (Wave 3: all +1; Nia's arithmetic
  5 capped to 4 by distribution discipline). See `trust_matrix.md` Wave 2 (authoritative) + Wave 3.
- **NEW STANDING RULE (#116)**: any change to Claude-related files must be added to install dirs
  AND reinstalled onto this repo. Enforced by `framework/install/reinstall.py --check` CI gate
  (byte-mirror scoped to `skills/`; hooks/lib run canonical-by-reference; charter via `--refresh-charter`).
- **Release convention**: pure semver is the SOLE publishing release; branch-name tag
  (`deployments-phase4-wave-2`) is lightweight-only (no Release → no double-publish).

## Open threads / follow-ups
- **#131** (tech-debt) — the last scorer artifact; Phase 5 candidate. Fix: gate
  `review_false_positives` on an actually-raised `Must-fix:` (reuse `_has_must_fix_items`).
- **Live-charter drift** (#122 tech-debt): `.claude/team/charter/charter.md:26` still says
  `--force`; reconcile via reinstall/refresh, or file the modular-vs-monolithic charter migration.
- **Reinstall push-only** (#129 tech-debt): a file deleted from canonical leaves an orphan live
  copy `--check` won't flag. Revisit as the managed set grows.
- Exploratory backlog #101–#110 still unscheduled → Phase 5 material (clustered in stub #133).

## Mechanical state
- Branch: **main** @ `9a8633c` (clean); wave branches `deployments/phase4/wave-{1,2}` retained.
- Latest release: **v0.4.2** (target `c1dd5b2`), live on PyPI + npm; fully OIDC (zero Actions secrets).
- Open PRs: (none). Open issues: **11** — #131 (tech-debt) + #101–#110 (exploratory) + #133 (Phase 5 stub).
- Lifecycle: `last_completed_wave=wave-3` (phase 4, wave-branch, 10 PRs, cr_cycles=0, concentration=30%);
  `global_wave_seq=3`; next allocate = **wave 4** (Phase 5 Wave 1, reserved meta-issue #133).
