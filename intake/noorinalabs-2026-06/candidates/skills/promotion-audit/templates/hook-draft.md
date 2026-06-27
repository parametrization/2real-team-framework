## Goal

Promote the `/{{SKILL_NAME}}` skill to a Claude Code hook so that the behavior fires automatically at the appropriate tool event, eliminating the "I forgot to run it" failure mode.

**Source skill description:** {{SKILL_DESCRIPTION}}

## Why a hook

Per charter § Enforcement Hierarchy (hook > skill > charter), skills that operators invoke consistently across waves are candidates for hook promotion. `/promotion-audit` detected this skill crossed the invocation threshold. Hooks eliminate reliance on operator discipline for the behavior.

**Hook promotion is always DECIDE-tier** (per issue #152 decision D6) — never auto-applied — because hooks are security-sensitive and can block unrelated work if misdesigned. This issue exists so a human can review and ratify the design before implementation.

## Proposed hook design

### Trigger

Decide which tool event the hook should fire on:

- `PreToolUse Bash` — if the skill wraps a shell-command workflow
- `PreToolUse Edit | Write | NotebookEdit` — if the skill gates code changes
- `PreToolUse Agent` — if the skill gates team-member spawns
- `PostToolUse Bash` — if the skill is a post-command check/logger
- `SessionStart` / `Stop` — if the skill is a session-boundary action

### Input language (per W8 Hook Authorship Spec)

Draft the hook's module docstring with:

- **Fires on:** _fill in_
- **Matches:** _fill in with exact command/input shape as regex or grammar_
- **Does NOT match:** _fill in — superficially similar but excluded inputs_
- **Flag pass-through:** _fill in — which CLI flags extracted and how_

### Block vs warn

Decide whether the hook blocks (`exit 2`) or warns (`systemMessage`). Default: block, with emergency override documented.

### Negative-match tests

List at least 3 inputs that look like a match but should NOT fire — guard against the substring-bug pattern documented in W8 retro.

## Skill source for reference

The existing skill's body is reproduced below as a starting point for the hook's matcher spec:

<details>
<summary>`.claude/skills/{{SKILL_NAME}}/SKILL.md` (current content)</summary>

```markdown
{{SKILL_BODY}}
```

</details>

## Scope

- One PR adding `.claude/hooks/{{SKILL_NAME}}.py` and registering in `.claude/settings.json` (or the appropriate dispatcher if >3 hooks per matcher — see charter § Dispatcher Consolidation Policy).
- Negative-match test coverage in `.claude/hooks/tests/`.
- Charter entry in `.claude/team/charter/hooks.md` including a `**Promotion provenance:**` block referencing `/{{SKILL_NAME}}` and this issue number — required so `/promotion-audit` recognizes the promotion on future runs.
- Feedback-log entry documenting the signal evidence that triggered promotion.

## Acceptance criteria

- All four W8 Hook Authorship requirements met (input-language docstring, charter entry, negative-match tests, dispatcher registration).
- Hook tested against its own commit path — author must confirm no false-positive block on their own PR.
- PR has 2 reviewers per charter § Pull Requests.

## References

- Charter § Enforcement Hierarchy
- Charter § Hook Authorship Requirements (charter/hooks.md)
- `/promotion-audit` skill (the tool that filed this issue)
- Hook 15 (`enforce_librarian_consulted`, PR #153) — the worked-example reference for the full pipeline
