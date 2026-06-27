"""Tests for ontology_gen — the owned structural ontology generator (main#855).

Covers the output-contract model (determinism, dedup, graph integrity, canonical
serialization), each language extractor (Python ast / TypeScript / Cypher), the
cross-file assembler (import/inherit/call/reference resolution), the llms.txt renderer,
the git union merge-driver, and an end-to-end generate over a throwaway repo tree.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Package lives at .claude/lib/ontology_gen/; this test is at .claude/lib/tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ontology_gen import build_graph, discover, generate  # noqa: E402
from ontology_gen.assemble import assemble  # noqa: E402
from ontology_gen.cypher_ext import extract_cypher  # noqa: E402
from ontology_gen.llms import render_llms  # noqa: E402
from ontology_gen.merge_driver import union_merge  # noqa: E402
from ontology_gen.model import (  # noqa: E402
    CodeGraph,
    Edge,
    Node,
    iter_symbols,
    serialize_graph,
)
from ontology_gen.python_ext import extract_python  # noqa: E402
from ontology_gen.typescript_ext import (  # noqa: E402
    _parse_extends_bases,
    _split_top_level_commas,
    extract_typescript,
)


class TestModel(unittest.TestCase):
    def test_node_edge_to_dict_key_order(self) -> None:
        node = Node(id="a.py", kind="module", path="a.py", line=1, lang="python")
        self.assertEqual(list(node.to_dict().keys()), ["id", "kind", "path", "line", "lang"])
        edge = Edge(src="a", dst="b", type="contains")
        self.assertEqual(list(edge.to_dict().keys()), ["src", "dst", "type"])

    def test_to_dict_dedups_and_sorts(self) -> None:
        graph = CodeGraph()
        # Insert out of order + a duplicate node + a duplicate edge.
        graph.add_node(Node("b.py", "module", "b.py", 1, "python"))
        graph.add_node(Node("a.py", "module", "a.py", 1, "python"))
        graph.add_node(Node("a.py", "module", "a.py", 1, "python"))  # dup
        graph.add_edge(Edge("a.py", "b.py", "imports"))
        graph.add_edge(Edge("a.py", "b.py", "imports"))  # dup
        out = graph.to_dict()
        paths = [n["path"] for n in out["nodes"]]
        self.assertEqual(paths, ["a.py", "b.py"])  # sorted, deduped
        self.assertEqual(len(out["edges"]), 1)

    def test_dangling_edges_are_dropped(self) -> None:
        graph = CodeGraph()
        graph.add_node(Node("a.py", "module", "a.py", 1, "python"))
        graph.add_edge(Edge("a.py", "ghost.py", "imports"))  # dst not a node
        out = graph.to_dict()
        self.assertEqual(out["edges"], [])

    def test_serialize_is_valid_json_one_record_per_line(self) -> None:
        graph = CodeGraph()
        graph.add_node(Node("a.py", "module", "a.py", 1, "python"))
        graph.add_node(Node("b.py", "module", "b.py", 1, "python"))
        graph.add_edge(Edge("a.py", "b.py", "imports"))
        text = serialize_graph(graph.to_dict())
        # Round-trips as valid JSON.
        parsed = json.loads(text)
        self.assertEqual(len(parsed["nodes"]), 2)
        self.assertEqual(len(parsed["edges"]), 1)
        # One node per line: exactly two lines that start with {"id".
        node_lines = [ln for ln in text.splitlines() if ln.startswith('{"id"')]
        self.assertEqual(len(node_lines), 2)
        self.assertTrue(text.endswith("\n"))

    def test_serialize_empty_graph(self) -> None:
        text = serialize_graph(CodeGraph().to_dict())
        self.assertEqual(json.loads(text), {"nodes": [], "edges": []})


class TestPythonExtractor(unittest.TestCase):
    SRC = '''\
"""Module summary line.

