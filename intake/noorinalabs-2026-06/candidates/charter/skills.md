# Skills

This file defines the charter rules that govern skill invocation, composition, and wave-lifecycle discipline. For skill authorship itself, see individual skill directories under `.claude/skills/`.

<!-- Promoted from memory: feedback_honest_audit_over_conclusion_claim.md (P3W5 retro 2026-05-06). Already enforced via Hook 17 (validate_wave_audit) per hooks.md L169 — the dedicated provenance entry there is now mirrored to the source memory's superseded_by. -->

## Wave Lifecycle — Open-Item Audit <!-- promotion-target: hook -->

Before any skill or agent claims a wave, workstream, or milestone is **"concluded"**, **"complete"**, or **"done"**, it MUST run a cross-repo open-item count for the active wave scope. The claim is only permitted if one of two conditions holds:

1. **Zero open items** for the wave label across every relevant repo, OR
2. An **explicit carry-forward list** naming every non-closed item with destination (next wave, backlog, deferred indefinitely).

### When this applies

- `/wave-wrapup` before emitting its summary.
- `/handoff` before any "concluded" narrative in the handoff body.
- `/wave-retro` before the "Wave Theme — complete" statement.
- Any skill that reports wave status.
- Manually-authored retros and wave summaries in feedback_log.md.

### Audit command

The canonical audit is:

```bash
for repo in noorinalabs-main noorinalabs-isnad-graph noorinalabs-user-service noorinalabs-deploy noorinalabs-design-system noorinalabs-landing-page noorinalabs-data-acquisition noorinalabs-isnad-ingest-platform; do
  COUNT=$(gh issue list --repo "noorinalabs/$repo" --state open --label "p2-wave-${N}" --json number --jq 'length' 2>/dev/null)
  [ -n "$COUNT" ] && [ "$COUNT" != "0" ] && echo "$repo: $COUNT open"
done
```

If any repo returns non-zero, either address those items before closing the wave or list them explicitly as carry-forward with destination.

### Rationale

During P2W9 wrapup, the orchestrator claimed "wave-9 parent-repo workstream concluded" in a handoff when ~22 items remained open across child repos (8 in deploy, 5 in isnad-graph, 3 in ingest-platform, plus others). The owner had to prompt "have we completed all PRs and open issues for wave 9?" to surface the truth. A narrative "concluded" claim carries forward as next-session assumption — the next orchestrator reads the handoff and assumes work is done that isn't.

Derived from Phase 2 Wave 9 retrospective, 2026-04-22.

## Promotion-target: hook

This rule is proposed for promotion to a hook-enforced check (hook > skill > charter per the enforcement-hierarchy principle). A wave-audit hook would scan handoff/retro/wrapup skill outputs for "concluded"/"done"/"complete" phrasing and block the skill's completion unless the open-item count is zero or an explicit carry-forward list is present. Tracked as a followup issue.

## Cross-repo-status.json upsert pattern <!-- promotion-target: hook -->

Any skill that writes top-level `wave_{N}_*` keys to `cross-repo-status.json` MUST use the shared upsert helper at `.claude/lib/upsert_status_keys.py`. Raw `jq ... > tmp && mv` (and equivalent full-file rewrites — `jq | sponge`, `python -c 'json.dump(...)'` round-trips, etc.) are **banned** for top-level `wave_{N}_*` key writes.

### Why

The file mixes shapes deliberately: top-level `wave_{N}_*` bookkeeping keys are compact single-liners (zero-churn diffs), while older `wave_{N}_scope` blocks are pretty-indented (human-readable). A naive jq round-trip reformats every compact line to jq's default pretty form, doubling file length and producing a 500+ line cosmetic diff per wave. PR #270 (W4 retro) and PR #276 (W5) both flagged this, and #278 closed the acute symptom by writing the helper. #332 closed a follow-up bug where the helper inserted new keys inside multi-line array values; the post-fix helper is multi-line-aware.

### Contract

