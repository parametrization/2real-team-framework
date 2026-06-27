#!/usr/bin/env python3
"""Git union merge-driver for ``code-graph.json`` (#855, borrows graphify's pattern).

``code-graph.json`` is a single committed artifact that parallel branches all
regenerate — exactly the ``feedback_parallel_panels_shared_file`` conflict hazard. A
textual 3-way merge produces spurious conflicts on the sorted node/edge arrays even when
the two sides touched different files. This driver instead **semantically union-merges**:
it parses both sides (and the base), unions nodes by ``id`` and edges by
``(src, dst, type)``, re-sorts via the canonical model ordering, and writes the result —
so concurrent regenerations merge cleanly and deterministically.

Wiring (the ``.gitattributes`` + ``git config`` lines) lands in #856; this is the script
that wiring points at.

Canonical invocation form (#871)
---------------------------------
The **plain-script form** is canonical across all repos::

    python3 <path-to>/merge_driver.py %O %A %B %P

This script is self-contained: the ``ImportError`` fallback below (#860) bootstraps
``.claude/lib`` onto ``sys.path`` via ``Path(__file__).resolve().parent.parent``, so
package-relative imports resolve without any ``PYTHONPATH`` manipulation. Git invokes
the driver via the shell, so a relative path works when the driver lives in the same
repo; child repos that locate the driver from the sibling noorinalabs-main checkout use
an absolute path resolved at registration time via ``locate_generator()``.

**noorinalabs-main** (driver lives here — relative path from repo root)::

    git config merge.ontology-codegraph.name 'ontology code-graph union merge'
    git config merge.ontology-codegraph.driver \\
        'python3 .claude/lib/ontology_gen/merge_driver.py %O %A %B %P'

    # or via the Makefile target:
    make setup-ontology-merge-driver

**Child repos** (driver lives in the sibling noorinalabs-main — absolute path resolved
at registration time by ``scripts/structural_ontology.py register-merge-driver`` using
``locate_generator()`` / ``$ONTOLOGY_GEN_LIB``)::

    # Run once per clone (``make setup-hooks`` calls this automatically):
    python3 scripts/structural_ontology.py register-merge-driver

    # Which emits (with the absolute path substituted at registration time):
    git config merge.ontology-codegraph.name 'ontology code-graph union merge'
    git config merge.ontology-codegraph.driver \\
        'python3 /abs/path/noorinalabs-main/.claude/lib/ontology_gen/merge_driver.py %O %A %B %P'

The Python module form (``PYTHONPATH=<lib> python3 -m ontology_gen.merge_driver``) also
works but is NOT canonical — it requires explicit ``PYTHONPATH`` at registration time and
bakes that into the git config. The plain-script self-contained fallback makes it
unnecessary. See ``docs/devops/ontology-structural.md`` for the full rationale and the
six-repo fan-out checklist (#871, #820 C×T2).

Git calls the driver as ``driver %O %A %B [%P]`` where %O=base, %A=ours (result is
written back here), %B=theirs. Exit 0 = merged cleanly.
"""

from __future__ import annotations

import json
import sys

# Git invokes a merge-driver as a PLAIN SCRIPT (``python3 .../merge_driver.py %O %A %B``),
# not as ``python3 -m`` — so at runtime there is no parent package and the relative
# ``from .model import`` fails with ImportError. Bootstrap ``.claude/lib`` onto sys.path
# and fall back to the absolute import so the exact invocation documented below (and wired
# in .gitattributes / `make setup-ontology-merge-driver`, main#856) actually runs. The
# package-relative import is kept as the primary path for ``-m`` / in-package callers.
try:
    from .model import CodeGraph, Edge, Node, serialize_graph
except ImportError:  # pragma: no cover - exercised via the plain-script subprocess test
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ontology_gen.model import CodeGraph, Edge, Node, serialize_graph


def _load(path: str) -> tuple[list[Node], list[Edge]]:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return [], []
    nodes = [
        Node(
            id=str(n["id"]),
            kind=str(n["kind"]),
            path=str(n["path"]),
            line=int(n["line"]),
            lang=str(n["lang"]),
        )
        for n in data.get("nodes", [])
        if isinstance(n, dict) and "id" in n
    ]
    edges = [
        Edge(src=str(e["src"]), dst=str(e["dst"]), type=str(e["type"]))
        for e in data.get("edges", [])
        if isinstance(e, dict) and {"src", "dst", "type"} <= e.keys()
    ]
    return nodes, edges


def union_merge(ours_path: str, theirs_path: str, base_path: str | None = None) -> str:
    """Union the two (and optional base) graph files; return canonical merged JSON."""
    graph = CodeGraph()
    paths = [p for p in (base_path, ours_path, theirs_path) if p]
    for path in paths:
        nodes, edges = _load(path)
        graph.nodes.extend(nodes)
        graph.edges.extend(edges)
    # to_dict() dedups (nodes by id, edges by triple) and re-sorts canonically;
    # serialize_graph() is the same canonical text the generator writes, so a merge
    # result is byte-identical to a fresh regenerate.
    return serialize_graph(graph.to_dict())


def main(argv: list[str]) -> int:
    # git passes: %O (base) %A (ours/output) %B (theirs) [%P (pathname)]
    if len(argv) < 3:
        sys.stderr.write("usage: merge_driver.py <base %O> <ours %A> <theirs %B> [pathname %P]\n")
        return 2
    base, ours, theirs = argv[0], argv[1], argv[2]
    merged = union_merge(ours, theirs, base)
    with open(ours, "w", encoding="utf-8") as handle:
        handle.write(merged)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
