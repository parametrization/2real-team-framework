# Skill Classification — noorinalabs → 2real-team-framework

Bucket: the 22 skills in `.claude/skills/`. Read-only audit for lifting GENERIC orchestration
machinery out of the noorinalabs domain (hadith/isnad/Neo4j/specific repos/specific personas).

## Summary — counts per verdict

| Verdict | Count |
|---|---|
| GENERIC-READY | 1 |
| NEEDS-GENERICISATION | 21 |
| PROJECT-SPECIFIC | 0 |

**Headline:** essentially the entire skill set is reusable orchestration machinery. *None* is
welded to the hadith/Neo4j domain — the opinionation is uniformly **stack/config** (org name
`noorinalabs`, the 7-repo list, `cross-repo-status.json`, GitHub Project #2, persona names,
`deployments/phase-{N}/wave-{M}` branch grammar, `wave-{X}` label grammar, the `.claude/lib/*`
helper scripts), not domain. Genericise once via a shared config (org, repo-list, board-number,
branch/label grammar, persona/identity table, paths) and ~all 21 lift cleanly. The single
GENERIC-READY skill (`annunaki`) only touches framework-internal paths.

Recurring opinionated tokens across the bucket (parameterize these org-wide and most skills
fall out generic):
- `noorinalabs` org + the literal 7/8-repo list
- GitHub **Project 2** (`gh project … 2 --owner noorinalabs`)
- `cross-repo-status.json` (the wave/phase state file) + its key grammar (`wave_{M}_*`, `current_wave`)
- branch grammar `deployments/phase-{N}/wave-{M}` and `{FirstInitial}.{LastName}/{IIII}-{slug}`
- label grammar `wave-{X}` / grandfathered `p{N}-wave-{M}` and the Wave single-select field
- persona identities (Aino Virtanen, Wanjiku Mwangi, Nadia Khoury, Santiago Ferreira, Fatima Okonkwo)
  and commit identity `parametrization+{First}.{Last}@gmail.com`
- charter/memory paths under `.claude/team/` + `.claude/memory/`
- `.claude/lib/*` helper scripts (trust_signals, wave_merge_model, wave_field_option, sync_main, …)

---

## Per-skill table

