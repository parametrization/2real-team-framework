#!/usr/bin/env python3
"""Deterministic memory -> charter -> skill -> hook promotion auditor (#102, P0).

Backs the ``/promotion-audit`` skill. Reads the pending entries of the
generic-prompt ledger (:mod:`generic_prompt_tracker`, written silently by the
:mod:`suggest_generic_prompt` PostToolUse hook), classifies each into a tier,
and acts:

  * **AUTO** — the artifact's content already carries BOTH halves of the
    charter's promotion marker convention (see
    ``framework/assets/team/charter/skills.md`` § Promotion Pipeline Marker
    Convention): an ``<!-- Promoted from memory... -->`` comment AND a
    ``**Promotion provenance:**`` line. A human already did the promotion
    bookkeeping in-place; the auditor's job is purely mechanical — flip the
    ledger decision to ``genericized`` and log it. No judgment call is made.
  * **DECIDE** — a pending artifact with no promotion markers. The auditor
    never guesses; it files (or, in ``--dry-run``, prints) a draft issue
    describing the candidate and leaves the ledger entry ``pending`` for a
    human call.
  * **DONE** — already decided (``genericized`` or ``skip``); nothing to do.

**Determinism.** Every function that shapes output (:func:`classify_tier`,
:func:`plan_audit`, :func:`render_audit_log`, :func:`render_draft_issue_body`)
is a pure function of its inputs — no wall-clock reads, no randomness, no
network — so the SAME ledger + artifact contents ALWAYS produce byte-identical
output. The only non-deterministic inputs (the current timestamp, the gh
issue-filing side effect) are pushed to the thin I/O layer at the bottom
(:func:`run_audit`) and are injectable in tests via ``at=`` / ``runner=``.

Layering mirrors ``trust_signals.py``: a pure classification/render core,
callable standalone on hand-built data; a thin SCM/I-O layer (:func:`run_audit`,
:func:`_run_gh`) that wires it to a real ledger + real ``gh``; a CLI.

Charter reference: [[reference_config_driven_architecture]]; ledger reference:
``generic_prompt_tracker.py``.

CLI:
  helpers.py plan <wave> [--ledger PATH] [--root PATH]
      Pure-plan JSON: reads the ledger + candidate contents from disk, prints
      the classification plan. Read-only — no writes, no gh calls.
  helpers.py run  <wave> [--ledger PATH] [--root PATH] [--label L] [--dry-run]
      Applies the plan: auto-promotes AUTO-tier ledger entries (always — this
      is a mechanical, reversible local write, never gated), files DECIDE-tier
      draft issues via ``gh issue create`` (skipped under ``--dry-run``, which
      prints the bodies instead), and writes the per-wave audit log to
      ``paths.promotion_audit_log/wave_<id>.md``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# The skill dir (assets/skills/promotion-audit or .claude/skills/promotion-audit) is a
# sibling of hooks/ and lib/ under a common parent (assets/ or .claude/) in BOTH the
# source tree and an installed tree — mirrors the lib->hooks bridge trust_signals.py /
# lifecycle.py use.
_SKILL_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _SKILL_DIR.parent.parent
_HOOKS_DIR = _ROOT_DIR / "hooks"
_LIB_DIR = _ROOT_DIR / "lib"
sys.path.insert(0, str(_HOOKS_DIR))
sys.path.insert(0, str(_LIB_DIR))

from _framework_config import config  # noqa: E402
import generic_prompt_tracker as gpt  # noqa: E402

_GH_TIMEOUT = 60

TIER_DONE = "DONE"
TIER_AUTO = "AUTO"
TIER_DECIDE = "DECIDE"

# The charter's Promotion Pipeline Marker Convention (skills.md): a leading HTML
# comment naming the memory source, and a bold "Promotion provenance:" line. Both
# must be present for the AUTO tier — either alone is not a completed promotion.
_MARKER_COMMENT_RE = re.compile(r"<!--\s*Promoted from memory\b.*?-->", re.IGNORECASE | re.DOTALL)
_PROVENANCE_LABEL_RE = re.compile(r"\*\*Promotion provenance:\*\*")


# ---------------------------------------------------------------------------
# Pure classification / rendering core (no I/O)
# ---------------------------------------------------------------------------


def has_promotion_markers(content: str) -> bool:
    """True when *content* carries BOTH halves of the marker convention."""
    return bool(_MARKER_COMMENT_RE.search(content) and _PROVENANCE_LABEL_RE.search(content))


def classify_tier(entry: dict, content: str | None) -> str:
    """The tier for one ledger entry: DONE / AUTO / DECIDE. Pure.

    ``entry`` is one ``ledger["candidates"][artifact]`` value; ``content`` is the
    artifact's current file text (``None`` if unreadable/missing — treated as
    "no markers", never auto-promoted).
    """
    decision = str(entry.get("decision", gpt.PENDING))
    if decision != gpt.PENDING:
        return TIER_DONE
    if content is not None and has_promotion_markers(content):
        return TIER_AUTO
    return TIER_DECIDE


def plan_audit(candidates: dict, contents: dict) -> dict:
    """Pure: classify every candidate, deterministically ordered by artifact name.

    ``candidates`` is ``ledger["candidates"]``; ``contents`` maps artifact ->
    file text (or ``None``). Returns ``{"auto": [...], "decide": [...], "done":
    [...]}``, each a sorted list of artifact names.
    """
    plan: dict[str, list[str]] = {"auto": [], "decide": [], "done": []}
    for artifact in sorted(candidates):
        tier = classify_tier(candidates[artifact], contents.get(artifact))
        key = {"AUTO": "auto", "DECIDE": "decide", "DONE": "done"}[tier]
        plan[key].append(artifact)
    return plan


def render_audit_log(wave: str, plan: dict, *, generated_at: str) -> str:
    """Pure: the per-wave audit-log markdown for *plan*. Deterministic text."""
    lines = [f"# Promotion Audit — wave {wave}", "", f"Generated: {generated_at}", ""]

    def _section(title: str, key: str) -> None:
        items = plan.get(key, [])
        lines.append(f"## {title} ({len(items)})")
        if items:
            lines.extend(f"- {a}" for a in items)
        else:
            lines.append("- (none)")
        lines.append("")

    _section("Auto-promoted", "auto")
    _section("Filed for decision", "decide")
    _section("Already decided", "done")
    return "\n".join(lines).rstrip() + "\n"


def render_draft_issue_title(artifact: str) -> str:
    return f"[promotion-audit] genericize or skip: {artifact}"


def render_draft_issue_body(artifact: str, entry: dict, *, wave: str) -> str:
    """Pure: the deterministic draft-issue body for a DECIDE-tier candidate."""
    detail = entry.get("detail") or "(no detail recorded)"
    first_touched = entry.get("decided_at", "unknown")
    return (
        f"The promotion-audit pipeline flagged `{artifact}` as a pending "
        f"promotion candidate (wave {wave}).\n\n"
        f"- First touched: {first_touched}\n"
        f"- Detail: {detail}\n\n"
        "No promotion markers were found on this artifact (the charter's "
        "`<!-- Promoted from memory... -->` + `**Promotion provenance:**` "
        "convention — see `team/charter/skills.md`), so this needs a human "
        "call: **genericize** it into `framework/assets/**` (and mark it per "
        "the convention), or **skip** it as project-specific "
        "(`generic_prompt_tracker.py record " + artifact + " --decision skip`).\n"
    )


# ---------------------------------------------------------------------------
# I/O layer (ledger + filesystem + gh). Everything above is reusable standalone.
# ---------------------------------------------------------------------------


def _now_iso(at: str | None = None) -> str:
    if at:
        return at
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_candidate_contents(root: Path, candidates: dict) -> dict[str, str | None]:
    """Read each candidate artifact's current text relative to *root*. Fail-open per-file."""
    out: dict[str, str | None] = {}
    for artifact in candidates:
        try:
            out[artifact] = (root / artifact).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            out[artifact] = None
    return out


