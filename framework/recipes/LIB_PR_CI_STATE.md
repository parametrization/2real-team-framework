# Recipe: `pr_ci_state.py` (lib CLI / library)

## Purpose
A query-time oracle answering "is this PR's CI ready to merge?" before you assert
merge-readiness in a status message, board update, or hand-off. The merge gate
(`validate_pr_ci_status`) only runs at merge time; this surfaces the *same*
verdict on demand.

## What it enforces
Reuses the gate's `fetch_checks` + `classify_rollup` + `classify_check` verbatim,
so the oracle and the gate cannot drift. Pins the load-bearing rule: an EMPTY
`statusCheckRollup` is a HARD not-ready state — readiness requires **non-empty
AND all-success**. Unlike the gate, it treats empty as not-ready
*unconditionally* (no repo-shape discrimination — that is the gate's job).

Exit codes: `0` ready, `1` not-ready (empty/failing/pending), `2` undeterminable.
Offers a text and a `--json` report, plus a `compute_ci_state()` library entry
returning a `CiState` dataclass.

## Config keys used
- `ci.neutral_pending_check_prefixes` — threaded into the shared classifier so a
  NEUTRAL-means-pending check is classified identically here and at the gate.

## Adaptation notes
- **Import resolution:** lives in `lib/`, imports the classifier from
  `hooks/validate_pr_ci_status.py` via `sys.path.insert(parent.parent/"hooks")`.
  Chosen over copying the classifier into a shared module — the live import is
  the lower-risk option because it keeps one source of truth (a vendored fork
  would silently drift). Requires the deployed layout to keep `lib/` and `hooks/`
  as siblings; the import fails loudly (exit 2) if not.
- Stdlib-only. `config()` resolves from cwd when called without `input_data`.
