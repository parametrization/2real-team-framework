#!/usr/bin/env python3
"""Scope-time premise-rot gate for /wave-scope (main#837).

The P6W16 retro found that two scoped issues reached *execution* on premises
that no longer held at origin HEAD: **#705** targeted ``wave_key_reset.py`` —
a file #804 had already deleted — and **#816**'s named root cause had been
inverted. ``/wave-scope`` reconciled labels-vs-meta-issue but never checked that
a scoped issue's named *file / path / symbol* still exists at the repo's origin
HEAD. This module is the deterministic check that closes that gap: it extends
``feedback_verify_diagnosis_before_delegating`` +
``feedback_pre_spawn_verify_file_exists`` from *spawn* time back to *scope* time.

Two-layer design (the pure core is the testable part; git I/O is injectable):

  * ``extract_path_candidates(text)`` — pure. Pulls path-like tokens out of an
    issue body (backtick code spans + a strict path regex over the full text),
    filtered by :func:`looks_like_path` so prose never produces a false STOP.
  * ``check_issue(issue, ref, path_checker, symbol_checker)`` — wires extraction
    to existence checks. The two checkers are injected (default: real git) so
    unit tests run with zero git, and the verdict logic is exercised in
    isolation.
  * ``git_path_status`` / ``git_symbol_status`` — the real checks:
    ``git -C <dir> cat-file -e <ref>:<path>`` for a path,
    ``git -C <dir> grep -q -e <symbol> <ref>`` for a symbol.

Verdict policy (deterministic):

  * a named path/symbol that the ref can read but does NOT contain -> ``MISSING``
    -> issue verdict ``STOP`` (premise rot — the headline #837 signal).
  * a ref or repo dir that cannot be read at all (child repo not cloned,
    origin not fetched, bad ref) -> ``UNVERIFIABLE`` -> verdict ``WARN``. This is
    deliberately NOT a STOP: a missing local checkout is an environment gap, not
    evidence the premise rotted — a false STOP there would block scope on
    tooling state, the opposite of the gate's purpose.
  * everything present, or no concrete refs to check -> ``OK``.

An issue may also declare explicit ``paths`` / ``symbols`` arrays (deliberate
named premises the orchestrator wants asserted even if the body phrasing is too
loose for auto-extraction); a symbol may be scoped to a pathspec.

CLI:
  premise_check.py check --issues ISSUES.json [--ref origin/main]
                         [--repos-root DIR] [--warn-only] [--json]

  ISSUES.json is a JSON array; each element:
    {
      "ref": "main#705",            # human label for reporting (required)
      "repo": "noorinalabs-main",   # used to resolve repo_dir under repos-root
      "body": "... `wave_key_reset.py` ...",   # auto-extracted (optional)
      "paths": ["explicit/path.py"],           # optional explicit paths
      "symbols": [                              # optional explicit symbols
        {"name": "wave_key_reset", "pathspec": ".claude/lib/"}
      ],
      "repo_dir": "/abs/path",      # optional; overrides repos-root resolution
      "git_ref": "origin/main"      # optional per-issue ref override
    }

Exit code: 1 if any issue verdict is STOP (unless ``--warn-only``), else 0.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# Repo root = two parents above .claude/lib/ (lib -> .claude -> root). Resolved
# from this file so the default repos-root is correct from any cwd or worktree.
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Candidate existence states.
EXISTS = "exists"
MISSING = "missing"
UNVERIFIABLE = "unverifiable"

# Per-issue verdicts.
OK = "ok"
WARN = "warn"
STOP = "stop"

# File extensions that mark a bare (slash-less) token as a path rather than
# prose. Lower-cased; the token's suffix is compared case-insensitively.
_CODE_EXTENSIONS = frozenset(
    {
        "py",
        "pyi",
        "md",
        "json",
        "jsonl",
        "ndjson",
        "yaml",
        "yml",
        "toml",
        "ts",
        "tsx",
        "js",
        "jsx",
        "mjs",
        "cjs",
        "sh",
        "bash",
        "zsh",
        "cfg",
        "ini",
        "txt",
        "lock",
        "sql",
        "tf",
        "tfvars",
        "astro",
        "css",
        "scss",
        "html",
        "env",
        "mk",
        "rs",
        "go",
        "csv",
        "tsv",
    }
)

# A token that could be a path: only path-safe characters, no whitespace. The
# stricter looks_like_path() decides whether it actually is one.
_PATH_TOKEN_RE = re.compile(r"[\w./\-]+")

# Backtick code span: ``foo`` -> foo. Non-greedy, single line.
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")


def looks_like_path(token: str) -> bool:
    """True when ``token`` is plausibly a repo-relative file/dir path.

    Precision over recall: a false negative just means one fewer thing checked;
    a false positive turns prose into a spurious STOP. Accepts a token only when
    it is whitespace-free, path-character-only, and EITHER contains a ``/``
    (directory structure) OR ends in a known code extension.
    """
    tok = token.strip()
    if not tok or " " in tok or "\t" in tok:
        return False
    if "://" in tok:  # URL, not a path
        return False
    if not re.fullmatch(r"[\w./\-]+", tok):
        return False
    # A bare issue/anchor ref or a number is never a path.
    if tok.lstrip("#").isdigit():
        return False
    if "/" in tok:
        return True
    ext = tok.rsplit(".", 1)[-1].lower() if "." in tok else ""
    return ext in _CODE_EXTENSIONS


def normalize_path(token: str) -> str:
    """Strip decoration so a raw token becomes a git-addressable repo path.

    Removes a leading ``./``, surrounding quotes/backticks, trailing sentence
    punctuation, and a ``:line`` / ``#Lnn`` location suffix (``foo.py:42`` and
    ``foo.py#L42`` both address ``foo.py``).
    """
    tok = token.strip().lstrip("`'\"")
    # Drop a file:line / file#Lnn location suffix before trimming punctuation
    # (so the digits aren't mistaken for a path char and the colon is removed).
    tok = re.sub(r":\d+(-\d+)?$", "", tok)
    tok = re.sub(r"#L\d+$", "", tok)
    # Trailing decoration: backticks, quotes, sentence punctuation. NOT stripped
    # from the left, where a leading `.` is meaningful (`.claude/...`, `./a`).
    tok = tok.rstrip("`'\").,;:")
    if tok.startswith("./"):
        tok = tok[2:]
    return tok


def extract_path_candidates(text: str) -> list[str]:
    """Path-like tokens in ``text``, de-duplicated, order-preserving.

    Union of backtick code spans and a path-token regex over the full text,
    each normalized and filtered through :func:`looks_like_path`.
    """
    if not text:
        return []
    raw: list[str] = list(_BACKTICK_RE.findall(text))
    raw.extend(_PATH_TOKEN_RE.findall(text))

    seen: set[str] = set()
    out: list[str] = []
    for token in raw:
        norm = normalize_path(token)
        if not looks_like_path(norm):
            continue
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


# --- git I/O (the injectable, side-effecting layer) -------------------------


def _run_git(repo_dir: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ``git -C <repo_dir> <args>`` with an explicit arg list.

    Never a shell string and never ``shell=True`` — no shell means no
    word-splitting under zsh (main#688), the contract shared across the lib.
    """
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-C", repo_dir, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def git_ref_exists(repo_dir: str, ref: str) -> bool:
    """True when ``ref`` resolves in the repo at ``repo_dir``."""
    if not Path(repo_dir).is_dir():
        return False
    proc = _run_git(repo_dir, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
    return proc.returncode == 0


def git_path_status(repo_dir: str, ref: str, path: str) -> str:
    """Existence of ``path`` at ``ref`` via ``git cat-file -e``.

    Returns :data:`UNVERIFIABLE` when the repo dir or ref cannot be read (an
    environment gap, never treated as premise rot), otherwise :data:`EXISTS` /
    :data:`MISSING`.
    """
    if not git_ref_exists(repo_dir, ref):
        return UNVERIFIABLE
    proc = _run_git(repo_dir, ["cat-file", "-e", f"{ref}:{path}"])
    return EXISTS if proc.returncode == 0 else MISSING


def git_symbol_status(repo_dir: str, ref: str, symbol: str, pathspec: str | None = None) -> str:
    """Presence of ``symbol`` at ``ref`` via ``git grep`` (optionally scoped).

    ``git grep`` exits 0 on a match, 1 on no match, and >1 on error. The error
    case (and an unreadable ref) degrades to :data:`UNVERIFIABLE`.
    """
    if not git_ref_exists(repo_dir, ref):
        return UNVERIFIABLE
    args = ["grep", "-I", "-q", "-F", "-e", symbol, ref]
    if pathspec:
        args += ["--", pathspec]
    proc = _run_git(repo_dir, args)
    if proc.returncode == 0:
        return EXISTS
    if proc.returncode == 1:
        return MISSING
    return UNVERIFIABLE


# --- verdict layer (pure given the injected checkers) -----------------------

# (repo_dir, ref, value) -> status
PathChecker = Callable[[str, str, str], str]
# (repo_dir, ref, symbol, pathspec) -> status
SymbolChecker = Callable[[str, str, str, "str | None"], str]


@dataclass
class CandidateResult:
    kind: str  # "path" | "symbol"
    value: str
    status: str  # EXISTS | MISSING | UNVERIFIABLE
    pathspec: str | None = None


@dataclass
class IssueResult:
    ref: str
    repo: str
    repo_dir: str
    git_ref: str
    verdict: str  # OK | WARN | STOP
    candidates: list[CandidateResult] = field(default_factory=list)

    @property
    def missing(self) -> list[CandidateResult]:
        return [c for c in self.candidates if c.status == MISSING]

    @property
    def unverifiable(self) -> list[CandidateResult]:
        return [c for c in self.candidates if c.status == UNVERIFIABLE]


def _verdict_for(candidates: list[CandidateResult]) -> str:
    if any(c.status == MISSING for c in candidates):
        return STOP
    if any(c.status == UNVERIFIABLE for c in candidates):
        return WARN
    return OK


def resolve_repo_dir(issue: dict, repos_root: Path) -> str:
    """Filesystem dir for an issue's repo.

    Explicit ``repo_dir`` wins. Otherwise the parent org root *is*
    ``noorinalabs-main``; every child repo lives at ``<repos_root>/<repo>``.
    """
    explicit = issue.get("repo_dir")
    if explicit:
        return str(explicit)
    repo = issue.get("repo") or "noorinalabs-main"
    if repo == "noorinalabs-main":
        return str(repos_root)
    return str(repos_root / repo)


def collect_candidates(issue: dict) -> list[tuple[str, str, str | None]]:
    """Flatten an issue's premises to ``(kind, value, pathspec)`` triples.

    Auto-extracted body paths + explicit ``paths`` (kind ``path``) and explicit
    ``symbols`` (kind ``symbol``). De-duplicated on ``(kind, value, pathspec)``.
    """
    triples: list[tuple[str, str, str | None]] = []
    seen: set[tuple[str, str, str | None]] = set()

    def _add(kind: str, value: str, pathspec: str | None) -> None:
        key = (kind, value, pathspec)
        if value and key not in seen:
            seen.add(key)
            triples.append(key)

    for p in extract_path_candidates(issue.get("body", "") or ""):
        _add("path", p, None)
    for p in issue.get("paths", []) or []:
        _add("path", normalize_path(str(p)), None)
    for sym in issue.get("symbols", []) or []:
        if isinstance(sym, dict):
            _add("symbol", str(sym.get("name", "")), sym.get("pathspec"))
        else:
            _add("symbol", str(sym), None)
    return triples


def check_issue(
    issue: dict,
    repos_root: Path,
    default_ref: str,
    path_checker: PathChecker = git_path_status,
    symbol_checker: SymbolChecker = git_symbol_status,
) -> IssueResult:
    """Verify every named premise of one scoped issue against its repo HEAD."""
    repo_dir = resolve_repo_dir(issue, repos_root)
    git_ref = issue.get("git_ref") or default_ref
    candidates: list[CandidateResult] = []
    for kind, value, pathspec in collect_candidates(issue):
        if kind == "path":
            status = path_checker(repo_dir, git_ref, value)
        else:
            status = symbol_checker(repo_dir, git_ref, value, pathspec)
        candidates.append(CandidateResult(kind, value, status, pathspec))
    return IssueResult(
        ref=str(issue.get("ref", "?")),
        repo=str(issue.get("repo", "noorinalabs-main")),
        repo_dir=repo_dir,
        git_ref=git_ref,
        verdict=_verdict_for(candidates),
        candidates=candidates,
    )


def check_issues(
    issues: list[dict],
    repos_root: Path,
    default_ref: str,
    path_checker: PathChecker = git_path_status,
    symbol_checker: SymbolChecker = git_symbol_status,
) -> list[IssueResult]:
    return [check_issue(i, repos_root, default_ref, path_checker, symbol_checker) for i in issues]


# --- reporting + CLI --------------------------------------------------------

_STATUS_GLYPH = {EXISTS: "ok", MISSING: "MISSING", UNVERIFIABLE: "unverifiable"}


def render_report(results: list[IssueResult]) -> str:
    lines: list[str] = []
    stops = [r for r in results if r.verdict == STOP]
    warns = [r for r in results if r.verdict == WARN]

    for r in results:
        if r.verdict == OK and not r.candidates:
            lines.append(f"[ok]   {r.ref}: no concrete file/symbol refs to verify")
            continue
        tag = {OK: "ok", WARN: "WARN", STOP: "STOP"}[r.verdict]
        lines.append(f"[{tag}] {r.ref}  ({r.repo} @ {r.git_ref})")
        for c in r.candidates:
            scope = f" in {c.pathspec}" if c.pathspec else ""
            lines.append(f"    - {c.kind} `{c.value}`{scope}: {_STATUS_GLYPH[c.status]}")

    lines.append("")
    if stops:
        lines.append(
            f"STOP: {len(stops)} issue(s) name a file/symbol absent at origin HEAD "
            "(premise rot). Re-scope, re-point, or close before /wave-kickoff:"
        )
        for r in stops:
            refs = ", ".join(f"{c.kind} {c.value}" for c in r.missing)
            lines.append(f"  - {r.ref}: {refs}")
    if warns:
        lines.append(
            f"WARN: {len(warns)} issue(s) could not be verified "
            "(repo not cloned / ref not fetched / unreadable). Verify manually:"
        )
        for r in warns:
            refs = ", ".join(f"{c.kind} {c.value}" for c in r.unverifiable)
            lines.append(f"  - {r.ref} ({r.repo_dir} @ {r.git_ref}): {refs}")
    if not stops and not warns:
        lines.append("All named files/symbols verified present at origin HEAD.")
    return "\n".join(lines)


def _result_to_dict(r: IssueResult) -> dict:
    return {
        "ref": r.ref,
        "repo": r.repo,
        "repo_dir": r.repo_dir,
        "git_ref": r.git_ref,
        "verdict": r.verdict,
        "candidates": [
            {"kind": c.kind, "value": c.value, "status": c.status, "pathspec": c.pathspec}
            for c in r.candidates
        ],
    }


def _cmd_check(args: argparse.Namespace) -> int:
    issues = json.loads(Path(args.issues).read_text())
    if not isinstance(issues, list):
        print("ERROR: --issues must be a JSON array of issue objects", file=sys.stderr)
        return 2
    results = check_issues(issues, args.repos_root, args.ref)

    if args.json:
        print(json.dumps([_result_to_dict(r) for r in results], indent=2))
    else:
        print(render_report(results))

    has_stop = any(r.verdict == STOP for r in results)
    if has_stop and not args.warn_only:
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="verify scoped issues' named files/symbols")
    p_check.add_argument("--issues", required=True, help="path to the issues JSON array")
    p_check.add_argument(
        "--ref", default="origin/main", help="git ref to check against (default origin/main)"
    )
    p_check.add_argument(
        "--repos-root",
        type=Path,
        default=_REPO_ROOT,
        help="root dir holding the org repos (default: this repo's root)",
    )
    p_check.add_argument(
        "--warn-only",
        action="store_true",
        help="report STOPs but exit 0 (advisory mode)",
    )
    p_check.add_argument("--json", action="store_true", help="machine-readable output")
    p_check.set_defaults(func=_cmd_check)
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
