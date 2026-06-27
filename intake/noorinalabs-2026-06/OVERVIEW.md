# Overview — what was scanned, and the one finding that matters

## The headline finding

**Almost none of this machinery is welded to the source project's domain.** noorinalabs is an
Islamic-scholarship data platform (hadith / isnad / narrator graphs, Neo4j, PyArrow) — yet across
**22 skills, 42 hooks, 26 libs, 13 charter files, and a 2-layer ontology system**, the coupling to
that domain is nearly zero. The opinionation is almost entirely **stack & config**, not domain:

- the org name `noorinalabs` and the literal 7/8-repo list
- the wave/phase state file `cross-repo-status.json` and its key grammar (`wave_{M}_*`, `current_wave`)
- GitHub **Project #2** and the `Wave` single-select field
- branch grammar `deployments/phase-{N}/wave-{M}` and `{FirstInitial}.{LastName}/{IIII}-{slug}`
- label grammar `wave-{X}` (+ grandfathered `p{N}-wave-{M}`)
- the persona identities and the commit-identity convention `parametrization+{First}.{Last}@gmail.com`
- `.claude/` paths for charter / memory / ontology / lib-helpers

**Consequence:** genericisation is not a rewrite. It is mostly *externalizing one shared config
object* (org, repo-list, board-number, branch/label grammar, identity table, paths) and replacing
the baked-in tokens with references to it. Design that config schema once and ~80% of the
NEEDS-GENERICISATION bucket falls out generic. That config schema is the single biggest unblock —
it is currently un-designed, and it gates everything else.

## Scan results (aggregate)

| Bucket | Artifacts | GENERIC-READY | NEEDS-GENERICISATION | PROJECT-SPECIFIC |
|--------|-----------|:---:|:---:|:---:|
| Skills | 22 | 1 | 21 | 0 |
| Hooks | 42 | 18 | 19 | 5 |
| Lib | 26 | 8 | 15 | 3 |
| Governance (charter + team) | 20 | 6 | 13 | 1 |
| Ontology + docs + scripts | ~24 groups | 12 | 9 | ~6 |
| **Total** | **~134** | **~45** | **~77** | **~15** |

Read the three verdicts as:

- **GENERIC-READY** — product-neutral or trivially so; lift as-is or near-as-is. ~45 artifacts.
- **NEEDS-GENERICISATION** — a valuable, reusable *pattern* that hard-codes a stack/tool/path/
  identity/repo-name choice. The dominant bucket (~77). These are the real prize: the orchestration
  engine. They need the shared-config externalization, not redesign.
- **PROJECT-SPECIFIC** — only the abstract *shape* is reusable; the content is the source project's
  (the brand name, the Dockerfile base-pin policy, the VPS host, the Arabic-corpus fixtures, the
  `domain.yaml` entities). ~15 artifacts. Ship at most a trimmed schema example.

Per-row detail for every artifact lives in `classification/{skills,hooks,lib,governance,ontology-and-docs}.md`.

## The seven orchestration pillars

The machinery organizes cleanly into seven pillars. `ORCHESTRATION.md` is the deep dive; in brief:

| Pillar | What it is | Anchor artifacts |
|--------|-----------|------------------|
| **SCM** | Branch/merge discipline: per-issue branches, wave branches, one-merge-model-per-wave, no force-merge | `review-pr`, `sync_main.py`, `block_no_verify`, `validate_branch_freshness`, `block_squash_wave_merge` |
| **TICKETING** | Issues ↔ Project board sync, orphan detection, wave-label grammar, bug intake | `board-audit`, `file-bug`, `close-stale-issues`, `auto_add_issue_to_board`, `validate_labels` |
| **CI/CD** | Red-gate-is-a-stop: merge blocked on CI status, local⇄CI parity, deploy verification | `validate_pr_ci_status`, `pre_commit_ci_sync.py`, `pr_ci_state.py`, `watch-deploy`, `verify_deployable_merge.py` |
| **META-CHILD** | One meta-repo coordinating N gitignored child repos; cross-repo branch creation, child-checkout checks | `wave-kickoff`, `check_child_checkouts.py`, `roster_union_sync.py`, cross-repo ontology aggregation |
| **TEAM** | Persistent personas, mechanical trust scoring, feedback loops, fire/promote | `wave-retro`, `promotion-audit`, `trust_signals.py`, `validate_commit_identity`, the roster/trust/feedback schema |
| **MEMORY-ONTOLOGY** | 2-layer ontology (hand-curated semantic overlay + generated structural index), version-controlled memory | `ontology_gen/`, `ontology-librarian`, `ontology-rebuild`, `ontology_tracker`, `enforce_ontology_context` |
| **LIFECYCLE** | Wave/phase state machine: start → scope → kickoff → audit → wrapup → retro, with precondition gates | `wave-start/scope/kickoff/audit/wrapup`, `retro`, `phase-review`, `plan-phase`, `session-start`, `wave_seq.py` |

Two cross-cutting engines underpin all seven:

- **The hook dispatcher** (`dispatcher.py` / `post_dispatcher.py`) — a single in-process entry point
  that runs an ordered list of `check(input)->dict|None` modules instead of spawning N subprocesses;
  PreToolUse blocks at the first veto, PostToolUse never blocks and fails open. The hard-coded module
  list is the per-project seam.
- **The status-file substrate** (`upsert_status_keys.py`) — text-level JSON upsert that preserves a
  compact-inline file shape while every skill reads/writes wave state through it.

## Existing framework — what's already here, and the gap

The 2real-team-framework already has **two disjoint layers**:

- **Layer A (CLI):** `2real-team init` renders 6 Mustache `templates/` + a preset's skill stubs from
  a `preset` JSON + YAML config. Knows only team-scaffolding artifacts. Mustache vocabulary is tiny
  (`{{project_name}}`, a `{{#team_members}}` loop). Does **not** render hooks or libs — it has no
  artifact-manifest concept for them.
- **Layer B (`generic_prompts/`):** 78 hand-written genericisation recipes — but **not** wired into
  the CLI. They are authoring docs.

Coverage gap vs. the current noorinalabs reality (full table in `GENERICISATION-BACKLOG.md`):

| Class | noorinalabs | has a recipe | **net-new (no representation)** |
|-------|:---:|:---:|:---:|
| Skills | 22 | 14 (+4 stubs) | **4** |
| Hooks | 42 | 22 | **20** |
| Libs (top-level) | 26 | 21 | **5** |
| Libs `ontology_gen/` | 11 | 11 | 0 |
| Charter files | 13 | 6 | **7** |

**36 net-new artifacts** have no recipe yet. That is the authoring queue. The `ontology_gen` package
and the 2-layer ontology model are already fully covered — no work needed there.

## Recommended next moves (in order)

1. **Design the shared-config schema** (org, repo-list, board#, branch/label grammar, identity table,
   paths, lib-helper locations). Everything in NEEDS-GENERICISATION collapses to references into it.
2. **Author the 36 net-new Layer-B recipes** (see `GENERICISATION-BACKLOG.md`), prioritizing the
   safety/SCM/CI gates and the lifecycle engine.
3. **Decide the CLI's artifact-manifest** so Layer A can eventually render hooks+libs, not just
   templates. This is the larger, separable effort — flagged, not started.
