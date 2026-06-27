# The orchestration crown jewel

This is the part worth extracting carefully. The source system is a **self-correcting simulated
team** that runs real software delivery against GitHub, with deterministic guardrails enforcing
process discipline that a single agent reliably drifts from. Below: the generic shape of each
interaction surface the framework should expose, with the candidate files that implement it.

Everything here is in `candidates/`. Where a file hard-codes the source project, the fix is a
reference into the **shared-config object** (`OVERVIEW.md` § headline) — noted inline as ⚙.

---

## 1. Generic source-control interaction (SCM)

The model: **per-issue feature branches → a wave branch → the default branch**, one merge model
per wave, never force-merged, identity-attributed per commit.

- **Branch grammar** ⚙ — `{FirstInitial}.{LastName}/{IIII}-{slug}` for feature branches;
  `deployments/phase-{N}/wave-{M}` for wave branches. Both are config-driven strings, not logic.
- **One merge model per wave** — `wave_merge_model.py` + `block_squash_wave_merge.py`: a wave is
  *either* "every PR bases on the wave branch, integration PR at wrapup" *or* "every PR bases on the
  default branch". Mixing strands commits. The guard is generic; the model is recorded in state.
- **Never force, never bypass** — `block_no_verify.py` (refuses `--no-verify` on commit/push),
  `block_git_config.py` (refuses `git config user.*` mutation), `no_worktree_self_delete.py`. These
  are **GENERIC-READY** — universal git hygiene.
- **Provably-safe default-branch sync** — `sync_main.py` fast-forwards the default branch and *never*
  forces; `validate_branch_freshness.py` flags a stale base before work starts. GENERIC-READY.
- **Review as a first-class artifact** — `review-pr` skill + `validate_review_comment_format.py`
  enforce a structured verdict comment (`Requestor` / `Requestee` / `RequestOrReplied`) that hooks
  later parse. The *template* is ⚙; the parse-and-enforce loop is generic.
- **rc-masking guard** — `warn_pipe_mask_rc.py` catches `git push … | tail` swallowing a rejected
  push (exit code lost to the pipe). GENERIC-READY, and a genuinely non-obvious footgun.

Generic surface to expose: *config-driven branch/merge grammar + a fixed set of git-safety hooks +
a structured-review contract.*

---

## 2. Generic ticketing / issue system

The model: **GitHub Issues are the work units; a GitHub Project board is the planning surface;
labels are canonical and the board's fields are a derived projection.**

- **Board ↔ issue drift detection** — `board-audit` skill: finds issues missing from the board
  (orphans) and issues whose wave-label disagrees with the board's `Wave` field, then bulk-fixes both
  via GraphQL. Ships battle-tested **GraphQL pagination** (the `first:` ≤ 100 cap, cursor walking) and
  per-call `timeout` patterns — exactly the things people get wrong. ⚙ on org/project#/repo-list.
- **Bug intake** — `file-bug` skill: a 3-pass discriminator (duplicate detection / state drift /
  multi-layer matching) before filing, plus auto-labeling and board-add. The discriminator is
  high-value generic; strip the domain examples.
- **Auto-board-add on create** — `auto_add_issue_to_board.py` (PostToolUse on `gh issue create`).
- **Label validation** — `validate_labels.py` validates labels exist before an issue references them
  (the board rejects unknown labels silently). GENERIC-READY.
- **Stale-issue closer** — `close-stale-issues`: maps merged PRs → resolvable issues by branch grammar.

Generic surface: *labels-are-canonical + board-is-projection, with a sync skill, a bug-intake
discriminator, and a small set of board hooks. All GitHub-specific but provider-shaped — the
abstraction boundary is "issue tracker + planning board".*

---

## 3. Generic CI/CD

The model: **a red gate is a stop, not a speed bump** — and "local clean" must not diverge from CI.

- **Merge blocked on CI status** — `validate_pr_ci_status.py` (PreToolUse on `gh pr merge`) refuses to
  merge when the PR's `statusCheckRollup` is red **or empty** (empty = "checks haven't reported" = hard
  not-ready, a subtle correctness point). Backed by the `pr_ci_state.py` oracle. GENERIC-READY.
