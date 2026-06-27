#!/usr/bin/env python3
"""Upsert top-level keys in cross-repo-status.json preserving compact-inline shape.

The skill ecosystem (/wave-kickoff, /wave-start) writes that file with deliberate
mixed style: top-level wave_{N}_* keys are compact single-liners, older
wave_*_scope blocks are pretty-indented. A naive `jq ... > tmp && mv` round-trip
reformats every compact line to jq's default pretty form, doubling the file
length and producing a 500+ line cosmetic diff per wave.

This helper does targeted text-level upsert:
  - If the key exists at top level → replace its line in place, preserving the
    key's existing leading indentation (1-space legacy keys and 2-space keys
    are both handled — main#595/#611 indent-tolerance fix).
  - If the key does not exist → insert a new compact-inline line right after
    the most-recent wave_{N}_* sibling (or before the closing `}`).

It also supports REMOVING a top-level key (`--remove-key` mode / the
`remove_top_level_key` function) — a general-purpose top-level key excision
that preserves the file shape and validates JSON either side of the rewrite.

Validates JSON before AND after the rewrite so a malformed write is caught.

Wave-key identity convention (main#804 — supersedes the main#611 overwrite scheme)
----------------------------------------------------------------------------------
Wave bookkeeping uses BARE `wave_{X}_*` top-level keys (e.g. `wave_16_scope`)
where `X` is a **global monotonic wave id** — a single counter (`global_wave_seq`)
that NEVER resets per phase and is never reused (allocated by `.claude/lib/wave_seq.py`
at `/wave-scope` Step 0). Phase is a derived display attribute (`wave_{X}_phase`
+ `wave_{X}_phase_ordinal`), not part of the key.

This replaces the pre-#804 per-phase scheme where `X` was a per-phase wave
number that reset to 1 each phase, so a same-numbered wave in a later phase
(P5W2 ↔ P6W2) collided on `wave_2_*`. That scheme relied on a `/wave-start`
§ 5a per-phase *reset* (the deleted `wave_key_reset.py`) to clear the prior
phase's stale keys — a band-aid that only cleaned up after the collision bit.
Under global ids the collision class cannot arise (a number is never reused),
so there is nothing to reset. Grandfathered in-flight P6 keys (`wave_1_*` /
`wave_2_*`) are preserved; the counter is seeded above all historical per-phase
numbers so the first new global wave is `wave_16`.

Invocation:
  upsert_status_keys.py <path> <key>=<json-encoded-value> [<key>=<json-encoded-value> ...]
  upsert_status_keys.py <path> --remove-key <key> [<key> ...]

Example (upsert):
  upsert_status_keys.py cross-repo-status.json \
    wave_5_scope_reconciled_at='"2026-05-05T22:31:00Z"' \
    wave_5_scope_reconciliation_note='"manual run"'

Example (key removal):
  upsert_status_keys.py cross-repo-status.json --remove-key \
    wave_1_scope wave_1_wrap_status wave_1_completed_at

Each VALUE must be a self-contained JSON literal (string/number/bool/array/object).
Strings include their quotes — pass `'"foo"'` from the shell.
"""

import json
import re
import sys
from pathlib import Path


def _is_top_level_position(text: str, position: int) -> bool:
    """Return True iff `position` in `text` is at JSON top-level depth.

    Walks the text from the start tracking bracket depth and JSON string
    state. Depth-1 (i.e., directly inside the outermost `{...}`) is what
    "top-level sibling" means for cross-repo-status.json. Positions inside
    nested objects/arrays or inside string values return False.

    This is the structural check that catches the bug class where the
    regex sibling-finder happens to match a key NAME that's nested inside
    a multi-line value (e.g., `wave_11_inner_key` at 2-space indent inside
    `wave_11_scope: {...}`). Without this check the helper would insert a
    new top-level key in the middle of a value, producing either invalid
    JSON or a logical/text divergence caught only by the post-write
    validation (which then aborts the entire upsert batch).

    Performance: O(position) per call — for cross-repo-status.json
    (~2700 lines, ~108KB) a single check is ~108K char-iterations, well
    under 10ms even on slow hardware. Called once per sibling-finder
    candidate, so worst case is ~108K × N candidates; N is typically 1–5
    so the total per-upsert cost remains negligible.
    """
    depth = 0
    in_string = False
    escape = False
    i = 0
    while i < position and i < len(text):
        c = text[i]
        if escape:
            escape = False
        elif c == "\\" and in_string:
            escape = True
        elif c == '"':
            in_string = not in_string
        elif not in_string:
            if c in "{[":
                depth += 1
            elif c in "}]":
                depth -= 1
        i += 1
    # Depth 1 means we're directly inside the outermost object's body.
    return depth == 1 and not in_string


