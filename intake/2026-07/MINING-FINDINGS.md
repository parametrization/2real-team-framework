# Sibling-repo mining findings — 2026-07 (#264)

Re-audit of the two sibling SOURCE repos for `.claude/` (hooks, charter, skills, libs) and
`ontology/` learnings to port into the 2real framework, covering commits since the last mine
(**2026-06-24**). Source repos are READ-ONLY; this is an audit + backlog-triage note only — no
product code, hooks, or assets were modified.

- `botfarm_inc` — `/home/parameterization/code/botfarm_inc` (Phase 4 W7 → Phase 6 W1)
- `noorinalabs-main` — `/home/parameterization/code/noorinalabs-main` (Phase 7 W18 → Phase 8 W24;
  no nested child-repo `.claude/` trees exist — single top-level tree)

Classification vocabulary (same as the [2026-06 backlog](../noorinalabs-2026-06/GENERICISATION-BACKLOG.md)):
**port-as-is** / **genericise-then-port** / **already-covered** (2real ships an equivalent in
`framework/assets/`; may still be a *refinement* worth back-porting) / **skip** (product-specific).

## Summary

**~38 candidates** worth tracking (product-domain and pure retro/ontology-rebuild bookkeeping
commits excluded up front):

| Classification | Count | Notes |
|---|---:|---|
| port-as-is | 2 | small, generic, lift with no adaptation |
| genericise-then-port | 15 | carry org/board/identity/state-file/deploy tokens |
| already-covered — refinement to back-port | 12 | fixes to hooks/libs 2real ALREADY ships |
| already-covered — verify-first (4 pending + 1 CONFIRMED no-op) | 5 | 2real independently hardened these; see caveat |
| skip / guidance-only | 4 | prose, blocked-on-missing-infra, or doc alignment |

**Biggest single caveat — the "refinement" bucket needs a per-candidate diff against 2real's
ACTUAL code before porting.** 2real's shared parsers have diverged (matured) well past the
botfarm/noorinalabs snapshots: `_shell_parse.py` already strips heredocs, quoted args and
`--body`/`--body-file` values and extracts a leading `cd <dir>`; `_repo_flag_parse.py` already
handles all four `-R`/`--repo` spellings. So several loudly-flagged "P0 gate-evasion" fixes from
the source repos (botfarm #451 quoted/heredoc, botfarm #501 `-R`/`--repo`, noorinalabs cd-prefix
`normalize_command_separators`) are **probably already covered here** and are marked
verify-first rather than P0. The genuinely net-new items (below) are the more actionable ports.

> **Correction (PR #290 review, Paloma).** This caveat also bit my own original headline P0 —
> noorinalabs **#881** (`trust_signals` false-positive scoping). Re-diffing source `92aaaba`
> against `framework/assets/lib/trust_signals.py` `parse_verdicts` (L490–505) confirms our shipped
> code ALREADY applies both #881 guards — `_strip_code_markup` (byte-identical to the source
> helper) plus the `verdict == "approved"` gate — and is a strict **superset** (it additionally
> requires `_has_must_fix_items`). So #881 is a **confirmed no-op**, reclassified below, and #291
> (filed off the original claim) can be closed as already-covered. The lesson stands reinforced:
> diff every "refinement" candidate against `framework/assets/` — including one's own top pick.

## Deliverable cross-check — botfarm #657 ↔ our #288

**Verdict: #657 does NOT provide the fix #288 needs, but the author-resolution PRIMITIVE its
lineage consolidated is exactly what #288 prong-1 asks for. Recommend porting the helper *shape*,
not the call-sites.**

- **botfarm #657** (`322e566`, `validate_pr_review.py`) distinguishes a *reversed header* (a real
  reviewer who swapped `Requestor:`/`Requestee:` so the Requestee names the PR author) from a
  plain *author self-comment*, by reading `Requestor:`. It only enriches the block/advisory
  MESSAGE (names the reviewer whose approval evaporated); **counting/blocking is unchanged**. So it
  is a messaging refinement, not the counting fix our #288 is about.
- **What IS reusable:** the #469→#591→#601→#657 line factored botfarm's author-resolution into a
  standalone pure helper `_resolves_to_author(display, lastname, branch_author_lastname,
  pr_author_login, author_identifier)` — a single three-anchor rule (branch-derived author
  lastname, PR-author login, full-identifier fallback) shared between the Requestee self-review
  filter and the Requestor reversed-header distinction. That factoring is precisely #288 prong-1's
  ask: *"a single shared helper so the three surfaces [`validate_pr_review`, `trust_signals`,
  `review_load`] never drift on whose verdicts count."*
