# Generic Charter: Pull Requests

## Purpose

A template for how a multi-agent team opens, reviews, sequences, and merges
PRs — including the comment-based review format the team uses when all agents
share one host account, the verification disciplines that keep reviews honest,
and the branch-protection / CI-gate posture that backs the conventions with
machine enforcement.

When all work on a branch is complete (committed, reviewed, must-fixes
resolved), the implementer **automatically creates the PR** using the CLI — no
manual instruction. **PR ownership:** only the member who implemented the work
creates the PR; coordinators must not create duplicate PRs for the same branch.

## Comment-based reviews (mandatory)

When all agents share a single host account, formal "approve" reviews fail
("cannot approve your own pull request"), so reviews use **structured
comments** instead.

**Review trailer** (posted as a PR comment):
```
Requestor: <comment author>
Requestee: <comment target>
RequestOrReplied: Request | Reply | Approved | ChangesRequested
TechDebt: none | #15, #16, ...
```

The role names always describe the **comment**, not the PR:
- **Requestor** = always the comment author (whether PR author or reviewer).
- **Requestee** = always the comment target.
- **RequestOrReplied** distinguishes the comment kind, not the role direction:
  `Request` (initial ask from PR author), `Reply` (non-verdict response),
  `Approved` (approving verdict), `ChangesRequested` (blocking verdict).

**Consequence for verdict comments:** on `Approved`/`ChangesRequested`, the
Requestor is the **reviewer** (the comment author). A review-counting hook
counts distinct `Requestor` values across verdict comments to verify the
2-reviewer rule (count distinct *Requestor*, not Requestee — on a verdict the
Requestee is the PR author).

**Validation rules:**
- A PR author cannot self-approve via comment.
- `TechDebt:` is **mandatory** on every verdict comment. If non-blocking
  observations were found, file tech-debt-labeled issues BEFORE posting and list
  their numbers; else write `TechDebt: none`.
- The 2-reviewer rule is satisfied by `Approved` comments from **two distinct
  Requestors, neither the PR author.**
- Each verdict Requestor must name a real roster member (full-name match).
  Non-roster strings don't count.
- Charter-format fields MUST appear ONLY in a **trailer block** — a contiguous
  fields block at the end of the comment, ideally after a `---` separator. The
  extractor reads fields only from the post-last-`---` substring and strips
  inline/fenced code first. **Never reproduce the literal `Field: value` shape
  in prose** — a first-match extractor will grab the prose line as the verdict.

## Review prompt template (mandatory)

When assigning a review, the prompt MUST include a **copy-paste-ready comment
command with all fields pre-filled.** Do not rely on agents writing the format
from memory — that has a ~100% error rate. Replace the verdict word and TechDebt
line as needed; add no bold markers, parentheticals, or extra fields. For
`Request`-kind comments the role direction inverts (Requestor = PR author).
Omitting the template from a review assignment is a minor feedback event for the
orchestrator.

## Reviewer assignment

- **Two reviewers per PR**, assigned at kickoff (a primary and a secondary),
  named in the spawn prompt and execution plan. The two-reviewer rule is a
  **floor, not a cap.**
- **Blast-radius PRs (3+ deliberately assigned reviewers):** do NOT merge once
  the 2-reviewer minimum is met. Wait for **every** deliberately-assigned
  reviewer (each carrying a distinct lens) to approve, or explicitly release one
  with a recorded reason. Merging at 2-of-3 ships without the lens the third was
  assigned to provide.

### Single-reviewer exceptions (narrow, budgeted)

- **Bootstrap exception:** PRs that establish the tooling/CI/hooks that
  subsequent PRs are gated by may use one reviewer — but only if the PR is
  genuinely bootstrap infra, **no more than once per iteration**, the reviewer
  is the standards/quality enforcer, and the exception is logged by name in the
  retro.
- **Trivial cross-repo doc sweep:** a byte-identical doc-sync landing in N>1
  child repos may use one reviewer per child PR provided every diff is
  byte-identical (verifiable via `git show`), there is no behavior change, every
  child PR links one parent tracking issue, and CI is green on every repo (one
  red revokes the exception for the whole sweep).