def _find_value_end(text: str, opener_match_end: int) -> int:
    """Given the regex-match end of a top-level key:value opener line,
    return the position immediately AFTER that key's value terminates
    (including trailing `,` if present).

    For a single-line value (line ends with `,` or `]` or `}` inline),
    `opener_match_end` is already past the value — returned as-is.

    For a multi-line value (line ends with `{` or `[`), scans forward
    tracking bracket depth and JSON string-escape state until depth
    returns to 0, then optionally consumes a trailing `,`.

    This is the fix for main#332: the prior implementation treated
    every wave_N_* sibling-finder match as the value's end position,
    which inserted INSIDE multi-line arrays/objects (e.g., wave_8_work
    or wave_8_carry_forward in the P3W8 reproducer).
    """
    line_start = text.rfind("\n", 0, opener_match_end) + 1
    line_text = text[line_start:opener_match_end].rstrip()
    if not line_text.endswith(("[", "{")):
        return opener_match_end

    depth = 1
    in_string = False
    escape = False
    pos = opener_match_end
    while pos < len(text):
        c = text[pos]
        if escape:
            escape = False
        elif c == "\\" and in_string:
            escape = True
        elif c == '"':
            in_string = not in_string
        elif not in_string:
            if c in "{[":
                depth += 1
            elif c in "}]":
                depth -= 1
                if depth == 0:
                    end = pos + 1
                    if end < len(text) and text[end] == ",":
                        end += 1
                    return end
        pos += 1
    raise ValueError(f"unterminated multi-line value starting at position {opener_match_end}")


def upsert_top_level_key(text: str, key: str, json_value: str) -> str:
    """Replace `"<key>": ...,` line in place, or insert a new line if absent.

    Insertion point: after the last existing key whose top-level name matches
    `wave_<N>_*` for the same wave number embedded in `key` (best-effort sibling
    grouping). Handles multi-line array/object siblings correctly — insertion
    is placed AFTER the sibling's structural close, not after the opening
    line (main#332 fix).

    Both the existing-key match AND the sibling-finder match are filtered
    by `_is_top_level_position` — a regex match whose position is nested
    inside a multi-line value (e.g., `wave_11_inner_key` at 2-space indent
    inside `wave_11_scope: {...}`) is rejected so insertions never land
    mid-value. This is the fix for main#456 — the regex sibling-finder
    pre-#456 would match nested keys and insert ON TOP of them, producing
    either invalid JSON or a logical/text divergence aborted by the
    post-write validation.

    Multi-line existing value on replace (main#736): when the key already
    exists and its current value spans multiple lines (a pretty-printed object
    or array — the common shape in cross-repo-status.json), the replace path
    excises the value through `_find_value_end`, not just the opener line. The
    pre-#736 code spliced at the opener line's end, leaving the old multi-line
    body dangling after the new compact value and producing invalid JSON that
    aborted the whole upsert batch (the `/wave-scope` replace-`wave_{M}_scope`
    failure). Single-line values are unaffected — `_find_value_end` returns the
    opener-line end unchanged for them.

    Indent-tolerance (main#595/#611): the replace-in-place and sibling-finder
    regexes accept ANY leading whitespace, not just exactly 2 spaces. The
    file mixes 1-space legacy keys (P3W1-era, e.g. `current_wave` /
    `last_completed_wave` near line ~1211) with 2-space newer keys. Pre-fix,
    the `^(  )` anchor could not match a 1-space key at all, so an UPDATE of
    an existing 1-space scalar fell through to the insert path and produced a
    DUPLICATE top-level key — the logical/text divergence that aborted the
    W15-wrapup write (main#595). The replacement now reuses the matched key's
    own leading indent so the line's style is preserved.

    Falls back to inserting right after the opening `{` line if no sibling
    exists.
    """
    # `[ \t]*` captures the key's own indentation so it is preserved on
    # replace; the value pattern is greedy to end-of-line so a trailing
    # comma (or its absence) is captured as part of the line rather than
    # left dangling — the pre-fix non-greedy `.*?,?\s*$` could under-match
    # certain value shapes (main#595).
    line_re = re.compile(r'^([ \t]*)"' + re.escape(key) + r'":[ \t].*$', re.MULTILINE)
    # Replace-in-place: walk every match and pick the first one that's at
    # top-level depth. The pre-#456 code took the first regex match
    # unconditionally; that mis-matched nested keys whose NAME happened to
    # equal `key` (e.g., a top-level `wave_11_meta_issue` upsert mis-matching
    # a nested `wave_11_meta_issue` inside a wave_11_scope dict).
    for m in line_re.finditer(text):
        if not _is_top_level_position(text, m.start()):
            continue
        indent = m.group(1)
        # `line_re` is line-anchored (`.*$` with no DOTALL), so `m.end()` is
        # the end of the OPENER line only. For a multi-line existing value
        # (the opener line ends with `{` or `[`), the value body continues on
        # following lines — `_find_value_end` walks past it to the value's true
        # terminator. The pre-#736 code spliced at `m.end()`, which for a
        # multi-line value left the old body dangling after the new compact
        # value and produced invalid JSON (`Expecting ',' delimiter`), aborting
        # the whole batch. For a single-line value `_find_value_end` returns
        # `m.end()` unchanged, so this is a no-op for the cases that worked.
        value_end = _find_value_end(text, m.end())
        replacement = f'{indent}"{key}": {json_value}'
        if value_end > 0 and text[value_end - 1] == ",":
            replacement += ","
        return text[: m.start()] + replacement + text[value_end:]

    new_line = f'  "{key}": {json_value},'
    wave_num_match = re.match(r"wave_(\d+)_", key)
    if wave_num_match:
        sibling_re = re.compile(
            r'^([ \t]*)"wave_' + re.escape(wave_num_match.group(1)) + r'_[^"]+":.*$',
            re.MULTILINE,
        )
        # Filter to top-level matches only; the pre-#456 code took ALL
        # matches including nested wave_N_* names inside value dicts.
        siblings = [m for m in sibling_re.finditer(text) if _is_top_level_position(text, m.start())]
        if siblings:
            last = siblings[-1]
            value_end = _find_value_end(text, last.end())
            # If the previous sibling was the JSON-final key (no trailing
            # comma after its value), we must add a comma to it AND drop
            # the trailing comma from our new line so the new key becomes
            # the new last. Otherwise we'd emit `prev_key: prev_value\n
            # new_key: new_value,\n}` which is missing the comma between
            # the two existing pairs.
            prev_has_trailing_comma = value_end > 0 and text[value_end - 1] == ","
            if prev_has_trailing_comma:
                return text[:value_end] + "\n" + new_line + text[value_end:]
            return text[:value_end] + "," + "\n" + new_line.rstrip(",") + text[value_end:]

    open_brace = text.find("{\n")
    if open_brace < 0:
        raise ValueError("could not locate opening `{` line for insertion")
    insertion_point = open_brace + 2
    return text[:insertion_point] + new_line + "\n" + text[insertion_point:]


