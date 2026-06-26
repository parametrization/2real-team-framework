# Generic Lib Prompt: Structural-Index Discovery + Orchestration

## Purpose

The one entry point that drives structural-index generation for a repo:
`generate(repo_root, out_dir, repo_name)`. It discovers supported source files,
dispatches each to its per-language extractor, assembles the `CodeGraph`, renders
the human-readable `llms.txt`, and writes both artifacts deterministically.

## Reusable Pattern

- **Git-aware discovery with a walk fallback.** When the root is a git repo,
  enumerate `git ls-files --cached --others --exclude-standard` (tracked +
  untracked-but-not-ignored) so the output reflects the working tree AND respects
  `.gitignore`. Otherwise fall back to an `os.walk`/`rglob` with a default
  ignore-dir set (`.git`, `node_modules`, `.venv`, caches, build dirs, …).
- **Always-skip prefixes** (e.g. nested worktree checkouts of other branches) are
  dropped even under git discovery, so transient scratch trees never pollute the
  index.
- **Per-file fault isolation.** A single unparseable file degrades to a bare
  file/module node (caught `SyntaxError`/decode error) instead of aborting the
  whole run.
- **Sorted, dedup-stable file list** → deterministic output regardless of walk
  order.
- **Extension → extractor dispatch** behind one `_extract_one`, so adding a
  language is adding an extension tuple and a branch.

## Algorithm

1. `discover(repo_root)`: git-listed (or walked) repo-relative POSIX paths, drop
   always-skip prefixes, keep supported extensions, return `sorted(set(...))`.
2. `build_graph`: read each file (skip on OS/decode error), dispatch to the
   matching extractor (Python via `ast` with a `SyntaxError` fallback; others by
   extension), collect `FileInfo`s, sort by path, `assemble`.
3. `generate`: `to_dict()` the graph, write `code-graph.json` via the canonical
   serializer, render and write `llms.txt`, return `{files, nodes, edges}` counts.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Discovery + orchestration for the structural index generator."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .assemble import assemble
from .llms import render_llms
from .model import CodeGraph, FileInfo, serialize_graph
from .python_ext import extract_python
from .typescript_ext import extract_typescript
# from .cypher_ext import extract_cypher  # + any other language extractors

_PY_EXTS = (".py",)
_TS_EXTS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
_SUPPORTED = _PY_EXTS + _TS_EXTS

_IGNORE_DIRS = frozenset({".git", ".hg", ".svn", "node_modules", ".venv", "venv",
                          "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
                          "dist", "build", ".worktrees"})
_ALWAYS_SKIP_PREFIXES = (".worktrees/",)


def _git_listed_files(repo_root: Path) -> list[str] | None:
    try:
        r = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                           cwd=repo_root, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return [ln for ln in r.stdout.splitlines() if ln]


def _walk_files(repo_root: Path) -> list[str]:
    out = []
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(repo_root).parts
        if any(part in _IGNORE_DIRS for part in rel):
            continue
        out.append("/".join(rel))
    return out


def discover(repo_root: Path) -> list[str]:
    listed = _git_listed_files(repo_root)
    cands = listed if listed is not None else _walk_files(repo_root)
    out = [rel for rel in cands
           if not rel.startswith(_ALWAYS_SKIP_PREFIXES) and rel.endswith(_SUPPORTED)]
    return sorted(set(out))


def _extract_one(rel: str, source: str) -> FileInfo:
    if rel.endswith(_PY_EXTS):
        try:
            return extract_python(rel, source)
        except SyntaxError:
            return FileInfo(path=rel, lang="python", kind="module")
    return extract_typescript(rel, source)


def build_graph(repo_root: Path) -> tuple[CodeGraph, list[FileInfo]]:
    files: list[FileInfo] = []
    for rel in discover(repo_root):
        try:
            source = (repo_root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        files.append(_extract_one(rel, source))
    files.sort(key=lambda f: f.path)
    return assemble(files), files


def generate(repo_root: Path, out_dir: Path, repo_name: str) -> dict[str, int]:
    graph, files = build_graph(repo_root)
    gd = graph.to_dict()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "code-graph.json").write_text(serialize_graph(gd), encoding="utf-8")
    (out_dir / "llms.txt").write_text(
        render_llms(files, repo_name, len(gd["nodes"]), len(gd["edges"])), encoding="utf-8")
    return {"files": len(files), "nodes": len(gd["nodes"]), "edges": len(gd["edges"])}
```

## Adaptation Notes

- **Prefer git discovery, fall back to walk.** Git listing respects `.gitignore`
  and includes new-but-uncommitted files; the walk fallback keeps the generator
  usable outside a git checkout. Keep both.
- **Per-file fault isolation is mandatory** for a generator run over a whole repo:
  one bad file must never abort the index. Degrade to a bare node and continue.
- **Sort everything that feeds output** so the artifacts are byte-stable across
  machines and runs.
- **New language = extension tuple + extractor + one dispatch branch.** Everything
  downstream (assemble, render, serialize) is language-agnostic.
```
