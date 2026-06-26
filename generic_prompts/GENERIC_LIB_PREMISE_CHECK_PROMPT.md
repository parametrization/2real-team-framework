# Generic Lib Prompt: Premise-Rot Gate (named-file/symbol existence at HEAD)

## Purpose

Catch **premise rot** before scoped work reaches execution: an issue/ticket that
names a specific file, path, or symbol as its target may rest on a premise that
no longer holds — the file was deleted, renamed, or the named root cause was
inverted by an intervening change. This deterministic gate verifies that every
file/path/symbol a scoped issue names **still exists at the repo's origin HEAD**
before the work is dispatched.

It extends "verify the diagnosis before delegating" and "verify file existence
at HEAD" from *spawn* time back to *scope* time, so a rotted premise is caught
when the work is planned, not when an implementer hits a missing file.

## Reusable Pattern

**Two-layer design: a pure, testable core + an injectable I/O layer.**

- **Pure core** — extract path/symbol candidates from issue text and decide a
  verdict from a list of existence statuses. No git, no subprocess. This is the
  part unit tests exercise in isolation.
- **Injectable checkers** — `path_checker(repo_dir, ref, path)` and
  `symbol_checker(repo_dir, ref, symbol, pathspec)` default to real git but are
  passed in, so tests run with zero git and the verdict logic is tested without
  a repo.

**Precision over recall in extraction.** A false negative just means one fewer
thing checked; a false positive turns prose into a spurious STOP that blocks
scoping. Accept a token as a path only when it is whitespace-free,
path-character-only, and EITHER contains a `/` OR ends in a known code
extension. Reject URLs and bare issue/anchor numbers.

**Three-state existence → three-tier verdict (the policy core):**

| Existence status | Meaning | Issue verdict |
|---|---|---|
| `MISSING` | ref readable, but does NOT contain the named path/symbol | **STOP** (premise rot — the headline signal) |
| `UNVERIFIABLE` | ref/repo dir cannot be read at all (not cloned, not fetched, bad ref) | **WARN** (environment gap, NOT premise rot) |
| `EXISTS` (or nothing concrete to check) | present | **OK** |

The `UNVERIFIABLE → WARN` (not STOP) decision is deliberate and load-bearing: a
missing local checkout is a tooling gap, not evidence the premise rotted. A
false STOP there would block scoping on environment state — the opposite of the
gate's purpose.

## Algorithm

1. **Extract candidates** from issue body: union of backtick code-spans and a
   path-token regex over the full text; normalize each (strip `./`, quotes,
   trailing punctuation, `:line`/`#Lnn` suffixes) and keep only those passing
   `looks_like_path`. Also accept explicit `paths`/`symbols` arrays an issue
   declares (a symbol may carry a `pathspec` scope).
2. **Check each candidate** against the ref via the injected checker:
   - path: `git -C <dir> cat-file -e <ref>:<path>` → EXISTS/MISSING; ref
     unreadable → UNVERIFIABLE.
   - symbol: `git -C <dir> grep -I -q -F -e <symbol> <ref> [-- <pathspec>]`
     → 0 EXISTS / 1 MISSING / >1 or unreadable UNVERIFIABLE.
3. **Verdict** per issue: any MISSING → STOP; else any UNVERIFIABLE → WARN; else OK.
4. Exit `1` if any issue is STOP (unless `--warn-only`), else `0`.

Use a fixed-argv subprocess call (never `shell=True`) so there is no shell
word-splitting.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Scope-time premise-rot gate: verify each scoped issue's named files/symbols
still exist at origin HEAD. Exit 1 if any verdict is STOP (unless --warn-only)."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

EXISTS, MISSING, UNVERIFIABLE = "exists", "missing", "unverifiable"
OK, WARN, STOP = "ok", "warn", "stop"

_CODE_EXTENSIONS = frozenset({
    "py", "pyi", "md", "json", "yaml", "yml", "toml", "ts", "tsx", "js", "jsx",
    "sh", "bash", "cfg", "ini", "txt", "lock", "sql", "css", "html", "go", "rs",
})
_PATH_TOKEN_RE = re.compile(r"[\w./\-]+")
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")


def looks_like_path(token: str) -> bool:
    tok = token.strip()
    if not tok or " " in tok or "\t" in tok or "://" in tok:
        return False
    if not re.fullmatch(r"[\w./\-]+", tok):
        return False
    if tok.lstrip("#").isdigit():
        return False
    if "/" in tok:
        return True
    ext = tok.rsplit(".", 1)[-1].lower() if "." in tok else ""
    return ext in _CODE_EXTENSIONS


def normalize_path(token: str) -> str:
    tok = token.strip().lstrip("`'\"")
    tok = re.sub(r":\d+(-\d+)?$", "", tok)
    tok = re.sub(r"#L\d+$", "", tok)
    tok = tok.rstrip("`'\").,;:")
    return tok[2:] if tok.startswith("./") else tok


