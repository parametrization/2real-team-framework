"""Tests for the ontology subsystem: structural generator + cross-repo aggregator +
the ontology_tracker change-tracker hook. Stdlib + pytest only; no network.

The generator/aggregator are exercised on tiny tmp git trees. The tracker hook is
exercised via check() with a tmp repo carrying a .claude/framework.config.json so config
resolution (root = config-file parent's parent, paths.ontology) works.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "lib"))
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))

from ontology_gen.aggregate import aggregate, discover_repos  # noqa: E402
from ontology_gen.generate import generate  # noqa: E402


def _git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)


# --------------------------------------------------------------- generator


def test_generate_emits_artifacts_and_counts(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "a.py").write_text("import b\n\n\nclass Foo:\n    def bar(self):\n        return 1\n")
    (tmp_path / "b.py").write_text("def helper():\n    return 2\n")

    counts = generate(tmp_path, tmp_path / "ontology" / "structural", "demo")

    assert counts["files"] == 2
    assert counts["nodes"] >= 4  # 2 modules + Foo + bar (+ helper)
    structural = tmp_path / "ontology" / "structural"
    assert (structural / "code-graph.json").is_file()
    llms = (structural / "llms.txt").read_text()
    assert "# Structural ontology index — demo" in llms
    assert "## a.py [python]" in llms
    # genericised header — no product/issue refs leaked through
    assert "noorinalabs" not in llms and "#855" not in llms


def test_generate_import_edge_resolves(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "a.py").write_text("import b\n")
    (tmp_path / "b.py").write_text("x = 1\n")
    generate(tmp_path, tmp_path / "out", "demo")
    doc = json.loads((tmp_path / "out" / "code-graph.json").read_text())
    edges = {(e["src"], e["dst"], e["type"]) for e in doc["edges"]}
    assert ("a.py", "b.py", "imports") in edges


# --------------------------------------------------------------- aggregator


def test_discover_repos_finds_children(tmp_path: Path) -> None:
    _git_init(tmp_path)
    child = tmp_path / "svc-api"
    child.mkdir()
    _git_init(child)
    (tmp_path / "not-a-repo").mkdir()
    repos = discover_repos(tmp_path)
    assert repos[tmp_path.name] == "."
    assert repos["svc-api"] == "svc-api"
    assert "not-a-repo" not in repos


def test_aggregate_namespaces_and_skips_absent(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "root.py").write_text("def r():\n    return 0\n")
    generate(tmp_path, tmp_path / "ontology" / "structural", tmp_path.name)

    child = tmp_path / "svc-api"
    child.mkdir()
    _git_init(child)
    (child / "app.py").write_text("def create_app():\n    return {}\n")
    generate(child, child / "ontology" / "structural", "svc-api")

    # A discovered child with no generated index → skipped gracefully.
    absent = tmp_path / "svc-worker"
    absent.mkdir()
    _git_init(absent)

    graph, statuses = aggregate(tmp_path)
    ids = {n["id"] for n in graph["nodes"]}
    assert "svc-api/app.py" in ids
    assert "svc-api/app.py::create_app" in ids
    assert any(n.startswith(f"{tmp_path.name}/") for n in ids)

    by_name = {s.name: s for s in statuses}
    assert by_name["svc-api"].present is True
    assert by_name["svc-worker"].present is False  # discovered but no index


# --------------------------------------------------------------- tracker hook


def _repo_with_config(tmp_path: Path, *, with_ontology: bool) -> Path:
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    (claude / "framework.config.json").write_text(json.dumps({"version": 1}))
    if with_ontology:
        (tmp_path / "ontology").mkdir()
    return tmp_path


def _edit(file_path: Path, cwd: Path) -> dict:
    return {"tool_name": "Edit", "tool_input": {"file_path": str(file_path)}, "cwd": str(cwd)}


def test_tracker_inert_without_ontology(tmp_path: Path) -> None:
    import ontology_tracker as ot

    root = _repo_with_config(tmp_path, with_ontology=False)
    target = root / "src.py"
    target.write_text("x = 1\n")
    assert ot.check(_edit(target, root)) is None
    assert not (root / "ontology" / "checksums.json").exists()


def test_tracker_records_overlay_edit(tmp_path: Path) -> None:
    import ontology_tracker as ot

    root = _repo_with_config(tmp_path, with_ontology=True)
    overlay = root / "ontology" / "domain.yaml"
    overlay.write_text("entities: []\n")
    result = ot.check(_edit(overlay, root))
    assert result == {"action": "tracked", "path": "ontology/domain.yaml"}

    ck = json.loads((root / "ontology" / "checksums.json").read_text())
    entry = ck["files"]["ontology/domain.yaml"]
    assert entry["last_tracked"] and entry["last_resolved"] == ""  # dirty


def test_tracker_skips_structural_and_checksums(tmp_path: Path) -> None:
    import ontology_tracker as ot

    root = _repo_with_config(tmp_path, with_ontology=True)
    (root / "ontology" / "structural").mkdir()
    struct = root / "ontology" / "structural" / "llms.txt"
    struct.write_text("# generated\n")
    assert ot.check(_edit(struct, root)) is None

    ck = root / "ontology" / "checksums.json"
    ck.write_text(json.dumps({"version": 1, "files": {}}))
    assert ot.check(_edit(ck, root)) is None


def test_tracker_skips_worktree_and_wrong_tool(tmp_path: Path) -> None:
    import ontology_tracker as ot

    root = _repo_with_config(tmp_path, with_ontology=True)
    wt = root / ".worktrees" / "x"
    wt.mkdir(parents=True)
    f = wt / "ontology_like.yaml"
    f.write_text("a: 1\n")
    assert ot.check(_edit(f, root)) is None

    overlay = root / "ontology" / "x.yaml"
    overlay.write_text("a: 1\n")
    bash = {"tool_name": "Bash", "tool_input": {"command": "echo hi"}, "cwd": str(root)}
    assert ot.check(bash) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
