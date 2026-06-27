#!/usr/bin/env python3
"""PreToolUse hook: Require TWO PR review comments before merge.

Blocks `gh pr merge` unless the PR has at least two reviews from distinct
non-authors, using either formal GitHub reviews or charter-format
comment-based reviews from different team members. Honors the
Single-Reviewer Exception for wave-bootstrap PRs reviewed by a charter-
enforcer role.

Input Language:
  Fires on:      PreToolUse Bash
  Matches:       gh pr merge [{N}] [--repo {OWNER/REPO}] [--squash|--merge|--rebase]
                             [--admin] [--auto]   — including when chained via
                             && / || / | / ; after env-var assignments.
  Does NOT match: gh pr list, gh pr view, gh pr checks, gh pr create,
                  git merge, git pull.
  Flag pass-through:
    --repo   → forwarded to `gh pr view` and comment fetch so the hook checks
               the PR in the repo the user named, not the cwd-resolved repo.
    --admin  → short-circuits (emergency override — allows merge).

  Batch-loop guard (#567, narrowed #886, broadened #894): a `gh pr merge` with
  a NON-LITERAL PR argument located INSIDE a for/while/until loop body (e.g.
  `for pr in 48 49; do gh pr merge "$pr" …; done`) is HARD BLOCKED. The
  literal-PR parse cannot resolve a non-integer argument, so the gate would
  fail-open and merge every iteration unverified (observed P3W11 + P3W13). The
  operator is told to run one literal merge per call so each PR is gate-checked.
  The merge must sit between a `do` and its matching `done` to trip the guard —
  an unrelated loop in the same block (e.g. a `gh run rerun "$r" --failed`
  staleness recheck) alongside a non-loop variable merge does NOT (#886). #894
  extended the matched argument forms from `$pr`/`${pr}` to ANY non-literal
  argument — also `${prs[$i]}`, `$(get_pr)`, and a subshell-wrapped
  `(gh pr merge $pr)` — closing two residual fail-open evasions. `--admin` still
  overrides; a literal `gh pr merge 54` is unaffected. Conservative DECIDE-tier
  shape (no conditional-allow) per `feedback_safety_direction_over_ux_friction`.

Charter-format review comments (canonical per `pull-requests.md` § Comment-Based Reviews,
resolves #233):

  Requestor: <comment author>     # always the team member POSTING the comment
  Requestee: <comment target>     # always the team member ADDRESSED by the comment
  RequestOrReplied: <Request|Reply|Approved|ChangesRequested>
  TechDebt: none | #15, #16, ...

  Direction by RequestOrReplied:
    - Request          — Requestor=PR author,  Requestee=reviewer (NOT a verdict)
    - Reply / Replied  — Requestor=replier,    Requestee=person-being-replied-to (NOT a verdict)
    - Approved         — Requestor=reviewer,   Requestee=PR author (verdict)
    - ChangesRequested — Requestor=reviewer,   Requestee=PR author (verdict)

  The reviewer for a verdict comment is the comment AUTHOR — i.e. the
  Requestor. The prior hook counted distinct Requestee values across
  Approved/ChangesRequested comments, which on verdicts is always the PR
  author and so collapsed to a single value (resolves #244).

Reviewer counting rule (resolves #244):
  - Verdict comments (Approved / ChangesRequested) → Requestor is the reviewer
  - Request / Reply comments → not reviews; do not contribute to reviewer count
  - Two-reviewer rule satisfied when there are TWO DISTINCT REVIEWER NAMES across
    Approved comments, neither of which is the PR author.

Reviewer dedup key:
  The reviewer set is keyed on the FULL reviewer name (lowercased), not on
  the lastname. Two distinct reviewers with the same lastname (e.g.,
  "Lucas Ferreira" and "Santiago Ferreira") are counted as TWO reviewers
  toward the two-peer-review requirement (issue #164).
  The author-equality check uses lastname because branches are named
  `{Initial}.{Lastname}/...` and we only have the author's lastname to
  compare against.

Single-Reviewer Exception (resolves #228):
  When the PR is labeled `wave-bootstrap` AND there is exactly ONE distinct
  reviewer who is a charter-enforcer role in the local roster, the hook
  permits merge with one Approved comment instead of two. Charter
  `pull-requests.md` § Single-Reviewer Exception (Wave-Bootstrap Only)
  defines the policy; this is its hook-side enforcement.

  Charter-enforcer roles are derived from the local repo's
  `.claude/team/roster/` filenames matching the prefix allowlist:
    standards_lead_*    (parent: Aino)
    program_director_*  (parent: Nadia)
    manager_*           (children: e.g. Maeve, Dilara, Bereket)
    project_lead_*      (children: e.g. Marcia)
    tech_lead_*         (children: e.g. Anya)
  Each file's `**Name:** <Full Name>` line is parsed for the canonical name.

Exit codes:
  0 — allow (not a merge command, two reviews, or single-reviewer exception)
  2 — block (fewer than two reviews and exception does not apply, or a
      verdict is missing TechDebt)
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo_flag_parse import extract_repo
from annunaki_log import log_pretooluse_block

# Charter-enforcer role prefixes for the Single-Reviewer Exception. Derived
# from `pull-requests.md § Single-Reviewer Exception (Wave-Bootstrap Only)`
# "Standards & Quality Lead (Aino) or a comparable charter enforcer". The
# prefix list captures the equivalent roles across parent + child rosters
# observed in the org: standards_lead, program_director (parent), manager,
# project_lead, tech_lead (children).
_CHARTER_ENFORCER_ROLE_PREFIXES = (
    "standards_lead_",
    "program_director_",
    "manager_",
    "project_lead_",
    "tech_lead_",
)


def is_merge_command(command: str) -> bool:
    """Check if the command is a gh pr merge invocation, including chained commands.

    Handles direct invocations and commands chained with &&, ||, ;, or |.
    """
    # Split on shell chaining operators to check each sub-command
    for segment in re.split(r"\s*(?:&&|\|\||\||;)\s*", command):
        stripped = segment.lstrip()
        # Skip past any leading env variable assignments (VAR=value ...)
        while re.match(r"[A-Za-z_][A-Za-z0-9_]*=\S*\s+", stripped):
            stripped = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+", "", stripped)
        if re.match(r"gh\s+pr\s+merge\b", stripped):
            return True
    return False


def extract_pr_number(command: str) -> str | None:
    """Extract PR number from gh pr merge command."""
    # gh pr merge 123 or gh pr merge <url>
    match = re.search(r"\bgh\s+pr\s+merge\s+(\d+)", command)
    if match:
        return match.group(1)
    # gh pr merge <url containing /pull/123>
    match = re.search(r"/pull/(\d+)", command)
    if match:
        return match.group(1)
    # gh pr merge with no number (current branch PR)
    return None


# A `gh pr merge` whose positional PR argument is NON-LITERAL — i.e. anything
# other than a bare integer PR number (the only form the literal-PR gate can
# resolve) or an absent positional (flags-only / current-branch merge). This
# deliberately matches on the FIRST character of the argument rather than on a
# fully-shaped `$var` token, so it is agnostic to how the argument is spelled or
# terminated. That single change closes two residual fail-open evasions of the
# old `$var`-only matcher (#894):
#
#   1. Subshell-wrapped merge — `(gh pr merge $pr)`. The old terminator lookahead
#      `(?=\s|;|&|\||$)` did not admit the `)` that ends the arg, so `$pr)` never
#      matched. Matching the leading `$` needs no terminator, so the `)` (and the
#      `}` of a `{ …; }` brace group, which already ends at `;` anyway) require no
#      special-casing.
#   2. Subscripted / compound / command-substitution arg — `"${prs[$i]}"`,
#      `"$(get_pr)"`. These survive quote-normalization now that
#      `_strip_quoted_runs_keep_var_args` unwraps any single-word expansion
#      (not only a lone `$pr`), and their leading `$` matches here.
#
# `(?![-\d])` keeps the two LITERAL/absent forms allowed: a flag (`--merge`,
# leading `-`) means no positional arg (current-branch merge, out of scope for
# #567), and a leading digit is the bare integer the gate resolves. The class
# `[^\s;&|()]` requires a real argument character — a bare terminator left behind
# by a stripped quoted run (`gh pr merge ;`) is NOT treated as an argument.
_GH_MERGE_NONLITERAL_ARG = re.compile(
    r"\bgh\s+pr\s+merge\s+"  # the merge verb + separating whitespace
    r"(?![-\d])"  # NOT a flag and NOT a bare-integer literal PR number
    r"[^\s;&|()]"  # a present, non-terminator positional argument character
)

# `do` / `done` loop keywords as standalone tokens (delimited by start-of-string,
# whitespace, or `;`). `do`/`done` are loop-only keywords in shell, so every
# balanced `do … done` pair delimits a loop BODY. The alternation lists `done`
# first so the longer keyword wins (otherwise `do` would match the `do` prefix
# of `done`). The keyword span is captured via the lookahead so the surrounding
# delimiters are not consumed and adjacent tokens are not swallowed (#886).
_LOOP_DO_DONE = re.compile(r"(?:^|[\s;])(done|do)(?=[\s;]|$)")


def _loop_body_spans(view: str) -> list[tuple[int, int]]:
    """Return the (start, end) character spans of each shell loop BODY in `view`.

    A loop body is the text between a `do` keyword and its matching `done`.
    `do`/`done` are loop-only keywords in shell, so every balanced `do … done`
    pair delimits one body; nested loops are paired via a stack (each `done`
    closes the most recent unmatched `do`). Unbalanced tokens are ignored.

    `view` is expected to be the quote-normalized command produced by
    `_strip_quoted_runs_keep_var_args`, so `do`/`done` mentioned inside a quoted
    `--body "…"` payload have already been stripped and do not create spans.
    """
    spans: list[tuple[int, int]] = []
    do_stack: list[int] = []  # end-offsets of open `do` keywords (body starts here)
    for m in _LOOP_DO_DONE.finditer(view):
        keyword = m.group(1)
        if keyword == "do":
            do_stack.append(m.end(1))
        elif do_stack:  # `done` — close the most recent `do`
            body_start = do_stack.pop()
            spans.append((body_start, m.start(1)))
    return spans


def _strip_expansions(text: str) -> str:
    """Return `text` with balanced `${…}` and `$(…)` expansion groups removed.

    Used by `_is_single_expansion_word` to decide whether a double-quoted run is
    a single shell WORD argument: a run like `"$(get_pr $i)"` or `"${prs[$i]}"`
    is one argument even though it contains whitespace INSIDE the expansion,
    whereas a prose run like `"do gh pr merge $pr"` carries whitespace OUTSIDE
    any expansion. Nested groups are paired with a depth counter over the group's
    own `(`/`)` or `{`/`}`. A bare `$pr` (no brace/paren) is left intact — it has
    no internal whitespace to hide, so the surrounding-whitespace test handles it.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "$" and i + 1 < n and text[i + 1] in "({":
            opener = text[i + 1]
            closer = ")" if opener == "(" else "}"
            depth = 0
            j = i + 1
            while j < n:
                if text[j] == opener:
                    depth += 1
                elif text[j] == closer:
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            i = j  # skip the whole (possibly unbalanced) expansion group
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _is_single_expansion_word(text: str) -> bool:
    """True if `text` is a single shell-word argument carrying an expansion.

    `text` qualifies when it (a) contains a `$` expansion and (b) has no
    whitespace OUTSIDE any `${…}`/`$(…)` group. This admits the real merge-arg
    forms a loop can carry — `$pr`, `${pr}`, `${prs[$i]}`, `$(get_pr)`,
    `$(get_pr $i)` — while rejecting a `--body "for … do gh pr merge $pr; done"`
    prose payload (whitespace outside the expansion) and a quoted literal word
    like `"done"` (no `$`, so it is not unwrapped into a stray loop keyword).
    """
    if "$" not in text:
        return False
    return not any(ch.isspace() for ch in _strip_expansions(text))