def remove_top_level_key(text: str, key: str) -> str:
    """Remove the top-level `"<key>": ...` entry from `text` entirely.

    A general-purpose top-level key excision (historically used at phase
    boundaries to clear stale `wave_{M}_*` keys before main#804's global wave
    ids removed that need). Reuses the same structural primitives as the upsert
    path:
      - `_is_top_level_position` rejects a name match that is nested inside a
        multi-line value, so removing `wave_1_scope` never deletes a nested
        key that happens to share the name.
      - `_find_value_end` handles both single-line and multi-line (array /
        object) values, so a multi-line block is removed in full.

    Indent-tolerant (`[ \t]*`) so 1-space legacy keys and 2-space keys are
    both removable.

    The whole physical line(s) — from the start of the key's line through its
    value's terminator and trailing comma plus the newline — is excised, so no
    blank line or dangling comma is left behind. If the removed entry was the
    JSON-final key (its value had no trailing comma), the now-final preceding
    entry's trailing comma is stripped to keep the JSON valid.

    Raises KeyError if no top-level key by that name exists (the caller can
    decide whether a missing key is fatal — `main` treats it as an error so a
    typo'd phase-cleanup key surfaces rather than silently no-op'ing).
    """
    opener_re = re.compile(r'^([ \t]*)"' + re.escape(key) + r'":[ \t]', re.MULTILINE)
    for m in opener_re.finditer(text):
        if not _is_top_level_position(text, m.start()):
            continue
        line_start = text.rfind("\n", 0, m.start()) + 1
        # `_find_value_end` expects the END of the opener LINE (it inspects
        # the line's last char to decide single- vs multi-line); m.end() is
        # only just past the `": "`. Advance to the line's newline first.
        line_end = text.find("\n", m.end())
        if line_end == -1:
            line_end = len(text)
        value_end = _find_value_end(text, line_end)
        # `_find_value_end` already consumed a trailing comma if present.
        # Consume the rest of the line (whitespace) and the newline so we
        # excise whole physical lines, leaving no blank line behind.
        cut_end = value_end
        while cut_end < len(text) and text[cut_end] in " \t":
            cut_end += 1
        if cut_end < len(text) and text[cut_end] == "\n":
            cut_end += 1
        had_trailing_comma = value_end > 0 and text[value_end - 1] == ","
        new_text = text[:line_start] + text[cut_end:]
        if not had_trailing_comma:
            # The removed entry was the JSON-final key; the entry now
            # immediately before the closing brace must lose its trailing
            # comma. Find the last `,` before the closing `}` and drop it.
            close = new_text.rfind("}")
            comma = new_text.rfind(",", 0, close)
            if comma != -1 and new_text[comma + 1 : close].strip() == "":
                new_text = new_text[:comma] + new_text[comma + 1 :]
        return new_text
    raise KeyError(f"top-level key {key!r} not found")