More detail here.
"""
import os
import a.b.c
from sync_main import helper
from . import sibling
from .pkgmod import thing


def top_level(x, y, *args, **kwargs):
    return helper(x)


class Base:
    pass


class Child(Base):
    def method(self, z):
        return self.method(z)

    class Nested:
        def inner(self):
            pass
'''

    def setUp(self) -> None:
        self.info = extract_python("pkg/mod.py", self.SRC)

    def test_module_metadata(self) -> None:
        self.assertEqual(self.info.kind, "module")
        self.assertEqual(self.info.lang, "python")
        self.assertEqual(self.info.summary, "Module summary line.")

    def test_imports(self) -> None:
        kinds = {(i.kind, i.module) for i in self.info.imports}
        self.assertIn(("imports", "os"), kinds)
        self.assertIn(("imports", "a.b.c"), kinds)
        self.assertIn(("imports_from", "sync_main"), kinds)
        self.assertIn(("imports_from", "."), kinds)  # from . import sibling
        self.assertIn(("imports_from", ".pkgmod"), kinds)

    def test_symbols_and_nesting(self) -> None:
        names = {s.qualname: s.kind for s in iter_symbols(self.info.symbols)}
        self.assertEqual(names["top_level"], "func")
        self.assertEqual(names["Base"], "class")
        self.assertEqual(names["Child"], "class")
        self.assertEqual(names["Child.method"], "method")
        self.assertEqual(names["Child.Nested"], "class")
        self.assertEqual(names["Child.Nested.inner"], "method")

    def test_params_and_bases_and_calls(self) -> None:
        by_qual = {s.qualname: s for s in iter_symbols(self.info.symbols)}
        self.assertEqual(by_qual["top_level"].params, ["x", "y", "*args", "**kwargs"])
        self.assertEqual(by_qual["Child"].bases, ["Base"])
        self.assertIn("helper", by_qual["top_level"].calls)
        self.assertIn("method", by_qual["Child.method"].calls)

    def test_syntax_error_propagates(self) -> None:
        with self.assertRaises(SyntaxError):
            extract_python("bad.py", "def (:\n")


class TestTypeScriptExtractor(unittest.TestCase):
    SRC = """\
// Component module banner.
import React from 'react';
import { thing } from './util';
export { reexported } from './other';

export class Widget extends Base {
}

export function render(a, b) {
  return a;
}