def _strip_quoted_runs_keep_var_args(command: str) -> str:
    """Return `command` with quoted regions removed, EXCEPT a double-quoted
    region that is a single-word expansion argument (`"$pr"`, `"${pr}"`,
    `"${prs[$i]}"`, `"$(get_pr)"`), which is unwrapped to its bare inner form.

    Why: the loop-merge detector must (a) NOT see a `gh pr merge $pr` that
    lives inside a `--body "..."` payload (quoted argument data — strip it),
    yet (b) STILL see the real arg in `gh pr merge "$pr"` where only the
    argument itself is quoted (unwrap it). Shell semantics agree: double
    quotes around a single expansion word are removed and the word remains the
    program's argument, whereas a quoted run of prose is one opaque arg.

    The unwrap predicate is `_is_single_expansion_word` (#894): the earlier
    matcher only unwrapped a LONE simple variable (`\\$\\{?name\\}?`), so a
    subscripted / compound / command-substitution arg failed that fullmatch and
    was stripped as opaque prose — making the real merge arg vanish and the
    guard fail-open. Keying on "single expansion word" keeps every such arg.

    Single-quoted runs are always opaque data (no expansion) and are removed
    wholesale. Double-quoted runs are unwrapped only when the inner text is a
    single expansion word; otherwise removed.
    """
    out: list[str] = []
    i = 0
    n = len(command)
    while i < n:
        ch = command[i]
        if ch == "'":
            # Single-quoted run: opaque, drop through the closing quote.
            j = command.find("'", i + 1)
            if j == -1:
                break  # unbalanced — stop; raw-string fallback handles it
            i = j + 1
            continue
        if ch == '"':
            j = command.find('"', i + 1)
            if j == -1:
                break  # unbalanced
            inner = command[i + 1 : j]
            # Keep a single-word expansion double-quoted arg as its bare form.
            if _is_single_expansion_word(inner):
                out.append(inner)
            i = j + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def is_variable_pr_merge_in_loop(command: str) -> bool:
    """True if `command` runs a `gh pr merge` with a NON-LITERAL PR argument
    inside a for/while/until loop — the batch-loop merge shape that fail-opens
    the 2-reviewer gate (#567/#886/#894, memory `feedback_batch_loop_merge_evades`).

    The gate parses a LITERAL PR number from `gh pr merge <N>` to fetch that
    PR's reviews. When the argument is not a bare integer (`$pr`, `${pr}`,
    `${prs[$i]}`, `$(get_pr)`, or a subshell-wrapped `(gh pr merge $pr)`), the
    literal parse returns None, `get_pr_data(None)` resolves the cwd branch's PR
    (or nothing), and the merge fail-opens — the gate is silently disabled for
    every iteration. Both originally-observed instances (P3W11 wave→main 4-merge
    loop, P3W13 ingest 6-PR loop) merged with the gate effectively off.

    Conservative DECIDE-tier design (per #567 + `feedback_safety_direction_
    over_ux_friction`): we HARD BLOCK the non-literal-PR-in-loop shape outright.
    We do NOT attempt to enumerate loop values and gate-verify each — that is
    the explicitly-deferred conditional-allow path. A literal `gh pr merge 54`
    is untouched (its PR number parses, the gate runs).

    Mechanic (#894 broadening). Detection runs on a quote-normalized view of the
    command (quoted prose stripped, a single-word expansion arg such as `"$pr"`
    or `"${prs[$i]}"` unwrapped — see `_strip_quoted_runs_keep_var_args`) so a
    `--body "... for … do gh pr merge $pr … done"` payload that merely MENTIONS
    the shape is not matched. On that view, `_GH_MERGE_NONLITERAL_ARG` matches a
    `gh pr merge` whose first positional-argument character is non-literal (not a
    flag, not a bare integer). Matching the argument's leading character rather
    than a fully-shaped `$var` token closes the two residual #886 evasions:
      - subshell `(gh pr merge $pr)` — old terminator lookahead omitted `)`;
      - compound `${prs[$i]}` / `$(get_pr)` — old unwrap dropped it as prose.

    Co-location is preserved (#886). The match must sit INSIDE a `do … done`
    loop body. A one-off `gh pr merge "$PR"` OUTSIDE any loop, co-occurring with
    an unrelated `for r in …; do gh run rerun "$r" --failed; done`, does NOT
    fail-open (the merge resolves its own PR) and so MUST NOT block — the
    co-location requirement leaves it alone, while the real batch-loop shape
    (`for pr in …; do gh pr merge "$pr"; done`) still trips.
    """
    view = _strip_quoted_runs_keep_var_args(command)
    merge_matches = list(_GH_MERGE_NONLITERAL_ARG.finditer(view))
    if not merge_matches:
        return False
    spans = _loop_body_spans(view)
    if not spans:
        return False
    return any(
        body_start <= mm.start() < body_end
        for mm in merge_matches
        for (body_start, body_end) in spans
    )


