# Generic Charter: Tech Preferences & Decision-Making

## Purpose

A template for how a team records technology preferences, debates tooling
choices, and breaks ties — plus a couple of durable, product-neutral technical
conventions that are worth codifying once so every future change inherits them
instead of re-deriving them from incident reflection.

## Individual preferences

Each team member tracks their **stack, tooling, library, and infra
preferences** in a dedicated section of their roster/profile card. Preferences
seed from the member's background and evolve with project experience. When a
preference changes, update the card — the card is the source of truth, not
memory of a past conversation.

## Debate & consensus

- Members may take input from each other and from sub-teams.
- Members may **debate** tooling / process / standards choices to reach the best
  solution.
- If consensus is reached, the agreed choice is adopted.

## Tie-breaking: least common ancestor

When agreement cannot be reached, the decision escalates to the **least common
ancestor (LCA) in the org chart**. The LCA makes the best call they can and the
team moves forward. Build the escalation table from your actual org chart:

| Disagreement between | LCA / decision-maker |
|----------------------|----------------------|
| Peer ↔ Peer (same manager) | That shared manager |
| Member ↔ sub-team manager | The next common manager up |
| Cross-org-level dispute | The senior coordinator both report through |

## Convention: base-image pinning (defense in depth)

All container `FROM` statements MUST combine a **digest-pinned tag** with an
**in-image package upgrade**. This closes two independent failure modes —
floating-tag drift and within-tag package drift — that each surface on their own.

**Required pattern:**

```dockerfile
# Digest-pinned tag + package upgrade for defense-in-depth
FROM <image>:<tag>@sha256:<digest>
RUN <package-manager upgrade>
```

| Distro family | Pin shape | Upgrade command |
|---|---|---|
| Alpine | `image:tag@sha256:digest` | `apk upgrade --no-cache` |
| Debian-slim | `image:tag@sha256:digest` | `apt-get update && apt-get -y upgrade && apt-get clean && rm -rf /var/lib/apt/lists/*` |
| Distroless | `image:tag@sha256:digest` | none — no package manager |
| Multi-stage `scratch` final | final layer pinned by upstream stage | n/a (no package manager) |

**Prohibited / insufficient:**
- Floating tag (`image:tag`) — pulls latest at build time; no reproducibility.
- Pin-only — tag frozen but packages drift inside the digest's lifetime; CVE
  class re-emerges silently.
- Upgrade-only — always-current packages but the base layer drifts
  unpredictably; build-time-dependent.

**Exemptions:** a `scratch` final layer (no package manager; upstream stages
still follow the rule); a vendor image not redistributable as digest-pinned
(document inline with a `# RATIONALE:` comment on the `FROM` line).

**Enforcement:** absence of a digest pin OR the upgrade step on a container PR is
grounds for Changes Requested. The pattern is mechanical; reviewers cite this
section. A companion automated check (Renovate/Dependabot) tracks digest-pin
*freshness* — pin-rot is the inverse failure mode, so pins must be refreshed on
a cadence, never frozen forever.

**Promotion path:** this is the charter + memory step of the enforcement
hierarchy. A future validating hook is the durable form once the convention
proves load-bearing across multiple PRs without manual reviewer reminders.

## Convention: per-environment credential provisioning

Every deployment environment (staging, prod, future dev/canary) gets its **own**
copy of any third-party OAuth client / app credential. They are never shared
across environments. Credentials resolve from **environment-scoped** secret
storage (same secret names per env; the scope encodes which env you are in), not
a single org-scoped secret.

Why per-env, not shared:
- **Provider state is per-app** — e.g. a provider's publishing/verification
  status (prod vs testing) cannot be both at once on one shared app.
- **Credential isolation** — a leaked staging credential does not affect prod.
- **Metrics & quota separation** — prod analytics aren't polluted by test
  traffic.
- **Redirect/callback hygiene** — each app's allowed-URI list contains only its
  own env's callback.

Service-internal secrets follow the same env-scope-by-default pattern; this
convention codifies the per-env requirement that makes env-scoping necessary.
Keep the operational provisioning/rotation procedure in a runbook; keep the
org-wide *requirement* here in the charter.

## Decision-record pattern (ADR-style)

For a significant architectural choice, record it as a dated decision entry with
a **status** (`pending` / `accepted` / `superseded`), the options considered
(e.g. ☐ Keep ☐ Hybrid ☐ Replace), the recommendation, and the rationale. Update
the entry **in place** as follow-on work lands, and explicitly mark superseded
notes as superseded rather than deleting them — the trail of why a decision
changed is itself load-bearing.

## Adaptation notes

- The base-image and per-env-credential conventions are broadly portable; keep
  the *shape* (defense-in-depth pin+upgrade; per-env not shared) and re-derive
  the specifics for your stack.
- The LCA tie-break needs your real org chart to be useful; the principle (push
  ties to the lowest shared owner, decide, move on) is the transferable part.
