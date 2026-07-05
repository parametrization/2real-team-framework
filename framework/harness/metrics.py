"""Metric measurement (#103 vocabulary, #104 §3 Stage 3).

Each metric has a stable snake_case id (verbatim from #103), a category (A-J), a kind
(pass_fail / scored / trend), and a mechanical measurement function that reads a
``CellContext`` and returns a ``Measurement`` (value + pass + expected/observed evidence).

Every measurement is one of #104's five mechanical kinds: a return code, a stdout/stderr
line, a file check, a byte-diff, or a fired-hook payload. Nothing is invented — the oracle is
the captured process(es) and the post-install file tree. Stdlib only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import manifest
from .records import KIND_PASS_FAIL, KIND_SCORED, KIND_TREND

# The exact installed root-settings hook wiring (asserted by settings_hooks_wired).
_EXPECTED_EVENTS = {
    "SessionStart": {None},                       # matcher-less -> start_dispatcher.py
    "PreToolUse": {"Bash", "Agent"},              # -> dispatcher.py
    "Stop": {None},                               # matcher-less -> stop_dispatcher.py
    "PostToolUse": {"Bash", "Edit|Write|MultiEdit|NotebookEdit"},  # -> post_dispatcher.py
}
_EVENT_DISPATCHER = {
    "SessionStart": "start_dispatcher.py",
    "PreToolUse": "dispatcher.py",
    "Stop": "stop_dispatcher.py",
    "PostToolUse": "post_dispatcher.py",
}
# framework.config.json default module lists (#84 regression guard).
_REQUIRED_PRE_BASH = {"validate_labels", "block_squash_wave_merge"}


@dataclass
class Measurement:
    """A single metric's mechanical result."""

    value: object
    passed: object  # bool for pass_fail/scored; None for pure-trend OR a skip
    expected: object
    observed: object
    notes: str = ""


@dataclass
class MetricSpec:
    metric: str
    category: str
    kind: str
    fn: Callable[["CellContext"], Measurement]


@dataclass
class CellContext:
    """Everything a metric needs to measure one (fixture, installer, permutation) cell.

    The runner populates only the auxiliaries the cell's applicable metrics require; metric
    functions defend against ``None`` and skip cleanly.
    """

    workdir: Path
    installer: str
    permutation: dict
    expect_exit: int = 0
    gate_expect: str | None = None  # "refuse" | "proceed" for repo_state_gate_correct
    primary: object = None          # RunResult of the install
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    reinstall: object = None        # RunResult of the 2nd run
    reinstall_diff: list = field(default_factory=list)  # byte-diff of .claude between runs
    dry_run: object = None
    dry_run_unchanged: object = None  # bool: target byte-identical after --dry-run
    fired: dict = field(default_factory=dict)  # name -> RunResult
    teardown_residue: object = None  # list of residual paths after manifest-driven uninstall
    preexisting: dict = field(default_factory=dict)
    child: dict = field(default_factory=dict)  # child buckets: {settings_text, config, ...}
    extra: dict = field(default_factory=dict)


# --------------------------------------------------------------------- helpers


def _skip(reason: str, *, expected=None, observed=None) -> Measurement:
    return Measurement(value=None, passed=None, expected=expected, observed=observed, notes=reason)


def _load_settings(workdir: Path) -> dict | None:
    p = workdir / ".claude" / "settings.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_config(workdir: Path) -> dict | None:
    p = workdir / ".claude" / "framework.config.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ------------------------------------------------------------ A. exit & gates


def m_install_exit_status(ctx: CellContext) -> Measurement:
    got = ctx.primary.returncode
    return Measurement(
        value=(got == ctx.expect_exit),
        passed=(got == ctx.expect_exit),
        expected={"exit": ctx.expect_exit},
        observed={"exit": got, "timed_out": ctx.primary.timed_out},
    )


def m_repo_state_gate_correct(ctx: CellContext) -> Measurement:
    out = ctx.primary.out
    rc = ctx.primary.returncode
    if ctx.gate_expect == "refuse":
        ok = rc == 1 and (
            "refusing to install (repo expectation gate)" in out
            or "looks EXISTING" in out
            or "looks FRESH" in out
        )
        installed = (ctx.workdir / ".claude" / "framework.config.json").is_file()
        ok = ok and not installed
        return Measurement(
            value=ok, passed=ok,
            expected={"exit": 1, "stdout_contains": ["refusing to install (repo expectation gate)"]},
            observed={"exit": rc, "installed": installed, "stdout_excerpt": _excerpt(out)},
        )
    # proceed leg (--expect existing|any, or an idempotent re-run)
    installed = (ctx.workdir / ".claude" / "framework.config.json").is_file()
    ok = rc == 0 and installed
    return Measurement(
        value=ok, passed=ok,
        expected={"exit": 0, "installed": True},
        observed={"exit": rc, "installed": installed},
    )


