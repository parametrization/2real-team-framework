#!/usr/bin/env python3
"""CLI entry point — ``python3 -m ontology_gen <repo-root> --out ontology/structural/``.

Run from ``.claude/lib`` (or with that dir on ``PYTHONPATH``) so the ``ontology_gen``
package is importable. Generates the structural index for ``<repo-root>`` into ``--out``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .generate import generate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m ontology_gen",
        description="Generate the structural ontology (code-graph.json + llms.txt) for a repo.",
    )
    parser.add_argument("repo_root", help="Path to the repository root to index.")
    parser.add_argument(
        "--out",
        required=True,
        help="Output directory for code-graph.json + llms.txt (e.g. ontology/structural/).",
    )
    parser.add_argument(
        "--repo-name",
        default=None,
        help="Display name for the index header (default: basename of repo-root).",
    )
    return parser


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
    sys.stderr.write(
        f"ontology_gen: {repo_name} → {out_dir} "
        f"(files={counts['files']} nodes={counts['nodes']} edges={counts['edges']})\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