export const Button = (props) => {
  return null;
};
"""

    def setUp(self) -> None:
        self.info = extract_typescript("src/widget.tsx", self.SRC)

    def test_file_metadata(self) -> None:
        self.assertEqual(self.info.kind, "file")
        self.assertEqual(self.info.lang, "typescript")
        self.assertEqual(self.info.summary, "Component module banner.")

    def test_imports_and_reexports(self) -> None:
        mods = {i.module for i in self.info.imports}
        self.assertIn("react", mods)
        self.assertIn("./util", mods)
        self.assertIn("./other", self.info.reexports)

    def test_symbols(self) -> None:
        by_name = {s.name: s for s in self.info.symbols}
        self.assertEqual(by_name["Widget"].kind, "class")
        self.assertEqual(by_name["Widget"].bases, ["Base"])
        self.assertEqual(by_name["render"].kind, "func")
        self.assertEqual(by_name["render"].params, ["a", "b"])
        self.assertEqual(by_name["Button"].kind, "func")
        self.assertEqual(by_name["Button"].params, ["props"])

    def test_js_extension_lang(self) -> None:
        info = extract_typescript("a/b.js", "export const x = () => 1;\n")
        self.assertEqual(info.lang, "javascript")


class TestTypeScriptInterfaceTypeExtractor(unittest.TestCase):
    """Tests for interface and type-alias extraction added in main#870."""

    INTERFACE_SRC = """\
// API types for narrator service.
import { Base } from './base';

export interface NarratorId {
  id: string;
  chain: number;
}

export interface NarratorRecord extends NarratorBase {
  fullName: string;
}

interface InternalHelper extends NarratorBase, Serializable {
  secret: boolean;
}
"""

    TYPE_SRC = """\
// Shared type aliases.
export type NarratorKind = 'transmitter' | 'collector';
export type Chain<T> = T[];
type MaybeNull<T> = T | null;
"""

    def test_interface_kind_emitted(self) -> None:
        info = extract_typescript("src/types.ts", self.INTERFACE_SRC)
        by_name = {s.name: s for s in info.symbols}
        self.assertIn("NarratorId", by_name)
        self.assertEqual(by_name["NarratorId"].kind, "interface")
        self.assertEqual(by_name["NarratorId"].bases, [])
        self.assertIn("NarratorRecord", by_name)
        self.assertEqual(by_name["NarratorRecord"].kind, "interface")
        self.assertEqual(by_name["NarratorRecord"].bases, ["NarratorBase"])
        self.assertIn("InternalHelper", by_name)
        self.assertEqual(by_name["InternalHelper"].kind, "interface")
        self.assertEqual(by_name["InternalHelper"].bases, ["NarratorBase", "Serializable"])

    def test_type_alias_kind_emitted(self) -> None:
        info = extract_typescript("src/aliases.ts", self.TYPE_SRC)
        by_name = {s.name: s for s in info.symbols}
        self.assertIn("NarratorKind", by_name)
        self.assertEqual(by_name["NarratorKind"].kind, "type")
        self.assertIn("Chain", by_name)
        self.assertEqual(by_name["Chain"].kind, "type")
        self.assertIn("MaybeNull", by_name)
        self.assertEqual(by_name["MaybeNull"].kind, "type")

    def test_interface_in_graph(self) -> None:
        """Interface symbols become nodes in the assembled graph."""
        info = extract_typescript("src/t.ts", self.INTERFACE_SRC)
        from ontology_gen.assemble import assemble

        graph = assemble([info])
        kinds = {n.kind for n in graph.nodes}
        self.assertIn("interface", kinds)

    def test_type_in_graph(self) -> None:
        """Type-alias symbols become nodes in the assembled graph."""
        info = extract_typescript("src/a.ts", self.TYPE_SRC)
        from ontology_gen.assemble import assemble

        graph = assemble([info])
        kinds = {n.kind for n in graph.nodes}
        self.assertIn("type", kinds)

    def test_interface_llms_rendering(self) -> None:
        info = extract_typescript("src/t.ts", self.INTERFACE_SRC)
        from ontology_gen.assemble import assemble
        from ontology_gen.llms import render_llms

        graph = assemble([info]).to_dict()
        text = render_llms([info], "demo", len(graph["nodes"]), len(graph["edges"]))
        self.assertIn("- interface NarratorId @", text)
        self.assertIn("- interface NarratorRecord(NarratorBase) @", text)
        self.assertIn("- interface InternalHelper(NarratorBase, Serializable) @", text)

    def test_type_llms_rendering(self) -> None:
        info = extract_typescript("src/a.ts", self.TYPE_SRC)
        from ontology_gen.assemble import assemble
        from ontology_gen.llms import render_llms

        graph = assemble([info]).to_dict()
        text = render_llms([info], "demo", len(graph["nodes"]), len(graph["edges"]))
        self.assertIn("- type NarratorKind @", text)
        self.assertIn("- type Chain @", text)

    def test_no_false_positive_type_in_non_decl_context(self) -> None:
        """``type`` keyword inside a function body / as a param name is not matched."""
        src = "function foo(type: string): void {\n  const type = 'x';\n}\n"
        info = extract_typescript("src/fn.ts", src)
        by_name = {s.name: s for s in info.symbols}
        # Only the function itself should appear, not a spurious 'type' symbol.
        self.assertNotIn("type", by_name)
        self.assertIn("foo", by_name)

    def test_no_regression_existing_kinds(self) -> None:
        """Python/class/func/method kinds are unaffected by #870."""
        py_info = extract_python("mod.py", "class Foo:\n    def bar(self):\n        pass\n")
        by_name = {s.qualname: s for s in iter_symbols(py_info.symbols)}
        self.assertEqual(by_name["Foo"].kind, "class")
        self.assertEqual(by_name["Foo.bar"].kind, "method")


