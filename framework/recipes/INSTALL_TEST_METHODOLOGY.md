# INSTALL / TEST / TEARDOWN METHODOLOGY + metric-record schema

**Status:** DESIGN / SPEC (issue #104, Phase 5 Wave 1). This is the executable-shaped spec that
issue **#105** (the harness) implements. It is the second half of the install-quality design:

- **#103 — [`INSTALL_QUALITY_HARNESS.md`](./INSTALL_QUALITY_HARNESS.md)** defines *what* is tested:
  the repo-type taxonomy (buckets **B1–B12**) and the metric **vocabulary** (stable snake_case ids,
  grouped A–J). That doc is the **contract**; this doc does not redefine it.
- **#104 — this doc** defines *how* a run happens end-to-end: the repeatable
  **provision → install → assert → teardown** flow, the **harness-side teardown contract**, the
  **metric-record schema** each run emits, and the **run-over-run comparison heuristics** that flag
  regression vs improvement.

Every metric id referenced here exists **verbatim** in #103. The one exception is flagged as an
**explicit proposed addition** (`cli_bridge_soft_degrade`, §Review note) pending fold-in to #103's
vocabulary — it is not silently introduced. Bucket ids (B1–B12) and metric ids are used as-is; if you
change one, change it in #103 first.

---

## 1. Flow — provision → install → assert → teardown

A **run** is the cartesian product **{applicable buckets} × {applicable installers}**, where the two
installers are the pair #103 fixes: the standalone **`bootstrap`**
(`python3 framework/install/bootstrap.py`) and the **`cli`** bridge (`2real-team init`, which
scaffolds the mustache team then subprocesses the *bundled* `bootstrap.py --no-team --non-interactive`).
Per §Owner-decisions the CI default runs the **full** matrix through `bootstrap` and a **smoke subset
(B2, B3, B6)** through `cli`.

Each (fixture, installer) cell runs the same four stages. The stages are deliberately mechanical so
#105 can drive them without judgement calls.

### Stage 1 — Provision (hermetic fixture)

**Goal:** a disposable working copy of the bucket's layout, with a *pre-install snapshot* captured
before a single install byte lands.

1. **Mint a tmp workdir** — `mktemp -d` (or `tempfile.mkdtemp`) under the harness scratch root. One
   workdir per (fixture, installer) cell; never shared, never reused.
2. **Synthesize the bucket layout** — materialize the illustrative layout #103 lists per bucket
   (e.g. B1 empty dir; B2 `git init`, no commits; B3 `pkg/__init__.py` + `.py` files with `def`s +
   `pyproject.toml`; B4 foreign files + one commit, no `.claude`; B5 pre-existing `CLAUDE.md` +
   minimal foreign `.claude/settings.json`; B6 meta root + `api/.git` (product) + `web/.git` (infra);
   B7 a parent with the framework already installed + a `svc/` child target; B8 `ontology/structural`
   as a **file**; B9 `gen/f0000.py … fNNNN.py`). Git-init and commit exactly where the bucket demands
   it — the fresh-vs-existing verdict is computed from `.git` presence, `git rev-parse HEAD` success,
   and non-framework files (`detect_repo_state`, `bootstrap.py:728`).
3. **Copy-first for `[real]` buckets** (B10/B11) — never point the installer at the live repo. `cp`
   the real tree into the tmp workdir (or a read-only-source rsync) and operate only on the copy. The
   live `noorinalabs-main` / `botfarm_inc` trees are **never** an install target. (B12 dogfood is the
   exception — see §Teardown, it is read-only by construction.)
4. **Capture the pre-install snapshot** — walk the workdir and record `{relpath: sha256}` for every
   file (skip `.git/objects` churn by hashing tracked+untracked working-tree paths only). This map is
   the ground truth teardown must restore to. Store it in the run record's fixture entry.

The workdir is now the *fixture*. Nothing outside it is ever touched, which is what makes teardown
trivially verifiable (§2).

### Stage 2 — Install (invoke the installer per bucket)

**Goal:** run exactly one installer invocation with the bucket's flag permutation, capturing the full
`CompletedProcess` (returncode, stdout, stderr, wall-clock).

- **Resolve the permutation from the bucket.** #103's taxonomy names the install condition each
  bucket stresses; that maps to real flags (all from `bootstrap.py` argparse, `:1221–1262`):
  - B1 → `--expect fresh` (empty, non-git); B2 → defaults (`repo.expect: fresh`); B3 →
    `--with-ontology --expect existing`; B4 → the gate matrix: `--expect fresh --non-interactive`
    (must **refuse**, exit 1) **and** `--expect existing|any` (must proceed); B5 → conflict/merge
    defaults over the pre-seeded `.claude`; B6 → `--model meta-and-children` (children from the
    resolved YAML `children:` list, verbatim in non-interactive mode); B7 → `--model child`
    (`parent.path` set); B8 → defaults (robustness / fail-open); B9 → defaults + timing.
  - Every install is driven **`--non-interactive`** with **stdin closed** so `non_interactive_zero_prompts`
    is exercised on every cell (a hang/`EOFError` is a failure). Interactive legs are out of the
    automated matrix.
  - Precedence is #103's: **CLI flags > user YAML (`--install-config`) > shipped default**
    (`framework/config/install.config.default.yaml`). The harness prefers passing flags for
    determinism; where a knob has no flag it writes a one-off `--install-config` YAML into the tmp
    workdir.
- **`bootstrap` cell:** `python3 framework/install/bootstrap.py <workdir> <permutation-flags>
  --non-interactive`. Contract from source: `main()` returns **0** on success/dry-run, **1** on hard
  error, `SystemExit`/exit 1 on invalid config. The result block is the parseable oracle — it always
  ends with `-- result --` (or `-- plan --` under `--dry-run`) and keyable lines
  (`hooks/lib copied:`, `framework.config:`, `settings.json:`, `skipped (exists):`,
  `structural index:`, `team roster:`, `identity gate:`, and the target-state block
  `verdict:` / `repo gate:`).
- **`cli` cell (smoke subset):** `2real-team init --target <workdir> --non-interactive
  [--config <yaml>] [--with-ontology|--no-ontology] [--no-hooks]`. Note the bridge's extra behaviors
  the assertions must expect: it **writes a root `CLAUDE.md`** (backing up any prior one to `.bak` —
  standalone `bootstrap` does **not** write a root `CLAUDE.md`), forwards `--no-team --non-interactive`
  to the bundled bootstrap, then `_sync_install_snapshot` corrects `team.enabled/preset/size` in
  `.claude/install.config.json`. If the bundled assets are absent the bridge **soft-degrades** (notice,
  no failure) — see the proposed `cli_bridge_soft_degrade` metric.
- **Idempotency / dry-run legs.** For buckets that assert `reinstall_idempotent` and
  `dry_run_writes_nothing`, the same cell runs the installer a **second time** (byte-diff of `.claude/`
  between run 1 and run 2 must be empty; stdout carries `skipped (exists)` + `already wired`, and
  `structural index:  fresh`) and a **`--dry-run`** leg (target byte-identical after; stdout carries
  `-- plan --` / `would …`). These extra invocations are part of the same fixture's install stage,
  captured as their own sub-`CompletedProcess`.

### Stage 3 — Assert (map observed behavior → metric records)

**Goal:** for each metric in the bucket's applicable set, emit exactly one metric record (§3) whose
`observed` is derived mechanically from the captured process(es) and the post-install file tree.

- **Applicability.** A metric applies to a bucket iff the bucket exercises the surface it measures
  (e.g. `child_wiring_portable` applies to B6/B7 only; `ontology_*` to `--with-ontology` legs;
  `reinstall_parity_clean` to B12 only; `identity_gate_active` to team-mode installs). #105 owns the
  applicability matrix as data (bucket → metric-id list) so it is inspectable and diffable.
- **Measurement is one of five mechanical kinds** (#103's "how measured" column):
  - **return code** — compare `CompletedProcess.returncode` to the bucket's expected code.
  - **stdout/stderr line** — substring/parse of the stable result block (e.g. `verdict:`,
    `repo gate:`, `structural index:  SKIPPED`, `refusing to install (repo expectation gate)`).
  - **file check** — path existence / JSON parse under `.claude/`, `ontology/`, `CLAUDE.md*`,
    resolved `.git/hooks/pre-push`.
  - **byte-diff** — tree or file byte-equality (dry-run no-op, reinstall idempotency, settings
    foreign-key survival, `CLAUDE.md` `.bak` recoverability).
  - **fired-hook payload** — pipe a JSON tool payload
    (`{"tool_name":"Bash","cwd":…,"tool_input":{"command":…}}`) into the *installed*
    `.claude/hooks/dispatcher.py` and read its exit code + stdout (mirrors `test_bootstrap_smoke.py`):
    `gate_blocks_no_verify` (exit **2**, mentions `no-verify`), `gate_passes_benign` (exit 0, empty),
    `identity_gate_active`, `shell_gate_respected` (`ZSH-SAFETY` advisory under `--shell zsh`).
- **Golden manifest** backs the completeness metrics. `files_installed_complete` compares the on-disk
  framework-owned paths against a per-permutation **golden manifest** the harness owns and versions;
  `no_unexpected_files` asserts every new path (vs the pre-install snapshot) falls inside the
  framework-owned namespace **`.claude/**`, `ontology/**`, `CLAUDE.md*`, `.git/hooks/pre-push*`**
  (mirrors `_FRAMEWORK_OWNED = {".git", ".claude", "ontology"}` + `CLAUDE.md*`, `bootstrap.py:725`).
- Each assertion yields `pass` (bool, for pass/fail metrics), or a `value` number (for scored/trend
  metrics), plus `expected`/`observed` evidence and the cell's `duration_s`.

### Stage 4 — Teardown (revert the fixture, verify zero residue)

Run the teardown contract (§2), emit `teardown_residue_zero` and `no_backup_litter`, then drop the
workdir. Nothing survives the cell.

---

## 2. Teardown contract (harness-side; no product uninstall today)

**Fact grounded in source:** `bootstrap.py` ships **no** `uninstall`/`--teardown`. The only
removal-adjacent behavior is renaming a conflicting `pre-push` (or `CLAUDE.md`) to a non-clobbering
`.bak` (`_next_backup_path`, `:1100`). So teardown is **harness-side**. Whether the product *should*
ship an uninstall is an **owner-decision** (§5); until then this contract guarantees the install
footprint is fully **enumerable and reversible**, and the harness proves it every run.

Teardown has two mechanisms; the contract fixes which applies per bucket:

### 2a. Drop-the-copy (primary — B1–B11)

Because every fixture is a disposable tmp workdir (Stage 1) and every install writes **only** inside
it (guarded by `no_unexpected_files`), teardown is `rm -rf <workdir>`. Residue is zero **by
construction**. Verification:

- `teardown_residue_zero` — for the drop-the-copy path, verified by asserting **(a)** the workdir no
  longer exists after `rm`, and **(b)** for copy-first `[real]` buckets, the *source* live tree's
  `{relpath: sha256}` is byte-identical to its own pre-run snapshot (proves the live repo was never
  mutated). `value` = count of residual/unexpected paths; **pass iff 0**.

### 2b. Manifest-driven in-place uninstall (the reversibility proof — runs on a copy)

Drop-the-copy is cheap but proves nothing about whether the footprint is *knowable*. So the harness
**also** runs, on a throwaway copy of a happy-path fixture (e.g. B2 and B6), a manifest-driven
uninstall leg that exercises `teardown_residue_zero` as a real **footprint assertion**:

1. For every path in the permutation's **golden manifest**, remove it (`.claude/**`, generated
   `ontology/**`, resolved `.git/hooks/pre-push`).
2. **Restore `CLAUDE.md`** from its `.bak`/`.bak.N` if the install created a backup (CLI / child /
   B5 conflict paths); remove the harness-written `CLAUDE.md` first. Restore a conflicting
   `pre-push` from its `.bak` likewise.
3. Recompute `{relpath: sha256}` and diff against the **pre-install snapshot** from Stage 1.
   `teardown_residue_zero.value` = size of the symmetric difference (paths present after teardown
   that were not in the snapshot, **plus** snapshot paths now missing or modified). **pass iff 0.**

A non-zero result means the installer wrote a path **not** in the golden manifest (footprint drift) —
which also trips `no_unexpected_files`. This is the mechanism that keeps the manifest honest: the two
metrics jointly assert *the install footprint equals the enumerated manifest, and nothing else*.

`no_backup_litter` complements it: a **happy-path fresh** install (no conflict) must produce **zero**
`.bak*` files — backups appear only when a real conflict existed.

### 2c. B12 dogfood — read-only, no teardown

B12 asserts `reinstall_parity_clean` via `python3 framework/install/reinstall.py --check`, which
**writes nothing** (exit 0 = `.claude/` in sync with canonical `framework/assets/`, exit 1 = drift).
No fixture is provisioned and no teardown runs; the guard is that the working tree is byte-identical
before and after (`--check` is read-only). This is the dual-deploy invariant (#116), not an install.

---

## 3. Metric-record schema

A run emits one **run envelope** containing one **metric record per (fixture, installer, metric)**,
plus a computed **rollup**. Records are the atom #105 emits mechanically and #104's comparison
(§4) diffs across runs. Format: one JSON document per run (newline-delimited records are an
acceptable alternative), written to a harness-owned results dir (path owned by #105; suggestion
`framework/tests/install_quality/runs/<run_id>.json`).

### 3a. Run envelope

```json
{
  "schema_version": 1,
  "run": {
    "run_id": "2026-07-05T14:22:31Z-9fc31ab",
    "git_sha": "9fc31ab2c4e17d0f5b8a6e21d4c9f0a3b7e5d612",
    "started_at": "2026-07-05T14:22:31Z",
    "finished_at": "2026-07-05T14:24:07Z",
    "harness_version": "0.1.0",
    "host_kind": "ci",
    "installers": ["bootstrap", "cli"],
    "buckets": ["B1","B2","B3","B4","B5","B6","B7","B8","B9"]
  },
  "records": [ /* §3b */ ],
  "rollup": { /* §3c */ }
}
```

### 3b. Metric record (one per fixture × installer × metric)

> **#138 fix (implemented in #105).** The join key carries a **permutation discriminant** —
> `record_id = "<bucket>/<installer>/<permutation>/<metric>"` — because a single bucket can assert
> the same metric across multiple permutations (e.g. B4's gate matrix records
> `repo_state_gate_correct` on both the *refuse* leg and the *proceed* leg). The old three-part key
> `<bucket>/<installer>/<metric>` collided on those, so run-over-run diffs (§4) overwrote each other.
> The colliding key is no longer emitted.

```json
{
  "record_id": "B4/bootstrap/refuse/repo_state_gate_correct",
  "bucket": "B4",
  "fixture": "existing-foreign-no-claude",
  "installer": "bootstrap",
  "permutation": { "expect": "fresh", "non_interactive": true, "model": "single-repo" },
  "metric": "repo_state_gate_correct",
  "category": "A",
  "kind": "pass_fail",
  "value": true,
  "pass": true,
  "expected": {
    "exit": 1,
    "stdout_contains": ["refusing to install (repo expectation gate)", "verdict:       existing"]
  },
  "observed": {
    "exit": 1,
    "stdout_excerpt": "verdict:       existing (repo.expect: fresh)\nrepo gate:     ... Refusing: set repo.expect ...\nERROR: refusing to install (repo expectation gate)."
  },
  "duration_s": 0.83,
  "timestamp": "2026-07-05T14:22:41Z",
  "git_sha": "9fc31ab2c4e17d0f5b8a6e21d4c9f0a3b7e5d612",
  "notes": ""
}
```

**Field semantics**

| field | meaning |
|-------|---------|
| `record_id` | stable join key across runs: `"<bucket>/<installer>/<permutation>/<metric>"` (the `<permutation>` discriminant is the #138 fix — see the callout above). The comparison (§4) diffs by this key. |
| `bucket` / `fixture` | #103 bucket id (B1–B12) + the human fixture label the harness synthesized. |
| `installer` | `"bootstrap"` or `"cli"`. |
| `permutation` | the resolved install knobs for this cell (real flag names). Records *why* two cells with the same metric can differ. |
| `metric` | #103 metric id **verbatim**. |
| `category` | #103 group A–J (denormalized for fast per-category rollup). |
| `kind` | `"pass_fail"` \| `"scored"` \| `"trend"`. `scored` = a number that also carries a pass threshold (e.g. `files_installed_complete` fraction, `teardown_residue_zero` count). `trend` = a number with **no** pass/fail (e.g. `install_duration_s`), tracked only over time. |
| `value` | bool for `pass_fail`; number for `scored`/`trend`. |
| `pass` | bool for `pass_fail`/`scored`; **`null`** for `trend` (pure-trend metrics have no pass/fail — they can still flag a *regression* via §4 budgets). |
| `expected` / `observed` | the mechanical evidence: expected exit/stdout/manifest vs what was seen. Keeps a failing record self-diagnosing. |
| `duration_s` | wall-clock attributable to producing this record (for `install_duration_s`/`ontology_gen_duration_s` this **is** the `value`). |
| `timestamp` / `git_sha` | per-record capture time + the SHA under test (denormalized from `run` for standalone records). |

### 3c. Rollup (computed, §4 heuristics)

```json
{
  "per_bucket_pass_rate":   { "B1": 1.0, "B2": 1.0, "B3": 1.0, "B4": 1.0, "B5": 0.94, "B6": 1.0, "B7": 1.0, "B8": 1.0, "B9": 1.0 },
  "per_category_pass_rate": { "A": 1.0, "B": 0.97, "C": 1.0, "D": 1.0, "E": 1.0, "F": 0.95, "G": 1.0, "H": 1.0 },
  "install_success_rate":   0.978,
  "reinstall_parity_clean": true,
  "trend": {
    "install_duration_s":      { "B9": 8.42, "B2": 0.71 },
    "ontology_gen_duration_s": { "B9": 6.10, "B3": 0.22 }
  }
}
```

---

## 4. Comparison / heuristics (run-over-run)

The comparison consumes the **current** run envelope and a **baseline** (the previous run for the same
matrix, located by newest `finished_at`), joins records by `record_id`, and classifies each.

### 4a. Roll-up definitions (this doc fixes the exact math)

- **`per_bucket_pass_rate[b]`** = passing pass_fail/scored records in bucket `b` ÷ applicable
  pass_fail/scored records in `b`. Pure-`trend` records are excluded (they have `pass == null`).
- **`per_category_pass_rate[c]`** = same, grouped by #103 category A–J.
- **`install_success_rate`** (the top-line quality number) = **passing pass_fail/scored records ÷
  total applicable pass_fail/scored records across the whole matrix** — a **metric-level** (not
  bucket-level) denominator, weighted 1 per applicable metric record. *(This reconciles the two
  phrasings in #103 — see §Review note; use the metric-level definition.)*
- **`reinstall_parity_clean`** = the B12 metric's boolean, surfaced as a top-line gate.

### 4b. Per-record classification (regression vs improvement)

For each `record_id` present in both runs:

- **pass_fail / scored**: compare `pass`.
  - `true → false` = **REGRESSION**.
  - `false → true` = **IMPROVEMENT**.
  - unchanged = **STABLE**.
  - present in current only (`new`) / baseline only (`dropped`) = flagged separately (coverage change,
    not a regression by itself).
- **scored value drift** (even when `pass` unchanged): flag a **soft regression** if the scored
  `value` degrades past its budget, e.g. `files_installed_complete` fraction drops, or
  `teardown_residue_zero` rises above 0.
- **trend** (`pass == null`): compute `delta = value − baseline_value` and compare to a per-metric
  **budget**:
  - `install_duration_s` / `ontology_gen_duration_s`: **regression** iff
    `delta > max(0.5s, 0.20 × baseline)` (relative + absolute floor so noise on fast buckets doesn't
    alarm). Improvement iff it drops by the same margin. Budgets are proposed defaults — **owner
    confirms** the numbers (§5).

### 4c. Overall run verdict

- **REGRESSION** if any pass_fail/scored record went `true → false`, **or** `install_success_rate`
  dropped, **or** `reinstall_parity_clean` flipped to `false`, **or** any trend metric breached its
  budget.
- **IMPROVEMENT** if there is ≥1 `false → true` (or a trend metric improved past budget) **and** zero
  regressions.
- **STABLE** otherwise.

The verdict + the per-record transition list is the human-readable diff the harness prints and the
machine gate CI keys on (a REGRESSION verdict fails the job).

---

## 5. Owner-decision items (surface at wave-end)

Carried forward / newly raised by this spec. Several restate #103's open questions now that the
methodology depends on them:

1. **Product `uninstall`/`--teardown`?** This spec makes teardown fully harness-side (§2). If the
   owner wants `teardown_residue_zero` to be a **product** assertion rather than a harness one, the
   product needs a real uninstall. **Recommendation: keep it harness-side for v1** (manifest-driven
   removal is sufficient and already proves reversibility); revisit only if users need to uninstall.
2. **Trend budgets (numbers).** §4b proposes `max(0.5s, 0.20 × baseline)`. Confirm the tolerance,
   especially the B9 scale budget.
3. **`install_success_rate` denominator.** This spec fixes it as **metric-level** (§4a). Confirm
   (it disambiguates #103's two phrasings).
4. **Golden-manifest ownership & drift gate.** Adopted from #103 Q2: the harness owns and versions
   the per-permutation manifests; a failing `files_installed_complete` means "you changed the
   footprint — update the manifest in the same PR." Confirm this is the intended gate.
5. **CLI-vs-bootstrap coverage.** Adopted from #103 Q4: full matrix through `bootstrap`, smoke subset
   (B2, B3, B6) through `cli`. Confirm.
6. **Real-fixture copy-first rule (B10/B11/B12).** Adopted from #103 Q3: copy-first for B10/B11,
   read-only `--check` for B12, live trees never mutated. Confirm which real buckets are in scope.

---

## 6. Handoff to #105 (what the harness implementer needs)

The harness is a thin driver over this spec. Concretely, #105 must provide:

1. **A fixture provisioner** per bucket (Stage 1) that synthesizes the layout, git-inits/commits per
   bucket, copy-firsts `[real]` buckets, and captures the `{relpath: sha256}` pre-install snapshot.
2. **An applicability matrix as data** — `bucket → [metric-id]` (and `bucket → [installer]`) — using
   #103 ids verbatim, so coverage is inspectable and diffable.
3. **A permutation table** — `bucket → resolved flags` (§1 Stage 2), preferring real flags, falling
   back to a per-cell `--install-config` YAML for flagless knobs.
4. **Per-permutation golden manifests** (owned + versioned by the harness) backing
   `files_installed_complete` and the §2b manifest-driven teardown.
5. **A metric-record emitter** that runs the five mechanical measurement kinds (§Stage 3) and writes
   the §3 schema. Reuse the existing unit assertions where they already encode a check
   (`test_bootstrap_smoke.py`, `test_meta_child_install.py`, `test_reinstall_parity.py`,
   `test_settings_permissions.py`, `test_session_hooks.py`) so the harness and the unit suite speak
   one vocabulary — this layer is the integration/trend layer *on top* of them.
6. **The teardown driver** (§2): drop-the-copy for B1–B11, the manifest-driven uninstall leg on a
   copy for the reversibility proof, read-only for B12.
7. **The comparison/rollup module** (§4): load baseline by newest `finished_at`, join by `record_id`,
   classify, compute the rollup, print the transition diff, and exit non-zero on a REGRESSION verdict.

Keep the metric/bucket vocabulary identical to #103. If the harness needs a check #103 has no id for,
add the id **to #103 first** (as with `cli_bridge_soft_degrade` below), then reference it here.

---

## Review note on #103 (PR #136) — from its assigned reviewer (Nia Rossi)

#103 is in good shape and this methodology consumes its vocabulary verbatim. Four small,
non-blocking items surfaced while building the flow on top of it:

1. **`install_success_rate` denominator is stated two ways.** §I calls it "pass fraction across the
   full bucket matrix per run"; the Aggregation section calls it "fraction of applicable pass/fail
   metrics passing." Those are different denominators (bucket-level vs metric-level). §4a of this doc
   resolves it as **metric-level**; recommend #103 adopt that phrasing so there is one definition.
2. **Coverage gap: the CLI-bridge soft-degrade path has no metric id.** #103's installer table
   describes the bridge degrading gracefully (soft notice, no failure) when bundled assets are absent,
   but there is no metric asserting it. Proposed **explicit addition** (justified, per this task's
   AC4): **`cli_bridge_soft_degrade`** — run `2real-team init` with the bundled framework assets made
   unavailable; **pass** iff the bridge prints the soft notice and still exits 0 (team scaffolding
   laid, runtime skipped). Requesting Tariq fold this id into #103's set so the vocabulary stays owned
   by #103 rather than defined here.
3. **`reinstall_idempotent` (F) vs `reinstall_parity_clean` (J) read as near-synonyms.** They are
   distinct — F is byte-stable re-run of a *target* install, J is canonical↔live parity of *this*
   repo (#116). A one-line note distinguishing them would prevent future confusion.
4. **Hardcoded counts in `files_installed_complete` prose** ("23 hook modules", "14 skills") will
   drift when the asset set changes. Recommend the golden manifest be the single source of those
   counts and the prose point at it, so the doc can't disagree with the installer.

None block merge of #136; items 1–2 are the ones worth folding in since #104/#105 depend on them.
