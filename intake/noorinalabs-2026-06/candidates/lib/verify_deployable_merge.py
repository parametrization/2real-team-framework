#!/usr/bin/env python3
"""Deterministic post-merge verification for *deployable* merges (main#864).

A PR's pre-merge CI is not the whole story. Some workflows are **push-to-main
only** — they never run on pull requests, so they give NO pre-merge signal and
only execute *after* the merge lands on `main`. The canonical example is a
container-publish workflow whose image vulnerability scan (Trivy) runs on
`push: branches: [main]` but not on `pull_request`: every per-issue PR can be
green while the post-merge publish goes red on a freshly-published base-image
CVE. That is precisely how `noorinalabs-isnad-graph#1131` (libexpat
CVE-2026-45186) slipped past #1130's green PR and reddened `main`.

`/wave-wrapup` Step 11 merges each wave branch to `main` — those ARE deployable
merges. Until this tool there was no deterministic, scriptable way to assert
"the merge I just performed actually went green across the post-merge-only
workflows too". The operator had to remember to eyeball `gh run list`, which is
exactly the manual step that rots (`feedback_enforcement_hierarchy`: a check
with no automation decays).

This CLI closes that gap. Given a repo and a merge commit SHA it:

  1. Determines the *expected* workflow set — either an explicit ``--workflows``
     list, or (default) by reading ``.github/workflows/*`` at that SHA and
     selecting the workflows that trigger on push-to-main / tags. With
     ``--require-deployable`` it narrows to the **post-merge-only** subset
     (push/tag triggered AND NOT ``pull_request``) — the genuinely blind ones.
  2. Polls the Actions runs for that exact ``head_sha`` until every expected
     workflow has a *completed* run (or the timeout elapses).
  3. Asserts every expected run concluded success/skipped. A FAILED run, or an
     expected workflow that produced **no** run at all (the silent-drop case —
     see `feedback_statuscheckrollup_ci_clean`, where an empty result is a hard
     not-verified, never a pass), fails the check.

It deliberately keys off the real run records for the SHA rather than trusting
the merge's own exit status: ``gh pr merge`` returns 0 the instant the merge
commit is created, long before the push-triggered workflows even start.

Usage:
    python3 .claude/lib/verify_deployable_merge.py <owner/repo> <sha>
    python3 .claude/lib/verify_deployable_merge.py <owner/repo> <sha> --require-deployable
    python3 .claude/lib/verify_deployable_merge.py <owner/repo> <sha> --workflows "Publish to GHCR"
    python3 .claude/lib/verify_deployable_merge.py <owner/repo> <sha> --timeout 1200 --json

Exit codes:
    0 — VERIFIED: every required workflow ran and concluded success AND no run
        that executed for the SHA went red. This includes the "nothing required"
        case (no post-merge-only / merge-triggered workflow at this ref, e.g. a
        meta repo) — verified by the no-red safety net alone.
    1 — NOT VERIFIED: a failed run, a required workflow that produced no run at
        all (silent drop), or still pending at timeout.
    2 — UNDETERMINED: a gh/API call failed — cannot determine.
"""

from __future__ import annotations

import argparse
import base64
import dataclasses
import json
import subprocess
import sys
import time

import yaml

# Conclusions GitHub may report on a *completed* run. Anything not in PASS and
# not pending is treated as a failure — including a completed run with a null
# conclusion, which should never happen but must not silently pass.
_PASS_CONCLUSIONS = frozenset({"success", "skipped", "neutral"})


# ---------------------------------------------------------------------------
# Pure logic (no network — unit-tested directly)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class WorkflowTrigger:
    """A workflow's trigger classification, derived from its ``on:`` block.

    Scoped to the event this tool verifies: a **branch merge to main** (a push
    to the main branch). A tag-only workflow (``push: {tags: [...]}`` with no
    branch filter) does NOT run on a branch merge — it runs on a separate
    release/tag event — so it is deliberately not treated as merge-triggered.
    """

    name: str
    path: str
    on_push_main: bool  # push to the main branch (the merge event)
    push_path_filtered: bool  # push trigger carries paths/paths-ignore (conditional)
    on_tag: bool  # push to a tag (a separate deploy path, not a branch merge)
    on_pull_request: bool  # pull_request / pull_request_target

    @property
    def is_merge_triggered(self) -> bool:
        """Runs UNCONDITIONALLY on a merge to main.

        A push-to-main trigger that carries a ``paths:``/``paths-ignore:`` filter
        is *conditional* — it legitimately may not run for a given merge — so it
        is excluded from the required set (its absence is not a silent drop). If
        such a workflow does run and fails, the no-red safety net still catches
        it.
        """
        return self.on_push_main and not self.push_path_filtered

    @property
    def is_post_merge_only(self) -> bool:
        """Merge-triggered AND invisible pre-merge (never runs on a PR)."""
        return self.is_merge_triggered and not self.on_pull_request


