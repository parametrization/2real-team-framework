#!/usr/bin/env python3
"""PreToolUse hook: HARD pre-review gate — new behavior needs a load-bearing test.

Story: Phase 6 Wave 2 S2, issue #167 (meta #165). All three Wave-1 must-fixes were
the same failure class: new behavior shipped without a revert->fail (load-bearing)
test, caught only at QA review. This hook moves that check to the left of review by
gating the review-request action itself (`gh pr create` / `gh pr ready`).

Fail-CLOSED, by design (contrast with the rest of this repo's hooks)
=====================================================================

Every other hook in this dispatcher fails OPEN on an infrastructure failure (a
missing module, a `gh api` timeout, an unresolvable repo) per the framework's
documented stdlib-only / fail-open philosophy (see `_framework_config.py` and
`charter/hooks.md`). This gate is the deliberate, owner-approved exception for the
review-request path (#167): an unverifiable PR diff must not silently pass a check
whose entire purpose is to stop unverified behavior from reaching review. So:

  - Cannot resolve `--repo` / head branch -> BLOCK (not allow).
  - `gh api compare` fails (network, auth, rate limit) -> BLOCK (not allow).
  - Diff shows a "new behavior" file with no accompanying test-file change -> BLOCK.

The only way past any of the three is the documented override (see below) — never
a silent bypass.

Detection signal (v1 — lightweight, deterministic, NOT semantic)
==================================================================

This hook cannot literally revert the PR's source and re-run the test suite inside
a PreToolUse gate (too slow/fragile for a hard interactive gate, and out of scope
per the story's "keep it lightweight and deterministic" guidance). It instead
enforces the mechanical PRECONDITION for a load-bearing test to exist at all: if
the diff (base...head) adds a substantive line to a *behavior* file (a `.py` file
under one of `_BEHAVIOR_ROOTS`, excluding test files), the SAME diff must also add
a substantive line to a test file PAIRED to that specific behavior file (#174 —
see "Per-file pairing" below). "Substantive" excludes blank lines and
Python-comment-only lines, so pure formatting/comment churn doesn't count on
either side of that ledger.

This is a proxy, not a proof: it cannot verify the touched test is actually
load-bearing (revert->fail) or that it covers the specific new behavior — that
judgment call remains the author's self-check duty (the story's documented
pre-review gate, see charter/pull-requests.md) and QA's review-time verification
(charter/pull-requests.md § Review Workflow). What it DOES mechanically guarantee:
a PR cannot open review claiming "new behavior, zero test changes" — the single
failure pattern that produced all three Wave-1 must-fixes.

Per-file pairing (v2, #174 — Wave 3 S2)
==========================================

v1 (#167) treated ANY substantive test-file change anywhere in the diff as
satisfying the WHOLE diff: a PR touching `hooks/foo.py` (new behavior) and
`lib/bar.py` (new behavior) with a test change only for `foo` let `bar.py`'s new
behavior through completely ungated. Pairing is now checked PER BEHAVIOR FILE —
each new-behavior file must have its OWN corresponding substantive test-file
change, not just any test-file change somewhere in the diff.

A behavior file `X` counts as paired if the diff also substantively touches a
test file that is:

  1. named `test_<stem>.py` or `<stem>_test.py` for `X`'s stem — the "mapped
     test path" for a separate-tree test layout (this repo's own convention:
     `framework/assets/hooks/foo.py` <-> `framework/tests/test_foo.py`), OR
  2. in the SAME DIRECTORY as `X` — for repos (this framework installs into
     many) that co-locate tests beside source instead of a separate tree, OR
  3. `conftest.py` — shared pytest fixture infrastructure isn't "for" any one
     behavior file, so a substantive conftest change is accepted for every
     behavior file in the diff.

Chosen granularity: PER-FILE, not per-directory. This repo's own behavior roots
(`framework/assets/hooks/`, `framework/assets/lib/`, etc.) each hold many
independently-reviewed, independently-tested modules that all share one test
root (`framework/tests/`) — a per-DIRECTORY bucket would still let module A's
test satisfy module B's new behavior whenever A and B share a behavior root,
reproducing the exact loophole #174 exists to close. Per-file pairing is the
only granularity that actually closes it for this project's own layout, while
rule 2 (same-dir) keeps the check meaningful for repos with a different,
co-located layout.

Known limitation: rule 1 requires the `test_<stem>.py` / `<stem>_test.py` naming
convention. Existing modules that predate this convention and aren't named that
way (and aren't covered by rule 2 or 3) will need a test renamed/added the next
time they gain new behavior, or can use the documented override (below) if the
change is genuinely test-exempt.

Out of scope for v1/v2
========================

- Non-Python behavior surfaces (shell scripts, TS/JS, YAML-driven config) are not
  scanned — `_is_behavior_path` only recognizes `.py` files under the configured
  roots. A PR that only changes those is invisible to this gate (same "out of
  scope" posture as the sibling `validate_workflow_paths_coverage` hook).
- Does not verify the touched test asserts anything about the touched behavior
  (no call-graph / coverage correlation) — file presence + a substantive added
  line is the entire signal.
- Does not execute a revert->fail simulation. See "Detection signal" above.
- Pairing (rule 1) is nominal (filename convention), not import-graph analysis —
  it does not open the test file to confirm it actually imports/exercises the
  behavior module (would require fetching full file content, not just the diff
  patch already available from the compare API, for every touched test file).

Override — deliberate, documented, audited
============================================

Mirrors the existing `ADMIN_MERGE_EXCEPTION` convention in
`validate_pr_ci_status.py` exactly, under a distinct env var so the two gates'
override audiences never collide:

    LOAD_BEARING_TEST_EXCEPTION="<class>:<rationale>" gh pr create ...

`<class>` must be a key in `policy.load_bearing_test_exceptions` (a map of
class -> human rationale) and `<rationale>` must be non-empty. This map ships
PRE-SEEDED with two classes: `refactor` (#176 — Wave 3 S3), a pure refactor /
no external-behavior-change PR has no new behavior to cover, so the hard-block
posture with zero configured bypass classes was a dead end for that legitimate
case; and `docs` (#284 — see "Automatic docs/comment-only exception" below). A
repo may add more classes via its own config — see
`policy.load_bearing_test_exceptions` in `framework.config.schema.json`. An
unrecognized/missing class, or an empty rationale, still blocks — the override
is validated, not a free escape hatch. Every attempted override (valid or not)
is logged via `_framework_log.log_pretooluse_block` for the audit trail.

Automatic docs/comment-only exception (#284)
===============================================

The manual override above still requires a human to type a rationale for
every PR — fine for a genuine refactor, overkill for a docstring or comment
addition, which has no new behavior to cover in the first place (the Wave 20
case, #279/#284: a docstring cross-reference added to a behavior file tripped
the gate with no way to say "there is nothing to test here" short of the
manual override ceremony). When the repo's config seeds a `docs` class under
`policy.load_bearing_test_exceptions`, a behavior file is exempted from
pairing AUTOMATICALLY, per file, with no env var needed, when EVERY added
line in that file's diff is a comment or part of a docstring (see
`_patch_is_docs_only`) — i.e. the file gained no line that looks like an
executable statement. A single added line that is not blank, a `#` comment,
or docstring content makes the whole file "real code" again and the file
falls back to the normal pairing check; mixing a hidden behavior line into an
otherwise doc-only diff does not get a free pass. This mirrors the
"lightweight, deterministic, not semantic" detection posture used everywhere
else in this module (see "Detection signal" above): no AST parse, just a
per-line scan of the added diff content. Opt-in via the config map, like the
manual override — a repo that forks the schema without the `docs` class keeps
the strict pre-#284 posture (every new behavior line, docstring or not, needs
a paired test or an explicit `LOAD_BEARING_TEST_EXCEPTION` override).

Fires on
========
    PreToolUse Bash
Matches:
    gh pr create [--repo OWNER/REPO] [--base BASE] [--head BRANCH] [...]
    gh pr ready [<number>] [--repo OWNER/REPO]

Command-shape detection, `--repo`/`--base`/`--head` extraction, and the compare-API
fetch shape are reused from the sibling `validate_workflow_paths_coverage` module
(same command surface, same "PreToolUse Bash / gh pr create|ready" gate) rather
than re-implemented — `validate_pr_ci_status.py` already establishes this
cross-hook-module reuse pattern (it imports `_build_coverage_signal` from the same
module) so the parsing logic has exactly one source of truth.

Exit codes:
    0 — allow (not a `gh pr create`/`gh pr ready`, no behavior file with a
        substantive added line in the diff, every such behavior file has its own
        paired test-file change, every remaining unpaired file is docs/comment-
        only under an active `docs` exception (#284), or a validated override
        was supplied)
    2 — block (one or more behavior files lack a paired test-file change, an
        unverifiable diff, or an invalid/unconfigured override attempt)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _framework_config import config  # noqa: E402
from _framework_log import log_pretooluse_block  # noqa: E402
from _shell_parse import resolve_invocation_cwd  # noqa: E402
from validate_workflow_paths_coverage import (  # noqa: E402
    _is_gh_pr_gate_command,
    _resolve_base,
    _resolve_head,
    _resolve_repo,
)

# Deliberately NOT declared `FAIL_OPEN = True` (#175): this hook is the repo's
# documented fail-CLOSED exception (see module docstring), so the dispatcher's
# default posture for an undeclared/crashing hook — block, not allow — is
# exactly what this gate needs. Do not add `FAIL_OPEN` here.

# --- Path classification -----------------------------------------------------

#: Repo-relative path prefixes treated as "behavior" surfaces for this gate's v1
#: scope. A `.py` file under one of these (and not a test file — see
#: `_is_test_path`) counts as "new behavior" when it gains a substantive line.
_BEHAVIOR_ROOTS = (
    "framework/assets/hooks/",
    "framework/assets/lib/",
    "framework/install/",
    "framework/harness/",
    "python/src/",
)

_TEST_DIR_RE = re.compile(r"(?:^|/)tests?/")
_TEST_BASENAME_RE = re.compile(r"^(test_.+|.+_test)\.py$")


def _is_test_path(path: str) -> bool:
    """True if `path` is a test file: under a `test(s)/` dir, or `test_*.py` /
    `*_test.py` / `conftest.py` by name — anywhere, not just under a tests dir
    (mirrors how pytest itself discovers test modules)."""
    basename = path.rsplit("/", 1)[-1]
    if basename == "conftest.py":
        return True
    if _TEST_BASENAME_RE.match(basename):
        return True
    return bool(_TEST_DIR_RE.search(path))


def _is_behavior_path(path: str) -> bool:
    """True if `path` is a `.py` behavior file in scope for this gate (v1)."""
    if not path.endswith(".py"):
        return False
    if _is_test_path(path):
        return False
    if path.rsplit("/", 1)[-1] == "__init__.py":
        return False
    return any(path.startswith(root) for root in _BEHAVIOR_ROOTS)


# --- Diff-substance parsing ---------------------------------------------------

#: A blank line or a Python-comment-only line (v1 scope is Python; see module
#: docstring). Lines matching this are NOT "substantive" on either side of the
#: behavior/test ledger — pure formatting/comment churn never trips the gate.
_TRIVIAL_ADDED_LINE_RE = re.compile(r"^\s*(#.*)?$")


def _added_substantive_lines(patch: object) -> list[str]:
    """Return the added (`+`-prefixed) lines of a unified diff `patch` that are
    NOT blank/comment-only. Empty list for a missing/binary/trivial/non-str patch."""
    if not patch or not isinstance(patch, str):
        return []
    lines: list[str] = []
    for raw in patch.splitlines():
        if raw.startswith("+++"):
            continue
        if not raw.startswith("+"):
            continue
        content = raw[1:]
        if _TRIVIAL_ADDED_LINE_RE.match(content):
            continue
        lines.append(content)
    return lines


def _fetch_compare_files(repo: str, base: str, head: str) -> list[dict] | None:
    """Return the `.files` array of `gh api repos/{repo}/compare/{base}...{head}`.

    Each entry carries at least `filename`, `status`, and (for text files) `patch`.
    Returns None on any failure — caller treats that as fail-CLOSED (see module
    docstring), unlike the sibling coverage hook's fail-open API-failure posture.
    """
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/compare/{base}...{head}", "--jq", ".files"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, list):
        return None
    return data


def _scan_diff(files: list[dict]) -> tuple[list[str], list[str]]:
    """Return (behavior_files_with_substance, test_files_with_substance)."""
    behavior_files: list[str] = []
    test_files: list[str] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        if entry.get("status") == "removed":
            continue
        filename = entry.get("filename", "")
        if not isinstance(filename, str) or not filename:
            continue
        added = _added_substantive_lines(entry.get("patch"))
        if not added:
            continue
        if _is_test_path(filename):
            test_files.append(filename)
        elif _is_behavior_path(filename):
            behavior_files.append(filename)
    return behavior_files, test_files


# --- Per-file pairing (#174) ---------------------------------------------------


def _stem(path: str) -> str:
    """The filename without its `.py` extension."""
    return path.rsplit("/", 1)[-1][:-3]


def _dirname(path: str) -> str:
    """The repo-relative directory portion of `path` (``""`` for a bare filename)."""
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _mapped_test_basenames(behavior_path: str) -> tuple[str, str]:
    """The two test-file basenames `behavior_path`'s stem maps to under the
    `test_<name>.py` / `<name>_test.py` naming convention — the "mapped test
    path" for a separate-tree test layout (see module docstring)."""
    stem = _stem(behavior_path)
    return (f"test_{stem}.py", f"{stem}_test.py")