| name | verdict | pillar | what's opinionated | genericisation note |
|---|---|---|---|---|
| annunaki | GENERIC-READY | NONE (observability) | only framework-internal paths: `.claude/annunaki/errors.jsonl`, `.claude/lib/annunaki_parse.py`, `post_dispatcher.py` | Lift as-is together with the annunaki hook+lib subsystem; no product coupling. |
| annunaki-attack | NEEDS-GENERICISATION | TICKETING | persona "Annunaki" commit identity + email, branch `Annunaki/{ISSUE}`, wave labels, Project board auto-add, 2-reviewer = Aino, `cross-repo-status.json` run-marker | Parameterize identity/reviewers/label-scheme/board; the error→hook/skill/charter classify+file pipeline is generic. |
| board-audit | NEEDS-GENERICISATION | TICKETING | `org=noorinalabs`, **project 2**, literal 8-repo list, Wave-field option grammar `W{X}`/`P{N}W{M}`, GraphQL pagination over noorinalabs | Parameterize org/project-number/repo-list/label-grammar; orphan-detect + field-sync logic is reusable as-is. |
| close-stale-issues | NEEDS-GENERICISATION | TICKETING | branch naming `{FirstInitial}.{LastName}/{ISSUE}-*`, wave-label patterns `p*-wave-*`/`wave-*`, tech-debt tracker convention | Parameterize branch-name regex + label patterns; merged-PR→issue resolution map is generic. |
| file-bug | NEEDS-GENERICISATION | TICKETING | `noorinalabs/<repo>` names + cross-repo examples (CSP/OAuth/notify-deploy), project 2, wave labels, memory/charter file refs, telemetry log path | Strip domain examples; parameterize repo-list/board/paths. The 3-pass dup/drift/multi-layer discriminator is high-value generic. |
| handoff | NEEDS-GENERICISATION | MEMORY-ONTOLOGY | literal repo-list loop, `cross-repo-status.json`, `MEMORY.md`, `ontology/checksums.json` paths | Parameterize repo-list + state/memory/ontology paths; session-pickup shape is generic. |
| ontology-librarian | NEEDS-GENERICISATION | MEMORY-ONTOLOGY | `ontology_gen` generator + aggregate, `ontology/` layout, source globs incl `.cypher/.cql` (Neo4j hint), Hook-15 sentinel scheme | Ships with the ontology subsystem; parameterize source-file globs + repo layout. Two-layer (semantic/structural) model is reusable. |
| ontology-rebuild | NEEDS-GENERICISATION | MEMORY-ONTOLOGY | Aino commit identity, ontology file names, `noorinalabs-isnad-graph` example, repo list, doc-freshness gate | Parameterize commit identity + repo list; code-is-arbiter resolver logic is generic. |
| phase-review | NEEDS-GENERICISATION | LIFECYCLE | tracking-issue grammar `noorinalabs-main#N`, phase-doc path `.claude/team/phases/`, 7-child-repo aggregation, 10% TD exit gate | Parameterize repo/issue-ref grammar + gate thresholds + phase-doc path. |
| plan-phase | NEEDS-GENERICISATION | LIFECYCLE | project 2, 8-repo list, roster cards, +20% TD intake policy, label scheme, 6-perspective review | Parameterize board/repos/roster/label-scheme/TD-policy; decompose+wave-structure logic generic. |
| promotion-audit | NEEDS-GENERICISATION | TEAM | Aino identity, org, project 2, wave labels, base `deployments/phase-{N}/wave-{M}`, reviewers Wanjiku/Nadia/Santiago, charter dir layout, `run.py`/`helpers.py` | Parameterize identities/board/branch/charter-paths. The memory→charter→skill→hook promotion pipeline (enforcement hierarchy) is crown-jewel generic + deterministic. |
| retro | NEEDS-GENERICISATION | LIFECYCLE | `cross-repo-status.json`, wave labels, base `main` | Light: parameterize state file + label scheme; mid-wave health-pulse queries are generic. |
| review-pr | NEEDS-GENERICISATION | SCM | charter verdict format (`Requestor`/`Requestee`/`RequestOrReplied`) that hooks parse, tech-debt+next-phase label scheme | Parameterize the review-comment template + label scheme; otherwise generic gh PR review. |
| session-start | NEEDS-GENERICISATION | LIFECYCLE | 7-child-repo list, org, `cross-repo-status.json`, `ontology_gen`, lib helpers (sync_main, check_child_checkouts, wave_unwrapped, wave_merge_model), Aino identity, base-image-CVE classifier, wave grammar | Parameterize repo-list/org/state-path/helpers/identity; the 7-step startup-orientation protocol (worktree→team→handoff→ontology→annunaki→wave→charter) is high-value generic. |
| team-reset | NEEDS-GENERICISATION | TEAM | roster path `.claude/team/roster/`, example persona "Fatima Okonkwo", `team_name` | Light: parameterize roster path + team name; agent shutdown/re-orient flow is generic. |
| watch-deploy | NEEDS-GENERICISATION | CICD | `noorinalabs-deploy`, `deploy-stg.yml`/`deploy-prod.yml`, fan-in repos isnad-graph/user-service, `repository_dispatch`, GHCR, kafka/alembic failure classes, rollback/promote workflows | Parameterize deploy-repo/workflow-names/fan-in-repos + failure-class signal table; poll→classify→bounded-fix-forward→escalate shape is generic. |
| wave-audit | NEEDS-GENERICISATION | LIFECYCLE | base `deployments/phase-{N}/wave-{M}`, wave-label grammar, branch naming, `fixed-in-phase{N}-wave-{M}` label | Parameterize branch/label grammar; orphan-close-against-merged-PR logic generic. |
| wave-kickoff | NEEDS-GENERICISATION | LIFECYCLE | org/repo-list, `cross-repo-status.json`, deployments branch grammar, personas (Wanjiku/Fatima), project 2 + Wave field, lib helpers (wave_merge_model, wave_field_option), child-repo-implementer rule, ontology-context bake, label grammar, OAuth scopes | Parameterize the full config bundle. Crown-jewel: branch-create + idempotency + label/board sync + merge-model declaration + spawn-brief preflight + task ledger. |
| wave-retro | NEEDS-GENERICISATION | TEAM | `trust_signals.py`/`trust_matrix.md`, `feedback_log.md`, deployments branch, personas, project 2, charter paths, board-audit/promotion-audit integration | Parameterize lib-helpers/identities/branch/paths. Crown-jewel: mechanical evidence-anchored trust scoring + feedback log + charter-change proposals. |
| wave-scope | NEEDS-GENERICISATION | LIFECYCLE | org/repos, wave labels, meta-issue convention, `cross-repo-status.json`, +20% TD intake, retro-carryforward/memory-must-include | Parameterize repos/labels/board/state + TD policy; declared-vs-labeled scope reconciliation is generic. |
| wave-start | NEEDS-GENERICISATION | LIFECYCLE | repo-list worktree cleanup, deployments branch grammar, label setup, `cross-repo-status.json` | Parameterize repos/branch/label/state; wave-init (worktree clean + branch + status) shape generic. |
| wave-wrapup | NEEDS-GENERICISATION | LIFECYCLE | org/repos, deployments branch + merge-model, personas, project 2, charter/ontology paths, deploy-verify (verify_deployable_merge), annunaki/handoff integration, lib helpers | Parameterize the full bundle; PR-review→merge-sequencing→deploy-verify→ontology→handoff lifecycle is crown-jewel generic. |

---

## Notes on pillar coverage

- **LIFECYCLE** (10): wave-start, wave-scope, wave-kickoff, wave-audit, wave-wrapup, retro, phase-review, plan-phase, session-start (orientation). The wave/phase engine is the densest and most opinionated cluster — all share one config surface.
- **TICKETING** (4): board-audit, close-stale-issues, file-bug, annunaki-attack.
- **TEAM** (3): wave-retro (trust), promotion-audit (governance), team-reset.
- **MEMORY-ONTOLOGY** (3): ontology-librarian, ontology-rebuild, handoff.
- **CICD** (1): watch-deploy.
- **SCM** (1): review-pr.
- **NONE/observability** (1): annunaki.

## Genericisation strategy (one line)

Author a single `team-framework.config` (org, repo-list, board-number, branch grammar, label
grammar, persona/identity table, state-file path, charter/memory/ontology paths, lib-helper
locations). Almost every skill's opinionation collapses to references into that config. The
`.claude/lib/*` Python helpers (trust_signals, wave_merge_model, wave_field_option, promotion
helpers.py, annunaki_parse, sync_main) are the load-bearing generic engines and lift with their
skills — they belong in the same bucket review.