def _run_remove(path: Path, keys: list[str]) -> int:
    """Remove each top-level `key` from the file, validating JSON pre/post.

    Mirrors the upsert path's safety contract: parse before, apply all
    removals text-level, parse after, and confirm the text-level result
    matches the logical result (the original parsed dict minus the removed
    keys) before writing. A missing key is a hard error so a typo in a
    phase-cleanup invocation surfaces instead of silently no-op'ing.
    """
    if not keys:
        print("ERROR: --remove-key requires at least one key", file=sys.stderr)
        return 2

    text = path.read_text()
    parsed = json.loads(text)

    for key in keys:
        if key not in parsed:
            print(f"ERROR: top-level key {key!r} not found in {path}", file=sys.stderr)
            return 1
        try:
            text = remove_top_level_key(text, key)
        except (KeyError, ValueError) as exc:
            print(f"ERROR: could not remove {key!r}: {exc}", file=sys.stderr)
            return 1
        del parsed[key]

    try:
        reparsed = json.loads(text)
    except json.JSONDecodeError as exc:
        print(
            f"ERROR: text-level removal produced invalid JSON: {exc}\n  Offending keys: {keys}",
            file=sys.stderr,
        )
        return 1

    if reparsed != parsed:
        diverged_keys = sorted(set(reparsed.keys()) ^ set(parsed.keys()))
        for k in set(reparsed.keys()) & set(parsed.keys()):
            if reparsed[k] != parsed[k]:
                diverged_keys.append(k)
        print(
            f"ERROR: text-level removal diverged from logical removal; aborting write.\n"
            f"  Diverged keys: {sorted(set(diverged_keys))}\n"
            f"  Removed keys (this call): {keys}",
            file=sys.stderr,
        )
        return 1

    path.write_text(text)
    for key in keys:
        print(f"  removed: {key}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2

    path = Path(argv[1])

    if argv[2] == "--remove-key":
        return _run_remove(path, argv[3:])

    pairs = []
    for arg in argv[2:]:
        if "=" not in arg:
            print(f"ERROR: argument {arg!r} is not key=value", file=sys.stderr)
            return 2
        k, _, raw = arg.partition("=")
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"ERROR: value for {k} is not valid JSON: {exc}", file=sys.stderr)
            return 2
        pairs.append((k, raw, decoded))

    text = path.read_text()
    parsed = json.loads(text)

    for key, json_value, decoded in pairs:
        text = upsert_top_level_key(text, key, json_value)
        parsed[key] = decoded

    try:
        reparsed = json.loads(text)
    except json.JSONDecodeError as exc:
        # Surface the offending key=value pairs so the issue filer can
        # paste them straight into a reproducer (main#456 follow-up).
        key_repr = ", ".join(f"{k}={raw[:80]}" for k, raw, _ in pairs)
        print(
            f"ERROR: text-level upsert produced invalid JSON: {exc}\n"
            f"  This usually means the helper's sibling-finder mis-located\n"
            f"  the insertion point inside a multi-line array/object value\n"
            f"  (main#332/#456 reproducer class). File the failing input as\n"
            f"  an issue with the offending key=value upsert command.\n"
            f"  Offending pairs: {key_repr}",
            file=sys.stderr,
        )
        return 1

    if reparsed != parsed:
        # Pinpoint which key diverged so reviewers can read the bug without
        # diffing the full file (main#456 follow-up).
        diverged_keys = sorted(set(reparsed.keys()) ^ set(parsed.keys()))
        # Also catch same-key different-value divergence.
        for k in set(reparsed.keys()) & set(parsed.keys()):
            if reparsed[k] != parsed[k]:
                diverged_keys.append(k)
        key_repr = ", ".join(f"{k}={raw[:80]}" for k, raw, _ in pairs)
        print(
            f"ERROR: text-level upsert diverged from logical upsert; aborting write.\n"
            f"  Diverged keys: {sorted(set(diverged_keys))}\n"
            f"  Offending pairs (this call): {key_repr}\n"
            f"  This usually means a previous key in the same call was\n"
            f"  inserted at the wrong position (main#456 sibling-finder bug).",
            file=sys.stderr,
        )
        return 1

    path.write_text(text)
    for key, _, _ in pairs:
        print(f"  upserted: {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
