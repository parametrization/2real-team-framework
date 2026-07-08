---
name: project_framework_extraction_state
description: Where the noorinalabs→2real framework extraction stands — shipped to v0.10.5 (Phase 6 Wave 13: HARDEN THE MACHINERY — verified_reviews per-(reviewer,PR) dedup + tightened _VERIFIED_CHECK_RE [#258/#259], rulesets-aware CI gate [#262], require_children --real-config surface + node unparseable-card warn [#251/#252]; ⚠️ W13's own retro exposed #270: _VERIFIED_CHECK_RE misses `revert->red` ASCII arrow → glyph-decided the reserved-5 rotation), what's built, what's deferred. Read first to pick up.
metadata:
  type: project
---

The `framework/` layer is the **product-neutral, config-driven extraction** of the
orchestration machinery from the sibling `noorinalabs-main` repo (`.claude/` +
`ontology/`). Source of candidate material: the `intake/` branch's
`GENERICISATION-BACKLOG.md` (36 net-new artifacts: 20 hooks, 7 charter files, 5 libs,
4 skills + the shared-config knob set + stack-opinionated assets §C).

**Current baseline (2026-07-08): released v0.10.5 — Phase 6 Wave 13 (HARDEN THE MACHINERY)
COMPLETE, merged to main, published to PyPI + npm.** Phase 4
("self-hosting & quality machinery") made the framework trustworthy run on itself; **Phase 5**
("installer robustness", v0.5.0) made the installer trustworthy on repos *other than this one*;
**Phase 6 Wave 1** (v0.6.0) *proved it in the wild* against real diverged forks; **Phase 6 Wave 2**
(v0.7.0) *closed the loop on the framework's own quality machinery*; **Phase 6 Wave 3** (v0.8.0)
*hardened the fail-closed guarantee and began porting the mined noorinalabs assets* (#102 P0 + ready P1
donors); **Phase 6 Wave 4** (v0.8.1) *validated the #102-P0 promotion pipeline in anger and closed the
charter-tree dual-deploy hole*; **Phase 6 Wave 5** (v0.9.0) *shipped the #102 P2 review-gate flagship —
a PR-review state machine, dormant by default*; **Phase 6 Wave 6** (v0.9.1) *ACTIVATED that gate on this
repo* (reviewers_required=2 + pr_review_gate_enabled=true; defaults stay dormant) *and formalized the
process*; **Phase 6 Wave 7** (v0.9.2) *HARDENED the armed gate* (oracle fail-open on comment-fetch error
via `unknown` sentinel; example.json `reviewers_required`→1; per-PR cr-cycles wording) *and cleared the
entire deferred-debt tail*; **Phase 6 Wave 8** (v0.10.0) *COMPLETED the installer* — shipped the product
`2real-team uninstall`/`--teardown` (byte-provenance guarded), killed the ontology mtime freshness flake,
and armed the `--compare` install-quality CI gate; **the first wave with a REAL blocking catch** (a
reviewer stopped user-data-loss on the flagship before it reached main); **Phase 6 Wave 9** (v0.10.1)
*FIXED the gate & scorer* — applied the W13 retro proposals: trust scorer credits resolved catches from
comment edit-history (closing the amend-in-place erasure) + difficulty weight, CI-green merge precondition
blocks a pending merge when the base has no branch-protection enforcement, documented amend-in-place +
rollup escape-hatch, mechanized wave-end review-load; **Phase 6 Wave 10** (v0.10.2) *HARDENED the
installer* — the deferred W8 follow-on: the amend path now reconciles (not unions) the config hook
module-lists onto the canonical shipped set so an upgrade-over-diverged install drops stale entries (#162),
and the real-repo provisioner got 4/5 hardening items (partial-clone fingerprint-on-failure, de-hardcoded
fixtures, merge-not-replace `--real-config` overrides, nested-child `mkdir(parents=True)`; item 4→#244, re-homed at W10 wrapup off the closed #101)
(#155); **Phase 6 Wave 11** (v0.10.3) *combined HARDEN + PROCESS* — friendly `MissingFixtureError` on a
source-less new-bucket `--real-config` (#243), an opt-in default-off zero-children guard (#244), an
amend-reconcile install-doc note (#242), the node-flake root-fix (#234: dedupe on bare names + seedable
RNG, `--retry=2` quarantine dropped), and charter process hardening (#245: per-agent temp namespacing +
e2e cd/mkdir hygiene promoted from the W14/W15 retros); **Phase 6 Wave 12** (v0.10.4) *made trust scoring
SYMMETRIC* — the owner chose option (3) "verified-clean-review positive signal" but required it be
counter-balanced by downward signals: new `verified_reviews` credit (a clean review with a substantive
`Verified:` block of concrete checks; anti-gaming `_has_verified_checks` gate rejects empty/boilerplate
blocks) earns +1 on a clean wave at ≥2, while `rework_cycles≥2` newly dings −1 and `must_fix_received`
ding tightened ≥3→≥2 (#254/PR #257, Paloma→Nia+Tariq); plus a rollup-hygiene charter runbook step
(fetch + merge `origin/<wave>` explicitly, never a stale LOCAL ref, then verify feature-code on the merge
parent) codifying the W11 slip (#255/PR #256, Ibrahim→Tariq+Paloma). **2 PRs / 0 CR / 50% conc; all 4
verdicts clean first-pass.** `trust_signals score 17`: **all four delta 0** — `verified_reviews` debut
validated BOTH directions (credited the 2 substantive #257 blocks [Nia, Tariq], anti-gaming REJECTED the
2 empty #256 blocks [Tariq, Paloma]), but each reviewer landed at 1 < 2 bonus threshold → no bump; no
decay (all have a signal), no retirement. **Reserved-5 still HELD (Tariq 5, others 4) — now
threshold-bound: rotation waits on a wave large/concentrated enough to clear ≥2 verified reviews.** New
tech-debt #258 (per-(reviewer,PR) `verified_reviews` dedup) / #259 (tighten bare-`determinism`
`_VERIFIED_CHECK_RE`). Both S1 + S2 dogfooded THIS wave (symmetric signal scored this very retro; rollup
step used in this wave's own escape-hatch rollup → content-probe PASS); **Phase 6 Wave 13** (v0.10.5)
*HARDENED THE MACHINERY* (owner picked themes 1+2) — 3 file-disjoint stories: S1 `verified_reviews`
per-(reviewer,PR) dedup [`credited_verified` set in `_account_pr`] + tightened `_VERIFIED_CHECK_RE`
[dropped bare `determinism`/`ci green`] (#258/#259, PR #266, Paloma→Tariq+Nia); S2 rulesets-aware CI gate
[`_rulesets_enforce_required_checks` reads `rules/branches/{base}`; True if EITHER classic OR rulesets
enforces; fail-open preserved] (#262, PR #267, Nia→Tariq+Ibrahim — NOTE the hook is wired IN PLACE from
`framework/assets/hooks/`, NO `.claude/hooks/` mirror, only `skills/` byte-mirrored per `reinstall.py`);
S3 `require_children` `--real-config` sidecar surface [default-off #244 preserved] + node
`usedNamesFromRoster` stderr warn on unparseable `**Name:**` (#251/#252, PR #268, Ibrahim→Nia+Paloma).
**3 PRs/0 CR/33% conc; all 6 verdicts clean first-pass w/ independent revert→red.** `trust_signals score
18`: **Tariq +1→5 EARNED (verified_reviews=2, first reserved-5 earned by signal not incumbency);
Nia/Paloma/Ibrahim 4→4 delta 0.** ⚠️ **HEADLINE: the rotation was GLYPH-DECIDED** — `_VERIFIED_CHECK_RE`
matches `revert→red` but NOT `revert->red` (ASCII arrow; the `>` breaks `revert\s*(?:→|-+|to)?\s*red`), so
both #268 reviewers' (Nia, Paloma) substantive blocks scored ZERO → Nia landed `verified_reviews=1` (only
#266, used `→`), Paloma 0; had Nia's #268 block matched she'd hit 2 as a diff-3 author → likely TAKEN the
reserved 5 on composite. Mechanical scores STAND; owner call on W18 reserved-5 deferred pending fix.
**NEW tech-debt: #269** (rulesets `parameters` non-dict guard, non-blocking crashes-into-fail-open),
**#270** (HIGH — the `revert->red` arrow false-negative). Also filed as standing backlog: **#264**
(re-audit botfarm_inc + noorinalabs-main for last-week learnings → feeds #102), **#265** (`2real-team
restore` product CLI command — `repo_space.py` has `restore_assets`+manifest [#108] but NOT surfaced on the
product CLI, and its contract is "managed assets" not "pristine"). See [[handoff]] for the exact pickup
(next = owner picks the theme; **no wave reserved**, stub #271 filed for wave 19; readiest = #270/#269 +
broaden Verified token-set [small hardening], #264 audit, #265 restore command, #110/#102 P2 [larger]).
The foundation (PR #41) shipped long ago; Phase 3 (v0.4.0) below.

**Phase 6 Wave 11 → v0.10.3 (2026-07-08, rollup direct-push merge `be5ec26`, bump `68814f8`, retro
`9b7f1ac`, ontology `52c4a89`) — "Harden + Process."** A combined hardening + process wave (owner
elected to bundle both readiness themes; reserved-5 rotation carried over as a standalone decision, NOT
changed this wave). **3 PRs, 0 changes-requested cycles, 33% concentration (3 distinct authors), 812
tests. All 6 reviewer verdicts clean first-pass** (2 per PR, author-exclusive). File-disjoint (provisioner
harness / node / charter). Meta #246; stories #248/#249/#247. Tariq QA'd all three.
- **S1 #248 (Paloma → Ibrahim + Tariq):** closes #243/#244/#242. `real_provision.py` — a source-less NEW
  bucket in a `--real-config`/`real_fixtures` partial patch now raises a friendly `MissingFixtureError`
  (naming the bucket, runner degrades to skip) instead of a bare `KeyError('source')`; the B10 zero-children
  path keeps warn-and-proceed by default but adds an opt-in `real_require_children` strict guard (extracted
  to `_guard_zero_children`) so a real run that must have children fails visibly. Plus a `config/README.md`
  note that amend `reconcile_module_lists()` resets the SIX framework-owned hook lists to canonical on
  re-install (Tariq caught the issue prose said "five"; code/doc say six). `config/README.md` single-homed.
- **S2 #249 (Ibrahim → Paloma + Tariq):** closes #234. `node/src/bootstrap.ts` — new `usedNamesFromRoster`
  parses the bare `**Name:**` field so `generateName`'s dedupe compares `First Last` (not the role-prefixed
  roster FILENAME the callers previously fed it — the actual W13 flake bug); RNG made injectable
  (`setRng`/`resetRng`/`makeSeededRng` mulberry32, production still defaults to `Math.random`). `--retry=2`
  vitest quarantine removed from `ci.yml` after verifying determinism (5–15× clean). Genuinely revert→red.
- **S3 #247 (Nia → Tariq + Paloma):** closes #245. Promoted the two W14/W15 retro fixes into the CHARTER —
  per-agent scratch-file namespacing (`agents.md`) + ad-hoc/e2e `cd`-on-`mkdir` hygiene (`branching.md`),
  applied byte-identically to both `.claude/team/charter/` and `framework/assets/team/charter/`;
  `.charter-manifest.json` refreshed via `install_charter(refresh=True)`; `charter_drift.plan()`=[]. No
  scoring/`trust_signals` touched (reserved-5 out of scope).
- **Trust (`score 16`):** every author delta 0 (one clean PR each — a single clean PR is not a bump); no
  must-fixes anywhere → no reviewer catch-credit (`must_fix_caught=0` across the board), a genuinely clean
  wave. **Tariq 5→5** (reserved HELD, no decay), **Nia 4→4** (finally an AUTHOR wave — resolves the W15
  review-only-dead-end framing, but clean difficulty-2 docs work still doesn't bump; rotation now purely
  mechanical), **Ibrahim 4→4** (meatiest story, difficulty 3), **Paloma 4→4** (multi-issue S1 + 5×
  determinism cross-review). Counter drift: none (pr=3/cr=0/conc=33 all matched recompute).
- **⚠️ ORCHESTRATOR ROLLUP SLIP (mine, non-charged):** the first rollup merged a STALE LOCAL wave branch —
  the feature PRs had merged into `origin/deployments/phase6/wave-11` server-side but the LOCAL ref was
  never fast-forwarded, so `git merge --no-ff deployments/phase6/wave-11` landed a code-less merge (state.json
  only) on main. Caught immediately by a post-merge content probe (`usedNamesFromRoster`=0 refs on main),
  fixed with a follow-up `git merge --no-ff origin/deployments/phase6/wave-11` BEFORE the bump/release — no
  release shipped without the code. **Fix for next time: at rollup, `git fetch` then merge `origin/<wave>`
  explicitly (or `git branch -f <wave> origin/<wave>` first) and verify feature-code presence on the merge
  parent.** Retro proposal filed. New tech-debt: #251 (`real_require_children` has no CLI/`--real-config`
  surface yet — programmatic-only), #252 (`usedNamesFromRoster` silently falls back to the filename string
  on an unparseable `**Name:**` card — add a warn).

**Phase 6 Wave 10 → v0.10.2 (2026-07-08, rollup direct-push merge `69e7ca6`, bump `2585ae8`, wrapup
`8fa9f2c`, ontology `d979da2`) — "Harden the installer."** The deferred W8 installer-hardening follow-on
and the second half of the approved W9→W10 two-wave plan. **2 PRs, 0 changes-requested cycles, 50%
concentration (2 distinct authors), 809 tests. All 4 reviewer verdicts clean first-pass.** File-disjoint
(`framework/install/bootstrap.py` vs `framework/harness/real_provision.py`). Meta #237; stories #238/#239.
- **S1 #238/PR#240 (Paloma → Nia + Tariq):** fixes #162. The keep-&-amend path called `write_config(force=
  False)`, which SKIPPED an existing `framework.config.json` entirely → diverged hook lists survived and the
  oracle `m_config_module_lists_complete` failed. New `reconcile_module_lists()` + `_RECONCILED_HOOK_LISTS`
  fully REPLACE the six framework-owned hook lists with the canonical set (drop stale, restore order,
  `agent`→[], `stop`→["session_handoff"]) while preserving user fields (`scm.owner`, `policy`, user
  `pre_push_commands`). Idempotent, fail-open on malformed config. All three reviewers mutation-proved a
  union would still fail the oracle.
- **S2 #239/PR#241 (Ibrahim → Paloma + Tariq):** fixes #155 items 1/2/3/5 (item 4→#244, re-homed at W10
  wrapup off the closed #101). In
  `framework/harness/real_provision.py`: (1) the read-only source after-fingerprint assertion now runs on
  partial clone failure via try/finally, `SourceMutatedError` prioritized, original error not swallowed;
  (2) removed hardcoded `/home/...` `DEFAULT_REAL_FIXTURES` (env-overridable `_default_source()`); (3)
  `--real-config`/`real_fixtures` overrides MERGE (preserve `children`) instead of replace, full spec still
  replaces (back-compat); (5) nested child paths clone via `mkdir(parents=True)`, clean error otherwise.
  Test file renamed `test_real_provisioner.py`→`test_real_provision.py` to satisfy the pairing gate.
- **Trust (`score 15`):** Paloma difficulty=2 / Ibrahim difficulty=3, both delta 0; clean wave, edit-history
  crediting did not fire. **Tariq 5→5** (reserved HELD — sole reviewer of both PRs, union/finally mutation
  probes). **Nia 4→4** (5-READY but review-only this wave; now flagship-caliber 3 of last 4 waves without
  taking the 5 — the rotation tension is the sharpest standing item). **Paloma 4→4** (flagship S1 + a
  mutation-probed S2 review). **Ibrahim 4→4** (clean S2).
- **✅ Both W14 orchestration incidents designed out** (distinct agent names + `isolation: worktree` → no
  collision; both PRs confirmed 12/12 CI-green before the gated merge → no red-merge). Two contained minor
  incidents: an errant bootstrap inside Paloma's isolated worktree (compound `cd`-after-hook-block; caught
  via `git status`, PR diff verified clean, never reached the PR) + a concurrent-agent temp-file collision
  (switched to per-agent-prefixed names). Proposals: per-agent temp-file namespacing; guard e2e `cd` on
  `mkdir`; resolve the reserved-5 rotation. New tech-debt filed: #242 (amend-reconcile doc note), #243
  (source-less new-bucket `--real-config` KeyError, pre-existing).

**Phase 6 Wave 9 → v0.10.1 (2026-07-07, rollup direct-push merge `7ee2bdb`, bump `9e8b2fa`, wrapup
`1495b46`, ontology `9368687`) — "Fix the gate & scorer."** Hardened the trust/gate machinery the team
runs on, applying the W13 retro proposals. **3 PRs, 0 changes-requested cycles, 33% concentration (3
distinct authors), ~797 tests. All 6 reviewer verdicts clean first-pass.** Patch bump (internal machinery).
OIDC published; GH Release `v0.10.1` + tag `deployments-phase6-wave-9`. Meta #228 + stories #229/#230/#231
closed. File-disjoint (scorer lib / gate hook / charter+skill).
- **S1 #229/PR#233 (Nia → Paloma + Tariq):** trust scorer reads reality. `trust_signals.py` now credits a
  resolved catch (a `Request` amended-in-place to `Replied`, which the oracle REQUIRES) from GitHub comment
  EDIT-HISTORY (GraphQL `userContentEdits`) — so `must_fix_caught`/`must_fix_received` are no longer zeroed
  by amend-in-place (the W13 erasure). Fail-open (`None` sentinel → falls back to live bodies), oracle
  untouched. Adds a coarse per-PR difficulty weight (diff magnitude → tier 1-3) feeding ONLY the reserved-5
  tiebreak, never `score_delta`. Verified by re-scoring live #227 (Tariq's erased catch now scores 1).
- **S2 #230/PR#235 (Tariq → Ibrahim + Nia):** CI-green merge precondition — story premise was CORRECTED by
  Tariq's investigation (a CI gate `validate_pr_ci_status.py` already existed; reconcile-don't-duplicate).
  The real W13 hole: no branch protection → the gate's pending path warn-allowed assuming GitHub holds the
  merge. Now `base_branch_enforces_required_checks()` (tri-state via classic protection endpoint) BLOCKS a
  pending/`--auto` merge when the base doesn't enforce the checks; fail-open + `--admin` exception preserved
  (now tested); node-flake `vitest --retry` quarantine. Node RNG root fix tracked in #234.
- **S3 #231/PR#232 (Ibrahim → Paloma + Tariq):** documented amend-in-place + the rollup direct-push
  escape-hatch as named charter steps in `pull-requests.md`; mechanized per-reviewer verdict counts in the
  `wave-end` skill (`review_load.py`).
- **Trust (`score 14`, FIRST run of the new scorer):** all three authors difficulty=3, delta 0; edit-history
  credited nothing (clean wave, no amend-in-place catches). Tariq 5→5 (HELD — standout S2 root-cause that
  corrected a mis-scoped story), Nia 4→4 (flagship S1 author, 5-ready but blocked by the single reserved-5),
  Ibrahim/Paloma 4→4. **⚠️ TWO orchestration-level incidents (mine, not the engineers'): a reused-agent-name
  worktree collision [engineers self-recovered, zero work lost] and the orchestrator merging S1 with a red
  CI check that was an infra flake [re-run green]. The CI-green hook the wave shipped is now LIVE on main, so
  the next wave's merges are protected. Retro proposals: codify safe re-spawning [distinct names + explicit
  `isolation: worktree`]; gate manual merges on confirmed-green CI; reserved-5-vs-difficulty-ties.**

**Phase 6 Wave 8 → v0.10.0 (2026-07-07, rollup direct-push merge `8210ad4`, bump `25dd116`, wrapup
`e04a849`, ontology `ae38d22`) — "Complete the installer."** Finished the installer story with a new
user-facing capability. **3 PRs, 1 changes-requested cycle, 33% concentration (3 distinct authors), 746
tests** (+29). Minor bump (new command). OIDC published (npm `latest`=0.10.0; PyPI `/0.10.0/json`=200);
GH Release `v0.10.0` + tag `deployments-phase6-wave-8`. Meta #221 + stories #222/#223/#224 closed; tracked
issues #142/#141/#148 closed. Stories were file-disjoint (install+package / ontology-freshness /
harness+CI). **The first NON-flawless wave under the 2-reviewer regime — and the first with a genuine
blocking catch:** on the flagship destructive `uninstall`, reviewer Tariq caught that the amend-disposition
teardown blind-unlinked a pre-existing USER file colliding with a framework manifest path (unrecoverable
data loss) that co-reviewer Nia had clean-approved past.
- **S1 #222/PR#227 (Paloma → Nia + Tariq):** product `2real-team uninstall` / `bootstrap.py --teardown` —
  reverse an install to byte-identical pre-install state. New `framework/install/uninstall.py` (+ package
  bridge `framework_install.py` + `cli.py` command). Removes exactly the golden-manifest set **gated on
  framework byte-provenance** (`_derivable_asset_bytes` reconstructs shipped/rendered bytes; a
  user-modified/foreign file at a manifest path is PRESERVED, never unlinked — this is the fix for Tariq's
  amend-path data-loss must-fix), restores consented-archive backups, idempotent, `--non-interactive`/
  `--dry-run` safe. Closes #142. **1 changes-requested fix cycle.**
- **S2 #223/PR#226 (Ibrahim → Nia + Paloma):** kill the ontology mtime freshness flake. A **regeneration
  barrier** in `ontology_gen/refresh.py`: when the staleness guard fires, byte-compare a deterministic
  regen against the prior index; byte-identical ⇒ report `fresh` (not a phantom `regenerated`). Closes
  #141. (Merged with a `node (20)` CI flake on its head — Python-only change, main green.)
- **S3 #224/PR#225 (Tariq → Ibrahim + Paloma):** implement `cli_bridge_soft_degrade` metric (bundled
  assets absent → exit 0 + notice) + grade it; arm the `--compare` regression gate as a CI job
  (`install-quality-gate.yml`) against a committed baseline. Closes #148.
- **Trust (`score 13` + distribution):** reserved-5 (Tariq) **VALIDATED on a real blocking catch** (last
  wave re-earned on authorship, this wave exercised the catch the 5 rewards). Paloma 4→4 (flagship author,
  clean fix of a legit must-fix). Ibrahim 4→4 (mechanical −1 for the node flake OVERRIDDEN). Nia 4→4 (deep
  reviews, but a documented review-MISS on the same PR — one more decays to 3). **⚠️ Headline finding:
  amend-in-place (required by the gate oracle) ERASES the review-cycle trust signals — `must_fix_caught`
  (reviewer) + `must_fix_received` (author) both read 0 once a Request is resolved in place, so the wave's
  best review scored mechanically zero and the distribution overrode by hand.** W13 retro proposals: credit
  resolved catches from comment edit-history; add a CI-green precondition to the merge step; make
  amend-in-place explicit in the reviewer flow.

**Phase 6 Wave 7 → v0.9.2 (2026-07-07, rollup PR #220 → main @ direct-push merge `adce920`, bump
`0a1c5d0`, wrapup `beb3998`, ontology `21e671f`) — "Harden the armed gate."** Hardened the gate armed in
W6 and **cleared the entire deferred-debt tail** (5 items / 3 waves). **3 PRs, 0 CR cycles, 33%
concentration (3 distinct authors), 717 tests** (+11). OIDC published (npm `latest`=0.9.2; PyPI
`/0.9.2/json`=200); GH Release `v0.9.2` + tag `deployments-phase6-wave-7`. Meta #213 + stories
#214/#215/#216 closed; folded debt #207/#208/#211 closed. **First wave whose story merges were themselves
governed by the LIVE 2-reviewer gate** (the oracle allowed #217/#218/#219 only after 2 distinct clean
verdicts each) — the gate governed its own maintenance.
- **S1 #214/PR#218 (Tariq → Nia + Paloma):** fail-open the oracle on comment-**fetch** error. Added an
  `unknown` sentinel to `pr_review_state.review_state()` (returned on transport error instead of masking
  as `pending`); `validate_pr_review` treats `unknown` as fail-open **ALLOW** while genuine
  `pending`/`changes_requested` still BLOCK; `compute_state()` (pure) untouched, still never fabricates
  `approved`. End-to-end test (stubs only `_pr_comment_bodies`) pins fetch-error→ALLOW. Closes #207.
- **S2 #215/PR#217 (Ibrahim → Paloma + Tariq):** `framework.config.example.json` `reviewers_required`
  2→1 (matches schema/`_DEFAULTS` default — adopters who later enable the gate no longer inherit a silent
  2-bar) + guard test pinning it to the schema default; wave-end `--cr-cycles` wording rebound to per-PR
  ("PRs that took ≥1 changes-requested round") to match `trust_signals.rework_cycles` at N≥2. This repo's
  armed runtime `.claude/framework.config.json` (=2) untouched. Closes #208, #211.
- **S3 #216/PR#219 (Paloma → Nia + Ibrahim):** `charter_drift.py plan()` now cross-checks each rendered
  charter module's on-disk sha256 against `.charter-manifest.json` (catches byte-match-but-stale-manifest);
  `ensure_gitignore_entries` normalized for idempotency (dedup/sort/blank-collapse). Both W9 carry-overs.
  Paloma held **sole golden-manifest integration-owner** (no regen needed — zero installed-path changes).
- **Trust (score 12 + distribution discipline): all implementers delta 0; reserved-5 ROTATES on
  pre-registered criteria.** **Tariq 4→5** (re-earned: authored the flagship #207 correctness fix — the
  W11-registered "own a tracked follow-up" path). **Nia 5→4** (decay: clean-no-catch wave, 0 authored
  PRs, 2 Replied reviews — the exact W11-pre-registered decay condition, parity with Tariq's W10). Paloma
  4→4, Ibrahim 4→4 (clean single PRs).
- **Operational finding (new):** with the gate now *permanently* armed (unlike W6, where local main was
  still dormant at rollup time), the rollup PR can't clear `gh pr merge` (it carries no verdicts of its
  own). Landed #220 via the documented **direct-push escape hatch** (direct push to main is not gated).
  W12 retro proposes codifying this as a named step. **Deferred-debt list is now EMPTY** (both W11
  proposals applied in-wave: hardening slot = this wave; review-load balanced Nia2/Paloma2/Tariq1/Ibrahim1).

**Phase 6 Wave 6 → v0.9.1 (2026-07-07, rollup PR #212 → main @ merge `191918e`, bump `911ccd6`,
wrapup `bcea7f6`, ontology `734787a`) — "Activate the review gate."** Turned on what W5 shipped dormant.
**3 PRs, 0 CR cycles, 33% concentration, 706 tests** (+6). **First wave under the 2-reviewer regime — 6
clean verdicts across 3 PRs, every PR cleared 2 distinct approvals first pass.** OIDC published (npm
`latest`=0.9.1; PyPI `/0.9.1/json`=200); GH Release `v0.9.1` + tag `deployments-phase6-wave-6` on merge
`191918e`. Meta #201 + stories #202/#203/#204 closed.
- **THE GATE IS NOW ARMED ON THIS REPO:** `.claude/framework.config.json` has `policy.reviewers_required=2`
  + `policy.pr_review_gate_enabled=true`. `gh pr ready`/`gh pr merge` on a PR with <2 distinct clean
  reviewer verdicts (or any unresolved Must-fix) is BLOCKED. **Framework DEFAULTS stay dormant** (schema/
  `_DEFAULTS`/example: gate off, reviewers_required=1) so downstream adopters still install inert.
  **Escape hatch:** disarm via a direct config-only commit to `main` (direct push is NOT gated; gate is
  fail-open on oracle *exception*). Practical consequence for future waves: **every PR now needs 2
  distinct reviewers**; rollup→main merges are done while local main is still dormant (or via the hatch),
  wrapup/bump/memory are direct pushes (ungated).
- **S1 #202/PR#206 (Paloma → Nia + Tariq):** armed the gate + proved it LIVE (self-contained throwaway PR
  #205: blocked 0/2 → passed 2/2); integration test binds to the real repo config; charter merge-rule +
  escape hatch documented.
- **S3 #204/PR#209 (Nia → Ibrahim + Tariq):** folded both W5 proposals into `charter/issues.md` (new
  "Wave Planning: Shared Artifacts & Frozen Contracts" section) + N=2 assignment rule into
  `charter/pull-requests.md`; both marked APPLIED. Nia was **sole charter integration-owner** (dogfooding
  proposal #1 in the same wave it was written).
- **S2 #203/PR#210 (Ibrahim → Paloma + Tariq):** proved the oracle N-of-M on **real** 2-reviewer data
  (PR #206's own Nia+Tariq verdicts) + mutation-proved no 1-reviewer assumption survives in
  `trust_signals`/`lifecycle`. Tests-only. Routed the `--cr-cycles` wording finding (#211) to S3/Manager.
- **3 tracked follow-ups from this activation (out of scope):** #207 (gate blocks rather than fail-opens
  on a transient comment-fetch error — `review_state` swallows it to `pending`), #208 (example.json ships
  `reviewers_required=2` — latent footgun if adopter later enables), #211 (`wave-end` `--cr-cycles`
  wording double-counts at N≥2 vs per-PR `rework_cycles`).

**Phase 6 Wave 5 → v0.9.0 (2026-07-07, rollup PR #200 → main @ merge `12300f3`, bump `03dba99`,
wrapup `afbe386`, ontology `30e4f7e`) — "PR-review state machine (dormant)."** The #102 **P2**
review-gate flagship. **3 PRs, 0 CR cycles (all three Replied first pass), 33% concentration (3 distinct
authors), 0 CI-red, 694 tests** (+33). OIDC published (npm `latest`=0.9.0; PyPI `/0.9.0/json`=200); GH
Release `v0.9.0` + lightweight tag `deployments-phase6-wave-5` on merge `12300f3`. Meta #193 + stories
#194/#195/#196 closed; #102 stays OPEN (more P2 remains).
- **S1 #194/PR#197 (Paloma → Tariq):** flagship `framework/assets/lib/pr_review_state.py` — a pure,
  unit-testable `compute_state(verdicts, reviewers_required)` + a thin fail-open `review_state(repo, pr)`
  wrapper that **reuses** `trust_signals.parse_verdicts`/`_pr_comment_bodies` (no parallel parser).
  `ReviewState = {state, approvals, reviewers_required, unresolved_must_fix}`; `approved` iff distinct
  **Requestor** (reviewer) clean approvals ≥ required AND no unresolved Must-fix; any unresolved Must-fix
  ⇒ `changes_requested`; else `pending`. Fetch error degrades to `pending`, never a false `approved`.
  Caught a real bug in the frozen contract (it said "requestees"; the charter grammar makes the reviewer
  the `Requestor:`) and escalated it — Hiro confirmed on #193.
- **S3 #196/PR#198 (Nia → Tariq):** `framework/assets/hooks/block_gh_pr_review.py` (PreToolUse, **live**,
  unflagged — only blocks always-wrong cases: raw `gh pr review`, malformed grammar, self-review;
  `Requestee: N/A` status turns exempt) reusing `validate_review_comment_format` (pinned reuse-guard) +
  enriched `review-pr` skill (config-aware, gate-compatible templates).
- **S2 #195/PR#199 (Ibrahim → Nia):** `framework/assets/hooks/validate_pr_review.py` (PreToolUse merge
  gate) — blocks `gh pr ready`/`gh pr merge` on a not-approved PR, but **SHIPS DORMANT** behind new
  `policy.pr_review_gate_enabled` (default **false**). `reviewers_required=1` is live here, so a live gate
  would self-lock; the flag check short-circuits *before* the oracle is consulted (Nia verified
  structurally). Activation is a deliberate future follow-up. Fail-open. Both new hooks registered in
  `hooks.pre_bash` across all sync points (schema/`_DEFAULTS`/bootstrap/example/this-repo).

**Phase 6 Wave 4 → v0.8.1 (2026-07-07, rollup PR #192 → main @ merge `bdb4bd9`, bump `61f725d`,
wrapup `2f2572f`) — "Trust the promotion pipeline."** Deliberately small hardening/dogfood wave
applying **both** W3-retro proposals before #102 P2 builds on the pipeline. **2 PRs, 0 CR cycles (both
Replied first pass), 50% concentration, 0 CI-red, 645 tests** (+16). OIDC published (npm `latest`=0.8.1;
PyPI `/0.8.1/json`=200); GH Release `v0.8.1` + lightweight tag `deployments-phase6-wave-4` on merge
commit. Both PRs merged clean (no conflicts).
- **S1 #189/PR#190** (Ibrahim → review Nia) — **charter-tree dual-deploy gate**: new read-only
  `framework/install/charter_drift.py --check` renders each canonical charter module with THIS repo's
  config and diffs vs runtime `.claude/team/charter/*.md`, failing CI on genuine content divergence only
  (placeholder substitutions never false-positive). Closes the #116 hole where `reinstall.py`'s
  `_MANAGED_TREES` covered only `skills/`. **Caught + remediated 4 pre-existing drifted charter modules
  on first run** (branching/charter/hooks/pull-requests) + added the missing `.charter-manifest.json`
  (repo predated #77). Wired as pytest gate `test_charter_drift.py`. *Applies W3-retro proposal #1.*
- **S2 #187/PR#191** (Paloma → review Tariq) — **first real dogfood of the #102-P0 pipeline + ledger
  policy settle**: ran `promotion-audit` on the real 3-candidate ledger (all classified DECIDE, none
  mis-auto-promoted); determinism re-verified byte-identical. **Caught + fixed a real bug** —
  `has_promotion_markers()` bare-substring-matched, so `charter/skills.md` (which quotes the marker in a
  fenced ``` block) false-positived as AUTO; fix strips fenced code before matching, regression tests
  pinned against the real doc (load-bearing). **Ledger policy settled:** live `generic_prompt_ledger.json`
  stays gitignored (transient queue), durable trail = committed per-wave audit log
  (`paths.promotion_audit_log/wave_<id>.md`), and `bootstrap.ensure_gitignore_entries()` wires the
  gitignore default into every install path (standalone/meta-parent/meta-child/standalone-child) so
  downstream adopters auto-get it. Closes #187. *Applies W3-retro proposal #2.*
- **Trust: all delta 0** (clean wave, `trust_signals.py score 9`). Ibrahim 4→4, Paloma 4→4 (both clean
  single PRs, no bump per policy); Nia 5, Tariq 5 hold reserved-5s from W8 (no scoring catch this wave —
  both Replied; per-wave/decaying, a substantive PR or real catch due to keep them anchored).
- **New tech-debt (feedback_log, 2 fold-in proposals):** (1) `charter_drift.py plan()` doesn't
  cross-check `.charter-manifest.json` checksums vs live charter (Nia) → manifest blind spot; (2)
  `ensure_gitignore_entries` exact-line match could dup a variant existing form + `is_owned` now treats
  any `.gitignore` at any depth as owned (Tariq).

**Phase 6 Wave 3 → v0.8.0 (2026-07-06, rollup PR #186 → main @ merge `4af3866`, bump `bb2bcd7`,
retro `0945b1c`) — "Fail-closed foundation + flagship asset port."** **5 PRs, 1 CR cycle, 40%
concentration, 0 CI-red, 629 tests.** OIDC published (npm `latest`=0.8.0; PyPI `/0.8.0/json`=200);
lightweight tag `deployments-phase6-wave-3`. Owner bundled everything flagged at end of W2:
- **Track A (fail-closed hardening):** **#175/PR#182** (Nia) — `dispatcher.py` now
  **blocks-unless-`FAIL_OPEN`**: uncaught `check()` exception in a fail-closed hook (incl.
  `require_load_bearing_test`) blocks instead of allowing; 9 legacy fail-open hooks declare
  `FAIL_OPEN=True` (bit-identical). *Resolves W2-retro proposal #1.* **#174+#176/PR#183** (Tariq) —
  load-bearing-test gate is now **per-behavior-file** (closes the diff-wide loophole) + seeded
  `refactor` exception class so pure refactors aren't hard-blocked.
- **Track B (#102 flagship port, P0 + ready P1 donors; P2 DEFERRED):** **#102-P0/PR#185** (Paloma) —
  promotion/genericization pipeline: `generic_prompt_ledger` + silent `suggest_generic_prompt`
  PostToolUse feeder hook + `generic_prompt_tracker` lib + deterministic **`promotion-audit` skill**
  (memory→charter→skill→hook auditor, pure-function-backed) + charter `skills.md` marker convention.
  **#179/PR#184** (Ibrahim) — P1 donors `validate_branch_freshness` (opt-in, `0`=disabled after QA
  fix), `roster_union_sync` + `roster_consistency_check` (meta∪child drift gate).
- **Track C:** **#180/PR#181** (Nia) — charter norm *a finding defeating a shipping feature's core
  guarantee is a Must-fix, not tech-debt* (W2-retro proposal #2, applied). **#177/PR#181** — rename
  cost-out report `framework/recipes/RENAME_COSTOUT.md` (repo+PyPI+npm; effort M; keep `0.x`; no rename).
- **The #164 durable ledger fired for real** (first contested wave): Tariq's #184 changes-requested
  verdict (the branch-freshness zero-tolerance-default footgun) recorded into `wave_8_review_catches`
  at issue-time, **survived** his `Request→Replied` amendment → `must_fix_caught=1` scored correctly.
- **Trust: Tariq 5→5** (the #184 catch), **Nia 4→5** (composite tie-top: 2 PRs incl. #175 keystone —
  **2nd earned 5**), Paloma 4→4 (clean flagship), Ibrahim 4→4 (1 received+rework, caught+fixed).
- **New process debt (feedback_log, unapplied):** (1) make `reinstall.py` mirror the charter tree —
  `_MANAGED_TREES` covers only `skills/`, so `team/charter/**` edits are hand-dual-deployed (drift
  passes CI today); (2) dogfood the `promotion-audit` skill before trusting its auto-promotions.

**Phase 6 Wave 2 → v0.7.0 (2026-07-06, rollup PR #173 → main @ merge `33c6388`, bump `b82939d`,
retro `6eee7b5`) — "Close the quality/process loop."** Clean wave: **4 PRs, 0 CR cycles, 25%
concentration, 0 CI-red, 507 tests** (+41). OIDC published (npm `latest`=0.7.0; PyPI `/0.7.0/json`
=200); lightweight tag `deployments-phase6-wave-2` on the merge commit (no Release → no
double-publish). Delivered all 3 owner-approved W6-retro process proposals:
- **#164/PR#171** (Paloma, flagship) — durable issue-time `wave_{W}_review_catches` ledger in
  `trust_signals.py` so `must_fix_caught`/`must_fix_received` survive the verdict amend-in-place
  convention; legacy live-comment fallback = zero regression. **Fixes the W1 scorer blind spot**
  but is NOT exercised by a no-amendment wave → first real test is the next contested wave.
- **#167/PR#172** (Tariq) — fail-closed `require_load_bearing_test` PreToolUse hook **hard-blocks**
  `gh pr create`/`gh pr ready` when a diff adds behavior without a test; auditable
  `LOAD_BEARING_TEST_EXCEPTION=<class>:<rationale>` override (policy empty by default). Live in this
  repo. Dual-deployed across 5 config sync points + charter docs.
- **#168/PR#169** (Nia) — `lifecycle.py wave assert-kickoff` + `kickoff_persisted` guard; wave-start
  skill (both dual-deploy copies) now fails loud if `state.json` doesn't advance `current_wave`.
- **#158/#163/#161/PR#170** (Ibrahim, S4) — restored `review-pr` asset↔runtime parity (#158),
  guarded `_fsync_dir` `os.close` fail-open path (#163, load-bearing this time), CONTRIBUTING doc (#161).
- **Trust: all delta 0** (clean wave). Tariq **holds 5** (reserved-5 not decayed — carried flagship
  S2 + all 3 reviews, signal not quiet); Paloma/Ibrahim/Nia hold **4**. Both W6 negative patterns
  visibly corrected (Paloma shipped #164 with test+fixture; Ibrahim's #163 test is load-bearing).
- **New tech-debt (OPEN):** **#174** S2 `test_touched` is diff-wide not per-file · **#175**
  `dispatcher.py` swallows uncaught hook exceptions as ALLOW (undermines #167's fail-closed intent —
  resolve before trusting the gate org-wide) · **#176** pre-seed a `load_bearing_test_exceptions`
  class (empty default hard-blocks pure refactors). 2 process proposals in feedback_log (unapplied).

**Phase 6 Wave 1 → v0.6.0 (2026-07-06, rollup PR #166 → main @ `8da3562`, bump `da1b705`) —
"Prove it on real repos" (validation).** Owner rolled up after one wave (no Wave 2 stack). OIDC
published (npm `latest`=0.6.0; PyPI `/0.6.0/json`=200, index CDN-lagged). Lightweight tag
`deployments-phase6-wave-1` (no Release → no double-publish). **5 PRs, 3 CR cycles (all Tariq,
load-bearing), 40% concentration, 466 tests.**
- **#153/PR#154** real-repo provisioner: clone-at-pinned-SHA (`git clone --no-local` + detached),
  **read-only** (HEAD+porcelain fingerprint → `SourceMutatedError`), wired as harness `--include-real`
  (B10/B11, opt-in). **#109/PR#157** botfarm upgrade-over-live-install study (byte-identical restore
  on 150-file diverged fork). **#101/PR#156** noorinalabs fork-reconciliation audit
  (`NOORINALABS_RECONCILE.md`). **#152/PR#159** installer docs (README/framework README/CONTRIBUTING).
  **#149/PR#160** durability hardening: `atomic_io` parent-dir fsync (mutation-proven test),
  `archive_assets` manifest-before-move, `no_backup_litter` baseline, `.claude-backups` gitignore.
- Scope = `framework/` dev-tooling + install fixes + docs; **no `framework/assets/**` runtime changes
  → #116 dual-deploy did NOT apply.** Both fixtures turned out to be **diverged forks** of this
  framework, which reframed #101 as fork-reconciliation and #109 as upgrade-over-live-install.
- **Trust: Tariq 4→5 (first earned 5 in project history** — `must_fix_caught=3` vs 0 for all others,
  distribution-discipline reserved 5); others hold at 4. **Process finding #164:** the verdict
  amend-in-place convention erases per-reviewer `must_fix_caught` from `trust_signals` (recompute
  reads current comment state) — W6 signals were reconstructed from historic evidence; `cr-cycles=3`
  preserved via `wave_6_counter_corrections`. Deferred (OPEN): **#102** (18-asset port, its own wave),
  tech-debt **#161/#162/#163/#164**, plus Phase-5 **#142/#148/#141**, exploratory **#110**.

**Phase 5 → v0.5.0 (2026-07-06, rollup PR #151 → main @ `7e6fe8b`) — installer robustness.**
Both waves rolled up as a unit (owner decision: stack W2 on W1, one release). Published via OIDC
to PyPI + npm (both `latest` = 0.5.0); lightweight tag `deployments-phase5-wave-2` for
traceability only. **8 feature PRs, 0 must-fix, 0 CR cycles, 442 tests.**
- **Wave 1 (global 4) — discovery**: **#131** scorer false-positive gate (last Phase-4 artifact —
  gate `review_false_positives` on `_has_must_fix_items`); **#106** `~/.claude` user-space audit →
  found load-bearing gap **G1** (installer never wrote the agent-teams env flag, so a fresh install
  couldn't spawn a team); **#103** test-repo taxonomy B1–B12 + ~31 metrics; **#104**
  install/test/teardown methodology. 3 design docs in `framework/recipes/`
  (`INSTALL_QUALITY_HARNESS.md`, `INSTALL_TEST_METHODOLOGY.md`, `USER_SPACE_AUDIT.md`).
- **Wave 2 (global 5) — build**: **#105** `python3 -m framework.harness` install/test/teardown
  harness (11 modules; B1–B9 + inline dogfood default; B10/B11 real fixtures opt-in behind
  `--include-real`, clone-at-pinned-SHA, never touch live repos) + **#138** record_id permutation
  discriminant; **#139** golden manifest `expected_install_set(config)` in `framework/install/manifest.py`
  (single source for install-completeness, derived from the installer's own iterators, `--check`
  drift guard, retires hardcoded counts); **#107** consented **idempotent** user-level install
  (`bootstrap.py --user-space`) — **closes G1** (check-existing no-op / backup-or-amend / never
  clobbers; reusable `consent.py`/`backup.py`/`user_space.py`); **#108** repo-level consent +
  backup/archive/**restore** (`repo_space.py` archives to sibling `.claude-backups/<UTC>/`, out of
  Claude load scope, byte-identical restore) + **#145** atomic settings write
  (`atomic_io.atomic_write_text`: temp→fsync→os.replace) across both paths.
- A latent flat-vs-nested config seam (harness passed flat permutation dicts; #139 reads nested
  dotted config) was caught in #105 review and fixed **pre-merge** via
  `permutation_to_install_config`, so `files_installed_complete` grades against the real manifest
  (activation verified post-merge, `install_success_rate 1.00`).
- Install code (`framework/install/`) and harness (`framework/harness/`) are NOT part of the
  `.claude/**` runtime → outside reinstall-parity scope. Team trust holds at **4 across the board**
  — third consecutive fully-clean score (steady state). Deferred follow-ups (all OPEN tech-debt):
  **#142** product `uninstall` · **#148** `cli_bridge_soft_degrade` + `--compare` CI gate · **#149**
  durability/fidelity hardening · **#141** pre-existing flaky meta-install idempotency test.

**Phase 4 (2026-07-05, two waves off `deployments/phase4/wave-{1,2}`):**
- **Wave 1 → v0.4.1** (#98 trust-vocab, #99 dogfood lifecycle into wave skills, #100 phase-aware
  `branch.integration`, #111 `validate_review_comment_format` gate). Dogfooding the retro surfaced
  4 defects → #116/#117/#118/#119.
- **Wave 2 → v0.4.2** (10 issues): **#116** reinstall-on-change rule + `framework/install/reinstall.py`
  + `--check` CI parity gate (byte-mirror scoped to `skills/`; hooks/lib canonical-by-reference;
  charter via `--refresh-charter`); **#117** `{wave}`→phase-local ordinal; **#118** verdict-grammar
  semantic warn tier; **#119** roster name normalization; **#77** `--refresh-charter` three-way
  charter refresh (`team/.charter-manifest.json`); **#82** copy-shared rm+recopy; **#94** merge-model
  wording + `policy.merge_model`→`wave-branch`; **#74** ontology_gen consumer-runtime exclusion;
  **#75** meta-child ontology install test; **#90** wave-audit zero-pad. 373 tests.
- **Wave 1 authoritative re-score closed** (corrected 3 mis-tagged approvals per #118); last scorer
  artifact isolated as **#131**. See `trust_matrix.md` + `feedback_log.md`. Both Python and Node
packages publish via **OIDC trusted publishing** — no long-lived tokens (PR #57 switched the
workflows; trusted publishers are configured on PyPI and npmjs.com for
`parametrization/2real-team-framework` + the respective `publish-*.yml` workflow). v0.3.0 had
failed to publish (PyPI trusted-publisher unconfigured; `NPM_TOKEN` expired end of May 2026);
v0.3.1 (PR #58) republished cleanly via OIDC with provenance/attestations. v0.3.2 (PR #59) is a
docs release: the README Skills section now documents all 11 skills (6 team-workflow + 5
runtime) so the PyPI/npm long-description metadata — baked per release — covers the runtime
skills installed by `--with-hooks`. Repo holds **zero** Actions secrets. Verify live state with
`gh release list` / `gh pr list` before assuming.

**v0.4.0 (2026-07-02, Phase 3 = PRs #64–#97, released from main @ `6605da8`):** the installer
overhaul. Unified `install.config.yaml` (v1 schema, stdlib `miniyaml`, precedence flags > user
YAML > shipped defaults at `framework/config/install.config.default.yaml`, resolved snapshot
written to `.claude/install.config.json`) + `--non-interactive`; meta/child install modes
(children get parent-relative hook paths, product vs infra flavor; one ontology at the meta
root with cross-repo aggregation — children get none); ontology generated at install; pre-push
installer (`noop` default); `.claude/`-scoped permissions allowlist merged into settings;
7-file modular charter template with `{{key}}` context substitution; Node CLI bridges to the
bundled Python bootstrap (prepack copies `framework/` into the npm package); Agent/Stop events
route through the dispatchers; skills 5→13. CI runs on PRs to `deployments/**` too. Also ships
the previously unreleased CLAUDE.md-at-root behavior (#60/#61). Release tag convention: `v0.x.y`
— both publish workflows fire on ANY published release, so exactly one release per version.

**Built + tested end-to-end** (framework tests 39 passing, python tests 103 passing):
- The config keystone (`framework/config/framework.config.schema.json`) + loader/logger/parsers.
- Both dispatchers (PreToolUse/PostToolUse) reading `hooks.pre_bash`/`hooks.post_bash`.
- 10 hooks: 4 safety (no_verify, git_config, worktree_self_delete, zsh_wordsplit) + 2 SCM
  (validate_labels, warn_pipe_mask_rc) + 3 CI (validate_pr_ci_status,
  validate_workflow_paths_coverage, block_squash_wave_merge) + 1 identity (validate_commit_identity).
- 4 libs: pr_ci_state (CI oracle), upsert_status_keys, trust_signals, lifecycle.
  See [[reference_lifecycle_state_machine]] and [[project_upsert_status_keys_seeding]].
- The deterministic bootstrapper + repo-introspecting roster generator with per-child
  union rosters (see [[reference_per_child_union_rosters]]).
- The `wave-lifecycle` orchestration skill.
- CLI wiring: `2real-team init` installs the runtime by default (see [[reference_cli_framework_bundling]]).
- **Skill discovery fix + generic session-lifecycle skills (2026-06-27, on `main`):** this
  repo's flat `.claude/skills/<name>.md` files were converted to `<name>/SKILL.md` (Claude Code
  only discovers the dir layout). Added generic, config-driven, fail-open `session-start` +
  `handoff` skills (framework/assets/skills/ install payload + active in `.claude/skills/`).
- **Ontology system ported (2026-06-27, PR on branch `framework/ontology-system`):** the
  two-layer model genericised — `lib/ontology_gen/` structural generator + cross-repo
  aggregator with **automatic child-git-repo discovery** (`discover_repos` scans the parent's
  immediate subdirs for `.git`), `hooks/ontology_tracker.py` (config-aware, INERT unless an
  ontology dir exists), a new `hooks.post_file` PostToolUse dispatch path (Edit/Write/MultiEdit),
  and `/ontology-librarian` + `/ontology-rebuild` skills. Bootstrap now copies `lib/` recursively
  (subpackages + `__init__.py`). 47 framework tests. See `framework/recipes/ONTOLOGY_SYSTEM.md`.

**Deferred — the pickup queue** (also in `framework/README.md` § "Next"). Owner directive
2026-06-27: port the FULL orchestration suite generically — nothing is fundamentally
project-coupled, it's config-decouplable:
1. ~~Full wave/phase lifecycle skill chain~~ — **largely shipped in v0.4.0** (Phase 3 Wave 2
   ported/enriched: phase-review, wave-audit, wave-retro, team-reset, plan-phase, retro,
   wave-start, close-stale-issues → 13 skills total). Remaining coupling to revisit: GitHub
   Projects v2 field-sync (`board.*`), reviewer counts (`policy.reviewers_required`).
2. **Review-gate tranche**: port `validate_pr_review` (~1189-line N-reviewer/TechDebt gate) +
   the `pr_review_state` oracle that reuses it. (`validate_review_comment_format` **shipped** in
   Phase 4: #111 ported it, #118 added the semantic warn tier.) Rest still deferred.
3. ~~`validate_branch_freshness`~~ — **shipped in v0.8.0** (#179/PR#184, opt-in `0`=disabled). Still
   deferred: mid-wave reachability `gh` wrapper around `lifecycle.classify_reachability`.
4. ~~Node CLI runtime install~~ — **shipped in v0.4.0** (#70): node CLI bundles `framework/`
   and subprocesses the Python bootstrap (`node/src/framework-install.ts`).
5. Optional LLM persona personalities (`python/src/real_team/personas.py`).
6. ~~Phase 3 tech-debt #74/#75/#77/#82/#90/#94~~ — **all shipped in Phase 4 Wave 2 (v0.4.2)**.
7. ~~**Phase 5 (installer robustness)**~~ — **COMPLETE, shipped in v0.5.0** (both waves: #131 scorer
   gate, #103/#104/#106 design+audit, #105 harness, #107/#108 consented user/repo install closing G1,
   #138/#139/#145 folded). Remaining Phase 5 *exploratory* backlog (deferred, OPEN): #101/#102
   (reverse-map noorinalabs against the new harness), #109 (botfarm before/after), #110 (ship the
   installer as a CC skill); plus tech-debt #142/#148/#149/#141.

**Architecture overview:** [[reference_config_driven_architecture]].
**Commit/PR mechanics for this repo:** [[feedback_framework_commit_pr_mechanics]].
