# v0.4.1

Patch release — Phase 4 Wave 1, "self-hosting & quality machinery." Internal
correctness work that makes the framework trustworthy when run on itself. No
change to the `init` install contract; downstream repos pick up corrected trust
scoring, live lifecycle wiring, and a new review-format gate.

## Trust scoring reads the charter's own verdict vocabulary (#98)

`trust_signals.py` scored every review as zero because it matched GitHub's
`ChangesRequested` token, while the charter writes `RequestOrReplied: Request`
with severity in the comment body (`Must-fix:`). The scorer now recognizes the
charter grammar (`Request` + enumerated `Must-fix:` ⇒ blocking; `Replied` ⇒
non-blocking; legacy tokens still resolved for other-repo deploys).

## Lifecycle state machine is dogfooded by the wave skills (#99)

`/wave-start` and `/wave-end` now drive `lifecycle.py` directly, so `state.json`
is written **live** (allocate → start → scope → kickoff → wrapup) instead of
being reconstructed after the fact. Libs resolve dual-deploy: `.claude/lib`
first, `framework/assets/lib` as the source-repo fallback.

## Phase-aware integration branches (#100)

`branch.integration` now substitutes both `{phase}` and `{wave}`. A
phase-namespaced project (`deployments/phase{phase}/wave-{wave}`) no longer
silently scopes to a nonexistent branch and finds zero PRs.

## Verdict-comment format gate (#111)

New `validate_review_comment_format` hook enforces the charter verdict-comment
grammar on `gh pr/issue comment`, with its header regex pinned byte-identical to
the trust scorer so the gate and the scorer can never drift.

## Notes

- 331 tests (up from 270); `ruff` clean across `framework/`.
- Known follow-ups filed for Wave 2: #116 (reinstall-on-change), #117 (branch
  phase-ordinal), #118 (Request-vs-Replied semantics), #119 (name normalization).

## Version bumps
- PyPI: 0.4.0 -> 0.4.1
- npm:  0.4.0 -> 0.4.1
