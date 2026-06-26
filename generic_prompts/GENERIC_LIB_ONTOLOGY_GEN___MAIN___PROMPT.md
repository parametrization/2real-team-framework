# Generic Lib Prompt: Structural-Generator CLI Entry Point (`__main__.py`)

## Purpose

The `python3 -m <package> <repo-root> --out <out-dir>/` entry point: a thin CLI
wrapper that parses arguments, validates the repo root, resolves a relative output
dir against the repo root, derives a display name, calls the package's single
`generate` orchestration function, and reports the resulting counts to stderr.

## Reusable Pattern

- **Thin wrapper, zero logic.** All real work lives in `generate`; `__main__` only
  does arg-parsing, path validation, and reporting. This keeps the library callable
  programmatically and the CLI a one-line delegation.
- **Validate inputs, return distinct exit codes.** A non-directory repo root →
  exit 2 (usage), not a crash.
- **Resolve a relative `--out` against the repo root**, so the same command works
  regardless of the caller's cwd.
- **Sensible default display name** (basename of the repo root) overridable by flag.
- **Report counts to stderr** (`files=… nodes=… edges=…`) so stdout stays clean for
  any piping.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""CLI entry point — python3 -m ontology_gen <repo-root> --out <out-dir>/.

Run from the lib dir (or with it on PYTHONPATH) so the package is importable.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .generate import generate


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m ontology_gen",
        description="Generate the structural index (code-graph.json + llms.txt) for a repo.")
    p.add_argument("repo_root", help="Path to the repository root to index.")
    p.add_argument("--out", required=True, help="Output dir for code-graph.json + llms.txt.")
    p.add_argument("--repo-name", default=None,
                   help="Display name for the header (default: basename of repo-root).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        sys.stderr.write(f"error: repo-root is not a directory: {repo_root}\n")
        return 2
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = repo_root / out_dir
    repo_name = args.repo_name or repo_root.name
    counts = generate(repo_root, out_dir, repo_name)
    sys.stderr.write(f"ontology_gen: {repo_name} -> {out_dir} "
                     f"(files={counts['files']} nodes={counts['nodes']} edges={counts['edges']})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## Adaptation Notes

- **Keep the CLI a delegation.** Resist putting discovery/extraction logic here;
  the package's `generate` is the one entry point so the same behavior is reachable
  programmatically and from the command line.
- **Relative-out-against-repo-root** is the small ergonomic that makes the command
  cwd-independent — keep it.
- **Distinct exit codes** (0 success, 2 usage) let callers/CI distinguish a bad
  invocation from a generation result.
```
