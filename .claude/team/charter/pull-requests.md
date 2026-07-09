# Pull Requests

When all work on a feature branch is complete (code committed, checks green), the
implementing team member **creates the PR themselves** with the `gh` CLI — do not
wait for manual instruction, and do not create a PR for someone else's branch.

## PR Creation

```bash
git push -u origin <feature-branch>
gh pr create --base <integration-branch> --title "<short title>" --body-file /tmp/pr-body.md
```

- **Base branch follows the wave's effective merge model** (configured default:
  `wave-branch`; the effective model for a wave is declared at kickoff via
  `lifecycle.py wave kickoff --merge-model …` and recorded in the state file —
  see [branching.md](branching.md)). Under `wave-branch`, target the wave's
  integration branch (`deployments/phase{phase}/wave-{wave}`), never `main`
  directly. Under `direct-to-main`, that base collapses to `main`
  and feature branches PR straight into it.
- Title under 70 characters; body references the issue with `Closes #N`.
- Push unpiped — piping `git push` through `tail`/`head` masks a rejected push
  behind the pipe's exit code (flagged — see [hooks.md](hooks.md)).

## Pre-Review Self-Check: Every New Behavior Needs a Load-Bearing Test

**Before requesting review, every new behavior must have a load-bearing test —
one that FAILS if the behavior it covers is reverted.** A test that passes
whether or not the behavior exists (tautological, or asserting on a mock instead
of the real code path) does not satisfy this.