def get_pr_data(pr_number: str | None, repo: str | None = None) -> dict | None:
    """Fetch all needed PR data in a single gh pr view call.

    Returns dict with keys: author (login str), number, reviews, headRefName,
    labels (list of label-name strings).
    Returns None if the fetch fails.
    """
    try:
        cmd = ["gh", "pr", "view"]
        if pr_number:
            cmd.append(pr_number)
        if repo:
            cmd.extend(["--repo", repo])
        cmd.extend(["--json", "author,number,reviews,headRefName,labels"])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        labels = [label.get("name", "") for label in data.get("labels", [])]
        return {
            "author": data.get("author", {}).get("login", ""),
            "number": data.get("number", pr_number),
            "reviews": data.get("reviews", []),
            "headRefName": data.get("headRefName", ""),
            "labels": labels,
        }

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def extract_branch_author_lastname(head_ref: str) -> str | None:
    """Extract the last name from branch format '{FirstInitial}.{LastName}[-/]...'.

    Accepts both separator styles seen in practice:
    - slash: `A.Virtanen/0179-branch-regex-fix` (legacy/charter spec)
    - dash:  `A.Virtanen-0179-branch-regex-fix` (observed on recent branches)

    Returns None if the head_ref does not match the `{Initial}.{LastName}` prefix
    followed by one of the accepted separators.
    """
    match = re.match(r"[A-Za-z]\.([A-Za-z]+)[-/]", head_ref)
    if match:
        return match.group(1)
    return None


PROJECT_NUMBER = 2
ORG = "noorinalabs"

# Path to the PARENT repo's roster directory. Resolved relative to the hook
# file: /<repo_root>/.claude/hooks/validate_pr_review.py → /<repo_root>/.claude/team/roster.
_ROSTER_DIR = Path(__file__).resolve().parent.parent / "team" / "roster"

