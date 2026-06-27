# Work Delegation & Issue Management

## Delegation Flow <!-- promotion-target: skill -->
1. **Program Director decomposes cross-repo requirements** and delegates each to the appropriate team member (TPM, Release Coordinator, or Standards & Quality Lead) based on domain.
2. **The assigned team member creates GitHub Issues** in the appropriate repository with clear acceptance criteria.
3. For cross-repo work, the Program Director creates **meta-issues** in `noorinalabs-main` that link to per-repo issues.

## Issue Review Process <!-- promotion-target: none -->
Every newly created cross-repo issue receives a review pass from each of the following roles. **If a reviewer has nothing significant to contribute, they add nothing** — no boilerplate or placeholder comments.

| Reviewer | Applies to |
|----------|-----------|
| Technical Program Manager (Wanjiku) | All cross-repo issues — dependency and timeline review |
| Release Coordinator (Santiago) | Issues affecting releases, versioning, or deployment sequencing |
| Standards & Quality Lead (Aino) | Issues affecting org-wide conventions, hooks, or charter rules |

Reviews may include: dependency concerns, timeline conflicts, release impact, standards compliance, or cross-team blockers. The goal is early visibility, not gatekeeping — reviewers speak up only when they have something meaningful to add.

## Work Gate: Issues Before Implementation <!-- promotion-target: none -->
**No team member may begin implementation work or delegate it to repo teams until ALL GitHub Issues for the current initiative have been:**

1. **Created** — the full set of issues covering the initiative's requirements exists.
2. **Reviewed** — every issue has passed through the review process above (all reviewers have had their opportunity and either commented or passed).

Only after both conditions are met does the Program Director signal that implementation may begin. This ensures the entire initiative is planned, visible, and vetted before any work starts.

## Issue-Filing Premise Verification at Origin HEAD <!-- promotion-target: none -->

<!-- Promoted from W15 retro proposed process change #1 (owner-approved 2026-06-02) -->

**Any issue whose body cites a gap, bug, or missing feature in a repository's code MUST have that premise verified against the target repo's `origin/main` HEAD at filing time** — not against a sibling issue's body, a meta-issue snapshot, another repo's description of the gap, or memory of the codebase.

Verification means at least one of:
- `gh api "repos/noorinalabs/<repo>/contents/<path>?ref=main"` confirming the cited file/code state
- `gh search code` / `gh api` grep confirming the claimed-missing symbol genuinely absent at HEAD
- `git log origin/main -- <path>` confirming no later commit already addressed the gap

**Why:** P3W15 incident — ig#943 was filed as a "new" isnad-graph gap from deploy#245's stale body snapshot; the work was already merged. Cost: a phantom scope row, an implementer reassignment, and a board repair. This is the issue-filing counterpart of the implementer-class `investigate-before-implement` rule and the reviewer-class `origin-over-local` rule: **every role class that asserts repository state verifies it at origin first.**

This applies to ALL issue-filing surfaces: orchestrator, team members, `/file-bug`, and skills that auto-file issues.

## Wave Planning — Project Board Is Authoritative <!-- promotion-target: skill -->

