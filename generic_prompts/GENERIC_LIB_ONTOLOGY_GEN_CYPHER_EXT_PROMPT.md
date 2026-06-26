# Generic Lib Prompt: Graph-Query (Cypher) Structural Extractor

## Purpose

Produce one `FileInfo` per graph-query file (`.cypher`/`.cql`) using a
zero-dependency regex scanner. Each query file becomes a single `file` node; its
structural detail — node **labels**, **relationship types**, and the
**clauses/operations** it uses — is captured into `FileInfo.extra` and rendered
into the file's human-readable section. This is a template for any
domain-specific-language extractor whose structure doesn't map onto the
class/function node contract.

## Reusable Pattern

- **Strip comments first** (line `//` and block `/* */`) so they don't pollute the
  label/relationship scans.
- **Regex-capture the domain's structural tokens:** node labels `(:Label)` /
  `(n:Label:Other)`, relationship types `-[:REL]->`, and the leading clause
  keywords used (the "operations" summary).
- **Extras, not new node kinds.** The graph-node-kind enum has no `label`/
  `relationship` kind, so labels and relationship types are intentionally NOT
  minted as graph nodes — that would need a contract extension. They live in the
  per-file `extra` dict (and the rendered section). The file's graph contribution
  is its single `file` node. This is a deliberate decision, documented, not an
  omission — the pattern for any structure that exceeds the node contract.
- **Leading comment line as the human summary.**
- **Deterministic extras:** sort label/relationship sets, keep clause order unique.

## Algorithm

1. Strip comments to a working copy.
2. `finditer` the label regex (split multi-label `n:A:B`), the relationship-type
   regex, and the clause-keyword regex.
3. Take the first leading `//` comment as the summary.
4. Return `FileInfo(path, lang="<dsl>", kind="file", summary, extra={labels,
   relationships, clauses})`.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Graph-query (Cypher) structural extractor — zero-dependency regex scanner.

Labels/relationship types are captured into FileInfo.extra (NOT minted as graph
nodes — the node-kind enum has no label/relationship kind). The file's graph
contribution is its single `file` node.
"""
from __future__ import annotations

import re

from .model import FileInfo

_RE_NODE_LABEL = re.compile(r"\(\s*[A-Za-z_][\w]*\s*:\s*([A-Za-z_][\w:]*)")
_RE_REL_TYPE = re.compile(r"\[\s*[A-Za-z_]?[\w]*\s*:\s*([A-Z_][A-Z0-9_]*)")
_RE_CLAUSE = re.compile(
    r"\b(MATCH|OPTIONAL MATCH|MERGE|CREATE|DELETE|DETACH DELETE|SET|REMOVE|RETURN|"
    r"WITH|WHERE|UNWIND|CALL|FOREACH|LOAD CSV|CREATE INDEX|CREATE CONSTRAINT|"
    r"DROP INDEX|DROP CONSTRAINT)\b", re.IGNORECASE)


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", " ", src)


def _ordered_unique(items: list[str]) -> list[str]:
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x); out.append(x)
    return out


def extract_cypher(rel_path: str, source: str) -> FileInfo:
    clean = _strip_comments(source)
    labels: list[str] = []
    for m in _RE_NODE_LABEL.finditer(clean):
        labels.extend(p for p in m.group(1).split(":") if p)
    relationships = [m.group(1) for m in _RE_REL_TYPE.finditer(clean)]
    clauses = [m.group(1).upper() for m in _RE_CLAUSE.finditer(clean)]
    summary = ""
    for line in source.splitlines():
        s = line.strip()
        if s.startswith("//"):
            summary = s.lstrip("/").strip(); break
        if s:
            break
    return FileInfo(
        path=rel_path, lang="cypher", kind="file", summary=summary,
        extra={"labels": sorted(set(labels)),
               "relationships": sorted(set(relationships)),
               "clauses": _ordered_unique(clauses)},
    )
```

## Adaptation Notes

- **Use `extra` for structure that exceeds the node contract.** When a language's
  meaningful structure (graph labels, SQL tables, route definitions) doesn't fit
  the class/function node kinds, capture it as `FileInfo.extra` and let the
  renderer surface it — rather than forcing a contract enum extension.
- **Strip comments before scanning** so commented-out queries don't inflate the
  label/relationship sets.
- **Keep extras deterministic** (sorted sets / ordered-unique lists) so the
  rendered section is byte-stable.
- **Document the "deliberate, not omitted" boundary** so a future maintainer
  doesn't mistake the missing label nodes for a bug.
```
