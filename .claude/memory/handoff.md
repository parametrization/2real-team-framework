<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-10T00:29:34Z (Phase 7 Wave 2 / global wave 23 — ROLLED UP TO MAIN, NO RELEASE CUT)

## Pickup (next concrete step)

**Ask the owner for the Wave 24 theme on #315.** Nothing else is in flight: `main` is clean at
`0099a60`, zero open PRs, no release tagged. The recommended spine is **#314 + #308 + #310**
("the scorer must not lie" — reconcile the negative sets, fix the stale charter claim, add the
structural guard), with #311/#312/#313 as small file-disjoint companions.

**Do NOT tag or publish a release without explicit owner go-ahead.** The owner approved the Wave 23
rollup and deliberately stopped before tag/PyPI/npm. Latest release remains `v0.12.0` (Wave 22).

**Do NOT start Wave 24 without explicit owner approval** (wave kickoff is a gate).

## Decisions made this session

- **Roll up Wave 23 to `main`, cut no release.** Owner chose "Roll up and merge to main now" over the
  release path. Honored: PR #316, merge `cdbc009`, 12/12 CI green, post-flight probe confirmed feature
  code (not a state.json-only rollup).
- **Park ALL Wave 23 trust deltas, citing #314.** Owner's call. Matrix held at Paloma 5, Tariq 5,
  Nia 3, Ibrahim 3. Mechanical output recorded in `trust_matrix.md` as *evidence*, not applied.
  Precedent for parking: W15, W20. This is the **second consecutive wave** Ibrahim's positives were
  gated away (W22 needed an owner override).
- **#308 scoped into Wave 24** as a story, rather than fixed opportunistically this wave.
- **Wave 23 theme was "Scoring and Process/record debt"** → shipped as "The record must not lie".

## Open threads / blockers

### 🚨 #314 — the scorer contradicts itself. Blocks all trust scoring.

`composite()` (the reserved-5 ranking key, **nested inside `apply_distribution_discipline`** in
`framework/assets/lib/trust_signals.py`) subtracts `must_fix_received`, `ci_red_merges`,
`review_false_positives` — but **NOT `missed_catches`**. `score_delta()` charges −1 per missed catch.

Reproduced live on Wave 23 data:

```
engineer   old  delta  new   composite   negatives
Ibrahim     3    -2     1      7 ←TOP    missed_catches=2
Nia         3    -1     2      6         recv=1, rework=1, missed=1
Paloma      5     0     5→4    6         recv=1, rework=1
Tariq       5     0     5→4    6         recv=1, rework=1
```

Ibrahim holds the **highest composite AND the worst delta** at once; because reserved-5 requires
`composite == top`, his 7 caps **Paloma and Tariq 5 → 4 for a third engineer's number**.

Root cause: `verified_reviews=2` and `missed_catches=2` come from **the same two reviews** — his clean,
`Verified:`-bearing verdicts on #307 and #309, each past a defect his co-reviewer caught.
`_has_verified_checks` validates that a receipt is *detailed*, not that the review *worked*. Composite
pays `+2×2` for the ritual; delta charges `−1×2` for the outcome.

`distribution_health([4,4,2,1])` → `degenerate=False`. No retirement triggers fired.

### Housekeeping

- **#297 (Wave 23 meta-issue) is still OPEN.** The four story issues closed from commit trailers as
  designed; the meta was never closed. Close it during Wave 24 kickoff, or confirm the convention is to
  leave meta-issues open until the phase ends.
