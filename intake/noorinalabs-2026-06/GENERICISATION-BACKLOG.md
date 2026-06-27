# Genericisation backlog

The actionable list: **what is opinionated / project-specific and could be genericised, and what it
would take.** Two parts: (A) the shared-config schema that unblocks ~80% of the work, and (B) the
36 net-new artifacts that have no Layer-B recipe yet.

---

## A. The shared-config schema (design this FIRST)

Nearly every NEEDS-GENERICISATION verdict reduces to the same recurring tokens. Externalize them once
into a single `team-framework.config` (YAML/JSON) and the opinionation across 77 artifacts collapses
to references into it. Proposed knob set, grouped by what reads it:

| Knob | Example (source value) | Read by |
|------|------------------------|---------|
| `org` | `noorinalabs` | every `gh` call, board-audit, kickoff |
| `repos[]` | the meta-repo + 7 child repos | wave-* skills, child-checkout, ontology aggregate |
| `meta_repo` | `noorinalabs-main` | meta-child coordination, state-file location |
| `board.project_number` | `2` | board-audit, file-bug, auto-add |
| `board.wave_field` | `Wave` (single-select) | board-audit field-sync |
| `branch.feature` | `{FirstInitial}.{LastName}/{IIII}-{slug}` | review-pr, close-stale, branch-freshness |
| `branch.wave` | `deployments/phase-{N}/wave-{M}` | kickoff, wrapup, wave-audit, merge-model |
| `label.wave` | `wave-{X}` (+ legacy `p{N}-wave-{M}`) | board-audit, wave-audit, kickoff, scope |
| `identity.email` | `parametrization+{First}.{Last}@gmail.com` | commit-identity hooks, trust, roster union |
| `identity.roster_source` | `.claude/team/roster.json` | identity validation, trust scoring |
| `state_file` | `cross-repo-status.json` + `wave_{M}_*` key grammar | every lifecycle skill, upsert substrate |
| `paths.charter` / `paths.memory` / `paths.ontology` | `.claude/team/`, `.claude/memory/`, `ontology/` | handoff, session-start, librarian, promotion |
| `paths.lib_helpers` | `.claude/lib/` | every skill that shells a helper |
| `policy.reviewers` | 2 | validate_pr_review, slates |
| `policy.td_intake` | +20% of feature/bug scope per wave | wave-scope, plan-phase |
| `policy.merge_model` | `wave-branch` \| `direct-to-main` | wave_merge_model, block_squash |
| `ci.tooling[]` | ruff/mypy/pytest/cspell/actionlint/gitleaks | pre_commit_ci_sync drift gate |
| `deploy.repo` / `deploy.workflows[]` / `deploy.failure_classes` | noorinalabs-deploy, deploy-{stg,prod}.yml | watch-deploy, verify_deployable_merge |
| `observability.error_log` | `.claude/annunaki/errors.jsonl` | annunaki subsystem |

The `dispatcher.py` module list is a *separate* per-project seam (which hooks are active, in what
order) — also config, but structurally distinct from the value knobs above.

---

## B. Net-new artifacts (no Layer-B recipe yet) — 36 to author

