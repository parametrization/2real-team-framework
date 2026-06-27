# Hook Classification — 2real-team-framework extraction audit

Scope: 42 Python files in `.claude/hooks/*.py` (incl. `_*.py` shared parsers; tests/fixtures/audit/__pycache__ excluded).
Read-only classification. Verdicts: GENERIC-READY / NEEDS-GENERICISATION / PROJECT-SPECIFIC.

## Summary counts

| Verdict | Count |
|---------|-------|
| GENERIC-READY | 18 |
| NEEDS-GENERICISATION | 19 |
| PROJECT-SPECIFIC | 5 |
| **Total** | **42** |

By pillar (primary): SAFETY 9, SCM 4, CICD 5, TICKETING 4, TEAM 4, MEMORY-ONTOLOGY 5, LIFECYCLE 6, NONE/infra 5.

## Dispatcher architecture

`dispatcher.py` (PreToolUse, matcher=Bash) and `post_dispatcher.py` (PostToolUse, matcher=Bash/Edit/Write/NotebookEdit) are single in-process entry points: instead of N subprocess invocations per tool call, each imports an ordered list of hook modules (`_BASH_HOOKS` / `_REGISTRY`) and calls each module's `check(input_data)->dict|None`. PreToolUse: first `decision:"block"` wins (exit 2); allow-warnings aggregated. PostToolUse: never blocks (exit 0 always), aggregates `systemMessage`s, fail-open on any hook exception, with per-check annunaki dispatch-tracing (#425). Both put hooks dir on sys.path; cheap/local checks ordered first, network-calling checks last. The two dispatchers are the ONE place the per-project hook registry lives — genericisation seam: make the module lists config-driven.

## Per-hook table