These two are **independent budgets** and **not cumulative** — a PR may invoke at
most one. All other PRs require two reviews. Invoking an exception on a
non-qualifying change is a moderate feedback event.

## Review workflow & finding disposition

1. Create the PR targeting the iteration branch.
2. Notify ≥2 reviewers (the gate requires two distinct non-author reviews; speed
   never exempts a PR from the gate).
3. Reviewer posts a verdict comment with **must-fix** items (block merge) and
   **tech-debt** items (don't block, but a tracking issue must exist), then
   notifies the PR creator.
4. PR creator acts: fix must-fixes on the branch; quick-fix trivial tech-debt;
   file issues for non-trivial tech-debt.
5. Push the fixes.
6. The team merges into the iteration branch themselves (no user approval needed
   for iteration-branch merges).

Every finding must be dispositioned before merge — none silently dropped. The
standards enforcer verifies must-fixes are resolved and tech-debt issues exist
and are labeled.

## Additive commits on ChangesRequested (mandatory)

When a reviewer marks `ChangesRequested`, the fix lands as an **additive commit
on the same branch.** Force-push during a ChangesRequested cycle is
**prohibited** — it resets the HEAD-SHA anchor the reviewer's
`contents?ref=<sha>` verification depends on, making the re-review's delta
unreliable. Allowed: new commits; a merge commit to update from base (`git
merge`, not `git rebase`). Prohibited: `--force`/`--force-with-lease`, rebase +
force-push, `--amend` + force-push, squashing prior commits. If a rebase is
genuinely needed, open a comment thread, get explicit "rebase OK" from the
requesting reviewer first; the re-review restarts from the new HEAD. Once both
reviewers have approved, the anchor is no longer load-bearing and a squash-merge
is the standard path. Violation: moderate feedback event.

## Merge model — one per iteration (mandatory)

An iteration uses **exactly one merge model for its whole lifetime**, chosen and
recorded at kickoff. Mixing the two is prohibited.

| Model | Per-issue PRs base on | Iteration→default integration PR |
|-------|-----------------------|----------------------------------|
| `direct-to-main` | the default branch | none — work is already on the default branch; the iteration branch stays at the kickoff point |
| `iteration-branch` | the iteration branch | opened at wrapup, merged via the integration-merge admin exception |

Record the choice in the status file at kickoff. **Enforce mid-iteration, not
only at wrapup:** session-start compares each repo's iteration branch against the
default branch and classifies the gap against the declared model — `direct-to-main`
+ commits on the iteration branch is a VIOLATION (someone mixed models);
`iteration-branch` + ahead + an open integration PR is OK; ahead + no PR is an
advisory (it will strand unless wrapup opens the PR). Only a model violation
fails session-start; advisories are expected mid-iteration states. A wave whose
model is unrecorded degrades to advisory-only, never a false violation.

## Integration-merge verification

At the end of an iteration/phase the integration PR (iteration branch → default
branch) is verified before presenting to the user: confirm every CI check is
green, fix any red before notifying, report CI status explicitly, and provide
full clickable PR URLs (not `repo#number`).

The integration merge runs via the **integration-merge admin exception — this is
the expected path, not a process failure.** The code was already 2×-reviewed on
its per-issue PRs; the integration PR is an *integration* merge, not new code to
re-review. After the user approves the sequence, merge each with a **literal PR
number, one per call** (a review-counting hook that parses literal numbers
fail-opens on a loop variable). Collecting fresh approvals on the integration PR
is not required. The review-block and admin-exception prompt firing on these is
expected and audited (each exception is logged), not a signal something is wrong.

## CI-trigger coverage for iteration branches

CI workflows using a `pull_request` trigger MUST include active iteration
branches in the `branches` filter, OR omit the filter entirely. A filter locked
to the default branch silently skips CI on iteration-branch PRs (producing an
empty check rollup that a naive "block on FAILED" gate treats as green). The
push-trigger counterpart: push triggers must cover the iteration-branch glob
too. Reviewers flag any single-branch PR-trigger filter that excludes iteration
branches unless the PR body justifies it.

## Cross-contract & dependency sequencing

- **Cross-contract PRs:** when ≥2 in-flight PRs produce/consume from each other
  (message topics, schemas, shared API/wire formats), the **first PR opened MUST
  include a "Contract" section** (shape, ownership/adjudicator, allowed
  divergence). Subsequent PRs link to it and document divergence. Any reviewer
  may block a cross-contract PR missing this. A few minutes of contract up front
  prevents two branches building on incompatible assumptions.
- **Dependency sequencing:** identify cross-PR dependencies before merging;
  merge base PR first; do NOT merge a dependent PR in parallel even with green CI
  (its CI ran against base *without* the dependency); after merging base, the
  dependent must update before its CI is trusted; document dependencies in the
  PR body.

## CI must be green before merge

No PR merges while CI is failing, **even if failures are pre-existing.** If a new
workflow catches pre-existing violations, fix them before or in the same PR (or
fix forward via a predecessor PR merged first). Merging with known failures is a
moderate feedback event.

### Full local⇄CI parity + no force-merging failing checks

- **Parity:** every repo's pre-commit/pre-push config MUST mirror the
  **complete** CI check-set across its commit + push stages (tests, every
  linter/formatter, type-check, spell-check, workflow-lint, secret-scan, drift
  gates) — not a subset. Commit vs push is a latency choice (fast checks on
  commit, heavy on push); the *union* must equal CI. A sync-drift gate
  machine-enforces this and must classify **every** CI kind — its silence on an
  unclassified kind is not evidence of parity.
- **No force-merge:** never commit/push/merge with a known-failing check without
  explicit owner permission — **even a pre-existing one not caused by your
  change.** A red gate is a stop, not a speed bump; the path is fix-forward, not
  merge-through. If a check genuinely can't be greened in-scope, that's an owner
  decision surfaced with a one-line diagnosis, not a self-granted exception.
  Force-merging a failing check is moderate; doing so on a security gate is
  severe.

## Branch protection + admin-merge exceptions

Default-branch protection should be enforced **server-side**, not by team
discipline alone. Because a shared host account cannot produce formal approvals,
a naive "require 1 approval" rule would deadlock every merge. So the ruleset
requires only what it can without breaking the flow:

- a `pull_request` rule with **0 required approvals**,
- a required-status-checks rule listing that repo's unconditional PR-gate
  contexts (omit for fully path-filtered repos, where CI-green falls to the
  merge-time CI-status hook instead),
- deletion + non-fast-forward protection,
- a single bypass actor: the repository-admin role (`always` bypass).

The 0-approvals choice is load-bearing: reviewer-count enforcement stays in the
review-counting hook (where issue-comment verdicts live), and the admin bypass
keeps the established exceptions working. The bypass is the server-side
counterpart to a **hook-side admin-merge exception list** — `--admin` is not a
silent bypass; the merge-time CI hook blocks `--admin` unless the operator
declares a charter-listed exception (e.g. `EXCEPTION="<class>:<rationale>"`),
with the rationale required and **logged to an audit trail.** Recognized classes
map one-to-one to charter sections (bootstrap, doc-sweep, integration-merge,
emergency); an absent/unrecognized exception blocks (fail-safe). Defense in
depth: the ruleset covers UI/external merges; the hook covers CLI merges and
writes the audit trail.

## Documentation freshness (advisory gate)

Code is the arbiter of truth for docs: when a PR changes a documented code
surface, the docs it implies are expected to move with it. An **advisory**
doc-freshness gate reports surfaces changed without a matching doc update — it
never blocks (a heuristic has unavoidable false-positives). When a change
legitimately needs no doc update, declare it with a `Docs-N/A:` /
`Skip-Doc-Check:` trailer.

## Closes vs Refs — decided at brief time, never flipped

The `Closes #N` vs `Refs #N` disposition is determined **once, when the brief is
authored**, and is not re-litigated after the PR opens. Use `Closes` only when
the PR fully delivers the issue's entire acceptance surface; use `Refs` when
acceptance includes work beyond this PR (an end-state criterion with remaining
rollout, a prod-gated runtime step, a multi-PR sequence) — the issue stays open
as the rollout tracker. If any acceptance will remain after merge, it's `Refs`
from the **first** PR; flipping `Closes`→`Refs` afterward is a routing change on
an in-flight artifact and triggers the same re-verify churn as any late pivot.

## Verification disciplines

### Trust the artifact, not the framing

PR-body framing is a navigation aid; the diff against the actual artifact is
ground truth.
- **Implementer side:** before implementing per a spec/brief, verify its
  load-bearing claims against the artifact (`git log <path>`, grep). If the spec
  diverges from ground truth, surface the gap BEFORE implementing — don't
  silently absorb it.
- **Reviewer side:** read the diff against the artifact, not the body's framing
  of what it does. **Confirm the PR head SHA before posting any verdict**
  (`gh pr view <N> --json headRefOid`) and state it in the verdict, anchoring the
  certification to a concrete head. If the PR is rebased/force-pushed after the
  verdict, the verdict is **stale** and must be re-confirmed against the new head.

### Origin > local clone for "still-has-X" claims

When asserting a "still has X / still missing Y" property about a PR's file
content, query origin at the head SHA (`contents?ref=<head_sha>` or
`pulls/<N>/files`). Do NOT grep a local checkout/worktree/clone — it's frozen at
clone time and stale the next push. A stale-clone "still has X" is a false
Changes-Requested that costs the implementer a counter-correction. Most acute in
high-churn multi-implementer cycles. A "still has X" comment must include the
`?ref=<head_sha>` query or be re-verifiable by another reviewer via it.

### Live-trace evidence > synthetic-test acceptance

When validating a new gate (CI hook, security check, alert rule), prefer the
gate **firing on a real in-the-wild artifact** over passing on tests authored
alongside it. Synthetic tests prove the gate handles cases the author imagined;
live-trace proves it handles cases the world produces. For PR-time gates,
demonstrate the verdict on the most-recent real failing artifact and cite it by
URL/SHA. If the only acceptance evidence is the gate's own fixtures, request a
live-trace before approving. For end-state criteria, require **live-environment
evidence** (a query against the deployed datastore, a request to the live host,
a trace of the deployed app) — CI-green and in-process harness results are
necessary but not sufficient; they prove the code works, not that the criterion
is true on the running system.

### Production-realistic fixtures

Fixtures for parse/extraction/load-invariant logic MUST be **lifted from real
upstream samples**, never hand-authored from a schema that matches the parser's
own assumptions, never simplified into toy strings. A fixture that is *greener
than real data* masks a bug — encode the source itself, not the author's mental
model of it. Note provenance in a comment; if trimming a large sample, don't
make it greener than the source. Reviewers ask: "was this lifted from real
upstream, or authored to match the parser?"

## PR-time vs runtime acceptance

Distinguish two lifecycle positions when an issue has both code and a runtime
gate:
- **PR-acceptance** — code correctness, hardening, scoped local validation;
  reviewable from the diff + CI.
- **Runtime-acceptance** — operational events firing on real infra that may not
  exist yet; verified post-merge.

Don't conflate them: blocking a PR on infrastructure that doesn't exist yet
either stalls indefinitely or forces synthetic-evidence fakery (worse than no
proof — it masks the real gate). Write the Test Plan in two sections (pre-merge /
post-merge); if a runtime gate is a genuine acceptance criterion, file a
**separate** issue for it. Some IaC providers validate only at **apply**, not
plan — a green plan + clean review cannot certify expression correctness; the
apply is the validation gate, so use `Refs #N` and close on verified-live (not
on merge) for runtime-gated issues.

## Design-rationale block for critical-path PRs

PRs touching critical-path workflow DAGs, observability stacks, or alert-rule
definitions MUST include a design-rationale block at the load-bearing decision
point — an inline comment at the gate/predicate (preferred) or a labeled PR-body
section — walking the predicate algebra / an outcome truth table / a
design-vs-alternatives comparison, with citations to the spec. Absence on an
applicable PR is grounds for Changes Requested; reviewers engage with the
block's quality. High-leverage for incident-response readability and retro
evidence.

## Security guards belong inline, not in a followup

When a PR's security model depends on a runtime guard (env check, scheme
whitelist, HTTPS-required-outside-test assertion, startup assertion, URL-rewriter
validation, auth-bypass flag), the guard MUST ship **in the same PR.** Filing a
followup issue is a legitimate paper trail but **not a substitute.** Reviewer
protocol: post Changes Requested even if a followup exists; file the followup
first so the verdict can cite it; approve only after the inline guard lands.
Docstring warnings and "remember to set X in prod" notes are never sufficient.
Approving a PR with a deferred guard is severe (a silent regression window).
Does NOT apply to defense-in-depth hardening, log tuning, or threat-preserving
refactors — those are legitimate followups.

