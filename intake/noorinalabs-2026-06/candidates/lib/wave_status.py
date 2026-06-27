#!/usr/bin/env python3
"""Deterministic wave repo-iteration + counter helper (main#688).

zsh — this org's shell (memory ``feedback_zsh_shell_environment``) — does NOT
word-split an unquoted parameter expansion ``$var`` the way bash/sh do. The
hand-rolled ``for R in $WAVE_REPOS_IN_SCOPE`` loops in /wave-wrapup,
/wave-kickoff and /wave-scope therefore collapsed the whole newline-joined
repo list into a SINGLE iteration: the string
``"noorinalabs-isnad-graph noorinalabs-user-service ..."`` was passed to ``gh``
as one repo, which 404'd ("Could not resolve repository") → merged-PR count 0
→ division-by-zero in the top-concentration math. It bit a single P5W4
``/wave-wrapup`` three times — a soft memory had not stopped the recurrence, so
the iteration + counter math is moved here, into deterministic code.

Design contract:
  * EVERY ``gh`` invocation goes through :func:`_run_gh`, which calls
    ``subprocess.run(["gh", *args], ...)`` with an explicit ARG LIST — never a
    shell string, never ``shell=True``. There is no word-splitting anywhere,
    under any shell.
  * ``repos``      — emit ``wave_{M}_repos_in_scope`` one-per-line so a bash
                     caller can iterate safely (``while IFS= read -r R``).
  * ``merged-prs`` — the wave's merged-PR set as JSON, cross-window-filtered by
                     ``wave_{M}_kicked_off_at`` (the #423 partition fix).
  * ``counters``   — ``final_pr_count`` / ``changes_requested_cycles`` /
                     ``top_concentration_pct``; ``--write`` upserts the three
                     canonical top-level keys that /wave-retro Step 2.5 reads
                     (via :mod:`upsert_status_keys`, preserving the
                     compact-inline file shape); ``--expect N`` loud-fails on a
                     count mismatch.

CLI:
  wave_status.py repos       <P> <M> [--status PATH]
  wave_status.py merged-prs  <P> <M> [--status PATH]
  wave_status.py counters    <P> <M> [--write] [--expect N] [--status PATH]
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections import Counter
from pathlib import Path

# upsert_status_keys.py lives alongside this file in .claude/lib/. When this
# module is run as a script its own directory is on sys.path[0]; the tests add
# the lib dir explicitly. Import lazily inside _write_counters so a missing
# helper only matters for the --write path.

# Repo root = two parents above .claude/lib/ (lib -> .claude -> root). Resolved
# from this file so the default is correct from any cwd or worktree, with no
# `git rev-parse` subprocess (which would re-introduce a shell dependency).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_STATUS = _REPO_ROOT / "cross-repo-status.json"

# A ChangesRequested verdict comment on a PR's issue-comments timeline. Mirrors
# the regex the pre-#688 bash Step 10.5 block used. The DOUBLED backslash is
# load-bearing: this string is embedded into a jq filter, and jq's own string
# parser collapses ``\\s`` to the regex ``\s`` — a single backslash would be an
# "invalid escape sequence" jq error (caught live, not by the mocked tests).
_CHANGES_REQUESTED_RE = "RequestOrReplied:\\\\s*ChangesRequested"


def _run_gh(args: list[str]) -> str:
    """Run ``gh <args>`` with an explicit arg list and return stdout.

    Never a shell string and never ``shell=True`` — this is the whole point of
    the helper (main#688): no shell means no word-splitting, so a multi-word
    repo list can never collapse into one bogus ``--repo`` value.
    """
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def _load_status(status_path: Path) -> dict:
    return json.loads(status_path.read_text())


def read_repos(wave: str, status_path: Path) -> list[str]:
    """Return ``wave_{M}_repos_in_scope`` as a list of repo names.

    Raises KeyError if the key is absent — by the time any of these subcommands
    runs the wave's scope must already be recorded, so a missing key is an
    operator error to surface rather than silently treat as the empty set.
    """
    data = _load_status(status_path)
    key = f"wave_{wave}_repos_in_scope"
    if key not in data:
        raise KeyError(key)
    repos = data[key]
    if not isinstance(repos, list):
        raise TypeError(f"{key} is not a list: {repos!r}")
    return [str(r) for r in repos]


def _kickoff_ts(wave: str, status_path: Path) -> str | None:
    """The cross-window filter boundary — ``wave_{M}_kicked_off_at`` or None.

    Absent for legacy waves (W1-W3 pre-/wave-start); in that case no filter is
    applied and the caller relies on the base-branch scoping alone (#423).
    """
    data = _load_status(status_path)
    val = data.get(f"wave_{wave}_kicked_off_at")
    return str(val) if val else None


def merged_prs(phase: str, wave: str, status_path: Path) -> list[dict]:
    """Build the wave's merged-PR set across every in-scope repo.

    For each repo: list merged PRs based on ``deployments/phase-<P>/wave-<M>``,
    drop any merged before ``wave_{M}_kicked_off_at`` (the #423 cross-window
    filter), and attach the head commit's author name (the identity the
    top-concentration metric is computed over).
    """
    repos = read_repos(wave, status_path)
    kickoff = _kickoff_ts(wave, status_path)
    base = f"deployments/phase-{phase}/wave-{wave}"

    out: list[dict] = []
    for repo in repos:
        listed = json.loads(
            _run_gh(
                [
                    "pr",
                    "list",
                    "--repo",
                    f"noorinalabs/{repo}",
                    "--state",
                    "merged",
                    "--base",
                    base,
                    "--json",
                    "number,headRefOid,mergedAt,author",
                ]
            )
        )
        for pr in listed:
            merged_at = pr.get("mergedAt") or ""
            if kickoff and merged_at < kickoff:
                continue
            sha = pr["headRefOid"]
            commit_author = _run_gh(
                [
                    "api",
                    f"repos/noorinalabs/{repo}/commits/{sha}",
                    "--jq",
                    ".commit.author.name",
                ]
            ).strip()
            out.append(
                {
                    "repo": repo,
                    "number": pr["number"],
                    "mergedAt": merged_at,
                    "headRefOid": sha,
                    "author": (pr.get("author") or {}).get("login"),
                    "commit_author_name": commit_author,
                }
            )
    return out


def _changes_requested_cycles(prs: list[dict]) -> int:
    """Sum ChangesRequested verdict comments across every PR's timeline."""
    total = 0
    for pr in prs:
        count = _run_gh(
            [
                "api",
                f"repos/noorinalabs/{pr['repo']}/issues/{pr['number']}/comments",
                "--jq",
                f'[.[] | select(.body | test("{_CHANGES_REQUESTED_RE}"))] | length',
            ]
        ).strip()
        total += int(count or 0)
    return total


def _top_concentration_pct(prs: list[dict]) -> int:
    """Top commit-author's PR-count as a half-up-rounded percentage of total.

    Returns 0 for an empty wave (no PRs) rather than dividing by zero — the
    exact crash main#688 set out to kill. Half-up rounding (``floor(x + 0.5)``)
    matches the pre-#688 bash ``printf "%d" x + 0.5`` so historical counter
    rows reproduce (e.g. 3/19 = 15.78 → 16).
    """
    total = len(prs)
    if total == 0:
        return 0
    counts = Counter(pr["commit_author_name"] for pr in prs)
    top = counts.most_common(1)[0][1]
    return math.floor(top * 100 / total + 0.5)


def compute_counters(phase: str, wave: str, status_path: Path) -> dict[str, int]:
    """Compute the three canonical wave counters from the merged-PR set."""
    prs = merged_prs(phase, wave, status_path)
    return {
        "final_pr_count": len(prs),
        "changes_requested_cycles": _changes_requested_cycles(prs),
        "top_concentration_pct": _top_concentration_pct(prs),
    }


def _write_counters(wave: str, counters: dict[str, int], status_path: Path) -> int:
    """Upsert the three canonical top-level keys via upsert_status_keys.main.

    Reuses the shared helper so the compact-inline shape of
    cross-repo-status.json is preserved and the write is JSON-validated before
    AND after (main#332/#456). Values are plain integers → bare JSON literals.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from upsert_status_keys import main as upsert_main

    # upsert_status_keys.main treats argv[0] as the program name (argv[1] is the
    # status path), so prepend a placeholder element.
    return upsert_main(
        [
            "wave_status",
            str(status_path),
            f"wave_{wave}_final_pr_count={counters['final_pr_count']}",
            f"wave_{wave}_changes_requested_cycles={counters['changes_requested_cycles']}",
            f"wave_{wave}_top_concentration_pct={counters['top_concentration_pct']}",
        ]
    )


def _cmd_repos(args: argparse.Namespace) -> int:
    for repo in read_repos(args.wave, args.status):
        print(repo)
    return 0


def _cmd_merged_prs(args: argparse.Namespace) -> int:
    print(json.dumps(merged_prs(args.phase, args.wave, args.status), indent=2))
    return 0


def _cmd_counters(args: argparse.Namespace) -> int:
    counters = compute_counters(args.phase, args.wave, args.status)
    print(json.dumps(counters, indent=2))

    if args.expect is not None and counters["final_pr_count"] != args.expect:
        print(
            f"ERROR: final_pr_count {counters['final_pr_count']} != --expect {args.expect}",
            file=sys.stderr,
        )
        return 1

    if args.write:
        rc = _write_counters(args.wave, counters, args.status)
        if rc != 0:
            return rc
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_pm(p: argparse.ArgumentParser) -> None:
        p.add_argument("phase", help="phase number (P)")
        p.add_argument("wave", help="wave number (M)")
        p.add_argument(
            "--status",
            type=Path,
            default=_DEFAULT_STATUS,
            help="path to cross-repo-status.json (default: repo-root copy)",
        )

    p_repos = sub.add_parser("repos", help="emit wave_{M}_repos_in_scope one per line")
    _add_pm(p_repos)
    p_repos.set_defaults(func=_cmd_repos)

    p_merged = sub.add_parser("merged-prs", help="emit the wave's merged-PR set as JSON")
    _add_pm(p_merged)
    p_merged.set_defaults(func=_cmd_merged_prs)

    p_counters = sub.add_parser("counters", help="compute (and optionally write) wave counters")
    _add_pm(p_counters)
    p_counters.add_argument(
        "--write",
        action="store_true",
        help="upsert the three canonical top-level keys into cross-repo-status.json",
    )
    p_counters.add_argument(
        "--expect",
        type=int,
        default=None,
        help="loud-fail (exit 1) if final_pr_count != N",
    )
    p_counters.set_defaults(func=_cmd_counters)
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except KeyError as exc:
        print(f"ERROR: missing key in cross-repo-status.json: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(
            f"ERROR: gh call failed (exit {exc.returncode}): {' '.join(exc.cmd)}\n{exc.stderr}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
