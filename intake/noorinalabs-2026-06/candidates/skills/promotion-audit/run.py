#!/usr/bin/env python3
"""Canonical CLI driver for the /promotion-audit skill.

This is the single, deterministic entrypoint that wires the `helpers.py`
pure functions + thresholds together exactly once. The SKILL.md invokes
this driver instead of describing the classify_* call sequence in prose.

Background (main#690)
=====================
The skill historically shipped `helpers.py` but no driver. The orchestrator
hand-rolled the classify_* call sequence inline each retro. At the P5W4
retro that hand-rolling mis-fired: the section→skill / skill→hook tiers
derived the invocation signal by calling
`count_skill_invocations(section.promoted_to, repo_root)` over an EMPTY
`promoted_to` slug. `git log --grep=/` matches (nearly) every commit, so
each not-yet-promoted section reported ~600 invocations and crossed the
threshold — producing 24 spurious AUTO decisions that would have opened 24
bogus charter/skill PRs. The more-carefully-called memory→charter tier
returned the correct 0 AUTO.

The fix is determinism-over-hand-rolling (same principle as main#688's
`wave_status.py`): wire the signal derivation in ONE place, with the
correct slug resolution, so the same repo state always yields the same
decisions.

Signal derivation, fixed in this driver
=======================================
- memory → charter: `count_retro_citations(memory, feedback_log)`.
- charter → skill: the candidate skill slug is `section.promoted_to`
  (with the `skills/` prefix stripped) when the section is already
  promoted, else `_slugify(section.heading)` — the *prospective* skill
  name. A not-yet-existent skill never appears in commit messages, so its
  invocation count is naturally ~0. The empty-slug footgun is also closed
  at the root in `helpers.count_skill_invocations` (blank slug → 0).
- skill → hook: `count_skill_invocations(skill.name, repo_root)`
  (always DECIDE per D6, never AUTO).

Usage
=====
    python3 .claude/skills/promotion-audit/run.py [wave] [--json] [--date YYYY-MM-DD]
    python3 -m run [wave] ...        # when CWD is the skill dir

With no `wave` argument the driver reads `current_wave` from
`cross-repo-status.json` and emits the phase-agnostic canonical form
`wave-{X}` (#810). Design B (#804) made the wave id global/monotonic, so the
cross-phase collision that #442 guarded against (which forbade bare
`wave-{M}`) no longer exists; #810 retires that prohibition. Legacy
`p{N}-wave-{M}` input is accepted and normalized to `wave-{X}`.

The driver performs ONLY the deterministic classification + rendering.
Artifact emission (PR/issue creation, project-board adds) stays in the
SKILL.md prose because it makes nondeterministic `gh` calls — but it now
drives off this driver's `--json` output rather than re-deriving signals.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
from pathlib import Path

# Make `helpers` importable whether run as a script or via `python -m`.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import helpers as h  # noqa: E402

# Walk up from .claude/skills/promotion-audit/run.py to the repo root.
_REPO_ROOT = _HERE.parent.parent.parent
# Project memory now lives IN-REPO (version-controlled, transferable) at
# .claude/memory/, not the user-space ~/.claude/projects/<cwd>/memory/ path it
# used pre-relocation (#732 / CLAUDE.md § Project Memory). Derive from repo root.
_DEFAULT_MEMORY_DIR = str(_REPO_ROOT / ".claude" / "memory")

DEFAULT_THRESHOLD = 5


@dataclasses.dataclass(frozen=True)
class AuditPaths:
    """Resolved input locations for one audit run."""

    repo_root: str
    memory_dir: str
    charter_parent: str  # dir CONTAINING charter/ (e.g. .claude/team), NOT charter/ itself
    skills_dir: str
    feedback_log: str
    status_path: str


def resolve_paths(
    repo_root: str | os.PathLike[str] | None = None,
    *,
    memory_dir: str | None = None,
) -> AuditPaths:
    """Resolve every input path from the repo root.

    `memory_dir` defaults to the in-repo `.claude/memory/` corpus
    (version-controlled since the #732 relocation). It can be overridden
    for tests against a fixture tree.
    """
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    team = root / ".claude" / "team"
    return AuditPaths(
        repo_root=str(root),
        memory_dir=memory_dir if memory_dir is not None else _DEFAULT_MEMORY_DIR,
        charter_parent=str(team),
        skills_dir=str(root / ".claude" / "skills"),
        feedback_log=str(team / "feedback_log.md"),
        status_path=str(root / "cross-repo-status.json"),
    )


_WAVE_M_RE = re.compile(r"(?:wave-)?(?P<m>\d+)\s*$")
_PHASE_PREFIXED_RE = re.compile(r"^p(?P<n>\d+)-wave-(?P<m>\d+)$")


def resolve_wave_name(arg: str | None, status_path: str) -> str:
    """Return the canonical phase-agnostic wave name `wave-{X}` (#810).

    - Legacy `p{N}-wave-{M}` args are normalized to `wave-{M}`.
    - Bare `wave-{M}` or `{M}` args yield `wave-{M}`.
    - No arg reads `current_wave` from `cross-repo-status.json`.

    Design B (#804) made the wave id global/monotonic, so the cross-phase
    collision that #442 guarded against (which forbade bare `wave-{M}`) no
    longer exists. #810 retires that prohibition: the canonical wave name —
    used for artifact labels, audit-log filenames, and feedback-log headers —
    is now the phase-agnostic `wave-{X}`. (`current_phase` is no longer needed
    to build the name; it remains in the status file as a derived display.)
    """
    data: dict = {}
    if os.path.isfile(status_path):
        data = json.loads(Path(status_path).read_text())

    if arg:
        arg = arg.strip()
        # `_WAVE_M_RE` (`(?:wave-)?(\d+)$`) extracts the wave id from the legacy
        # `p{N}-wave-{M}`, the new `wave-{M}`, and the bare `{M}` forms alike.
        m = _WAVE_M_RE.search(arg)
        if not m:
            raise ValueError(f"Cannot parse wave from {arg!r} (expected p5-wave-5 or wave-5 or 5)")
        wave_m = m.group("m")
    else:
        current_wave = str(data.get("current_wave", "")).strip()
        m = _WAVE_M_RE.search(current_wave)
        if not m:
            raise ValueError(f"cross-repo-status.json current_wave={current_wave!r} is unparseable")
        wave_m = m.group("m")

    return f"wave-{wave_m}"


def resolve_audit_date(wave_name: str, status_path: str) -> str:
    """Pin the audit date to the wave boundary (UTC, `YYYY-MM-DD`).

    Determinism requires we never use `datetime.now()` — the date is read
    from the wave's boundary timestamp in `cross-repo-status.json`. Tries,
    in order: `wave_{M}_kicked_off_at`, `wave_{M}_started_at`,
    `wave_{M}_scope_reconciled_at`. Returns "unknown-date" only if the
    status file or every boundary key is absent (callers may override with
    `--date`).
    """
    m = _PHASE_PREFIXED_RE.match(wave_name)
    wave_m = m.group("m") if m else _WAVE_M_RE.search(wave_name).group("m")  # type: ignore[union-attr]
    if not os.path.isfile(status_path):
        return "unknown-date"
    data = json.loads(Path(status_path).read_text())
    for key in (
        f"wave_{wave_m}_kicked_off_at",
        f"wave_{wave_m}_started_at",
        f"wave_{wave_m}_scope_reconciled_at",
    ):
        val = data.get(key)
        if val:
            return str(val)[:10]
    return "unknown-date"


def _section_signal_slug(section: h.CharterSection) -> str:
    """The skill slug whose invocations gate this section's charter→skill move.

    For an already-promoted section, that's the existing skill slug recorded
    in the `promoted-to: skills/{slug}` back-reference. For a not-yet-promoted
    section, it's the *prospective* skill name derived from the heading —
    which, because the skill does not exist yet, naturally yields ~0
    invocations rather than the all-commits count an empty slug produced
    in the P5W4 mis-fire (main#690).
    """
    if section.promoted_to:
        return section.promoted_to.split("/")[-1]
    return h._slugify(section.heading)


@dataclasses.dataclass(frozen=True)
class AuditResult:
    wave_name: str
    audit_date: str
    threshold: int
    decisions: list[h.Decision]

    def counts(self) -> dict[str, int]:
        out = {"AUTO": 0, "DECIDE": 0, "KEPT": 0, "SUPERSEDED": 0, "ALREADY-PROMOTED": 0}
        for d in self.decisions:
            out[d.kind] = out.get(d.kind, 0) + 1
        return out

    def table(self) -> str:
        return h.render_audit_table(self.decisions, self.wave_name, self.audit_date)

    def summary_line(self) -> str:
        c = self.counts()
        supers = c["SUPERSEDED"] + c["ALREADY-PROMOTED"]
        return (
            f"Promotion audit {self.wave_name} complete: "
            f"{c['AUTO']} AUTO · {c['DECIDE']} DECIDE · {c['KEPT']} KEPT · {supers} SUPERSEDED"
        )


def run_audit(
    paths: AuditPaths,
    *,
    wave_name: str,
    audit_date: str,
    threshold: int = DEFAULT_THRESHOLD,
) -> AuditResult:
    """Drive the full deterministic classification pipeline exactly once.

    Re-running on unchanged repo state yields byte-identical decisions —
    every input list is read in sorted order by the helpers, and signals
    are derived from git history + on-disk files only (no clock, no
    transcripts, no network).
    """
    memories = h.read_all_memories(paths.memory_dir)
    sections = h.read_all_charter_sections(paths.charter_parent)
    skills = h.read_all_skills(paths.skills_dir)
    already = h.find_already_promoted_in_charter(paths.charter_parent)

    decisions: list[h.Decision] = []

    # memory → charter
    for mem in memories:
        cites = h.count_retro_citations(mem, paths.feedback_log)
        decisions.append(h.classify_memory(mem, {"retro_citations": cites}, already))

    # charter → skill
    for sec in sections:
        slug = _section_signal_slug(sec)
        invocations = h.count_skill_invocations(slug, paths.repo_root)
        decisions.append(
            h.classify_section(sec, {"skill_invocations": invocations, "threshold": threshold})
        )

    # skill → hook (always DECIDE)
    for sk in skills:
        invocations = h.count_skill_invocations(sk.name, paths.repo_root)
        decisions.append(
            h.classify_skill(
                sk, {"skill_invocations": invocations, "threshold": threshold}, already
            )
        )

    return AuditResult(
        wave_name=wave_name,
        audit_date=audit_date,
        threshold=threshold,
        decisions=decisions,
    )


def _decisions_as_json(result: AuditResult) -> str:
    payload = {
        "wave_name": result.wave_name,
        "audit_date": result.audit_date,
        "threshold": result.threshold,
        "counts": result.counts(),
        "decisions": [dataclasses.asdict(d) for d in result.decisions],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="promotion-audit",
        description="Canonical deterministic driver for the /promotion-audit skill.",
    )
    p.add_argument(
        "wave",
        nargs="?",
        default=None,
        help="wave name (p5-wave-5, wave-5, or 5); default reads cross-repo-status.json",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable decisions (for artifact-emission drivers)",
    )
    p.add_argument(
        "--date",
        default=None,
        help="override the audit date (YYYY-MM-DD); default reads the wave boundary",
    )
    p.add_argument(
        "--repo-root",
        default=None,
        help="repo root (default: inferred from this file's location)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    paths = resolve_paths(args.repo_root)
    wave_name = resolve_wave_name(args.wave, paths.status_path)
    audit_date = args.date or resolve_audit_date(wave_name, paths.status_path)
    result = run_audit(paths, wave_name=wave_name, audit_date=audit_date)

    if args.json:
        print(_decisions_as_json(result))
    else:
        print(result.table())
        print()
        print(result.summary_line())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
