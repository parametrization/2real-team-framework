---
name: file-bug
description: File a GitHub issue with built-in dup-search, drift-evidence-on-existing-issue, and multi-layer-gap discrimination. Consolidates 3 charter-promotion-target memories into a single command.
args: optional — keyword(s) describing the bug; if omitted, the skill prompts for them
---

Files a GitHub issue against the appropriate repo, but FIRST runs three discriminator passes that catch:

1. **Duplicates** — same root cause, different framing
2. **Drift evidence** — single-instance drift covered by an open rationalization workstream
3. **Multi-layer gaps** — distinct layers (detection / strategy / docs) that share a root cause but are NOT duplicates

This skill consolidates three feedback memories that have hit the charter-promotion threshold but are skill-shaped, not charter-shaped:

- `feedback_search_before_filing.md` — duplicate detection
- `feedback_drift_evidence_to_existing_rationalization_issue.md` — single-instance-of-pattern detection
- `feedback_multi_layer_gap_filing.md` — distinct-layer counter-rule

> **Note:** all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory.

## When to use

- The user reports a bug or surfaces a gap in conversation.
- A code review surfaces a finding that needs tracking.
- The orchestrator's `/wave-wrapup` audit identifies a rationalization opportunity.

Invoke as `/file-bug <keywords>` (e.g., `/file-bug CSP theme-flash`) OR with no args (the skill will prompt).

## Instructions

### 1. Gather inputs

Identify:

- **Symptom keywords** — 2-4 words from the surface symptom (e.g., `theme flash`, `notify-deploy`, `OAuth /token`).
- **Suspected root cause keywords** — 2-4 words describing the underlying mechanism (e.g., `CSP inline script`, `repository_dispatch event-type`, `URL override prod-gate`).
- **Layer classification** (preliminary) — is this:
  - **detection** (CI / hook / validator / monitor)
  - **strategy / architectural** (ADR, IaC pattern, ownership)
  - **docs / runbook** (operator procedure, escalation path)
  - **bug** (single concrete defect at one layer)
- **Affected repo** — which repo's tracker should the issue land in?
- **Layer-sibling candidates** — does this incident also surface gaps at OTHER layers? (Pre-flag for the multi-layer-gap pass below.)

### 2. Pass A — search-before-filing (duplicate detection)

Search the relevant repo for existing issues that may cover the same root cause:

```bash
gh issue list --repo "noorinalabs/<repo>" --state all --search "<symptom keywords>" --json number,title,state --limit 10
gh issue list --repo "noorinalabs/<repo>" --state all --search "<root-cause keywords>" --json number,title,state --limit 10
```

For cross-repo bugs (deploy chain, CSP, auth, ontology), search BOTH the symptom-side repo AND the cause-side repo. Examples:

- notify-deploy bugs may be filed in `noorinalabs-deploy` OR `noorinalabs-isnad-graph`.
- CSP issues may be filed in `noorinalabs-isnad-graph` OR `noorinalabs-design-system`.
- Hook drift may be filed in `noorinalabs-main` OR the affected child repo.

Read the matches.