def m_invalid_config_refused(ctx: CellContext) -> Measurement:
    rc = ctx.primary.returncode
    installed = (ctx.workdir / ".claude" / "framework.config.json").is_file()
    ok = rc != 0 and not installed
    return Measurement(
        value=ok, passed=ok,
        expected={"exit": "!=0", "wrote_nothing": True},
        observed={"exit": rc, "installed": installed, "stdout_excerpt": _excerpt(ctx.primary.out)},
    )


def m_non_interactive_zero_prompts(ctx: CellContext) -> Measurement:
    # stdin is always closed; a prompt would EOFError/hang -> our timeout (124).
    ok = not ctx.primary.timed_out
    return Measurement(
        value=ok, passed=ok,
        expected={"completed_without_stdin": True},
        observed={"timed_out": ctx.primary.timed_out, "duration_s": round(ctx.primary.duration_s, 3)},
    )


# ------------------------------------------------------------ B. completeness


def m_files_installed_complete(ctx: CellContext) -> Measurement:
    expected = manifest.expected_install_set(ctx.permutation)
    if expected is None:
        return _skip(manifest.PENDING_NOTE)
    present = {p for p in ctx.after if p.startswith(".claude/") or p.startswith("ontology/")
               or p.startswith("CLAUDE.md") or p.startswith(".git/hooks/pre-push")}
    missing = sorted(expected - present)
    fraction = round(len(expected & present) / len(expected), 4) if expected else 1.0
    ok = not missing
    return Measurement(
        value=fraction, passed=ok,
        expected={"count": len(expected)},
        observed={"fraction": fraction, "missing": missing[:20], "missing_count": len(missing)},
        notes="wired to #139 golden manifest",
    )


def m_no_unexpected_files(ctx: CellContext) -> Measurement:
    from .snapshot import unexpected_paths

    stray = unexpected_paths(ctx.before, ctx.after)
    return Measurement(
        value=len(stray), passed=(not stray),
        expected={"stray": 0},
        observed={"stray_count": len(stray), "stray": stray[:20]},
    )


def m_install_snapshot_recorded(ctx: CellContext) -> Measurement:
    p = ctx.workdir / ".claude" / "install.config.json"
    if not p.is_file():
        return Measurement(False, False, {"exists": True}, {"exists": False})
    try:
        snap = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Measurement(False, False, {"parses": True}, {"parses": False})
    if ctx.installer == "cli":
        team = snap.get("team", {})
        ok = "enabled" in team
        return Measurement(ok, ok, {"team_synced": True}, {"team": team})
    return Measurement(True, True, {"exists": True}, {"keys": sorted(snap)[:10]})


# ------------------------------------------------------------ C. hook wiring


def m_settings_hooks_wired(ctx: CellContext) -> Measurement:
    settings = _load_settings(ctx.workdir)
    if settings is None:
        return Measurement(False, False, {"settings.json": "present+parseable"}, {"settings.json": None})
    hooks = settings.get("hooks", {})
    problems: list[str] = []
    for event, want_matchers in _EXPECTED_EVENTS.items():
        blocks = hooks.get(event, [])
        got_matchers = {b.get("matcher") for b in blocks}
        if got_matchers != want_matchers:
            problems.append(f"{event} matchers {sorted(map(str, got_matchers))} != {sorted(map(str, want_matchers))}")
            continue
        want_disp = _EVENT_DISPATCHER[event]
        cmds = [h.get("command", "") for b in blocks for h in b.get("hooks", [])]
        if not any(want_disp in c for c in cmds):
            problems.append(f"{event} not wired to {want_disp}")
    ok = not problems
    return Measurement(ok, ok, {"events": {k: sorted(map(str, v)) for k, v in _EXPECTED_EVENTS.items()}},
                       {"problems": problems})