def _behavior_file_paired(behavior_path: str, test_files: list[str]) -> bool:
    """True if `behavior_path` has its own corresponding substantive test-file
    change among `test_files` — the S2 (#174) per-file pairing check. See the
    module docstring's "Per-file pairing" section for the three pairing rules
    (mapped test-name, same directory, `conftest.py`)."""
    mapped = set(_mapped_test_basenames(behavior_path))
    behavior_dir = _dirname(behavior_path)
    for test_path in test_files:
        basename = test_path.rsplit("/", 1)[-1]
        if basename == "conftest.py":
            return True
        if basename in mapped:
            return True
        if _dirname(test_path) == behavior_dir:
            return True
    return False


# --- Automatic docs/comment-only exception (#284) -----------------------------

#: Recognizes a (stripped) line that OPENS, or entirely IS, a triple-quoted
#: string — the conventional docstring placement this repo (and PEP 257) use,
#: e.g. `"""Summary."""` or a bare `"""` opening a multi-line docstring. A
#: triple-quote appearing mid-line (e.g. `x = """foo"""`, a real assignment)
#: does NOT match — it falls through to the "real code" branch in
#: `_patch_is_docs_only` below. Deliberately naive (no tokenizer — the diff
#: patch is not standalone valid Python) but tight in the direction that
#: matters: it only ever WIDENS what counts as "real code", never narrows it.
_DOCSTRING_OPEN_RE = re.compile(r'^("""|\'\'\')')

