#!/usr/bin/env python3
"""PreToolUse hook: Verify cited file paths at origin before applying wave labels.

Three-occurrence W8 pattern (deploy#276, isnad-graph#866-870, audit-re-framing
#871): issue bodies assert artifact state X (file path) that is false at origin
head_sha at the time of wave-labeling. Manual review caught some; missed cases
consumed implementer-spawn cycles.

Per `feedback_enforcement_hierarchy.md` (hook > skill > charter), promote
from manager-discipline to PreToolUse hook.

Input Language:
  Fires on: PreToolUse Bash
  Matches:
    gh issue create [--repo R] ... --label '...p<N>-wave-<M>...'
    gh issue edit <NUM> [--repo R] ... --add-label '...p<N>-wave-<M>...'
  Does NOT match: gh issue list/view, gh label create, gh pr create.

Algorithm:
  1. Tokenize command via the shared `_shell_parse` tokenizer (segment-aware,
     line-continuation-normalized, heredoc-stripped) — NOT a private shlex
     reimplementation. Flag VALUES are extracted via `walk_flag_values` and
     `_repo_flag_parse.extract_repo`, so label-shaped / repo-shaped tokens in
     `--body`/`--body-file` content cannot leak into extraction (main#663
     gh-command parser invariant — see `charter/hooks.md`).
  2. Detect wave-label application (regex `p\\d+-wave-\\d+` in any --label /
     --add-label value).
  3. Resolve the target repo. When `--repo`/`-R` is OMITTED (in-repo
     invocation, gh's ambient-git-context resolution), recover it from the
     invocation cwd's `origin` via `resolve_repo_short_name` (mirroring gh)
     instead of falling through to the old empty-default-repo `noorinalabs/`
     slug (the #650/#659 ambient-omitted class — MUST #2 of the invariant).
     If the ambient repo is unresolvable, log a `skip_no_repo_context`
     diagnostic and ALLOW (fail-open) — never a silent drop.
  4. Resolve issue body:
       - gh issue create: from --body, --body-file, or stdin (skip if neither)
       - gh issue edit:   from `gh api repos/{repo}/issues/{num} --jq .body`
  4. If body contains `Origin-Verification:` line → ALLOW (override).
  5. Else extract cited Python file paths via regex.
  6. If no cited paths → ALLOW (nothing to verify; pure-policy issue).
  7. For each cited path, check existence at:
       - origin/main:                  gh api .../contents/<path>?ref=main
       - origin/deployments/phase-<N>/wave-<M>: same but at wave branch
  8. If EVERY cited path 404s at BOTH refs → BLOCK with override directive.
  9. Else ALLOW (at least one path verified).

Override: include `Origin-Verification: <reason>` in issue body. The hook
performs a substring match — typical values: `Origin-Verification: <path>
exists at <ref>`, or `Origin-Verification: not-applicable` for policy issues.

Exit codes:
  0 — allow (not a wave-label command, no cited paths, override present, or
      at least one path verified)
  2 — block (wave-label command with cited paths and none verify at origin)
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo_flag_parse import extract_repo  # noqa: E402
from _shell_parse import (  # noqa: E402
    find_gh_subcommand,
    iter_command_segments,
    resolve_repo_short_name,
    strip_heredocs,
    tokenize,
    walk_flag_values,
)
from _wave_label_parse import is_wave_label, parse_wave_label_spec  # noqa: E402
from annunaki_log import log_pretooluse_block, log_pretooluse_diagnostic  # noqa: E402

# cross-repo-status.json lives at the noorinalabs-main repo root, two levels up
# from `.claude/hooks/`. Used to recover the (derived-display) phase for the new
# phase-agnostic `wave-{X}` label form (#810) when building the wave branch ref.
_STATUS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "cross-repo-status.json",
)


def _read_status_phase() -> int | None:
    """Return the active phase number from cross-repo-status.json, or None.

    The new `wave-{X}` label form carries no phase (Design B #804 made phase a
    derived display). To build the `deployments/phase-{P}/wave-{X}` branch ref
    for the second existence check, recover the phase from status. Returns None
    on any failure (missing/malformed file, missing/unparseable `phase`); the
    caller then checks `main` only — never a hard failure.
    """
    try:
        with open(_STATUS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    # Prefer `current_phase` (the live integer); fall back to the `phase-{N}`
    # string. (`phase` can lag `current_phase` — see the stale-pointer note in
    # /wave-kickoff SKILL.md.)
    cp = data.get("current_phase")
    if cp is not None:
        try:
            return int(cp)
        except (TypeError, ValueError):
            pass
    m = re.fullmatch(r"phase-(\d+)", str(data.get("phase", "")))
    if m:
        return int(m.group(1))
    return None


# Python paths in the .claude tree (hooks, skills, tests). Broad-enough to catch
# the W8 reproducer shape `noorinalabs-isnad-graph/.claude/hooks/<name>.py`
# AND child-repo source files. Tightening to specific subdirs avoids matching
# arbitrary `foo.py` mentions in prose.
_CITED_PATH_RE = re.compile(
    r"\b(?:noorinalabs-[a-z-]+/)?\.claude/[a-z][a-z0-9_/-]*\.py\b"
    r"|\bnoorinalabs-[a-z-]+/(?:src|tests)/[a-z][a-z0-9_/.-]*\.py\b"
)

_OVERRIDE_RE = re.compile(r"^Origin-Verification:\s*\S", re.MULTILINE)


def _find_issue_command(command: str) -> tuple[str, str | None, list[str]] | None:
    """Locate the first `gh issue create` / `gh issue edit <NUM>` segment.

    Routes through the shared `_shell_parse` primitives (heredoc-strip,
    line-continuation-aware tokenize, segment split, gh-subcommand locate)
    rather than a private shlex reimplementation (main#663 invariant). This
    also gains the #287 backslash-line-continuation fix the old private
    `_tokenize` lacked.

    Returns `(kind, issue_number, rest_tokens)` where `kind` is `"create"` or
    `"edit"`, `issue_number` is the bare positional after `edit` (else None),
    and `rest_tokens` is the post-`gh` token tail (e.g.
    `["issue", "create", "--label", ...]`). Returns None when no matching
    segment is present or the command does not tokenize.
    """
    tokens = tokenize(strip_heredocs(command))
    if tokens is None:
        return None
    for segment in iter_command_segments(tokens):
        gh = find_gh_subcommand(segment)
        if gh is None:
            continue
        _globals, rest = gh
        if len(rest) >= 2 and rest[0] == "issue" and rest[1] == "create":
            return "create", None, rest
        if len(rest) >= 3 and rest[0] == "issue" and rest[1] == "edit" and rest[2].isdigit():
            return "edit", rest[2], rest
    return None


def _collect_labels(rest: list[str], flags: set[str]) -> list[str]:
    """Return label values for `flags`, splitting gh's comma-separated form.

    `walk_flag_values` scopes extraction to the actual flag VALUES (never
    label-shaped tokens inside `--body`); gh additionally accepts a single
    `--label a,b,c` token, so each value is comma-split here.
    """
    out: list[str] = []
    for raw in walk_flag_values(rest, flags):
        out.extend(p for p in raw.split(",") if p)
    return out


def _first_value(rest: list[str], flags: set[str]) -> str | None:
    """First value for any single-value flag in `flags`, or None."""
    values = walk_flag_values(rest, flags)
    return values[0] if values else None


def _read_body_file(path: str) -> str | None:
    """Read body content from --body-file path. Returns None on any error."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _resolve_issue_body_for_edit(issue_num: str, repo: str | None) -> str | None:
    """Fetch the issue body for `gh issue edit` matcher. None on any error."""
    args = ["gh", "issue", "view", issue_num, "--json", "body", "--jq", ".body"]
    if repo:
        args.extend(["--repo", repo])
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return None
        return r.stdout
    except (subprocess.TimeoutExpired, OSError):
        return None


def _path_exists_at_ref(repo: str, path: str, ref: str) -> bool:
    """Check `gh api .../contents/<path>?ref=<ref>`. True if 200, False if 404."""
    args = [
        "gh",
        "api",
        f"repos/{repo}/contents/{path}",
        "-f",
        f"ref={ref}",
        "--silent",
    ]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _extract_repo_for_path(path: str, default_repo: str) -> tuple[str, str]:
    """If path starts with `noorinalabs-X/`, that's the repo; rest is the
    in-repo path. Otherwise the path is in `default_repo`."""
    if path.startswith("noorinalabs-"):
        slash = path.find("/")
        if slash > 0:
            return path[:slash], path[slash + 1 :]
    if "/" in default_repo:
        return default_repo, path
    return f"noorinalabs/{default_repo}", path


def check(input_data: dict) -> dict | None:
    """Hook entrypoint. Returns None to allow, dict with block decision to block."""
    if input_data.get("tool_name") != "Bash":
        return None
    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return None

    found = _find_issue_command(command)
    if found is None:
        return None
    kind, issue_num, rest = found
    is_create = kind == "create"

    label_flags = {"--label", "-l"} if is_create else {"--add-label"}
    labels = _collect_labels(rest, label_flags)
    # Accept ALL wave-label forms (#810): legacy `p{N}-wave-{M}`, phase-agnostic
    # `wave-{X}`, and the `wave-x` placeholder — via the shared anchored grammar
    # so a new-form label can't bypass the cited-path evidence gate.
    wave_label = next(
        (lbl for lbl in labels if is_wave_label(lbl)),
        None,
    )
    if not wave_label:
        return None

    # Resolve the target repo. `--repo`/`-R` is OPTIONAL: an in-repo
    # `gh issue create/edit` relies on gh's ambient-git-context resolution and
    # carries no `--repo` token. Recover that case from the invocation cwd's
    # origin (main#663 invariant MUST #2) instead of the old empty-default
    # `noorinalabs/` slug. If the ambient repo is unresolvable, log a skip
    # diagnostic and fail-open (allow) — never a silent drop.
    repo = extract_repo(command)
    if not repo:
        short = resolve_repo_short_name(input_data)
        if not short:
            log_pretooluse_diagnostic(
                "validate_wave_label_evidence",
                command,
                {"skip": "skip_no_repo_context", "wave_label": wave_label},
            )
            return None
        repo = f"noorinalabs/{short}"

    # Resolve issue body
    body: str | None = None
    if is_create:
        body = _first_value(rest, {"--body"})
        if body is None:
            bf = _first_value(rest, {"--body-file", "-F"})
            if bf:
                body = _read_body_file(bf)
    elif issue_num is not None:
        body = _resolve_issue_body_for_edit(issue_num, repo)

    if not body:
        return None  # Nothing to verify against

    # Override path
    if _OVERRIDE_RE.search(body):
        return None

    # Extract cited paths
    cited_paths = list(set(_CITED_PATH_RE.findall(body)))
    if not cited_paths:
        return None  # No paths to verify

    # Resolve wave branch ref. Legacy `p{N}-wave-{M}` carries the phase inline;
    # the new `wave-{X}` form (#810) does not, so recover the phase from
    # cross-repo-status.json. If the phase is unavailable (or the label is the
    # `wave-x` placeholder with no wave id), wave_branch stays None and only
    # `main` is checked — a graceful degradation, never a hard failure.
    spec = parse_wave_label_spec(wave_label)
    phase_num = spec.phase if spec else None
    wave_num = spec.wave if spec else None
    if phase_num is None and wave_num is not None:
        phase_num = _read_status_phase()
    wave_branch = (
        f"deployments/phase-{phase_num}/wave-{wave_num}"
        if phase_num is not None and wave_num is not None
        else None
    )

    # Verify each cited path at origin
    unverified: list[str] = []
    for path in cited_paths:
        path_repo, inner_path = _extract_repo_for_path(path, repo)
        exists_at_main = _path_exists_at_ref(path_repo, inner_path, "main")
        exists_at_wave = (
            _path_exists_at_ref(path_repo, inner_path, wave_branch) if wave_branch else False
        )
        if not (exists_at_main or exists_at_wave):
            unverified.append(path)

    if unverified == cited_paths:
        # EVERY cited path 404'd at BOTH refs — block
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: wave-label `{wave_label}` would be applied to an issue "
                f"whose body cites file paths that do NOT exist at origin.\n"
                f"Unverified paths (404 at both `main` and `{wave_branch}`):\n"
                + "\n".join(f"  - {p}" for p in unverified)
                + "\n\n"
                "Three-occurrence W8 pattern (deploy#276, isnad-graph#866-870, "
                "PR#871 stale-worktree) — issue body asserts state X, origin head_sha "
                "shows X doesn't exist. Manual review caught some; this hook catches "
                "the rest before implementer spawns are wasted.\n\n"
                "Fix-forward options:\n"
                "  (a) Verify the path EXISTS at origin and update the issue body to "
                "cite a real one; OR\n"
                "  (b) If the path is intentionally not-yet-existing (e.g., proposed "
                "new hook), add `Origin-Verification: not-applicable — <reason>` to "
                "the issue body; OR\n"
                "  (c) If the path exists at a non-standard ref, add\n"
                "      `Origin-Verification: <path> exists at <ref>` to the body.\n"
                "See main#337 for the rule + override path."
            ),
        }
        log_pretooluse_block("validate_wave_label_evidence", command, result["reason"])
        return result

    return None


if __name__ == "__main__":
    data = json.load(sys.stdin)
    result = check(data)
    if result is None:
        sys.exit(0)
    print(json.dumps(result))
    sys.exit(2 if result.get("decision") == "block" else 0)
