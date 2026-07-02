<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-02 (Phase 3 shipped: v0.4.0 live on both registries)

## Pickup (next concrete step)
No active work in flight. **v0.4.0 is released and live** on PyPI + npm (`2real-team-framework`
0.4.0 on both, verified via registry APIs). `main` tip = `6605da8` (merge of
`deployments/phase3/wave-1`, PR #97). Next candidates: open tech-debt issues (#74 #75 #77 #82
#90 #94), the deferred PR/CI review-gate hook tranche, or Phase 4 planning (wave retro first).

## What happened this session (Phase 3, waves 1–3)
- **Wave 1 — installer overhaul** (#64–#70, #73): unified `install.config.yaml` (v1 schema,
  stdlib miniyaml, flags > user YAML > shipped defaults, resolved snapshot at
  `.claude/install.config.json`), `--non-interactive`, meta/child install modes (parent-relative
  hook paths, product vs infra flavor), ontology generated at install, pre-push installer
  (noop default), 10-rule `.claude/`-scoped permissions block in settings template, 7-file
  modular charter template with `{{key}}` context substitution, Node CLI bridge (bundles
  framework/, subprocesses Python bootstrap), CI now triggers on PRs to `deployments/**`.
- **Wave 2 — skills + dispatch** (#85–#88): skills 5→13 (ported team-reset, wave-audit,
  wave-retro, phase-review; enriched close-stale-issues, plan-phase, retro, wave-start),
  Agent/Stop events route through dispatcher (`stop_dispatcher.py` always exit 0), dogfood
  closeout (#93: config snapshot, merged permissions, modular charter in `.claude/team/charter/`).
- **Wave 3 — release** (#95/#96): versions → 0.4.0 (pyproject, `__init__.py`, package.json,
  lockfile), `RELEASE_NOTES_0.4.0.md` (Tariq-corrected wording: permissions claim scoped to
  framework runtime; one ontology at meta root; STOP-guards "before any branch work"), README
  install-config table + meta/child + pre-push + 13-skills sections.
- **Ship**: PR #97 wave→main merged (merge commit, 11/11 CI green on merge head), release
  `v0.4.0` created, OIDC publish workflows both green
  (https://github.com/parametrization/2real-team-framework/releases/tag/v0.4.0).

## Decisions made this session
- Release tag convention confirmed by user: **`v0.4.0`** (registry `v*` style), not CLAUDE.md's
  older `deployments-phase3-wave-1` branch-name style. Only ONE release per version — both
  publish workflows fire on *any* published release.
- Review-gate hook tranche deferred to a future phase (user choice).
- Node parity via "Bridge to Python" (bundle framework/, subprocess bootstrap), not a rewrite.
- GitHub auto-close only fires on default-branch merges — issues tied to wave-branch PRs get
  closed manually with a reference comment (Hiro did #95).

## Open threads / blockers
- Tech-debt issues open for future waves: #74, #75, #77, #82, #90, #94.
- **User should rotate the 160-byte hex secret** that was in `~/npm_secret_delete_me.txt` (prior
  session) — rotate at its source. Standing reminder.
- No blockers. All CI green; both registries at 0.4.0.

## Mechanical state
- Branch: main @ 6605da8 (clean); `deployments/phase3/wave-1` retained @ 4085a3f
- Latest release: **v0.4.0** — main == released state
- Open PRs: (none)
- Open issues: tech-debt only (#74 #75 #77 #82 #90 #94)
- Actions secrets: (none — fully OIDC)