This is a **hard, fail-closed gate** (owner decision, 2026-07-06, #167 — one of
three Wave-1 retro process proposals, meta #165): all three Wave-1 must-fixes were
new behavior shipped without a revert→fail test, caught only at QA. The
`require_load_bearing_test` hook (see [hooks.md](hooks.md)) enforces the
mechanical precondition at `gh pr create`/`gh pr ready` time — it blocks when the
diff adds a substantive line to a behavior file with no test-file change PAIRED
to that specific file in the same diff, and blocks (rather than the usual
fail-open posture) when the diff itself cannot be verified (network/API failure,
unresolvable repo/head).

**Pairing is per behavior file** (Wave 3 S2, #174): a substantive test-file
change elsewhere in the same PR, for an unrelated module, does NOT satisfy a
different behavior file's own requirement. A behavior file counts as paired if
the diff also substantively touches a test file named `test_<name>.py` /
`<name>_test.py` for its stem, a test file in the same directory, or
`conftest.py`. Touching every file's own test is the reliable way to satisfy
this (not "touch any one test file in the PR").

The hook is a lightweight, deterministic proxy — file-presence plus a substantive
added line, not a semantic proof. It CANNOT verify that a touched test is actually
load-bearing for the specific new behavior, or execute a real revert→fail
simulation. That judgment remains the author's self-check duty before requesting
review, and QA's review-time verification (see § Review Workflow below) holds the
same bar the hook only approximates.

**Override:** short of a deliberate, documented exception, this gate cannot be
bypassed. Classes are configured under `policy.load_bearing_test_exceptions`,
which ships pre-seeded with one class, `refactor` (Wave 3 S3, #176), for PRs
that are a pure refactor with no external behavior change (so there is no new
behavior to pair a test to). To use it:

```bash
LOAD_BEARING_TEST_EXCEPTION="refactor:<what you restructured, why behavior is unchanged>" gh pr create ...
```

More generally:

```bash
LOAD_BEARING_TEST_EXCEPTION="<class>:<rationale>" gh pr create ...
```

where `<class>` must be a key configured under `policy.load_bearing_test_exceptions`
and `<rationale>` a non-empty, specific justification — an unrecognized class or
empty rationale still blocks. Every attempt — authorized or not — is logged to
the events log for audit.

**PR body template:**

```markdown
## Summary
<1-3 bullet points describing the change>

## Related Issues
Closes #<issue-number>

## Review Checklist
- [ ] Reviewed by another team member
- [ ] Must-fix items resolved
- [ ] Tech debt items filed as GitHub Issues (if any)
```

## Review Workflow

Every PR requires **2 review(s)** from team members who are not
the branch author.

### The N-reviewer merge gate (mechanically enforced when armed)

The reviewer bar is not advisory when `policy.pr_review_gate_enabled` is **true**: the
`validate_pr_review` PreToolUse hook (thin over the `lib/pr_review_state` oracle — see
[hooks.md](hooks.md)) **blocks `gh pr ready` / `gh pr merge` until the PR is
`approved`** — meaning **2 distinct clean reviewer approvals AND no
unresolved `Must-fix:` verdict**. Approvals are counted over distinct `Requestor:`
identities whose current verdict is clean (a `Replied` review with `Must-fix: None`, per
[issues.md](issues.md)); a standing `Must-fix:` blocks regardless of the approval count.

- **On THIS repo the gate is LIVE as of Phase 6 Wave 6** (`pr_review_gate_enabled=true`,
  `reviewers_required=2`): a merge cannot land without 2 distinct clean approvals.
- **The framework ships the gate DORMANT** (`pr_review_gate_enabled=false`): a downstream
  install keeps this bar advisory until its owner flips the flag, so nothing here blocks a
  fresh adopter's merges.
- **Escape hatch (if the team wedges):** the gate must never trap the team. It can be
  disarmed by a **direct config-only commit to `main`** setting
  `policy.pr_review_gate_enabled` back to `false` (no PR merge required — the config edit
  itself is not a gated verb). The gate is additionally **fail-open on oracle error**: an
  inability to *evaluate* approval state ALLOWS the merge rather than hard-blocking it, so a
  broken oracle can never wedge the workflow either.

1. **Create the PR** and notify the assigned reviewer(s).
2. **Reviewer reviews** and posts findings on the PR, classified as:
   - **Must-fix** — blocks merge; the submitter resolves before proceeding.
   - **Tech debt** — does not block merge; tracked as a GitHub Issue labeled
     `tech-debt` (see [issues.md](issues.md)).
3. **Submitter acts:** must-fix items are fixed and pushed; quick tech debt is fixed
   inline; non-trivial tech debt becomes a self-assigned issue for the Tech Lead to
   allocate in future planning.
4. **Merge into the integration branch** — the team merges these PRs itself; no
   owner approval is needed below `main`.

### Clearing a `Request`: amend in place (never post a new comment)

When you re-review after the submitter has pushed a fix, **clear your blocking verdict by
EDITING your original `Request` comment in place** to `Replied` / `Must-fix: None` — do
**not** post a fresh `Replied` comment and leave the old `Request` standing:

```bash
gh api -X PATCH /repos/<owner>/<repo>/issues/comments/<comment-id> --field body=@resolved.md
```

**Why this is load-bearing, not stylistic.** The armed-gate oracle
(`lib/pr_review_state`) counts **every current comment** that parses as a `Must-fix:` /
`Request` as a still-open blocker, and a reviewer with any standing blocking comment is
**not** counted as an approver even if they later add a separate clean one. A new `Replied`
comment therefore leaves your old `Request` in force — the oracle stays `changes_requested`
and the PR cannot reach `approved`. Editing the original comment is the only way to retract
the block. (Learned the hard way in Phase 6 Wave 8, #231.)

The scorer credits the catch regardless of the amendment: `trust_signals` records each
changes-requested catch to a durable review-catch ledger **at issue time**, and (per S1,
#229) also reconstructs catches from the comment **edit history** — so amending your
`Request` away to `Replied` clears the oracle's block *without* erasing the
`must_fix_caught` / `must_fix_received` credit for the review. Amend freely; the signal
survives.

### Reviewer Assignment (distinct, author-exclusive)

Reviewers are assigned by the lead at wave kickoff (spread the load). The reviewer runs
the tests on the branch — a review is an act of verification, not a reading exercise.

Every PR is assigned **2 distinct reviewers**, and the assignment
is **author-exclusive**: a reviewer can never be the PR's own author — the `Requestee:`
of that PR's verdicts, per the verdict grammar in [issues.md](issues.md). The
2 reviewers must be 2 *different* people; the
same reviewer counted twice does not satisfy the bar, and no self-review is permitted.

This assignment convention is what the armed merge gate partly enforces (§ The
N-reviewer merge gate): the oracle counts clean approvals over **distinct `Requestor:`
identities**, so assigning fewer than 2 distinct reviewers leaves
the PR unable to reach `approved` — it cannot merge. Assign the full slate at kickoff
so the process the gate checks and the process the team runs are the same one.

> **Documented contract the code does NOT yet meet (#293).** The gate is *intended* to
> count distinct `Requestor:` identities **other than the author**, matching the
> author-exclusive assignment above. The current oracle
> (`pr_review_state.compute_state`) does NOT exclude the author — it counts every
> distinct `Requestor:`, so an author's own clean self-verdict still counts toward the
> bar (a **live self-approval bypass**: author self-verdict + one genuine reviewer
> reaches `approved` at `reviewers_required=2`). #293 brings the code up to this
> contract by reusing `trust_signals.is_author_self_review`. Until it lands, the
> author-exclusive bar rests on the assignment convention plus the reviewer-only
> verdict grammar ([issues.md](issues.md)) — not on the gate. (The trust *scorer* is
> already author-exclusive, per #288.)

## CI Gates

1. **Wait for CI to complete before merging.** Merging with red CI is prohibited
   (enforced — see [hooks.md](hooks.md)).
2. If CI fails: investigate, fix, push to the same branch. If unresolvable, do NOT
   merge — escalate to the project owner.
3. If the base has moved since you branched, merge the base in and let CI re-run —
   a stale branch can be green against an old base and still break the integrated
   result.

## Merge Order & Dependencies

When PRs in the same wave depend on each other (PR B uses code from PR A):

1. Identify dependencies before merging; note them in the PR body
   ("Depends on #N — must merge first").
2. Merge in dependency order — never dependent PRs in parallel, even if both are
   green: the dependent PR's CI ran without the dependency.
3. After the base PR merges, the dependent PR merges the updated base before its CI
   result is trusted.

## Definition of Done

### Pushed = Done

A commit or merge that exists only in a local worktree is **not done** — it is
invisible to CI, reviewers, and the merge gates. After committing, push and verify
the tip landed (`git rev-parse origin/<branch>` matches local `HEAD`). A completion
report states the pushed SHA and branch.

### Completion Reports Reconcile Against the Diff

Before reporting done, the implementer runs `gh pr diff <PR#> --name-only` and
confirms every claimed file is in the diff (and nothing unexpected is), and that the
PR body carries the `Closes #N` lines for every issue it claims to resolve. A "done"
report that fails its own reconciliation is not done — fix it first, don't caveat it.

### Claude Assets: Reinstall on Change

A repo that is both the framework **source** and a live **consumer** of it (this repo)
keeps Claude-related assets in two trees that must not drift:

- **Canonical / install source** — `framework/assets/**` (+ `framework/config/**`,
  `framework/install/**`): what deploys to target repos.
- **Live runtime** — `.claude/**`: what this repo actually loads.

A change touching any Claude asset (skills, hooks, libs, charter, config, settings) is
**not done** until (1) it exists in the canonical/install dir, (2) the live `.claude/**`
copy has been regenerated from it, and (3) the two are verified in sync (byte-identical
where a parity test applies).

Reinstall command (this repo):

```bash
python3 framework/install/reinstall.py           # regenerate .claude/ from framework/assets/
python3 framework/install/reinstall.py --check    # verify in sync (CI gate; exit 1 on drift)
```

Deploying into another repo uses the same installer via the published CLI
(`real-team init --with-hooks --force`, i.e. the bundled bootstrap).

Not every asset needs a copy step: **hooks/** + **lib/** are wired in place (settings.json
points the dispatchers at `framework/assets/hooks/`, so they run canonical directly and
cannot drift), and **team/charter/** is rendered with per-repo substitution and is
hand-evolvable. The byte-mirrored trees (today: `skills/`) are the ones `reinstall.py`
manages and `test_reinstall_parity.py` enforces in CI — a PR that edits a canonical
mirrored asset (or its live copy) without reinstalling fails that check.

## Wave Merge PR

At the end of a wave/phase, the Manager creates a PR from the integration branch
into `main`. The **project owner reviews and approves** this merge —
do not proceed until they have (see [charter.md § Ground Rules](charter.md)).

### Landing the rollup under a permanently-armed gate: the direct-push escape hatch

A wave-rollup PR carries **no verdicts of its own** — its constituent story PRs each
already cleared the gate with 2 clean reviews; re-reviewing the
rollup is theater. But under a **permanently-armed** gate (`pr_review_gate_enabled=true`
on `main`) the oracle still demands 2 clean approvals
before `gh pr merge`, so a verdict-less rollup PR **cannot** clear the gate.

The sanctioned way to land it is a **direct-push merge** — a direct push to
`main` is not a gated verb (only `gh pr ready` / `gh pr merge` are), so it
is ungated by construction:

```bash
git fetch origin                                     # refresh the remote wave tip FIRST
git checkout main && git pull
git merge --no-ff origin/<integration-branch>        # the REMOTE ref (e.g. origin/deployments/phaseN/wave-M) — never a stale local ref
git -c user.name="<Manager>" -c user.email="<...>" commit   # only if the merge needs one
git push origin main
```

### Rollup pre-flight: merge `origin/<wave>`, never a stale LOCAL ref, then verify code landed

The story PRs merge into the wave branch **server-side** (`origin/…`); a local
`deployments/phaseN/wave-M` ref that was never fast-forwarded is **stale**, and merging that
bare local name gives `main` a **code-less** rollup (only `state.json` moves).
Before the merge above:

1. **`git fetch origin`** so the remote wave tip is local.
2. Merge the **remote-tracking** ref explicitly — `git merge --no-ff origin/<integration-branch>`
   — or fast-forward the local ref first
   (`git branch -f <integration-branch> origin/<integration-branch>`); never merge the
   possibly-stale bare local branch name.
3. **Verify feature-code is on the merge parent BEFORE bump/release.** Grep a known new
   symbol from this wave on `main`:

   ```bash
   git show main:<path/to/changed/file> | grep -c '<new-symbol>'
   ```

   A non-zero count confirms the feature code landed. A rollup that moved only `state.json`
   (grep count `0`) is a **STOP-and-investigate**: you almost certainly merged a stale local
   ref — re-run from step 1 against `origin/<wave>` before tagging or releasing.

(Codified from the Phase 6 Wave 11 slip: the first rollup merged a stale local wave ref, so
`main` got a code-less merge — caught only by a post-merge content probe and
fixed by merging `origin/<wave>` before bump/release. #255.)

GitHub auto-marks the rollup PR **MERGED** once its head commits reach
`main`. This is the escape hatch for the rollup specifically — it does **not**
lower the bar for the story PRs, which still go through the gate normally, and it is
distinct from the § N-reviewer merge gate escape hatch (which *disarms* the gate via a
config-only commit; this one leaves the gate armed and merges around it for the one
verdict-less rollup). The same ungated-direct-push property is why wrapup / version-bump /
memory / ontology commits also land as direct pushes. (Codified from Phase 6 Wave 7–8
practice, #231.)
