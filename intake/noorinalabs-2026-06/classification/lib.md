# `.claude/lib/*.py` genericisation classification

Bucket: the 26 library Python files in `/home/parameterization/code/noorinalabs-main/.claude/lib/*.py`.
Skipped (not classified, per instructions): `tests/`, `__pycache__/`, and the `ontology_gen/` package.

> `ontology_gen/` (noted, not classified): an owned generator package (#855) that builds the
> structural ontology layer — `llms.txt`, `code-graph.json`, `cross-repo-graph.json` — from a repo's
> file/module/symbol graph, plus a cross-repo aggregator. Generic-in-spirit (a code-graph indexer)
> but org-coupled by its `noorinalabs` repo-namespacing and aggregation conventions; needs its own audit.

## Summary (counts per verdict)

| Verdict | Count | Files |
|---|---|---|
| `GENERIC-READY` | 8 | upsert_status_keys, wave_seq, pr_ci_state, pr_review_state, doc_freshness, pre_commit_ci_sync, check_agent_liveness, sync_main |
| `NEEDS-GENERICISATION` | 15 | wave_status, wave_merge_model, trust_signals, premise_check, verify_deployable_merge, wave_field_option, generic_prompt_tracker, annunaki_parse, check_child_checkouts, memory_budget, headcount_budget, roster_consistency_check, roster_union_sync, verify_commit_identity, wave_unwrapped |
| `PROJECT-SPECIFIC` | 3 | check_dockerfile_base_pin, check_fixture_realism, lint_skill_graphql_pagination |

The dominant opinionation across the NEEDS bucket is the same three knobs:
`noorinalabs/<repo>` hardcoded into `gh` calls, the `wave_{M}_*` / `cross-repo-status.json` status-file
key shape, and the `parametrization+{First}.{Last}@gmail.com` / roster.json identity convention.
Factor those into config and most of the NEEDS bucket lifts cleanly.

---

## Per-file rows

| name | verdict | pillar | what it does | what's opinionated | genericisation note |
|---|---|---|---|---|---|
| upsert_status_keys.py | GENERIC-READY | LIFECYCLE | Text-level JSON upsert/remove of top-level keys preserving compact-inline shape; validates JSON pre/post | Sibling-grouping heuristic keys off `wave_{N}_` prefix; docstrings cite `cross-repo-status.json` | Already generic mechanics; make the sibling-prefix regex a param. Ship as-is. |
| wave_seq.py | GENERIC-READY | LIFECYCLE | Monotonic never-resetting "wave" id allocator + phase/ordinal stamping over a status JSON | `wave_`/`global_wave_seq`/`phase` vocabulary; `HISTORICAL_FLOOR=15` migration seed; default path | Rename wave→iteration; drop the historical-floor migration constant. Clean generic counter. |
| pr_ci_state.py | GENERIC-READY | CICD | PR CI-readiness oracle reusing the merge-gate's `fetch_checks`/`classify_rollup` (empty rollup = hard not-ready) | Imports sibling hook by path; GitHub `statusCheckRollup` shape | GitHub-coupled but product-neutral. Ship with the CI-gate hook it reuses. |
| pr_review_state.py | GENERIC-READY | CICD | PR review-state oracle reusing Hook4's 2-reviewer/TechDebt logic | `REVIEW_THRESHOLD=2`, TechDebt line, wave-branch `deployments/phase-N/wave-M` sentinel; imports sibling hook | Generic GitHub review oracle; threshold + branch sentinel are config. Ships with its gate hook. |
| doc_freshness.py | GENERIC-READY | META-CHILD | Advisory gate: code changed in a documented surface without a matching doc touch; always exits 0 | `SURFACE_RULES` reference `.claude/hooks|lib`, `ontology/`, CLAUDE.md; opt-out trailer names | Engine is generic; `SURFACE_RULES` are data meant to be repo-extended. Ship engine + example rules. |
| pre_commit_ci_sync.py | GENERIC-READY | CICD | Drift gate: every CI-enforced check-kind must be mirrored in `.pre-commit-config.yaml` | `_KIND_PATTERNS` includes org-specific kinds (memory-budget, headcount-budget, fixture-realism, skill-graphql-pagination, office-drift) | Core classifier is fully generic; trim the org-specific kinds from the default pattern table. |
| check_agent_liveness.py | GENERIC-READY | TEAM | Pure snapshot evaluator for spawned-agent stalls (missing task / zero-artifact / throttle cadence) | Thresholds cite charter `agents.md`; snapshot schema assumes orchestrator-fed | Pure function, injectable snapshot, zero I/O. Thresholds are constants → config. Lift as-is. |
| sync_main.py | GENERIC-READY | SCM | Safe fast-forward of local default branch to remote when provably safe; never forces | `GENERATED_ALLOWLIST` = annunaki log + ontology checksums (2 paths) | Generic git ff-guard; the allowlist is the only knob → make it a param/config. |
| wave_status.py | NEEDS-GENERICISATION | LIFECYCLE | Wave repo-iteration + merged-PR set + counters (PR count / changes-requested / top-concentration) | `noorinalabs/<repo>` in every gh call; `wave_{M}_*` keys; `RequestOrReplied:ChangesRequested` verdict shape | Strong generic core (no-shell `_run_gh`, counter math); parameterise owner, key prefix, verdict regex. |
| wave_merge_model.py | NEEDS-GENERICISATION | LIFECYCLE | Declares one-merge-model-per-wave + mid-wave wave-branch reachability classifier (pure) | `noorinalabs/<repo>`; `deployments/phase-{P}/wave-{M}` branch; `wave_{M}_merge_model` key | `classify_reachability` is pure+generic; the gh/branch/key layer needs the same 3 knobs as wave_status. |
| trust_signals.py | NEEDS-GENERICISATION | TEAM | Per-engineer mechanical trust signals from merged-PR set + pure scoring/decay/retirement | Reuses wave_status (owner/keys); verdict `Requestor:`/`RequestOrReplied:` shape; identity = commit author name | Scoring layer is pure and very reusable; extraction inherits wave_status's coupling. Split + parameterise. |
| premise_check.py | NEEDS-GENERICISATION | TICKETING | Scope-time premise-rot gate: named file/symbol in an issue must still exist at repo HEAD | `resolve_repo_dir` assumes `noorinalabs-main` parent + `<root>/<repo>` child layout; default ref | Pure extraction + git checkers are generic; only repo-dir resolution is org-shaped → inject a resolver. |
| verify_deployable_merge.py | NEEDS-GENERICISATION | CICD | Post-merge verification that push-to-main-only workflows (Trivy etc.) went green for a SHA | GHA YAML/`on:` parsing + run-record logic fully generic; CLI examples cite noorinalabs repos | Almost generic — only repo arg is `owner/repo`. Light: scrub doc examples; the logic is reusable as-is. |
| wave_field_option.py | NEEDS-GENERICISATION | TICKETING | Idempotently ensures a GitHub Project-2 "Wave" single-select option exists for a wave label | `ORG="noorinalabs"`, `PROJECT_NUMBER=2`, field name `"Wave"`, `wave-{X}`/`p{N}-wave-{M}` grammar | GraphQL full-list-preserve mechanic is generic; org/project/field-name/label-grammar all need to be config. |
| generic_prompt_tracker.py | NEEDS-GENERICISATION | META-CHILD | Pending+decisions ledgers for the batched per-wave "genericize this artifact" checkpoint | Hardcodes `2real-team-framework/generic_prompts` sibling path; `.claude/` category map; wave vocabulary | The intake-tracker for THIS very framework; ledger mechanics generic but framework-path + categories are config. |
| annunaki_parse.py | NEEDS-GENERICISATION | SAFETY | Reader/filter for the error-monitor JSONL log (skips benign traces + low-confidence) | Imports `annunaki_log.TRACE_RECORD_TYPES` from sibling hook; default `.claude/annunaki/errors.jsonl`; "annunaki" branding | Generic JSONL error-log filter; rename annunaki→error-monitor, keep the trace/confidence schema as config. |
| check_child_checkouts.py | NEEDS-GENERICISATION | META-CHILD | Staleness guard + safe ff for the parent's embedded child-repo clones | Hardcoded 7-element `CHILD_REPOS` tuple of noorinalabs repo names | Logic is generic (reuses sync_main); the child-repo list must come from config/CLAUDE.md map. |
| memory_budget.py | NEEDS-GENERICISATION | MEMORY-ONTOLOGY | Hard-block budget gate on `.claude/memory/` corpus (index entries / file count / bytes) | `.claude/memory/MEMORY.md` path + `- [` index-row shape; `session_handoff.md` exclusion; tuned caps | Generic budget mechanic; paths + caps + index regex are config. Clean template once parameterised. |
| headcount_budget.py | NEEDS-GENERICISATION | TEAM | Hard-block budget gate on persona-card count in `.claude/team/roster/` | `.claude/team/roster` path; caps 9/6; calibration prose cites noorinalabs personas | Same budget mechanic as memory_budget; path + caps → config. Reusable roster-size gate. |
| roster_consistency_check.py | NEEDS-GENERICISATION | TEAM | Advisory: `roster.json` ⇄ `roster/*.md` identity-card drift (name/email match) | `.claude/team/roster.json` + card template (`**Name:**`/`**user.name:**`/`**user.email:**`) | Generic two-source drift check; the card-field regexes + paths are the template knobs. |
| roster_union_sync.py | NEEDS-GENERICISATION | META-CHILD | Sync-drift gate: parent union roster must superset every child-repo roster (fetched via gh) | `DEFAULT_CHILD_REPOS` noorinalabs list; `--owner noorinalabs`; `roster.json` path | Generic superset-drift gate; child-repo list + owner are config. Parallels pre_commit_ci_sync pattern. |
| verify_commit_identity.py | NEEDS-GENERICISATION | TEAM | CI gate: every non-merge commit author in a PR range is a known roster name | `GH_PRINCIPAL_LOGIN="parametrization"`; roster.json path; `--no-merges` GitHub merge convention | Generic author-allowlist gate; the principal login + roster source are config. Reusable identity gate. |
| wave_unwrapped.py | NEEDS-GENERICISATION | LIFECYCLE | Detects a wave merged to main but never formally wrapped (active+unwrapped+0 open PRs) | `noorinalabs/<repo>` gh calls; `wave_{M}_*` keys; `current_wave` pointer; wrapup-marker spellings | Same 3 status/gh knobs as wave_status; pure `evaluate` core is reusable once parameterised. |
| check_dockerfile_base_pin.py | PROJECT-SPECIFIC | NONE | Lints Dockerfile `FROM` for digest-pin + distro upgrade | Encodes a specific charter `tech-decisions.md § Base Image Pinning` policy (apk/apt/distroless table) | Domain-policy lint. Generic-CLI-shaped but the *rule* is a noorinalabs decision; ship as optional example. |
| check_fixture_realism.py | PROJECT-SPECIFIC | NONE | Lints Arabic-text fixtures for vocalization + عن transmission particle | Entirely about Arabic isnad/hadith corpus realism (harakat ranges, عن particle) | Pure domain (Islamic-scholarship corpus). Not reusable outside this product. Exclude from framework. |
| lint_skill_graphql_pagination.py | PROJECT-SPECIFIC | NONE | Lints skill `.md` for GitHub GraphQL `first: > 100` over-cap footgun | Scoped to `.claude/skills/**/*.md` and a board-audit-specific bug (#888) | Narrow regression guard for one internal footgun; could generalise to "GraphQL cap lint" but low value. |
