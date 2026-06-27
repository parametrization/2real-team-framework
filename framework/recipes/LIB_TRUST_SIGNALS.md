# Recipe: `trust_signals.py` (lib CLI / library)

## Purpose
Replaces narrative self-grading of teammates with **countable** per-engineer
signals taken from an iteration's merged-PR set, and turns them into bidirectional
trust deltas. A delta is no longer "felt" — it is derived from numbers and must
cite them. Split into an SCM-coupled **extraction** half and a pure **scoring**
half; the scoring half is usable standalone on a hand-built `Signals` dict.

## The scoring model (in brief)
- `score_delta(sig)` — pure, symmetric, clamped to **[-2, +2]**. `-1` per CI-red
  merge, `-1` per review false-positive, `-1` if `must_fix_received >= 3`; then
  (only if the iteration is clean of those negatives) `+1` if `prs_merged >= 2`,
  `+1` if `must_fix_caught >= 2`. New score = `clamp(NEUTRAL + delta, 1, 5)`.
- `decay(old, n)` — drift one step toward NEUTRAL (3) after 3 unsignalled iterations.
- `apply_distribution_discipline(proposals)` — **5 is reserved**: a proposed 5
  survives only for the top *composite* performer (and only if strictly positive);
  every other proposed 5 is capped to 4.
- `negative_signal_line(name, sig)` — forces a per-engineer gap line; a bare
  `None`/`N/A`/`-` is banned (`validate_negative_signal_pass` rejects it).
- `retirement_trigger(scores, ci_reds, k=3)` — flags sustained bottom-tier (<=2)
  or repeated CI-red merges across the last k iterations.

## Config keys used
- `scm.owner` + `project.repos` — the repo set (bare names get the owner prefix;
  `owner/name` used as-is). Falls back to the single cwd repo (`gh repo view`).
- `branch.integration` — formatted with `{wave}` to derive the merged-PR base branch.
- `paths.state_file` — default `--status` path (kickoff-timestamp source).

## What is PROJECT-COUPLED in extraction
- `_integration_base` — the base branch is derived from `branch.integration`
  rather than the source's hard-coded `deployments/phase-<P>/wave-<M>`.
- `_kickoff_ts` — the cross-window merge lower-bound reads a state-file key named
  `wave_<id>_kicked_off_at`. Absent/unreadable → no filter (base-branch scoping
  only), the safe default. Both spots are marked `# PROJECT-COUPLING:` in source.

## Adaptation notes
- Stdlib-only. Imports `_framework_config` via the `lib/ -> hooks/` sibling bridge
  (same pattern as `pr_ci_state.py`); requires that deployed layout.
- The verdict-comment shape (`Requestor:` / `RequestOrReplied:` lines, with a
  retraction-vocabulary heuristic) is the review convention extraction parses —
  swap the regexes in `_FIELD_RE` / `_FALSE_POSITIVE_RE` for a different format.
- Every `gh` call carries a 60s timeout. Scoring functions never touch the SCM,
  so unit-test them directly on synthetic `Signals`.
