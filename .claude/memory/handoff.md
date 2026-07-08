<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-08 (Phase 6 Wave 16 / global wave 21 SHIPPED; v0.11.1; trust scoring UN-PARKED — #275 CLOSED)

## ✅ READ FIRST — trust scoring is UN-PARKED; the #275 calibration is resolved and closed
The two-wave park (W19/W20 deltas held) is over. The owner decided #275 with **"fix the composite, keep
the 1–5 scale, un-park from W21"** and that is now **executed and shipped (v0.11.1)**:
- **New composite** (`framework/assets/lib/trust_signals.py`): credits `must_fix_caught` +
  `verified_reviews` at `REVIEW_VALUE_WEIGHT=2` and caps `difficulty_points` at `DIFFICULTY_COMPOSITE_CAP=2`.
- **W21 deltas APPLIED (first write since W18):** **Paloma 4→5** (reserved-5 rotated IN — composite 5, top
  of wave on BOTH author + reviewer axes: caught the #287 bypass as reviewer AND shipped the hardest clean
  PR), **Tariq 5→4** (rotated OFF the single-seat reserved-5), **Nia 4→4**, **Ibrahim 4→3**
  (`must_fix_received=2` + `rework=1`).
- **The fix works:** under the OLD author-only composite Tariq (pure reviewer this wave) scored ~0 and would
  be structurally demoted; the NEW composite lifts him to 4. Paloma takes the 5 by genuinely out-contributing,
  NOT by the W20 failure mode (a clean author displacing a defect-catcher). High-value review now competes.
- **#275 is CLOSED.** Standing matrix is now **Paloma 5, Tariq 4, Nia 4, Ibrahim 3.**

## ⚠️ New tech-debt from this wave — #288 (make the scorer author-exclusive)
The merge gate (`validate_pr_review`) is author-exclusive; `trust_signals`/`review_load` are NOT. A W21
author reply-to-must-fix on #287 wore reviewer verdict grammar (`Requestor: Ibrahim`), so the extractor
counted the PR author as a third reviewer of his own PR → spurious `missed_catches=1`/`verified_reviews=1`.
Worked around by amending the note to a plain comment (re-verified signals → 0) BEFORE deltas were computed;
**#288** filed for the durable fix (one shared author-exclusivity helper across all three surfaces + a
charter note that author replies are plain comments, never `Requestor:` grammar). This did NOT affect the
merge outcome (gate excluded the self-verdict).

## ⚠️ Review gate + rollup mechanics (LIVE, unchanged)
`.claude/framework.config.json`: `policy.reviewers_required=2` + `policy.pr_review_gate_enabled=true`.
Every PR needs **2 distinct clean reviewer verdicts** (charter `Requestor:` grammar, author-exclusive) and
no unresolved Must-fix, or `gh pr merge`/`gh pr ready` is BLOCKED.
- Clean verdict = `RequestOrReplied: Replied` + `Must-fix: None` + a substantive `Verified:` block (earns
  `verified_reviews`; anti-gaming rejects boilerplate). Clear a `Request` by AMEND-IN-PLACE.
- **`gh api -X PATCH` comment bodies from a file MUST use `-F body=@file`, NEVER `-f body=@file`** — `-f`
  sends the literal `@path` string (silent corruption). Hit twice this wave. (Memory updated.)
- `require_load_bearing_test` HARD-BLOCKS `gh pr create`/`gh pr ready` when a behavior file adds substantive
  lines without a test — NOW with a default-on `docs` exception (#284) for pure-doc diffs.
- CI-GREEN ENFORCED AT MERGE. **ROLLUP→MAIN via ESCAPE HATCH** — `git checkout main && git pull --ff-only`,
  `git fetch origin`, `git merge --no-ff origin/<wave>` (owner `-c` identity + `-F` message), **content-probe
  main** (grep new symbol) BEFORE bump, `git push`. Wrapup/bump/retro/memory/ontology are direct pushes.
- **HOOKS + lib WIRED IN PLACE** — `.claude/settings.json` runs `framework/assets/hooks/*` and
  `framework/assets/lib/*` directly; NO `.claude/hooks/`/`.claude/lib/` mirror. So the skill-bundled helpers
  that resolve libs via `.claude/lib` (e.g. `wave-end/review_load.py`) must be run from the
  `framework/assets/skills/...` copy, not the `.claude/skills/...` copy. `reinstall.py --check` mirrors only `skills/`.
- **npm publish CI drift:** `publish-npm.yml` now pins `npm@^11.5.1` (npm@12 dropped node-20 support) + has
  a `workflow_dispatch` trigger for re-publishing. If a release's npm job fails, dispatch that workflow on
  main (it publishes whatever version is in `node/package.json`).

## Pickup (next concrete step)
**W21 (Phase 6 W16 / global 21) is SHIPPED: v0.11.1 on main + PyPI + npm; wrapped; retro done + trust
un-parked; issues #275/#284/#285 closed.** Next action is an **owner decision** on Wave 22:
- **wave-22 stub = #289** (`wave_22_meta_issue` reserved; `wave peek → 22`). Per the standing plan, **Phase 7
  opens with sibling-repo mining (#264 → #102)** as the owner-deferred exploratory section — leading
  candidate theme, but the owner sets it. Do NOT start a wave without theme + kickoff approval.
- Carry-forward for W22: **#288** (author-exclusive scorer), npm-CI durability (bump runner to node 22),
  #264/#102 mining, #110.

## What W21 shipped (v0.11.1, "reward the reviewer + clear the gate debt" — 2 stories, 2 PRs / 1 CR / 50%)
- **S1 #275 / PR #286** (Paloma → Nia + Tariq): reserved-5 composite fix. Clean first-pass.
- **S2 #284 / PR #287** (Ibrahim → Paloma + Tariq): docs/refactor `load_bearing_test_exceptions` class. **1 CR
  cycle** — the 2-reviewer gate caught a real `_patch_is_docs_only` self-close+trailing-code bypass; fixed
  fail-safe on both classifier branches with revert→red tests.

## Mechanical state
- Branch: main, HEAD after the W21 retro/memory/ontology commit; v0.11.1 live on PyPI + npm.
- Open PRs: none.
- Lifecycle: `current_wave=wave-21`, `last_completed_wave=wave-21`, `global_wave_seq=21`,
  `wave_21_completed_at` set; counters 2/1/50; `wave_22_meta_issue=#289` reserved (peek → 22).
- Trust: **Paloma 5, Tariq 4, Nia 4, Ibrahim 3** (W21 applied; #275 closed).
- Open issues: #289 (wave-22 stub), #288 (author-exclusive scorer), #264 (Phase 7 sibling-repo mining),
  #110, #102. Housekeeping: large backlog of stale LOCAL feature branches (all merged server-side) — harmless.
