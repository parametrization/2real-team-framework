#!/usr/bin/env python3
"""Discovery + orchestration for the structural ontology generator.

``generate(repo_root, out_dir, repo_name)`` is the one entry point the CLI calls:

1. discover supported source files (git-tracked + untracked-not-ignored when the root
   is a git repo — so generated output reflects the working tree and respects
   ``.gitignore``; an ``os.walk`` fallback with a default ignore set otherwise).
   Well-known vendored/build dirs (``node_modules``/``dist``/``build``/``coverage``)
   are skipped in both modes — even when committed — so they don't flood the index,
2. dispatch each to its language extractor (a single unparseable file degrades to a
   bare file node instead of aborting the run),
3. assemble the :class:`CodeGraph` and render ``llms.txt``,
4. write both artifacts deterministically.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .assemble import assemble
from .cypher_ext import extract_cypher
from .llms import render_llms
from .model import CodeGraph, FileInfo, serialize_graph
from .python_ext import extract_python
from .typescript_ext import extract_typescript

_PY_EXTS = (".py",)
_TS_EXTS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
_CYPHER_EXTS = (".cypher", ".cql")
_SUPPORTED = _PY_EXTS + _TS_EXTS + _CYPHER_EXTS

# os.walk fallback ignore set (git ls-files handles these via .gitignore normally).
_IGNORE_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".terraform",
        "dist",
        "build",
        ".worktrees",
    }
)
# Always skipped even under git discovery (scratch checkouts of other branches).
_ALWAYS_SKIP_PREFIXES = (".claude/worktrees/",)
# The framework's OWN installed runtime in a consumer repo (issue #74). A bootstrap install
# lays ~35 framework internals under .claude/hooks/ + .claude/lib/; indexing them floods a
# target repo's structural index with framework noise instead of the user's code. Skipped in
# consumer repos only — the framework SOURCE repo's .claude/ is a live dogfood copy worth
# indexing, so it keeps the current behaviour (see _is_framework_source_repo).
_INSTALLED_RUNTIME_PREFIX = ".claude/"
# Vendored deps / build output — skipped in BOTH discovery modes, even when committed.
# git ls-files trusts tracked files, so repos that commit node_modules/dist/coverage would
# otherwise flood the index with thousands of vendored/generated files.
_ALWAYS_SKIP_DIRS = frozenset({"node_modules", "dist", "build", "coverage"})


def _is_framework_source_repo(repo_root: Path) -> bool:
    """True when ``repo_root`` is the framework SOURCE checkout, not a consumer install.

    The source repo ships the canonical install dirs (``framework/assets`` +
    ``framework/install``); a repo that merely *installed* the framework has a populated
    ``.claude/`` but none of that source tree. This gate decides whether the installed
    ``.claude/`` runtime is the framework's own dogfood (index it) or deployed noise in a
    consumer repo (skip it — issue #74).
    """
    return (repo_root / "framework" / "assets").is_dir() and (
        repo_root / "framework" / "install"
    ).is_dir()


def _git_listed_files(repo_root: Path) -> list[str] | None:
    """Tracked + untracked-not-ignored repo-relative paths, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return [line for line in result.stdout.splitlines() if line]


def _walk_files(repo_root: Path) -> list[str]:
    out: list[str] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(repo_root).parts
        if any(part in _IGNORE_DIRS for part in rel_parts):
            continue
        out.append("/".join(rel_parts))
    return out


def discover(repo_root: Path) -> list[str]:
    """Repo-relative POSIX paths of supported source files, sorted, dedup-stable."""
    listed = _git_listed_files(repo_root)
    candidates = listed if listed is not None else _walk_files(repo_root)
    skip_prefixes = _ALWAYS_SKIP_PREFIXES
    if not _is_framework_source_repo(repo_root):
        # Consumer repo: drop the framework's own installed .claude/ runtime (#74).
        skip_prefixes = skip_prefixes + (_INSTALLED_RUNTIME_PREFIX,)
    out: list[str] = []
    for rel in candidates:
        if rel.startswith(skip_prefixes):
            continue
        # Exclude vendored/build dirs at any depth, even when git-tracked.
        if any(part in _ALWAYS_SKIP_DIRS for part in rel.split("/")[:-1]):
            continue
        if rel.endswith(_SUPPORTED):
            out.append(rel)
    return sorted(set(out))


def _extract_one(rel: str, source: str) -> FileInfo:
    if rel.endswith(_PY_EXTS):
        try:
            return extract_python(rel, source)
        except SyntaxError:
            # Unparseable Python: keep a bare module node so the file is still indexed.
            return FileInfo(path=rel, lang="python", kind="module")
    if rel.endswith(_CYPHER_EXTS):
        return extract_cypher(rel, source)
    return extract_typescript(rel, source)


def build_graph(repo_root: Path) -> tuple[CodeGraph, list[FileInfo]]:
    """Discover, extract, and assemble — returns the graph and the per-file records."""
    files: list[FileInfo] = []
    for rel in discover(repo_root):
        abs_path = repo_root / rel
        try:
            source = abs_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        files.append(_extract_one(rel, source))
    files.sort(key=lambda f: f.path)
    return assemble(files), files


def generate(repo_root: Path, out_dir: Path, repo_name: str) -> dict[str, int]:
    """Generate ``code-graph.json`` + ``llms.txt`` into ``out_dir``. Returns counts."""
    graph, files = build_graph(repo_root)
    graph_dict = graph.to_dict()
    node_count = len(graph_dict["nodes"])
    edge_count = len(graph_dict["edges"])

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "code-graph.json").write_text(serialize_graph(graph_dict), encoding="utf-8")

    llms_text = render_llms(files, repo_name, node_count, edge_count)
    (out_dir / "llms.txt").write_text(llms_text, encoding="utf-8")

    return {"files": len(files), "nodes": node_count, "edges": edge_count}
