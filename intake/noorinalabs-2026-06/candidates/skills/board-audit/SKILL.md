---
name: board-audit
description: Periodic project-board drift check — detect orphan issues and sync the Wave field from labels
args: (none — runs against project 2 and all 8 org repos)
---

Detect drift between GitHub Project 2 (the Cross-Repo Wave Plan board) and the actual issue/PR state across all 8 `noorinalabs` repos. Two failure modes are gated:

1. **Orphan detection** — issues that exist but are NOT on the project board (invisible to any planning pass that reads the board).
2. **Wave-field drift** — issues whose wave label (`wave-{X}` or grandfathered `p{N}-wave-{M}`) disagrees with the project's `Wave` single-select field.

Closes main#199.

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Wave Lifecycle for the canonical skill order and preconditions.

## Background

On 2026-04-23 a manual audit found **72 of 193 open issues (37%) missing from project 2**. Root cause: Hook 13 (`auto_add_issue_to_board.py`) only catches `gh issue create` calls in active sessions — bot-created, manual-UI-created, and pre-hook-13 issues all drift off the board silently.

Decision (owner, 2026-04-25): **labels are canonical for phase/wave assignment; the Wave field is a derived projection**. This skill is the sync mechanism. Per `feedback_enforcement_hierarchy.md`, this is skill-tier enforcement; Option B (a daily cron + Hook 13 extension) is deferred unless drift recurs after this skill ships.

## Invocation patterns

- **Manual** — orchestrator runs `/board-audit` ad-hoc when board drift is suspected.
- **Wired into `/wave-kickoff`** — runs once before label-application so kickoff sees a current board.
- **Wired into `/wave-retro`** — runs once before retro-emit so the retro reads from a current board.
- **Wired into `/session-start` step 5** — drift report shown during session orientation.

## Pre-requisite — Wave-field options exist

The project's `Wave` single-select field MUST have an option for every active wave. Option-name grammar (#810, matching `_wave_label_parse.wave_label_to_option_name`):

- new phase-agnostic label `wave-{X}` → option `W{X}` (e.g. `wave-16` → `W16`)
- grandfathered legacy label `p{N}-wave-{M}` → option `P{N}W{M}` (e.g. `P3W9`)
- placeholder label `wave-x` → option `WX` ("Wave (TBD)")

Owner adds new options via the Project Settings → Fields → Wave UI (or `gh project field-create` with project-edit scope).

If an option is missing for a label encountered during sync (e.g., issues labeled `wave-16` but no `W16` option, or legacy `p3-wave-10` but no `P3W10`), the skill reports the missing options and skips those issues' field-sync (does NOT block; orphan detection still runs).

## Instructions

### 0. Run `/ontology-librarian` (mandatory)

