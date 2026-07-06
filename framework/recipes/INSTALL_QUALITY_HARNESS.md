# INSTALL QUALITY HARNESS: test-repo sample + install-quality metrics

**Status:** DESIGN / PROPOSAL (issue #103, `[Explore]` spike). The sample shortlist below needs
**owner sign-off at wave-end** — see the OWNER-DECISION callouts. This is the living design doc the
build wave references: issue **#104** (methodology) and **#105** (the harness) consume the metric
vocabulary and taxonomy defined here. Keep metric ids and semantics stable once agreed — they are a
contract the harness computes against.

## Purpose

Decide *what repo types* 2real installation is tested against, and define the *statistics/heuristics*
that indicate installation quality and let us track it over time. Every metric here is asserted
against **observed installer behavior** (grounded in `framework/install/bootstrap.py`,
`framework/install/child_install.py`, `framework/install/reinstall.py`, the `2real-team init` CLI in
`python/src/real_team/`, and `framework/config/install.config.default.yaml`), not invented behavior.

## Two installers under test

The harness must exercise **both** entry points, because they wire differently:

| Installer | Entry | Notes |
|-----------|-------|-------|
| **Standalone bootstrapper** | `python3 framework/install/bootstrap.py <target> [flags]` | Deterministic, stdlib-only. `main()` returns 0 on success/dry-run, 1 on hard error; `SystemExit` on invalid config. Source of truth for install logic. Does **not** write a root `CLAUDE.md` in standalone/meta mode (only child mode does). |
| **CLI bridge** | `2real-team init --target <t> [--config yaml] [--no-hooks] [--with-ontology]` | `python/src/real_team/cli.py` scaffolds the team (mustache — this is what writes the root `CLAUDE.md`, backing up any prior one to `.bak`), then `framework_install.install_framework` subprocesses the **bundled** `bootstrap.py` with `--no-team --non-interactive`. Degrades gracefully (soft notice, no failure) when bundled assets are absent. |

Both resolve every install-time decision from the unified YAML (`framework/config/install.config.default.yaml`),
precedence **CLI flags > user YAML > shipped default**.

### Install-time knobs the harness must permute (real flags)

From `bootstrap.py` argparse: `--install-config YAML`, `--config JSON`, `--owner`, `--project-name`,
`--model {single-repo,meta-and-children,child}`, `--expect {fresh,existing,any}`,
`--shell {bash,zsh}`, `--pre-push {noop,enforce,none}`, `--reviewers`,
`--merge-model {wave-branch,direct-to-main}`, `--interactive|--non-interactive`, `--no-team`,
`--team-size`, `--no-enforce-identity`, `--with-ontology|--no-ontology`, `--no-permissions`,
`--force`, `--refresh-charter`, `--dry-run`. CLI adds `--with-hooks/--no-hooks` and a tri-state
`--with-ontology/--no-ontology`.

## Taxonomy

Repo-type buckets to test against. Each bucket names the installer condition it stresses. Buckets
prefixed **[hermetic]** can be synthesized locally with no external dependency (preferred — a
hermetic harness is reproducible in CI); **[real]** buckets reference the three real projects on this
machine and are opt-in / owner-gated.

| ID | Bucket | What it stresses | Primary install mode |
|----|--------|------------------|----------------------|
| **B1** | **[hermetic] Empty non-git dir** | `detect_repo_state` fail-open when `git` finds nothing; classification `fresh`; pre-push install skipped (no `.git`) | `--expect fresh` standalone |
| **B2** | **[hermetic] Fresh git repo** (`git init`, no commits) | Default `repo.expect: fresh` happy path; pre-push hook install into the resolved `.git/hooks/` dir | default standalone + CLI |
| **B3** | **[hermetic] Single-language app** (small Python package with `def`s) | Ontology **structural generation** over real sources (`code-graph.json` nodes must include the target's files); `--with-ontology` | `--with-ontology`, `--expect existing` |
| **B4** | **[hermetic] Existing repo, foreign files, no `.claude`** | The **fresh-vs-existing gate**: non-interactive `--expect fresh` must **REFUSE** (exit 1); `--expect existing`/`any` proceeds | gate matrix |
| **B5** | **[hermetic] Repo with a pre-existing `.claude` / `CLAUDE.md`** | Backup-on-conflict (`CLAUDE.md` → non-clobbering `.bak`), settings.json **union merge** (not overwrite, foreign keys survive), pre-push `.bak` on conflicting hook | conflict / merge |
| **B6** | **[hermetic] Meta + children** (parent + N immediate-subdir git repos) | `--model meta-and-children`; per-child parent-relative settings, child `framework.config.json`, roster subset, child `CLAUDE.md`; `product` vs `infra` flavor filtering; children carry **no** hooks/lib/charter/ontology | meta install |
| **B7** | **[hermetic] Standalone child** (points at an already-installed parent) | `--model child`; portable `$CLAUDE_PROJECT_DIR/<rel>/.claude/...` wiring (**no machine-absolute path**); parent-precondition refusal (exit 1) when parent lacks the framework | child install |
| **B8** | **[hermetic] Adversarial / degraded** (`ontology/structural` is a *file*; unreadable/invalid config; conflicting non-JSON settings) | **Fail-open**: ontology-gen failure warns + continues (still exit 0, overlay/runtime laid); invalid-config refusal; bad `settings.json` left untouched | robustness |
| **B9** | **[hermetic] Large repo** (synthesized N-thousand source files) | Install **duration** and ontology-gen scaling; no timeout/quadratic blowup | perf/scale |
| **B10** | **[real] Meta real-world** — `noorinalabs-main` (+ ~8 git children, `ontology/`) | Meta install against a genuine multi-language monorepo; child detection realism | meta, read-only copy |
| **B11** | **[real] Standalone real-world** — `botfarm_inc` | Existing single real repo with its own `.claude` already present | existing |
| **B12** | **[real] Self-host / dogfood** — `2real-team-framework` (this repo) | `reinstall.py --check` **parity** (canonical `framework/assets/**` ↔ live `.claude/**`); the dual-deploy invariant | reinstall parity |

> **OWNER-DECISION — sample shortlist to confirm at wave-end**
>
> 1. **Hermetic-first.** Proposal: the CI-run harness uses **only B1–B9** (all synthesizable, no
>    external repos, deterministic). Confirm this is the agreed default shortlist.
> 2. **Real-world fixtures (B10–B12) are opt-in, not in default CI.** They are heavier and two are
>    private working repos. Proposal: run them **on-demand/locally** against a **read-only copy**
>    (never mutate the live `noorinalabs-main` / `botfarm_inc` trees). Confirm which of B10/B11/B12 to
>    include, and confirm the copy-first rule.
> 3. **Large-repo size for B9.** Proposal: synthesize ~2,000 trivial Python files as the scale
>    fixture (enough to surface quadratic behavior, still fast). Confirm the target size / whether a
>    real large repo should stand in instead.
> 4. **Golden manifests.** The `files_installed_complete` metric (below) needs a per-flag **expected
>    file manifest** checked into the harness. Confirm the harness owns and versions these manifests
>    (they drift when installer output changes — intentional, gated by the metric).

### Proposed concrete fixtures (hermetic buckets)

Illustrative layouts the harness synthesizes into a tmp dir per run (all disposable):

```
B1  <tmp>/                      # empty, no .git
B2  <tmp>/.git/ (git init)     # no commits
B3  <tmp>/pkg/__init__.py      # + a couple of .py files with defs -> non-empty code graph
    <tmp>/pyproject.toml
B4  <tmp>/README.md, src/...   # foreign files, git-init + one commit, NO .claude
B5  <tmp>/CLAUDE.md            # pre-existing, hand content
    <tmp>/.claude/settings.json# minimal foreign settings -> tests merge + .bak
B6  <tmp>/            (meta root, git)
    <tmp>/api/.git   <tmp>/web/.git    # two child git repos (product + infra flavors)
B7  <parent>/ (framework already installed) + <parent>/svc/  (child target)
B8  <tmp>/ontology/structural  # a regular FILE (not a dir) -> forces gen failure
B9  <tmp>/gen/f0000.py ... fNNNN.py
```

## Metric Definitions

Each metric has a stable snake_case **id** (`#104`/`#105` reference these verbatim), **how it is
measured** (mechanical — a return code, a file check, a byte-diff, a parsed stdout line, or a fired
hook payload), and **pass/fail (or scored) semantics**. "Scored" metrics also emit a number the
harness trends over time. Many stdout lines are keyable (e.g. `skipped (exists)`, `already wired`,
`structural index:  fresh`) — the installer's result block is stable and parseable.

### A. Exit status & gates

| id | how measured | pass/fail |
|----|--------------|-----------|
| `install_exit_status` | `CompletedProcess.returncode` of the installer subprocess | **pass** iff equals the bucket's expected code (0 for happy paths / dry-run; **1** for the B4 non-interactive gate refusal, B7 missing-parent refusal, and invalid-config refusal) |
| `repo_state_gate_correct` | run with mismatched `--expect`; parse stdout `verdict:` + `repo gate:` lines | **pass** iff non-interactive mismatch REFUSES (exit 1, `"refusing to install (repo expectation gate)"`), `--expect any`/match proceeds, and an already-installed target (`.claude/framework.config.json` present) **skips the gate** on idempotent re-run |
| `invalid_config_refused` | feed a config missing `version`; expect `SystemExit`/exit 1 `"refusing to install … invalid"` | **pass** iff install aborts non-zero and writes nothing |
| `non_interactive_zero_prompts` | run `--non-interactive` with stdin closed; watch for hang/`EOFError` | **pass** iff completes without reading stdin (bounded wall-clock) |
| `cli_bridge_soft_degrade` | **CLI installer only.** Run `2real-team init` with the bundled framework assets made unavailable (the `real_team/_bundled/framework` payload absent). Parse stdout for the soft-degrade notice | **pass** iff the bridge prints the soft-degrade notice and still **exits 0** — team scaffolding (mustache + root `CLAUDE.md`) is laid, the `bootstrap.py` runtime step is skipped, and no error is raised. Asserts the "degrades gracefully (soft notice, no failure) when bundled assets are absent" behavior of the CLI bridge (see *Two installers under test*). |

### B. Completeness (files installed vs expected)

| id | how measured | pass/fail |
|----|--------------|-----------|
| `files_installed_complete` | compare on-disk paths under `.claude/` (+ `ontology/`, `CLAUDE.md`, resolved `.git/hooks/pre-push`) against the bucket's **golden manifest** | **scored**: fraction present/expected; **pass** iff 1.0. The expected `.claude/**` set is NOT a literal here — it is derived from `framework/assets/**` + the resolved install config by the **golden manifest single source**, `framework/install/manifest.py` (`expected_install_set(config) -> set[str]`; snapshot at `framework/install/golden-manifest.json`), which respects install mode (standalone / meta / child) and the `team.enabled` toggle. So the completeness metric can never disagree with what the installer actually copies (a coupling test in `framework/tests/test_golden_manifest.py` installs for real and asserts equality). Data-driven persona cards under `.claude/team/roster/` are asserted as a **non-empty directory** in team mode (their names/count depend on repo introspection + `team.size`), not enumerated. The manifest is scoped to `.claude/**`; a root `CLAUDE.md` (expected only for **CLI** and **child-mode** installs, not standalone `bootstrap.py`), the `ontology/**` overlay+index, and the resolved `.git/hooks/pre-push` are checked by this metric outside the `.claude/**` manifest. |
| `no_unexpected_files` | diff the target tree before/after; every new path must fall inside the framework-owned namespace (`.claude/**`, `ontology/**`, `CLAUDE.md*`, `.git/hooks/pre-push*`) | **pass** iff no writes land outside that namespace |
| `install_snapshot_recorded` | `.claude/install.config.json` exists; (CLI path) `team.enabled/preset/size` reflect what was scaffolded (`_sync_install_snapshot`) | **pass**/fail |

### C. Hook wiring (settings + config)

| id | how measured | pass/fail |
|----|--------------|-----------|
| `settings_hooks_wired` | parse `.claude/settings.json`; assert the event blocks | **pass** iff `SessionStart`→`start_dispatcher.py`, `PreToolUse` matchers == `{Bash, Agent}`→`dispatcher.py`, `Stop`→`stop_dispatcher.py`, `PostToolUse` matchers == `{Bash, Edit\|Write\|MultiEdit\|NotebookEdit}`→`post_dispatcher.py` |
| `permissions_allowlist_present` | `settings.json` `permissions.allow` contains the curated rules (unless `--no-permissions`) | **pass**/fail (and **absent** when `--no-permissions`) |
| `config_module_lists_complete` | parse `.claude/framework.config.json`; assert `hooks.pre_bash` carries the full default list (`validate_labels`, `block_squash_wave_merge`, …), `hooks.agent == []`, `hooks.stop == ["session_handoff"]` (regression guard for #84) | **pass**/fail |

### D. Behavioral (hooks actually fire)

Measured by piping a JSON tool payload (`{"tool_name":"Bash","cwd":…,"tool_input":{"command":…}}`)
into the **installed** dispatcher, mirroring `test_bootstrap_smoke.py`.

| id | how measured | pass/fail |
|----|--------------|-----------|
| `gate_blocks_no_verify` | fire `git commit --no-verify -m x` through `.claude/hooks/dispatcher.py` | **pass** iff exit **2** and stdout mentions `no-verify` |
| `gate_passes_benign` | fire `ls -la` | **pass** iff exit 0 and stdout empty (no spurious warnings) |
| `identity_gate_active` | team mode: `roster.json` present, `identity.enforce true`, `validate_commit_identity` prepended to `pre_bash`; fire a commit as a non-roster identity | **pass** iff enforced install blocks the foreign identity (and `--no-team`/`--no-enforce-identity` leaves it off) |
| `shell_gate_respected` | install `--shell zsh`, fire a bash-ism → expect `ZSH-SAFETY` advisory (exit 0); flip config to `bash` → advisory gone | **pass**/fail |

### E. Ontology

| id | how measured | pass/fail |
|----|--------------|-----------|
| `ontology_overlay_seeded` | with `--with-ontology`: `ontology/{domain.yaml,services.yaml,conventions.md,README.md}` exist | **pass**/fail |
| `ontology_structural_generated` | `ontology/structural/{code-graph.json,llms.txt}` exist; `code-graph.json` parses with `nodes`+`edges`; for a code-bearing target (B3) the target's source paths appear in `nodes` | **pass**/fail |
| `ontology_fail_open` | B8 (structural path is a file): parse stdout `structural index:  SKIPPED` + `install continues`; overlay + `.claude/hooks/dispatcher.py` still laid; **exit 0** | **pass**/fail |

### F. Idempotency & safety

| id | how measured | pass/fail |
|----|--------------|-----------|
| `reinstall_idempotent` | run twice; second run exit 0, stdout contains `skipped (exists)` **and** `already wired`; **byte-diff of `.claude/` between run 1 and run 2 is empty** (config not clobbered); with ontology, stdout `structural index:  fresh` | **pass**/fail |
| `claude_md_backup_safe` | B5/CLI/child: pre-existing `CLAUDE.md` content preserved as a non-clobbering `.bak`/`.bak.N`; new `CLAUDE.md` written | **pass** iff original bytes recoverable, none lost |
| `settings_merge_preserves_foreign` | B5: a foreign key/hook in the pre-existing `settings.json` survives the union merge; invalid pre-existing JSON is left untouched (error reported, exit 0) | **pass**/fail |
| `dry_run_writes_nothing` | `--dry-run`: target tree byte-identical after; stdout `would generate`/`would write`/`-- plan --` | **pass**/fail |

> **Note — `reinstall_idempotent` (F) vs `reinstall_parity_clean` (J) are different assertions.**
> `reinstall_idempotent` asserts that **re-running the installer on a target is a no-op** — the
> second run changes no bytes under that target's `.claude/` (config not clobbered, `skipped
> (exists)` / `already wired`). `reinstall_parity_clean` (J) asserts **canonical↔live byte
> parity for THIS repo** — that `.claude/**` matches its source in `framework/assets/**` via
> `reinstall.py --check` (the dogfood dual-deploy invariant, #116). One is about *re-running an
> install*; the other is about *this repo's live copy tracking its canonical source*. They can
> pass and fail independently.

### G. Meta / child wiring

| id | how measured | pass/fail |
|----|--------------|-----------|
| `child_wiring_portable` | B6/B7 child `settings.json`: **no absolute path** anywhere; hook commands anchored at `$CLAUDE_PROJECT_DIR/<rel>/.claude/…`; child dir has **no** local `hooks/`/`lib/`/`charter/`/`ontology/` | **pass** iff zero machine-absolute paths and correct traversal depth (`api`→`..`, `services/api`→`../..`) |
| `child_flavor_filtered` | `infra` child wires **only** `Bash`-matched `PreToolUse`/`PostToolUse` (no SessionStart / file-edit blocks); `product` child wires all events | **pass**/fail |
| `child_parent_precondition` | B7 with a parent missing `framework.config.json` or `hooks/dispatcher.py`: install refuses (exit 1) with the `parent_install_error` message | **pass**/fail |
| `child_config_inherits` | child `framework.config.json` = `model:child` + `parent` + `flavor`, inheriting `scm`/`identity`/`policy`/`hooks` from parent | **pass**/fail |

### H. Teardown / residue

| id | how measured | pass/fail |
|----|--------------|-----------|
| `teardown_residue_zero` | after a manifest-driven removal of installed paths (harness-owned uninstall: rm `.claude/`, `ontology/`, restore `CLAUDE.md` from `.bak`, rm the installed `.git/hooks/pre-push`), the tree equals the pre-install snapshot | **scored**: count of residual/stray files (target **0**); **pass** iff 0 |
| `no_backup_litter` | happy-path fresh install creates **no** `.bak*` files (backups appear only when a real conflict existed) | **pass**/fail |

> **Note — no product uninstall today.** `bootstrap.py` has no teardown/uninstall function (confirmed:
> the only removal-adjacent behavior is renaming a conflicting `pre-push` to a `.bak`). So
> `teardown_residue_zero` is asserted by a **harness-side** uninstaller driven by the same golden
> manifest. Whether the product should ship an `uninstall`/`--teardown` is an **OWNER-DECISION** (see
> Open Questions) — until then the metric guards that the install footprint is fully enumerable and
> reversible.

### I. Performance / trend heuristics (scored, not pass/fail)

| id | how measured | semantics |
|----|--------------|-----------|
| `install_duration_s` | wall-clock of the install subprocess | trend line; per-bucket soft budget (regression alarm on Δ, esp. B9) |
| `ontology_gen_duration_s` | time attributable to structural generation (B3/B9) | trend; scaling check |
| `install_success_rate` | **metric-level** pass fraction: passing applicable pass/fail (+ scored) metric records ÷ total applicable such records across the whole bucket × installer matrix per run. Weighted 1 per applicable metric record, **not** per bucket. Pure-`trend` records (no pass/fail) are excluded from both numerator and denominator | the top-line quality number tracked over time (this is the single canonical definition #104 §4a computes against) |

### J. Dogfood parity (real-world B12 only)

| id | how measured | pass/fail |
|----|--------------|-----------|
| `reinstall_parity_clean` | `python3 framework/install/reinstall.py --check` on this repo | **pass** iff exit 0 (`.claude/` in sync with canonical `framework/assets/`); the dual-deploy invariant (#116) |

## Aggregation model (proposed)

A run = the bucket matrix × the two installers. Per bucket, the applicable metrics produce a
pass/fail vector plus scored values. Roll-up = `install_success_rate` — the **metric-level** pass
fraction defined in §I (passing applicable pass/fail + scored metric records ÷ all such applicable
records across the whole matrix, weighted 1 per metric record, not per bucket) — plus the scored
trend series. `#104` §4a owns the exact scoring/weighting and computes against this one definition;
this doc fixes the **vocabulary and semantics** those scores are computed from.

## Open Questions (for #104 / owner)

1. **Product uninstall?** Should 2real ship a real `uninstall`/`--teardown` (making
   `teardown_residue_zero` a product assertion, not just a harness one), or is manifest-driven
   removal by the harness sufficient? (OWNER-DECISION.)
2. **Golden-manifest ownership & drift policy.** When installer output legitimately changes, the
   `files_installed_complete` manifest must be updated in the same PR. Confirm this is the intended
   gate (a failing completeness metric = "you changed the footprint, update the manifest").
3. **Real-fixture isolation.** For B10/B11, confirm the copy-first rule and whether children of
   `noorinalabs-main` are installed individually (B7 child mode) or only via the meta pass (B6).
4. **CLI-vs-bootstrap coverage.** Do we run the **full** matrix through both installers, or only a
   smoke subset through `2real-team init` (which forwards to `bootstrap.py --no-team`)? Proposal:
   full matrix through `bootstrap.py`, smoke subset (B2, B3, B6) through the CLI bridge.
5. **`git`-less environments.** B1/non-git covers fail-open detection, but should the harness also run
   a matrix leg with `git` unavailable on `PATH` to prove `detect_repo_state` stays fail-open?
6. **Windows / path separators.** Out of scope for v1? The child-traversal logic is posix-normalized;
   note if cross-platform is a later concern.

## Relationship to existing tests

`framework/tests/test_bootstrap_smoke.py`, `test_meta_child_install.py`, `test_reinstall_parity.py`,
`test_settings_permissions.py`, and `test_session_hooks.py` already assert many of these invariants at
**unit** granularity against a `tmp_path` install. This harness is the **integration/quality-trend**
layer on top: same assertions, but run across the full repo-type matrix, scored, and tracked over
time. The metric ids here should be reused where those tests already encode the check, so the harness
and the unit suite speak one vocabulary.
