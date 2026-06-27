# Pull Requests

When all work on a feature branch is complete (code committed, review done, must-fixes resolved), the submitting team member **automatically creates a PR to the deployments branch** for their wave using the `gh` CLI. Do not wait for manual instruction.

**PR ownership:** Only the team member who implemented the work creates the PR. The Program Director must NOT create duplicate PRs for the same branch.

## Comment-Based Reviews (Mandatory) <!-- promotion-target: none -->
All agents share a single GitHub user account. **`gh pr review --approve` is blocked** — it always fails with "cannot approve your own pull request". All PR reviews MUST use comment-based reviews instead.

**Review format** (posted via `gh pr comment`):
```
Requestor: <comment author>
Requestee: <comment target>
RequestOrReplied: Request | Reply | Approved | ChangesRequested
TechDebt: none | #15, #16, ...
```

### Canonical meaning (resolves main#233)

The role names always describe the **comment** (not the PR):

- **`Requestor` is always the comment author** — the team member posting the comment, regardless of whether they are the PR author or a reviewer.
- **`Requestee` is always the comment target** — the team member the comment is addressed to.
- **`RequestOrReplied`** distinguishes the comment kind, NOT the role direction:
  - `Request` — initial review request from PR author (Requestor=PR author, Requestee=reviewer)
  - `Reply` — non-verdict response from any party (Requestor=replier, Requestee=person-being-replied-to)
  - `Approved` — reviewer's approving verdict (Requestor=reviewer, Requestee=PR author)
  - `ChangesRequested` — reviewer's blocking verdict (Requestor=reviewer, Requestee=PR author)

