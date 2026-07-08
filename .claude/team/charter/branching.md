# Branching Rules

**Configured merge model: `wave-branch`.** Under `wave-branch`, feature work
integrates through a shared integration branch per wave and only the wave rollup
reaches `main`. Under `direct-to-main`, feature branches PR straight
into `main`; the integration-branch sections below then collapse to
"base = `main`" and the same feature-branch and worktree rules apply.

## Integration (Wave) Branches

Work is organized into **waves** of parallel tasks. Before starting a wave, create
an integration branch from the latest `main`:

```
deployments/phase{phase}/wave-{wave}
```

- **All feature branches for the wave PR into the integration branch** — not into
  `main`.
- At the end of the wave/phase, PR the integration branch into `main`.
  **Wait for the project owner to approve that merge** before proceeding.

## Feature Branches

- Branch naming scheme: `{initials}/{issue}-{slug}` — the branch carries the team
  member's identity and the issue number. **No branch may be created without an
  existing issue** (see [issues.md](issues.md)).
- All feature branches are created from the **current integration branch** for their
  wave, pulled fresh:
  ```bash
  git fetch origin && git checkout -b <feature-branch> origin/<integration-branch>
  ```
- **Branch safety:** before every commit, run `git branch --show-current` and confirm
  you are on your own branch. Never commit to another member's branch.
- **Before submitting a PR**, merge the latest integration branch into your feature
  branch and resolve conflicts:
  ```bash
  git fetch origin && git merge origin/<integration-branch>
  ```

## Worktree Isolation

**Every code-writing agent works in its own git worktree.** The orchestrator creates
it from the main checkout before spawning:

```bash
git -C <main-repo> worktree add <path> -b <branch> origin/<base>
```

- Agents MUST NOT run a bare `git checkout` / `git checkout -B` in the **main repo
  checkout** — it moves the shared HEAD, corrupts sibling worktrees, and lands the
  orchestrator's own commits on the wrong branch. Always go through `worktree add`.
  (`git -C <other-path> checkout` redirected to a different repo, and pathspec
  restores like `git checkout -- <file>`, are fine.)
- An agent never removes the worktree it is standing in (enforced — see
  [hooks.md](hooks.md)).

## Ad-hoc / e2e Check Hygiene

Ad-hoc end-to-end checks (bootstrap runs, install dry-runs, throwaway scripts) MUST
execute in an **explicit, pre-created scratch dir**. Chain the directory creation and
the `cd` with `&&` so the `cd` cannot run unless the `mkdir` succeeded:

```bash
mkdir -p <scratch> && cd <scratch> && <command>
```

Never split `mkdir` and `cd` across a `;`-separated chain (or leave the `cd` on its
own line) where an earlier command can be blocked or fail: a hook-blocked or failed
`mkdir` leaves the following `cd` pointing at a directory that was never created, the
`cd` fails silently, and every later command runs in the **worktree root** instead —
where an ad-hoc `bootstrap`/install can clobber tracked files (Phase 6 Wave 10
incident #1). Chaining with `&&` aborts the whole sequence on the first failure, so a
silently-redirected cwd can never happen.

## Worktree Cleanup

**After every wave completes** (all PRs merged into the integration branch), clean
up stale worktrees from the main checkout:

```bash
git worktree prune
```

Without this, branches used by deleted worktrees remain locked and cannot be checked
out. The orchestrator runs it after shutting down the wave's agents and before
creating the next wave's integration branch.

## Releases

When an integration branch is merged into `main`, create a release
tagged with the branch name (slashes → hyphens), title = tag, notes = summary of the
wave's work. Release creation requires the project owner's approval (see
[charter.md § Ground Rules](charter.md)).