#: The `policy.load_bearing_test_exceptions` class key that arms the automatic
#: per-file exception below (see module docstring, "Automatic docs/comment-only
#: exception"). Also usable as a manual `LOAD_BEARING_TEST_EXCEPTION=docs:...`
#: override class once seeded, same as any other configured class.
_DOCS_EXCEPTION_CLASS = "docs"


def _patch_is_docs_only(patch: object) -> bool:
    """True if EVERY added, non-trivial line of `patch` is a `#` comment or
    part of a docstring — i.e. no added line looks like an executable
    statement. Returns False for a missing/binary/non-str patch, or a patch
    with no docstring/comment content at all (nothing to exempt).

    A single added line that is not blank, a comment, or docstring content
    (open/interior/close) makes the WHOLE patch "real code" and returns False
    immediately — a doc-only diff cannot hide a behavior line by mixing it in
    with genuine docstring content.
    """
    if not patch or not isinstance(patch, str):
        return False
    in_docstring = False
    saw_docs_or_comment = False
    for raw in patch.splitlines():
        if raw.startswith("+++") or not raw.startswith("+"):
            continue
        stripped = raw[1:].strip()
        if not stripped:
            continue
        if in_docstring:
            saw_docs_or_comment = True
            if stripped.endswith('"""') or stripped.endswith("'''"):
                in_docstring = False
            continue
        if stripped.startswith("#"):
            saw_docs_or_comment = True
            continue
        opens = _DOCSTRING_OPEN_RE.match(stripped)
        if opens:
            quote = opens.group(1)
            body = stripped[3:]
            saw_docs_or_comment = True
            if not (len(body) >= 3 and body.endswith(quote)):
                in_docstring = True  # unterminated on this line -> multi-line
            continue
        return False
    return saw_docs_or_comment and not in_docstring


