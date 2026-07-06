# BOTFARM_UPGRADE_STUDY — B11 upgrade-over-live-install (#109)

Real-repo acceptance test for the #108 repo-level **consent + archive + restore** flow, run
against `botfarm_inc` — a repo that **already runs its own independently-evolved 2real install**
(its own bootstrap commit `d4c058d`, its own phase/wave history). Per the owner decision on #109
the framing is **upgrade-over-live-install**, not a blank/foreign-repo replacement: we clone
botfarm at its current `main` (which carries that diverged install) and prove the archive/restore
flow returns the managed Claude assets **byte-identical**.

Everything runs on a throwaway clone in scratch. The live tree is **never** modified: the
provisioner (`framework/harness/real_provision.py`, #153) clones with `git clone --no-local` +
detached checkout and asserts the source `{HEAD, porcelain}` is byte-unchanged before/after.

## Run configuration

| Item | Value |
|------|-------|
| Source | `/home/parameterization/code/botfarm_inc` (B11 fixture; remote `git@github.com:parametrization/botfarm_inc.git`) |
| Pin | resolved **live** via `git ls-remote <source> refs/heads/main` at run time (`pin=null`) |
| Resolved SHA (study run) | `2a219921df044b5e5a0f5a8bb0223988eb80d3d9` |
| `--real-config` | `framework/tests/install_quality/real-config.botfarm.example.json` (example sidecar; machine-local path stays out of checked-in defaults, #155 item 2) |
| Harness bucket | `B11 standalone-real-world` via `python3 -m framework.harness --include-real --buckets B11 --installers bootstrap` |
| Archive/restore study | `python3 -m framework.harness.botfarm_upgrade_study` |

> **Pin note.** The issue AC pinned `a4e622dd…`; the local `main` advanced to `2a219921…`
> *during this session* (botfarm is under concurrent work — exactly why the pin is resolved live
> and never trusted from a checked-out branch). Both SHAs carry the same diverged install; the
> study is internally consistent (its own before/after are both at `2a219921`).

## Two dispositions, measured separately

#108 offers two dispositions for a repo that already has Claude assets. This study measures both:

1. **amend-in-place** — the `B11` harness bucket (`bootstrap --expect existing`) merges the
   framework over botfarm's live install. Gives the metric records + `install_success_rate`.
2. **archive-then-fresh-then-restore** — the reversible path #108 adds. The study script archives
   botfarm's entire `.claude/` + `CLAUDE.md` out of scope, lays a fresh install, then restores,
   and proves a byte-identical restore via `snapshot()` / `symmetric_diff()`.

---

## BEFORE — what botfarm's existing install looks like

A mature, org-scale install: **150 files** under `.claude/` + a hand-evolved `CLAUDE.md`, and a
**12-member** roster (`Steven French, Miriam Osei, Davi Santos, Yuna Park, Tariq El-Amin, Ingrid
Haugen, Cem Yilmaz, Kwame Mensah, Lena Volkov, Sofia Marino, Priya Raghavan, Annunaki`).

### Divergence vs our `expected_install_set` (standalone + team = 67 files)

| | Count | Examples |
|---|---|---|
| Files botfarm **has, expected set does not** (local extension) | **91** | `annunaki_log.py` / `annunaki_monitor.py` + `skills/annunaki*`; `auto_close_referenced_issues.py`, `auto_rebase_queue.py`, `autoformat.py`; `validate_orchestrator_*`, `validate_branch_freshness.py`, `validate_ci_*`, `block_gh_pr_*`; **20** extra `team/roster/*` members; **26** `hooks/tests/*`; `context/`, `plans/phase-*.md`, `team/waves/*-merge-order.json`, `skills/wave-kickoff`, `skills/wave-wrapup` |
| Files expected set **has, botfarm is missing** (older base) | **8** | `hooks/stop_dispatcher.py`, `hooks/validate_review_comment_format.py`, `install.config.json`, `team/.charter-manifest.json`, `team/charter/charter.md`, `skills/{phase-review,retro,wave-end}/SKILL.md` |

Botfarm is simultaneously **ahead** (91 files of local extension — an `annunaki` subsystem, an
org-scale roster, phase plans, wave merge-orders) and **behind** (missing 8 files that landed in
the framework after its `d4c058d` bootstrap, including a skills-layout migration from flat
`skills/foo.md` to `skills/foo/SKILL.md`). This is a genuinely *diverged* install — a strong
fixture for archive/restore.

---

## amend-in-place — `B11` harness records

`install_success_rate = 0.75` (9/12 graded metrics; 13 records incl. 1 trend). `install_duration_s`
trend = **0.20 s**.

| Result | Metric (category) |
|--------|-------------------|
| PASS | `install_exit_status` (A), `non_interactive_zero_prompts` (A), `repo_state_gate_correct` (A) |
| PASS | `no_unexpected_files` (B), `install_snapshot_recorded` (B), `files_installed_complete` (B, scored) |
| PASS | `permissions_allowlist_present` (C) |
| PASS | `reinstall_idempotent` (F), `no_backup_litter` (H) |
| **FAIL** | `settings_hooks_wired` (C) — botfarm's diverged `settings.json` carries extra matchers (`SessionStart: resume/startup`, split `PostToolUse: Bash/Edit/Write`) that the merge preserves → superset, not the exact clean set |
| **FAIL** | `config_module_lists_complete` (C) — the idempotent merge preserves botfarm's own `framework.config.json` (its `pre_bash` lacks our `validate_labels`/`block_squash_wave_merge`; `hooks.agent`/`hooks.stop` absent) rather than reconciling to canonical |
| **FAIL** | `teardown_residue_zero` (H, scored) — residue `[.claude/settings.json]` (see finding #1 below) |

The three failures are **not installer defects** — they are the signature of merging over a
diverged live install: the merge correctly *preserves foreign* config/hooks (that survival is the
point of `settings_merge_preserves_foreign` in B5), but that means the amend path neither reaches
our clean-install matcher set nor upgrades stale module lists, and an in-place merge into a
pre-existing file is not reversible by the drop-added-files teardown.

---

## archive-then-fresh-then-restore — byte-identical proof

Evidence record (`botfarm_upgrade_study`, full JSON captured at run time):

| Stage | Observation |
|-------|-------------|
| provision | `source_unchanged_after_provision = true` (read-only invariant held) |
| BEFORE | 151 managed files; assets `[.claude, CLAUDE.md]`; 12-member roster |
| **archive** | `action = archived`; moved `[.claude, CLAUDE.md]` → `.claude-backups/<UTC>/`; root assets now `[]`; roster no longer loadable at root (`[]`) |
| fresh install | `rc = 0`; wrote a **different** roster (`Aria Okafor, Mateo Reyes, Nadia Haddad`) — proving botfarm's old roster is out of scope; `differs_from_before = true` |
| **restore** | restored `[.claude, CLAUDE.md]`, `conflicts = []`, `managed_symmetric_diff = []` → **`byte_identical = true`** |
| source | `source_unchanged = true` |
| teardown | `teardown_scratch_removed = true` (drop-the-copy ⇒ zero residue by construction) |

**Restore is byte-identical** for the #108-managed assets (`.claude/**` + `CLAUDE.md`): the
symmetric-diff of the pre-existing install against the post-restore state is empty.

### Honest out-of-scope accounting

`symmetric_diff` over the **whole tree** (not just managed assets) leaves two residual paths the
restore deliberately does not own:

- `.claude-backups/<UTC>/archive-manifest.json` — the restore manifest sidecar (restore *moves*
  assets back but leaves its own manifest + the now-empty backup dir).
- `.git/hooks/pre-push` — installed by the fresh-install leg; `restore_assets` is scoped to
  `.claude/` + `CLAUDE.md` and does not remove it.

Neither is a managed asset, so "byte-identical restore" holds for what #108 guarantees; a fully
pristine repo would additionally prune the emptied `.claude-backups/` and the fresh `pre-push`
(see findings for #149).

---

## Reproduce

```bash
# amend-in-place metric records
python3 -m framework.harness --include-real --buckets B11 --installers bootstrap --no-dogfood \
    --real-config framework/tests/install_quality/real-config.botfarm.example.json

# archive → fresh → restore byte-identical study
python3 -m framework.harness.botfarm_upgrade_study \
    --real-config framework/tests/install_quality/real-config.botfarm.example.json --out study.json
```

Hermetic coverage (no real botfarm, CI-safe): `framework/tests/test_botfarm_upgrade_study.py`.

## Durability / fidelity findings (recorded for #149)

See the PR / #109 report and the #149 comment. Summary:

1. **In-place merge into a pre-existing `settings.json` is not reversible** by the manifest-driven
   teardown (drives the `teardown_residue_zero` failure). The merge modifies the pre-existing file
   with **no `.bak`** (`no_backup_litter` passes), so teardown — which only removes *added* files
   and restores `.bak`s — cannot recover the original bytes. The reversible answer is the #108
   archive path, proven byte-identical here.
2. **Restore leaves out-of-scope residue** (`.git/hooks/pre-push`, emptied `.claude-backups/`).
3. **`.claude-backups/` is not gitignored**, so archive-then-fresh surfaces it as untracked in a
   real working tree.
4. **`atomic_io.atomic_write_text` has a parent-dir fsync gap** — it fsyncs the temp file and
   `os.replace`s, but never fsyncs the *parent directory*, so a crash right after the rename can
   lose the directory entry (manifest present-but-not-durable). `archive_assets` compounds this:
   the asset `shutil.move`s and the manifest write are individually non-atomic w.r.t. a crash
   *between* them, so a crash could strand a half-archive with no manifest → unrestorable.
5. **The amend path silently leaves stale config module lists** — an "upgrade" via amend does not
   reconcile `framework.config.json` hook lists to canonical (drives `config_module_lists_complete`).