These exist in the source `.claude` but have **no** `generic_prompts/GENERIC_*_PROMPT.md` recipe. They
are the authoring queue. (`ontology_gen`'s 11 modules and the 2-layer ontology are already covered.)

### Hooks (20)

`_consultation_sentinel`, `auto_add_issue_to_board`, `auto_set_env_test`, `auto_sync_main`,
`block_git_config`, `block_no_verify`, `block_shutdown_without_retro`, `block_squash_wave_merge`,
`block_stale_tmp_message_file`, `enforce_ontology_context`, `no_worktree_self_delete`,
`suggest_generic_prompt`, `validate_branch_freshness`, `validate_edit_completion`, `validate_labels`,
`validate_lockfile_paths`, `validate_review_comment_format`, `validate_vps_host`,
`validate_wave_context`, `validate_workflow_paths_coverage`.

Priority within hooks: the **GENERIC-READY safety/SCM/CI** ones first (`block_no_verify`,
`block_git_config`, `no_worktree_self_delete`, `validate_labels`, `validate_branch_freshness`,
`validate_workflow_paths_coverage`) — they lift with almost no adaptation. `validate_vps_host` is
PROJECT-SPECIFIC (ship only its shape).

### Charter files (7)

`agents.md`, `branching.md`, `commits.md`, `communication.md`, `emergency-mode.md`, `skills.md`,
`state-claims.md`. The source charter is split into 13 topic files; 2real ships a single monolithic
`charter.md.mustache`. Splitting it and authoring these 7 modular sections is the charter delta.
(GENERIC-READY policy with example tokens: `branching`, `commits`, `communication`, `emergency-mode`,
`state-claims`. `agents.md` + `skills.md` carry more org-specific mechanics → NEEDS-GENERICISATION.)

### Libs (5)

`pr_review_state`, `roster_consistency_check`, `roster_union_sync`, `verify_commit_identity`,
`wave_status`. (`pr_review_state` is GENERIC-READY; the roster/identity trio is ⚙ on the identity
convention; `wave_status` is ⚙ on the state-file key grammar.)

### Skills (4)

`file-bug`, `handoff`, `team-reset`, `watch-deploy`. (`handoff` + `team-reset` are light; `file-bug` +
`watch-deploy` carry more config surface.)

---

## C. Stack-opinionated assets — genericise behind an explicit "target stack" choice

Per the original ask: some assets are opinionated about *programming language / tooling / deployment /
infra*, and are useful but need the target stack declared before they make sense.

| Asset | Stack assumption | Genericisation move |
|-------|------------------|---------------------|
| `.pre-commit-config.yaml` mirror + `pre_commit_ci_sync.py` | Python: ruff (pinned), mypy, pytest; cspell/actionlint/gitleaks | Drive the mirrored tool list from `ci.tooling[]`; ship per-stack presets (python / node / go) like the existing `presets/`. **The single clearest "needs the target stack" case.** |
| `auto_set_env_test.py` | `ENVIRONMENT=test` pytest convention | Parameterize the env-var + test-runner. |
| `TOOLCHAIN.md` | zsh shell, `ast-grep` over grep/sed, ruff pins, `uv` | Useful broadly; split the universally-true (zsh-safety, structural-search) from the stack-pinned (ruff/uv) parts. |
| `check_dockerfile_base_pin.py` | Docker base-image digest-pinning policy | PROJECT-SPECIFIC policy; ship as opt-in infra preset. |
| `warn_ghcr_image.py` / `validate_vps_host.py` | GHCR registry + a named VPS host | PROJECT-SPECIFIC; ship shape only. |
| `gen-office.sh` | LibreOffice doc generation | Niche; skip or ship as an example. |
| `watch-deploy` / `verify_deployable_merge.py` | GitHub Actions deploy workflows, Kafka/Alembic failure classes | Generic shape, ⚙ deploy config; the failure-class table is stack-specific. |

The framework already has a **preset** mechanism (`presets/data-pipeline.json`,
`fullstack-monorepo.json`, `library.json`) — that is the natural home for "target stack" bundles. The
backlog above suggests extending presets from *team shape* to also carry *`ci.tooling[]` + deploy
config*, so a `python-monorepo` preset can render the right pre-commit mirror.

---

## Sequencing recommendation

1. **Design the shared-config schema** (§A). Nothing else parameterizes cleanly without it.
2. **Author the GENERIC-READY net-new hooks + libs** (§B) — safety/SCM/CI first; smallest adaptation.
3. **Author the lifecycle + team skills recipes** (`session-start`, `wave-*`, `wave-retro`,
   `promotion-audit`) — highest value, larger config surface.
4. **Extend `presets/` to carry stack/CI/deploy config** (§C) so the opinionated assets render per-stack.
5. **(Separate, larger effort)** give the CLI an artifact-manifest so Layer A can render hooks+libs,
   not just team-scaffolding templates.
