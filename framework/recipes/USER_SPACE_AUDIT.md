# User-Space (`~/.claude`) Audit + Installer Invisible-Dependency Gap List

**Issue:** #106 `[Explore]` — Audit user-space Claude files across the three projects and find installer gaps.
**Author:** Ibrahim El-Amin (Phase 5 / Wave 1). **Mode:** read-only spike. Nothing under `~/.claude` was modified.
**Feeds:** #107 (consented user-level install) and #108 (repo-level pattern).

Machine: `parameterization@` WSL2. Claude Code `2.1.200`. Home: `/home/parameterization`.
Three in-scope projects live as siblings under `/home/parameterization/code/`:
`noorinalabs-main` (+ children), `2real-team-framework` (this repo), `botfarm_inc`.

---

## Headline finding

**User space is almost entirely GENERIC and GLOBAL, not per-project.** There are **no** custom
`skills/`, `commands/`, `agents/`, `hooks/`, `output-styles/`, or `keybindings.json` under `~/.claude`.
Every operational framework asset (skills, hooks, lib, charter, roster) lives at **project** level
(`<repo>/.claude/…`, or `framework/assets/…` in this repo) and is provisioned by the installer. The
only per-project user-space state is harness-managed **auto-memory** and **ephemeral session/team**
runtime dirs.

Consequently the "invisible dependency" gap is **not** missing user-level skills/agents. It is a small
set of **harness-global settings in `~/.claude/settings.json` that the installer never writes** — chiefly
the experimental **agent-teams** flag on which the entire simulated-team workflow silently depends. A
fresh clone + `2real-team init` on a clean machine produces a correct project `.claude/` but a harness
that **cannot spawn a team**.

---

## 1. Inventory of `~/.claude`

Classification key: **Generic** = useful to any project / harness-global; **Per-project** = state keyed to
one project; **Runtime** = machine-local cache/session state, not a config input; **Secret** = redacted.

| Path (`~/.claude/`) | Kind | Classification | Which project |
|---|---|---|---|
| `settings.json` | Global harness config (env, permissions, model, plugins, statusline, voice, worktree) | **Generic / global** — but contains load-bearing team deps (see §2) | All (single shared file) |
| `settings.local.json` | Local override (`git branch` perm + agent-teams env) | Generic / global | All |
| `settings.json.bak`, `settings.json.orig` | Prior snapshots of settings | Runtime (backup) | — |
| `.credentials.json` | OAuth/API credential | **Secret present, redacted** — never install | All |
| `statusline.sh` | Statusline command → `npx ccstatusline@latest` | Generic | All |
| `plugins/` (`installed_plugins.json`, `known_marketplaces.json`, `marketplaces/`, `cache/`, `blocklist.json`, `plugin-catalog-cache.json`) | Plugin state; installed: `frontend-design@claude-plugins-official` (user scope) | Generic | All |
| `projects/<slug>/memory/*.md` | Harness auto-memory (`MEMORY.md` + topic files) | **Per-project** | one dir per project (see below) |
| `teams/session-*/`, `teams/noorinalabs.archive-*` | Simulated-team session state (`config.json`, `inboxes/`) | Runtime (ephemeral) | mixed / session-keyed |
| `tasks/`, `jobs/`, `sessions/`, `session-env/`, `shell-snapshots/` | Session & task runtime | Runtime | — |
| `history.jsonl` | Prompt history | Runtime | All |
| `file-history/`, `backups/`, `paste-cache/`, `downloads/`, `cache/`, `telemetry/` | Caches | Runtime | — |
| `daemon/`, `daemon.log`, `ide/`, `chrome/` | Daemon / IDE / browser-integration runtime | Runtime | — |
| `stats-cache.json`, `gh-pr-status-cache.json`, `.last-update-result.json`, `.last-cleanup` | Caches / status | Runtime | — |
| `worktrees/` (user-level) | Empty; harness worktree scratch | Runtime | — |

**Absent (notable):** `~/.claude/CLAUDE.md`, `~/.claude/skills/`, `~/.claude/commands/`, `~/.claude/agents/`,
`~/.claude/hooks/`, `~/.claude/output-styles/`, `~/.claude/keybindings.json` — none exist. No user-level
custom prompt assets are in play.