# Parent repo root — the directory that holds `.claude/` AND under which the
# org's child repos are checked out as siblings (per CLAUDE.md § Repository
# Map: `noorinalabs-isnad-graph/`, `noorinalabs-deploy/`, …). Used to locate a
# child repo's own `.claude/team/roster/` when a `gh pr merge --repo
# noorinalabs/<child>` command targets that repo (#552).
_PARENT_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class RosterResolutionError(Exception):
    """Raised when a child repo is named but its roster dir cannot be read.

    Signals the caller to fail in the SAFE direction (HARD BLOCK with a
    diagnostic) rather than silently falling back to the parent-only roster,
    which would re-introduce the #552 false-block / fail-open behavior under a
    different guise (per `feedback_safety_direction_over_ux_friction`).
    """


def _child_roster_dir(repo: str | None) -> Path | None:
    """Resolve the child repo's roster dir from a `--repo OWNER/NAME` value.

    Child repos are checked out as siblings under `_PARENT_REPO_ROOT` (the
    directory holding the parent's `.claude/`), so `noorinalabs/<child>`
    resolves to `_PARENT_REPO_ROOT/<child>/.claude/team/roster` (#552).

    Returns None when:
      - `repo` is absent / malformed (no `OWNER/NAME` shape), or
      - `repo` names the PARENT repo itself (`noorinalabs-main`) — the parent
        roster is already `_ROSTER_DIR`, so there is no distinct child dir.

    A non-None return is a path that the caller is expected to find on disk;
    if it does not exist, that is a hard-block condition (RosterResolutionError),
    NOT a silent parent-only fallback.
    """
    if not repo or "/" not in repo:
        return None
    _owner, _, name = repo.partition("/")
    if not name or name == _PARENT_REPO_ROOT.name:
        return None
    return _PARENT_REPO_ROOT / name / ".claude" / "team" / "roster"


class CommentReviewResult:
    """Result of checking PR comments for charter-format reviews."""

    def __init__(self) -> None:
        self.reviewers: set[str] = set()
        self.reviews_missing_tech_debt: list[str] = []  # reviewer names missing TechDebt line
        self.tech_debt_issue_numbers: list[str] = []  # issue numbers from TechDebt: lines


# Only these RequestOrReplied values represent actual review verdicts that
# REQUIRE the TechDebt attestation line. Request / Reply comments are
# process metadata (review requests, author replies) and do NOT require it.
# Issue #147: the prior implementation flagged any Requestee+RequestOrReplied
# comment, which over-enforced TechDebt on Request/Replied traffic.
#
# Includes both the canonical `ChangesRequested` (one word, charter-line-14)
# and the spaced/short variants observed in practice.
_VERDICT_REQUIRING_TECH_DEBT = {
    "approved",
    "changes requested",
    "changesrequested",
    "changes",
}


def _is_verdict(value: str) -> bool:
    """Return True if a RequestOrReplied value is an actual review verdict.

    Comparison is case-insensitive and whitespace-trimmed. Accepts the
    canonical `ChangesRequested` (per charter line 14), the spaced
    `Changes Requested` form, and the shorter `Changes` variant noted in
    charter discussion as seen in practice. Does NOT accept Request (a
    review request) or Reply / Replied (an author's reply).
    """
    normalized = value.strip().lower()
    # Strip trailing markdown markers and stray punctuation
    normalized = normalized.rstrip("*").strip()
    return normalized in _VERDICT_REQUIRING_TECH_DEBT


def _is_approved(value: str) -> bool:
    """Return True if a RequestOrReplied value is specifically Approved.

    The 2-reviewer rule (charter line 36) counts distinct Requestor values
    across `Approved` comments only — NOT ChangesRequested. A
    ChangesRequested comment is a verdict (TechDebt required) but does not
    contribute to the 2-reviewer threshold.
    """
    normalized = value.strip().lower().rstrip("*").strip()
    return normalized == "approved"


def _strip_code_regions(body: str) -> str:
    """Strip fenced code blocks (```…```) and inline code (`…`) from `body`.

    Returns a body where every char inside a code region is replaced with a
    space (preserving line indices for downstream regex). This prevents
    reviewer prose like `` `Requestor: (TBD)` `` from being captured as the
    actual Requestor value (#511 — Bereket-on-deploy#339 pattern).

    The replacement char is space (not empty) so any `re.search` line/column
    arithmetic remains accurate against the original `body`'s line offsets,
    making `_trailer_block_substring`'s `---`-line detection unaffected.
    """
    out: list[str] = []
    i = 0
    n = len(body)
    while i < n:
        # Fenced code: ```...``` (triple-backtick on its own or with lang tag).
        if body.startswith("```", i):
            end = body.find("```", i + 3)
            if end == -1:
                # Unterminated fence — strip rest of body.
                out.append(" " * (n - i))
                break
            out.append(" " * (end + 3 - i))
            i = end + 3
            continue
        # Inline code: `...` on a single span (no newlines inside the run).
        if body[i] == "`":
            end = body.find("`", i + 1)
            if end == -1 or "\n" in body[i + 1 : end]:
                # Not a closed inline span — pass through as literal.
                out.append(body[i])
                i += 1
                continue
            out.append(" " * (end + 1 - i))
            i = end + 1
            continue
        out.append(body[i])
        i += 1
    return "".join(out)


def _trailer_block_substring(body: str) -> str:
    """Return the trailer-block substring of `body` for field extraction.

    Trailer-block definition (#511):
      - If `body` contains one or more lines that are a sole `---` separator
        (charter convention for delimiting the structured-fields block), the
        trailer is everything AFTER the LAST such separator line.
      - Otherwise (legacy comments without separator), fall back to the full
        body — `_extract_charter_field` then uses last-match-wins to remain
        forgiving while still avoiding most prose-above-trailer false-matches.

    The `---` must be on a line by itself (with optional leading/trailing
    whitespace) to count. Embedded `---` within a sentence does not count.
    """
    lines = body.splitlines(keepends=True)
    last_sep_idx = -1
    for idx, line in enumerate(lines):
        if line.strip() == "---":
            last_sep_idx = idx
    if last_sep_idx == -1:
        return body
    return "".join(lines[last_sep_idx + 1 :])


