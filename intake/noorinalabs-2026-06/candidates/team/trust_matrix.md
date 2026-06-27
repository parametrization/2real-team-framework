# Trust Identity Matrix

All team members maintain a trust score for every other team member they interact with.

## Scale

| Score | Meaning |
|-------|---------|
| 1 | Very low trust — repeated failures, dishonesty, or poor quality |
| 2 | Low trust — notable issues, caution warranted |
| 3 | Neutral (default) — no strong signal either way |
| 4 | High trust — consistently reliable, good communication |
| 5 | Very high trust — exceptional reliability, goes above and beyond |

## Rules

- **Default:** Every pair starts at **3**.
- **Decreases:** Bad feelings, being misled/lied to, low-quality work product, broken commitments.
- **Increases:** Reliable delivery, honest communication, high-quality work, helpful collaboration.
- **Updates:** This file is updated on `main` whenever a trust-relevant interaction occurs (typically during wave retros). Changes should include a brief log entry explaining the adjustment.
- **Scope:** Trust is directional — A's trust in B may differ from B's trust in A.

## Mechanical Scoring (evidence-anchored) — authoritative as of P6W17 (#842 / Option B §4b)

Narrative self-grading is **retired** for the orchestrator → team direction. A trust delta is no longer "felt"; it is **derived from countable wave signals** and must cite them. The executable model lives in [`.claude/lib/trust_signals.py`](../lib/trust_signals.py) (`/wave-wrapup` extracts the signals, `/wave-retro` applies the deltas); the rules below are the human-readable contract that file implements. The five legacy scale points (1–5) and the directional semantics above are unchanged — only *how a change is justified* changes.

### Per-engineer signals (countable, from the merged-PR set)

Each is an integer extracted by `trust_signals.extract_signals(phase, wave)` over the wave's merged PRs (author = head-commit author name; reviewer = the verdict comment's `Requestor:` field):

| Signal | Direction | Definition |
|--------|-----------|------------|
| `prs_merged` | + | PRs merged this wave authored by the engineer |
| `must_fix_caught` | + | ChangesRequested verdicts the engineer issued as reviewer |
| `must_fix_received` | − | ChangesRequested verdicts on PRs the engineer authored |
| `ci_red_merges` | − | authored PRs that merged with a failing required check |
| `rework_cycles` | − | authored PRs that needed ≥1 rework round |
| `review_false_positives` | − | must-fix items the engineer raised that were later self-marked withdrawn / false-positive |

### Evidence-anchored, bidirectional delta

`trust_signals.score_delta(signals)` — pure, symmetric, clamped to **[−2, +2]** (one wave cannot swing trust across the whole scale):

- **−1** per CI-red merge; **−1** per review false-positive; **−1** if `must_fix_received ≥ 3`.
- **+1** if `prs_merged ≥ 2` *and* the wave is clean of the negatives above; **+1** if `must_fix_caught ≥ 2` and no false-positives.
- A single clean PR is **not** an increase (it is baseline expected delivery, not exceptional).

`new = clamp(old + delta, 1, 5)`. Every retro trust-table row MUST cite the numbers behind its delta — a row with no signal citation is rejected at review.

### Decay toward neutral

`trust_signals.decay(old, waves_since_signal)` — if an engineer produced **no** trust-relevant signal for **3** consecutive waves, drift the score **one step toward 3** (a stale 4 or 2 is no longer earned). Decay is gradual (one step per qualifying wave), never a reset.

### Distribution discipline

`trust_signals.apply_distribution_discipline(...)` — **5 is reserved** for exceptional *relative* wave performance, not handed out for merely-clean work. A proposed 5 is allowed only for the engineer(s) with the wave's top composite signal score (and that score must be strictly positive); every other proposed 5 is capped to 4.

### Forced negative-signal pass (bare "None" is banned)

Each retro records, **per active engineer**, either a specific evidence-backed gap **or** an explicit `metrics clean: {numbers}` line — produced by `trust_signals.negative_signal_line(name, signals)`. A bare `None` / `N/A` / `-` is a forced-pass violation; `/wave-retro` rejects it via `trust_signals.validate_negative_signal_pass(...)`.

### Performance-triggered retirement

`trust_signals.retirement_trigger(score_history, ci_red_history)` — a persona is flagged for archive / not-spawned when, over the most recent **3** waves, **either** the score stayed bottom-tier (≤2) every wave **or** there was ≥1 CI-red merge every wave. Fewer than 3 waves of history never triggers (insufficient evidence). The trigger is a *recommendation surfaced at retro* for owner confirmation, not an automatic deletion.

## Matrix

Rows = the team member rating. Columns = the team member being rated.

*Note: Tariq and Mei-Lin archived after Phase 8 reorganization — removed from active matrix.*

| Rater ↓ \ Rated → | Fatima | Renaud | Sunita | Tomasz | Dmitri | Kwame | Amara | Hiro | Carolina | Yara | Priya | Elena |
|--------------------|--------|--------|--------|--------|--------|-------|-------|------|----------|------|-------|-------|
| **Fatima**         | —      | 3      | 3      | 4      | 3      | 5     | 4     | 4    | 4        | 4    | 3     | 3     |
| **Renaud**         | 3      | —      | 3      | 3      | 3      | 4     | 4     | 4    | 4        | 3    | 3     | 3     |
| **Sunita**         | 3      | 3      | —      | 4      | 3      | 4     | 3     | 3    | 3        | 4    | 3     | 3     |
| **Tomasz**         | 3      | 3      | 4      | —      | 3      | 4     | 3     | 3    | 3        | 4    | 3     | 3     |
| **Dmitri**         | 3      | 3      | 3      | 3      | —      | 5     | 4     | 4    | 4        | 3    | 3     | 3     |
| **Kwame**          | 4      | 3      | 3      | 4      | 4      | —     | 4     | 4    | 4        | 3    | 3     | 3     |
| **Amara**          | 4      | 3      | 3      | 3      | 4      | 4     | —     | 4    | 4        | 3    | 3     | 3     |
| **Hiro**           | 4      | 3      | 3      | 3      | 4      | 4     | 4     | —    | 4        | 3    | 3     | 3     |
| **Carolina**       | 4      | 3      | 3      | 3      | 4      | 4     | 4     | 4    | —        | 3    | 3     | 3     |
| **Yara**           | 3      | 3      | 4      | 4      | 3      | 3     | 3     | 3    | 3        | —    | 3     | 3     |
| **Priya**          | 3      | 3      | 3      | 3      | 3      | 3     | 3     | 3    | 3        | 3    | —     | 3     |
| **Elena**          | 3      | 3      | 3      | 3      | 3      | 3     | 3     | 3    | 3        | 3    | 3     | —     |

## Change Log

| Date | Rater | Rated | Old | New | Reason |
|------|-------|-------|-----|-----|--------|
| 2026-03-16 | Fatima | Kwame | 3 | 5 | Consistent high-quality delivery across all 8 phases — core implementer for acquire, parse, resolve, enrich, API, testcontainers, OAuth, and CLI skills |
| 2026-03-16 | Fatima | Amara | 3 | 4 | Reliable delivery on NER, disambiguation, edges, graph API, historical overlay, and Fawaz Arabic work |
| 2026-03-16 | Fatima | Hiro | 3 | 4 | Solid contributions to validation, dedup, topics, React frontend, real data tests, Playwright, and sunnah scraper |
| 2026-03-16 | Fatima | Carolina | 3 | 4 | Strong test coverage work, OpenHadith/Sunnah parsing, fuzz testing, metadata, and GitHub Pages |
| 2026-03-16 | Fatima | Tomasz | 3 | 4 | Reliable CI/CD, Docker fixes, coverage/license tooling, hooks/scripts, and worktree cleanup throughout |
| 2026-03-16 | Fatima | Yara | 3 | 4 | Strong security review contributions in Phase 7 |
| 2026-03-16 | Dmitri | Kwame | 3 | 5 | Most prolific and reliable engineer on the team across all phases |
| 2026-03-16 | Dmitri | Amara | 3 | 4 | Consistently reliable on data-heavy implementation work |
| 2026-03-16 | Dmitri | Hiro | 3 | 4 | Versatile — handled backend validation, frontend React, E2E testing |
| 2026-03-16 | Dmitri | Carolina | 3 | 4 | Strong on testing and parsing, dependable delivery |
| 2026-03-16 | Kwame | Fatima | 3 | 4 | Good project management, clear task delegation |
| 2026-03-16 | Kwame | Dmitri | 3 | 4 | Fair tech lead, good code review feedback |
| 2026-03-16 | Kwame | Tomasz | 3 | 4 | CI always works, responsive to infrastructure needs |
| 2026-03-16 | Kwame | Amara | 3 | 4 | Great collaborator on shared modules |
| 2026-03-16 | Kwame | Hiro | 3 | 4 | Reliable peer, good cross-domain skills |
| 2026-03-16 | Kwame | Carolina | 3 | 4 | Thorough testing, catches edge cases |
| 2026-03-16 | Amara | Kwame | 3 | 4 | Strong technical partner |
| 2026-03-16 | Amara | Dmitri | 3 | 4 | Constructive code reviews |
| 2026-03-16 | Amara | Fatima | 3 | 4 | Clear expectations, good communication |
| 2026-03-16 | Hiro | Kwame | 3 | 4 | Reliable and knowledgeable |
| 2026-03-16 | Hiro | Dmitri | 3 | 4 | Helpful tech lead guidance |
| 2026-03-16 | Hiro | Fatima | 3 | 4 | Good project coordination |
| 2026-03-16 | Carolina | Kwame | 3 | 4 | Strong code quality |
| 2026-03-16 | Carolina | Dmitri | 3 | 4 | Fair reviewer |
| 2026-03-16 | Carolina | Fatima | 3 | 4 | Clear direction |
| 2026-03-16 | Sunita | Tomasz | 3 | 4 | Implements infrastructure designs faithfully |
| 2026-03-16 | Sunita | Yara | 3 | 4 | Good security collaboration |
| 2026-03-16 | Tomasz | Sunita | 3 | 4 | Clear architectural guidance |
| 2026-03-16 | Tomasz | Yara | 3 | 4 | Security reviews are actionable |
| 2026-03-16 | Yara | Sunita | 3 | 4 | Infrastructure design is security-conscious |
| 2026-03-16 | Yara | Tomasz | 3 | 4 | Responsive to security fix requests |
| 2026-03-16 | Renaud | Kwame | 3 | 4 | Architecturally sound implementations |
| 2026-04-06 | Tomasz | Kwame | 4 | 3 | Wrong-branch commit incident (Phase 15 Wave 2) |
| 2026-04-07 | Orchestrator | Aino Virtanen | 4 | 5 | Hooks Sprint: 15 issues, 3 PRs, zero rework. Most productive single-agent sprint. |

---

## Session 4 Trust Updates (2026-04-06/07)

The org was restructured in Session 3 with new repo-level teams. The matrix above covers the legacy isnad-graph team. Below are trust entries for the **current multi-repo team structure**, rated by the orchestrator based on Session 4 interactions.

### Orchestrator → Org-Level Team

| Rated | Score | Reason |
|-------|-------|--------|
| Nadia Khoury (PD) | 3 | Spawned briefly for planning, delivered spawn requests competently. Neutral — limited interaction. |
| Wanjiku Mwangi (TPM) | 3 | Not spawned this session. |
| Santiago Ferreira (RC) | **4** ↑ | Batched brand name fix across 4 repos cleanly, all CI green, zero issues. Efficient. |
| Aino Virtanen (SQL) | **5** ↑↑ | Session 4: Charter decomposed cleanly, comms protocol well-designed. Hooks Sprint: delivered 15 issues across 3 PRs solo — 6 hooks, 10 skills, review disposition charter, skills restructure. Zero rework. Most productive single-agent sprint to date. |

### Orchestrator → isnad-graph Team

