# Classification — master index

Every one of the ~134 scanned artifacts has a verdict, an orchestration pillar, a "what's
opinionated" note, and a one-line genericisation note. The **full per-artifact tables** live in the
appendices below (verbatim output of the five classification passes). This file is the index +
aggregate + the highest-value lift shortlist.

## Verdicts

- **GENERIC-READY** — product-neutral or trivially so; lift as-is / near-as-is.
- **NEEDS-GENERICISATION** — reusable pattern that hard-codes a stack/tool/path/identity/repo-name; fix
  via the shared-config object, not a rewrite.
- **PROJECT-SPECIFIC** — only the abstract shape is reusable; content is the source project's.

## Aggregate

| Bucket | Artifacts | GENERIC-READY | NEEDS-GEN | PROJECT-SPECIFIC | Appendix |
|--------|:---:|:---:|:---:|:---:|----------|
| Skills | 22 | 1 | 21 | 0 | [`classification/skills.md`](classification/skills.md) |
| Hooks | 42 | 18 | 19 | 5 | [`classification/hooks.md`](classification/hooks.md) |
| Lib | 26 | 8 | 15 | 3 | [`classification/lib.md`](classification/lib.md) |
| Governance | 20 | 6 | 13 | 1 | [`classification/governance.md`](classification/governance.md) |
| Ontology + docs | ~24 | 12 | 9 | ~6 | [`classification/ontology-and-docs.md`](classification/ontology-and-docs.md) |
| **Total** | **~134** | **~45** | **~77** | **~15** | |

## Highest-value lift shortlist

The artifacts to extract first — highest reuse value, lowest genericisation cost.

### GENERIC-READY — lift now, near-zero rework

| Artifact | Pillar | Why |
|----------|--------|-----|
| `_shell_parse.py` | (foundation) | Command-position git/gh parser; ~12 hooks depend on it. Lift first. |
| `upsert_status_keys.py` | LIFECYCLE | Text-level JSON upsert preserving compact shape; the state substrate. |
| `validate_pr_ci_status.py` + `pr_ci_state.py` | CI/CD | Block merge on red/empty CI rollup. Universal merge gate. |
| `pr_review_state.py` | TEAM | N-reviewer-before-merge oracle. |
| `block_no_verify.py` | SCM/safety | Refuse `--no-verify`. Universal. |
| `block_git_config.py` | SCM/safety | Refuse `git config user.*` mutation. |
| `warn_pipe_mask_rc.py` | SCM/safety | Catch rc-masking pipes (`git push | tail`). Non-obvious footgun. |
| `warn_zsh_wordsplit.py` | safety | zsh bash-ism warner; any zsh project as-is. |
| `sync_main.py` | SCM | Provably-safe fast-forward; never forces. |
| `pre_commit_ci_sync.py` | CI/CD | Local⇄CI drift gate. |
| `check_agent_liveness.py` | META-CHILD | Pure zero-I/O multi-agent stall detector. |
| `wave_seq.py` | LIFECYCLE | Monotonic never-reset id allocator. |
| `validate_workflow_paths_coverage.py` | CI/CD | Flags un-CI'd workflow files. |
| `ontology_gen/` (11 modules) | MEMORY-ONTOLOGY | Stdlib-only deterministic code-graph generator. Ships verbatim. |
| `check-mermaid.py` | CI/CD | Mermaid-diagram validator. |

### NEEDS-GENERICISATION — the prize (extract after shared-config schema exists)

| Artifact | Pillar | The one knob it needs |
|----------|--------|----------------------|
| `wave-kickoff` | LIFECYCLE | Full config bundle (org/repos/branch/board/identity). The orchestration centerpiece. |
| `wave-wrapup` | LIFECYCLE | Same bundle. PR-review → merge-sequence → deploy-verify → ontology → handoff. |
| `wave-retro` + `trust_signals.py` | TEAM | Roster + lib-helper paths. Mechanical evidence-anchored trust scoring. |
| `promotion-audit` | TEAM | Identities + charter paths. The enforcement-hierarchy pipeline. |
| `board-audit` | TICKETING | org / project# / repo-list / label grammar. GraphQL pagination patterns included. |
| `session-start` | LIFECYCLE | repo-list / paths / helpers. The 7-step resume protocol. |
| `validate_pr_review.py` | TEAM | Reviewer count + verdict format. |
| `validate_commit_identity.py` | TEAM | Email regex + roster source. |
| `dispatcher.py` / `post_dispatcher.py` | (engine) | Externalize the hard-coded module list. |
| `file-bug` | TICKETING | repo-list / board. The 3-pass dup/drift/multi-layer discriminator. |
| `watch-deploy` | CI/CD | deploy-repo / workflow names / failure-class table. |

### PROJECT-SPECIFIC — ship at most a trimmed schema example, or skip

`brand.md` (the literal brand-name guard — concept generic, content not), `validate_vps_host.py`,
`check_dockerfile_base_pin.py`, `check_fixture_realism.py`, `lint_skill_graphql_pagination.py`,
`domain.yaml` / `services.yaml` / `repos/*.yaml` (overlay *content* — schema is a generic template),
`architecture*.md`, `settings.local.json` (omitted entirely).

## How to read the appendices

Each appendix opens with its own per-verdict counts and a "recurring opinionated tokens" note, then a
full table (`name | verdict | pillar | what's opinionated | genericisation note`) and per-artifact
prose. They are the verbatim, authoritative classification — this index summarizes; they decide.
