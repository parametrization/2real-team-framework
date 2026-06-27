---
name: wave-retro
description: Automated wave retrospective — PR analysis, assessments, trust matrix updates, feedback log, charter change proposals
args: team_name, Phase number, Wave number
---

Run a retrospective for a completed wave of the `{team_name}` team.

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Wave Lifecycle for the canonical skill order and preconditions.

## Instructions

### 1. Ontology check

Run `/ontology-librarian` to check ontology staleness before the retro. If the ontology is significantly behind, note it in the retro findings — the wrapup should have run `/ontology-rebuild`, so staleness here indicates a process gap.

### 1.5. Board freshness check (added per main#199)

Run `/board-audit` to ensure project 2's view of the wave matches actual issue state. Stale board state can mis-frame retro findings (e.g., issues that closed during the wave but never came off the active column would appear unresolved). The skill detects orphans + Wave-field drift and reports both before any retro analysis runs. Labels are canonical (charter `issues.md § Wave Planning — Project Board Is Authoritative`); the Wave field is the derived projection. If drift is found, repair it before continuing.

### 2. Gather merged PRs

List all PRs merged to the wave's deployments branch:

```bash
gh pr list --state merged --base "deployments/phase-{N}/wave-{M}" --json number,title,author,body,mergedAt,reviews
```

### 2.5. Status-counter verification (added P3W5 retro 2026-05-06)

Before per-engineer assessment, verify the numeric counters in `cross-repo-status.json` against PR-level evidence. The counters are written at wrapup time and tend to drift — recompute them from the PR data gathered in Step 2 and surface drift before it propagates into the retro narrative.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"

# Read claimed counters
CLAIMED_PR_COUNT=$(jq -r ".wave_${M}_final_pr_count" "$REPO_ROOT/cross-repo-status.json")
CLAIMED_CR_CYCLES=$(jq -r ".wave_${M}_changes_requested_cycles" "$REPO_ROOT/cross-repo-status.json")
CLAIMED_CONCENTRATION=$(jq -r ".wave_${M}_top_concentration_pct" "$REPO_ROOT/cross-repo-status.json")

# Recompute from Step-2 PR data (sum across all repos in scope)
ACTUAL_PR_COUNT=...           # count of merged PRs across wave_${M}_repos_in_scope
ACTUAL_CR_CYCLES=...           # count of comments where RequestOrReplied == "ChangesRequested"
ACTUAL_CONCENTRATION=...       # max(PRs by single author) / total PRs, as integer percent

# Surface drift
if [ "$CLAIMED_PR_COUNT" != "$ACTUAL_PR_COUNT" ]; then
  echo "DRIFT: wave_${M}_final_pr_count = $CLAIMED_PR_COUNT (claimed) vs $ACTUAL_PR_COUNT (actual)"
