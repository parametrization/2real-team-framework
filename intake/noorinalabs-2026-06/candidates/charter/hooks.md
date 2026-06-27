# Automated Enforcement Hooks (Claude Code)

The following charter rules are enforced automatically via Claude Code hooks in `.claude/settings.json`. These are PreToolUse hooks that fire before Bash commands. Hook scripts live in `.claude/hooks/`.

## Hook 1: Validate Commit Identity (`validate_commit_identity.py`)

- **What it automates:** Commit Identity rules — validates that every `git commit` command includes `-c user.name=` and `-c user.email=` flags matching a roster member.
- **Parent+child roster merge (#112 part a):** When the target repo (either the repo hosting this hook, or the `cd <path>` target of a cross-repo commit) sits inside another git repo that itself has `.claude/team/roster.json`, the hook loads the parent roster and merges it under the child roster at load time. Child entries win on name collision. Walk-up is limited to ONE level to avoid false positives in nested `code/` trees. This lets org-level coordinators (e.g. Nadia.Khoury, Wanjiku, Santiago, Aino) commit in any child repo without duplicating their entries into every child `roster.json`.
- **Augments:** The [Commit Identity](commits.md) section. The manual rule still applies; this hook enforces it automatically.
- **Manual steps remaining:** When a new team member is hired, add their name and email to the appropriate `.claude/team/roster.json` — org-level coordinators go in `noorinalabs-main`'s roster, per-repo members go in that repo's roster.
- **Emergency override:** Remove or comment out the hook entry in `.claude/settings.json`. Re-add after the emergency.

## Hook 2: Block `--no-verify` (`block_no_verify.py`)

- **What it automates:** Prevents team members from using `--no-verify` on git commit, which bypasses pre-commit hooks.
- **Augments:** General code quality and CI enforcement rules. Pre-commit hooks are a required gate.
- **Manual steps remaining:** None — the hook is fully automated.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`. The user can also run git commands directly outside Claude Code.

## Hook 3: Block `git config` (`block_git_config.py`)

- **What it automates:** Commit Identity rules — blocks `git config` write commands to prevent modification of global/repo-level git config. Read-only operations (`--get`, `--list`, `-l`, etc.) are allowed for tooling compatibility.
- **Augments:** The charter rule "do NOT modify the global or repo-level git config."
- **Manual steps remaining:** None.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`.

## Hook 4: Auto-set `ENVIRONMENT=test` (`auto_set_env_test.py`)

- **What it automates:** Ensures `ENVIRONMENT=test` is set before any `pytest`, `uv run pytest`, or `make test` command. Prevents CI breaks caused by missing environment variable.
- **Augments:** Testing workflow. This is an automated safeguard, not replacing a prior manual rule.
- **Manual steps remaining:** None — the hook blocks and instructs the user to prepend `ENVIRONMENT=test`.
- **Skip conditions (#114):** Two short-circuits run before the pytest/make-test regex to prevent substring false-positives in GitHub API calls and body content:
  1. **`gh` subcommands** — if the effective argv[0] (after stripping leading `VAR=value` assignments) is `gh`, the hook skips. `gh` is a GitHub API client, never a test runner.
  2. **`--body` / `--body-file` flags** — if the command contains either flag, the hook skips. Structured bodies almost always contain user-supplied text mentioning `pytest` or `make test`. This skip is intentionally broad — a rare false negative on an exotic `--body`-using tool is cheaper than blocking every review/issue/comment that references pytest.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`.

## Hook 5: Validate Labels Before `gh issue create` (`validate_labels.py`)

- **What it automates:** GitHub Label Hygiene — validates that all `--label` values exist in the repository before `gh issue create` runs.
- **Augments:** The label hygiene section. The manual rule to run `gh label list` first is now enforced automatically.
- **Manual steps remaining:** None — the hook fetches labels and validates automatically.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`. If `gh label list` is unavailable (network issue), the hook allows the command with a warning.

## Hook 6: Validate Lockfile Paths (`validate_lockfile_paths.py`)

- **What it automates:** Blocks `git commit` if any staged `package-lock.json` contains `/tmp/` or `file:/` paths — local worktree artifacts that break CI.
- **Augments:** CI reliability. Session 4 had a Playwright PR with `/tmp/noorinalabs-design-system-0.0.1.tgz` baked into the lockfile.
- **Manual steps remaining:** None — the hook scans staged lockfiles automatically.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`.

## Hook 7: Validate PR Review (`validate_pr_review.py`)

- **What it automates:** Blocks `gh pr merge` unless the PR has at least one review from a non-author. Enforces the charter's peer review requirement.
- **Augments:** [Pull Requests](pull-requests.md) review requirements. Session 4 saw all PR reviews skipped across 3 waves.
- **Manual steps remaining:** None — the hook queries `gh pr view` for reviews automatically. Use `--admin` flag for emergency overrides.
- **Emergency override:** Pass `--admin` to `gh pr merge`, or remove the hook entry.

## Hook 8: Block `gh pr review` (`block_gh_pr_review.py`)

- **What it automates:** Blocks `gh pr review` commands (--approve, --request-changes, etc.) since all agents share one GitHub user and API-based reviews always fail with "cannot approve your own pull request".
- **Augments:** [Pull Requests](pull-requests.md) § Comment-Based Reviews. Redirects agents to use `gh pr comment` with the charter review format (Requestor/Requestee/RequestOrReplied fields).
- **Manual steps remaining:** None — the hook blocks and provides the correct format.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`.

## Hook 9: Validate Branch Freshness (`validate_branch_freshness.py`)

- **What it automates:** Blocks `gh pr create` if the feature branch is behind the base branch. Prevents merge conflicts from stale branches. Honors the `--repo OWNER/REPO` flag (#118 fix): when present, the freshness check uses the GitHub `compare` API against the target repo instead of the cwd-based `git fetch`/`git merge-base`. Without `--repo`, falls back to cwd behavior. Cross-repo PRs without `--head` are skipped (we cannot infer head reliably from cwd).
- **Augments:** [Branching](branching.md) workflow. Session 4 had RBAC and session hardening PRs conflict because neither was rebased.
- **Manual steps remaining:** None — the hook runs `git fetch` and `git merge-base --is-ancestor` (cwd path) or `gh api repos/.../compare/{base}...{head}` (cross-repo path) automatically.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`.

## Hook 10: Validate VPS_HOST (`validate_vps_host.py`)

- **What it automates:** Blocks `gh variable set VPS_HOST` if the value resolves to a Cloudflare IP range. Also warns if a hostname is used instead of a direct IP.
- **Augments:** Deployment safety. Session 4 had VPS_HOST set to a Cloudflare-proxied domain, causing SSH timeout on deploy.
- **Manual steps remaining:** None — the hook resolves the hostname and checks against known Cloudflare ranges.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`.

## Hook 11: Warn GHCR Image (`warn_ghcr_image.py`)

- **What it automates:** Warns (does not block) when `gh workflow run` triggers a deploy-related workflow and the expected GHCR image may not exist.
- **Augments:** Deployment safety. Session 4 had deploy-all triggered before the landing page GHCR image was built.
- **Manual steps remaining:** None — the hook checks `gh api` for the image. This is a warning only since deploy workflows sometimes build the image.
- **Emergency override:** Not needed (warning only). Remove the hook entry to suppress.

## Hook 12: Validate Wave Context (`validate_wave_context.py`)

- **What it automates:** Warns when agents are spawned without an active wave context in `cross-repo-status.json`. Ensures `/wave-kickoff` is run before agent work begins.
- **Augments:** [Agent Lifecycle](agents.md) wave management. Session 4 had the orchestrator bypass the team structure entirely.
- **Matcher:** `Agent` (not `Bash`) — fires on Agent tool calls.
- **Manual steps remaining:** Run `/wave-kickoff` to set the wave context. The hook is a warning, not a block.
- **Emergency override:** Not needed (warning only). Remove the hook entry to suppress.

## Bash Hook Dispatcher Architecture <!-- promotion-target: none -->
All Bash-matcher hooks are consolidated into a **single dispatcher** (`bash_dispatcher.py`) that dynamically loads individual hook modules via `importlib.util`. This reduces process spawns from N (one per hook) to 1 per Bash tool call.

**Key design decisions:**
- Individual hook files remain as standalone modules — testable independently, loaded dynamically by the dispatcher
- `bash_dispatcher.py` is the **only** Bash-matcher entry in `.claude/settings.json`
- Hook execution order is preserved (matches the order hooks are registered in the dispatcher)
- **Fail-open:** If an individual hook crashes, the dispatcher logs a warning and continues — it does not block the command
- **Short-circuit on block:** If any hook returns a blocking result, subsequent hooks are skipped
- `sys.exit` calls from individual hooks are intercepted via mock to prevent the dispatcher from terminating

**Adding a new Bash hook:**
1. Create the hook script in `.claude/hooks/` as a standalone Python module
2. Register it in `bash_dispatcher.py`'s hook list
3. Do NOT add a separate entry in `.claude/settings.json` — the dispatcher handles all Bash hooks

**Why:** Phase 2 Wave 1 PR #73 consolidated 12 individual Bash-matcher hooks into this pattern, reducing process spawns from 12 to 1 per Bash call.

## Dispatcher Consolidation Policy <!-- promotion-target: none -->
When hooks sharing the same matcher type (Bash, Agent, SendMessage, etc.) accumulate beyond **3**, they must be consolidated into a dispatcher immediately. Do not wait for hook sprawl to become a performance problem.

**Threshold:** >3 hooks of the same matcher type triggers mandatory consolidation.

**Pattern to follow:** The Bash hook dispatcher (`bash_dispatcher.py`) is the reference implementation. Key properties any new dispatcher must preserve:
- Dynamic module loading via `importlib.util` — individual hooks remain standalone and independently testable
- Single entry in `.claude/settings.json` per matcher type — the dispatcher is the only registered hook
- Fail-open on individual hook crashes — log a warning, continue to the next hook
- Short-circuit on block — if any hook returns a blocking result, skip subsequent hooks
- Intercept `sys.exit` calls from individual hooks to prevent dispatcher termination

**When to apply:**
- Before adding a 4th hook of the same matcher type, consolidate the existing hooks into a dispatcher first
- When reviewing PRs that add new hooks, verify the hook count and flag if consolidation is needed
- This applies to all matcher types: Bash, Agent, SendMessage, PreToolUse, PostToolUse

**Why:** Phase 2 Wave 1 accumulated 12 Bash-matcher hooks before consolidation (PR #73). Each hook spawned a separate Python process per Bash call — 12 process spawns for every command. Consolidation reduced this to 1. Apply the pattern proactively to avoid repeating this accumulation.

## Hook 13: Auto-Add Issues to Project Board (`auto_add_issue_to_board.py`)

- **What it automates:** After `gh issue create` runs, detects the new issue URL in stdout and runs `gh project item-add` to add it to the Cross-Repo Wave Plan board (project #2).
- **Type:** PostToolUse (advisory, non-blocking).
- **Augments:** Cross-Repo Wave Plan § Board Maintenance Rules — "New issues created during a wave must be added to the board immediately."
- **Manual steps remaining:** None — fully automated.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`.

## Hook 14: Validate PR CI Status (`validate_pr_ci_status.py`)

- **What it automates:** Blocks `gh pr merge` when any CI check on the PR is failing, cancelled, timed out, or requires action. Pending checks also block unless the user passes `--auto` (let GitHub auto-merge on green). Queries `gh pr view --json statusCheckRollup`; supports the `--repo` flag.
- **Augments:** [Pull Requests](pull-requests.md) "green CI before merge" requirement. Phase 2 Wave 7 merged multiple PRs with red `security-audit`, `e2e`, and `test_migrate_users.py` checks despite the charter rule. Per the enforcement-hierarchy principle (hook > skill > charter), a repeatedly violated charter rule becomes a hook.
- **Manual steps remaining:** None — the hook queries `gh pr view` for the check rollup automatically.
- **Emergency override:** Pass `--admin` to `gh pr merge`, or remove the `validate_pr_ci_status` entry from the dispatcher hook list.
- **P2W9 retro findings (2026-04-22):** Hook 14 is registered in noorinalabs-main but is NOT synced to child repos. `gh pr merge` on child-repo PRs (deploy#146 in particular) bypassed the CI check because the dispatcher in the child repo doesn't list this hook. **Action:** sync Hook 14 to all 7 child-repo dispatchers following the same pattern as #112 part (b) for `validate_commit_identity`. Additionally, the hook's behavior on **pending** checks may have been too permissive during P2W9 — the mid-CI-run merge window allowed main#178 to merge before FAILURE conclusions materialized. Tighten the pending-check semantics to block mid-run merges unless `--auto` is passed to hand off to GitHub's auto-merge. Tracking issues: noorinalabs-main#182 (main), noorinalabs-deploy#148 (cross-repo sync).
- **NEUTRAL allowlist (resolves #219, P3W4 T5):** GitHub's Checks API uses `NEUTRAL` to mean "the check has no opinion" — historically treated as pass. Chromatic (the dominant visual-regression service for Storybook-based component libraries) returns `NEUTRAL` on snapshots-pending-review, so a vanilla `NEUTRAL → pass` interpretation would let a PR merge while visual-regression review is still pending. The hook now consults a `_NEUTRAL_PENDING_CHECK_PREFIXES` allowlist (case-insensitive `startswith` on the CheckRun's display name) to decide: a name that starts with an allowlisted prefix treats `NEUTRAL` as **pending**, all other names preserve the prior `NEUTRAL → pass` behavior. Initial allowlist: `("chromatic",)`. Prefix matching (broadened from the v1 exact-string set per #262) catches multi-step Chromatic check-name shapes like `Chromatic / Visual` or `chromatic-visual` that GitHub Actions surfaces once design-system wires Chromatic into `storybook.yml`. Add new entries when a CI service uses `NEUTRAL` to mean "review pending" rather than "no opinion." Surfaced by Luciana Ferreyra (design-system QA) on design-system#61 review, comment-id 4335373566.

## Hook 15: Enforce Librarian Consulted (`enforce_librarian_consulted.py`)

- **ADVISORY as of [#857](https://github.com/noorinalabs/noorinalabs-main/issues/857) (P6W17, parent [#820](https://github.com/noorinalabs/noorinalabs-main/issues/820) / C×T2 decision):** this hook was originally a **hard block** (deny the edit, exit 2 — #150). It is now **advisory**: when `/ontology-librarian` was not consulted it emits a `systemMessage` warning and **allows the edit to proceed (exit 0, always)**. Rationale: the block existed to guarantee the agent had loaded *current ontology context* — chiefly the **structural** layer (module/service topology). That layer is now **generated** (committed `ontology/structural/`, owned generator [#855](https://github.com/noorinalabs/noorinalabs-main/issues/855)) and therefore *always-current-by-regeneration* rather than hand-resolved and potentially stale, so the staleness the block defended against no longer exists for it (cf. `feedback_safety_direction_over_ux_friction`: soften a guard only once the safety it provided is demonstrably redundant — it is here). The hand-curated **semantic overlay** (`domain.yaml`/`services.yaml`/`conventions.md`/`*.md`) still benefits from consulting the librarian, so the advisory nudge remains — it reminds without gating.
- **What it does:** On `Edit`, `Write`, and `NotebookEdit`, checks whether `/ontology-librarian` was consulted earlier in the session. Reads the session transcript (`transcript_path` from the Claude Code hook input) and scans for either a user slash-command invocation of `/ontology-librarian` or an assistant `Skill` tool_use with `skill: "ontology-librarian"`. As of [#169](https://github.com/noorinalabs/noorinalabs-main/issues/169) the hook also accepts a cwd-keyed sentinel file at `<cwd>/.claude/.consulted/ontology-librarian/<sha1(cwd)>.marker` written by the librarian skill, with a 1-hour TTL. Either signal (transcript OR fresh sentinel) suppresses the advisory; the sentinel fallback covers a transcript-flush race that affected worktree subagents. Known limitation: a subagent sharing its parent's cwd (non-worktree, rare) would be covered by the parent's sentinel — worktree subagents, the dominant case, each have distinct cwds and distinct sentinels. If neither signal is present, the hook prints the advisory `systemMessage` and the edit proceeds anyway.
- **Augments:** [CLAUDE.md § Ontology — "Before any code changes (recommended)"](../../../CLAUDE.md). The charter guidance "Every agent — orchestrator, team member, or one-off — SHOULD run `/ontology-librarian {topic}` before making code changes" was honored inconsistently across Phase 2 Wave 9 (3 of 4 code-change PRs skipped it — deploy#125 kafka GID, deploy#130 obs fix, user-service#67 OAuth GET), which originally motivated a hard hook ([#150](https://github.com/noorinalabs/noorinalabs-main/issues/150)). With the structural layer now generated (#855), the consult is no longer a hard precondition — the hook backstops the guidance as an advisory reminder.
- **Matcher:** `Edit`, `Write`, `NotebookEdit` (not `Bash`) — direct registration in `settings.json` since these are the first PreToolUse hooks on these matchers. When a 4th hook is added to any of these matchers, consolidate via the dispatcher pattern (see § Dispatcher Consolidation Policy).
- **Scope of advisory:** `/tmp/**` (out-of-repo scratch), `~/.claude/**` (user config), `**/memory/*.md` and `MEMORY.md` (project memory), `.claude/annunaki/*` (hook-managed log) never warn. All other paths — including `.claude/team/feedback_log.md`, charter files, and source code — get the advisory when the librarian was not consulted. None of these block: the advisory is a non-fatal `systemMessage` only.
- **Manual steps remaining:** None required (the hook never blocks). Best practice: run `/ontology-librarian {topic}` once per session before code edits to load semantic context and suppress the advisory.
- **Disabling the advisory:** Remove the three `enforce_librarian_consulted.py` entries (Edit/Write/NotebookEdit matchers) from `.claude/settings.json` if the reminder is unwanted. (Since #857 there is nothing to "override" — the hook is non-blocking — so this is a noise-suppression knob, not an escape hatch.)
- **Promotion provenance:** First end-to-end execution of the memory → charter → hook promotion pattern ratified by the owner on 2026-04-19 (original hard-block form). Softened to advisory by #857 (#820 / C×T2 decision) once the structural layer became generated/always-current. Rule lived in CLAUDE.md § Ontology (charter-equivalent location) since W7. Worked example referenced by the `/promotion-audit` skill design.

## Hook 16: Refuse Worktree Self-Delete (`no_worktree_self_delete.py`)

- **What it automates:** Blocks `git worktree remove <path>` when the caller's current directory (`input_data["cwd"]`, the shell's actual `$PWD` at tool-call time) equals `<path>` or is a descendant of it. Resolves both sides via `os.path.realpath` so symlinks do not defeat the check. Splits chained commands on `&&`, `||`, `;`, and `|` so `cd /safe && git worktree remove <cwd>` still blocks — the `cd` is a plan the shell has not yet executed when the hook fires. Strips leading `FOO=bar` env-var assignments and skips global `git -C <dir>` / `-c k=v` options plus `remove`-level flags (`-f`, `--force`) during parse so the `<path>` argument is extracted reliably. Prefix-confusion is avoided via `Path.relative_to` semantics rather than string `startswith`, so `/foo/wt-a-sibling` is not treated as descending from `/foo/wt-a`. The block message names a safe cwd to move to (best-guess via `git rev-parse --show-superproject-working-tree` / `--show-toplevel` run with the parent of the target worktree as cwd; generic fallback if those fail).
- **Augments:** Worktree hygiene. Wave-8 retro item 5 noted: "Worktree-self-delete is a real operator risk... Guard: prefix with explicit `cd <project-root>` to a known-existing path, or detect cwd ancestry before removing." The guard was noted but not implemented; the same footgun fired again and forced a session restart during cleanup. Per the enforcement-hierarchy principle (hook > skill > charter), a caller-side convention that decayed becomes a hook. See issue [#173](https://github.com/noorinalabs/noorinalabs-main/issues/173).
- **Matcher:** `Bash` via the dispatcher (`no_worktree_self_delete` entry in `dispatcher.py`'s `_BASH_HOOKS` list). Cheap filesystem-only check, ordered near the top of the list.
- **Manual steps remaining:** None — the hook fires automatically on every Bash call that contains a `git worktree remove` segment. Skills that remove worktrees (`/wave-wrapup`, cleanup flows) should still follow the safe-cd pattern (defense in depth) — the hook is the backstop, not the only line of defense.
- **Emergency override:** Remove the `no_worktree_self_delete` entry from `dispatcher.py`'s `_BASH_HOOKS` list. Re-add after the emergency. There is no in-band override flag — the purpose of the hook is to prevent a specific operator footgun, so an inline bypass would defeat the point.

## Hook 17: Validate Wave Audit (`validate_wave_audit.py`)

- **What it automates:** Blocks PreToolUse `Skill` calls for `wave-wrapup`, `wave-retro`, and `handoff` when the active wave has open items in any org repo AND the skill's `args` payload does not contain an explicit carry-forward marker. Reads the active wave labels from `cross-repo-status.json` (`current_wave` + `phase` → BOTH the new phase-agnostic `wave-{X}` AND the grandfathered `p{N}-wave-{M}`, main#810), runs `gh issue list --repo noorinalabs/<repo> --state open --label <label> --json number` across the 8 org repos for each label form (charter `skills.md` § Audit command), UNIONS the issue numbers per repo (an issue carrying either form counts once), sums the result, and gates accordingly. Carry-forward markers recognized: `Carry-forward:` or `Carry forward:` inline (case-insensitive), `## Carry-forward` markdown heading, or `#<N> → <destination>` arrow patterns naming a non-numeric destination. All infrastructure failures (missing `gh`, network errors, malformed `cross-repo-status.json`, missing wave label) fail OPEN with a system warning so a transient infra hiccup never blocks legitimate work — the hook only blocks when it is *certain* the wave has open items the author hasn't acknowledged.
- **Merge-ready-PR exemption (issue [#664](https://github.com/noorinalabs/noorinalabs-main/issues/664), owner-adopted P4W7 retro 2026-06-13):** an open wave-labeled issue does NOT count toward the blocking total if it has a **merge-ready PR targeting the wave branch** `deployments/phase-<P>/wave-<M>` (derived from the same `cross-repo-status.json` phase/wave that yields the label). This fixes the `/wave-wrapup` chicken-and-egg where the wave's own work-issues only close as part of wrapup's merge steps, yet the gate counted them and forced a merge+close-first then re-run. "Merge-ready" is defined narrowly to guard against false-exempt (acceptance #3): the PR is **OPEN + not draft**, its **base is exactly the wave branch** (`gh pr list --base <wave-branch>`; an arbitrary PR into `main` or another branch does NOT qualify), `mergeable == "MERGEABLE"` (no conflicts; `UNKNOWN` treated as not-ready), **every status check is green** (all `SUCCESS`/`NEUTRAL`/`SKIPPED`; any failing or *pending* check → not-ready), and the PR **declares it closes the issue** via a closing keyword in its body/title (`Closes #N` / `Fixes #N` / `Resolves #N` + conjugations, case-insensitive) — **not** a bare `#N` mention. (Linkage is parsed from the PR body/title rather than the structured `closingIssuesReferences` API field because GitHub only registers closing references for PRs based on the *default* branch — that field is always empty for wave-branch PRs, the same root cause as `Closes #N` not auto-closing on wave-branch merges; cf. `feedback_wave_branch_issue_close`.) If the wave branch can't be derived or any PR query fails, NO exemption is applied — the count stays strict (fail toward blocking, never false-exempt). Per repo the audit lists wave-branch PRs once (`gh pr list --base <wave-branch> --json …,body,title`) and subtracts each merge-ready PR's declared-closes issue set before counting.
- **Augments:** [`charter/skills.md`](skills.md) § Wave Lifecycle — Open-Item Audit. The charter rule is the source of truth for *what* counts as a valid carry-forward acknowledgment; this hook is the enforcement layer. Promotion provenance: memory `feedback_honest_audit_over_conclusion_claim` (2026-04-22) → charter `skills.md` § Wave Lifecycle (PR #193) → this hook (issue [#195](https://github.com/noorinalabs/noorinalabs-main/issues/195)). Second worked example of the memory→charter→hook promotion pipeline ratified 2026-04-19 (Hook 15 was the first).
- **Matcher:** `Skill` (new matcher type — first hook of this kind in the codebase). Direct registration in `settings.json` per dispatcher consolidation policy (§ Dispatcher Consolidation Policy: consolidate at 4+ hooks of the same matcher; this is the only Skill-matcher hook).
- **Manual steps remaining:** None when the gate fires — the operator must either close the open items, OR add a carry-forward block to the skill `args`. The charter rule still mandates the same discipline for manually-authored handoffs and retros that don't go through skills (those are out of scope for the hook; a separate Stop-hook scan was considered and deferred per the design comment on #195).
- **Emergency override:** Remove the `Skill` matcher entry from `.claude/settings.json`. There is no in-band override flag — the purpose of the hook is to break the "this one's fine, just say concluded" rationalization that put the P2W9 incident on owner's desk. Matches Hook 15's *original* (pre-#857) no-in-band-override stance; Hook 17 remains a hard block — Hook 15 itself was softened to advisory by #857, but the design principle it set still governs genuinely-blocking gates like this one.
- **Deliberate-non-implementation of `--ack-incomplete`:** A `--ack-incomplete '<reason>'` in-band override flag was proposed during design ratification on #195 alongside the `--carry-forward` marker path. Only `--carry-forward` was implemented in PR #218; `--ack-incomplete` was deliberately omitted. Rationale: any per-session bypass — even one that demands a logged reason — invites the same rationalization fail-mode the hook exists to prevent. Hook 15 precedent (no in-band override on its original hard-block form; Hook 15 was later softened to advisory by #857, but the no-override design principle stands for blocking gates). Settings.json-removal is the right granularity for "I genuinely need to bypass" — annoying enough to be deliberate, visible in commit history. Adding a flag for a hypothetical need violates the pre-emptive-surface-area rule. Re-open conditions (file a comment on [#220](https://github.com/noorinalabs/noorinalabs-main/issues/220) with evidence if any surface): (1) real escape-hatch need during a security incident — capture the timeline; (2) repeat operator action of "edit settings.json to bypass + put back" within a 30-day window — vote-with-feet signal; (3) pattern of carry-forward markers added purely to silence the gate without genuine carry-forward intent — theater-marker rationalization. Issue [#220](https://github.com/noorinalabs/noorinalabs-main/issues/220) stays OPEN as the canonical watch-list anchor for these conditions (mirrors how phase-end-state meta-issues stay open while their dependencies close). PD ratification: 2026-04-28.

## Hook 18: Validate Edit Completion (`validate_edit_completion.py`)

- **What it automates:** Two-phase gate that closes the **tool-error-soft-accept** failure class. PostToolUse on Edit/Write/NotebookEdit records `is_error: true` responses to a session-scoped sentinel at `<repo_root>/.claude/.edit-error-sentinel/<session-id>.jsonl` (gitignored). PreToolUse on subsequent state-sensitive actions (Edit/Write/NotebookEdit on the same path, SendMessage, or Bash matching `git commit` / `gh pr comment` / `gh issue comment`) reads the sentinel and blocks unless the error has been acknowledged via one of: a `Read` of the errored path, a Bash `cat`/`head`/`tail`/`grep`/`less`/`ls`/`wc` of the path, OR a SendMessage / comment text containing both the path AND the literal string `edit-error acknowledged`. Acknowledged entries are pruned atomically.
- **Augments:** P2W10 retro-mandated discipline. Two independent W10 instances (Marcia walkback on prompt-drafting Edit error; Bereket Contract-revert false-status report despite 5 consecutive Edit `is_error: true`). Same tool, same failure class, same blast-radius. Per `feedback_enforcement_hierarchy.md`, charter rule "always verify edits landed" decays without enforcement; this is the hook-tier enforcement.
- **Matcher:** Multi-matcher — `Bash` via `dispatcher.py` (`_BASH_HOOKS` list); `Edit` / `Write` / `NotebookEdit` direct PreToolUse + PostToolUse registration in `settings.json`; `SendMessage` direct PreToolUse registration in `settings.json` (alongside `block_shutdown_without_retro.py`). The dispatcher routes Bash via the hook's `check(input_data)` function; the other matchers go through `main()` which dispatches on `hook_event_name` to either `_post_tool_use` (record-on-error) or `_pre_tool_use_blocks` (gate-if-unacked).
- **Manual steps remaining:** When a state-sensitive action blocks, the agent acknowledges via Read / Bash-verb / explicit-marker on the errored path. Charter `pull-requests.md` § Trust the Artifact, Not the Framing already prescribes verify-before-claim discipline; this hook is the enforcement layer for that prescription on the Edit-tool surface.
- **Emergency override:** Pass an explicit `edit-error acknowledged` marker in the next SendMessage / comment for the path (in-band escape hatch for recovery edits). Or remove the hook entry from `dispatcher.py`'s `_BASH_HOOKS` list AND the `settings.json` registrations. The marker path is the recommended emergency path because it preserves the audit trail.
- **Promotion provenance:** P2W10 retro (2026-04-23 — Khoury framing: "if it keeps surfacing, hook candidate — something that blocks next Write/Edit if prior Edit returned an error-that-wasn't-explicitly-handled"). Filed as [#198](https://github.com/noorinalabs/noorinalabs-main/issues/198), promoted to hook in P3W4 T5.

## Hook 19: Validate Workflow Paths Coverage (`validate_workflow_paths_coverage.py`)

- **What it automates:** Blocks `gh pr create` / `gh pr ready` when the PR diff modifies any `.github/workflows/*.yml` file that is NOT covered by any base-branch workflow's `on.pull_request.paths:` filter (or by a base workflow with `on.pull_request:` and no `paths:` filter). Closes the **workflow-file orphan** failure class — a PR can land workflow changes that GitHub silently skips CI on, producing `statusCheckRollup: []` + `mergeStateStatus: CLEAN` (which `validate_pr_ci_status` only blocks on FAILED, not EMPTY). Companion to Hook 9 / `validate_pr_ci_status` at the trigger-graph layer.
- **Coverage logic:** Builds the union of `on.pull_request.paths:` patterns across all base-branch workflows; tracks whether ANY base workflow has `on.pull_request:` without a `paths:` filter (covers everything). For each `.github/workflows/**` file in the PR diff, checks against the union. Path matching uses `fnmatch` with `**` glob expansion. Workflows with `paths-ignore:` only (no `paths:`) are conservatively treated as no-paths-filter coverage (over-allows slightly; safer side for the orphan-blocking goal).
- **Augments:** Charter `pull-requests.md § CI Workflow `pull_request` Triggers Must Cover Wave Branches` (sibling at the wave-branch coverage layer; this hook covers the workflow-file-orphan layer). Both rules together close the trigger-gap class surfaced in P2W10 via deploy#153 + user-service#80/#81.
- **Matcher:** `Bash` via `dispatcher.py` (`_BASH_HOOKS` list, ordered after `validate_branch_freshness` since both are PR-create gates and this one fetches base-branch workflow YAMLs — the network calls land late in the chain).
- **Manual steps remaining:** When the hook blocks, the PR author has three remediation paths (named in the block message): (a) precursor PR adds `'.github/workflows/**'` to a base workflow's paths filter — recommended; (b) add a workflow with `on.pull_request:` and no `paths:` filter (covers everything including future workflow files); (c) `--admin` at merge time if the change genuinely needs no CI (rare).
- **Emergency override:** Remove the `validate_workflow_paths_coverage` entry from `dispatcher.py`'s `_BASH_HOOKS` list. There is no in-band override flag — the purpose of the hook is to prevent silent CI skipping, so an inline bypass would defeat the point.
- **Out of scope for v1:** Net-zero infra-revert orphan detection (`statusCheckRollup: []` + non-base HEAD) — requires re-running GitHub's paths-filter evaluator at hook time. Filed as follow-up. Cross-repo reusable-workflow inheritance (`workflow_call`/`uses:`) — reviewer responsibility.
- **Promotion provenance:** P2W10 retro-candidate (2026-04-24, deploy#153 76d7d7f orphan). Filed as [#203](https://github.com/noorinalabs/noorinalabs-main/issues/203) sibling of [#200](https://github.com/noorinalabs/noorinalabs-main/issues/200) — different layer of the same trigger-gap class. Promoted to hook in P3W4 T5.

## Hook 20: Validate Wave-Label Evidence (`validate_wave_label_evidence.py`)

- **What it automates:** Blocks `gh issue create --label '...p<N>-wave-<M>...'` and `gh issue edit <NUM> --add-label '...p<N>-wave-<M>...'` when the issue body cites file paths that 404 at BOTH `origin/main` AND the corresponding `origin/deployments/phase-<N>/wave-<M>` branch. Closes the **stale-path wave-labeling** failure class — three independent W8 occurrences (deploy#276 already-resolved, isnad-graph#866-870 hook-files-don't-exist, PR#871 stale-worktree audit-re-framing) consumed implementer-spawn cycles before manual review caught the divergence.
- **Verification logic:** Tokenizes the command via shlex; identifies wave-label application; resolves issue body from `--body` / `--body-file` for create or via `gh issue view --json body` for edit. Regex-extracts cited Python file paths (`.claude/**/*.py` and `src/**/*.py` and `tests/**/*.py` shapes, with optional `noorinalabs-<repo>/` prefix for cross-repo refs). For each cited path, runs `gh api repos/<owner>/<repo>/contents/<path>?ref=<ref>` against `main` AND the wave branch. If EVERY cited path 404s at BOTH refs, blocks; if at least one verifies, allows.
- **Override mechanism:** Add `Origin-Verification: <reason>` to the issue body before applying the wave label. Three legitimate shapes: (a) `Origin-Verification: <path> exists at <ref>` (path exists at non-standard ref), (b) `Origin-Verification: not-applicable — <reason>` (pure-policy issue with no real file claim, e.g., proposed-new-hook), (c) `Origin-Verification: <other rationale>`. The override line is regex-matched (`^Origin-Verification:\s*\S`), so any substantive value after the prefix counts.
- **Augments:** Charter `pull-requests.md § Origin > Local Clone for "Still-Has-X" File-Content Claims` (the file-content discipline this hook gates at wave-label-application time). Three-strikes-in-one-wave argues for hook-tier per `feedback_enforcement_hierarchy.md`: not isolated incident, not edge case, recurring root-cause across distinct repos and roles.
- **Matcher:** `Bash` via `dispatcher.py` (`_BASH_HOOKS` list, ordered after `validate_labels` since both gate `gh issue create` and this one fetches contents via `gh api` — the network calls land late in the chain).
- **Manual steps remaining:** When the hook blocks, the operator has three remediation paths (named in the block message): (a) verify the path EXISTS at origin and update the body to cite a real path; (b) add `Origin-Verification: not-applicable` for legitimately path-less or proposed-new-artifact issues; (c) add `Origin-Verification: <path> exists at <ref>` if the path exists at a non-standard ref.
- **Emergency override:** Remove the `validate_wave_label_evidence` entry from `dispatcher.py`'s `_BASH_HOOKS` list. There is no in-band override flag beyond the `Origin-Verification:` body line, which is the discipline-preserving path.
- **Out of scope for v1:** `gh project item-add` matcher (W8 instances of stale-path issues hit the labeling surface before the project-add surface; covering label-time is the higher-leverage gate). Cited-issue freshness ("any cited issue # must be OPEN or noted as `closed-resolved-by-X`") — heavier hook surface; deferred to retro for now. Both filed as follow-ups against this hook.
- **Promotion provenance:** Three-occurrence W8 pattern (2026-05-09 audit, see [#337](https://github.com/noorinalabs/noorinalabs-main/issues/337) for full provenance chain). Source memory family: `feedback_origin_over_local_for_still_has_claims.md` (SUPERSEDED 2026-05-10 by charter `pull-requests.md`), `feedback_pre_spawn_brief_verified_at_head.md`, `feedback_verify_diagnosis_before_delegating.md`. Promoted to hook in P3W9.

## Hook 21: Post-Label-Change Wave Field Sync (`post_label_change_wave_field_sync.py`)

- **What it automates:** When `gh issue edit <num> --add-label "p{N}-wave-{M}"` or `--remove-label "p{N}-wave-{M}"` succeeds, PATCHes the issue's `Wave` single-select field on project 2 (Cross-Repo Wave Plan board) via GraphQL `updateProjectV2ItemFieldValue` to match the post-edit label state. Compound `--add-label X --remove-label Y` honors post-edit state (set to X). Companion to Hook 13 (`auto_add_issue_to_board.py`) which catches CREATE-time only; this hook closes the label-EDIT gap.
- **Input language:** PostToolUse Bash. Matches `gh issue edit <num> --repo <r> ...` segments with at least one `--add-label`/`--remove-label` flag-value pair whose value is a canonical wave label in ANY accepted form (main#810): legacy `p{N}-wave-{M}` (anchored `^p\d+-wave-\d+$`), phase-agnostic `wave-{X}` (`^wave-\d+$`), or the `wave-x` placeholder. The option-name mapping is `p{N}-wave-{M}`→`P{N}W{M}`, `wave-{X}`→`W{X}`, `wave-x`→`WX`. Does NOT match: `gh issue create` (Hook 13's surface); `gh pr edit ...` (PR labels don't drive the Wave field — the Wave field lives on issues in project 2); commands with non-wave labels; suffixed labels (`p3-wave-10-special`, `wave-10-frozen` are out of pattern).
- **Verification logic:** Tokenizes via shared `_wave_label_parse.parse_wave_label_change` helper (which itself sits on top of `_shell_parse` per Hook Authorship Requirement 5). Pre-flights `gh auth status -h github.com` for `project` token-scope before any GraphQL call — silently skips and logs ONE annunaki advisory per session if scope is missing (debounced via `.claude/.consulted/post_label_change_wave_field_sync/auth_scope_warned.marker`). Caches project-2 IDs (project_id, Wave-field id, per-wave option_ids) to `.claude/.consulted/post_label_change_wave_field_sync/project_ids.json` with 1h TTL, mode 0600. On `field-not-found` errors from the mutation, busts the cache and retries once before giving up.
- **Augments:** Hook 13 (`auto_add_issue_to_board.py`) which enforces the same "wave-labeled issues belong on the board" invariant at the CREATE surface; this hook applies it at the EDIT surface. Also augments the `/board-audit` skill (`.claude/skills/board-audit/SKILL.md`) which is the periodic compensating control — Hook 21 reduces the steady-state drift count that board-audit has to clean up.
- **Kill-switch:** Set `NOORIN_DISABLE_LABEL_SYNC_HOOK=1` in the environment to bypass the hook entirely (no GraphQL call, no error, silent skip). Only the literal string `1` skips; `=0`, empty, unset → hook proceeds normally (Unix-tradition truthy-only). Use during debugging or incident response when auto-mutation of the project board would interfere.
- **Manual steps remaining:** New wave options must be pre-created in Project Settings → Fields → Wave (e.g. `W16` before any `wave-16` label is applied; `WX` for the placeholder; legacy `P{N}W{M}` for grandfathered labels). If an option is missing, the hook logs an annunaki advisory and skips that fire — same pre-requisite that `board-audit` documents. The user must also have `gh auth refresh -s project` once per workstation; the hook surfaces this via annunaki on first label-edit if missing.
- **Test coverage:** `.claude/hooks/tests/test_post_label_change_wave_field_sync.py` covers 6 semantic buckets per `skills.md § Acceptance-Criteria-Bucketing-In-Reports` — ACTIONABLE (regex match, kill-switch, auth-scope, ID-cache including field-not-found bust+retry); INFORMATIONAL (regex no-match including `gh pr edit` and `p3-wave-10-special`, GraphQL no-op for off-board issues and missing wave options). Also pure-function coverage for `_wave_label_to_option_name` and `_kill_switch_active`. Parser-fixture coverage for the `--add-label`/`--remove-label` shape lives in `_wave_label_parse.py` consumers' tests (this hook's tests + the existing `test_post_wave_kickoff_comment.py` set).
- **Matcher:** `Bash` via `post_dispatcher.py`'s `_REGISTRY["Bash"]` list, ordered AFTER `auto_add_issue_to_board` (Hook 13) and `post_wave_kickoff_comment` so the slower GraphQL mutation lands last in the chain.
- **Emergency override:** Remove the `post_label_change_wave_field_sync` entry from `post_dispatcher.py`'s `_REGISTRY["Bash"]` list (or set `NOORIN_DISABLE_LABEL_SYNC_HOOK=1` for transient mute without code change).
- **Out of scope for v1:** Per-issue opt-out label (`noorin-no-board-sync`). Decided invariant: all wave-labeled issues are board-tracked (per `feedback_wave_planning_from_board.md`); adding an opt-out would silently drop wave-labeled issues off the board, contradicting `/wave-scope` and `/board-audit` semantics. If real opt-out cases emerge, file a strictly-additive follow-up (no breaking change required). Also out of scope: pagination beyond `items(first: 100)` for the project-item lookup query; a 100-item first page covers every wave's working set we've seen. Extend if production miss-after-first-page false-skips surface.
- **Promotion provenance:** Promoted from memory `feedback_wave_planning_from_board.md` (the originating drift discovery on 2026-04-23) via P3W10 retro escalation. P3W10 retro PR #441 § Proposed Process Changes #3. Owner-decided 2026-05-16; charter adoption via PR #444 (`ccc7edf`); hook implementation via PR #446 (issue #445). 5-drift evidence base from W10 /board-audit run (all label-edit-class drifts that Hook 13 didn't catch). Companion to Hook 13 (`auto_add_issue_to_board.py`) which catches CREATE-time only; this hook closes the label-EDIT gap. Shares the `_wave_label_parse.py` shared helper with sibling hook `post_wave_kickoff_comment` per shared-helper-extraction discipline (`_shell_parse.py` consolidation precedent from P3W4).

## Hook 22: Block Squash-Merge Into a Wave Branch (`block_squash_wave_merge.py`)

- **What it automates:** Blocks `gh pr merge <N> --squash` when the PR's base is a wave branch (`deployments/phase-{P}/wave-{M}`). GitHub squash-merge re-authors the single squash commit to the bare gh principal (`parametrization`), dropping the persona content-commit authorship — the wave→main integration PR then fails the `Verify commit authors are roster members` gate at wrapup (`verify_commit_identity.py`, main#627), because `git log --no-merges base..head` does NOT carve out a single-parent squash commit. The fix is trivial and unambiguous (`--merge`, which preserves persona authorship and lets the bare-principal merge commit be excluded by `--no-merges`), so this is a **hard block** with a diagnostic, not an advisory (memory `feedback_safety_direction_over_ux_friction`).
- **Input language:** PreToolUse Bash. Cheap pre-filter on the literal substring `merge` short-circuits the common case before any parse or network call (gating on `merge` rather than `--squash` is required to also catch gh's short `-s` form — `-s` is too generic to substring-match safely, but every `gh pr merge` contains `merge`). On a match, tokenizes via the shared `_shell_parse` primitives (`strip_heredocs` → `tokenize` → `iter_command_segments` → `find_gh_subcommand`, per Hook Authorship Requirement 5) and yields each command-position `gh pr merge <N>` segment carrying **either** `--squash` **or** the short `-s` (cover-all-syntactic-forms, memory `feedback_lint_gate_cover_all_syntactic_forms` — caught in the PR #900 review) with its `--repo`/`-R` value. Does NOT match: `--merge`/`-m` merges (the correct method, never blocked even on a wave base); `gh pr view`/other gh subcommands; a `git merge` (parses cheaply, yields no `gh pr merge` segment → allow, no network); a `--squash` inside a heredoc body (prose, stripped first); a non-digit PR token (e.g. a `$pr` loop variable — unresolvable, and the batch-loop shape is guarded separately by `validate_pr_review`, memory `feedback_batch_loop_merge_evades`).
- **Verification logic:** Resolves each candidate PR's base ref via `gh pr view <N> --json baseRefName` (isolated behind `_resolve_base_ref(..., runner=)` for test injection) and blocks iff the base matches `^deployments/phase-\d+/wave-\d+$` (anchored — a feature branch merely containing the substring does not match). A normal squash-merge into `main` (the standard GitHub-flow squash for feature work) resolves to base `main` and is untouched.
- **Fail-open:** Because base-resolution needs a network call, the hook is ordered LAST in `dispatcher.py`'s `_BASH_HOOKS` (network-calling checks last) and fails **open** on any error — gh missing, offline, non-zero exit, timeout, or an unresolvable PR token all return allow. A transient gh hiccup never blocks legitimate work; the cost is that an offline squash-into-wave slips through (acceptable — the wrapup commit-author gate is the backstop).
- **Test coverage:** `.claude/hooks/tests/test_block_squash_wave_merge.py` (16 tests) — squash-into-wave blocks (`--squash` and short `-s`, with `--repo`, flag-order-independent, `-s -d`), squash-into-main allows (long and short), `--merge`-into-wave allows, non-Bash tool allows, unresolvable base fails open, non-digit PR token never consults the runner, the `merge` pre-filter short-circuits a non-merge command before any parse/network, a `--merge` merge never consults the runner, and heredoc/compound-segment safety. Injected fake runner — never a real gh call.
- **Matcher:** `Bash` via `dispatcher.py`'s `_BASH_HOOKS` list (last entry).
- **Promotion provenance:** Promoted from memory `feedback_wave_branch_merge_not_squash.md` (the P7W19 #898/#222 lesson) via the P7W19 retro (Step 7.7 memory-to-automation audit). Owner-decided 2026-06-25 ("build the hook this retro"). Codifies charter `pull-requests.md § One Merge Model Per Wave`, which previously relied on memory alone to prevent the squash footgun.

## Shared Helpers <!-- promotion-target: none -->

Reusable primitives that multiple hooks (or hooks + skills) consume. Each helper has a single-source-of-truth implementation under `.claude/hooks/` with an underscore-prefix filename (`_<helper>.py`) marking it as internal, not a hook itself.

### `_shell_parse.py` — Tokenize Bash commands safely

Multiple PreToolUse hooks need to detect command shapes (`git commit`, `gh pr create`, etc.) without regex'ing the raw command string — a pattern that has repeatedly mis-fired on heredoc bodies, code-fence blocks, and `--body-file` argument values (issues #118, #134, #144, #188, #189, #216, #223, #226, #227). The helper exposes `tokenize`, `strip_heredocs`, `iter_command_segments`, `find_git_subcommand`, `find_gh_subcommand`, and `extract_dash_c_pairs`. Consumed directly by `validate_commit_identity`, `validate_branch_freshness`, `block_git_config`, `block_no_verify`, `block_shutdown_without_retro`, `block_stale_tmp_message_file`, `validate_review_comment_format`; and transitively by `post_wave_kickoff_comment` + `post_label_change_wave_field_sync` (both via the domain-shape `_wave_label_parse` helper below). When a new transcript-or-command-reading hook needs to discriminate command shape, consume this helper rather than regex.

### `_wave_label_parse.py` — Parse `gh issue edit ... --add-label|--remove-label "<wave-label>"`

Two PostToolUse Bash hooks need to detect when a wave label is being added or removed on a GitHub issue: `post_wave_kickoff_comment` (posts a charter-format kickoff comment on label-APPLY) and `post_label_change_wave_field_sync` (syncs the project 2 Wave field on label-ADD or -REMOVE). The shape they each match — `gh issue edit <num> --add-label|--remove-label "p{N}-wave-{M}"` with arbitrary flag ordering, both two-token and equals forms, compound pipelines, and tolerated extra non-wave-label flags — is the same; duplicating the parser would re-introduce the regression class the `_shell_parse` consolidation closed in P3W4 (#226 #227 #223 #216 #188 #189 #144).

The helper exposes `parse_wave_label_change(command) -> WaveLabelChange | None` (returning a frozen dataclass with `repo`, `issue_number`, `add_label`, `remove_label`), `is_wave_label(value) -> bool`, `parse_wave_label_spec(value) -> WaveLabelSpec | None`, `wave_label_to_option_name(value) -> str | None`, and `parse_wave_label(value) -> (phase_num, wave_num) | None`.

**Wave-label grammar (main#810, completing Design B #804).** Three forms are accepted everywhere: legacy `p{N}-wave-{M}` (anchored `^p\d+-wave-\d+$`, grandfathered), phase-agnostic global `wave-{X}` (`^wave-\d+$`, the going-forward form), and the `wave-x` placeholder. All are fully anchored, so suffixed values like `p3-wave-10-special` or `wave-10-frozen` are out-of-pattern. `is_wave_label` / `parse_wave_label_spec` / `wave_label_to_option_name` accept all three; `parse_wave_label` is **legacy-form-only** (its `(phase, wave)` tuple cannot express a missing phase — new forms return `None`). `WaveLabelSpec` carries `(raw, phase|None, wave|None, is_placeholder)`. Option-name mapping: `p{N}-wave-{M}`→`P{N}W{M}`, `wave-{X}`→`W{X}`, `wave-x`→`WX`.

**Promotion provenance:** Extracted from `post_wave_kickoff_comment.py`'s pre-#445 `parse_label_apply_command` during Hook 21 implementation (PR #446, issue #445). The extraction is behavior-preserving for `post_wave_kickoff_comment` (verified by running its existing 30-test suite both pre- and post-refactor — identical pass/fail counts and test names). Follows the `_shell_parse.py` consolidation precedent from P3W4 #226/#227/#223/#216/#188/#189/#144 — when ≥2 hooks need the same input shape, extract a shared helper rather than duplicate.

### `_consultation_sentinel.py` — Cwd-keyed consultation sentinel

Generalizes the Hook 15 sentinel pattern (introduction: [#169](https://github.com/noorinalabs/noorinalabs-main/issues/169); generalization: [#176](https://github.com/noorinalabs/noorinalabs-main/issues/176)) for any future transcript-reading enforcement hook. The pattern: a skill writes a marker file in the agent's cwd recording that it was invoked; the hook reads the marker as a second acceptance signal beside the transcript scan. Subagent worktree sessions repeatedly hit a transcript-flush race that left the marker absent from the file the hook reads — the sentinel survives that race because the skill writes it synchronously.

**Path scheme:** `<cwd>/.claude/.consulted/<skill_name>/<sha1(abspath(cwd)+"\n")[:16]>.marker`. Namespaced by skill name so multiple transcript-reading hooks don't collide. The trailing-newline hash matches the shell idiom `pwd | sha1sum | cut -c1-16` so skills can write the sentinel from shell and the Python helper computes the same path (parity gated by `test_consultation_sentinel.ShellPythonParityTests`).

**API:**
- `write_consultation_sentinel(skill_name, cwd=None) -> Path | None` — skill-side write. Returns None on OSError (fail-open).
- `consultation_sentinel_is_fresh(cwd, skill_name, ttl_seconds=3600) -> bool` — hook-side read. False on missing / stale / unreadable / future-dated marker.
- `consultation_sentinel_path(cwd, skill_name) -> Path` — pure path composition (tests use this to write sentinels manually).
- `cwd_sentinel_hash(cwd) -> str` — 16-char sha1 prefix, exported because Hook 15 tests pin the shell/Python parity property.

**Use this helper** when authoring a new transcript-reading enforcement hook. Do NOT reinvent path-keying, hashing, or TTL logic — every divergence becomes a sentinel-doesn't-match bug in worktree subagents.

**Promotion provenance:** Hook 15 (#150 + #169) original sentinel introduction. PR #174 added synchronous skill-side write. Issue #176 extracted the helper. Filed by Nadia Khoury during PR #174 review.

## Hook Sync Across Child Repos <!-- promotion-target: none -->

> The org-wide artifact ownership + execution-location matrix (hooks, skills, charter, memory, ontology, settings — meta vs child) is canonicalized in [`charter/artifact-ownership.md`](artifact-ownership.md) (#328). This section remains the authoritative detail for the **hook** class specifically; the matrix points back here.

Shared hooks live in `noorinalabs-main/.claude/hooks/` (the parent repo's hooks tree). Child repos consume them via **parent-canonical paths** — their own `.claude/settings.json` registers each hook by absolute path into the parent's hooks tree, e.g.:

```jsonc
{
  "matcher": "Bash",
  "hooks": [{
    "type": "command",
    "command": "python3 /home/parameterization/code/noorinalabs-main/.claude/hooks/dispatcher.py",
    "timeout": 30
  }]
}
```

**The parent's `.claude/hooks/` is the single source of truth for shared hook code.** Child repos do NOT keep local `.py` copies of shared hooks; they reference the parent's files by path. This makes a new shared hook a configuration change in each child's `settings.json`, not a code-fan-out across child repos — eliminating the drift risk that surfaced in P2W9 (Hook 14 was registered in the parent for ~2 weeks before #194 surfaced no child had it).

### Required pattern

For every shared hook (i.e., a hook that exists at `noorinalabs-main/.claude/hooks/<name>.py` and applies to multiple repos):

1. Hook source code lives at `noorinalabs-main/.claude/hooks/<name>.py` ONLY. No copies in child repos.
2. Each child repo's `.claude/settings.json` registers the hook under the appropriate matcher with a `command` of `python3 /home/parameterization/code/noorinalabs-main/.claude/hooks/<name>.py` (or the dispatcher path for Bash hooks).
3. Child repos do NOT have their own `annunaki_log.py`, `_shell_parse.py`, `dispatcher.py`, or other shared support files. They reference the parent's copies.

### Anti-pattern: copy-resident hooks

Do NOT copy `.py` hook files into a child repo's `.claude/hooks/` and register them via relative paths. This is the **copy-resident anti-pattern**:

- Forces a per-repo PR to ship every shared-hook update (versus a single line in each child's `settings.json`).
- Two distinct mental models in flight whenever some children are copy-resident and others are symlink-style.
- Drift is permanent — no compile-time check that all copies are in sync with the parent's source of truth.

If you find a child repo using copy-resident hooks during routine work, file a tracking issue and align on the next hook-sync wave's plan rather than mixing the cleanup into an unrelated PR.

### Anti-pattern: empty child config

A child repo that participates in hook-gated workflows (commits, PRs, merges) MUST have a `.claude/settings.json` registering at least the parent dispatcher and matcher hooks relevant to that repo's surface (Edit/Write for sources, SendMessage for cross-repo coordination, etc.). An **empty child config** is a silent gap — hooks the parent enforces simply don't fire in that repo. Audit during wave-kickoff and file `tech-debt` if any in-scope repo is empty.

### Reviewer enforcement

When a PR adds or modifies a child repo's `.claude/settings.json`, reviewers verify:
- Each hook entry uses an absolute path into `noorinalabs-main/.claude/hooks/`, not a relative path.
- No new `.py` hook files are added to the child's `.claude/hooks/` (the dir should be empty or contain only child-local hooks specific to that repo's surface — none currently exist).
- Coverage matches the parent's matcher list for the equivalent surface (e.g., a child with code-editing tools should register PreToolUse Edit/Write hooks that the parent registers for the same purposes).

### Caveats acknowledged

- Symlink-style is fragile to parent-dir layout changes — but the org-canonical workstation layout (`/home/parameterization/code/noorinalabs-main/...`) has been stable since project inception.
- Symlink-style breaks when a child repo is cloned standalone OUTSIDE the parent. Hooks fail to invoke (no matching path); the harness gracefully falls through (no hook = allow). Document this in any per-child-repo CLAUDE.md that anticipates standalone cloning.
- Hook updates require a child-side `settings.json` edit when hook count changes (new hook added; matcher consolidation per § Dispatcher Consolidation Policy). This is one line per child — significantly cheaper than the per-repo PR cost the copy-resident pattern imposes.

### Promotion provenance

Surfaced during execution of [#194](https://github.com/noorinalabs/noorinalabs-main/issues/194) (Hook 14 sync to 7 child repos) — Aino's survey found 3 copy-resident, 3 symlink-style, 2 empty across the 7 child repos. Owner-greenlit the canonicalization 2026-04-27. Phase 1 (this section, charter codification) lands in P3W4. Phase 2 (per-child-repo sweep migrating the 3 copy-resident repos to symlink-style + scaffolding any empty repos) is tracked separately for P3W5. See [#214](https://github.com/noorinalabs/noorinalabs-main/issues/214).

---

## Hook Authorship Requirements <!-- promotion-target: none -->
Every new hook in `.claude/hooks/` must meet these requirements **at the time it is merged**. Partial compliance is a moderate feedback event.

### 1. Input-language specification

The hook's module docstring (top of file) must include an explicit **Input Language** section defining:

- **Fires on:** which PreToolUse event (Bash, Agent, Edit, Write, etc.)
- **Matches:** the exact command / input shape the hook acts on, expressed as a regex or grammar fragment
- **Does NOT match:** inputs that superficially look similar but are intentionally out of scope (with examples)
- **Flag pass-through:** which CLI flags (e.g., `--repo`, `--admin`) are extracted from the matched command and how

Example (from `validate_pr_ci_status.py`):
```python
"""
Input Language:
  Fires on:      PreToolUse Bash
  Matches:       gh pr merge {N} [--repo {OWNER/REPO}] [--squash|--merge|--rebase] [--admin] [--auto]
  Does NOT match: gh pr list, gh pr view, gh pr checks, gh pr create, git merge, git pull
  Flag pass-through:
    --repo   → overrides cwd-resolved repo when querying gh pr view
    --admin  → short-circuits (emergency override, allows merge)
    --auto   → allows pending checks (GitHub auto-merge)
"""
```

**Why:** Phase 2 Wave 8 surfaced six hook substring/regex bugs (#113 validate_labels cwd, #114 auto_set_env_test test-string false-positives, #118 validate_branch_freshness cwd, #123 validate_pr_review RequestOrReplied-Requested false-positive, ontology-tracker /tmp ghost entries, validate_labels default-limit). Root cause was hooks written liberally without an explicit spec of what they match vs. don't. An input-language docstring forces the author to enumerate the negative space before shipping.

### 2. Charter entry in `charter/hooks.md`

Every new hook must have a numbered entry in this file with: What it automates, Augments (which charter section), Manual steps remaining, Emergency override. No hook ships without a charter entry.

### 3. Test coverage for negative matches

The hook's test suite (or docstring-embedded manual verification) must include at least one input that **looks like a match but is intentionally excluded** — to guard against the substring-bug pattern. Example: a `validate_pr_merge` hook must verify it does NOT fire on `gh pr list`.

### 4. Dispatcher registration (not settings.json)

New Bash hooks must register in `dispatcher.py`'s `_BASH_HOOKS` list, not as a separate `settings.json` entry. See `charter/hooks.md` § Hook Dispatcher Consolidation (Hook 7 pattern).

### 5. Parser-Fixture Coverage Requirements

Every hook with input parsing MUST have test fixtures covering all known input shapes. New input shapes discovered in production (e.g., a `head_ref` shape the parser doesn't recognize, a quoting style that trips shlex, a YAML edge case) require fixture-add backport BEFORE the bug-fix PR can merge — the fixture pinning the new shape lands together with the parser fix in the same commit.

**Rationale:** P3W6 surfaced 4 hook parser bugs in a single wave (#285 /wave-kickoff Step 1 EXISTING_SHA captures 404 body; #287 validate_commit_identity false-blocks backslash-line-continuation; #289 validate_workflow_paths_coverage misparses bare `on.pull_request:`; #294 validate_pr_review skips reviewer counting on `deployments/*/wave-*` heads). All four are parser bugs in production hooks discovered AT runtime when an unanticipated input shape arrives. Fixture-with-fix discipline pins the new shape so future regressions surface in CI.

**Acceptance:** PR introducing a parser-bug fix MUST include the new fixture in the same commit. CI (or hook authors during review) flags PRs that change parser logic without an accompanying fixture addition.

**Dispatcher-style children (no committed `.claude/hooks/`):** Children that delegate all hook execution to the parent canonical via `settings.json` are exempt from per-child fixture requirements. Coverage obligations are fulfilled by the parent's test suite. A child is classified as dispatcher-style when `gh api repos/<owner>/<repo>/git/trees/<head_sha>?recursive=1` returns 0 entries under `.claude/hooks/`. Design-system and landing-page (post-W5) are the canonical exemplars.

#### 5a. Mandatory Test Coverage for PreToolUse Segment Parsers

This is a **specialization of §5** for the narrow class of hooks that split a bash command on shell separators into segments (e.g. `auto_set_env_test.py` splits on `&&`/`||`/`;`/`|`/`\n` to check each test-bearing segment independently). Any such **segment-parser** hook MUST carry test coverage for ALL SIX separator classes — not just the ones the original feature happened to exercise.

| Class | Example | Test-class-name convention |
|---|---|---|
| Standard separators | `cmd1 && cmd2`, `cmd1 \|\| cmd2`, `cmd1; cmd2`, `cmd1 \| cmd2` | `StandardSeparatorTests` |
| Newline | `cmd1\ncmd2` (multi-line script) | `NewlineSeparatorTests` |
| Subshell | `(cmd1; cmd2)` | `SubshellTests` |
| Control-flow body | `for x in ...; do cmd; done` | `ControlFlowBodyTests` |
| Line-continuation | `cmd \`<br>`  arg` (backslash-newline) | `LineContinuationTests` |
| Quoted regions | `'sep && inside'`, `"sep \| inside"` | `QuotedRegionTests` |

Each class MUST include at minimum:

- One **allow** case — the segment correctly receives the env-block / hook-condition and the hook passes.
- One **block-with-correctly-targeted-suggestion** case — the segment is missing the env / hook-condition, the hook blocks, AND the suggestion lands on the right token (not a neighbouring segment). For the control-flow class where a clean splice is impossible, the block case asserts the HARD-BLOCK diagnostic path instead (per §Hook 4 / #478). Because that hook deliberately does NOT peek into the loop body for an existing env-block (even env-already-inside hard-blocks, so the operator edits manually), the control-flow "allow" case is a control-flow construct that carries no test runner at all — the hook correctly does not fire.

The canonical reference implementation is `.claude/hooks/tests/test_auto_set_env_test.py`. The convention-named classes there carry a `# segment-class: <Standard|Newline|Subshell|ControlFlowBody|LineContinuation|QuotedRegion>` marker comment so a future grep-based CI gate (out of scope here, follow-up) can assert all six are present.

**Why charter, not a code-review checklist:** a checklist is opt-in and decays (`feedback_enforcement_hierarchy`: "Charter rules without enforcement decay"). The `auto_set_env_test` hook shipped quote-aware (#478) and control-flow-aware detection but had NO coverage for newline-as-separator; the gap surfaced as repeated operator friction ("I've seen this error a few times") before #537 was filed and fixed in #538. Encoding the six-class matrix as a contract makes the NEXT segment-parser hook add all six from the start, rather than discovering each gap at runtime.

**Spawn-brief line for hook PRs:** reviewer-class and implementer-class spawn briefs for any segment-parser hook PR MUST include the line: *"ensure all 6 segment-class tests present (per `hooks.md § Mandatory Test Coverage for PreToolUse Segment Parsers`)."*

**Out of scope (follow-ups):** a grep-based CI gate asserting the six convention class-names; backfilling the six classes for *other* existing hooks (they have at least partial coverage already; a separate sweep); coverage requirements for non-segment-parser PreToolUse hooks (different signal pattern — §3 negative-match coverage already governs those).

<!-- Promoted from memory: feedback_safety_direction_over_ux_friction (control-flow safety-direction precedent #478) — codifies P3W12 retro § Proposed Process Changes #2 (issue #543), newline precedent #537/#538. Charter-tier only (no hook); CI-gate enforcement is a deferred follow-up. -->

### 6. Promotion Provenance Phrasing

Every hook's charter entry includes a provenance block describing where the hook came from. The `/promotion-audit` skill's `find_already_promoted` parser scans these blocks to decide which memories / charter rules / skill patterns have already landed as hooks. Ambiguous phrasing defeats the parser (false-negatives produce noisy AUTO classifications; false-positives produce noisy ALREADY-PROMOTED classifications). Three required parts:

**Backward claim (required):** a single sentence declaring backward provenance — what prior tier (memory / charter / skill / pattern) this hook was promoted from. Example:

> Promoted from memory `feedback_enforcement_hierarchy.md` via charter § Ontology Librarian Rule (PR #153).

Every hook MUST have exactly one backward-claim sentence. The parser's `_PROVENANCE_RE` and `_HTML_COMMENT_PROMOTED_RE` recognizers extract memory / charter / skill references from this sentence, so it MUST cite the source artifact by filename (memories: `feedback_X.md` or unsuffixed `feedback_X`; skills: `/skill-name`; charter rules: `CLAUDE.md § X` or `charter/X.md § Y`).

**Forward references (optional, must be in a separate paragraph):** if the hook's charter entry mentions sibling hooks, future artifacts, or design narrative, that narrative MUST live in its OWN paragraph — never co-located with the backward-claim sentence. Example forward reference:

> Worked example referenced by the future `/promotion-audit` skill design.

**Why separate paragraphs:** `find_already_promoted`'s `_FORWARD_REFERENCE_MARKERS` filter (`future`, `planned`, `design`, `upcoming`, `referenced by`, `will reference`, `proposed`, `TBD`) excludes slash-command hits that sit within ~60 chars of these markers. Forward-reference narrative mixed into the backward-claim sentence makes that filter trip on the backward citation too — turning a real promotion record invisible. Keeping the two concerns in separate paragraphs is the simplest discipline that preserves both meanings.

**Recognized parse keys:** the literal tokens `/promotion-audit` scans for. Author your provenance block with one of these as the opener so the parser finds it:

- `**Promotion provenance:**` — block-style header; the parser's `_PROVENANCE_RE` greedy-matches until the next blank line / heading. Used by hooks.md per-hook entries (e.g. Hook 15).
- `Promoted from` — opening token recognized inline; works inside either the block-style entry or a standalone sentence.
- `<!-- Promoted from memory: X -->` — HTML-comment marker form codified in #283 / #393. Used for charter-tier-only promotions (no corresponding hook). The parser's `_HTML_COMMENT_PROMOTED_RE` (DOTALL) captures the body up to `-->`, so trailing context (date, retro citation, rationale) is included in the regex sweep.

**Rationale:** PR #155 added the reactive `_FORWARD_REFERENCE_MARKERS` filter to handle Hook 15's own provenance block — which had narrative referencing a future skill mixed in with the backward citation. The filter is the runtime safety net; this guidance is the preempt-at-author-time fix that reduces future filter-edits. Sibling of #393 (HTML-marker convention) — this section catalogues the parse keys; the authoritative shape-selection rule (when to use HTML-comment vs. bold-prose) lives at [`charter/skills.md` § Promotion Pipeline Marker Convention](skills.md#promotion-pipeline-marker-convention).

### 7. gh-command Parser Invariant (flag-value scoping + ambient-repo resolution)

**Any hook that parses a `gh` command (`gh issue` / `gh pr` / `gh workflow` / `gh api`) MUST:**

1. **Scope label/repo extraction to the actual flag VALUES** — the tokens that follow `--label`/`-l`/`--add-label`/`--remove-label`/`--repo`/`-R` — via the shared tokenizer (`_shell_parse.walk_flag_values` / `first_flag_value`, `_repo_flag_parse.extract_repo`, or the domain-shape `_wave_label_parse` helpers). It MUST NOT regex flag-shaped or label-shaped strings out of arbitrary command text, and MUST NOT reimplement shell tokenization privately (`shlex.split(...)` in the hook body). Routing through `_shell_parse.tokenize` is mandatory because it carries fixes a private copy silently loses — line-continuation normalization (#287), heredoc stripping, and segment splitting — and because a private regex over the raw command leaks label-shaped tokens out of `--body`/`--body-file` content (the #661 false-block).

2. **Resolve the flag-omitted (ambient git-context) case** — a `gh issue create/edit` run *inside* the target repo carries no `--repo` and relies on gh's ambient resolution. The hook MUST recover the repo from the invocation cwd's `origin` via `_shell_parse.resolve_repo_short_name` (mirroring gh), or log a `skip_no_repo_context`-style diagnostic and fail-open — **never silently drop the command** (the #650 EDIT-path drop) and never fall through to a malformed default repo (the #659 CREATE-path twin).

**Backing class:** #650 (EDIT path required `--repo`, dropped in-repo label edits — fixed PR #658), #659 (CREATE path same gate — fixed PR, commit `9ab5c37`), #661 (`validate_labels` matched a label-shaped token in `--body` — fixed `9ab5c37`), `validate_wave_label_evidence` (private `shlex`/flag-walker reimplementation + empty-default `noorinalabs/` slug — migrated under #663), and `warn_ghcr_image` (ad-hoc `re.search(r"-R\s+...")` extractor on `gh workflow run`, no ambient resolution — migrated under #663 wave-16, extending the invariant to the `gh workflow`/`gh api` class). `block_gh_pr_review` likewise dropped its private `re.split` segmenter for the shared tokenizer + heredoc strip (wave-16). Lineage: cwd-anchor #144/#521 → multi-cmd #455 → #650 → #659/#661 → workflow/api class (#663 wave-16).

**Machine-enforcement:** `.claude/hooks/tests/test_gh_command_parser_invariant.py` is the gate (runs in the pytest suite CI already mirrors in `.pre-commit-config.yaml`, so no new CI job / no `ci.yml` edit). It classifies every top-level hook that reads the incoming command and matches a `gh issue`/`gh pr`/`gh workflow`/`gh api` shape, then asserts each (A) does not call `shlex.split`/`shlex.shlex` directly and (C) carries no ad-hoc flag-value-capturing regex. The three sanctioned shared parsers (`_shell_parse`, `_wave_label_parse`, `_repo_flag_parse`) are exempt — they ARE the tokenizer/flag-walker/ambient-resolver. **Scope** is the full gh-command value-flag parser class: `gh issue`/`gh pr` (original) PLUS `gh workflow`/`gh api`, which #663 wave-16 migrated onto the shared parser and folded into enforcement — closing the deferred follow-up the original gate had enumerated.

<!-- Promoted from charter feedback `feedback_enforcement_hierarchy.md` (hook > skill > charter) and the convergent #650/#659/#661 class — owner-adopted P4W7 retro Proposed Change #1 (2026-06-13), actioned in P5 via issue #663 (charter rule + pytest gate for the `gh issue`/`gh pr` class), then extended to the `gh workflow`/`gh api` class in P6 wave-16 (#663). The gh-command analogue of the deferred grep-gate noted in §5a. -->

**Enforcement:** The Standards & Quality Lead (Aino) verifies these requirements during hook PR review. A hook missing any of the seven requirements must not be approved. For segment-parser hooks specifically, §5a's six-class test matrix is part of that verification; for gh-command parsers (`gh issue`/`gh pr`/`gh workflow`/`gh api`), §7's flag-value-scoping + ambient-repo resolution (and its gate) are part of it.

## Hook Audit Protocol

When auditing a repo's hook ownership status (hook-owning vs. dispatcher-style):

1. Fetch the committed tree:
   ```
   gh api repos/<owner>/<repo>/git/trees/<head_sha>?recursive=1 \
     --jq '[.tree[].path | select(startswith(".claude/hooks/"))]'
   ```
2. Classification: if the result is empty (`[]`), the repo is dispatcher-style. If non-empty, it is hook-owning.
3. Filesystem enumeration (SSH, `ls`, `find`) is NOT a valid substitute — it includes untracked files, worktree artifacts, and gitignored content that are invisible to git.

**Rationale:** P3W7 produced 3 repo misclassifications from a single root cause: auditors enumerated working-directory files instead of querying the committed git tree. Misclassified repos: design-system, user-service, data-acquisition — all initially called "stale-mirror hook-owning" but confirmed dispatcher-style via committed-tree inspection. The correct method is one API call away.

**Enforcement:** Any audit-finding comment that asserts a repo's classification must cite the `gh api .../git/trees` invocation it ran (or the equivalent `gh api .../contents/.claude/hooks?ref=<sha>` form). Reviewers reject classification claims sourced from `ls`, `find`, SSH, or local checkout.
