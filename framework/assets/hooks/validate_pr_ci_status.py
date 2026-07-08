#!/usr/bin/env python3
"""PreToolUse hook: Block `gh pr merge` if CI is not green.

Queries `gh pr view --json statusCheckRollup` and blocks merge when any check
has failed, been cancelled, timed out, or requires action. Pending checks block
unless the user passes `--auto` AND the base branch genuinely enforces those
checks via branch protection (see `--auto` semantics below).

The whole gate is active only when `ci.merge_requires_green` is true (default).
If a project does not require green CI before merge, `check()` returns None.

`--auto` only warn-allows pending when GitHub will actually hold the merge (#230)
=============================================================================

`gh pr merge --auto` asks GitHub to complete the merge once the PR's *branch-
protection required status checks* pass. If the base branch has NO required
status checks configured (an unprotected branch — this repo, and most fresh
installs), GitHub has nothing to wait for and merges IMMEDIATELY. A check that
is still pending at that moment then finishes — possibly RED — *after* the merge
already landed. That is exactly how Wave-13 merged S2 #226 with a red `node (20)`
check: `--auto` was treated as "GitHub will hold for green", but with no branch
protection there was nothing to hold it.

So the pending + `--auto` warn-allow is now conditional on real enforcement:

  - base branch enforces required checks (non-empty required-status-checks set)
        → GitHub genuinely holds the merge until green → warn-allow (as before).
  - base branch does NOT enforce them (unprotected / empty required set; the
        endpoint 404s) → `--auto` would merge NOW, before CI finishes → BLOCK.
        Pending != green when nothing will hold the merge.
  - enforcement undeterminable (no base ref, or a transport/permission error on
        the protection query) → fail-open warn-allow (never manufacture a block
        on an inability to read), with a caveat surfaced in the message.

A pending merge WITHOUT `--auto` blocks unconditionally, as before. A check that
is already RED at merge time blocks regardless of `--auto`. The audited `--admin`
+ ADMIN_MERGE_EXCEPTION path remains the sanctioned override for all of the above.

Empty rollup
============

An EMPTY `statusCheckRollup` ("no checks reported") is NOT the same as green:
"no checks reported" is not "all checks passed" (a silently-dropped workflow
trigger can produce zero runs that a naive "no failing checks" gate waves
through). Gated on `ci.empty_rollup_is_blocking` (default true):

  - true  → discriminate via the sibling `validate_workflow_paths_coverage`
            coverage signal: if the repo has an `on.pull_request` workflow with
            no `paths:` filter (runs on every PR), an empty rollup is an
            anomalous dropped-trigger → BLOCK. If the repo is fully
            path-filtered, an empty rollup may be the legitimate docs-only
            zero-check case → warn-allow (no deadlock).
  - false → empty rollup is warn-allowed (still surfaced, never blocks).

The companion `lib/pr_ci_state.py` readiness oracle treats empty as not-ready
unconditionally — that is the query-time readiness assertion, distinct from
this PreToolUse gate's repo-shape discrimination.

Admin-merge exception validation
================================

`--admin` lets a repo admin bypass GitHub's required-status-checks gate. An
unconditional, unlogged `--admin` short-circuit is a silent escape hatch, so it
is validated instead: it requires an `ADMIN_MERGE_EXCEPTION` env var of the form
`<class>:<rationale>`, where `<class>` is one of the configured exception
classes (`policy.admin_merge_exceptions`, a map of class→rationale) and
`<rationale>` is a non-empty justification. The use is logged (the audit trail).
An absent/unrecognized exception BLOCKS — fail-safe. If no exception classes are
configured, ANY `--admin` blocks (no bypass is configured).

NEUTRAL conclusion semantics
============================

GitHub's Checks API uses `NEUTRAL` to mean "the check has no opinion," normally
treated as pass. Some services (e.g. visual-regression on snapshots-pending-
review) return `NEUTRAL` while structurally not-finished; treating that as pass
would let a merge through while review is still pending. The configured
`ci.neutral_pending_check_prefixes` list names CheckRun display-name PREFIXES
(case-insensitive `startswith`) whose `NEUTRAL` conclusion is treated as
*pending* instead of pass. Any check not matching a prefix keeps NEUTRAL → pass.

Exit codes:
  0 — allow (not a merge command, gate disabled, validated `--admin` exception,
      all checks green, or a legitimately-empty rollup)
  2 — block (failing/pending checks without `--auto`, an anomalous empty rollup
      where a covering workflow should have run, or `--admin` without a valid
      configured exception)
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _framework_config import config  # noqa: E402
from _framework_log import log_pretooluse_block  # noqa: E402
from _repo_flag_parse import extract_repo  # noqa: E402

#: Declares this hook's fail-direction to the dispatcher (#175): an uncaught
#: exception from `check()` allows the command rather than blocking on the
#: hook's own bug.
FAIL_OPEN = True

# Conclusion values that unambiguously indicate a failed check.
_FAILURE_CONCLUSIONS = {
    "FAILURE",
    "CANCELLED",
    "TIMED_OUT",
    "ACTION_REQUIRED",
    "STARTUP_FAILURE",
}

# Status values that indicate the check has not finished yet.
_PENDING_STATUSES = {"QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "REQUESTED"}

# Bucket values (GitHub check rollup) that map to pass/fail.
_FAIL_BUCKETS = {"fail"}
_PASS_BUCKETS = {"pass", "skipping"}


def _neutral_pending_prefixes(input_data: dict | None) -> tuple[str, ...]:
    """Configured CheckRun name prefixes whose NEUTRAL conclusion means pending."""
    raw = config(input_data).get("ci.neutral_pending_check_prefixes", []) or []
    return tuple(str(p).lower() for p in raw)


def is_merge_command(command: str) -> bool:
    """Check if the command is a gh pr merge invocation, including chained commands."""
    for segment in re.split(r"\s*(?:&&|\|\||\||;)\s*", command):
        stripped = segment.lstrip()
        while re.match(r"[A-Za-z_][A-Za-z0-9_]*=\S*\s+", stripped):
            stripped = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+", "", stripped)
        if re.match(r"gh\s+pr\s+merge\b", stripped):
            return True
    return False


def validate_admin_exception(input_data: dict) -> dict | None:
    """Validate an `--admin` merge against the configured exception list.

    Returns None when the admin merge is authorized (a recognized exception
    class with a non-empty rationale) — the caller then allows the merge.
    Returns a block result dict when the exception is absent or unrecognized,
    so an undeclared `--admin` fails safe instead of silently bypassing the
    gate. The authorized case is logged too, for the audit trail. When no
    exception classes are configured, every `--admin` blocks.
    """
    exceptions = config(input_data).get("policy.admin_merge_exceptions", {}) or {}

    raw = (input_data.get("env", {}) or {}).get("ADMIN_MERGE_EXCEPTION")
    if raw is None:
        raw = os.environ.get("ADMIN_MERGE_EXCEPTION", "")
    raw = (raw or "").strip()

    cls, sep, rationale = raw.partition(":")
    cls = cls.strip()
    rationale = rationale.strip()
    valid_list = ", ".join(sorted(exceptions)) if exceptions else "(none configured)"

    if not exceptions or not sep or cls not in exceptions or not rationale:
        return {
            "decision": "block",
            "reason": (
                "BLOCKED: `--admin` merge requires a configured exception. "
                'Set ADMIN_MERGE_EXCEPTION="<class>:<rationale>" before merging, '
                f"where <class> is one of: {valid_list}, and <rationale> is a "
                "non-empty justification (logged for audit).\n"
                "Configure allowed classes under `policy.admin_merge_exceptions` "
                "in the framework config. With none configured, --admin always "
                "blocks (project policy: no silent CI bypass).\n"
                f"Received ADMIN_MERGE_EXCEPTION={raw!r}."
            ),
        }
    return None


def extract_pr_number(command: str) -> str | None:
    """Extract PR number from gh pr merge command."""
    match = re.search(r"\bgh\s+pr\s+merge\s+(\d+)", command)
    if match:
        return match.group(1)
    match = re.search(r"/pull/(\d+)", command)
    if match:
        return match.group(1)
    return None


def fetch_checks(pr_number: str | None, repo: str | None) -> list[dict] | None:
    """Fetch statusCheckRollup entries for the PR. Returns None on failure."""
    try:
        cmd = ["gh", "pr", "view"]
        if pr_number:
            cmd.append(pr_number)
        if repo:
            cmd.extend(["--repo", repo])
        cmd.extend(["--json", "statusCheckRollup"])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        rollup = data.get("statusCheckRollup", [])
        if not isinstance(rollup, list):
            return None
        return rollup
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def fetch_pr_base_ref(pr_number: str | None, repo: str | None) -> str | None:
    """Return the PR's base branch name (e.g. `main`), or None on failure.

    Used only on the empty-rollup path to anchor the covering-workflow lookup
    against the branch the PR actually merges into (an integration-branch PR's
    base is that branch, whose workflow set may differ from the default's).
    """
    try:
        cmd = ["gh", "pr", "view"]
        if pr_number:
            cmd.append(pr_number)
        if repo:
            cmd.extend(["--repo", repo])
        cmd.extend(["--json", "baseRefName"])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout).get("baseRefName") or None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def _classic_enforces_required_checks(repo: str | None, base: str | None) -> bool | None:
    """Does *base* enforce required checks via CLASSIC branch protection?

    Reads only the legacy branch-protection endpoint
    (`repos/{repo}/branches/{base}/protection/required_status_checks`).

    Returns:
      True  — the base has a non-empty required-status-checks set.
      False — the base has NO required status checks under classic protection: an
              unprotected branch, or a protected branch with an empty required set
              (both 404 this endpoint).
      None  — undeterminable: no repo/base, or a transport/permission error.

    A 404 / "branch not protected" is a DEFINITIVE "no required checks configured"
    (→ False), deliberately kept distinct from a transport error (→ None): the
    server answering "there is no required-checks config here" is not the same as
    being unable to ask at all. Conflating them would either wedge merges on a
    flaky API call (if a 404 fell through to a block) or re-open the slip on every
    unprotected repo (if a real error were read as "not enforced" and allowed).
    """
    if not repo or not base:
        return None
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/branches/{base}/protection/required_status_checks"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        blob = f"{result.stdout}\n{result.stderr}".lower()
        # A 404 / "branch not protected" / "not found" is a definitive "no
        # required checks configured" → NOT enforced. Any other failure
        # (permission, transport, rate-limit) is undeterminable → fail-open None.
        if "not protected" in blob or "404" in blob or "not found" in blob:
            return False
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    # `contexts` is the legacy list; `checks` the current app-aware form. Either
    # being non-empty means at least one required status check is enforced.
    contexts = data.get("contexts") or []
    checks = data.get("checks") or []
    return bool(contexts or checks)


def _rulesets_enforce_required_checks(repo: str | None, base: str | None) -> bool | None:
    """Does *base* enforce required checks via a GitHub RULESET (#262)?

    Repos that migrated off classic branch protection to *rulesets* configure
    required status checks under the rulesets API, not the classic
    `protection/*` endpoints. The classic probe 404s on such a repo and reads it
    as unenforced — a FALSE NEGATIVE that safe-sides the `--auto`/pending gate
    into an over-block. This helper closes that gap by reading the branch's
    effective rules (`repos/{repo}/rules/branches/{base}`), which flattens every
    ruleset (repo- and org-level) that applies to the branch.

    Returns:
      True  — at least one applicable `required_status_checks` rule names a
              non-empty required-checks set. GitHub holds an `--auto` merge until
              those checks pass, exactly like a classic required set.
      False — the branch's effective rules contain no enforcing
              `required_status_checks` rule (this endpoint returns `200 []` for a
              branch with no rules, so an empty answer is DEFINITIVE not-enforced),
              or the repo/branch itself is absent (404).
      None  — undeterminable: no repo/base, or a transport/permission error. The
              caller preserves fail-open, never manufacturing a block on an
              inability to read.
    """
    if not repo or not base:
        return None
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/rules/branches/{base}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        blob = f"{result.stdout}\n{result.stderr}".lower()
        # This endpoint returns `200 []` for a branch with no rules, so a
        # non-zero exit is not the "no enforcement" signal a classic 404 is. A
        # 404 here means the repo/branch itself is absent → definitively no
        # ruleset enforcement (→ False). Any other failure is undeterminable →
        # fail-open None.
        if "404" in blob or "not found" in blob:
            return False
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    for rule in data:
        if not isinstance(rule, dict):
            continue
        if rule.get("type") != "required_status_checks":
            continue
        params = rule.get("parameters") or {}
        required = params.get("required_status_checks") or []
        if required:
            return True
    return False


def base_branch_enforces_required_checks(repo: str | None, base: str | None) -> bool | None:
    """Does *base* enforce required status checks (classic OR rulesets)?

    Answers the one question the `--auto`/pending path needs: will GitHub HOLD an
    `--auto` merge until CI goes green? It does so when the base branch has a
    non-empty required-status-checks set — configured EITHER via classic branch
    protection OR via a GitHub ruleset (#262). If EITHER source reports
    enforcement, the base is treated as protected.

    Returns:
      True  — classic protection OR a ruleset enforces a non-empty required-checks
              set. A still-pending check under `--auto` is safe to warn-allow
              (GitHub really will wait for green).
      False — BOTH sources definitively report no required checks: an unprotected
              branch with no enforcing ruleset. GitHub will NOT hold an `--auto`
              merge, so a pending check can fail AFTER the merge lands (the W13
              `node (20)` slip, #230) → the caller blocks.
      None  — undeterminable: no repo/base, or a transport/permission error on
              EITHER probe with neither reporting enforcement. Fail-open: the
              caller warn-allows, never manufacturing a block on an inability to
              read. (A read error on one source cannot rule out that the other —
              unread — source enforces, so a definitive "not enforced" would be
              unsound.)
    """
    classic = _classic_enforces_required_checks(repo, base)
    if classic is True:
        return True
    rulesets = _rulesets_enforce_required_checks(repo, base)
    if rulesets is True:
        return True
    # Neither source reported True. Only assert the definitive "not enforced"
    # (→ False, the #230 pending/--auto block) when BOTH probes answered
    # definitively; if either was undeterminable, stay fail-open (None).
    if classic is None or rulesets is None:
        return None
    return False


def covering_pr_workflow_exists(repo: str | None, base: str | None) -> bool | None:
    """Discriminate an anomalous empty rollup from a legitimately-empty one.

    Returns:
      True  — the repo has at least one `on.pull_request` workflow with NO
              `paths:` filter on `base`, i.e. a workflow that runs on EVERY PR.
              When such a workflow exists, an empty `statusCheckRollup` means
              that always-running check produced zero runs — the anomalous
              dropped-trigger case → the empty rollup is a hard not-ready state
              and `check()` blocks.
      False — every `on.pull_request` workflow on `base` is `paths:`-filtered.
              The repo is fully path-filtered by design: a docs-only PR there
              legitimately produces zero check-runs, so the empty rollup is
              warn-allowed rather than hard-blocked (no deadlock).
      None  — undeterminable (no repo/base, or an API/import failure). Caller
              fails open to the warn-allow branch.

    Reuses the sibling hook's `_build_coverage_signal` so the empty-rollup
    discriminator and the workflow-orphan gate share one paths-filter parser
    and cannot drift.
    """
    if not repo or not base:
        return None
    try:
        import validate_workflow_paths_coverage as coverage_hook
    except ImportError:
        return None
    signal = coverage_hook._build_coverage_signal(repo, base)
    if signal is None:
        return None
    _covered_globs, any_no_paths = signal
    return any_no_paths


def classify_check(check: dict, neutral_pending_prefixes: tuple[str, ...] = ()) -> str:
    """Return 'fail', 'pending', or 'pass' for a single check entry.

    NEUTRAL conclusion handling: CheckRuns whose display name starts with a
    prefix in `neutral_pending_prefixes` (case-insensitive `startswith`) treat
    NEUTRAL as 'pending' rather than 'pass'. All other checks preserve the
    NEUTRAL → pass behavior. Prefixes come from `ci.neutral_pending_check_prefixes`.
    """
    bucket = (check.get("bucket") or "").lower()
    conclusion = (check.get("conclusion") or "").upper()
    status = (check.get("status") or check.get("state") or "").upper()

    if bucket in _FAIL_BUCKETS or conclusion in _FAILURE_CONCLUSIONS:
        return "fail"
    if status in _PENDING_STATUSES or conclusion == "":
        # Completed with no conclusion is treated as success; truly pending
        # checks have status != COMPLETED.
        if status == "COMPLETED":
            return "pass"
        return "pending"
    # NEUTRAL allowlist: CheckRuns whose name starts with a configured prefix
    # treat NEUTRAL as pending.
    if conclusion == "NEUTRAL":
        name_lc = check_name(check).lower()
        if any(name_lc.startswith(p) for p in neutral_pending_prefixes):
            return "pending"
    if bucket in _PASS_BUCKETS or conclusion in {"SUCCESS", "NEUTRAL", "SKIPPED"}:
        return "pass"
    return "pass"


def classify_rollup(rollup: list[dict], neutral_pending_prefixes: tuple[str, ...] = ()) -> str:
    """Classify a whole statusCheckRollup into a single readiness verdict.

    Returns exactly one of:
      "empty"   — no checks reported. A HARD not-ready state, NEVER green:
                  "no checks reported" is not "all checks passed" (a dropped
                  trigger can produce zero runs a naive gate would wave through).
      "failing" — at least one check classifies as fail.
      "pending" — no failing checks, but at least one is still pending.
      "ready"   — non-empty AND every check passes.

    This is the single source of truth for the empty/fail/pending/ready
    taxonomy, shared verbatim by this hook's `check()` (the gh-pr-merge gate)
    and the `lib/pr_ci_state.py` readiness oracle, so the gate and the oracle
    cannot drift.
    """
    if not rollup:
        return "empty"
    if any(classify_check(c, neutral_pending_prefixes) == "fail" for c in rollup):
        return "failing"
    if any(classify_check(c, neutral_pending_prefixes) == "pending" for c in rollup):
        return "pending"
    return "ready"


def check_name(check: dict) -> str:
    """Best-effort display name for a check."""
    return check.get("name") or check.get("context") or check.get("workflowName") or "<unnamed>"


def check_url(check: dict) -> str:
    """Best-effort URL for a check."""
    return check.get("detailsUrl") or check.get("targetUrl") or ""


def format_check_list(checks: list[dict]) -> str:
    lines = []
    for c in checks:
        name = check_name(c)
        conclusion = (c.get("conclusion") or c.get("status") or "").lower() or "unknown"
        url = check_url(c)
        suffix = f" ({url})" if url else ""
        lines.append(f"  - {name} [{conclusion}]{suffix}")
    return "\n".join(lines)


def check(input_data: dict) -> dict | None:
    """Check PR CI status. Returns result dict if blocking, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    if not is_merge_command(command):
        return None

    # Whole gate is opt-out: if the project does not require green CI, allow.
    if not config(input_data).get("ci.merge_requires_green", True):
        return None

    if "--admin" in command:
        # `--admin` no longer short-circuits unconditionally. It must name a
        # configured exception via ADMIN_MERGE_EXCEPTION, else block.
        exception_block = validate_admin_exception(input_data)
        if exception_block is not None:
            log_pretooluse_block(
                "validate_pr_ci_status", command, exception_block["reason"], input_data=input_data
            )
            return exception_block
        # Authorized exception — allow, but log the use for audit.
        raw = (input_data.get("env", {}) or {}).get("ADMIN_MERGE_EXCEPTION") or os.environ.get(
            "ADMIN_MERGE_EXCEPTION", ""
        )
        log_pretooluse_block(
            "validate_pr_ci_status",
            command,
            f"ADMIN-MERGE EXCEPTION AUTHORIZED (audit): {raw.strip()}",
            input_data=input_data,
        )
        return None

    pr_number = extract_pr_number(command)
    repo = extract_repo(command)
    rollup = fetch_checks(pr_number, repo)
    prefixes = _neutral_pending_prefixes(input_data)

    pr_display = f"#{pr_number}" if pr_number else "(current branch)"

    if rollup is None:
        return {
            "decision": "allow",
            "systemMessage": (
                f"WARNING: Could not verify CI status for PR {pr_display}. "
                "Ensure all checks are green before merging."
            ),
        }

    if not rollup:
        # Empty statusCheckRollup — no CI checks reported. An empty rollup is
        # NOT the same as green ("no checks reported" != "all checks passed").
        empty_blocking = config(input_data).get("ci.empty_rollup_is_blocking", True)
        if not empty_blocking:
            return {
                "decision": "allow",
                "systemMessage": (
                    f"WARNING: PR {pr_display} has no CI checks (empty statusCheckRollup). "
                    "Empty-rollup blocking is disabled (`ci.empty_rollup_is_blocking`=false), "
                    "so this is allowed — but an empty rollup is NOT green CI. Verify via "
                    "`gh pr checks` before asserting merge-readiness."
                ),
            }
        # Blocking mode: discriminate the anomalous dropped-trigger case from a
        # legitimately-empty rollup on a fully path-filtered repo.
        #   - covering unfiltered-`paths` workflow EXISTS → an always-running
        #     check reported nothing → anomalous dropped-trigger → BLOCK.
        #   - fully path-filtered (or undeterminable) → legitimate docs-only
        #     empty may apply → warn-allow (preserves the path-filtered design).
        base_ref = fetch_pr_base_ref(pr_number, repo)
        if covering_pr_workflow_exists(repo, base_ref) is True:
            result = {
                "decision": "block",
                "reason": (
                    f"BLOCKED: PR {pr_display} has an EMPTY statusCheckRollup (no checks "
                    "reported), but this repo has an on.pull_request workflow with no "
                    "`paths:` filter that runs on every PR — so a covering check SHOULD "
                    "have reported. An empty rollup here is an anomalous dropped-trigger, "
                    "NOT green CI.\n"
                    "Investigate the missing run (re-trigger via close/reopen or an empty "
                    "commit, or check `validate_workflow_paths_coverage`); silent absence "
                    "of CI != green CI. If this is a genuine configured exception, pass "
                    "`--admin` with an ADMIN_MERGE_EXCEPTION."
                ),
            }
            log_pretooluse_block(
                "validate_pr_ci_status", command, result["reason"], input_data=input_data
            )
            return result
        return {
            "decision": "allow",
            "systemMessage": (
                f"WARNING: PR {pr_display} has no CI checks (empty statusCheckRollup). "
                "Every on.pull_request workflow on this repo is `paths:`-filtered, so this "
                "may be the legitimate docs-only zero-check case — but an empty rollup is "
                "NOT green CI. Verify the workflow coverage via "
                "`validate_workflow_paths_coverage` or `gh pr checks`, or query "
                "`lib/pr_ci_state.py <PR#>` before asserting merge-readiness — "
                "silent absence of CI != green CI."
            ),
        }

    failing: list[dict] = []
    pending: list[dict] = []
    for entry in rollup:
        verdict = classify_check(entry, prefixes)
        if verdict == "fail":
            failing.append(entry)
        elif verdict == "pending":
            pending.append(entry)

    if failing:
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: PR {pr_display} has {len(failing)} failing CI check(s). "
                "Project policy requires green CI before merge.\n"
                f"Failing checks:\n{format_check_list(failing)}\n\n"
                "Fix the failures and re-run, or pass `--admin` for emergency overrides only."
            ),
        }
        log_pretooluse_block(
            "validate_pr_ci_status", command, result["reason"], input_data=input_data
        )
        return result

    if pending:
        # A pending check is only safe to warn-allow under `--auto` if GitHub will
        # actually HOLD the merge until it goes green — which it does only when the
        # base branch enforces that check via branch-protection required status
        # checks. With NO branch protection (this repo, most fresh installs),
        # `gh pr merge --auto` merges IMMEDIATELY, so a still-pending check that
        # later fails lands AFTER the merge — the W13 `node (20)` slip (#230). So
        # `--auto` warn-allows pending ONLY when protection genuinely enforces it.
        if "--auto" in command:
            base_ref = fetch_pr_base_ref(pr_number, repo)
            enforces = base_branch_enforces_required_checks(repo, base_ref)
            if enforces is None:
                # Undeterminable (no base ref, or a transport/permission error on
                # the protection query). Preserve the fail-open posture: warn-allow
                # rather than manufacture a block on an inability to read — but
                # surface that GitHub may NOT hold the merge if the base is in fact
                # unprotected.
                return {
                    "decision": "allow",
                    "systemMessage": (
                        f"WARNING: PR {pr_display} has {len(pending)} pending CI check(s) and "
                        "`--auto` was passed, but branch protection on the base could not be "
                        "determined (fail-open allow). If the base does NOT enforce these checks, "
                        "`--auto` merges immediately and a check that later fails will have already "
                        "landed — verify branch protection or wait for green.\n"
                        f"{format_check_list(pending)}"
                    ),
                }
            if enforces:
                return {
                    "decision": "allow",
                    "systemMessage": (
                        f"WARNING: PR {pr_display} has {len(pending)} pending CI check(s); "
                        "the base branch enforces required checks via branch protection, so "
                        "`--auto` will let GitHub merge only once they finish green.\n"
                        f"{format_check_list(pending)}"
                    ),
                }
            # enforces is False: the base has NO required-status-check enforcement.
            # `--auto` would merge NOW, before these checks finish — pending != green
            # when nothing will hold the merge. BLOCK (the W13 slip fix, #230).
            result = {
                "decision": "block",
                "reason": (
                    f"BLOCKED: PR {pr_display} has {len(pending)} pending CI check(s) and "
                    "`--auto` was passed, but the base branch has NO branch-protection required "
                    "status checks — GitHub would merge IMMEDIATELY without waiting for CI, so a "
                    "check that later fails would land after the merge (the exact W13 `node (20)` "
                    "slip). `--auto` cannot substitute for green CI when nothing enforces it.\n"
                    f"Pending checks:\n{format_check_list(pending)}\n\n"
                    "Wait for CI to finish and merge on green, configure branch protection to make "
                    "these checks required, or pass `--admin` with an ADMIN_MERGE_EXCEPTION for an "
                    "audited emergency override."
                ),
            }
            log_pretooluse_block(
                "validate_pr_ci_status", command, result["reason"], input_data=input_data
            )
            return result
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: PR {pr_display} has {len(pending)} pending CI check(s). "
                "Wait for CI to finish, pass `--auto` to let GitHub merge on green (honored only "
                "when branch protection enforces the checks), or pass `--admin` for emergency "
                "overrides.\n"
                f"Pending checks:\n{format_check_list(pending)}"
            ),
        }
        log_pretooluse_block(
            "validate_pr_ci_status", command, result["reason"], input_data=input_data
        )
        return result

    return None


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