> **Origin > local clone**: when evaluating file-content claims in a matched issue (e.g., "file X still exists at path Y", "config Z has value W"), fetch via `gh api repos/<owner>/<repo>/contents/<path>?ref=<head_sha>` — NOT the local clone. Local main may lag origin, especially during waves where work lands on a wave branch first. Charter `pull-requests.md § Origin > Local Clone for "Still-Has-X" File-Content Claims` (promoted from `feedback_origin_over_local_for_still_has_claims.md`, Bereket→Lucas-87/PR #181 2026-04-28).

Score each as:

| Score | Meaning | Action |
|---|---|---|
| **STRONG dup** | Same root cause, same proposed fix; titles share core keywords | Comment new diagnosis on existing issue, exit |
| **WEAK dup** | Adjacent symptom, may share root cause but unclear | Comment on existing AND consider continuing — confirm with user |
| **No match** | No existing issue covers this | Continue to Pass B |

If STRONG dup: comment your diagnosis (with `gh api` head_sha verification per `state-claims.md § Refresh State Before Claim`), then EXIT. Do not file a new issue.

### 3. Pass B — drift-evidence-on-existing (single-instance pattern detection)

Even if Pass A found no symptom dup, search for open **rationalization / cleanup** issues whose execution would eliminate this entire class of bug:

```bash
gh issue list --repo "noorinalabs/<repo>" --state open \
  --search "rationalize OR consolidate OR standardize OR cleanup OR canonical" \
  --json number,title,labels --limit 20
```

Also search for issue titles matching `tech-debt:`, `rationalize:`, `consolidate:`, `cleanup:`, `standardize:`.

If your incident is a **single concrete instance** of a pattern that one of these issues would eliminate (typical examples: copy-resident drift, duplicated config, divergent paths after rename), the right action is to **comment evidence on the existing rationalization issue**, NOT file a new single-instance ticket.

Decision rule:

| Pattern | Open rationalization issue exists? | Action |
|---|---|---|
| Single-instance drift | Yes — would eliminate this class | Comment evidence on existing; do NOT file |
| Single-instance drift | No | Continue to Pass C |
| Multi-instance / new class | (irrelevant) | Continue to Pass C |

Comment shape on the existing rationalization issue:

```markdown
## Concrete drift example surfaced 2026-MM-DD

**Surface:** <file path or component>
**Drift observed:** <specific divergence — sha refs, line numbers>
**Source:** <where this surfaced — code review of PR #N, /wave-wrapup audit, etc.>

This strengthens the case for #<this-issue> rationalization (concrete > abstract).
Not filed as a separate issue per `feedback_drift_evidence_to_existing_rationalization_issue.md`.
```

Surface the observation in the originating review comment as well (so the author sees it inline). Both, not either.

### 4. Pass C — multi-layer-gap discrimination

If the incident has surfaced gaps at MORE THAN ONE layer (detection AND strategy, or strategy AND docs, etc.), **file separately at each layer with cross-references** rather than collapsing into one comprehensive issue.

Distinct-layer issues that share a root cause are NOT duplicates. The `search-before-filing` rule (Pass A) catches symptom-dup; this rule catches the inverse — false-collapse of distinct layers.

Worked example (B2 cred rotation, 2026-04-28):

| Layer | Issue | Concern |
|---|---|---|
| Detection | `noorinalabs-deploy#158` | CI validate-creds drift check (automation) |
| Strategy | `noorinalabs-deploy#180` | ADR / bucket IaC management, rotation cadence (architectural decision) |
| Docs | `noorinalabs-deploy#182` | Operator runbook for rotation loop (documentation) |

Each was filed separately, all three cross-referenced in their bodies. Bereket initially proposed dedup at retro; Lucas-Rev-177's three-layer separation overrode.

For each distinct-layer issue, draft a body that:

- Names the layer in the title prefix (e.g., `detection:`, `strategy:`, `docs:`)
- Cross-references all sibling issues in a `## Layer siblings` section
- Notes the shared root cause but the layer-specific scope

### 5. File the issue (single layer, or one of N)

After Passes A + B + C, file the new issue (or batch of layer-issues):

```bash
gh issue create --repo "noorinalabs/<repo>" \
  --title "<discoverable title — symptom + root-cause guess>" \
  --body-file /tmp/issue-body-<descriptive-slug>.txt \
  --label "<bug|tech-debt>" \
  --label "<assignee-label, if known>" \
  --label "<wave-label, if applicable>"
```

Title discipline (per `feedback_search_before_filing.md`): include both the symptom AND a guess at the root cause. The next person who hits this should find your issue via either keyword.

Issue body skeleton:

```markdown
## Symptom

<observable behavior, with file/line references where possible>

## Suspected root cause

<mechanism — what's broken, why>

## Reproduction (if applicable)

<minimal repro steps>

## Layer siblings (if multi-layer)

- detection: #N
- strategy: #M
- docs: #K

## Pre-filing dup-search performed

- `gh issue list --search "<symptom>"` → no matches OR matches considered: #X (different scope), #Y (different scope)
- `gh issue list --search "<root-cause>"` → no matches OR matches considered: #Z (resolved 2026-MM-DD)
- Rationalization scan (Pass B) → no eliminating issue found OR found #W (this is multi-instance / new class, not single-instance covered by #W)

## Acceptance Criteria

- [ ] <specific, testable>
- [ ] <specific, testable>

## Out of scope

<what this issue does NOT cover, with cross-refs to where it does>
```

Per `feedback_tmp_msg_file_stale.md`: write the body to `/tmp/issue-body-<descriptive-slug>.txt` (NOT `/tmp/msg.txt` — the issue#-keyed slug avoids the stale-tmp-file race), then `gh issue create --body-file`. Read-back-verify within 30s of creation per `feedback_gh_pr_edit_silent_noop.md`:

```bash
NEW_ISSUE_NUM=<from gh issue create output>
gh issue view "$NEW_ISSUE_NUM" --repo "noorinalabs/<repo>" --json number,title,labels --jq '{n:.number, t:.title, l:[.labels[].name]}'
```

### 6. Post-file follow-up

Per `CLAUDE.md § Bug Report Workflow`:

1. **Label for current wave** — check `cross-repo-status.json` for `wave_<N>_active=true`, apply that wave label.
2. **Add to project board** — `gh project item-add 2 --owner noorinalabs --url <issue-url>`.
3. **If multi-layer:** repeat steps 5-6 for each sibling issue, then update each issue's `## Layer siblings` section with the actual issue numbers (since they only become known after creation).

### 7. Telemetry append (every invocation)

Append a single JSONL line per `/file-bug` invocation to `.claude/.file-bug-log.jsonl` (gitignored). Captures the Pass A/B/C outcome and the disposition (filed-new, commented-existing, etc.) so aggregate signal is queryable without re-deriving from issue-body prose.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
LOG="$REPO_ROOT/.claude/.file-bug-log.jsonl"

# Build the record from your in-skill state. Pass values come from each Pass's
# outcome (the prose summary in Step 8 already encodes them).
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
REPO_FULL="noorinalabs/<repo>"
PASS_A="<STRONG_DUP|WEAK_DUP|NO_MATCH>"       # Step 2 outcome
PASS_B="<COMMENTED_ON|NO_MATCH|SKIPPED>"      # Step 3 outcome (SKIPPED if A intercepted)
PASS_C="<SINGLE_LAYER|MULTI_LAYER_N|SKIPPED>" # Step 4 outcome (SKIPPED if A/B intercepted)
DISPOSITION="<FILED_NEW|FILED_MULTIPLE|COMMENTED_EXISTING|NOT_FILED>"
# Issue numbers as a JSON array: the new issue(s) filed, OR the existing issue
# you commented on, OR empty array if nothing was created/touched.
ISSUE_NUMBERS_JSON='[362]'   # or '[]' or '[362,363,364]' for multi-layer

jq -c -n \
  --arg ts "$TS" \
  --arg repo "$REPO_FULL" \
  --arg a "$PASS_A" \
  --arg b "$PASS_B" \
  --arg c "$PASS_C" \
  --arg d "$DISPOSITION" \
  --argjson nums "$ISSUE_NUMBERS_JSON" \
  '{ts:$ts, repo:$repo, pass_a:$a, pass_b:$b, pass_c:$c, disposition:$d, issue_numbers:$nums}' \
  >> "$LOG"
```

The record is append-only — no rewrites, no per-issue back-references. Each invocation produces exactly one line, regardless of whether 0 / 1 / N issues were created.

Required state values (closed enums — keep stable so retro queries don't drift):

| Field | Values |
|---|---|
| `pass_a` | `STRONG_DUP`, `WEAK_DUP`, `NO_MATCH` |
| `pass_b` | `COMMENTED_ON`, `NO_MATCH`, `SKIPPED` |
| `pass_c` | `SINGLE_LAYER`, `MULTI_LAYER_2`, `MULTI_LAYER_3`, …, `SKIPPED` |
| `disposition` | `FILED_NEW`, `FILED_MULTIPLE`, `COMMENTED_EXISTING`, `NOT_FILED` |

If you EXIT at Pass A on STRONG dup: `pass_a=STRONG_DUP`, `pass_b=SKIPPED`, `pass_c=SKIPPED`, `disposition=COMMENTED_EXISTING`, `issue_numbers=[<the existing one>]`.

If you comment evidence on a rationalization issue at Pass B: `pass_a=NO_MATCH`, `pass_b=COMMENTED_ON`, `pass_c=SKIPPED`, `disposition=COMMENTED_EXISTING`.

If you file N siblings at Pass C: `disposition=FILED_MULTIPLE`, `pass_c=MULTI_LAYER_N`, `issue_numbers=[<all N>]`.

## Output to user

Present a structured summary:

```
**File-bug result**

| Pass | Result |
|---|---|
| A — search-before-filing | <STRONG dup #N | WEAK dup #M | no match> |
| B — drift-evidence-on-existing | <commented on #K | no rationalization match> |
| C — multi-layer | <single layer | N siblings: #X #Y #Z> |

**Action taken:** <filed #N | commented on #K | filed N siblings: #X #Y #Z>
**Follow-up:** <wave-labeled, project-board-added, all sibling cross-refs updated>
```

If Pass A or B intercepted the file (no new issue created), state that clearly so the operator knows the bug is tracked even though no new issue exists.

## What remains manual

- **Score interpretation** — STRONG vs WEAK dup is judgment; the skill surfaces matches, the operator decides.
- **Layer classification at incident time** — the skill prompts for it but does not infer it.
- **Acceptance criteria authorship** — domain-specific, operator-authored.

The skill encodes the discipline; it does not replace the judgment.

## Reporting

Aggregate signal lives in `.claude/.file-bug-log.jsonl` (gitignored, append-only). Query directly with `jq -s` — no separate reporting skill is required.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
LOG="$REPO_ROOT/.claude/.file-bug-log.jsonl"

# Total invocations this wave (or all-time if no time filter)
jq -s 'length' "$LOG"

# Pass A intercept rate — would-have-duped saves
jq -s '[.[] | select(.pass_a == "STRONG_DUP")] | length' "$LOG"

# Pass B intercept rate — drift-evidence-on-existing
jq -s '[.[] | select(.pass_b == "COMMENTED_ON")] | length' "$LOG"

# Pass C multi-layer preservation — issues that would have been collapsed
# by Pass-A-alone but were correctly split by Pass C
jq -s '[.[] | select(.pass_c | startswith("MULTI_LAYER_"))] | length' "$LOG"

# Per-repo dup-attempt rate
jq -s 'group_by(.repo) | map({
  repo: .[0].repo,
  total: length,
  strong_dup: ([.[] | select(.pass_a == "STRONG_DUP")] | length),
  multi_layer: ([.[] | select(.pass_c | startswith("MULTI_LAYER_"))] | length)
})' "$LOG"

# This-wave only (filter by ISO date range)
WAVE_START="2026-05-10T17:55:00Z"
jq -s --arg s "$WAVE_START" '[.[] | select(.ts >= $s)] | {total: length,
  strong_dup: ([.[] | select(.pass_a == "STRONG_DUP")] | length),
  pass_b_commented: ([.[] | select(.pass_b == "COMMENTED_ON")] | length),
  multi_layer: ([.[] | select(.pass_c | startswith("MULTI_LAYER_"))] | length),
  filed_new: ([.[] | select(.disposition == "FILED_NEW")] | length),
  filed_multiple: ([.[] | select(.disposition == "FILED_MULTIPLE")] | length)
}' "$LOG"
```

`/wave-retro` Step 7.7 (memory-to-automation audit) should cite the wave-scoped totals from the last recipe in its skill-effectiveness summary, starting with the first retro after this PR lands.