fi
# ... same for CR cycles, concentration
```

**Required handling per drift case:**

1. **Counter mismatch ≤ ±2 or ≤ ±5%**: log the correction in the retro feedback_log entry under "Top 3 pain points" or "Orchestrator Needs Improvement", and rewrite the counter in `cross-repo-status.json` with a `wave_{N}_counter_corrections` array entry recording the (claimed, actual, corrected_at) triple.
2. **Counter mismatch > ±2 or > ±5%**: surface as retro-blocker — investigate the wrapup-time arithmetic (likely a bug in `/wave-wrapup` step 7 or 10) before continuing the retro. File a follow-up issue against the wrapup skill.

**Why:** P3W4 wrapup wrote `wave_4_top_concentration_pct: 22` when the actual was 80% (recomputed at retro). P3W5 wrapup wrote `wave_5_changes_requested_cycles: 6` when the actual was 4 (recomputed at retro). Same-class drift across two consecutive waves: wrapup-time counters are not being re-verified, and they are being narrated into retro language as if authoritative. Operationally, drifted counters distort the trust matrix and the wave-shape table — either the retro relies on the wrong numbers, or a separate recomputation pass quietly happens with no record of the mismatch.

**Acceptance:** Step 3 (gather review comments) does not begin until every numeric counter in `wave_{M}_*` either matches the PR-level recomputation OR has a `wave_{M}_counter_corrections` entry recording the gap.

**CR-cycle counter semantics — wrapup-time count is authoritative-historic (added P3W15 retro change #4, owner-approved 2026-06-02):** `changes_requested_cycles` recomputation from *current* comment state will under-count whenever a ChangesRequested verdict was later edited-in-place to Approved (which is exactly what charter `pull-requests.md` § verdict-amendment requires after fixes land). The two rules collide by design: the amendment rule rewrites history's surface; the recomputation reads only that surface. **Resolution:** when recomputed < claimed AND the gap is fully explained by edit-in-place verdicts (verify via the PR's review timeline or the wrapup-time record), the **claimed (wrapup-time) value stands as authoritative-historic**. Record a `wave_{M}_counter_corrections` entry documenting the measurement conflict — do NOT "correct" the historical count downward. Worked example: P3W15 claimed 1 CR cycle (Nino→Aisha, deploy#396); retro recomputation found 0 because the verdict was edited to Approved; the claimed 1 stood.

### 3. Gather review comments and CI data

For each merged PR:

```bash
gh pr view {NUMBER} --json reviews,comments
gh run list --branch {PR_BRANCH} --json conclusion,name
```

Collect:
- Review comments (must-fix items, tech-debt items)
- CI pass/fail counts per PR
- Time from PR creation to merge

### 4. Per-engineer assessment

Per-engineer trust scoring is **mechanical and evidence-anchored** as of P6W17 (#842 / Option B §4b) — narrative self-grading is retired. Read the per-engineer signals `/wave-wrapup` Step 10.6 wrote, or re-extract them (the helper is idempotent over the same merged-PR set):

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
# Prefer the wrapup-written block; fall back to a live re-extract if absent.
jq -e --arg m "{M}" '.["wave_" + $m + "_trust_signals"]' "$REPO_ROOT/cross-repo-status.json" \
  || python3 "$REPO_ROOT/.claude/lib/trust_signals.py" extract {N} {M}

# `score` emits, per engineer: signals, the bidirectional delta, the
# distribution-disciplined proposed score, and the forced negative-signal line.
python3 "$REPO_ROOT/.claude/lib/trust_signals.py" score {N} {M}
```

For each engineer who had PRs in this wave, assess from the **countable signals** (`prs_merged`, `must_fix_caught`, `must_fix_received`, `ci_red_merges`, `rework_cycles`, `review_false_positives`) — not from narrative impressions:

```
### {Engineer Name}
- PRs: #{N1}, #{N2}
- Signals: prs_merged={x}, must_fix_caught={x}, must_fix_received={x}, ci_red_merges={x}, rework_cycles={x}, review_false_positives={x}
- Delta: {trust_signals.score_delta} (cite the signal(s) behind it)
- Negative-signal line: {trust_signals.negative_signal_line — a specific gap OR "metrics clean: {numbers}", NEVER bare "None"}
- Severity: {minor|moderate|severe|none}
```

**Forced negative-signal pass (banned: bare "None").** Every active engineer MUST get a `negative_signal_line` — a specific evidence-backed gap or an explicit `metrics clean: {numbers}`. Mechanically reject a bare `None` / `N/A` / `-` before continuing:

```bash
# Collect the negative-signal lines you wrote (one per engineer) into a file,
# then validate. A non-empty result is a forced-pass violation — fix it.
python3 - <<'PY'
import sys
sys.path.insert(0, ".claude/lib")
import trust_signals
lines = [ln.rstrip("\n") for ln in open("/tmp/negative_signal_lines.txt")]
bad = trust_signals.validate_negative_signal_pass(lines)
if bad:
    print("FORCED-PASS VIOLATION (bare None banned):", bad)
    sys.exit(1)
print("negative-signal pass clean")
PY
```

### 5. Update trust matrix

**Trust matrix lives on `main`**, not a side branch. Edit `.claude/team/trust_matrix.md` directly on the retro branch so the update lands in the same retro PR as the feedback log. Do NOT use a separate worktree or push to `CEO/0000-Trust_Matrix` — that pattern (retired 2026-04-17) orphaned trust updates off-main for months.

Trust deltas are **mechanical** (`.claude/team/trust_matrix.md` § Mechanical Scoring, implemented in `.claude/lib/trust_signals.py`) — every row cites the countable signal behind it:

