#!/usr/bin/env python3
"""Detect drift between a repo's pre-commit config and what its CI enforces.

Phase-3 end-state criterion #6 (noorinalabs-main#327) requires that local
pre-commit / pre-push hooks MIRROR the GitHub Actions checks, so a developer's
local commit fails fast instead of surfacing a lint/type/test error only after
a PR is opened. This module is the drift GATE: it parses both sides into a set
of canonical "check kinds" and reports any check CI enforces that the
pre-commit config does NOT run locally.

Structural YAML parse (#748 D3)
===============================
Both sides are parsed with ``yaml.safe_load`` and classified against the
STRUCTURAL values that actually carry a check invocation — never raw lines,
step ``name:`` text, or comments. Concretely:

- CI workflow: only ``jobs[].steps[].run`` (the whole multi-line block scalar,
  which ``safe_load`` folds for us — no hand-rolled ``run: |`` block emulation)
  and ``jobs[].steps[].uses`` (action refs).
- pre-commit config: only ``repos[].hooks[].id``, ``.entry`` and ``.name``.

This deletes the previous line-scanner's false-positive class deterministically:
a step *named* ``lint with ruff`` or a job *named* ``build-and-validate`` can no
longer masquerade as a real ``ruff``/``build`` check, because names are never
classified. A YAML comment cannot match either — the parser strips it.

Robustness: on a YAML parse error, or a document that parses to a bare scalar,
the classifier RAISES rather than returning an empty set. An empty set would be
a silent false-green (the gate would report "no drift" for a file it could not
read), which is the exact failure mode this gate exists to prevent. A genuinely
empty/whitespace file (``safe_load`` -> ``None``) contributes nothing, which is
correct — there is no check to mirror.

Drift direction that matters
============================
We gate on **CI-enforced-but-not-local** drift only. That is the harmful
direction: CI catches something the dev's machine doesn't, so the failure
appears at PR time (the friction #327 exists to remove). The reverse
(local runs something CI doesn't) is *stricter local* — not a regression, so
it is reported as informational, never a gate failure.

Canonical check kinds
=====================
Heterogeneous repos express the same check different ways (a `ruff` CI `run:`
step vs a `ruff` pre-commit `id:`). We normalize both sides to a small set of
kind tokens so they compare:

    ruff-lint, ruff-format, mypy, pytest, eslint, typescript, prettier,
    terraform-fmt, gitleaks, actionlint, astro-check, pip-audit, build,
    cspell, dockerfile-base-pin, fixture-realism, skill-graphql-pagination

Unknown tools are ignored (neither side gates on a kind we can't classify),
which keeps the gate conservative — it never fails on something it doesn't
understand. Closing a blind spot here means ADDING the kind to
`_KIND_PATTERNS` (cf. `cspell`, #684) so a CI job that runs it starts
demanding a pre-commit mirror — an un-classified CI check is silently
un-mirrored, which is the exact divergence this gate exists to prevent.

Exit codes (CLI):
    0 — no harmful drift (every CI-enforced kind is mirrored in pre-commit)
    1 — harmful drift (a CI-enforced kind is missing from pre-commit)
    2 — usage / file-not-found / unparseable-config error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterator

import yaml

# Each kind maps to the keyword patterns that identify it in a STRUCTURAL value
# (a pre-commit hook id/entry/name, or a CI step's run/uses string). Patterns
# are substrings matched case-insensitively against that single value — they are
# NOT raw-line fragments. So `ruff-lint` keys off the hook id VALUE `ruff` (or a
# `ruff check` run), not the literal line `id: ruff`; `terraform-fmt` keys off
# the id VALUE `terraform_fmt`/`terraform-fmt` (or a `terraform fmt` run), not
# `id: terraform`.
#
# `ruff-lint` is `("ruff",)` on purpose: structurally each value is ONE tool, so
# the bare-`ruff` id (which carries no `-lint`/`check` suffix) must still map to
# lint. A `ruff format` / `ruff-format` value would also contain `ruff`, so
# `_classify_value` detects ruff-format FIRST and suppresses ruff-lint on that
# value — preserving the format-before-lint ordering correctness without the old
# span-removal hack.
#
# `build` matches only real build-QUALITY GATES — a step whose `run:`/`uses:`
# fails the PR if the project does not build/compile (`build-and-validate`,
# `build-and-test`, `npm run build`). It deliberately does NOT match bare
# `docker build` / `docker buildx`: those are runtime image-MOVING (retag,
# promote, publish to a registry, cold-rebuild dry-runs, digest resolution),
# which is the deploy/publish job itself, not a quality gate a local pre-commit
# hook could mirror. A bare `docker build` substring also matches `docker
# buildx`, so a repo that uses buildx at runtime (deploy, the image-publishing
# CI in isnad-graph / ingest-platform) would otherwise see a permanent
# un-mirrorable `build` kind and the drift gate could never exit 0 (#576). If a
# repo ever adds a genuine docker-build-as-quality-gate, express it as a
# `run:`/`uses:` matching `build-and-validate` / `build-and-test` (or add an
# explicit pattern) so it is mirror-tracked. Tightening lifted verbatim from the
# deploy-rollout form (deploy#391, A.Idrissi) and canonicalized here so all
# vendored child copies converge.
_KIND_PATTERNS: dict[str, tuple[str, ...]] = {
    "ruff-format": ("ruff-format", "ruff format"),
    "ruff-lint": ("ruff",),
    "mypy": ("mypy",),
    "pytest": ("pytest",),
    "eslint": ("eslint",),
    "typescript": ("tsc", "typecheck", "type-check", "astro check"),
    "prettier": ("prettier",),
    "terraform-fmt": ("terraform fmt", "terraform_fmt", "terraform-fmt"),
    "gitleaks": ("gitleaks",),
    "actionlint": ("actionlint",),
    "pip-audit": ("pip-audit", "pip audit"),
    "build": ("build-and-validate", "build-and-test", "npm run build"),
    # `cspell` closes the spell-check blind spot (#684): the CI Spellcheck job
    # runs the `streetsidesoftware/cspell-action` (or a `cspell` CLI), but until
    # this kind existed an un-classified spell gate produced ZERO drift signal,
    # so a repo could enforce cspell in CI with no pre-commit mirror — new
    # domain vocabulary then failed only after push. Patterns cover the action
    # ref, the bundled-CLI step name, and the generic job/step word.
    "cspell": ("cspell", "spellcheck", "streetsidesoftware/cspell"),
    # `memory-budget` is the project-memory corpus size/count gate
    # (`.claude/lib/memory_budget.py`, #733). Classifying it makes the drift gate
    # actively DEMAND the local⇄CI mirror (#684): a `memory_budget.py` CI run
    # with no pre-commit hook is harmful drift, not a silently-ignored unknown.
    # Patterns cover the hook `id`/`name` token (`memory-budget`) and the CI
    # `run` invocation token (`memory_budget`).
    "memory-budget": ("memory-budget", "memory_budget"),
    # `headcount-budget` is the persona-roster headcount gate
    # (`.claude/lib/headcount_budget.py`, #841 — persona Option B / criterion #3).
    # Same contract as `memory-budget` above: a `headcount_budget.py` CI run with
    # no pre-commit hook is harmful drift (#684), not a silently-ignored unknown,
    # so classifying it makes the drift gate actively DEMAND the local⇄CI mirror.
    # Patterns cover the hook `id`/`name` token (`headcount-budget`) and the CI
    # `run` invocation token (`headcount_budget`).
    "headcount-budget": ("headcount-budget", "headcount_budget"),
    # `doc-freshness` is the advisory PR-time doc-freshness gate
    # (`.claude/lib/doc_freshness.py`, #768). It is ADVISORY (always exits 0), but
    # it is still a real CI check, so it must be mirrored in pre-commit for
    # local⇄CI parity (#684) — classifying it makes the drift gate DEMAND that
    # mirror rather than silently ignoring an un-classified kind. Patterns cover
    # the hook `id`/`name` token (`doc-freshness`) and the CI `run` invocation
    # token (`doc_freshness`).
    "doc-freshness": ("doc-freshness", "doc_freshness"),
    # `office-drift` is the generated-Office-binary drift gate (#781): the CI
    # `Office docs drift gate` job regenerates the committed .docx/.xlsx/.pptx
    # from their markdown sources via `scripts/gen-office.sh` and fails on a byte
    # diff. Classifying it makes the drift gate DEMAND the pre-commit mirror
    # (#684) — an un-mirrored office gate would let a stale binary fail only at
    # PR time. Patterns cover the hook `id`/`name` token (`office-drift`) and the
    # generator both sides invoke (`gen-office`).
    "office-drift": ("office-drift", "gen-office"),
    # `mermaid` is the mermaid render gate (#787): the CI `Mermaid render gate`
    # job installs mermaid-cli and runs `scripts/check-mermaid.py` to render every
    # fenced mermaid block, failing on a non-rendering diagram. Classifying it
    # makes the drift gate DEMAND the pre-commit mirror (#684). Patterns cover the
    # tool/hook token (`mermaid`) and the validator both sides invoke
    # (`check-mermaid`).
    "mermaid": ("mermaid", "check-mermaid"),
    # `dockerfile-base-pin` and `fixture-realism` are the two charter-prose→code
    # gates built in #735 (worklist #4 + #1 of the #734 inventory). Each is a
    # `.claude/lib/check_*.py` invoked identically by a CI job and a pre-commit
    # hook; classifying them here is what makes the sync-drift gate DEMAND the
    # mirror (the #684 contract: an un-classified CI check is a silent blind
    # spot). Patterns match the script basename (present on both sides' invoke
    # line) and the hook id / job name.
    "dockerfile-base-pin": ("check_dockerfile_base_pin", "dockerfile-base-pin"),
    "fixture-realism": ("check_fixture_realism", "fixture-realism"),
    # `skill-graphql-pagination` is the skill-markdown GraphQL over-cap lint
    # (`.claude/lib/lint_skill_graphql_pagination.py`, #888/#892 → wired by #893):
    # it flags any `first: > 100` inside a `gh api graphql` block in
    # `.claude/skills/**/*.md` (the over-cap footgun that made `/board-audit` read
    # every issue as an orphan). Same contract as the two charter-prose→code gates
    # above — a CI run of the lint with no pre-commit hook is harmful drift (#684),
    # not a silently-ignored unknown, so classifying it makes the drift gate
    # actively DEMAND the local⇄CI mirror. Patterns match the script basename
    # (present on both sides' invoke line) and the hook id / job name.
    "skill-graphql-pagination": (
        "lint_skill_graphql_pagination",
        "skill-graphql-pagination",
    ),
}


def _classify_value(value: str) -> set[str]:
    """Return the canonical kinds a single structural VALUE implies.

    A value is one tool now (an `id`, an `entry`, a `uses` ref, or one line of a
    `run` script), so ruff disambiguation is a precise format-first check rather
    than the old line-level span removal: a `ruff format` / `ruff-format` value
    is ruff-format and is NOT also counted as ruff-lint.
    """
    low = value.lower()
    kinds: set[str] = set()
    is_ruff_format = any(p in low for p in _KIND_PATTERNS["ruff-format"])
    if is_ruff_format:
        kinds.add("ruff-format")
    for kind, patterns in _KIND_PATTERNS.items():
        if kind == "ruff-format":
            continue
        if kind == "ruff-lint" and is_ruff_format:
            # A ruff-format value (`ruff-format` id / `ruff format` run) must
            # not also register ruff-lint via the bare `ruff` pattern.
            continue
        if any(p in low for p in patterns):
            kinds.add(kind)
    return kinds


def _classify_run(run: str) -> set[str]:
    """Classify a (possibly multi-line) `run:` block scalar.

    `safe_load` already folded `run: |` / `run: >` into one string, so we just
    walk its lines, skipping blank and shell-comment (`#…`) lines so a commented
    invocation is not mistaken for a real one.
    """
    kinds: set[str] = set()
    for raw in run.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        kinds |= _classify_value(stripped)
    return kinds


def _safe_load_or_raise(text: str, what: str) -> Any:
    """Parse YAML, refusing to degrade a parse failure into a false-green.

    Returns the parsed document (``dict``/``list``), or ``None`` for a genuinely
    empty document. Raises ``ValueError`` on a YAML syntax error or a document
    that parses to a bare scalar — either would otherwise yield an empty kind-set
    and silently hide drift.
    """
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"{what} is not valid YAML: {exc}") from exc
    if doc is not None and not isinstance(doc, (dict, list)):
        raise ValueError(
            f"{what} did not parse to a YAML mapping/sequence "
            f"(got {type(doc).__name__}); refusing to treat it as 'no checks'."
        )
    return doc


def _iter_ci_steps(doc: Any) -> Iterator[dict[str, Any]]:
    """Yield the step mappings of a parsed CI workflow.

    Handles the full workflow shape (``jobs[].steps[]``) and the bare
    step-list / single-step shapes used by focused unit tests. Only mappings are
    yielded; ``run``/``uses`` are read off them by the caller.
    """
    if isinstance(doc, dict):
        jobs = doc.get("jobs")
        if isinstance(jobs, dict):
            for job in jobs.values():
                if isinstance(job, dict):
                    steps = job.get("steps")
                    if isinstance(steps, list):
                        for step in steps:
                            if isinstance(step, dict):
                                yield step
            return
        steps = doc.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    yield step
            return
        if "run" in doc or "uses" in doc:
            yield doc
    elif isinstance(doc, list):
        for step in doc:
            if isinstance(step, dict):
                yield step


def kinds_from_ci(workflow_text: str) -> set[str]:
    """Canonical check-kinds a single CI workflow enforces.

    Classifies ONLY each step's `run:` shell (whole block scalar) and `uses:`
    action ref. Step/job `name:` and comments are never classified — that
    exclusion is the #748 false-positive fix.
    """
    doc = _safe_load_or_raise(workflow_text, "CI workflow")
    if doc is None:
        return set()
    kinds: set[str] = set()
    for step in _iter_ci_steps(doc):
        run = step.get("run")
        if isinstance(run, str):
            kinds |= _classify_run(run)
        uses = step.get("uses")
        if isinstance(uses, str):
            kinds |= _classify_value(uses)
    return kinds


def kinds_from_precommit(config_text: str) -> set[str]:
    """Canonical check-kinds a `.pre-commit-config.yaml` runs locally.

    Classifies ONLY each hook's `id`, `entry` and `name` values. Comments and
    the surrounding YAML structure are never classified.
    """
    doc = _safe_load_or_raise(config_text, "pre-commit config")
    if not isinstance(doc, dict):
        return set()
    kinds: set[str] = set()
    repos = doc.get("repos")
    if not isinstance(repos, list):
        return kinds
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        hooks = repo.get("hooks")
        if not isinstance(hooks, list):
            continue
        for hook in hooks:
            if not isinstance(hook, dict):
                continue
            for key in ("id", "entry", "name"):
                value = hook.get(key)
                if isinstance(value, str):
                    kinds |= _classify_value(value)
    return kinds


def compute_drift(precommit_kinds: set[str], ci_kinds: set[str]) -> tuple[set[str], set[str]]:
    """Return (harmful_drift, stricter_local).

    harmful_drift  = CI enforces it, pre-commit does not (gate fails on these).
    stricter_local = pre-commit runs it, CI does not (informational only).
    """
    harmful = ci_kinds - precommit_kinds
    stricter = precommit_kinds - ci_kinds
    return harmful, stricter


def check_repo(precommit_path: Path, ci_paths: list[Path]) -> tuple[set[str], set[str]]:
    """Read the files and compute drift. Missing files contribute nothing.

    Each CI workflow is parsed independently and the kinds unioned — workflow
    files are separate YAML documents and must not be concatenated into one
    parse (duplicate top-level keys would raise).
    """
    pc_text = precommit_path.read_text(encoding="utf-8") if precommit_path.is_file() else ""
    pc_kinds = kinds_from_precommit(pc_text)
    ci_kinds: set[str] = set()
    for path in ci_paths:
        if path.is_file():
            ci_kinds |= kinds_from_ci(path.read_text(encoding="utf-8"))
    return compute_drift(pc_kinds, ci_kinds)


def _default_ci_paths(repo_root: Path) -> list[Path]:
    wf_dir = repo_root / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    return sorted(p for p in wf_dir.glob("*.y*ml"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repo_root",
        nargs="?",
        default=".",
        help="Repo root to check (default: cwd).",
    )
    parser.add_argument(
        "--precommit",
        help="Path to .pre-commit-config.yaml (default: <repo_root>/.pre-commit-config.yaml).",
    )
    parser.add_argument(
        "--ci",
        action="append",
        help=(
            "Path to a CI workflow file (repeatable). "
            "Default: all <repo_root>/.github/workflows/*.yml."
        ),
    )
    args = parser.parse_args(argv[1:])

    repo_root = Path(args.repo_root).resolve()
    precommit_path = (
        Path(args.precommit) if args.precommit else repo_root / ".pre-commit-config.yaml"
    )
    ci_paths = [Path(p) for p in args.ci] if args.ci else _default_ci_paths(repo_root)

    if not precommit_path.is_file():
        print(
            f"ERROR: no pre-commit config at {precommit_path} — "
            "every repo must have one (criterion #327).",
            file=sys.stderr,
        )
        return 2

    try:
        harmful, stricter = check_repo(precommit_path, ci_paths)
    except ValueError as exc:
        # Unparseable config: fail loudly (exit 2), never silently green.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if stricter:
        print(f"INFO: pre-commit runs (CI does not): {sorted(stricter)} — stricter local, OK.")

    if harmful:
        print("DRIFT: CI enforces these checks but pre-commit does NOT run them locally:")
        for k in sorted(harmful):
            print(f"  - {k}")
        print(
            "\nAdd the missing check(s) to .pre-commit-config.yaml so local commits "
            "fail fast (criterion #327). Pin the same tool version CI uses."
        )
        return 1

    print("OK: pre-commit config mirrors all CI-enforced checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
