# Team Governance Layer — Genericisation Classification

Bucket: `.claude/team/charter/*.md` (13 files) + `.claude/team/` top-level (`charter.md`, `lifecycle.md`, `roster.json`, `roster/*.md`, `trust_matrix.md`, `feedback_log.md`).
Target: lift the GENERIC governance machinery into `2real-team-framework`; leave behind noorinalabs domain/persona/repo specifics.

## Summary (counts per verdict)

| Verdict | Count | Files |
|---------|-------|-------|
| GENERIC-READY | 6 | lifecycle.md, commits.md, branching.md, communication.md, emergency-mode.md, state-claims.md |
| NEEDS-GENERICISATION | 13 | charter.md, agents.md, issues.md, pull-requests.md, hooks.md, skills.md, tech-decisions.md, artifact-ownership.md, roster.json, roster/*.md (cards), trust_matrix.md, feedback_log.md |
| PROJECT-SPECIFIC | 1 | brand.md |

> "GENERIC-READY" here = the file is a reusable template whose only project coupling is in *examples* (repo names, persona names, issue numbers) that a consumer can ignore or swap; the *policy* is clean. "NEEDS-GENERICISATION" = real org/repo/persona/stack constants are baked into the normative text and must be parameterised. Persona *cards* and *roster.json* are a GENERIC SCHEMA populated with illustrative data — schema is reusable, the rows are examples.

---

## Per-file rows

### charter.md (root team charter)
- **verdict:** NEEDS-GENERICISATION
- **pillar:** GOVERNANCE
- **what's reusable:** The whole governance skeleton — execution model (agents = personas, worktree-required, ontology-consult-before-code), org chart with PD/TPM/Release/Standards roles, feedback system (upward/downward, 3 severity levels, fire-and-replace = archive card + fresh hire), trust-identity-matrix concept, steady-state goal, session-start protocol, board-maintenance rules (pre-wave sequencing, kickoff/wrapup gates), sub-document index.
- **what's opinionated:** "Noorina Labs", the 4 named child repos, persona names (Nadia/Wanjiku/Santiago/Aino), `noorinalabs` project URLs, `cross-repo-status.json`, GitHub Project 2.
- **genericisation note:** Keep structure verbatim; template the org name, repo list, persona names, and board URL as `{{placeholders}}`.

### charter/agents.md
- **verdict:** NEEDS-GENERICISATION
- **pillar:** TEAM
- **what's reusable:** Agent-naming-maps-to-roster rule, hub-and-spoke single-leader spawn model (only orchestrator spawns; managers request via SendMessage), governed-headcount budget concept (machine-enforced roster cap), agent lifecycle (shut down on completion, mandatory retro before teardown), per-repo worktree isolation, worktree lock management, orchestrator spawn-discipline (reuse idle, don't clone), reviewer-slate discipline, child-repo-implementer rule, pre-spawn verification checklists.
- **what's opinionated:** Persona names + role→task mapping table, caps (≤9 parent / ≤6 child), `headcount_budget.py`, specific repo names + per-repo implementer pools, Alembic/migration-chain example, hard paths (`/home/parameterization/...`).
- **genericisation note:** Strongest generic orchestration doc in the set; parameterise persona/repo names + cap numbers, drop the Alembic-specific subsection or mark it as an example.

### charter/artifact-ownership.md
- **verdict:** NEEDS-GENERICISATION
- **pillar:** META-CHILD
- **what's reusable:** The meta-vs-child ownership model — two axes (ownership = source-of-truth tree vs execution location), the ownership+execution matrix by artifact class (shared hooks parent-canonical/dispatcher-style, org vs per-repo skills, charter, rosters, ontology, settings.json vs settings.local.json), collision rules (name reservation, copy-resident anti-pattern), create-time placement gate.
- **what's opinionated:** Specific repo enumeration + the 2026-05-31 drift audit table, issue numbers (#328/#560), "22 org skills" count, hard hook filenames.
- **genericisation note:** Keep the matrix + collision/placement rules as the generic meta-child contract; strip the dated audit table and issue refs.

### charter/branching.md
- **verdict:** GENERIC-READY
- **pillar:** SCM
- **what's reusable:** Whole policy — phase/wave deployments-branch model (`deployments/phase-{N}/wave-{M}`), feature branches off the wave branch, pull-before-branch, worktree branch-safety self-check, merge-base-before-PR, `git worktree prune` after wave.
- **what's opinionated:** Nothing hard-coded; the branch grammar is illustrative-but-generic.
- **genericisation note:** Ship as-is; the `{FirstInitial}.{LastName}/{IIII}-{issue}` grammar is a generic convention.

### charter/brand.md
- **verdict:** PROJECT-SPECIFIC
- **pillar:** NONE
- **what's reusable:** Only the *concept* — a brand-name guard (display name vs code identifier; spell-gate enforces the canonical form everywhere except the one doc that documents the wrong form).
- **what's opinionated:** Entirely "Noorina Labs" / `noorinalabs` / `noorinalabs.com` / `@noorinalabs/*`.
- **genericisation note:** Drop the file; carry forward only a one-line "define a brand display-vs-slug guard" pattern in the framework overview.

### charter/commits.md
- **verdict:** GENERIC-READY
- **pillar:** SCM
- **what's reusable:** Per-commit identity via `-c user.name/-c user.email` (never global/repo config), dual `Co-Authored-By` trailers (member + Claude), new-hire identity rule. This is the core commit-attribution policy.
- **what's opinionated:** The 4-row identity table + `parametrization+{First}.{Last}@gmail.com` email scheme.
- **genericisation note:** Keep policy; replace the table with a "generated from roster.json" note and template the email pattern.

### charter/communication.md
- **verdict:** GENERIC-READY
- **pillar:** TEAM
- **what's reusable:** Direct manager-to-manager messaging (vs pure hub-spoke), shared-state file pattern (`cross-repo-status.json`), dependency-contracts file (`provides`/`needs`), topic-channel conventions, event-driven spawn triggers, 6 protocol rules (check-state-first, update-promptly, escalate-to-PD-for-conflicts, contracts-are-binding).
- **what's opinionated:** Named agents (`main-nadia`, `isnad-graph-{manager}`), the repo list, the B2/ingest example trigger.
- **genericisation note:** Policy is generic; swap the agent/repo table for placeholders.

### charter/emergency-mode.md
- **verdict:** GENERIC-READY
- **pillar:** SAFETY
- **what's reusable:** The whole escape-valve model — trigger conditions (prod-down/security-incident/DR), allowed bypasses (single/zero-reviewer, `[EMERGENCY]` prefix, direct-to-main) vs what is NEVER bypassed (identity/secrets/no-verify hooks, root-fix, honest-audit), enter/exit in-band declaration, post-emergency catchup, `[OWNER-ACTION]` manual-action state-delta protocol.
- **what's opinionated:** The P3W2 incident narrative + Hetzner/Cloudflare/B2 examples (illustrative only).
- **genericisation note:** Ship as-is; the incident examples read as case-study color, not coupling.

### charter/hooks.md
- **verdict:** NEEDS-GENERICISATION
- **pillar:** SAFETY
- **what's reusable:** The enforcement-via-hooks catalog model, dispatcher architecture, hook-sync-across-child-repos (absolute-path registration, no copy-resident hooks), hook-authorship requirements (parser-fixture coverage), hook audit protocol via committed-tree inspection. Many individual hooks are generic (commit-identity, no-verify, git-config, PR-review-count, branch-freshness, board-add, CI-status, squash-block).
- **what's opinionated:** Hook count/numbering tied to this repo, `VPS_HOST`/GHCR/VPS hooks (deploy-specific), wave-context + librarian + ontology hooks (tie to this repo's lifecycle/ontology), specific filenames.
- **genericisation note:** Generic frame + ~12 portable hooks; deploy-specific (VPS/GHCR) and ontology/wave hooks are opt-in modules. This doc indexes the hooks bucket already classified separately.

### charter/issues.md
- **verdict:** NEEDS-GENERICISATION
- **pillar:** TICKETING
- **what's reusable:** Delegation flow, issue review pass, work-gate (issues-before-implementation), issue-filing premise-verification-at-origin-HEAD, project-board-is-authoritative wave planning, multi-step meta-issue 48h re-audit, pre-wave checklist, `FIRSTNAME_LASTNAME` assignment-label scheme, `[MANUAL]` issue prefix, issue hygiene, delivered-vs-applied-at-origin close-condition, comment format (Requestor/Requestee/RequestOrReplied), reply-swap protocol.
- **what's opinionated:** The 8-repo loop, project 2, persona names, specific incident issue numbers.
- **genericisation note:** All policy is generic; parameterise the repo loop + board id + persona names. The comment-format trailer schema is a strong reusable primitive.

### charter/pull-requests.md
- **verdict:** NEEDS-GENERICISATION
- **pillar:** CICD
- **what's reusable:** The PR rulebook — comment-based reviews (shared-account → no self-approve, Requestor/Requestee/RequestOrReplied/TechDebt trailer), 2-reviewer rule + count-distinct-Requestor mechanics, all-assigned-reviewers-approve for blast-radius PRs, single-reviewer wave-bootstrap exception, additive-commits-on-ChangesRequested, post-merge integration verification, one-merge-model-per-wave, wave-merge verification, full local⇄CI parity + no-force-merge, branch-protection rollout, CI-green-before-merge, trust-the-artifact-not-the-framing, security-guards-inline, origin>local for file-content claims, retro-PR body-vs-diff discipline, closes-vs-refs disposition.
- **what's opinionated:** Persona names in templates, `noorinalabs/{REPO}`, wave-branch grammar, many incident issue numbers, the 8-repo/Project-2 assumptions.
- **genericisation note:** Largest and richest governance doc; nearly all policy is generic. Parameterise org/repo/persona tokens; the review trailer + 2-reviewer hook contract are core framework primitives.

### charter/skills.md
- **verdict:** NEEDS-GENERICISATION
- **pillar:** LIFECYCLE
- **what's reusable:** Charter rules governing skill invocation — wave-lifecycle open-item audit before "concluded", cross-repo-status upsert-helper mandate, codify-determinism-on-tooling-fragility, enforcement hierarchy (hook>skill>charter>memory), promotion markers/conventions.
- **what's opinionated:** The 8-repo audit loop, `cross-repo-status.json`/`upsert_status_keys.py`, specific skill names + issue numbers.
- **genericisation note:** Policies are generic; the enforcement-hierarchy + open-item-audit rules are framework-grade. Parameterise file/skill names.

### charter/state-claims.md
- **verdict:** GENERIC-READY
- **pillar:** GOVERNANCE
- **what's reusable:** Entire discipline — refresh-state-before-claim (pre-write checklist, manager-class-not-exempt), PR-state field set, empty-statusCheckRollup-is-hard-not-ready, issue-state field set, merge_commit_sha reachability for "fix landed", ledger-vs-artifact reconciliation, refresh-before-acting, canonical-source-via-`git show <sha>:<path>`.
- **what's opinionated:** `gh`/GitHub-specific commands, some `noorinalabs` repo refs in examples, incident IDs.
- **genericisation note:** Policy is provider-agnostic in spirit; the `gh` recipes are the only coupling and are reusable for any GitHub-backed project. Ship as-is.

### charter/tech-decisions.md
- **verdict:** NEEDS-GENERICISATION
- **pillar:** GOVERNANCE
- **what's reusable:** Individual tech-preferences-on-roster-card, debate/consensus, tie-break by Least-Common-Ancestor in org chart (with LCA table). This decision-governance triad is the generic core.
- **what's opinionated:** Base-image digest-pin convention (Docker-specific), per-env OAuth provisioning (deploy-specific), ontology-vs-graphify owner decision (project-specific), persona names in LCA table.
- **genericisation note:** Keep the LCA/debate/preferences machinery; the Docker/OAuth/ontology sections are domain modules to drop or move to a stack-specific appendix.

### lifecycle.md
- **verdict:** GENERIC-READY
- **pillar:** LIFECYCLE
- **what's reusable:** The canonical skill-ordering doc — phase/wave/session lifecycle tables (precondition → side-effects/state-written → next-skill), counter-write-ownership (writer authoritative, verifier loud-fails), mid-wave on-demand skills, the Mermaid flow diagrams, the "SKILL.md is authoritative on disagreement" maintenance rule.
- **what's opinionated:** `cross-repo-status.json` key names, the 8-repo count, specific issue/incident refs, prod app example.
- **genericisation note:** Structure and state-machine are fully generic; the key names map 1:1 onto the framework's status file. Ship as the lifecycle reference.

### roster.json
- **verdict:** NEEDS-GENERICISATION
- **pillar:** TEAM
- **what's reusable:** The SCHEMA — a name→commit-email union manifest used by the commit-identity hook (parent+child merge, history-preservation for retired personas). Generic and load-bearing.
- **what's opinionated:** Every row (~60 persona names + `parametrization+*@gmail.com`).
- **genericisation note:** Ship an empty/2-row template with the email pattern documented; the file is generated/extended as personas are hired.

### roster/*.md (9 persona cards)
- **verdict:** NEEDS-GENERICISATION (schema GENERIC-READY)
- **pillar:** TEAM
- **what's reusable:** The persona-card SCHEMA is fully generic and is the framework's identity primitive: Identity (name/role/level/status/hired), Git Identity, Personality Profile (comms style, background), Tech Preferences table, role-specific checklists, Work Affinity Spectrum, and the Learned Adjustments table (retro-fed, evidence-gated rows — "the only evolving prose on the card", replacing static personality blocks per persona Option B).
- **what's opinionated:** Every card's *content* — specific names, bios, schools, the noorinalabs role set.
- **genericisation note:** Lift the card template (headings + the evidence-gated Learned-Adjustments mechanic); ship 1-2 example cards clearly marked EXAMPLE.

### trust_matrix.md
- **verdict:** NEEDS-GENERICISATION (model GENERIC-READY)
- **pillar:** TEAM
- **what's reusable:** The trust-scoring MODEL — 1-5 directional scale, default 3, increase/decrease rules, mechanical evidence-anchored scoring (`trust_signals.py`: countable per-engineer signals prs_merged/must_fix_caught/received/ci_red_merges/rework/false_positives → clamped [-2,+2] delta), decay-toward-neutral after 3 silent waves, distribution discipline (5 reserved for top performer), forced-negative-signal pass (bare "None" banned), performance-triggered retirement. The N×N directional matrix + change-log format.
- **what's opinionated:** The actual scores, persona names/columns, archived-persona notes, dated change-log rows.
- **genericisation note:** Lift the scale + mechanical scoring contract + matrix/change-log format; empty the data. `trust_signals.py` is the executable model (in the lib bucket).

### feedback_log.md
- **verdict:** NEEDS-GENERICISATION (format GENERIC-READY)
- **pillar:** GOVERNANCE
- **what's reusable:** The retro-record FORMAT — per-wave retrospective entry (Team Performance, wave-shape metrics table, Per-Engineer Assessments, Top-3 going well / pain points, Proposed Process Changes with owner). This is the append-only feedback ledger that feeds trust updates + charter-change promotion.
- **what's opinionated:** 100% of content — every retro is noorinalabs wave history (personas, issue numbers, hadith/isnad domain).
- **genericisation note:** Ship the retro-entry TEMPLATE only; the 375KB of accumulated history is project-specific and dropped.

---

## Generic team-governance model (framework overview synthesis)

A simulated team is a roster of **personas** — each a persona card carrying a persistent identity (name, role, level), a git commit identity, seeded preferences, and an evidence-gated "Learned Adjustments" log — registered in a `roster.json` union manifest that the commit-identity hook reads so every commit is attributable to a real persona. Personas are spawned as agents under a **hub-and-spoke single-leader model** (only the orchestrator spawns; managers request spawns) and do work in **waves** against a ticketing board, with charter-governed PRs (comment-based reviews, a 2-reviewer rule, no force-merging a red gate). Quality and honesty are scored two ways that reinforce each other: a **trust matrix** assigns directional 1-5 scores updated mechanically from countable wave signals (PRs merged, must-fixes caught vs received, CI-red merges, rework) with decay toward neutral and reserved-top scoring, while a **feedback log** records per-wave retros (going-well, pain points, proposed process changes) — together driving fire-and-replace and the promotion of recurring lessons up the **enforcement hierarchy** (memory → charter → skill → hook). The whole thing runs on a **lifecycle** state machine — session/wave/phase brackets with precondition→state-written contracts and counter-write ownership — and the **charter** is the living rulebook (commit identity, branching, issues, PRs, state-claim discipline, emergency escape-valve) that every persona reads and that retros continuously amend. Identity persists, trust evolves from evidence, feedback accumulates and promotes into enforcement, and the lifecycle sequences it all — so the team self-corrects toward a steady state of minimal negative feedback.
