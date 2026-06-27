# Artifact Ownership — Meta Repo vs Child Repos <!-- promotion-target: none -->

Canonical disambiguation of **which `.claude/` (and ontology/) artifact classes are owned where, and where each one executes**, across the org parent repo (`noorinalabs-main`) and the 7 child repos. This is the single source of truth for Phase-3 end-state criterion #7 (`noorinalabs-main#328`); it consolidates semantics that were previously scattered across `charter/hooks.md § Hook Sync Across Child Repos`, `CLAUDE.md § Session team architecture`, `charter/skills.md`, and the `Hook Audit Protocol`.

Two distinct axes, kept separate throughout:

- **Ownership** — which repo's tree is the single source of truth for the artifact's content (where a change to it must land).
- **Execution location** — where the artifact actually runs / is read at invocation time (which may differ from where it is owned, e.g. a parent-owned hook that fires inside a child-repo commit).

## Ownership + execution matrix

| Artifact class | Lives at (owner) | Executes / is read at | Parent-vs-child semantics |
|---|---|---|---|
| **Shared hooks** (`*.py` + support: `dispatcher.py`, `annunaki_log.py`, `_shell_parse.py`, `_consultation_sentinel.py`, …) | `noorinalabs-main/.claude/hooks/` **ONLY** | Every repo — each child's `.claude/settings.json` registers them by **absolute path** into the parent tree | **Parent-canonical.** Children are *dispatcher-style*: no local `.py` copies. See `hooks.md § Hook Sync Across Child Repos`. |
| **Child-local hooks** (a hook specific to one repo's surface) | `<child>/.claude/hooks/` | That child only | **Child-owned.** Rare; none currently exist. A child-local *doc* (e.g. `<child>/.claude/hooks/audit/*.md`) is NOT hook code and is fine. |
| **Org-level skills** (wave lifecycle, ontology, promotion, board, file-bug, session-start, …) | `noorinalabs-main/.claude/skills/<name>/SKILL.md` (directory form) | Run from the parent session (org-coordination team) | **Parent-canonical.** The 22 org skills are owned here. |
| **Per-repo skills** (a workflow only meaningful inside one repo) | `<child>/.claude/skills/<name>/SKILL.md` | That child's session | **Child-owned**, only when genuinely repo-specific. NOT a copy of an org skill (see § Collision rules). |
| **Org-wide charter** (`agents.md`, `hooks.md`, `pull-requests.md`, `issues.md`, `skills.md`, `state-claims.md`, `commits.md`, `branching.md`, `communication.md`, `tech-decisions.md`, `emergency-mode.md`, `brand.md`, plus root `CLAUDE.md`) | `noorinalabs-main/.claude/team/charter/` + `noorinalabs-main/CLAUDE.md` | Read by every agent in every repo | **Parent-canonical.** Child charter sections must not restate org rules; they add only repo-specific build/architecture detail. |
| **Per-repo charter / CLAUDE.md** | `<child>/CLAUDE.md` (+ any `<child>/.claude/team/charter/` repo-specific docs) | That child's agents | **Child-owned**, repo-specific scope only (build commands, architecture, conventions). |
| **Rosters** (commit identity, domain ownership, reviewer pairing) | `<repo>/.claude/team/roster/` + `<repo>/.claude/team/roster.json` (parent AND each child) | Hook 5 reads the *working repo's* roster at commit time | **Each repo owns its own roster.** Session team is a logical overlay; the per-repo roster is canonical for identity. See `CLAUDE.md § Session team architecture`. |
| **Memory** (`feedback_*.md`, `project_*.md`, `MEMORY.md`) | Project memory dir (machine-local, OUTSIDE any repo: `~/.claude/projects/<slug>/memory/`) | Recalled into the session that wrote it | **Machine-local, not versioned.** Never committed to any repo. |
| **Ontology — semantic overlay** (`domain.yaml`, `services.yaml`, `conventions.md`, `repos/*.yaml`, `checksums.json`) | `noorinalabs-main/ontology/` | Read by `/ontology-librarian` / `/ontology-rebuild`; tracker hook updates `checksums.json` on **overlay** edits in any repo | **Parent-canonical, versioned.** Hand-curated. Org-wide entities live here; per-repo internals under `ontology/repos/<repo>.yaml`. |
| **Ontology — structural layer** (`ontology/structural/`) | `noorinalabs-main/ontology/` | Built by the owned generator (#855); read by `/ontology-librarian` | **Parent-canonical, versioned, GENERATED.** Always-current-by-regeneration — **not** checksum-tracked and **not** resolved by `/ontology-rebuild` (#857, #820/C×T2). Regenerate via its generator, never hand-edit. |
| **Settings** (`settings.json` vs `settings.local.json`) | `<repo>/.claude/settings.json` (versioned) and `<repo>/.claude/settings.local.json` (machine-local) | The harness, per repo, at session start | **`settings.json` is versioned + owned per repo** (registers the parent hooks for children). **`settings.local.json` is machine-local**, never committed. |

## Collision rules

1. **Skill name collisions (org vs per-repo).** An org-level skill name (the 22 in `noorinalabs-main/.claude/skills/`) is **reserved org-wide**. A child repo MUST NOT ship a same-named skill that merely duplicates the org one — that is the skill analogue of the copy-resident hook anti-pattern (drift with no sync check). A child may define a skill with a DISTINCT name for a genuinely repo-specific workflow. If a child needs to *invoke* an org skill, it runs in the parent-rooted session; it does not copy the SKILL.md.
2. **Hook name collisions.** A child-local hook MUST NOT share a name with a parent shared hook. Hook 5 / dispatcher resolution is by absolute path into the parent tree; a same-named child copy is the copy-resident anti-pattern (`hooks.md § Anti-pattern: copy-resident hooks`).
3. **Charter section collisions.** Org-wide rules live ONLY in the parent charter. A child `CLAUDE.md` that restates an org rule creates a second source of truth that silently drifts; children reference the parent section instead.
4. **Format collisions (skills).** The canonical skill format is the **directory form** `<name>/SKILL.md`. The legacy **flat `<name>.md`** form is deprecated; a flat-`.md` skill file in a child that shadows an org skill is drift to be cleaned (see § Audit).

## Audit of existing artifacts against this doc (2026-05-31)

Method: committed-tree inspection (`gh api repos/<repo>/git/trees/main?recursive=1`), per `Hook Audit Protocol` — NOT filesystem enumeration.

| Repo | Finding | Verdict |
|---|---|---|
| noorinalabs-main | 22 org skills (dir form), shared hooks tree, 12 charter docs + root CLAUDE.md, ontology/ | **canonical — OK** |
| noorinalabs-isnad-graph | `.claude/hooks/audit/parser_fixture_coverage.md` is a child-local DOC (not `.py` hook code); 16 charter docs; 10 **flat-`.md`** skill files (`wave-kickoff.md`, `retro.md`, `review-pr.md`, …) shadowing org skills | **DRIFT** — flat-`.md` skills duplicate org skills (collision rule 1 + 4) |
| noorinalabs-deploy, noorinalabs-landing-page, noorinalabs-data-acquisition | 10 **flat-`.md`** skill files each, shadowing org skills; 0 committed hooks (dispatcher-style) | **DRIFT** — flat-`.md` skill duplicates |
| noorinalabs-user-service, noorinalabs-design-system, noorinalabs-isnad-ingest-platform | 0 committed skills, 0 committed hooks (dispatcher-style) | **OK** (no skill duplication; verify settings.json registers parent hooks) |

**Drift filed:** the flat-`.md` org-skill duplicates across isnad-graph / deploy / landing-page / data-acquisition are a cleanup sweep — file/track as a `tech-debt` follow-up (remove the shadowing flat files; children invoke org skills from the parent-rooted session). This is intentionally NOT bundled into this doc PR (unrelated-cleanup discipline, `hooks.md § Anti-pattern: copy-resident hooks` precedent).

**Tracked as:** `noorinalabs-main#560` (filed from this audit; P3W15). Each of the 4 child repos carries the SAME 10 flat-`.md` files — `close-stale-issues.md`, `plan-phase.md`, `retro.md`, `review-pr.md`, `team-reset.md`, `wave-audit.md`, `wave-end.md`, `wave-kickoff.md`, `wave-retro.md`, `wave-start.md`. Re-verified at each child's `main` HEAD via `gh api .../git/trees/main?recursive=1` (2026-06-01). Every flat file's frontmatter `name:` matches an org-canonical skill (9 map directly to a `<name>/SKILL.md`; `wave-end.md` is the deprecated-name predecessor of org `wave-wrapup`, and `retro.md` is mislabelled — its body is a wave-retrospective, i.e. a shadow of org `wave-retro`, not org `retro`). The flat bodies have drifted from the org dir-form canonical (the org versions evolved across waves; the frozen flat copies did not), which is exactly the no-sync-check drift collision rules 1 + 4 prohibit — confirming these are stale shadows, NOT repo-specific workflows. Deletions execute in the child repos under #560 (child-roster authors per the child-repo implementer rule); this audit row flips to **OK** once all 4 child PRs merge.

## Create-time ownership gate

New artifacts must land in the repo this doc assigns them to. The gate is, in escalation order:

1. **Doc-convention (this section, in force now).** Any PR that adds a `.claude/hooks/*.py`, `.claude/skills/<name>/`, or charter doc is reviewed against the matrix above: a shared hook or org skill or org-wide charter rule landing in a *child* repo is a wrong-owner placement and is a **Changes-Requested** verdict. Reviewers cite this section.
2. **Hook (follow-up, deferred).** A `PreToolUse`/CI gate that blocks an Edit/Write creating a parent-canonical artifact-class file under a child repo's tree (or a child-shadowing org-skill name) would make the convention machine-enforced. Per `feedback_enforcement_hierarchy` (hook > skill > charter) this is the durable form; it is scoped as a follow-up rather than in this doc-deliverable PR so the doc + audit land first. Tracked under #328's family.

Until the hook exists, the doc-convention + reviewer enforcement is the gate — same posture the Hook Sync section used before its own enforcement matured.

## Relationship to sibling end-state criteria

- **#326 (all committed artifacts pass CI)** depends on this doc to define WHICH artifact classes each repo owns, so CI path-coverage rules can be written per class.
- **#327 (pre-commit + pre-push hooks every repo)** depends on this doc to define what each repo owns and must therefore lint locally.

This is why #328 sequences first.

## Provenance

Phase-3 end-state criterion #7 (`noorinalabs-main#328`), pulled into W13 by owner decision 2026-05-31. Consolidates `hooks.md § Hook Sync Across Child Repos`, `CLAUDE.md § Session team architecture`, `skills.md`, and the `Hook Audit Protocol` into the single canonical ownership doc the criterion required. Audit performed at `main` HEAD 2026-05-31.
