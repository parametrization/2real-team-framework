# Generic Skill: Iteration Scope Reconciliation

## Purpose

Reconcile **declared scope** (the next-iteration meta-issue body) with **actual
scope** (issues labeled for the iteration across all repos) between the
retrospective and kickoff. It surfaces drift accumulated during the prior
iteration, folds in retro carry-forwards + memory-tracked must-includes, applies a
deliberate tech-debt intake, validates implementer/reviewer names, and produces a
clean meta-issue + label set + structured scope for kickoff to act on.

> NOT branch creation (kickoff), NOT kickoff comments (kickoff), NOT the
> end-of-iteration close-orphans audit. Arguments: phase + iteration identifiers.

## Workflow

### 0. Inputs + 0.0. allocate the global iteration id

Owner provides the phase + the **global iteration id**. If iteration ids are a
single never-resetting monotonic counter, don't hand-pick the id — **allocate it
deterministically** from the counter (peek for the value, allocate-with-write to
persist the counter + the phase/ordinal display fields). The skill **either
reconciles or authors** the meta-issue (authoring a stub here is cheap; the body
is fully refreshed in Step 11 regardless).

### 0.5. Phase-review prerequisite + owner-set theme (two mandatory gates)

- **Gate A:** the phase-review skill must have run this session (without phase
  context, theme-picking is reactive). If absent → STOP, direct to phase-review.
- **Gate B:** the theme is set by owner **via dialogue** — NEVER inferred from
  carry-forwards / backlog ordering / retro proposals. Surface 2–3 candidate
  themes, wait for the owner to pick/hybridize, and record it in BOTH the status
  file (`iteration_<id>_scope.theme`) and the meta-issue body (a `## Theme`
  heading). No `## Theme` heading → STOP.

### 1. Read prior-iteration retro carry-forward

From the structured `phase_<P>_carry_forwards` array (preferred — survives
feedback-log churn) and the retro's free-text carry-forward subsections. Collect
into a working list.

### 2. Read memory must-includes

Scan project memory for must-include directives keyed to this iteration. Extract
the issue references; if a reference doesn't parse to a `repo#N` shape, surface it
(vague references are a process gap). If a must-include points to a closed /
non-existent issue, surface as stale memory — do NOT silently drop it.

### 3. Locate-or-author the meta-issue → declared scope

Find the meta-issue (canonical title pattern). If none exists, author a stub body
(including the owner-set theme so it passes the `## Theme` check) and file it.
Meta-issue label set is the phase bucket label + process/meta labels — **NOT** the
iteration label (that's reserved for work items). Extract every `repo#N` reference
from the body + comments → the **declared** set.

### 4. Query labeled scope across all repos

For each repo, list open issues carrying the iteration label (tolerate
missing-label stderr — labels are per-repo). → the **actual** set (with title +
creation date).

### 5. Compute scope drift

| Delta | Meaning | Default action |
|---|---|---|
| actual − declared | labeled but not declared (silent label-drift) | review per-item |
| declared − actual | declared but not labeled (forgot to tag) | apply label after confirm |
| must-includes − actual | must-includes missing the label | apply label (non-negotiable) |
| carry-forwards − actual | carry-forwards missing the label | apply after confirm |

### 6. Present unscoped items, repo-batched

Group actual−declared by repo with title, created date, body excerpt.

### 6.5. Premise-rot gate — verify named files/symbols exist at origin HEAD

For each in-scope issue, assert its named **file/path/symbol still exists at origin
HEAD** (a deterministic check: auto-extract path-like tokens from the body, run
`git cat-file -e <ref>:<path>` / `git grep` per declared symbol). Verdicts: a path
the ref can read but doesn't contain → **STOP** (premise rot — re-point, re-scope,
or close before collecting dispositions); a repo/ref unreadable (not cloned / not
fetched) → **WARN** (environment gap, not a STOP); present → OK. Best-effort fetch
each in-scope repo first so checks resolve against real HEADs.

### 7. Collect dispositions per unscoped item (owner-judgment gate)

Per item the owner picks: keep / defer-to-next / strip-label / close-as-obsolete.
Record in a working table; apply nothing until Step 10. Empty dispositions = STOP
(this is the only blocking owner-judgment gate, with Step 8.5).

### 8. Verify must-includes + carry-forwards are labeled

Queue a label-apply (Step 10) for any missing the iteration label.

