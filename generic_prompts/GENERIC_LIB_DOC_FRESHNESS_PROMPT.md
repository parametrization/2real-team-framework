# Generic Lib Prompt: Advisory Doc-Freshness Gate

## Purpose

When a change touches **code in a documented surface**, nudge the author and
reviewer that the matching docs (README / docs/ / a registry/index / a charter)
were *not* touched in the same change set — unless an explicit opt-out marker is
present. It mechanizes "code drives the docs": when code moves, the docs that
describe it are expected to move with it.

The signal is **unavoidably heuristic** (a pure refactor, a typo fix, a comment
tweak legitimately need no doc change), so this gate is **advisory by design — it
always exits 0**. It prints a clear report and never blocks a commit, push, or
build. The pattern: a check that *cannot auto-fix cleanly* either hard-blocks with
a precise diagnostic OR stays advisory; for an irreducibly-heuristic nudge, the
right call is advisory.

## Reusable Pattern

- **Always exit 0.** Non-blocking on both sides of the local⇄CI mirror; mark the
  CI job `continue-on-error` to make the intent explicit. Still register it as a
  real check kind in any sync-drift gate so local⇄CI parity holds (the job and
  the hook must both exist).
- **Three-dot diff against a base ref** (`base...HEAD`) = the branch's own changes,
  i.e. a PR's diff. Resolve the base by precedence: explicit `--base` > a CI
  `origin/$BASE_REF` env > `origin/main`. Any git failure degrades to an empty
  change set (report nothing, exit 0) — never crash on an odd git state.
- **Conservative, high-signal surface rules.** Each rule pairs CODE path patterns
  (with a git name-status filter) to the DOC path patterns expected to move with
  them. A rule fires when a code path matches AND none of its doc paths were
  touched. Status-scope the rules: a *new* (`A`) module almost always needs a
  registry entry; editing an existing module's internals (`M`) usually does not —
  scoping the new-module rule to `A` removes that false positive. Fold rename/copy
  (`R`/`C`) to `M`.
- **Opt-out trailer with a load-bearing colon.** A `Docs-N/A:` / `Skip-Doc-Check:`
  line (case-insensitive) in a commit message or the PR body suppresses findings.
  The trailing colon is required so prose that merely *names* the marker (a commit
  or doc discussing it — including this module) does not self-trigger, and so it
  stays distinct from other `Field:`-shaped verdict lines.

## Algorithm

1. Resolve the base ref; if none, report nothing and exit 0.
2. Gather opt-out texts (commit messages in `base..HEAD`, an explicit PR-body
   text, an env var). If any contains an opt-out marker → skip, exit 0.
3. `git diff --name-status base...HEAD` → `(status, path)` pairs.
4. For each surface rule: collect code paths matching its patterns with a status
   in its `statuses` set; if any AND no doc path matched → emit a finding.