Per Hook 15 (`enforce_librarian_consulted`). The board-audit work edits no source — but Hook 15 fires on Edit/Write regardless, and this skill MAY surface findings that get filed as issues (a `gh issue create` doesn't trigger Hook 15, but the librarian is cheap and lets the orchestrator decide whether to file).

```bash
/ontology-librarian board-audit drift orphan project field-sync
```

### 1. Fetch all open issues (with labels) across the 8 org repos

Fetch `url` **and** `labels` in one call per repo. The labels feed Step 4's drift
detection **in memory** — there is NO per-board-item `gh issue view` later (#888 defect 2).
Each call is wrapped in a `timeout` and skip-and-warns rather than hanging the whole
audit on a single stalled `gh` call (#888 defect 3 — the org-wide loop hung at the 2-min
mark twice, though each repo returns in <0.4 s alone).

```bash
# Literal repo list in the `for` (NOT `for repo in $SCALAR`) — under zsh an unquoted
# scalar is not word-split, so a "$REPOS"-string would collapse to one bogus iteration
# (#759). A literal word-list is split correctly in both bash and zsh.
: > /tmp/issue-labels.tsv      # url \t expected-Wave-option (computed from the wave label)
: > /tmp/all-issue-urls.txt    # every open issue url across the org

for repo in noorinalabs-main noorinalabs-isnad-graph noorinalabs-user-service \
            noorinalabs-deploy noorinalabs-design-system noorinalabs-landing-page \
            noorinalabs-data-acquisition noorinalabs-isnad-ingest-platform; do
  # Per-call timeout: one stalled call must not hang the whole audit (#888 defect 3).
  # `timeout` exits 124 on stall → the `if !` branch warns and `continue`s.
  if ! timeout 45 gh issue list --repo "noorinalabs/$repo" --state open \
         --limit 500 --json url,labels > "/tmp/issues-$repo.json" 2>/dev/null; then
    echo "WARN: gh issue list for $repo stalled/failed — skipping (audit continues)" >&2
    continue
  fi

  # url + the highest-numbered wave label, mapped to its expected Wave-field option:
  #   wave-{X}  -> W{X}      p{N}-wave-{M} -> P{N}W{M}      wave-x -> WX
  # Ties on multiple wave labels (rare, transitional) resolve to highest-numbered, matching
  # the issue body's "highest-numbered wins" rule. Issues with no wave label are omitted here.
  jq -r '.[]
         | .url as $u
         | ([.labels[].name
             | select(test("^wave-[0-9]+$") or test("^p[0-9]+-wave-[0-9]+$") or . == "wave-x")]
            | sort_by(if . == "wave-x" then -1 else (capture("(?<n>[0-9]+)$").n | tonumber) end)
            | last) as $lbl
         | select($lbl != null)
         | ($lbl
            | if . == "wave-x" then "WX"
              elif startswith("wave-") then "W" + ltrimstr("wave-")
              else (capture("p(?<n>[0-9]+)-wave-(?<m>[0-9]+)") | "P\(.n)W\(.m)")
              end) as $opt
         | "\($u)\t\($opt)"' "/tmp/issues-$repo.json" >> /tmp/issue-labels.tsv

  jq -r '.[].url' "/tmp/issues-$repo.json" >> /tmp/all-issue-urls.txt
  printf '  %s: done\n' "$repo"          # progress flush — unbuffered, per-repo
done

echo "Open issues across org: $(wc -l < /tmp/all-issue-urls.txt | tr -d ' ')"
echo "Issues carrying a wave label: $(wc -l < /tmp/issue-labels.tsv | tr -d ' ')"
```

`--limit 500` is intentional — the default 30 truncates silently per memory `feedback_gh_pr_edit_silent_noop` family. Adjust upward if any single repo crosses 500 open issues (unlikely but capture as an annunaki event if hit).

### 2. Fetch all items on project 2 (paginated — connections cap at 100)

**`items(first: …)` MUST be ≤ 100.** GitHub's GraphQL API caps every connection's
`first:` at 100 — `first: 500` errors with *"Requesting 500 records on the connection
exceeds the `first` limit of 100 records"* and returns **0 nodes**, which downstream
reads as "every issue is an orphan" (#888 defect 1; project 2 had 1394 items at the
P7W19 run, so this is not an edge case). Page with `first: 100` + a `$endCursor` cursor
var + `pageInfo { hasNextPage endCursor }`, let `gh api graphql --paginate` walk the
pages, then merge them with `jq -s`.

```bash
# `--paginate` re-runs the query with $endCursor for each page (it keys off
# `pageInfo.endCursor` — the cursor var MUST be named endCursor). It emits one JSON
# document per page on stdout; `jq -s` (Step below) slurps them into one array.
gh api graphql --paginate -f org=noorinalabs -F project=2 -f query='
query($org: String!, $project: Int!, $endCursor: String) {
  organization(login: $org) {
    projectV2(number: $project) {
      id
      items(first: 100, after: $endCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          content {
            __typename
            ... on Issue { url number repository { name } state }
            ... on PullRequest { url number repository { name } state }
          }
          fieldValues(first: 30) {
            nodes {
              __typename
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2SingleSelectField { name } }
              }
            }
          }
        }
      }
    }
  }
}' > /tmp/board-items-pages.json

# Merge the per-page documents into the single-object shape downstream jq expects:
# `.data.organization.projectV2.{id,items.nodes[]}`. `jq -s` slurps the page stream
# into an array; we flatten every page's nodes[] and keep page 0's project id (stable
# across pages). Works whether there were 1 page or 14.
jq -s '{ data: { organization: { projectV2: {
          id: .[0].data.organization.projectV2.id,
          items: { nodes: [ .[].data.organization.projectV2.items.nodes[] ] }
        } } } }' /tmp/board-items-pages.json > /tmp/board-items.json

echo "Board items fetched: $(jq '.data.organization.projectV2.items.nodes | length' /tmp/board-items.json)"
```

Save raw to `/tmp/` (or `.claude/scratch/`) for downstream parsing. A board-item count
of **0** here is a red flag (the over-cap symptom) — investigate before treating every
issue as an orphan, never run the apply steps off a zero-item fetch.

### 3. Detect orphans

```bash
# Build set of URLs on the board
BOARD_URLS=$(jq -r '.data.organization.projectV2.items.nodes[] | .content.url // empty' /tmp/board-items.json | sort -u)

# Set of URLs found in repo issue lists (collected to a file in Step 1)
ISSUE_URLS=$(sort -u /tmp/all-issue-urls.txt)

# Orphans = issues NOT on the board
ORPHANS=$(comm -23 <(echo "$ISSUE_URLS") <(echo "$BOARD_URLS"))

ORPHAN_COUNT=$(echo "$ORPHANS" | grep -c . || true)
echo "Orphan issues (in repo, missing from board): $ORPHAN_COUNT"
echo "$ORPHANS" | head -20
```

### 4. Detect Wave-field drift

Drift is computed **entirely in memory** by cross-referencing two maps already on disk —
no per-board-item `gh issue view` (#888 defect 2; the old loop was ~1394 serial network
calls). The expected Wave-field option per issue comes from `/tmp/issue-labels.tsv` (built
in Step 1 from the bulk `--json url,labels` fetch, grammar `wave-{X}` → `W{X}`,
`p{N}-wave-{M}` → `P{N}W{M}`, `wave-x` → `WX`); the board's actual Wave-field value comes
from the Step-2 GraphQL response. A single hash-join `awk` matches them by URL.

```bash
# Board side: url \t item_id \t current-Wave-field (from the merged Step-2 response).
jq -r '.data.organization.projectV2.items.nodes[]
       | select(.content.url != null)
       | "\(.content.url)\t\(.id)\t\(
           ([.fieldValues.nodes[]
             | select(.__typename == "ProjectV2ItemFieldSingleSelectValue")
             | select(.field.name == "Wave")
             | .name] | first // "(unset)")
         )"' /tmp/board-items.json > /tmp/board-wave-values.tsv

# In-memory hash join (NO network): first file builds url -> expected-option, second
# file (board) is streamed and annotated with the expected option (or "(unset)" when the
# issue carries no wave label / isn't an open issue — e.g. a PR or closed item).
# NB: the map array is `want`, NOT `exp` — `exp` is awk's built-in exponential fn and
# using it as an array name is a syntax error.
awk -F'\t' '
  NR==FNR { want[$1] = $2; next }                # /tmp/issue-labels.tsv : url -> W{X}
  { e = ($1 in want) ? want[$1] : "(unset)";
    print $1 "\t" $3 "\t" e }                     # url \t current_wave \t expected
' /tmp/issue-labels.tsv /tmp/board-wave-values.tsv > /tmp/board-drift-join.tsv

# Bucket the join rows (see #427 for the regression that motivated the split):
#   DRIFT      — actionable rows where a mutation will change board state.
#   NOOP_COUNT — no wave label AND Wave field already (unset). Functionally
#                `(unset) → (clear)`; the apply step's clearProjectV2ItemFieldValue is a
#                no-op against an already-cleared field. Counted separately so the operator
#                sees "audit is clean" even when the no-op equivalence class is non-empty;
#                MUST stay out of DRIFT so Step 7 doesn't emit redundant clear mutations and
#                Step 5's gate doesn't over-report.
# DRIFT rows carry REAL tab separators (`$'\t'`, not the literal backslash-t that a
# double-quoted "\t" would store) so Step 7's `while IFS=$'\t' read` actually splits them.
DRIFT=()
NOOP_COUNT=0
while IFS=$'\t' read -r url current_wave expected; do
  [ -n "$url" ] || continue
  if [ "$expected" != "(unset)" ]; then
    if [ "$current_wave" != "$expected" ]; then
      DRIFT+=("$url"$'\t'"$current_wave"$'\t'"$expected")
    fi
  elif [ "$current_wave" != "(unset)" ]; then
    # No wave label but Wave field is populated — should clear.
    DRIFT+=("$url"$'\t'"$current_wave"$'\t'"(clear)")
  else
    # No wave label AND Wave field already (unset) — already in desired state.
    NOOP_COUNT=$((NOOP_COUNT + 1))
  fi
done < /tmp/board-drift-join.tsv

echo "Actionable Wave-field drift:        ${#DRIFT[@]}"
echo "No-op equivalents (unset == clear): ${NOOP_COUNT}"
printf '%s\n' "${DRIFT[@]}" | head -30
```

"Multiple wave labels (rare, transitional)" — Step 1's `sort_by(... | tonumber) | last`
takes the highest-numbered, matching the issue body's "highest-numbered wins" rule.

### 5. Confirmation gate (mandatory)

Print the drift report and PAUSE for explicit user confirmation before mutating anything. Sample report shape:

```
Board audit results:
- Orphan issues:                       12 (in repo, missing from board)
- Actionable Wave-field drift:          7 (label and Wave field disagree; mutation will change state)
- No-op equivalents (unset == clear): 83 (functional duplicates; skipped by apply, shown for visibility)
- Missing Wave-field options:           0 (P3W9, P3W10 all present)

Orphan issues:
  https://github.com/noorinalabs/noorinalabs-main/issues/250
  ...

Actionable Wave-field drift:
  https://github.com/noorinalabs/noorinalabs-main/issues/123    P3W7 -> P3W9
  https://github.com/noorinalabs/noorinalabs-deploy/issues/87   P2W10 -> (clear)
  ...

Proceed with bulk-add and bulk-sync? [y/N]
```

The confirmation gate is keyed off the **actionable** drift count (`${#DRIFT[@]}`) plus the orphan count. No-op equivalents never appear under "Actionable Wave-field drift" and never gate the prompt — the apply step would skip them anyway, per the Step 4 forensic note.

The user MUST type `y` to proceed. Any other answer aborts with `BLOCK: user declined; no mutations made`.

### 6. Bulk-add orphans

```bash
# `while read` over the newline-list, NOT `for url in $ORPHANS` — zsh does not
# word-split an unquoted scalar, so the whole list would collapse into one bogus
# iteration (#759, same class as main#688). The `[ -n ]` guard preserves the
# zero-iteration-on-empty behaviour `for` gives when $ORPHANS is empty.
while IFS= read -r url; do
  [ -n "$url" ] || continue
  gh project item-add 2 --owner noorinalabs --url "$url" || \
    echo "WARN: failed to add $url"
done <<< "$ORPHANS"
```

Per memory `feedback_gh_pr_edit_silent_noop` family, `gh project item-add` can silently no-op — `gh` is being deprecated for project-classic operations (see `pull-requests.md § gh pr edit projects-classic deprecation`). If the bulk-add appears to succeed but the orphan count doesn't drop on the next audit run, fall back to the GraphQL `addProjectV2ItemById` mutation:

```bash
gh api graphql -f query='
mutation($project: ID!, $content: ID!) {
  addProjectV2ItemById(input: {projectId: $project, contentId: $content}) {
    item { id }
  }
}' -f project="$PROJECT_NODE_ID" -f content="$ISSUE_NODE_ID"
```

(Project and issue node IDs come from the step-2 query.)

### 7. Bulk-sync Wave field via GraphQL

For each drift row, run `updateProjectV2ItemFieldValue` with the option ID of the expected Wave value:

```bash
# One-time per session: fetch Wave-field option IDs.
gh api graphql -f query='
query {
  organization(login: "noorinalabs") {
    projectV2(number: 2) {
      field(name: "Wave") {
        ... on ProjectV2SingleSelectField {
          id
          options { id name }
        }
      }
    }
  }
}' > /tmp/wave-options.json

WAVE_FIELD_ID=$(jq -r '.data.organization.projectV2.field.id' /tmp/wave-options.json)
declare -A WAVE_OPTION_IDS
while IFS=$'\t' read -r name id; do
  # Unquoted subscript on assignment — zsh keeps quotes *inside* a subscript as
  # part of the key (`WAVE_OPTION_IDS["$name"]=` would store key `"P6W1"`, with
  # the quotes, so later `${WAVE_OPTION_IDS[$expected]}` lookups miss). Bash
  # strips them; the unquoted form is correct in both. Keys are wave names
  # (no spaces), so no word-split risk. (zsh-safety, #759)
  WAVE_OPTION_IDS[$name]=$id
done < <(jq -r '.data.organization.projectV2.field.options[] | "\(.name)\t\(.id)"' /tmp/wave-options.json)

# Project node ID — same response.
PROJECT_NODE_ID=$(jq -r '...path to project.id...' /tmp/board-items.json)

# Per drift row, set the Wave field.
while IFS=$'\t' read -r url current expected; do
  ITEM_ID=$(jq -r --arg u "$url" '.data.organization.projectV2.items.nodes[]
                                  | select(.content.url == $u) | .id' \
              /tmp/board-items.json)
  OPTION_ID="${WAVE_OPTION_IDS[$expected]:-}"

  if [ "$expected" = "(clear)" ]; then
    # Clear the field — pass null value.
    gh api graphql -f query='
mutation($project: ID!, $item: ID!, $field: ID!) {
  clearProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field}) {
    projectV2Item { id }
  }
}' -f project="$PROJECT_NODE_ID" -f item="$ITEM_ID" -f field="$WAVE_FIELD_ID" \
      || echo "WARN: clear failed for $url"
  elif [ -n "$OPTION_ID" ]; then
    gh api graphql -f query='
mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $project, itemId: $item, fieldId: $field,
    value: {singleSelectOptionId: $option}
  }) { projectV2Item { id } }
}' -f project="$PROJECT_NODE_ID" -f item="$ITEM_ID" \
   -f field="$WAVE_FIELD_ID" -f option="$OPTION_ID" \
      || echo "WARN: sync failed for $url"
  else
    echo "WARN: no Wave option for $expected; add it to project 2 (Settings → Fields → Wave → Add option) and rerun"
  fi
done <<< "$(printf '%s\n' "${DRIFT[@]}")"
```

### 8. Read-back verify

Re-run step 2 (board fetch) and re-compute step 3 (orphans) + step 4 (drift). Success criterion is **actionable drift == 0** AND **orphan count == 0** — the `NOOP_COUNT` bucket is expected to be non-zero on a healthy board (any issue intentionally left unlabeled lives here) and MUST NOT fail the read-back. If actionable drift or orphans are non-zero post-sync, surface to the user — the gh / GraphQL mutations may have silently no-op'd per the projects-classic deprecation family.

### 9. Report

```
Board audit complete:
- Orphans added: {count} (was {pre} → board now has {post} items)
- Wave fields synced: {count} (pre-actionable-drift: {pre} → post-actionable-drift: {post})
- No-op equivalents (unset == clear): {count} (informational; unchanged by sync)
- Missing Wave-field options: {list, if any}
- Read-back actionable drift remaining: {count}
```

If read-back actionable drift > 0, raise a warning and link to charter `pull-requests.md § gh pr edit projects-classic deprecation` (the same silent-no-op family). A non-zero no-op count is normal and does NOT warrant escalation.

## Acceptance criteria status (per main#199)

- [x] Skill `/board-audit` exists at `.claude/skills/board-audit/SKILL.md`.
- [x] Skill detects orphans across all 8 repos and project 2 (steps 1-3).
- [x] Skill detects wave label (`wave-{X}` / grandfathered `p{N}-wave-{M}`) / Wave-field drift (step 4).
- [x] Skill bulk-adds orphans with user confirmation (steps 5-6).
- [x] Skill bulk-syncs Wave field via GraphQL `updateProjectV2ItemFieldValue` mutation (step 7).
- [ ] Project 2 Wave-field options extended with `P2W10` + `P3W1`+ — **OWNER ACTION REQUIRED** (one-time per phase; not a code change).
- [x] Skill wired into `/wave-kickoff` and `/wave-retro` — added in this PR via SKILL.md cross-refs (callers update sequentially when next invoked).
- [x] Skill referenced from `/session-start` step 5 — added in this PR via SKILL.md cross-refs.
- [x] Charter `issues.md` (or `skills.md`) documents the labels-canonical rule — added in this PR via `skills.md § Cross-repo-status.json upsert pattern` companion section + a one-line note in `issues.md`.

## Out of scope (deliberately)

- Daily cron (issue body Option B) — deferred unless drift recurs after this skill ships.
- Auto-add via Hook 13 extension — Hook 13 catches in-session creates; extending it to cron-style cross-repo scans is the Option B path, deferred for the same reason.
- Wave-field option auto-creation — `gh project field-create` requires project-edit scope; one-time owner action.

## Skill-authoring notes — GitHub API access patterns

These are the footguns this skill hit (main#888, surfaced during the P7W19 `/board-audit`
run). Any skill that queries the GitHub GraphQL or REST APIs over a growing collection
should heed them:

- **GraphQL connections cap at 100 — always paginate.** Every GraphQL *connection*
  (`items`, `nodes`, `issues`, …) rejects `first:` > 100 with a hard error and returns
  zero rows. Use `first: 100` + `pageInfo { hasNextPage endCursor }` + a `$endCursor`
  query var + `gh api graphql --paginate`, then merge pages with `jq -s`. Never raise
  `first:` to "fit the dataset" — that is the over-cap regression (Step 2).
- **Derive in memory; don't loop network calls per row.** If you already have the data in
  a bulk response (or can get it in one `gh … --json` call per repo), cross-reference it
  in memory (an `awk`/`jq` hash join) rather than an `O(collection)` per-item `gh view`
  loop (Step 1 + Step 4).
- **Wrap each external call in a `timeout` and skip-and-warn.** A single stalled `gh`/HTTP
  call must not hang a whole multi-repo sweep; bound it and continue (Step 1).

A cheap regression lint for the first item ships at
[`.claude/lib/lint_skill_graphql_pagination.py`](../../lib/lint_skill_graphql_pagination.py):
it flags `first: <n≥100>` inside a `gh api graphql` block across `.claude/skills/**/*.md`.
Run it over the skills tree with:

```bash
python3 .claude/lib/lint_skill_graphql_pagination.py .claude/skills/**/*.md
```

Wiring it into pre-commit/CI is a deliberate follow-up (it is not yet a blocking gate); its
detection logic is covered by `.claude/lib/tests/test_lint_skill_graphql_pagination.py`.

## Promotion provenance

Memory `feedback_wave_planning_from_board.md` (2026-04-23 — the 37% drift discovery) → owner decision 2026-04-25 (labels canonical, Wave field derived) → this skill. Originating issue: main#199. Sibling-of: main#286 (hookify /wave-kickoff Steps 7+8, which depends on a current board); main#196 (/wave-scope, which depends on a current board). Class: same family as #286 — automation of cross-repo bookkeeping that decayed via in-band-repair patterns.
