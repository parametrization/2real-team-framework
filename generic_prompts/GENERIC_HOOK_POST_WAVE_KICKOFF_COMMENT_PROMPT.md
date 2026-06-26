# Auto-Post Kickoff Comment on Iteration-Label Apply (PostToolUse hook)

**Purpose:** When an issue is assigned into an iteration by applying its iteration label, deterministically post a standardized "kickoff" comment to that issue — naming the assignee, reviewers, branch base, and priority — instead of relying on an orchestrator to remember to do it. This embodies the enforcement hierarchy "prefer hook > skill > charter": a skill step can be skipped or mis-executed, but a hook fires deterministically on the trigger event.

This is a PostToolUse `Bash` hook with `check(...) -> dict | None`. Advisory; always exits 0. Built on the iteration-label parser and the error-log helper. Reads assignment data from a project status file.

---

## The rule it enforces

On a command that **applies** (not merely removes) an iteration label to an issue: resolve the repo (from `--repo`, else cwd), recover the iteration's display context (e.g. phase) from the status file when the label is phase-agnostic, find the issue's assignment row in the iteration's scope, render the standardized comment, and post it via `<cli> issue comment --body-file <fresh-file>`. Skip — and log one event — on each failure mode (meta-issue, already-posted, missing scope, no assignment row, post failed).

## Key mechanics (each is a real lesson)

- **Apply-only + relabel filter.** Fire only when the command adds an iteration label and does NOT also remove one. A carry-forward relabel (`--add-label new --remove-label old`) is moving an already-assigned issue between iterations, not an initial kickoff — silently skip it, or you get a noise burst.
- **Iteration-specific idempotency.** Check existing comments for a heading that matches the **current** iteration literally (not a wildcard digit). A carry-forward issue carries its prior iteration's kickoff comment; a wildcard match would see it and skip the new iteration's kickoff.
- **Fresh body file, not `/tmp`.** Write the comment body to an in-repo scratch dir with a millisecond-stamped filename, immediately before the post — this both evades a stale-tmp-file guard hook and avoids concurrent-write collisions in a kickoff loop.
- **Assignment-row matching with fallbacks.** Match by full `id`, short `ref`, repo-level backlog row, or a bare short-ref string (synthesizing a placeholder row with `(unassigned)` slots) — a visible kickoff the orchestrator can backfill beats no comment.
- **Phase recovery.** A phase-agnostic label carries no phase; recover it from the status file's live pointer (with a fallback), and skip rather than render a "Phase None" comment.

## Code skeleton (stdlib only — `json`, `re`, `subprocess`, `time`)

