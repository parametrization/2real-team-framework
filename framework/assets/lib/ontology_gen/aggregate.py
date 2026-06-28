#!/usr/bin/env python3
"""Cross-repo structural ontology aggregator.

For a **meta + children** project (a parent git repo whose immediate subdirectories are
themselves git repos), each repo generates its own ``ontology/structural/code-graph.json``
(via :mod:`ontology_gen`). This module rolls those per-repo indices up into a single
**cross-repo view**:

* **union** of every in-scope repo's nodes and edges,
* **namespaced by repo** so ids never collide across repos — every node id / path and
  every edge endpoint is prefixed ``<repo>/`` (e.g. ``api/src/app.py`` and
  ``api/src/app.py::create_app``). The repo name becomes a virtual top-level directory,
  so the same relative path in two repos yields two distinct nodes.

It is **offline and deterministic** — no DB, no LLM, no network. It reads whatever in-scope
repo indices are present on disk and **degrades gracefully** when one is absent (a repo whose
index has not been generated/committed yet is simply skipped and reported). Output is the same
``{"nodes": [...], "edges": [...]}`` document shape as a per-repo index, serialized through the
canonical :func:`~ontology_gen.model.serialize_graph` (one record per line) so it is
record-granular-diffable and union-mergeable by the same merge-driver.

The in-scope repo set is **discovered** from the parent root by default (the parent itself,
keyed by its directory name with subdir ``.``, plus every immediate subdirectory that is a git
repo). Override explicitly with repeatable ``--repo NAME=SUBDIR``.

CLI: ``python3 -m ontology_gen.aggregate <root> --out <central-graph.json>``
(default out: ``ontology/structural/cross-repo-graph.json``).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .model import CodeGraph, Edge, GraphDict, Node, serialize_graph

# Where each repo's generated per-repo index lives (relative to that repo's root).
INDEX_RELPATH = "ontology/structural/code-graph.json"
# Default central artifact path (relative to the parent root).
DEFAULT_OUT = "ontology/structural/cross-repo-graph.json"


def discover_repos(root: Path) -> dict[str, str]:
    """Discover the in-scope repo set for a meta+children layout.

    Returns ``{namespace: subdir}`` mapping repo-relative-to-``root``. The parent root
    itself is included (keyed by its directory name, subdir ``.``) so its own index rolls
    in alongside the children. Each immediate subdirectory that is itself a git repo (has a
    ``.git`` entry — dir for a clone, file for a worktree/submodule) is included, keyed by
    its directory name. Deterministic: subdirs are scanned in sorted order.

    A single-repo project (no child git-repos) yields just ``{root.name: "."}``.
    """
    repos: dict[str, str] = {root.name: "."}
    try:
        children = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        children = []
    for child in children:
        if child.name == ".git":
            continue
        if (child / ".git").exists():
            repos[child.name] = child.name
    return repos


@dataclass(frozen=True)
class RepoIndexStatus:
    """Per-repo aggregation outcome — whether its index was found and what it contributed.

    ``nodes``/``edges`` are this repo's pre-dedup contribution (post-namespacing); the
    aggregated totals after cross-repo dedup come from the assembled graph, not the sum of
    these (a per-repo index never shares ids with another once namespaced, so in practice
    the totals equal the sums — but the graph remains the source of truth).
    """

    name: str
    index_path: Path
    present: bool
    nodes: int
    edges: int


def _load_namespaced(name: str, path: Path) -> tuple[list[Node], list[Edge]] | None:
    """Load one repo's index and namespace every id by ``<name>/``.

    Returns ``None`` when the index is absent or unreadable (the caller degrades
    gracefully); returns ``([], [])`` for a present-but-empty index. Malformed records are
    skipped individually rather than aborting the whole roll-up.
    """
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    raw_nodes = data.get("nodes", [])
    raw_edges = data.get("edges", [])
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        return None

    prefix = f"{name}/"
    nodes = [
        Node(
            id=prefix + str(n["id"]),
            kind=str(n["kind"]),
            path=prefix + str(n["path"]),
            line=int(n["line"]),
            lang=str(n["lang"]),
        )
        for n in raw_nodes
        if isinstance(n, dict) and {"id", "kind", "path", "line", "lang"} <= n.keys()
    ]
    edges = [
        Edge(src=prefix + str(e["src"]), dst=prefix + str(e["dst"]), type=str(e["type"]))
        for e in raw_edges
        if isinstance(e, dict) and {"src", "dst", "type"} <= e.keys()
    ]
    return nodes, edges


def aggregate(
    root: Path,
    repos: dict[str, str] | None = None,
    index_relpath: str = INDEX_RELPATH,
) -> tuple[GraphDict, list[RepoIndexStatus]]:
    """Union every in-scope repo's structural index into one namespaced cross-repo graph.

    ``repos`` maps namespace -> repo subdir (relative to ``root``); defaults to
    :func:`discover_repos`. Returns the canonical (deduped, sorted) graph dict and a status
    per repo (sorted by name for deterministic reporting).
    """
    repo_map = repos if repos is not None else discover_repos(root)
    graph = CodeGraph()
    statuses: list[RepoIndexStatus] = []
    for name in sorted(repo_map):
        index_path = (root / repo_map[name] / index_relpath).resolve()
        loaded = _load_namespaced(name, index_path)
        if loaded is None:
            statuses.append(RepoIndexStatus(name, index_path, False, 0, 0))
            continue
        nodes, edges = loaded
        graph.nodes.extend(nodes)
        graph.edges.extend(edges)
        statuses.append(RepoIndexStatus(name, index_path, True, len(nodes), len(edges)))
    return graph.to_dict(), statuses


def write_aggregate(
    root: Path,
    out_path: Path,
    repos: dict[str, str] | None = None,
    index_relpath: str = INDEX_RELPATH,
) -> tuple[int, int, list[RepoIndexStatus]]:
    """Aggregate and write the central artifact. Returns ``(nodes, edges, statuses)``."""
    graph_dict, statuses = aggregate(root, repos, index_relpath)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(serialize_graph(graph_dict), encoding="utf-8")
    return len(graph_dict["nodes"]), len(graph_dict["edges"]), statuses


def _parse_repo_overrides(values: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"error: --repo expects NAME=SUBDIR, got: {value!r}")
        name, _, subdir = value.partition("=")
        if not name or not subdir:
            raise SystemExit(f"error: --repo expects NAME=SUBDIR, got: {value!r}")
        overrides[name] = subdir
    return overrides


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m ontology_gen.aggregate",
        description=(
            "Roll each in-scope repo's structural index (ontology/structural/code-graph.json) "
            "into a central, namespaced cross-repo graph at the parent root."
        ),
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Path to the parent (meta) repo root (default: current directory).",
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=f"Output path for the cross-repo graph (default: {DEFAULT_OUT}).",
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=[],
        metavar="NAME=SUBDIR",
        help=(
            "Override the in-scope repo set with an explicit NAME=SUBDIR entry "
            "(repeatable). When given, replaces the discovered repo map entirely."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        sys.stderr.write(f"error: root is not a directory: {root}\n")
        return 2

    repos = _parse_repo_overrides(args.repo) if args.repo else None
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = root / out_path

    nodes, edges, statuses = write_aggregate(root, out_path, repos)

    present = [s for s in statuses if s.present]
    absent = [s for s in statuses if not s.present]
    sys.stderr.write(
        f"ontology_gen.aggregate: {out_path} "
        f"(repos={len(present)}/{len(statuses)} nodes={nodes} edges={edges})\n"
    )
    for status in present:
        sys.stderr.write(f"  + {status.name}: nodes={status.nodes} edges={status.edges}\n")
    for status in absent:
        sys.stderr.write(f"  - {status.name}: index absent ({status.index_path}) — skipped\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
