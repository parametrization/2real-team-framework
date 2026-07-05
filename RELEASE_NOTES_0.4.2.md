# v0.4.2

Patch release — Phase 4 Wave 2, "quality-machinery hardening & tech-debt floor."
Internal correctness and self-hosting work that makes the framework trustworthy when
run on itself. No change to the `init` install contract; downstream repos pick up a
reinstall-on-change gate, corrected trust scoring, and charter-refresh safety.

## Reinstall-on-change gate (#116)

New `framework/install/reinstall.py` regenerates the live `.claude/**` runtime from
canonical `framework/assets/**`; `--check` verifies the two are in sync and exits non-zero
on drift. `test_reinstall_parity.py` asserts `reinstall.plan() == []` as a real CI gate,
catching drift in **both** directions (canonical edited without reinstall, or live copy
hand-edited). The byte-mirror is scoped to what Claude loads verbatim (`skills/`); hooks and
libs run canonical-by-reference (wired in place via `settings.json`) and the charter is
rendered/hand-evolvable — both deliberately excluded from the mirror.

## Charter refresh preserves hand-evolved edits (#77)

New `--refresh-charter` does a three-way refresh: a per-module render checksum in
`team/.charter-manifest.json` classifies each module as unchanged / clean-refresh /
hand-evolved-preserved. Fail-open — a missing manifest preserves everything. `--force` still
blanket-overwrites. Reinstall (#116) consumes the refresh path rather than clobbering the
charter.

## Trust-scoring correctness (#117, #119, #118)

- **#117** — `trust_signals` renders the `{wave}` branch token as the phase-local ordinal
  (`wave_<id>_phase_ordinal`), not the global wave sequence, so phase-namespaced projects
  score their real integration branch instead of finding zero PRs.
- **#119** — reviewer/author names are normalized against the roster before bucketing
  (hyphens preserved, fail-open on missing roster), so dotted vs spaced spellings no longer
  split one person's ledger.
- **#118** — verdict-comment grammar gains a semantic warn tier: `Request` with no `Must-fix:`
  suggests `Replied`; a non-blocking item under `Must-fix:` suggests `Tech-debt:`. Fail-open
  (never blocks); the malformed-header block path is unchanged. Must-fix regexes are pinned
  byte-identical to the scorer.

## Other fixes

- **#94** — merge-model-conditional PR wording; `policy.merge_model` reconciled to
  `wave-branch` to match practice (behavior-neutral — that key only feeds the session-start
  banner; enforcement uses per-wave state).
- **#82** — `copy-shared.js` refreshes the node framework bundle on every prepack
  (rm+recopy non-symlink dests) instead of skip-if-exists; symlink escape-hatch preserved.
- **#74** — `ontology_gen` excludes the installed `.claude/` runtime in consumer repos
  (index noise); the framework-source dogfood copy is still indexed.
- **#90** — `wave-audit` fallback matches zero-padded issue numbers per the `{IIII}` grammar.
- **#75** — new test coverage for meta-and-children ontology generation at install time.

## Notes

- 373 tests (up from 331); `ruff` clean across `framework/`.
- Dogfooding milestone: this wave's retro ran the machinery on itself and produced the first
  fully-clean mechanical trust score, and closed the Phase 4 Wave 1 authoritative re-score.
- Follow-up filed: #131 (false-positive heuristic fires without a raised Must-fix) — the last
  isolated scoring artifact, a Phase 5 candidate.

## Version bumps
- PyPI: 0.4.1 -> 0.4.2
- npm:  0.4.1 -> 0.4.2
