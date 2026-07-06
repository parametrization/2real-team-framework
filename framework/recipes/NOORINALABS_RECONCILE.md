# noorinalabs-main ↔ 2real Framework Reconciliation Audit (#101)

**Status:** AUDIT / mapping only. **No assets are ported in this PR** — porting is #102.
**Author:** Paloma Gupta (Principal). **Wave:** Phase 6 Wave 1.

`noorinalabs-main` is **not** a foreign repo to mine — it is an independently-evolved deployment
of *this same framework*, with its own `.claude/team/charter`, `roster.json`, `phases/`, and a
wave history running (by its own commit log) into Phase 7+. This document therefore treats the
task as **fork reconciliation**: where have the two forks diverged, and what did noorinalabs
invent that 2real should pull upstream?

The headline number: noorinalabs carries **433 tracked `.claude/**` files** vs. 2real's donor set
of ~60 canonical assets. noorinalabs is the more mature fork on almost every axis.

---

## 1. B10 harness run — evidence

Run via the real-repo provisioner (#153) with an explicit `--real-config` sidecar (children
supplied explicitly; the hardcoded `DEFAULT_REAL_FIXTURES` was **not** relied on, per #155 item 2).

**Scope:** parent + 3 representative children (Hiro's proposed set — all three verified present as
single-level child dirs, so #155 item 5 (nested path) does not bite):

| Role | Source | Pinned SHA (`refs/heads/main` via `git ls-remote`) | flavor |
|---|---|---|---|
| meta parent | `noorinalabs-main` | `00d2acf82732188bd7133a91199cd16fb266d437` | — |
| child | `noorinalabs-user-service` | `3bc103fb85d27ead2764c2bba6d32e6dfbb56bc5` | product |
| child | `noorinalabs-deploy` | `5f68b31ce98b9f1ac8c73cc9cd0ae7b1f6d907af` | infra |
| child | `noorinalabs-isnad-ingest-platform` | `e10bc2e3b322192702a2ed61cd16b2a6af8f1eb3` | product |

Pins were resolved from `refs/heads/main`, **not** the checked-out branch — every source's live
working tree sat on a different feature-branch HEAD (e.g. user-service checked-out `56d7a9c…` vs
main `3bc103f…`), exactly the concurrent-work hazard the provisioner's `ls-remote` design guards
against.

**Command** (sidecar kept local-only in scratch, per #155 item 2 — the sidecar shape is in §7):

```
python3 -m framework.harness --include-real --buckets B10 --installers bootstrap \
  --no-dogfood --real-config <local-sidecar>.json
```

**Rollup:**

| Metric | Result |
|---|---|
| `install_success_rate` | **0.625** (5/8 graded metrics passed) |
| graded records | 8 (+ 1 trend `install_duration_s` = 0.30 s, ungraded) |
| per-category | A 1.00 · B 1.00 · F 1.00 · G 0.50 · H 0.00 |
| **read-only invariant** | **HELD** — all 4 live sources byte-identical `{HEAD, porcelain}` before/after; provisioner raised no `SourceMutatedError` |

**Zero-residue on the live tree (independent proof):** re-fingerprinting all four sources after the
run produced an **empty symmetric diff** vs. before (HEADs and porcelain-line counts identical,
including the deliberately-dirty isnad-ingest-platform working tree at 53 porcelain lines). The
clone-at-pinned-SHA into scratch never touched the source.

### The 3 failures are all "install-over-an-existing-framework" artifacts, not harness bugs

Because noorinalabs *already has the framework installed*, the clean-install metrics measure
merge/pre-existing-state effects rather than installer defects:

| Failed metric | Observed | Root cause |
|---|---|---|
| `child_wiring_portable` (G) | `noorinalabs-user-service: unexpected local lib` | noorinalabs children carry their **own** `.claude/lib/` (e.g. `check_dockerfile_base_pin.py`, `pre_commit_ci_sync.py`) — a **divergent child model**: their children are not pure lib-less children (see §5). |
| `no_backup_litter` (H) | 4 `.bak`: 2×`CLAUDE.md.bak` + 2×`errors.jsonl.bak.*` | Two are our installer backing up their pre-existing `CLAUDE.md`; **two are noorinalabs's own checked-in** `.claude/annunaki/errors.jsonl.bak.20260429…/…20260430…` — a hygiene smell in their tree. |
| `teardown_residue_zero` (H) | 9 residue: `.claude/settings.json`, child `settings.json`+`CLAUDE.md`, `ontology/structural/*` | Manifest-driven uninstall cannot restore files that **pre-existed and were merged** (settings.json, CLAUDE.md) or regenerated (ontology structural index). Expected on a repo that already ships these. |

These are honest signals about the harness's clean-install assumptions, not failures of the
provisioner. See §6 for the durability follow-ups (#149).

---

## 2. Reconciliation methodology

Two comparisons, both mechanical:

1. **Donor diff** — `git ls-files .claude` on the noorinalabs parent @ pin vs. `framework/assets/**`
   (basename set-difference for hooks / lib / skills / charter).
2. **Golden-manifest diff** — noorinalabs's installed footprint vs.
   `expected_install_set(config)` (`framework/install/manifest.py`) for the meta config.

Each divergent asset is classified **port** (generalizable, 2real should adopt) / **investigate**
(promising but needs de-branding or design reconciliation) / **skip** (project-specific), with a
priority **P0–P3**.

---

## 3. Assets noorinalabs EVOLVED that 2real should pull upstream

### 3a. FLAGSHIP — the promotion / genericization pipeline (P0)

This is the single most valuable divergence and directly serves 2real's reason to exist (extracting
generic framework assets from a live deployment). It is a cohesive subsystem, not one file:

| Asset | Kind | Delta vs 2real | Rec | Prio |
|---|---|---|---|---|
| `generic_prompt_ledger.json` | state | Durable audit trail of per-artifact genericize/skip decisions (`decided_at`, `decision`, `detail`, `wave`). 2real has **nothing** equivalent. | port | **P0** |
| `hooks/suggest_generic_prompt.py` | PostToolUse hook | Silent state-feeder: records touched `.claude/` artifacts into a pending ledger, no mid-task nudge (deliberately de-escalated from a per-edit `systemMessage` that decayed — their main#716). | port | **P0** |
| `lib/generic_prompt_tracker.py` | lib | `record_candidate` / ledger read-write backing the hook + skill. | port | **P0** |
| `skills/promotion-audit/**` | skill (+ helpers.py, run.py, templates/, tests/) | Deterministic **memory→charter→skill→hook** promotion auditor: auto-promotes AUTO-tier, files DECIDE-tier draft issues, writes a per-wave audit log. Pure-function backed for byte-identical output. | port | **P0** |
| `team/charter/skills.md` § Promotion Pipeline Marker Convention | charter | The authoritative marker-shape rules the pipeline parses (`<!-- Promoted from memory… -->` / `**Promotion provenance:**`). | port | **P0** |
| `team/promotion_audit_log/**` | data | ~25 per-wave audit logs — evidence the pipeline runs continuously. | investigate (adopt format, not their data) | P1 |

**Expected improvement:** gives 2real a mechanical, enforcement-hierarchy-driven pipeline
(`hook > skill > charter > memory`) for exactly the promotion work it currently does by hand.

### 3b. Governance / charter modules 2real lacks (P1)

2real charter has: agents, branching, charter, commits, hooks, issues, pull-requests.
noorinalabs adds seven; six are generalizable:

| Charter module | Rec | Prio | Note |
|---|---|---|---|
| `skills.md` | port | P0 | (see 3a — backs the pipeline) |
| `state-claims.md` | port | P1 | Discipline for status claims — pairs with 2real memory `feedback_refresh_before_status_claim`-style lessons. |
| `communication.md` | port | P1 | Feedback-flow / inter-agent comms conventions. |
| `emergency-mode.md` | investigate | P1 | Fast-path override protocol; reconcile with 2real approval gates. |
| `tech-decisions.md` | port | P2 | ADR-style decision recording. |
| `artifact-ownership.md` | port | P2 | Who-owns-what across `.claude/`. |
| `brand.md` | **skip** | — | noorinalabs-specific brand identity. |

### 3c. Roster / headcount enforcement (P1)

2real already ships **per-child union rosters** (memory `reference_per_child_union_rosters`);
noorinalabs ships the *enforcement checks* 2real lacks:

| Asset | Rec | Prio | Note |
|---|---|---|---|
| `lib/roster_union_sync.py` | port | P1 | Enforces meta∪child roster union — directly complements 2real's `roster_gen`. |
| `lib/roster_consistency_check.py` | port | P1 | Roster/charter consistency guard. |
| `lib/headcount_budget.py` | port | P2 | Team-size budget check. |

### 3d. Branch-freshness (P1 — 2real has a *deferred* item for exactly this)

| Asset | Rec | Prio | Note |
|---|---|---|---|
| `hooks/validate_branch_freshness.py` (+ tests) | port | **P1** | 2real's memory lists "branch-freshness" as **deferred tech-debt**. noorinalabs has a shipped, tested implementation — a ready reference/donor. |

### 3e. Wave-lifecycle & GitHub-Projects automation (P1/P2 — architectural, investigate)

noorinalabs and 2real diverge **architecturally** here. 2real: unified `lib/lifecycle.py` (monotonic
allocator) + `wave-start`/`wave-end`/`wave-lifecycle` skills. noorinalabs: split
`wave_seq.py`/`wave_status.py`/`wave_merge_model.py`/`wave_field_option.py`/`wave_unwrapped.py` +
`wave-kickoff`/`wave-scope`/`wave-wrapup` skills + a `team/lifecycle.md` doc. **Do not port
piecemeal** — reconcile the models first.

| Asset | Rec | Prio |
|---|---|---|
| `wave-scope`, `wave-kickoff`, `wave-wrapup` skills | investigate (vs 2real wave-start/end) | P1 |
| `lib/wave_field_option.py`, `wave_status.py`, `wave_merge_model.py`, `wave_unwrapped.py`, `wave_seq.py` | investigate (vs `lifecycle.py`) | P1 |
| `hooks/post_wave_kickoff_comment.py`, `post_label_change_wave_field_sync.py`, `_wave_label_parse.py` | port (GH-Projects wave-field sync — 2real uses Projects too) | P2 |
| `hooks/validate_wave_audit.py`, `validate_wave_label_evidence.py`, `validate_wave_context.py` | port (wave-evidence gates) | P2 |
| `hooks/auto_add_issue_to_board.py`, `lib/board_audit_drift.py`, `lib/apply_implementor_labels.py`, `skills/board-audit` | port (board automation) | P2 |
| `lib/verify_deployable_merge.py` | investigate (vs 2real merge models) | P2 |

### 3f. Ontology-consultation enforcement (P2)

2real ships the `ontology-librarian`/`ontology-rebuild` skills + ontology hooks; noorinalabs adds
the *gates* that force consultation:

| Asset | Rec | Prio |
|---|---|---|
| `hooks/enforce_librarian_consulted.py`, `enforce_ontology_context.py`, `_consultation_sentinel.py` | port | P2 |

Note: **cross-repo ontology aggregation exists in BOTH** (`lib/ontology_gen/aggregate.py`). What
noorinalabs adds on top is the **meta-parent status rollup** `cross-repo-status.json` (194 KB) +
`ontology/structural/cross-repo-graph.json` (the "central aggregator + overlay wiring" from the
#101 body, commit `08e56db`). → **investigate** (P2) as a meta-mode status layer 2real may want.

### 3g. Process / QA hygiene hooks & lib (P2)

| Asset | Rec | Prio | Note |
|---|---|---|---|
| `hooks/block_shutdown_without_retro.py` | port | P2 | Enforces retro before shutdown — 2real has retro/wave-retro skills but no gate. |
| `hooks/block_stale_tmp_message_file.py` (+ parser tests) | port | P2 | Guards stale tmp message files — relates to 2real `feedback_framework_commit_pr_mechanics` (msgs via `-F file`). |
| `hooks/validate_edit_completion.py` | investigate | P2 | Post-edit completeness gate. |
| `hooks/validate_pr_review.py`, `lib/pr_review_state.py`, `hooks/block_gh_pr_review.py`, `skills/review-pr` | port | P2 | PR-review state machine + gates. **Note:** 2real's *runtime* `.claude/skills/` already has `review-pr` but it is **absent from `framework/assets/skills/`** — a source↔runtime drift (#116) to close regardless. |
| `hooks/auto_sync_main.py` + `lib/sync_main.py` | port | P2 | Auto-sync deployment branch ← main. |
| `lib/verify_commit_identity.py` | investigate | P2 | Complements 2real's `validate_commit_identity` hook. |
| `lib/doc_freshness.py`, `lib/memory_budget.py` | port | P2 | Doc/memory hygiene budgets — generalizable. |
| `skills/file-bug`, `lib/premise_check.py`, `lib/check_fixture_realism.py` | port | P2 | QA tooling (bug intake, premise validation, fixture-realism lint). |
| `lib/check_agent_liveness.py`, `lib/check_child_checkouts.py` | investigate | P2 | Meta-orchestration health checks — generalizable if de-coupled from their layout. |

### 3h. The `annunaki` error-capture subsystem (P2 — investigate, needs de-branding)

`hooks/annunaki_log.py`, `annunaki_monitor.py`, `lib/annunaki_parse.py`, `skills/annunaki`,
`skills/annunaki-attack`, `.claude/annunaki/errors.jsonl`. A structured **error-ledger + monitor**
subsystem. The name is noorinalabs-flavored, but their own `generic_prompt_ledger.json` already
marks `annunaki_log`/`annunaki_monitor` as `genericized` (with `GENERIC_HOOK_ANNUNAKI_*_PROMPT.md`
drafts) — so a de-branded generic form is a proven direction. → **investigate** (rename +
generalize) P2.

---

## 4. Novel top-level artifacts

| Asset | Rec | Prio | Note |
|---|---|---|---|
| `.claude/context/{project-architecture,user-preferences}.md` | investigate | P3 | Content is project-specific; the *pattern* (a seeded `.claude/context/` scaffold) may be generic. |
| `.claude/plugins/{blocklist,known_marketplaces}.json` | skip | P3 | Claude Code plugin config; low framework value. |
| `.claude/annunaki/errors.jsonl(.bak.*)` | skip (data) | — | Runtime data; the `.bak.*` files are the hygiene smell surfaced by `no_backup_litter` (§1). |

---

## 5. Assets 2real HAS that noorinalabs lacks / diverges on (upgrade-gap — no action here)

Recorded for completeness (AC). These are where 2real is ahead or simply structured differently;
none is a "pull from noorinalabs" candidate.

| 2real asset | noorinalabs state | Note |
|---|---|---|
| `lib/lifecycle.py` (monotonic wave allocator) | split into `wave_seq`/`wave_status`/`wave_merge_model` | 2real's unified model is arguably cleaner; see 3e — reconcile, don't replace. |
| `hooks/start_dispatcher.py`, `stop_dispatcher.py` | folds SessionStart/Stop into `session_start.py`/`session_handoff.py` + `dispatcher`/`post_dispatcher` | Dispatcher-architecture divergence. |
| `hooks/_framework_config.py`, `_framework_log.py` | uses `annunaki_*` logging + inline config | 2real's shared-config module (`reference_config_driven_architecture`). |
| `hooks/ontology_refresh.py` + `lib/ontology_gen/refresh.py` | no standalone refresh hook | Minor 2real-ahead. |
| **Divergent child model** | children carry own `.claude/lib/` (§1) | 2real children are lib-less (invoke parent's); noorinalabs children install domain lib locally. **This is the root of the `child_wiring_portable` failure** — a genuine model difference to decide on, not a bug. |

---

## 6. Durability / harness findings (for #149)

1. **Clean-install metrics mis-model "install over an existing framework."** `no_backup_litter`,
   `teardown_residue_zero`, and `child_wiring_portable` all fail against noorinalabs purely because
   it already ships framework assets. B10's metric set should either (a) gain a "pre-existing
   framework" baseline mode that diffs against the *installed* state, or (b) mark these three as
   advisory (not graded) for `real=True` meta buckets. **File under #149.**
2. **`no_backup_litter` counts the source repo's OWN checked-in `.bak` files** (`errors.jsonl.bak.*`)
   as installer litter. The metric should scope `.bak` detection to files the *install* created
   (diff vs pre-install snapshot), not any `.bak` in the tree.
3. **#155 item 4 (B10 zero-children guard) — addressed defensively.** A bare `--include-real` B10
   with no `--real-config` still installs a degenerate zero-children meta. This PR adds a
   non-fatal `warnings.warn` in `provision_real` when a `meta-and-children` spec resolves to zero
   children, so the degenerate case is visible instead of silent. #155 items 3 (override-merge) and
   5 (nested child path) did **not** bite this run (full spec supplied; single-level children) and
   are left to their owners.

---

## 7. The `--real-config` used (reproducibility)

Kept **out of checked-in defaults** (#155 item 2) — this is the example shape; a run supplies it as
a local sidecar with machine-absolute `source` paths:

```json
{
  "B10": {
    "source": "<abs>/noorinalabs-main",
    "pin": "00d2acf82732188bd7133a91199cd16fb266d437",
    "ref": "refs/heads/main",
    "model": "meta-and-children",
    "children": [
      {"path": "noorinalabs-user-service",           "source": "<abs>/noorinalabs-main/noorinalabs-user-service",           "pin": "3bc103fb85d27ead2764c2bba6d32e6dfbb56bc5", "flavor": "product"},
      {"path": "noorinalabs-deploy",                 "source": "<abs>/noorinalabs-main/noorinalabs-deploy",                 "pin": "5f68b31ce98b9f1ac8c73cc9cd0ae7b1f6d907af", "flavor": "infra"},
      {"path": "noorinalabs-isnad-ingest-platform",  "source": "<abs>/noorinalabs-main/noorinalabs-isnad-ingest-platform",  "pin": "e10bc2e3b322192702a2ed61cd16b2a6af8f1eb3", "flavor": "product"}
    ]
  }
}
```

---

## 8. Prioritized shortlist for #102

- **P0 — promotion pipeline (3a):** `generic_prompt_ledger.json` + `suggest_generic_prompt.py` +
  `generic_prompt_tracker.py` + `promotion-audit` skill + `charter/skills.md` marker convention.
- **P1:** `validate_branch_freshness.py` (closes a deferred 2real item) · roster enforcement
  (`roster_union_sync.py`, `roster_consistency_check.py`) · charter `state-claims.md` /
  `communication.md` · wave-lifecycle model reconciliation (investigate before porting).
- **P2:** ontology-consultation gates · board/wave-field automation · retro-gate,
  stale-tmp guard, PR-review state · doc/memory budgets · QA tooling (`file-bug`, `premise_check`,
  `check_fixture_realism`) · annunaki de-branding · cross-repo status rollup.
- **P3 / skip:** `brand.md`, `plugins/`, `context/` content, deployment-stack assets
  (`validate_vps_host`, `warn_ghcr_image`, `check_dockerfile_base_pin`, `validate_lockfile_paths`,
  `watch-deploy`, `pre_commit_ci_sync`, `lint_skill_graphql_pagination`, `auto_set_env_test`).

**Port-worthy count:** ~18 discrete assets/subsystems recommended `port`, ~11 `investigate`,
the remainder `skip`. The clear P0 is the promotion pipeline — it is the mechanism 2real needs to
do *this kind of reconciliation* mechanically in future.
