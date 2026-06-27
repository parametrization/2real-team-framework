# Tech Preferences & Decision-Making

## Individual Preferences <!-- promotion-target: none -->
Each team member tracks their **stack, tooling, library, and cloud preferences** in a `## Tech Preferences` section of their roster card. Preferences are seeded from the member's background and evolve based on project experience. When a preference changes, update the roster card.

## Debate & Consensus <!-- promotion-target: none -->
- Team members may take input from each other and from repo-level teams.
- Team members can **debate** tooling/process/standards choices to arrive at the best solution.
- If consensus is reached, the agreed-upon choice is adopted.

## Tie-Breaking: Least Common Ancestor <!-- promotion-target: none -->
When agreement cannot be reached between parties, the decision escalates to the **least common ancestor (LCA) in the org chart**. The LCA makes the best decision they can and the team moves forward.

| Disagreement between | LCA / Decision-maker |
|----------------------|---------------------|
| TPM ↔ Release Coordinator | Program Director (Nadia) |
| TPM ↔ Standards Lead | Program Director (Nadia) |
| Release Coordinator ↔ Standards Lead | Program Director (Nadia) |
| Any org-level member ↔ repo manager | Program Director (Nadia) |

## Base Image Pinning <!-- promotion-target: none -->

All Dockerfile `FROM` statements MUST use a **digest-pinned tag** combined with an in-image package upgrade. This closes two failure modes that were each individually surfaced — floating-tag drift and within-tag package drift — by combining the two defenses.

**Required pattern (Alpine-based images):**

```dockerfile
# Digest-pinned tag + apk upgrade for defense-in-depth
FROM nginx:stable-alpine3.23@sha256:0272e460...
RUN apk upgrade --no-cache
```

**Equivalent for other distro families:**

| Family | Pin shape | Upgrade command |
|---|---|---|
| Alpine | `image:tag@sha256:digest` | `RUN apk upgrade --no-cache` |
| Debian-slim | `image:tag@sha256:digest` | `RUN apt-get update && apt-get -y upgrade && apt-get clean && rm -rf /var/lib/apt/lists/*` |
| Distroless | `image:tag@sha256:digest` | none — no package manager (pinned-only is sufficient) |
| Multi-stage with `scratch` final | final layer pinned by upstream stage's digest | n/a (final layer has no package manager) |

**What is prohibited:**

```dockerfile
# WRONG (floating tag): pulls latest at build time; no reproducibility
FROM nginx:alpine

# INSUFFICIENT (pin-only): tag is frozen but Alpine packages drift inside the
# pinned digest's lifetime. CVE class re-emerges silently. This is exactly
# the shape isnad-graph#853 hit.
FROM nginx:stable-alpine3.23@sha256:...

# INSUFFICIENT (apk-only): always-current packages but base layer drifts
# unpredictably; build-time-dependent.
FROM nginx:alpine
RUN apk upgrade --no-cache
```

**Acceptable exemptions:**

- `scratch` final layer in a multi-stage build — final image has no package manager; the upstream stages still follow this rule.
- Vendor-supplied images that are not redistributable as digest-pinned (rare; document the exemption inline as a `# RATIONALE:` comment on the `FROM` line).

**Reviewer enforcement:** Absence of a digest pin OR absence of the upgrade step on a `Dockerfile` PR is grounds for `ChangesRequested`. The pattern is mechanical; reviewers cite this section.

**Promotion path:** This is step 1 + 2 (charter + memory) of the [enforcement hierarchy](hooks.md). A future `validate_dockerfile_base_pin` PreToolUse hook (step 3) is filed if the convention proves load-bearing across multiple Dockerfile PRs without manual reviewer reminders.