def m_permissions_allowlist_present(ctx: CellContext) -> Measurement:
    settings = _load_settings(ctx.workdir)
    allow = (settings or {}).get("permissions", {}).get("allow", [])
    no_perms = ctx.permutation.get("no_permissions", False)
    if no_perms:
        ok = not allow
        return Measurement(ok, ok, {"allow": "absent"}, {"allow_count": len(allow)})
    ok = len(allow) >= 5
    return Measurement(ok, ok, {"allow": ">=5 curated rules"}, {"allow_count": len(allow)})


def m_config_module_lists_complete(ctx: CellContext) -> Measurement:
    cfg = _load_config(ctx.workdir)
    if cfg is None:
        return Measurement(False, False, {"framework.config.json": "present"}, {"present": False})
    hooks = cfg.get("hooks", {})
    pre = set(hooks.get("pre_bash", []))
    problems: list[str] = []
    if not _REQUIRED_PRE_BASH <= pre:
        problems.append(f"pre_bash missing {sorted(_REQUIRED_PRE_BASH - pre)}")
    if hooks.get("agent") != []:
        problems.append(f"hooks.agent != [] (got {hooks.get('agent')})")
    if hooks.get("stop") != ["session_handoff"]:
        problems.append(f"hooks.stop != ['session_handoff'] (got {hooks.get('stop')})")
    ok = not problems
    return Measurement(ok, ok, {"pre_bash>=": sorted(_REQUIRED_PRE_BASH), "agent": [], "stop": ["session_handoff"]},
                       {"problems": problems})


# ------------------------------------------------------------ D. behavioral


def m_gate_blocks_no_verify(ctx: CellContext) -> Measurement:
    r = ctx.fired.get("no_verify")
    if r is None:
        return _skip("hook not fired")
    ok = r.returncode == 2 and "no-verify" in r.stdout.lower()
    return Measurement(ok, ok, {"exit": 2, "mentions": "no-verify"},
                       {"exit": r.returncode, "stdout_excerpt": _excerpt(r.stdout)})


def m_gate_passes_benign(ctx: CellContext) -> Measurement:
    r = ctx.fired.get("benign")
    if r is None:
        return _skip("hook not fired")
    ok = r.returncode == 0 and r.stdout.strip() == ""
    return Measurement(ok, ok, {"exit": 0, "stdout": "empty"},
                       {"exit": r.returncode, "stdout_excerpt": _excerpt(r.stdout)})


def m_identity_gate_active(ctx: CellContext) -> Measurement:
    cfg = _load_config(ctx.workdir)
    roster = (ctx.workdir / ".claude" / "team" / "roster.json").is_file()
    enforce = bool((cfg or {}).get("identity", {}).get("enforce"))
    pre = (cfg or {}).get("hooks", {}).get("pre_bash", [])
    first_is_identity = pre[:1] == ["validate_commit_identity"]
    wired = roster and enforce and first_is_identity
    r = ctx.fired.get("foreign_commit")
    fired_block = (r is not None and r.returncode == 2)
    ok = wired and fired_block
    return Measurement(
        ok, ok,
        {"roster": True, "enforce": True, "pre_bash[0]": "validate_commit_identity", "foreign_commit_exit": 2},
        {"roster": roster, "enforce": enforce, "identity_first": first_is_identity,
         "foreign_commit_exit": (r.returncode if r else None)},
    )


def m_shell_gate_respected(ctx: CellContext) -> Measurement:
    r = ctx.fired.get("bashism")
    if r is None:
        return _skip("hook not fired")
    ok = r.returncode == 0 and "ZSH-SAFETY" in r.stdout
    return Measurement(ok, ok, {"exit": 0, "advisory": "ZSH-SAFETY"},
                       {"exit": r.returncode, "stdout_excerpt": _excerpt(r.stdout)})


# ------------------------------------------------------------ E. ontology


def m_ontology_overlay_seeded(ctx: CellContext) -> Measurement:
    onto = ctx.workdir / "ontology"
    names = ("domain.yaml", "services.yaml", "conventions.md", "README.md")
    missing = [n for n in names if not (onto / n).is_file()]
    ok = not missing
    return Measurement(ok, ok, {"overlay": list(names)}, {"missing": missing})


