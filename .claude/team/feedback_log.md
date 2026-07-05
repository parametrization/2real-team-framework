# Team Feedback Log — 2real-team-framework

Track all feedback events here. Format:

```
## [DATE] — [FROM] → [TO] — Severity: [minor/moderate/severe]
[Feedback content]
[Action taken, if any]
```

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
