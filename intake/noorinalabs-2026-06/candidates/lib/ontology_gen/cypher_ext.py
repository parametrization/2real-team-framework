#!/usr/bin/env python3
"""Cypher structural extractor — ``.cypher`` / ``.cql`` (#855, closes a #843 gap).

Zero-dependency regex scanner. Each query file becomes a single ``file`` node (lang
``cypher``); the structural detail — node **labels**, **relationship types**, and the
**clauses/operations** used — is captured into ``FileInfo.extra`` and rendered into the
file's ``llms.txt`` section.

Contract note (flagged for #856/#1128): the ``code-graph.json`` node-kind enum is
``{file, module, class, interface, type, func, method}`` (``interface`` and ``type``
added in main#870 for TypeScript). There is still no ``label``/``relationship`` kind, so
Cypher labels and relationship types are intentionally **not** minted as graph nodes —
that would require a further enum extension. They live in the per-file ``llms.txt``
section (where an agent reads them) and in ``FileInfo.extra``. The graph contribution of
a Cypher file is its ``file`` node. This is a deliberate decision, not an omission.
"""

from __future__ import annotations

import re

from .model import FileInfo

# (:Label)  /  (n:Label)  /  (n:Label:Other {..})  — capture each label segment.
_RE_NODE_LABEL = re.compile(r"\(\s*[A-Za-z_][\w]*\s*:\s*([A-Za-z_][\w:]*)")
# -[:REL_TYPE]-  /  -[r:REL_TYPE]->  /  -[r:REL_TYPE*1..2]->
_RE_REL_TYPE = re.compile(r"\[\s*[A-Za-z_]?[\w]*\s*:\s*([A-Z_][A-Z0-9_]*)")
# Leading clause keywords used in the file (the "operations" summary).
_RE_CLAUSE = re.compile(
    r"\b(MATCH|OPTIONAL MATCH|MERGE|CREATE|DELETE|DETACH DELETE|SET|REMOVE|RETURN|"
    r"WITH|WHERE|UNWIND|CALL|FOREACH|LOAD CSV|CREATE INDEX|CREATE CONSTRAINT|"
    r"DROP INDEX|DROP CONSTRAINT)\b",
    re.IGNORECASE,
)


def _strip_comments(source: str) -> str:
    # Line comments (//) and block comments (/* */). Good enough for label/rel scans.
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.DOTALL)
    source = re.sub(r"//[^\n]*", " ", source)
    return source


def _ordered_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def extract_cypher(rel_path: str, source: str) -> FileInfo:
    clean = _strip_comments(source)

    labels: list[str] = []
    for m in _RE_NODE_LABEL.finditer(clean):
        # A node pattern may carry multiple labels separated by ':' (n:A:B).
        labels.extend(part for part in m.group(1).split(":") if part)
    relationships = [m.group(1) for m in _RE_REL_TYPE.finditer(clean)]
    clauses = [m.group(1).upper() for m in _RE_CLAUSE.finditer(clean)]

    # A leading comment line as the human summary, if present.
    summary = ""
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            summary = stripped.lstrip("/").strip()
            break
        if stripped:
            break

    extra: dict[str, list[str]] = {
        "labels": sorted(set(labels)),
        "relationships": sorted(set(relationships)),
        "clauses": _ordered_unique(clauses),
    }
    return FileInfo(
        path=rel_path,
        lang="cypher",
        kind="file",
        summary=summary,
        extra=extra,
    )