Wave and phase planning MUST begin with the full project board as the candidate pool, not with the subset of issues carrying a wave label (`wave-{X}` or grandfathered `p{N}-wave-{M}`, main#810) or listed in a meta-issue body.

1. **Source of truth:** project 2 (`gh project item-list 2 --owner noorinalabs`). Every open issue across all repos should appear there.
2. **Labels are post-scoping tags**, not pre-scoping filters. When a wave is planned, in-scope issues get labeled; the labels document decisions but do not bound which issues could have been considered.
3. **Meta-issue bodies document declared scope** and carry the wave narrative, but they do not replace the board audit.

**Pre-wave drift audit:** before a wave-scoping pass, verify every repo's open issues are on the board. Hook 13 (`auto_add_issue_to_board.py`) auto-adds issues created via our in-session `gh issue create` calls, but externally created issues (manual UI creation, bot PRs, cross-repo-dispatch-triggered issues) slip past. Run:

```bash
for repo in noorinalabs-main noorinalabs-isnad-graph noorinalabs-user-service \
           noorinalabs-deploy noorinalabs-design-system noorinalabs-landing-page \
           noorinalabs-data-acquisition noorinalabs-isnad-ingest-platform; do
  gh issue list --repo "noorinalabs/$repo" --state open --limit 500 --json url --jq '.[].url'
done | sort -u > /tmp/all_open.txt

gh project item-list 2 --owner noorinalabs --format json --limit 1000 \
  --jq '.items[] | select(.content.url) | .content.url' | sort -u > /tmp/board_urls.txt

comm -23 /tmp/all_open.txt /tmp/board_urls.txt
```

Any URL printed by the final `comm` is an open issue missing from the board — add it via `gh project item-add 2 --owner noorinalabs --url <url>` before scoping.

**Why:** On 2026-04-23, running this check during P2W10 execution revealed **72 of 193 open issues (37%) were missing from the board**. Those issues were invisible to any wave-planning pass that read labels or meta-issue bodies. Planning from labels alone systematically excludes work the team forgot to triage.

**Skill:** `/board-audit` (main#199) automates both the orphan-detection check above AND the wave-label → project Wave-field sync (`wave-{X}`→`W{X}`, grandfathered `p{N}-wave-{M}`→`P{N}W{M}`, main#810). Labels are canonical for phase/wave assignment; the project's `Wave` single-select field is a **derived projection** of labels, maintained by `/board-audit`. The skill is wired into `/wave-kickoff`, `/wave-retro`, and `/session-start` step 5 so the board stays current at every wave boundary. Manual invocation is also valid whenever drift is suspected.

## Multi-Step Meta-Issue Freshness Re-Audit <!-- promotion-target: skill -->

A meta-issue's enumerated scope is a snapshot of HEAD at filing time, not a standing claim. Parallel work lands in the same repos between filing and next-pass implementation, so the longer the gap, the more the body drifts from ground truth.

**Trigger:** A **multi-step meta-issue** (one whose scope is enumerated as a list of files, repos, or per-step acceptance criteria) that is **older than 48 hours at next-pass implementation** requires the implementer brief to **begin with a HEAD audit, per repo named in the issue**. The audit MUST precede any Edit/Write. Single-step issues (one acceptance criterion referencing one file/symbol) are exempt — they are covered by the existing pre-spawn file-existence verify, not this re-audit.

Why 48 hours: within the window the body tracks filing-time state closely enough for a routine brief; beyond it, parallel PR closures and `gh issue` events in the named repos have typically had a chance to land and must be cross-referenced before spawning.

**Audit deliverable** (produced before the first implementer is spawned):

1. **Per-repo HEAD-state summary** — `file:line` refs for each scope element, read at the wave-branch HEAD via `gh api repos/<owner>/<repo>/contents/<path>?ref=<head_sha>` (per [`pull-requests.md` § Origin > Local Clone for "Still-Has-X" File-Content Claims](pull-requests.md)), not the working tree.
2. **Comparison against the meta-issue's enumerated scope** — element by element.
3. **Per-element verdict** — one of `STILL TODO` / `ALREADY DONE` / `SCOPE CHANGED` / `NEW ITEM SURFACED`.
4. **Audit finding posted as a COMMENT on the meta-issue, NOT a body edit.** Editing the body erases the record that scope shrank; the comment preserves the audit trail of the reduction (per the audit-as-comment precedent in [Comment Format](#comment-format) — same reasoning as drift-evidence on an existing issue).

The orchestrator then briefs only the `STILL TODO` / `SCOPE CHANGED` / `NEW ITEM SURFACED` elements; `ALREADY DONE` elements are dropped from the spawn plan and the spawn count is recomputed against the audited scope, never the body's original enumeration.

**Why:** caught twice in one P3W12 session. On `noorinalabs-main#536` (Node.js 20→24 cross-repo sweep) the body still listed all 5 repos as todo two days after filing, but 4 had already merged direct-to-main within hours — the HEAD audit cut 5 planned implementer spawns to 1. On `noorinalabs-deploy#245` (vhost carve-out) a step listed as todo a month after filing was already done in isnad-graph commit `1a6f2ae`; the audit reduced a planned 3-PR sweep to 2 in-scope PRs plus one sibling issue, filed as a comment to keep the scope-reduction trail. Memory `feedback_pre_spawn_verify_file_existence_at_head` covers the *what* (verify file existence at HEAD); this section encodes the *when* — the 48-hour threshold that tells operators a multi-step meta-issue is stale enough to re-audit.

## Pre-Wave Checklist <!-- promotion-target: skill -->
Before any wave begins, the Manager must verify:

1. **Roster validation** — all assigned engineers exist in the org-level `roster.json`. If missing, add them before work begins. This prevents commit identity blockers.
2. **CI workflow exists** — the repo has a working CI workflow that triggers on `deployments/**` branches. If this is Wave 1 of a new repo/phase, the scaffolding issue MUST include a CI workflow. No Wave 2 work starts without CI running.
3. **Critical-path work identified** — if a task blocks others, that engineer is spawned first with priority.

## Implementation Kickoff & Issue Assignment <!-- promotion-target: none -->
Once the work gate is cleared, the Program Director delegates to the appropriate repo teams via their respective managers.

### Assignment

- Issues are assigned via a GitHub label: **`FIRSTNAME_LASTNAME`** (e.g., `NADIA_KHOURY`).
- Each team member works only on issues labeled with their name.
- **No branch may be created without an existing ticket.** The branch name must reference the issue number (per [Branching Rules](branching.md)).

### Reassignment on Termination

When a team member is fired:
1. Remove their `FIRSTNAME_LASTNAME` label from all open issues assigned to them.
2. The Program Director reassigns each issue to an appropriate person — an existing team member or a new hire.
3. The new assignee's label is applied.

### Manual Issues

Issues that require a human to complete (e.g., configuring a third-party dashboard, signing up for a service, uploading credentials) MUST have their title prefixed with `[MANUAL]`. Example: `[MANUAL] Enable GitHub Pages in design-system repo settings`.

- A `[MANUAL]` issue does **not** require a PR (though one may accompany it)
- It is closed when the human confirms the action is done (via issue comment)
- Agents may create `[MANUAL]` issues when they identify work they cannot perform

### Issue Hygiene

Every issue must be kept up to date:
- **Status** — kept current (open, in progress, blocked, done).
- **Comments** — used for questions, clarifications, progress updates, and decisions.
- **Close condition** — issues are closed **only** when the corresponding work is complete and verified. Do not close prematurely. For `[MANUAL]` issues, the human confirms completion via comment.

## End-State Criterion: Delivered vs. Applied-and-Verified-at-Origin <!-- promotion-target: none -->

An **end-state criterion** (or any rollout/enforcement issue) is **MET only when the mechanism is APPLIED and verified at origin via API — not when the spec, script, or hook that would apply it is merely *delivered***. "Delivered" (the spec/PR/script exists) and "applied" (the live system actually enforces it) are distinct states; a criterion-tracking issue MUST distinguish them and stay OPEN as the rollout tracker until *applied-and-verified* is true for every target.

**Rule.** Before framing or closing a criterion as met, verify the enforcing state at origin with the authoritative API for that mechanism, and cite the verification. Examples of the right probe per mechanism:
- **Branch-protection / rulesets** (criterion #4 / #322): `gh api repos/<owner>/<repo>/rulesets` (and `.../rulesets/<id>`) returns the ruleset with the expected required-check contexts — for **every** target default branch, not just the pilot. The spec + hook + one pilot is *delivered*; the criterion is *met* only once the ruleset is read-back-confirmed on all 8 default branches.
- **CI gate live** (e.g. sync-drift, docs): the gate job appears and is green in the latest default-branch run (`gh api .../actions/runs?branch=main` / `statusCheckRollup`), not just present in the workflow file on a feature branch.
- **Staging-green** (criterion #3 / #325): a successful `deploy-stg` run exists in run history, not just a `deploy-stg.yml` that *would* run.

**Why:** a spec or script that is merged but never applied leaves the criterion's protection entirely absent while the issue's framing implies it is in place — the exact gap behind #322 (specs+scripts delivered, ruleset unapplied) and the 12-day-red GHCR publish (workflow present, latest default-branch run failing). Aligns with [`pull-requests.md` § Branch Protection — criterion #4](pull-requests.md) ("criterion #4 is met only when the W14 rollout has applied the ruleset to all 8 default branches") and `feedback_honest_audit_over_conclusion_claim` (an honest open-item count before any "done" claim). The discipline generalizes that per-criterion note into a standing rule: deliverable-exists ≠ criterion-met; the origin-verified applied state is the close condition.

**Disposition shorthand:** while the mechanism is delivered-but-not-fully-applied, the tracking issue uses `Refs #N` on the delivering PR (NOT `Closes #N`) and stays open as the rollout tracker; it is closed only after the applied-and-verified-at-origin check passes for all targets. (`Closes` on a wave-branch PR would not fire anyway — see `feedback_wave_branch_issue_close` — but the substantive reason is the delivered-vs-applied distinction, not the merge mechanics.)

<!-- Promoted from: P3W14 retro (2026-06-01) Proposed Process Change #3, owner-approved. Rationale: #322 specs+scripts delivered but unapplied; GHCR publish red on main 12 days undetected. Generalizes pull-requests.md § criterion #4's per-criterion note into a standing close-condition rule. -->

## Comment Format <!-- promotion-target: none -->
All issue comments MUST follow this format:

```
Requestor: Firstname.Lastname
Requestee: Firstname.Lastname
RequestOrReplied: Request

<actual comment body>
```

- **Requestor** = the person writing the comment.
- **Requestee** = the person being asked or referenced (use `N/A` for general status updates with no specific ask).
- **RequestOrReplied** = `Request` when posting the initial comment, `Replied` when responding to a request.

## Reply Protocol <!-- promotion-target: none -->
When a team member is tagged as **Requestee** on a comment with `RequestOrReplied: Request`, they **must** respond with a new comment on the same issue using this format:

```
Requestor: Firstname.Lastname   <- (was the original Requestee)
Requestee: Firstname.Lastname   <- (was the original Requestor)
RequestOrReplied: Replied

<reply body>
```

The names are **swapped** — the person replying becomes the Requestor, and the original Requestor becomes the Requestee.

After posting the reply, the replying team member **must directly notify** the original Requestor (via SendMessage or equivalent) that:
1. A reply has been posted on the issue.
2. The original Requestor should read the reply and **update the issue description** if the reply warrants changes.

## Ticket Update Rules Based on Ownership <!-- promotion-target: none -->
The **ticket owner** is the team member whose `FIRSTNAME_LASTNAME` label is on the issue.

- **Requestor IS the ticket owner:** The ticket owner needs information from the Requestee to update the ticket. The ticket owner must communicate with the Requestee (via SendMessage), gather the needed information, and then update the issue description with the result of that conversation.

- **Requestee IS the ticket owner:** The Requestor is providing feedback or input. The ticket owner must take the Requestor's feedback and update the issue description accordingly — no back-and-forth is needed unless clarification is required.

## Escalation & Cross-Team Clarification <!-- promotion-target: skill -->
When a ticket needs clarification or feedback from another team member:
1. Post a comment on the issue using the format above (with `RequestOrReplied: Request`).
2. Notify the Program Director if needed.
3. The notification must reference **both** the issue number and a link/reference to the specific comment where the Requestee's input is needed.
