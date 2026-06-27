#!/usr/bin/env python3
"""Validate Workflow Paths Coverage — block workflow-file orphans on `gh pr create`.

This hook addresses the **workflow-file orphan** failure class surfaced on
deploy#153 (commit `76d7d7f`): a PR modified `.github/workflows/db-migrate.yml`
but no workflow in the repo had a `pull_request.paths:` filter that matches
`.github/workflows/**`, so the workflow change was silently un-CI'd. Combined
with a strict `git checkout origin/main -- infra/...` revert that removed the
prior `infra/**`-matched delta, the PR ended with `statusCheckRollup: []` and
`mergeStateStatus: CLEAN` — a state that looks fine to `validate_pr_ci_status`
(which only blocks on failing/cancelled, not empty rollup) but actually means
"no one ever validated this commit."

This hook closes the workflow-file half: if a PR adds or modifies any file
under `.github/workflows/**`, it MUST be covered by at least one workflow's
`pull_request.paths:` filter (or the workflow may omit the `paths:` filter
entirely, which matches all paths).

Input Language
==============

Fires on:
    PreToolUse Bash
Matches:
    gh pr create [--repo OWNER/REPO] [--base BASE] [--head BRANCH] [other flags]
    gh pr ready [<number>] [--repo OWNER/REPO]

Does NOT match:
    - `gh pr create` with no `.github/workflows/**` files in the PR diff
    - `gh pr list`, `gh pr view`, `gh pr checks`, `gh pr edit`, `gh pr merge`
    - `git push`, `git commit` — workflow-orphan check is gated at PR-open
      time, not at every push (the harness can re-trigger the same hook on
      `gh pr ready` if a PR is opened as draft and later marked ready)

Flag pass-through:
    --repo OWNER/REPO  → forwarded to `gh pr diff` and base-workflow-list
                          fetches; defaults to cwd-resolved repo
    --base BASE        → defaults to `main`
    --head HEAD        → defaults to `git rev-parse --abbrev-ref HEAD` in cwd

Coverage logic
==============

Strict (`pull_request.paths:` filter coverage):
    1. List the BASE branch's `.github/workflows/*.yml` files.
    2. For each workflow, parse `on.pull_request.paths` (and the equivalent
       `on.pull_request.paths-ignore` complement). Build the union of paths
       covered by at least one workflow's filter.
    3. List the PR diff's files under `.github/workflows/**`.
    4. For each PR-diff workflow file, check coverage:
       - The file's path matches one of the BASE workflows' `paths:` patterns
         (after fnmatch / `**` glob expansion), OR
       - At least one BASE workflow has NO `pull_request.paths:` filter
         (the bare `on: pull_request:` form matches everything), OR
       - At least one BASE workflow has `'.github/workflows/**'` in its
         `paths:` filter (canonical coverage)
    5. If ANY PR-diff workflow file is uncovered → block with a remediation
       message that names the file + suggests adding `'.github/workflows/**'`
       to a covering workflow's `paths:`.

Out of scope for v1
===================

- Net-zero infra-revert orphan detection (`statusCheckRollup: []` + non-base
  HEAD). Filed as a follow-up — requires comparing post-revert state against
  PR-open-time base in a way that's harder to do correctly at hook time
  without re-running the GitHub paths-filter evaluator.
- Cross-repo workflow inheritance (reusable workflows via
  `workflow_call`/`uses:`). The hook checks only the immediate repo's
  workflows; reusable workflows in other repos are reviewer responsibility.
- `paths-ignore` exclusion semantics — for v1, treat `paths-ignore` as a
  signal that the workflow MIGHT cover the file (lower-confidence; never
  blocks on its presence). Future hardening: implement the full
  GitHub-paths-filter algebra.

Promotion provenance
====================

P2W10 retro-candidate (2026-04-24, deploy#153). Filed as #203 sibling of
#200 (charter: pull_request triggers must include wave branches —
different layer of the same trigger-gap class).

Exit codes:
    0 — allow (not a `gh pr create` / `gh pr ready`, no workflow-file in
        diff, all workflow files covered, or any infrastructure failure
        that prevents a confident decision — fail-open)
    2 — block (workflow file uncovered, with remediation message)
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shell_parse import (  # noqa: E402
    find_gh_subcommand,
    iter_command_segments,
    resolve_invocation_cwd,
    strip_heredocs,
    tokenize,
)
from annunaki_log import log_pretooluse_block  # noqa: E402

# --- Command-shape matchers -------------------------------------------------

_GH_PR_GATE_ACTIONS = {"create", "ready"}

# Regex fallback used only when shlex tokenization fails (unbalanced quotes,
# malformed input). Intentionally kept so the hook degrades to the old
# substring-match path rather than silently allowing on parse failure.
_GH_PR_GATE_RE = re.compile(
    r"(?:^|[;&|]\s*|&&\s*|\|\|\s*)\s*"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*"
    r"gh\s+pr\s+(?:create|ready)\b",
    re.MULTILINE,
)


def _is_gh_pr_gate_command(command: str) -> bool:
    """True if any segment of `command` is a `gh pr create` or `gh pr ready` call.

    Uses _shell_parse.tokenize + find_gh_subcommand for command-position detection.
    Falls back to regex on shlex parse failure (fail-open for the gate check:
    a false negative just means we proceed to the coverage check).
    Inherits _shell_parse.tokenize() line-continuation normalization from #305.
    """
    cleaned = strip_heredocs(command)
    tokens = tokenize(cleaned)
    if tokens is None:
        return bool(_GH_PR_GATE_RE.search(command))
    for segment in iter_command_segments(tokens):
        result = find_gh_subcommand(segment)
        if result is None:
            continue
        _globals, rest = result
        if len(rest) >= 2 and rest[0] == "pr" and rest[1] in _GH_PR_GATE_ACTIONS:
            return True
    return False


def _walk_flag_value(tokens: list[str], flag: str) -> str | None:
    """Return the first value of `--flag` found in `tokens`, or None.

    Handles `--flag value` (two tokens) and `--flag=value` (one token).
    Only matches tokens in flag position — never inside quoted values of
    other flags (shlex has already collapsed those to single tokens).
    """
    for i, tok in enumerate(tokens):
        if tok == f"--{flag}" and i + 1 < len(tokens):
            return tokens[i + 1]
        if tok.startswith(f"--{flag}="):
            return tok[len(flag) + 3 :]
    return None


def _extract_flag(command: str, flag: str) -> str | None:
    """Return the value of --flag from `command`, or None if absent.

    Tokenizes with _shell_parse.tokenize() so flag values inside quoted
    --body strings or heredocs cannot masquerade as --repo/--base/--head.
    Falls back to a regex scan on shlex parse failure (fail-open: a false
    negative means we fall back to the default value in callers).
    """
    cleaned = strip_heredocs(command)
    tokens = tokenize(cleaned)
    if tokens is None:
        f = re.escape(flag)
        pat = rf"--{f}(?:=|\s+)([^\s'\"]+)" rf"|--{f}\s+\"([^\"]+)\"" rf"|--{f}\s+'([^']+)'"
        m = re.search(pat, command)
        if not m:
            return None
        for grp in m.groups():
            if grp:
                return grp
        return None
    return _walk_flag_value(tokens, flag)


# --- Workflow paths filter parsing ------------------------------------------


def _parse_workflow_paths(yml_text: str) -> tuple[set[str], bool]:
    """Parse a workflow YAML and return (paths_set, has_pull_request_no_paths).

    Returns:
        paths_set: set of glob patterns from `on.pull_request.paths:`
            (empty set if the workflow has no pull_request trigger,
             or has pull_request but no paths filter).
        has_pull_request_no_paths: True if the workflow has an `on.pull_request:`
            trigger WITHOUT a `paths:` filter (matches all paths). When True,
            ANY workflow-file change is considered covered by this workflow.

    No external YAML library used; the parser is regex-based for two reasons:
    (1) the hook ships in `.claude/hooks/` and the dispatcher loads it via
    `importlib.import_module` — adding a YAML dependency would be the first
    such dep across all hooks. (2) the paths-filter shape is mechanical
    enough for line-by-line state-machine parsing. Caveat: this parser does
    NOT handle every YAML variation (multi-line flow mappings, anchors, etc.)
    — it handles the canonical block-style form used by every workflow in
    the org today. Anything it can't parse → returns (set(), False) =
    "no coverage signal" = conservative.
    """
    lines = yml_text.splitlines()
    in_on = False
    in_pr = False
    in_pr_paths = False
    pr_has_paths_key = False
    paths: set[str] = []  # type: ignore[assignment]
    paths = set()
    on_indent = -1
    pr_indent = -1
    paths_indent = -1

    for raw in lines:
        # Strip comments and trailing whitespace.
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        # Detect entering / leaving `on:` block.
        if not in_on:
            if re.match(r"^on\s*:\s*$", stripped):
                in_on = True
                on_indent = indent
                continue
            # Inline form `on: [push, pull_request]` — pull_request matches
            # everything (no paths filter possible in this form).
            if re.match(r"^on\s*:\s*\[", stripped) and "pull_request" in stripped:
                return set(), True
            # Inline form `on: pull_request` — matches everything.
            if re.match(r"^on\s*:\s*pull_request\s*$", stripped):
                return set(), True
            continue

        # Inside `on:` block.
        if indent <= on_indent:
            # Symmetric with the sibling-boundary case (line 220-227) and the
            # EOF case (line 256-258): if we exit `on:` while still inside
            # `pull_request:` with no `paths:` key seen, that's covers-all.
            # Without this guard, workflows where `pull_request:` is the LAST
            # child of `on:` are misparsed as covering-nothing (#289).
            if in_pr and not pr_has_paths_key:
                return set(), True
            in_on = False
            in_pr = False
            in_pr_paths = False
            # Re-evaluate this line as a top-level
            if re.match(r"^on\s*:\s*$", stripped):
                in_on = True
                on_indent = indent
            continue

        if not in_pr:
            if stripped.startswith("pull_request:"):
                # Could be `pull_request:` (block) or `pull_request: ...` (inline).
                rest = stripped[len("pull_request:") :].strip()
                if rest:
                    # Inline form (rare); treat as no-paths-filter coverage.
                    return set(), True
                in_pr = True
                pr_indent = indent
                pr_has_paths_key = False
            continue

        # Inside `on.pull_request:` block.
        if indent <= pr_indent:
            in_pr = False
            in_pr_paths = False
            # Did we exit pull_request without seeing a `paths:` key?
            # Then this workflow's pull_request matches all paths.
            if not pr_has_paths_key:
                return set(), True
            # Else — paths_set already populated; fall through.
            continue

        if not in_pr_paths:
            if stripped.startswith("paths:"):
                pr_has_paths_key = True
                rest = stripped[len("paths:") :].strip()
                if rest.startswith("[") and rest.endswith("]"):
                    # Inline list form: paths: ["a/**", "b/**"]
                    inner = rest[1:-1]
                    for item in re.findall(r"['\"]([^'\"]+)['\"]", inner):
                        paths.add(item)
                else:
                    in_pr_paths = True
                    paths_indent = indent
            elif stripped.startswith("paths-ignore:"):
                # Ignore-form: do nothing; do NOT mark as covered.
                pass
            continue

        # Inside `on.pull_request.paths:` block-list.
        if indent <= paths_indent:
            in_pr_paths = False
            continue
        m = re.match(r"^-\s*['\"]?([^'\"]+?)['\"]?\s*$", stripped)
        if m:
            paths.add(m.group(1).strip())

    # If we ended still inside pull_request without seeing paths, no-filter coverage.
    if in_pr and not pr_has_paths_key:
        return set(), True

    return paths, False


def _path_matches_any_glob(path: str, globs: set[str]) -> bool:
    """True if `path` matches any glob in `globs` (GitHub-style `**` semantics)."""
    for g in globs:
        # GitHub workflow paths uses `**` for any-depth match. Python's
        # fnmatch doesn't natively distinguish `*` and `**`, but for the
        # path-level matching we care about, fnmatch with the glob pattern
        # converted to a Python re-able pattern is sufficient. The
        # canonical `.github/workflows/**` pattern resolves to a path-prefix
        # match against `.github/workflows/`.
        if fnmatch.fnmatch(path, g):
            return True
        # Convert `**` to `*` for fnmatch fallback (loose; over-matches).
        loose = g.replace("**", "*")
        if fnmatch.fnmatch(path, loose):
            return True
    return False


# --- Repo / branch resolution ----------------------------------------------


def _resolve_repo(command: str, cwd: str | None = None) -> str | None:
    """Return OWNER/REPO from --repo flag, or from `cwd`'s git remote.

    `cwd` anchors `git remote get-url origin` so a worktree subagent's
    `gh pr create` resolves ITS repo, not the hook's parent-process repo
    (#521). Falls back to a `GH_REPO` env-var fast-path before cwd
    resolution — gh's own canonical implicit-repo override.
    """
    explicit = _extract_flag(command, "repo")
    if explicit:
        return explicit
    env_repo = (os.environ.get("GH_REPO") or "").strip()
    if env_repo:
        parts = env_repo.split("/")
        if len(parts) == 2 and all(parts):
            return env_repo
        if len(parts) == 3 and all(parts):  # HOST/OWNER/REPO
            return "/".join(parts[1:])
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=cwd,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    url = (result.stdout or "").strip()
    m = re.search(r"github\.com[:/]([^/]+/[^/.\s]+?)(?:\.git)?/?$", url)
    if m:
        return m.group(1)
    return None


def _resolve_base(command: str) -> str:
    return _extract_flag(command, "base") or "main"


def _resolve_head(command: str, cwd: str | None = None) -> str | None:
    """Return --head value, or the current branch in `cwd`.

    `cwd` anchors `git rev-parse --abbrev-ref HEAD` so a worktree subagent
    reads ITS branch, not the hook's parent-process branch (#521).
    """
    explicit = _extract_flag(command, "head")
    if explicit:
        # Strip OWNER: prefix on cross-fork PRs.
        if ":" in explicit:
            return explicit.split(":", 1)[1]
        return explicit
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=cwd,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    name = (result.stdout or "").strip()
    return name or None


# --- API: list base workflows + PR diff -------------------------------------


def _list_base_workflows(repo: str, base: str) -> list[str] | None:
    """List paths of `.yml`/`.yaml` files under `.github/workflows/` on the base ref.

    Returns None on API failure (treated as fail-open by callers).
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/contents/.github/workflows?ref={base}",
                "--jq",
                '.[] | select(.type == "file") | .path',
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    paths = [p.strip() for p in result.stdout.splitlines() if p.strip()]
    return [p for p in paths if p.endswith(".yml") or p.endswith(".yaml")]


def _fetch_workflow_yml(repo: str, base: str, path: str) -> str | None:
    """Fetch the contents of a workflow file on the base ref. None on failure."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/contents/{path}?ref={base}", "--jq", ".content"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    import base64

    try:
        return base64.b64decode(result.stdout.strip()).decode("utf-8", errors="replace")
    except (ValueError, OSError):
        return None


def _list_pr_diff_files(repo: str, base: str, head: str) -> list[str] | None:
    """List file paths in the PR diff (base...head). None on failure."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/compare/{base}...{head}", "--jq", ".files[].filename"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    return [p.strip() for p in result.stdout.splitlines() if p.strip()]


# --- Coverage decision -----------------------------------------------------


def _is_workflow_file(path: str) -> bool:
    """True if `path` is under `.github/workflows/` and ends with .yml/.yaml."""
    return path.startswith(".github/workflows/") and (
        path.endswith(".yml") or path.endswith(".yaml")
    )


def _build_coverage_signal(repo: str, base: str) -> tuple[set[str], bool] | None:
    """Build the org-wide paths-filter union for the BASE branch's workflows.

    Returns (covered_globs, any_no_paths_pr_trigger):
        covered_globs: union of all `on.pull_request.paths:` patterns.
        any_no_paths_pr_trigger: True if ANY workflow has `on.pull_request:`
            without a `paths:` filter (matches all paths — covers everything).

    Returns None on infrastructure failure (caller fails open).
    """
    workflows = _list_base_workflows(repo, base)
    if workflows is None:
        return None
    union: set[str] = set()
    any_no_paths = False
    for wf_path in workflows:
        yml = _fetch_workflow_yml(repo, base, wf_path)
        if yml is None:
            continue
        paths, no_paths = _parse_workflow_paths(yml)
        union |= paths
        if no_paths:
            any_no_paths = True
    return union, any_no_paths


# --- Public entry points ---------------------------------------------------


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry. None to allow, dict to block."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None
    command = input_data.get("tool_input", {}).get("command", "")
    if not _is_gh_pr_gate_command(command):
        return None

    cwd = resolve_invocation_cwd(input_data)
    repo = _resolve_repo(command, cwd=cwd)
    base = _resolve_base(command)
    head = _resolve_head(command, cwd=cwd)
    if not repo or not head:
        # Cannot determine PR scope → fail open. We don't block on our own
        # inability to resolve the args.
        return None

    diff_files = _list_pr_diff_files(repo, base, head)
    if diff_files is None:
        return None  # API failure → fail open

    workflow_files_in_diff = [p for p in diff_files if _is_workflow_file(p)]
    if not workflow_files_in_diff:
        return None  # No .github/workflows/** changes → no orphan possible

    coverage = _build_coverage_signal(repo, base)
    if coverage is None:
        return None  # API failure → fail open
    covered_globs, any_no_paths = coverage

    if any_no_paths:
        # At least one workflow's `on.pull_request:` has no paths filter →
        # ANY change in the diff is covered. Allow.
        return None

    # Check each workflow file in the diff for coverage.
    uncovered: list[str] = []
    for path in workflow_files_in_diff:
        if _path_matches_any_glob(path, covered_globs):
            continue
        # Special case: a path in the diff that is itself a workflow whose
        # OWN `paths:` filter covers it self-validates. We don't have the
        # PR head's version of the workflow yet (would need a separate
        # gh api fetch on head). For v1, only the BASE-branch coverage
        # signal is consulted — adding a new self-validating workflow in
        # the same PR doesn't satisfy this hook. The reviewer can either
        # (a) add `.github/workflows/**` to a base workflow's paths filter
        # in a precursor PR, OR (b) include the precursor change in this
        # same PR (still needs the BASE coverage to land first via two-PR
        # sequencing). Documented in the block message.
        uncovered.append(path)

    if not uncovered:
        return None

    files_list = "\n  - ".join(uncovered)
    reason = (
        f"BLOCKED: {len(uncovered)} workflow file(s) in this PR are NOT covered by any "
        f"`on.pull_request.paths:` filter on the base branch ({base}):\n  - {files_list}\n\n"
        f"Without paths-filter coverage, GitHub will silently skip CI on these workflow "
        f"changes. Per charter `pull-requests.md` § CI Workflow `pull_request` Triggers Must "
        f"Cover Wave Branches (sibling rule for this orphan class):\n\n"
        f"Either:\n"
        f"  (a) Add `'.github/workflows/**'` to one of the base workflows' "
        f"`on.pull_request.paths:` filter in a PRECURSOR PR (recommended — establishes "
        f"the coverage baseline), OR\n"
        f"  (b) Add a workflow with `on.pull_request:` and NO `paths:` filter (covers "
        f"everything, including future workflow files), OR\n"
        f"  (c) Confirm the change does not need CI (rare — e.g., comment-only edits) and "
        f"pass `--admin` at merge time.\n"
    )
    return {"decision": "block", "reason": reason}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    result = check(input_data)
    if result is None:
        sys.exit(0)
    print(json.dumps(result))
    if result.get("decision") == "block":
        log_pretooluse_block(
            "validate_workflow_paths_coverage",
            (input_data.get("tool_input") or {}).get("command", ""),
            result["reason"],
        )
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
