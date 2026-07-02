"""Minimal stdlib-only YAML-subset parser for install-time configuration.

``framework/install`` must stay stdlib-only (it runs anywhere ``python3`` does,
before any dependency is installed), so this module implements just enough of
YAML to read ``install.config.yaml`` files:

Supported
=========
- nested mappings (indentation-based)
- block sequences (``- item``), including sequences of mappings
  (``- path: x`` + continuation lines) and sequences at the same indent
  as their parent key
- flow sequences/mappings on one line: ``[a, b]``, ``{path: x, flavor: y}``,
  ``[]``, ``{}``
- scalars: booleans (``true/false``, YAML 1.2 core casings), null
  (``null``/``~``/empty), integers, floats, single/double-quoted strings,
  plain strings
- comments: full-line and trailing (`` # ...``), quote-aware
- a leading ``---`` document-start marker

Deliberately NOT supported (raises :class:`MiniYamlError` with a line number):
anchors/aliases (``&``, ``*``), block scalars (``|``, ``>``), multi-document
streams, tags (``!``), tabs in indentation, multi-line flow collections.

The module is self-contained (no sibling imports) so it can also be copied
verbatim as an asset if a later issue needs it at runtime.

API: :func:`loads`, :func:`load`, :class:`MiniYamlError`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

__all__ = ["MiniYamlError", "load", "loads"]


class MiniYamlError(ValueError):
    """Parse error carrying a 1-based source line number."""

    def __init__(self, message: str, line: int | None = None) -> None:
        self.line = line
        super().__init__(f"line {line}: {message}" if line is not None else message)


_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
_BOOL_TRUE = frozenset({"true", "True", "TRUE"})
_BOOL_FALSE = frozenset({"false", "False", "FALSE"})
_NULLS = frozenset({"null", "Null", "NULL", "~"})
_DQ_ESCAPES = {"\\": "\\", '"': '"', "n": "\n", "t": "\t", "r": "\r", "0": "\0"}


def load(path: str | Path) -> Any:
    """Parse the YAML-subset file at ``path``."""
    return loads(Path(path).read_text(encoding="utf-8"))


def loads(text: str) -> Any:
    """Parse a YAML-subset document from a string. Empty document -> None."""
    lines = _prepare(text)
    if not lines:
        return None
    value, idx = _parse_block(lines, 0, lines[0][1])
    if idx != len(lines):
        raise MiniYamlError("unexpected content (bad indentation?)", lines[idx][0])
    return value


# ---------------------------------------------------------------- line prep


def _prepare(text: str) -> list[list]:
    """Return significant lines as mutable ``[lineno, indent, content]`` triples."""
    out: list[list] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        body = _strip_comment(raw.rstrip(), lineno)
        if not body.strip():
            continue
        indent = len(body) - len(body.lstrip(" "))
        if "\t" in body[:indent] or body.lstrip(" ").startswith("\t"):
            raise MiniYamlError("tabs are not allowed in indentation", lineno)
        content = body.strip()
        if not out and content == "---":
            continue  # document-start marker
        if content in ("---", "..."):
            raise MiniYamlError("multi-document streams are not supported", lineno)
        out.append([lineno, indent, content])
    return out


def _strip_comment(line: str, lineno: int) -> str:
    """Remove a trailing `` # comment`` (quote-aware). Full-line comments -> ''."""
    in_single = in_double = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_single:
            if ch == "'":
                if i + 1 < len(line) and line[i + 1] == "'":
                    i += 1  # escaped '' inside single quotes
                else:
                    in_single = False
        elif in_double:
            if ch == "\\":
                i += 1
            elif ch == '"':
                in_double = False
        elif ch == "'":
            in_single = True
        elif ch == '"':
            in_double = True
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
        i += 1
    if in_single or in_double:
        raise MiniYamlError("unterminated quoted string", lineno)
    return line


# ---------------------------------------------------------------- block parse


def _is_seq_item(content: str) -> bool:
    return content == "-" or content.startswith("- ")


def _parse_block(lines: list[list], i: int, indent: int) -> tuple[Any, int]:
    lineno, ind, content = lines[i]
    if ind != indent:
        raise MiniYamlError("unexpected indentation", lineno)
    if _is_seq_item(content):
        return _parse_sequence(lines, i, indent)
    return _parse_mapping(lines, i, indent)


def _parse_sequence(lines: list[list], i: int, indent: int) -> tuple[list, int]:
    items: list[Any] = []
    while i < len(lines):
        lineno, ind, content = lines[i]
        if ind != indent or not _is_seq_item(content):
            break
        rest = content[1:].lstrip()
        if not rest:
            # A bare `-`: the item is the following deeper block (or null).
            if i + 1 < len(lines) and lines[i + 1][1] > indent:
                value, i = _parse_block(lines, i + 1, lines[i + 1][1])
                items.append(value)
            else:
                items.append(None)
                i += 1
            continue
        rest_col = ind + (len(content) - len(rest))
        if rest[0] in "[{":
            # Flow collection item: `- {path: x}` / `- [a, b]`.
            items.append(_parse_scalar(rest, lineno))
            i += 1
        elif _looks_like_mapping_entry(rest) or _is_seq_item(rest):
            # Compact form: `- key: value` (or `- - x`). Reparse the remainder
            # as a block starting at the column where it begins.
            lines[i] = [lineno, rest_col, rest]
            value, i = _parse_block(lines, i, rest_col)
            items.append(value)
        else:
            items.append(_parse_scalar(rest, lineno))
            i += 1
    return items, i