- **Architectural inversion to respect when porting:** botfarm keys "self-addressed" off
  `Requestee == author` (their reviewer is the `Requestor`). Our charter/scorer *attributes the
  review to the `Requestor`*, and #288's bug is a `Requestor == author` self-verdict counting as a
  review (Wave-21 PR #287). So port the **helper + three-anchor resolution rule**, but the trigger
  is mirrored: in 2real the exclusion fires when the **Requestor** resolves-to-author (drop the
  verdict from `missed_catches`/`verified_reviews`/review-load), not the Requestee.
- **Observation for Paloma (#288 author):** 2real's `pr_review_state.build_review_state`
  (lines ~208–216) counts approvals over distinct `Requestor` identities with **no**
  author-resolution at all — the gate is only "author-exclusive" insofar as an author self-note is
  typically a non-clean `Replied` verdict. If #288 introduces a shared `_resolves_to_author`-style
  helper, `pr_review_state` is a fourth surface that should adopt it for true parity.
- **Recommendation:** classify the port of botfarm's `_resolves_to_author` shape as
  **genericise-then-port, P1**, sequenced to land WITH #288 (it's the concrete implementation of
  #288's "single shared helper" requirement).

## A. botfarm_inc candidates

| Candidate (issue# — summary) | Classification | Net-new / Refinement | P | Rationale |
|---|---|---|---|---|
| #501 `gh pr merge` gate evasion via `-R`/`--repo` + `$(...)` | already-covered — **verify-first** | Refinement | verify | 2real ships `_repo_flag_parse` (all 4 flag forms) — confirm the merge PreToolUse path actually consults it before treating as P0 |
| #451 command-text triggers ignore quoted/heredoc | already-covered — **verify-first** | Refinement | verify | 2real `_shell_parse` already strips heredocs/quotes/`--body`; likely no-op here |
| cd-prefix / newline `normalize_command_separators` (noorinalabs origin, cross-listed) | already-covered — **verify-first** | Refinement | verify | 2real `_shell_parse` extracts leading `cd`; confirm the *following* command is still tokenized+gated (subtle gap) |
| #495 `validate_branch_freshness` blocks instead of auto-merging under default identity | already-covered — refinement | Refinement | P1 | Commit-identity correctness: auto-merge produced commits under the machine default identity inside a teammate PR. Diff vs 2real's `validate_branch_freshness`/`validate_commit_identity` |
| #591 parse charter fields independently + reject reversed Requestee loudly | already-covered — refinement | Refinement | P1 | Single-line field layout mis-parse + silent drop of a reversed-header approval. Diff vs 2real `validate_pr_review`; overlaps the #657↔#288 cross-check |
| #424 reviewer-load cap as a **hard kickoff gate** (+ `check_reviewer_load.py`) + full-roster denominator fix (#424b) | genericise-then-port | Net-new (kickoff-time) | P1 | 2real's `review_load.py` is a wave-END *report*; this is a wave-START hard cap with a symmetric ±1 band. Distinct lifecycle point. Fail-open fix (average over FULL roster) is the load-bearing part |
| #499 hoist `gh pr merge` PR-number extractor to shared `_gh_pr_args` | genericise-then-port | Net-new (refactor) | P1 | Dedup 4 divergent extractors into one hardened selector; parallels 2real's `_repo_flag_parse`/`_shell_parse` shared-helper pattern |
| #508 CI job gating the `.claude/hooks/tests` suite | genericise-then-port | Net-new | P1 | 2real hooks have tests but confirm CI gates them; wiring is pytest/pin-specific |
| #529 session-limit resilience protocol (charter) | genericise-then-port | Net-new | P1 | Orchestrator-recovery recipe + incremental-review-findings norm; no org tokens; extends `agents`/`pull-requests` charter modules |
| #608 seed review-request verdict as `Approved` not `Replied` | port-as-is | Net-new | P1 | Small charter-template + advisory fix; closes a recurring double-comment/merge-block bug; reuses shipped `validate_pr_review` |
| #609 wave-wrapup auto-refresh rollup base before merge approval | genericise-then-port | Net-new | P1 | Pre-empts the freshness gate on the rollup PR; maps onto 2real `wave-end`; SKILL prose needs term-mapping |
| #622 wave-wrapup CI-wait polls ALL workflows on head SHA | genericise-then-port | Refinement (of #609) | P1 | Fixes a fail-open (`select(.name=="CI")` missed red sibling workflows) in the CI-wait step |
| #623 advisory warn on in-flight-review head move | port-as-is | Net-new | P1 | Builds on shipped `validate_pr_review`+`_shell_parse`; no org tokens |
| #590 wave-wrapup full structural regen + completeness assertion | already-covered — refinement | Refinement | P1 | `ontology_gen.completeness` + `--verify-added-since`; fixes wave-added files silently missing from the graph |
| #589 `${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}` fallback | already-covered — refinement | Refinement | P1 | Generic skill-shell interpolation fallback; prevents hard session-start failures |
| #597 `resolve_repo_root` `__file__` fallback before SystemExit | already-covered — refinement | Refinement | P1 | Generic session-start reliability; diff vs 2real ontology hooks |
| #596 index unreadable/non-UTF8 files as bare nodes | already-covered — refinement | Refinement | P1 | Fixes a false COMPLETENESS FAILURE in `ontology_gen.build_graph`; applies directly to 2real `ontology_gen/*` |
| #613 harden `resolve_repo_root` against foreign worktrees | already-covered — refinement | Refinement | P1 | Project-sentinel check before accepting git-toplevel |
| #571 worktree-location-agnostic repo-context (git-common-dir) | already-covered — refinement | Refinement | P1 | Closes gitlink-worktree-misclassified-as-sandbox enforcement gap |
| #572 spawn-contract blocks in-repo `.claude/worktrees/` targets | genericise-then-port | Net-new | P2 | Hardcodes botfarm worktree convention; remap to 2real's `$SCRATCHPAD/wt-<issue>` |
| #643 wave-kickoff flag shared-refactor/double-rename collisions | genericise-then-port | Net-new | P2 | 3rd adjacency-inference pass (shared-symbol rename) for wave-start; examples are botfarm-specific |
| #599 wave-kickoff flag shared gates/modules by class-of-change | genericise-then-port | Net-new | P2 | Theme→module map hardcodes botfarm hook names; table pattern is portable |
| #642 guard test `os.environ` pollution + full-suite review norm | genericise-then-port | Net-new | P2 | pytest/monkeypatch stack-specific; the "steer raw process-global mutation to an auto-restoring API" pattern generalizes |
| #443 `auto_set_env_test` rewrites via `updatedInput` (not block) | genericise-then-port | Net-new | P2 | `ENVIRONMENT=test` stack-specific; the rewrite-not-block-and-retry UX pattern is generically valuable |
| ruff-check gate for the `.claude` hook/lib tree | genericise-then-port | Net-new | P2 | Lint-gate-the-hook-tree idea; CI/Makefile wiring is ruff-pin specific |
| #610 wave-kickoff `$MAIN` prose fix | skip | — | — | Author-stated "no behavior change" |
| #588 auto-rebase re-ping staled approvers | skip | — | — | Depends on `auto_rebase_queue.py` infra 2real does not ship |

## B. noorinalabs-main candidates

| Candidate (issue# — summary) | Classification | Net-new / Refinement | P | Rationale |
|---|---|---|---|---|
| #881 `trust_signals` `review_false_positive` scoping (only actual withdrawals) | already-covered — **verify-first CONFIRMED no-op** | Refinement | n/a | Re-diffed `92aaaba` vs our `parse_verdicts` (L490–505): 2real ALREADY has `_strip_code_markup` (byte-identical) + the `Approved`-verdict gate, and is a strict superset (also requires `_has_must_fix_items`). Landed in-window. Nothing to port; close #291 as no-op |
| #886/#896/#897 `validate_pr_review` batch-loop merge-guard hardening | already-covered — refinement | Refinement | P1 | Three successive fail-open closes (in-loop co-location narrowing, subshell/compound-arg, no-arg current-branch merge). Port as the 3-commit sequence; pure parser, no org tokens — but diff vs 2real's current guard first |
| #864 `verify_deployable_merge` lib (deterministic post-merge CI verification) | genericise-then-port | Net-new | P1 | Fills a real gap: 2real has no post-merge verify for wave→main, so a push-to-main-only red workflow goes unnoticed. Generic polling/"nothing-required = pass"; strip GHCR/Trivy/graph deploy example tokens + `main`-branch assumption |
| #890 `wave_seq` reservation-aware `allocate` | genericise-then-port | Net-new (2real has no `wave_seq`) | P1 | Fixes retro-reserved id being skipped by a naive `current+1`. Carries `cross-repo-status.json` key grammar → map to 2real state-file. Relevant if 2real's wave-retro/start reserve-then-commit ids |
| #870 + #887 `ontology_gen` NODE_KINDS interface/type + depth-aware TS `extends` splitter | already-covered — refinement | Refinement | P1 | Generic TS-parse correctness (interface/type-alias kinds; nested-generic-safe extends split); zero org tokens; clean backport to 2real `ontology_gen/typescript_ext` |
| #895 `lint_skill_graphql_pagination` lib + CI/pre-commit wire-in | genericise-then-port | Net-new | P1 | Greps skills for `first: >100` inside `gh api graphql` blocks — generic GraphQL-footgun guard; low-cost even without board-audit |
| #907 implementor-label convention + enforcement tool | genericise-then-port | Net-new | P1 | Flagged missing in 2real. Branch-prefix-first / commit-author fallback / REST-not-GraphQL label endpoint is generic; `FIRSTNAME_LASTNAME` label grammar + ASCII-fold needs 2real identity mapping |
| #900 `block_squash_wave_merge` also match short `-s` flag | already-covered — refinement | Refinement | P1 | Pure `gh` syntax coverage (`-s` == `--squash`); 2real ships this hook — diff and back-port verbatim if the `-s` widening is absent |
| #892/#902 board-audit paginate GraphQL + drift-clear guards | genericise-then-port | Net-new (2real has no board-audit) | P2 | Fixes to a skill 2real lacks; import base skill first. Underlying lesson (GraphQL connections cap at 100) is captured by #895 lint instead |
| #868 `wave_field_option` helper + kickoff wire-in / wave-field autocreate | genericise-then-port | Net-new | P2 | Only useful if 2real syncs wave labels to a Projects-V2 single-select field; hardcodes board + `wave-{X}`→`W{X}` grammar |
| `warn_zsh_wordsplit` (+ FP boundary fix) | already-covered — verify parity | Refinement | P2 | 2real ships this hook by name; diff specifically for the path/glob-prefix false-positive boundary regex |
| #871 standardize merge-driver invocation to plain-script form | already-covered — refinement | Refinement | P2 | 2real ships `ontology_gen/merge_driver`; mostly registration-convention, low urgency |
| Hook4 roster-validates Requestor name form (dotted `First.Last` blocks merge) | genericise-then-port (guidance) | Net-new insight (no code) | P2 | Memory-prose gotcha: branch-style `First.Last` in verdict headers gets miscounted by the roster match. Port as a one-line charter/spawn-brief note ("use the exact roster-card space-form name") — overlaps the #288/#657 verdict-grammar theme |
| ontology framework-path alignment + `ontology/README` author | skip | — | — | noorinalabs-internal two-layer rollout prose; 2real already ships `ontology/README.md` |

## Ranked port queue (top items)

Ranked after dropping the original #881 headline (confirmed no-op). Every headline below is either
a confirmed-net-new gap (verified absent from `framework/assets/`) or a candidate I diffed directly —
no unverified "refinement improves our code" claims in the top slots.

1. **botfarm `_resolves_to_author` helper shape (P1, land WITH #288).** The concrete implementation
   of #288 prong-1's "single shared author-resolution helper" — diffed against our
   `validate_pr_review`/`pr_review_state`; see cross-check above.
2. **noorinalabs #864 — `verify_deployable_merge` (P1, net-new).** Confirmed absent from
   `framework/assets/lib/`; closes 2real's post-merge wave→main verification gap.
3. **botfarm #424 — reviewer-load cap as a hard KICKOFF gate + full-roster denominator (P1,
   net-new lifecycle point).** 2real's `review_load.py` is wave-END reporting only (confirmed); this
   is a wave-START hard cap. The fail-open fix (average over the FULL roster) is the load-bearing bit.
4. **noorinalabs #907 + #895 (P1, net-new).** Implementor-label tooling + skill GraphQL-pagination
   lint — both confirmed absent from 2real.
5. **noorinalabs #886/#896/#897 — `validate_pr_review` batch-loop hardening (P1, refinement —
   diff-first).** Port the 3-commit sequence only if 2real's guard still fails-open on in-loop merges.
6. **noorinalabs #870/#887 + #900 (P1, refinement — diff-first).** Candidate refinements to
   `ontology_gen/typescript_ext` and `block_squash_wave_merge` that 2real already ships; confirm the
   gap before porting.
7. **botfarm #608 / #623 (P1, port-as-is).** Small generic review-gate UX fixes.

> Reclassification of #881 makes this concrete: the `already-covered` bucket must be diffed, not
> assumed. Only #1–#4 above are safe to scope without a pre-flight `framework/assets/` diff; #5–#6
> are refinements gated on that diff.

## Sequencing note

The refinement bucket dominates because both source repos spent this window hardening the SAME
review-gate / shell-parse / ontology machinery 2real already ships. **Do a per-candidate diff
against 2real's `framework/assets/` before opening any port PR** — 2real's shared parsers are more
mature than the source snapshots, so triage each "refinement" as (a) already-covered no-op, or
(b) a genuine gap. The net-new libs (`verify_deployable_merge`, `wave_seq`, `wave_field_option`,
`lint_skill_graphql_pagination`, implementor-label tooling, board-audit skill) are independent of
that diff and can be scoped as standalone stories.
