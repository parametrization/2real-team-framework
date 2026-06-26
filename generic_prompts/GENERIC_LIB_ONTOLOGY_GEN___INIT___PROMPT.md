# Generic Lib Prompt: Structural-Generator Package Facade (`__init__.py`)

## Purpose

The package facade for a multi-module structural-index generator: re-export the
small public surface (the orchestration entry points and the data-model contract
types) so callers import from the package root, while keeping the CLI-only
submodules out of the facade.

## Reusable Pattern

- **Re-export the library surface, not the CLIs.** Expose the `generate` /
  `build_graph` / `discover` orchestration functions and the `CodeGraph` / `Node` /
  `Edge` / `FileInfo` contract types from `__init__`. These are what a library
  consumer (or a sibling tool) imports.
- **Do NOT re-export submodules that are run as `python3 -m ontology_gen.<sub>`**
  (the aggregator, the merge-driver). Importing them at package-init time would
  re-import the module after the package loads and emit a spurious
  `RuntimeWarning` from `runpy`. Import those directly where needed
  (`from ontology_gen.aggregate import aggregate`).
- **Explicit `__all__`** documents and bounds the public surface.

## Code Template (stdlib only)

```python
"""Owned structural ontology generator.

Generates the per-repo structural layer (code-graph.json + llms.txt) from source,
replacing hand-resolution of that layer with regeneration.

CLI: python3 -m ontology_gen <repo-root> --out <out-dir>/
"""
from __future__ import annotations

from .generate import build_graph, discover, generate
from .model import CodeGraph, Edge, FileInfo, Node

# NOTE: the CLI submodules (aggregate, merge_driver) are intentionally NOT
# re-exported here. Both run as `python3 -m ontology_gen.<submodule>`; importing
# them at package-init time would re-import after the package loads and emit a
# spurious RuntimeWarning from runpy. Import them directly where needed.

__all__ = [
    "CodeGraph",
    "Edge",
    "FileInfo",
    "Node",
    "build_graph",
    "discover",
    "generate",
]
```

## Adaptation Notes

- **The runpy gotcha is the transferable lesson.** Any package that has both a
  library surface AND submodules invoked via `python3 -m pkg.sub` should keep those
  `-m`-run submodules out of `__init__`, or importing the package while running the
  submodule triggers a double-import `RuntimeWarning`.
- **Keep `__all__` tight** — the facade is the contract for what's public; CLI
  internals and helpers stay unexported.
```