class TestExtendsBaseSplitter(unittest.TestCase):
    """Depth-aware top-level-comma splitting of ``extends``/``implements`` lists (#887)."""

    def test_nested_generic_not_split(self) -> None:
        # The inner ``, `` of ``Map<K, V>`` must NOT be a split point.
        self.assertEqual(_parse_extends_bases("Bar<Map<K, V>>, Baz"), ["Bar", "Baz"])

    def test_two_generics_each_with_args(self) -> None:
        self.assertEqual(_parse_extends_bases("Foo<A, B>, Bar<C>"), ["Foo", "Bar"])

    def test_paren_and_bracket_nesting(self) -> None:
        # Commas inside ``()`` and ``[]`` are likewise depth-protected.
        self.assertEqual(
            _parse_extends_bases("Foo<[A, B]>, Bar<(C, D)>, Baz"),
            ["Foo", "Bar", "Baz"],
        )

    def test_deeply_nested_generic(self) -> None:
        self.assertEqual(
            _parse_extends_bases("A<B<C, D<E, F>>>, G"),
            ["A", "G"],
        )

    def test_plain_list_unchanged(self) -> None:
        self.assertEqual(_parse_extends_bases("Alpha, Beta, Gamma"), ["Alpha", "Beta", "Gamma"])

    def test_single_base(self) -> None:
        self.assertEqual(_parse_extends_bases("OnlyBase"), ["OnlyBase"])

    def test_empty_clause(self) -> None:
        self.assertEqual(_parse_extends_bases(""), [])
        self.assertEqual(_parse_extends_bases("   "), [])

    def test_splitter_keeps_nested_segment_intact(self) -> None:
        # The low-level splitter returns the whole nested segment as one part.
        self.assertEqual(
            _split_top_level_commas("Bar<Map<K, V>>, Baz"),
            ["Bar<Map<K, V>>", " Baz"],
        )

    def test_interface_with_nested_generic_base(self) -> None:
        # End-to-end through the extractor: a real interface declaration.
        src = "export interface Repo extends Bar<Map<K, V>>, Baz {\n  x: number;\n}\n"
        info = extract_typescript("src/repo.ts", src)
        by_name = {s.name: s for s in info.symbols}
        self.assertIn("Repo", by_name)
        self.assertEqual(by_name["Repo"].bases, ["Bar", "Baz"])


class TestCypherExtractor(unittest.TestCase):
    SRC = """\
// Narrator chain loader.
MATCH (n:Narrator)-[:TRANSMITTED_TO]->(m:Narrator:Scholar)
MERGE (h:Hadith {id: $id})
CREATE (n)-[r:NARRATED]->(h)
RETURN n;
"""

    def setUp(self) -> None:
        self.info = extract_cypher("queries/chain.cypher", self.SRC)

    def test_metadata(self) -> None:
        self.assertEqual(self.info.kind, "file")
        self.assertEqual(self.info.lang, "cypher")
        self.assertEqual(self.info.summary, "Narrator chain loader.")

    def test_labels_rels_clauses(self) -> None:
        self.assertEqual(self.info.extra["labels"], ["Hadith", "Narrator", "Scholar"])
        self.assertEqual(self.info.extra["relationships"], ["NARRATED", "TRANSMITTED_TO"])
        self.assertIn("MATCH", self.info.extra["clauses"])
        self.assertIn("MERGE", self.info.extra["clauses"])