def _parse_mapping(lines: list[list], i: int, indent: int) -> tuple[dict, int]:
    out: dict[str, Any] = {}
    while i < len(lines):
        lineno, ind, content = lines[i]
        if ind != indent or _is_seq_item(content):
            break
        key, rest = _split_key(content, lineno)
        if key in out:
            raise MiniYamlError(f"duplicate key {key!r}", lineno)
        if rest:
            out[key] = _parse_scalar(rest, lineno)
            i += 1
            continue
        i += 1
        if i < len(lines) and lines[i][1] > indent:
            out[key], i = _parse_block(lines, i, lines[i][1])
        elif i < len(lines) and lines[i][1] == indent and _is_seq_item(lines[i][2]):
            # Sequence at the same indent as its key (common YAML style).
            out[key], i = _parse_sequence(lines, i, indent)
        else:
            out[key] = None
    return out, i


def _looks_like_mapping_entry(s: str) -> bool:
    try:
        _split_key(s, 0)
        return True
    except MiniYamlError:
        return False


def _split_key(content: str, lineno: int) -> tuple[str, str]:
    """Split ``key: rest`` (colon must be outside quotes, followed by space/EOL)."""
    in_single = in_double = False
    i = 0
    while i < len(content):
        ch = content[i]
        if in_single:
            if ch == "'":
                if i + 1 < len(content) and content[i + 1] == "'":
                    i += 1
                else:
                    in_single = False
        elif in_double:
            if ch == "\\":
                i += 1
            elif ch == '"':
                in_double = False
        elif ch == "'":
            in_single = True
        elif ch == '"':
            in_double = True
        elif ch == ":" and (i + 1 == len(content) or content[i + 1] in " \t"):
            raw_key = content[:i].strip()
            if not raw_key:
                raise MiniYamlError("empty mapping key", lineno)
            key = _parse_scalar(raw_key, lineno) if raw_key[0] in "'\"" else raw_key
            if not isinstance(key, str):
                raise MiniYamlError("mapping keys must be strings", lineno)
            return key, content[i + 1 :].strip()
        i += 1
    raise MiniYamlError("expected a `key: value` mapping entry", lineno)


# ---------------------------------------------------------------- scalars


def _parse_scalar(s: str, lineno: int) -> Any:
    s = s.strip()
    if not s:
        return None
    first = s[0]
    if first in "'\"":
        value, end = _parse_quoted(s, lineno)
        if s[end:].strip():
            raise MiniYamlError(
                f"unexpected trailing content after quoted string: {s[end:]!r}", lineno
            )
        return value
    if first == "[":
        return _parse_flow_seq(s, lineno)
    if first == "{":
        return _parse_flow_map(s, lineno)
    if first in "&*":
        raise MiniYamlError("anchors/aliases are not supported", lineno)
    if first in "|>":
        raise MiniYamlError("block scalars (| and >) are not supported", lineno)
    if first == "!":
        raise MiniYamlError("tags are not supported", lineno)
    if s in _BOOL_TRUE:
        return True
    if s in _BOOL_FALSE:
        return False
    if s in _NULLS:
        return None
    if _INT_RE.match(s):
        return int(s)
    if _FLOAT_RE.match(s):
        return float(s)
    return s


def _parse_quoted(s: str, lineno: int) -> tuple[str, int]:
    """Parse a quoted string at the start of ``s``; return (value, end_index)."""
    quote = s[0]
    buf: list[str] = []
    i = 1
    while i < len(s):
        ch = s[i]
        if quote == "'":
            if ch == "'":
                if i + 1 < len(s) and s[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                return "".join(buf), i + 1
            buf.append(ch)
            i += 1
        else:  # double-quoted
            if ch == "\\":
                if i + 1 >= len(s):
                    raise MiniYamlError("dangling escape in double-quoted string", lineno)
                esc = s[i + 1]
                if esc not in _DQ_ESCAPES:
                    raise MiniYamlError(f"unsupported escape sequence \\{esc}", lineno)
                buf.append(_DQ_ESCAPES[esc])
                i += 2
                continue
            if ch == '"':
                return "".join(buf), i + 1
            buf.append(ch)
            i += 1
    raise MiniYamlError("unterminated quoted string", lineno)


def _split_flow_items(inner: str) -> list[str]:
    """Split flow-collection contents on top-level commas (quote/bracket-aware)."""
    items: list[str] = []
    depth = 0
    in_single = in_double = False
    start = 0
    i = 0
    while i < len(inner):
        ch = inner[i]
        if in_single:
            if ch == "'":
                if i + 1 < len(inner) and inner[i + 1] == "'":
                    i += 1
                else:
                    in_single = False
        elif in_double:
            if ch == "\\":
                i += 1
            elif ch == '"':
                in_double = False
        elif ch == "'":
            in_single = True
        elif ch == '"':
            in_double = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            items.append(inner[start:i])
            start = i + 1
        i += 1
    items.append(inner[start:])
    return [item.strip() for item in items if item.strip()]


def _parse_flow_seq(s: str, lineno: int) -> list:
    if not s.endswith("]"):
        raise MiniYamlError(
            "unterminated flow sequence (multi-line flow is not supported)", lineno
        )
    inner = s[1:-1].strip()
    if not inner:
        return []
    return [_parse_scalar(item, lineno) for item in _split_flow_items(inner)]


def _parse_flow_map(s: str, lineno: int) -> dict:
    if not s.endswith("}"):
        raise MiniYamlError(
            "unterminated flow mapping (multi-line flow is not supported)", lineno
        )
    inner = s[1:-1].strip()
    out: dict[str, Any] = {}
    if not inner:
        return out
    for item in _split_flow_items(inner):
        key, rest = _split_key(item, lineno)
        if key in out:
            raise MiniYamlError(f"duplicate key {key!r}", lineno)
        out[key] = _parse_scalar(rest, lineno) if rest else None
    return out
