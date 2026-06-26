# Generic Lib Prompt: Pre-commit ⇄ CI Sync-Drift Gate

## Purpose

Detect **drift** between a repo's local pre-commit/pre-push config and what its
CI actually enforces, so a developer's local commit fails fast instead of
surfacing a lint/type/test error only *after* a PR is opened.

The contract: every check CI enforces MUST be **mirrored** in the local
`.pre-commit-config.yaml`. This module is the machine-enforcement of that
contract — it parses both sides into a set of canonical "check kinds" and fails
the build when CI enforces a kind the local config does not run.

## Reusable Pattern

**Structural YAML parse, never line-scanning.** Parse both files with a real
YAML loader and classify only the STRUCTURAL values that carry a check
invocation — never raw lines, step `name:` text, or comments. Concretely:

- **CI workflow:** only `jobs[].steps[].run` (the whole block scalar — the YAML
  loader folds multi-line `run: |` for you) and `jobs[].steps[].uses`.
- **pre-commit config:** only `repos[].hooks[].id`, `.entry`, and `.name`.

This deletes an entire false-positive class deterministically: a step *named*
"lint with ruff" or a job *named* "build-and-validate" can no longer masquerade
as a real check, because names are never classified, and a YAML comment can
never match because the parser strips it.

**Fail loud on unparseable input, never false-green.** On a YAML syntax error,
or a document that parses to a bare scalar, RAISE rather than returning an empty
kind-set. An empty set would report "no drift" for a file it could not read —
the exact failure mode the gate exists to prevent. A genuinely empty file (loads
to `None`) correctly contributes nothing.

**Gate on one drift direction only.** Fail only on **CI-enforced-but-not-local**
drift — the harmful direction, where CI catches something the dev's machine
misses, so the failure appears at PR time. The reverse (local stricter than CI)
is reported as informational, never a gate failure.

**Unknown tools are ignored — and that is the blind spot to close deliberately.**
Normalize both sides to a small set of canonical kind tokens. A tool you cannot
classify is silently un-mirrored: an un-classified CI check produces ZERO drift
signal, so a repo could enforce it in CI with no local mirror. Closing a blind
spot means ADDING the kind to the pattern table — that is the maintenance action
that keeps the gate honest.

## Algorithm

1. Parse the pre-commit config → set of kinds from every hook `id`/`entry`/`name`.
2. Parse each CI workflow independently (separate YAML docs — never concatenate)
   → union of kinds from every step `run` (line-walked, skipping blank/`#` lines)
   and `uses`.
3. `harmful = ci_kinds - precommit_kinds`; `stricter = precommit_kinds - ci_kinds`.
4. Exit `1` if `harmful` is non-empty (drift), `0` otherwise; `2` on
   usage/parse error.

**Disambiguation example (ruff):** a `ruff format` value and a `ruff` value both
contain the substring `ruff`. Detect the more-specific `ruff-format` FIRST and
suppress the generic `ruff-lint` on that same value, so format-vs-lint stays
correct without span-removal hacks.

**Build-kind caution:** match only genuine build-QUALITY gates
(`build-and-validate`, `npm run build`). Do NOT match bare `docker build` /
`docker buildx` — those are runtime image-moving (publish/promote/retag), not a
quality gate a local hook could mirror; treating them as a `build` kind makes
the gate permanently un-satisfiable on any repo that publishes images.

## Code Template (stdlib + a YAML loader)

