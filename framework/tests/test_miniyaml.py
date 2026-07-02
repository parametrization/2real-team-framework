"""Unit tests for the stdlib-only YAML-subset parser (framework/install/miniyaml.py)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "install"))

import miniyaml  # noqa: E402


# ---------------------------------------------------------------- scalars


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a: 1", {"a": 1}),
        ("a: -7", {"a": -7}),
        ("a: 3.5", {"a": 3.5}),
        ("a: true", {"a": True}),
        ("a: True", {"a": True}),
        ("a: false", {"a": False}),
        ("a: FALSE", {"a": False}),
        ("a: null", {"a": None}),
        ("a: ~", {"a": None}),
        ("a:", {"a": None}),
        ("a: hello world", {"a": "hello world"}),
        ("a: 'quoted: string'", {"a": "quoted: string"}),
        ('a: "with # hash"', {"a": "with # hash"}),
        ('a: "esc\\nline"', {"a": "esc\nline"}),
        ("a: 'it''s'", {"a": "it's"}),
        ("a: github-actions", {"a": "github-actions"}),
        ("a: v1.2.3", {"a": "v1.2.3"}),
    ],
)
def test_scalars(text: str, expected: dict) -> None:
    assert miniyaml.loads(text) == expected


def test_empty_document_is_none() -> None:
    assert miniyaml.loads("") is None
    assert miniyaml.loads("\n# only a comment\n") is None


# ---------------------------------------------------------------- structure


def test_nested_maps() -> None:
    text = """
scm:
  provider: github
  owner: my-org
pre_push:
  mode: noop
"""
    assert miniyaml.loads(text) == {
        "scm": {"provider": "github", "owner": "my-org"},
        "pre_push": {"mode": "noop"},
    }


def test_deeply_nested_maps() -> None:
    text = "a:\n  b:\n    c:\n      d: 1\n"
    assert miniyaml.loads(text) == {"a": {"b": {"c": {"d": 1}}}}


def test_list_of_scalars() -> None:
    text = "skills:\n  - retro\n  - wave-start\n  - 3\n"
    assert miniyaml.loads(text) == {"skills": ["retro", "wave-start", 3]}


def test_list_at_same_indent_as_key() -> None:
    text = "skills:\n- retro\n- wave-start\nafter: yes-more\n"
    assert miniyaml.loads(text) == {"skills": ["retro", "wave-start"], "after": "yes-more"}


def test_list_of_maps_children_shape() -> None:
    text = """
children:
  - path: services/api
    flavor: product
  - path: infra/terraform
    flavor: infra
"""
    assert miniyaml.loads(text) == {
        "children": [
            {"path": "services/api", "flavor": "product"},
            {"path": "infra/terraform", "flavor": "infra"},
        ]
    }


def test_flow_collections() -> None:
    text = "empty: []\nemptymap: {}\nnums: [1, 2, 3]\nchild: {path: a/b, flavor: infra}\n"
    assert miniyaml.loads(text) == {
        "empty": [],
        "emptymap": {},
        "nums": [1, 2, 3],
        "child": {"path": "a/b", "flavor": "infra"},
    }


def test_list_of_flow_maps() -> None:
    text = "children:\n  - {path: a, flavor: product}\n  - {path: b}\n"
    assert miniyaml.loads(text) == {
        "children": [{"path": "a", "flavor": "product"}, {"path": "b"}]
    }


def test_top_level_sequence() -> None:
    assert miniyaml.loads("- a\n- b\n") == ["a", "b"]


def test_document_start_marker_ignored() -> None:
    assert miniyaml.loads("---\na: 1\n") == {"a": 1}


# ---------------------------------------------------------------- comments


def test_comments_full_line_and_trailing() -> None:
    text = """
# a full-line comment
a: 1   # trailing comment
b: "kept # inside quotes"
  # indented comment
c: 3
"""
    assert miniyaml.loads(text) == {"a": 1, "b": "kept # inside quotes", "c": 3}


def test_hash_without_leading_space_is_not_a_comment() -> None:
    assert miniyaml.loads("a: foo#bar") == {"a": "foo#bar"}


# ---------------------------------------------------------------- errors


@pytest.mark.parametrize(
    "text",
    [
        "a: &anchor 1",
        "a: *alias",
        "a: |\n  block",
        "a: >\n  folded",
        "a: !!str tagged",
        "\ta: 1",
        "a: 'unterminated",
        'a: "bad \\q escape"',
        "a: [1, 2",
        "a: {k: v",
        "a: 1\na: 2",
        "just a plain line",
        "a: 1\n--- \nb: 2",
    ],
)
def test_unsupported_or_malformed_raises(text: str) -> None:
    with pytest.raises(miniyaml.MiniYamlError):
        miniyaml.loads(text)


def test_error_carries_line_number() -> None:
    with pytest.raises(miniyaml.MiniYamlError) as exc_info:
        miniyaml.loads("a: 1\nb: &x 2\n")
    assert exc_info.value.line == 2
    assert "line 2" in str(exc_info.value)


def test_bad_indentation_raises() -> None:
    with pytest.raises(miniyaml.MiniYamlError):
        miniyaml.loads("a:\n  b: 1\n c: 2\n")


# ---------------------------------------------------------------- shipped file


def test_shipped_default_config_parses() -> None:
    cfg = miniyaml.load(_FRAMEWORK_ROOT / "config" / "install.config.default.yaml")
    assert cfg["version"] == 1
    assert cfg["repo"]["expect"] == "fresh"
    assert cfg["project"]["model"] == "standalone"
    assert cfg["project"]["name"] is None
    assert cfg["scm"] == {"provider": "github", "owner": None}
    assert cfg["ci"]["provider"] == "github-actions"
    assert cfg["ticketing"]["provider"] == "github-issues"
    assert cfg["pre_push"]["mode"] == "noop"
    assert cfg["ontology"]["enabled"] is True
    assert cfg["team"] == {"enabled": True, "preset": None, "size": None}
    assert cfg["children"] == []


def test_shipped_default_matches_pyyaml_if_available() -> None:
    yaml = pytest.importorskip("yaml")
    path = _FRAMEWORK_ROOT / "config" / "install.config.default.yaml"
    assert miniyaml.load(path) == yaml.safe_load(path.read_text(encoding="utf-8"))
