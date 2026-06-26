# Generic Lib Prompt: Token-Economical `llms.txt` Structural Renderer

## Purpose

Render the per-file extraction records into a **token-economical, section-loadable
`llms.txt`** — a structural summary an agent reads instead of slurping the whole
machine graph. The load-bearing affordance: an agent can grep `## <path>` and read
**one module's section** rather than loading the entire index. This is the property
a heavyweight whole-graph dump loses, and the reason the format is per-file
sections, not one giant blob.

## Reusable Pattern

- **Short header with whole-index counts** (files / nodes / edges / language
  histogram) so a reader knows the shape before loading anything, plus a
  DO-NOT-EDIT / regenerate-with line.
- **One `## <path> [lang]` section per file, in stable path order**, each
  independently readable. The section header is greppable.
- **Deliberately terse sections** to hold the whole-index token cost near a target:
  parameter names without type annotations, module names without per-symbol import
  members. Terseness is the point.
- **Symbol rendering by kind:** class/interface show base/extends names in
  parentheses (no params); type aliases show just the name; functions/methods show
  `(params)`; nest children with indentation.
- **Language-specific extras** (e.g. graph labels/relationships/clauses, re-exports)
  appended as compact lines from `FileInfo.extra`.
- **Single trailing newline** for diff stability.

## Algorithm

1. Sort files by path; build a language histogram.
2. Emit the header (counts + langs).
3. Per file: `## <path> [lang]`, optional summary line, deduped `imports:` line,
   then each symbol recursively, then any extras (`labels:`/`rels:`/`clauses:`/
   `re-exports:`).
4. Join with newlines; `rstrip("\n") + "\n"`.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Render a token-economical, section-loadable llms.txt structural summary."""
from __future__ import annotations

from .model import FileInfo, SymbolInfo

_HEADER = (
    "# Structural index — {repo}\n"
    "# Generated — DO NOT EDIT — regenerate with the structural generator.\n"
    "# files={files} nodes={nodes} edges={edges} langs={langs}\n"
    "# Each '## <path>' section is independently loadable — read only what you need.\n"
)


def _dedup(seq: list[str]) -> list[str]:
    seen, out = set(), []
    for x in seq:
        if x and x not in seen:
            seen.add(x); out.append(x)
    return out


def _render_symbol(sym: SymbolInfo, depth: int, lines: list[str]) -> None:
    indent = "  " * depth
    if sym.kind in ("class", "interface"):
        bases = f"({', '.join(sym.bases)})" if sym.bases else ""
        lines.append(f"{indent}- {sym.kind} {sym.name}{bases} @{sym.line}")
    elif sym.kind == "type":
        lines.append(f"{indent}- type {sym.name} @{sym.line}")
    else:
        lines.append(f"{indent}- {sym.kind} {sym.name}({', '.join(sym.params)}) @{sym.line}")
    for child in sym.children:
        _render_symbol(child, depth + 1, lines)


def _render_file(fi: FileInfo) -> list[str]:
    lines = [f"## {fi.path} [{fi.lang}]"]
    if fi.summary:
        lines.append(fi.summary)
    mods = _dedup([imp.module for imp in fi.imports])
    if mods:
        lines.append(f"imports: {', '.join(mods)}")
    for sym in fi.symbols:
        _render_symbol(sym, 0, lines)
    for key in ("labels", "relationships", "clauses"):
        vals = fi.extra.get(key)
        if vals:
            label = "rels" if key == "relationships" else key
            lines.append(f"{label}: {', '.join(vals)}")
    if fi.reexports:
        lines.append(f"re-exports: {', '.join(_dedup(fi.reexports))}")
    return lines


def render_llms(files: list[FileInfo], repo_name: str, nodes: int, edges: int) -> str:
    ordered = sorted(files, key=lambda f: f.path)
    counts: dict[str, int] = {}
    for f in ordered:
        counts[f.lang] = counts.get(f.lang, 0) + 1
    langs = ",".join(f"{k}:{counts[k]}" for k in sorted(counts))
    out = [_HEADER.format(repo=repo_name, files=len(ordered), nodes=nodes,
                          edges=edges, langs=langs or "none")]
    for fi in ordered:
        out.append("")
        out.extend(_render_file(fi))
    return "\n".join(out).rstrip("\n") + "\n"
```

## Adaptation Notes

- **Section-loadability is the whole point.** Keep one greppable `## <path>` header
  per file so a consumer reads a single module's block, not the whole file.
- **Stay terse on purpose.** Dropping type annotations and per-symbol import members
  is what keeps the whole-index token cost near target. Add detail only if your
  budget allows.
- **Extras are a generic escape hatch.** Any language-specific structure that
  doesn't fit the node/edge contract (graph labels, query clauses, re-exports)
  rides in `FileInfo.extra` and renders as a compact line here.
- **Keep output byte-stable** (sorted files, deduped lists, single trailing
  newline) so regeneration diffs stay minimal.
```
