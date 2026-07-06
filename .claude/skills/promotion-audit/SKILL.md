---
name: promotion-audit
description: "Deterministic memory->charter->skill->hook promotion auditor — auto-promotes AUTO-tier candidates, files DECIDE-tier draft issues, writes a per-wave audit log."
args: Wave id (defaults to the current/last wave)
---

# Promotion Audit

Mechanically works the backlog the `suggest_generic_prompt` PostToolUse hook silently
accumulates in the generic-prompt ledger (`generic_prompt_tracker.py`): every project-local
`.claude/{memory,skills,hooks,lib,team/charter}/**` artifact touched since it was last
decided. This skill is the periodic, deterministic surface for that signal — there is no
per-edit nudge (that pattern decayed on an earlier per-edit `systemMessage` design and was
deliberately de-escalated to this silent-ledger-plus-periodic-audit shape).

**Enforcement hierarchy this pipeline serves:** `hook > skill > charter > memory`. A rule
that keeps needing to be restated belongs promoted one level up; this skill is the
mechanical check that promotion actually happens instead of staying a memory note forever.

> Config-driven + fail-open: reads `.claude/framework.config.json` via `jq`. All classification
> logic (`helpers.py`) is pure-function backed for byte-identical output — the plan for a given
> ledger + artifact set never varies between runs.

## Instructions

### 0. Resolve config + paths

```bash
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CFG="$REPO_ROOT/.claude/framework.config.json"
get() { jq -r "$1 // empty" "$CFG" 2>/dev/null; }   # fail-open dotted read

LEDGER_REL="$(get '.paths.generic_prompt_ledger')"; : "${LEDGER_REL:=.claude/generic_prompt_ledger.json}"
LEDGER="$REPO_ROOT/$LEDGER_REL"

# helpers.py: installed location first, framework-source checkout as fallback (mirrors
# wave-retro's lib-path resolution).
HELPERS="$REPO_ROOT/.claude/skills/promotion-audit/helpers.py"
[ -f "$HELPERS" ] || HELPERS="$REPO_ROOT/framework/assets/skills/promotion-audit/helpers.py"

# The wave under audit: the argument, else the current/last wave from lifecycle state.
LIB="$REPO_ROOT/.claude/lib"; [ -f "$LIB/lifecycle.py" ] || LIB="$REPO_ROOT/framework/assets/lib"
WAVE="{args}"; [ -n "$WAVE" ] || WAVE="$(python3 "$LIB/lifecycle.py" state show | jq -r '.current_wave // .last_completed_wave // empty')"
```

### 1. Read-only plan (always run this first)

```bash
python3 "$HELPERS" plan "$WAVE" --ledger "$LEDGER" --root "$REPO_ROOT"
```

Emits `{"auto": [...], "decide": [...], "done": [...]}` — the deterministic classification
of every ledger candidate:

- **`auto`** — the artifact's current content already carries BOTH halves of the charter's
  Promotion Pipeline Marker Convention (`team/charter/skills.md`): an
  `<!-- Promoted from memory... -->` comment AND a `**Promotion provenance:**` line. A human
  already did the promotion; nothing here is a judgment call.
- **`decide`** — pending, no markers found. Needs a human call.
- **`done`** — already decided (`genericized` or `skip`) in a prior pass. No action.

Review the plan. If `decide` is non-empty, skim each artifact briefly so the draft issues
Step 2 files make sense — this skill never guesses which side of genericize/skip a `decide`
candidate falls on.

### 2. Apply the plan

```bash
python3 "$HELPERS" run "$WAVE" --ledger "$LEDGER" --root "$REPO_ROOT" --label promotion-audit
```

This **always**:

- Mechanically flips every `auto`-tier ledger entry to `decision: genericized` (a local,
  reversible write — never gated; there is no judgment call to make when the markers are
  already present).
- Writes the per-wave audit log to `paths.promotion_audit_log/wave_<id>.md` (default
  `.claude/team/promotion_audit_log/wave_<id>.md`).

By **default it runs `--dry-run`**: `decide`-tier candidates get their draft-issue title/body
printed but nothing is filed. Review the printed bodies, then re-run with `--apply` to
actually file them:

```bash
python3 "$HELPERS" run "$WAVE" --ledger "$LEDGER" --root "$REPO_ROOT" --label promotion-audit --apply
```

### 3. Report

Summarize to the user: counts per tier, the audit-log path written, and (if `--apply` ran)
the issue numbers filed for `decide`-tier candidates. An empty ledger (`{"candidates": {}}`)
or a ledger with only `done` entries is a clean pass — say so plainly, do not manufacture
findings.

### 4. Finalizing a `decide` candidate

Once a human makes the genericize/skip call for a filed issue:

- **Genericize:** port the artifact into `framework/assets/**`, add the marker convention to
  the LIVE project-local copy (see `team/charter/skills.md`), then
  `python3 "$LIB/generic_prompt_tracker.py" record <artifact> --decision genericized --wave $WAVE --ledger "$LEDGER"`.
- **Skip:** `python3 "$LIB/generic_prompt_tracker.py" record <artifact> --decision skip --detail "<why>" --wave $WAVE --ledger "$LEDGER"`.

Either way, close the draft issue referencing the ledger update.