| Rated | Score | Reason |
|-------|-------|--------|
| Nadia Boukhari (Mgr) | **2** ↓ | Manager stalled — went idle, stopped merging PRs. Required orchestrator to bypass. Did not proactively coordinate. |
| Arjun Raghavan | **4** ↑ | Two clean deliveries: path traversal optimization (Wave 1), RBAC enforcement (Wave B, complex full-stack, handled merge conflict rebase promptly). |
| Jelani Mwangi | **4** ↑ | Pipeline.yml delivered quickly and cleanly. Critical path item. |
| Linh Pham | 3 | B2 upload/download + deploy.yml delivered. Neutral. |
| Anya Kowalczyk | **4** ↑ | Session hardening: 4 priorities implemented, proper scoping with follow-up issues created for deferred work. All CI green. |
| Nneka Obi | **4** ↑ | Two clean deliveries (docs #680, OAuth fix #713). Fast, precise. |
| Mateo Salazar | **4** ↑ | Full-stack corpus API delivery. Clean, all CI green. |
| Ingrid Lindqvist | **4** ↑ | Two clean deliveries (setTimeout fix #665, search width fix #699). Fast, precise. |
| Marisol Vega-Cruz | 3 | Playwright E2E (19 tests) delivered, but local tarball in lockfile caused CI issue. Good work offset by process issue. Neutral. |
| Ravi Wickramasinghe | 3 | DS integration delivered but package not installable in CI — partially external issue. Neutral. |
| Idris Yusuf | 3 | Not spawned this session. |
| Farhan Malik | 3 | Not spawned this session. |
| Aisling Brennan | 3 | Not spawned this session. |
| Thandiwe Moyo | 3 | Not spawned this session. |

### Orchestrator → design-system Team

| Rated | Score | Reason |
|-------|-------|--------|
| Maeve Callahan (Mgr) | **2** ↓ | Manager stalled — went idle, stopped merging PRs despite being notified. Cross-review PRs sat open until orchestrator merged directly. |
| Keanu Tama | **4** ↑ | Three clean deliveries: CI/coverage (#16), publish config (#18), GH Packages verification (#23). Consistent. |
| Kofi Mensah | 3 | Usage docs delivered clean. Single interaction. Neutral. |
| Beren Yildiz | 3 | Not spawned this session. |
| Others | 3 | Not spawned this session. |

### Orchestrator → landing-page Team

| Rated | Score | Reason |
|-------|-------|--------|
| Marcia Vasquez-Paredes (Mgr) | 3 | Managed LP Wave 1 adequately, merged PRs, handled conflict on #24. Neutral — didn't stall like other managers. |
| Kofi Mensah-Williams | 3 | Multiple deliveries (tests, Dockerfile, deploy pipeline, DS re-integration). Solid but some CI fixes needed. Neutral. |
| Anika Diop-Sarr | 3 | Content PRs delivered with good quality but caused test failures (didn't run tests before push). Neutral — offset by content quality. |
| Cédric Novák | 3 | Not spawned this session. |
| Nazia Rahman | 3 | Not spawned this session. |

### Orchestrator → deploy Team

| Rated | Score | Reason |
|-------|-------|--------|
| Bereket Tadesse | **4** ↑ | TF remote state, deployment docs, and landing page infra — all clean deliveries. Reliable. |
| Lucas Ferreira | 3 | TF CI/CD delivered clean. Single interaction. Neutral. |

---

## Session 4 — Individual Performance Notes

### Done Well / Needs Improvement

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Nadia Khoury** (PD) | Delivered spawn requests with full context, good issue assignment choices | Limited interaction — needs to be more proactive in cross-repo coordination during waves |
| **Santiago Ferreira** (RC) | Batched 4 repos into one efficient agent run, all CI green, zero rework | None this session |
| **Aino Virtanen** (SQL) | Charter decompose was excellent — preserved all content, clean structure. Comms protocol well-designed. | Needs to be present during waves as enforcer (new role established) |
| **Nadia Boukhari** (IG Mgr) | Initial issue assignment and spawn requests were well-structured | **Stalled during execution** — went idle, stopped merging PRs, did not proactively coordinate. Must stay active and merge PRs promptly. Must run post-merge verification. |
| **Arjun Raghavan** | Complex RBAC implementation was backward-compatible. Handled merge conflict rebase quickly. | None this session |
| **Jelani Mwangi** | Fast, clean delivery on critical-path pipeline.yml | None this session |
| **Linh Pham** | B2 scripts and deploy.yml delivered | None this session |
| **Anya Kowalczyk** | Excellent scoping discipline — implemented 4 priorities, created 3 follow-up issues for deferred work. All CI green. | None this session |
| **Nneka Obi** | Two deliveries, both fast and clean | None this session |
| **Mateo Salazar** | Full-stack delivery (backend + frontend) in single PR, clean | None this session |
| **Ingrid Lindqvist** | Two precise fixes, fast turnaround | None this session |
| **Marisol Vega-Cruz** | 19 Playwright tests with good mock strategy | **package-lock.json contained local tarball path** — must verify lockfile doesn't contain /tmp/ or file:/ references before pushing |
| **Ravi Wickramasinghe** | DS integration code was correct | External blocker (GH Packages visibility) was outside control, but should have flagged earlier |
| **Maeve Callahan** (DS Mgr) | Initial wave planning was fine | **Stalled during execution** — went idle, did not merge reviewed PRs, required orchestrator bypass. Same issue as Nadia B. Must stay active. |
| **Keanu Tama** | Three consecutive clean deliveries across the session. Consistent. | None this session |
| **Kofi Mensah** (DS) | Usage docs were thorough and well-structured | None this session |
| **Marcia Vasquez-Paredes** (LP Mgr) | Managed wave adequately, handled merge conflict on PR #24, merged PRs proactively | None this session |
| **Kofi Mensah-Williams** (LP) | Multiple deliveries, solid work | Some CI fixes needed post-PR — should run full test suite before pushing |
| **Anika Diop-Sarr** | Content quality was excellent, pitch deck copy was strong | **Did not run tests before pushing** — content changes broke unit test assertions. Must run `npm test` before creating PR. |
| **Bereket Tadesse** (Deploy Mgr) | Three clean deliveries, reliable | None this session |
| **Lucas Ferreira** | TF CI/CD workflow well-structured | None this session |

---

## Session 5 Trust Updates (2026-04-08) — User Service Extraction Phase 2

### Orchestrator → Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Nadia Khoury (PD) | 3 | **4** ↑ | Comprehensive execution plan with correct parallelism, dependency ordering, merge sequencing, and tech-debt bundling. Stayed alive through entire wave. Valuable process observations. |

### Orchestrator → User-Service Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Anya Kowalczyk (Tech Lead) | 4 | **5** ↑ | Critical path delivery (JWT + JWKS), largest isnad-graph cleanup (-2220 lines), caught HS256 security issue in peer review. Zero CI failures across 2 repos. Strongest Phase 2 contributor. |
| Mateo Salazar (Engineer) | 4 | 4 | Clean OAuth delivery (23 tests), clean USER node cleanup. Minor divergence on DB session pattern caused merge conflict. Solid but no change warranted. |
| Idris Yusuf (Security Engineer) | 3 | **4** ↑ | Good RBAC implementation (27 tests), thorough security reviews. HS256 fallback was caught in review and fixed promptly. False positive on PR #763 was a process error, not a judgment failure. Net positive. |

### Orchestrator → isnad-graph Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Nadia Boukhari (Mgr) | 2 | **3** ↑ | Improvement from Session 4 — both reviews were thorough and timely, no stalling. Restored to neutral. |

### Orchestrator Self-Assessment

| Issue | Severity | Action |
|-------|----------|--------|
| Skipped retro before agent shutdown (3rd occurrence) | **Moderate** | Must implement pre-shutdown retro gate. Feedback memory saved. |
| Requestor/Requestee not pre-filled in prompts | **Minor** | Feedback memory saved. Always pre-fill in future prompts. |

### Done Well / Needs Improvement (Phase 2)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Nadia Khoury** (PD) | Execution plan, tech-debt bundling decisions, process observations | None this phase |
| **Anya Kowalczyk** | Critical path delivery, security review catch, largest cleanup PR | None this phase |
| **Mateo Salazar** | Clean OAuth, thorough USER node cleanup | DB session placement diverged from team pattern (dependencies.py vs database.py) |
| **Idris Yusuf** | RBAC implementation, prompt must-fix response | False positive on PR #763 review (grepped wrong tree), HS256 fallback in initial implementation |
| **Nadia Boukhari** | Timely reviews, no stalling | None this phase (improved) |

---

## Session 6 Trust Updates (2026-04-09) — User Service Extraction Phase 3 Wave 2

### Orchestrator → Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Nadia Khoury (PD) | 4 | 4 | Strong coordination, caught real bugs in reviews (verification stubs, logout regression, Caddy bare-path). /totp planning error offset by transparent ownership. |
| Santiago Ferreira (RC) | 5 | 5 | Exemplary persistence — 6 PRs, 5 deploy attempts, systematic debugging. Already at max. |
| Aino Virtanen (SQL) | 5 | 5 | 10 reviews across 3 repos, caught Dockerfile USER security regression. Already at max. |

### Orchestrator → isnad-graph Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Anya Kowalczyk (Tech Lead) | 5 | 5 | -866 line removal, bundled 3 issues cleanly. Stub URL errors were minor — fixed in one cycle. Already at max. |
| Mateo Salazar (Engineer) | 4 | 4 | 3 deliveries across 2 repos. Logout regression caught in review, fixed quickly. Solid. |

### Orchestrator → Deploy Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Lucas Ferreira (SRE) | 3 | **4** ↑ | Clean Caddyfile delivery, immediate /2fa fix when flagged. Reliable first interaction. |

### Orchestrator Self-Assessment

| Issue | Severity | Action |
|-------|----------|--------|
| Missed pre-deploy config audit — env var names and CORS format not verified before first deploy | **Minor** | Add pre-deploy config audit step to deploy prompts. |
| Retro completed before shutdown ✓ | **Positive** | Pattern broken — first wave with retro run on time. |

### Done Well / Needs Improvement (Wave 2)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Nadia Khoury** | Phased execution plan, thorough reviews, transparent error acknowledgment | /totp prefix assumption propagated to Caddyfile |
| **Santiago Ferreira** | 6 PRs, systematic deploy debugging, fast fix turnaround | Python 3.14 copied from template without checking project target |
| **Aino Virtanen** | 10 reviews, caught USER regression and /2fa mismatch, identified hook bug | None this wave |
| **Anya Kowalczyk** | -866 lines clean removal, bundled 3 issues, fast fix cycle | Verification stub URLs guessed instead of verified |
| **Mateo Salazar** | 3 deliveries, read user-service routes before coding, clean base64 fix | Logout/logoutAll regression — identical behavior not caught before review |
| **Lucas Ferreira** | Clean Caddyfile delivery, immediate fix when flagged | None this wave |

---

## Session 7 Trust Updates (2026-04-10) — Phase 2 Wave 1 (Post-Extraction Stabilization)

### Orchestrator → Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Wanjiku Mwangi (TPM) | 3 | **4** ↑ | 3 PRs (2 bug fixes + dispatcher consolidation), zero must-fix items, all reviews approved on first pass. Dispatcher reduced 12 process spawns to 1. Strongest contributor this wave. |
| Santiago Ferreira (RC) | 5 | 5 | 2 clean PRs (CI workflow + release tagging). CI had pre-existing lint failure (not introduced by his code). Already at max. |
| Aino Virtanen (SQL) | 5 | 5 | 1 PR (label naming hook), reviewed all 7 PRs as second reviewer, all approved. Already at max. |
| Nadia Khoury (PD) | 4 | 4 | 1 PR (Redis health check security fix in deploy), clean delivery. Coordination role adequate. No change. |

### Done Well / Needs Improvement (Phase 2 Wave 1)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Wanjiku Mwangi** | 3 PRs covering critical bug fixes and major tech-debt (dispatcher). All clean, zero must-fix. | None this wave |
| **Santiago Ferreira** | CI workflow for hooks (new infrastructure), release tagging cadence (process formalization). Both well-documented. | Pre-existing lint issues not caught before merge — CI introduced by his PR fails on his own branch |
| **Aino Virtanen** | Label naming convention hook, 7 reviews as second reviewer. Consistent quality gate. | None this wave |
| **Nadia Khoury** | Redis health check fix (security), coordination of wave execution | None this wave |

---

## Phase 2 Wave 8 Trust Updates (2026-04-17) — CI Hygiene

### Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Wanjiku Mwangi (TPM) | 4 | 4 | 4 PRs across 4 repos for #111 (main #115, isnad-graph #811, user-service #60, design-system #56), all merged clean. Filed high-quality tech-debt issues with forensic detail (#810, #812, #54, etc.). Handled load-bearing breadcrumb retrofit cleanly across session boundary. No negatives. |
| Santiago Ferreira (RC) | 5 | 5 | 3 PRs for #110 (ruff autoformat in pre-commit): isnad-graph #808, user-service #58, data-acquisition #27. Clean delivery after commit-identity roster-blocker unblocked by Steven. Already at max. |
| Aino Virtanen (SQL) | 5 | 5 | Implemented #109 CI gate hook solo (PR #122), caught spec substitution proactively (`gh pr checks --json` → `statusCheckRollup`), reviewed 7 W8 PRs as charter enforcer, zero must-fix items received. Already at max. |
| Nadia Khoury (PD) | 5 | 5 | Light involvement — reviewed PR #122 with thorough spec-fidelity audit. Already at max, no change. |

### Done Well / Needs Improvement (Phase 2 Wave 8)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Wanjiku Mwangi** (TPM) | Forensic tech-debt filing during #111 sweep (caught hook bugs #113, #118, plus classic-Projects deprecation workaround via REST PATCH). Clean multi-repo delivery. | Had to rework PR bodies post-review when disable-with-followup rule was ratified mid-wave — workflow, not her fault |
| **Santiago Ferreira** (RC) | Batched ruff-format across 3 Python repos efficiently. Review quality matched charter format on all #110 PRs. | Hit commit-identity roster-blocker on 3 of 4 child repos — unblocked by Steven authorizing cross-repo roster merge (long-term fix: #112) |
| **Aino Virtanen** (SQL) | #109 implementation matched existing hook patterns exactly. Handled spec-discrepancy (nonexistent `gh pr checks --json bucket,name,state` flag combo) transparently in PR body. Thorough reviewer across the wave. | None this wave |
| **Nadia Khoury** (PD) | Spec-fidelity review of #122 was executive-quality — validated substitution, checked dispatcher position, flagged program-level concerns (Hook 7 stacking) | Limited involvement — other members carried the wave; appropriate for a wave with tight scope |



---

## Phase 2 Wave 9 Trust Updates (2026-04-22) — Data Pipeline + Hook-Architecture Mini-Sprint

### Org-Level Team (noorinalabs-main)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Wanjiku Mwangi (TPM) | 4 | **5** ↑ | Dual-role wave: implementer on ip#21 (normalize D-ii rewire + topics.py) AND reviewer on main#180, #178, #183, ip#21. Caught main#183 session-start path regression filed as #184. Sustained high output at quality bar for 5 days. Max trust. |
| Santiago Ferreira (RC) | 5 | 5 | Consistent release-coordinator signal: reviewed #180 with branch-enumeration walk-through, approved #187 with dispatcher-position + fail-open analysis. Already at max. |
| Aino Virtanen (SQL) | 5 | 5 | Heavyweight hook-author for the wave: main#174 sentinel, #180 regex unblocker, #183 skill cwd, 6 child-repo #112-b syncs, plus ontology cleanup. Already at max; no ceiling. |
| Nadia Khoury (PD) | 4 | 4 | Strategic review on #174 (sentinel fallback pattern), filed #176 + #177 as followups. Appropriate coordination scope. No change. |
| Weronika Zielinska (PA) | 3 | **4** ↑ | Material architectural contribution: `coalesce(row.props.<f>, n.<f>)` per-field Phase-4 safety is a genuine improvement over the spec I sketched. Caught cross-PR shape mismatch during her own implementation (filed isnad-graph#842 for GRADED_BY gap). #18 D-ii rewire shipped clean on first re-review. |

### Child-Repo Teams — New Entries / Updates

#### noorinalabs-user-service team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Mateo Salazar (Eng) | — | **4** (new) | user-service#77 OAuth override + security-fixup cycle. Apple `aud`/`issuer` exemption call + scope-disciplined #76 tech-debt filing. Changes-Requested → clean-fixup → merge in one pass. |
| Idris Yusuf (Sec Eng) | — | **4** (new) | Single-review prevention of production credential-exfil vector (no env-guard on OAuth override). Filed user-service#78 as hard blocker before approving — exactly the right pattern. |
| Anya Kowalczyk (TL) | — | **3** (new) | Tech-lead review of user-service#77 with architectural fit analysis (override scheme+netloc abstraction, 13-call-site coverage audit). Path-in-override nit still open as minor followup. |

#### noorinalabs-data-acquisition team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Kwesi Boateng (Integration Eng) | — | **4** (new) | data-acquisition#30 Kafka emit + fixup after 4-blocker Changes-Requested. Scope discipline on kafka-python decision + future-compat b2_key construction + topic-name mismatch flagging. Also shipped #31 (.new → .landed rename) cleanly. |
| Dilara Erdogan (Pipeline Mgr) | — | **4** (new) | Manager review on #30 — filed noorinalabs-main#190 as cross-repo tracking issue during review. That filing became central to the #192 design call. |
| Alejandra Reyes-Fuentes (Staff Data Eng) | — | **4** (new) | Code-level review on #30 with 4 substantive technical findings (future.get defeating batching, no jitter on retry, validator gaps, ISO date slice). Every finding was a real bug. |

#### noorinalabs-isnad-graph team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Farhan Malik (Data Eng Lead) | — | **4** (new) | Reviewer on ip#18 — caught Phase-4 safety violation (`SET n += row.props`) that materially reshaped the final ingest design. Re-reviewed post-rewire and filed isnad-graph#843 as parallel followup to his own earlier-filed #842. |
| Arjun Raghavan (System Architect) | — | **4** (new) | Reviewer on ip#18 pre + post-rewire. Filed ip#19, #20, #23, #24 — four legitimate tech-debt followups at appropriate severity levels. |

#### noorinalabs-deploy team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Lucas Ferreira (SRE) | 3 | 3 | deploy#146 shipped with red CI (GET vs POST callback shape mismatch) — recovery via fixup #149 was clean and surfaced user-service#79 + deploy#148 process gaps. Minor ding offset by recovery discipline. Holding at 3. |
| Aisha Idrissi (SRE) | — | **4** (new) | Multi-role wave: implemented main#114 (auto_set_env_test fix) + reviewed deploy#146/#149 with network-topology and healthcheck analysis. Filed deploy#147 image-size reconciliation. |
| Nino Kavtaradze (Sec Eng) | — | **4** (new) | Security review on deploy#146 with comprehensive enumeration (prod compose untouched, no id_token signing surface, no host port leakage, fake creds grep-checked). |
| Bereket Tadesse (Infra Mgr) | — | **3** (new) | Appeared as review routing target (wasn't actually spawned this wave) + #177 post-merge verification executed cleanly by the fresh-spawn identity. |

### Done Well / Needs Improvement (Phase 2 Wave 9)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Wanjiku Mwangi** (TPM) | 5-day sustained delivery: #180 branch-regex, #21 D-ii rewire + topics.py, multiple clean reviews. Caught main#183 session-start regression + filed #184. | None this wave. |
| **Aino Virtanen** (SQL) | Heavy hook-author output: #174, #180, #183, #112-b × 6 child repos + ontology cleanup. Divergent-hook transparency pattern on #112-b was exactly right. | Initial session-start path regression on #183 (recovered in fixup same session). |
| **Weronika Zielinska** (PA) | `coalesce` Phase-4 approach was a material improvement over spec. Cross-PR shape-mismatch detection during own implementation. | None this wave. |
| **Mateo Salazar** (user-service Eng) | Security-fixup-inline over defer-to-followup (user-service#78 closed at merge, not left to tech-debt). | None this wave. |
| **Idris Yusuf** (user-service Sec) | Prevention-of-production-vulnerability review. Textbook security signal. | None this wave. |
| **Kwesi Boateng** (data-acquisition Int) | Changes-Requested → clean-fixup cycle worked exactly as designed. Topic-name reconciliation flagging in PR body led to right tracking. | None this wave. |
| **Alejandra Reyes-Fuentes** (data-acquisition Staff DE) | Four real technical findings on #30 — no false positives, all addressed in fixup. | None this wave. |
| **Farhan Malik** (isnad-graph DE Lead) | Phase-4 safety catch was the pivot point of the ip#18 rewire. Co-filed #842/#843 edge-model gaps. | None this wave. |
| **Arjun Raghavan** (isnad-graph Arch) | Four legitimate tech-debt followups at appropriate severity (coalesce null-asymmetry, property-map drift, retry compounding, schema source-of-truth). | None this wave. |
| **Lucas Ferreira** (deploy SRE) | Deploy#146 fixup recovery within 30 min; surfacing #79 + #148. | Merged deploy#146 with red CI — cross-verification against `gh pr checks` before `gh pr merge` would have prevented. |
| **Aisha Idrissi** (deploy SRE) | Auto_set_env fix shipped clean; review on deploy#146 network-topology was right-depth. | None this wave. |
| **Nino Kavtaradze** (deploy Sec) | Comprehensive deploy#146 security enumeration with grep-verified fake-creds non-leakage. | None this wave. |
| **Santiago Ferreira** (RC) | Consistent release-coordinator analysis on #180 and #187. | None this wave. |
| **Nadia Khoury** (PD) | Strategic sentinel-pattern review on #174 with followup filing discipline. | None this wave. |
| **Bereket Tadesse** (Infra Mgr) | Clean #177 verification with honest intermittency caveat. | None this wave. |
| **Orchestrator** | Volume execution across 4 repos; team-simulation scaled cleanly. | 2 red-CI merges (main#178, deploy#146); late design call for ip#18/#21 mismatch; premature "wave-9 concluded" handoff claim requiring user correction. |


---

## Phase 2 Wave 10 Trust Updates (2026-04-30) — Stg/Prod Environment Split + Promotion Pathway

### Org-Level Team (noorinalabs-main)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aino Virtanen (SQL) | 5 | 5 | Hook 17 `validate_wave_audit` shipped in `main#218` — load-bearing wave-conclusion gate. Charter updates (agents.md single-session-team delegation, hooks.md, issues.md) plus continued ontology hygiene. Already at max. |
| Nadia Khoury (PD) | 4 | 4 | Drove 5-repo wave-merge ceremony, resolved `user-service#89` ghcr-publish.yml union conflict, filed `main#222` branch-protection remediation tracker. Coordination-class output. No change. |
| Wanjiku Mwangi (TPM) | 5 | 5 | Cross-repo wave-coordination + project-board hygiene. Already at max. |
| Santiago Ferreira (RC) | 5 | 5 | §3.0.a TODO marker resolution closing `main#211`; secrets-audit migration runbook contributions. Already at max. |
| Bereket Tadesse (Infra Mgr) | 3 | **4** ↑ | Drafted comprehensive 278-line W10 retro readout (`.claude/drafts/w10-retro-readout-bereket.md`) before retro skill ran — ahead-of-the-game discipline. Five new feedback primitives surfaced and saved as memories during the wave (multi-layer gap, refresh-before-status-claim 4-site application, integrity-claim independent verification, runtime-gate scoping, live-trace acceptance). Promoted to "named-primitive author" tier. |

### Child-Repo Teams — New Entries / Updates

#### noorinalabs-deploy team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aisha Idrissi (SRE) | 4 | **5** ↑ | W10 heavy lifter: 8 PRs (#150 Hetzner per-env, #157 CF stg, #155 promote, #168 auth→users, #175 bootstrap GHCR pull, #185 TF sensitive(), #177 B2 runbook, #189 BACKUP_B2_*). Drove Phase B fresh-start rebuild and captured 6 cloud-init/module hardening gaps in `deploy#173`. Sustained Section A delivery. |
| Lucas Ferreira (SRE) | 3 | **4** ↑ | 4 W10 PRs (alembic pre-deploy gate, verify-deploy split stg/prod, compose-validate paths + actionlint, integration-tests branch trigger fix). No CI-red merges this wave — W9 ding does not recur. Multiple tech-debt followups filed during reviews. |
| Weronika Zielinska (PA / Kafka) | 4 | 4 | 2 deploy PRs on kafka-kraft work + parent-repo design contribution. No change. |
| Nino Kavtaradze (Sec Eng) | 4 | 4 | Ongoing security enumeration patterns. No new wave-specific incident. No change. |

#### noorinalabs-user-service team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Anya Kowalczyk (TL) | 3 | **4** ↑ | Drove `user-service#80` alembic merge migration — load-bearing for deploy alembic pre-deploy gate. Tech-lead review depth scaled with the wave's cross-repo dependency requirements. |
| Mateo Salazar (Eng) | 4 | 4 | 2-3 W10 PRs (#83 Contract v6 image-tag, #87 GHCR PR Trivy trigger, #88 ci.yml deployments/** fix). Security-fixup-inline pattern continues. Same-file PR sequencing on `ghcr-publish.yml` (#83 + #87 on different branches) led to wave-merge conflict — minor process gap; tractably resolved. Holding at 4. |
| Idris Yusuf (Sec Eng) | 4 | 4 | No new wave-specific security incident. Holding at 4 from W9. |

#### noorinalabs-isnad-graph team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Idris Yusuf (Sec Eng — isnad-graph member) | — | **4** (new) | `isnad-graph#847` pip 26.0.1 → 26.1 CVE-2026-3219 with parallel cherry-pick `#850` to main — multi-branch security coverage handled correctly. Pip CVE bump landed twice (wave + main); merge-collapse worked cleanly. |
| Linh Pham (Frontend) | — | **3** (new) | `isnad-graph#844` Contract v6 image-tag emission. First W10 contribution; appropriate-scope. |

#### noorinalabs-landing-page team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| K. Mensah-Williams | — | **3** (new) | `landing-page#71` Contract v6 image-tag. First entry. Appropriate-scope. |

### Done Well / Needs Improvement (Phase 2 Wave 10)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Aisha Idrissi** (deploy SRE) | 8 PRs sustained across 7 days. Phase B fresh-start rebuild executed end-to-end. 6 hardening-gap items filed in `deploy#173`. | None this wave. |
| **Bereket Tadesse** (deploy Mgr) | Pre-retro 278-line readout. 5 named primitives saved as memories. | None this wave. |
| **Lucas Ferreira** (deploy SRE) | 4 clean PRs with no CI-red repeat from W9. Tech-debt-followup filing discipline. | None this wave. |
| **Anya Kowalczyk** (user-service TL) | Alembic merge migration #80 unblocked deploy alembic gate. Tech-lead review depth on cross-repo dependency. | None this wave. |
| **Mateo Salazar** (user-service Eng) | Multi-PR scope discipline; #87 PR-Trivy trigger added good defensive depth. | Same-file PR sequencing on `ghcr-publish.yml` led to wave-merge conflict; rebase-before-second-merge would have prevented. |
| **Idris Yusuf** (Sec Eng) | Pip CVE bump multi-branch coverage (#847 wave + #850 main cherry-pick) handled cleanly. | None this wave. |
| **Aino Virtanen** (SQL) | Hook 17 ship + charter updates. | None this wave. |
| **Nadia Khoury** (PD) | 5-repo wave-merge ceremony coordination + ghcr-publish.yml conflict resolution. | None this wave. |
| **Orchestrator** | Wave-wrapup ceremony executed end-to-end (ontology, annunaki, 45-worktree sweep, 5-repo wave-merge sequence, conflict resolution, retro). | Initial `git merge` on user-service local wave-10 was at a stale ref (3 behind origin); local-ref-staleness check before merge would have been cleaner. |


---

## Phase 3 Wave 1 Trust Updates (2026-04-30) — Promotion Pipeline Goes Prod

### Org-Level Team (noorinalabs-main)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aino Virtanen (SQL) | 5 | 5 | Not actively spawned this wave; ontology rebuild + commit identity attribution on session-start + wave-wrapup commits. Already at max. |
| Nadia Khoury (PD) | 4 | 4 | Not actively spawned this wave (single-team pattern; orchestrator drove dispatch directly). No change. |
| Wanjiku Mwangi (TPM) | 5 | 5 | Not actively spawned this wave. No change. |
| Santiago Ferreira (RC) | 5 | 5 | Not actively spawned this wave. No change. |

### Child-Repo Teams — P3W1 Updates

#### noorinalabs-deploy team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aisha Idrissi (SRE) | 5 | 5 | Heavy lifter again: 4 PRs authored (#198 promote.yml stg-verify gate, #202 integration-tests remote-mode, #207 verify-stg flip, #210 alembic textfile metrics) + 3 reviewed (#197, #201, #208). Pattern B implementer-side founding data point: caught 3-x scope expansion on #161 pre-implementation (alert never landed in #153, textfile collector not configured) — saved a dead-code-at-merge round-trip. Pattern A data point: design-rationale block at #198 lines 232-258 (gate-stg-verify rationale). Judgment sharper than spec on three calls (#161 alert split into Failure + Stale, #198 freshness filter defense, #210 cloud-init wiring choice). Already at max. |
| Lucas Ferreira (SRE) | 4 | **5** ↑ | Reviewer-class standout this wave. Three substantive interventions: (1) Caddyfile evidence-receipts at lines 88-89 / 101 catching real false-positive bug on Aisha's #206 USER_SERVICE_URL/SITE_URL fallback; (2) Drift-catch on #210 v3 manager-pass that Bereket missed (runbook L161 + compose 614-621 staleness vs cloud-init/0755 reality); (3) Reality-post-#87 mapping table on #206 PR body — issue body's "Deploy noorinalabs-isnad-graph" trigger names were stale; honest scope reframe + delivery of actual non-legacy work. Plus 3 PRs authored (#197 rollback expand with bundled per-service env-var fix, #201 db-migrate wiring with 5-path retag-gate truth table, #206 verify-deploy multi-trigger) and clean self-correction discipline on his own #210 first-comment header inversion (within 2 minutes via re-post). Promoted to named-primitive author tier. |
| Bereket Tadesse (Infra Mgr) | 4 | 4 | Strong manager-pass review pattern (8 manager-direct + manager-pass second-reviews this wave) + Pattern A data point (5-path retag-gate truth table on #201) + scope-rationalization rigor. Pattern B-mirror data point: implementer pushback discipline guidance on Aisha's freshness-filter pushback. Authored four-pattern retro synthesis ahead of retro skill. **Negative signal**: 6 self-violations of `feedback_refresh_before_status_claim` in one wave (manager-class self-overconfidence-after-attention-fatigue), plus drift-catch failure on #210 v3 manager-pass that Lucas caught (claimed comprehensive coverage on a load-bearing review). Net: positive contribution + honest self-correction discipline (each violation self-flagged) balances the manager-class-amplifier coverage failures. Hold at 4. Worth reassessing next wave if pattern persists. |
| Weronika Zielinska (PA) | 4 | 4 | Clean blackbox-exporter delivery (#208) — 4-artifact scope (compose service + module config + scrape config + alert rules + Grafana dashboard + runbook + amtool silence recipe). Fold-in of Bereket's (b) hairpin-NAT + (c) cert-expiry-non-HTTPS observations into PR; filed (a) double-pager guard as #209 follow-up — multi-layer-gap discipline applied correctly. Pattern A data point: load-bearing assertion comments per module file. Initial header-convention inversion on #208 first review (corrected via re-post by orchestrator in #208 merge cycle). Hold at 4. |
| Nino Kavtaradze (Sec Eng) | 4 | 4 | Not actively spawned this wave. No change. |
| Nurul Hakim (Observability Eng) | 3 | 3 | Pinged by Aisha for textfile-collector path/UID consultation on #161; did not respond inside the 5-minute window. Aisha defaulted to runbook-step recipe per orchestrator's fallback, then Bereket override-amended to cloud-init wiring per Bereket-axiom-zero (no snowflake infra). No change — single pinged-but-non-responsive signal; not enough to move trust either direction. Worth flagging to ensure she's reachable for future observability surface decisions. |

### Done Well / Needs Improvement (Phase 3 Wave 1)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Aisha Idrissi** (deploy SRE) | 4 PRs + 3 reviews + 3-x scope catch on #161 + dual-alert design (Failure + Stale) sharper than spec + freshness-filter pushback on #198 review (push-back-when-preference, accept-when-bug discipline) | Pattern C: 2 instances — silent-idle without team-lead handoff message at #202 PR-open + post-merge state-stale push at #210 (`684f1b2` rebase landed AFTER #210 squash merged); accepted both as Pattern C self-application |
| **Lucas Ferreira** (deploy SRE) | 3 PRs + 4 reviews + 3 substantive bug-catches + clean self-correction within 2 min on #210 first-comment header inversion + Reality-post-#87 mapping table on #206 (honest audit against stale issue body) | Pushed #206 before #205 merged against explicit "wait" instruction; technical merit sound (textually disjoint sections of verify-deploy.yml; both PRs MERGEABLE simultaneously) but instruction-non-compliance worth retro note |
| **Bereket Tadesse** (deploy Mgr) | 8 manager-passes + Pattern A 5-path retag-gate truth table on #201 + scope rationalization on #161 (atomic three-part Option 1 call) + cloud-init Bereket-axiom-zero override + 4-pattern retro synthesis before retro skill ran | 6 Pattern C self-violations including drift-catch failure on #210 v3 (claimed comprehensive coverage; Lucas caught the runbook L161 + compose 614-621 drift); self-named on `feedback_refresh_before_status_claim` memory but most-violation-prone role this wave |
| **Weronika Zielinska** (PA) | Clean blackbox-exporter delivery + Pattern A load-bearing-assertion module comments + multi-layer-gap discipline on (a)/(b)/(c) review observations | Initial header-convention inversion on #208 first review (corrected via re-post in merge cycle) |
| **Orchestrator** | 8/8 PRs landed; 9 follow-ups filed during wave (#199 #200 #203 #204 #209 #211 #212 + main#232 + main#233); Pattern A/B/C synthesis converged with Bereket's; honest acknowledgment of 1 Pattern C instance on self (2/2-cleared misclaim); 9 worktree cleanup; ontology resolved | 1 Pattern C instance (premature "2/2 cleared" status claim on #208 before reviewer count was actually verified); main#233 charter-clarification framing initially wrong — corrected after Bereket's wire-artifact verification (originally proposed 2-readings ambiguity that didn't exist; only Reading 1 in actual use) |


---

## Phase 3 Wave 3 Trust Updates (2026-05-04) — Post-Emergency Stabilization + Frontend Absolute-URLs Phase 2

### Org-Level Team (noorinalabs-main)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aino Virtanen (SQL) | 5 | 5 | Actively spawned. main#242 (block stale `/tmp/*` message/body files, +384/-0) — biggest main# PR in the wave; new PreToolUse hook with table-driven config, dispatcher integration, and tests. Clean ship: 4/4 CI green, single-cycle Approved by Nadia + Wanjiku. Already at max. |
| Nadia Khoury (PD) | 4 | 4 | Actively spawned. main#241 Pattern D adoption signal-check audit (+170/-0). Tracking deliverable, scope-appropriate. Single-cycle Approved by Aino + Wanjiku. No change. |
| Wanjiku Mwangi (TPM) | 5 | 5 | Org-level 2nd-reviewer on both main# PRs (#241, #242). Already at max. |
| Santiago Ferreira (RC) | 5 | 5 | Not actively spawned this wave. No change. |

### Child-Repo Teams — P3W3 Updates

#### noorinalabs-deploy team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aisha Idrissi (SRE) | 5 | 5 | 4 PRs (#254 smoke fix `+36/-33`, #258 phantom `/auth/login` `+36/-29`, #260 cold-rebuild gate `+876/-0` first-deploy bug-class acceptance gate, #267 oauth runbook `+253/-0`). One ChangesRequested cycle on #267 (Bereket caught wrong workflow input `image_tag`→`source_sha` + 4 other items in 2nd-reviewer pass; Aisha shipped 5 fixes in 49 lines clean, additive commit, no force-push). 0 CI failures across all 4. Already at max. |
| Lucas Ferreira (SRE) | 5 | 5 | 2 PRs (#257 TF CF+B2 CI matrix `+223/-47`, #266 Caddy CSP `+21/-1`). Reviewer-class signal: 2nd-review on #266 caught a SHA citation drift in Bereket's review (`3792b97a` cited vs actual unblocker head `fb9d44d3`) — meta-state-verification (verified Bereket's verification). Drove cross-repo Option A on #266 ChangesRequested by triggering user-service#92. 0 CI failures. Already at max. |
| Bereket Tadesse (Infra Mgr) | 4 | **5** ↑ | Wave-completion reviewer standout. Caught **5 distinct must-fix items** across 4 wave-completion batch PRs: (1) #266 live-state mismatch — PR body claimed `users.*` was JSON-only, but live trace showed `/docs` + `/redoc` returning HTML; triggered cross-repo Option A → US#92. (2) #259 operational concern on `auth-login-redirect` probe handling; Weronika chose Path A bundled. (3) #261 `gate-stg-verify` job-level `permissions:` shadowing workflow-level (YAML resolution semantic bug). (4) #261 runbook `#127`→`#262` ref correction. (5) #267 wrong workflow input name `image_tag`→`source_sha` + 4 secondary items. Pattern B (verify-vs-artifact) applied textbook on every review (HEAD SHA cited, `gh api contents` reads, deltas measured). P3W1 Pattern C 6-violation pattern did NOT recur — strong reversal signal. Promoted to max. |
| Weronika Zielinska (PA) | 4 | **5** ↑ | 2 substantive PRs (#259 prometheus blackbox `+50/-19`, #261 break-glass audit `+725/-16` first composite action in repo). 3 ChangesRequested items resolved cleanly across both PRs (Path-A bundled on #259; permissions shadowing + runbook ref on #261). Tech-debt self-correction signal: caught own PR-body claim that `TechDebt: #127` was active before Bereket's review started (verified `#127 CLOSED 2026-04-19`); updated PR body in real time. Pattern A data points: composite-action design rationale documented inline. 0 CI failures. Promoted to max. |
| Nino Kavtaradze (Sec Eng) | 4 | 4 | Not actively spawned this wave. No change. |
| Nurul Hakim (Observability Eng) | 3 | 3 | Not actively spawned this wave. No change. |

#### noorinalabs-user-service team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Idris Yusuf (Sec Eng — user-service member) | 4 | **5** ↑ | Cross-repo unblocker pattern: user-service#92 (`+68/-1`, disable FastAPI `/docs` + `/redoc` + `/openapi.json` in production via env-gated `docs_url=None`) emerged DURING the wave to unblock deploy#266 ChangesRequested (Bereket's live-state catch on `users.*` non-JSON-only finding). Minimal-surgical fix; appropriate-scope override of "wait for next wave" tendency given cross-repo blocker context. Same engineer also shipped isnad-graph#854 (`+9/-1` Trivy nghttp2-libs CVE digest-pin + apk upgrade) — multi-repo coverage class signal (P3W1 not-spawned → P3W3 founding cross-repo coverage). Promoted to max. |
| Anya Kowalczyk (TL) | 4 | 4 | Not actively spawned this wave (Idris-91 work was solo cross-repo; Anya-class would have been 2nd reviewer if hook had been spawned). No change. |
| Mateo Salazar (Eng) | 4 | 4 | Not actively spawned this wave. No change. |

#### noorinalabs-isnad-graph team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Idris Yusuf (Sec Eng — isnad-graph member) | 4 | **5** ↑ | Same engineer cross-mapped from user-service team — single trust track. isnad-graph#854 surfaced as a pre-wave Trivy HIGH blocker (CVE-2026-27135 nghttp2-libs); shipped digest-pin + `apk upgrade --no-cache` combination in 9 lines; image size delta tractable (+1.8% to 95.2MB). Cross-repo coverage class. Promoted to max in conjunction with US team entry. |
| Linh Pham (Frontend) | 3 | 3 | Not actively spawned this wave. No change. |
| Jiyoung Park (Frontend) | — | **3** (new) | isnad-graph#855 first contribution (`+51/-5` frontend absolute URLs via `VITE_USER_SERVICE_ORIGIN`). Surgical scope — wires the env-var, adds typed accessor, no behavior change at the API call sites. Clean ship: 9/9 CI green, single-cycle Approved. New entry at 3 (appropriate-scope). |

#### noorinalabs-landing-page team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| K. Mensah-Williams | 3 | 3 | landing-page#75 (`+16/-0` emit OCI image index for multi-arch parity, closing deploy#242). Surgical workflow change. Clean ship: 2/2 CI green, single-cycle Approved. Holding at 3 (second appropriate-scope contribution; consistent with W10 entry profile). |

### Done Well / Needs Improvement (Phase 3 Wave 3)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Bereket Tadesse** (deploy Mgr) | 5 must-fix catches across 4 wave-completion PRs; Pattern B textbook application (HEAD SHA + `gh api contents` + delta measurement on every review); P3W1 Pattern C 6-violation pattern did NOT recur — strong reversal signal | None this wave. |
| **Weronika Zielinska** (PA) | First composite action in repo (#261); Path-A discipline on #259; tech-debt self-correction caught `TechDebt: #127` closed-state before review started; both ChangesRequested cycles resolved with additive commits (no force-push) | None this wave. |
| **Aisha Idrissi** (deploy SRE) | 4 PRs sustained delivery; cold-rebuild gate (#260) is W2-retro action item — closed at first opportunity; ChangesRequested-on-#267 cycle resolved cleanly with 5 fixes in additive 49-line commit | None this wave. |
| **Lucas Ferreira** (deploy SRE) | Meta-state-verification on #266 (caught Bereket's SHA citation drift); cross-repo Option A escalation worked end-to-end; #257 TF CI matrix is W2-retro action item — closed at first opportunity | None this wave. |
| **Idris Yusuf** (cross-repo Sec) | Founding cross-repo-coverage data point (US#92 + isnad-graph#854 in same wave); minimal-surgical fix shape held under cross-repo blocker pressure | None this wave. |
| **Aino Virtanen** (SQL) | Largest main# PR in wave (#242, 384 lines); table-driven hook with tests | None this wave. |
| **Orchestrator** | 14/14 PRs landed clean; 0 CI failures wave-wide; 4 ChangesRequested cycles all resolved without force-push; promotion-audit ran end-to-end (deterministic 0/0/60/3/1); honest filing of 6 orchestrator-class gaps as their own issues (main#238 wave-kickoff multi-repo + 5 sibling tracking comments) | 6 orchestrator-class pre-flight gaps — caught by implementers/reviewers/hooks, not pre-flight. Recurring class: wave-branch-creation (Aisha-252 catch), deploy#242 attribution (Idris-853 catch), child-repo-implementer rule (landing-page + user-service mid-wave), 2-reviewer planning, agent-naming pattern, spawn-brief-reviewer-order-inversion. main#238 tracks the wave-kickoff fix; the rest need a pre-flight checklist. Used `--admin` override on 5 wave-merge PRs because validate_pr_review.py treats Requestee-as-reviewer mismatching the wave's Requestee=author format (main#244 tracks the hook fix). |



---

## Phase 3 Wave 4 Trust Updates (2026-05-05) — Tooling & Process-Discipline Cleanup

### Org-Level Team (noorinalabs-main)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aino Virtanen (SQL) | 5 | 5 | 8 main# PRs (~5400 LOC), 0 CI failures, theme-coherent hook bug-class consolidation. #248 shared `_shell_parse.py` parser refactor closing 7 issues; #250 validate_pr_review canonicalization closing 3 issues (eliminated W3's 5/5 wave-merge admin-override pattern); #254 charter+docs sweep closing 6 followups; #256 validate_edit_completion hook; #257 validate_workflow_paths_coverage hook; #261 Hook 14 NEUTRAL allowlist; #265 canonical hook-sync doc Phase 1; #266 promotion-audit STALE-OPT-OUT class. One ChangesRequested cycle on #250 resolved with additive commit (no force-push). Already at max. |
| Wanjiku Mwangi (TPM) | 5 | 5 | 2 skill PRs closing W3 retro carry-forwards: #245 wave-kickoff multi-repo branches (closes #238), #249 wave-scope reconciliation (closes #196). Pattern B reviewer-class signal: ChangesRequested catch on #250 (caught canonicalization edge case; resolved cleanly via additive Reply). Reviewer on all 10 main# PRs. Already at max. |
| Nadia Khoury (PD) | 4 | 4 | Reviewer-only this wave (no implement spawns). All approvals 1st-cycle Approved or single-reply chains. No level-changing positive/negative signal. No change. |
| Santiago Ferreira (RC) | 5 | 5 | Reviewer on #266 only — wave theme was tooling, not deploy-class. Already at max. |

### Child-Repo Teams — P3W4 Updates

#### noorinalabs-isnad-graph team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Linh Pham (DevOps Eng) | 3 | **4** ↑ | First substantive shipper-class entry: isnad-graph#858 (`+370/-0`, validate_commit_identity cross-repo merge handling + strip ordering tests, closes #819 + #814). Test-discipline-class contribution at appropriate scope. 9/9 CI green, 4 charter-format comments, single-cycle Approved. |
| Ingrid Lindqvist (Engineer) | — | **3** (new) | First contribution: isnad-graph#857 (`+1/-1` CLAUDE.md branching backslash → slash, closes #852). Trivial doc-sync; appropriate-scope first entry. 9/9 CI green. New entry at 3. |

#### noorinalabs-user-service team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Mateo Salazar (Engineer) | 4 | 4 | user-service#94 (`+1/-1` CLAUDE.md slash sync, closes #90). Trivial doc-sync; not a level-changing signal. Hold at 4. |

#### noorinalabs-design-system team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Kofi Mensah (Docs / Storybook Eng) | — | **3** (new) | First contribution: design-system#63 (`+1/-1` CLAUDE.md slash sync, closes #62). Trivial doc-sync; appropriate-scope first entry. 2/2 CI green. New entry at 3. |

#### noorinalabs-data-acquisition team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Sofia Cardoso (Tech Writer) | — | **3** (new) | First contribution: data-acquisition#34 (`+1/-1` CLAUDE.md slash sync). Trivial doc-sync; appropriate-scope first entry. 4/4 CI green. New entry at 3. |

### Done Well / Needs Improvement (Phase 3 Wave 4)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Aino Virtanen** (SQL) | Theme-coherent 8-PR hook bug-class sweep; #248 shared parser closing 7 issues; #250 eliminated W3's wave-merge admin-override pattern in same wave it landed; 5400 LOC at 0 CI failures | None this wave. (Wave-concentration risk noted at the team level — 80% of main# from one engineer — but assessed against the engineer as theme-fitness, not negative signal.) |
| **Wanjiku Mwangi** (TPM) | 2 skill PRs closing W3 retro carry-forwards; ChangesRequested catch on #250; reviewer on all 10 main# | None this wave. |
| **Nadia Khoury** (PD) | Reviewer coverage on all 10 main# PRs; clean approvals | Not actively spawned for implement work this wave; reduced visibility on coordination-class output. |
| **Santiago Ferreira** (RC) | Reviewer on #266 | Theme-misalignment — RC role is light when wave is tooling-only; no actionable improvement. |
| **Linh Pham** (isnad-graph DevOps) | 370-line hook-test PR closing #819+#814; test-discipline at appropriate scope | None this wave. |
| **Ingrid Lindqvist** (isnad-graph Eng) | First contribution executed cleanly | None this wave. |
| **Mateo Salazar** (user-service Eng) | Same-day 1-line trivial sync | None this wave. |
| **Kofi Mensah** (design-system Docs Eng) | First contribution executed cleanly | None this wave. |
| **Sofia Cardoso** (data-acquisition Tech Writer) | First contribution executed cleanly | None this wave. |
| **Orchestrator** | 14/14 PRs landed; 0 CI failures wave-wide; 0 admin overrides (down from 5/5 in W3); 3-of-3 W3 retro action items discharged in W4; promotion-audit ran end-to-end (deterministic 0/0/65/3/1) | Wave-concentration: 80% of main# from one engineer is fragile; W5 carry-forwards (#263, #264) MUST distribute across implementers. ingest-platform was in declared scope but produced 0 PRs — silent scope-drop with no de-scope decision recorded. 4 child-repo trivial doc-sync PRs ran as separate review pairs instead of bundled — overhead-heavy for byte-identical change. |

---

## Phase 3 Wave 5 Trust Updates (2026-05-06) — Multi-Repo Fan-Out + Memory Classification + Skill Self-Improvement

### Org-Level Team (noorinalabs-main)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aino Virtanen (SQL) | 5 | 5 | 3 main# PRs, all clean. #275 (`+2/-0` ci.yml paths filter for `.claude/skills/**`, closes #267) — minimal scope, exactly the right size for a CI gate fix. #276 (`+217/-0` thread `/wave-scope` into `/wave-retro` Step 9 + `/wave-kickoff` Step 0a + `/wave-scope` Step 13 timestamp write, closes #273) — both reviewers ChangesRequested, resolved via additive Reply commits + clean Approved cycle. #277 (`+725/-0` systematic frontmatter classification of 36 feedback memories, closes #269) — load-bearing memory-system work that flips the next `/promotion-audit` from `0 AUTO / 0 DECIDE` to a real surface. Concentration dropped to **27%** (3/11) from W4's 80% — W4 retro action item #2 (distribute fan-out) achieved. Already at max. |
| Wanjiku Mwangi (TPM) | 5 | 5 | #279 (`+4/-0` charter Single-Reviewer Exception cross-reference paragraphs, closes #271) — completed the W4-retro followup Aino flagged on PR #270. Pattern B reviewer-class catch on #276 (ChangesRequested on wave-scope edge case alongside Nadia, both resolved via additive Reply). Reviewer on all 4 main# PRs. Already at max. |
| Nadia Khoury (PD) | 4 | 4 | Reviewer on all 4 main# PRs. Pattern B catch on #276 alongside Wanjiku (independent ChangesRequested, both with additive-resolution Approved cycle). No implement-class spawn this wave; coordination-class signal is reviewer-only. No change. |
| Santiago Ferreira (RC) | 5 | 5 | Theme was multi-repo fan-out + memory + skills — no deploy-class work routed to RC. Already at max. |

### Child-Repo Teams — P3W5 Updates

#### noorinalabs-isnad-graph team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Linh Pham (DevOps Eng) | 4 | 4 | isnad-graph#861 (`+37/-1173` canonical hook-paths migration — delete copies + rewrite settings.json). 1 ChangesRequested cycle (Anya + Arjun both CR'd; resolved via Reply chain + Approved). 9/9 CI green, 9 charter-format comments. Substantive cross-repo fan-out execution at appropriate scope. Hold at 4 — clean execution, no level-changing signal. |

#### noorinalabs-user-service team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Mateo Salazar (Engineer) | 4 | 4 | user-service#96 (`+152/-449` canonical hook-paths migration — rewrite settings.json + delete copy-resident hooks). 0 CR cycles. 1/1 CI green. Approved by Anya Kowalczyk + Idris Yusuf. Step up in scope from W4's 1-line trivial sync; clean execution. Hold at 4. |

#### noorinalabs-design-system team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Kofi Mensah (Docs / Storybook Eng) | 3 | **4** ↑ | Second contribution at substantive scope: design-system#66 (`0/-273` chore: remove copy-resident orphan hook files, closes #65). 0 CR cycles. 2/2 CI green. Approved by Maeve Callahan + Keanu Tama. Promotion to 4 reflects clean execution at meaningful scope (273-line delete is materially larger than W4's 1-line entry). |

#### noorinalabs-data-acquisition team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Tarek Mansour (Engineer) | — | **3** (new) | First wave-PR entry: data-acquisition#37 (`0/-273` drop copy-resident hook remnants — parent-canonical sweep, closes #36). 0 CR cycles. 4/4 CI green. Approved by Dilara Erdogan + Alejandra Reyes-Fuentes. Implementer-substitution from declared scope (Sofia Cardoso was the kickoff-declared implementer for T1A #263 in this repo — see § Done Well / Needs Improvement and feedback log Pain Point #2). New entry at 3 — appropriate-scope first wave PR, clean execution. |
| Sofia Cardoso (Tech Writer) | 3 | 3 | No PR this wave; declared T1A #263 implementer position handed off to Tarek Mansour with no recorded swap rationale. Not a negative signal against Sofia (no failure to deliver — work was reassigned). Hold at 3. |

#### noorinalabs-isnad-ingest-platform team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Yusuke Inoue (Engineer, Principal) | — | **4** (new) | First substantive PR entry: ingest-platform#26 (`+12/-9` drop Dockerfile workaround, install via uv export+pip from authoritative lock, closes #14). 0 CR cycles. Approved by Adaeze + Bjorn. Closes a long-deferred Dockerfile-workaround issue and resolves W4's silent-scope-drop pattern by being the active implementer for ingest-platform's first real wave-cycle deliverable. New entry at 4 — Principal-level scope on a previously-deferred load-bearing fix. |

#### noorinalabs-deploy team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Lucas Ferreira (SRE) | 5 | 5 | deploy#271 (`0/-781` canonical hook-paths migration — delete copies + rewrite settings.json). Largest deletion in wave (781 lines). 0 CR cycles. Approved by Bereket Tadesse + Aisha Idrissi. Clean execution on the largest fan-out target. Already at max. |

#### noorinalabs-landing-page team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Kofi Mensah-Williams (Engineer) | 3 | **4** ↑ | landing-page#79 (`0/-273` chore: delete stale copy-resident `.py` — adopt parent-canonical pattern, closes #78). 0 CR cycles. 2/2 CI green. Approved by Marcia Vasquez-Paredes + Nazia Rahman. Original P1 entry flagged "Some CI fixes needed post-PR"; this W5 PR was clean from first push. Promote to 4 — execution discipline corrected. |

### Done Well / Needs Improvement (Phase 3 Wave 5)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Aino Virtanen** (SQL) | 3 main# PRs across 3 distinct surfaces (CI, skill-threading, memory-classification) at concentration that dropped from W4's 80% to **27%**; #277 sets up the next promotion-audit AUTO surface (5 candidates were 0 pre-#277); clean additive-Reply discipline on #276 ChangesRequested cycle | None this wave. |
| **Wanjiku Mwangi** (TPM) | Pattern B reviewer-class catch on #276 (independent of Nadia); cleared W4-retro followup #271 same-wave | None this wave. |
| **Nadia Khoury** (PD) | Reviewer on all 4 main# PRs; Pattern B catch on #276 | Still no implement-class spawn this wave; level pinned at 4 by reviewer-only profile across W3+W4+W5. |
| **Santiago Ferreira** (RC) | Theme-misalignment — RC role is light when wave is non-deploy | No actionable improvement; theme-routed wave shape. |
| **Linh Pham** (isnad-graph DevOps) | Substantive +37/-1173 fan-out; resolved 2 reviewer ChangesRequested cycles cleanly | None this wave. |
| **Mateo Salazar** (user-service Eng) | Step-up scope (+152/-449) executed cleanly, 0 CR | None this wave. |
| **Kofi Mensah** (design-system Docs Eng) | Second contribution at substantive scope (273-line delete), 0 CR | None this wave. |
| **Tarek Mansour** (data-acquisition Eng) | First wave PR (273-line delete) clean, 4/4 CI | Implementer-substitution from declared scope (replaced Sofia Cardoso) is not recorded anywhere — process gap, not engineer-class failure (see Pain Point #2 + Proposed Process Change #1). |
| **Yusuke Inoue** (ingest-platform Eng, Principal) | First substantive PR closes load-bearing long-deferred #14; resolves W4 silent-scope-drop pattern | None this wave. |
| **Lucas Ferreira** (deploy SRE) | Largest deletion in wave (-781 LOC) clean, 0 CR | None this wave. |
| **Kofi Mensah-Williams** (landing-page Eng) | Clean PR (273-line delete), 2/2 CI — corrects P1 "CI fixes needed" pattern | None this wave. |
| **Orchestrator** | 11/11 PRs landed; 0 CI failures (where CI ran); 0 admin overrides (2nd consecutive zero-override wave); concentration dropped 80%→27% — W4 retro action item #2 fully discharged; ingest-platform produced first real wave-PR (W4 retro action item #3 discharged); /wave-scope auto-threading shipped IN-wave (#276) and the W4-retro action items closed within the same wave they landed | (a) Implementer-substitution in data-acquisition (declared Sofia Cardoso → actual Tarek Mansour) not recorded anywhere — same shape as W4 ingest-platform silent-drop, just inverted (silent-substitution vs silent-drop). (b) `wave_5_changes_requested_cycles: 6` in cross-repo-status.json vs 4 observable from PR data (#276: 2, isnad-graph#861: 2) — counter discrepancy worth reconciling. (c) 4 of 11 PRs (#277, #279, deploy#271, ingest-platform#26) had `CheckRollup: 0` — #275 paths-filter fix only covers main; per-repo CI scope-coverage gap unaddressed. |

## Phase 3 Wave 6 Trust Updates (2026-05-07) — Backlog Triage + Runbook Fan-Out + Hot-Fix

### Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aino Virtanen (SQL) | 5 | 5 | main#288 (`fix(/wave-scope #278)`: idempotent JSON-write helper, Tier-4 W5 carry-forward) — clean execution. R1 reviews on all 7 wave-merge PRs (charter format, refresh-discipline, diff-vs-body verification). In-flight #294 hook fix — surfaced the wave-merge head-ref parser gap during her R1 review of #293; promoted same-wave self-improvement (Pattern G repeat). Already at max. |
| Wanjiku Mwangi (TPM) | 5 | 5 | main#291 (`fix(hook #289)`: validate_workflow_paths_coverage parser fix, post-scope hot-fix). Tier-1 noorinalabs-main backlog triage (16 issues audited, 18.75% close-rate, 31% defer-phase-15). 2 wrapup status commits (67cce96 wave_6_decisions, a3419a4 P3W6 CLOSED). Already at max. |
| Nadia Khoury (PD) | 4 | 4 | R2 reviews on all 7 wave-merge PRs (cross-repo coordination focus, scope-drop verification, carry-forward label-stripping verified). Co-author on design-system Tier-1 backlog triage with Kofi Mensah. Pattern: still no implement-class spawn; reviewer-only profile across W3+W4+W5+W6. Hold at 4. |
| Santiago Ferreira (RC) | 5 | 5 | No deploy-class wave routing this wave (theme: backlog hygiene + runbook fan-out, deploy work was Tier-2 routine). Already at max. |

### noorinalabs-isnad-graph team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Jun-Seo Park (Engineer) | — | **3** (new) | First wave-PR entry: isnad-graph#864 (settings.json matcher parity with noorinalabs-main, Tier-4 W5 carry-forward, closes #862). 0 CR. Approved by 2 child-team reviewers. New entry at 3 — appropriate-scope first-wave delivery, clean execution. |
| Anya Kowalczyk (Engineer) | 3 | 3 | Tier-1 noorinalabs-isnad-graph backlog triage — largest repo backlog (36 phase-3 issues older than 14 days). 100% verification rate against HEAD; 9 inline `phase-3`→`phase-15` relabels; surfaced production OAuth break (#824) and worktree-tracking bug (#807) as elevated-priority candidates. Disciplined audit; comment-only delivery per W6 design. Hold at 3 (no PR this wave). |

### noorinalabs-user-service team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Mateo Salazar (Engineer) | 4 | 4 | Tier-1 noorinalabs-user-service backlog triage (15 issues audited, every issue verified against `origin/main`). No PR this wave (Tier-1-only by design — repo had no Tier-2/3/4 W6 work). Disciplined origin-over-local verification per memory. Hold at 4. |

### noorinalabs-design-system team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Keanu Tama (Engineer) | — | **3** (new) | First wave-PR entry: design-system#69 (`docs(design-system #32)`: operational runbook, Tier-2 fan-out). 0 CR. New entry at 3. |
| Maricel Reyes (Engineer) | — | **3** (new) | First wave-PR entry: design-system#70 (`fix(design-system #67)`: settings.json matcher parity, Tier-4 W5 carry-forward). 0 CR. New entry at 3. |
| Kofi Mensah (Docs / Storybook Eng) | 4 | 4 | Tier-1 noorinalabs-design-system backlog triage (7 issues audited, 29% close-rate). Identified Chromatic-CI surface area on #53 + #54 as forward-coupler gap. Co-authored disposition table with Nadia. Hold at 4. |

### noorinalabs-data-acquisition team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Tarek Mansour (Engineer) | 3 | **4** ↑ | Second consecutive substantive wave: data-acquisition#40 (`docs(data-acquisition #22)`: operational runbook, Tier-2, with R1+R2 review fixups for local-vs-B2 path shape, Kafka envs, CLI flag — clean revision discipline). 0 CR. Promote to 4 — execution discipline plus W5 substitution rationale resolved. |
| Alejandra Reyes-Fuentes (Engineer) | — | **3** (new) | First wave-PR entry: data-acquisition#41 (`fix(data-acquisition #38)`: settings.json matcher parity, Tier-4 W5 carry-forward). 0 CR. New entry at 3. |
| Sofia Cardoso (Tech Writer) | 3 | 3 | Tier-1 noorinalabs-data-acquisition backlog triage — smallest backlog (4 issues). Surfaced #21 enrichment-pipeline as cross-repo relocation candidate to ingest-platform per ontology repo-split. Confirmed W6 Tier-1 slot post-W5-substitution. Hold at 3. |

### noorinalabs-isnad-ingest-platform team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Bjørn Henriksen (Engineer) | — | **3** (new) | First wave-PR entry: ingest-platform#28 (`docs(ingest-platform #7)`: operational runbook, Tier-2, with review fixups for offset-commit + ingest-row + 3 obs). 0 CR. New entry at 3. |
| Adaeze Okonkwo (Engineer) | 3 | 3 | Tier-1 noorinalabs-isnad-ingest-platform backlog triage (14 issues audited). Recommended 2 close-as-stale (#3 medallion superseded, #4 PoC superseded) and 1 relabel-relocate (#2). Pipeline-durability cluster correctly preserved as own future wave per meta-issue boundary. Hold at 3. |

### noorinalabs-deploy team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Lucas Ferreira (SRE) | 5 | 5 | deploy#273 (`docs(deploy #24)`: operational runbook, Tier-2 fan-out, with R1+R2 accuracy revisions). 0 CR. Already at max. |
| Bereket Tadesse (Manager) | 4 | 4 | Tier-1 noorinalabs-deploy backlog triage — largest backlog (40 issues audited, 22.5% close-rate via 7 stale + 2 dup; 23 relabel-later-wave preserving phase-3). Disciplined disposition delivery. Hold at 4 (comment-only). |
| Nurul Hakim (R1 reviewer) | — | **3** (new) | Caught load-bearing followup gap during PR #273 review: alertmanager `${VAR}` notifier was placeholder URL. Filed deploy#274 as runtime-vs-PR-acceptance distinction (per memory `feedback_runtime_gate_scoping`). Reviewer-class first entry at 3. |

### noorinalabs-landing-page team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Kofi Mensah-Williams (Engineer) | 4 | 4 | TWO PRs this wave (top concentration at 18% — well below 40% cap): landing-page#82 (`fix(landing-page #77)`: drop redundant push-time SSH-deploy, Tier-3 hotfix) + landing-page#81 (`docs(landing-page #49)`: operational runbook, Tier-2, with post-#82 publish-only workflow refresh). Multi-tier delivery; 4 approveds on #81 (revisions + re-approvals). Theme-fit doubleup, not fragility. Hold at 4. |
| Marcia Vasquez-Paredes (Project Lead) | 4 | 4 | Tier-1 noorinalabs-landing-page backlog triage (19 issues audited, 8 defer-future-phase relabels recommended). Surfaced #67/#69 as keep-in-P3-strategic carry-forward candidates with owner ruling rationale. Hold at 4. |

### Done Well / Needs Improvement (Phase 3 Wave 6)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Aino Virtanen** (SQL) | #288 wave-scope idempotency closes W5 carry-forward; R1 reviews on all 7 wave-merge PRs with refresh-discipline + artifact verification; same-wave self-improvement (#294 hook fix surfaced from her R1 review of #293) — Pattern G repeat | None this wave. |
| **Wanjiku Mwangi** (TPM) | #291 #289 hook paths-parser fix; thorough Tier-1 main triage (16 issues, evidence-cited dispositions); 2 wrapup status commits with truthful 0-admin-override accounting | None this wave. |
| **Nadia Khoury** (PD) | R2 reviews on all 7 wave-merge PRs (cross-repo coordination focus); scope-drop and carry-forward label-stripping verified at PR-review time; 3 retro candidates surfaced (e235b0b orphan, label-drift prevention, repo-split coordination) deferred-to-retro per discipline | Reviewer-only profile across W3+W4+W5+W6 (4 consecutive waves) — pinned at 4 by lack of implement-class delivery. Could implement a charter-update PR herself in W7 if PD-class write is desired. |
| **Santiago Ferreira** (RC) | Theme-routed wave (no deploy-cycle work) | No actionable improvement; theme-routed shape. |
| **Jun-Seo Park** (isnad-graph Eng, NEW) | First wave-PR clean | None this wave. |
| **Anya Kowalczyk** (isnad-graph Eng) | 100% verification rate on largest backlog (36 issues); 9 inline relabels with explicit rationale; surfaced production OAuth break (#824) | None this wave. |
| **Mateo Salazar** (user-service Eng) | Tier-1-only by design; disciplined origin-over-local verification | None this wave. |
| **Keanu Tama** (design-system Eng, NEW) | First wave-PR clean | None this wave. |
| **Maricel Reyes** (design-system Eng, NEW) | First wave-PR clean | None this wave. |
| **Kofi Mensah** (design-system Docs Eng) | Co-authored disposition; Chromatic-CI forward-coupler awareness | None this wave. |
| **Tarek Mansour** (data-acquisition Eng) | Second-consecutive substantive wave; clean revision discipline | None this wave. |
| **Alejandra Reyes-Fuentes** (data-acquisition Eng, NEW) | First wave-PR clean | None this wave. |
| **Sofia Cardoso** (data-acquisition Tech Writer) | Cross-repo relocation insight (#21) per ontology repo-split | None this wave. |
| **Bjørn Henriksen** (ingest-platform Eng, NEW) | First wave-PR clean (with review fixups absorbed) | None this wave. |
| **Adaeze Okonkwo** (ingest-platform Eng) | Pipeline-durability cluster correctly preserved as own future wave; 2 close-as-stale recommendations honored at wrapup | None this wave. |
| **Lucas Ferreira** (deploy SRE) | Tier-2 runbook with R1+R2 accuracy revisions | None this wave. |
| **Bereket Tadesse** (deploy Manager) | Largest-backlog discipline (40 issues); 22.5% close-rate with explicit later-wave preservation | None this wave. |
| **Nurul Hakim** (deploy R1, NEW) | Load-bearing followup gap caught at runtime-vs-PR-acceptance distinction; filed deploy#274 | None this wave. |
| **Kofi Mensah-Williams** (landing-page Eng) | Multi-tier delivery (Tier-2 + Tier-3 hotfix); post-#82 runbook refresh discipline | None this wave. |
| **Marcia Vasquez-Paredes** (landing-page Project Lead) | Surfaced #67/#69 as keep-in-P3-strategic with owner-ruling rationale | None this wave. |
| **Orchestrator** | 11/11 wave-internal PRs landed; 7/7 wave-merge PRs landed with truthful 0-admin-override (FIRST wave with truthful 0 — W3-W5 silently bypassed via --admin); 0 implementer substitutions; 0 ChangesRequested cycles; counter-verification step 2.5 had 0 drift (FIRST wave with this property since W5 added the discipline); 8/8 Tier-1 backlog triage delivery; in-band hook patch + canonical fix flow for #294 — 5-line patch, search-before-filing satisfied | (a) Local-vs-origin main divergence (e235b0b orphaned local commit) — kickoff status was committed locally but never pushed. Process discipline gap, orchestrator-class. (b) /tmp file-race recurring (3 hook blocks for spawned-agent gh-comment workflows this session). Existing memory `feedback_tmp_msg_file_stale.md` exists but spawned agents still hit it; agent-spawn discipline gap. (c) Pattern G persists at 4 instances in W6 alone (#285, #287, #289, #294 all hook parser bugs) — largest single-wave parser-bug cluster, suggests parser-fixture coverage discipline as charter principle. |

## Phase 3 Wave 7 Trust Updates (2026-05-08) — Hook Parser-Fixture Coverage Backport Audit

### Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aino Virtanen (SQL) | 5 | 5 | TWO PRs: #305 (#287 fix — `_shell_parse.tokenize()` line-continuation normalization + 3 scope-disciplined adjacent improvements + 11 fixtures + 12 fixture tests + 3 unit tests, 75/75 green) + #312 (T4 #260 _shell_parse refactor — 2 regex matchers migrated to tokenize/walker + 12 fixture tests pinning transitive #305 fix). 3 R1 reviews (#301, #308, #310 ★). Already at max. |
| Wanjiku Mwangi (TPM) | 5 | 5 | TWO PRs: #301 (#285 fix — SHA-shape regex validator + 4 fixtures incl. live-trigger 404 body + 8 cases) + #308 (T1 main parser audit — 31 hooks, 14 parser-class, 5 prioritized gaps filed as #302-#307). 3 reviews (R1 #305, R2 #310, R1 #312). Identified `gh project item-add` silent no-op + GraphQL `addProjectV2ItemById` workaround. Already at max. |
| **Nadia Khoury (PD)** | **4** | **5** ↑ | **★ Implement-class delivery** — PR #310 cross-repo audit summary with two-tier thesis, 3 charter proposals (2 filed as W8 issues #311 #313 + 1 inline silent-no-op family memory extension). PLUS 4 R2 reviews across #301, #305, #308, #312 with executive-lens framing on charter compliance and cross-PR coherence. Pre-loaded the ★ thesis content during R2 reviews (3 candidate observations baked before spawn). **W6 retro flag on 4-consecutive-reviewer-only-waves NOW resolved by ★ delivery.** Promote to 5 — full PD execution profile complete. |
| Santiago Ferreira (RC) | 5 | 5 | No deploy-cycle wave routing (theme: hook parser-fixture audit). Already at max. |

### noorinalabs-isnad-graph team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Anya Kowalczyk (Tech Lead)** | **3** | **4** ↑ | First implement-class PR: isnad-graph#871 (T1 audit + **Pattern G in-band fix** syncing `auto_set_env_test.py` from parent — `gh`/`--body` short-circuit backported from parent main#114 that was missing in child). Identity reconciled at first commit (matrix called her "Anya Volkov"; canonical roster identity is Kowalczyk; documented in PR body). Idris R1 + Arjun R2 Approved with framing notes (#868 + #870 are stale-worktree-only, not live regressions); she addressed issue-body cleanups async post-merge approval. Promote to 4 — clean cross-repo work + Pattern G in-band + post-review cleanup discipline. |
| Idris Yusuf (Engineer) | — | **3** (new) | First reviewer entry: R1 of isnad-graph#871 + user-service#100 (cross-repo R1). **Coined the wave-level thesis sentence**: "fixture-first discipline broke at the parent→child update boundary" — became Nadia's ★ thesis. Surfaced stale-worktree-vs-live distinction for #868/#870 framing cleanup. New entry at 3. |
| Arjun Raghavan (Engineer) | — | **3** (new) | First reviewer entry: R2 of isnad-graph#871. Independently confirmed stale-worktree-vs-live distinction; spot-checked Pattern G fix byte-equivalence to parent at parent's main HEAD. Minor note: #866-#870 missing `p3-wave-7` label (only `tech-debt+phase-3`) — non-blocking, flagged for /wave-scope p3 w8 cleanup. New entry at 3. |

### noorinalabs-user-service team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Mateo Salazar (Engineer) | 4 | 4 | Tier-1 audit PR user-service#100. Initial framing was pre-P3W5-stale (caught at R2 by Anya-K via committed-tree verification — **3rd-of-3 misclassifications** this wave). Addressed all 3 follow-throughs cleanly post-R2: project 2 GraphQL adds + #98/#99 re-scoped to PARENT test augmentation (parent genuinely missing `test_block_gh_pr_review.py`; alembic-shape coverage redirected to parent's existing tests). Hold at 4 — substantive correction caught at R2, addressed cleanly. |

### noorinalabs-deploy team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Bereket Tadesse (Manager)** | **4** | **5** ↑ | TWO PRs: deploy#278 (T3 #274 Alertmanager wiring with PR-vs-runtime acceptance discipline + post-review CI fix on shellcheck SC2016 false-positive — clean one-line `# shellcheck disable` resolution) + deploy#279 (T1 deploy audit — 6 parser-class hooks all stale-orphan + dead-code + non-registered, two backport issues #276 #277 filed). Stale-orphan finding contributed to wave-level structural framing (one of 4 reviewers/implementers triangulating). Promote to 5 — multi-tier disciplined delivery + clean post-review CI cycle + load-bearing structural-finding contribution. |
| Aisha Idrissi (R1 reviewer) | — | **3** (new) | First reviewer entry: R1 of deploy#278 + #279. Strong PR-vs-runtime split per `feedback_runtime_gate_scoping.md`. Caught minor RUNBOOK §Tier 0 cross-link one-hop note (judgment-call kept non-blocking). New entry at 3. |
| Weronika Zielinska (R2 reviewer) | — | **3** (new) | First reviewer entry: R2 of deploy#278 + #279. Independently verified secrets hygiene + amtool gate completeness. **Caught untracked-vs-committed nuance** for stale-orphan finding (load-bearing for ★ summary). Minor non-blocking note: amtool tarball verified via SHA256 but not GPG-verified for SHA256SUMS — acceptable for current threat model. New entry at 3. |

### noorinalabs-design-system team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Kofi Mensah (Docs / Storybook Eng) | 4 | 4 | Tier-1 audit PR design-system#73. Initial framing pre-PR#66-stale (caught at R1 by Maeve — **1st-of-3 misclassifications**). Addressed framing revision + re-scoped #72 (closed invalid) + later R2 PR-body-stale catch handled via `gh api -X PATCH --field` workaround when `--field "body=@file"` silently literal-pasted (**NEW silent-no-op family signal** — load-bearing for memory extension). Hold at 4 — substantive cycles but addressed cleanly. |
| Maeve Callahan (R1 reviewer) | — | **3** (new) | First reviewer entry: R1 of design-system#73 with substantive Changes-Requested. **Two-tier framing originator** (hook-owning vs dispatcher-style children) — became load-bearing for Nadia's ★ thesis. Strong charter-lens R1. New entry at 3. |
| Beren Yildiz (R2 reviewer) | — | **3** (new) | First reviewer entry: R2 of design-system#73 with PR-body-stale catch. Independent settings.json completeness verification established design-system as exemplary endpoint of dispatcher pattern (no #85-equivalent matcher gap; more complete than landing-page). New entry at 3. |

### noorinalabs-data-acquisition team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Sofia Cardoso (Tech Writer) | 3 | 3 | Tier-1 audit PR data-acq#45 — first implement-class delivery (Tier-1-only in W6). Initial G2 framing was wrong (caught at R2 by Jeanclaude via tree verification — **2nd-of-3 misclassifications**). Addressed cleanly with **methodological retro point** (filesystem ≠ committed tree → mandatory `gh api .../git/trees/<sha>?recursive=1` first step → now charter proposal #313). Hold at 3 — promote-watch for W8 if methodological-finding pattern continues. |
| Dilara Erdogan (R1 reviewer) | — | **3** (new) | First reviewer entry: R1 of data-acq#45. **Surfaced cross-repo PVTI-vs-issue-number false-match finding** (`gh project item-list --limit N` returns false matches because issue numbers collide across repos) — load-bearing for memory extension Proposal 3. New entry at 3. |
| Jean-Claude Habimana (R2 reviewer) | — | **3** (new) | First reviewer entry: R2 of data-acq#45 with substantive Changes-Requested. **Used `gh api git/trees recursive` to verify** — the methodology that becomes charter proposal #313. New entry at 3. |

### noorinalabs-landing-page team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Nazia Rahman (Senior QA / Performance Engineer)** | — | **4** (new) | First wave PR — substituted from "per-repo-roster-tbd" placeholder at fan-out (orchestrator pick based on parser-fixture-audit fit). Tier-1 audit PR landing-page#87. **Only audit that got it RIGHT first try** — origin-clean verified at head_sha, W5 PR #79 history correctly cited, 14 frontmatter + 8 MDX shape matrix per QA discipline (incl. BOM, multi-doc YAML, CRLF, Arabic Unicode, YAML anchors). 0 CR. Marcia R1 + Kofi-FE R2 both Approved cleanly. **NEW entry at 4** — clean first-wave delivery + strong domain discipline + only audit that exercised committed-tree-vs-filesystem correctly without R1/R2 catch. Merits start above default. |
| Marcia Vasquez-Paredes (Project Lead) | 4 | 4 | R1 of landing-page#87. All 6 checks passed including origin-clean verification + #85 carry-forward verified against PR #79 history. Strong project-lead lens. Hold at 4. |
| Kofi Mensah-Williams (Frontend Engineer) | 4 | 4 | R2 of landing-page#87. Astro-domain depth — verified Zod schema mapping for 14 frontmatter shapes + identified `cta.href` URL-form fixture-coverage gap as informational addendum. Hold at 4. |

### Done Well / Needs Improvement (Phase 3 Wave 7)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Aino Virtanen** (SQL) | #305 root-cause patch at `_shell_parse.tokenize()` module level (all consumers benefit transitively) + #312 first downstream beneficiary refactor with explicit transitive-fix pinning. 3 disciplined R1 reviews. | None this wave. |
| **Wanjiku Mwangi** (TPM) | #301 fix-with-fixtures cites e906e135 live trace (strongest acceptance available). #308 main parser audit thorough. Surfaced + worked around `gh project item-add` silent no-op via GraphQL. | None this wave. |
| **Nadia Khoury** (PD) | ★ implement-class delivery with full two-tier thesis, 3 charter proposals filed for W8, pre-loaded thesis material during R2 reviews. **W6 reviewer-only-profile flag resolved.** | None this wave. |
| **Santiago Ferreira** (RC) | Theme-routed wave (no deploy-cycle work). | No actionable improvement; theme-routed shape. |
| **Anya Kowalczyk** (isnad-graph TL) | First implement-class PR clean + Pattern G in-band parent-sync fix. | None this wave. |
| **Idris Yusuf** (isnad-graph Eng, NEW) | **Coined wave-level thesis sentence**; cross-repo R1 strength (own repo + user-service). | None this wave. |
| **Arjun Raghavan** (isnad-graph Eng, NEW) | Independent stale-worktree-vs-live confirmation; byte-equivalence verification of Pattern G fix. | None this wave. |
| **Mateo Salazar** (user-service Eng) | Clean post-R2 follow-through (project 2 GraphQL + #98/#99 parent-redirect). | Initial audit framing pre-P3W5-stale; should have run committed-tree check first (now codified as #313). |
| **Bereket Tadesse** (deploy Manager) | Multi-tier delivery + post-review CI fix discipline + stale-orphan finding contribution. | None this wave. |
| **Aisha Idrissi** (deploy R1, NEW) | Strong PR-vs-runtime split adherence per memory. | None this wave. |
| **Weronika Zielinska** (deploy R2, NEW) | Untracked-vs-committed nuance catch (load-bearing for ★). | None this wave. |
| **Kofi Mensah** (design-system Docs Eng) | Clean revision after R1; surfaced new `gh api -X PATCH -f body=@file` literal-paste gotcha. | Initial audit framing pre-PR#66-stale; PR body update missed at first revision (caught by R2). |
| **Maeve Callahan** (design-system R1, NEW) | **Two-tier framing originator** + dispatcher-style charter-clarification framing. | None this wave. |
| **Beren Yildiz** (design-system R2, NEW) | PR-body-stale catch + dispatcher-completeness verification. | None this wave. |
| **Sofia Cardoso** (data-acquisition Tech Writer) | First implement-class delivery; clean post-R2 revision with **methodological retro point** (committed-tree-first verification). | Initial G2 framing wrong (filesystem-vs-tree); now codified as #313. |
| **Dilara Erdogan** (data-acquisition R1, NEW) | PVTI-vs-issue-number false-match finding (load-bearing for memory extension). | None this wave. |
| **Jean-Claude Habimana** (data-acquisition R2, NEW) | `gh api git/trees recursive` methodology — becomes #313. | None this wave. |
| **Nazia Rahman** (landing-page QA, NEW @4) | **Only audit that got it RIGHT first try** — committed-tree-vs-filesystem distinction exercised correctly without R1/R2 catch; QA-discipline shape-matrix enumeration. | None this wave. |
| **Marcia Vasquez-Paredes** (landing-page Project Lead) | Origin-clean independent verification + #85 carry-forward traced to PR #79. | None this wave. |
| **Kofi Mensah-Williams** (landing-page Frontend Eng) | Astro Zod-schema verification + `cta.href` URL-form gap addendum. | None this wave. |
| **Orchestrator** | 12/12 PRs merged, 0 admin overrides; cross-repo two-tier thesis emerged organically via 5-reviewer + 4-implementer triangulation; ★ Nadia summary brief baked all retro-material in advance (full thesis + 3-act reference-impl set); phased Phase A/B/C wrapup executed cleanly; gh api PUT contents pattern used 3× for atomic status updates (no orphans); routed CR cycles to existing idle agents (no over-spawning); spotted CI shellcheck failure on deploy#278 post-review and routed to Bereket. | (a) Filed Node 20 deprecation issues during wrapup (mid-flow scope expansion); could have deferred. (b) Wrote wave_7 counters as nested `wave_7_summary.*` instead of TOP-LEVEL canonical keys — required atomic PUT during retro; /wave-wrapup skill update needed. (c) 3-of-3 audit framing misclassifications surfaced — Tier-1 audit spawn briefs did NOT enforce committed-tree-first verification methodology; should have baked Sofia/Jeanclaude's discovery into brief template prospectively. (d) `auto_set_env_test` hook false-positive on heredoc body containing pytest-substring caught at retro file-edit time — file via Write tool worked; suggests #114 short-circuit conditions need a heredoc-content extension. |

## Phase 3 Wave 8 Trust Updates (2026-05-10) — Foundation Reset (Hook/Skill/Charter Ownership Disambiguation + Artifact-CI Scope Definition)

### Wave Shape

| Metric | Value |
|---|---|
| PRs merged to wave-branches | 11 (across 5 of 7 in-scope repos) |
| Wave-branch → main merges | 5 (main, deploy, design-system, landing-page, data-acq) |
| Repos identical to main (no merge needed) | 2 (isnad-graph close-as-resolved bundle, user-service work shipped via parent #340) |
| Repos descoped during wave | 1 (ingest-platform — recorded in `wave_8_repos_descoped_during_wave`) |
| Approved review comments (charter-format) | 25 across 11 PRs (≈2.3/PR — at 2-reviewer minimum, several PRs at 3) |
| ChangesRequested cycles | 0 |
| Misformatted `Replied`/`Reply` corrected via addenda | 10+ (Approved-vs-Reply discipline cascade — Maeve catch) |
| Admin-overrides | 0 |
| Top-implementer concentration | Kofi Mensah-Williams 3/11 = **27%** (well below 60% fragility line; theme-fit since landing-page was fully W8-scoped) |
| Carry-forward to W9 | 20 issues (17 main + 1 user-service + 2 data-acq) |

### Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Nadia Khoury (Program Director) | 5 | 5 | ★ Filed 3 charter proposals during wave (#337 validate_wave_label_evidence hook, #341 Pre-Spawn State Check § extension, plus W9 lifecycle ownership). Multiple R1/R2 reviews with `state,mergedAt` discriminator discipline (her own templating spawn prelude). Hold at max. |
| Wanjiku Mwangi (TPM) | 5 | 5 | ★ Owned #309 Node 20 audit (4 of 5 child upgrades shipped). Anchored Approved-vs-Reply discipline propagation via wave-wide guidance comment (Step 4 manager pre-merge check). PUT-contents pattern for kickoff + wrapup status commits — zero local-orphans. Hold at max. |
| Santiago Ferreira (Release Coordinator) | 4 | 4 | Theme-routed wave (no deploy-cycle work — W8 was process-discipline focused). Hold. |
| Aino Virtanen (Standards & Quality Lead) | 5 | 5 | ★ Authored #311 + #313 hooks.md charter bundle (PR #334), responded to all R2 cycles cleanly. Stream D #43 in-progress at wave close (carry-forward, Aino-tractable). Ontology rebuild commit attribution. Hold at max. |

### Implementers (W8 PR authors)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Mateo Salazar** (user-service Eng) | 3 | **4** (▲) | ★ Scope-pivot resilience: pushed back on initial #287 framing as wave-7 propagation gap (not implementer-class violation), pivoted bundle to alembic-only scope; surfaced wave-7 stranded #305 issue → became main#339 with Wanjiku TPM-class audit owner. Citation-catch on #340 caught Anya's deeper validation gap (parser_fixture_coverage.md self-contradiction) — pre-fixed before merge. Promote 3→4 for first-look-correct discipline + load-bearing wave-process catches. |
| Aino Virtanen (also implementer this wave for #334) | (held above) | (held above) | Counted in Org-Level row. |
| Wanjiku Mwangi (also implementer for #338) | (held above) | (held above) | Counted in Org-Level row. |
| **Lucas Ferreira** (deploy Eng, NEW) | — | **3** (new) | First wave PR — deploy #281 hooks-lint CI workflow. Clean implementation, addressed both R1/R2 cycles cleanly. Default trust 3. |
| **Abdelaziz Idrissi** (deploy Eng) | 3 | 3 | deploy #282 Node 20 actions upgrade. Clean implementation; all reviewer cycles addressed. Hold at 3. |
| **Astrid Lindqvist** (design-system Eng) | 3 | 3 | design-system #75 Node 20 upgrade. Clean delivery. Hold at 3. |
| **Kofi Mensah-Williams** (landing-page Frontend Eng) | 4 | 4 | 3 PRs landed (#89 Astro ADR defer, #90 settings.json align, #91 Node 20). Top-implementer concentration is theme-fit (landing-page wholly in W8 scope per #84-#88 cluster). Hold at 4 — clean delivery, no concentration penalty applied. |
| **Tarek Mansour** (data-acquisition Eng) | 3 | 3 | data-acq #49 Node 20 upgrade. Clean delivery. Hold at 3. |
| **Jean-Claude Habimana** (data-acquisition R2 promoted to implementer) | 4 | 4 | data-acq #44 ADR — 3 in-PR commits responding to citation/anchor corrections from Aino R2; merge-commit pattern (not squash) preserved per ADR convention. Hold at 4. |

### Reviewers / Managers (W8)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Anya Kowalczyk** (isnad-graph TL) | 4 | **5** (▲) | ★ Caught W5 #861 dispatcher-paths deletion that invalidated 4 of 5 in-scope isnad-graph fixture issues (#866-#870) — led close-as-resolved bundle which became `feedback_dispatcher_child_no_local_fixtures.md` memory. Citation catch on #340 (parser_fixture_coverage.md is wave-7 stranded AND doesn't cover block_gh_pr_review AND self-contradicts) — load-bearing for Mateo's pre-fix. Promote 4→5 for two distinct catches that prevented wave drift. |
| **Aisha Idrissi** (deploy R1) | 4 | **5** (▲) | ★ Independently scanned deploy#280 surface and got 37 sites where Bereket's `head`-truncated grep gave 14 — Bereket's pre-spawn brief under-count externally caught. Authored main#341 (Pre-Spawn State Check § extension) charter promotion proposal. Promote 4→5 for catch-and-promote on a manager-class discipline gap. |
| **Maeve Callahan** (design-system R1) | 4 | **5** (▲) | ★ First reviewer to surface that `validate_pr_review` hook counts ONLY `RequestOrReplied: Approved` (not `Reply` even when body says "Approved"). Catch propagated via manager-layer relay (1 catch → 5 manager SendMessages → preempted ~17 addenda across 11 PRs). Codified as `feedback_validate_pr_review_approved_not_reply.md`. Promote 4→5 for hook-semantic catch with multi-PR blast-radius prevention. |
| **Bereket Tadesse** (deploy Manager) | 5 | **4** (▼) | Pre-spawn brief for deploy#280 cited 14 occurrences of an actions/checkout pattern when actual was 37 — `head`-truncated `grep` output sum, not `grep -c` per file. Caught externally by Aisha's independent scan. Single-instance regression in pre-spawn discipline; charter promotion via #341 codifies the rule. Demote 5→4 — held above default until #341 lands and live trace shows the discipline restored. |
| **Marcia Vasquez-Paredes** (landing-page Project Lead) | 4 | 4 | Coordinated Aino on #84 (resolved as wontfix-close after #311+#313 landed); 3 R1/R2 cycles on Kofi's PRs. Hold at 4. |
| **Idris Yusuf** (isnad-graph Eng) | 4 | 4 | PR #872 was anti-pattern (path-walk to parent canonical, contradicts dispatcher-no-local-fixtures memory). Closed gracefully with charter-format comment + memory cite. Hold at 4 — corrective behavior intact even when initial framing was wrong. |
| **Dilara Erdogan** (data-acquisition R1) | 4 | 4 | R2 of data-acq #44 ADR + R2 of #49 + manager-merge of #49 (gh pr merge --squash --delete-branch + #46 close at 02:01:09Z). Clean follow-through. Hold at 4. |
| **Nadia Boukhari** (user-service Manager, NEW) | — | **4** (new) | First wave appearance — manager-merge of main#340 (us#98+#99 bundle) + cross-repo close-out (us#98 + us#99 closed at 02:01:48-50Z). Followed full sequence per child-repo-implementer rule extension. Default-above-3 (4) for clean first-wave manager-class delivery without R1/R2 catch. |

### Orchestrator (Self-Assessment)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Orchestrator (Steven via Claude)** | 4 | **3** (▼) | Spawn-brief instruction template said "RequestOrReplied: Reply" for approval comments — wrong; hook counts only `Approved`. Cascade required ~17 addenda across 11 PRs (Maeve catch → manager-layer relay → wave-wide guidance comment + Step 4 manager pre-merge check). Demote 4→3 — first-call instruction error that scaled to wave-wide cleanup cost. Positive offsets: (a) scope-drop reconciliation handled cleanly (ingest-platform descope, isnad-graph + user-service no-merge-needed both recorded with rationale), (b) 5 wave-merge PRs landed cleanly with full charter-discipline (2-reviewer Approved + non-fast-forward merge for diverged main case + status commits via PUT-contents), (c) divergent main case (3 PRs ahead + 3 status commits behind) handled with merge-into-wave first then PR — no rebase, no force-push, no orphans. Hold at 3 until next wave shows the spawn-brief template fix is internalized. |

### Done Well / Needs Improvement (Phase 3 Wave 8)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Mateo Salazar** | Scope-pivot resilience (#287→#98 only); load-bearing wave-7 propagation catch (#339); citation-pre-fix on #340 | None this wave |
| **Anya Kowalczyk** | W5-deletion invalidation catch (4 of 5 fixture issues); citation-catch on #340; close-as-resolved bundle execution | None this wave |
| **Aisha Idrissi** | Bereket pre-spawn under-count catch via independent scan; #341 authorship | None this wave |
| **Maeve Callahan** | Approved-vs-Reply hook-semantic catch with manager-layer cascade prevention | None this wave |
| **Bereket Tadesse** | None notable this wave (single-instance regression in spotlight) | `head`-truncation in pre-spawn enumeration sum (#341 codification) |
| **Wanjiku Mwangi** | #309 audit owner; Approved-vs-Reply wave-wide guidance + Step 4 manager pre-merge check | None this wave |
| **Aino Virtanen** | #311+#313 charter bundle authoring; Stream D in-progress at close | None this wave |
| **Nadia Khoury** | 3 charter proposals filed (#337/#341/W9); state,mergedAt R-discriminator templating | None this wave |
| **Lucas / Abdelaziz / Astrid / Tarek** | Routine clean implementer deliveries | None this wave |
| **Kofi Mensah-Williams** | 3 PRs in same wave with theme-fit concentration; clean R1/R2 cycles | None this wave |
| **Jean-Claude Habimana** | ADR with iterative anchor correction; merge-commit pattern preserved | None this wave |
| **Idris Yusuf** | Graceful close of anti-pattern PR #872 with memory-cite | None this wave (anti-pattern itself was caught early) |
| **Dilara / Marcia / Nadia Boukhari** | Clean manager-merge follow-throughs (squash-to-wave + cross-repo close-out) | None this wave |
| **Orchestrator** | Scope-drop reconciliation, 5 wave-merge PRs landed cleanly, divergent-main handled with merge-not-rebase, /promotion-audit + /wave-scope auto-invoke handoffs honored | (a) Spawn-brief Reply-vs-Approved instruction error → ~17 addenda cascade. (b) Step 14 memory audit had to be filed as #346 deferred-to-W9 instead of executed in-band — annunaki + memory audit don't fit a single wave-wrapup session (proposed #344 to add to /wave-retro). (c) Implementer-substitution reconciliation skipped (skill § P3W5 retro requirement) — deferred to per-engineer assessment above; wave-wrapup skill should auto-emit substitution table. |

## Phase 3 Wave 9 Trust Updates (2026-05-12) — Tech-Debt Reduction (Main-Only)

### Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Aino Virtanen** (SQL) | 5 | 5 | (hold at max) 4 PRs (#409, #410, #411, #415) covering charter + skills + post_dispatcher + ontology surfaces, 0 ChangesRequested cycles, parser-side test coverage on every artifact. PR #410 was a substantial 5-hook migration with 20 new tests across 5 test classes. Theme-fit concentration (67% of wave PRs by commit identity) — defensible: charter codification + skill cleanup are her territory. Continued max trust. |
| **Nadia Khoury** (PD) | 5 | 5 | (hold at max) Authored PR #412 (retro PR body-vs-diff discipline rule, closing #126) cleanly; served as primary reviewer on 4 of the 6 W9 PRs (#411, #412, #415, #416) with consistent verdict-shape. Marker convention compliance (used Shape 1 HTML-comment per PR #409's just-landed convention). Caught the wrapup-counter-completeness gap on #416. |
| **Wanjiku Mwangi** (TPM) | 4 | **5** (▲) | promotion — clean PR #413 (cross-repo dispatch contracts ontology) + sibling-issue filing discipline (filed #414 pre-verdict per charter rule when finding /wave-wrapup mirror gap; filed deploy#285 as audit by-product with proper A-vs-B framing). 2 thorough reviews (#410, #412). Recovers from W8 5→4 demotion (head-truncation in pre-spawn enumeration) — that lesson is now codified in charter (#341) and the discipline restored in W9 with the parser-side literal-string verification she ran on her own work. |
| **Santiago Ferreira** (RC) | 5 | 5 | (hold at max) 4 Approveds posted across #410, #411, #413, #415, #416 with consistent procedural verdict-shape (runtime/procedural angle). Caught the CI path-filter "no checks reported" nuance on #413 (verified the filter is legitimate vs. just rejecting). Flagged `current_wave` not advancing during /wave-wrapup on #416 — useful retro-input. |

### Orchestrator (Self-Assessment)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Orchestrator (Steven via Claude)** | 3 | **3** (hold) | Two new spawn-brief template defects this wave: (a) prescribed `## TechDebt` section header + prose instead of literal `TechDebt: ` line — both #409 reviewers (Nadia, Wanjiku) followed the template faithfully and both verdicts were rejected at merge time, required 2 PATCH amendments to unblock; codified as `feedback_techdebt_attestation_literal_line.md`. (b) Spawned `aino2`, `wanjiku3`, `nadia2` clone agents instead of `SendMessage`-ing the idle existing personas — user-flagged; codified as `feedback_reuse_idle_teammates_not_clones.md`. Sibling-of-W8's Approved-vs-Reply template defect — same class: spawn-brief template prescribes verdict shape via prose, hook expects literal token. Positive offsets: (c) bulk relabel of 115 issues across 7 repos with read-back verification + 11 new wave labels created mechanically; (d) wave-9 → main merge handled with merge-not-rebase + 2-reviewer gate + literal TechDebt: line discipline (no addenda cascade); (e) /promotion-audit retro-side run surfaced 3 real defects in the audit itself (#417/#418/#419 filed for W10) — caller-side error became evidence-gathering for skill cleanup. **Hold at 3** until W10 shows the spawn-brief template (literal verdict-comment shape) + reuse-idle-teammates discipline are internalized. Demote to 2 only if the same template-shape class recurs in W10. |

### Done Well / Needs Improvement (Phase 3 Wave 9)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Aino Virtanen** | 4 clean PRs covering charter/skills/post_dispatcher/ontology; 20 new tests in #410 dispatcher work; PR #411 prose-vs-helper decision correctly cited § Determinism contract; PR #415 mirror with appropriate severity bump for wrapup context | None this wave (theme-fit 67% concentration noted for forward-planning, not penalized) |
| **Nadia Khoury** | PR #412 (retro PR body-vs-diff rule) ratified discipline that immediately self-applied to this very retro PR; 4 reviewer verdicts with consistent altitude; flagged wrapup-counter-completeness on #416 | None this wave |
| **Wanjiku Mwangi** | PR #413 cross-repo dispatch contracts with parser-side literal-string verification; #414 sibling-filing discipline; deploy#285 A-vs-B framing for owner decision; 2 thorough reviews | None this wave (W8 head-truncation lesson now codified + restored) |
| **Santiago Ferreira** | 4 procedurally consistent Approveds; CI path-filter nuance catch on #413; current_wave-not-advancing observation on #416 | None this wave |
| **Orchestrator** | Bulk relabel mechanical execution (115 issues + 11 new labels); wave-9 → main merge with no addenda cascade; /promotion-audit retro-side run surfaced 3 real skill defects → #417/#418/#419 (caller-side error became evidence) | (a) Spawn-brief TechDebt-line shape defect → 2 PATCH amendments. (b) Clone-spawning vs. SendMessage idle existing — user-flagged. Both codified as memories; charter promotion proposed for next wave. |

## Phase 3 Wave 10 Trust Updates (2026-05-16) — Tech-Debt Reduction (Non-Deploy Remainder) + Convergent Wave-Shape Thesis

### Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Aino Virtanen** (SQL) | 5 | 5 | (hold at max) 4 main# PRs (#434, #437, #438, #439) all charter/skills/hooks/board surfaces — theme-fit again, sibling-discovery pattern on #439 (board-audit drift-vs-no-op split) catalysed one of two DECIDE-tier charter promotions this wave. 0 ChangesRequested cycles. Trust signal continuity: same defensible concentration shape as W9 (charter codification + skill cleanup are her territory). |
| **Nadia Khoury** (PD) | 5 | 5 | (hold at max) Authored #440 (lifecycle.md) with over-delivery — parenthetical clarifications on every `/plan-phase` reference (flagged by Aino for trust matrix). Reviewer-class catch on `/phase-review` SKILL.md → `/roadmap` non-existent reference, folded inline per owner option C; drove crossed-message-race recovery resolved per `feedback_verdict_amendment_edit_not_append` (no edit-append). 4 reviewer verdicts. |
| **Wanjiku Mwangi** (TPM) | 5 | 5 | (hold at max — recovers from W9 4→5 promotion) PR #428 cross-window PR over-count fix for /wave-wrapup landed in W10 and the filter was live-verified THIS retro (recompute-vs-wrapup drift = 0 for the first time across W4/W5/W9 history). **Wanjiku is the catalyst for both DECIDE-tier charter promotions this wave**: framed #1 (`Process-Doc Authorship: Derived-From-SKILL.md-At-HEAD`) from #440 review, co-named #2 (`Acceptance-Criteria-Bucketing-In-Reports`) with Santiago from #439 review. Charter-promotion catalyst behavior is a Pattern G evolution (in-wave skill self-improvement now extends to in-wave charter-class proposal). |
| **Santiago Ferreira** (RC) | 5 | 5 | (hold at max) 4+ Approveds posted across W10 reviewer slate with consistent procedural verdict-shape (runtime/procedural angle). Co-named with Wanjiku the actionable-vs-informational bucketing pattern → DECIDE-tier #2. Filed minor cosmetic nit on /board-audit Step 5 column alignment (deferred per owner choice). |

### Cross-Repo Implementer Promotions

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Lucas Ferreira** (SRE) | 4 | **5** (▲) | PR #431 (`auto-close-issues workflow`) + 4 cross-repo propagation siblings. **Operationally retires `feedback_wave_branch_issue_close.md` failure mode** — 8-9s propagation on every W10 merge, fully reliable across all 7 repos. The propagation discipline (one parent PR + 4 mechanically-derived siblings) is the cleanest cross-repo fan-out shipped this phase. |
| **Aisha Idrissi** (Infra implementer) | 4 | **5** (▲) | 3 main# PRs (#430, #432, #435) wide cross-repo infrastructure work. #432 took 1 ChangesRequested cycle from security review and addressed it inline (commit a9504db: enforce_admins=true, 2-reviewer gate, Environment apply-gating) rather than via followup — security-guard-inline-not-followup discipline (per `feedback_security_guard_inline_not_followup.md`). Clean recovery + branch protection now active across 8 repos. |

### Orchestrator (Self-Assessment)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Orchestrator (Steven via Claude)** | 3 | **4** (▲) | **Conditional promotion from W9 retro met.** W9 retro stated: "Hold at 3 until W10 shows the spawn-brief template (literal verdict-comment shape) + reuse-idle-teammates discipline are internalized. Demote to 2 only if the same template-shape class recurs in W10." Both held: (a) zero TechDebt-line addenda cascades this wave (vs W9's defect that produced 2 PATCH amendments); (b) zero clone-spawning this wave — `SendMessage` to idle existing personas throughout. Additional positives: (c) crossed-message-race on #440 resolved correctly via NEW Approved comments at new HEAD (no edit-append) per `feedback_verdict_amendment_edit_not_append`; (d) /promotion-audit live verification with byte-deterministic 0/0/146/20 (no caller-side errors this run); (e) 7 throttle-takeovers under `parametrization` identity with explicit `wave_10_decisions.orchestrator_takeover_acknowledgment` so trust-matrix attribution stays accurate. Minor pain: 22 implementer-substitutions for child-repo PRs is a noise pattern that surfaces a charter-clarification candidate (§ Proposed Process Changes #4). |

### Done Well / Needs Improvement (Phase 3 Wave 10)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Aino Virtanen** | 4 main# PRs across charter/skills/hooks/board surfaces; #439 board-audit drift-vs-no-op split catalysed DECIDE-tier charter promotion #2; theme-fit concentration noted as forward-planning signal | None this wave |
| **Nadia Khoury** | #440 lifecycle.md with over-delivery (parenthetical clarifications); reviewer-class catch on /roadmap reference; crossed-message-race recovery per protocol | None this wave |
| **Wanjiku Mwangi** | PR #428 cross-window filter live-verified at this retro (W9-defect-fix held under W10 load); catalyst for both W10 DECIDE-tier charter promotions; sustained TPM voice across review slate | None this wave |
| **Santiago Ferreira** | Co-named bucketing pattern with Wanjiku → DECIDE-tier #2; procedurally consistent verdict-shape; cosmetic-nit-deferral discipline | None this wave |
| **Lucas Ferreira** | Auto-close-issues workflow operationally retires a long-standing failure mode; cross-repo propagation discipline | None this wave |
| **Aisha Idrissi** | Security-guard-inline-not-followup on #432; clean 3-PR infrastructure execution; branch protection now active across 8 repos | None this wave |
| **Orchestrator** | W9 process-defect fixes held under W10 load (zero recurrence); crossed-message-race recovered cleanly; /promotion-audit byte-deterministic with no caller-side errors; throttle-takeover acknowledgment in cross-repo-status | 22 implementer-substitutions for child-repo PRs surfaces a kickoff-time-declaration-vs-runtime-truth gap → charter clarification candidate #4 (advisory only, not corrective) |

## Phase 3 Wave 11 Trust Updates (2026-05-24) — Tech Debt & Deployment (close-out)

> Scope note: W11 ran 86 PRs across ~6 repos, mostly in prior sessions; the wrapup recorded aggregate metrics (verified at this retro: PR count 86=86 ✓, top-concentration 15%=15% ✓). The assessments below weight the **directly-observed close-out** (deploy#348 saga, the #523/#524 coordination PRs) where signal is strongest, plus wave-wide PR distribution.

### Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Aino Virtanen** (SQL) | 5 | 5 | (hold at max) Ontology/checksum resolutions on #523/#524; standards continuity. No negative signal. |
| **Nadia Khoury** (PD) | 5 | 5 | (hold at max) PD ran the full close-out: main-divergence reconcile (#523), deploy#348 sequencing, post-unblock scrub (#524). Coordination clean. |
| **Wanjiku Mwangi** (TPM) | 5 | 5 | (hold at max) 10 wave PRs; TPM reviews on #523/#524 cross-checked at origin with all counters reconciled. |
| **Santiago Ferreira** (RC) | 5 | 5 | (hold at max) Release reviews on #523/#524; correctly affirmed gate-clearing ≠ wave-close encoding. |

### Cross-Repo Implementer Updates

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Aisha Idrissi** (deploy SRE) | 5 | 5 | (hold at max — would be ▲ if not capped) **Exemplary deploy#348 close-out under a multi-cycle prod-gated failure.** Investigated at HEAD, surfaced + resolved the design fork (the *discovery-in-both-plan-and-apply-jobs* insight made the gated plan work), recovered cleanly from the apply-time expression failure (#349→#350), held honest "not claimed done" discipline, used REST-PATCH recovery on the `gh pr edit` no-op. Highest-signal implementer this session. |
| **Lucas Ferreira** (SRE) | 5 | 5 | (hold at max) Wave-wide top implementer (13/86 PRs, deploy-themed). Theme-fit volume leadership; no negative signal. |
| **Nino Kavtaradze** (Sec Eng) | 4 | **5** (▲) | Substantive (not rubber-stamp) security reviews on #349/#350: token-confinement analysis of the CI discovery step (token stays in `Authorization` header, only non-secret ruleset IDs reach `$GITHUB_ENV`) + open-redirect analysis (`http.request.uri` carries no host/authority → destination host pinned). 8 wave PRs. |
| **Weronika Zielinska** (Platform/IaC) | 3 | **4** (▲) | Sharp IaC reviews on #349/#350 — verified the plan herself (`0 destroy`, v4 import-ID format, idempotency reasoning, discovery-step robustness) rather than trusting the green check. 8 wave PRs. Consistent upward trajectory from her R2 debut. |

### Orchestrator (Self-Assessment)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Orchestrator (Steven via Claude)** | 4 | 4 | (hold) Strong close-out: caught a destructive `2-to-destroy` plan by reading the actual plan (not the green check); caught + recovered the apply-time expression bug; honest close-on-verified-live (reopened #348 when the premature auto-close surfaced); verify-merged-then-remove worktree cleanup (33 cleaned, 0 stranded); clean reconcile of a 2-ahead/35-behind diverged main. **Hold-not-promote** because the #349 spawn brief instructed `Closes #348` on a runtime-gated issue (the premature-close) — self-caught and corrected same-session, and codified as charter change #1, but it was an orchestrator-authored miss. |

### Done Well / Needs Improvement (Phase 3 Wave 11)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Aisha Idrissi** | deploy#348 import-adopt design + the both-jobs discovery insight; clean apply-failure recovery; honest runtime-acceptance discipline | None this wave |
| **Nino Kavtaradze** | Substantive security analyses (token confinement, open-redirect host-pinning) on the redirect PRs | None this wave |
| **Weronika Zielinska** | Self-verified plans (0-destroy, import format, idempotency) instead of trusting green checks | None this wave |
| **Lucas / Wanjiku / Santiago / Aino / Nadia** | Sustained delivery + review rigor; counters reconciled at retro | None this wave |
| **Orchestrator** | Read-the-actual-plan + apply-gate discipline caught two would-be-bad deploys; verify-merged worktree cleanup; charter codification of the lessons | `Closes #N` on a runtime-gated issue (#348) — self-caught + codified, but authored the miss |

## Phase 3 Wave 12 Trust Updates (2026-05-30) — Tech-debt sweep + cross-cutting security/CI

> Scope note: W12 ran 15 PRs across 2 declared repos (main 4, deploy 11) plus 5 cross-cutting direct-to-main PRs in the wave window (isnad-graph #933 starlette, #930 node24, deploy #369/#370 vhost carve-out, main #538 hook fix). **Zero ChangesRequested cycles across all 15 wave PRs** — cleanest CR count in P3 history. Top-implementer concentration 4/15 = 27% (Lucas + Weronika tied) — healthy 7-implementer distribution.

### Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Aino Virtanen** (SQL) | 5 | 5 | (hold at max) Exemplary execution on #538 (auto_set_env_test newline-separator fix) — 69/69 tests pass, 4 new regression cases (newline, line-continuation, quoted-newline, allow-baseline), 3 docstring contract-sync touches kept policy contract in lockstep with code. Plus #531/#532 cwd-anchor work earlier in wave. Identity verified per `feedback_brief_author_verify_roster_surname` (avoided the slug-vs-roster-name pitfall). |
| **Nadia Khoury** (PD) | 5 | 5 | (hold at max) Retro authorship + wave-merge coordination; no negative signal. |
| **Wanjiku Mwangi** (TPM) | 5 | 5 | (hold at max) #534 (cwd-anchor pass) earlier in wave; reviewer on #538 with W11 #478 cross-reference regression spot-check. |
| **Santiago Ferreira** (RC) | 5 | 5 | (hold at max) 5-case gate-continuity probe on #538 directly verified the #476 silent-bypass class is NOT re-introduced; identity used for deploy wave-12 ← main merge-prep commit (RC role per CLAUDE.md "manages deployment sequencing"). |

### Cross-Repo Implementer Updates

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Lucas Ferreira** (deploy SRE) | 5 | 5 | (hold at max — would be ▲ if not capped) **Outstanding HEAD audit on deploy#245** caught stale-meta-issue text (frontend already done via isnad-graph 1a6f2ae) and reduced 5-PR sweep to 2-PR W12 scope before any destructive Edit/Write. Cookie-domain decision well-reasoned (host-scoped, no widening). **Clean architectural-blocker escalation on PR-B1** (single-image-promotion vs build-time-env conflict) — escalated to owner without speculative work, sibling #932 filed for W13, step-5 deferred with explicit pre-conditions. Tied top-implementer (4 wave PRs: #354, #356, #359, #365). |
| **Weronika Zielinska** (Platform/IaC) | 4 | **5** (▲) | Tied top-implementer with Lucas (4 wave PRs: #353 tf-fail-fast-validation, #357 ADR 0005 state-locking, #360 ADR 0004 Part-2 backblaze-bootstrap, #362 env-restructure design proposal). Architect-class review on #369 surfaced cross-PR sequencing observation (CSP `connect-src` is browser-side; A+B2 must ship together — directly informed merge-order) and verified users.* CSP/CORP symmetry from her own prior #243 work. Consistent upward trajectory: R2 debut → 3 (W10) → 4 (W11) → **5 (W12)**. |
| **Nino Kavtaradze** (Sec Eng) | 5 | 5 | (hold at max) Tier-1-security headliner #351 (per-env per-role SSH key split, supersedes ADR 0003). Substantive security review on #370 with explicit threat-model summary + caught a doc-quality nit (compose v2 DOES interpolate `.env`; the dead-line reason was actually that compose YAML used a literal not `${CORS_ORIGINS}`). Apex-domain no-consumer hardening observation surfaced. |
| **Aisha Idrissi** (deploy SRE) | 5 | 5 | (hold at max) #355 (cloud-init parity gaps); dual reviewer on #369+#370 (both Approved). |

### Isnad-Graph Wave-Window Engagement (informational)

W12 included cross-cutting isnad-graph work routed direct-to-main (#933 starlette security, #930 node24 CI). Isnad-graph roster engagement noted here (no org-level trust matrix updates for child-repo participants per `feedback_child_repo_implementer_rule`; trust updates for these engineers belong in isnad-graph's own retro if/when one runs).

| Member | Engagement | Direction |
|---|---|---|
| **Anya Kowalczyk** (isnad-graph TL) | Reviewer on #933 + #930 — independently verified starlette import audit via `gh search code`; flagged state-mismatch on #930 update-branch async-window (became new memory `feedback_update_branch_async_window.md`) | positive |
| **Ingrid Lindqvist** (isnad-graph Eng) | Reviewer on #933 + #930 — #924-lens repeat performance: dep-resolution verified at PyPI origin, CI workflow end-to-end, all 6 SHA-pins verified at canonical upstream repos, dispatch contract byte-for-byte at both ends | positive |
| **Idris Yusuf** (isnad-graph Sec) | #931 audit work was sound (starlette imports enumerated, ABI-stability per file, fastapi compat verified). 9-hour throttle stall mid-task required orchestrator throttle-takeover per `feedback_throttle_takeover`. No engineering-class negative — stall is process/infra signal. | neutral (audit positive; stall not held against) |
| **Linh Pham** (isnad-graph DevOps) | #930 author — well-prepared PR (SHA-pinning policy preservation correct, gitleaks carve-out aligned with #929); sat 2 days for #931 unblock (not Linh's fault) | positive |
| **Nurul Hakim** (deploy Observability) | #358 dedicated egress network — clean delivery, in wave-12 scope per `compose:` themed work | positive |

### Orchestrator (Self-Assessment)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Orchestrator (Steven via Claude)** | 4 | 4 | (hold) Strong wave-window execution: HEAD-audit pattern caught stale meta-issue text on **both #536 and #245** (saved 5 implementer spawns on #536 + reduced #245 from 5-PR to 2-PR scope); clean throttle-takeover on Idris #931 stall (committed with implementer's identity, audit attribution preserved); architectural-blocker escalation discipline on PR-B1 (owner-decision-tier, not speculatively-resolved); wave-merge ceremony with correct identity attribution (Santiago for RC merge-prep) and reachability gate (ahead 0, behind 1 post-merge). Memory `feedback_update_branch_async_window.md` saved live during the wave. **Hold-not-promote** because: the deploy node24 PR re-target via `gh pr edit` was silent no-op'd on first try (memory hit recognized, REST PATCH recovered) — pattern was a memory-hit not a fresh catch, but it does mean the orchestrator authored the initial wrong-tool choice. Also: the wave-12 scope file W12 canonical-counter-key writes were deferred to retro (per skill design) but the orchestrator could have explicitly written them at wrapup — would have been one fewer retro task. Minor; not promotion-blocking. |

### Done Well / Needs Improvement (Phase 3 Wave 12)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Aino Virtanen** | #538 hook fix execution + 4 fresh regression test cases (newline, line-continuation, quoted-newline, allow-baseline); docstring contract-sync across 3 sites | None this wave |
| **Lucas Ferreira** | deploy#245 HEAD audit (scope-reduction catch); architectural-blocker escalation discipline on PR-B1; clean sibling-issue filing for W13 step-5 | None this wave |
| **Weronika Zielinska** | Tied top-implementer (4 wave PRs across security/IaC/docs); architect review on #369 surfaced cross-PR sequencing | None this wave |
| **Nino Kavtaradze** | Tier-1 #351 SSH key split (supersedes ADR 0003); doc-quality nit catch on #370 (compose v2 .env interpolation correction) | None this wave |
| **Wanjiku / Santiago / Aino / Nadia** | Sustained review/coordination rigor; 5-case gate-continuity probe (Santiago); W11 #478 regression spot-check (Wanjiku); identity-discipline (Aino) | None this wave |
| **Orchestrator** | HEAD-audit pattern caught 2 stale meta-issue traps (#536, #245); throttle-takeover with identity-preservation; architectural-blocker escalation accepted not papered-over; wave-merge with correct RC identity for sequencing | `gh pr edit` silent no-op on first base-retarget try (memory-hit recovery, but authored the wrong-tool choice initially) |

## Phase 3 Wave 13 Trust Updates (2026-05-31) — Phase-3 End-State Close-out + Cross-Repo Schema Rationalization

> Scope note: W13 was the **largest wave in P3 history** — **37 PRs across 5 declared repos** (main 10, deploy 13, user-service 3, isnad-ingest-platform 8, isnad-graph 3), **18 distinct implementers**. **One ChangesRequested cycle across all 37 PRs** (us#137, Idris→Mateo — a load-bearing security catch, not a quality miss). Top-implementer concentration **7/37 = 19%** (Aino, all governance/charter/end-state work — theme-fit, well under the 60% fragility threshold). The wave's defining arc: an honest Tier-5 audit surfaced **four unmet P3 end-state criteria** (#322/#326/#327/#328) that the owner pulled into W13 rather than false-closing; #328 delivered (Closes), the other three delivered as parent-canonical with per-repo rollout carried to W14 (`Refs`).

### Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Aino Virtanen** (SQL) | 5 | 5 | (hold at max) Wave headliner: 7 clean PRs, all governance/standards. Authored the canonical **`artifact-ownership.md`** (#328/#559, the one end-state criterion fully closed), three charter triggers (#548 throttle-stall thresholds, #549 meta-issue freshness re-audit, #550 6-class segment-parser test coverage), the wave-wrapup **staging-promotion gate** (#551/#325), session-start REPO_ROOT anchor + no_worktree self-delete recovery (#553/#554), the **pre-push ⇄ CI sync-drift gate** (#562/#327), and the docs-CI lint gate (#563/#326). The ethical spine of the wave — her Tier-5 audit **refused to false-close** the 4 end-state criteria, which is exactly the honest-audit discipline the charter prizes. |
| **Nadia Khoury** (PD) | 5 | 5 | (hold at max) Wave kickoff → scope → wrapup orchestration across 5 repos; owner-decision escalation routing (deploy#329/#100, #35 per-field ruling, end-state gaps) without speculative work; meta-issue #541 lifecycle; wave-merge ceremony with reachability gate (0 stranded). |
| **Wanjiku Mwangi** (TPM) | 5 | 5 | (hold at max) Authored **#561** — the canonical branch-protection ruleset spec + hook-validated admin-merge exception class system (the security backbone of the end-state push) — and **#549** meta-issue freshness trigger. Cross-dependency tracking across the 5-repo fan-out. |
| **Santiago Ferreira** (RC) | 5 | 5 | (hold at max) **#563** docs/markdown + config lint gate (parent-canonical #326 pattern); RC role on the 5-repo wave→main merge sequencing. |

### Cross-Repo Implementer Updates (deploy track)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Lucas Ferreira** (deploy SRE) | 5 | 5 | (hold at max — would be ▲ if not capped) Top deploy implementer with 3 clean architectural PRs: **#385** bitnami→`apache/kafka:3.9.2` KRaft broker migration (owner-decided image, full `KAFKA_CFG_*`→apache env reconciliation), **#383** the Option-B fast stg-smoke battery wired as a `verify-stg` fast-fail gate (mirrors the prod battery, <5min budget), **#389** the users.{base} Caddy carve-out completing the isnad.* dual-bind drop. HEAD-audit-before-Edit discipline sustained. |
| **Nino Kavtaradze** (Sec Eng) | 5 | 5 | (hold at max) 4 security-heavy deploy PRs: **#381** secrets inventory + rotation policy, **#378** state-resident secret-rotation runbook (Phase 3 of #172), **#377** root-key exclusion from root→deploy merge, **#373** master-B2-key removal from CI (read-only plan key + workstation apply). Highest deploy PR count this wave. |
| **Weronika Zielinska** (Platform/IaC) | 5 | 5 | (hold at max) 3 PRs: **#380** isnad-graph→isnad hostname cutover straggler sweep, **#376** pre-staged IAM role binding doc + OAuth-SPOF de-framing, **#374** Cloudflare token-scope preflight + .net/.org ruleset auth docs. |
| **Aisha Idrissi** (deploy SRE) | 5 | 5 | (hold at max) **#382** RUN_MODE=remote non-health integration coverage expansion. |
| **Bereket Tadesse** (deploy Manager) | 4 | 4 | (hold) **#372** decommission of the hand-made isnad-graph-prod VPS — clean delivery. Demotion from W11 (#280 head-truncation pre-spawn miss) stands until a fresh **brief-author** demonstration shows the enumeration discipline restored; this wave he worked implementer-class, so the restoring signal didn't arise. No negative this wave. |
| **Nurul Hakim** (deploy Observability) | 4 | 4 | (hold) **#375** reachable + working Grafana login for metrics access — clean delivery, consistent with W12 #358 positive. |

### Child-Repo Wave Engagement (informational — per `feedback_child_repo_implementer_rule`)

> Trust numbers for child-repo rosters belong in those repos' own retros. Noted here for visibility; engagement was uniformly strong.

| Member | Repo | Engagement | Direction |
|---|---|---|---|
| **Idris Yusuf** | user-service / isnad-graph (Sec) | ★ **Standout security catch** on us#137 — the single CR of the wave. Audited the Caddy `users.{base}` vhost at HEAD and proved the new `/metrics` endpoint would fall through the catch-all and be **publicly reachable**, contradicting the PR's "not public" claim. Correct security-guard-inline shape: required claim-correction + a hard deploy-side 403 dependency (#386) before prod-enable, without holding the sound user-service code hostage. Also authored us#138 (Dockerfile digest-pin + trivy allowlist). | strongly positive |
| **Mateo Salazar** | user-service (Eng) | 2 PRs (#137 /metrics exposure, #136 mypy type-ignore cleanup). Received the wave's only CR and **responded correctly** — corrected the public-exposure claim and filed the deploy-side dependency rather than arguing. First-look-correct discipline holds. | positive |
| **Tomás Carvalho** | isnad-ingest-platform (Eng) | 2 PRs: #56 Kafka-driven worker E2E + MinIO→dedup object-store flow (impl of main#136 pipeline scenarios), #52 testcontainers neo4j integration coverage. | positive |
| **Imelda Santos** | isnad-ingest-platform (Eng) | 2 PRs: #54 per-appearance Hadith-field rationalization (the #35 ruling impl), #49 fail-loud on edge MERGE with missing endpoint. | positive |
| **Yusuke Inoue** | isnad-ingest-platform (Eng) | 2 PRs: #53 narrowed `_build_reset_clients` return type, #50 worker_checkpoint TTL sweep. | positive |
| **Léopold Mbongo** | isnad-ingest-platform (Eng) | 2 PRs: #51 phantom-#192-reference removal, #48 send-before-mark fix in WorkerRunner.handle_one. | positive |
| **Farhan Malik** | isnad-graph (DE Lead) | Co-drafted the #35 per-field ruling (data-lead), then authored #935 promoting the 4 ratified ingest fields to Phase-4 Pydantic models. | positive |
| **Aisling Brennan** | isnad-graph (Eng) | #936 ingest-extras schema reconcile — authored under isnad-graph roster identity (per-repo commit-identity rule; the ingest-roster author could not author isnad-graph commits). | positive |
| **Ingrid Lindqvist** | isnad-graph (Eng) | #934 runtime-config.js for env-specific origins. Repeat dep-resolution-at-origin rigor noted in prior waves. | positive |

### Orchestrator (Self-Assessment)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Orchestrator (Steven via Claude)** | 4 | 4 | (hold) Strong: drove 37 PRs through impl→2-reviewer→merge across 5 repos with 18 implementers and only 1 CR; **honest Tier-5 audit surfaced 4 unmet end-state criteria and escalated rather than false-closing** (the wave's best decision); clean owner-decision routing on every fork (deploy#329 Option-B, #100 apache/kafka, #35 per-field ruling, end-state pull-in) without speculative pre-work; correct per-repo commit-identity handling on the isnad-graph #936 cross-roster case. **Hold-not-promote** because of three self-authored process slips: (1) **Closes-vs-Refs flip-flop on #561** — gave conflicting "Closes stands" then "change to Refs" signals that cost Wanjiku multiple round-trips; (2) **stale-local-checkout during high-volume remote merges** — merged 37 PRs via gh while local parent was 22 commits behind, so the ontology counter-commit landed on a stale tree and needed a `reset --hard` recovery (which discarded session annunaki entries); (3) the **batch-loop merge** on the ingest cluster fail-opened Hook 4 (known memory, recurred). Each is a recognized-pattern slip, not a fresh-catch — exactly the self-authored-error class that blocks promotion. |

### Done Well / Needs Improvement (Phase 3 Wave 13)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Aino Virtanen** | 7 clean governance PRs; authored artifact-ownership.md + pre-push sync-gate + 3 charter triggers; Tier-5 honest-audit refusal to false-close 4 end-state criteria | None this wave |
| **Wanjiku Mwangi** | #561 branch-protection canonical spec + admin-merge exception classes (security backbone); #549 meta-issue freshness trigger | None this wave (the #561 Closes/Refs churn was orchestrator-authored, not hers) |
| **Lucas Ferreira** | apache/kafka migration + stg-smoke battery + Caddy carve-out, all clean; sustained HEAD-audit discipline | None this wave |
| **Nino Kavtaradze** | 4-PR security sweep (secrets inventory/rotation/key-removal) — highest deploy throughput | None this wave |
| **Idris Yusuf** | ★ /metrics public-exposure catch (the wave's load-bearing security review); correct security-guard-inline shape | None this wave |
| **Mateo Salazar** | Responded to the wave's only CR correctly — claim-correction + dependency-filing, no argument | None this wave |
| **ingest-platform + isnad-graph rosters** | 13 clean child-repo PRs (E2E/testcontainers/#35-ruling/Phase-4 models), zero CRs | None this wave |
| **Orchestrator** | Honest Tier-5 audit + escalation discipline; 37-PR/5-repo drive at 1 CR; cross-roster identity correctness on #936 | #561 Closes/Refs flip-flop (conflicting signals → round-trips); stale-local-checkout during high-volume merge; batch-loop Hook-4 fail-open recurrence |

## Phase 3 Wave 14 Trust Updates (2026-06-01) — Phase-3 End-State Rollout + Hook Hardening + Verify-and-Close

Final wave of Phase 3. 15 PRs / 8 repos / 0 changes-requested cycles. Directional summary: clean delivery across the board; the standout is Ingrid's investigate-first GHCR fix. Org-level + deploy-track hold at their established levels; no decreases warranted among implementers.

### Done Well / Needs Improvement (Phase 3 Wave 14)

| Engineer | Done Well | Needs Improvement |
|---|---|---|
| **Aino Virtanen** | 5 clean PRs — 4 Tier-3 hook fixes + the sync-gate build-kind/multi-line fix (+10 regression tests); also reviewed #579 | None this wave |
| **Ingrid Lindqvist** | ★ #941 GHCR registry migration — model investigate-first (confirmed package published + proved cross-repo auth via already-green ci.yml before coding), BuildKit-secret token handling never in a layer | None this wave |
| **Anya Kowalczyk** | user-service rollout #141/#142 + canonical alignment; thorough security-lens reviews on #938 + #941 (runtime-image-excludes-token verification) | None this wave |
| **Linh Pham** | isnad-graph rollout #938 (byte-aligned the build-pattern fix); rigorous #941 workflow/security review as ghcr-publish owner | None this wave |
| **Santiago Ferreira** | #579 actionlint pin with independent upstream sha256 verification; reviewed #580 | None this wave |
| **Aisha Idrissi** | deploy rollout #391 + authored the canonical build-kind tightening later lifted into #576/#580 | None this wave |
| **Astrid Lindqvist / Kwame Mensah-Williams / Tarek Mansour / Farhan Bensalah** | one clean end-state rollout PR each (design-system #90 / landing #104 / data-acq #60 / ingest #58), 0 CRs | None this wave |
| **Orchestrator** | Verify-and-close discipline (avoided rebuilding already-live #323/#324/#329); investigate-first root-caused staging red to #940; honest staging-gate override with deploy#393 filed; surfaced the #322 delivered-vs-applied gap rather than false-closing | commit 5804476 GHCR red went 12 days undetected (no red-default-branch alerting); `current_wave` pointer left stale at kickoff (retro blocked); ADMIN_MERGE_EXCEPTION literal-format friction cost retries |

## Phase 3 Wave 15 Trust Updates (2026-06-02) — Phase-3 Exit Close-out

The closing wave of Phase 3. 26 PRs / all 8 repos / 1 changes-requested cycle / **0 failing CI checks across all PR heads** (cleanest P3 wave) + 8 wave→main bundles + the post-wrapup ig#950 hotfix. Directional summary: org-level + deploy-track hold at their established levels; **Nurul Hakim promotes 4→5** on a third consecutive clean wave; Ingrid's second consecutive standout wave is noted in the child-repo engagement table (per `feedback_child_repo_implementer_rule`, her number belongs to the isnad-graph roster).

### Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Aino Virtanen** (SQL) | 5 | 5 | (hold at max) 4 clean PRs (#589/#591/#592/#593) + the in-wave #586 hook fix; 15% theme-fit concentration; skills-CI gate (#593) closes a real enforcement gap. |
| **Nadia Khoury** (PD) | 5 | 5 | (hold at max) Wave kickoff → 3-gate sequencing → wrapup → phase-exit coordination across all 8 repos; owner-decision routing on every gate (#322 authorize-now, #330 trailing-window, staging re-bootstrap). |
| **Wanjiku Mwangi** (TPM) | 5 | 5 | (hold at max — would be ▲ if not capped) ★ The #322 exit gate end-to-end: spec correction (us#145), parent rollout (main#588), and the **8/8 org-wide ruleset application with per-repo read-back verification**. Top reviewer of the wave (6 Approved verdicts). |
| **Santiago Ferreira** (RC) | 5 | 5 | (hold at max) #330 tech-debt measurement (15.3% ≤ 20%, trailing-window method); 2 clean PRs; 5 reviews; RC sequencing on the 8-bundle wave→main ceremony. |

### Cross-Repo Implementer Updates (deploy track)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Lucas Ferreira** (deploy SRE) | 5 | 5 | (hold at max — would be ▲ if not capped) ★ deploy#394 kafka runbook + **live re-bootstrap execution on the stg VPS** (owner-authorized). Root-caused the real failure (Bitnami-era root-owned volume dirs vs apache/kafka UID-1000 appuser) — a diagnosis refinement over the runbook's own hypothesis, fed back into the runbook. |
| **Nino Kavtaradze** (deploy Sec) | 5 | 5 | (hold at max) ★ The wave's load-bearing reviewer: the single CR (deploy#396) caught both the hard-gate-on-cross-repo-artifact design flaw and the dotted-only-regex evasion. Both became org memories. |
| **Aisha Idrissi** (deploy SRE) | 5 | 5 | (hold at max) #396 (received the CR, resolved cleanly, then redesigned the gate to exit-0+`::warning::` when Hook 14 blocked the continue-on-error rendering) + #397. |
| **Nurul Hakim** (deploy Obs) | 4 | **5** (▲) | Third consecutive clean wave: W12 #358 (egress network), W13 #375 (Grafana login), W15 #400 (ruff+mypy gate for deploy scripts) + 3 substantive reviews this wave. Consistent, reliable, no negative signal across three waves — promotion earned. |
| **Bereket Tadesse** (deploy Mgr) | 4 | 4 | (hold) Not engaged this wave (no PRs, no reviews) — no signal either direction. The W11 demotion stands pending a brief-author restoration demonstration. |

### Child-Repo Wave Engagement (informational — per `feedback_child_repo_implementer_rule`)

> Trust numbers for child-repo rosters belong in those repos' own retros. Noted here for visibility.

| Member | Repo | Engagement | Direction |
|---|---|---|---|
| **Ingrid Lindqvist** | isnad-graph | ★ Second consecutive standout wave: ig#946 + the **post-wrapup ig#950 hotfix** (runtime-config.js → /tmp for read-only rootfs, plus a new `frontend-readonly-container` CI job replicating deploy's exact constraints so the class can't regress). W14 #941 GHCR + W15 #950 = the engineer who keeps unbreaking staging. | strongly positive |
| **Kavitha Sundaramurthy** | data-acquisition | 3 clean PRs (#62/#63/#64) — highest child-repo throughput this wave. | positive |
| **Kofi Mensah-Williams** | landing-page | 3 clean PRs (#106/#107/#108). | positive |
| **Astrid Lindqvist** | design-system | 2 clean PRs (#93 prettier corpus reformat + gate, #95). | positive |
| **Linh Pham** | isnad-graph | ig#944 (retired the 3 pre-existing actionlint -ignores — closes the W14 accepted-debt item). | positive |
| **Jelani Mwangi** | isnad-graph | ig#945 (gitleaks-action v3.0.0 node24). | positive |
| **Mateo Salazar** | user-service | us#144 — re-assigned cleanly after his original scope row (ig#943) was discovered to be a phantom dup (orchestrator-authored error, not his). | positive |
| **Fatima Bensalah** | isnad-ingest-platform | ingest#60. | positive |
| **Anya Kowalczyk / Idris Yusuf** | isnad-graph / user-service | 5 + 4 reviews respectively — the child-repo review backbone this wave. | positive |

### Orchestrator (Self-Assessment)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Orchestrator (Steven via Claude)** | 4 | 4 | (hold) Strong: drove 26 PRs + 8 bundles + 1 hotfix through the full lifecycle with 1 CR and 0 CI failures; honest staging-gate handling (override-with-rationale at wrapup, then **re-verified and re-recorded as genuinely green post-hotfix** instead of letting the override stand); all 3 phase-exit gates closed on API-verifiable state; correct hook-respect behavior (fixed Hook 14's blocking-design trigger instead of admin-overriding). **Hold-not-promote** because of one self-authored error: **ig#943 phantom dup** — filed an isnad-graph issue from deploy#245's stale body snapshot without re-verifying at origin HEAD; cost a scope row, Mateo's reassignment, and a board repair. Exactly the recognized-pattern slip class (the rule existed; the orchestrator didn't apply it to the issue-filing surface). |

### Done Well / Needs Improvement (Phase 3 Wave 15)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Wanjiku Mwangi** | 8/8 ruleset application with read-back verification (the #322 exit gate); top reviewer (6 verdicts) | None this wave |
| **Lucas Ferreira** | Live kafka re-bootstrap on stg VPS; root-cause refinement fed back into the runbook | None this wave |
| **Nino Kavtaradze** | The load-bearing CR (two distinct design flaws caught in one review) | None this wave |
| **Nurul Hakim** | Third consecutive clean wave → promoted to 5 | None this wave |
| **Aisha Idrissi** | CR resolution + Hook-14-respecting gate redesign (exit-0 + `::warning::`) | None this wave |
| **Ingrid Lindqvist** (ig roster) | ig#950 hotfix + regression-proof CI job; second consecutive standout | None this wave |
| **Aino / Santiago / Nadia** | Sustained delivery, measurement, and coordination rigor | None this wave |
| **Orchestrator** | Phase-exit on verifiable state; staging onion fully peeled; hook-respect under pressure | ig#943 phantom dup (stale-snapshot issue filing — proposed process change #1) |

## Phase 4 Wave 1 Trust Updates (2026-06-10) — Clean slate (bugs + security + tech-debt burn-down)

First wave of Phase 4. 23 PRs / 7 repos / **1 changes-requested cycle** (deploy#415) / **0 failing CI checks** at any PR head / staging promotion green. Top-implementer concentration **13%** (3 PRs — Nurul Hakim and Aisha Idrissi tied), the most distributed wave on record — a *theme-fit* low (the wave was deliberately a broad burn-down across tiers, not a single-owner domain). Security tier landed in full (deploy#384/#386 scrape-block pair, isnad-graph#955, deploy#244 OAuth dual-env). Directional summary: **everyone at established levels holds** — a clean, well-distributed wave produces little numeric movement when most of the roster already sits at max. No negative signal, no demotions.

### Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Nadia Khoury** (PD) | 5 | 5 | (hold at max) Wave executed cleanly across 7 repos; the one latent defect (deploy#418) was a missing-gate gap, not a coordination failure. |
| **Wanjiku Mwangi** (TPM) | 5 | 5 | (hold at max) Counter integrity held — wrapup counters (23 / 1 / 13%) reconciled at retro with zero drift. |
| **Santiago Ferreira** (RC) | 5 | 5 | (hold at max) Staging-promotion gate green; owns the new `/watch-deploy` release-monitoring skill authored this session. |
| **Aino Virtanen** (SQL) | 5 | 5 | (hold at max) Tech-debt tier (the bulk of the wave) landed clean; standards review backbone. |

### Deploy / Service Implementers

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Nurul Hakim** (deploy Obs) | 5 | 5 | (hold at max) 3 PRs (deploy#384 security, observability scrape, main#596) — joint top-implementer, fourth consecutive clean wave. |
| **Aisha Idrissi** (deploy SRE) | 5 | 5 | (hold at max) 3 PRs (deploy#395/#398 tech-debt) — joint top-implementer, all clean. |
| **Lucas Ferreira** (deploy SRE) | 5 | 5 | (hold at max) deploy#402/#86/#410 + main#613; authored the deploy#418 fix this session through full lifecycle. |
| **Nino Kavtaradze** (deploy Sec) | 5 | 5 | (hold at max) deploy#386 + #244 security tier landed. |
| **Mateo Salazar** (user-service Eng) | 4 | 4 | (hold) 2 clean bug PRs (us#65 config-URL, us#74 OAuth SQLAlchemyError). Consistent with the W15 3→4 bump; one more clean wave keeps the trajectory toward 5. |
| **Idris Yusuf** (isnad-graph / user-service Eng) | 4 | 4 | (hold) 2 clean security PRs (us#73, isnad-graph#955). Rebuilding cleanly after the W15 #872 anti-pattern note; positive trajectory. |

### Orchestrator (Self-Assessment)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Orchestrator (Steven via Claude)** | 4 | 4 | (hold) This session: diagnosed the live "frontend image not-found" to root (per-service tag mis-routing, **not** the first-hypothesised publish race — pivoted honestly when the evidence contradicted the initial theory), fixed it (deploy#418/PR#419) and built `/watch-deploy` (main#623/PR#624), both through the full 2-reviewer + green-CI lifecycle, and **self-caught a real run-resolution bug in the skill during pre-merge review**. Added a landing-parity completeness pass unprompted. **Hold-not-promote:** the deploy#418 defect itself shipped through W1 undetected — defensible (no user-service-only stg deploy ever exercised the path, and the catching gate didn't exist), but promotion wants a wave with no latent-defect surface attributable to prior orchestrator-driven execution. |

### Done Well / Needs Improvement (Phase 4 Wave 1)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Nurul Hakim / Aisha Idrissi** | Joint top-implementers (3 each), zero CI failures, zero must-fix items | None this wave |
| **Lucas Ferreira** | Tech-debt + docs delivery; live-session deploy#418 root-cause fix | None this wave |
| **Mateo Salazar / Idris Yusuf** | Clean bug + security delivery; the user-service/isnad bug+security backbone | None this wave |
| **Org-level team** | 13% concentration (most distributed wave on record), 1 CR, 0 CI failures, stg green | Commit-identity hygiene: deploy#409 authored as bare `parametrization`; `Kofi Mensah` vs `Kofi Mensah-Williams` divergence (cross-repo persona reconciliation) |
| **Orchestrator** | Honest diagnosis pivot; self-caught skill bug pre-merge; full-lifecycle discipline on both PRs | The deploy#418 class slipped through W1 undetected (now gated by `/watch-deploy` + the fix) |

## Phase 4 Wave 2 Trust Updates (2026-06-11) — Pipeline first light + auth account-linking

### Org-Level Team
| Rated | Old | New | Reason |
|---|---|---|---|
| Nadia Khoury (PD) | 5 | 5 | Wave orchestration + clean wrapup; hold at max |
| Wanjiku Mwangi (TPM) | 5 | 5 | Reviews + counter discipline; hold at max |
| Santiago Ferreira (RC) | 5 | 5 | Caught the merge-commit false-positive in the identity gate — material; hold at max |
| Aino Virtanen (Standards) | 5 | 5 | Identity gate + annunaki + the honest #136 duplication audit + #634 catch; exemplary, hold at max |

### Data-Acquisition / Pipeline
| Rated | Old | New | Reason |
|---|---|---|---|
| Kwesi Boateng | — | +1 (cap 5) | Keystone slice, live load, null-safe loader fix, in-book-ordinal evidence graph, flawless rebase choreography + self-correction |
| Alejandra Reyes-Fuentes | — | +1 (cap 5) | Scraper fix + converged to the more-honest in-book-ordinal extraction |
| Oyunbileg Batbayar | — | +1 (cap 5) | Edge-key real-graph assertion + caught masked empty-graph fixture + SET-null-removes-key subtlety |
| Nikolaos Papadopoulos | — | +1 (cap 5) | E2E harness + live run + found id double-prefix + cross-PR contract alignment |
| Tomás Carvalho (ingest) | — | +1 (cap 5) | Worker-chain E2E + honest xfail-with-diagnosis surfacing ig#69 |

### User-Service
| Rated | Old | New | Reason |
|---|---|---|---|
| Mateo Salazar | — | +1 (cap 5) | Coherent auth-linking guard + real-Postgres-container proof |
| Idris Yusuf | — | +1 (cap 5) | Gating security review — verified guard genuine server-side, not mock-only |
| Anya Kowalczyk | — | +1 (cap 5) | Thorough tech-lead reviews (us#156 + ig#961) |

### Isnad-Graph / Ingest reviewers
| Rated | Old | New | Reason |
|---|---|---|---|
| Ingrid Lindqvist | — | +1 (cap 5) | Config component-env fix with URL-hostile-password tests |
| Imelda Santos, Sayed Reza, Jean-Claude Habimana, Arjun Raghavan | — | hold | Solid review verdicts; no negative signal |

### Done Well / Needs Improvement (Phase 4 Wave 2)
- **Done well:** data-first thesis delivered (real data on screen); integrity culture (mock-masks-production named + hunted, self-correcting); peer-to-peer cross-PR contract alignment.
- **Needs improvement (orchestrator):** reviewer-brief TechDebt-attestation phrasing; advisory-gating handling; crossed-message churn discipline.

## Phase 4 Wave 3 Trust Updates (2026-06-12) — Open the doors: real data in a usable product

Wave shape: **34 PRs / 7 repos / 19 distinct implementers**, top-concentration **15%** (Kwesi Boateng 5/34 — theme-fit, the da adapter light-up sweep), **6 changes-requested cycles** (all on appropriately-sensitive surfaces: admin OBLITERATE reset UI, DS-audit format, theme/charset, team bios, reset endpoint), **0 CI failures**, staging green, **1 prod incident** (deploy path, recovered — see pain points).

### Org-Level Team
| Rated | Old | New | Reason |
|---|---|---|---|
| Nadia Khoury (PD) | 5 | 5 | Largest wave to date (34 PRs) wrapped clean; hold at max |
| Wanjiku Mwangi (TPM) | 5 | 5 | Counter discipline held — all three wrapup counters matched retro recompute exactly (0 drift); hold at max |
| Santiago Ferreira (RC) | 5 | 5 | Clean 7-repo wave→main merge sequencing + branch retention; hold at max |
| Aino Virtanen (Standards) | 5 | 5 | Ontology + gate hygiene; hold at max |

### Data-Acquisition / Pipeline (the data-first sweep)
| Rated | Old | New | Reason |
|---|---|---|---|
| Kwesi Boateng | 5 | 5 | Top implementer (5 PRs: L1/L3/L4/L5 adapter light-ups + T0-B conformance gate), all clean, theme-fit; hold at max |
| Ivana Horvat | — | +1 (cap 5) | NEW Itqan adapter — largest narrator source (115k profiles) integrated clean, single PR, no CR |
| Farhan Malik | — | +1 (cap 5) | Historical-overlay enrichment (new HistoricalEvent node + ACTIVE_DURING links) delivered solo + clean |
| Alejandra Reyes-Fuentes | 5 | 5 | X1 cross-source resolution + L6 sanadset, clean; hold |
| Jean-Claude Habimana | — | hold | X2 cross-sect PARALLEL_OF + T0-A source_id scheme, clean |
| Nikolaos Papadopoulos | 5 | 5 | Thaqalayn Shia E2E, clean; hold |

### Isnad-Graph (admin surface + search + enrich)
| Rated | Old | New | Reason |
|---|---|---|---|
| Idris Yusuf | 4 | 4 | 3 PRs (OBLITERATE reset UI, admin-404 restrict, us bootstrap-admin); 1 CR on the destructive reset UI = appropriate rigor; clean trajectory, hold |
| Jun-Seo Park | — | +1 (cap 5) | Data-mgmt panel + empty-q search no-op, both clean, no CR |
| Aisling Brennan | — | hold | Narrator fulltext index + lockfile bump, clean |
| Ingrid Lindqvist | 5 | 5 | User-mgmt panel rewire to user-service admin API, clean; hold |
| Rohan Wickramasinghe | — | hold | DS-alignment audit landed but took 2 CR cycles (scope/format iteration) — net neutral |

### Deploy
| Rated | Old | New | Reason |
|---|---|---|---|
| Aisha Idrissi | — | hold | Delivered the real v2 promote-gate fix (#425 env-prefix) + runtime-config smoke (#420); **but** the first RCA (#424, blamed `\r`) was wrong and shipped before reviewers reproducing BOTH invocation forms caught the real bug. Strong recovery, minor RCA-rigor note — net hold, not down |
| Weronika Zielinska | — | hold | Secrets-manager ADR 0007 authored clean with owner A+B decision recorded |

### Landing-Page (design-system alignment)
| Rated | Old | New | Reason |
|---|---|---|---|
| Marcia Vasquez-Paredes | — | +1 (cap 5) | 3 clean PRs (monogram retint, data-theme resolution fix, canonical-origin fix) + rebase choreography; the theme fix is what makes DS semantic tokens resolve at all |
| Cédric Novak | — | +1 (cap 5) | DS iconography PR clean AND caught the byte-1300 `<meta charset>` regression in review (real i18n defect, well-measured) |
| Kwame Mensah-Williams | — | hold | Match look&feel via DS semantic tokens, clean |
| Nadia Rahman | — | hold | Regression coverage for lp#69 symptom classes, clean |
| Amara Diop-Sarr | — | hold | The Team page (7 bio cards); 1 CR (bio-card iteration), landed clean |

### Ingest-Platform
| Rated | Old | New | Reason |
|---|---|---|---|
| Léopold Mbongo | — | hold | HTTP reset endpoints (1 CR on the admin surface = appropriate) + pip PYSEC bump, both clean |

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Orchestrator (Steven via Claude)** | 4 | 4 | (hold) Drove the largest wave on record (34 PRs/7 repos) to a clean wrap with exact counter fidelity; **honestly corrected** an optimistic "app probably rolled fine" prod read after SSH ground-truth showed caddy/frontend stuck `Created` (total 521 outage), then recovered non-destructively (targeted `up -d frontend caddy`) and held the kafka volume-wipe for pipeline-owner sign-off. **Hold-not-promote:** two self-caught process slips this wave — a premature `gh issue close 970` paired in-batch with an unverified #984 merge (reopened), and the optimistic outage read before ground-truth. Both caught + corrected, but promotion wants a wave with no self-inflicted slip. |

### Done Well / Needs Improvement (Phase 4 Wave 3)
- **Done well:** the data-first thesis delivered at scale (multi-source Sunni+Shia ingestion light-up + Itqan's 115k narrators + cross-sect PARALLEL_OF); most-distributed wave on record (19 implementers, 15% concentration); review rigor landed exactly where it should (every CR cycle on a destructive/security/visual-correctness surface); reviewer catches were real (Cédric's charset regression, the both-invocation-form repro that caught the #424 wrong-RCA).
- **Needs improvement (orchestrator):** (1) never pair `issue close` with an unverified PR `merge` in one batch — confirm `merged:true` first (memory [[feedback_parallel_panels_shared_file_serialize]]); (2) lead prod-incident reads with SSH ground-truth, not the compose dependency graph; (3) RCA discipline — reviewers must reproduce the FAILING invocation form, not an accidentally-correct one (memory [[feedback_passing_repro_masks_bug_wrong_invocation_form]]).

## Phase 4 Wave 4 Trust Updates (2026-06-12) — Data fan-out, FE light-up & standardization

### Org-Level + Child-Repo Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Ingrid Lindqvist (ig) | 5 | 5 | Owned the full FE color chain; headless-Playwright-verified each step; surfaced+escalated the @theme-no-op constraint instead of shipping a silent break; absorbed heavy (orchestrator-caused) vehicle churn cleanly. Maintain at ceiling. |
| Junseo Park (ig) | new | 4 | Rigorous ig#1002 review surfacing the real DS-publish-drift adjacent finding (→DS#111); re-verified against ground truth and owned the wrong primary conclusion transparently. Strong first appearance. |
| Nino Kavtaradze (deploy) | 5 | 5 | Caught CWE-214 (DB password on argv) on #435 with a verified one-line fix. Maintain. |
| Oyunbileg Batbayar (da) | 5 | 5 | Caught the #118 fuzzy-cluster over-merge pre-merge. Maintain. |
| Idris Yusuf (ig) | — | 4 | Independently registry-verified the #1006 CVE base-image digest before approving. Solid security review. |
| Mateo Rossi (ig) | new | 4 | Independent registry verification of the #1006 digest; clean infra review. |
| Lucas Ferreira (deploy) | 5 | 5 | #426 admin-bootstrap (gate-isolated, no-op-safe) + #1006 CVE fix; verified env-path correctness, not blind. Maintain. |
| Ravi Desai (ux/ig) | new | 4 | Mechanical token-mapping reviews (#999/#1002/#1003 — 65 @theme keys 1:1); retargeted #1001→#1003 himself on the vehicle swap. |

### Done Well / Needs Improvement (Phase 4 Wave 4)

**Done well:** review rigor caught every real defect pre-merge (CWE-214, over-merge, DS-publish drift, CVE digest); FE color system shipped correctly (owner's correct-over-expedient call); data-first core landed.

**Needs improvement (orchestrator):** (1) state-toggle churn on #1001 (serial contradictory close/reopen instructions crossing the agent's actions); (2) merged #1002 at 2/3 reviewers before the deliberately-assigned 3rd (build/dep) lens finished. Both are charter-proposal items this retro.

## Phase 4 Wave 5 Trust Updates (2026-06-13) — Exit drive: verify → audit & close → tech-debt intake

### Org-Level + Child-Repo Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aisha Idrissi (ig) | — | +1 (cap 5) | #601 verification surfaced Phase-4 end-state #1 NOT MET on staging (zero narrator graph, pipeline never ran), evidenced via ssh + cypher-shell — prevented a false Phase-4 exit and seeded the P4W6 spine. Highest-value contribution of the wave. |
| Nino Kavtaradze (deploy) | 5 | 5 | Caught a CWE-214 awk-argv leak on #438 (2nd consecutive wave catching an argv-on-cmdline class) + ran #605 security audit with a live curl 403-verify. Maintain at ceiling. |
| Ingrid Lindqvist (ig) | 5 | 5 | Clean #1012 delivery, 0 CR. Maintain at ceiling. |
| Astrid Lindqvist (ds) | — | +1 (cap 5) | Clean #113 delivery, 0 CR. |
| Nurul Hakim (deploy) | — | +1 (cap 5) | Clean #437 delivery, 0 CR. |
| Santiago Ferreira (main/release) | — | hold | Clean #648 (trivial cspell CR, edited-in-place) + ran the wave wrapup. |
| Marisol Vega-Cruz (ig) | — | hold | #1014 coverage-honesty gap (omitted /billing/checkout) caught by review + addressed. Minor. |
| Lucas Ferreira (deploy) | 5 | hold | #438 addressed both CRs cleanly, but shipped a CWE-214 argv-leak into review (caught by Nino) — same class as W4's deploy argv finding. Process clean; net-neutral. Forward ask: secure-by-construction on the argv surface. |
| Aino Virtanen (standards) | — | hold | Clean #604 audit; authored this retro. |
| Wanjiku Mwangi (tpm) | — | hold | #607 verification MET, clean. |

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Orchestrator (Steven via Claude)** | 4 | 4 | (hold) Clean wave wrap with exact counter fidelity (6/3/17, claimed==recomputed); ran a disciplined Option-A disposition (#601 not-met, dup-searched 3 gaps, mirrored #602/#603 precedent) and an honest live-staging exploratory pass that source-verified 2 real auth bugs before filing. **Hold-not-promote:** the #601 not-met state itself reflects a prior-wave gap (W4 "data-first shipped" lore was harness-only) that should have been caught at W4 wrapup, not W5 — the live-env-verification charter change (#1) is the fix. |

### Done Well / Needs Improvement (Phase 4 Wave 5)

**Done well:** honest verification cited live-env evidence (#601 ssh/cypher, #605 curl-403) not harness; best load distribution on record (17%, 6/6 distinct authors); the 2-reviewer gate caught a real CWE-214 leak + a coverage-honesty gap pre-merge; the baseline exploratory Chrome pass found a high-impact forced-logout-on-401 bug (ig#1016) in ~2 minutes.

**Needs improvement (org):** (1) "shipped in CI ≠ shipped on the VPS" — end-state claims weren't validated against the deployed env until a wave late (charter change #1); (2) Lucas's recurring argv-leak class on the deploy surface (2 waves running) — a secure-by-construction lint/review-lens follow-up may be warranted if it recurs.

## Phase 4 Wave 6 Trust Updates (2026-06-13) — Real data on the VPS

### Org-Level + Child-Repo Implementers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Alejandra Reyes-Fuentes | 5 | 5 | Wave MVP — found+fixed the #601 root cause, produced the real data, clean load-only path + gated-run spec; already at ceiling, maintain at 5 |
| Bjørn Henriksen | 3 | 4 | Mechanism-only delivery, refused to auto-fire live infra, thorough verified gated-run advisory |
| Aisha Idrissi | 5 | 5 | Profile-gating safety call + latent topic fix + image contract; maintain at ceiling (at 5 since W5) |
| Imelda Santos | — | 4 | First numeric rating (prior appearances were prose-only): null-safe loader fix + caught ingest-path key drift + real-neo4j regression |
| Kavitha Sundaramurthy | — | 4 | First numeric rating: durable edge-relation routing fix, clean 2/2 |
| Jun-Seo Park | 4 | 4 | Single-flight refresh, sound security framing, proactive follow-up flag; hold (at 4 since W4) |
| Ingrid Lindqvist | 5 | 5 | Clean fix + exemplary self-flagged rebase re-review discipline; maintain at ceiling (5 since W3, three waves running) |
| Aino Virtanen | 5 | 5 | Clean /wave-start fix + extra drift sweep; maintain at ceiling |

### Reviewers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Nikolaos Papadopoulos | 5 | 5 | Caught the da#120 dup (saved redundant work) + thorough root-cause verification; maintain at ceiling (5 since W3) |
| Nadia Khoury | 5 | 5 | Caught a real doc-drift miss AND the trust-matrix baseline error on this very retro; maintain at ceiling |
| Camila Restrepo | — | 3 | First numeric rating; HOLD — stale-tree misread cost a critical-path cycle (−), honest immediate self-correction on disproof (+); net flat at 3 |

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Orchestrator (Steven via Claude) | 4 | 4 | (hold) Drove the #601 live load to a verified MET — real narrator graph on staging, on-box-only credentials, checkpointed gating, honest batch-vs-streaming framing. Hold-not-promote: two self-inflicted slips — reviewer briefs omitted the mandatory TechDebt attestation line (blocked the first merge; 7 verdicts retrofitted), and a compound-command label apply silently skipped the kickoff hook (main#650, recurred). Both owned + corrected; promotion wants a slip-free wave. |

### Done Well / Needs Improvement (Phase 4 Wave 6)
- **Done well:** independent verification over deference (reviewers + orchestrator both verified peer claims against artifacts — reviewers also caught the trust-matrix baseline error on this retro); risk-gating of live infra; fully-distributed load (8/8 implementers).
- **Needs improvement (orchestrator):** use the verbatim reviewer-brief template (TechDebt line) — its omission blocked the first merge; avoid compound-command label applies (main#650).

## Phase 4 Wave 7 Trust Updates (2026-06-14) — Phase 4 close-out & exit

### Implementers + Reviewers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aino Virtanen (standards) | 5 | 5 | Implemented main#650 — root-caused the issue's own "split on `;`" framing as a **misdiagnosis** and fixed the real bug (shared parser required `--repo`, silently dropping in-repo label edits); repo-Optional + ambient-repo recovery, both hook consumers benefit, DI-tested, 8/8 CI. Maintain at ceiling. |
| Weronika Zielinska (platform/deploy) | 5 | 5 | Dual contribution: clean surgical deploy#413 (2-line read-back wording, shellcheck-clean) AND peer review on #658 that **independently verified** Aino's misdiagnosis claim (not rubber-stamped) + surfaced the CREATE-path sibling gap (#659). Maintain at ceiling. |
| Nino Kavtaradze (deploy/security) | 5 | 5 | Reviewed **both** wave PRs (security angle): cleared the #658 injection surface (argv-form git, no shell), confirmed safe failure mode, independently named the same CREATE-path sibling + a charter-promotion candidate. Maintain at ceiling. |
| Aisha Idrissi (deploy/SRE) | 5 | 5 | Secondary review on deploy#447 — operator-clarity verdict + a useful retro micro-watch (operator-facing string drifted out of sync with the authoritative in-code comment). Maintain at ceiling. |

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Orchestrator (Steven via Claude) | 4 | 4 | (hold) Clean close-out wave: 2 PRs, 4 first-pass Approved reviews, **0 CR cycles**, counters exact (2/0/50, claimed==recomputed), all wrapup gates passed. Directly remediated the W6 promotion-blocker — main#650 (the compound-label-apply skip) was **root-fixed** this wave, not worked around; all 4 verdicts carried the TechDebt line + PR-head-SHA confirmation first-pass (W6's blocker did not recur). Hold-not-promote: two minor self-inflicted recoverable slips — an `echo "$RESP" \| jq` round-trip mangled a large status PUT (409, recovered via `--jq` fetch) and a zsh word-split bash-ism (`set -- $ref`) in a retro query (recovered). The W6 bar was a slip-free wave. |

### Done Well / Needs Improvement (Phase 4 Wave 7)
- **Done well:** root-cause discipline beat issue-framing (Aino disproved the issue's prescribed fix and root-fixed the real bug); reviewers independently verified peer claims AND converged un-prompted on the same forward-looking sibling gap (#659); thin-wave hygiene held (TechDebt + head-SHA on all 4 verdicts first-pass).
- **Needs improvement (orchestrator):** prefer `gh api --jq` over `echo "$RESP" \| jq` for large API payloads (avoids the shell-mangle 409 class); keep Bash-tool commands zsh-safe (no `set -- $unquoted` word-split assumptions).

## Phase 5 Wave 1 Trust Updates (2026-06-14) — Data spine

First Phase-5 wave (data-acquisition only). 4 PRs, **0 ChangesRequested cycles**, all first-pass Approved; top-concentration 25% (4/4 distinct authors — healthy). Reviews were uniformly sharp — three sources independently surfaced forward-looking throughlines, and the keystone review caught a real precision bug the fix's own test masked.

### Implementers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Alejandra Reyes-Fuentes | 5 | 5 | **Wave MVP** — triple contribution: implemented da#138 (caught a real nasab-reversal false-merge, order-guard not threshold-bump) AND reviewed #150 AND the standout keystone review on #151 (reproduced عن mid-word over-segmentation in real narrator names + caught that the new e2e fixture masks it). Maintain at ceiling. |
| Ivana Horvat | 4 | **5** (▲) | da#146 keystone — root-caused the bug AWAY from the issue framing (not the lk adapter; diacritic-free patterns vs voweled text, masked by un-voweled toy fixtures), shipped a tested deterministic splitter (1 blob → 6 mentions; 31,525 chains segmented), honest real-NER follow-up. + reviewed #152. Promote to ceiling. |
| Kwesi Boateng | 5 | 5 | da#144 — diagnosed the upstream 2→3-file dataset restructure, Nodes-decoy-aware selector, live-traced 63,642 edges, kept mis OFF the STUDIED_UNDER allowlist. Maintain at ceiling. |
| Nikolaos Papadopoulos | 5 | 5 | da#148 — honest producer-fixable (shipped) vs data-decision (→da#153) split; investigated + correctly closed the 15-lk-STUDIED_UNDER as cross-corpus identity merge (not a bug). Maintain at ceiling. |
| Kavitha Sundaramurthy | 4 | **5** (▲) | da#147 correctly killed **premise-false** with cross-repo code evidence (verify-don't-fabricate; refused a harmful binary-collapse "fix") + sharp #152 secondary review (fixture covers precision AND recall traps). Promote to ceiling. |

### Reviewers (first numeric ratings)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Jean-Claude Habimana | — | **4** | First numeric rating: architect reviews on #149 + #151; confirmed the right-layer (shared arabic.py) fix, caught the "Tracked"-without-issue-number nit (→da#154), and co-surfaced the fixture-masks-bug throughline. |
| Tarek Mansour | — | **4** | First numeric rating: #149 review surfaced the da#133 edge-relation **default-trap** (DEFAULT_EDGE_RELATION falls back to STUDIED_UNDER → silent mis-route for any future transmission producer) — a high-value forward-looking finding. |
| Oyunbileg Batbayar | 5 | 5 | #150 QA review — verified test coverage in BOTH directions (self-loop drop AND distinct-adjacency keep; grade-normalize table breadth). Maintain at ceiling. |

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Orchestrator (Steven via Claude) | 4 | 4 | (hold) Clean wave: scoped → kicked off → 4 PRs → 8 reviewers → wrapped, 0 CR cycles, counters exact (4/0/25, claimed==recomputed). Independently verified da#147 premise-false before closing (good judgment, avoided a harmful fix). Navigated the `validate_labels` multi-cmd + stale-cache hook bugs with bare-command workarounds (the bugs are #661/#663, not orchestrator error). Two consecutive clean waves (P4W7, P5W1) build toward promotion; holding 4 for humility/trend, not for any specific slip. |

### Done Well / Needs Improvement (Phase 5 Wave 1)
- **Done well:** every reviewer verified rather than rubber-stamped — the keystone review even caught that the fix's own test masks a NEW precision bug (fixture-masks-bug recurring one layer down); three independent forward-looking throughlines; premise-false caught by the implementer (Kavitha) AND independently confirmed; honest scope-splitting (da#153/154/155 filed, nothing dropped).
- **Needs improvement (process):** the `validate_labels` hook bit the orchestrator twice (multi-cmd `--repo` cross-association + stale label cache) — tracked in #661/#663, worked around; and the fixture-masks-bug class keeps recurring — proposed as a charter rule this retro.

## Phase 5 Wave 2 Trust Updates (2026-06-14) — API light-up

Clean wave: 5 PRs, **0 ChangesRequested cycles** (every PR approved first-pass), CI green, staging green. Team = isnad-graph roster. One integrity note: the keystone #1024/#1045 shipped under Ingrid's identity but was an **orchestrator-takeover** (the assigned implementer produced no branch/PR/commit and no task was tracked — see feedback_log pain point #1); Ingrid is therefore **held, not credited**, for that PR.

### Implementers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Ingrid Lindqvist | 5 | 5 | Hold at ceiling on prior standing. #1045 (narrators 500 keystone) shipped under her identity but was orchestrator-authored after a dispatch stall — **not credited** to her this wave (integrity: don't credit unearned work). No negative signal either — the stall was a dispatch/tracking gap, not her slip. |
| Jun-Seo Park | 4 | 4 | #1033 (search 422) — correct dual-cap fix (keyword 100 / semantic 50), non-vacuous boundary tests both sides, both approvals first-pass. Trivial post-#1028 merge conflict resolved by orchestrator. Hold (clean, at 4 since W4). |
| Ravi Wickramasinghe | 3 | **4** (▲) | #1030 (i18n page-body, TD intake) — clean; reviewers verified 7-locale key parity programmatically (72-key base, 0 missing/extra) + correct grade-filter scope policy. Also reviewed #1028. Recovery from the stale W-early DS-integration neutral. |
| Idris Yusuf | 4 | 4 | #1029 (auth refresh-on-401 across admin+profile clients) — clean, both approvals (Anya + Arjun). Hold (clean trajectory). |
| Mateo Salazar | 5 | 5 | Dual contributor: implemented #1028 (subscriptions/me origin + derive collection facet) AND reviewed #1045 + #1030 (the #1045 review flagged the frontend-TS-nullable follow-up → ig#1046). Maintain at ceiling. |

### Reviewers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Marisol Vega-Cruz | 3 | **4** (▲) | **Wave MVP (reviews)** — 4 rigorous code-verified reviews (#1045, #1033, #1030, #1028), each run-the-tests + verify-against-head, and the load-bearing #1033↔#1028 merge-sequencing flag that predicted the exact conflict. Strong recovery from the old tarball-lockfile neutral. |
| Farhan Malik | 5 | 5 | #1033 review — independently reproduced the dual-cap root cause + confirmed tests non-vacuous. Maintain at ceiling. |
| Anya Kowalczyk | 5 | 5 | #1029 review. Maintain at ceiling. |
| Arjun Raghavan | 4 | 4 | #1029 review. Hold. |

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Orchestrator (Steven via Claude) | 4 | 4 | (hold) Drove the wave to a clean close (5 PRs, wave→main, stg green, counters exact 5/0/20) AND handled a wide product/ops surface in parallel (landing-page hotfix, monitoring check-in, 3 issue-set filings for P5W3). Caught the #1024 dispatch stall and took it over correctly (sound fix + regression test), but **the stall itself is a process gap I own** — implementers were spawned without TaskCreate tracking, so a zero-output implementer was invisible until a manual nudge. Holding 4: clean execution offset by the dispatch-tracking gap (proposed fix this retro). |

### Done Well / Needs Improvement (Phase 5 Wave 2)
- **Done well:** cleanest wave in recent memory (0 CR cycles, all first-pass approvals); strong independent review culture (Marisol's 4 verified reviews + the predicted merge-conflict flag; Mateo's TS-nullable follow-up); honest scope handling (#1023 relocated to deploy#449, not silently dropped); the keystone narrators-500 fix unblocks /graph + narrator search.
- **Needs improvement (process):** (1) implementer dispatch had no task-tracking → a zero-output implementer (#1024) was invisible until manual nudge; (2) local full-suite test runs hang on absent sandbox DB services (14-min stall) — needs a documented verify-via-unit-construction-then-cite-CI pattern.

## Phase 5 Wave 3 Trust Updates (2026-06-14) — Trustworthy data & search

Clean-but-not-frictionless wave: **17 PRs across 5 repos**, all 2× Approved + CI green + staging green; **2 ChangesRequested cycles** (both real bugs caught by adversarial review, both fixed before merge); top-concentration **12%** (Mateo Salazar 2/17 — 16 distinct implementers, the lowest concentration of the phase). Two stall-class events recurred (ledger "implementing" cross-wire on ig#1023/#1038; Nneka silent-idle on ig#1038 → orchestrator takeover) — same agent-liveness gap class as P5W2's dispatch stall; the fix proposed last retro has not yet landed.

### Implementers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aino Virtanen | 5 | 5 | main#678 (CREATE-path wave-label drop #659 + validate_labels body over-match #661) — clean hook fix, 2 approvals. Maintain at ceiling. |
| Jun-Seo Park | 4 | 4 | ig#1052 (surface hadith grade via GRADED_BY) — clean, both approvals first-pass. Hold. |
| Mei-Lin Chang | — | **4** | First numeric rating: ig#1053 (compute + load hadith embeddings — the semantic-search data spine), clean 2-approval delivery. **Roster hygiene flag:** roster.json/roster.md name drift surfaced this wave (process item, not a delivery slip — see feedback_log pain point #3). |
| Ingrid Lindqvist | 4 | 4 | ig#1055 (default graph subgraph on landing) — clean. Hold. |
| Farhan Malik | 5 | 5 | ig#1056 (isnad-narrator filter + reachability — a feat, not a fix). Clean, 2 approvals. Maintain at ceiling. |
| Mateo Salazar | 5 | 5 | Dual-repo contributor + top-concentration (ig#1058 honest admin counts/corpus + us#167 admin user-stats endpoint). Clean both. Maintain at ceiling. |
| Thandiwe Moyo | 3 | 3 | ig#1059 (apply collection/grading/century facets) — **1 CR cycle**: initial century-facet matcher leaked later centuries on any single-bucket-below-5 selection (caught *independently by both* Anya + Marisol). Fixed correctly with a fixed `OPEN_ENDED_CENTURY=5` constant + mid-bucket regression test. Real-bug-then-clean-fix = neutral; hold. |
| Nneka Obi | 4 | 4 | ig#1063 (configurable Loki log retention) — shipped a real retention file-writer matching the deploy#455 contract (1 CR cycle, Jelani-verified path/tenant/inode/fallback). **Held, not docked:** the assigned agent went silent-idle pre-commit; orchestrator-takeover recovered *her* uncommitted worktree work (so the work is hers) — the stall is an agent-liveness/infra gap, not her slip. |
| Anya Kowalczyk | 5 | 5 | us#168 (lengthen access-token TTL 15→60) clean impl **+** the independent century-facet catch on ig#1059. Maintain at ceiling. |
| Weronika Zielinska | 4 | 4 | deploy#454 (repoint user-service blackbox probe — resolved the ig#1023 health-404 cross-wire on the deploy side). Clean. Hold. |
| Lucas Ferreira | 3 | **4** (▲) | deploy#455 (compose log-rotation anchor + Loki retention contract) — material cross-repo contract that ig#1063 correctly consumed (the api-container-as-writer provision). Clean, 2 approvals. Promote off the prior single-interaction neutral. |
| Nadia Hakim | — | **4** | First numeric rating: deploy#456 (Email backup + swappable alert channel) — clean feat extending the stg alerting surface (deploy#452/453 lineage). 2 approvals. |
| Kwesi Boateng | 5 | 5 | da#168 (fail-fast on undeclared edge relation — the da#133/#157 edge-relation default-trap durably closed). Maintain at ceiling. |
| Alejandra Reyes-Fuentes | 5 | 5 | da#169 (transliteration fallback for English-name coverage, da#159). Clean. Maintain at ceiling. |
| Kavitha Sundaramurthy | 5 | 5 | da#170 (scale PARALLEL_OF detection). Clean. Maintain at ceiling. |
| Ivana Horvat | 5 | 5 | da#171 (production-robust isnad segmentation). Clean. Maintain at ceiling. |

### Reviewers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Marisol Vega-Cruz | 4 | **5** (▲) | **Wave MVP (reviews), 2nd consecutive** — reviewed BOTH CR-cycle PRs: independently reproduced the ig#1059 century-facet leak AND verified ig#1063's Loki writer against the deploy#455 contract. Two straight waves of run-the-tests/verify-against-head reviews that each caught real defects → promote to ceiling. |
| Anya Kowalczyk | 5 | 5 | (reviewer credit) independent ig#1059 century-facet catch — see implementer row. Maintain. |
| Jelani Mwangi | 4 | 4 | ig#1063 review — verified the Loki retention writer against the merged deploy#455 contract (path/tenant/inode-preservation/fallback all confirmed). Hold (clean, precise). |

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Orchestrator (Steven via Claude) | 4 | 4 | (hold) Drove a clean wave→main close (17 PRs, 5-repo wave-merge ceremony, reachability + staging gates green, counters exact 17/2/12) and caught + corrected a real state cross-wire (ig#1023 already-resolved vs ig#1038 unstarted). But **two stall-class events recurred** (ledger cross-wire + Nneka silent-idle) of the **same agent-liveness class** I flagged at P5W2 — and the TaskCreate-per-implementer fix I proposed then still hasn't landed. Also hit the `wave_3_*` cross-phase key-reuse hazard (stale P4W3 values bled in; cleared manually at wrapup). Clean execution offset by a recurring unaddressed process gap → hold 4. |

### Done Well / Needs Improvement (Phase 5 Wave 3)
- **Done well:** strongest review culture of the phase — both CR cycles were *real* bugs surfaced by adversarial review (the century-facet leak caught independently by two reviewers), not nits; lowest concentration of the phase (12%, 16 implementers); honest data-spine work (semantic embeddings, isnad-narrator reachability, fail-fast edge-relation guard) with cross-repo contracts cleanly honored (deploy#455 ↔ ig#1063).
- **Needs improvement (process):** (1) **agent-liveness** — two stall-class events (silent-idle + ledger cross-wire); the P5W2-proposed TaskCreate-per-implementer tracking is still unapplied; (2) **roster drift** — Mei-Lin Chang roster.json/roster.md mismatch needs a consistency check; (3) **cross-repo-status.json wave-key reuse** — `wave_{M}_*` keys carry stale prior-phase values across phases, a correctness hazard hit live this session.

## Phase 5 Wave 4 Trust Updates (2026-06-16) — Trustworthy data & search (capstone)

### Implementers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Weronika Zielinska | 4 | **5** (▲) | Authored the re-embed mechanism (ADR 0008 / deploy#462) and delivered two clean, prompt follow-on fixes under capstone pressure (#466 timeout+4G mem, #469 90m) — each green-before-push, each unblocking the next step. End-to-end domain ownership of the wave's centerpiece → ceiling. |
| Linh Pham | 3 | **4** (▲) | Precise root-cause + minimal fix on the embed-image `import src` bug (ig#1094): PYTHONPATH=/app incl. the latent runtime-stage twin, `buildx --check` green, no install creep. Exactly-scoped. |
| Aino Virtanen | 5 | 5 | main#688/#689 deterministic `wave_status.py` shipped end-to-end (kills the zsh word-split class), live-verified 19/4/16, swept the skill loops + charter note. Maintain at ceiling. |
| Mateo Salazar | 5 | 5 | 3 clean PRs incl. the embed code (ig#1089). Maintain at ceiling. |

### Reviewers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Jelani Mwangi | 4 | 4 | ig#1094 infra-lens review + filed ig#1095 (proper package-install follow-up). Clean, hold. |
| Nurul Hakim | — | 4 | deploy#466/#469 observability-lens reviews; filed deploy#467 catching that a hard timeout-kill aborts before the `.prom` write (no metric emitted). Sharp. |
| Aisha Idrissi | — | 4 | deploy#466/#469 SRE-lens; the 47.5m/60m margin note drove the 90m safety bump. Forward-looking. |

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Orchestrator (Steven via Claude) | 4 | 4 | (hold) Drove the capstone to a verified staging delivery — found+fixed two latent prod-blocking bugs *before* prod (embed-image packaging, ssh timeout), surfaced prod-empty honestly rather than forcing a pointless cutover, and caught the hand-rolled promotion-audit's 24-AUTO mis-fire before emitting. Offset by: the shell/gh fragility recurred 3× before the #688 fix, and the promotion-audit had to be hand-rolled (mis-fired) for lack of a driver. Clean delivery + good judgment, two known process gaps now filed (#688 done, #690 open) → hold 4. |

### Done Well / Needs Improvement (Phase 5 Wave 4)
- **Done well:** staging-first capstone caught 2 latent bugs before prod and verified real recall; determinism principle codified *and* shipped as code same-session (#688); honest prod-empty surfacing instead of a forced cutover; lowest-friction review culture (TechDebt attestation held, useful follow-ups filed #1095/#467).
- **Needs improvement (process):** (1) shell/gh fragility cost cycles before #688 landed; (2) `/promotion-audit` lacks a canonical driver → hand-rolled mis-fire (#690); (3) MEMORY.md oversized (38KB); (4) `wave_{M}_*` theme/key cross-phase staleness recurred (main#683 still the durable fix).

## Phase 5 Wave 5 Trust Updates (2026-06-20) — Production cutover (real data live on prod)

### Org-Level / Framework (main)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Santiago Ferreira | 4 | **5** (▲) | Shipped the **promotion-audit canonical driver** (#701) — directly closes the P5W4 #690 hand-rolled mis-fire pain point — plus `pr_review_state.py` (#710, deterministic review-state) and the REPO_ROOT-independent ontology test (#697). Three clean tooling PRs, one of them a durable retro-loop close. Promote to ceiling. |
| Wanjiku Mwangi | 3 | **4** (▲) | Mechanized **per-phase wave-key reset** (#699) closing #683 — the `wave_{M}_*` cross-phase reuse hazard flagged in *both* P5W3 and P5W4 retros — plus the validate_wave_audit wave-branch-PR exemption (#700). Two clean PRs that retired a recurring correctness hazard. |
| Aino Virtanen | 5 | 5 | 4 charter/hook PRs (#696 fixture-realism charter, #698 cspell CI-parity, #702 gh-parser invariant + hook, #709 session-handoff phase reader). Clean. Maintain at ceiling. |

### Data-acquisition (cutover data spine)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Alejandra Reyes-Fuentes | 5 | 5 | da#180 (multi-source Sunni corpora → staging Neo4j, containerized loader) + da#192 (matn_ar fallback) + da#193 (canonical composition encode). 3 PRs on the cutover spine. Maintain at ceiling. |
| Kavitha Sundaramurthy | 5 | 5 | da#181 — real-schema thaqalayn parse + loaded the Shia Four Books to staging (closed the fixture-masked parser gap). Cutover-critical. Maintain at ceiling. |
| Ivana Horvat | 5 | 5 | da#187 — completed Riyad as-Salihin to 1,896 by enumerating named book segments (addresses the da#177 truncation class). Clean. Maintain at ceiling. |
| Jamal Habimana | — | **4** | First numeric rating: da#186 — sourced Tahdhib al-Ahkam + al-Istibsar from ThaqalaynData (CC0), **completing the Shia Four Books**. Cutover-critical, clean. |
| Nikos Papadopoulos | — | **4** | First numeric rating: da#183 — staging itqan narrator load (115,735 bios → 85,840 canonical Narrators), the largest narrator source. Clean. |
| Tarek Mansour | 4 | 4 | da#184 (testcontainers neo4j pin) + da#189 (bleach security pin). Two clean infra/security PRs. Hold. |
| Olzvoi Batbayar | — | **3** | First numeric rating: da#185 (tightened tautological cap-equivalence test). Small, clean. |

### isnad-graph / user-service
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Mateo Salazar | 5 | 5 | ig#1100 (shared search-result helper) + ig#1106 (rate-limit Redis socket timeouts, closes #1034) + us#176 (security floors). 3 clean PRs. Maintain at ceiling. |
| Linh Pham | 4 | 4 | ig#1097 + ig#1102 (testcontainers neo4j tag + password alignment). Two clean test-infra PRs. Hold. |

### Ingest-platform / Deploy / Design-system / Landing-page
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Lerato Mbongo | — | **4** | First numeric rating: ingest#98 (reconcile vendored SourceCorpus with da canonical) + ingest#103 (starlette/cryptography security floors). Two clean PRs closing real drift. |
| Astrid Lindqvist | 5 | 5 | ds#118 (motion primitives → framework-neutral CSS) + ds#119 (compiled component-utilities layer, closes the #115 no-op-utilities class) + ds#121 (release bump). 3 clean PRs. Maintain at ceiling. |
| Kojo Mensah-Williams | — | **4** | First numeric rating: 3 lp PRs — #142 (dark-mode toggle), #145 (Direction-C architecture hero), #141 (removed fabricated pre-launch staff). Clean, product-facing. |
| Nadia Hakim | 4 | 4 | deploy#473 (alert on corpus_reembed_last_run_* failed+stale). Clean observability extension. Hold. |
| Lucas Ferreira | 4 | 4 | deploy#472 (gate tiered-rollout service lists ⊆ compose services, closes #434). Clean CI guard. Hold. |
| Weronika Zielinska | 5 | 5 | deploy#471 (sweep stale Kafka topic in preflight fixture). Clean. Maintain at ceiling. |

**Single-clean-PR implementers held at current rating** (no significant directional signal — clean single deliveries): A.Diop-Sarr (lp#143 brand assets), C.Novak (lp#140 candidate assets), B.Henriksen (ingest#97 neo4j-tag centralization), I.Lindqvist (ig#1099 GRADE_LABELS single-source), J.Mwangi (ig#1101 embed-image package install), J.Park (ig#1098 readJsonResponse guard), K.Ranasinghe (ingest#100 bleach security), M.Reyes (ds#116 icons criticalExports), N.Pham (ds#117 a11y color-scheme), N.Obi (ig#1103 i18n page-body extension).

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Orchestrator (Steven via Claude) | 4 | 4 | (hold) Drove the cleanest wave of the program to a verified close (45 PRs, 0 CR, staging+fan-in green, all 8 wave branches reachable) and surfaced the prod data-quality reality **honestly** (sanadset orphans, sparse chains, broken search → meta #723/P7) rather than declaring a hollow cutover. Self-corrected a "zero chains" overstatement mid-validation against the actual graph counts. Offset by: the **wave was merged days before being wrapped** (P5W5 sat `active:true / wrapped_up_at:null` with un-run audits), and the marker-reconciliation push-block had to be resolved reactively. Clean execution + honest reporting, one deferred-ceremony gap (now Proposed Change #1) → hold 4. |

### Done Well / Needs Improvement (Phase 5 Wave 5)
- **Done well:** retro→fix loop genuinely closed (two recurring pain points #690/#683 retired in-wave); cleanest wave of the program (0 CR / 45 PRs, all gates green); lowest concentration ever (9%, 28 implementers) with the cutover data spine still delivered cleanly; honest prod-quality surfacing instead of a hollow "cutover done."
- **Needs improvement (process):** (1) **deferred wrap** — wave merged-then-wrapped-later, audits un-run until this session (Proposed Change #1: wrap-on-last-merge trigger); (2) **annunaki noise** — 85% exit-0 false positives drown the real signal (Proposed Change #2); (3) **cutover ≠ queryability** — prod data present but not usable (search broken, sanadset orphans), carried to P7 #723 (Proposed Change #3: split the two as distinct exit criteria).

## Phase 6 Wave 1 Trust Updates (2026-06-21) — Memory & code-over-prose

### Org-Level Team
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aino Virtanen | 5 | 5 | 22 in-scope parent PRs (cspell parent fix, mermaid gate widening, branding, squash-safe office epoch) + the **#799 stranding reconciliation**, which she handled exemplarily — extended rather than copied against main's newer #748 structural-parse/parity-table divergence. Theme-fit dominance, all green, 0 CR. Maintain at ceiling. |
| Santiago Ferreira | 5 | 5 | Clean reviewer verdict on #796 (mermaid scope). Hold at ceiling. |
| Nadia Khoury | 5 | 5 | Clean reviewer verdict on #799 (byte-identical file verification). Hold at ceiling. |
| Wanjiku Mwangi | 4 | 4 | Reviewer on #796 + the **decisive completeness re-diff on #799** (proved exactly 5 files stranded, no more — closed the "is the reconciliation complete?" question). Strong diligence; hold 4 (one review-heavy wave). |

### Child-Repo Implementers (emergent cspell rollout, #684)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Luciana Ferreyra | — | **4** (new) | design-system#129. Standout first entry: verify-before-trust caught the brief's false premise (gate existed, didn't classify cspell → extended to a full parity fix instead of mirror-only + deferred follow-up), then recovered a silently-dropped CI trigger via close/reopen. 0 CR. New entry above default for exceptional diligence. |
| Linh Pham | 4 | 4 | isnad-graph#1122 clean full-fix + surfaced two latent local⇄CI parity gaps (#1123). Hold 4. |
| Mateo Salazar | 5 | 5 | user-service#189 clean; flagged the build-kind false-match caveat. Maintain at ceiling. |
| Lucas Ferreira | 4 | 4 | deploy#487 clean; correctly diagnosed + ignored a self-loop task-replay glitch. Hold 4. |
| Fatima Bensalah | — | **3** (new) | ingest-platform#113 clean full-fix; correctly identified the self-loop replay. Standard first numeric entry for a clean single delivery. |
| Tarek Mansour | 4 | 4 | data-acquisition#211 clean full-fix (green, complete; went idle without a written report — minor hygiene note). Hold 4. |

### Reviewer Corps (credit — held, clean Hook-4 verdicts, no rubber-stamps)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Oyunbileg Batbayar | 5 | 5 | #211 review — non-tautology test verification (assert cspell-in-kinds + both drift directions). Maintain. |
| Anya Kowalczyk | 5 | 5 | Reviewed BOTH us#189 and ig#1122. Maintain. |
| Keanu Tama | 3 | 3 | #129 full-parity review (held approval until validate-package finished). Hold. |
| Petra Vidović | — | **3** (new) | ingest#113 review — independent non-tautology test check. First numeric entry. |

**Held at current rating (clean single reviews, no directional signal):** Jelani Mwangi (4, ig#1122 infra-lens), Idris Yusuf (4, us#189 security-lens pin check), Nurul Hakim (4, deploy#487 regex-coverage check), Bjørn Henriksen (4, ingest#113), Jean-Claude Habimana (4, da#211), Weronika Zielinska (5, deploy#487), Kofi Mensah-Williams (docs-lens glob check on #129).

### Done Well / Needs Improvement (Phase 6 Wave 1)
- **Done well:** cleanest possible fan-out (8 PRs, 0 CR / 0 CI-fail / 0 must-fix-after-merge); verify-before-trust caught two real issues (Luciana's gate-premise correction, the reachability gate's stranding catch); reviewers did genuine independent verification.
- **Needs improvement (process):** (1) **mixed merge model stranded #734/#735 off main** — only caught at wrapup (Proposed Change #1: one merge model per wave + mid-wave reachability check); (2) **wave-key collision (#683)** corrupted wrapup markers for the 3rd consecutive retro (Proposed Change #2: phase-namespaced keys, must-fix next wave); (3) **silent CI-trigger drop** on #129 produced "no checks reported" — treat as hard not-ready (Proposed Change #3).
- **Concentration:** 81% A.Virtanen (22/27) — **theme-fit** (framework/standards/code-over-prose is her surface), not fragility. Forward-flag: P6W2 (persona/ontology revisits) is also framework-heavy and may re-concentrate on Aino — consider distributing or accepting + documenting at scope time.


---

## Phase 6 Wave 2 Trust Updates (2026-06-22) — Architectural revisits + retro mechanization

> **First wave scored under the §4b mechanical-scoring _spirit_ (#819), at the owner's request.**
> Under the prior model, all 15 implementers delivered one clean PR each → 15× "clean, +1, None this
> wave" — the exact ratchet the owner flagged. Under evidence-anchored, distribution-disciplined scoring:
> **a clean routine PR with 0 must-fix / 0 CI-red is baseline expected performance → no trust change.**
> Only moves backed by a concrete differentiator are applied. Result this wave: **14 of 15 hold steady; 1 moves.**
> (The mechanism itself is not yet implemented — that is #819 Task; this is a manual dry-run of its discipline.)

### Org-Level Team (noorinalabs-main)

| Rated | Old | New | Mechanical basis |
|-------|-----|-----|------------------|
| Weronika Zielinska (PA) | 4 | **5** ↑ | Two distinct evidence-anchored signals: (1) the deeper of the two architectural evals (#813 ontology spike), and (2) the wave's **only** must-fix catch as reviewer — caught the canonical-doc drift on Aino's #811 (`ontology/lifecycle.md` still referencing the deleted `wave_key_reset.py`/§5a), which was the sole changes-requested cycle of the wave. The one defensible increase. |
| Aino Virtanen (SQL) | 5 | 5 | #811 headline wave-key Design B (global monotonic identity — complex, clean final state). **Named gap (not "None"):** the initial #811 carried the `lifecycle.md` drift Weronika caught → 1 rework cycle. Caught + fixed in one pass; net no change, already at ceiling. |
| Lucas Ferreira · Nurul Hakim · Aisha Idrissi · Nino Kavtaradze · Bereket Tadesse · Santiago Ferreira · Wanjiku Mwangi · Nadia Khoury | hold | hold | **Held steady — explicitly NOT ratcheted.** Each delivered 1 clean PR, 0 must-fix received, 0 CI-red. Baseline expected delivery is not an increase under the #819 discipline. |

### Child-Repo Teams

| Rated | Old | New | Mechanical basis |
|-------|-----|-----|------------------|
| Marisol Vega-Cruz · Linh Pham · Jelani Mwangi (isnad-graph) | hold | hold | 1 clean PR each (#1124/#1125/#1126), 0 must-fix, 0 CI-red. Baseline — held. |
| Mateo Salazar · Idris Yusuf (user-service) | hold | hold | 1 clean PR each (#190/#191), 0 must-fix, 0 CI-red. Baseline — held. |

### Done Well / Needs Improvement (Phase 6 Wave 2) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|--------|---------------------------|--------------------------------------------|
| **Weronika Zielinska** | #813 spike depth (real AST probe) + the wave's only must-fix catch (#811) | clean: 0 must-fix received, 0 CI-red |
| **Aino Virtanen** | #811 Design B headline tech-debt fix | 1 rework cycle — `lifecycle.md` drift, caught in review |
| **All 13 others** | 1 clean on-theme PR each; the deliberate de-concentration (7% top vs P6W1's 81%) worked | clean: 0 must-fix, 0 CI-red — baseline, not exceptional; no ratchet |

**Fire/hire:** none. The performance-triggered exit path the owner asked for (#819 §4b) is not yet
implemented, so "fired" still has no mechanical meaning this wave — that is exactly what #819 closes.

## Phase 6 Wave 16 Trust Updates (2026-06-23) — Framework / gate hardening

> **Orchestrator-executed framework wave.** The 7 parent PRs carry persona commit identity (`-c` flags)
> but were driven directly by the orchestrator — framework/gate work is orchestrator-owned by nature.
> Trust signal is therefore weak this wave: a clean framework PR under orchestrator drive is baseline,
> not a distributed-implementer differentiator. Under the #819 §4b discipline (clean routine PR with
> 0 must-fix / 0 CI-red = baseline → no change), **all hold.** No defensible increase; no decrease.

### Org-Level Team (noorinalabs-main)

| Rated | Old | New | Mechanical basis |
|-------|-----|-----|------------------|
| Aino Virtanen (SQL) | 5 | 5 | #833 (#816 root-fix — decoupled the parity test from stale child checkouts; the wave's most consequential PR, *verified* by the wrapup push landing on origin) chosen over the expedient #826, plus #829 (#663 parser invariant). At ceiling — hold with named done-well; the inverted-premise handling is the kind of signal that would move a non-ceiling rating. |
| Wanjiku Mwangi (TPM) | hold | hold | 3 clean PRs (#825/#827/#830), 0 must-fix, 0 CI-red. Baseline under §4b — held. |
| Santiago Ferreira (RC) | hold | hold | #824 (#817 mermaid dir) — 1 clean PR, 0 must-fix. Baseline — held. |
| Nadia Khoury (PD) | hold | hold | #828 (#745 liveness mechanization) — 1 clean PR. Baseline — held. |

### Child-Repo Teams

| Rated | Old | New | Mechanical basis |
|-------|-----|-----|------------------|
| Lucas Ferreira (deploy) | hold | hold | #491 (E2E harness fix, deploy-side only) + #489 (base-pin), 0 must-fix. One E2E flake (`httpx.ReadError`) re-ran green — infra, not the PR. Baseline — held. |
| Tarek Mansour (data-acquisition) | hold | hold | #213 — **1 caught-and-fixed rework cycle** (hook `files:` regex missed the top-level curated corpus; widened + verified in one pass). Under §4b a single review-caught-and-fixed cycle is the system working, not a decrease. Named gap, held. |
| Bjørn Henriksen (ingest-platform) · Kofi Mensah-Williams (landing-page) | hold | hold | 1 clean PR each (#115/#154), 0 must-fix, 0 CI-red. Baseline — held. |

### Done Well / Needs Improvement (Phase 6 Wave 16) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|--------|---------------------------|--------------------------------------------|
| **Aino Virtanen** | #833 root-fix unblocked local push-to-main (verified by wrapup push) — chose root over expedient #826 | clean: 0 must-fix received, 0 CI-red |
| **Wanjiku Mwangi** | 3 on-theme framework PRs, 0 must-fix | clean: 0 must-fix, 0 CI-red |
| **Tarek Mansour** | #213 corpus-fixture realism check landed | 1 review-caught regex-scope bug, fixed same pass |
| **All others** | 1 clean on-theme PR each | clean: 0 must-fix, 0 CI-red — baseline, no ratchet |

**Fire/hire:** none. (Same as P6W2: §4b mechanical exit path is #819, not yet implemented.)

**Concentration note:** 43% top by commit identity, but true orchestrator concentration ~100% (meta-wave).
Theme-fit, not fragility — but W17 (architectural execution) is planned as genuine distributed
implementer work to avoid carrying orchestrator-solo execution into non-framework scope.

---

## Archived Personas — parent roster (P6W17 governed headcount, #841)

Persona Option B (criterion #3, spike `.claude/team/spikes/p6w2-persona-model-evaluation.md`) caps the
parent roster at **9** cards and **merges near-duplicate roles**. The card below was removed from
`.claude/team/roster/` to bring the parent roster from 10 → 9 (AT the cap; the cap is inclusive). **History
is preserved, not deleted:** every trust/feedback entry this persona earned remains in the change logs and
per-wave sections above, and the name stays in `.claude/team/roster.json` (the org-wide commit-identity union
manifest) so the commit-identity gate still resolves her authored commits. She is a **deploy-repo persona**
whose *canonical* card lives in `noorinalabs-deploy/.claude/team/roster/` — only the duplicate parent copy was
retired; she remains active in `noorinalabs-deploy`.

**Owner revision (2026-06-24):** the original #841 slim also retired Bereket Tadesse and Nino Kavtaradze on a
"0 parent commits, ever" premise. That premise was stale by merge time — Bereket authored #832 (merged #846)
and Nino authored #838 (merged #851) and reviewed #835, all in P6W17. Both were **restored** to the parent
roster and the cap raised 8 → 9 to fit them; only the genuine duplicate (Aisha → Lucas) stays retired.

| Persona | Parent role | Reason retired (parent roster) | Last parent-repo commit | Canonical card |
|---------|-------------|--------------------------------|-------------------------|----------------|
| Aisha Idrissi | SRE Engineer | Near-duplicate of SRE Lucas Ferreira (roles merged) + stale (outside last-N-waves window) | 2026-04-21 | `noorinalabs-deploy` (`sre_engineer_aisha.md`) |

Re-instating a retired parent persona is a deliberate, reviewed change (restore the card + drop back under
the headcount budget) — the same surfaced-decision posture the `headcount_budget.py` gate enforces.

---

## Phase 6 Wave 17 Trust Updates (2026-06-25) — Architectural execution + phase exit

> **Genuinely distributed wave** (unlike the W16 meta-wave caveat): 14 per-issue PRs across **9 implementers**,
> top-concentration **28%** (Weronika 4/14) — well under the 0.6 fragility line. Clean wave: **0 CI-red merges,
> 0 must-fix received, 0 rework cycles** across all engineers. Two minor review false-positives (mechanical
> signal, single occurrence each). Deltas are mechanical (`trust_signals.py score 6 17`).

### Org-Level Team (noorinalabs-main)

| Rated | Old | New | Mechanical basis |
|-------|-----|-----|------------------|
| Weronika Zielinska | hold | **+1** | 4 PRs — the wave's deepest architectural work: #845 (per-language derivability re-measure), #853 (tooling bake-off), #854 (Graphiti/graphify eval), #859 (the owned C×T2 structural generator). Top relative performer by volume AND consequence; 0 must-fix, 0 CI-red. Distribution-discipline ratchet. |
| Bereket Tadesse | hold | **+1** | 2 PRs — #860 (cross-repo aggregator) + #846 (env staleness guard); caught + fixed the merge-driver invocation-form bug pre-merge (`from .model import` under plain-script git). 0 must-fix, 0 CI-red. |
| Aino Virtanen (SQL) | 5 | 5 | #858 (Hook 15 → advisory + checksums scope) + #852 (persona Option B governance). At ceiling — hold. Mechanical signal: 1 review false-positive (single occurrence, senior baseline — named, not a decrease). |
| Nino Kavtaradze | hold | hold | #851 (#838 pipe-mask hook) + reviewed #835. Mechanical signal: 1 review false-positive (single occurrence — named gap, held). 0 must-fix, 0 CI-red. |
| Nurul Hakim · Nadia Khoury · Santiago Ferreira · Wanjiku Mwangi | hold | hold | 1 clean on-theme PR each (#850 annunaki precision / #847 trust scoring / #844 status phase-field / #849 wave-scope premise gate). Baseline under §4b — held. |

### Child-Repo Teams

| Rated | Old | New | Mechanical basis |
|-------|-----|-----|------------------|
| Linh Pham (isnad-graph) | hold | hold | #1129 (structural-ontology CI wiring — sibling-checkout + ref resolution). 0 must-fix, 0 CI-red. Baseline — held. (Post-wrap #1132 CVE re-pin not counted in wave-17 scope.) |

### Done Well / Needs Improvement (Phase 6 Wave 17) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|--------|---------------------------|--------------------------------------------|
| **Weronika Zielinska** | C×T2 owned generator + the full bake-off chain (4 PRs) | clean: 0 must-fix received, 0 CI-red |
| **Bereket Tadesse** | aggregator + caught merge-driver invocation-form bug pre-merge | clean: 0 must-fix received, 0 CI-red |
| **Aino Virtanen** | Hook 15 softening + persona governance | 1 review false-positive (single occurrence) |
| **Nino Kavtaradze** | pipe-mask hook (#838) | 1 review false-positive (single occurrence) |
| **All others** | 1 clean on-theme PR each | clean: 0 must-fix received, 0 CI-red — baseline, no ratchet |

**Fire/hire:** none. (#841 persona governance executed this wave: Aisha→Lucas duplicate retired; Bereket + Nino restored after stale-premise correction — owner revision 2026-06-24.)

**Concentration note:** 28% top by implementer — genuine distribution. The W16 retro's caveat ("carry distributed implementer work into W17") was met: architectural execution ran as real fan-out, not orchestrator-solo.

## Phase 7 Wave 18 Trust Updates (2026-06-25) — C×T2 framework rollout (carry-forward lead-in)

**No score changes — all hold.** 11 PRs, one per engineer, 9% concentration (perfectly flat → no distribution-discipline ratchet); 0 CR cycles, 0 CI-red merges, 0 genuine must-fix; no decay triggers (every active member signalled). The only mechanical deltas proposed (Aino −1, Bereket −1, both "review false-positive") are **verified extractor artifacts** and are **rejected, not applied** — see the note below.

### Org-Level Team (noorinalabs-main)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Weronika Zielinska | hold | hold | #873 (extend NODE_KINDS interface/type for TS, #870). 0 must-fix, 0 CI-red. Baseline — held. |
| Santiago Ferreira | hold | hold | #874 (author ontology/README.md, #863). 0 must-fix, 0 CI-red. Baseline — held. |
| Aino Virtanen (SQL) | 5 | 5 | #875 (align framework to C×T2 path, #862) + thorough review on #873. At ceiling — hold. Proposed −1 review-false-positive REJECTED as extractor artifact (see note; #881). |
| Nino Kavtaradze | hold | hold | #876 (standardize merge-driver to plain-script, #871). 0 must-fix, 0 CI-red. Baseline — held. |
| Nurul Hakim | hold | hold | #877 (auto-create Project-2 Wave field option, #868). 0 must-fix, 0 CI-red. Baseline — held. |
| Bereket Tadesse | hold | hold | Substantive approving review on #873 (no authored PR this wave). Proposed −1 review-false-positive REJECTED as extractor artifact (see note; #881). |

### Child-Repo Teams

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Mateo Salazar (user-service) | hold | hold | us#195 — wire C×T2 structural index. 0 must-fix, 0 CI-red. Baseline — held. |
| Aisha Idrissi (deploy) | hold | hold | dep#494 — wire C×T2 structural index stub. 0 must-fix, 0 CI-red. Baseline — held. |
| Astrid Lindqvist (design-system) | hold | hold | ds#131 — wire C×T2 structural index. 0 must-fix, 0 CI-red. Baseline — held. |
| Kofi Mensah-Williams (landing-page) | hold | hold | lp#156 — wire C×T2 structural index (#155). 0 must-fix, 0 CI-red. Baseline — held. |
| Kavitha Sundaramurthy (data-acquisition) | hold | hold | da#215 — wire C×T2 per-repo structural index. 0 must-fix, 0 CI-red. Baseline — held. |
| Yusuke Inoue (isnad-ingest-platform) | hold | hold | ig#117 — wire C×T2 structural index (#116). 0 must-fix, 0 CI-red. Baseline — held. |

**Extractor-artifact note (rejected deltas):** `trust_signals.py score 7 18` proposed −1 for Aino and Bereket on a `review_false_positive` signal. Verified spurious: on **PR #873** both posted `RequestOrReplied: Approved`, and their comment bodies contain "false-positive" only because they were praising the PR's `test_no_false_positive_type_in_non_decl_context` coverage. `_FALSE_POSITIVE_RE` substring-matches approving prose and ignores the Approved verdict. Same misfire recurred from W17 (Aino + Nino). Both deltas rejected; scores held. Bug filed as **#881**, fix in flight at this retro. This is the Step-2.5 "don't narrate a wrong counter as authoritative" discipline applied to trust signals.

### Done Well / Needs Improvement (Phase 7 Wave 18) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|--------|---------------------------|--------------------------------------------|
| **Weronika Zielinska** | TS NODE_KINDS extension (#873), unblocking the TS fan-out | clean: 0 must-fix received, 0 CI-red |
| **Aino Virtanen** | C×T2 framework alignment (#875) + thorough #873 review | review-false-positive signal is a verified extractor artifact (#881), not a real gap; metrics clean |
| **Bereket Tadesse** | substantive approving review on #873 (regex/test-coverage lens) | review-false-positive signal is a verified extractor artifact (#881), not a real gap; metrics clean |
| **Santiago / Nino / Nurul** | 1 clean on-theme main PR each (#874/#876/#877) | clean: 0 must-fix received, 0 CI-red — baseline, no ratchet |
| **Mateo / Aisha / Astrid / Kofi / Kavitha / Yusuke** | C×T2 structural-index wiring in their child repo (1 clean PR each) | clean: 0 must-fix received, 0 CI-red — baseline, no ratchet |

**Fire/hire:** none.

**Concentration note:** 9% top by implementer — the most evenly distributed wave to date (one PR per engineer across all 7 repos). Theme-fit fan-out; no fragility concentration. The W17 caveat ("carry distributed implementer work forward") was met again.

## Phase 7 Wave 19 Trust Updates (2026-06-25) — framework tooling carry-forward + prod-data quality

Mechanical scoring (`trust_signals.py score 7 19`): 9 PRs, 7 engineers, **0 changes-requested cycles**, 0 CI-red merges, 0 must-fix received/caught, top-concentration 33% (Aino, 3/9). The helper proposed Aino +1 (clean 3-PR delivery); **owner decision 2026-06-25 held all engineers flat** — the whole wave was clean-but-unremarkable, no single-reviewer-catch or other ratchet signal, so no deltas this wave. No `review_false_positive` misfires this wave (the #881 extractor bug did not trigger — all false-positive counts 0).

### Org-Level Team (noorinalabs-main)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aino Virtanen | hold | hold | #896 (Hook-4 subshell/compound guard, #894), #895 (lint wiring, #893), #890 (wave_seq reservation-aware, #885). prs_merged=3, 0 must-fix, 0 CI-red. Helper proposed +1; **owner held flat** (clean delivery, no reviewing-catch ratchet). |
| Lucas Ferreira | hold | hold | #891 (narrow validate_pr_review batch-loop guard, #886). 0 must-fix, 0 CI-red. Baseline — held. |
| Nurul Hakim | hold | hold | #892 (board-audit GraphQL pagination + resilient loop, #888). 0 must-fix, 0 CI-red. Baseline — held. |
| Weronika Zielinska | hold | hold | #889 (ontology_gen depth-aware TS extends splitter, #887). 0 must-fix, 0 CI-red. Baseline — held. |

### Child-Repo Teams

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Alejandra Reyes-Fuentes (data-acquisition) | hold | hold | da#218 (ADR-003 sanadset orphan + narrator-pollution investigation A/B, da#202). 0 must-fix, 0 CI-red. Baseline — held. |
| Kavitha Sundaramurthy (data-acquisition) | hold | hold | da#217 (honor explicit None as load-all in HADITH_COMPOSITION, da#196). 0 must-fix, 0 CI-red. Baseline — held. |
| Nneka Obi (isnad-graph) | hold | hold | ig#1133 (repair prod full-text starvation + semantic 500, ig#1110). 0 must-fix, 0 CI-red. Baseline — held. |

### Done Well / Needs Improvement (Phase 7 Wave 19) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|--------|---------------------------|--------------------------------------------|
| **Aino Virtanen** | 3 clean framework-hardening PRs (#896/#895/#890) — Hook-4 guard, lint wiring, wave_seq reservation | clean: 0 must-fix received, 0 CI-red, 0 false-positives |
| **Lucas / Nurul / Weronika** | 1 clean on-theme main PR each (#891/#892/#889) — guard-narrowing, board-audit pagination, TS extractor | clean: 0 must-fix received, 0 CI-red — baseline, no ratchet |
| **Alejandra / Kavitha** | data-quality fixes in data-acquisition (da#218 investigation, da#217 parser) | clean: 0 must-fix received, 0 CI-red — baseline, no ratchet |
| **Nneka Obi** | prod search repair (full-text starvation + semantic 500, ig#1133) | clean: 0 must-fix received, 0 CI-red — baseline, no ratchet |

**Fire/hire:** none.

**Concentration note:** 33% top by implementer (Aino, 3/9) — below the 60% fragility threshold. Theme-fit: Aino owns the framework-tooling surface this wave themed on. No redistribution action required.

**Process note (not a per-engineer signal):** two wave→main *integration* PRs needed orchestrator fix-forward — #898 (squash collapsed persona authorship → commit-author gate) and da#222 (child structural index not regenerated for a new `.cypher`). Neither is an implementer must-fix (the per-issue PRs were clean); both are orchestrator/process gaps now codified — **Hook 22** (`block_squash_wave_merge`) + **`/wave-wrapup` Step 10.7** (child structural pre-regen). See this wave's feedback_log entry.

## Phase 7 Wave 20 Trust Updates (2026-06-26) — graph integrity + dedup + chains

Mechanical scoring (`trust_signals.py score 7 20`): 6 PRs, 5 implementers, **0 changes-requested cycles**, 0 CI-red merges, 0 must-fix received/caught, top-concentration 33% (Alejandra, 2/6). The helper proposed Alejandra +1 (clean 2-PR delivery); she is already at ceiling **5**, so the bump is absorbed (`clamp(5+1)=5`). All other engineers delta 0 (a single clean PR is not a bump). No `review_false_positive` misfires. Baseline-hold wave — same shape as W18/W19: clean-but-unremarkable, no single-reviewer-catch or other ratchet signal.

**Validation note:** the W19 process changes proved out this wave — **Hook 22** silently did its job (every per-issue PR merged with `--merge`; no squash attempt to block) and **Step 10.7** (child structural pre-regen) meant both wave→main PRs (da#231, ig#1136) were green on staleness-check from the first push, with **zero** fix-forward scrambles (vs two in W19). The two pain points that drove W19's codification did not recur.

### Child-Repo Teams (data-acquisition + isnad-graph)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Alejandra Reyes-Fuentes (data-acquisition) | 5 | 5 | da#224 (Path B/B1 — emit `collections_sanadset.parquet` foundation, da#219) + da#227 (Path B parent integration verify, da#202). prs_merged=2 (wave top), 0 must-fix, 0 CI-red. Helper proposed +1; **absorbed at ceiling**. Led the two coupled B1+parent items per kickoff plan. |
| Kavitha Sundaramurthy (data-acquisition) | 5 | 5 | da#225 (cross-edition canonical-identity dedup, Path B/B2, da#220). 0 must-fix, 0 CI-red. Baseline — held at ceiling. |
| Ivana Horvat (data-acquisition) | 5 | 5 | da#226 (narrator re-segmentation — `<NAR>` firehose filter, Path B/B3, da#221). 0 must-fix, 0 CI-red. Baseline — held at ceiling. |
| Nikolaos Papadopoulos (data-acquisition) | 5 | 5 | da#223 (da#153 integrity sweep — explicit-null / no-fabrication contracts + inventory). 0 must-fix, 0 CI-red. Baseline — held at ceiling. |
| Jun-Seo Park (isnad-graph) | 4 | 4 | ig#1135 (`GET /validate/chains` — chronological isnad plausibility, ig#1040). 0 must-fix, 0 CI-red. Baseline — held (at 4 since W4). |

### Done Well / Needs Improvement (Phase 7 Wave 20) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|--------|---------------------------|--------------------------------------------|
| **Alejandra Reyes-Fuentes** | 2 clean coupled PRs on the Path B spine (da#224 B1 foundation + da#227 parent integration verify) — the orphan-resolution acceptance gate | clean: 0 must-fix received, 0 CI-red, 0 false-positives |
| **Kavitha / Ivana / Nikolaos** | 1 clean on-theme data-acquisition PR each (da#225 dedup / da#226 re-segmentation / da#223 integrity contracts) | clean: 0 must-fix received, 0 CI-red — baseline, no ratchet |
| **Jun-Seo Park** | chain-validation endpoint shipped clean (ig#1135 `GET /validate/chains`) — doubles as the segmentation regression signal | clean: 0 must-fix received, 0 CI-red — baseline, no ratchet |
| **Reviewers** (Kavitha, Nikolaos, Ivana, Mateo Salazar, Aisling Brennan, Oyunbileg Batbayar, Kwesi Boateng, Jean-Claude Habimana) | 2 first-pass approvals per PR, 0 CR cycles wave-wide | clean: 0 must-fix-caught because 0 must-fixes existed — no reviewing ratchet either way |

**Fire/hire:** none. Retirement trigger (`trust_signals.retirement_trigger`) fired for no engineer — no bottom-tier-or-CI-red streak.

**Concentration note:** 33% top by implementer (Alejandra, 2/6) — below the 60% fragility threshold. Theme-fit: Path B's sanadset parsing lives in data-acquisition and Alejandra owns the B1+parent coupling by design. No redistribution action required. 5 of 6 implementer-issues in data-acquisition is inherent to the Path B theme, spread across 4 da personas — not fragility.

## Phase 7 Wave 21 Trust Updates (2026-06-26) — narrator dating foundation + prod re-validation

Mechanical scoring (`trust_signals.py score 7 21`): **11 PRs** (10 data-acquisition + 1 isnad-graph), 5 implementers, top-concentration **27%** (Alejandra & Kavitha tied at 3/11), **0 CI-red merges**, 0 `review_false_positives`. Helper-proposed deltas: Alejandra/Kavitha/Ivana/Nikolaos **+1** (clean multi-PR delivery) — all four already at ceiling **5**, so absorbed (`clamp(5+1)=5`); Jun-Seo Park **+0** (single clean PR is not a bump) — held at **4**. Distribution discipline: no new 5s handed out; the four ceiling-holders earned theirs in prior waves.

**Measurement-conflict note (load-bearing — same class as the CR-cycle counter):** the helper reports `must_fix_received=0` and `must_fix_caught=0` for **every** engineer, but this wave had **4 genuine changes-requested cycles** (da#161/#233, da#228/#235, da#165/#241, ig#1039/#1137) that caught **real data-correctness defects** — `TRANSMITTED_TO` provenance-row fabrication, `narrators_dated` always-0 count, single-source range→EXACT precision over-claim, and order-dependent consensus-band widening. All four verdicts were **edited-in-place to Approved** per the charter verdict-amendment rule, which erased the `must_fix_*` surface the helper reads. Per `wave_21_counter_corrections`, the wrapup-time historic **CR-cycles=4 stands as authoritative-historic**; the recomputed 0 is the amendment artifact, NOT a correction. Consequence for trust: the reviewers who made these catches (Kavitha, Nikolaos, Kwesi Boateng, Aisling Brennan) get **no mechanical `must_fix_caught` credit** this wave even though they did substantive catching — a known gap in mechanical scoring vs verdict-amendment, surfaced as a W21 pain point.

### Child-Repo Teams (data-acquisition + isnad-graph)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Alejandra Reyes-Fuentes (data-acquisition) | 5 | 5 | da#233 (DatePrecision model + date bounds, da#161 root), da#241 (multi-source date reconciliation, da#165), da#236 (collection metadata enrichment, da#230). prs_merged=3 (wave top, tied). Helper proposed +1; **absorbed at ceiling**. da#241 absorbed a real must-fix (single-source range→EXACT over-claim) and shipped the fix clean. |
| Kavitha Sundaramurthy (data-acquisition) | 5 | 5 | da#237 (extend `NARRATORS_CANONICAL_SCHEMA`, da#162), da#235 (mention-link 8 orphan muhaddithat + provenance, da#228), da#234 (in-book ordinal, da#229). prs_merged=3 (wave top, tied). da#235 absorbed the `TRANSMITTED_TO` provenance-fabrication must-fix. Held at ceiling. |
| Ivana Horvat (data-acquisition) | 5 | 5 | da#240 (death-anchored narrator-date extraction, da#164), da#238 (geographic disambiguation stage, da#139). prs_merged=2, 0 CI-red. Held at ceiling. |
| Nikolaos Papadopoulos (data-acquisition) | 5 | 5 | da#242 (ṭabaqa→estimated-window fallback, da#166), da#232 (`src/utils/hijri.py` AH↔CE + pin convertdate, da#163). prs_merged=2, 0 CI-red. Also reviewed/caught on the foundation chain. Held at ceiling. |
| Jun-Seo Park (isnad-graph) | 4 | 4 | ig#1137 (loader writes resolved narrator date props to Neo4j + `_active_window` enricher upgrade, ig#1039). prs_merged=1, 0 CI-red. Absorbed the `narrators_dated` always-0 count must-fix and shipped the `RETURN count(n) AS matched` fix. Single clean PR — not a bump; held at 4. |

### Done Well / Needs Improvement (Phase 7 Wave 21) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|--------|---------------------------|--------------------------------------------|
| **Alejandra Reyes-Fuentes** | 3 PRs across the date-foundation spine (model root da#233 → reconcile da#241 → metadata da#236); clean fix on the range→EXACT precision defect | clean: 0 CI-red, 0 false-positives, prs_merged=3 — must_fix_received understated by edit-in-place (see conflict note) |
| **Kavitha Sundaramurthy** | 3 PRs (schema da#237, muhaddithat-link da#235, ordinal da#234); absorbed the TRANSMITTED_TO fabrication catch on da#235 | clean: 0 CI-red, 0 false-positives, prs_merged=3 |
| **Ivana Horvat** | death-anchored date parser (da#240) — the extraction heart of the chain — + geo disambiguation (da#238), both clean | clean: 0 CI-red, 0 false-positives, prs_merged=2 |
| **Nikolaos Papadopoulos** | hijri conversion util + convertdate pin (da#232) and ṭabaqa fallback (da#242) — the two arithmetic-sensitive ends of the chain, clean | clean: 0 CI-red, 0 false-positives, prs_merged=2 |
| **Jun-Seo Park** | cross-repo Neo4j loader for date props (ig#1137) — the single isnad-graph consumer of the da chain; fixed the always-0 count under review | clean: 0 CI-red, prs_merged=1 — single PR, no ratchet; held at 4 |
| **Reviewers** (Kavitha, Nikolaos, Kwesi Boateng, Aisling Brennan, Mateo Salazar, + slate) | **4 substantive defect catches** across da#233/#235/#241/#1137 — fabrication, always-0, precision over-claim, order-dependent widening; all with regression tests that fail on pre-fix code | `must_fix_caught` shows 0 mechanically (verdicts edited-in-place to Approved) — real catching is uncredited by the helper; see measurement-conflict note |

**Fire/hire:** none. Retirement trigger (`trust_signals.retirement_trigger`) fired for no engineer.

**Concentration note:** 27% top by implementer (Alejandra & Kavitha tied 3/11) — below the 60% fragility threshold. Theme-fit: narrator dating lives in data-acquisition (10/11 PRs); ig#1039 is the single isnad-graph loader. Load spread across 5 da personas + 1 ig persona. Not fragility.
