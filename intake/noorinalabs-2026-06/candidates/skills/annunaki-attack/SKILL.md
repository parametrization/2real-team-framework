---
name: annunaki-attack
description: Analyze captured errors, propose automation (hooks/skills/charter), create issues, and implement fixes
---

Process the Annunaki error log, deduplicate errors, propose preventative automation, create GitHub issues, and implement fixes. This is the **action** counterpart to the `/annunaki` status viewer.

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Wave Lifecycle for the canonical skill order and preconditions.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149).

## When to run

- **Preferred:** during `/wave-retro` Step 7.6 — findings feed the retro's charter-change proposals (added P3W9 #344, 2026-05-11)
- Fallback: during `/wave-wrapup` Step 13 — same run-marker (`wave_${M}_annunaki_attack_ran_at`) prevents double-execution; whichever surface runs first wins
- Manually when the error log has accumulated enough entries to be worth processing
- Before planning the next wave — ensures error-driven improvements are captured as issues

## Instructions

### 1. Read and deduplicate the error log

Read **only genuine errors** via the shared reader (#625): it skips blank/corrupt lines AND benign-trace records (`posttooluse_dispatch` / `pretooluse_diagnostic`), which were 76% of the pre-#625 log and must never be classified as errors.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
# Genuine-error count (benign traces excluded):
python3 "$REPO_ROOT/.claude/lib/annunaki_parse.py" "$REPO_ROOT/.claude/annunaki/errors.jsonl" --count
# Iterate genuine errors in your analysis step:
python3 -c "import sys; sys.path.insert(0,'$REPO_ROOT/.claude/lib'); from annunaki_parse import iter_records; from pathlib import Path; [print(r) for r in iter_records(Path('$REPO_ROOT/.claude/annunaki/errors.jsonl'))]"
```

If the genuine-error count is 0 (file empty/missing, or it contains only benign traces), report "No errors to process" and exit. **Do NOT process `traces.jsonl`** — it is benign forensic output, gitignored, and ages out on its own.

**Deduplication rules:**
- Group errors by the **normalized command prefix** (first 2 tokens of the command, e.g., `git commit`, `npm run`, `gh pr`)
- Within each group, deduplicate by **error pattern** (the `matched_patterns` field)
- Keep the **most recent** occurrence of each unique error and a count of how many times it occurred
- Write the deduplicated list back:

```bash
# Back up the original
cp "$REPO_ROOT/.claude/annunaki/errors.jsonl" \
   "$REPO_ROOT/.claude/annunaki/errors.jsonl.bak.$(date +%Y%m%d%H%M%S)"

# Write deduplicated version (done in the analysis step below)
```

### 2. Classify each unique error

For each deduplicated error, classify it:

| Classification | Criteria | Proposed Fix |
|----------------|----------|--------------|
| **Hook candidate** | Error is preventable by validating input before the command runs (e.g., missing flags, wrong branch, bad arguments) | Create a PreToolUse hook |
| **Skill candidate** | Error occurs during a multi-step workflow that could be codified (e.g., repeated manual steps that fail) | Create a skill in `.claude/skills/` |
| **Charter update** | Error stems from a process gap or unclear convention | Update the relevant charter section |
| **One-off / noise** | Error is transient, environmental, or not actionable (e.g., network timeout, user typo) | Skip — remove from log |

**Preference order:** Hook > Skill > Charter update. Hooks are deterministic enforcement; skills are repeatable workflows; charter updates are documentation. Always prefer the most automated option.

### 3. Determine the target wave

```bash
# Check for current wave. Canonical label is the phase-agnostic `wave-{X}`
# (#810); legacy `p{N}-wave-{M}` is grandfathered — the `wave` search catches both.
gh label list --search "wave" --json name --limit 50
```

- If a wave is currently active (open issues with a wave label), use that wave label
- If no wave is active, determine the next wave label from the most recent closed wave
- Store the target wave label for issue creation

### 4. Create GitHub issues

For each non-noise error classification, create a GitHub issue:

```bash
gh issue create \
    --title "annunaki: {Brief description of the fix}" \
    --label "{target-wave-label},annunaki,{hook|skill|process}" \
    --body "$(cat <<'EOF'
## Source

Captured by Annunaki error monitor.

**Error pattern:** {pattern}
**Occurrences:** {count}
**Most recent:** {timestamp}
**Command:** `{command}`
**Error excerpt:**
```
{error_lines}
```

## Proposed Fix

**Type:** {Hook | Skill | Charter update}
**Description:** {What the fix should do}

## Acceptance Criteria

- [ ] Fix is implemented and tested
- [ ] Error pattern no longer triggers in normal operation
- [ ] If hook: registered in settings.json
- [ ] If skill: SKILL.md created with instructions
- [ ] If charter: section updated with rationale

---
*Filed by Annunaki error monitor*
EOF
)"
```

The `auto_add_issue_to_board.py` hook will automatically add it to the project board.

### 5. Implement fixes immediately

For each issue created, implement the fix following the standard team workflow:

**For hooks:**
1. Create the hook script in `.claude/hooks/`
2. Register it in `.claude/settings.json` under the appropriate event (PreToolUse or PostToolUse)
3. Test by simulating the error condition

**For skills:**
1. Create the skill directory in `.claude/skills/{name}/`
2. Write `SKILL.md` with full instructions
3. Verify the skill appears in the available skills list

**For charter updates:**
1. Edit the relevant charter file in `.claude/team/`
2. Add a clear rationale section explaining why the change was made

**Branch and PR conventions:**
- Branch: `Annunaki/{ISSUE_NUMBER}-{brief-description}`
- Commit identity: `git -c user.name="Annunaki" -c user.email="parametrization+Annunaki@gmail.com"`
- PR must reference the issue: `Closes #{ISSUE_NUMBER}`
- PR needs 2 reviewers per charter (request from Aino Virtanen as primary)

