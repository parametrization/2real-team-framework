<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-06-29 (CLAUDE.md at project root)

## Pickup (next concrete step)
No active work in flight. **`main` is ahead of the released `v0.3.2` tag** with unreleased
behavior (see below) — registries are still at 0.3.2. Cut a release when ready to ship it (user
chose "let it ride" — no release was made this session). Deferred queue lives in
`project_framework_extraction_state.md` (items 1–5).

## What happened this session
- **v0.3.2 docs release** (earlier): README Skills section now documents all 11 skills (6
  team-workflow + 5 runtime); released to refresh the PyPI/npm long-description (PR #59).
- **CLAUDE.md now installs at the project root** (issue #60 / PR #61): both bootstraps (Python
  `bootstrap.py` + Node `bootstrap.ts`) write `CLAUDE.md` to the project **root** instead of
  `.claude/CLAUDE.md`. If a root `CLAUDE.md` already exists it's preserved as `CLAUDE.md.bak`
  (non-clobbering → `.bak.1`, `.bak.2`, …) and the user is warned to reconcile (framework writes
  only the team section). Helper: `_next_backup_path` / `nextBackupPath`. CLI next-steps message
  updated; tests cover fresh + conflict paths in both languages; README file-tree updated.
- **Dogfood move** (issue #62 / PR #63): this repo's own `.claude/CLAUDE.md` → root `CLAUDE.md`
  (pure `git mv`, 100% rename). The `@.claude/memory/MEMORY.md` import is repo-root-relative and
  stays valid. Nested `python/.claude/CLAUDE.md` (sub-project demo) intentionally left untouched.

## Decisions made this session
- **Let it ride** — no 0.3.3 release for the CLAUDE.md-root behavior; it ships with the next
  release. `main` has the code now regardless.
- **Backup is non-clobbering** — never overwrite an existing `.bak`; use the next free suffix.
- **Dogfood the new convention** in this repo (root `CLAUDE.md`).

## Open threads / blockers
- **`main` is ahead of `v0.3.2`** — the root-CLAUDE.md install behavior is unreleased. Cut a
  release to ship it to PyPI/npm when desired.
- **User should rotate the 160-byte hex secret** that was in `~/npm_secret_delete_me.txt` (prior
  session) — a real credential exposed in a since-shredded plaintext file. Rotate at its source.
- No other blockers. All CI green.

## Mechanical state
- Branch: main (clean)
- Latest release: v0.3.2 (tag `v0.3.2`) — **main is ahead of it (unreleased CLAUDE.md-root work)**
- Open PRs: (none)
- Open issues: (none)
- Lifecycle: (no wave state)
- Actions secrets: (none — fully OIDC)