def m_ontology_structural_generated(ctx: CellContext) -> Measurement:
    struct = ctx.workdir / "ontology" / "structural"
    graph_p = struct / "code-graph.json"
    llms_p = struct / "llms.txt"
    if not graph_p.is_file() or not llms_p.is_file():
        return Measurement(False, False, {"files": ["code-graph.json", "llms.txt"]},
                           {"code-graph.json": graph_p.is_file(), "llms.txt": llms_p.is_file()})
    try:
        graph = json.loads(graph_p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Measurement(False, False, {"parses": True}, {"parses": False})
    has_shape = "nodes" in graph and "edges" in graph
    want_src = ctx.extra.get("expect_source_path")
    src_ok = True
    if want_src:
        paths = {n.get("path") for n in graph.get("nodes", [])}
        src_ok = want_src in paths
    ok = has_shape and src_ok
    return Measurement(ok, ok, {"nodes+edges": True, "source_in_graph": want_src},
                       {"has_shape": has_shape, "source_present": src_ok})


def m_ontology_fail_open(ctx: CellContext) -> Measurement:
    out = ctx.primary.out
    rc = ctx.primary.returncode
    skipped = "structural index:  SKIPPED" in out or "install continues" in out
    overlay = (ctx.workdir / "ontology" / "domain.yaml").is_file()
    dispatcher = (ctx.workdir / ".claude" / "hooks" / "dispatcher.py").is_file()
    ok = rc == 0 and skipped and overlay and dispatcher
    return Measurement(ok, ok, {"exit": 0, "structural": "SKIPPED", "overlay+runtime": True},
                       {"exit": rc, "skipped_line": skipped, "overlay": overlay, "dispatcher": dispatcher})


# ------------------------------------------------------------ F. idempotency & safety


def m_reinstall_idempotent(ctx: CellContext) -> Measurement:
    r = ctx.reinstall
    if r is None:
        return _skip("second run not performed")
    out = r.out
    ok = (
        r.returncode == 0
        and "skipped (exists)" in out
        and "already wired" in out
        and not ctx.reinstall_diff
    )
    return Measurement(ok, ok,
                       {"exit": 0, "stdout": ["skipped (exists)", "already wired"], "claude_byte_diff": "empty"},
                       {"exit": r.returncode, "byte_diff": ctx.reinstall_diff[:20],
                        "byte_diff_count": len(ctx.reinstall_diff)})


def m_claude_md_backup_safe(ctx: CellContext) -> Measurement:
    original = ctx.preexisting.get("claude_md")
    if original is None:
        return _skip("no pre-existing CLAUDE.md in this fixture")
    # The original bytes must be recoverable from a .bak/.bak.N and a new CLAUDE.md written.
    baks = sorted(ctx.workdir.glob("CLAUDE.md.bak*"))
    recovered = any(b.read_bytes() == original for b in baks)
    new_written = (ctx.workdir / "CLAUDE.md").is_file()
    ok = recovered and new_written
    return Measurement(ok, ok, {"original_recoverable": True, "new_CLAUDE.md": True},
                       {"backups": [b.name for b in baks], "recovered": recovered, "new_written": new_written})


def m_settings_merge_preserves_foreign(ctx: CellContext) -> Measurement:
    key = ctx.preexisting.get("settings_foreign_key")
    if not key:
        return _skip("no pre-existing foreign settings key in this fixture")
    settings = _load_settings(ctx.workdir)
    fk, fv = key
    ok = settings is not None and settings.get(fk) == fv
    return Measurement(ok, ok, {f"settings[{fk}]": fv},
                       {"present": ok, "value": (settings or {}).get(fk)})


def m_dry_run_writes_nothing(ctx: CellContext) -> Measurement:
    if ctx.dry_run is None:
        return _skip("dry-run leg not performed")
    out = ctx.dry_run.out
    marker = "-- plan --" in out or "would generate" in out or "would write" in out
    ok = ctx.dry_run.returncode == 0 and bool(ctx.dry_run_unchanged) and marker
    return Measurement(ok, ok, {"exit": 0, "tree_unchanged": True, "stdout": "-- plan --/would …"},
                       {"exit": ctx.dry_run.returncode, "tree_unchanged": ctx.dry_run_unchanged,
                        "plan_marker": marker})


# ------------------------------------------------------------ G. meta / child wiring


def m_child_wiring_portable(ctx: CellContext) -> Measurement:
    children = ctx.child.get("children", [])
    if not children:
        return _skip("no child settings in this fixture")
    problems: list[str] = []
    machine_root = ctx.extra.get("machine_root", "")
    for c in children:
        text = c["settings_text"]
        if machine_root and machine_root in text:
            problems.append(f"{c['path']}: machine-absolute path leaked")
        anchor = f"$CLAUDE_PROJECT_DIR/{c['rel']}/.claude/hooks/"
        if anchor not in text:
            problems.append(f"{c['path']}: missing anchor {anchor}")
        child_dir = ctx.workdir / c["path"] / ".claude"
        for local in ("hooks", "lib", "team/charter", "ontology"):
            if (child_dir / local).exists():
                problems.append(f"{c['path']}: unexpected local {local}")
    ok = not problems
    return Measurement(ok, ok, {"portable": True, "no_local_hooks_lib_charter": True},
                       {"problems": problems})


def m_child_flavor_filtered(ctx: CellContext) -> Measurement:
    children = ctx.child.get("children", [])
    infra = [c for c in children if c.get("flavor") == "infra"]
    product = [c for c in children if c.get("flavor") == "product"]
    if not infra and not product:
        return _skip("no flavored children in this fixture")
    problems: list[str] = []
    for c in infra:
        s = json.loads(c["settings_text"])
        events = set(s.get("hooks", {}))
        if events != {"PreToolUse", "PostToolUse"}:
            problems.append(f"{c['path']} infra events {sorted(events)} != PreToolUse+PostToolUse")
        matchers = {b.get("matcher") for blocks in s["hooks"].values() for b in blocks}
        if matchers != {"Bash"}:
            problems.append(f"{c['path']} infra matchers {sorted(map(str, matchers))} != Bash-only")
    for c in product:
        s = json.loads(c["settings_text"])
        events = set(s.get("hooks", {}))
        if events != {"SessionStart", "PreToolUse", "PostToolUse", "Stop"}:
            problems.append(f"{c['path']} product events {sorted(events)} incomplete")
    ok = not problems
    return Measurement(ok, ok, {"infra": "Bash pre/post only", "product": "all events"},
                       {"problems": problems})


def m_child_parent_precondition(ctx: CellContext) -> Measurement:
    rc = ctx.primary.returncode
    out = ctx.primary.out
    installed = (ctx.workdir / ".claude" / "settings.json").is_file()
    ok = rc == 1 and "does not have the framework installed" in out and not installed
    return Measurement(ok, ok, {"exit": 1, "message": "parent … does not have the framework installed"},
                       {"exit": rc, "installed": installed, "stdout_excerpt": _excerpt(out)})


def m_child_config_inherits(ctx: CellContext) -> Measurement:
    cfg = _load_config(ctx.workdir)
    if cfg is None:
        return Measurement(False, False, {"framework.config.json": "present"}, {"present": False})
    proj = cfg.get("project", {})
    want = ctx.extra.get("child_expect", {})
    problems: list[str] = []
    if proj.get("model") != "child":
        problems.append(f"model={proj.get('model')} != child")
    if "parent" not in proj:
        problems.append("no project.parent")
    for k, v in want.items():
        if proj.get(k) != v:
            problems.append(f"project.{k}={proj.get(k)} != {v}")
    if "scm" not in cfg:
        problems.append("scm not inherited")
    ok = not problems
    return Measurement(ok, ok, {"model": "child", "parent+flavor": True, "inherits_scm": True},
                       {"problems": problems, "project": proj})


# ------------------------------------------------------------ H. teardown / residue


def m_teardown_residue_zero(ctx: CellContext) -> Measurement:
    residue = ctx.teardown_residue
    if residue is None:
        return _skip("manifest-driven teardown leg not run for this fixture")
    ok = len(residue) == 0
    return Measurement(len(residue), ok, {"residue": 0},
                       {"residue_count": len(residue), "residue": residue[:20]})


def m_no_backup_litter(ctx: CellContext) -> Measurement:
    # A happy-path fresh install (no conflict) must create zero .bak* files.
    baks = [p.name for p in ctx.workdir.rglob("*.bak*") if ".git" not in p.parts]
    ok = not baks
    return Measurement(len(baks), ok, {"bak_files": 0}, {"bak_count": len(baks), "baks": baks[:20]})


# ------------------------------------------------------------ I. performance / trend


def m_install_duration_s(ctx: CellContext) -> Measurement:
    d = round(ctx.primary.duration_s, 4)
    return Measurement(d, None, {"trend": True}, {"seconds": d})


def m_ontology_gen_duration_s(ctx: CellContext) -> Measurement:
    # Attribute the whole install wall-clock as an upper bound proxy for the ontology-gen
    # buckets (B3/B9 run --with-ontology; the structural gen dominates their delta over time).
    d = round(ctx.primary.duration_s, 4)
    return Measurement(d, None, {"trend": True}, {"seconds_upper_bound": d})


# ------------------------------------------------------------ J. dogfood parity


def m_reinstall_parity_clean(ctx: CellContext) -> Measurement:
    r = ctx.primary
    ok = r.returncode == 0
    return Measurement(ok, ok, {"exit": 0, "invariant": "canonical<->live in sync (#116)"},
                       {"exit": r.returncode, "stdout_excerpt": _excerpt(r.out)})


def _excerpt(text: str, limit: int = 600) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + " …[truncated]"


# --------------------------------------------------------------------- registry

REGISTRY: dict[str, MetricSpec] = {}


def _reg(metric: str, category: str, kind: str, fn) -> None:
    REGISTRY[metric] = MetricSpec(metric, category, kind, fn)


_reg("install_exit_status", "A", KIND_PASS_FAIL, m_install_exit_status)
_reg("repo_state_gate_correct", "A", KIND_PASS_FAIL, m_repo_state_gate_correct)
_reg("invalid_config_refused", "A", KIND_PASS_FAIL, m_invalid_config_refused)
_reg("non_interactive_zero_prompts", "A", KIND_PASS_FAIL, m_non_interactive_zero_prompts)
_reg("files_installed_complete", "B", KIND_SCORED, m_files_installed_complete)
_reg("no_unexpected_files", "B", KIND_PASS_FAIL, m_no_unexpected_files)
_reg("install_snapshot_recorded", "B", KIND_PASS_FAIL, m_install_snapshot_recorded)
_reg("settings_hooks_wired", "C", KIND_PASS_FAIL, m_settings_hooks_wired)
_reg("permissions_allowlist_present", "C", KIND_PASS_FAIL, m_permissions_allowlist_present)
_reg("config_module_lists_complete", "C", KIND_PASS_FAIL, m_config_module_lists_complete)
_reg("gate_blocks_no_verify", "D", KIND_PASS_FAIL, m_gate_blocks_no_verify)
_reg("gate_passes_benign", "D", KIND_PASS_FAIL, m_gate_passes_benign)
_reg("identity_gate_active", "D", KIND_PASS_FAIL, m_identity_gate_active)
_reg("shell_gate_respected", "D", KIND_PASS_FAIL, m_shell_gate_respected)
_reg("ontology_overlay_seeded", "E", KIND_PASS_FAIL, m_ontology_overlay_seeded)
_reg("ontology_structural_generated", "E", KIND_PASS_FAIL, m_ontology_structural_generated)
_reg("ontology_fail_open", "E", KIND_PASS_FAIL, m_ontology_fail_open)
_reg("reinstall_idempotent", "F", KIND_PASS_FAIL, m_reinstall_idempotent)
_reg("claude_md_backup_safe", "F", KIND_PASS_FAIL, m_claude_md_backup_safe)
_reg("settings_merge_preserves_foreign", "F", KIND_PASS_FAIL, m_settings_merge_preserves_foreign)
_reg("dry_run_writes_nothing", "F", KIND_PASS_FAIL, m_dry_run_writes_nothing)
_reg("child_wiring_portable", "G", KIND_PASS_FAIL, m_child_wiring_portable)
_reg("child_flavor_filtered", "G", KIND_PASS_FAIL, m_child_flavor_filtered)
_reg("child_parent_precondition", "G", KIND_PASS_FAIL, m_child_parent_precondition)
_reg("child_config_inherits", "G", KIND_PASS_FAIL, m_child_config_inherits)
_reg("teardown_residue_zero", "H", KIND_SCORED, m_teardown_residue_zero)
_reg("no_backup_litter", "H", KIND_PASS_FAIL, m_no_backup_litter)
_reg("install_duration_s", "I", KIND_TREND, m_install_duration_s)
_reg("ontology_gen_duration_s", "I", KIND_TREND, m_ontology_gen_duration_s)
_reg("reinstall_parity_clean", "J", KIND_PASS_FAIL, m_reinstall_parity_clean)