### 6. Clear processed errors

After all issues are created and fixes implemented, clear the processed errors:

```bash
# Keep only errors that were classified as noise (they'll naturally age out)
# Write a fresh errors.jsonl with only unprocessed entries (if any)
: > "$REPO_ROOT/.claude/annunaki/errors.jsonl"
```

### 7. Report

```
**Annunaki Attack Report**

**Errors processed:** {total_count}
**Deduplicated to:** {unique_count}
**Classified as noise:** {noise_count} (removed)

| # | Error Pattern | Classification | Issue | PR | Status |
|---|---------------|----------------|-------|----|--------|
| 1 | {pattern}     | Hook           | #{N}  | #{N} | {Implemented | Created} |
| 2 | {pattern}     | Skill          | #{N}  | #{N} | {Implemented | Created} |

**Error log:** Cleared after processing.
**Next step:** Issues are labeled for {wave_label} and added to the project board.
```

## Integration with wave-retro / wave-wrapup

This skill is called from **`/wave-retro` Step 7.6** (preferred surface, added P3W9 #344) or **`/wave-wrapup` Step 13** (fallback for retro-delayed cases). Both surfaces guard the call with a `wave_${M}_annunaki_attack_ran_at` run-marker in `cross-repo-status.json` so the attack runs at most once per wave.

When called from either surface:
- Use the current wave label (already known from context)
- If no errors to process, report "Annunaki: No errors captured this wave", **still write the run-marker**, and continue
- Fixes created here are included in the wave report totals (wrapup) and feed Step 7 charter-change proposals (retro)
- On completion, write `wave_${M}_annunaki_attack_ran_at = <ISO-8601 UTC timestamp>` to `cross-repo-status.json`

## What remains manual

- User approval is needed before merging PRs (standard charter rule)
- Complex fixes that span multiple repos need Program Director coordination
- If the proposed hook/skill conflicts with existing automation, flag for human review