def _coerce_on_block(parsed: object) -> object:
    """Return the ``on:`` value from a parsed workflow mapping.

    GitHub Actions' ``on:`` collides with YAML 1.1's boolean literals: PyYAML
    parses the bare key ``on`` as the boolean ``True``, so ``data["on"]`` is a
    KeyError and the trigger block hides under ``data[True]``. This is the
    single most common GHA-YAML parsing bug; handle both spellings.
    """
    if not isinstance(parsed, dict):
        return None
    if "on" in parsed:
        return parsed["on"]
    if True in parsed:
        return parsed[True]
    return None


def _branches_include_main(node: object) -> bool:
    """True if a push trigger's branch filter includes main, or has none.

    A push trigger with no ``branches``/``branches-ignore`` filter fires on all
    branches (so it covers main). A ``branches`` list counts only if it names
    ``main`` (we do not try to resolve globs beyond an explicit ``**`` / ``*``).
    """
    if not isinstance(node, dict):
        # `push:` with a null/empty value → fires on every branch.
        return True
    branches = node.get("branches")
    if branches is None:
        # No positive filter → fires on all branches (branches-ignore style).
        return True
    if isinstance(branches, str):
        branches = [branches]
    if not isinstance(branches, list):
        return True
    return any(b in ("main", "*", "**") for b in branches)


def classify_trigger(name: str, path: str, yaml_text: str) -> WorkflowTrigger | None:
    """Parse one workflow file's ``on:`` into a WorkflowTrigger.

    Returns None if the file does not parse as a mapping or declares no usable
    ``on:`` block — such a file contributes no expected runs.
    """
    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return None
    on = _coerce_on_block(parsed)
    if on is None:
        return None

    # `on:` may be a bare string ("push"), a list (["push","pull_request"]) or a
    # mapping ({push: {...}, pull_request: {...}}). Normalise to a dict keyed by
    # event name; for the string/list forms the per-event config is absent.
    events: dict[str, object] = {}
    if isinstance(on, str):
        events[on] = None
    elif isinstance(on, list):
        for item in on:
            if isinstance(item, str):
                events[item] = None
    elif isinstance(on, dict):
        for key, value in on.items():
            events[str(key)] = value

    on_push_main = False
    push_path_filtered = False
    on_tag = False
    if "push" in events:
        push_cfg = events["push"]
        on_push_main = _branches_include_main(push_cfg)
        if isinstance(push_cfg, dict):
            on_tag = bool(push_cfg.get("tags"))
            push_path_filtered = "paths" in push_cfg or "paths-ignore" in push_cfg
            # A push trigger that names ONLY tags (no branches key) does not fire
            # on a branch merge — _branches_include_main returns True for the
            # no-branches case, so correct that here for the tags-only shape.
            if "branches" not in push_cfg and push_cfg.get("tags"):
                on_push_main = False

    on_pull_request = "pull_request" in events or "pull_request_target" in events

    display = name or path.rsplit("/", 1)[-1]
    return WorkflowTrigger(
        name=display,
        path=path,
        on_push_main=on_push_main,
        push_path_filtered=push_path_filtered,
        on_tag=on_tag,
        on_pull_request=on_pull_request,
    )


def workflow_display_name(path: str, yaml_text: str) -> str:
    """The workflow's ``name:`` if present, else the bare filename.

    GitHub keys an Actions run's ``name`` off the workflow's top-level ``name:``;
    when absent it uses the file path. We must match runs by the SAME label, so
    derive it identically here.
    """
    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get("name"), str):
        return parsed["name"]
    return path.rsplit("/", 1)[-1]


@dataclasses.dataclass(frozen=True)
class RunVerdict:
    bucket: str  # "pass" | "fail" | "pending"
    conclusion: str
    status: str


def classify_run(status: str, conclusion: str) -> RunVerdict:
    """Bucket a single workflow run record."""
    if status != "completed":
        return RunVerdict("pending", conclusion or "", status or "")
    if conclusion in _PASS_CONCLUSIONS:
        return RunVerdict("pass", conclusion, status)
    return RunVerdict("fail", conclusion or "(none)", status)


