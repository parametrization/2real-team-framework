# Intake — noorinalabs orchestration scan (2026-06)

This folder is a **staging area** ("intake") holding a body of candidate artifacts lifted
from a live, mature Claude Code orchestration system, captured for genericisation into the
2real-team-framework. It is *raw material pending review* — not promoted, not wired into the
CLI, not yet parameterized. The point is to get a **complete body of candidates + an overview**
on the table so the genericisation work can proceed against real files instead of from memory.

## Provenance

| Field | Value |
|-------|-------|
| Source repo | `noorinalabs-main` (the org meta-repo that gitignores 7 child product repos) |
| Source commit | `f9938092e9594d0c1b2b51a1e2b207f42db3ca37` (`main`) |
| Scan date | 2026-06-27 |
| Method | 5 parallel classification agents (skills / hooks / lib / governance / ontology+docs) + 1 gap-analysis agent over this repo |
| Scope | **Everything**: orchestration core + governance + ontology system + toolchain/architecture docs + scripts + settings |

The source `noorinalabs` system has run an 8-phase, 18+-wave simulated-team program against
GitHub Issues / Projects / Actions across a meta-repo + 7 child repos. The `.claude/` machinery
that drives it (22 skills, 42 hooks, 26 libs, 13 charter files, a 2-layer ontology) is the
crown jewel being extracted here.

## What's in here

| Path | Contents |
|------|----------|
| `OVERVIEW.md` | Executive overview — scan results, the headline finding, the shared-config knob set, how this relates to the existing framework. **Start here.** |
| `ORCHESTRATION.md` | Deep dive on the orchestration crown jewel across 7 pillars (SCM, ticketing, CI/CD, meta+child repos, team/identity, memory/ontology, lifecycle). |
| `CLASSIFICATION.md` | Master index + aggregate verdict counts + the highest-value lift candidates. Links the per-bucket appendices. |
| `GENERICISATION-BACKLOG.md` | The actionable list: project-specific / opinionated scripts & hooks that *could* be genericised, what each hard-codes, and what it would take. Includes the 36 net-new recipe backlog. |
| `classification/` | Verbatim per-bucket classification tables (skills, hooks, lib, governance, ontology-and-docs) — one row per artifact with verdict / pillar / what's-opinionated / genericisation note. |
| `candidates/` | The **actual source files**, copied verbatim, organized by class. 246 files. This is the body of candidates to work from. |

## How this relates to the rest of the framework

The 2real-team-framework already has two layers (see `OVERVIEW.md` § "Existing framework"):

- **Layer A** — the CLI bootstrapper (`templates/*.mustache` + `presets/*.json` + `python/`,`node/`).
- **Layer B** — `generic_prompts/` — 78 hand-written genericisation *recipes* (Purpose / Rule /
  stdlib code-template / adaptation-notes), one per source artifact. **Not** wired into the CLI;
  they are authoring docs.

This intake is upstream of **Layer B**. The recommended promotion path:

```
intake/noorinalabs-2026-06/candidates/<class>/<artifact>     ← raw candidate (here)
        │  review + author recipe
        ▼
generic_prompts/GENERIC_<CLASS>_<NAME>_PROMPT.md             ← promoted recipe (Layer B)
        │  (future, separate effort) decide renderable
        ▼
templates/ + presets/ + CLI artifact-manifest               ← Layer A
```

`GENERICISATION-BACKLOG.md` enumerates the **36 net-new** artifacts that have no Layer-B recipe
yet (20 hooks, 7 charter files, 5 libs, 4 skills) — the highest-leverage authoring queue.

## Status

- [x] Candidate files copied verbatim (provenance above).
- [x] Every artifact classified (`classification/`).
- [x] Overview + orchestration deep-dive + genericisation backlog written.
- [ ] Recipes authored for the 36 net-new artifacts (next).
- [ ] Shared-config schema designed (the single biggest unblock — see `OVERVIEW.md`).
- [ ] Promotion of reviewed recipes into `generic_prompts/` + (later) CLI rendering.

Nothing here is sanitized beyond omitting `settings.local.json` (local permissions). `settings.json`
was scanned for secrets before inclusion (none). Persona names/emails in `team/` are the source
project's illustrative cast — they are examples of a generic schema, not real contributors.
