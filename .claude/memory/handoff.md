# Session Handoff — 2026-06-28 (OIDC publishing)

## Pickup (next concrete step)
No active work in flight. `main` is clean and at **v0.3.1**, released to both registries via
OIDC. If picking up new work, the deferred queue lives in
`project_framework_extraction_state.md` (items 1–5: full wave/phase lifecycle skill chain,
review-gate tranche, branch-freshness, node CLI runtime install, optional LLM personas).

## What happened this session
- **Closed 4 stale issues** (#13, #18, #19, #33) — all resolved by PRs that merged into
  `deployments/phase2/wave-2` (PR #32), so GitHub auto-close never fired.
- **Diagnosed the v0.3.0 publish failures:** PyPI failed `invalid-publisher` (OIDC trusted
  publisher was never configured); npm failed `E404` (auth-failure-in-disguise — the
  `NPM_TOKEN` had expired end of May 2026).
- **Configured OIDC trusted publishers** on PyPI and npmjs.com for
  `parametrization/2real-team-framework` (workflows `publish-pypi.yml` / `publish-npm.yml`,
  PyPI environment `pypi`, no env on npm). npm setup required a security-key 2FA tap by owner.
- **PR #57** (merged): switched both publish workflows to OIDC — PyPI back to
  `id-token: write` + `environment: pypi` (reverted PR #55's API token); npm dropped
  `NODE_AUTH_TOKEN` and added `npm install -g npm@latest` (OIDC needs npm ≥ 11.5.1).
- **PR #58** (merged): version bump 0.3.0 → 0.3.1 (chose a bump over re-cutting v0.3.0 so
  both registries publish cleanly without a PyPI duplicate error).
- **Released v0.3.1** → both publish runs green. PyPI 0.3.1 live (with attestations);
  npm 0.3.1 live (`latest`, with provenance). npm history: 0.2.0 → 0.3.1 (skips 0.3.0).
- **Cleanup:** deleted unused `NPM_TOKEN` + `PYPI_API_TOKEN` repo secrets (repo now has zero
  secrets); shredded the local `~/npm_secret_delete_me.txt`.

## Decisions made this session
- **Tokenless publishing via OIDC** for both registries (durable fix for the recurring
  token-expiry breakage). Trusted publishers live on PyPI + npm; nothing to rotate.
- **Bump to 0.3.1** instead of re-cutting v0.3.0 (avoids deleting a published release and a
  PyPI duplicate-version error). npm intentionally skips 0.3.0.

## Open threads / blockers
- **User should rotate the 160-byte hex secret** that was in `~/npm_secret_delete_me.txt` — it
  was a real credential (not an npm token) and was exposed in a plaintext file; rotate it at
  its source. The file itself has been shredded.
- No other blockers. All publish CI green; both registries at 0.3.1.

## Mechanical state
- Branch: main (clean aside from these memory edits)
- Latest release: v0.3.1 (tag `v0.3.1`)
- Open PRs: (none)
- Open issues: (none)
- Lifecycle: (no wave state)
- Actions secrets: (none — fully OIDC)