@dataclasses.dataclass
class Aggregate:
    """Overall verdict over the expected workflow set for one SHA."""

    verified: bool
    pending: bool
    rows: list[dict]  # per-expected-workflow: name, bucket, conclusion, url
    missing: list[str]  # expected workflows with no run for the SHA
    expected: list[str]  # the required workflow set (empty == nothing required)


def aggregate(expected: list[str], runs: list[dict]) -> Aggregate:
    """Combine expected workflow names with the runs found for a SHA.

    ``runs`` are records with ``name``, ``status``, ``conclusion``, ``html_url``.
    When a workflow has multiple runs for the SHA (re-runs), the most recent —
    last in API order is newest-first, so index 0 — wins.
    """
    by_name: dict[str, dict] = {}
    for run in runs:
        nm = run.get("name", "")
        # API returns newest first; keep the first seen per name.
        by_name.setdefault(nm, run)

    rows: list[dict] = []
    missing: list[str] = []
    any_fail = False
    any_pending = False
    expected_set = set(expected)

    # Required set: every expected workflow must be present AND pass. A missing
    # one is the silent-drop case (empty == hard not-verified).
    for name in expected:
        found = by_name.get(name)
        if found is None:
            missing.append(name)
            rows.append({"name": name, "bucket": "missing", "conclusion": "", "url": ""})
            continue
        verdict = classify_run(found.get("status", ""), found.get("conclusion", ""))
        rows.append(
            {
                "name": name,
                "bucket": verdict.bucket,
                "conclusion": verdict.conclusion,
                "url": found.get("html_url", ""),
            }
        )
        if verdict.bucket == "fail":
            any_fail = True
        elif verdict.bucket == "pending":
            any_pending = True

    # No-red safety net: ANY run that executed for this SHA but is not in the
    # required set (e.g. a path-filtered push workflow that did fire) must not be
    # red, and we wait for it to settle. This catches failures the required-set
    # detection would otherwise miss without over-requiring conditional workflows.
    for run in runs:
        nm = run.get("name", "")
        if nm in expected_set:
            continue
        verdict = classify_run(run.get("status", ""), run.get("conclusion", ""))
        if verdict.bucket == "fail":
            any_fail = True
            rows.append(
                {
                    "name": nm,
                    "bucket": "fail",
                    "conclusion": verdict.conclusion,
                    "url": run.get("html_url", ""),
                }
            )
        elif verdict.bucket == "pending":
            any_pending = True

    pending = any_pending or bool(missing)
    verified = not any_fail and not pending
    return Aggregate(
        verified=verified,
        pending=pending,
        rows=rows,
        missing=missing,
        expected=list(expected),
    )


# ---------------------------------------------------------------------------
# I/O (gh subprocess — mocked in tests)
# ---------------------------------------------------------------------------


class GhError(RuntimeError):
    """A gh/API call failed; readiness cannot be determined (exit 2)."""