- **Delta:** `new = clamp(old + score_delta(signals), 1, 5)` — bidirectional, clamped to ±2/wave. Each CI-red merge / false-positive is −1; clean multi-PR delivery or strong reviewing (`must_fix_caught ≥ 2`) is +1. A single clean PR is **not** a bump.
- **Decay:** an engineer with no signal for 3 consecutive waves drifts one step toward 3 (`trust_signals.decay`).
- **Distribution discipline:** 5 is reserved for the wave's top relative performer (`trust_signals.apply_distribution_discipline`) — never handed out for merely-clean work.
- **Retirement trigger:** run `trust_signals.retirement_trigger(score_history, ci_red_history)` per engineer; if it fires (bottom-tier ≤2 or ≥1 CI-red merge in each of the last 3 waves), surface a **persona-archive recommendation** for owner confirmation — do not auto-delete.

Append a new `## Phase {N} Wave {M} Trust Updates ({DATE}) — {theme}` section with:
- A `| Rated | Old | New | Reason |` table for each relevant team grouping (e.g., `### Org-Level Team`) — the `Reason` MUST cite the signal numbers, not prose impressions.
- A `### Done Well / Needs Improvement (Phase {N} Wave {M})` matrix whose "Needs Improvement" column is the forced negative-signal line (no bare "None").

The edit will be committed as part of the retro PR (see Step 6). Do NOT create a separate commit or PR for the trust matrix update.

### 6. Append to feedback log

Append a retro entry to `.claude/team/feedback_log.md`:

```markdown
## Retrospective: Phase {N} Wave {M} — {DATE}

### Team Performance
{summary of wave metrics: PRs merged, issues closed, CI health}

### Per-Engineer Assessments
{from step 3}

### Top 3 Going Well
1. {finding}
2. {finding}
3. {finding}

### Top 3 Pain Points
1. {finding}
2. {finding}
3. {finding}

### Proposed Process Changes
1. {change} — Rationale: {why}
2. {change} — Rationale: {why}
```

### 6.5. Retro PR body-vs-diff sanity check (added P3W9 #126 — 2026-05-12)

Per `charter/pull-requests.md § Retro PR Body-vs-Diff Discipline`: any charter/skill/trust-matrix file claimed in the retro PR body MUST be in the retro PR diff. Direct-to-main commits for ratified retro outputs are forbidden.

Once the retro PR is open, before requesting reviewers:

```bash
RETRO_PR=<N>
gh pr view "$RETRO_PR" --repo noorinalabs/noorinalabs-main --json files --jq '[.files[].path] | sort'
# Compare against the "Files changed" section of the PR body. Every charter/skill/trust file
# claimed in the body MUST appear in the listing. If a claimed file is missing, commit it
# to the retro branch and push — do NOT amend the body to remove the claim, and do NOT
# commit the substantive change direct-to-main.
```

Worked example of the failure mode: PR #124 (W8 retro) body claimed 7 files, diff contained 2; the other 5 were committed direct-to-main (`2b92605`, `ecd1c76`). Filed as #126; this step prevents repeats.

### 7. Propose charter changes

Based on pain points and findings, propose specific charter amendments. Present each as:

```
**Proposed change:** {what to change in charter}
**Section:** {which charter section}
**Rationale:** {why, based on retro findings}
```


### 7.5. Run promotion audit (`/promotion-audit`)

Invoke `/promotion-audit` to deterministically check whether any memories, charter sections, or skills have crossed promotion thresholds during this wave. The audit resolves the current wave from `cross-repo-status.json`, classifies every candidate, and:

- **AUTO-tier** (memory → charter, charter → skill): opens a PR with the auto-generated artifact; lands via the standard 2-reviewer pattern.
- **DECIDE-tier** (skill → hook): files a draft issue with the proposed hook design. Hooks are security-sensitive — never auto-applied (D6).
- **KEPT / SUPERSEDED / ALREADY-PROMOTED**: informational; no action.

The audit appends its table to this retro's feedback_log entry **and** writes a standalone log at `.claude/team/promotion_audit_log/{wave-name}.md`. On unchanged repo state, the audit is byte-deterministic — re-running produces identical output. See issue #152 for the full pipeline spec and PR #153 / Hook 15 for the worked example.

### 7.6. Annunaki-attack (added P3W9 #344 — 2026-05-11)

Invoke `/annunaki-attack` to process errors captured by the Annunaki monitor during this wave. Any hooks/skills/charter changes that emerge feed back into Step 7 (charter changes) retroactively — review the new artifacts in this retro's charter-changes proposal block.

