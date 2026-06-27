"""Tests for ontology_gen.aggregate — the cross-repo structural aggregator (main#856).

Covers repo-namespacing, cross-repo id-collision avoidance, graceful degradation when a
repo index is absent, determinism, edge preservation, and the CLI entry point. Fixtures
build small per-repo ``code-graph.json`` files in a temp tree mimicking the parent/child
repo layout (``<root>/ontology/structural/`` for main, ``<root>/<child>/ontology/
structural/`` for children).
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Package lives at .claude/lib/ontology_gen/; this test is at .claude/lib/tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ontology_gen.aggregate import (  # noqa: E402
    DEFAULT_REPOS,
    INDEX_RELPATH,
    aggregate,
    main,
    write_aggregate,
)
from ontology_gen.model import CodeGraph, Edge, Node, serialize_graph  # noqa: E402


def _write_index(repo_root: Path, graph: CodeGraph) -> Path:
    """Write ``graph`` as a per-repo code-graph.json under ``repo_root`` and return it."""
    out = repo_root / INDEX_RELPATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(serialize_graph(graph.to_dict()), encoding="utf-8")
    return out


def _graph_with(path: str, lang: str = "python") -> CodeGraph:
    """A minimal graph: one module + one contained func with a contains edge."""
    graph = CodeGraph()
    graph.add_node(Node(path, "module", path, 1, lang))
    graph.add_node(Node(f"{path}::f", "func", path, 2, lang))
    graph.add_edge(Edge(path, f"{path}::f", "contains"))
    return graph


class TestNamespacing(unittest.TestCase):
    def test_ids_and_paths_are_repo_prefixed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_index(root, _graph_with("app.py"))
            graph_dict, statuses = aggregate(root, {"main": "."})

            ids = {n["id"] for n in graph_dict["nodes"]}
            paths = {n["path"] for n in graph_dict["nodes"]}
            self.assertEqual(ids, {"main/app.py", "main/app.py::f"})
            self.assertEqual(paths, {"main/app.py"})
            # Edge endpoints namespaced too, edge preserved.
            self.assertEqual(
                {(e["src"], e["dst"], e["type"]) for e in graph_dict["edges"]},
                {("main/app.py", "main/app.py::f", "contains")},
            )
            self.assertEqual([s.name for s in statuses], ["main"])
            self.assertTrue(statuses[0].present)

    def test_no_collision_across_repos_same_relpath(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_index(root, _graph_with("app.py"))
            _write_index(root / "noorinalabs-isnad-graph", _graph_with("app.py"))
            graph_dict, _ = aggregate(root, {"main": ".", "isnad-graph": "noorinalabs-isnad-graph"})
            ids = {n["id"] for n in graph_dict["nodes"]}
            # Identical relpath in two repos -> two distinct namespaced nodes.
            self.assertIn("main/app.py", ids)
            self.assertIn("isnad-graph/app.py", ids)
            self.assertEqual(len(graph_dict["nodes"]), 4)
            self.assertEqual(len(graph_dict["edges"]), 2)


class TestGracefulDegradation(unittest.TestCase):
    def test_absent_repo_is_skipped_not_fatal(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_index(root, _graph_with("app.py"))
            # isnad-graph has no index on disk.
            graph_dict, statuses = aggregate(
                root, {"main": ".", "isnad-graph": "noorinalabs-isnad-graph"}
            )
            by_name = {s.name: s for s in statuses}
            self.assertTrue(by_name["main"].present)
            self.assertFalse(by_name["isnad-graph"].present)
            # Present repo's nodes still aggregated.
            self.assertEqual(
                {n["id"] for n in graph_dict["nodes"]}, {"main/app.py", "main/app.py::f"}
            )

    def test_all_absent_yields_empty_graph(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph_dict, statuses = aggregate(root, {"main": ".", "isnad-graph": "x"})
            self.assertEqual(graph_dict, {"nodes": [], "edges": []})
            self.assertTrue(all(not s.present for s in statuses))

    def test_malformed_index_degrades(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = root / INDEX_RELPATH
            bad.parent.mkdir(parents=True, exist_ok=True)
            bad.write_text("{ not json", encoding="utf-8")
            graph_dict, statuses = aggregate(root, {"main": "."})
            self.assertEqual(graph_dict, {"nodes": [], "edges": []})
            self.assertFalse(statuses[0].present)


class TestDeterminism(unittest.TestCase):
    def test_aggregate_is_deterministic_and_canonical(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_index(root, _graph_with("b.py"))
            _write_index(root / "noorinalabs-user-service", _graph_with("a.py"))
            repos = {"main": ".", "user-service": "noorinalabs-user-service"}
            d1, _ = aggregate(root, repos)
            d2, _ = aggregate(root, repos)
            self.assertEqual(serialize_graph(d1), serialize_graph(d2))
            # Canonical sort by path: user-service/a.py sorts before main/b.py.
            paths = [n["path"] for n in d1["nodes"]]
            self.assertEqual(paths, sorted(paths))


class TestCli(unittest.TestCase):
    def test_main_writes_central_artifact(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_index(root, _graph_with("app.py"))
            out = root / "ontology" / "structural" / "cross-repo-graph.json"
            rc = main([str(root), "--out", str(out), "--repo", "main=."])
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            parsed = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual({n["id"] for n in parsed["nodes"]}, {"main/app.py", "main/app.py::f"})

    def test_write_aggregate_returns_counts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_index(root, _graph_with("app.py"))
            out = root / "cross.json"
            nodes, edges, statuses = write_aggregate(root, out, {"main": "."})
            self.assertEqual(nodes, 2)
            self.assertEqual(edges, 1)
            self.assertEqual(len(statuses), 1)

    def test_bad_repo_override_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                main([tmp, "--repo", "noequalsign"])


class TestDefaultRepos(unittest.TestCase):
    def test_default_map_covers_main_and_seven_children(self) -> None:
        self.assertEqual(DEFAULT_REPOS["main"], ".")
        # main + 7 child repos (CLAUDE.md § Repository Map).
        self.assertEqual(len(DEFAULT_REPOS), 8)
        for child in ("isnad-graph", "user-service", "deploy", "design-system"):
            self.assertTrue(DEFAULT_REPOS[child].startswith("noorinalabs-"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
