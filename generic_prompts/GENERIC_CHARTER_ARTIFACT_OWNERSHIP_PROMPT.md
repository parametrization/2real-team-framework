# Generic Charter: Artifact Ownership — Parent Repo vs Child Repos

## Purpose

When a multi-repo program runs from a **parent orchestration repo** that
coordinates several **child repos**, every shared `.claude/` (and ontology /
knowledge-base) artifact needs an unambiguous home. This template is the single
source of truth for **which artifact class is owned where, and where each one
executes**, so a change to it lands in exactly one place and no second source of
truth silently drifts.

Keep two axes separate throughout:

- **Ownership** — which repo's tree is the single source of truth for the
  artifact's content (where a change to it must land).
- **Execution location** — where the artifact actually runs / is read at
  invocation time, which may differ from where it is owned (e.g. a parent-owned
  hook that fires inside a child-repo commit).

## Ownership + execution matrix (template)

| Artifact class | Lives at (owner) | Executes / is read at | Parent-vs-child semantics |
|---|---|---|---|
| **Shared hooks** (`*.py` + support libs: dispatcher, log helper, shell-parse, …) | Parent `.claude/hooks/` **ONLY** | Every repo — each child's settings file registers them by **absolute path** into the parent tree | **Parent-canonical.** Children are *dispatcher-style*: no local `.py` copies. |
| **Child-local hooks** (specific to one repo's surface) | `<child>/.claude/hooks/` | That child only | **Child-owned.** Rare. A child-local *doc* under the hooks dir is not hook code and is fine. |
| **Org-level skills** (lifecycle, knowledge-base, board, file-bug, session-start, …) | Parent `.claude/skills/<name>/SKILL.md` (directory form) | Run from the parent session | **Parent-canonical.** |
| **Per-repo skills** (a workflow meaningful only inside one repo) | `<child>/.claude/skills/<name>/SKILL.md` | That child's session | **Child-owned**, only when genuinely repo-specific. NOT a copy of an org skill. |
| **Org-wide charter** (all charter docs + root project-instructions file) | Parent `.claude/team/charter/` + parent root instructions | Read by every agent in every repo | **Parent-canonical.** Child charter sections must not restate org rules; they add only repo-specific build/architecture detail. |
| **Per-repo charter / instructions** | `<child>/` root instructions (+ any repo-specific charter docs) | That child's agents | **Child-owned**, repo-specific scope only. |
| **Rosters** (commit identity, domain ownership, reviewer pairing) | `<repo>/.claude/team/roster/` + roster index (parent AND each child) | The identity hook reads the *working repo's* roster at commit time | **Each repo owns its own roster.** The session team is a logical overlay; the per-repo roster is canonical for identity. |
| **Memory / notes** | Project-memory location per your setup (committed or machine-local) | Recalled into the session that wrote it | Define ownership + whether versioned, once, here. |
| **Knowledge-base — curated layer** | Parent knowledge-base dir | Read by the librarian / rebuild skills; tracker updates checksums on edits | **Parent-canonical, versioned.** Hand-curated. |
| **Knowledge-base — generated layer** | Parent knowledge-base dir | Built by the owned generator; read by the librarian | **Parent-canonical, versioned, GENERATED.** Always-current-by-regeneration — not checksum-tracked; regenerate, never hand-edit. |
| **Settings** (versioned vs machine-local) | `<repo>/.claude/settings.json` (versioned) and `settings.local.json` (machine-local) | The harness, per repo, at session start | **Versioned file is owned per repo** (registers parent hooks for children). **Local file is machine-local**, never committed. |

## Collision rules

1. **Skill name collisions (org vs per-repo).** An org-level skill name is
   **reserved org-wide.** A child MUST NOT ship a same-named skill that merely
   duplicates the org one — that is the skill analogue of the copy-resident hook
   anti-pattern (drift with no sync check). A child may define a skill with a
   **distinct** name for a genuinely repo-specific workflow. To *invoke* an org
   skill, run in the parent-rooted session; do not copy the SKILL.md.
2. **Hook name collisions.** A child-local hook MUST NOT share a name with a
   parent shared hook. Resolution is by absolute path into the parent tree; a
   same-named child copy is the copy-resident anti-pattern.
3. **Charter section collisions.** Org-wide rules live ONLY in the parent
   charter. A child instructions file that restates an org rule creates a second
   source of truth that silently drifts; children reference the parent section.
4. **Format collisions (skills).** The canonical skill format is the **directory
   form** `<name>/SKILL.md`. A legacy flat `<name>.md` form that shadows an org
   skill is drift to be cleaned.

## Audit method

When classifying a repo's artifacts (hook-owning vs dispatcher-style, skill
shadows, etc.), inspect the **committed git tree**, not the working directory:

```
<git-host-api> repos/<owner>/<repo>/git/trees/<head_sha>?recursive=1
```

Filesystem enumeration (`ls`, `find`, SSH) is NOT a valid substitute — it
includes untracked files, worktree artifacts, and ignored content invisible to
git. Any classification claim must cite the tree (or `contents?ref=<sha>`) query
it ran.

## Create-time ownership gate

New artifacts must land in the repo this doc assigns them to. The gate is, in
escalation order:

1. **Doc-convention (in force immediately).** Any PR adding a hook, skill, or
   charter doc is reviewed against the matrix: a shared hook / org skill /
   org-wide charter rule landing in a *child* repo is a wrong-owner placement →
   **Changes Requested.** Reviewers cite this section.
2. **Hook (durable form, deferred).** A PreToolUse / CI gate that blocks an
   Edit/Write creating a parent-canonical artifact-class file under a child
   tree (or a child-shadowing org-skill name) makes the convention
   machine-enforced. Per the enforcement hierarchy (hook > skill > charter) this
   is the durable form; scope it as a follow-up so the doc + audit land first.

Until the hook exists, doc-convention + reviewer enforcement is the gate.

## Adaptation notes

- Replace the artifact-class names and paths with your own layout; keep the two
  axes (ownership vs execution) and the collision + create-time-placement rules.
- The parent/child merge for rosters and the dispatcher-style child pattern are
  what let org-level coordinators operate across child repos without duplicating
  identity or hook code — preserve that if you run a hub-and-spoke team.
- This doc sequences *before* sibling end-state criteria like "all committed
  artifacts pass CI" and "pre-commit hooks in every repo," because those need a
  per-class ownership definition to write path-coverage and lint rules against.