class TestAssemble(unittest.TestCase):
    def test_contains_edges(self) -> None:
        info = extract_python("a.py", "def f():\n    pass\n")
        graph = assemble([info])
        out = graph.to_dict()
        edges = {(e["src"], e["dst"], e["type"]) for e in out["edges"]}
        self.assertIn(("a.py", "a.py::f", "contains"), edges)

    def test_python_import_resolution_by_stem(self) -> None:
        caller = extract_python("dir/caller.py", "from helper import x\n")
        helper = extract_python("other/helper.py", "x = 1\n")
        out = assemble([caller, helper]).to_dict()
        edges = {(e["src"], e["dst"], e["type"]) for e in out["edges"]}
        self.assertIn(("dir/caller.py", "other/helper.py", "imports_from"), edges)

    def test_python_import_resolution_by_dotted(self) -> None:
        caller = extract_python("caller.py", "import pkg.sub.mod\n")
        target = extract_python("pkg/sub/mod.py", "y = 2\n")
        out = assemble([caller, target]).to_dict()
        edges = {(e["src"], e["dst"], e["type"]) for e in out["edges"]}
        self.assertIn(("caller.py", "pkg/sub/mod.py", "imports"), edges)

    def test_python_relative_import_resolution(self) -> None:
        caller = extract_python("pkg/caller.py", "from .sibling import z\n")
        sibling = extract_python("pkg/sibling.py", "z = 3\n")
        out = assemble([caller, sibling]).to_dict()
        edges = {(e["src"], e["dst"], e["type"]) for e in out["edges"]}
        self.assertIn(("pkg/caller.py", "pkg/sibling.py", "imports_from"), edges)

    def test_ambiguous_stem_not_resolved(self) -> None:
        caller = extract_python("caller.py", "from dup import x\n")
        a = extract_python("one/dup.py", "x = 1\n")
        b = extract_python("two/dup.py", "x = 1\n")
        out = assemble([caller, a, b]).to_dict()
        edges = {(e["src"], e["dst"]) for e in out["edges"]}
        self.assertNotIn(("caller.py", "one/dup.py"), edges)
        self.assertNotIn(("caller.py", "two/dup.py"), edges)

    def test_inherits_and_calls_within_file(self) -> None:
        src = (
            "class Base:\n    pass\n\n"
            "class Child(Base):\n    pass\n\n"
            "def helper():\n    pass\n\n"
            "def caller():\n    return helper()\n"
        )
        out = assemble([extract_python("m.py", src)]).to_dict()
        edges = {(e["src"], e["dst"], e["type"]) for e in out["edges"]}
        self.assertIn(("m.py::Child", "m.py::Base", "inherits"), edges)
        self.assertIn(("m.py::caller", "m.py::helper", "calls"), edges)

    def test_ts_relative_import_and_reexport(self) -> None:
        a = extract_typescript("src/a.ts", "import { x } from './b';\nexport { y } from './c';\n")
        b = extract_typescript("src/b.ts", "export const x = 1;\n")
        c = extract_typescript("src/c.ts", "export const y = 2;\n")
        out = assemble([a, b, c]).to_dict()
        edges = {(e["src"], e["dst"], e["type"]) for e in out["edges"]}
        self.assertIn(("src/a.ts", "src/b.ts", "imports"), edges)
        self.assertIn(("src/a.ts", "src/c.ts", "references"), edges)


class TestLlms(unittest.TestCase):
    def test_render_has_header_and_sections(self) -> None:
        info = extract_python("a.py", '"""Doc."""\ndef f(x):\n    pass\n')
        graph = assemble([info]).to_dict()
        text = render_llms(
            [info],
            "demo",
            len(graph["nodes"]),
            len(graph["edges"]),
        )
        self.assertIn("# Structural ontology index — demo", text)
        self.assertIn("## a.py [python]", text)
        self.assertIn("- func f(x) @2", text)
        self.assertIn("langs=python:1", text)

    def test_cypher_section_renders_extras(self) -> None:
        info = extract_cypher("q.cypher", "MATCH (n:Narrator)-[:WROTE]->(h:Hadith) RETURN n;\n")
        text = render_llms([info], "demo", 1, 0)
        self.assertIn("labels: Hadith, Narrator", text)
        self.assertIn("rels: WROTE", text)