def _extract_charter_field(field_name: str, body: str) -> str | None:
    """Extract a charter-format field value from a comment body.

    Handles markdown bold (`**Field:**`) and plain (`Field:`) variants.
    Returns the value with markdown markers and parenthetical role
    descriptions stripped. Returns None if the field is not present.

    Match-scope discipline (#511):
      - First, strip fenced (``` ... ```) and inline (`...`) code regions to
        prevent reviewer prose-quoting from being captured as a verdict field
        (Bereket-on-deploy#339 pattern).
      - Then narrow to the trailer-block substring per charter convention
        (text after the last `---` separator line). If no separator is
        present, fall back to the full body to remain backward-compatible
        with legacy verdict comments.
      - Within that scope, use LAST-MATCH-WINS so a prose mention of the
        field above the trailer block (without a separator) does not
        outscore the actual trailer line (Wanjiku-on-main#509 / Lucas-on-
        deploy#337 pattern).
    """
    scope = _trailer_block_substring(_strip_code_regions(body))
    pattern = rf"\*{{0,2}}{re.escape(field_name)}:\*{{0,2}}\s*(.+)"
    matches = list(re.finditer(pattern, scope))
    if not matches:
        return None
    match = matches[-1]
    value = match.group(1).strip()
    # Drop trailing content after first newline (single-line field).
    value = value.split("\n", 1)[0].strip()
    # Strip markdown bold and parenthetical role descriptions.
    value = value.strip("*").strip()
    value = re.sub(r"\s*\(.*?\)\s*$", "", value).strip()
    return value or None


def _name_lastname(full_name: str) -> str:
    """Return the last name from a `Firstname Lastname` or `Firstname.Lastname` string."""
    parts = re.split(r"[\s.]+", full_name)
    if len(parts) >= 2:
        return parts[-1]
    return full_name