5. Print the advisory report; **always return 0.**

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Advisory doc-freshness check — always exits 0 (never blocks)."""
from __future__ import annotations

import argparse
import os
import re
import subprocess  # noqa: S404 - fixed argv, no shell
import sys
from dataclasses import dataclass, field
from pathlib import Path

OPT_OUT_MARKERS = ("docs-n/a:", "skip-doc-check:")


@dataclass(frozen=True)
class Surface:
    name: str
    code: tuple[str, ...]
    docs: tuple[str, ...]
    hint: str
    statuses: frozenset[str] = field(default_factory=lambda: frozenset({"A", "M"}))


# Conservative, high-signal rules. Extend per documented surface in your repo.
SURFACE_RULES: tuple[Surface, ...] = (
    Surface("new-module", (r"^src/[^/]+\.py$",), (r"^docs/INDEX\.md$",),
            "New module — register it in docs/INDEX.md.", frozenset({"A"})),
    Surface("ci-topology", (r"^\.github/workflows/.*\.ya?ml$",), (r"^README\.md$",),
            "CI topology changed — reflect it in README."),
)


def _norm_status(raw: str) -> str:
    if not raw:
        return ""
    first = raw[0].upper()
    return "M" if first in ("R", "C") else first


def has_opt_out(texts: list[str]) -> bool:
    blob = "\n".join(texts).lower()
    return any(m in blob for m in OPT_OUT_MARKERS)


@dataclass(frozen=True)
class Finding:
    surface: str
    code_paths: tuple[str, ...]
    expected_docs: tuple[str, ...]
    hint: str


def evaluate(changed: list[tuple[str, str]], rules=SURFACE_RULES) -> list[Finding]:
    out = []
    for rule in rules:
        code_pats = [re.compile(p) for p in rule.code]
        doc_pats = [re.compile(p) for p in rule.docs]
        touched = [path for st, path in changed
                   if _norm_status(st) in rule.statuses and any(p.match(path) for p in code_pats)]
        if not touched:
            continue
        if any(any(p.match(path) for p in doc_pats) for _, path in changed):
            continue
        out.append(Finding(rule.name, tuple(sorted(set(touched))), rule.docs, rule.hint))
    return out


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                           text=True, check=False)  # noqa: S603
    except (OSError, ValueError):
        return None
    return r.stdout if r.returncode == 0 else None


def resolve_base(root: Path, explicit: str | None) -> str | None:
    cands = ([explicit] if explicit else [])
    ref = os.environ.get("GITHUB_BASE_REF", "").strip()
    if ref:
        cands.append(f"origin/{ref}")
    cands.append("origin/main")
    for ref in cands:
        if _git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], root) is not None:
            return ref
    return None


def changed_files(root: Path, base: str) -> list[tuple[str, str]]:
    out = _git(["diff", "--name-status", f"{base}...HEAD"], root)
    if out is None:
        return []
    pairs = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            pairs.append((parts[0], parts[-1]))  # rename: new path is last field
    return pairs


def render(findings: list[Finding]) -> str:
    if not findings:
        return "doc-freshness: no documented surface changed without a matching doc."
    lines = ["doc-freshness (advisory): code changed in a documented surface "
             "without a matching doc update.", ""]
    for f in findings:
        lines.append(f"  surface: {f.surface}")
        lines += [f"    changed: {p}" for p in f.code_paths]
        lines.append(f"    expected one of: {', '.join(f.expected_docs)}")
        lines.append(f"    -> {f.hint}")
    lines.append("\nLegitimately no doc needed? Add a `Docs-N/A:` trailer to a commit or the PR body.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("repo_root", nargs="?", default=".")
    p.add_argument("--base")
    p.add_argument("--opt-out-text")
    args = p.parse_args(argv[1:])
    root = Path(args.repo_root).resolve()
    base = resolve_base(root, args.base)
    if base is None:
        print("doc-freshness: no diff base resolved — skipping.")
        return 0
    texts = []
    log = _git(["log", "--format=%B", f"{base}..HEAD"], root)
    if log:
        texts.append(log)
    if args.opt_out_text:
        texts.append(args.opt_out_text)
    if has_opt_out(texts):
        print("doc-freshness: opt-out marker present — skipping.")
        return 0
    print(render(evaluate(changed_files(root, base))))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as exc:  # noqa: BLE001 — advisory: never stop a push/build
        print(f"doc-freshness: skipped (internal error: {exc})", file=sys.stderr)
        sys.exit(0)
```

## Adaptation Notes

- **Keep the rules few and conservative.** The value is high signal; an
  exhaustive code↔doc map drowns it. Prefer status-scoped `A`-only rules for
  "new artifact needs a registry entry" — that is the lowest-false-positive case.
- **Never make it blocking.** The exit-0 guarantee (including the outer
  try/except) is the whole posture. If a future edit could exit non-zero,
  `continue-on-error` on the CI side preserves the intent.
- **The colon in the opt-out marker is mandatory** so the marker can be discussed
  in prose without self-triggering. Choose marker spellings distinct from any
  other `Field:` verdict line your tooling parses.
- **Inject a change set for tests** (a `--changed STATUS:PATH` flag) to exercise
  `evaluate` without a git repo.
```
