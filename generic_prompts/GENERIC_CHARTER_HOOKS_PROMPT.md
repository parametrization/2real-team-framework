# Generic Charter: Automated Enforcement Hooks

## Purpose

A template for governing **agent enforcement hooks** — the `PreToolUse` /
`PostToolUse` scripts that fire around tool calls (Bash, Edit, Write, Agent,
SendMessage, Skill, …) to enforce charter rules automatically. It covers the
catalog format, the dispatcher architecture, authorship requirements, the shared
audit protocol, and how hooks are shared across a parent + child repos.

The governing principle is the **enforcement hierarchy: hook > skill >
charter.** A charter rule with no automated backstop decays. When a rule is
violated repeatedly, promote it down the hierarchy toward a hook.

## Hook catalog format

Every hook gets a numbered entry with five fields:

- **What it automates** — the rule it enforces, in one line.
- **Augments** — which charter section it backstops.
- **Manual steps remaining** — what a human still does (often "none").
- **Emergency override** — how to bypass in an incident (usually: remove the
  entry from settings / the dispatcher list; re-add after).
- **Promotion provenance** — where the hook came from (see Authorship §6).

Representative hook classes worth having (rename to your stack):

- **Identity / config guards** — validate per-commit author identity; block
  config-write commands that would change global identity; block verification
  bypass flags (`--no-verify`-class).
- **CI / merge gates** — block a merge unless a non-author review exists; block a
  merge while any CI check is failing/pending; block a merge on an **empty**
  check rollup when the repo has a covering trigger (an empty rollup is an
  anomalous dropped-trigger, not green CI).
- **PR-hygiene gates** — block PR-create on a stale branch (behind base); block
  PR-create when a changed workflow file isn't covered by any trigger's path
  filter (a silent-CI-skip class); validate the review-comment format.
- **Issue / board automation** — validate labels exist before issue-create;
  auto-add new issues to the board (create-time); sync the board field on label
  edits (edit-time). Create-time and edit-time are **separate surfaces** — cover
  both.