### `settings.json` field-level breakdown (the config that matters)

| Key | Value (observed) | Load-bearing for team flow? | Classification |
|---|---|---|---|
| `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | `"1"` | **YES — enables the whole simulated-team workflow** | Global, framework-critical |
| `env.teammateMode` / top-level `teammateMode` | `"split-panes"` / `"auto"` | Yes — teammate spawn UX | Global, framework-relevant |
| `worktree.baseRef` | `"fresh"` | Yes — worktrees are the mandated isolation method (`charter/branching.md`) | Global, framework-relevant |
| `permissions.allow[]` | broad `.claude/**` **plus** absolute `~/.claude/**` and `code/**/.claude/**` globs | Partly — cross-repo/home globs let the orchestrator write sibling worktrees & user space without prompts | Global, framework-relevant |
| `model` | `"opus[1m]"` | No | Generic user pref |
| `effortLevel` | `"high"` | No | Generic user pref |
| `enabledPlugins.frontend-design@…` | `true` | No | Generic user pref |
| `statusLine` | `~/.claude/statusline.sh` | No | Generic user pref |
| `skipDangerousModePermissionPrompt`, `remoteControlAtStartup`, `agentPushNotifEnabled`, `inputNeededNotifEnabled`, `voice*`, `tui`, `editorMode`, `verbose`, `autoDreamEnabled`, `defaultMode` | assorted | No | Generic user prefs |

### Per-project auto-memory (the only per-project user-space state)

`~/.claude/projects/<slug>/memory/` exists for each project. Attribution by slug:

| Slug | Project |
|---|---|
| `-home-parameterization-code-noorinalabs-main` (+ worktree slugs) | **noorinalabs-main** (+ children) |
| `-home-parameterization-code-2real-team-framework` | **2real-team-framework** |
| `-home-parameterization-code-botfarm_inc` and `…-botfarm-inc` (two slugs, underscore vs hyphen) | **botfarm_inc** |
| `-home-parameterization-code-isnad-graph`, `…-reddit-bot`, `…-other-brain` | out of scope (other projects) |

These are machine-local and **not version-controlled**. Note this repo separately keeps its *own*
version-controlled memory at `<repo>/.claude/memory/` (per `CLAUDE.md`), so auto-memory is a parallel,
regenerable store — not something a fresh clone needs installed.

---

## 2. Invisible-Dependency Gaps

Definition: a user-space item the working flow relies on that the repo installer
(`framework/install/bootstrap.py` + `2real-team init`) **never writes**. Verified: `bootstrap.py` only ever
targets `<target>/.claude/…` and merges hook wiring into the **project-level** `settings.json`; it never
touches `~/.claude`. A repo-wide grep confirms **nothing in the repo ever sets
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`.**

| # | User-space item | Why it's a gap (what silently breaks on a clean machine) | Recommended disposition |
|---|---|---|---|
| G1 | `settings.json → env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS = "1"` | **The entire team workflow depends on it.** Without it the harness cannot spawn teammates; `botfarm_inc`'s install "works" only because this machine already had the flag. Fresh clone + `init` yields a project with charter/roster/hooks but **no ability to run the team**. Installer never sets it. | **should-become-user-level-installed** (#107) — it is a harness-global flag, not a per-repo setting; a repo-level file cannot enable it. |
| G2 | `settings.json → teammateMode` (`split-panes` / `auto`) | Teammate spawn UX; team flow degrades / prompts without it. Installer never sets it. | **should-become-user-level-installed** (#107) |
| G3 | `settings.json → worktree.baseRef = "fresh"` | Charter mandates every code-writing agent runs in its own worktree; without a user-level worktree default the orchestrator's worktree creation is unprimed. Installer provides no worktree config at any level. | **should-become-user-level-installed** (#107); consider documenting a repo-level note in #108. |
| G4 | `settings.json → permissions.allow[]` absolute/home globs (`~/.claude/**`, `code/**/.claude/**`, cross-repo git) | The installer's `settings.template.json` grants only **relative** `.claude/**` perms (project-scoped). The orchestrator also writes **sibling worktrees** and **user space**, which needs the absolute/home globs seen here — otherwise every cross-repo/user-space write prompts. | **split:** project-relative subset **should-become-repo-installed** (already partially is, via `settings.template.json`); the home/cross-repo globs are machine-shaped → **should-become-user-level-installed** (#107). |
| G5 | `plugins/` — `frontend-design@claude-plugins-official` (user scope) + marketplace registration | `frontend-design` is enabled in `settings.json` and its assets live only in user-space plugin cache. If a skill/flow invokes it on a fresh machine it's absent. Currently generic, low-criticality. | **leave-manual** (document as an optional prereq; not team-critical). |
| G6 | `statusline.sh` → `ccstatusline` | Cosmetic; statusline command referenced by `settings.json` but the script + `npx` dep are user-space. Non-blocking. | **leave-manual** |
| G7 | Per-project auto-memory `projects/<slug>/memory/` | Flow reads it, but it is harness-managed, regenerable, and this repo already version-controls its own `.claude/memory/`. A fresh clone does not need it seeded. | **leave-manual** (regenerates; no action) |
| G8 | `.credentials.json` | Auth. **Secret — redacted.** Required for the harness but provided by user login, never by an installer. | **leave-manual** (out of scope; never install) |
| G9 | Generic prefs (`model`, `effortLevel`, voice, tui, notifications, `skipDangerousModePermissionPrompt`, etc.) | Personal preferences; not required by the team flow. | **leave-manual** |

---

## 3. Summary & Recommendations (feeding #107 / #108)

- The framework's **project-level** provisioning is essentially complete: skills, hooks, lib, charter, and
  roster are all installer-written into `<repo>/.claude/`. The dual-deploy requirement is met there.
- The real gap is a **thin user-level layer** the installer has never owned. In priority order:
  **G1 (agent-teams flag) is the single load-bearing invisible dependency** — everything else is UX polish,
  regenerable state, or personal preference.
- **For #107 (consented user-level install):** ship a small, idempotent, **consent-gated** step that ensures
  `~/.claude/settings.json` has `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (G1), `teammateMode` (G2),
  `worktree.baseRef=fresh` (G3), and the home/cross-repo permission globs (G4-user subset). It must **merge,
  never overwrite** (user settings hold credentials refs and personal prefs), diff-and-confirm before
  writing, and touch nothing else.
- **For #108 (repo-level pattern):** the project-relative permission subset (G4-repo) already lives in
  `settings.template.json` — formalize/verify it there. A repo-level file **cannot** satisfy G1-G3 (they are
  harness-global), so document them as a documented prerequisite/preflight check the installer prints when
  the flag is absent.
- **Preflight suggestion (cheap, high value):** have `2real-team init` / session-start **detect** a missing
  `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` and emit a loud warning + one-line fix, even before #107 lands. This
  removes the "silent" from the silent dependency.

---

## OWNER-DECISION — dispositions requiring sign-off at wave-end

The following gap dispositions change behavior on the user's machine / installer contract and need the
project owner's explicit approval before #107/#108 implement them:

1. **G1 — agent-teams flag → user-level install.** Approve writing
   `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` into `~/.claude/settings.json` via a consent-gated,
   merge-only step. (This is an experimental harness flag — owner must accept enabling it programmatically.)
2. **G2 / G3 — `teammateMode` + `worktree.baseRef=fresh` → user-level install.** Approve seeding these
   harness-global defaults.
3. **G4 — permission-glob split.** Approve (a) keeping the project-relative subset repo-installed and
   (b) writing the absolute `~/.claude/**` + `code/**/.claude/**` + cross-repo git globs at user level.
   These broaden auto-approved write scope — owner should confirm the breadth.
4. **G5 — `frontend-design` plugin: leave-manual vs document-as-prereq.** Confirm it stays manual.
5. **Consent model for #107.** Confirm the required guarantees: never overwrite, diff-and-confirm before
   any write to `~/.claude/settings.json`, idempotent re-runs, and no modification of credentials/prefs.