| name | verdict | pillar | trigger | wired-via | opinionated | genericisation note |
|------|---------|--------|---------|-----------|-------------|--------------------|
| dispatcher.py | NEEDS-GENERICISATION | NONE | PreToolUse(Bash) | — (is the dispatcher) | hard-coded `_BASH_HOOKS` list | mechanism generic; externalize the module registry to config |
| post_dispatcher.py | NEEDS-GENERICISATION | NONE | PostToolUse | — (is the dispatcher) | hard-coded `_REGISTRY`, imports annunaki_log | mechanism generic; externalize registry; rename annunaki dep |
| _shell_parse.py | GENERIC-READY | SAFETY | shared lib | imported by ~12 hooks | none — pure shlex/bashlex git/gh command-position parser | lift verbatim; foundational, all gh/git matchers depend on it |
| _repo_flag_parse.py | GENERIC-READY | SCM | shared lib | imported by validate_labels, warn_ghcr_image, … | none — `--repo/-R` 4-form extraction | lift verbatim (generic gh CLI) |
| _wave_label_parse.py | PROJECT-SPECIFIC | LIFECYCLE | shared lib | post_wave_kickoff_comment, post_label_change_wave_field_sync | `p{N}-wave-{M}` / `wave-{X}` grammar | only abstract shape (label-change parser) reusable |
| _consultation_sentinel.py | GENERIC-READY | MEMORY-ONTOLOGY | shared lib | enforce_librarian_consulted | cwd-keyed skill-consult marker; `.claude/.consulted/` path | generic mechanism for "did skill X run"; param skill name |
| annunaki_log.py | GENERIC-READY | SAFETY | shared lib | most blocking hooks | `.claude/annunaki/` path, "annunaki" naming, test-mode env vars | rename "annunaki"→error-log; JSONL block-logging is generic |
| annunaki_monitor.py | GENERIC-READY | SAFETY | PostToolUse(Bash) | post_dispatcher | "annunaki" naming; error/ignore regex patterns | rename; error-signal detection over Bash output is generic |
| validate_commit_identity.py | NEEDS-GENERICISATION | SAFETY/TEAM | PreToolUse(Bash) | dispatcher | roster.json path, persona email `parametrization+First.Last@gmail.com` | param roster source + email regex; identity-on-every-commit is generic |
| block_no_verify.py | GENERIC-READY | SAFETY | PreToolUse(Bash) | dispatcher | "charter" wording only | universal — block `--no-verify` on commit/push |
| block_git_config.py | GENERIC-READY | SAFETY | PreToolUse(Bash) | dispatcher | "charter" wording; blocks `user.*` writes | universal — protect git identity namespace |
| block_gh_pr_review.py | NEEDS-GENERICISATION | TEAM/SCM | PreToolUse(Bash) | dispatcher | "all agents share one GitHub user"; Requestor/Requestee format | param: gate `gh pr review` only under shared-principal team model |
| block_stale_tmp_message_file.py | GENERIC-READY | SAFETY | PreToolUse(Bash) | dispatcher | references a feedback memory; `/tmp/` paths | generic — stale body-file race guard for git/gh |
| no_worktree_self_delete.py | GENERIC-READY | SAFETY/SCM | PreToolUse(Bash) | dispatcher | none — fs ancestry check | universal git-worktree footgun guard |
| block_shutdown_without_retro.py | PROJECT-SPECIFIC | TEAM/LIFECYCLE | PreToolUse(SendMessage) | standalone | structured shutdown_request, feedback_log.md retro, sim-team | abstract shape (gate shutdown on precondition) reusable only |
| block_squash_wave_merge.py | NEEDS-GENERICISATION | SCM/LIFECYCLE | PreToolUse(Bash) | dispatcher (last) | `deployments/phase-N/wave-M` regex, persona-email aliasing | param protected-base-branch pattern + squash-author rationale |
| validate_lockfile_paths.py | GENERIC-READY | CICD/SAFETY | PreToolUse(Bash) | dispatcher | none — `/tmp/`,`file:/` in package-lock.json | generic for any npm project |
| validate_labels.py | GENERIC-READY | TICKETING | PreToolUse(Bash) | dispatcher | none — validates `gh issue create` labels exist | generic gh/GitHub |
| validate_wave_label_evidence.py | NEEDS-GENERICISATION | TICKETING | PreToolUse(Bash) | dispatcher | `p\d+-wave-\d+` trigger; cross-repo wave branch refs | "verify cited file paths exist at origin" is generic; decouple from wave-label trigger |
| validate_review_comment_format.py | NEEDS-GENERICISATION | TEAM | PreToolUse(Bash) | dispatcher | Requestor/Requestee swap, charter Direction table | param the review-comment schema |
| validate_pr_review.py | NEEDS-GENERICISATION | TEAM | PreToolUse(Bash) | dispatcher | 2-reviewer rule, charter comment format, shared-principal, batch-loop guard | HIGH VALUE; param reviewer count + review format/source |
| validate_pr_ci_status.py | GENERIC-READY | CICD | PreToolUse(Bash) | dispatcher | charter admin-merge exception list; sibling-coverage coupling | core (block merge on red statusCheckRollup) generic; param admin-allowlist |
| validate_branch_freshness.py | GENERIC-READY | SCM | PreToolUse(Bash) | dispatcher | base defaults "main" | generic — block PR-create when branch behind base |
| validate_workflow_paths_coverage.py | GENERIC-READY | CICD | PreToolUse(Bash) | dispatcher | names 2 path-filtered repos in prose | generic GitHub-Actions workflow-orphan guard |
| validate_vps_host.py | PROJECT-SPECIFIC | CICD | PreToolUse(Bash) | dispatcher | `VPS_HOST` var, Cloudflare IP ranges, SSH-deploy | only abstract (validate a deploy var) reusable |
| warn_ghcr_image.py | NEEDS-GENERICISATION | CICD | PreToolUse(Bash) | dispatcher | `REPO_IMAGE_MAP` noorinalabs ghcr images, noorinalabs org | param image map + org; deploy-image-exists warn is generic |
| auto_set_env_test.py | NEEDS-GENERICISATION | CICD | PreToolUse(Bash) | dispatcher | `ENVIRONMENT=test`, pytest/make-test | param env-var name + test-runner regex |
| warn_zsh_wordsplit.py | GENERIC-READY | SAFETY | PreToolUse(Bash) | dispatcher | none — flags bash-isms under zsh | lift verbatim for any zsh project |
| warn_pipe_mask_rc.py | GENERIC-READY | SAFETY/SCM | PostToolUse(Bash) | post_dispatcher | git push/gh pr merge specific maskers | generic rc-masking-pipe footgun; broaden trigger commands |
| auto_sync_main.py | GENERIC-READY | SCM | PostToolUse(Bash) | post_dispatcher | "main" branch name; sync_main lib | generic — ff local default branch after push/merge |
| auto_add_issue_to_board.py | NEEDS-GENERICISATION | TICKETING | PostToolUse(Bash) | post_dispatcher | project #2, noorinalabs org, Wave single-select field | param project id/org/field; auto-add-issue-to-board generic |
| post_label_change_wave_field_sync.py | NEEDS-GENERICISATION | TICKETING | PostToolUse(Bash) | post_dispatcher | project 2 Wave field, `p{N}-wave-{M}` | board-field-sync-on-label generic; param field+label grammar |
| post_wave_kickoff_comment.py | PROJECT-SPECIFIC | LIFECYCLE/TICKETING | PostToolUse(Bash) | post_dispatcher | wave kickoff template, cross-repo-status.json tier arrays, roster slots | only abstract (auto-comment on label-apply) reusable |
| ontology_tracker.py | NEEDS-GENERICISATION | MEMORY-ONTOLOGY | PostToolUse(Edit/Write) | post_dispatcher | `ontology/checksums.json` tracked dir | generic checksum change-tracker; param tracked path(s) |
| suggest_generic_prompt.py | NEEDS-GENERICISATION | MEMORY-ONTOLOGY/META-CHILD | PostToolUse(Edit/Write) | post_dispatcher | `.claude/` artifact, generic_prompt_tracker ledger | abstract: track artifact edits for later review |
| validate_edit_completion.py | GENERIC-READY | SAFETY | PostToolUse + PreToolUse(Edit/Write/Bash/SendMessage) | dispatcher + post_dispatcher + NotebookEdit | SendMessage tool; sentinel under .claude/ | generic tool-error-soft-accept guard; SendMessage branch optional |
| enforce_ontology_context.py | NEEDS-GENERICISATION | MEMORY-ONTOLOGY/TEAM | PreToolUse(Agent) | standalone | ontology markers, coordinator role enumeration | param context-markers + exempt-role list |
| enforce_librarian_consulted.py | NEEDS-GENERICISATION | MEMORY-ONTOLOGY | PreToolUse(Edit/Write/NotebookEdit) | standalone | `/ontology-librarian` skill, allow-list paths | param required-skill name; transcript-scan mechanism generic |
| validate_wave_context.py | NEEDS-GENERICISATION | LIFECYCLE/TEAM | PreToolUse(Agent) | standalone | cross-repo-status.json wave keys | param status-file + active-marker keys |
| validate_wave_audit.py | PROJECT-SPECIFIC | LIFECYCLE | PreToolUse(Skill) | standalone | wave-wrapup/retro/handoff skills, cross-repo audit, carry-forward | abstract (gate lifecycle skill on precondition) reusable |
| session_start.py | NEEDS-GENERICISATION | LIFECYCLE | SessionStart | settings.json | 7-step protocol: ontology/annunaki/wave/charter/handoff paths | generic session-orientation shape; param the step set/paths |
| session_handoff.py | NEEDS-GENERICISATION | LIFECYCLE/MEMORY | Stop | settings.json | git/PR/issue/wave/ontology state to .claude/memory | param captured-state set + memory path |

## Notes on dispatcher wiring

- PreToolUse Bash hooks run via `dispatcher.py` (21 modules in `_BASH_HOOKS`).
- PostToolUse hooks run via `post_dispatcher.py` `_REGISTRY` (Bash: annunaki_monitor, warn_pipe_mask_rc, auto_sync_main, auto_add_issue_to_board, post_wave_kickoff_comment, post_label_change_wave_field_sync; Edit/Write: ontology_tracker, suggest_generic_prompt, validate_edit_completion; NotebookEdit: validate_edit_completion).
- Standalone (own settings.json entry, NOT in a dispatcher): enforce_ontology_context, enforce_librarian_consulted, validate_wave_context, validate_wave_audit (non-Bash matchers: Agent/Skill/Edit), block_shutdown_without_retro (SendMessage), session_start (SessionStart), session_handoff (Stop).
</content>
</invoke>