def _docs_only_exception_active(input_data: dict) -> bool:
    """True if the repo's config seeds a `docs` class under
    `policy.load_bearing_test_exceptions` (#284) — see module docstring. Opt-in:
    a repo that forks the schema without this class keeps the strict
    pre-#284 posture (every behavior file, docstring-only or not, needs a
    paired test or an explicit override)."""
    exceptions = config(input_data).get("policy.load_bearing_test_exceptions", {}) or {}
    return _DOCS_EXCEPTION_CLASS in exceptions


# --- Override validation (mirrors ADMIN_MERGE_EXCEPTION in
#     validate_pr_ci_status.py, under a distinct env var / config key) --------

_OVERRIDE_ENV_VAR = "LOAD_BEARING_TEST_EXCEPTION"


def _override_raw(input_data: dict) -> str:
    raw = (input_data.get("env", {}) or {}).get(_OVERRIDE_ENV_VAR)
    if raw is None:
        raw = os.environ.get(_OVERRIDE_ENV_VAR, "")
    return (raw or "").strip()


def _validate_override(input_data: dict) -> bool | None:
    """Return True (valid), False (attempted but invalid), or None (not attempted)."""
    raw = _override_raw(input_data)
    if not raw:
        return None
    exceptions = config(input_data).get("policy.load_bearing_test_exceptions", {}) or {}
    cls, sep, rationale = raw.partition(":")
    cls, rationale = cls.strip(), rationale.strip()
    if not exceptions or not sep or cls not in exceptions or not rationale:
        return False
    return True


