# Generic Library Prompt: Shape-Preserving JSON Top-Level Key Upsert / Remove

## Purpose

Upsert (insert-or-replace) and remove **top-level keys** in a JSON state file
**without reformatting the rest of the file**. A naive `parse → mutate → pretty-
print → write` round-trip reflows every line to the serializer's default style,
turning a one-key change into a huge cosmetic diff. When a state file deliberately
mixes styles — some top-level keys are compact single-liners, other blocks are
pretty-indented multi-line objects/arrays — a full reserialize destroys that and
produces a several-hundred-line diff per edit.

This helper does a **targeted text-level edit** that preserves the file's existing
shape, then validates JSON before and after the rewrite so a malformed edit is
caught and aborted (never written).

Use this for any append-mostly JSON "status / ledger / manifest" file that is both
machine-written and human-read, where diff noise matters (it lives in version
control and is reviewed).

## Reusable algorithm

### Three structural primitives (the reusable core)

1. **`_is_top_level_position(text, pos)`** — walk the text from the start tracking
   bracket depth and JSON-string state; return True iff `pos` sits at depth 1
   (directly inside the outermost `{...}`). This is what distinguishes a genuine
   top-level key from a *nested* key that happens to share the name inside a
   multi-line value. Without it, a regex sibling-finder can match a nested key and
   insert mid-value, producing invalid JSON.

2. **`_find_value_end(text, opener_line_end)`** — given the end of a key's opener
   line, return the position just past where that key's value terminates
   (including a trailing comma). For a single-line value the opener end *is* the
   value end. For a multi-line value (opener line ends with `{` or `[`), scan
   forward tracking bracket depth + string-escape state until depth returns to 0.
   This is what lets replace/remove excise a whole multi-line block rather than
   just the opener line.

3. **Indent-tolerant line regex** — `^([ \t]*)"<key>":[ \t].*$` per line (no
   DOTALL). Capture the key's own leading whitespace so replacement preserves the
   line's style, and tolerate *any* indent so legacy 1-space keys and newer
   2-space keys are both handled. (A regex hard-coded to exactly 2 spaces silently
   fails to match a 1-space key and falls through to insert — producing a DUPLICATE
   top-level key.)

### Upsert logic

- **Replace-in-place:** walk every line-regex match, pick the first one that is at
  top-level depth, splice from `match.start()` through `_find_value_end(...)`
  (so a multi-line existing value is fully replaced, not left dangling), reusing
  the matched key's indent and preserving its trailing comma if present.
- **Insert when absent:** group the new key with siblings — if the key matches a
  `prefix_<N>_*` family, find the last top-level sibling of the same `<N>` and
  insert *after that sibling's structural close* (`_find_value_end`), not after its
  opener line. Handle the trailing-comma bookkeeping so the previously-final key
  gains a comma and the new last key drops its own. Fall back to inserting right
  after the opening `{` line if there is no sibling.

### Remove logic

Reuses the same primitives: reject a nested name match, find the value end (single
or multi-line), excise the whole physical line(s) plus trailing whitespace and
newline (no blank line / dangling comma left behind), and if the removed entry was
the JSON-final key, strip the now-final preceding entry's trailing comma.

### Safety contract (both paths)

Parse-before, apply all edits text-level, parse-after, and **confirm the
text-level result equals the logical result** (the parsed dict with the same
mutation applied) before writing. On any divergence, print which keys diverged and
abort without writing. This catches a mis-located insertion deterministically.

## Code template (stdlib only)

```python
"""Shape-preserving top-level key upsert/remove for a compact-inline JSON file."""
import json, re, sys
from pathlib import Path


def _is_top_level_position(text: str, position: int) -> bool:
    depth = in_str = escape = 0
    for i in range(min(position, len(text))):
        c = text[i]
        if escape:           escape = 0
        elif c == "\\" and in_str: escape = 1
        elif c == '"':       in_str = not in_str
        elif not in_str:
            if c in "{[":    depth += 1
            elif c in "}]":  depth -= 1
    return depth == 1 and not in_str


def _find_value_end(text: str, opener_end: int) -> int:
    line_start = text.rfind("\n", 0, opener_end) + 1
    if not text[line_start:opener_end].rstrip().endswith(("[", "{")):
        return opener_end
    depth, in_str, escape, pos = 1, False, False, opener_end
    while pos < len(text):
        c = text[pos]
        if escape:           escape = False
        elif c == "\\" and in_str: escape = True
        elif c == '"':       in_str = not in_str
        elif not in_str:
            if c in "{[":    depth += 1
            elif c in "}]":
                depth -= 1
                if depth == 0:
                    end = pos + 1
                    return end + 1 if end < len(text) and text[end] == "," else end
        pos += 1
    raise ValueError("unterminated multi-line value")


def upsert_top_level_key(text: str, key: str, json_value: str) -> str:
    line_re = re.compile(r'^([ \t]*)"' + re.escape(key) + r'":[ \t].*$', re.MULTILINE)
    for m in line_re.finditer(text):
        if not _is_top_level_position(text, m.start()):
            continue
        indent, value_end = m.group(1), _find_value_end(text, m.end())
        repl = f'{indent}"{key}": {json_value}'
        if value_end > 0 and text[value_end - 1] == ",":
            repl += ","
        return text[:m.start()] + repl + text[value_end:]
    # ... sibling-grouped insert (see algorithm above) ...
    new_line = f'  "{key}": {json_value},'
    brace = text.find("{\n")
    return text[:brace + 2] + new_line + "\n" + text[brace + 2:]
```

`main` decodes each `key=<json-literal>` argument, applies upserts logically and
text-level, runs the parse-after + equality guard, and only then writes. A
`--remove-key` mode mirrors the same safety contract.

## Adaptation notes

- The sibling-grouping prefix (`prefix_<N>_*`) is domain-specific; generalize it to
  whatever family key your file uses, or drop sibling-grouping and always insert
  after the opening brace.
- Each value argument is a self-contained JSON literal — strings carry their own
  quotes (pass `'"foo"'` from the shell). Decode with `json.loads` to validate.
- The whole point is diff minimalism; if your file is always machine-only and diff
  noise is irrelevant, a plain `json.dump` round-trip is simpler — use this only
  when the shape-preservation matters.
- Performance is O(position) per top-level check; for a ~100KB file a check is a
  few hundred-thousand char iterations, negligible for the handful of candidates
  per edit.