**Key consequence for verdict comments**: on `Approved` and `ChangesRequested` comments, `Requestor` is the reviewer (because the reviewer is the comment author). The hook counts distinct `Requestor` values across `Approved`/`ChangesRequested` comments to verify the 2-reviewer rule (resolves main#244 — the prior hook counted distinct `Requestee` values, which on verdict comments is the PR author, not the reviewer).

**Scope of the `validate_review_comment_format` hook** (resolves main#378, realigned in main#386): This hook enforces Requestor/Requestee non-swap detection ONLY for `Approved` and `Changes Requested` verdict comments, where the Direction table above binds `Requestor = reviewer` and `Requestee = PR author`. Within that scope the hook blocks when `Requestor.lastname == branch-author.lastname` — i.e., when the PR author is being named as the reviewer (the post-#244 swap shape). For `Request` and `Reply` comments — where the role bindings invert (`Requestor = PR author`, `Requestee = reviewer`) — the swap heuristic does not apply and the hook returns `None`. Author/reviewer discipline for `Request`/`Reply` traffic is operator-trusted; the hook does not gate it. Unrecognized `RequestOrReplied` values also pass through (the verdict-word vocabulary is `validate_pr_review`'s scope, not this hook's).

### Validation

- The `Requestor` of a `Request`-kind comment must differ from the comment author of the `Approved`/`ChangesRequested` comments (a PR author cannot self-approve their own PR via comment-based review). Enforced by `block_gh_pr_review.py` PreToolUse hook + `validate_pr_review.py` at merge time.
- The `TechDebt:` line is **mandatory** on every `Approved` and `ChangesRequested` comment. If the reviewer found non-blocking observations, they MUST create `tech-debt`-labeled issues BEFORE posting the verdict, then list the issue numbers. If no tech-debt was found, write `TechDebt: none`. Enforced by `validate_pr_review.py` PreToolUse hook at merge time.
- The 2-reviewer rule is satisfied when there are `Approved` comments from **two distinct `Requestor` values**, neither of which is the PR author. Single-reviewer waivers per § Single-Reviewer Exception (Wave-Bootstrap Only) are honored by the hook (resolves main#228) when the PR is labeled `wave-bootstrap` and the single reviewer is the Standards & Quality Lead.
- Each `Requestor` value on an `Approved` comment must name a persona in the local `.claude/team/roster/` (full-name match against `**Name:**` lines). Non-roster Requestor strings do NOT count toward the 2-reviewer threshold — Hook 4 filters them out and reports them in the BLOCK diagnostic. Mirrors `validate_commit_identity.py`'s strict-roster discipline (resolves main#498).
- Charter-format fields (`Requestor:` / `Requestee:` / `RequestOrReplied:` / `TechDebt:`) MUST appear ONLY in the trailer block — a contiguous structured-fields block at the end of the comment body, ideally after a bare-line `---` separator. Hook 4 extracts fields only from the trailer-block substring (post-last-`---`) and strips inline (`` `…` ``) and fenced (```` ```…``` ````) code regions before matching. Prose that quotes the field syntax above the trailer (or uses backticks to discuss it) will be ignored by the extractor, but reviewers should still avoid duplicating field patterns in prose for clarity. Pre-#511 the regex first-matched any `<Field>:` mention, which false-blocked 3 reviewer verdicts in P3W11 batch 11 (main#509, deploy#337, deploy#339) — each required orchestrator REST PATCH (resolves main#511).

## Review Prompt Template (Mandatory) <!-- promotion-target: none -->
When the orchestrator assigns a review to any agent, the prompt **MUST** include a copy-paste-ready `gh pr comment` command with all fields pre-filled. Do not rely on agents writing the format from memory — this has a 100% error rate.

**Template for orchestrator prompts** (Approved/ChangesRequested verdict — reviewer is the comment author, so Requestor=reviewer):
```
Post your review using this exact command:

gh pr comment {PR_NUMBER} --repo noorinalabs/{REPO} --body "Requestor: {REVIEWER_NAME}
Requestee: {PR_AUTHOR_NAME}
RequestOrReplied: Approved
TechDebt: none

{Your review summary here.}"
```

Replace `Approved` with `ChangesRequested` if blocking issues found. Replace `TechDebt: none` with issue numbers if tech-debt filed. Do NOT add bold markers, parenthetical descriptions, or extra fields.

For `Request`-kind comments (initial review request from PR author), the role direction inverts: Requestor={PR_AUTHOR_NAME}, Requestee={REVIEWER_NAME} (because the PR author is the comment author of the request).

**Why:** In Phase 3 Wave 1, all 7 initial reviews used wrong field names (`Requestee (reviewer):` instead of `Requestee:`) and omitted the `TechDebt:` line, requiring re-posts and blocking merges for ~15 minutes. In P3W3, the wave-completion batch's verdict comments mostly had `Requestee=author` (because Requestor was the reviewer-as-comment-author), which the prior `validate_pr_review.py` interpretation treated as 1 distinct reviewer instead of 2 — forcing `--admin` overrides on 5/5 wave-merge PRs (main#244).

Failing to include the review template in a review assignment prompt is a **minor feedback event** for the orchestrator.

## Two-Reviewer Assignment at Wave Kickoff <!-- promotion-target: none -->
Every PR must have **two reviewers** assigned at wave kickoff — a primary and a secondary. Both reviewers are named in the agent's spawn prompt and in the execution plan.

**Why:** In Phase 3 Wave 1, only one reviewer was planned per PR. Every PR needed ad-hoc second reviewer assignments, causing merge delays while idle agents were redirected.

The Program Director's execution plan MUST include a review matrix with two named reviewers per expected PR. The orchestrator verifies this before spawning agents.

## All Deliberately-Assigned Reviewers Must Approve Before Merge (Blast-Radius PRs) <!-- promotion-target: none -->

The two-reviewer rule above is a **floor**, not a cap. When a PR has **three or more reviewers deliberately assigned** — typically because it has app-wide blast radius and each reviewer carries a distinct lens (e.g. correctness, build/dependency, security) — the orchestrator MUST NOT merge once the 2-reviewer minimum is met. It waits for **every** deliberately-assigned reviewer to approve (or to be explicitly released by the orchestrator with a recorded reason).

### Why

`validate_pr_review` (the 2-distinct-Approved hook) is satisfied at two approvals — but when a third reviewer was assigned *on purpose* to cover a lens the first two don't, merging at 2/3 ships the PR without the lens that reviewer was assigned to provide. The minimum-gate being green is not evidence that the deliberate review slate is complete.

### How to apply

1. Track the **assigned** reviewer slate per PR (from the spawn plan / execution matrix), not just the count of approvals received.
2. For a blast-radius PR (3+ assigned), gate merge on **all** assigned reviewers Approved — even though the hook would let you merge at 2.
3. To merge before an assigned reviewer finishes, the orchestrator must **explicitly release** that reviewer with a recorded reason (e.g. "released build/dep lens — change is docs-only after rebase"); silent merge-at-2/3 is not permitted.
4. This is orchestrator discipline today; a future enhancement could key the merge gate on assigned-reviewer count.

### Severity if violated

- Merge at 2/3 where the 3rd reviewer's lens turns out non-applicable: **minor** (lucky).
- Merge at 2/3 where the 3rd reviewer later surfaces a real finding the merged change embodies: **moderate** — the deliberate slate existed precisely to catch it.

### Origin

P4W4 ig#1002 (the DS `@theme` color bridge — app-wide blast radius): merged at 2/3 approvals before the deliberately-assigned 3rd (build/dependency) reviewer, Junseo, finished. His verdict (a false-alarm primary conclusion but a real adjacent DS-publish-drift finding → DS#111) landed post-merge; the outcome was non-blocking but only by luck. Owner-approved at the P4W4 retro.

## Single-Reviewer Exception (Wave-Bootstrap Only) <!-- promotion-target: none -->
The two-reviewer requirement may be waived **exclusively** for wave-bootstrap PRs — i.e., PRs that establish the tooling/CI/hooks that subsequent wave PRs will be gated by (e.g., the pre-commit hook rollout that the CI sweep depends on).

Strict conditions — **all must hold**:
- The PR is part of wave bootstrap (establishes infra that blocks other wave work)
- No more than **one** such exception per wave
- The single reviewer is the Standards & Quality Lead (Aino) or a comparable charter enforcer
- The exception is logged by name in the wave retro, with explicit justification

All other PRs require two comment-based reviews. `--admin` merges without two reviews are subject to the moderate-feedback-event classification in § Feedback System.

**See also:** § Trivial Cross-Repo Doc Sweep — a separate single-reviewer exception class for byte-identical doc syncs across child repos. The two exceptions are **independent budgets** (the wave-bootstrap 1-per-wave cap does not consume, and is not consumed by, doc-sweep waivers) and are **not cumulative** — a single PR may invoke at most one.

**Why:** In Phase 2 Wave 8, the single-reviewer shortcut was invoked 8× — it had stopped being an exception and become a pattern of convenience. This clause formalizes the boundary.

## Load-Bearing Followups for Disabled CI Jobs <!-- promotion-target: skill -->
When a PR disables a CI job to unblock merge, the followup tracking issue must be **load-bearing** — the re-enablement of the job is a first-class acceptance criterion of the issue, not a hidden subtask of "fix the underlying bug."

Concrete requirements:
1. **Followup issue exists before the disable PR is approved.** The reviewer verifies the issue number in the PR body under a `## Disabled CI jobs (load-bearing followup)` section.
2. **Followup issue acceptance criteria** must include:
   - A specific fix for the underlying problem
   - Re-enable the CI job (remove `if: false` / `--skip` / equivalent)
   - Verify green CI after re-enablement
   - All three bullets are required in the issue body.
3. **Breadcrumb in PR body.** The PR that disables a job must include a top-level section `## Disabled CI jobs (load-bearing followup)` naming the job disabled, the reason, and the followup issue number.
4. **No silent disables.** A PR that disables a CI job without both the issue and the breadcrumb is a moderate feedback event.

**Why:** Phase 2 Wave 8 ratified this rule mid-wave after two PRs (isnad-graph#811, design-system#56) disabled CI jobs with tracking issues that could be "closed" by just fixing the bug without ever re-enabling the job. Promoting the rule into the charter closes that loophole. Reference: `feedback_disable_followup_load_bearing.md` (historical memory, superseded by this clause).

## PR Review Workflow for Deployments Branch PRs <!-- promotion-target: skill -->
1. **Create the PR** targeting `deployments/phase-{N}/wave-{M}`.
2. **Notify reviewers** — the PR creator must notify at least **two** other team members to review the PR. Use SendMessage or a GitHub comment to notify. **A PR MUST NOT be merged without at least two peer reviews from distinct non-authors.** For waves with fewer than 4 engineers, the manager's review counts but must include a substantive review comment (not just "LGTM"). This is enforced by the `validate_pr_review.py` PreToolUse hook. **This rule applies even on fast/compact waves** — speed does not exempt PRs from the review gate. Wave 7 merged 5 PRs with zero reviews; this must not recur.
3. **Reviewer performs the review** and posts a comment-based review on the PR with:
   - **Must-fix items** — blocks merge; the submitter must resolve before proceeding.
   - **Tech debt items** — does not block merge; tracked as GitHub Issues.
   - The reviewer then **notifies the PR creator** (via SendMessage or mention) that the review is complete and what action is needed.
4. **PR creator acts on review**:
   - **Must-fix items**: Fix immediately and push to the branch.
   - **Quick-fix tech debt**: Fix immediately if minimal impact.
   - **Non-trivial tech debt**: Create a GitHub Issue for future planning.
5. **Push final changes** from the review fixes.
6. **The team merges** the PR into the deployments branch themselves — no user approval needed for PRs into deployments branches.

## Additive Commits on ChangesRequested (Mandatory) <!-- promotion-target: none -->

When a reviewer marks `RequestOrReplied: ChangesRequested`, the fix MUST land as an **additive commit on the same branch**. Force-push (`git push --force` / `git push --force-with-lease`) during a ChangesRequested cycle is **prohibited** because it resets the HEAD-SHA anchor that the reviewer's `gh api contents/<path>?ref=<sha>` verification chain depends on (see § Trust the Artifact, Not the Framing). Without HEAD-SHA stability, the re-review's "delta from prior review" comparison becomes unreliable.

**What is allowed during ChangesRequested:**
- New commits added to the same branch (no rewrite of existing commits)
- A merge commit to update from base if the base advanced (use `git merge origin/<base>`, not `git rebase`)

**What is prohibited during ChangesRequested:**
- `git push --force` / `--force-with-lease`
- `git rebase` followed by force-push
- `git commit --amend` followed by force-push
- Squashing prior commits before re-review

**If a rebase is genuinely needed** (e.g., merge conflict that cannot be resolved by a merge commit, or the requesting reviewer asks for a clean history), the implementer MUST open a comment thread on the PR BEFORE rebasing, get explicit "rebase OK" from the requesting reviewer, then rebase. The reply to a request-to-rebase counts as a `RequestOrReplied: Reply` not an Approval — the re-review cycle restarts from the new HEAD.

**Pre-Approved squash-merge is unaffected.** Once both reviewers have posted `RequestOrReplied: Approved`, the HEAD-SHA anchor is no longer load-bearing, and `gh pr merge --squash` (which performs an effective rebase server-side) is the standard path.

**Why:** In Phase 3 Wave 3, all 4 ChangesRequested cycles (deploy#259 Path-A bundled, #261 perms+runbook, #266 cross-repo Option A, #267 5-fixes-in-49-lines) shipped as additive commits. The reviewers' second-pass reviews could compute the delta deterministically against the prior HEAD SHA. Zero force-pushes; zero "what changed since I last looked" ambiguity. Codifying the practice that worked.

**Severity if violated:** **Moderate** feedback event for the implementer. The reviewer may either re-do the full review at the new HEAD (slow path) or block merge until the implementer reverts the force-push and re-applies the fix as additive (correct path).

## Review Finding Disposition <!-- promotion-target: none -->
Every finding from a PR review must be dispositioned before merge. No finding may be silently dropped.

| Finding Type | Action Required | Blocks Merge? |
|-------------|----------------|---------------|
| **Must-fix** | PR originator fixes on the branch before merge | Yes |
| **Tech-debt** | Reviewer or originator creates a GitHub Issue for each item before merge | No (but issues must exist) |
| **Quick-fix tech-debt** | PR originator fixes immediately if minimal effort | No |

**Enforcement:** The charter enforcer (Aino) verifies during PR review that:
1. All must-fix items are resolved before approving merge
2. All tech-debt items have corresponding GitHub Issues created
3. Issues are labeled `tech-debt` and assigned to the appropriate team member

## Post-Merge Integration Verification <!-- promotion-target: skill -->
**After every PR merge into a deployments branch**, the manager must verify the integrated result before merging the next PR:

1. **Pull the updated deployments branch** locally (or in a worktree).
2. **Run the repo's full check command** (`make check`, `npm run check`, or equivalent — lint + typecheck + build).
3. **If the check fails:** The last-merged PR introduced a regression. The manager must notify the PR author to fix it before any further PRs are merged.
4. **If the check passes:** The next PR may be merged.

This catches semantic conflicts that GitHub's textual merge cannot detect (e.g., two PRs that individually pass CI but break when combined). Managers must NOT merge multiple PRs in rapid succession without verifying in between.

**CI enforcement:** All repositories must configure CI workflows to trigger on pushes to `deployments/**` branches (not just PRs). This provides automatic verification after each merge, complementing the manager's manual check.

## CI Workflow `pull_request` Triggers Must Cover Wave Branches <!-- promotion-target: none -->

CI workflows using a `pull_request` trigger MUST include active wave branches in the `branches` filter, OR omit the filter entirely so the workflow triggers on any base branch. Workflows whose `branches` filter is locked to `["main"]` (or any other single-branch list) silently skip CI on PRs targeting `deployments/phase-{N}/wave-{M}` — the wave PRs that aggregate before the main merge. This is the inverse of the push-trigger rule above: push triggers must cover `deployments/**`, AND PR triggers must cover them too.

**Required pattern** — explicit branch list including wave branches:

```yaml
on:
  pull_request:
    branches: ["main", "deployments/**"]
```

**OR — path-filtered (no branches filter at all):**

```yaml
on:
  pull_request:
    paths:
      - "src/**"
      - "tests/**"
```

**Anti-pattern** — main-only filter that drops wave-branch PRs:

```yaml
on:
  pull_request:
    branches: ["main"]   # WRONG: wave-branch PRs skip CI silently
```

**Reviewer enforcement:** When a PR adds or modifies a `.github/workflows/*.yml` file with a `pull_request: branches:` filter, reviewers MUST flag any single-branch list that does NOT include `deployments/**`, unless the PR body explicitly justifies the exclusion (e.g., "this workflow only runs on main-merge promotions, not pre-merge PRs").

**Why:** P2W10 surfaced this convention gap twice independently. (1) `noorinalabs-user-service/ci.yml` had `branches: ["main"]` — Anya's user-service#80 alembic-merge PR targeting `deployments/phase-2/wave-10` produced an empty `statusCheckRollup` (filed user-service#81). (2) `noorinalabs-deploy/integration-tests.yml` had the same anti-pattern — wave-10 PRs touching `integration-tests/**` would skip CI (filed deploy#152, fix in deploy#154). Both are the same CI-trigger-filter-written-against-single-branch-PR-flow error. Per [`feedback_enforcement_hierarchy.md`](../feedback_log.md), charter codification is step 1 + 2 (rule + reviewer reference); a future `validate_ci_trigger_branches` PreToolUse hook is filed as step 3 if the convention proves robust without manual reviewer reminders.

## Cross-Contract PRs <!-- promotion-target: skill -->
When two or more PRs in flight consume/produce from each other (Kafka topics, Parquet schemas, shared API contracts, wire formats between workers or services), the **first PR opened MUST include a "Contract" section** in the PR body. Subsequent PRs that consume or produce against that contract link to it and document any divergence explicitly.

The Contract section must specify:

1. **Message / schema / API shape** — concrete example or reference to a shared constants module (e.g., `workers/lib/topics.py`).
2. **Ownership** — which PR owns the contract; which owner adjudicates disputes.
3. **Divergence** — how other PRs may legitimately deviate (optional fields, label supersets, etc.).

Any reviewer may block a cross-contract PR that fails this requirement.

**Rationale:** in P2W9, noorinalabs-isnad-ingest-platform#18 (Weronika) and #21 (Wanjiku) built in parallel on incompatible assumptions about message shape (per-row `{label, id, props}` vs Parquet batches with `hadiths.parquet` payload). The mismatch surfaced only during reviewer cross-check after both PRs were essentially complete, forcing an owner-chaired design call (noorinalabs-main#192) and substantive rewires on both branches. A 5-minute Contract section in whichever PR opened first would have caught this upfront.

Derived from Phase 2 Wave 9 retrospective, 2026-04-22.

## Cross-PR Dependency Sequencing <!-- promotion-target: skill -->
When multiple PRs in the same wave have dependencies (e.g., PR B depends on changes from PR A):

1. **Identify dependencies** before merging — check if any PR depends on another PR's changes
2. **Merge in dependency order** — base PR first, dependent PR second
3. **Do NOT merge dependent PRs in parallel** — even if both have green CI, the dependent PR's CI ran against the base branch WITHOUT the dependency
4. **After merging the base PR**, the dependent PR must rebase/merge the updated base before its CI result is trusted
5. **Document dependencies** in PR descriptions: "Depends on PR #N (must merge first)"

## One Merge Model Per Wave (Mandatory) <!-- promotion-target: skill -->

A wave uses **exactly one merge model for its entire lifetime**, chosen and recorded at `/wave-kickoff`. Mixing the two within a single wave is **prohibited**.

| Model | Where per-issue PRs base | Wave→main integration PR |
|-------|--------------------------|--------------------------|
| `direct-to-main` | every PR bases on `main` | none — work is already on `main`; the `deployments/phase-{P}/wave-{M}` branch stays at the kickoff point and never accumulates commits |
| `wave-branch` | every PR bases on `deployments/phase-{P}/wave-{M}` | opened at `/wave-wrapup` Step 11, merged via the `wave-merge` admin exception |

**Per-issue → wave-branch merges use `--merge`, NEVER `--squash` (hook-enforced).** GitHub squash-merge re-authors the squash commit to the bare gh principal (every persona email is a Gmail +alias of the one `parametrization@gmail.com` account), dropping persona content-commit authorship → the wave→main integration PR fails the `Verify commit authors are roster members` gate at wrapup (main#627). `--merge` preserves the persona-authored content commits (they pass the gate) and the bare-principal merge commit is excluded by `--no-merges`. Enforced by **Hook 22 (`block_squash_wave_merge.py`)**, which hard-blocks `gh pr merge <N> --squash` when the PR's base resolves to a `deployments/phase-*/wave-*` branch (squash-into-`main` for feature work is untouched). Source: P7W19 #898/#222; memory `feedback_wave_branch_merge_not_squash`. *(Note: the "Pre-Approved squash-merge is unaffected" clause above governs the orthogonal HEAD-SHA-anchor concern for PRs merging to **main** — it does not license `--squash` into a wave branch.)*

**Origin (P6W1 retro, owner-approved 2026-06-21, [#801](https://github.com/noorinalabs/noorinalabs-main/issues/801)):** P6W1 *mixed* models — #704/#706/#734/#735 merged to the `deployments/phase-6/wave-1` branch while the doc batch + cspell/mermaid work went **direct to main**, and the wave→main PR was never opened. Five net-new deliverables sat stranded off `main`, caught only at `/wave-wrapup` Step 11.5 (resolved via #799).

**Declared at kickoff.** `/wave-kickoff` records the chosen model in `cross-repo-status.json` under `wave_{M}_merge_model` (one of `direct-to-main` / `wave-branch`) via `.claude/lib/wave_merge_model.py set {P} {M} <model>`. The default for cross-repo waves is `wave-branch`; a meta-only or single-repo wave may declare `direct-to-main`.

**Enforced mid-wave, not only at wrapup.** `/session-start` runs `wave_merge_model.py reachability {P} {M}`, which compares each in-scope repo's wave branch against `origin/main` and classifies the gap **against the declared model** — so model-mixing or stranding surfaces within hours instead of at the Step 11.5 wrapup gate (the durable strengthening #801 adds on top of that gate):

- `direct-to-main` + the wave branch carries commits ahead of `main` → **VIOLATION** (someone merged to the wave branch under a direct-to-main wave — the exact P6W1 mixing). Non-zero exit.
- `wave-branch` + ahead + an **open** wave→main PR → **OK** (the integration PR is tracking the work).
- `wave-branch` + ahead + **no** open wave→main PR → **ADVISORY** (expected mid-wave, but it *will* strand unless `/wave-wrapup` opens the PR).

Advisories are expected mid-wave states and do **not** fail `/session-start` (a non-fatal step); only a model VIOLATION exits non-zero. A wave whose `wave_{M}_merge_model` is absent (legacy / pre-#801) degrades to advisory-only with a nudge to declare it — never a false VIOLATION. The classification logic is unit-tested (`.claude/lib/tests/test_wave_merge_model.py`) and the gh I/O layer is shell-free (explicit arg-list, main#688).

## Wave Merge PR Verification <!-- promotion-target: skill -->
At the **end of a wave or phase**, the Manager creates a PR from the deployments branch into `main`. Before presenting the PR to the user:

1. **Verify all CI checks are green** — run `gh pr checks {NUMBER}` and confirm every job passes.
2. **If any check fails**, fix it before notifying the user. The user should NEVER see a wave merge PR with red CI.
3. **Report CI status** explicitly when presenting the PR: "All N checks passing."
4. **Provide full clickable URLs** when presenting PRs to the user — use `https://github.com/{org}/{repo}/pull/{number}`, not `repo#number` format.
5. **Merge via the `wave-merge` admin exception — this is the expected path, not a process failure.** The code on a `deployments/phase-{P}/wave-{M}` branch was already 2×-reviewed on its per-issue wave-branch PRs; the wave→main PR is an *integration* merge, not new code to re-review. After the user approves the merge sequence, the orchestrator merges each with a **literal PR number, one per call** (the `validate_pr_review` hook parses literal numbers — a loop variable fail-opens it): `ADMIN_MERGE_EXCEPTION="wave-merge:<rationale>" gh pr merge <N> --merge --admin`. Collecting *fresh* 2-reviewer approvals on the integration PR is **not** required and should not be requested. The `validate_pr_review` BLOCK (0/2 reviews) and the `--admin` exception prompt firing on these PRs is **expected and audited** (each exception is logged to the Annunaki trail per § Admin-merge exception list) — not a signal that something is wrong. Never `--delete-branch` (wave branches are retained, owner directive 2026-06-09). *Rationale: P4W5 fired this 4× — once per wave repo; the expected path was undocumented, producing per-wave "is this right?" friction.*

The **user approves the merge sequence**; the orchestrator executes the `wave-merge` merges per point 5. Do not proceed to the next phase until every wave→main PR is merged and the Step 11.5 reachability gate is clean.

## Wave-Wrapup Staging-Promotion Gate (Mandatory) <!-- promotion-target: skill -->

A wave is **not closeable** until its merged code has been promoted to **staging green**. This is Phase-3 end-state criterion #3 (`noorinalabs-main#325`): "/wave-wrapup requires successful stg promotion as a wave-completion criterion." The gate is the wrapup-time enforcement counterpart of the same liveness contract the deploy track exists to satisfy — code that merged to main but never reached a green staging deploy is the deploy-track analogue of the stranded-wave-branch pattern (§ the reachability gate in `/wave-wrapup` Step 11.5).

### The gate

`/wave-wrapup` Step 11.6 (immediately after the Step 11.5 reachability-to-main gate) verifies that the staging deploy is green for the wave's merged code:

1. **Workflow:** the canonical staging deploy is `noorinalabs-deploy/.github/workflows/deploy-stg.yml` (triggered by service-repo `repository_dispatch` fan-in on push, or `workflow_dispatch` for a manual redeploy). The gate inspects the latest `deploy-stg.yml` run reachable for the wave's merged commits.
2. **Block on red:** if the latest staging run concluded `failure`/`cancelled`/`timed_out`, the wave is NOT closeable. The operator fixes-forward (re-trigger the deploy, fix the regression) before re-invoking `/wave-wrapup`.
3. **Dependency-aware deferral (criterion #1):** criterion #3 is **blocked by criterion #1** (staging must exist). Until a live staging environment + `deploy-stg.yml` run history exist, the gate reports `staging-promotion gate DEFERRED — criterion #1 (live staging) not yet satisfied` and proceeds. This deferral is itself logged (so it is visible, not silent) and disappears automatically once staging is live. The gate must NOT hard-fail every wrapup before staging exists.
4. **Override (when red is acceptable):** an explicit `STG_PROMOTION_OVERRIDE_RATIONALE="<reason>"` env var lets the operator close a wave despite a red/absent staging run (e.g. staging infra is mid-migration, the wave is meta-only with no deployable surface). Rationale is required (no empty string), logged to the wrapup report, and persisted — mirroring the Step 11.5 `STRANDING_OVERRIDE_RATIONALE` mechanism.
5. **Persistence + retro hand-off:** the staging-promotion result (`success` / `failure` / `deferred` / `overridden`) is written to `cross-repo-status.json` as `wave_{M}_stg_promotion` via the shared `upsert_status_keys.py` helper, alongside the run URL. `/wave-retro` records the stg-promotion result in the wave history row next to PR count and admin overrides.

### Why a gate, not a checklist

A "remember to check staging" checklist item is opt-in and decays (`feedback_enforcement_hierarchy`: "Charter rules without enforcement decay"). Encoding the gate in the `/wave-wrapup` skill with a hard block (and a noisy, rationale-required override) makes staging-green a contractual wave-completion condition — the deploy track's whole purpose per Phase-3 end-state.

<!-- Promoted from memory: feedback_enforcement_hierarchy (hook>skill>charter — gate-over-checklist) — codifies Phase-3 end-state criterion #3 (issue #325, deploy-track-alongside Proposal B ratified 2026-05-31). Skill-tier enforcement lands in /wave-wrapup Step 11.6; a hook MAY further enforce at invocation time (follow-up). -->

## End-State Criterion Verification Requires Live-Environment Evidence (Mandatory) <!-- promotion-target: skill -->

A Phase **end-state criterion** (the `noorinalabs-main#60x`-class tracking meta-issues) may be marked **MET** only when its verification cites **live-environment evidence** — an `ssh` / `cypher-shell` query against the deployed datastore, a `curl` against the live vhost, or a Chrome/Playwright trace of the deployed app. CI-green, testcontainers, and in-process-harness results are **necessary but not sufficient**: they prove the code works, not that the criterion is true on the running system.

**Why:** P4W5 found Phase-4 end-state #1 ("data pipeline runs E2E on staging") had been treated as shipped on the strength of CI/harness runs (ingest-platform#55, main#139), while the live staging Neo4j held 47 out-of-band hadiths and **zero** narrator graph — the deployed pipeline had never run (main#601, verified by `ssh noorinalabs-stg` + `docker exec cypher-shell`). "Shipped in CI ≠ shipped on the VPS." An end-state claim backed only by harness evidence is a false exit waiting to surface a wave — or a phase — late.

**How to apply:** the auditor of a `#60x` end-state criterion records the live-env command + its output (or run URL) in the issue's verification comment (cf. #605's `users.stg.noorinalabs.com/metrics → 403` curl-proof). A criterion whose live-env check is not yet runnable (e.g. blocked by another unmet criterion) stays **OPEN and explicitly NOT-MET** — it is never marked MET on harness evidence alone, and its remediation is dispositioned (carried or re-scheduled), not silently closed.

<!-- Promoted from retro: P4W5 #601 not-met lesson (owner-approved 2026-06-13). Extends § Live-Trace Evidence > Synthetic-Test Acceptance (PR-time) to phase end-state criteria. -->

## PR Template <!-- promotion-target: none -->
```bash
git push -u origin <branch-name>
gh pr create --base deployments/phase-{N}/wave-{M} --title "<short title>" --body "$(cat <<'EOF'
## Summary <!-- promotion-target: none -->
<1-3 bullet points describing the change>

## Related Issues <!-- promotion-target: none -->
Closes #<issue-number>

## Review Checklist <!-- promotion-target: none -->
- [ ] Reviewed by another team member
- [ ] Must-fix items resolved
- [ ] Tech debt items filed as GitHub Issues (if any)
- [ ] Docs updated for the code change (README / docs/ / ontology), or a `Docs-N/A:` opt-out trailer is justified

Co-Authored-By: Firstname Lastname <parametrization+Firstname.Lastname@gmail.com>
Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

- PR title should be concise (under 70 characters).
- The body must reference the related GitHub Issue(s) with `Closes #N`.
- The submitting team member is responsible for creating the PR immediately upon branch completion.

### Documentation freshness (advisory gate — #768)

Code is the arbiter of truth for the docs: when a PR changes a **documented code surface**, the docs it implies (README / `docs/` / ontology / CLAUDE.md) are expected to move with it. The advisory `doc-freshness` gate (`.claude/lib/doc_freshness.py`, mirrored as the `Doc-freshness gate (advisory)` CI job and the `doc-freshness` pre-push hook) reports surfaces changed without a matching doc update. It is **advisory — never blocks** (it always exits 0; a heuristic freshness signal has unavoidable false-positives). When a change legitimately needs no doc update, declare it with a `Docs-N/A:` or `Skip-Doc-Check:` trailer line (the trailing colon is required) in a commit message or the PR body. Canonical rule: `ontology/conventions.md` § Ontology: code is the arbiter of truth.

## Closes-vs-Refs Disposition — Decided at Brief Time, Never Flipped <!-- promotion-target: none -->

<!-- Promoted from memory: feedback_owner_pivot_supersedes_protocol (P3W13 retro proposal #2 — #561 Closes/Refs flip-flop) -->

The `Closes #N` vs `Refs #N` disposition for an issue is determined **once, when the implementer brief is authored**, and is **not re-litigated after the PR opens or merges**.

- **`Closes #N`** — use only when the PR fully delivers the issue's entire acceptance surface. After merge to the default branch the issue auto-closes (and per `state-claims.md`, on a wave-branch merge it must be closed manually).
- **`Refs #N`** — use when the issue's acceptance includes **work beyond this PR** — most commonly an **end-state / org-wide criterion with remaining per-repo rollout**, a prod-gated runtime step, or a multi-PR sequence. The issue **stays open as the rollout tracker**; closing it is a separate, later decision.

**The rule:** if at brief-authoring time any part of the issue's acceptance will remain after this PR merges, the disposition is `Refs` from the **first** PR. Do not open with `Closes`, discover remaining rollout, and flip to `Refs` afterward — that flip is a routing change on an in-flight artifact and triggers the same supersede/re-verify churn as any other late pivot (see the Owner-Pivot-Supersedes protocol in `agents.md` and memory `feedback_owner_pivot_supersedes_protocol`).

**Origin (P3W13 #561):** the org-wide branch-protection criterion (#322) was opened with `Closes`, then flipped to `Refs` after the per-repo-rollout-remaining nature surfaced — costing the brief author multiple round-trips. Deciding `Refs` up front (because rollout to 7 repos plainly remained) would have avoided every one of them.

## Pre-Push Checklist <!-- promotion-target: none -->
Before pushing a branch and creating a PR, every engineer must:

1. **Run the repo's lint check** (`ruff check` / `npm run lint` / equivalent) — fix all errors.
2. **Run the repo's format check** (`ruff format --check` / `npx prettier --check` / equivalent) — fix any formatting issues.
3. **Run the repo's typecheck** (`mypy` / `npm run typecheck` / equivalent) — fix type errors.
4. **Run the full test suite** — `npm run test` / `make test` / equivalent. This includes unit tests AND E2E/Playwright if the repo has them. Do NOT skip tests — content changes can break test assertions.
5. **Verify branch name** — `git branch --show-current` must match `{FirstInitial}.{LastName}/{IIII}-{issue-name}`.

Pushing code that fails lint, formatting, or tests is a **minor feedback event**.

## CI Must Be Green Before Merge <!-- promotion-target: none -->
**No PR may be merged while CI is failing, even if failures are pre-existing.** If a new CI workflow is introduced and it catches pre-existing violations, those violations must be fixed before or in the same PR as the workflow addition.

- If CI is red on the target branch due to pre-existing issues, fix forward — create a predecessor PR that resolves the violations, merge it first, then merge the CI workflow PR.
- If CI is red on a feature branch, the PR author must fix the failures before requesting review.
- Merging a PR with known CI failures is a **moderate feedback event**.

**Why:** In Phase 2 Wave 1, PR #72 introduced a hook CI workflow that immediately failed on pre-existing ruff I001 lint in other files. CI went red on main because the violations weren't fixed before merge.

## Full Local⇄CI Tooling Parity + No Force-Merging Failing Checks (Mandatory) <!-- promotion-target: none -->

Two owner directives (2026-06-14, `noorinalabs-main#684`) on local-hook/CI discipline, binding on **every** repo.

### 1. Full local⇄CI tooling parity

Every repo's `.pre-commit-config.yaml` (commit-stage AND push-stage hooks together) MUST mirror the **complete** set of checks its CI enforces — not a subset. If CI runs it, a local hook must run it too: the relevant test suite, **every** linter and formatter, the type-checker, **cspell**, `actionlint`, `gitleaks`, schema/drift gates, and any other gate in `.github/workflows/`. The point is that a clean local commit/push is a faithful predictor of green CI — a partial mirror that omits (say) cspell lets a spelling failure reach CI that the developer had no local signal for.

- **Commit vs push staging is a latency choice, not a coverage choice.** Fast checks (format, lint) belong on the commit stage; heavier checks (typecheck, full test suite, cspell over the tree, actionlint) belong on the push stage. Either way, the *union* of the two stages must equal the CI check-set.
- The `.claude/lib/pre_commit_ci_sync.py` **sync-drift gate** is the machine-enforcement of this parity, and its enforcement must be **complete** — today it silently ignores check kinds it cannot classify (e.g. cspell), which is exactly the blind spot this rule closes. Closing that gap (classifying every CI kind so an unmirrored cspell/actionlint/gitleaks job fails the gate) and rolling the full-parity hook set out to every child repo is tracked by **`noorinalabs-main#684`**. Do NOT treat the current gate's silence on an unclassified kind as evidence of parity, and do NOT claim to fix the gate code under this section — that is #684's per-repo work.

### 2. No force-committing / force-pushing / force-merging failing checks

Never commit, push, or merge a PR with a **known-failing check** without explicit owner permission — and this holds **even when the failing check is pre-existing and not caused by your change**. `--no-verify` is already hard-blocked (`hooks.md` Hook 2 `block_no_verify`); this rule extends the same stance to the *outcome*: a red gate is a stop, not a speed bump.

- A pre-existing red check is **not** a unilateral "carve-out." Per § CI Must Be Green Before Merge, the path is *fix-forward* (a predecessor PR that greens the check, merged first) — never "merge through it because it was already broken."
- If a check genuinely cannot be greened in-scope (infra-dependent runtime gate, advisory-DB drift, etc.), that is an **owner decision** — surfaced with the one-line diagnosis and the evidence, not a self-granted exception. The recognized admin-merge exception classes (§ Admin-merge exception list) are the *only* pre-authorized bypasses; anything else needs explicit owner sign-off.
- **Severity:** force-merging a failing check without owner sign-off is a **moderate** feedback event (matching § CI Must Be Green Before Merge); doing so on a security-relevant gate (`gitleaks`, `security-audit`) is **severe**.

**Cross-references:** § Pre-Push Checklist (run the gates before you push), § CI Must Be Green Before Merge (fix-forward, not merge-through), `hooks.md` Hook 2 (`block_no_verify`), `agents.md` § Orchestrator checklist when spawning an implementer (the green-before-push spawn-discipline item), and the `CLAUDE.md` § Local Hooks section (full-parity + no-force restated for the orchestrator repo).

## Org-Wide Branch Protection + Admin-Merge Exceptions (Mandatory) <!-- promotion-target: none -->

Phase-3 end-state criterion #4 (`noorinalabs-main#322`): **CI failures block all merges** on every repo's default branch, org-wide — not just by team discipline, but enforced server-side by GitHub. As of W13, 7 of 8 repos (all child repos + `noorinalabs-main`) had NO branch protection and relied SOLELY on the Hook 4 comment-gate; that single-layer gap is what let the W11 batch-loop merge evade review (`feedback_batch_loop_merge_evades_pr_review_hook`). This section is the canonical spec that closes that gap; the live pilot proves it and the remaining repos adopt it per the application-status note (the spec, not a blanket apply, is the durable artifact).

This section is the **canonical ruleset spec** — the shape every repo's protection must take. It is the high-value deliverable of #322 because it resolves a real tension: GitHub's native "require approvals" counts formal reviews our team structurally cannot produce, so a naive protection rule would deadlock our merge flow. The spec below defines a shape that enforces protection *without* that deadlock.

### Application status

The spec, the hook-side admin-merge gate, and a de-risked live pilot all land in **W13** (this PR, **`Refs #322`**); the org-wide application to the remaining repos is the **W14 fast-follow**, so `#322` stays **OPEN** as the rollout tracker until all 8 repos carry the protection. Mid-wave caution: applying default-branch protection to a repo with in-flight wave-branch PRs or before the wave→main wrapup merge can block our own merges, so org-wide application is staged rather than blanket-applied in one shot.

**Pilot (W13, live):** the spec is proven live on **one** repo with no in-flight W13 PRs — `noorinalabs-data-acquisition` (ruleset id `17091263`): `~DEFAULT_BRANCH`, active, `pull_request` (0 reviews) + `required_status_checks` (strict; `Lint`, `Type Check`, `Test`, `Integration Tests`) + `deletion` + `non_fast_forward` + Repository-admin `always` bypass. Read-back-verified at origin. `noorinalabs-isnad-graph` already carried its own pre-existing protection and is untouched.

**Remaining 6 repos:** the apply is **mechanical re-creation from this spec** — `gh api -X POST repos/<repo>/rulesets --input <json>` per repo with the required-check contexts tabulated below, read-back-verified, scheduled for whenever that repo has no in-flight default-branch merge in flight (post-wrapup is the safe window). This is execution of a fully-specified plan, not open design — but it is still execution that has not yet happened, so **criterion #4 is met only when the W14 rollout has applied the ruleset to all 8 default branches**; until then `#322` stays OPEN as the rollout tracker. This PR delivers the spec, the hook, and the pilot — not the org-wide enforcement.

### The ruleset shape (and why it's shaped this way)

The ruleset each repo adopts is a **repository ruleset** targeting `~DEFAULT_BRANCH`, `enforcement: active`, with (the pilot already carries it; the remaining repos adopt it per the application-status note above):

- a `pull_request` rule with **`required_approving_review_count: 0`**, and
- a `required_status_checks` rule (`strict_required_status_checks_policy: true`) listing that repo's **unconditional PR-gate check contexts**, and
- `deletion` + `non_fast_forward` protection, and
- a single `bypass_actors` entry: the built-in **Repository admin** role (`actor_id: 5`, `bypass_mode: always`).

The load-bearing design decision is **0 required approvals, not 1.** GitHub's "require approvals" counts **formal GitHub PR reviews** — which our team cannot produce: the `gh` auth principal IS the PR author (`parametrization`), so a formal self-approval 422s (`feedback_gh_review_self_approve_422`), and our review discipline runs on **issue-comment verdicts** validated by Hook 4 (`validate_pr_review`), not formal reviews. A naive "require 1 approval" rule would therefore **deadlock every merge**. So the ruleset enforces only what it can enforce without breaking us — *a PR must exist* + *CI must be green* — and leaves reviewer-count enforcement to Hook 4, where the issue's own scope note ("Required-reviewer count beyond charter — already covered by `validate_pr_review`") puts it.

The **Repository-admin `always` bypass** is what keeps the established flow working: the orchestrator's `--admin` wave→main wrapup merges, the wave-bootstrap and doc-sweep single-reviewer exceptions, and Emergency-Mode restore merges all run as admin. The bypass is the GitHub-side counterpart to the hook-side exception list below — protection for everyone, an audited escape valve for the established exceptions.

### Two path-filtered repos require PR-before-merge only

`noorinalabs-main` and `noorinalabs-deploy` have **fully path-filtered CI** — every PR-triggered workflow carries a `paths:` filter, so a PR that doesn't touch those paths (e.g. a charter/docs-only PR) produces **zero check-runs**. GitHub treats a hard-required-but-never-reported check as perpetually pending → it would deadlock the majority of PRs in those two repos. The spec therefore assigns these two a **PR-before-merge + deletion/non-fast-forward** ruleset that does NOT hard-require status-check contexts. For these two, CI-green enforcement falls to the **`validate_pr_ci_status` hook** (which reads the live `statusCheckRollup` at `gh pr merge` time and blocks on red/pending — and, per `main#802`, on an **empty** rollup too when the repo has a covering `on.pull_request` workflow with no `paths:` filter, so an empty rollup is treated as an anomalous dropped-trigger, not green CI; a fully path-filtered repo with no such workflow keeps a warn-allow for the legitimate docs-only zero-check case) plus the admin-merge exception gate below. (Note: `noorinalabs-main`'s `commit-identity.yml` runs on every PR with no `paths:` filter, so in practice its PRs always report ≥1 check; a truly-empty rollup there is anomalous. See `state-claims.md` § Empty `statusCheckRollup` Is Hard Not-Ready for the readiness-claim discipline and the `.claude/lib/pr_ci_state.py` oracle.) The five remaining repos (data-acquisition, user-service, design-system, landing-page, ingest-platform) have unconditional PR CI, so the spec assigns them a ruleset that DOES hard-require their gate contexts. The per-repo required-check contexts the W14 rollout will apply:

| Repo | CI posture | Required check contexts (strict) |
|---|---|---|
| data-acquisition | unconditional PR CI | `Lint`, `Type Check`, `Test`, `Integration Tests` |
| user-service | unconditional PR CI | `check`, `openapi-snapshot-drift` |
| design-system | unconditional PR CI | `ci (20.x)`, `validate-package` |
| landing-page | unconditional PR CI | `Lint, Type Check & Build`, `E2E Tests (Playwright)` |
| ingest-platform | unconditional PR CI | `lint-and-typecheck`, `security-audit`, `test` |
| **noorinalabs-main** | path-filtered | (none — PR-before-merge only) |
| **noorinalabs-deploy** | path-filtered | (none — PR-before-merge only) |

(Contexts enumerated from each repo's default-branch check-runs at 2026-05-31; the rollout re-confirms them at apply time, since a repo's CI job names can change.)

### Admin-merge exception list (hook-validated)

`--admin` is no longer a silent bypass. `validate_pr_ci_status` blocks a `gh pr merge --admin` unless the operator declares a **charter-listed exception** via `ADMIN_MERGE_EXCEPTION="<class>:<rationale>"`. The `<rationale>` is required (non-empty) and **logged to the Annunaki audit trail** so each admin merge is reviewable at retro time (the issue's "auditable + reviewed at retro time" / "0 admin overrides per wave is a measured indicator"). The recognized classes:

| Class | Charter source |
|---|---|
| `wave-bootstrap` | § Single-Reviewer Exception (Wave-Bootstrap Only) |
| `doc-sweep` | § Trivial Cross-Repo Doc Sweep |
| `wave-merge` | the wave→main wrapup merge (orchestrator-merged) |
| `emergency` | `emergency-mode.md` § Allowed bypasses (`[EMERGENCY]`-prefixed) |

An absent or unrecognized exception **blocks** (fail-safe per `feedback_safety_direction_over_ux_friction`). Adding a class here requires adding the matching entry to `_CHARTER_ADMIN_EXCEPTIONS` in the hook — the two are kept in lockstep.

**Why:** criterion #4 closes the silent-bypass class directly via two complementary gates. The ruleset is the server-side gate (covers UI merges, external actors, the batch-loop-evasion class); the hook is the operator-side gate (covers `gh pr merge`, names the exceptions, writes the audit trail). Defense in depth — neither alone is sufficient, because the ruleset's admin bypass would otherwise be unaudited and the hook alone doesn't cover non-`gh`-CLI merges. The hook-side gate is **active now** (this PR); the server-side ruleset is **active on the pilot now** and rolls out org-wide in W14 per the rollout-status note above. Note the two gates are mutually reinforcing on the apply order: because the hook already requires `ADMIN_MERGE_EXCEPTION` for `--admin`, the W14 rollout can apply default-branch rulesets without the admin-bypass becoming an unaudited hole the moment it exists.

## CI Enforcement After PR Creation <!-- promotion-target: skill -->
After creating a PR, **every team member** must follow this process:

1. **Wait for all CI jobs to complete.** Do not merge or request review until CI has finished.
2. **If all CI jobs pass:** The PR is ready for review. Proceed with the normal review workflow.
3. **If any CI job fails:**
   - Investigate the failure and attempt to fix the root cause.
   - Push the fix to the **same branch** (the PR will update automatically).
   - Alert the project owner (user) with the following information:
     - Which CI job failed
     - Root cause of the failure
     - What was done to fix it
     - Whether project owner assistance is required
4. **If the failure cannot be resolved:** Do **NOT** merge the PR. Notify the project owner immediately and pause all dependent work until the issue is resolved.

Violating this process (e.g., merging with red CI, ignoring failures, or failing to escalate) is treated as a **moderate feedback event** per the Feedback System.

## Design-Rationale Block for Critical-Path PRs (Mandatory) <!-- promotion-target: skill -->

PRs that touch critical-path workflow DAGs, observability stacks, or alert-rule definitions MUST include a design-rationale block at the load-bearing decision point.

### When this requirement applies

- PRs touching `.github/workflows/promote.yml`, `deploy-stg.yml`, `deploy-prod.yml`, or any other workflow whose failure-mode propagates to prod gates.
- PRs touching `infra/prometheus/alerts.yml`, `infra/prometheus/prometheus.yml`, blackbox/textfile-exporter configs, or any other observability artifact whose silence vs. firing has operator consequence.
- PRs introducing a new gate, predicate, or DAG ordering whose correctness depends on a specific multi-path outcome matrix.

### What the block must contain

- Either an inline file comment at the gate/predicate/decision point (preferred when the rationale binds to a specific code site), OR a section in the PR body labeled `Design rationale` / `Outcome matrix` / `Sequencing rationale`.
- A walk of the predicate algebra OR an outcome truth table OR a design-rationale-vs-alternatives comparison — whichever load-bears the decision.
- Citations to the issue body's spec (or a `Reality post-#N` mapping if the spec has drifted from current state).

### Worked examples (Phase 3 Wave 1)

- `noorinalabs-deploy#198` lines 232-258 — gate-stg-verify rationale block walking three failure modes (missing artifact, stale artifact, schema-version mismatch).
- `noorinalabs-deploy#201` PR body — 5-path retag-gate truth table (success/skipped/failure crosses + break-glass).
- `noorinalabs-deploy#208` `infra/blackbox-exporter/blackbox.yml` — load-bearing assertion comments per module.
- `noorinalabs-deploy#210` `infra/prometheus/alerts.yml` — dual-alert design comment (Failure vs Stale split rationale).

### Reviewer enforcement

Absence of a design-rationale block on an applicable PR is grounds for Changes-Requested. The block's quality (rather than its mere presence) is what reviewers should engage with.

### Severity if violated

Minor — but recurrence is moderate. The discipline is high-leverage for incident-response readability and retro-evidence quality; both pay dividends across multiple waves.

### Why

Phase 3 Wave 1 produced 4 corroborating data points (above) where the design-rationale block earned positive reviewer engagement, surfaced design alternatives during review, and provided the canonical retro evidence later. Without it, gate-DAG correctness is invisible to anyone reading the PR after merge.

<!-- Promoted from memory: feedback_review_against_artifact_not_framing.md (P3W5 retro 2026-05-06; reviewer-side). The implementer-side data points (#161, #206 Reality-post-#87) predate the dedicated memory and were the original founding examples; the memory codified the reviewer-side counterpart, which this section now incorporates. -->

## Trust the Artifact, Not the Framing (Mandatory) <!-- promotion-target: skill -->

Both implementer and reviewer disciplines on the same axis: verify spec assumptions and PR-body framing against ground truth before action.

### Implementer side

Before implementing per a spec, issue body, or upstream brief, verify the spec's load-bearing claims against the actual artifact:

- Issue body says "alert exists at X / read it, don't re-implement" → check `git log -- X` and `grep` the file before assuming.
- Spec says "extend Y to add Z" → check Y's current shape (post-prior-merges) before drafting; the spec may predate later changes.
- Brief from manager says "use convention K" → check `git branch -a` / `git grep` for K-shaped artifacts before encoding it as truth.

If the spec's load-bearing claims diverge from ground truth, surface the gap to the manager BEFORE implementing — do not silently absorb the divergence.

**Authoritative example:** `noorinalabs-deploy#161` 3-x scope catch (issue body said alert exists at `#153`, alert had been deferred and never landed; verified via `git log` + `grep` before pushing dead code).

### Reviewer side

Read the diff against the actual artifact (Caddyfile, compose env-vars, terraform state, alert YAML, runbook, etc.), not against the PR body's framing of what the diff does. PR-body framing is a useful navigation aid; the diff against the artifact is the ground truth.

**Authoritative example:** `noorinalabs-deploy#206` review caught a false-positive bug by walking `caddy/Caddyfile` lines 88-89 + 101 against the PR's section 3b dual-route logic. The PR-body framing said "user-service /health probe via Caddy rewrite + post-#156 subdomain fallback"; the artifact showed the fallback would route to isnad-graph instead of user-service, producing a silent false positive on user-service availability if user-service goes down.

#### Confirm the PR head SHA before posting any verdict

Reading the diff against the artifact only proves anything if you read the artifact at the SHA you are about to certify. Before posting Approved or ChangesRequested, the reviewer MUST record and confirm the PR head SHA they reviewed:

```bash
gh pr view <N> --repo <owner>/<repo> --json headRefOid --jq .headRefOid
```

State that SHA (or the short form) in the verdict so the certification is anchored to a concrete head, not to "the PR" as a moving target. Then:

- **If the PR is rebased or force-pushed after your verdict**, the prior verdict is **stale** — it certified a head that no longer exists. It must be re-confirmed against the new head before it counts toward merge; a materially-changed diff requires a fresh read of the changed surface, not a carry-over of the old Approved. (This is the reviewer-facing companion to § Additive-Commits-Only on ChangesRequested Cycles, which keeps the head anchor stable so this re-confirmation is rarely needed.)
- **Before posting ChangesRequested**, confirm the line(s) you are blocking on exist at the head SHA — not in a stale local checkout. A "still has X" block sourced from a local working tree that lags the head is a false positive (per § Origin > Local Clone for "Still-Has-X" File-Content Claims).

**Authoritative examples (P4W6):** `noorinalabs-isnad-graph#1020` was rebased *after* approval — the head SHA changed and the diff changed materially; the author proactively flagged it and the approval was correctly re-verified against the new head rather than carried over. Conversely, `noorinalabs-ingest-platform#85` drew a ChangesRequested that turned out to be a stale-tree misread (the reviewer judged a phase-3/wave-11 working tree, not the PR head), costing a critical-path re-verify cycle — a head-SHA confirmation step at verdict time would have caught it before the block was posted.

### How to apply

- **Implementer:** before any Edit/Write inside a worktree, run `gh issue view`, `git log -- <load-bearing-path>`, and `grep` for any spec claim about existing artifacts.
- **Reviewer:** confirm the PR head SHA (`gh pr view <N> --json headRefOid`) and state it in the verdict, then walk at least one load-bearing claim in the PR body against the actual artifact at that SHA via `gh api .../contents/<path>?ref=<head_sha>` or `git show <head_sha>:<path>`. If the head moves after your verdict (rebase/force-push), re-confirm before it counts toward merge.

### Severity if violated

- Implementer: silent absorption of a spec-vs-reality gap that produces dead code or wrong defaults is minor; producing a security regression (route mismatch, env-var leak, etc.) is severe.
- Reviewer: rubber-stamping based on PR-body framing alone is minor; missing a false-positive bug because reviewer read the framing but not the artifact is moderate. Posting a verdict with no head-SHA anchor that then goes stale on a post-verdict rebase and is carried over to merge, or blocking on a line that does not exist at the head (stale-local-tree misread), is moderate.

### Why

Phase 3 Wave 1 produced 4 corroborating data points across two roles. Implementer side: `#161` scope catch + `#206` Reality-post-#87 mapping table. Reviewer side: `#206` Caddyfile evidence-receipts. Both halves of the same discipline.


## Trivial Cross-Repo Doc Sweep

When a single doc-sync change must land identically in N>1 child repos (e.g., backslash→slash path corrections, broken-URL fixes, copyright-year updates, identical CLAUDE.md sentence sync), a **Single-Reviewer Exception** is granted per child PR provided ALL of the following hold:

1. **Byte-identical diff** — every child PR's diff is byte-identical to every other (verifiable via `git show <pr-head>:<path> | diff -`). Per-repo adaptations (different branding, different file paths) DO NOT qualify; those go through standard 2-reviewer review.
2. **No behavior change** — change is doc/comment-only OR a configuration sync that produces no runtime difference.
3. **Tracking-issue link** — every child PR references one parent tracking issue in `noorinalabs-main` that enumerates all child PRs.
4. **CI green on every repo** — no CI failures across the sweep; one red CI revokes the exception for the whole sweep.

A sweep PR uses the same charter-format comments and TechDebt line as standard PRs. When the exception is invoked, the PR body must include a "Sweep:" line citing the tracking issue and the byte-identical-diff verification command.

**See also:** § Single-Reviewer Exception (Wave-Bootstrap Only) — a separate single-reviewer exception class for tooling/CI/hook-rollout PRs that gate subsequent wave work. The two exceptions are **independent budgets** (the wave-bootstrap 1-per-wave cap does not consume, and is not consumed by, doc-sweep waivers) and are **not cumulative** — a single PR may invoke at most one.

**Why:** P3W4 ran 4 separate per-repo PRs for an identical 1-line CLAUDE.md slash sync (isnad-graph#857, user-service#94, design-system#63, data-acquisition#34) — 4 review pairs, 4 CI runs, ~12 charter-format comments for a no-decision change. The 2-reviewer requirement is load-bearing for behavior changes; for byte-identical doc sweeps, the verification value is concentrated at the parent tracking issue, not at each child PR.

**Severity if violated:** Invoking the sweep exception on a non-byte-identical change, or skipping the tracking issue, is moderate (review-bypass for changes that needed standard review). The 2nd reviewer is the load-bearing safeguard against silent behavior change.

<!-- Promoted from memory: feedback_security_guard_inline_not_followup.md (P3W5 retro 2026-05-06) -->

## Security Guards Belong Inline, Not in a Followup (Mandatory) <!-- promotion-target: skill -->

When reviewing a PR whose security model depends on a runtime guard — env check, scheme restriction (`{http,https}` whitelist), HTTPS-required-outside-test, startup assertion, URL rewriter, auth bypass flag — the guard MUST ship in the same PR. Filing a TechDebt followup issue is a legitimate review artifact (paper trail in case the guard ever regresses), but it is **not a substitute** for the inline guard.

### Reviewer protocol

When the threat model requires a runtime guard:

1. **Post `Changes Requested`**, even if a followup issue exists for the guard.
2. **File the followup BEFORE posting the review comment** so the comment can cite `TechDebt: #N` cleanly.
3. **Frame the ask as:** "Resolve inline; close the followup with the fixup SHA referenced from this PR." The followup is a tracking artifact, not a fix.
4. **Approve only after** the inline guard lands. Acceptable shapes for the guard: env-gate that refuses-to-boot in prod, scheme whitelist, HTTPS-required-outside-test assertion, startup-time check that fails fast, URL-rewriter input validation.

### What this rule applies to

- Environment gates (prod/staging refuse-to-boot under override paths)
- Scheme whitelists (`{http,https}` restrictions on user-controlled URLs)
- HTTPS-required-outside-test assertions
- Startup-time security assertions (boot fails if config is unsafe)
- URL rewriters / proxy redirects (input validation)
- Auth bypass flags (e.g., `OAUTH_PROVIDER_BASE_URL_OVERRIDE`-class knobs)

Docstring warnings, code-comment cautions, and "remember to set X in prod" notes are NEVER sufficient for these.

### What this rule does NOT apply to

- Defense-in-depth hardening that doesn't change the threat surface
- Log-level tuning, observability additions
- Doc updates that describe existing behavior
- Refactors that preserve threat model

These are legitimate followups when the inline change is already safe.

### Severity if violated

- Reviewer Approves a PR with a deferred runtime guard, no inline safeguard: **severe** (silent regression window between merge and followup-fixup).
- Implementer ships a knob without the guard, even if a followup is filed: **moderate** (the followup is paperwork; the threat surface is open until the guard lands).

### Worked example

`noorinalabs-user-service#77` (`OAUTH_PROVIDER_BASE_URL_OVERRIDE`, 2026-04-21). Reviewer filed followup #78 proposing a prod-environment guard + HTTPS-outside-test requirement, and posted `Changes Requested`. Mateo landed both inline in fixup `1104104`; #78 closed same day. Team-lead's verdict: "shipping the env-gate + HTTPS requirement inline rather than deferring to #78 was the right call." Deferring would have left a window where a prod misconfig could exfil `client_secret` via `/token` POSTs with no backstop.

<!-- Promoted from memory: feedback_live_trace_over_synthetic_acceptance.md (P3W9 #346 memory audit, 2026-05-10) -->

## Live-Trace Evidence > Synthetic-Test Acceptance (Mandatory) <!-- promotion-target: skill -->

When validating a new gate (CI hook, security check, alert rule, validation logic), prefer **live-trace evidence** — the gate firing on a real, in-the-wild triggering artifact — over **synthetic-test acceptance** — the gate passing on test cases authored alongside the gate.

### Why

Synthetic tests prove the gate handles the cases the author *imagined*. Live-trace proves the gate handles the cases the *world produces* — which routinely diverge from the author's mental model. Synthetic tests can be written to pass; live-trace evidence can't be retroactively shaped to fit. The gate either fires correctly on the wild artifact or it doesn't.

### How to apply

- **For PR-time gates (CI hooks, validators, lint rules):** identify the most-recent failed real PR (not a synthetic one) and demonstrate the gate's verdict on that PR. Reference the failed run by URL or sha in the PR body. If you cannot find a recent in-the-wild failure, that is itself a signal — the gate may need a longer observation window before high-confidence acceptance, or its scope may be too narrow to be worth shipping.
- **For runtime gates (alerts, monitors, startup assertions):** capture the gate firing on a real production event (alert firing, monitor crossing threshold, boot-time assertion tripping). Reference the firing artifact (alert ID, run ID, log entry, sha range) in the PR body or evidence package.
- **Document the live-trace explicitly** in PR review evidence — reviewers can verify the artifact independently. Synthetic tests remain valuable as a regression floor; they just don't substitute for live-trace.

### Reviewer enforcement

When reviewing a new gate, ask "what wild artifact did this fire on?" If the only acceptance evidence is the gate's own test fixtures, request a live-trace before approving (Changes Requested if no live-trace exists; tech-debt followup if a live-trace is achievable but deferred to next wave).

### Severity if violated

- Implementer ships a gate with synthetic-only acceptance: **minor** (the gate may still be correct; the discipline gap is in evidence quality).
- Reviewer rubber-stamps a gate without asking for live-trace: **minor**, **moderate** if recurring across a wave.
- Gate ships with synthetic-only acceptance and silently misclassifies a wild artifact post-merge: **moderate** (the missed live-trace would have caught the misclassification before merge).

### Worked example

`noorinalabs-main#194` Hook 14 (`validate_pr_ci_status.py`) fan-out, 2026-04-28. Marisol's PR landed the strongest acceptance signal across the entire fan-out series by **live-tracing `classify_check` against an actual in-flight failed security-audit CI run** at the time — not against a fabricated failure. The live-trace caught a behavior pattern that synthetic tests would have missed because the author didn't think to test for it. Aino flagged this as the strongest acceptance proof in the entire fan-out — distinct enough that it materially changed Hook 14's confidence floor.

## Text-Processing / NER / Graph Fixtures Must Use Production-Realistic Input (Mandatory) <!-- promotion-target: hook -->

Fixtures for **Arabic text processing, NER / segmentation, and graph-load invariants** MUST be derived from **real upstream samples** — never hand-authored from a schema that matches the parser's own assumptions, and never simplified into toy strings. A fixture that is *greener than real data* is masking a bug.

### The rule

- **Voweled (vocalized) Arabic** matching real corpus text — never un-voweled toy strings. Text-processing and segmentation logic behaves differently on vocalized input; a fixture stripped of diacritics exercises a code path the production corpus never takes.
- **Real high-frequency structures.** An isnad-chain fixture MUST contain the high-frequency transmission particle عن (ʿan) AND at least one narrator name carrying an عن / قال substring — e.g. عنبسة (ʿAnbasa), معن (Maʿn), مقالة (maqāla). These are exactly the strings a naive segmenter over-splits; omitting them lets an over-segmentation bug pass.
- **Real-shape rows.** Use the actual upstream column set / schema (a captured sample row), not a minimal hand-built dict. A fixture authored from the parser's assumed schema validates the assumption, not the data.
- **Parse-path tests run against real-upstream fixtures.** The test that exercises the parse / NER / graph-load path asserts against a sample lifted from the real source, so the test fails when the parser's model of the source is wrong.

### Why (the recurring class)

The **fixture-masks-bug** class has recurred 5+ times, most damningly *inside its own fix*: da#146 (PR #151) replaced an un-voweled toy blob — but its Bukhari-h1 replacement fixture contained no عن, masking a new over-segmentation surfaced only later as da#155. The same shape recurred again in P5W5: da#175's thaqalayn (al-Kafi) parser shipped a fixture matching an *assumed* schema rather than the real upstream, so 0% extracted Arabic text went undetected. Earlier instances: `MockNeo4jClient` masking the APPEARS_IN null-property loader bug; toy h-1 fixtures masking the double-prefix hadith-id bug; local-only staging edges. The defect is always the same — the fixture encodes the author's mental model of the source instead of the source itself, so the test is green and the parser is wrong.

This is the **input-side companion** to § Live-Trace Evidence > Synthetic-Test Acceptance: that rule says a gate's *acceptance* must be proven on a wild artifact; this rule says a parser's *fixture* must be lifted from one.

### How to apply

- When adding or changing a text-processing / NER / graph-load fixture, **lift the bytes from a real upstream sample** (a real hadith / isnad / rijāl row from the actual source) and commit that, not a minimal reconstruction. Note the provenance (source + identifier) in a comment or the test docstring.
- If the real sample is large, trim it to a representative slice — but preserve vocalization, the عن particle, and at least one عن/قال-substring narrator name. Trimming MUST NOT make the fixture greener than the source.
- Never author a fixture from the schema you *expect* the parser to consume; capture what the source actually emits and let the test prove the parser matches it.

### Reviewer enforcement

When reviewing a PR that adds or edits one of these fixtures, ask: **"was this lifted from real upstream, or authored to match the parser?"** If the Arabic is un-voweled, if the chain lacks عن, or if the row is a minimal hand-built dict, request the real-sample fixture before approving (Changes Requested). A fixture whose only virtue is that it passes the new code is not acceptance evidence.

### Enforcement opportunity

A lint / review-lens can flag Arabic-text fixtures that lack vocalization marks (no Arabic diacritic codepoints `ً–ْ`) or whose isnad strings lack عن — a cheap static signal that a fixture is a toy. Tracked as the optional half of #671; the charter rule is the floor, the lens is a plus.

### Severity if violated

- Shipping a text-processing / NER / graph fixture that is hand-authored from the parser's assumed schema or stripped of vocalization: **moderate** (it actively masks the next bug in that path — the failure mode that recurred 5+ times).
- Reviewer approving such a fixture without asking for the real-upstream sample: **minor**, **moderate** if it lets a masked bug merge.

### Worked example

da#146 / PR #151 (fix), da#155 (the bug it masked), 2026-06: the fix for an un-voweled-toy-fixture bug shipped a replacement Bukhari-h1 e2e fixture with no عن, masking a fresh over-segmentation. Surfaced independently by Alejandra Reyes-Fuentes and Jean-Claude Habimana on PR #151. The class recurred in P5W5 on da#175 (thaqalayn / al-Kafi), where a schema-assumed fixture hid 0% extracted Arabic — the recurrence that motivated codifying this rule (owner-adopted P5W1 retro, main#671).

<!-- Promoted from memory: feedback_pr_vs_runtime_acceptance_criteria.md (P3W9 #346 memory audit, 2026-05-10) -->

## PR-Time Acceptance vs Runtime Acceptance (Mandatory) <!-- promotion-target: none -->

When a fix lands a PR for an issue that ALSO has a runtime gate (e.g., "one successful end-to-end backup before DNS-flip", "first deploy succeeds without manual intervention", "CI green on first run after credential rotation"), distinguish the two lifecycle positions:

- **PR-acceptance criteria** — code-correctness, unit-mechanic correctness, hardening, scoped local validation. Reviewable in PR comments. Lives in PR review scope.
- **Runtime-acceptance criteria** — operational events firing on real infrastructure that may not exist yet. Lives in cutover / runbook / operational scope. Verified post-merge in production-event flow.

### Failure modes if conflated

1. **Blocks PR on infrastructure that doesn't exist yet** — e.g., demanding "B2 object key proof of successful upload" from a PR fixing the backup unit, when the new prod box hasn't been provisioned and there's no compose stack to back up. The PR then either waits indefinitely OR is blocked by an irrelevant external dependency.
2. **Forces synthetic-evidence fakery** — implementer fabricates fake "proof" (stub creds, mock invocations) to satisfy reviewer demand for evidence that can't legitimately exist yet. Worse than no proof: it masks the real runtime gate when it fires.

### How to apply

- When scoping a PR for an issue that has a runtime gate, write the PR's Test Plan as **two sections**:
  1. **Pre-merge validation** (PR-acceptance) — what the reviewer can verify from the diff + CI + author's local validation.
  2. **Post-merge validation** (runtime-acceptance) — what fires after merge in production flow, NOT required for merge.
- If a reviewer asks for runtime evidence in PR review, push back: "that gate fires at lifecycle position X (e.g., post-compose-up on new TF-prod box); cannot legitimately exist at PR-review time. Documented in post-merge Test Plan section."
- If a runtime gate is a genuine wave-acceptance criterion, file a SEPARATE issue tracking the runtime gate (not the code fix). The code fix's PR closes its own issue; the runtime gate's issue closes on its own runtime-event trigger.

### Provider-validated expressions are apply-time acceptance (added P3W11 retro 2026-05-24)

Some IaC providers validate field values only at **apply**, not at plan. Cloudflare Ruleset `target_url` / filter (wirefilter) expressions are the canonical case: `terraform plan` shows a clean diff for a syntactically-malformed expression, and the provider rejects it only when `apply` calls the API. Therefore **a green plan + a clean two-reviewer pass cannot certify expression correctness** — the apply is the validation gate.

- For PRs touching provider-validated expressions, the reviewer's Approved verdict certifies code/diff/plan correctness ONLY; expression validity is an explicit **post-merge, apply-time** acceptance line in the Test Plan.
- Where feasible, add a pre-apply check (a CI step exercising the expression against the provider's validation endpoint, or a documented `terraform apply` in a non-prod scope) so the failure surfaces before the prod apply.
- Do not claim "verified" on a clean plan alone for these fields.
- Worked example: `noorinalabs-deploy#349` (P3W11) passed plan + two reviews but failed at apply — `target_url` used `if()`/`len()`, unsupported in CF's redirect expression language ("unknown identifier", apply-time only). Fixed in #350.

### Adjacent to layer-separation

This is the **lifecycle-separation** companion to the **layer-separation** discipline encoded by the multi-layer-gap-filing memory: both are about respecting boundaries when scoping work. Multi-layer says "different layers of one root cause = separate issues." This says "different lifecycle positions of one acceptance criterion = separate scope (PR vs runtime), not bundled."

### Severity if violated

- Reviewer demands runtime evidence in PR scope and implementer concedes by fabricating synthetic proof: **moderate** (synthetic substitute masks the real gate when it fires).
- Implementer bundles runtime-acceptance criteria into PR-acceptance Test Plan, blocking merge on infrastructure that doesn't exist: **minor**, **moderate** if it blocks a wave.
- Reviewer correctly distinguishes and pushes back on conflation: positive feedback event.

### Worked example

`noorinalabs-deploy#121` / PR #187, 2026-04-28. The PR fixed `isnad-backup.{service,timer}` (3 + 2 stacked bugs). `noorinalabs-main#212` cutover-gate required "one successful end-to-end backup within 24h of first compose-up before DNS-flip." Aisha's spawn brief asked for "B2 object key proving end-to-end success" as PR evidence. Aisha correctly DEFERRED that evidence to post-compose-up runtime, documented what she CANNOT validate (no docker-compose stack on stg = `docker compose ps` preflight refuses to proceed = no B2 path reached), shipped unit-mechanic correctness, and added an explicit post-merge Test Plan step for the runtime gate. Bereket endorsed the deferral as canonical: "fix landing now, gate firing later" is the right shape.

## Sandbox Test-Verification Pattern — Unit-Construct + Cite-CI When the Suite Hangs (Mandatory) <!-- promotion-target: none -->

The dev sandbox has **no local backing services** (Neo4j/Postgres/Redis bolt + frontend resolve only inside the cluster — see memory `project_staging_neo4j_frontend_unreachable_from_sandbox`). A test whose fixture spins up the app (FastAPI `TestClient` lifespan, DB-connected `client` fixture) will **block on a connection attempt that never completes** — it presents as "still running," not as a failure, so it silently burns wall-clock.

### How to apply

- **If the full suite hangs**, do NOT keep waiting on it. Verify the changed logic via a **targeted unit check that needs no app/DB startup** — construct the model/function directly and assert behavior — then **cite the green CI job** (which runs with real services) as the suite-pass evidence in the PR / review.
- **Reviewers:** a verdict may rest on "direct unit verification + green CI `test` job" when a local full-suite run is environmentally infeasible; say so explicitly. Do not demand a completed local suite run that the sandbox cannot produce (companion to § PR-Time Acceptance vs Runtime Acceptance — environmental infeasibility, not deferral).
- **`uv run` gotcha:** prefer invoking the tool through the resolved venv (`.venv/bin/pytest`, `.venv/bin/ruff`, `.venv/bin/mypy`) over `uv run <tool>` — `uv run` can stall on venv lock-contention behind a hung sibling process, compounding the hang.

### Severity if violated

- Burning a long wait on a hung full-suite run instead of unit-constructing + citing CI: **minor** (wasted wall-clock).
- Claiming "tests pass" from a run that actually hung (never reached a terminal state): **moderate** — that is an unverified claim; cite the CI job or the direct unit check, not a hung local run.

### Worked example

P5W2 (#1024 / PR #1045, #1048 diagnosis): `pytest tests/test_api/test_narrators.py` ran 14 min at 0.4% CPU / 163 MB RSS — hung on the `client` fixture's app-startup DB connect, not computing. Resolution: constructed `NarratorResponse` directly from a sparse `{id, name_ar}` dict to prove the fix (+ ran `ruff`/`mypy` via `.venv/bin`), and cited the green CI `test` job. Marisol independently hit the same ~9-min stall and correctly cited CI rather than a completed local run.

## Close Runtime-Gated Issues on Verified-Live, Not on Merge (Mandatory) <!-- promotion-target: none -->

When an issue's real acceptance is a **gated production apply or live behavior** (the runtime-acceptance half of the section above), the PR that implements it MUST reference the issue with `Refs #N`, NOT `Closes #N`. The orchestrator closes the issue manually **after** the post-merge apply succeeds and the live behavior is verified.

### Why

`Closes #N` fires on default-branch merge — which is BEFORE the gated apply runs (the apply is a separate, environment-approval-gated push-to-main run). Merge ≠ live. An auto-close on merge produces a closed-but-not-done issue when the apply then fails or is still pending approval.

### How to apply

- PR body uses `Refs #N` for runtime-gated issues; `Closes #N` is reserved for issues whose acceptance is fully satisfied at merge (code/CI).
- After merge → gated apply → live verification, the orchestrator closes #N with the apply result + live-verification evidence (e.g. apply summary + `curl -sI` output) in the close comment.

### Severity if violated

- `Closes #N` on a runtime-gated issue auto-closes it on merge before the apply runs: **minor** if caught and reopened same-session; **moderate** if it ships a closed-but-broken issue into the backlog.

### Worked example

`noorinalabs-deploy#348`, 2026-05-24. PR #349 merged with "Closes #348" → #348 auto-closed on merge, but the prod apply then FAILED (apply-time CF expression rejection). Had to reopen #348. The fix PR #350 used "Refs #348"; #348 was closed only after the apply succeeded (`0 added / 2 changed / 0 destroyed`) and `curl` confirmed live 301s on `.net`/`.org`.

<!-- Promoted from memory: feedback_cf_plan_not_validate_expr_and_close_on_verified_live.md (P3W11 retro, 2026-05-24) -->

<!-- Promoted from memory: feedback_origin_over_local_for_still_has_claims.md (P3W9 #346 memory audit, 2026-05-10) -->

## Origin > Local Clone for "Still-Has-X" File-Content Claims (Mandatory) <!-- promotion-target: none -->

When asserting a "still has X" / "still at Y" / "still missing Z" property about a PR's file content, query origin directly via `gh api repos/<owner>/<repo>/contents/<path>?ref=<head_sha>` (or `gh api .../pulls/<N>/files`). Do NOT grep a local checkout, worktree, or `/tmp/` clone of the PR branch.

### Why

Local clones are point-in-time snapshots — frozen the moment they're created and stale the next push that lands. In high-churn cycles (active multi-implementer wave work), a clone made N minutes ago can be N commits behind origin. Asserting "still has X" against the local snapshot generates a false-positive Changes-Requested that confuses the implementer and forces a counter-correction.

This is the file-content-assertion specialization of the umbrella state-verification discipline encoded in `state-claims.md § Refresh State Before Claim`. That section governs top-line PR/issue state via `gh pr view --json state,...`. This rule extends the same discipline to per-path file content via `gh api .../contents`.

### How to apply

- For any "PR still has bug Y" / "file <path> still does Z" / "removal didn't land" assertion, fetch the file at the PR head:
  ```bash
  HEAD_SHA=$(gh pr view <N> --repo <owner>/<repo> --json headRefOid --jq .headRefOid)
  gh api "repos/<owner>/<repo>/contents/<path>?ref=$HEAD_SHA" --jq '.content' | base64 -d
  ```
- Refreshing a local checkout via `git fetch && git checkout <head_sha>` before grep is acceptable but takes more steps; direct `gh api repos/.../contents/<path>?ref=<head_sha>` is one call.
- Most acute in **high-churn cycles** where commits land in the few-minute window between cloning and asserting.

### Reviewer enforcement

When a reviewer's review-comment cites "still has X" / "still missing Y", the comment must either include the `?ref=<head_sha>` query or be re-verifiable by another reviewer via that query. Local-checkout-grep claims that produce a false-positive Changes-Requested are correctable on the next refresh; if the implementer counter-verifies via `gh api ... contents` and demonstrates the change has landed, the original review-comment must be revised (not silently abandoned) — paper trail matters.

### Severity if violated

- Single false-positive Changes-Requested from local-checkout staleness: **minor**, paper-trail correction required.
- Recurring across a wave: **moderate** (signals the discipline isn't being applied; consumes implementer cycles on counter-corrections).
- Local-checkout-grep used to assert a security-relevant claim ("PR still missing the auth guard") that turns out to be wrong: **moderate-to-severe** depending on whether the false-positive blocks a real fix from landing.

### Worked example

`noorinalabs-deploy#181` / Bereket → Lucas-87, 2026-04-28. Lucas pushed `c0b65e2` addressing Weronika's 3 blockers. Bereket cloned PR #181 branch to `/tmp/pr181-v2/` at HEAD `c0b65e2`. Lucas then pushed `3c7ee55` adding Nurul's 2 nits (junit-dup + schema_version). Bereket's "ready for re-review" message arrived AFTER `c0b65e2`, BEFORE `3c7ee55`. Bereket grep'd `/tmp/pr181-v2/` (still at `c0b65e2`) and reported "still has the duplicate junit-xml" — false positive. Lucas had to counter-verify via `gh api ... contents/...?ref=3c7ee55` and demonstrate the fixes were already there. Local clone was correct *at the time it was cloned*, but stale by the time the assertion was made.

### Cross-references

- `state-claims.md § Refresh State Before Claim` — top-line state-verification umbrella; this rule is the file-content specialization.
- `pull-requests.md § Trust the Artifact, Not the Framing` — companion: read the artifact at HEAD, not the PR-body framing. Both rules converge on the same access primitive (`gh api ... contents/?ref=<head_sha>`).

<!-- Promoted from memory: (none — this section codifies retro-PR-diff discipline; sourced from #126 + W8 PR #124 incident) -->

## Retro PR Body-vs-Diff Discipline (Mandatory) <!-- promotion-target: skill -->

The retro PR is the **authoritative artifact** for a wave's ratified changes. If the retro accepts charter, skill, or trust-matrix updates, those file edits MUST land **in the retro PR's diff** — not via direct-to-main commits committed alongside.

### Why

The retro PR is where future reviewers, audits, and `git log --first-parent main -- .claude/team/charter/` trace **wave theme → ratified charter changes → trust updates**. Direct-to-main commits for substantive retro outputs break that trace and bypass two gates the charter relies on:

1. **The two-reviewer rule** (`pull-requests.md § Comment-Based Reviews`) — direct-to-main commits skip review entirely. No `RequestOrReplied: Approved` comments, no `validate_pr_review` hook gate, no peer scrutiny of the charter/skill text that future agents are bound by.
2. **`validate_pr_ci_status`** (`hooks.md § Hook validate_pr_ci_status`) — no PR means no CI gate, so charter/skill edits land without `hooks-lint`, schema validation, or any other automated check that the PR path would have run.

The audit-trail break is the more durable harm: a ratified charter section with no PR linkage looks identical, six months later, to a charter section someone slipped in unreviewed. The retro PR body claiming files that aren't in the diff makes the mismatch worse — it manufactures the appearance of review for changes that received none.

### How to apply

**For retro-PR authors:**

- **In-scope for the retro PR diff:** every charter, skill, trust-matrix, or memory file the retro ratified, plus the `feedback_log.md` narrative and `ontology/checksums.json` resolution. Edit on the retro branch; commit; push; let the diff land via the PR.
- **Out-of-scope for direct-to-main:** ratified charter/skill/trust-matrix changes. There is no "small enough to land direct" carve-out — if it was a retro proposal accepted by the user, it goes through the retro PR.
- **PR body discipline:** the "Files changed" section of the retro PR body MUST match `gh pr view <N> --json files --jq '.files[].path'`. If the body lists a file the diff doesn't contain, fix the diff (push the commit) — do NOT amend the body to remove the claim.

**For retro-PR reviewers (Mandatory enforcement clause):**

Before approving a retro PR, run:

```bash
gh pr view <N> --repo <owner>/<repo> --json files --jq '.files[].path' | sort > /tmp/retro_<N>_diff_files.txt
# Then read the PR body's "Files changed" section and compare.
```

If the body claims any file (charter/skill/trust-matrix, in particular) that is not in `/tmp/retro_<N>_diff_files.txt`, post **ChangesRequested** with the specific missing path(s). Approving a retro PR whose body claims files absent from the diff is a charter violation in the reviewer-class.

### Skill enforcement

`/wave-retro` (Step 6 / Step 8) and `/wave-wrapup` SHOULD run a body-vs-diff sanity check before emitting the retro summary or wrapup table:

```bash
RETRO_PR=<N>
gh pr view "$RETRO_PR" --repo <owner>/<repo> --json files --jq '[.files[].path] | sort' > /tmp/retro_diff.json
# Parse the PR body's "Files changed" section.
# For each path claimed in body but missing from /tmp/retro_diff.json, ABORT with a clear "body claims X not in diff" error.
```

Promotion target on this section is `skill` — the retro skill is the natural home for the check, and the `/promotion-audit` pipeline can pick it up on a future pass.

### Severity if violated

- Retro PR body lists a charter/skill file that is not in the diff, and the actual edit is committed direct-to-main: **severe**. Bypasses two-reviewer gate and CI; breaks the audit trail. Reviewer who approved it shares the severity.
- Retro PR body lists files that aren't in the diff, but the edits never actually landed (typo in body, no direct-to-main commit either): **moderate**. The audit trail is salvageable by editing the body, but the misleading framing already shipped to anyone who read the merged PR.
- Retro author commits substantive charter/skill changes direct-to-main alongside the retro PR but does NOT claim those files in the body: **moderate-to-severe** depending on whether the change was substantive. The two-reviewer gate is still bypassed even without the body mismatch.

### Worked example

`noorinalabs/noorinalabs-main` PR [#124](https://github.com/noorinalabs/noorinalabs-main/pull/124) (W8 retro, merged 2026-04-17). The PR body listed seven files: `feedback_log.md`, `trust_matrix.md`, `charter/pull-requests.md` (2 new sections), `charter/hooks.md`, `skills/wave-retro/SKILL.md`, `skills/wave-kickoff/SKILL.md`, `ontology/checksums.json`. The actual PR diff contained two: `feedback_log.md` + `ontology/checksums.json`. The five substantive charter/skill/trust-matrix changes landed via two direct-to-main commits (`2b92605`, `ecd1c76`) with no PR — bypassing two-reviewer review and `validate_pr_ci_status`. Found by Santiago's post-merge review of #124; filed as [#126](https://github.com/noorinalabs/noorinalabs-main/issues/126).

### Cross-references

- `pull-requests.md § Comment-Based Reviews` — the two-reviewer gate this rule protects.
- `hooks.md § Hook validate_pr_ci_status` — the CI gate this rule protects.
- `pull-requests.md § Trust the Artifact, Not the Framing` — sibling rule on the reviewer side: read the artifact, not the body framing. This rule extends the discipline to the **author** side of the retro PR.
- `skills/wave-retro/SKILL.md` — the skill that should adopt the body-vs-diff sanity check per the Skill enforcement clause above.

## `gh pr edit` projects-classic deprecation — use REST API for body/title updates (Mandatory) <!-- promotion-target: none -->

`gh pr edit <num> --body <text>` (and `--body-file <path>`, and `--title`) on gh-cli versions older than the one that migrated off the deprecated projects-classic GraphQL scope **silently fails** the body/title mutation. The command exits non-zero with a `GraphQL: Projects (classic) is being deprecated` error, but the error reads like a benign warning and the PR body appears unchanged on subsequent inspection — exactly the "silent-no-op" shape captured in memory `feedback_gh_pr_edit_silent_noop`.

Root cause: `gh pr edit` fetches `repository.pullRequest.projectCards` as a side-effect of the mutation; the classic-projects deprecation fails that sub-query, poisoning the whole call. Resolves main#185 (Linh.Pham hit 2026-04-22 — PR#844 body silently retained option-A through the entire v5 phase; reviewers never saw v5 content for ~30 minutes).

### Required workaround — use REST API directly

For any PR body or title update, prefer the REST API:

```bash
# Body update (single line)
gh api "repos/<owner>/<repo>/pulls/<num>" -X PATCH \
  -f body="$(cat /path/to/body.md)"

# Body update (multi-line, recommended — avoids quote-escape bugs)
gh api "repos/<owner>/<repo>/pulls/<num>" \
  --method PATCH \
  --input <(jq -nc --rawfile b /path/to/body.md '{body:$b}')

# Title update
gh api "repos/<owner>/<repo>/pulls/<num>" -X PATCH \
  -f title="new title"
```

`-f` is `--field` and treats the value as a string. For multi-line bodies, prefer `--input` with a `jq`-built JSON body to avoid `-f`'s newline-stripping behavior (see memory `feedback_gh_pr_edit_silent_noop` for the related `gh api -f body=@file` no-op trap — use `--input` or pipe through `jq --rawfile`).

### Eligibility

The REST path applies whenever the gh-cli version is older than the upstream fix release. As of this writing (May 2026) the locally-installed gh is `v2.45.0` (July 2025 build). The upstream fix landed in a later release (`cli/cli` migrated the projects-classic scope post-2025). To check locally:

```bash
gh --version
```

If `gh --version` reports `v2.45.0` or older, USE the REST path. If newer, the native `gh pr edit` may be safe — but the REST path always works regardless of version, so skill authors who want maximum portability should default to REST.

### Read-back verify

Per the silent-no-op shape: ALWAYS verify the body/title landed after an update, regardless of which path you used:

```bash
gh pr view <num> --repo <owner>/<repo> --json body --jq '.body | length'
# OR (head of body):
gh api "repos/<owner>/<repo>/pulls/<num>" --jq '.body[0:80]'
```

A 0-length body or a stale prefix is the signal the mutation didn't land.

### Severity if violated

- Skill or script uses `gh pr edit --body` and never reads back: **moderate** — silently produces wrong state visible to reviewers as "the body says X" when X is the prior version. Worked example: isnad-graph#844's 30-minute reviewer confusion window (Linh.Pham, P2W10).
- Skill author uses `gh pr edit` AND read-back-verifies: **minor**. The read-back catches the no-op even if the mutation surface stays risky.
- Manual one-off `gh pr edit` invocation by a human operator: **out of scope** for charter enforcement (humans can interactively re-run); the charter rule applies to skill/script paths where the no-op compounds across batched calls.

### Cross-references

- Memory `feedback_gh_pr_edit_silent_noop` — the broader silent-no-op family (`gh project item-add`, `gh project item-list --limit`, `gh api -X PATCH -f body=@file`) sharing this shape.
- Resolves main#185.
