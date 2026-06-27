# Recipe: `upsert_status_keys.py` lib

## Purpose
Upsert (or remove) top-level keys in a status JSON file WITHOUT reformatting it.
A naive `jq … > tmp && mv` round-trip rewrites every compact single-line key to
jq's pretty form, producing a large cosmetic diff. This helper edits at the text
level so compact-inline lines stay compact and pretty blocks stay pretty.

## What it does
Standalone stdlib module — both a CLI and importable functions:
- `upsert_top_level_key(text, key, json_value)` — replace the key's line in
  place (indent-preserving, handles single- and multi-line existing values) or
  insert a new compact line after the last `wave_<N>_*` sibling / after the
  opening `{`.
- `remove_top_level_key(text, key)` — excise a top-level entry in full,
  including multi-line values and fixing trailing-comma JSON validity.
- Both filter matches by `_is_top_level_position` so a NAME nested in a
  multi-line value never mis-anchors an edit; `_find_value_end` walks multi-line
  values to their true terminator.
- CLI validates JSON before AND after, and aborts if the text-level result
  diverges from the logical (parsed-dict) result.

CLI:
```
upsert_status_keys.py <path> <key>='<json-value>' [...]
upsert_status_keys.py <path> --remove-key <key> [...]
```
Each value is a self-contained JSON literal; strings include quotes (`'"foo"'`).

## Config keys used
None. Pure stdlib (`json`, `re`, `sys`, `pathlib`); no framework config.

## Adaptation notes
- Sibling grouping is keyed on the `wave_<N>_` prefix. For a different scheme,
  adjust the `wave_(\d+)_` regex in `upsert_top_level_key`; keys not matching it
  simply fall back to insert-after-opening-`{`.
- Works on any JSON object file, not just status files. Designed for the common
  case of a 2-space pretty file with some compact lines.
