---
name: promotion-audit
description: Deterministic audit of the memory → charter → skill → hook promotion pipeline. Auto-promotes AUTO-tier artifacts, files DECIDE-tier issues with drafts, writes a per-wave audit log.
args: wave_name (optional — defaults to the current wave from cross-repo-status.json)
---

Run a deterministic audit of the promotion pipeline. Every step below is backed by a pure function in `helpers.py` so the same input produces byte-identical output.

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Wave Lifecycle for the canonical skill order and preconditions.

## Context

The project's enforcement hierarchy is **hook > skill > charter > memory** (see `.claude/team/charter.md` § Enforcement Hierarchy and memory `feedback_enforcement_hierarchy.md`). Rules migrate upward along that path as evidence accumulates.

| From | To | Trigger |
|---|---|---|
| memory | charter | `promotion_target: charter` AND `retro_citations >= threshold` AND `status: active` |
| charter | skill | Section marker `<!-- promotion-target: skill -->` AND skill-invocation signal >= threshold |
| skill | hook | `promotion-target: hook` in skill frontmatter AND invocation signal >= threshold |

Skill-to-hook **ALWAYS** produces a DECIDE-tier draft issue — never auto-applies (D6, hooks are security-sensitive).

**Marker convention:** The audit pipeline recognizes exactly two provenance marker shapes — `<!-- Promoted from memory: <filename> (<context>) -->` (Shape 1, charter-tier; parser regex `_HTML_COMMENT_PROMOTED_RE`) and `**Promotion provenance:** <body>` (Shape 2, hook-tier and multi-source; parser regex `_PROVENANCE_RE`). The authoritative source for the SHAPE selection rule is [`charter/skills.md` § Promotion Pipeline Marker Convention](../../team/charter/skills.md#promotion-pipeline-marker-convention). For per-hook authoring discipline (forward-reference filter, paragraph separation), see [`charter/hooks.md` § 6. Promotion Provenance Phrasing](../../team/charter/hooks.md#6-promotion-provenance-phrasing). Any future change to the recognized shapes MUST update the charter section first, then the parser, then this skill — in that order, in a single PR.

## Instructions

> **Do NOT hand-roll the `classify_*` call sequence.** Run the canonical
> driver (`run.py`) — it wires the helper calls, slug resolution, and
> thresholds in exactly one place. Hand-rolling the sequence inline is what
> produced the P5W4 24-spurious-AUTO mis-fire (main#690): the section→skill
> tier called `count_skill_invocations(section.promoted_to, …)` over an
> empty `promoted_to` slug, and `git log --grep=/` matched ~every commit,
> crossing the threshold for 24 not-yet-promoted sections. The driver
> derives the candidate-skill slug from the heading for not-yet-promoted sections,
> and `helpers.count_skill_invocations` now returns 0 for a blank slug.

### 1. Run the canonical driver

```bash
# Human-readable audit table + summary line:
python3 .claude/skills/promotion-audit/run.py [wave]

# Machine-readable decisions, to drive artifact emission in step 4:
python3 .claude/skills/promotion-audit/run.py [wave] --json
```

- **Wave resolution.** With no `wave` argument the driver reads
  `current_wave` from `cross-repo-status.json` and emits the canonical
  phase-agnostic form `wave-{X}` (e.g. `wave-16`), #810. A bare `{M}` arg or a
  legacy `p{N}-wave-{M}` arg is normalized to `wave-{X}`. Design B (#804) made
  the wave id global/monotonic, so the cross-phase collision #442 guarded
  against no longer exists; #810 retires the bare-form prohibition.
- **Audit date** is pinned to the wave boundary (`wave_{M}_kicked_off_at`,
  else `_started_at`, else `_scope_reconciled_at`) — never `datetime.now()`,
  so re-runs on unchanged state are byte-identical. Override with `--date`.
- The driver performs ONLY the deterministic classification + rendering. It
  makes no `gh` calls and emits no artifacts — that is step 4, which reads
  the driver's `--json` output.

The `--json` payload is `{wave_name, audit_date, threshold, counts,
decisions[]}` where each decision carries `kind, item_id, from_tier,
to_tier, signal, reason, artifact_ref, extra`. Drive step 4 off the
`AUTO` and `DECIDE` decisions in that list.

### 2. How the driver classifies (reference — do not re-implement)

The driver reads inputs via `read_all_memories` / `read_all_charter_sections`
/ `read_all_skills` / `find_already_promoted_in_charter` (the latter
aggregates `Promotion provenance:` blocks AND `<!-- Promoted from memory: X -->`
markers across all charter sub-docs, #283), then routes each candidate to
its tier-specific classifier. There is no single `classify()` entry point —
each transition has a distinct signature because the signal sources differ:

| Function | Signature | `signals` keys consumed |
|---|---|---|
| `classify_memory(memory, signals, already_promoted)` | `(Memory, dict[str,int], set[str]) -> Decision` | `retro_citations` |
| `classify_section(section, signals)` | `(CharterSection, dict[str,int]) -> Decision` | `skill_invocations`, `threshold` |
| `classify_skill(skill, signals, already_promoted)` | `(Skill, dict[str,int], set[str]) -> Decision` | `skill_invocations`, `threshold` |

Signal derivation (wired once in `run.py`): memory→charter uses
`count_retro_citations`; charter→skill counts invocations of the section's
candidate-skill slug (`promoted_to` with the `skills/` prefix stripped if
already promoted, else `_slugify(heading)` — never an empty slug);
skill→hook counts invocations of the skill name (always DECIDE, D6).

> `charter_parent` is the directory CONTAINING `charter/` (e.g.
> `.claude/team`), NOT `charter/` itself — passing `.claude/team/charter`
> raises ValueError (#418). The driver resolves this correctly; this note
> matters only if you call the helpers directly in a one-off.

Each `Decision` has one of these kinds:

- **AUTO** — thresholds met, promotion target is charter or skill, NOT already promoted
- **DECIDE** — thresholds met, target is hook (always DECIDE), OR `requires_decision: true` override, OR signals ambiguous
- **KEPT** — promotion-target is `none`, thresholds not yet met, or status is `active` with no promotion intent
  - **STALE-OPT-OUT (informational sub-class)** — when a memory has `promotion_target: none` AND `retro_citations >= 2 * threshold`, the entry stays KEPT (the opt-out is authoritative) but is rendered in a separate sub-list so operators can spot drift during wave-retro. No auto-action, no issue filed, no override of the opt-out. (#158)
- **SUPERSEDED** — status is `superseded` or `enforced-elsewhere` with an explicit `superseded_by` reference
- **ALREADY-PROMOTED** — name appears in `find_already_promoted_in_charter()` set (recognized via `Promotion provenance:` blocks AND `<!-- Promoted from memory: X -->` HTML-comment markers across all charter sub-docs; #283)

### 4. Produce artifacts

Resolve the **current wave label** once at the top of this step from `cross-repo-status.json` `current_wave` (e.g. `wave-9` → label `wave-9`, #810 phase-agnostic form). Every artifact created below — AUTO PRs AND DECIDE issues — MUST carry this label so the GitHub Project board's Wave-field sync (see `/board-audit`) routes the artifact to the current wave column. Missing this label is the failure mode #401 was filed against — PRs/issues land off-board and off-wave.

#### AUTO artifacts

For each `AUTO` decision in the driver's `--json` output (step 1):
- **memory → charter:** apply `templates/charter-section.md` to the memory, append to the appropriate charter file, mark memory `superseded_by: charter:{file} § {section}`. Stage the diff.
- **charter → skill:** apply `templates/skill-scaffold.md` to the section, write `.claude/skills/{slug}/SKILL.md`, add a back-reference comment `<!-- promoted-to: skills/{slug} -->` after the section's `promotion-target` marker. Stage.

**Commit (Aino identity per `charter/commits.md` § Identity Table):**

```bash
git -c user.name="Aino Virtanen" \
    -c user.email="parametrization+Aino.Virtanen@gmail.com" \
    commit -F .claude/scratch/promotion-audit-{wave}-commit.txt
```

The commit-identity flags are **mandatory** (no shortcut to `git commit -m`) — they're the only way `validate_commit_identity` recognizes Aino as the author. Write the commit message to `.claude/scratch/promotion-audit-{wave}-commit.txt` and pass via `-F`, not heredoc — heredoc inside the parent `-c` line trips the identity-hook parser (memory `feedback_heredoc_in_git_commit.md`). Include two `Co-Authored-By` trailers (Aino + Claude).

**Branch + push:**

```bash
git checkout -b A.Virtanen/promotion-audit-{wave}-{timestamp}
git push -u origin A.Virtanen/promotion-audit-{wave}-{timestamp}
```

**Open the PR** following `charter/pull-requests.md § PR Template` body shape (Summary / Related Issues / Review Checklist + two `Co-Authored-By` trailers). Always include the literal three labels:

```bash
gh pr create \
  --base deployments/phase-{N}/wave-{M} \
  --title "promotion-audit: AUTO promotions for {wave} (closes #N)" \
  --body-file .claude/scratch/promotion-audit-{wave}-pr-body.md \
  --label tech-debt \
  --label enhancement \
  --label {wave-label}
```

The label set is **non-negotiable**: `tech-debt` (this is process/quality work), `enhancement` (functional addition to charter/skills), AND the current wave label `{wave-label}` (the phase-agnostic `wave-{X}` form, #810). Validate the labels actually stuck — `gh pr edit` silently no-ops on bad label names (memory `feedback_gh_pr_edit_silent_noop.md`):

```bash
gh pr view <PR#> --json labels --jq '.labels[].name'
# Expect: enhancement, {wave-label}, tech-debt (any order)
```

If any label is missing, retry with `gh pr edit <PR#> --add-label <name>` and re-verify.

**Add to project board (Project 2):**

```bash
PR_URL=$(gh pr view <PR#> --json url --jq .url)
gh project item-add 2 --owner noorinalabs --url "$PR_URL"
```

`gh project item-add` is in the silent-no-op family (memory `feedback_gh_pr_edit_silent_noop.md`) — its "no output = success" output is misleading when the item-add fails. **Read-back-verify** the add stuck:

```bash
gh project item-list 2 --owner noorinalabs --format json --limit 200 \
  | jq -r '.items[] | select(.content.url == "'"$PR_URL"'") | .id'
```

A non-empty ID confirms the add succeeded. Empty output = the add silently no-op'd — retry once, then escalate to team-lead if still empty.

**Assign two reviewers** per `charter/agents.md` § Orchestrator checklist when spawning a reviewer. Use SendMessage to spawn each reviewer (do NOT use `gh pr review` — `block_gh_pr_review` enforces; memory `feedback_validate_pr_review_approved_not_reply.md`). The reviewer spawn brief MUST embed the verbatim verdict template with the literal `TechDebt: ` line shape (memory `feedback_techdebt_attestation_literal_line.md`) — `## TechDebt` headers are NOT recognized by `validate_pr_review.py`. Reviewer slate per scope:
- memory → charter promotions: Wanjiku (TPM) + Nadia (PD)
- charter → skill promotions: Wanjiku (TPM) + Aino (yourself ineligible — pick Santiago or Nadia)

Q3 decision: auto-promote artifacts land via PR (2-reviewer gate), not direct commit.

#### DECIDE artifacts

For each `DECIDE` decision in the driver's `--json` output (step 1):
- Apply `templates/hook-draft.md` to generate an issue title + body. Write the body to `.claude/scratch/promotion-audit-{wave}-decide-{slug}.md`.
- Create the issue with the **same three-label set** as AUTO PRs (`tech-debt` + `enhancement` + current-wave label) and the same project-board treatment:

```bash
gh issue create \
  --repo noorinalabs/noorinalabs-main \
  --title "<title from template>" \
  --body-file .claude/scratch/promotion-audit-{wave}-decide-{slug}.md \
  --label tech-debt \
  --label enhancement \
  --label {wave-label}
```

Use `--body-file`, NOT `--body` — the `|` hook bug #146 surfaces on long-prose `--body` arguments.

**Add the issue to Project 2** with the same read-back-verify protocol as AUTO PRs:

```bash
ISSUE_URL=$(gh issue view <N> --json url --jq .url)
gh project item-add 2 --owner noorinalabs --url "$ISSUE_URL"
gh project item-list 2 --owner noorinalabs --format json --limit 200 \
  | jq -r '.items[] | select(.content.url == "'"$ISSUE_URL"'") | .id'
```

Empty output = retry; persistent empty after retry = escalate.

#### Determinism note

The `gh` calls in this step (PR/issue creation, project-board adds, label/board verification) are **the only nondeterministic external calls the skill makes** — they're isolated to artifact-emission, not to the classification logic (helpers.py). Re-running the audit on unchanged repo state still produces byte-identical classification output; the artifacts themselves carry timestamps in their branch names and bodies and are not expected to be byte-identical across runs.

### 5. Render the audit table

The driver already renders this table — its default (non-`--json`) stdout
**is** the audit table followed by the summary line. Capture that stdout
for steps 6–7 rather than calling `render_audit_table` by hand. The table
has four subsections:

```
## Promotion Audit — {wave_name}

### AUTO-PROMOTED (artifacts generated this run)
| Item | From → To | Signal | Artifact |
|---|---|---|---|
...

### REQUIRES DECISION (issues filed)
| Item | Candidate target | Signal | Issue |
|---|---|---|---|
...

### KEPT (no action — informational)
- {item}: {reason}

**STALE-OPT-OUT (review the opt-out — informational only):**
- {item}: {reason}    ← only rendered when at least one entry crosses 2× threshold

### SUPERSEDED / ALREADY-PROMOTED (no action — informational)
- {item}: {pointer}
```

### 6. Write outputs (Q4 — BOTH)

1. **Append to feedback_log.md** — if the audit runs inside a retro (detect by checking if the most recent `## Retrospective:` entry is on today's date), append under the current retro. Otherwise prepend a fresh `## Promotion Audit — {wave_name} ({DATE})` entry at the top of the log. `{wave_name}` is the phase-agnostic form `wave-{X}` (e.g., `wave-16`), #810. The bare form is now SAFE: Design B (#804) made the wave id global/monotonic, so the cross-phase collision #442 guarded against (P2W10 vs P3W10) can no longer occur — `wave-{X}` is unique across all phases.
2. **Standalone log** — always write to `.claude/team/promotion_audit_log/{wave_name}.md` where `{wave_name}` is the phase-agnostic form `wave-{X}` (e.g., `.claude/team/promotion_audit_log/wave-16.md`). Create the directory if it doesn't exist. Overwrite if re-run. (Pre-#810 logs named `p{N}-wave-{M}.md` remain valid on disk; new runs use `wave-{X}.md`.)

### 7. Report

Print a two-line summary to stdout: counts per decision category and a link to the standalone log:

```
Promotion audit wave-{X} complete: 0 AUTO · 0 DECIDE · 13 KEPT · 1 SUPERSEDED
Log: .claude/team/promotion_audit_log/wave-{X}.md
```

## Determinism

The audit MUST produce byte-identical output when re-run on unchanged repo state. The canonical driver (`run.py`) is what guarantees this — it wires the helpers exactly once so the classification logic cannot drift between runs or operators:
- Sort every list by a stable key before iteration (memory name, charter path+heading, skill name) — done inside the helpers the driver calls.
- Use UTC dates pinned to the wave boundary (`run.py` reads `wave_{M}_kicked_off_at`/`_started_at`/`_scope_reconciled_at` from `cross-repo-status.json`), never `datetime.now()`.
- Never count invocations for an empty/blank slug (`count_skill_invocations` guards this; `--grep=/` would otherwise match ~every commit — the main#690 mis-fire).
- Never read transcript files (per D4(i)).
- Never invoke external tools with nondeterministic output (no `gh api` except for issue creation at the end).

Tests in `.claude/skills/promotion-audit/tests/` cover each helper (`test_helpers.py`), a smoke test verifying the first-run expected outcome (zero AUTO, zero DECIDE on current repo state — `test_smoke.py`), and the driver itself including the empty-slug regression and steady-state-through-the-driver (`test_run.py`).

## Integration

- `wave-retro` (see `.claude/skills/wave-retro/SKILL.md`) invokes this skill right after step 7 "Charter change proposals".
- Standalone invocation is supported — operators can run `/promotion-audit` between retros if drift is suspected.
- The output log is greppable: `git log --follow .claude/team/promotion_audit_log/` gives the full promotion history.

## What this skill does NOT do

- It does not promote skill → hook automatically (Q6 locked: hooks are security-sensitive; always DECIDE).
- It does not mutate any memory file in user-level `~/.claude/projects/` — it only reads. If a memory is auto-promoted, the memory's `superseded_by` is updated by the skill (writing to the user-level memory file is allowed per feedback-settings-permission memory).
- It does not scan conversation transcripts — signal sources are charter files, feedback_log.md, and git history only (D4 lightweight).
