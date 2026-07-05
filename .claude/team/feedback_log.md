# Team Feedback Log — 2real-team-framework

Track all feedback events here. Format:

```
## [DATE] — [FROM] → [TO] — Severity: [minor/moderate/severe]
[Feedback content]
[Action taken, if any]
```

---

## Retrospective: Wave 2 (Phase 4 Wave 1, "self-hosting & quality machinery") — 2026-07-05

> **First live retro.** State machine drove the wave (via #99); counters recorded live at wrapup,
> no backfill. Two Phase 4 exit criteria met: state written live, retros need no backfill.

### Wave Metrics
- **4 PRs merged** into `deployments/phase4/wave-1` — #112 (#100, Ibrahim), #113 (#98, Paloma),
  #114 (#99, Nia), #115 (#111, Tariq). 4 issues closed (#98/#99/#100/#111).
- **1 legitimate changes-requested cycle** (Paloma → #112, test-union merge order; resolved by
  Ibrahim's rebase). Recorded `wave_2_changes_requested_cycles=1`.
- CI green on every PR; integrated tip: `ruff` clean, **331 tests** (270→331; union suite +
  #114/#115 additions). Counter drift: **zero** (recomputed = recorded).
- Tech-debt filed this retro: **#116** (owner reinstall rule), **#117/#118/#119** (retro defects).

### Top-Implementer Concentration
1 PR each across 4 engineers → **max 1 / 4 = 25%**. Balanced; no fragility or theme-fit flag.

### Per-Engineer Assessments (signals contaminated — see trust matrix)
Deltas held flat. Raw signals: Ibrahim/Paloma/Tariq delta 0, Nia delta −1 (a #118 false-positive
artifact). Every author showed a phantom `must_fix_received=1` because approving reviewers wrote
`Request` (not `Replied`) and filed non-blocking notes under `Must-fix:`. See #118/#119.

### Top 3 Going Well
1. **The quality machinery runs end-to-end** — Phase 3's retro scored all-zero; this one executed
   the full pipeline and (by design) caught its own remaining defects.
2. **Clean, balanced delivery** — 4/4 PRs, 25% concentration, one real must-fix, zero CI-red.
3. **Cross-coupling reconciled in isolation** — #111 defined the vocab, #98 aligned to it, both
   pinned the same regex; three independent reviewers confirmed the coupling survives integration.

### Top 3 Pain Points
1. **Branch renderer ignores phase-local ordinal (#117)** — scored 0 PRs until manually overridden;
   the retro could not self-score. Sibling of #100.
2. **Verdict-grammar semantics unenforced (#118)** — `Request` vs `Replied` and Must-fix-vs-Tech-debt
   placement are convention-only; misuse silently contaminated trust signals.
3. **Reviewer-name splitting (#119)** — dotted vs spaced names fragment one person's ledger.

### Proposed Process Changes (approval-gated — not yet applied)
1. **Fix #117** so `{wave}` resolves to `wave_<id>_phase_ordinal` for phase-namespaced projects —
   restores authoritative self-scoring. *(Rationale: retro must not need a manual base override.)*
2. **Fix #118** — charter clarity + gate warning on the two misuse patterns. *(Rationale: the
   scorer is only as good as the review vocabulary; structure-only enforcement isn't enough.)*
3. **Fix #119** — roster-normalize captured names before bucketing. *(Rationale: split identities
   silently understate reviewer contribution.)*
4. **Adopt #116** — reinstall-on-change rule to end source↔runtime drift.
5. Minor fold-ins (from PR reviews, non-blocking): `/wave-start` allocate-idempotency guard
   (re-run double-advances state); `_phase_for_wave`↔`lifecycle.phase_of` shared resolver;
   `merged_prs` phase-passthrough + bad-JSON fail-open tests; wave-end in `DUAL_DEPLOY_REQUIRED`.

### Re-score commitment
Once #117/#118/#119 land, re-run `trust_signals score` on this wave's corrected comments and
replace the flat-held deltas with authoritative numbers (same commitment the Phase 3 entry made).

---

## Retrospective: Wave 1 (Phase 3, "installer overhaul → v0.4.0") — 2026-07-05

> **Reconstructed retro.** Phase 3 was run without the lifecycle state machine (no
> `state.json`). State was backfilled on 2026-07-05 from the merged-PR record and this retro
> run then. Phase 3's three "waves" all merged to a single integration branch
> (`deployments/phase3/wave-1`), so mechanically they are **one** tracked wave (global wave 1)
> covering all 13 PRs — they cannot be split three ways after the fact by base branch.

### Wave Metrics
- Merged PRs: **13** (into `deployments/phase3/wave-1`), rolled to `main` via PR #97, shipped v0.4.0.
- Issues closed: 12 wave issues (#64–#70, #73, #85–#88) — closed 2026-07-05 via /wave-audit.
- CI health: green at every merge head (PRs before #76 predate CI-on-wave-branches, so no checks).
- Merge model: **wave-branch** (features → wave branch → main). NOTE: config declares
  `direct-to-main` — the config/practice mismatch is open tech-debt #94.
- Counter corrections: none — counters were reconstructed at retro time from PR data, not
  recorded at a historical wrapup, so drift is zero by construction.

### Top-Implementer Concentration
Ibrahim El-Amin 5 / 13 = **38%** — below the 60% force-call threshold. Load was reasonably
spread across four engineers (Ibrahim 5, Nia 3, Paloma 3, Tariq 2). *Theme-fit:* the wave was
installer/bootstrap-heavy, Ibrahim's domain. No fragility flag.

### Per-Engineer Assessments (signals + deltas)
Extraction note: `trust_signals.py` returned **all-zero** review signals because it matches the
verdict token `ChangesRequested`, but this project's charter convention writes
`RequestOrReplied: Request` with severity in the body (`Must-fix:`). The must-fix signals below
are a **supplementary manual tally** of the `Must-fix:` markers; the pure scoring layer
(`score_delta`/discipline) was then run on the corrected signals. Deltas are therefore
**provisional** pending the vocabulary fix (see proposed changes).

- **Nia Rossi** — prs_merged=3, must_fix_received=0, must_fix_caught=1, ci_red=0 → delta **+1** →
  **3→4**. Only fully-clean author with ≥2 PRs. Negative-signal line: *metrics clean*.
- **Ibrahim El-Amin** — prs_merged=5, must_fix_received=2 (#78, #96), caught=0, ci_red=0 →
  delta **0** → **3→3**. Highest output, but two rework rounds keep it off a bump.
  Negative-signal line: *2 must-fix received*.
- **Paloma Gupta** — prs_merged=3, must_fix_received=1 (#79 rebase/semantic-conflict), caught=0 →
  delta **0** → **3→3**. Negative-signal line: *1 must-fix received*.
- **Tariq Morales** — prs_merged=2, must_fix_received=1 (#93, from Nia), must_fix_caught=3,
  ci_red=0 → delta **0** → **3→3**. Reviewed nearly every PR and caught the most issues, but the
  model gates the reviewer +1 behind being "clean," and he received one must-fix → no bump.

### Top 3 Going Well
1. Clean delivery: 13 PRs, zero CI-red merges, shipped v0.4.0 to both registries first try.
2. Real review pressure: QA (Tariq) reviewed nearly every PR; must-fixes were raised and resolved
   (e.g. #79's semantic ontology-conflict rebase) rather than waved through.
3. Load spread across four engineers (38% top concentration) despite an installer-heavy theme.

### Top 3 Pain Points
1. **The framework didn't dogfood its own lifecycle state machine** — Phase 3 ran with no
   `state.json`; this retro was only possible by after-the-fact backfill.
2. **Trust-scoring is blind to this project's own review vocabulary** — `trust_signals.py`
   matches `ChangesRequested`; the charter uses `Request` + body `Must-fix:`. Left uncorrected,
   every engineer scores falsely "clean → +1."
3. **Waves weren't isolated as branches** — 2 & 3 shared wave-1's integration branch, so
   per-wave mechanical scoring is impossible retroactively.

### Proposed Process/Framework Changes (approval-gated — not yet applied)
1. Fix `trust_signals.py` verdict vocabulary to match the charter (`Request`/`Replied` + body
   `Must-fix:` severity), OR align the charter to emit `ChangesRequested`. → new tech-debt issue.
2. Drive every wave through `lifecycle.py` (allocate→…→wrapup) so `state.json` exists live and
   retros need no backfill. Wire it into /wave-start and /wave-end. → new tech-debt issue.
3. Reconcile `policy.merge_model` (`direct-to-main`) vs actual wave-branch practice — already
   tracked as **#94**.
4. Make `branch.integration` phase-aware (template supports only `{wave}`, not `{phase}`), so
   phase-namespaced projects can be scored without hand-editing config. → new tech-debt issue.