def extract_path_candidates(text: str) -> list[str]:
    if not text:
        return []
    raw = list(_BACKTICK_RE.findall(text)) + _PATH_TOKEN_RE.findall(text)
    seen, out = set(), []
    for token in raw:
        norm = normalize_path(token)
        if looks_like_path(norm) and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def _run_git(repo_dir: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # fixed argv, no shell
        ["git", "-C", repo_dir, *args], capture_output=True, text=True, check=False
    )


def git_ref_exists(repo_dir: str, ref: str) -> bool:
    if not Path(repo_dir).is_dir():
        return False
    return _run_git(repo_dir, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"]).returncode == 0


def git_path_status(repo_dir: str, ref: str, path: str) -> str:
    if not git_ref_exists(repo_dir, ref):
        return UNVERIFIABLE
    return EXISTS if _run_git(repo_dir, ["cat-file", "-e", f"{ref}:{path}"]).returncode == 0 else MISSING


def git_symbol_status(repo_dir: str, ref: str, symbol: str, pathspec: str | None = None) -> str:
    if not git_ref_exists(repo_dir, ref):
        return UNVERIFIABLE
    args = ["grep", "-I", "-q", "-F", "-e", symbol, ref]
    if pathspec:
        args += ["--", pathspec]
    rc = _run_git(repo_dir, args).returncode
    return EXISTS if rc == 0 else (MISSING if rc == 1 else UNVERIFIABLE)


PathChecker = Callable[[str, str, str], str]
SymbolChecker = Callable[[str, str, str, "str | None"], str]


@dataclass
class CandidateResult:
    kind: str
    value: str
    status: str
    pathspec: str | None = None


@dataclass
class IssueResult:
    ref: str
    verdict: str
    candidates: list[CandidateResult] = field(default_factory=list)


def _verdict_for(cands: list[CandidateResult]) -> str:
    if any(c.status == MISSING for c in cands):
        return STOP
    if any(c.status == UNVERIFIABLE for c in cands):
        return WARN
    return OK


def collect_candidates(issue: dict) -> list[tuple[str, str, str | None]]:
    triples, seen = [], set()

    def add(kind, value, pathspec):
        key = (kind, value, pathspec)
        if value and key not in seen:
            seen.add(key)
            triples.append(key)

    for p in extract_path_candidates(issue.get("body", "") or ""):
        add("path", p, None)
    for p in issue.get("paths", []) or []:
        add("path", normalize_path(str(p)), None)
    for sym in issue.get("symbols", []) or []:
        if isinstance(sym, dict):
            add("symbol", str(sym.get("name", "")), sym.get("pathspec"))
        else:
            add("symbol", str(sym), None)
    return triples


def check_issue(issue, repos_root, default_ref,
                path_checker=git_path_status, symbol_checker=git_symbol_status):
    repo_dir = str(issue.get("repo_dir") or repos_root)
    git_ref = issue.get("git_ref") or default_ref
    cands = []
    for kind, value, pathspec in collect_candidates(issue):
        status = (path_checker(repo_dir, git_ref, value) if kind == "path"
                  else symbol_checker(repo_dir, git_ref, value, pathspec))
        cands.append(CandidateResult(kind, value, status, pathspec))
    return IssueResult(str(issue.get("ref", "?")), _verdict_for(cands), cands)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--issues", required=True)
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--repos-root", type=Path, default=Path("."))
    ap.add_argument("--warn-only", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    issues = json.loads(Path(args.issues).read_text())
    if not isinstance(issues, list):
        print("ERROR: --issues must be a JSON array", file=sys.stderr)
        return 2
    results = [check_issue(i, args.repos_root, args.ref) for i in issues]
    for r in results:
        print(f"[{r.verdict.upper()}] {r.ref}")
        for c in r.candidates:
            print(f"    - {c.kind} `{c.value}`: {c.status}")
    has_stop = any(r.verdict == STOP for r in results)
    return 1 if (has_stop and not args.warn_only) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

## Adaptation Notes

- **The three-tier verdict policy is the core idea** — keep `MISSING → STOP`
  (premise rot) distinct from `UNVERIFIABLE → WARN` (environment gap). Collapsing
  them re-introduces the false STOP this gate avoids.
- **Inject the checkers** so the pure extraction/verdict logic is unit-testable
  without a real repo. Test the core with fake checkers that return canned
  statuses.
- **Tune `_CODE_EXTENSIONS`** to the languages in your repos. The extension set
  is what lets a bare (slash-less) token like `config.py` be recognized as a
  path while leaving prose words alone.
- For a **multi-repo** setup, resolve each issue's `repo` to a directory under a
  `--repos-root` (with an explicit `repo_dir` override); for a single repo,
  default the dir to the repo root. The `git grep`/`cat-file` checks work the
  same either way.
- Wire this into the **scope/planning step** of your workflow, with `--warn-only`
  available for an advisory rollout before flipping it to a hard gate.