## Retro PR body-vs-diff discipline

The retro PR is the **authoritative artifact** for an iteration's ratified
changes. Every charter/skill/trust-matrix file the retro ratified MUST land **in
the retro PR's diff** — not via direct-to-main commits alongside it.
Direct-to-main bypasses the two-reviewer gate AND the CI gate, and breaks the
audit trail that traces theme → ratified changes. The PR body's "Files changed"
section MUST match the actual diff file list; if the body claims a file the diff
lacks, fix the diff (push the commit) — do NOT amend the body to drop the claim.
Reviewers compare the body's claimed files against the diff before approving;
approving a retro PR whose body claims absent files is a reviewer-class
violation. Body claims a charter file not in the diff, with the edit committed
direct-to-main: severe.

## Pre-push checklist

Before pushing and opening a PR: run the repo's lint, format-check, typecheck,
and full test suite (including E2E if present — content changes break test
assertions); verify the branch name matches the convention. Pushing code that
fails lint/format/tests is a minor feedback event.

## Sandbox test-verification fallback

When the dev environment has no local backing services, a test whose fixture
spins up the app will **block on a connection that never completes** — it
presents as "still running," not a failure, silently burning wall-clock. If the
full suite hangs, don't keep waiting: verify the changed logic via a **targeted
unit check that needs no app/DB startup**, then **cite the green CI job** (which
runs with real services) as suite-pass evidence. Claiming "tests pass" from a
run that actually hung (never reached terminal) is a moderate unverified claim.

