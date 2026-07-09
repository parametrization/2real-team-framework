<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-09 (Phase 7 Wave 2 / global wave 23 — ROLLED UP TO MAIN, NO RELEASE CUT)

## ✅ READ FIRST — Wave 23 is on `main`. Trust scoring is PARKED. No release tagged.

Wave 23 ("The record must not lie") is **complete and merged to `main`** via rollup PR #316
(merge commit `cdbc009`). All 12 CI checks green. The owner explicitly approved the rollup and
**stopped before any release** — no tag, no PyPI, no npm. `main` is at `v0.12.x` unreleased.

**Do NOT tag or publish a release without explicit owner go-ahead.**

## What landed (4 stories, all 2/2 gate-approved, file-disjoint)

| PR | Issue | Author | Rounds | What |
|---|---|---|---|---|
| #306 | #296 | Paloma | 1 CR | `_NEGATIVE_SIGNAL_FIELDS` single source of truth; `_VACUOUS_BODY_RE` rejects `"Name: None"`/`-`/`n/a`/blank |
| #307 | #300 | Nia | 2 CR | `/wave-end` derives counters from `trust_signals extract`; 3 read-trust defenses (REST rate-limit preflight, `PR_LIST_RC=$?`, cross-check) |
| #305 | #301 | Ibrahim | clean | reserved-5 pluralized to "top relative performer(s)"; ties intended, documented |
| #309 | #304 | Tariq | 1 CR | `validate_pr_body.py` PreToolUse hook — blocks closing keywords in PR bodies |

All four issues **closed from commit trailers**, each attributed to its own author's commit
(verified: #296 ← Paloma's `6bd8c7a`, not Tariq's hook commit). That attribution *was* the point of #304.

## 🚨 THE BLOCKER — #314: the scorer contradicts itself. Wave 23 deltas NOT applied.

`composite()` (the reserved-5 ranking key) subtracts `must_fix_received`, `ci_red_merges`,
`review_false_positives` — but **NOT `missed_catches`**. `score_delta()` charges −1 per missed catch.

Reproduced live on Wave 23 data:
- **Ibrahim holds the highest composite (7) AND the worst delta (−2 → 1)** simultaneously.
- Because the reserved 5 requires `composite == top`, his 7 caps **Paloma and Tariq 5 → 4 for a third
  engineer's number**.

Root cause: `verified_reviews=2` and `missed_catches=2` come from **the same two reviews** — his clean
verdicts on #307 and #309, each carrying a substantive `Verified:` block, each past a defect the
co-reviewer caught. `_has_verified_checks` validates that a receipt is *detailed*, not that the review
*worked*. Composite pays `+2×2` for the ritual; delta charges `−1×2` for the outcome.

**Owner decision: park all deltas.** Matrix scores held at Paloma 5, Tariq 5, Nia 3, Ibrahim 3.
Mechanical output recorded as evidence in `trust_matrix.md` under "Wave 23 Trust Updates". Precedent: W15, W20.
This is the **second consecutive wave** Ibrahim's positives were gated away (Wave 22 needed an owner override).

## Open issues from the Wave 23 sweep — every one "a component asserting something it never verified"

- **#314** — composite/delta negative-set split. **Headline for Wave 24; blocks scoring.**
- **#308** — charter claims the merge gate doesn't author-exclude. False since #293/#294 (Wave 22).
  **Owner scoped this into Wave 24.**
- **#302** — policy question: grade `has_negative()` suppression (hard gate vs soft offset). Orthogonal to #314.
- **#310** — no structural guard forces a new negative `Signals` field into `_NEGATIVE_SIGNAL_FIELDS`.
- **#311** — `trust_signals extract` returns `{}` at **exit 0** under GraphQL exhaustion. Should fail loud (scorer), not open (hook).
- **#312** — commit messages auto-close too, and are unguarded. **`mask_code` must NOT be reused there**:
  backticks are inert markdown in a PR body, literal characters in a commit message.
- **#313** — `review_load.py` crashes in the framework's own repo (`.claude/` has no `lib/`/`hooks/`) while its
  comment claims it works in both trees. `/wave-end` resolves the broken copy first. The **Wave 22 review-load
  figure cannot have come from a clean run of it.**

Next-wave stub: **#315** (theme TBD — owner sets it). `global_wave_seq` still 23; the id is reserved via
`wave_24_meta_issue`, not a counter bump.

## Hard-won operational facts (cost real time this session)

- **`gh` caches HTTP responses in `/tmp/gh-cli-cache`, NOT `~/.cache/gh`.** `gh pr merge` sends
  `X-Gh-Cache-Ttl: 24h0m0s`, so a GraphQL **rate-limit error caches as a 200 and replays for 24 hours**.
  Symptom: `gh pr merge` reports "rate limit already exceeded" with a frozen `X-Ratelimit-Reset` and an
  identical `X-Github-Request-Id` on every attempt, while plain `gh api graphql` reads show thousands
  remaining. Fix: `find /tmp/gh-cli-cache -type f ! -name 'run-log-*.zip' -delete`. Cost ~80 minutes.
- **Never pipe `gh pr merge` (or any command whose exit code matters) through `sed`/`grep`/`tail` under
  `set -e`** — the pipeline's status comes from the filter, which always succeeds. This reported **4 merges
  that never happened**. Verify against the API: `gh api repos/OWNER/REPO/pulls/N --jq .merged`.
  `warn_pipe_mask_rc.py` exists for this and did **not** fire (retro follow-up).
- **`jq '.blockers // "none"'`** on `pr_review_state.py` output prints a confident `"none"` — the real key is
  **`unresolved_must_fix`**. Nearly filed a bug against a working merge gate.
- The merge gate matches only `gh\s+pr\s+(ready|merge)`. `gh api graphql` mutations, REST `PUT .../merge`, and
  local pushes **all bypass it**. Never route around a rate limit that way — it is a `gate_bypasses` signal.

## Suggested next step

Ask the owner for the Wave 24 theme on **#315**. The obvious spine is **#314 + #308 + #310** ("the scorer
must not lie" — reconcile the negative sets, add the structural guard, fix the stale charter claim), with
#311/#312/#313 as small file-disjoint companions. Trust scoring stays parked until #314 lands.

Nothing is released. `main` = `cdbc009`.
