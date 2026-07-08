"""Load-bearing wiring test for bootstrap._schema_defaults() (issue #196).

`bootstrap._schema_defaults()` is what the installer WRITES into a target repo's
`framework.config.json` — the third of the three `hooks.pre_bash` copies
`test_defaults_sync.py` keeps in sync. This module pins the #196 wiring from the
installer's side: a freshly bootstrapped repo's written config activates
`block_gh_pr_review` (a module present in the schema but missing from the written
config would never run in a deployed repo — the exact #84 drift class).

Load-bearing (revert -> fail): drop the `block_gh_pr_review` entry from
`bootstrap._schema_defaults()["hooks"]["pre_bash"]` and
`test_installer_writes_hook_into_pre_bash` fails.

Complements `test_bootstrap_smoke.py` (end-to-end install) with a targeted unit
assertion on the written-defaults source. Stdlib + pytest only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _FRAMEWORK_ROOT.parent
sys.path.insert(0, str(_REPO_ROOT))  # make `framework.harness` importable (namespace package)
sys.path.insert(0, str(_FRAMEWORK_ROOT / "install"))

import bootstrap  # noqa: E402

from framework.harness import metrics  # noqa: E402  (read-only ORACLE — never mutated here)


def _written_pre_bash() -> list[str]:
    return list(bootstrap._schema_defaults()["hooks"]["pre_bash"])


def test_installer_writes_hook_into_pre_bash() -> None:
    """A bootstrapped repo's written config activates block_gh_pr_review."""
    assert "block_gh_pr_review" in _written_pre_bash()


def test_written_order_groups_hook_with_verdict_grammar_gate() -> None:
    """block_gh_pr_review follows validate_review_comment_format in the written
    order (matches the schema/runtime copies test_defaults_sync pins equal)."""
    pre = _written_pre_bash()
    assert pre.index("block_gh_pr_review") == pre.index("validate_review_comment_format") + 1


# --------------------------------------------------------------------------
# ensure_gitignore_entries() normalization pairing (#216).
#
# Full coverage (dedup / stable-order / blank-collapse / run-twice-no-diff,
# each mutation-verified) lives in test_gitignore_ledger_default.py, which
# pre-dates and is dedicated to this helper. This test pins the same
# load-bearing contract directly against bootstrap.py so the file-pairing
# gate (charter/pull-requests.md § Pre-Review Self-Check) has a same-stem
# test for THIS file's own new behavior.


def test_ensure_gitignore_entries_dedupes_and_orders_deterministically(tmp_path: Path) -> None:
    """Load-bearing (revert -> fail): calling with a duplicated/unordered entries
    tuple must still produce a single, alphabetically-stable set of appended
    lines. Reverting either the input-dedup step or the ``sorted(...)`` around
    the missing entries in ``ensure_gitignore_entries`` makes this fail."""
    # Deliberately passed in the REVERSE of sorted order (with a repeat), so this
    # catches both a dropped dedup step and a dropped `sorted(...)` independently.
    bootstrap.ensure_gitignore_entries(
        tmp_path, (".claude/x.json", ".claude-backups/", ".claude-backups/"), dry_run=False
    )
    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count(".claude-backups/") == 1
    # sorted(...) output is deterministic regardless of call-site argument order.
    assert lines.index(".claude-backups/") < lines.index(".claude/x.json")


# --------------------------------------------------------------------------
# Amend / upgrade-over-diverged-install: write_config() must RECONCILE (not
# union) the framework hook module-lists so a re-install over a diverged live
# config DROPS stale entries and converges on the shipped canonical set
# (#162, closed by #238). The harness metric `config_module_lists_complete`
# is the ORACLE — this test drives the real amend write and evaluates that
# metric read-only, proving the fix from the installer's own side.


def _canonical_cfg() -> dict:
    """The RUNTIME config an amend writes: schema defaults with the identity gate
    prepended (what the team-enabled standalone/amend path builds at line ~1524)."""
    cfg = bootstrap._schema_defaults()
    pre = cfg["hooks"]["pre_bash"]
    if "validate_commit_identity" not in pre:
        pre.insert(0, "validate_commit_identity")
    return cfg


def _diverged_live_config() -> dict:
    """A live install that has DRIFTED: pre_bash carries a stale extra module and
    has lost required entries + canonical order; agent is non-empty; stop is wrong.
    Also carries a user-owned field (`scm.owner`) and a custom `pre_push_commands`
    that the amend MUST preserve untouched."""
    return {
        "version": 1,
        "scm": {"owner": "acme-user-set"},  # user field — must survive the amend
        "hooks": {
            "pre_bash": ["validate_commit_identity", "stale_removed_module", "validate_labels"],
            "post_bash": ["warn_pipe_mask_rc"],
            "agent": ["legacy_agent_hook"],          # must reconcile -> []
            "stop": ["some_old_stop", "session_handoff"],  # must reconcile -> [session_handoff]
            "pre_push_commands": ["pytest -q"],      # user data — must be preserved verbatim
        },
    }