def _invalid_override_reason(input_data: dict) -> str:
    exceptions = config(input_data).get("policy.load_bearing_test_exceptions", {}) or {}
    valid_list = ", ".join(sorted(exceptions)) if exceptions else "(none configured)"
    raw = _override_raw(input_data)
    return (
        f"BLOCKED: {_OVERRIDE_ENV_VAR} was set but is not a valid override.\n"
        f'Set {_OVERRIDE_ENV_VAR}="<class>:<rationale>" where <class> is one of: '
        f"{valid_list}, and <rationale> is a non-empty justification (logged for audit).\n"
        "With no classes configured under `policy.load_bearing_test_exceptions`, no "
        "override exists — this gate cannot be bypassed silently.\n"
        f"Received {_OVERRIDE_ENV_VAR}={raw!r}."
    )


# --- Decision assembly ---------------------------------------------------------


def _fail_closed_reason(detail: str) -> str:
    return (
        f"BLOCKED (fail-closed): the load-bearing-test pre-review gate could not "
        f"verify this PR's diff ({detail}).\n\n"
        "Unlike most hooks in this repo, this gate is intentionally fail-CLOSED "
        "for the review-request path (S2, #167) — an unverifiable diff must not "
        "silently pass a check whose entire purpose is to stop unverified new "
        "behavior from reaching review.\n\n"
        "Retry once the underlying issue (network / gh auth / rate limit / "
        "unresolvable --repo or --head) is resolved, or — if you are certain "
        "every new behavior in this PR has a load-bearing (revert->fail) test — "
        "use the documented override:\n"
        f'  {_OVERRIDE_ENV_VAR}="<class>:<rationale>" gh pr create ...\n'
        "where <class> is a key configured under `policy.load_bearing_test_exceptions`."
    )