```python
#!/usr/bin/env python3
"""PostToolUse Bash: post a standardized kickoff comment on iteration-label apply."""
from __future__ import annotations
import json, re, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shell_parse import resolve_repo_short_name
from _wave_label_parse import parse_label_change, parse_label_spec
from annunaki_log import log_posttooluse_event

EMIT_DISPATCH_SUMMARY = True  # let the dispatcher surface "posted vs skipped"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATUS_FILE = REPO_ROOT / "project-status.json"
SCRATCH_DIR = REPO_ROOT / ".claude" / "scratch"
KICKOFF_REQUESTOR = "Coordinator"  # the orchestrator persona name


def _heading_re(iter_num: int | None):
    """Iteration-specific heading regex; None = wildcard (legacy fallback)."""
    n = r"\d+" if iter_num is None else str(iter_num)
    return re.compile(rf"\*\*Iteration\s+{n}\s+Kickoff\b")


def parse_apply(command: str):
    """Return (repo, issue, label) for an APPLY (not a relabel), else None."""
    change = parse_label_change(command)
    if change is None or change.add_label is None:
        return None
    if change.remove_label is not None:   # carry-forward relabel — not a kickoff
        return None
    return change.repo, change.issue_number, change.add_label


def render(row: dict, iter_num: int, phase: int) -> str:
    impl = row.get("implementer") or "(unassigned)"
    rev = row.get("reviewer") or "(unassigned)"
    rev2 = row.get("reviewer_2") or "(unassigned)"
    return "\n".join([
        f"Requestor: {KICKOFF_REQUESTOR}", f"Requestee: {impl}",
        "RequestOrReplied: Request", "",
        f"**Iteration {iter_num} Kickoff — Phase {phase}**", "",
        f"This issue is assigned to you for iteration {iter_num}.",
        f"- Peer reviewer: {rev}", f"- Secondary reviewer: {rev2}",
        "- Branch naming: `{FirstInitial}.{LastName}/{IIII}-{issue-slug}`", "",
        "Please begin implementation.",
    ])


def check(input_data, status_loader=None, comment_fetcher=None,
          comment_poster=None, body_writer=None, git_runner=None):
    if input_data.get("tool_name") != "Bash":
        return None
    command = (input_data.get("tool_input") or {}).get("command", "")
    parsed = parse_apply(command) if command else None
    if parsed is None:
        return None
    repo, issue, label = parsed
    if repo is None:
        repo = resolve_repo_short_name(input_data, git_runner=git_runner)
        if repo is None:
            log_posttooluse_event("kickoff_comment", command,
                f"skip_no_repo_context: issue {issue} omitted --repo, unresolvable.")
            return {"action": "skip_no_repo_context", "issue": issue}

    spec = parse_label_spec(label)
    if spec is None or spec.minor is None:   # placeholder label — not a kickoff
        return None
    iter_num, phase = spec.minor, spec.major

    status = (status_loader or _read_status)()
    if status is None:
        return {"action": "skip_no_scope", "repo": repo, "issue": issue}
    if phase is None:
        phase = _phase_from_status(status)
        if phase is None:
            return {"action": "skip_no_phase", "repo": repo, "issue": issue}

    # meta-issue skip / scope+row lookup / idempotency (iteration-specific) ...
    row = _find_assignment_row(status, repo, issue, iter_num)
    if row is None:
        return {"action": "skip_no_row", "repo": repo, "issue": issue}
    if _already_posted(repo, issue, iter_num, comment_fetcher):
        return {"action": "skip_idempotent", "repo": repo, "issue": issue}

    body = render(row, iter_num, phase)
    path = (body_writer or _write_fresh_body)(body, repo, issue)
    if not (comment_poster or _post_comment)(repo, issue, path):
        log_posttooluse_event("kickoff_comment", command,
            f"post failed for {repo}#{issue} (body at {path}).")
        return {"action": "skip_post_failed", "repo": repo, "issue": issue}
    return {"action": "post", "repo": repo, "issue": issue, "label": label}


def _write_fresh_body(body, repo, issue) -> Path:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", repo)
    p = SCRATCH_DIR / f"kickoff-{safe}-{issue}-{int(time.time()*1000)}.md"
    p.write_text(body, encoding="utf-8")
    return p
# _read_status, _phase_from_status, _find_assignment_row, _already_posted,
# _post_comment(gh issue comment --body-file) ... (omitted, all fail-soft)


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    try:
        check(input_data)
    except Exception as e:  # noqa: BLE001 — advisory, never raise
        try:
            log_posttooluse_event("kickoff_comment",
                (input_data.get("tool_input") or {}).get("command", "")[:500],
                f"Unexpected hook error: {type(e).__name__}: {e}")
        except Exception:
            pass
    sys.exit(0)
```

## How to adapt

- **The comment template is yours.** Keep field names consistent with whatever reviewer/assignment validators parse downstream.
- **Idempotency must be iteration-specific** or carry-forwards get silently skipped. Match the current iteration's heading literally.
- **Relabel filter** prevents firing on every carry-forward relabel — only bare `--add-label` (no paired removal) is an initial kickoff.
- **Inject everything external** (status loader, comment fetcher/poster, body writer, git runner) so tests never touch the network or filesystem.
- **`EMIT_DISPATCH_SUMMARY = True`** so the PostToolUse dispatcher surfaces "posted vs skip_idempotent" — silent skips were the original "is the hook even running?" confusion.