def _metric_passes(workdir: Path) -> metrics.Measurement:
    ctx = metrics.CellContext(workdir=workdir, installer="bootstrap", permutation={})
    return metrics.m_config_module_lists_complete(ctx)


def test_amend_reconciles_diverged_config_module_lists(tmp_path: Path) -> None:
    """Load-bearing (revert -> fail): amending over a diverged config converges the
    hook module-lists onto the canonical set — stale entries gone, required order
    restored, agent->[] and stop->[session_handoff] — and the ORACLE metric passes.
    Reverting the reconcile in `write_config` (back to blanket skip-if-exists) makes
    both the stale-entry assertion and the metric assertion fail."""
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "framework.config.json").write_text(
        json.dumps(_diverged_live_config()) + "\n", encoding="utf-8"
    )

    # Pre-condition: the diverged config FAILS the oracle before the amend.
    assert _metric_passes(tmp_path).passed is False

    status = bootstrap.write_config(claude, _canonical_cfg(), force=False, dry_run=False)
    assert "reconciled" in status

    written = json.loads((claude / "framework.config.json").read_text(encoding="utf-8"))
    hooks = written["hooks"]
    # Stale accumulation is GONE (reconcile, not union).
    assert "stale_removed_module" not in hooks["pre_bash"]
    assert hooks["agent"] == []
    assert hooks["stop"] == ["session_handoff"]
    # pre_bash converged to the canonical shipped list, in canonical order.
    assert hooks["pre_bash"] == _canonical_cfg()["hooks"]["pre_bash"]
    assert metrics._REQUIRED_PRE_BASH <= set(hooks["pre_bash"])
    # User-owned fields are preserved verbatim across the amend.
    assert written["scm"]["owner"] == "acme-user-set"
    assert hooks["pre_push_commands"] == ["pytest -q"]
    # The ORACLE now passes post-amend.
    assert _metric_passes(tmp_path).passed is True


def test_amend_reconcile_is_idempotent(tmp_path: Path) -> None:
    """Amending twice == amending once: no drift, no duplication. The 2nd amend
    is a no-op (config already canonical) and the file stays byte-identical."""
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "framework.config.json").write_text(
        json.dumps(_diverged_live_config()) + "\n", encoding="utf-8"
    )
    bootstrap.write_config(claude, _canonical_cfg(), force=False, dry_run=False)
    after_first = (claude / "framework.config.json").read_text(encoding="utf-8")

    status2 = bootstrap.write_config(claude, _canonical_cfg(), force=False, dry_run=False)
    assert "already canonical" in status2
    assert (claude / "framework.config.json").read_text(encoding="utf-8") == after_first
    assert _metric_passes(tmp_path).passed is True


def test_amend_fail_open_on_malformed_live_config(tmp_path: Path) -> None:
    """Fail-open (AC #3): a malformed/partial live config never crashes the amend —
    it degrades gracefully and leaves the file untouched rather than throwing."""
    claude = tmp_path / ".claude"
    claude.mkdir()
    dest = claude / "framework.config.json"
    dest.write_text("{not valid json", encoding="utf-8")
    status = bootstrap.write_config(claude, _canonical_cfg(), force=False, dry_run=False)
    assert "unreadable" in status
    assert dest.read_text(encoding="utf-8") == "{not valid json"  # left untouched


def test_reconcile_module_lists_drops_stale_without_union() -> None:
    """Unit: reconcile REPLACES a diverged list with the canonical one (drops the
    stale entry) rather than unioning the two — and reports `changed`."""
    existing = {"hooks": {"pre_bash": ["stale", "validate_labels"], "agent": ["x"], "stop": []}}
    canonical = {"hooks": {"pre_bash": ["validate_labels", "block_squash_wave_merge"],
                           "agent": [], "stop": ["session_handoff"]}}
    merged, changed = bootstrap.reconcile_module_lists(existing, canonical)
    assert changed is True
    assert merged["hooks"]["pre_bash"] == ["validate_labels", "block_squash_wave_merge"]
    assert "stale" not in merged["hooks"]["pre_bash"]
    assert merged["hooks"]["agent"] == [] and merged["hooks"]["stop"] == ["session_handoff"]
    # Idempotent: reconciling the result again reports no change.
    _, changed2 = bootstrap.reconcile_module_lists(merged, canonical)
    assert changed2 is False


def test_reconcile_module_lists_rebuilds_partial_hooks() -> None:
    """Unit / fail-open: a config MISSING the hooks block gets it rebuilt from the
    canonical lists without raising."""
    merged, changed = bootstrap.reconcile_module_lists(
        {"version": 1}, {"hooks": {"agent": [], "stop": ["session_handoff"]}}
    )
    assert changed is True
    assert merged["hooks"]["agent"] == [] and merged["hooks"]["stop"] == ["session_handoff"]
    assert merged["version"] == 1  # untouched