This step is **co-located** with `/wave-wrapup` Step 13. The run-marker check below prevents double-execution; whichever surface runs first wins, and the other surface skips.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
ALREADY_RAN=$(jq -r ".wave_${M}_annunaki_attack_ran_at // empty" "$REPO_ROOT/cross-repo-status.json")

if [ -n "$ALREADY_RAN" ]; then
  echo "Annunaki-attack: already ran at $ALREADY_RAN (likely via /wave-wrapup Step 13). Skipping."
else
  # Invoke /annunaki-attack with the current wave context.
  # On successful completion, the skill (or this step's post-invoke wrapper) writes:
  #   wave_${M}_annunaki_attack_ran_at = <ISO-8601 UTC timestamp>
  # to cross-repo-status.json — the marker /wave-wrapup Step 13 reads.
fi
```

If `.claude/annunaki/errors.jsonl` is empty or missing, report "Annunaki: No errors captured this wave" and still write the marker (so wrapup's Step 13 doesn't re-check). Include any Annunaki-created issues + PRs in the wave-shape table and per-engineer assessments (Step 4) before presenting the retro at Step 8.

This step runs **before** Step 7.7 (memory-to-automation audit) so that new hooks/skills/charter from error analysis are visible to the memory audit — a memory file matching a just-created hook can be retired in the same retro instead of re-surfacing as a separate audit candidate.

### 7.7. Memory-to-automation audit (added P3W9 #344 — 2026-05-11)

Examine all memory files in the project memory directory for entries that describe behaviors, rules, or patterns that could be codified as a **hook**, **skill**, or **charter update** instead of remaining as soft memory. Findings feed Step 7 (charter changes) retroactively.

This step is **co-located** with `/wave-wrapup` Step 14. Run-marker check is the same pattern as 7.6:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
ALREADY_RAN=$(jq -r ".wave_${M}_memory_audit_ran_at // empty" "$REPO_ROOT/cross-repo-status.json")

if [ -n "$ALREADY_RAN" ]; then
  echo "Memory-to-automation audit: already ran at $ALREADY_RAN (likely via /wave-wrapup Step 14). Skipping."
else
  # Run the audit per the recipe in /wave-wrapup Step 14 (kept canonical there to avoid duplication):
  #   1. Read all memory files: ls ~/.claude/projects/*/memory/*.md
  #   2. Classify each: Hook candidate | Skill candidate | Charter update | Keep as memory
  #   3. For each non-keep classification: file an issue, spawn/message best-fit owner, verify, delete/update memory
  #   4. Report the conversion table
  # On completion, write wave_${M}_memory_audit_ran_at = <ISO-8601 UTC timestamp> to cross-repo-status.json.
fi
```

**Designated owner:** Aino Virtanen handles most conversions (hooks, charter, standards). The orchestrator spawns her with the audit list and she reports back when done — same convention as `/wave-wrapup` Step 14.

