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
  integration branch (`deployments/wave-{wave}`), never `main`
  directly. Under `direct-to-main`, that base collapses to `main`
  and feature branches PR straight into it.
- Title under 70 characters; body references the issue with `Closes #N`.
- Push unpiped — piping `git push` through `tail`/`head` masks a rejected push
  behind the pipe's exit code (flagged — see [hooks.md](hooks.md)).

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

Every PR requires **1 review(s)** from team members who are not
the branch author.

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

Reviewers are assigned by the lead at wave kickoff (no self-review; spread the load).
The reviewer runs the tests on the branch — a review is an act of verification, not
a reading exercise.

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
