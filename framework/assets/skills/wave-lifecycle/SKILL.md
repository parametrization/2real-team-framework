# wave-lifecycle

Drive one iteration ("wave") of team work through its lifecycle:

    allocate → start → scope → kickoff → (work) → wrapup → retro

This skill is **deterministic-first**: every state mutation goes through
`.claude/lib/lifecycle.py`, which owns the state file (config'd
`paths.state_file`, default `.claude/state.json`) and writes canonical
`wave_{W}_*` keys. Prompts only fill in decisions a human must make (the wave
theme, the in-scope repo list, the merge model). Everything else is mechanical.

All values come from `.claude/framework.config.json` — `scm.owner`,
`scm.default_branch`, `branch.feature` / `branch.integration`, `labels.wave`,
`policy.reviewers_required`, `policy.merge_model`, `ci.tooling`. Read them; never
hard-code a project choice here.

## Preconditions

- The framework is installed (`.claude/hooks/`, `.claude/lib/`, a roster under
  `paths.team`). If commit-identity is enforced, every commit in the steps below
  uses `git -c user.name=… -c user.email=…` from the roster.
- `gh` (or your SCM CLI) is authenticated for `scm.owner`.

## Steps

### 1. Allocate the wave id (monotonic, never reused)

```bash
python3 .claude/lib/lifecycle.py wave peek                 # what the next id will be
python3 .claude/lib/lifecycle.py wave allocate --phase {P} --write
```

`allocate --write` advances `global_wave_seq` and stamps `wave_{W}_phase` +
`wave_{W}_phase_ordinal` (the "Phase P, Wave N" display). The allocator is
reservation-aware: an id reserved ahead of the counter (a `wave_{N}_meta_issue`)
is claimed, not skipped.

### 2. Start the wave

```bash
python3 .claude/lib/lifecycle.py wave start {W}
```

Sets `current_wave`, `wave_{W}_active=true`, `wave_{W}_started_at`.

### 3. Scope it (owner decision: which repos)

Decide the in-scope repo list (single-repo: just the one; meta+children: the
subset that changes this wave), then record it:

```bash
python3 .claude/lib/lifecycle.py wave scope {W} --repos repo-a,repo-b --phase {P}
```

Writes `wave_{W}_repos_in_scope` + `wave_{W}_scope_reconciled_at`. For each
in-scope repo, create the wave branch from `scm.default_branch` if the merge
model is `wave-branch` (see step 4), and apply the `labels.wave` label to the
wave's issues.

### 4. Kick off (owner decision: merge model)

A wave uses exactly ONE merge model for its whole life — `wave-branch` (per-issue
PRs base on `branch.integration`; one integration PR to default at wrapup) or
`direct-to-main` (every PR bases on the default branch). Mixing strands work.

```bash
python3 .claude/lib/lifecycle.py wave kickoff {W} --merge-model wave-branch
```

Records `wave_{W}_kicked_off_at` + `wave_{W}_merge_model` and re-points
`current_wave`. Then spawn implementers/reviewers per the roster (reviewers =
`policy.reviewers_required`).

### 5. Mid-wave (on demand)

Check that nothing is stranding against the declared model — `lifecycle.py`
exposes the pure `classify_reachability`; wrap it with your SCM's compare API
(`main...<wave-branch>` ahead_by/status + whether an integration PR is open).
A `direct-to-main` wave with commits on the wave branch is a hard violation.

### 6. Wrap up

Merge ready PRs in dependency order, close resolved issues, then record the
wave's counters and close it:

```bash
python3 .claude/lib/lifecycle.py wave wrapup {W} \
    --pr-count {N} --cr-cycles {C} --concentration {PCT}
```

Sets `wave_{W}_active=false`, `wave_{W}_completed_at`, advances
`last_completed_wave`, and writes the three counters `/wave-retro` reads. Then
extract per-engineer trust signals from the merged-PR set:

```bash
python3 .claude/lib/trust_signals.py extract {W}     # countable per-engineer signals
python3 .claude/lib/trust_signals.py score   {W}     # bidirectional deltas + forced negative line
```

### 7. Retro

Apply the mechanical trust deltas from `trust_signals.py score` to
`paths.team/trust_matrix.md` (each row cites the signal numbers — no narrative
self-grading), append a retro entry to `feedback_log.md`, and surface the
going-well / pain-points / proposed-changes summary to the owner. Do **not**
apply charter/process changes without owner approval.

## Inspecting state

```bash
python3 .claude/lib/lifecycle.py state path      # resolved state file path
python3 .claude/lib/lifecycle.py state show      # dump current state
python3 .claude/lib/lifecycle.py merge-model get {W}
```

## Why determinism-first

The lifecycle is a state machine; encoding it in code (`lifecycle.py`) instead of
prose means the keyspace and the counter can never disagree, the writes preserve
the file shape and are JSON-validated, and re-running a step is idempotent. The
skill is the thin human-decision layer on top.