```python
#!/usr/bin/env python3
"""Detect drift between a repo's pre-commit config and what its CI enforces.

Exit codes:
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

# Each canonical kind -> substrings that identify it in a STRUCTURAL value
# (a hook id/entry/name, or a CI step's run/uses string). Matched
# case-insensitively against a single value, NOT against raw lines.
# Closing a blind spot = ADD a kind here.
_KIND_PATTERNS: dict[str, tuple[str, ...]] = {
    "ruff-format": ("ruff-format", "ruff format"),
    "ruff-lint": ("ruff",),
    "mypy": ("mypy",),
    "pytest": ("pytest",),
    "eslint": ("eslint",),
    "typescript": ("tsc", "typecheck", "type-check"),
    "prettier": ("prettier",),
    "gitleaks": ("gitleaks",),
    "actionlint": ("actionlint",),
    "cspell": ("cspell", "spellcheck"),
    # build-QUALITY gates only — never bare `docker build`/`buildx`.
    "build": ("build-and-validate", "build-and-test", "npm run build"),
}


def _classify_value(value: str) -> set[str]:
    low = value.lower()
    kinds: set[str] = set()
    is_fmt = any(p in low for p in _KIND_PATTERNS["ruff-format"])
    if is_fmt:
        kinds.add("ruff-format")
    for kind, patterns in _KIND_PATTERNS.items():
        if kind == "ruff-format":
            continue
        if kind == "ruff-lint" and is_fmt:  # format value must not also be lint
            continue
        if any(p in low for p in patterns):
            kinds.add(kind)
    return kinds


def _classify_run(run: str) -> set[str]:
    kinds: set[str] = set()
    for raw in run.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        kinds |= _classify_value(s)
    return kinds


def _safe_load_or_raise(text: str, what: str) -> Any:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"{what} is not valid YAML: {exc}") from exc
    if doc is not None and not isinstance(doc, (dict, list)):
        raise ValueError(f"{what} parsed to a bare scalar; refusing to treat as 'no checks'.")
    return doc


def _iter_ci_steps(doc: Any) -> Iterator[dict[str, Any]]:
    if isinstance(doc, dict):
        jobs = doc.get("jobs")
        if isinstance(jobs, dict):
            for job in jobs.values():
                if isinstance(job, dict) and isinstance(job.get("steps"), list):
                    yield from (s for s in job["steps"] if isinstance(s, dict))
            return
        if isinstance(doc.get("steps"), list):
            yield from (s for s in doc["steps"] if isinstance(s, dict))
            return
        if "run" in doc or "uses" in doc:
            yield doc
    elif isinstance(doc, list):
        yield from (s for s in doc if isinstance(s, dict))


def kinds_from_ci(text: str) -> set[str]:
    doc = _safe_load_or_raise(text, "CI workflow")
    if doc is None:
        return set()
    kinds: set[str] = set()
    for step in _iter_ci_steps(doc):
        if isinstance(step.get("run"), str):
            kinds |= _classify_run(step["run"])
        if isinstance(step.get("uses"), str):
            kinds |= _classify_value(step["uses"])
    return kinds


def kinds_from_precommit(text: str) -> set[str]:
    doc = _safe_load_or_raise(text, "pre-commit config")
    if not isinstance(doc, dict) or not isinstance(doc.get("repos"), list):
        return set()
    kinds: set[str] = set()
    for repo in doc["repos"]:
        if not isinstance(repo, dict) or not isinstance(repo.get("hooks"), list):
            continue
        for hook in repo["hooks"]:
            if not isinstance(hook, dict):
                continue
            for key in ("id", "entry", "name"):
                if isinstance(hook.get(key), str):
                    kinds |= _classify_value(hook[key])
    return kinds


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo_root", nargs="?", default=".")
    ap.add_argument("--precommit")
    ap.add_argument("--ci", action="append")
    args = ap.parse_args(argv[1:])

    root = Path(args.repo_root).resolve()
    pc = Path(args.precommit) if args.precommit else root / ".pre-commit-config.yaml"
    if args.ci:
        ci_paths = [Path(p) for p in args.ci]
    else:
        wf = root / ".github" / "workflows"
        ci_paths = sorted(wf.glob("*.y*ml")) if wf.is_dir() else []

    if not pc.is_file():
        print(f"ERROR: no pre-commit config at {pc}", file=sys.stderr)
        return 2
    try:
        pc_kinds = kinds_from_precommit(pc.read_text("utf-8"))
        ci_kinds: set[str] = set()
        for p in ci_paths:
            if p.is_file():
                ci_kinds |= kinds_from_ci(p.read_text("utf-8"))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    harmful = ci_kinds - pc_kinds
    stricter = pc_kinds - ci_kinds
    if stricter:
        print(f"INFO: pre-commit runs (CI does not): {sorted(stricter)} — OK.")
    if harmful:
        print("DRIFT: CI enforces these but pre-commit does NOT run them locally:")
        for k in sorted(harmful):
            print(f"  - {k}")
        return 1
    print("OK: pre-commit config mirrors all CI-enforced checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

## Adaptation Notes

- **`_KIND_PATTERNS` is the project-specific surface.** Seed it with the tools
  your CI actually runs; every new CI check needs a kind here or it is silently
  un-mirrored. Match patterns against the structural *value*, not the raw line.
- **Each CI workflow is a separate YAML document** — parse independently and
  union. Concatenating them risks duplicate-top-level-key parse errors.
- **Keep the asymmetry:** harmful drift fails the build; stricter-local is just
  informational. Local being stricter than CI is never a regression.
- Wire this both as a **local hook** (so devs see drift before pushing) and as a
  **CI job** (so the gate itself cannot be skipped). The gate guarding the
  mirror is what keeps the mirror from rotting.
- Adapt the source globs for your CI system (`.github/workflows/*.yml`,
  `.gitlab-ci.yml`, etc.). The classification logic is CI-system-agnostic; only
  the file discovery and the YAML shape walked differ.