- **Local⇄CI parity gate** — `pre_commit_ci_sync.py`: a CI job that fails the build if a check CI
  enforces (lint/type/test/spell/…) is *not* mirrored in `.pre-commit-config.yaml`. This is the
  machine-enforcement that keeps local hooks from rotting relative to CI. The classifier is generic;
  the specific tool set (ruff/mypy/pytest/cspell/actionlint/gitleaks) is ⚙ stack config.
- **Deploy verification** — `verify_deployable_merge.py` checks post-merge-only GHA workflows
  (publish/Trivy/etc.) actually ran and passed after a merge to the deployable branch — a green PR is
  *not* proof a publish job fired. Already `owner/repo`-parameterized; only doc examples are project-specific.
- **Deploy watch** — `watch-deploy` skill: poll → classify failure → bounded fix-forward → escalate,
  over staging/prod deploy workflows. The shape is generic; ⚙ on workflow names + failure-class table.
- **Workflow coverage** — `validate_workflow_paths_coverage.py` flags `.github/workflows/**` files that
  no CI job actually exercises. GENERIC-READY GitHub Actions guard.

Generic surface: *CI-status-before-merge + local⇄CI parity gate + post-merge deploy verification.* The
first two are the highest-value, lowest-friction lifts in the whole corpus.

---

## 4. Generic meta-repo with child repos

The model: a **parent meta-repo that `.gitignore`s N independent child repos**, giving org-wide team
config + cross-repo coordination in one place while each child keeps its own branches/PRs/CI.

- **Cross-repo wave kickoff** — `wave-kickoff` skill: idempotent `deployments/phase-{N}/wave-{M}`
  branch creation across *every* repo in scope (via `gh api`, no clean local checkout required),
  distinguishing created / exists-clean / exists-ancestor / exists-drift; declares the wave's merge
  model; runs a pre-flight checklist; persists branch SHAs to the state file. This is the densest
  piece of orchestration in the system.
- **Child-checkout coherence** — `check_child_checkouts.py`, `check_agent_liveness.py` (a pure,
  zero-I/O multi-agent stall detector: missing-task / zero-artifact / throttle-cadence signals).
- **Cross-repo identity union** — `roster_union_sync.py` / `roster_consistency_check.py`: every child
  repo's roster rolls up into a union manifest the commit-identity hook reads, so a commit in any repo
  is attributable. ⚙ on identity convention.
- **Cross-repo ontology aggregation** — `ontology_gen.aggregate` namespaces each child's structural
  graph into one central cross-repo graph. Already `--repo NAME=SUBDIR` overridable.

Generic surface: *a repo-list config + cross-repo branch/label/board operations driven entirely
through `gh api` (so no working-tree dependency) + a roll-up identity/ontology manifest.* The
"operate via API, not local checkout" discipline is what makes this robust under parallel agents.

---

## 5. Generic team / identity / trust (the self-correction loop)

> *Synthesis (from the governance audit):* A simulated team is a roster of personas — each a persona
> card with a persistent identity (name, role, level), a git commit identity, seeded preferences, and
> an evidence-gated "Learned Adjustments" log — registered in a `roster.json` union manifest the
> commit-identity hook reads so every commit is attributable. Personas spawn as agents under a
> hub-and-spoke single-leader model (only the orchestrator spawns; managers request spawns) and work
> in waves against a ticketing board, with charter-governed PRs (comment-based reviews, N-reviewer
> rule, no force-merging a red gate). Quality and honesty are scored two reinforcing ways: a **trust
> matrix** of directional 1–5 scores updated *mechanically* from countable wave signals (PRs merged,
> must-fixes caught vs received, CI-red merges, rework cycles) with decay-to-neutral and reserved-top
> scoring, and a **feedback log** of per-wave retros — together driving fire-and-replace and promotion
> of recurring lessons up the **enforcement hierarchy** (memory → charter → skill → hook). A lifecycle
> state machine sequences it all, and the charter is the living rulebook retros continuously amend.
> Identity persists, trust evolves from evidence, feedback accumulates into enforcement, and the
> lifecycle orchestrates — so the team self-corrects toward minimal negative feedback.

Anchor files: `trust_signals.py` (mechanical per-engineer scoring — the heart; ⚙ on roster),
`verify_commit_identity.py` / `validate_commit_identity.py` (⚙ on email regex), the roster persona-card
**schema** (GENERIC-READY; the specific cast is example data), `trust_matrix.md` + `feedback_log.md`
(populated examples of a generic format), `promotion-audit` skill (the deterministic
memory→charter→skill→hook promotion pipeline — encodes the enforcement hierarchy as runnable code).