**Why retro is the preferred surface (P3W9 #344 rationale):** wave-wrapup is already long, and the audits routinely get deferred at wrapup time, pushing them days or weeks into the next wave-wrapup cycle. Retro is the natural moment because:
- The retro narrative already discusses charter-change proposals (Step 7); promotion candidates discovered in Step 7.7 land in the same proposal block.
- Trust matrix updates (Step 5) and feedback_log entries (Step 6) are already in flight; new Aino-assigned audit-conversion issues count toward her wave engagement in the same retro pass.
- Carry-forward to next wave (Step 9 `/wave-scope`) immediately follows; any audit-conversion issues filed here are visible to scope reconciliation.

P3W8 surfaced the gap (2026-05-10): user explicitly noted "these should be a part of the wave-retro for next time." This step is that next time.

### 8. Present full retro summary to the user

**Output the complete retro summary directly in the conversation.** Do not just write to files — the user must see the retro without having to open `feedback_log.md`. Include:

- **Wave metrics:** PRs merged, issues closed, CI health, tech-debt filed
- **Per-engineer assessments:** each engineer's PRs, must-fix items, CI failures, severity rating
- **Trust matrix changes:** who went up/down and why
- **Top 3 going well**
- **Top 3 pain points**
- **Proposed process changes** with rationale
- **Fire/hire actions** (if any)
- **Proposed charter changes** (if any)

**Do NOT apply any charter changes without explicit user approval.** The user decides which proposals to adopt, modify, or reject.

### 9. Reconcile next-wave scope (`/wave-scope`) — added P3W5 #273

Carry-forward and memory-must-include state is freshest immediately after retro, so this is the highest-value moment to run `/wave-scope`. Auto-invoke if the next-wave meta-issue exists; **otherwise auto-draft a stub meta-issue** (the scaffold is mechanical — only the theme is an owner decision) and surface "set the theme," rather than re-emitting a manual "go draft an issue" blocker every retro (owner directive, P4W1 retro 2026-06-10 — the blocker recurred every wave).

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
# Global wave ids (main#804) are monotonic and NOT sequential-per-phase, so the
# next wave id is NOT {M}+1 (e.g. after the grandfathered wave_2 the next id is
# wave_16). Read it from the counter instead of computing it.
NEXT_WAVE=$(python3 "$REPO_ROOT/.claude/lib/wave_seq.py" peek "$REPO_ROOT/cross-repo-status.json")

# Anchored title pattern + open-state filter. Meta-issue title format is
# "Phase {N} Wave <next-global-id> — <theme>" — the dash-space tail prevents bleed into
# retro tracking issues like "Phase 3 Wave 5 retro tracking" that some teams
# file separately. Asserting exactly-one-hit surfaces ambiguity as a blocker
# instead of silently picking whichever issue GitHub orders first.
META_HITS=$(gh issue list --repo noorinalabs/noorinalabs-main --state open \
    --search "\"Phase {N} Wave $NEXT_WAVE —\" in:title" \
    --json number,title)
HIT_COUNT=$(echo "$META_HITS" | jq 'length')
NEXT_META_ISSUE=$(echo "$META_HITS" | jq -r '.[0].number // empty')

if [ "$HIT_COUNT" -eq 0 ]; then
  # AUTO-DRAFT the next-wave meta-issue stub (P4W1 retro 2026-06-10 — owner
  # directive: stop re-surfacing "draft the meta-issue" as a manual blocker
  # every retro). The stub's scaffold — title, carry-forward, candidate pointer
  # — is mechanical; only the THEME is an owner decision. We create it with a
  # TBD theme, board it, and record wave_${NEXT_WAVE}_meta_issue, then surface
  # "set the theme". /wave-scope Gate B still blocks on the owner-set theme, so
  # this removes the toil without removing the owner decision.
  #
  # Carry-forward scaffold: any "deliberately_not_in_w*" deferred markers from
  # this wave's scope (machine-readable). The owner/orchestrator refines at
  # /wave-scope; this is a starting point, not the final scope.
  DEFERRED=$(jq -r '.["wave_{M}_scope"] // {} | to_entries[]
      | select(.key | startswith("deliberately_not_in_w"))
      | .value[]? | "- " + .' "$REPO_ROOT/cross-repo-status.json" 2>/dev/null)
  [ -z "$DEFERRED" ] && DEFERRED="- (no deferred markers recorded in wave_{M}_scope — see this retro's feedback_log entry for carry-forward)"

  STUB_BODY=$(cat <<MD
## Theme

**TBD — owner to set.** Replace this line with the wave theme, then \`/wave-scope {N} $NEXT_WAVE\` proceeds (Gate B reads the theme from this heading + cross-repo-status.json).

## Carry-forward from Phase {N} Wave {M} (auto-scaffold)
$DEFERRED

## Candidate scope (refined at /wave-scope {N} $NEXT_WAVE)
- Open issues labeled for the next wave, plus the **+20% tech-debt intake** applied automatically at \`/wave-scope\` Step 8.5.
- See the Phase {N} Wave {M} retro entry in \`.claude/team/feedback_log.md\` for pain-point follow-ups to fold in.

---
*Auto-drafted stub from \`/wave-retro {N} {M}\` Step 9. Owner sets the theme; \`/wave-scope\` finalizes scope. Title + ## Theme line are the only manual edits.*
MD
)
  NEW_URL=$(gh issue create --repo noorinalabs/noorinalabs-main \
    --title "Phase {N} Wave $NEXT_WAVE — (theme TBD — owner to set)" \
    --body "$STUB_BODY")
  NEW_NUM=$(echo "$NEW_URL" | grep -oE '[0-9]+$')
  gh project item-add 2 --owner noorinalabs --url "$NEW_URL" 2>/dev/null || true
  # NOTE (main#885): this reserves the id via the meta_issue key only and does
  # NOT bump global_wave_seq (the counter advances at /wave-scope `allocate
  # --write`). That split is SAFE because `wave_seq.py` is reservation-aware:
  # `allocate`/`peek` detect this `wave_${NEXT_WAVE}_meta_issue` reservation at
  # `global_wave_seq + 1` and claim THAT id instead of skipping past it. Do not
  # "fix" this by adding a counter bump here — that would double-advance.
  python3 "$REPO_ROOT/.claude/lib/upsert_status_keys.py" "$REPO_ROOT/cross-repo-status.json" \
    "wave_${NEXT_WAVE}_meta_issue=\"noorinalabs-main#$NEW_NUM\""
  echo "AUTO-DRAFTED next-wave meta-issue stub: $NEW_URL"
  echo "  → Set the theme (replace the TBD ## Theme line + the title), then /wave-scope {N} $NEXT_WAVE proceeds."
  echo "    The theme is the ONLY manual step — the stub, board card, and status key are already in place."
  NEXT_META_ISSUE="$NEW_NUM"
elif [ "$HIT_COUNT" -gt 1 ]; then
  echo "BLOCKER for /wave-kickoff p{N} w$NEXT_WAVE:"
  echo "  Multiple open issues match 'Phase {N} Wave $NEXT_WAVE —' in title — meta-issue is ambiguous:"
  echo "$META_HITS" | jq -r '.[] | "    - #\(.number): \(.title)"'
  echo "  Resolve before running /wave-scope."
else
  echo "Auto-invoking /wave-scope {N} $NEXT_WAVE (next-wave meta-issue: noorinalabs-main#$NEXT_META_ISSUE)"
  # Invoke the skill — it will write wave_${NEXT_WAVE}_scope_reconciled_at to cross-repo-status.json on success.
fi
```

**When a meta-issue with a set (non-TBD) theme exists** (the `HIT_COUNT == 1` branch), invoke the `/wave-scope` skill with the next phase + wave numbers. The skill is responsible for:
- Reading carry-forward (just-written by step 6) and memory must-includes
- Reconciling declared (meta-issue) vs labeled scope across all repos
- Refreshing the next-wave meta-issue body
- Writing `wave_$NEXT_WAVE_scope_reconciled_at` so `/wave-kickoff` Step 0a passes

**When the stub was just auto-drafted** (the `HIT_COUNT == 0` branch above), do **NOT** invoke `/wave-scope` yet — its Gate B requires an owner-set theme, and the stub's theme is `TBD`. Surface the auto-drafted issue URL and stop; the owner sets the theme, then `/wave-scope {N} $NEXT_WAVE` runs on the next turn (or the next retro/session picks it up via the now-existing meta-issue).

This step closes the retro→kickoff handoff loop: every retro produces *either* a reconciled next-wave scope *or* a ready-to-theme stub meta-issue — never a bare "go create an issue" blocker. The only manual action left to the owner is the theme decision itself.

## What remains manual

- User must approve all charter changes before they are applied
- Subjective assessment calibration (severity levels) may need user override
- Trust matrix changes are proposed — user can veto specific adjustments

## Wave-Concentration Metric (added P3W4 retro 2026-05-05)

In step 4 (per-engineer assessment), compute and report the **top-implementer concentration**:

```
top_concentration = (max PRs by single implementer) / (total PRs in wave)
```

If `top_concentration >= 0.6`, surface this in step 6 (feedback log) under "Top 3 pain points" or "Top 3 going well" depending on context:

- **Theme-fit concentration** (e.g., wave themed on a single domain that one engineer owns): note as a "going well" with a forward-looking flag for next wave's planning.
- **Fragility concentration** (e.g., a multi-domain wave where one engineer happened to absorb most of the load): note as a "pain point" with explicit redistribution actions for the next wave.

The metric is **visibility, not policy** — concentration is sometimes correct (theme-fit) and sometimes a risk (fragility); the retro forces the call.

Include in the wave-shape table as a separate row:

| Top-implementer concentration | {N PRs} / {total} = {pct}% by {engineer} |

**Why:** P3W4 had 80% of main# PRs from one engineer (Aino, 8 of 10). The work was clean (theme-fit hook bug-class consolidation), but the dependency risk on W5 carry-forwards (#263, #264 also Aino-tractable) was invisible until retro. A concentration row at the top of every retro forces next-wave planning to address it explicitly — distribute, accept the risk and document, or theme the next wave around the same engineer's surface.
