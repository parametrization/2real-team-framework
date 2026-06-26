# Generic Reusable Script: Promotion-Audit Deterministic Driver

## Purpose

The single, **deterministic** entrypoint for the promotion-pipeline audit
(`GENERIC_SKILL_PROMOTION_AUDIT_PROMPT.md`). It wires a set of pure
classification functions + thresholds together in exactly **one** place, so the
same repo state always yields the same decisions. The audit skill's prose invokes
this driver instead of describing the classify call sequence inline.

## Background — why a single driver exists

A promotion audit historically shipped pure helper functions but **no driver**,
so the operator hand-rolled the classify call sequence each iteration. That
hand-rolling mis-fired: the section→skill / skill→hook tiers derived the
invocation signal by counting commits for an **empty** candidate-skill slug, and a
`git log --grep=/` over an empty pattern matches ~every commit. Every
not-yet-promoted section then reported a huge invocation count, crossed the
threshold, and produced dozens of **spurious AUTO** decisions that would have
opened dozens of bogus promotion PRs. The more-carefully-called memory→doc tier
returned the correct zero.

The fix is **determinism-over-hand-rolling**: wire signal derivation in ONE place,
with correct slug resolution, so identical repo state yields identical decisions.

## Signal derivation (fixed in the driver)

- **memory → doc:** count retro-citations of the memory in the feedback log.
- **doc → skill:** the candidate skill slug is the section's recorded
  `promoted_to` (with any `skills/` prefix stripped) when already promoted, else
  the slugified heading — the *prospective* skill name. A not-yet-existent skill
  never appears in commit messages, so its count is naturally ~0. The empty-slug
  footgun is **also closed at the root**: a blank slug must count zero.
- **skill → hook:** count invocations of the skill name (**always DECIDE**, never
  AUTO).

## Structure (stdlib only)

1. **Path resolution.** From the script's own location walk up to the repo root;
   derive input locations: memory dir, the directory *containing* the process-doc
   tree (NOT the doc tree itself — passing the inner dir is a common error), the
   skills dir, the feedback log, the central status file. Allow a `--repo-root`
   override for tests against a fixture tree, and a `memory_dir` override.

2. **Iteration-name resolution.** Accept a positional iteration arg in any of the
   accepted forms and normalize to the canonical form; with no arg, read the
   current iteration from the status file. Raise a clear error on an unparseable
   value.

3. **Audit-date resolution.** Pin the date to the iteration boundary timestamp
   from the status file (try kicked-off, then started, then scope-reconciled
   keys), returning a sentinel only if all are absent. **Never `datetime.now()`** —
   that would break byte-identical re-runs. Allow a `--date` override.

4. **`run_audit`.** Read inputs in **sorted order** (done inside the helpers).
   For each memory → classify with retro-citations; for each doc section →
   classify with the resolved candidate-slug's invocation count + threshold; for
   each skill → classify with the skill's invocation count (always DECIDE). Return
   an immutable result carrying iteration name, audit date, threshold, and the
   decision list, with `counts()`, `table()`, and `summary_line()` helpers.

5. **CLI.** `argparse` with: positional `iteration` (optional), `--json` (emit a
   machine-readable `{iteration, audit_date, threshold, counts, decisions[]}`
   payload, sorted keys), `--date`, `--repo-root`. Default stdout is the rendered
   table + summary line; `--json` drives the skill's artifact-emission step. The
   driver performs ONLY classification + rendering — it makes no external calls and
   emits no artifacts.

## Determinism contract

- Sort every input list by a stable key before iterating.
- Pin dates to the iteration boundary, never the wall clock.
- Never count invocations for an empty/blank slug.
- Read only on-disk files + git history — no transcripts, no network.

Re-running on unchanged repo state yields byte-identical decisions and table.

## Adaptation Notes

- The reusable lesson is **wire-once determinism**: a pipeline that ships pure
  helpers but no canonical driver invites per-run hand-rolling and the empty-slug
  class of bug.
- Guard the empty/blank-slug case **at the root** (in the invocation-count helper)
  as well as in the slug resolver — defense in depth against the all-commits match.
- Keep classification (this driver, deterministic) strictly separate from
  artifact emission (the skill prose, nondeterministic external calls).
- Tests should cover: iteration-name normalization, date resolution precedence,
  the empty-slug regression, all-tiers coverage, byte-identical re-runs, and a
  steady-state assertion (zero AUTO / zero DECIDE on a clean backfilled tree).