def build_plan(ledger_path: Path, root: Path) -> tuple[dict, dict]:
    """Load the ledger, read pending-candidate contents, and return (ledger, plan)."""
    ledger = gpt.load_ledger(ledger_path)
    candidates = ledger.get("candidates", {})
    contents = read_candidate_contents(root, candidates)
    plan = plan_audit(candidates, contents)
    return ledger, plan


def apply_auto_promotions(ledger_path: Path, artifacts: list[str], wave: str, *, at: str | None = None) -> None:
    """Mechanically flip each AUTO-tier artifact's ledger decision to genericized."""
    for artifact in artifacts:
        gpt.record_candidate(
            ledger_path,
            artifact,
            decision=gpt.GENERICIZED,
            detail="auto-promoted: promotion markers already present",
            wave=wave,
            at=at,
        )


def _run_gh(args: list[str]) -> str:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, check=True, timeout=_GH_TIMEOUT)
    return proc.stdout


def file_draft_issues(
    candidates: dict,
    artifacts: list[str],
    wave: str,
    *,
    label: str | None = None,
    runner=_run_gh,
) -> list[dict]:
    """File one draft issue per DECIDE-tier artifact. Returns the filed-issue records.

    ``runner`` is injectable (tests pass a stub instead of shelling out to real gh).
    """
    filed: list[dict] = []
    for artifact in artifacts:
        entry = candidates.get(artifact, {})
        title = render_draft_issue_title(artifact)
        body = render_draft_issue_body(artifact, entry, wave=wave)
        args = ["issue", "create", "--title", title, "--body", body]
        if label:
            args += ["--label", label]
        try:
            output = runner(args)
        except (subprocess.SubprocessError, OSError) as exc:
            output = f"ERROR: {exc}"
        filed.append({"artifact": artifact, "title": title, "body": body, "result": output})
    return filed