class TestMergeDriver(unittest.TestCase):
    def test_union_of_two_partial_graphs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            g1 = CodeGraph()
            g1.add_node(Node("a.py", "module", "a.py", 1, "python"))
            g2 = CodeGraph()
            g2.add_node(Node("b.py", "module", "b.py", 1, "python"))
            ours = root / "ours.json"
            theirs = root / "theirs.json"
            ours.write_text(serialize_graph(g1.to_dict()), encoding="utf-8")
            theirs.write_text(serialize_graph(g2.to_dict()), encoding="utf-8")
            merged = union_merge(str(ours), str(theirs))
            parsed = json.loads(merged)
            paths = sorted(n["path"] for n in parsed["nodes"])
            self.assertEqual(paths, ["a.py", "b.py"])

    def test_union_is_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            g = CodeGraph()
            g.add_node(Node("a.py", "module", "a.py", 1, "python"))
            g.add_node(Node("a.py::f", "func", "a.py", 2, "python"))
            g.add_edge(Edge("a.py", "a.py::f", "contains"))
            canonical = serialize_graph(g.to_dict())
            same = root / "same.json"
            same.write_text(canonical, encoding="utf-8")
            merged = union_merge(str(same), str(same), str(same))
            self.assertEqual(merged, canonical)

    def test_plain_script_invocation_merges(self) -> None:
        """Git invokes the driver as a PLAIN SCRIPT (not ``-m``); that path must work.

        Regression guard for main#856: the in-process ``union_merge`` import masked a
        relative-import failure on the actual git invocation form documented in
        .gitattributes (``python3 .claude/lib/ontology_gen/merge_driver.py %O %A %B %P``).
        This runs the script exactly as git would and asserts ``%A`` is union-merged.
        """
        import subprocess

        driver = Path(__file__).resolve().parent.parent / "ontology_gen" / "merge_driver.py"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            g1 = CodeGraph()
            g1.add_node(Node("a.py", "module", "a.py", 1, "python"))
            g2 = CodeGraph()
            g2.add_node(Node("b.py", "module", "b.py", 1, "python"))
            base = root / "base.json"
            ours = root / "ours.json"
            theirs = root / "theirs.json"
            base.write_text(serialize_graph(CodeGraph().to_dict()), encoding="utf-8")
            ours.write_text(serialize_graph(g1.to_dict()), encoding="utf-8")
            theirs.write_text(serialize_graph(g2.to_dict()), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(driver), str(base), str(ours), str(theirs), "code-graph.json"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            parsed = json.loads(ours.read_text(encoding="utf-8"))
            self.assertEqual(sorted(n["path"] for n in parsed["nodes"]), ["a.py", "b.py"])


class TestEndToEnd(unittest.TestCase):
    def _make_repo(self, root: Path) -> None:
        (root / "pkg").mkdir(parents=True)
        (root / "pkg" / "core.py").write_text(
            '"""Core module."""\n\n'
            "def run():\n    return helper()\n\n"
            "def helper():\n    return 1\n",
            encoding="utf-8",
        )
        (root / "pkg" / "app.py").write_text(
            "from core import run\n\nclass App:\n    def start(self):\n        return run()\n",
            encoding="utf-8",
        )
        (root / "web.tsx").write_text(
            "import { App } from './pkg/app';\nexport const Page = () => null;\n",
            encoding="utf-8",
        )
        (root / "q.cypher").write_text("MATCH (n:Narrator) RETURN n;\n", encoding="utf-8")

    def test_discover_and_generate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_repo(root)
            found = discover(root)
            self.assertIn("pkg/core.py", found)
            self.assertIn("web.tsx", found)
            self.assertIn("q.cypher", found)

            out_dir = root / "ontology" / "structural"
            counts = generate(root, out_dir, "demo")
            self.assertEqual(counts["files"], 4)
            self.assertGreater(counts["nodes"], 4)

            graph = json.loads((out_dir / "code-graph.json").read_text())
            kinds = {n["kind"] for n in graph["nodes"]}
            self.assertEqual(kinds, {"file", "module", "class", "func", "method"})
            langs = {n["lang"] for n in graph["nodes"]}
            self.assertEqual(langs, {"python", "typescript", "cypher"})

            llms = (out_dir / "llms.txt").read_text()
            self.assertIn("## pkg/core.py [python]", llms)
            self.assertIn("## q.cypher [cypher]", llms)

    def test_generate_is_deterministic(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_repo(root)
            out1 = root / "o1"
            out2 = root / "o2"
            generate(root, out1, "demo")
            generate(root, out2, "demo")
            self.assertEqual(
                (out1 / "code-graph.json").read_text(),
                (out2 / "code-graph.json").read_text(),
            )
            self.assertEqual((out1 / "llms.txt").read_text(), (out2 / "llms.txt").read_text())

    def test_unparseable_python_degrades_to_module_node(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "broken.py").write_text("def (:\n", encoding="utf-8")
            graph, files = build_graph(root)
            ids = {n.id for n in graph.nodes}
            self.assertIn("broken.py", ids)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