- **Knowledge-base / consult nudges** — advise (don't block) when a reference
  consult was skipped before an edit, once the context it guarded is
  generated/always-current.
- **Footgun guards** — refuse a worktree self-delete (removing the cwd out from
  under the session); block a state-sensitive action after an unacknowledged
  tool error (the tool-error-soft-accept class).

For each, document the input language, the override, and whether it blocks or
warns.

## Dispatcher architecture

When several hooks share a matcher type (Bash, Agent, Edit, …), consolidate them
into a **single dispatcher** that dynamically loads individual hook modules
(e.g. via `importlib`), instead of registering N separate settings entries.

Key properties any dispatcher must preserve:
- Individual hook files remain **standalone, independently testable** modules.
- **One** settings entry per matcher type — the dispatcher is the only
  registered hook for that matcher.
- **Execution order preserved** — matches the registration order.
- **Fail-open on individual crash** — log a warning, continue to the next hook.
- **Short-circuit on block** — if any hook blocks, skip the rest.
- **Intercept `sys.exit`** from individual hooks so one can't terminate the
  dispatcher.

**Consolidation policy:** when hooks of one matcher type exceed **3**,
consolidate immediately — before adding the 4th. Don't wait for sprawl to become
a performance problem (each unconsolidated hook is a separate process spawn per
tool call).

## Shared helpers

Reusable primitives that multiple hooks consume live as **single-source
underscore-prefixed modules** (`_<helper>.py`) — marked internal, not hooks
themselves. Canonical examples:

- **Shell tokenizer** (`_shell_parse`) — tokenize, strip heredocs, iterate
  command segments, find a git/gh subcommand, extract `-c key=value` pairs. Any
  hook that detects a command shape MUST route through this rather than regexing
  the raw string — a private regex repeatedly mis-fires on heredoc bodies, code
  fences, and `--body-file` values, and a private `shlex.split` silently loses
  the tokenizer's fixes (line-continuation normalization, heredoc stripping).
- **Domain-shape parsers** (e.g. a label-change parser) — when ≥2 hooks need the
  same input shape, extract a shared helper rather than duplicate; duplication
  re-introduces the regression class the consolidation closed.
- **Consultation sentinel** — a cwd-keyed marker a skill writes synchronously,
  read by a transcript-reading hook as a second acceptance signal. Survives a
  transcript-flush race that affects worktree subagents. Namespace the marker by
  skill name; key the path by a hash of the absolute cwd; give it a TTL.

## Authorship requirements

Every new hook must meet these **at merge time** (partial compliance is a
moderate feedback event):

1. **Input-language spec in the module docstring** — `Fires on:` (event),
   `Matches:` (exact command/input shape as a grammar fragment), `Does NOT
   match:` (similar-looking inputs intentionally excluded, with examples), and
   `Flag pass-through:` (which flags are extracted and how). Forces the author to
   enumerate the negative space before shipping.
2. **Charter catalog entry** — the five-field entry above. No hook ships without
   one.
3. **Negative-match test coverage** — at least one input that *looks like a
   match but is intentionally excluded* (guards the substring-bug pattern).
4. **Dispatcher registration**, not a standalone settings entry, for any matcher
   that already has a dispatcher.
5. **Parser-fixture coverage** — every parsing hook has fixtures for all known
   input shapes. A new shape discovered in production requires a fixture-add
   **in the same commit** as the bug fix, pinning the shape so regressions
   surface in CI.
   - **5a. Segment-parser hooks** (those that split a command on shell
     separators) MUST cover all six separator classes: standard
     (`&&`/`||`/`;`/`|`), newline, subshell, control-flow body, line-continuation,
     and quoted regions — each with an allow case and a correctly-targeted block
     case. A hook that shipped quote- and control-flow-aware but lacked
     newline-as-separator coverage is the canonical gap this closes.
6. **Promotion provenance phrasing** — exactly one **backward-claim** sentence
   citing the source artifact by name (memory file / `/skill` / charter
   section), so an audit tool can trace what has already been promoted. Keep any
   **forward references** (sibling hooks, future design) in a *separate
   paragraph* — mixing them into the backward claim trips the audit's
   forward-reference filter and hides the real record.
7. **Command-parser invariant** — any hook parsing a CLI command (issue/PR/
   workflow/api) MUST (a) scope label/repo extraction to the actual flag VALUES
   via the shared tokenizer (never regex flag-shaped strings out of arbitrary
   text, never reimplement tokenization privately), and (b) resolve the
   flag-omitted ambient case (a command run *inside* the target repo with no
   `--repo`) from the cwd's origin, or log a skip and **fail open** — never
   silently drop the command, never fall through to a malformed default repo. A
   pytest gate should assert no in-scope hook calls `shlex.split` directly or
   carries an ad-hoc flag-capturing regex (the three sanctioned shared parsers
   are exempt — they *are* the tokenizer).

## Hook audit protocol

When auditing a repo's hook-ownership status (hook-owning vs dispatcher-style):
1. Fetch the **committed tree** (`git/trees/<head_sha>?recursive=1`) filtered to
   the hooks path.
2. Empty result → dispatcher-style; non-empty → hook-owning.
3. Filesystem enumeration (`ls`, `find`, SSH) is NOT a valid substitute — it
   includes untracked, worktree, and ignored files invisible to git.

Any classification claim must cite the tree (or `contents?ref=<sha>`) query it
ran. Reviewers reject claims sourced from local checkout or SSH.

## Hook sync across child repos

Shared hooks live in the **parent** repo's hooks tree **only**. Child repos
consume them **parent-canonical**: each child's settings registers each hook by
**absolute path into the parent tree** (or the parent dispatcher path for Bash).
This makes a new shared hook a one-line config change per child, not a
code-fan-out across repos.

**Required pattern:** hook source at the parent path only (no child `.py`
copies, including shared support files); each child's settings registers the
parent path under the right matcher.

**Anti-patterns:**
- **Copy-resident hooks** — copying `.py` files into a child and registering
  relative paths. Forces a per-repo PR per update; permanent drift with no
  sync check. If found during routine work, file a tracking issue — don't bundle
  the cleanup into an unrelated PR.
- **Empty child config** — a child that participates in hook-gated workflows but
  registers nothing. Hooks the parent enforces simply don't fire there. Audit at
  kickoff and file tech-debt for any in-scope empty repo.

**Reviewer enforcement** on a child settings PR: each entry uses an absolute
path into the parent tree (not relative); no new `.py` hooks added to the child;
matcher coverage matches the parent's for the equivalent surface.

**Caveats:** absolute-path style breaks if the child is cloned standalone
outside the parent (hooks silently don't invoke — the harness falls through to
allow); document this in any child that anticipates standalone cloning. A
machine-enforcement counterpart is a **sync-drift gate** — a CI job that fails if
a check CI enforces is not mirrored in the local pre-commit/pre-push config, so
"clean locally" stays a faithful predictor of green CI.

## Adaptation notes

- The hierarchy (hook > skill > charter), the dispatcher properties, the
  authorship requirements, and the audit protocol are the portable governance
  core. The specific hook list is illustrative — keep the *classes* and
  re-derive instances for your tooling.
- Hooks are stdlib-only and fail-open by default except where safety direction
  argues for fail-closed: when a guard can't auto-fix cleanly, **hard-block with
  a diagnostic** rather than allow-with-log. Reserve in-band override flags for
  cases where a logged bypass won't invite the rationalization the hook exists to
  prevent; otherwise make the override "edit the settings file" — annoying
  enough to be deliberate and visible in history.
