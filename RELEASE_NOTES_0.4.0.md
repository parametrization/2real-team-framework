# v0.4.0

Feature release — one config file now drives a fully non-interactive install,
including multi-repo (meta + child) layouts, and the runtime ships a much
larger skills tier. Both CLIs (`pip install 2real-team-framework`,
`npm install -g 2real-team-framework`) expose the same `init` contract.

## Unified install config + non-interactive mode (#64)

Every interactive decision point across both installers is now covered by a
single `install.config.yaml` schema (precedence: CLI flags > user YAML >
shipped defaults):

```bash
# Standalone framework installer (stdlib-only, zero prompts)
python3 framework/install/bootstrap.py /path/to/repo \
  --install-config my.install.yaml --non-interactive

# CLI (same file, auto-detected)
2real-team init --config my.install.yaml --non-interactive
```

With `--non-interactive` there are **zero prompts on any path**. The resolved
config is recorded at `.claude/install.config.json` for downstream tooling. A
fully commented reference lives at
`framework/config/install.config.default.yaml`; the key table is in the README
("Install configuration").

## Meta-repo and child installs (#65)

`project.model: standalone | meta | child` describes your repo shape:

- **meta** — full framework at the meta root, plus a hook-less child layout in
  each repo listed under `children:` (with per-child `flavor: product|infra`).
  Children invoke the parent's dispatchers via portable parent-relative
  commands — one copy of the hooks, the whole tree clones anywhere.
- **child** — lay just the child layout, pointing at an already-bootstrapped
  parent (`parent.path`, relative only).

Installs are also gated by `repo.expect: fresh | existing | any` — the
installer detects the target's actual state and refuses (non-interactive) or
asks (interactive) on a mismatch; idempotent re-runs skip the gate.

## More runtime, out of the box

- **Ontology at install** (#66) — `ontology.enabled: true` (default) seeds the
  two-layer ontology (semantic overlay + generated structural index) and
  activates the ontology hooks at install; for meta trees the ontology lives
  at the meta root with cross-repo aggregation over the children.
- **Pre-push hook installer** (#67) — `pre_push.mode: noop | enforce | none`.
  `enforce` runs `hooks.pre_push_commands` from `framework.config.json` at
  push time; existing non-framework hooks are preserved as `pre-push.bak`.
- **Shipped permissions allowlist** (#68) — `settings.template.json` now
  carries a genericized permissions allowlist so a fresh install doesn't
  prompt for the framework's own runtime — `.claude/` file edits and
  hook/lib invocations.
- **Modular charter template** (#69) — the installed charter is a thin index
  over per-topic modules (`.claude/team/charter/*.md`), so teams evolve
  individual sections without merge pain.
- **Agent/Stop dispatch + session hooks** (#87) — the dispatcher now covers
  Agent and Stop events and ships `session_start` / `session_handoff` hooks;
  also reconciled the config schema defaults drift (#84).

## Skills tier grew: 13 runtime skills (#85, #86)

New: `team-reset`, `wave-audit`, `wave-retro` (mechanical, evidence-anchored
trust scoring), `phase-review`, plus STOP-guards in `wave-start`. Enriched
runtime versions of `retro`, `wave-start`, `plan-phase`, and
`close-stale-issues` supersede the templated ones when the runtime is
installed. Full list in the README ("Skills").

## Node CLI: full parity via the bundled Python bootstrap (#70)

`npx 2real-team-framework init` now installs the framework runtime by bridging
to the bundled Python bootstrapper (`python3` or `python` on PATH; team
scaffolding still completes without one, with instructions to finish). The npm
package has its own README, and the CLI version comes from `package.json` —
no hardcoded version strings.

## Proven on itself

- CI now runs on PRs into `deployments/**` wave branches (#73).
- This repo is bootstrapped through its own installer (#88) — the framework
  dogfoods every hook, skill, and config path it ships.

## Distribution

- PyPI: 0.3.2 -> 0.4.0
- npm:  0.3.2 -> 0.4.0