def default_audit_log_path(wave: str, cfg=None) -> Path | None:
    cfg = cfg or config()
    if cfg.path is None:
        return None
    rel = cfg.get("paths.promotion_audit_log", ".claude/team/promotion_audit_log")
    return cfg.path.parent.parent / rel / f"wave_{wave}.md"


def run_audit(
    ledger_path: Path,
    root: Path,
    wave: str,
    *,
    label: str | None = None,
    dry_run: bool = True,
    at: str | None = None,
    audit_log_path: Path | None = None,
    cfg=None,
    runner=_run_gh,
) -> dict:
    """Orchestrate one full audit pass: plan, auto-promote, file drafts, log.

    Always applies AUTO-tier ledger promotions (a mechanical, local, reversible
    write — never gated). ``dry_run=True`` (default) skips the actual
    ``gh issue create`` call for DECIDE-tier candidates and instead reports the
    bodies that WOULD be filed; the audit log is still written either way.
    ``runner`` is forwarded to :func:`file_draft_issues` (tests inject a stub
    instead of shelling out to real ``gh``).
    """
    ledger, plan = build_plan(ledger_path, root)
    candidates = ledger.get("candidates", {})
    generated_at = _now_iso(at)

    apply_auto_promotions(ledger_path, plan["auto"], wave, at=generated_at)

    if dry_run:
        filed = [
            {
                "artifact": a,
                "title": render_draft_issue_title(a),
                "body": render_draft_issue_body(a, candidates.get(a, {}), wave=wave),
                "result": "DRY-RUN (not filed)",
            }
            for a in plan["decide"]
        ]
    else:
        filed = file_draft_issues(candidates, plan["decide"], wave, label=label, runner=runner)

    log_path = audit_log_path or default_audit_log_path(wave, cfg=cfg)
    log_text = render_audit_log(wave, plan, generated_at=generated_at)
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(log_text, encoding="utf-8")

    return {
        "wave": wave,
        "generated_at": generated_at,
        "plan": plan,
        "filed": filed,
        "audit_log_path": str(log_path) if log_path is not None else None,
        "audit_log": log_text,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli_root(args: argparse.Namespace) -> Path:
    if args.root:
        return Path(args.root)
    cfg = config()
    if cfg.path is not None:
        return cfg.path.parent.parent
    return Path.cwd()


def _cli_cfg(root: Path):
    """Config resolved from *root* — NOT ambient cwd — so an explicit ``--root``
    always drives every path default (ledger, audit log) consistently."""
    return config(start_dir=str(root))


def _cli_ledger_path(args: argparse.Namespace, root: Path, cfg) -> Path:
    if args.ledger:
        return Path(args.ledger)
    resolved = gpt.default_ledger_path(cfg)
    if resolved is None:
        print("ERROR: --ledger (or a resolvable framework config) is required", file=sys.stderr)
        raise SystemExit(2)
    return resolved


def _cmd_plan(args: argparse.Namespace) -> int:
    root = _cli_root(args)
    cfg = _cli_cfg(root)
    _, plan = build_plan(_cli_ledger_path(args, root, cfg), root)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    root = _cli_root(args)
    cfg = _cli_cfg(root)
    result = run_audit(
        _cli_ledger_path(args, root, cfg),
        root,
        args.wave,
        label=args.label,
        dry_run=args.dry_run,
        cfg=cfg,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--ledger", default=None, help="path to the ledger (default: configured path)"
        )
        p.add_argument("--root", default=None, help="repo root (default: config-derived)")

    p_plan = sub.add_parser("plan", help="pure read-only classification plan")
    p_plan.add_argument("wave", help="iteration / wave id (unused by plan, kept for symmetry)")
    _add_common(p_plan)
    p_plan.set_defaults(func=_cmd_plan)

    p_run = sub.add_parser("run", help="apply the plan: auto-promote, file drafts, log")
    p_run.add_argument("wave", help="iteration / wave id")
    _add_common(p_run)
    p_run.add_argument("--label", default=None, help="label to apply to filed draft issues")
    p_run.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="(default) do not actually file gh issues; print what would be filed",
    )
    p_run.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="actually file gh issues for DECIDE-tier candidates",
    )
    p_run.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
