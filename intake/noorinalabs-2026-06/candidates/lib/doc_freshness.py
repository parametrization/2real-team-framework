#!/usr/bin/env python3
"""Advisory doc-freshness check (#768, part of #765).

When a PR (or a push) changes CODE in a *documented surface*, this gate checks
that the relevant docs (README / docs/ / ontology / charter) were ALSO touched
in the same change set — or that an explicit opt-out marker is present. It is the
machine companion to the project's "code is the final arbiter of truth for the
ontology" principle (ontology/conventions.md § Ontology: code is the arbiter of
truth): code drives the docs, so when code moves the docs are expected to move
with it.

ADVISORY, BY DESIGN — never blocks
==================================
This gate **always exits 0**. It prints a clear report and never fails a build
or blocks a commit/push. A heuristic "the docs probably need updating" signal has
an irreducible false-positive class — a pure refactor, a typo fix, a comment
tweak — so hard-gating it would punish legitimate doc-irrelevant changes (cf.
``feedback_artifact_gate_non_blocking`` and ``feedback_safety_direction_over_ux_friction``:
a hook that cannot *auto-fix cleanly* either hard-blocks with a precise diagnostic
or stays advisory; for an unavoidably-heuristic freshness nudge the right call is
advisory). The signal nudges the author and the reviewer; the human decides.

Because it exits 0 it is non-blocking on BOTH sides of the local⇄CI mirror: the
pre-commit hook never blocks a push, and the CI job is green-by-construction
(the job is additionally marked ``continue-on-error`` to make the advisory intent
explicit even if a future edit makes the script exit non-zero). It is still
registered as a real check kind in the sync-drift gate
(``pre_commit_ci_sync.py`` ``doc-freshness``) so local⇄CI parity (#684) holds:
the CI job and the pre-commit hook must both exist or the drift gate goes red.

How "changed surface" is computed
=================================
The change set is the three-dot diff against a base ref (``git diff --name-status
BASE...HEAD``) — i.e. what this branch changed relative to where it forked from
``main``, which is exactly a PR's diff. In CI the base is ``origin/<GITHUB_BASE_REF>``
(falling back to ``origin/main``); at pre-push it is the merge-base with
``origin/main``. Git failures degrade to an empty change set (advisory: report
nothing, exit 0) — the gate never crashes a commit because git was in an odd
state.

Surface rules (``SURFACE_RULES``)
=================================
Each rule pairs CODE path patterns with the DOC path patterns expected to move
with them. A rule fires when the change set touches a code path (with a status in
the rule's ``statuses``) but touches NONE of the rule's doc paths. The rules are
deliberately CONSERVATIVE and high-signal — a few mappings whose false-positive
rate is low — not an exhaustive code↔doc map (which would drown the signal). The
clearest case is ``statuses={"A"}``: a brand-new hook/lib module or skill almost
always needs a registry/index doc entry, whereas editing an existing module's
internals usually does not. Child repos vendor this file and extend
``SURFACE_RULES`` with their own documented surfaces.

Opt-out
=======
A change that legitimately needs no doc update declares it with an opt-out
TRAILER (case-insensitive) in any commit message of the range or in an
explicitly-passed opt-out text (the PR body, via ``--opt-out-text`` or
``DOC_FRESHNESS_OPT_OUT_TEXT``): a ``Docs-N/A:`` or ``Skip-Doc-Check:`` line,
optionally followed by a reason (e.g. ``Docs-N/A: pure refactor``). When present,
the gate reports the opt-out and emits no findings.

The trailing COLON is load-bearing: it is what distinguishes a deliberate opt-out
from prose that merely *names* the marker (a commit, doc, or this very module that
discusses ``Docs-N/A`` would otherwise self-trigger the opt-out). Matching the
colon form also keeps it distinct from the charter's ``TechDebt:`` / review
``Requestor:`` line shapes so it can never be mistaken for a review verdict by
Hook 4 (cf. feedback_hook4_regex_prose_false_match).

Exit code: always 0 (advisory). CLI usage errors print to stderr but still 0,
because this gate must never be the reason a push or build stops.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess  # noqa: S404 - git invocations are fixed, no shell, args are literals
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Opt-out trailers (matched case-insensitively). The trailing colon is REQUIRED
# so prose that merely names the marker does not self-trigger the opt-out (see
# the module docstring § Opt-out). Documented spellings: ``Docs-N/A:`` and
# ``Skip-Doc-Check:``, each optionally followed by a reason.
OPT_OUT_MARKERS: tuple[str, ...] = ("docs-n/a:", "skip-doc-check:")


@dataclass(frozen=True)
class Surface:
    """A documented code surface and the docs expected to move with it.

    ``code`` / ``docs`` are regex patterns matched against repo-relative POSIX
    paths. A rule FIRES (is reported) when the change set contains a path that
    matches any ``code`` pattern with a status in ``statuses`` AND contains NO
    path matching any ``docs`` pattern. ``hint`` is the human guidance printed.
    """

    name: str
    code: tuple[str, ...]
    docs: tuple[str, ...]
    hint: str
    statuses: frozenset[str] = field(default_factory=lambda: frozenset({"A", "M"}))


# Conservative, high-signal rules for noorinalabs-main. Child repos extend this.
#
# Rule 1 (new module): a brand-new org hook/lib module (status A, direct child
#   of .claude/hooks/ or .claude/lib/ — `tests/` and `__pycache__/` live in
#   subdirs so the `[^/]+` segment excludes them) is expected to be registered
#   in the Automation-hooks table in ontology/conventions.md and/or in
#   docs/TOOLCHAIN.md. Editing an existing module's internals is status M and
#   does NOT fire — that is the false-positive this status scoping removes.
# Rule 2 (new skill): a new skill (its SKILL.md is added) is expected to be
#   listed in CLAUDE.md / README.md / conventions.
# Rule 3 (CI / pre-commit topology): any change to a CI workflow or the
#   pre-commit config is expected to be reflected in the local⇄CI parity docs
#   (CLAUDE.md § Local Hooks, conventions § Pre-commit hooks, docs/TOOLCHAIN.md).
SURFACE_RULES: tuple[Surface, ...] = (
    Surface(
        name="new-org-hook-or-lib-module",
        code=(r"^\.claude/(hooks|lib)/[^/]+\.py$",),
        docs=(r"^ontology/conventions\.md$", r"^docs/TOOLCHAIN\.md$"),
        hint=(
            "New org hook/lib module — register it in ontology/conventions.md "
            "(§ Automation hooks) and/or docs/TOOLCHAIN.md."
        ),
        statuses=frozenset({"A"}),
    ),
    Surface(
        name="new-skill",
        code=(r"^\.claude/skills/[^/]+/SKILL\.md$",),
        docs=(r"^CLAUDE\.md$", r"^README\.md$", r"^ontology/conventions\.md$"),
        hint="New skill — list it in CLAUDE.md / README.md so it is discoverable.",
        statuses=frozenset({"A"}),
    ),
    Surface(
        name="ci-or-precommit-topology",
        code=(r"^\.github/workflows/.*\.ya?ml$", r"^\.pre-commit-config\.yaml$"),
        docs=(
            r"^CLAUDE\.md$",
            r"^ontology/conventions\.md$",
            r"^docs/TOOLCHAIN\.md$",
        ),
        hint=(
            "CI / pre-commit topology changed — reflect it in the local⇄CI "
            "parity docs (CLAUDE.md § Local Hooks, conventions § Pre-commit hooks)."
        ),
    ),
)


@dataclass(frozen=True)
class Finding:
    surface: str
    code_paths: tuple[str, ...]
    expected_docs: tuple[str, ...]
    hint: str


def _normalize_status(raw: str) -> str:
    """First letter of a git name-status code, renames/copies folded to M.

    ``git diff --name-status`` emits ``A``/``M``/``D`` and similarity-scored
    ``R100``/``C075`` for renames/copies. A rename keeps the file existing under
    a new path, so for surface purposes it is a modification (``M``), not a fresh
    addition — folding R/C to M avoids spuriously firing an ``A``-scoped rule on
    a path that already had its docs written.
    """
    if not raw:
        return ""
    first = raw[0].upper()
    return "M" if first in ("R", "C") else first


def has_opt_out(texts: list[str]) -> bool:
    """True if any opt-out marker appears (case-insensitive) in any text."""
    blob = "\n".join(texts).lower()
    return any(marker in blob for marker in OPT_OUT_MARKERS)


def evaluate(
    changed: list[tuple[str, str]],
    rules: tuple[Surface, ...] = SURFACE_RULES,
) -> list[Finding]:
    """Return findings: surfaces whose code changed without a corresponding doc.

    ``changed`` is a list of ``(status, path)`` pairs (status is a git
    name-status code; only its first letter, with R/C folded to M, is used).
    Paths are repo-relative POSIX strings.
    """
    findings: list[Finding] = []
    for rule in rules:
        code_pats = [re.compile(p) for p in rule.code]
        doc_pats = [re.compile(p) for p in rule.docs]

        touched_code = [
            path
            for status, path in changed
            if _normalize_status(status) in rule.statuses and any(p.match(path) for p in code_pats)
        ]
        if not touched_code:
            continue

        # A doc counts as "updated" on ANY change status (add or modify).
        doc_touched = any(any(p.match(path) for p in doc_pats) for _status, path in changed)
        if doc_touched:
            continue

        findings.append(
            Finding(
                surface=rule.name,
                code_paths=tuple(sorted(set(touched_code))),
                expected_docs=rule.docs,
                hint=rule.hint,
            )
        )
    return findings


# --------------------------------------------------------------------------- #
# Git layer — best-effort, never raises out of these helpers.
# --------------------------------------------------------------------------- #
def _run_git(args: list[str], cwd: Path) -> str | None:
    """Run ``git <args>`` in ``cwd``; return stdout, or None on any failure."""
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def resolve_base(repo_root: Path, explicit: str | None) -> str | None:
    """Resolve the diff base ref for the three-dot diff.

    Precedence: explicit ``--base`` > ``origin/$GITHUB_BASE_REF`` (CI pull_request)
    > ``origin/main``. Returns None if no usable base resolves (advisory: then
    there is nothing to compare against and the gate reports nothing).
    """
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    base_ref = os.environ.get("GITHUB_BASE_REF", "").strip()
    if base_ref:
        candidates.append(f"origin/{base_ref}")
    candidates.append("origin/main")

    for ref in candidates:
        if (
            _run_git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], repo_root)
            is not None
        ):
            return ref
    return None


def changed_files(repo_root: Path, base: str, head: str = "HEAD") -> list[tuple[str, str]]:
    """``git diff --name-status base...head`` parsed to ``(status, path)`` pairs.

    Three-dot (merge-base) diff = the branch's own changes relative to where it
    forked from base, i.e. a PR's diff. Returns [] on any git failure.
    """
    out = _run_git(["diff", "--name-status", f"{base}...{head}"], repo_root)
    if out is None:
        return []
    pairs: list[tuple[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        # Rename/copy lines are "R100\told\tnew" — the new path is the last field.
        path = parts[-1]
        pairs.append((status, path))
    return pairs


def collect_opt_out_texts(repo_root: Path, base: str, extra: str | None) -> list[str]:
    """Commit messages in base..HEAD plus any explicit opt-out text (PR body)."""
    texts: list[str] = []
    log = _run_git(["log", "--format=%B", f"{base}..HEAD"], repo_root)
    if log:
        texts.append(log)
    if extra:
        texts.append(extra)
    env_text = os.environ.get("DOC_FRESHNESS_OPT_OUT_TEXT", "")
    if env_text:
        texts.append(env_text)
    return texts


def render(findings: list[Finding]) -> str:
    """Human-readable advisory report."""
    if not findings:
        return "doc-freshness: no documented code surface changed without a matching doc update."
    lines = [
        "doc-freshness (advisory): code changed in a documented surface, but no "
        "matching doc was updated in this change set.",
        "",
    ]
    for f in findings:
        lines.append(f"  surface: {f.surface}")
        for p in f.code_paths:
            lines.append(f"    changed: {p}")
        lines.append(f"    expected one of: {', '.join(f.expected_docs)}")
        lines.append(f"    -> {f.hint}")
        lines.append("")
    lines.append(
        "If this change legitimately needs no doc update, add an opt-out trailer "
        "(a `Docs-N/A:` or `Skip-Doc-Check:` line) to a commit message or the PR body."
    )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Advisory doc-freshness check (#768).")
    parser.add_argument("repo_root", nargs="?", default=".", help="Repo root (default: cwd).")
    parser.add_argument(
        "--base", help="Diff base ref (default: origin/$GITHUB_BASE_REF or origin/main)."
    )
    parser.add_argument(
        "--opt-out-text",
        help="Extra text to scan for an opt-out marker (e.g. the PR body).",
    )
    parser.add_argument(
        "--changed",
        action="append",
        metavar="STATUS:PATH",
        help="Inject a changed entry instead of reading git (repeatable; for tests).",
    )
    args = parser.parse_args(argv[1:])
    repo_root = Path(args.repo_root).resolve()

    # Injected change set (tests) bypasses the git layer entirely.
    if args.changed:
        injected: list[tuple[str, str]] = []
        for item in args.changed:
            status, _, path = item.partition(":")
            if path:
                injected.append((status, path))
        opt_texts = [args.opt_out_text] if args.opt_out_text else []
        if has_opt_out(opt_texts):
            print("doc-freshness: opt-out marker present — skipping.")
            return 0
        print(render(evaluate(injected)))
        return 0

    base = resolve_base(repo_root, args.base)
    if base is None:
        print("doc-freshness: no diff base resolved (origin/main not fetched?) — skipping.")
        return 0

    if has_opt_out(collect_opt_out_texts(repo_root, base, args.opt_out_text)):
        print("doc-freshness: opt-out marker present — skipping.")
        return 0

    print(render(evaluate(changed_files(repo_root, base))))
    return 0


if __name__ == "__main__":
    # Advisory: even an unexpected error must not stop a push/build.
    try:
        sys.exit(main(sys.argv))
    except Exception as exc:  # noqa: BLE001
        print(f"doc-freshness: skipped (internal error: {exc})", file=sys.stderr)
        sys.exit(0)