**Why:** Surfaced by Linh-review during P3W3 review of `noorinalabs-isnad-graph#854` (Idris-853's Trivy CVE fix). The combined `digest-pin + apk upgrade` pattern Idris chose was the right shape but had no normative reference; without it the next Dockerfile author would default to a floating `nginx:alpine` (the failure shape that produced #853 in the first place). Codifying the pattern closes that gap.

**Scope:** Applies to all repos under the `noorinalabs` org. Companion issue tracks digest-pin freshness via Renovate/Dependabot (pin-rot is the inverse failure mode — pins must be updated on a cadence, never frozen indefinitely).

## Per-Env OAuth Provisioning <!-- promotion-target: none -->

Every deployment environment (`stg`, `prod`, future `dev` / `canary`) gets its **own** Google OAuth client and its own GitHub OAuth app. They are never shared across environments.

The four `AUTH_GOOGLE_CLIENT_ID/SECRET` + `AUTH_GITHUB_CLIENT_ID/SECRET` secrets resolve from GitHub Environments **env-scope**, not org-scope. Same secret names across envs; env-scope encodes which env you are in.

**Why per-env, not shared:**

- **Google publishing-status is per-app** — `prod` must run `In Production`, `stg` must run `Testing`. The same OAuth app cannot be both.
- **Credential isolation** — a leaked stg credential does not affect prod login.
- **Metrics & quota separation** — prod analytics aren't polluted by stg test traffic.
- **Redirect URI hygiene** — each app's allowed-URI list contains only its env's callback (`/auth/callback` on the env's host).

**How (operations):** see [`noorinalabs-deploy/docs/runbooks/oauth-per-env.md`](https://github.com/noorinalabs/noorinalabs-deploy/blob/main/docs/runbooks/oauth-per-env.md) for the 4-step provisioning + rotation procedure and the redirect-URI convention table.

**Adjacent conventions:** env-scope-by-default for service-internal secrets (`USER_POSTGRES_*`, `JWT_*`, `KAFKA_*`, `NEO4J_PASSWORD`) per [secrets-audit § 3.9](../../../docs/secrets-audit-2026-04-24.md). OAuth credentials follow the same env-scope pattern; this convention codifies the "per-env" requirement that makes the env-scope pattern necessary in the first place.

**Promotion provenance:** Surfaced from [deploy#244](https://github.com/noorinalabs/noorinalabs-deploy/issues/244) — runbook landed in deploy repo, but the org-wide convention is the right altitude for charter. Filed as main#240 to capture in this charter so future env splits inherit the pattern from day 1 instead of re-deriving it from incident reflection.

## Ontology-vs-graphify — owner decision <!-- promotion-target: none -->

**Status:** spike complete (main#728, P6W2); owner decision **pending**.

The three-role ontology stack (Tracker hook → `checksums.json`, Resolver `/ontology-rebuild`,
Librarian `/ontology-librarian`, + Hook-15 consult gate) was spiked against a Google
LLM-doc-format (`llms.txt`) + graphify approach. Full analysis and the four-axis comparison live in
[`.claude/team/spikes/p6w2-ontology-vs-graphify.md`](../spikes/p6w2-ontology-vs-graphify.md);
the owner-decision stub is in [`phase-6.md`](../phases/phase-6.md) §criterion #4.

**Spike recommendation — Hybrid:** auto-derive the code-structural layer (measured 100% derivable —
54/54 modules self-document — in ~60 LOC, vs the current 1,347 LOC of freshness machinery + 1,760
lines of curated payload + a per-edit Hook-15 tax), retain hand-curated **semantics/intent** (domain
entities, service topology, ADR "why") as low-churn markdown, and soften Hook 15 to advisory.

**Decision options:** ☐ Keep ☑ Hybrid ☐ Replace. (Spike recommendation adopted as the
**C×T2** decision, tracked under [#820](https://github.com/noorinalabs/noorinalabs-main/issues/820).)
The earlier 2026-06-20 "no teardown in Phase 6" note is superseded — the owner greenlit the
Hybrid implementation in **P6W17** under #820.

**Implementation (P6W17, #820 / C×T2):**
- [#855](https://github.com/noorinalabs/noorinalabs-main/issues/855) — owned generator building the
  regenerable **structural** layer at `ontology/structural/`.
- [#857](https://github.com/noorinalabs/noorinalabs-main/issues/857) — Hook 15 softened from hard
  block → **advisory** (`systemMessage`, never denies), and the change-tracker/`ontology-rebuild`
  machinery **retired for the structural layer** (the tracker skips `ontology/structural/`; the
  resolver never touches it). The hand-curated **semantic overlay**
  (`domain.yaml`/`services.yaml`/`conventions.md`/`repos/*.yaml`/`*.md`) **retains** its tracker +
  resolver. The Hook-15 softening is safe because the structural context the block guarded is now
  current-by-regeneration, not stale.

This entry is updated in place as the remaining C×T2 streams (#3b aggregator/overlay, #3d
isnad-graph wiring) land.
