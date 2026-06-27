---
name: wave-scope
description: Reconcile declared-vs-labeled wave scope between /wave-retro and /wave-kickoff — collect dispositions, fold in retro carry-forwards and memory must-includes, and refresh the meta-issue
args: Phase number, Wave number
---

Reconcile **declared scope** (next-wave meta-issue body) with **actual scope** (issues labeled `wave-{M}` across all repos) before kickoff. Surfaces drift that accumulated during the prior wave, folds in retro carry-forwards and memory-tracked must-includes, and produces a clean meta-issue + label set for `/wave-kickoff` to act on.

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Wave Lifecycle for the canonical skill order and preconditions.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149).

## When to use

- **Between `/wave-retro` (wave N done) and `/wave-kickoff` (wave N+1 launching).** Owner-confirmed cadence; running it inside an active wave is fine but lower-value.
- **Triggered by drift signal** — e.g. last-wave audit found multiple unscoped labels, or memory contains `W{N+1} must include` entries that weren't surfaced at retro.

## What this skill is NOT

- Not a branch-creation step — that's `/wave-kickoff` (Step 1, `gh api` ref-create).
- Not a kickoff-comment step — that's `/wave-kickoff`.
- Not an end-of-wave audit — that's `/wave-audit` (close orphans against merged PRs).

## Instructions

### 0. Inputs and prerequisites

Before invoking, the user provides:
- `{P}` — phase number for the next wave (e.g. `3`)
- `{M}` — the **global wave id** for the next wave. Since main#804 (Design B) wave ids are a single never-resetting monotonic counter, NOT a per-phase number — P6's first wave is `wave_16`, not `wave_1`. Do not hand-pick `{M}`; allocate it deterministically in Step 0.0 below. The human-friendly "Phase {P}, Wave {ordinal}" framing is preserved as the *display* fields `wave_{M}_phase` + `wave_{M}_phase_ordinal`; the bare `wave_{M}_*` KEY is always the global id.

The skill **either reconciles or authors** the next-wave meta-issue:
- If it already exists (drafted at the prior retro or before), Step 3 reads it and Step 11 refreshes the body.
- If it does not exist, Step 3 drafts a stub body containing the owner-set theme + carry-forwards + must-includes, files it, and proceeds. Step 11 then refreshes the body with the post-disposition structured scope, identical to the existing-meta path.

This was changed 2026-05-10 (P3W9 owner directive): `/wave-retro` does not currently author the next-wave meta as a guaranteed deliverable, so making `/wave-scope` STOP on missing-meta produced a chicken-and-egg gap. Authoring a stub here is cheap and the body is fully refreshed in Step 11 anyway.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
# Canonical wave label is the phase-agnostic `wave-{X}` (#810; {X} == global
# wave id). Legacy `p{N}-wave-{M}` labels on in-flight issues are grandfathered.
WAVE_LABEL="wave-{M}"
PRIOR_WAVE_LABEL="wave-$(({M} - 1))"  # for retro carry-forward cross-ref
```

### 0.0. Allocate the global wave id (main#804)

The wave id is a global monotonic counter (`global_wave_seq` in `cross-repo-status.json`). Allocate the next id and stamp the phase/ordinal display fields with `.claude/lib/wave_seq.py` — the value it prints is your `{M}` (run this before the steps below depend on it). This replaces the retired `/wave-start` § 5a per-phase reset: a never-reused id cannot collide, so there is nothing to reset.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
STATUS_FILE="$REPO_ROOT/cross-repo-status.json"

# Peek: print the next global wave id (no write) — this is your {M}.
python3 "$REPO_ROOT/.claude/lib/wave_seq.py" peek "$STATUS_FILE"

# Allocate: persist global_wave_seq + wave_{M}_phase + wave_{M}_phase_ordinal
# (ordinal auto-computed as 1 + waves already stamped to phase {P}). Run ONCE per wave.
python3 "$REPO_ROOT/.claude/lib/wave_seq.py" allocate "$STATUS_FILE" --phase {P} --write
```

The `--write` path goes through `upsert_status_keys.py`, so the compact-inline file shape is preserved and the rewrite is JSON-validated before AND after. The counter self-seeds above all historical per-phase wave numbers if `global_wave_seq` is absent. When operating on the `main` copy, run against the fetched content and fold the result into the PUT-contents write `/wave-kickoff` Step 1a uses.

### 0.5. Phase-review prerequisite + owner-set theme (MANDATORY)

**Two non-negotiable gates before proceeding past Step 0.5.**

**Gate A — `/phase-review` must have run in this session.** Without phase context, theme picking is reactive. Check the conversation transcript for a `/phase-review` invocation against phase `{P}`. If absent:

```
STOP. /phase-review must run before /wave-scope. Run:
   /phase-review {P}
Then re-run /wave-scope.
```

**Gate B — wave theme set by owner via dialogue.** The theme is NEVER inferred from carry-forwards, backlog tier ordering, or retro proposals alone. The orchestrator MUST:

1. Surface 2-3 candidate themes to the owner (informed by `/phase-review` output and the phase plan's remaining end-state criteria).
2. Wait for the owner to pick or hybridize.
3. Record the chosen theme in BOTH:
   - `cross-repo-status.json` → `wave_{M}_scope.theme = "<theme string>"`
   - The next-wave meta-issue body, top section, as a `## Theme` heading.

If the meta-issue body has no `## Theme` heading after this step, `/wave-scope` STOPS and refuses to proceed. The hook layer (or a future hook addition) should enforce this at meta-issue update time.

**Why this gate exists:** Phase 3 reset 2026-05-08 — 5 of 7 prior P3 waves had no recorded theme, and theme-picking had drifted to "whatever's most painful in retro carry-forwards." Owner directive: theme is a deliberate choice, not an emergent property.

### 1. Read previous-wave retro carry-forward

`/wave-retro` writes carry-forward items to two places:
- `.claude/team/feedback_log.md` — most recent `## Retrospective: Phase {P} Wave {M-1}` section, "Deferred to next wave" / "Carry-forward" subsections.
- `cross-repo-status.json` — `phase_{P}_carry_forwards` array (canonical structured list, post-W10).

```bash
# Structured carry-forwards (preferred — survives feedback_log churn)
jq -r '.phase_{P}_carry_forwards[]? | "\(.id)\t\(.type)\t\(.note)"' "$REPO_ROOT/cross-repo-status.json"

# Free-text carry-forwards (fallback / supplement)
awk '/^## Retrospective: Phase {P} Wave '$((M-1))'/,/^## /' "$REPO_ROOT/.claude/team/feedback_log.md" \
    | sed -n '/[Cc]arry.forward\|[Dd]efer/,/^### \|^## /p'
```

Collect into a `CARRY_FORWARDS=[]` working list. Each entry: `{id, source: "retro", type, note}`.

### 2. Read memory must-includes

Project memory may carry must-include directives keyed to the next wave (e.g. `W{N+1} must include user-service#63`). Scan the project memory dir:

```bash
# Memory is version-controlled in-repo since the #732 relocation (was the
# user-space ~/.claude/projects/<cwd>/memory/ path).
MEMORY_DIR="$(git rev-parse --show-toplevel)/.claude/memory"
# `|| true` because grep -l exits 1 when there are no matches, which is the
# normal case for waves with no filed must-includes — not an error.
MUST_INCLUDE_FILES=$(grep -l -i "W{M} must include\|wave-{M} must\|w{M}.must.include" "$MEMORY_DIR"/*.md 2>/dev/null || true)
[ -z "$MUST_INCLUDE_FILES" ] && echo "  (no must-includes filed for W{M})"
```

For each match, read the file and extract the issue references. Memory naming convention: `project_w{M}_*.md` (e.g. `project_w10_user_service_alembic.md` — the W10 example matched on the literal phrase `W10 must include` in MEMORY.md and the file body itself). Add to working list as `MUST_INCLUDES=[]`. Each entry: `{id, source: "memory", file, note}`.

If a referenced issue ID does not parse to a `repo#N` shape, surface to the user before proceeding — memories with vague references are a process gap that should be fixed at the source.

### 3. Locate-or-author next-wave meta-issue → declared scope

The meta-issue body + comments are the canonical declared scope. If no meta-issue exists yet, draft a stub body and file it — see § 0 for rationale.

```bash
# Find the meta-issue. Canonical pattern: title contains "Phase {P} Wave {M}" and is in noorinalabs-main.
META_ISSUE=$(gh issue list --repo noorinalabs/noorinalabs-main \
    --search "Phase {P} Wave {M} in:title" \
    --json number,title --jq '.[0].number')

if [ -z "$META_ISSUE" ] || [ "$META_ISSUE" = "null" ]; then
    # No meta-issue — author a stub. Body is full-refreshed in Step 11 after dispositions.
    # Include the owner-set theme (§ 0.5 Gate B) so the file passes the ## Theme heading check.
    cat > /tmp/wavescope-{M}-meta-stub.md <<EOF
## Theme

${WAVE_THEME}

## Scope

Reconciled by /wave-scope on $(date -u +%Y-%m-%d). Initial declared scope, carry-forwards, and must-includes folded in below; full structured scope written by Step 11.

## Carry-forwards from prior phase work

(populated by /wave-scope from \`phase_{P}_carry_forwards\` + retro free-text — Step 1 output)

## Memory must-includes

(populated by /wave-scope from project memory — Step 2 output; "(none filed)" when absent)

## References

- Phase plan: \`.claude/team/phases/phase-{P}.md\`
- Owner directive: this session's \`/phase-review\` and \`/wave-scope\`
EOF
    META_URL=$(gh issue create \
        --repo noorinalabs/noorinalabs-main \
        --title "Phase {P} Wave {M} — ${WAVE_THEME_SHORT}" \
        --body-file /tmp/wavescope-{M}-meta-stub.md \
        --label "meta-issue" --label "process" --label "phase-{P}" \
        --assignee "@me")
    META_ISSUE=$(echo "$META_URL" | grep -oE '[0-9]+$')
    echo "  authored W{M} meta-issue: noorinalabs-main#${META_ISSUE}"
fi

# Pull body + every comment (declared scope can land in either)
gh issue view "$META_ISSUE" --repo noorinalabs/noorinalabs-main --json body,comments \
    --jq '.body, (.comments[] | .body)' > /tmp/wavescope-{M}-declared.txt
```

**Meta-issue label set:** `meta-issue, process, phase-{P}` only. Do NOT add `wave-{M}` to the meta-issue itself — `phase-{P}` is the canonical bucket label for meta-issues per the W8 precedent (#331). The wave label `wave-{M}` is reserved for in-scope work items, not the meta.

**WAVE_THEME and WAVE_THEME_SHORT** are environment variables the orchestrator sets after Gate B's theme dialogue. `WAVE_THEME` is the full theme string written to `cross-repo-status.json`. `WAVE_THEME_SHORT` is a ~50-char title-friendly version for the issue title.

Extract every `repo#N` reference from the body and comments. Use a permissive regex to catch the common shapes:

```bash
grep -oE '\b(noorinalabs-[a-z-]+|main|deploy|isnad-graph|user-service|design-system|landing-page|data-acquisition|isnad-ingest-platform)#[0-9]+' \
    /tmp/wavescope-{M}-declared.txt | sort -u > /tmp/wavescope-{M}-declared-issues.txt
```

This is the `DECLARED=[]` set.

### 4. Query labeled scope across all repos

Use the canonical cross-repo audit primitive (charter `skills.md` § Wave Lifecycle — Open-Item Audit):

```bash
REPOS=(
    noorinalabs-main noorinalabs-isnad-graph noorinalabs-user-service
    noorinalabs-deploy noorinalabs-design-system noorinalabs-landing-page
    noorinalabs-data-acquisition noorinalabs-isnad-ingest-platform
)
> /tmp/wavescope-{M}-actual-issues.txt
for repo in "${REPOS[@]}"; do
    # 2>/dev/null suppresses "label not found" stderr — labels are per-repo so
    # not every repo will have $WAVE_LABEL until step 9 (or a prior /wave-start).
    # Non-zero exit on missing-label is normal and ignored.
    gh issue list --repo "noorinalabs/$repo" --state open --label "$WAVE_LABEL" \
        --json number,title,createdAt \
        --jq '.[] | "'"$repo"'#\(.number)\t\(.title)\t\(.createdAt)"' \
        2>/dev/null >> /tmp/wavescope-{M}-actual-issues.txt || true
done
echo "  Actual labeled: $(wc -l < /tmp/wavescope-{M}-actual-issues.txt) items across ${#REPOS[@]} repos"
```

This is the `ACTUAL=[]` set (with title and creation date).

### 5. Compute scope drift

The drift is `ACTUAL − DECLARED`. Two complementary deltas:

| Delta | Meaning | Default action |
|---|---|---|
| `ACTUAL − DECLARED` | Items labeled but not declared (silent label-drift) | Review per-item: keep, defer, strip-label, close |
| `DECLARED − ACTUAL` | Items declared but not labeled (forgot-to-tag) | Apply label after user confirms still-in-scope |
| `MUST_INCLUDES − ACTUAL` | Memory must-includes missing the wave label | Apply label (these are non-negotiable per their memory entries) |
| `CARRY_FORWARDS − ACTUAL` | Retro carry-forwards missing the wave label | Apply label after user confirms still applicable |

```bash
comm -23 <(cut -f1 /tmp/wavescope-{M}-actual-issues.txt | sort) \
         <(sort /tmp/wavescope-{M}-declared-issues.txt) > /tmp/wavescope-{M}-unscoped-drift.txt

comm -13 <(cut -f1 /tmp/wavescope-{M}-actual-issues.txt | sort) \
         <(sort /tmp/wavescope-{M}-declared-issues.txt) > /tmp/wavescope-{M}-unlabeled-declared.txt
```

### 6. Present unscoped items in repo-batched review

For each item in `ACTUAL − DECLARED`, group by repo and show:

```
**Unscoped Drift — `wave-{M}` labeled but not in meta-issue**

### noorinalabs-deploy ({count} items)

| Issue | Title | Created | Body excerpt |
|---|---|---|---|
| #N | ...  | YYYY-MM-DD | First 80 chars of body... |
| #N | ...  | YYYY-MM-DD | ... |

### noorinalabs-isnad-graph ({count} items)
...
```

Per-item body excerpt:

```bash
gh issue view {N} --repo "noorinalabs/{repo}" --json body --jq '.body | .[0:80]'
```

### 6.5. Premise-rot gate — verify named files/symbols exist at origin HEAD (#837)

P6W16 shipped two issues to execution on **rotted premises**: #705 targeted
`wave_key_reset.py`, a file #804 had already deleted, and #816's named root cause
was inverted. `/wave-scope` reconciled labels-vs-meta but never asserted that a
scoped issue's named *file / path / symbol* still exists at origin HEAD. This
gate closes that — it is the scope-time twin of [[feedback_pre_spawn_verify_file_exists]]
(spawn-time) and [[feedback_verify_diagnosis_before_delegating]].

The deterministic check is `.claude/lib/premise_check.py`. It auto-extracts
path-like tokens from each in-scope issue's body (backtick spans + a strict path
regex, so prose never produces a false STOP), then runs `git cat-file -e
<ref>:<path>` per path (and `git grep` per explicitly-declared symbol) against
the repo's origin HEAD. Verdicts: a path/symbol the ref can read but does not
contain → **STOP** (premise rot); a repo/ref that cannot be read at all (child
not cloned, origin not fetched) → **WARN** (an environment gap, deliberately not
a STOP); everything present → **OK**.

Run it over the actual labeled scope (Step 4 output). Fetch each in-scope repo's
`origin` first so the check resolves against real HEADs (an unfetched repo only
downgrades to WARN, never a false STOP):

```bash
PREMISE_CHECK="$REPO_ROOT/.claude/lib/premise_check.py"
PREMISE_ROWS="/tmp/wavescope-{M}-premise-rows.jsonl"
PREMISE_INPUT="/tmp/wavescope-{M}-premise-issues.json"

# Best-effort fetch of every in-scope repo so origin/main resolves locally.
for repo in "${REPOS[@]}"; do
    dir="$REPO_ROOT"
    [ "$repo" != "noorinalabs-main" ] && dir="$REPO_ROOT/$repo"
    [ -d "$dir/.git" ] && git -C "$dir" fetch -q origin 2>/dev/null || true
done

# Build the issues JSON from the actual labeled set (repo#N\ttitle\tcreatedAt).
: > "$PREMISE_ROWS"
while IFS="$(printf '\t')" read -r ref title created; do
    [ -z "$ref" ] && continue
    repo="${ref%%#*}"
    num="${ref##*#}"
    body=$(gh issue view "$num" --repo "noorinalabs/$repo" --json body --jq '.body' 2>/dev/null || true)
    jq -nc --arg ref "$ref" --arg repo "$repo" --arg body "$body" \
        '{ref:$ref, repo:$repo, body:$body}' >> "$PREMISE_ROWS"
done < /tmp/wavescope-{M}-actual-issues.txt
jq -s '.' "$PREMISE_ROWS" > "$PREMISE_INPUT"

python3 "$PREMISE_CHECK" check --issues "$PREMISE_INPUT" --ref origin/main
PREMISE_RC=$?
if [ "$PREMISE_RC" -ne 0 ]; then
    echo "STOP: premise-rot detected (see above). For each flagged issue, either"
    echo "  re-point it to the current file/symbol, re-scope it, or close it,"
    echo "  BEFORE collecting dispositions (Step 7). Re-run /wave-scope after."
    exit 1
fi
```

WARN-level rows (unverifiable) are surfaced but do not block; verify those
manually when the named repo could not be read. To declare a concrete symbol (or
a path the body phrasing is too loose to auto-extract) add explicit `paths` /
`symbols` arrays to that issue's row before the `jq -s` merge — see the module
docstring for the per-issue shape. `--warn-only` downgrades a STOP to advisory
for a dry run, but the gate is a hard STOP by default.

### 7. Collect dispositions per item (manual — owner judgment)

For each unscoped item, the owner picks one of:

| Disposition | Mechanic |
|---|---|
| `keep-in-w{M}` | Add to declared scope (step 11 will fold it into the meta-issue body) |
| `defer-to-w{M+1}` | Strip `wave-{M}` label, apply `wave-{M+1}` (create label if needed in step 9) |
| `strip-label` | Strip `wave-{M}` label, no other label change |
| `close-as-obsolete` | Close issue with a comment referencing the disposition |

Record dispositions in a working table. Do NOT apply any label changes until step 10. Do NOT close any issues until step 10.

This step is the orchestration's only blocking owner-judgment gate. Empty dispositions = STOP.

### 8. Verify must-includes and carry-forwards are labeled

For each entry in `MUST_INCLUDES` and `CARRY_FORWARDS`:

```bash
HAS_LABEL=$(gh issue view {N} --repo "noorinalabs/{repo}" --json labels \
    --jq '.labels[] | select(.name == "'"$WAVE_LABEL"'") | .name')
[ -z "$HAS_LABEL" ] && echo "MISSING LABEL: {repo}#{N}"
```

For each missing-label item, queue a label-apply for step 10.

If a `MUST_INCLUDES` entry is closed or non-existent, the source memory file is stale — surface to the user with a recommendation to remove or update the memory entry. Do NOT silently drop a must-include.

### 8.5. Tech-debt intake top-up (+20% of feature/bug scope) — MANDATORY every wave

**Standing owner policy (2026-06-09).** A hard cumulative TD-*ratio* gate (phase criterion #6) whipsaws as the backlog shrinks: the denominator collapses faster than real debt does, so a genuinely healthy small backlog can still read "over." Replace ratio-chasing with steady **intake** — every wave deliberately pulls in tech-debt work proportional to its feature/bug load.

After Step 7 has fixed the wave's feature + bug + security content, top it up with **tech-debt-only** issues equal to **20% of that content, rounded up**. If fewer qualifying TD issues exist than the target, add **all** of them — a shortfall here is a *good* signal (debt is genuinely low), never something to backfill with invented work. See [[feedback_td_intake_20pct_per_wave]].

**Last-wave-of-phase relaxation (owner 2026-06-16).** On the **final wave of a phase**, the +20% intake is a **floor, not a cap** — deliberately pull in a large chunk of tech-debt (well beyond 20%) to clean up before phase exit. The per-wave cap that prevents TD from crowding out feature work does **not** apply to a phase's last wave; clearing debt *is* the goal there. The `TARGET` below is the minimum; the orchestrator/owner sizes the actual chunk at scope time (`POOL > TARGET` is no longer a select-`TARGET`-only ceiling on the last wave — surface the whole pool and let the owner take as much as phase-exit warrants).

**1. Compute base + target.** Base = the post-Step-7 **intended** in-scope set that is NOT `tech-debt` and NOT `meta-issue` — the feature/bug/security items the owner just decided to keep. The query below counts items already carrying `$WAVE_LABEL`; some Step-7 keeps / must-includes / carry-forwards are not labeled until Step 10, so **add those not-yet-labeled non-TD keeps to `BASE`** before computing the target (otherwise the intake target undercounts the real scope).

```bash
REPOS=(
    noorinalabs-main noorinalabs-isnad-graph noorinalabs-user-service
    noorinalabs-deploy noorinalabs-design-system noorinalabs-landing-page
    noorinalabs-data-acquisition noorinalabs-isnad-ingest-platform
)
BASE=0
for repo in "${REPOS[@]}"; do
    n=$(gh issue list --repo "noorinalabs/$repo" --state open --label "$WAVE_LABEL" \
          --json number,labels \
          --jq '[.[] | select((.labels|map(.name)|index("tech-debt"))|not)
                     | select((.labels|map(.name)|index("meta-issue"))|not)] | length' 2>/dev/null || echo 0)
    BASE=$((BASE + n))
done
TARGET=$(( (BASE * 20 + 99) / 100 ))   # ceil(0.20 * BASE)
echo "feature/bug/security in-scope: $BASE  →  TD intake target: $TARGET"
```

**2. Build candidate pool** — open, `tech-debt`-labeled, NOT `meta-issue`, and NOT already carrying any `wave-*` label (un-scheduled debt), pooled across all repos. Oldest-first so long-lived debt drains first; the owner may reorder.

```bash
> /tmp/wavescope-{M}-td-pool.txt
for repo in "${REPOS[@]}"; do
    gh issue list --repo "noorinalabs/$repo" --state open --label tech-debt \
        --json number,title,labels,createdAt \
        --jq '.[] | select((.labels|map(.name)|index("meta-issue"))|not)
                  | select((.labels|map(.name)|any(startswith("p") and contains("-wave-")))|not)
                  | "\(.createdAt)\t'"$repo"'#\(.number)\t\(.title)"' \
        2>/dev/null >> /tmp/wavescope-{M}-td-pool.txt || true
done
sort /tmp/wavescope-{M}-td-pool.txt
POOL=$(wc -l < /tmp/wavescope-{M}-td-pool.txt)
echo "un-scheduled TD pool: $POOL  |  target: $TARGET"
```

**3. Select + confirm (owner-judgment gate, same as Step 7).**
- `POOL <= TARGET` → select **all** pool items. Report: `TD intake: <POOL> of <POOL> available — debt backlog below the 20% target (healthy)`.
- `POOL > TARGET` → surface the top `TARGET` oldest candidates to the owner for confirmation; the owner may swap in higher-priority debt. Final selection = `TARGET` items. **On the final wave of a phase, `TARGET` is a floor, not the cap** (see the relaxation note above) — surface the whole pool and let the owner pull in as much debt as phase-exit cleanup warrants.

This is a blocking owner-judgment gate exactly like Step 7 — present, don't auto-apply.

**4. Queue + fold in.** For each selected TD issue:
- queue a `$WAVE_LABEL` label-apply into the **Step 10** batch (do NOT apply here);
- add it to the `tier_3_tech_debt` array of `WAVE_SCOPE_STRUCTURED` as an assignment-row dict (§ 13.1), assigning implementer/reviewers from the **owning repo's** roster;
- add it to project board 2 (`gh project item-add 2 --owner noorinalabs --url <url>`).

Record `td_intake: <selected>/<target>` (and `td_pool: <POOL>`) for the Step 12 summary and Step 13 `wave_{M}_scope`.

**Interaction with phase criterion #6.** This step is the operational mechanism behind the TD goal. The cumulative-ratio reading stays *informational*, but the gate the team actually works to is "did the wave take its 20% intake," not a brittle ratio threshold — which avoids the small-backlog whipsaw the owner flagged. Cross-ref `phase-4.md` § criterion #6.

### 9. Create next-wave label (`wave-{M+1}`) if any defer dispositions

If any disposition in step 7 was `defer-to-w{M+1}`, ensure the label exists in every relevant repo:

```bash
# Global wave ids (main#804) are monotonic, NOT sequential-per-phase: the next
# wave id is the counter's peek value, not {M}+1. The label is the phase-agnostic
# `wave-{X}` form (main#810, the follow-up that retired the phase prefix).
NEXT_WAVE_ID=$(python3 "$REPO_ROOT/.claude/lib/wave_seq.py" peek "$REPO_ROOT/cross-repo-status.json")
NEXT_LABEL="wave-${NEXT_WAVE_ID}"
# Match the color/description of the current wave label for consistency
CURRENT_COLOR=$(gh label list --repo noorinalabs/noorinalabs-main --search "$WAVE_LABEL" --json color --jq '.[0].color')

# Build REPOS_WITH_DEFER as a bash/zsh ARRAY (e.g. REPOS_WITH_DEFER=(repo-a
# repo-b)) and iterate it quoted — `for repo in $REPOS_WITH_DEFER` would
# collapse a multi-repo string into one iteration under zsh (main#688), the
# same word-split trap as the other wave skills. The `"${arr[@]}"` form matches
# the `REPOS` iteration earlier in this skill.
for repo in "${REPOS_WITH_DEFER[@]}"; do
    gh label list --repo "noorinalabs/$repo" --search "$NEXT_LABEL" --json name --jq '.[].name' | grep -q "$NEXT_LABEL" || \
        gh label create "$NEXT_LABEL" --repo "noorinalabs/$repo" \
            --description "Phase {P} Wave ${NEXT_WAVE_ID} (global id)" --color "$CURRENT_COLOR"
done
```

### 10. Apply label churn in one batch per repo

Group all label edits per repo and apply with explicit user confirmation:

```
**Label changes about to apply** ({total} edits across {repos} repos)

### noorinalabs-deploy
- Add `wave-{M}` to: #A, #B
- Strip `wave-{M}` from: #C
- Strip `wave-{M}` AND add `wave-{M+1}` to: #D, #E
- Close as obsolete (with comment): #F

### noorinalabs-isnad-graph
...

Confirm to apply, or send back individual reversals.
```

After confirmation:

```bash
# Add label
gh issue edit {N} --repo "noorinalabs/{repo}" --add-label "$WAVE_LABEL"
# Strip label
gh issue edit {N} --repo "noorinalabs/{repo}" --remove-label "$WAVE_LABEL"
# Defer (strip current, add next)
gh issue edit {N} --repo "noorinalabs/{repo}" --remove-label "$WAVE_LABEL" --add-label "$NEXT_LABEL"
# Close as obsolete
gh issue close {N} --repo "noorinalabs/{repo}" --comment "Closed via /wave-scope: out-of-scope for $WAVE_LABEL and not warranted on its own — see meta-issue #$META_ISSUE"
```

### 11. Refresh meta-issue body

Rewrite the meta-issue body with the post-disposition scope. Categorize kept items into sections (the categories are owner-proposable; the skill suggests but does not decide):

- **Promotion-pathway core** — issues that drive the wave's primary theme
- **Precursors** — must-merge-first dependencies for the core
- **Memory must-includes** — items from step 2
- **Retro-mandated work** — items from step 1
- **Direct blockers** — anything blocking promotion of the wave's theme

Append a `## Deferred to W{M+1}` section listing the deferred items + a one-line reason each.

```bash
# Build new body via heredoc, then PATCH via gh api (gh issue edit --body has the same
# silent-no-op risk as gh pr edit per memory feedback_gh_pr_edit_silent_noop.md — use
# gh api PATCH and read-back-verify)
NEW_BODY=$(cat <<'EOF'
{post-disposition body}
EOF
)
echo "{\"body\": $(printf '%s' "$NEW_BODY" | jq -Rs .)}" > /tmp/wavescope-{M}-meta-body.json
gh api -X PATCH "repos/noorinalabs/noorinalabs-main/issues/$META_ISSUE" \
    --input /tmp/wavescope-{M}-meta-body.json --silent

# Read-back verify
READBACK=$(gh api "repos/noorinalabs/noorinalabs-main/issues/$META_ISSUE" --jq '.body | .[0:120]')
echo "$READBACK" | grep -q "Phase {P} Wave {M}" || echo "WARN: meta-issue body update may not have landed"
```

Do NOT delete the original body — copy it (or post the pre-update version as a comment) so the audit trail survives.

### 12. Emit summary

```
**Wave Scope: Phase {P} Wave {M}**

| Metric | Count |
|---|---|
| Declared (pre-scope) | N |
| Labeled actual (pre-scope) | M |
| Drift (actual − declared) | M − N |
| Kept in scope | K |
| Deferred to W{M+1} | D |
| Stripped (no longer in any wave) | S |
| Closed as obsolete | C |
| Memory must-includes folded in | MI |
| Retro carry-forwards folded in | CF |

**Final declared scope:** {final count} items, ready for `/wave-kickoff`.

**Label edits applied:** {edit count} across {repo count} repos.
**Meta-issue refreshed:** noorinalabs-main#$META_ISSUE
```

If any step surfaced a process gap (stale memory, missing meta-issue, vague reference), include a `**Process gaps surfaced**` section so the next retro can address them.

### 12.5. Validate implementer/reviewer names against per-repo rosters (#319)

If the wave-scope output includes an implementer/reviewer matrix (a per-repo mapping of `implementer` / `reviewer` / `reviewer_2` to team-member names), validate every declared name against the relevant roster BEFORE `/wave-kickoff` fan-out. Pre-#319 a stale alias like "Anya Volkov" (canonical: "Anya Kowalczyk") would propagate through scope and only surface at first-spawn time — P3W7 retro recorded TWO such substitutions in `wave_7_decisions.implementer_substitutions`.

**Resolution rules:**
- Per-repo entries (`noorinalabs-deploy`, `noorinalabs-isnad-graph`, …) → child-repo roster (`<repo>/.claude/team/roster/*.md`) UNION parent roster. This lets org-level coordinators (Aino, Nadia, Wanjiku, Santiago) fill child-repo slots without duplicating roster entries.
- Parent entries (`noorinalabs-main` or empty repo key) → parent-only roster (`.claude/team/roster/*.md`).
- Match is case-insensitive; trailing parenthetical role suffix (`Aino Virtanen (Standards & Quality Lead)`) is stripped before comparison.
- On miss: fuzzy-match via difflib SequenceMatcher; surface the top-3 closest matches to the operator.

**Invocation:**

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
VALIDATOR="$REPO_ROOT/.claude/skills/wave-scope/validate_matrix_names.py"

# The matrix JSON shape is {repo: {role: name, ...}, ...}. Build it from
# the scope file you composed (or extract from cross-repo-status.json's
# wave_{M}_scope tier_* entries if those have been written).
cat > /tmp/wave-{M}-matrix.json <<'EOF'
{
    "noorinalabs-isnad-graph": {
        "implementer": "Anya Kowalczyk",
        "reviewer": "Idris Yusuf",
        "reviewer_2": "Marisol Vega-Cruz"
    },
    "noorinalabs-deploy": {
        "implementer": "Bereket Tadesse",
        "reviewer": "Lucas Ferreira",
        "reviewer_2": "Aino Virtanen"
    }
}
EOF

python3 "$VALIDATOR" /tmp/wave-{M}-matrix.json
RC=$?
if [ $RC -ne 0 ]; then
    echo "STOP: resolve unresolved names before /wave-kickoff fan-out."
    echo "  If a substitution is intentional, document it in"
    echo "  cross-repo-status.json wave_{M}_decisions.implementer_substitutions"
    echo "  with rationale; then update the matrix and re-run /wave-scope."
    exit 1
fi
```

**Acceptance:**
- Every implementer / reviewer / reviewer_2 name in the scope matrix resolves to a canonical roster entry.
- Unresolved names are surfaced with suggested matches.
- Approved overrides are recorded under `wave_{M}_decisions.implementer_substitutions` in `cross-repo-status.json` with this shape:

```json
{
    "repo": "<repo-name>",
    "pr": "<repo>#<N>",
    "declared": "<matrix name>",
    "actual": "<canonical roster name>",
    "swapped_at": "<ISO-8601 UTC>",
    "rationale": "<why the substitution is correct>"
}
```

**Why this lives in `/wave-scope` not `/wave-kickoff`:** Step 0 of kickoff is a pre-flight CHECKLIST that the orchestrator confirms manually. By the time kickoff runs, scope is supposed to be settled. Validating names at scope-time means the matrix shape is already correct when kickoff reads it — the orchestrator never sees a "name not in roster" surface at fan-out time, only at scope-time review.

### 13. Write reconciliation timestamp + structured bookkeeping keys to `cross-repo-status.json`

This is what `/wave-kickoff` Steps 0a and 0 read to confirm the wave's scope was reconciled before kickoff AND to derive the per-repo iteration list. Write only on full success — if the run aborted at step 7 (no dispositions) or step 10 (label-churn confirmation declined), do NOT write.

The helper writes **four** keys (added P3W5 #273; structured-keys triplet added P3W6 #278 after `/wave-kickoff 3 6` STOPped on the missing keys):

| Key | Source | Type |
|---|---|---|
| `wave_{M}_scope_reconciled_at` | `$TS` — UTC ISO timestamp captured at write time | string |
| `wave_{M}_repos_in_scope` | the canonical 8-repo `REPOS` array from Step 4, optionally overridden by `WAVE_SCOPE_REPOS` (space-separated repo names) when a wave deliberately excludes a repo | array of strings |
| `wave_{M}_meta_issue` | `$META_ISSUE` from Step 3 | integer |
| `wave_{M}_scope` | from `WAVE_SCOPE_STRUCTURED` env var (a JSON object the orchestrator built from the meta-issue body — tier_*_*, deliberately_not_in_w*, concentration metrics, etc.) — falls back to a minimal `{"declared_refs": [...], "carry_forwards": [...], "must_includes": [...]}` shape derived from steps 1-3 if the env var is unset. **`tier_*_*` arrays MUST hold assignment-row dicts, not bare short-ref strings — see § 13.1.** | object |

**Why not raw jq:** `jq ... > tmp && mv` round-trips reformat the entire file from compact-inline (the deliberate shape used by `/wave-kickoff` and `/wave-start` for `wave_{N}_*` keys) to jq's default pretty form, doubling line count and producing a 500+ line cosmetic diff per run. P3W5 PR #276 review flagged this as load-bearing. The targeted upsert helper below preserves the existing shape — replace-in-place when the key exists (zero churn), insert-near-sibling when it doesn't (delta = 1 line per new key).

```bash
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# repos_in_scope: env-var override else canonical REPOS array from Step 4
if [ -n "${WAVE_SCOPE_REPOS:-}" ]; then
  REPOS_IN_SCOPE_JSON=$(printf '%s\n' $WAVE_SCOPE_REPOS | jq -Rnc '[inputs]')
else
  REPOS_IN_SCOPE_JSON=$(printf '%s\n' "${REPOS[@]}" | jq -Rnc '[inputs]')
fi

# Cross-check against meta-issue body (main#333 fix). The meta-issue's body
# is the canonical declared scope (see Step 11 framing). Without this check
# the JSON could ship with a different set than the meta-issue declares, and
# /wave-kickoff Step 0.5 pre-flight would fail on the divergence — exactly
# the P3W8 kickoff failure (canonical 8 repos, meta-issue body 7 repos,
# ingest-platform pre-flight failed missing branch + missing label).
META_BODY=$(gh issue view "$META_ISSUE" --repo noorinalabs/noorinalabs-main --json body --jq '.body')
# Two reference shapes observed in real meta-issue bodies:
#   1. Explicit cross-repo issue refs: `noorinalabs-isnad-graph#866`
#   2. Section-header bullets: `- noorinalabs-isnad-graph: #866, #867, ...`
# Both indicate the repo is in scope. The regex matches either suffix
# (`#N` for the explicit form OR `:` for the section-header form) and
# strips the suffix. Leading `(^|[^a-z])` prevents partial-word matches
# (e.g., `non-noorinalabs-X` won't match). main#333 fix.
ACTUAL_CHILDREN=$(echo "$META_BODY" \
  | grep -oE '(^|[^a-z])noorinalabs-[a-z][a-z0-9-]*(#[0-9]+|:)' \
  | sed -E 's/^[^a-z]*//; s/(#[0-9]+|:)$//' \
  | sort -u \
  | grep -v '^noorinalabs-main$' || true)
# Canonical = repos_in_scope minus main (the meta-issue lives in main and
# self-refs use `main#N` or bare `#N`; main is always implicitly in scope)
CANONICAL_CHILDREN=$(echo "$REPOS_IN_SCOPE_JSON" \
  | jq -r '.[] | select(. != "noorinalabs-main")' | sort)

EXTRA_IN_BODY=$(comm -23 \
  <(printf '%s\n' "$ACTUAL_CHILDREN") \
  <(printf '%s\n' "$CANONICAL_CHILDREN") | grep -v '^$' || true)
MISSING_FROM_BODY=$(comm -13 \
  <(printf '%s\n' "$ACTUAL_CHILDREN") \
  <(printf '%s\n' "$CANONICAL_CHILDREN") | grep -v '^$' || true)

if [ -n "$EXTRA_IN_BODY" ]; then
  echo "ERROR: meta-issue $META_ISSUE body references repo(s) NOT in canonical/override:"
  echo "$EXTRA_IN_BODY" | sed 's/^/  /'
  echo ""
  echo "Either (a) add the repo to WAVE_SCOPE_REPOS env var and re-run, or"
  echo "(b) remove the repo's references from the meta-issue body."
  echo "/wave-scope aborts so cross-repo-status.json does not ship with an"
  echo "inconsistent canonical truth — /wave-kickoff Step 0.5 would fail on it."
  exit 1
fi

if [ -n "$MISSING_FROM_BODY" ]; then
  # Body declares FEWER repos than canonical/override — deliberate scope reduction
  echo "INFO: meta-issue $META_ISSUE deliberately excludes child repo(s):"
  echo "$MISSING_FROM_BODY" | sed 's/^/  /'
  echo "Using meta-issue-derived scope (noorinalabs-main + body-referenced children)"
  echo "instead of the canonical/override array. This is the descope-from-meta path."
  # Rebuild REPOS_IN_SCOPE_JSON: main + body-derived children
  REPOS_IN_SCOPE_JSON=$(printf '%s\n' "noorinalabs-main" $ACTUAL_CHILDREN \
    | jq -Rnc '[inputs | select(. != "")]')
fi

# wave_{M}_scope: WAVE_SCOPE_STRUCTURED if owner pre-built it, else minimal derived shape
if [ -n "${WAVE_SCOPE_STRUCTURED:-}" ]; then
  # Validate it is a JSON object before passing through
  echo "$WAVE_SCOPE_STRUCTURED" | jq -e 'type == "object"' > /dev/null || {
    echo "ERROR: WAVE_SCOPE_STRUCTURED is not a JSON object"; exit 1;
  }
  SCOPE_JSON="$WAVE_SCOPE_STRUCTURED"
else
  # Minimal deterministic shape from earlier steps
  DECLARED_JSON=$(jq -Rnc '[inputs]' < /tmp/wavescope-{M}-declared-issues.txt)
  CF_JSON=$(printf '%s\n' "${CARRY_FORWARDS[@]:-}" | jq -Rnc '[inputs | select(. != "")]')
  MI_JSON=$(printf '%s\n' "${MUST_INCLUDES[@]:-}" | jq -Rnc '[inputs | select(. != "")]')
  SCOPE_JSON=$(jq -nc \
    --argjson d "$DECLARED_JSON" \
    --argjson c "$CF_JSON" \
    --argjson m "$MI_JSON" \
    '{declared_refs: $d, carry_forwards: $c, must_includes: $m}')
fi

# Stamp the owning phase into the scope object regardless of which branch built
# it. This is the per-phase phase-stamp that /wave-start § 5a reads to detect a
# same-number wave reused across phases (P4W4 ↔ P5W4) — the reliable signal that
# replaces the broken `current_phase` guard (main#683). `current_phase` tracks
# the LATEST phase, not the phase that owns these wave_{M}_* keys, so the stamp
# must live INSIDE the wave's own scope. Force-set (not default) so a stale
# WAVE_SCOPE_STRUCTURED carried over from a prior phase cannot poison it.
SCOPE_JSON=$(echo "$SCOPE_JSON" | jq -c --argjson p "{P}" '.phase = $p')

UPSERT_ARGS=(
  "wave_{M}_scope_reconciled_at=$(jq -nc --arg t "$TS" '$t')"
  "wave_{M}_repos_in_scope=$REPOS_IN_SCOPE_JSON"
  "wave_{M}_meta_issue=$META_ISSUE"
  "wave_{M}_scope=$SCOPE_JSON"
)

if [ -n "${SCOPE_RECONCILIATION_NOTE:-}" ]; then
  UPSERT_ARGS+=("wave_{M}_scope_reconciliation_note=$(jq -nc --arg n "$SCOPE_RECONCILIATION_NOTE" '$n')")
fi

python3 "$REPO_ROOT/.claude/lib/upsert_status_keys.py" \
  "$REPO_ROOT/cross-repo-status.json" \
  "${UPSERT_ARGS[@]}"

echo "  wave_{M}_scope_reconciled_at = $TS"
echo "  wave_{M}_repos_in_scope      = $REPOS_IN_SCOPE_JSON"
echo "  wave_{M}_meta_issue          = $META_ISSUE"
echo "  wave_{M}_scope               = $(echo "$SCOPE_JSON" | jq -c 'keys')"
```

The helper validates JSON pre- and post-write, replaces top-level keys in place when they already exist, and inserts new keys after the most-recent `wave_{N}_*` sibling line. Idempotent — re-running with identical values produces zero diff (re-confirmed via P3W6 #278 dry-run on a fictional `wave_99_*` shape).

**Why these four are the canonical bookkeeping shape.** `/wave-kickoff` Step 0 STOPs unconditionally without `wave_{M}_repos_in_scope` (it iterates the array for branch creation, label application, and kickoff comments). `wave_{M}_meta_issue` lets retro/wrapup skills find the meta-issue without re-querying GitHub. `wave_{M}_scope` is the structured payload retros and audits read for tier-by-tier breakdown. Writing all three at scope-reconciliation time eliminates the W5 silent-zero-write and W6 in-band-repair patterns observed before #278.

The optional `wave_{M}_scope_reconciliation_note` is for capturing edge cases (e.g., "no drift; no memory must-includes; manual run because skill not yet built"). Set `SCOPE_RECONCILIATION_NOTE` in the environment before invoking the helper if there is a non-trivial summary worth preserving for the next retro.

The companion read-side check is `/wave-kickoff` SKILL.md § 0a — it stops kickoff if this timestamp is missing or predates the prior wave's retro.

### 13.1. Tier-row shape — assignment-row dicts, not bare strings (#586)

The `tier_*_*` arrays inside `wave_{M}_scope` are consumed by the `post_wave_kickoff_comment.py` PostToolUse hook (Hook: kickoff-comment), which renders a per-issue charter-format kickoff comment when the wave label is applied. The hook's `find_assignment_row` matches an issue to its row by `id` / `ref`, then reads `implementer` / `reviewer` / `reviewer_2` / `priority` off that row to fill the comment.

Each tier entry MUST therefore be an **assignment-row dict**, not a bare short-ref string:

```json
{
  "id": "noorinalabs-main#322",
  "ref": "main#322",
  "implementer": "Wanjiku Mwangi",
  "reviewer": "Santiago Ferreira",
  "reviewer_2": "Aino Virtanen",
  "priority": "tech-debt"
}
```

- **`id`** — full repo name + `#<num>` (`noorinalabs-<repo>#<num>`). This is the hook's primary match key.
- **`ref`** — short form (`<repo>#<num>`, org prefix stripped). Convenience for human-readable scope review; the hook also matches on this.
- **`implementer` / `reviewer` / `reviewer_2`** — may be `null` at scope time if the slate is not yet decided; `/wave-kickoff` Step 0.4 fills them. The hook renders `(unassigned)` for any missing slot rather than blanking the bullet.
- **`priority`** — optional; defaults to `feature` in the rendered comment.

**Why dicts and not strings (the #586 regression).** `/wave-scope` historically wrote tier entries as plain short-ref strings (`["main#322", "deploy#363", …]`). The hook only matched dict rows, so every per-issue kickoff comment was silently skipped — this bit both W14 and W15 (zero auto-posted kickoff comments until the W15 orchestrator hand-converted the tiers, commit `3d2387c`). Emitting dict rows here is the source-of-truth fix; the hook additionally degrades gracefully on any residual plain-string entry (synthesizes a placeholder row, posts with `(unassigned)` slots) so the failure mode is a visible-and-backfillable comment, never a silent skip.

When building `WAVE_SCOPE_STRUCTURED`, construct each tier as an array of these dicts. If the implementer/reviewer matrix (§ 12.5) is already validated, fold its names directly into the rows so kickoff has nothing to backfill.

## Relationship to other wave skills

| Skill | Timing | Output |
|---|---|---|
| `/wave-retro` | End of wave N | Carry-forward list, deferred items, trust updates |
| **`/wave-scope`** | **Between waves** | **Declared-vs-labeled reconciled; meta-issue refreshed** |
| `/wave-start` | Start of wave N+1 | Park checkout on `main`, label setup, worktree cleanup |
| `/wave-kickoff` | Start of wave N+1 | Branch creation, issue assignment, kickoff comments, execution plan |
| `/wave-wrapup` | Near end of wave N | PR merge sequencing |
| `/wave-audit` | End of wave N | Close orphans against merged PRs |

`/wave-kickoff` currently assumes the meta-issue reflects reality. This skill makes that assumption true.

## What remains manual

- **Step 7** — disposition per unscoped item is owner judgment. The skill cannot decide keep-vs-defer-vs-close; it can only present the items and apply the result.
- **Step 11** — section categories on the refreshed meta-issue are owner judgment. The skill proposes; owner confirms.
- **Process-gap escalation** — when a memory must-include points to a closed/non-existent issue, the skill surfaces but does not auto-clean the memory file (that's a follow-up the owner triages).

## Idempotency

Re-running `/wave-scope` after an initial pass should:
- Find drift = 0 if labels match the refreshed meta-issue.
- Re-fold any new must-includes added to memory since the prior pass (cheap re-check).
- Be safe to abort at any step before step 10 — only step 10 (label churn) and step 11 (meta-issue PATCH) mutate state.
- Step 13's four `wave_{M}_*` JSON-write keys are upserted via `upsert_status_keys.py`: identical values produce zero diff, novel values produce 1 line per new key (plus replace-in-place when already present). This is the load-bearing shape #278 closed — no full-file reformat, no churn.

## Promotion provenance

- **Origin:** Conversation during W10 planning (2026-04-23) — owner walked through the 10-step pattern manually after the W10 scope-pass found 30 drift items and a missing must-include (`user-service#63`).
- **Promotion target:** skill (orchestration with one human-judgment gate; not a hook).
- **Issue:** noorinalabs-main#196.