- **9 agent worktrees remain registered** after `git worktree prune` (they're resumable, left intact).

### Rest of the Wave 23 sweep — every one "a component asserting something it never verified"

- **#308** — charter claims the merge gate doesn't author-exclude. False since #293/#294. **Owner scoped into W24.**
- **#310** — no structural guard forces a new negative `Signals` field into `_NEGATIVE_SIGNAL_FIELDS`.
- **#311** — `trust_signals extract` returns `{}` at **exit 0** under GraphQL exhaustion. Should fail loud (scorer), not open (hook).
- **#312** — commit messages auto-close too, and are unguarded. **`mask_code` must NOT be reused there**:
  backticks are inert markdown in a PR body, literal characters in a plain-text commit message.
- **#313** — `review_load.py` crashes in the framework's own repo (`.claude/` has no `lib/`/`hooks/`) while
  its comment claims it works in both trees. `/wave-end` resolves the broken copy first. The **Wave 22
  review-load figure cannot have come from a clean run of it.**
- **#302** — policy: grade `has_negative()` suppression (hard gate vs soft offset). Orthogonal to #314.

## What landed (4 stories, all 2/2 gate-approved, file-disjoint)

| PR | Issue | Author | Rounds | What |
|---|---|---|---|---|
| #306 | #296 | Paloma | 1 CR | `_NEGATIVE_SIGNAL_FIELDS` single source of truth; `_VACUOUS_BODY_RE` rejects `"Name: None"`/`-`/`n/a`/blank |
| #307 | #300 | Nia | 2 CR | `/wave-end` derives counters from `trust_signals extract`; 3 read-trust defenses (REST rate-limit preflight, `PR_LIST_RC=$?`, cross-check) |
| #305 | #301 | Ibrahim | clean | reserved-5 pluralized to "top relative performer(s)"; ties intended, documented |
| #309 | #304 | Tariq | 1 CR | `validate_pr_body.py` PreToolUse hook — blocks closing keywords in PR bodies |

Every story contained the defect it was written to eliminate. All four issues **closed from commit
trailers**, each attributed to its own author's commit — verified `#296 ← 6bd8c7a` (Paloma), *not*
Tariq's hook commit. That attribution *was* the point of #304.

Counters `4 PRs / 3 CR cycles / 25% concentration`; review load even (2 verdicts, 2 PRs each);
**zero counter drift — first since W12**, because `/wave-end` derived them with the code #307 shipped
that same wave.

## Hard-won operational facts (cost real time this session)

- **`gh` caches HTTP responses in `/tmp/gh-cli-cache`, NOT `~/.cache/gh`.** `gh pr merge` sends
  `X-Gh-Cache-Ttl: 24h0m0s`, and GraphQL returns rate-limit errors as **HTTP 200** — so the error caches
  and replays for 24 hours. Symptom: frozen `X-Ratelimit-Reset` and an **identical `X-Github-Request-Id`**
  on every attempt, while plain `gh api graphql` reads show thousands remaining. The cache key is the
  request **body**. Fix: `find /tmp/gh-cli-cache -type f ! -name 'run-log-*.zip' -delete`. Cost ~80 min.
- **Never pipe a command whose exit code matters through `sed`/`grep`/`tail` under `set -e`** — the
  pipeline's status comes from the filter, which always succeeds. This **reported 4 merges that never
  happened**. Verify against the API: `gh api repos/OWNER/REPO/pulls/N --jq .merged`.
  `warn_pipe_mask_rc.py` exists for exactly this and did **not** fire (retro follow-up).
- **`jq '.blockers // "none"'`** on `pr_review_state.py` output prints a confident `"none"` for a key that
  doesn't exist — the real key is **`unresolved_must_fix`**. Nearly filed a bug against a working merge gate.
- **`jq '.conclusion // .status'` then `select(.s==null)`** never matches — `//` already substituted the
  null. This produced a false-green CI poll. Use `select(.conclusion != null and .conclusion != "")`.
- The merge gate matches only `gh\s+pr\s+(ready|merge)`. `gh api graphql` mutations, REST `PUT .../merge`,
  and local pushes **all bypass it**. Never route around a rate limit that way — it is a `gate_bypasses` signal.
- `composite()` is **nested inside** `apply_distribution_discipline` — `trust_signals.composite` raises
  `AttributeError`. Read the source, don't import it.
- f-strings with escaped quotes inside `python3 -c` heredocs → `SyntaxError`. Write to a temp `.py` instead.

## Mechanical state

- Branch: `main` (clean) @ `0099a60`
- Open PRs: **(none)**
- Open issues: #315 (W24 stub, theme TBD), #314, #313, #312, #311, #310, #308, #302, #298, **#297 (W23 meta — still open)**, #295, #110, #102
- Lifecycle: `wave_23_active=false`, `wave_23_completed_at=2026-07-09T23:25:30Z`,
  counters `pr_count=4 / cr_cycles=3 / concentration=25`, `merge_model=wave-branch`.
  `wave_24_meta_issue="#315"` reserved; `global_wave_seq` still **23** (reservation, not a counter bump).
- Releases: latest `v0.12.0` (`deployments-phase7-wave-1`). **Nothing released for Wave 23.**
- Worktrees: 9 registered after prune.