def _no_test_reason(unpaired_files: list[str], repo: str, base: str, head: str) -> str:
    files_list = "\n  - ".join(unpaired_files)
    return (
        f"BLOCKED: this PR ({repo} {base}...{head}) adds new behavior to "
        f"{len(unpaired_files)} file(s) with no test-file change PAIRED to that "
        f"specific file in the same diff:\n  - {files_list}\n\n"
        "Pre-review self-check gate (charter/pull-requests.md § Pre-Review "
        "Self-Check, #167/#174): every new-behavior file needs its OWN "
        "load-bearing (revert->fail) test. Pairing is checked PER FILE, not once "
        "for the whole diff (#174) — a substantive test-file change elsewhere in "
        "this PR does not satisfy the file(s) listed above unless it is named "
        "`test_<name>.py` / `<name>_test.py` for that file's stem, lives in the "
        "same directory as that file, or is `conftest.py`. All three Wave-1 "
        "must-fixes were this exact failure class, caught only at QA; this gate "
        "moves the check to PR-open time.\n\n"
        "Add or extend a paired test for each file above, then retry `gh pr "
        "create`/`gh pr ready`. If this really is test-exempt (e.g. a pure "
        "refactor with no behavior change — note this gate cannot tell that "
        "apart from new behavior with a missing test), use the documented "
        "override:\n"
        f'  {_OVERRIDE_ENV_VAR}="<class>:<rationale>" gh pr create ...\n'
        "where <class> is a key configured under `policy.load_bearing_test_exceptions` "
        "(ships pre-seeded with a `refactor` class, #176)."
    )


def _blocked_with_override_check(input_data: dict, command: str, reason: str) -> dict:
    """Apply the override to a would-be block. Every path (authorized override,
    invalid override, or the original block) is logged for the audit trail."""
    verdict = _validate_override(input_data)
    if verdict is True:
        raw = _override_raw(input_data)
        log_pretooluse_block(
            "require_load_bearing_test",
            command,
            f"LOAD-BEARING-TEST EXCEPTION AUTHORIZED (audit): {raw}",
            input_data=input_data,
        )
        return {
            "decision": "allow",
            "systemMessage": f"Load-bearing-test pre-review gate overridden: {raw}",
        }
    if verdict is False:
        invalid_reason = _invalid_override_reason(input_data)
        log_pretooluse_block(
            "require_load_bearing_test", command, invalid_reason, input_data=input_data
        )
        return {"decision": "block", "reason": invalid_reason}
    log_pretooluse_block("require_load_bearing_test", command, reason, input_data=input_data)
    return {"decision": "block", "reason": reason}


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry. None to allow, dict to block/warn."""
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
        return _blocked_with_override_check(
            input_data,
            command,
            _fail_closed_reason("could not resolve --repo/--head for this command"),
        )

    files = _fetch_compare_files(repo, base, head)
    if files is None:
        return _blocked_with_override_check(
            input_data,
            command,
            _fail_closed_reason(f"`gh api compare {repo} {base}...{head}` failed"),
        )

    behavior_files, test_files = _scan_diff(files)
    if not behavior_files:
        return None

    unpaired = [f for f in behavior_files if not _behavior_file_paired(f, test_files)]
    if unpaired and _docs_only_exception_active(input_data):
        patch_by_filename = {
            entry.get("filename"): entry.get("patch")
            for entry in files
            if isinstance(entry, dict) and isinstance(entry.get("filename"), str)
        }
        unpaired = [f for f in unpaired if not _patch_is_docs_only(patch_by_filename.get(f))]
    if not unpaired:
        return None

    return _blocked_with_override_check(
        input_data, command, _no_test_reason(unpaired, repo, base, head)
    )


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
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