def check_comment_reviews(
    pr_number: str | int,
    branch_author_lastname: str,
    repo: str | None = None,
) -> CommentReviewResult:
    """Check PR comments for charter-format review comments from different authors.

    Returns a CommentReviewResult with distinct reviewer names (keyed on full
    name, lowercased) and any reviews missing the mandatory TechDebt line.

    Reviewer identification per charter (resolves #244):
      - Approved / ChangesRequested → reviewer is the Requestor (comment author)
      - Request / Reply → not a review; does not contribute to reviewer set
      - 2-reviewer threshold counts distinct Requestor values across Approved
        comments only (ChangesRequested is a verdict-with-TechDebt but does
        not count toward the threshold).
    """
    result = CommentReviewResult()
    try:
        # Get repo info — prefer --repo flag from the merge command
        if repo and "/" in repo:
            owner, repo_name = repo.split("/", 1)
        else:
            repo_result = subprocess.run(
                ["gh", "repo", "view", "--json", "owner,name"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if repo_result.returncode != 0:
                return result
            repo_data = json.loads(repo_result.stdout)
            owner = repo_data.get("owner", {}).get("login", "")
            repo_name = repo_data.get("name", "")

        # Fetch ALL PR comments via the issues API. `--paginate` concatenates
        # each page's JSON array into one combined response; without it, the
        # hook silently misses reviews appearing after comment #100 (#303).
        # Bumped the subprocess timeout to 30s to give pagination room — most
        # PRs have <100 comments and complete in <5s; the few high-traffic
        # PRs that need multiple pages take longer.
        comments_result = subprocess.run(
            [
                "gh",
                "api",
                "--paginate",
                f"repos/{owner}/{repo_name}/issues/{pr_number}/comments?per_page=100",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if comments_result.returncode != 0:
            return result

        comments = json.loads(comments_result.stdout)
        for comment in comments:
            body = comment.get("body", "")
            requestor = _extract_charter_field("Requestor", body)
            ror_value = _extract_charter_field("RequestOrReplied", body)

            # A charter-format comment must have BOTH Requestor and
            # RequestOrReplied. Comments missing either are not parsed.
            if not (requestor and ror_value):
                continue

            is_verdict_comment = _is_verdict(ror_value)
            is_approved_comment = _is_approved(ror_value)

            # Only Approved comments contribute to the reviewer set toward
            # the 2-reviewer threshold (charter line 36, resolves #244).
            if is_approved_comment:
                reviewer_lastname = _name_lastname(requestor)
                if reviewer_lastname.lower() != branch_author_lastname.lower():
                    result.reviewers.add(requestor.lower())

            # TechDebt attestation is required on every verdict
            # (Approved + ChangesRequested) — issue #147 fix.
            if is_verdict_comment:
                has_tech_debt = re.search(r"\*{0,2}TechDebt:\*{0,2}\s*(.+)", body)
                if not has_tech_debt:
                    # Reviewer name = Requestor on verdicts (charter line 30).
                    result.reviews_missing_tech_debt.append(requestor)
                else:
                    td_value = has_tech_debt.group(1).strip().strip("*").strip()
                    if td_value.lower() != "none":
                        # Extract issue numbers (#15, #16, etc.)
                        issue_nums = re.findall(r"#(\d+)", td_value)
                        result.tech_debt_issue_numbers.extend(issue_nums)

        return result

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return result


def _iter_roster_entries(
    role_prefix_filter: tuple[str, ...] | None = None,
    roster_dir: Path | None = None,
) -> set[str]:
    """Walk a roster dir and return canonical names from `**Name:** <Full Name>`.

    Shared parser for `load_charter_enforcer_names` (role-filtered) and
    `_load_roster_names` (all members). When `role_prefix_filter` is supplied,
    only filenames starting with one of the listed prefixes are read; when
    `None`, every `*.md` in the roster dir contributes.

    `roster_dir` defaults to `_ROSTER_DIR` (the parent repo's roster). Callers
    pass a child repo's roster dir to union child reviewers into the gate (#552).

    Names are returned in lowercase to match `CommentReviewResult.reviewers`'
    dedup key (full name, lowercased). Returns an empty set on any I/O failure
    (fail-closed — see callers for safe-direction semantics).
    """
    roster_dir = roster_dir if roster_dir is not None else _ROSTER_DIR
    names: set[str] = set()
    try:
        if not roster_dir.is_dir():
            return names
        for entry in roster_dir.iterdir():
            if entry.suffix != ".md":
                continue
            if role_prefix_filter is not None and not any(
                entry.name.startswith(p) for p in role_prefix_filter
            ):
                continue
            try:
                content = entry.read_text(encoding="utf-8")
            except OSError:
                continue
            match = re.search(r"\*\*Name:\*\*\s*([^\n]+)", content)
            if match:
                names.add(match.group(1).strip().lower())
    except OSError:
        return set()
    return names


def _resolve_roster_dirs(repo: str | None) -> list[Path]:
    """Return the roster dirs to union for a merge targeting `repo` (#552).

    Always includes the parent `_ROSTER_DIR` (org-level reviewers — Nadia,
    Wanjiku, Santiago, Aino — may review any repo's PR). When `--repo` names a
    distinct child repo, its `.claude/team/roster/` is appended so legitimate
    child-repo reviewers (per CLAUDE.md: child rosters are canonical for
    reviewer pairing) pass the gate.

    Raises `RosterResolutionError` when a child repo IS named but its roster
    dir does not exist — fail in the safe direction (HARD BLOCK) rather than
    silently degrading to parent-only, which would re-block legitimate child
    reviewers exactly as #552 did.
    """
    dirs = [_ROSTER_DIR]
    child_dir = _child_roster_dir(repo)
    if child_dir is not None:
        if not child_dir.is_dir():
            raise RosterResolutionError(
                f"child roster dir not found for --repo '{repo}': {child_dir}"
            )
        dirs.append(child_dir)
    return dirs


def load_charter_enforcer_names(repo: str | None = None) -> set[str]:
    """Read the relevant roster dirs and return canonical charter-enforcer names.

    Charter enforcers are roster files matching the
    `_CHARTER_ENFORCER_ROLE_PREFIXES` allowlist. Each file's
    `**Name:** <Full Name>` line is parsed for the canonical name.

    When `repo` names a child repo, the parent roster is unioned with that
    child's roster (#552) so a child-repo enforcer (e.g. a child Manager /
    Tech Lead / Project Lead) is recognized for the Single-Reviewer Exception.
    Returns an empty set on any I/O failure (fail-closed for the exception
    path: if we can't read the roster, we don't grant the exception).

    Names are returned in lowercase to match `CommentReviewResult.reviewers`'
    dedup key (full name, lowercased).
    """
    names: set[str] = set()
    for roster_dir in _resolve_roster_dirs(repo):
        names |= _iter_roster_entries(
            role_prefix_filter=_CHARTER_ENFORCER_ROLE_PREFIXES, roster_dir=roster_dir
        )
    return names


def _load_roster_names(repo: str | None = None) -> set[str]:
    """Read the relevant roster dirs and return ALL canonical persona names.

    Unlike `load_charter_enforcer_names`, this set is not role-filtered — it
    is the full membership used by the 2-reviewer gate to reject Approved
    verdicts whose Requestor string does not name a real roster persona (#498).

    When `repo` names a child repo, the parent roster is UNIONED with that
    child's `.claude/team/roster/` (#552), so a reviewer valid in EITHER the
    org-level team or the target child repo passes the gate. Without this,
    legitimate child-repo reviewers were filtered as non-roster and child PRs
    could not reach the real 2-reviewer threshold — forcing `--admin`.

    Names are returned in lowercase. Empty set indicates the roster could not
    be read (missing dir or I/O failure); the caller is responsible for
    failing closed. Propagates `RosterResolutionError` when a named child
    roster dir is missing so the caller hard-blocks (safe direction).
    """
    names: set[str] = set()
    for roster_dir in _resolve_roster_dirs(repo):
        names |= _iter_roster_entries(role_prefix_filter=None, roster_dir=roster_dir)
    return names


def is_single_reviewer_exception(
    pr_labels: list[str],
    reviewers: set[str],
    repo: str | None = None,
) -> bool:
    """Return True if the PR qualifies for the Single-Reviewer Exception.

    Strict conditions per charter `pull-requests.md` § Single-Reviewer Exception
    (Wave-Bootstrap Only):
      1. PR is labeled `wave-bootstrap`
      2. There is EXACTLY ONE distinct reviewer in `reviewers`
      3. That reviewer is a charter-enforcer role in the local roster

    When `repo` names a child repo, the enforcer set unions the parent and
    child rosters (#552) so a child-repo enforcer qualifies for the exception
    on that child's PRs.

    Resolves #228 — hook-side enforcement of the charter exception that was
    previously not honored.
    """
    if "wave-bootstrap" not in pr_labels:
        return False
    if len(reviewers) != 1:
        return False
    sole_reviewer = next(iter(reviewers))
    enforcers = load_charter_enforcer_names(repo=repo)
    return sole_reviewer in enforcers


def ensure_issues_on_board(repo: str, issue_numbers: list[str]) -> None:
    """Best-effort add tech-debt issues to the project board."""
    for num in issue_numbers:
        url = f"https://github.com/{ORG}/{repo}/issues/{num}"
        try:
            subprocess.run(
                [
                    "gh",
                    "project",
                    "item-add",
                    str(PROJECT_NUMBER),
                    "--owner",
                    ORG,
                    "--url",
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # Best-effort — don't block merge on board failures


def check(input_data: dict) -> dict | None:
    """Check PR review requirements. Returns result dict if blocking/warning, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    # `--admin` is the emergency override — it bypasses the whole gate
    # (including the batch-loop guard below), matching the existing
    # short-circuit semantics. Checked first so an explicit admin override
    # is honored even for the loop shape.
    if "--admin" in command:
        return None

    # Batch-loop merge guard (#567): a `gh pr merge $pr` inside a for/while
    # loop fail-opens the 2-reviewer gate (the literal-PR parse can't resolve
    # the loop variable, so get_pr_data falls back to the cwd branch and the
    # gate is silently disabled per iteration). HARD BLOCK and instruct
    # one-literal-merge-per-call so the gate stays active — fail in the safe
    # direction (`feedback_safety_direction_over_ux_friction`).
    #
    # This runs BEFORE the `is_merge_command` early-return below ON PURPOSE:
    # `is_merge_command` splits on `&&`/`;`/`|` and checks each segment's
    # FIRST token for `gh pr merge`. In a loop the merge segment leads with
    # the `do` keyword (`do gh pr merge "$pr"`), so `is_merge_command`
    # returns False and `check()` would early-exit — re-opening the exact
    # fail-open hole this guard closes. Detecting the loop shape here is the
    # only placement that fires on it.
    if is_variable_pr_merge_in_loop(command):
        result = {
            "decision": "block",
            "reason": (
                "Batch-loop `gh pr merge` with a shell-variable PR number "
                '(e.g. `for pr in 48 49 50; do gh pr merge "$pr" ...; done`) is '
                "BLOCKED. The 2-reviewer gate parses a LITERAL PR number to fetch "
                "that PR's reviews; a loop variable cannot be resolved at parse "
                "time, so the gate fail-opens and the merge proceeds UNVERIFIED "
                "(this happened twice — P3W11 and P3W13). Merge one PR per call "
                "with a literal number so the gate verifies each PR:\n"
                "  gh pr merge 48 --repo <owner/repo> --merge\n"
                "  gh pr merge 49 --repo <owner/repo> --merge\n"
                "Run them as separate commands (not a loop). Each literal merge "
                "is checked for two distinct Approved reviewers individually."
            ),
        }
        log_pretooluse_block("validate_pr_review", command, result["reason"])
        return result

    # Not the loop shape — only a plain `gh pr merge <N>` invocation is gated
    # below. Anything else (gh pr list/view/create, git merge, …) is allowed.
    if not is_merge_command(command):
        return None

    pr_number = extract_pr_number(command)
    repo = extract_repo(command)
    pr_data = get_pr_data(pr_number, repo=repo)

    if pr_data is None:
        return {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not verify PR review status. "
                "Ensure the PR has at least one peer review before merging."
            ),
        }

    author = pr_data["author"]
    reviews = pr_data["reviews"]
    head_ref = pr_data["headRefName"]
    number = pr_data["number"]
    labels = pr_data["labels"]

    formal_reviewers: set[str] = set()
    for review in reviews:
        login = review.get("author", {}).get("login", "")
        if login and login != author:
            formal_reviewers.add(login.lower())

    comment_review_result = CommentReviewResult()
    branch_author_lastname = None
    if head_ref:
        branch_author_lastname = extract_branch_author_lastname(head_ref)
        if branch_author_lastname:
            comment_review_result = check_comment_reviews(number, branch_author_lastname, repo=repo)
        elif head_ref.startswith("deployments/") and "/wave-" in head_ref:
            # Wave-merge PR (head = deployments/phase-{N}/wave-{M}); no implementer-branch
            # author. Pass empty sentinel so the reviewer-vs-author lastname comparison
            # admits any non-empty reviewer name. See main#294.
            comment_review_result = check_comment_reviews(number, "", repo=repo)

    pr_display = f"#{pr_number}" if pr_number else "(current branch)"

    # Filter charter-format (comment-based) reviewers against the roster before
    # counting them toward the 2-reviewer gate (#498). The 2-reviewer rule
    # exists to ensure two distinct ROSTER MEMBERS reviewed; without this
    # filter, fictional / non-roster Requestor strings (e.g., the P3W11 #487
    # "Camila Restrepo" / "Imelda Santos" incident) slip through unchallenged.
    # Formal GitHub reviews (`formal_reviewers`) are NOT filtered — those are
    # real GitHub identities authenticated by the platform, not persona names
    # that need cross-checking against `.claude/team/roster/`.
    #
    # The roster is resolved relative to the PR's TARGET repo (#552): the parent
    # roster is unioned with the named child repo's `.claude/team/roster/`, so a
    # reviewer valid in EITHER the org-level team or the target child repo
    # passes. If a child repo is named but its roster dir is unreadable, fail in
    # the SAFE direction (HARD BLOCK with diagnostic — never silent parent-only
    # fallback, which would re-block legitimate child reviewers as #552 did).
    try:
        roster_names = _load_roster_names(repo=repo)
    except RosterResolutionError as exc:
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: PR {pr_display} targets a child repo whose roster directory "
                "could not be resolved, so the 2-reviewer gate cannot validate reviewer "
                "names.\n"
                f"Detail: {exc}\n"
                "Hook 4 resolves the reviewer roster relative to the PR's target repo "
                "(#552): the parent `.claude/team/roster/` is unioned with the named child "
                "repo's `.claude/team/roster/`. The child roster dir was named via "
                "`--repo` but does not exist on disk.\n"
                "Fix one of:\n"
                "  - Ensure the child repo is checked out as a sibling of the parent repo "
                "with a populated `.claude/team/roster/`.\n"
                "  - Correct the `--repo OWNER/NAME` value if the repo name is wrong.\n"
                "Pass `--admin` for emergency overrides only."
            ),
        }
        log_pretooluse_block("validate_pr_review", command, result["reason"])
        return result

    non_roster_requestors = {r for r in comment_review_result.reviewers if r not in roster_names}
    roster_comment_reviewers = comment_review_result.reviewers - non_roster_requestors

    distinct_reviewers = formal_reviewers | roster_comment_reviewers
    total_distinct = len(distinct_reviewers)

    # Single-Reviewer Exception (resolves #228) — wave-bootstrap PRs reviewed
    # by a charter enforcer may merge with one Approved comment instead of
    # two. Charter-enforcer role check uses the target-repo-resolved roster.
    if total_distinct == 1 and is_single_reviewer_exception(labels, distinct_reviewers, repo=repo):
        # Exception applies — fall through to TechDebt check, then allow.
        pass
    elif total_distinct < 2:
        # If the shortfall is wholly or partly caused by non-roster Requestor
        # strings, prepend a dedicated diagnostic that names them (#498). The
        # general 2-reviewer guidance still follows below.
        roster_diagnostic = ""
        if non_roster_requestors:
            sample_roster = sorted(roster_names)[:20]
            sample_label = (
                f"Valid roster ({len(roster_names)} total, first 20): {', '.join(sample_roster)}"
                if roster_names
                else "Valid roster: <empty — local roster dir could not be read>"
            )
            raw_total = len(comment_review_result.reviewers)
            roster_count = len(roster_comment_reviewers)
            roster_diagnostic = (
                f"BLOCKED: PR {pr_display} has {raw_total} distinct Requestor string(s) "
                f"on Approved verdicts but only {roster_count} are recognized roster "
                "members.\n"
                f"Non-roster: {', '.join(sorted(non_roster_requestors))}\n"
                f"{sample_label}\n"
                "Hook 4 (#498) requires every Approved verdict's Requestor to match a "
                "persona in `.claude/team/roster/` — non-roster Requestor strings do "
                "NOT count toward the 2-reviewer threshold. Re-post the verdict under a "
                "roster persona, or amend the roster if this is a new member.\n\n"
            )
        result = {
            "decision": "block",
            "reason": (
                roster_diagnostic
                + f"BLOCKED: PR {pr_display} has {total_distinct}/2 required peer reviews. "
                "At least TWO Approved reviews from distinct non-authors are required before "
                "merge.\n"
                "Charter § Comment-Based Reviews counts distinct Requestor values across "
                "Approved comments (resolves main#244).\n"
                "Use `gh pr comment <PR#> --body '...'` with charter format:\n"
                "  Requestor: <reviewer>  Requestee: <PR author>  "
                "RequestOrReplied: Approved  TechDebt: none | #issue, ...\n\n"
                "Common failure mode — Reply vs Approved:\n"
                "  RequestOrReplied: Reply / Replied / Request / ChangesRequested do NOT\n"
                "  count toward the 2-reviewer threshold, EVEN IF the body prose says\n"
                '  "Approved" or "looks good." The hook parses the RequestOrReplied:\n'
                "  field directly — body prose is not inspected for verdict signals.\n"
                "  If a reviewer's intent was to approve, they must post a NEW comment\n"
                "  with `RequestOrReplied: Approved` (Reply comments cannot be edited\n"
                "  in-place to change the field).\n\n"
                "Common failure mode — Requestor / Requestee swap:\n"
                "  Requestor is the REVIEWER (the team member POSTING the comment).\n"
                "  Requestee is the PR AUTHOR (the team member ADDRESSED by the\n"
                "  comment). The hook counts distinct Requestor values across Approved\n"
                "  comments. If two reviewers BOTH set `Requestor:` to the PR author\n"
                "  (treating Requestor as 'addressed-to'), the hook sees 1 distinct\n"
                "  reviewer (the author's name, twice) even though two people approved.\n"
                "  This is the W9 PR#349 cascade root cause — orchestrator spawn brief\n"
                "  template had the fields swapped; 7 reviewer comments posted before\n"
                "  the hook surfaced the count mismatch.\n"
                "  Diagnose the swap directly:\n"
                "    gh api repos/<owner>/<repo>/issues/<PR>/comments \\\n"
                "      --jq '[.[] | select(.body | "
                'contains("RequestOrReplied: Approved"))\n'
                "             | .body "
                '| capture("Requestor: *(?<r>[^\\\\n]+)") '
                "| .r] | unique'\n"
                "  Expected: distinct reviewer names. Seen: PR author's name repeated\n"
                "  → swap. Charter `pull-requests.md § Comment-Based Reviews` Direction\n"
                "  table (Approved row): Requestor=reviewer, Requestee=PR author.\n\n"
                "Diagnose the count yourself before retrying merge:\n"
                "  gh api repos/<owner>/<repo>/issues/<PR>/comments \\\n"
                "    --jq '[.[] | select(.body | "
                'contains("RequestOrReplied: Approved"))] | length\'\n\n'
                "Common failure mode — prose-mention of fields outside the trailer block:\n"
                "  As of #511 the hook ONLY extracts Requestor/RequestOrReplied from the\n"
                "  trailer-block substring (after the LAST `---` separator line) and ignores\n"
                "  matches inside backticks/code fences. If your verdict comment quotes\n"
                "  field syntax in prose (e.g., describing the PR body's trailer), make\n"
                "  sure the actual structured-fields block follows a `---` separator AND\n"
                "  is the very last block. Inline-code fences (`Requestor: foo`) and fenced\n"
                "  code (``` ... ```) are stripped before matching.\n"
                "  Historical instances driving this enforcement (P3W11 batch 11, 2026-05-19):\n"
                "    - main#509 — Wanjiku's prose described the bare-line block; captured\n"
                "      Requestor as rest-of-line garbage; 1/2 false-block.\n"
                "    - deploy#337 — Lucas noted PR body lacked the trailer; captured\n"
                "      garbage Requestor; 1/2 false-block.\n"
                "    - deploy#339 — Bereket quoted `Requestor: (TBD — orchestrator will\n"
                "      assign)`; captured TBD as Requestor; 1/2 false-block.\n"
                "  All three required orchestrator REST PATCH pre-#511 fix.\n\n"
                "Single-Reviewer Exception (charter § Single-Reviewer Exception (Wave-Bootstrap "
                "Only)): label PR `wave-bootstrap` AND have a charter-enforcer review (Standards "
                "Lead, Manager, Tech Lead, Project Lead, or Program Director).\n"
                "Pass `--admin` for emergency overrides only.\n"
                "See memory feedback_validate_pr_review_approved_not_reply.md for full context."
            ),
        }
        log_pretooluse_block("validate_pr_review", command, result["reason"])
        return result

    missing = comment_review_result.reviews_missing_tech_debt
    if missing:
        names = ", ".join(missing)
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: PR {pr_display} has review(s) missing the mandatory "
                f"TechDebt: attestation line.\n"
                f"Reviewers without TechDebt line: {names}\n"
                "Charter § Comment-Based Reviews requires every Approved/ChangesRequested "
                "comment to include:\n"
                "  TechDebt: none        (if no tech-debt found)\n"
                "  TechDebt: #15, #16    (if issues were filed)\n"
                "Reviewer must create tech-debt labeled issues for all non-blocking "
                "findings BEFORE posting the verdict.\n"
                "Pass `--admin` for emergency overrides only."
            ),
        }
        log_pretooluse_block("validate_pr_review", command, result["reason"])
        return result

    # All checks passed — ensure any referenced tech-debt issues are on the board
    td_issues = comment_review_result.tech_debt_issue_numbers
    if td_issues:
        board_repo_name = ""
        if repo and "/" in repo:
            board_repo_name = repo.split("/", 1)[1]
        else:
            try:
                repo_result = subprocess.run(
                    ["gh", "repo", "view", "--json", "name"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if repo_result.returncode == 0:
                    board_repo_name = json.loads(repo_result.stdout).get("name", "")
            except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
                pass
        if board_repo_name:
            ensure_issues_on_board(board_repo_name, td_issues)

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