def _run_gh(args: list[str]) -> str:
    """Run ``gh <args>`` with an explicit arg list (never a shell string).

    Mirrors ``wave_status._run_gh`` (main#688): no shell means no word-splitting,
    so a multi-word value can never collapse into a bogus flag.
    """
    try:
        proc = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:  # gh not installed
        raise GhError("gh CLI not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise GhError(f"gh {' '.join(args)} failed: {exc.stderr.strip()}") from exc
    return proc.stdout


def fetch_workflow_files(repo: str, ref: str) -> dict[str, str]:
    """Return {path: yaml_text} for every workflow under .github/workflows at ref."""
    listing_raw = _run_gh(["api", f"repos/{repo}/contents/.github/workflows?ref={ref}"])
    try:
        listing = json.loads(listing_raw)
    except json.JSONDecodeError as exc:
        raise GhError("could not parse workflows directory listing") from exc
    if not isinstance(listing, list):
        raise GhError(".github/workflows is not a directory at this ref")

    files: dict[str, str] = {}
    for entry in listing:
        path = entry.get("path", "")
        if not (path.endswith(".yml") or path.endswith(".yaml")):
            continue
        blob_raw = _run_gh(["api", f"repos/{repo}/contents/{path}?ref={ref}"])
        try:
            blob = json.loads(blob_raw)
            content = base64.b64decode(blob.get("content", "")).decode("utf-8")
        except (json.JSONDecodeError, ValueError) as exc:
            raise GhError(f"could not decode {path}") from exc
        files[path] = content
    return files


def fetch_runs_for_sha(repo: str, sha: str) -> list[dict]:
    """Return the Actions run records for a commit SHA (newest first)."""
    raw = _run_gh(["api", f"repos/{repo}/actions/runs?head_sha={sha}&per_page=100"])
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GhError("could not parse actions runs response") from exc
    runs = data.get("workflow_runs", [])
    return [
        {
            "name": r.get("name", ""),
            "status": r.get("status", ""),
            "conclusion": r.get("conclusion", ""),
            "html_url": r.get("html_url", ""),
            "event": r.get("event", ""),
            "path": r.get("path", ""),
        }
        for r in runs
    ]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def resolve_expected(
    repo: str, sha: str, explicit: list[str] | None, require_deployable: bool
) -> list[str]:
    """Resolve the set of workflow display-names we expect to run for the SHA."""
    if explicit:
        return explicit
    files = fetch_workflow_files(repo, sha)
    expected: list[str] = []
    for path, text in files.items():
        trigger = classify_trigger(workflow_display_name(path, text), path, text)
        if trigger is None or not trigger.is_merge_triggered:
            continue
        if require_deployable and not trigger.is_post_merge_only:
            continue
        expected.append(trigger.name)
    return sorted(set(expected))


def verify(
    repo: str,
    sha: str,
    *,
    explicit_workflows: list[str] | None = None,
    require_deployable: bool = False,
    timeout: int = 900,
    poll: int = 20,
    sleep=time.sleep,
    clock=time.monotonic,
) -> Aggregate:
    """Poll until the expected workflows for SHA are all complete, then verdict.

    ``sleep``/``clock`` are injectable so tests drive the poll loop without real
    time. Raises GhError (→ exit 2) if expected resolution finds nothing.
    """
    expected = resolve_expected(repo, sha, explicit_workflows, require_deployable)
    # An empty required set is NOT an error: a repo may have no post-merge-only
    # workflow (e.g. a meta repo whose CI is path-partitioned and PR-visible).
    # We still fetch the runs and apply the no-red safety net — a red run is
    # caught regardless of whether anything was "required" — so "nothing
    # required" resolves to verified iff nothing that ran went red. GhError
    # (a real gh/API failure → exit 2) is raised only by the fetch calls.
    deadline = clock() + timeout
    result = aggregate(expected, fetch_runs_for_sha(repo, sha))
    while result.pending and clock() < deadline:
        sleep(poll)
        result = aggregate(expected, fetch_runs_for_sha(repo, sha))
    return result


def _format_report(repo: str, sha: str, result: Aggregate) -> str:
    lines = [f"Deployable-merge verification — {repo} @ {sha[:8]}"]
    if not result.expected:
        lines.append("  (no required post-merge workflows at this ref — no-red safety net only)")
    for row in result.rows:
        mark = {"pass": "✓", "fail": "✗", "pending": "…", "missing": "∅"}.get(row["bucket"], "?")
        detail = row["conclusion"] or row["bucket"]
        lines.append(f"  {mark} {row['name']}: {detail}")
        if row["bucket"] in ("fail", "missing") and row["url"]:
            lines.append(f"      {row['url']}")
    if result.missing:
        lines.append(
            "  ! missing workflows never produced a run for this SHA "
            "(silent-drop / not-triggered) — treated as NOT verified."
        )
    if any(r["bucket"] == "fail" for r in result.rows):
        lines.append("  → inspect: gh run view <run-id> --repo " + repo + " --log-failed")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a deployable merge's post-merge workflows went green."
    )
    parser.add_argument("repo", help="owner/repo, e.g. noorinalabs/noorinalabs-isnad-graph")
    parser.add_argument("sha", help="merge commit SHA on the deployable branch")
    parser.add_argument(
        "--workflows",
        default="",
        help="comma-separated workflow display-names to verify (skips auto-detect)",
    )
    parser.add_argument(
        "--require-deployable",
        action="store_true",
        help="auto-detect only post-merge-only workflows (push/tag AND not pull_request)",
    )
    parser.add_argument("--timeout", type=int, default=900, help="seconds to wait (default 900)")
    parser.add_argument("--poll", type=int, default=20, help="poll interval seconds (default 20)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args(argv)

    explicit = [w.strip() for w in args.workflows.split(",") if w.strip()] or None

    try:
        result = verify(
            args.repo,
            args.sha,
            explicit_workflows=explicit,
            require_deployable=args.require_deployable,
            timeout=args.timeout,
            poll=args.poll,
        )
    except GhError as exc:
        if args.json:
            print(json.dumps({"verified": False, "undetermined": True, "error": str(exc)}))
        else:
            print(f"UNDETERMINED: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "pending": result.pending,
                    "missing": result.missing,
                    "rows": result.rows,
                }
            )
        )
    else:
        print(_format_report(args.repo, args.sha, result))
        print("VERIFIED" if result.verified else "NOT VERIFIED")

    return 0 if result.verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