## CLI silent-no-op caution

Some CLI mutation commands **silently no-op** (exit nonzero with a benign-looking
warning while the mutation doesn't land). Prefer the REST/raw-API path for body/
title updates over the convenience CLI, and **always read back** after any
mutation — a zero-length or stale value is the signal it didn't land. Skill/
script paths that mutate without read-back are moderate; the no-op compounds
across batched calls.

## PR template (shape)

```
## Summary
<1-3 bullets>

## Related Issues
Closes #<issue-number>   (or: Refs #<issue-number> for runtime-gated work)

## Review Checklist
- [ ] Reviewed by another team member
- [ ] Must-fix items resolved
- [ ] Tech-debt items filed as issues (if any)
- [ ] Docs updated for the code change, or a Docs-N/A: opt-out is justified

Co-Authored-By: <Member> <per-member identity>
```

Title concise (under ~70 chars); body references the related issue(s); the
implementer creates the PR immediately on branch completion.

## Adaptation notes

- The comment-based-review format and the 0-required-approvals branch-protection
  shape are the workarounds for **all agents sharing one host account.** If your
  agents have distinct accounts, you can use native approvals and drop those two
  pieces — but keep the verification disciplines (trust-the-artifact, origin >
  local, live-trace, head-SHA-anchoring), which are independent of that
  constraint.
- The severity ladder (minor / moderate / severe) and the enforcement-hierarchy
  promotion path (charter → skill → hook) are the portable governance core.
