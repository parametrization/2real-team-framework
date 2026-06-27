# Emergency Mode

## Purpose <!-- promotion-target: none -->

Defines the explicit escape valve for charter compliance during DR / restore / security-incident situations where the standard 2-reviewer + wave-process discipline cannot be maintained without prolonging the outage. Without this section the bypass happens silently and degrades unmonitored — the P3W2 emergency thread (2026-05-01 → 2026-05-02) is the canonical example: 13 deploy PRs merged in a 6h window, comment density dropped from 4-per-PR to zero, merge time dropped from 13 min to 4 seconds, all owner-self-merged with no formal review.

## Trigger conditions <!-- promotion-target: none -->

Emergency Mode activates when ANY of:

- **Prod-down** — a public hostname is returning non-2xx/3xx, or an underlying service is unreachable from the public internet.
- **Active security incident** — credential leak, unauthorized access, exploited CVE in production.
- **DR / first-deploy** — initial bring-up of new infrastructure where the standard promotion pipeline cannot run because prerequisite state doesn't exist yet (empty image registry, no prior tag to promote, etc.).

Discomfort, urgency, or "I just want to ship this fast" are NOT trigger conditions. Use the standard wave process.

## Allowed bypasses <!-- promotion-target: none -->

Once Emergency Mode is active:

- **Single-reviewer or zero-reviewer merges** are allowed.
- **PR title MUST be prefixed with `[EMERGENCY]`** so post-emergency catchup can find them.
- **Direct-to-main commits** are allowed if a PR cannot be opened (e.g., during prod restore where every minute of outage matters). Direct commits MUST include `[EMERGENCY]` in the commit message subject.
- **Charter-format review comments** may be skipped in favor of one-line PR body context.

What is NOT bypassed:
- **Commit-identity, secrets-in-diff, no-verify hooks** stay active. Attribution and secret-leak prevention are non-negotiable even under fire.
- **Root-fix discipline.** Emergency PRs still earn root fixes, not patches-around. Tech-debt explicitly filed is allowed; tech-debt forgotten is not.
- **Honest-audit-before-concluded.** Even mid-restore, status claims still earn artifact verification.

## Entering and exiting <!-- promotion-target: none -->

**Entering** — declare in-band: "Entering Emergency Mode per `charter/emergency-mode.md` — trigger: {prod-down | security incident | DR}." This is the signal to later auditors and to the post-emergency catchup pass.

**Exiting** — declare when the trigger condition has resolved: "Exiting Emergency Mode — {hostname back up | incident contained | first-deploy stabilized}." Subsequent PRs return to the standard wave process.

## Post-emergency catchup <!-- promotion-target: none -->

Within 24h of stabilization:

1. Walk every `[EMERGENCY]`-prefixed PR merged during the window.
2. Run an async review pass on each — same charter-format comment, but post-merge.
3. File any TechDebt items found as separate issues, labeled to the current or next wave.
4. Update runbooks, hooks, or charter sections with lessons learned.
5. The standards lead (Aino) signs off on catchup completion.

Until catchup completes, the emergency-PR set is considered open process debt. Subsequent `/wave-kickoff` cannot proceed if catchup is unresolved.

## Owner-Manual-Action Protocol <!-- promotion-target: none -->

When the project owner takes infrastructure action outside the orchestrator's tool scope — including:

- Deleting/creating Hetzner servers via web console or `hcloud` CLI
- Console-pasting SSH keys, secrets, or cloud-init content
- Rotating credentials at provider dashboards (Cloudflare, GitHub, B2)
- Executing `terraform apply` from local machine
- Direct `gh secret set` / `gh api` calls outside a session

…the owner posts a one-line state delta to the active session BEFORE proceeding to the next dependent action.

Format:

```
[OWNER-ACTION] {what was done} — {what state changed} — {what now points where}
```

Examples:

- `[OWNER-ACTION] deleted hcloud server 124917846 (1box-prod) — Hetzner inventory now 1 server — CF DNS still points at 124917846 IP, needs reconcile`
- `[OWNER-ACTION] regenerated GH_PACKAGES_TOKEN with write:packages — old token revoked — set as org secret CLOUDFLARE_API_TOKEN`

The post is the orchestrator's pre-flight surface for the next action. Without it, the orchestrator cannot pre-check downstream dependencies (DNS pointing, secret consumers, dependent services) before they fail.

The orchestrator, on receiving an `[OWNER-ACTION]` line, MUST acknowledge by enumerating the dependent state it will pre-flight check before the next action.

## Why <!-- promotion-target: none -->

P3W2 emergency thread (2026-05-01 → 2026-05-02):

- Owner manually deleted hand-made 1box-prod (id 124917846) while CF DNS still pointed at it → prod went down. The owner action was correct on its own; the gap was orchestrator had no state-model of the impending decommission, so couldn't pre-flight DNS.
- Five workflow bugs surfaced under emergency pressure that no PR-time review could have caught: `terraform.yml` ephemeral keypairs, `promote.yml` retag-token mismatch, `promote.yml` `stg-latest` TOCTOU race, `promote.yml` multi-arch assumption, `db-migrate.yml` `psycopg`-vs-`asyncpg` URL. These are first-deploy / cold-start bugs.
- Process discipline collapsed silently. PR comment density dropped to zero by PR #246; merge time dropped below 5 seconds. No in-band signal that standard mode had been suspended.

This section makes the bypass legible.
