# v0.5.0

Minor release — **Phase 5: installer robustness**. Two waves (discovery → build) that make the
2real installer trustworthy on repos *other than this one*: a repeatable install/test/teardown
harness, a golden install manifest, and consented backup/amend/restore install flows at both the
user and repo level. New user-facing installer capabilities; the existing `init` contract is
unchanged and backward-compatible (all new destructive paths are opt-in and `--non-interactive` safe).

## Consented user-level install — closes the agent-teams gap (#107)

`bootstrap.py --user-space` (and the standalone `framework/install/user_space.py`) adds a
**consented, idempotent** install step for `~/.claude/settings.json`. It closes the load-bearing
gap surfaced in Phase 5 Wave 1's audit (#106): the installer never wrote
`env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, so a fresh clone could install a correct project
whose harness still couldn't spawn a team.

- Writes the agent-teams flag + `teammateMode` + `worktree.baseRef=fresh` — **only with explicit consent**.
- **Check-existing first**: already-set-and-matching → no-op, no prompt; missing → prompt + timestamped
  backup + amend-in-place; present-but-different → surfaces the conflict, **never clobbers** a user value.
- `--non-interactive` / non-TTY default = **skip** (never writes unprompted). Reusable `consent.py` /
  `backup.py` module.

## Consented repo-level backup / archive / restore (#108)

Repo-level `.claude` install gains the same consent UX plus a restorable archive path: existing repo
Claude assets can be **archived out of Claude's load scope** (a timestamped `.claude-backups/<UTC>/`
sibling, not under `.claude/`) or amended in place. A documented, tested **restore** brings them back
byte-identical. Round-trip verified (install → archive → out-of-scope → restore → identical).

## Install/test/teardown harness (#105) + golden manifest (#139)

`python3 -m framework.harness` provisions fixtures, runs the real installer, asserts install-quality
metrics, and tears down with a zero-residue proof (symmetric-diff vs a pre-install snapshot).

- **Fixtures:** hermetic buckets B1–B9 + this repo's inline reinstall-parity dogfood run by default;
  real-repo buckets (B10/B11) are opt-in behind `--include-real` and never touch live repos (clone at a
  pinned SHA into scratch when enabled).
- **Golden manifest** (`framework/install/manifest.py`, `expected_install_set(config)`) is the single
  source of truth for install-completeness — derived from the installer's own asset iterators (can't drift),
  with a `--check` drift guard. Retires the previously hardcoded module/skill counts.
- Metric records carry a permutation-discriminated `record_id` (#138); latest full run: `install_success_rate 1.00`.

## Other fixes

- **#145** — settings writes are now **atomic** (temp-file + `os.replace`), protecting both the user-space
  and repo-space paths against a truncated `settings.json` on a mid-write crash.
- **#131** (shipped Wave 1) — the trust scorer's `review_false_positives` heuristic is gated on an
  actually-raised `Must-fix:`, so a clean approval can no longer score a phantom retraction.

## Notes

- **442 tests** (up from 376 at v0.4.2); `ruff` clean across `framework/`; reinstall-parity and
  golden-manifest drift guards both green.
- Deferred follow-ups filed: #142 (product `uninstall` command), #148 (cli_bridge_soft_degrade +
  `--compare` CI gate), #149 (durability/fidelity hardening).

## Version bumps
- PyPI: 0.4.2 -> 0.5.0
- npm:  0.4.2 -> 0.5.0