`upsert_top_level_key(text, key, value)`:
- **Replace-in-place** when `key` exists at top level → zero churn (identical input produces identical output).
- **Insert-near-sibling** when `key` does not exist → +1 line per new key, placed after the most-recent `wave_{N}_*` sibling (or before the closing `}`).
- **JSON-validates** the input before the rewrite AND the output after the rewrite. Malformed input or output raises rather than silently writing corrupted state.
- **Multi-line-aware** (post-#332): skips past multi-line array / object sibling values, never inserts inside them.

### Canonical invocation

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
python3 "$REPO_ROOT/.claude/lib/upsert_status_keys.py" \
  "$REPO_ROOT/cross-repo-status.json" \
  "wave_{N}_scope_reconciled_at=\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"" \
  "wave_{N}_active=true"
```

Each `key=value` argument's VALUE must be a self-contained JSON literal (string with quotes / number / bool / array / object). The helper's own docstring documents the full invocation surface.

### Current consumers

- `/wave-scope` Step 13 — writes `wave_{M}_scope_reconciled_at`, `wave_{M}_repos_in_scope`, `wave_{M}_meta_issue`, `wave_{M}_scope`, optional `wave_{M}_scope_reconciliation_note`.
- `/wave-wrapup` Step 10.5 — writes `wave_{M}_final_pr_count`, `wave_{M}_changes_requested_cycles`, `wave_{M}_top_concentration_pct` via `.claude/lib/wave_status.py counters … --write`, which delegates to this helper (main#688).
- Future skills writing top-level `wave_{N}_*` keys → MUST use the helper; do NOT reinvent.

### Promotion provenance

Memory `feedback_enforcement_hierarchy.md` (hook > skill > charter). Acute fix landed in PR #288 closing #278; broader codification carried forward as #292 → this charter section + the helper promotion from `.claude/skills/wave-scope/` to `.claude/lib/` (multi-consumer triggered the shared-lib promotion per the issue body's item 3 decision rule).

### Hook-class enforcement decision

Per #292 item 4 — should a `validate_cross_repo_status_format` PostToolUse hook fire on Edit/Write of `cross-repo-status.json` and block writes that expand line count >N% relative to additions OR reformat compact-inline to pretty? **Decision: DEFER.** Rationale: zero charter-rule violations observed across W6–W9 since the helper landed. The two current consumers (`/wave-scope`, `/wave-wrapup`) both invoke the helper correctly. Per `feedback_enforcement_hierarchy.md`, charter-only-without-violations does NOT require hook promotion; promote-on-first-violation is the established trigger. Re-evaluate if any future skill OR manual edit produces a non-helper-mediated write that expands the file >2x its prior line count.

## Codify Determinism on Tooling Fragility <!-- promotion-target: none -->

This is the **when-to-promote-to-code companion** to the enforcement hierarchy (hook > skill > charter > memory; memory `feedback_enforcement_hierarchy`). The hierarchy says a load-bearing *rule* that decays should climb toward a hook. This principle says the same about fragile *mechanics*: the first time a shell or `gh` syntax fragility bites a load-bearing path, the response is deterministic code — **not** a one-off patch and **not** a soft memory.

### The rule

The first time a shell or `gh` syntax fragility breaks a **load-bearing** automation path — a skill step, a counter/metric computation, or a merge/ceremony gate — do **not** just fix the one command and move on, and do **not** rely on a memory to prevent recurrence. Write a deterministic `.claude/lib/` helper (stdlib + `subprocess.run([...])` with explicit arg lists — no `shell=True`, no word-splitting, no string-interpolated command lines), give it tests under `.claude/lib/tests/`, and rewire the skill step to call it in place of the fragile bash. File a `tech-debt(process)` issue and route it through the normal pipeline. The conversion owner is the Standards & Quality Lead; this is the same memory→automation move `/wave-retro` Step 7.7 performs — done the moment the fragility bites, not deferred to the retro.

### Trigger family (codify, don't work around)

- **zsh no-word-split on a parameter expansion** — zsh does NOT split an unquoted `$VAR`, so `for X in $VAR` collapses an entire list into ONE iteration. Use `while IFS= read -r X` (here-string or process-substitution form) or a Python emitter. Worked instance: § Zsh-safe repo iteration in wave skills, immediately below.
- **`gh api -f body=@file`** posts the literal `@path` string, not the file contents — use `-F`/`--field` (memory `feedback_gh_pr_edit_silent_noop`).
- **`gh pr merge` in a loop** can fail-open the 2-reviewer gate when the loop variable word-splits or empties — drive merges from explicit, read-back-verified PR numbers, never an unquoted loop variable.
- **`gh project item-add` / `gh pr edit` silent no-ops** — read back and verify the mutation landed, or route it through a deterministic helper.

### Why a memory is not enough

`feedback_zsh_shell_environment` already existed when zsh `for X in $VAR` word-splitting silently broke `/wave-wrapup` repo-iteration **three times in one wave** (merge loop + counter loop ×2) → `gh` "could not resolve repository" → zero/garbage counters and division-by-zero. The memory did not stop recurrence; the deterministic helper removes the failure mode entirely. Each concrete trigger above is itself promotable to a lint-style gate on **first recurrence** (per the promote-on-first-violation trigger) — e.g. the deferred `validate_skill_bash_no_param_for_loop`.

**Promotion provenance:** Owner-approved 2026-06-16 as a general charter principle, promoting memory `feedback_codify_determinism_on_shell_fragility` (owner directive 2026-06-15) from memory to charter and generalizing the narrow worked instance § Zsh-safe repo iteration in wave skills (main#689). Companion to memory `feedback_enforcement_hierarchy` (hook > skill > charter > memory). Evidence — the pattern bit 3× in P5W4: main#688 (`.claude/lib/wave_status.py`, shipped — deterministic repo/counter helper) and main#690 (`/promotion-audit` hand-rolled CLI driver mis-fired section/skill tiers — same pattern, second instance in one wave). Related memories: `feedback_gh_pr_edit_silent_noop`, `feedback_heredoc_in_git_commit`, `feedback_zsh_shell_environment`.

## Zsh-safe repo iteration in wave skills <!-- promotion-target: hook -->

This section is the specific **worked instance** of § Codify Determinism on Tooling Fragility above — the zsh-parameter-expansion trigger, codified into `.claude/lib/wave_status.py`.

Skill bash blocks run under **zsh** (this org's shell — memory `feedback_zsh_shell_environment`). Unlike bash/sh, zsh does **NOT** word-split an unquoted **parameter** expansion: `for R in $WAVE_REPOS_IN_SCOPE` (where the variable holds a newline- or space-joined list) collapses the **entire list into ONE iteration**. The collapsed blob is then passed to `gh --repo`, which 404s ("Could not resolve repository") → merged-PR count 0 → division-by-zero in the counter math. This bit a single P5W4 `/wave-wrapup` three times (main#688).

### The rule

To iterate a repo list (or any multi-item parameter) in a skill bash block, use **one** of these — never `for X in $VAR`:

```bash
# (a) here-string into `while read` — keeps the loop in the CURRENT shell, so
#     arrays/assoc-arrays mutated inside the loop survive past `done`.
while IFS= read -r R; do …; done <<< "$WAVE_REPOS_IN_SCOPE"

# (b) process substitution from the deterministic helper — same current-shell
#     property; preferred when the source is the repos-in-scope list.
while IFS= read -r R; do …; done < <(python3 "$REPO_ROOT/.claude/lib/wave_status.py" repos {P} {M})

# (c) a quoted array expansion when the list is already a bash/zsh array.
for repo in "${REPOS[@]}"; do …; done
```

**Do NOT use `… | while IFS= read -r R` (a pipe) when the loop body mutates a variable used after the loop** — a piped `while` runs in a subshell and the mutation is lost. Use the here-string (a) or process-substitution (b) form, both of which keep the loop in the current shell.

`$(…)` command substitution (`for R in $(jq …)`) *does* split under zsh, so it is not broken — but standardize on `while read` anyway so the form operators copy is the one that is also parameter-safe.

### Deterministic counter helper

`/wave-wrapup` Step 10.5 counter math (final-PR-count / changes-requested-cycles / top-concentration) is computed by `.claude/lib/wave_status.py`, which issues every `gh` call as `subprocess.run([...])` with an explicit arg list (no shell → no word-split anywhere) and reproduces the canonical P5W4 actuals 19 / 4 / 16. New skills computing wave counters MUST use this helper rather than re-rolling bash.

### Promotion provenance

main#688; memory `feedback_zsh_shell_environment` (codified here) and `feedback_enforcement_hierarchy.md` (hook > skill > charter). **Hook-class decision: DEFER** — the three wave skills are swept clean and the counter math is now code, so there are zero current violations; promote a `validate_skill_bash_no_param_for_loop` lint-style gate (grep skill `*.md` bash fences for `for \w+ in \$[A-Z_]`) on first recurrence, per the promote-on-first-violation trigger.

## Promotion Pipeline Marker Convention <!-- promotion-target: none -->

The charter records its own evolution via TWO markers, each with a distinct authoring role. New charter content MUST pick one of these two shapes — inventing a third (italic prose, blockquote, plain "from memory X") defeats the `/promotion-audit` pipeline because the parser only recognizes the two below.

### Shape 1 — HTML-comment marker (charter-tier provenance)

```markdown
<!-- Promoted from memory: <memory_filename> (<context>) -->

## <Section Heading> <!-- promotion-target: ... -->
```

**Use for:** A charter section that codifies a single memory's rule with no hook-tier promotion or multi-source narrative. The marker lives immediately adjacent to the section header. The `(<context>)` parenthetical typically cites the retro date or PR that ratified the promotion — e.g. `(P3W5 retro 2026-05-06)` or `(PR #392)`.

**Parser-recognized via:** `_HTML_COMMENT_PROMOTED_RE` in `.claude/skills/promotion-audit/helpers.py` (DOTALL match; captures the body up to `-->`, so trailing context is part of the regex sweep).

**Where used at HEAD:** 10 actual usage sites across 5 charter sub-docs — `pull-requests.md` (5), `state-claims.md` (3), `agents.md` (1), `skills.md` (1, the line-5 marker for this file). `hooks.md` mentions the shape once in § Hook Provenance Block Format as a cataloging reference, not as a usage.

### Shape 2 — Bold-block narrative (hook-tier and multi-source provenance)

```markdown
**Promotion provenance:** <narrative citing memory filenames, PR numbers, dates, prior charter sections, augments/supersedes relationships>
```

The block lives at the END of the section it describes (or as a bullet under a hook entry in `hooks.md`).

**Use for:**
- A hook charter entry — cite hook number + PR + worked-example pointer.
- Any charter section whose provenance crosses multiple waves, memories, or prior charter sections.
- A section that declares an `Augments:` relationship with an existing rule.
- Multi-step memory → charter → hook narratives.

**Parser-recognized via:** `_PROVENANCE_RE` in `.claude/skills/promotion-audit/helpers.py` (matches `**Promotion provenance:**` literally; body extracted greedily until next blank line or document end).

**Where used at HEAD:** 6 actual usage sites across 2 charter sub-docs — `hooks.md` (5, on Hooks 14/15/17/etc.), `tech-decisions.md` (1, § Per-Env OAuth Provisioning). `hooks.md` § 6. Promotion Provenance Phrasing also mentions the shape literal once as a cataloguing reference, not a usage. Counts treat catalogue mentions consistently — see Shape 1 above, same exclusion rule.

### Choice rule

1. **Default to Shape 1** for memory → charter promotions ratified at a single retro with no hook follow-up planned.
2. **Use Shape 2** when one or more of:
   - The promotion lands a HOOK (cite hook number + PR).
   - The provenance crosses multiple waves, memories, or prior charter sections.
   - The section declares an `Augments:` relationship with an existing rule.
   - Multiple worked examples need to be cited in-line.

### Forbidden shapes

Reviewers reject charter PRs that introduce any of the following — correct to one of the two canonical shapes during review:

- `_Promoted from memory X_` (italic prose) — NOT parser-recognized.
- `> Promoted from memory X` (blockquote) — NOT parser-recognized.
- Plain "Promotion provenance:" (un-bolded) — NOT parser-recognized; the regex requires `**` markdown bold delimiters.
- Plain-text "from memory X" prose without either marker — NOT parser-recognized.
- `### Promotion provenance` heading-form WITHOUT a `**Promotion provenance:**` line in its body — NOT parser-recognized. Two pre-existing heading-form instances (`hooks.md` § Hook-Tree Layout, `skills.md` § Cross-repo-status upsert pattern just above this section) predate this convention; they remain valid because the source artifacts have `superseded_by` set in memory. New authoring should use Shape 2's bold-prose form, OR include a bold-prose line inside the heading-form body.

### Auto-template alignment

The `/promotion-audit` skill's `templates/charter-section.md` emits Shape 1 (HTML-comment marker). It MUST NOT emit italic-prose or blockquote forms — those are not recognized by either parser regex AND must not be hand-authored either. If the AUTO-template ever needs richer provenance than a single line, escalate to Shape 2 manually rather than inventing a third form.

### Cross-references

- `/promotion-audit` SKILL.md § Context cites this convention as the authoritative source for marker shape selection.
- `charter/hooks.md` § 6. Promotion Provenance Phrasing catalogues the parse keys and the per-hook forward-reference-filter discipline. That section documents the parser KEYS; this section codifies the authoring CHOICE between them.

### Provenance

<!-- Promoted from memory: (none — this section codifies the marker convention itself, not a memory-to-charter promotion) -->

Filed as [#393](https://github.com/noorinalabs/noorinalabs-main/issues/393) (P3W9) — sibling of [#283](https://github.com/noorinalabs/noorinalabs-main/issues/283) (PR #392) which extended `find_already_promoted()` to recognize the HTML-comment shape via `_HTML_COMMENT_PROMOTED_RE`. PR #392 enabled the parser; this section codifies the authoring discipline that the parser support requires. Replaces the pre-#393 implicit convention (manual authors had already converged on the two shapes documented here across ~17 charter promotions) with an authoritative source.

<!-- Promoted from memory: (none — this section codifies retro proposal #1, ratified at P3W10 retro via PR #441 owner-decided 2026-05-16) -->

## Process-Doc Authorship: Derived-From-SKILL.md-At-HEAD <!-- promotion-target: none -->

When AUTHORING a process doc — a skill's `SKILL.md`, a charter section, a `lifecycle.md`, any reference doc that other agents will rely on — the source of truth is the **artifact at HEAD**: the actual SKILL.md content, the actual charter section content, the actual lifecycle steps as they exist on disk. NOT the framing in the spawn brief, NOT the commit-message rationale, NOT the surrounding PR body, NOT the issue body that asked for the change.

### Why

A 3-catch convergent class across PRs #438, #439, #440 in P3W10 traced back to authors writing FROM framing instead of FROM grep-able artifact state. The framing was directionally correct but lost fidelity at the detail level — counts, exact section names, behavior under edge cases — and the resulting process doc cited behavior that didn't match what the skill/charter actually did at HEAD.

This Augments the existing reviewer-class discipline `feedback_review_against_artifact_not_framing.md` (and its charter form `pull-requests.md § Trust the Artifact, Not the Framing`) by lifting the same primitive to the AUTHOR layer: authors of process docs must derive content from the artifact, not from the framing handed to them.

### How to apply

1. **Before writing**: open the SKILL.md / charter section / lifecycle.md being documented and read it at the working commit (`git show HEAD:<path>` if uncertain about working-tree drift).
2. **While writing**: every cited behavior — every "the skill does X", every "the hook fires on Y", every counter / threshold / step number — must be grep-able at HEAD.
3. **PR review**: every process-doc PR review verifies cited skill/charter/lifecycle behavior is grep-able at HEAD of the PR. Reviewers MUST read the source artifact at HEAD, not trust the PR body's framing.

### Severity if violated

- **Minor** first occurrence — Changes-Requested with a `gh api repos/.../contents/<path>?ref=<head_sha>` link to the source artifact and the divergent line.
- **Moderate** for a pattern (same author or same skill, 2+ occurrences within a wave).

### Provenance

P3W10 retro PR #441 § Proposed Process Changes #1. Wanjiku-framed at PR #440 review. 3-catch convergent class across #438/#439/#440. Owner-adopted 2026-05-16 (PR #444). Augments `pull-requests.md § Trust the Artifact, Not the Framing` (reviewer layer) and `feedback_review_against_artifact_not_framing.md` (reviewer-class memory).

<!-- Promoted from memory: (none — this section codifies retro proposal #2, ratified at P3W10 retro via PR #441 owner-decided 2026-05-16) -->

## Acceptance-Criteria-Bucketing-In-Reports <!-- promotion-target: none -->

Any skill or hook that emits a count-based summary block MUST distinguish at least two semantic buckets — typically **actionable vs informational** — so readers can tell whether the count indicates a problem requiring action or ambient state to acknowledge and move on.

### Why

A single "N items" number is ambiguous: the reader cannot tell whether N=166 is a backlog crisis or a healthy steady-state. The W10 `/board-audit` DRIFT-vs-NOOP split (landed in #439) demonstrated that adding bucketing made the same underlying data immediately actionable — the same audit run that previously read as "166 items processed" became "0 DRIFT / 166 NOOP," which the reader can act on (or not) in one glance.

### How to apply

Every count-emitting summary block has **at least 2 buckets with semantic labels**. Examples of well-bucketed outputs:

- `/promotion-audit`: `0 AUTO · 0 DECIDE · 146 KEPT · 5 SUPERSEDED · 15 ALREADY-PROMOTED` (actionable buckets first: AUTO/DECIDE; informational buckets last: KEPT/SUPERSEDED/ALREADY-PROMOTED).
- `/board-audit`: `0 DRIFT · 166 NOOP` (DRIFT requires action; NOOP is ambient).
- `/wave-retro`: Top 3 Going Well vs Top 3 Pain Points (positive vs negative semantic split).

A **single undifferentiated number** ("166 items processed", "N events captured", "M files scanned") is **forbidden** in summary blocks emitted by skills or hooks.

### Sibling / retrofit list (skills/hooks that should adopt this convention as they next change)

- `/promotion-audit` — already bucketed (AUTO/DECIDE/KEPT/SUPERSEDED/ALREADY-PROMOTED); cited as a positive example here. The combined SUPERSEDED + ALREADY-PROMOTED 20-line summary is the natural application of this rule.
- `/wave-retro` — Top 3 Going Well vs Top 3 Pain Points; further bucketing of the Memory-to-Automation Audit (Keep vs Charter-candidate vs Hook-candidate) recommended.
- `/board-audit` — DRIFT vs NOOP already landed in #439.
- `/session-start` — errors-needing-action vs ambient-state buckets in the startup status table.
- `/wave-wrapup` — open-items-this-wave vs carry-forward vs merged-this-wave buckets.
- `/wave-scope` — declared-in-retro vs labeled-only vs both vs explicit-out-of-scope buckets.

The retrofit list is non-binding: existing skills retrofit at their next material change, not in a mass sweep.

### Severity if violated

**Minor** — reviewers should ask for bucketing in PR review of any new or materially-changed skill/hook that emits a summary block. Existing un-bucketed summaries are not retroactively in violation; they retrofit at next change.

### Provenance

P3W10 retro PR #441 § Proposed Process Changes #2. Wanjiku + Santiago independently named the pattern on PR #439 review. Sibling generalization of the `/board-audit` DRIFT-vs-NOOP split that landed in #439. Owner-adopted 2026-05-16 (PR #444).
