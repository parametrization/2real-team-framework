# Skills

Skills (`.claude/skills/<name>/SKILL.md`) are the team's runbooks — the procedural layer
between "a hook mechanically enforces it" and "a charter module documents the rule but
nothing runs it." Invoke one with `/<name>`. Several skills are backed by pure-function
Python helpers (`lifecycle.py`, `trust_signals.py`, `generic_prompt_tracker.py`, and a
skill-local `helpers.py`) so their arithmetic/classification is unit-tested directly rather
than trusted to prose.

## Promotion Pipeline Marker Convention

The `promotion-audit` skill (backed by `generic_prompt_tracker.py` and the
`suggest_generic_prompt` PostToolUse hook) mechanically audits the project's
`memory -> charter -> skill -> hook` promotion pipeline: a rule or pattern discovered in
project memory that proves durable should climb toward the enforcement hierarchy
`hook > skill > charter > memory` — not stay a memory note forever. This section is the
**authoritative marker shape** the pipeline parses; get it wrong and the auditor cannot tell
a completed promotion from an untouched one.

A completed promotion is marked directly on the **promoted-to** artifact (the charter
module, skill, or hook the memory/pattern was ported into) with BOTH of the following,
present together:

1. **A leading HTML comment** naming the memory source it was promoted from:

   ```markdown
   <!-- Promoted from memory: <memory-slug> (#<issue>) -->
   ```

   Placed as the first line of the promoted content (immediately after the module's own
   `#`/frontmatter header, if any). `<memory-slug>` is the `.claude/memory/<slug>.md`
   file the rule came from; `#<issue>` is the tracking issue for the promotion (omit the
   parenthetical only if there genuinely is none).

2. **A `Promotion provenance:` line**, bold-labeled, giving the human-readable why/when:

   ```markdown
   **Promotion provenance:** <one-line rationale> — promoted <ISO-8601 date>.
   ```

Both must be present for the auditor's **AUTO tier** to fire — `has_promotion_markers()` in
`promotion-audit/helpers.py` requires the marker comment AND the provenance line together;
either alone reads as an incomplete promotion and the artifact stays in the **DECIDE tier**
(a human call, surfaced via a filed draft issue) rather than being auto-flipped to
`genericized`.

### Example

A memory `reference_widget_timeout_backoff.md` that proves durable enough to become a
charter rule is promoted like this in `team/charter/pull-requests.md`:

```markdown
<!-- Promoted from memory: reference_widget_timeout_backoff (#142) -->
**Promotion provenance:** recurring retro finding across 3 waves — promoted 2026-05-01.

### Widget-timeout backoff

...the actual rule text...
```

### Why the ledger, not just the marker

The marker convention alone tells the auditor a promotion is *complete*; it does not tell it
which artifacts are still *pending* a decision. That durable, wave-scoped signal — every
project-local artifact touched since it was last decided — lives in the
**generic-prompt ledger** (`paths.generic_prompt_ledger`, default
`.claude/generic_prompt_ledger.json`), fed silently by the `suggest_generic_prompt`
PostToolUse hook and read by `/promotion-audit`. See `generic_prompt_tracker.py`'s module
docstring for the ledger shape.

## Writing a New Skill

- Frontmatter: `name`, `description` (shown in `/help` and the skill picker), optional `args`.
- Config-driven + fail-open: resolve `.claude/framework.config.json` via `jq` in Step 0 (see
  any existing skill for the pattern), never hard-code an owner/branch/label.
- If the skill's logic is more than a few lines of arithmetic/classification, back it with a
  pure-function-tested Python helper (a `lib/*.py` module for logic shared across skills, or
  a skill-local `helpers.py` for logic that is only ever this skill's) instead of encoding it
  in the markdown prose — mirrors `hooks.md`'s "hooks are the floor" principle one level up.
- Tests for a skill-local `helpers.py` live centrally under `framework/tests/` (2real's
  convention — see `test_trust_signals.py`, `test_lifecycle.py`), not in a `tests/` dir under
  the skill itself: `bootstrap.py` copies every file under `assets/skills/<name>/**`
  verbatim into every consumer's install, so a skill-local `tests/` would ship test bloat
  into every deployed repo.