The **enforcement hierarchy** ("prefer hook > skill > charter; a charter rule without enforcement
decays") is itself one of the most transferable ideas in the system: process rules are only as real
as their cheapest automatic check.

---

## 6. Generic memory / ontology

> *Synthesis (from the ontology audit):* The ontology is two non-contaminating layers. The
> **structural layer** is *generated* by `ontology_gen` — a zero-dependency, offline, deterministic
> code-graph (`code-graph.json`) plus a token-economical, section-loadable `llms.txt` over
> files/symbols/imports/calls/inheritance — always-current-by-regeneration, so never hand-edited and
> never checksum-tracked. The **semantic overlay** is *hand-curated* YAML/markdown (domain entities,
> services, conventions, per-repo internals) capturing meaning a parser can't infer; it's dirty-tracked
> by a `checksums.json` contract (dirty when `last_tracked != last_resolved`) and reconciled by a
> resolver skill. Three roles bind them: a PostToolUse **tracker** hook (overlay only), a **resolver**
> skill, and a read-only **librarian** skill. The overlay references generated nodes by stable id
> rather than re-describing them; a git union merge-driver keeps parallel regenerations conflict-free;
> code is the arbiter of truth on conflict.

**Crown-jewel generic engine — `ontology_gen` (`candidates/lib/ontology_gen/`):** a self-contained,
stdlib-only Python package (no network/DB/LLM). `model.py` fixes the public `code-graph.json` contract
(frozen node/edge enums) with total-order sort+dedup → byte-deterministic, record-granular-diffable
output. `generate.py` discovers via `git ls-files` (respects `.gitignore`, walk fallback), dispatches
per-language (Python `ast`, TS/JS, Cypher), and degrades unparseable files to bare nodes instead of
aborting. `assemble.py` does conservative unambiguous-only cross-file edge resolution; `llms.py`
renders the ~24k-token section-loadable digest; `merge_driver.py` union-merges parallel regenerations.
The **only** project coupling is `aggregate.DEFAULT_REPOS` (already `--repo NAME=SUBDIR` overridable).
**Ships verbatim.** Also lift: the project-memory pattern itself — version-controlled `.claude/memory/`
with a `MEMORY.md` index `@import`ed into context, transferable on `git pull` with zero per-machine setup.

---

## 7. Generic lifecycle (the wave/phase state machine)

The spine the other six hang on. A **wave** brackets: `wave-start` (clean worktrees + branch + state)
→ `wave-scope` (reconcile declared vs labeled scope) → `wave-kickoff` (branches, board, slates,
spawns) → work → `wave-audit` → `wave-wrapup` (review → merge-sequence → deploy-verify → ontology
rebuild → handoff) → `wave-retro` (trust + feedback + charter proposals). A **phase** brackets waves
with `plan-phase` / `phase-review`. `session-start` is the resume protocol that re-orients any new
session (worktree → team → handoff → ontology → annunaki → wave → charter).

Two primitives make it robust:

- **`wave_seq.py`** — a monotonic, never-reset iteration-id allocator (generic the moment "wave" → "iteration").
- **`upsert_status_keys.py`** — text-level JSON upsert that preserves a compact-inline file shape while
  every skill reads/writes wave state through it (a naïve `jq > tmp && mv` reformats the whole file).
  GENERIC-READY substrate.

Plus precondition gates everywhere: a skill `STOP`s unless the prior phase wrote its completion marker
— the state machine refuses to advance on a stale or skipped step. That precondition→state-written
contract is the pattern that makes a multi-session, multi-agent program resumable and hard to corrupt.

---

## The two cross-cutting engines

- **Hook dispatcher** (`dispatcher.py` / `post_dispatcher.py`) — single in-process entry point importing
  an ordered list of `check(input)->dict|None` modules. PreToolUse stops at the first `block` and
  aggregates allow-warnings; PostToolUse never blocks (exit 0 always), aggregates `systemMessage`s, and
  **fails open** on any hook exception. The hard-coded module list is the per-project seam — externalize
  it to config and the dispatcher is generic. ~12 hooks depend on the shared `_shell_parse.py`
  command-position git/gh parser (lift that verbatim first).
- **Status-file substrate** (`upsert_status_keys.py`, above).

Get these two and the shared-config schema right, and the rest of the corpus assembles on top.