### 8.5. Tech-debt intake top-up (+20% of feature/bug scope) — every iteration

Replace a brittle cumulative-ratio gate with steady **intake**: after Step 7 fixes
the feature/bug/security content, top up with **tech-debt-only** issues equal to
**20% of that content, rounded up** (add ALL if fewer qualify — a shortfall is a
good signal, never backfill with invented work). Compute base (post-Step-7 non-TD,
non-meta keeps, including not-yet-labeled ones), build an oldest-first un-scheduled
TD pool, select + **confirm with the owner** (blocking gate like Step 7), then
queue the label-applies + fold the selections into the structured scope's
tech-debt tier + board them. **Last-iteration-of-phase relaxation:** the +20% is a
**floor, not a cap** — surface the whole pool and let the owner pull in as much
debt as phase-exit cleanup warrants.

### 9. Create the next-iteration label if any defer dispositions

If any disposition was defer, ensure the next iteration's label exists in every
relevant repo (next id from the monotonic counter, not `{id}+1`).

### 10. Apply label churn in one batch per repo

Group all label edits per repo, present them, and apply only after explicit
confirmation (add / strip / defer = strip+add / close-as-obsolete with comment).

### 11. Refresh the meta-issue body

Rewrite with the post-disposition scope, categorized (theme core / precursors /
must-includes / retro-mandated / blockers) + a deferred-to-next section. PATCH via
API and **read-back-verify** (issue-body edit can silently no-op). Preserve the
original (copy or post as a comment) for the audit trail.

### 12. Emit summary

A metrics table (declared / labeled / drift / kept / deferred / stripped / closed /
must-includes folded / carry-forwards folded), final scope count, label edits
applied, meta-issue refreshed. Include a process-gaps section if any surfaced.

### 12.5. Validate implementer/reviewer names against rosters

If the scope includes an implementer/reviewer matrix, validate every name against
the relevant roster (child-repo entries → child roster ∪ parent roster; parent
entries → parent roster; case-insensitive, strip role suffix; fuzzy-match misses
and surface top-3). On a miss → STOP; an intentional substitution must be recorded
with rationale. Doing this at scope-time means the matrix is correct before kickoff
fans out.

### 13. Write the reconciliation timestamp + structured bookkeeping keys

Write four keys (only on full success): `scope_reconciled_at`, `repos_in_scope`
(canonical repo array, optionally overridden to exclude a repo), `meta_issue`, and
`scope` (the structured payload — tiers, deferred markers, metrics). **Use a
targeted text-level upsert helper, NOT `jq > tmp && mv`** (which reformats the
whole compact-inline file into a giant cosmetic diff). Validate JSON pre/post.
Cross-check the repo set against the meta-issue body (extra-in-body → STOP;
fewer-in-body → the deliberate descope path). Stamp the owning phase **inside** the
scope object (the key itself is the global id; phase is a derived display).

### 13.1. Tier-row shape — assignment-row dicts, not bare strings

The scope's tier arrays are consumed by the kickoff-comment hook, which matches an
issue to its row by id/ref and reads implementer/reviewer/priority. Each tier entry
MUST be an **assignment-row dict** (`id`, `ref`, `implementer`, `reviewer`,
`reviewer_2` — may be null at scope time, filled at kickoff — `priority`), not a
bare short-ref string. Bare strings silently skipped every per-issue kickoff
comment in a real regression; the hook degrades gracefully on residual strings but
dict rows are the source-of-truth fix.

## What remains manual

- Per-item dispositions (Step 7) and tech-debt selection (8.5) are owner judgment.
- Meta-issue section categories (Step 11) are owner judgment.
- Stale-memory escalation surfaces but does not auto-clean the memory file.

## Idempotency

Re-running finds drift 0 if labels match the refreshed meta-issue; safe to abort
before Step 10 (only Steps 10–11 mutate state); the Step 13 upsert produces zero
diff on identical values.

## Adaptation Notes

- The **premise-rot gate** (verify named files/symbols at origin HEAD before
  scoping) is a high-value, low-cost reuse — it catches issues built on deleted
  files / inverted root causes before they reach an implementer.
- **Tech-debt intake (steady 20%, floor on phase-exit)** is a more robust policy
  than a cumulative-ratio gate that whipsaws as the backlog shrinks.
- The **assignment-row-dict tier shape** and **name validation at scope-time** are
  what make the downstream kickoff hook + spawn fan-out correct-by-construction.
