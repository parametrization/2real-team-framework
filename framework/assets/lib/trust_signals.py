#!/usr/bin/env python3
"""Per-engineer mechanical trust signals + evidence-anchored scoring.

Replaces narrative self-grading in a trust matrix with **countable** signals
derived from an iteration's merged-PR set. The trust delta a retro records is no
longer "felt" — it is derived from numbers and must cite them.

Two cleanly separated layers:

  * **Extraction** (SCM-dependent) — :func:`extract_signals` builds a
    ``{engineer_name: Signals}`` map from the merged-PR set, reading the repo
    list and integration-branch convention from the framework config and parsing
    each PR's verdict comments for the ``Requestor:`` / ``RequestOrReplied:``
    review-verdict shape.

  * **Scoring** (pure, no I/O) — :func:`score_delta`, :func:`decay`,
    :func:`apply_distribution_discipline`, :func:`negative_signal_line`,
    :func:`validate_negative_signal_pass`, :func:`retirement_trigger`. Every one
    is a pure function so the model is unit-testable, and usable standalone on a
    hand-built signal dict, without touching the SCM at all.

Signals per engineer (all integers, all countable from the merged-PR set):

  ===========================  ============================================
  prs_merged                   PRs merged this iteration with them as commit
                               author.
  must_fix_received            ChangesRequested verdicts on PRs they
                               authored (negative — author signal).
  must_fix_caught              ChangesRequested verdicts they issued as the
                               Requestor/reviewer (positive — review
                               signal).
  ci_red_merges                PRs they authored that merged with a failing
                               required check (negative — hard ding).
  rework_cycles                PRs they authored that needed >=1 rework
                               round (received >=1 ChangesRequested).
  review_false_positives       must-fix items they raised that were later
                               marked withdrawn/false-positive (negative —
                               review-quality signal).
  ===========================  ============================================

CLI:
  trust_signals.py extract <wave> [--label L] [--status PATH]   # signals JSON
  trust_signals.py score   <wave> [--label L] [--status PATH]   # signals +
                                                                # proposed deltas
                                                                # + forced
                                                                # negative line
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# The shared config loader lives in the framework's hooks dir. This lib lives in
# the sibling lib/ dir; mirror pr_ci_state.py's lib->hooks import bridge so the
# scoring half stays importable wherever the framework is deployed.
_HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))

from _framework_config import config  # noqa: E402

# Every gh subprocess call carries a timeout so a hung network call can never
# wedge the tool indefinitely.
_GH_TIMEOUT = 60

# Neutral / default trust score. Decay drifts unsignalled scores back to it.
NEUTRAL = 3
MIN_SCORE = 1
MAX_SCORE = 5

# Decay: no trust-relevant signal for this many iterations → drift one step
# toward NEUTRAL (a 4 with nothing to say for 3 iterations is no longer a 4).
DECAY_AFTER_WAVES = 3

# Retirement: sustained bottom-tier or repeated CI-red merges over K iterations.
RETIRE_AFTER_WAVES = 3
BOTTOM_TIER = 2

# A verdict comment field, e.g. ``Requestor: Jane Doe`` or the bold form
# ``**Requestor:** Jane Doe``. Optional surrounding ``**`` on the label AND the
# value; value trimmed of trailing bold.
_FIELD_RE = {
    "requestor": re.compile(r"^\**Requestor\**:\**\s*(.+?)\**\s*$", re.MULTILINE),
    "requestee": re.compile(r"^\**Requestee\**:\**\s*(.+?)\**\s*$", re.MULTILINE),
    "verdict": re.compile(r"^\**RequestOrReplied\**:\**\s*(\w+)", re.MULTILINE),
}

# A verdict comment is a "false positive" when its author explicitly retracts it
# (withdrawn / false-positive / retracted). Heuristic, deliberately conservative
# — only a self-marked retraction counts, never an inferred one.
_FALSE_POSITIVE_RE = re.compile(
    r"\b(false[\s-]?positive|withdrawn|withdraw|retracted|retract|invalid finding)\b",
    re.IGNORECASE,
)


def _strip_code_markup(text: str) -> str:
    """Remove fenced code blocks and inline code spans from *text*.

    Called before :data:`_FALSE_POSITIVE_RE` is applied so that symbol names
    and test identifiers that happen to contain the retraction vocabulary
    (e.g. ``test_no_false_positive_type`` inside a code span) are not
    mistaken for genuine self-withdrawal language.  The removal is
    positional — we replace each code region with whitespace of the same
    length so that surrounding context positions are preserved for any
    subsequent line-oriented parsing, though :data:`_FALSE_POSITIVE_RE`
    does not rely on positions.
    """
    # Fenced blocks first (```...``` or ~~~...~~~, possibly multiline).
    text = re.sub(
        r"```.*?```|~~~.*?~~~", lambda m: " " * len(m.group()), text, flags=re.DOTALL
    )
    # Inline code spans (`...`); single-backtick, non-newline interior.
    text = re.sub(r"`[^`\n]+`", lambda m: " " * len(m.group()), text)
    return text


@dataclass
class Signals:
    """Countable per-engineer signals for one iteration. All fields are evidence."""

    prs_merged: int = 0
    must_fix_received: int = 0
    must_fix_caught: int = 0
    ci_red_merges: int = 0
    rework_cycles: int = 0
    review_false_positives: int = 0
    # PR numbers the engineer authored (for the evidence citation in the line).
    authored_prs: list[int] = field(default_factory=list)

    def has_signal(self) -> bool:
        """True if anything trust-relevant happened — drives the decay path."""
        return any(
            (
                self.prs_merged,
                self.must_fix_received,
                self.must_fix_caught,
                self.ci_red_merges,
                self.rework_cycles,
                self.review_false_positives,
            )
        )

    def has_negative(self) -> bool:
        return bool(
            self.must_fix_received or self.ci_red_merges or self.review_false_positives
        )


@dataclass
class Verdict:
    """A parsed verdict comment: who reviewed whom, the call, and retraction."""

    requestor: str | None
    requestee: str | None
    verdict: str | None
    false_positive: bool


def parse_verdicts(comment_bodies: list[str]) -> list[Verdict]:
    """Parse the review-verdict comment shape out of a PR's comment bodies.

    Pure function — no I/O. Accepts both the bare (``Requestor: Name``) and bold
    (``**Requestor:** Name``) forms. A comment with no ``RequestOrReplied`` line
    is not a verdict and is skipped.
    """
    out: list[Verdict] = []
    for body in comment_bodies:
        verdict_m = _FIELD_RE["verdict"].search(body)
        if not verdict_m:
            continue
        req_m = _FIELD_RE["requestor"].search(body)
        ree_m = _FIELD_RE["requestee"].search(body)
        verdict_str = verdict_m.group(1).strip()
        # A retraction only counts when the reviewer actually raised a
        # finding — approvals are never retractions.  Also strip code
        # spans and fenced blocks first so symbol/test names that contain
        # the retraction vocabulary (e.g. `test_no_false_positive_*`) are
        # not matched.
        if verdict_str.lower() == "approved":
            is_false_positive = False
        else:
            is_false_positive = bool(
                _FALSE_POSITIVE_RE.search(_strip_code_markup(body))
            )
        out.append(
            Verdict(
                requestor=req_m.group(1).strip() if req_m else None,
                requestee=ree_m.group(1).strip() if ree_m else None,
                verdict=verdict_str,
                false_positive=is_false_positive,
            )
        )
    return out


def _is_changes_requested(verdict: str | None) -> bool:
    return verdict is not None and verdict.lower() == "changesrequested"


# ---------------------------------------------------------------------------
# Extraction layer (SCM-coupled). The scoring layer below works standalone on a
# hand-built signal dict even if everything in this section is unavailable.
# ---------------------------------------------------------------------------


def _run_gh(args: list[str]) -> str:
    """Run ``gh <args>`` with an explicit arg list and return stdout.

    Never a shell string and never ``shell=True`` — an explicit arg vector means
    no word-splitting, so a multi-word value can never collapse. Carries a
    timeout so a hung call cannot wedge the tool.
    """
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=_GH_TIMEOUT,
    )
    return proc.stdout


def _resolve_repos(cfg) -> list[str]:
    """Resolve the iteration's repo set as ``owner/name`` strings.

    Reads ``scm.owner`` + ``project.repos`` from config. Each repo may already
    be ``owner/name`` (used as-is) or a bare name (prefixed with ``scm.owner``).
    With no configured repos, falls back to the single repo resolved from the
    current working directory (``gh repo view``).
    """
    owner = cfg.get("scm.owner")
    repos = cfg.get("project.repos") or []
    if repos:
        out: list[str] = []
        for r in repos:
            r = str(r)
            out.append(r if "/" in r else (f"{owner}/{r}" if owner else r))
        return out
    # Fall back to a single repo: whatever the cwd points at.
    try:
        nwo = _run_gh(
            ["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]
        ).strip()
    except (subprocess.SubprocessError, OSError):
        nwo = ""
    return [nwo] if nwo else []


def _integration_base(cfg, wave: str) -> str:
    """The merged-PR base branch for *wave*, from the integration-branch template.

    PROJECT-COUPLING: the original tool scoped the base to a phase+wave path
    (``deployments/phase-<P>/wave-<M>``). Here the base is derived generically
    from the configured ``branch.integration`` template (default
    ``deployments/wave-{wave}``) so it tracks whatever branching scheme a project
    declares. A project whose merges target the default branch directly should
    set ``branch.integration`` to that branch name.
    """
    template = cfg.get("branch.integration", "deployments/wave-{wave}")
    try:
        return str(template).format(wave=wave)
    except (KeyError, IndexError):
        return str(template)


def _kickoff_ts(wave: str, status_path: Path | None) -> str | None:
    """Cross-window filter boundary — a merge timestamp lower-bound, or None.

    PROJECT-COUPLING: keyed on a state-file entry named ``wave_<id>_kicked_off_at``
    written by an iteration-kickoff workflow. Absent in a generic project (or
    when the state file is missing/unreadable) → no filter is applied and the
    base-branch scoping alone selects the iteration's PRs, which is the safe
    default. Drop this read entirely if your project has no kickoff timestamp.
    """
    if status_path is None:
        return None
    try:
        data = json.loads(Path(status_path).read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    val = data.get(f"wave_{wave}_kicked_off_at")
    return str(val) if val else None


def _pr_comment_bodies(repo: str, number: int) -> list[str]:
    """Every issue-comment body on a PR (verdict comments live here)."""
    raw = _run_gh(
        [
            "api",
            f"repos/{repo}/issues/{number}/comments",
            "--jq",
            "[.[].body]",
        ]
    )
    parsed = json.loads(raw or "[]")
    return [str(b) for b in parsed]


def _pr_ci_is_red(repo: str, number: int) -> bool:
    """True if the PR's latest status rollup carries a failing required check.

    Reads ``statusCheckRollup`` at the PR head. Post-merge this reflects the
    final state of the merged head, the closest mechanical proxy for "merged
    with red CI" available after the fact. Treats both the checks-API
    ``conclusion`` and the legacy commit-status ``state`` failure vocabularies as
    red.
    """
    raw = _run_gh(
        [
            "pr",
            "view",
            str(number),
            "--repo",
            repo,
            "--json",
            "statusCheckRollup",
            "--jq",
            ".statusCheckRollup",
        ]
    )
    rollup = json.loads(raw or "[]") or []
    red = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"}
    for check in rollup:
        status = (check.get("conclusion") or check.get("state") or "").upper()
        if status in red:
            return True
    return False


def merged_prs(
    wave: str,
    status_path: Path | None = None,
    *,
    label: str | None = None,
    cfg=None,
) -> list[dict]:
    """Build the iteration's merged-PR set across every in-scope repo.

    For each repo: list merged PRs whose base is the iteration's integration
    branch (and optionally carrying *label*), drop any merged before the kickoff
    timestamp if one is recorded, and attach the head commit's author name (the
    author identity the signals are bucketed by).
    """
    cfg = cfg or config()
    repos = _resolve_repos(cfg)
    base = _integration_base(cfg, wave)
    kickoff = _kickoff_ts(wave, status_path)

    out: list[dict] = []
    for repo in repos:
        list_args = [
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "merged",
            "--base",
            base,
            "--json",
            "number,headRefOid,mergedAt,author",
        ]
        if label:
            list_args += ["--label", label]
        listed = json.loads(_run_gh(list_args) or "[]")
        for pr in listed:
            merged_at = pr.get("mergedAt") or ""
            if kickoff and merged_at < kickoff:
                continue
            sha = pr["headRefOid"]
            commit_author = _run_gh(
                [
                    "api",
                    f"repos/{repo}/commits/{sha}",
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


def extract_signals(
    wave: str,
    status_path: Path | None = None,
    *,
    label: str | None = None,
    cfg=None,
) -> dict[str, Signals]:
    """Build the ``{engineer_name: Signals}`` map for one iteration.

    Author identity is the head commit's author name (``commit_author_name``).
    Reviewer identity is the ``Requestor:`` field of the verdict comment, because
    the SCM principal that posts the comment is typically the orchestrator, not
    the reviewer.
    """
    cfg = cfg or config()
    prs = merged_prs(wave, status_path, label=label, cfg=cfg)
    signals: dict[str, Signals] = {}

    def _bucket(name: str) -> Signals:
        return signals.setdefault(name, Signals())

    for pr in prs:
        author = pr.get("commit_author_name") or "(unknown)"
        repo = pr["repo"]
        number = pr["number"]

        author_sig = _bucket(author)
        author_sig.prs_merged += 1
        author_sig.authored_prs.append(number)

        if _pr_ci_is_red(repo, number):
            author_sig.ci_red_merges += 1

        verdicts = parse_verdicts(_pr_comment_bodies(repo, number))
        pr_had_changes_requested = False
        for v in verdicts:
            if _is_changes_requested(v.verdict):
                pr_had_changes_requested = True
                author_sig.must_fix_received += 1
                if v.requestor:
                    _bucket(v.requestor).must_fix_caught += 1
            if v.false_positive and v.requestor:
                _bucket(v.requestor).review_false_positives += 1
        if pr_had_changes_requested:
            author_sig.rework_cycles += 1

    return signals


# ---------------------------------------------------------------------------
# Scoring layer (pure, no I/O). Preserved exactly — the arithmetic, thresholds,
# and clamps are the value of this module. Callable on any hand-built Signals.
# ---------------------------------------------------------------------------


def score_delta(sig: Signals) -> int:
    """Evidence-anchored, **bidirectional** trust delta for one iteration.

    Pure function of the countable signals — never a narrative judgement. The
    mapping is intentionally simple and symmetric, clamped to [-2, +2] so a
    single iteration cannot swing trust across the whole scale:

      negative
        - each CI-red merge:                      -1  (hard ding)
        - each review false-positive:             -1
        - 3+ must-fix items received as author:   -1
      positive (only when the iteration is clean of the negatives above)
        - 2+ PRs merged clean:                    +1
        - 2+ must-fix items caught as reviewer:   +1
    """
    delta = 0
    delta -= sig.ci_red_merges
    delta -= sig.review_false_positives
    if sig.must_fix_received >= 3:
        delta -= 1

    clean = not sig.has_negative()
    if clean:
        if sig.prs_merged >= 2:
            delta += 1
        if sig.must_fix_caught >= 2:
            delta += 1

    return max(-2, min(2, delta))


def decay(
    old_score: int, waves_since_signal: int, *, after: int = DECAY_AFTER_WAVES
) -> int:
    """Drift an unsignalled score one step toward NEUTRAL after ``after`` iterations.

    No signal for N iterations is itself a (weak) signal: a stale 4 or 2 is no
    longer earned. Drifts a single step per call so decay is gradual, never a
    reset.
    """
    if waves_since_signal < after:
        return old_score
    if old_score > NEUTRAL:
        return old_score - 1
    if old_score < NEUTRAL:
        return old_score + 1
    return NEUTRAL


def apply_distribution_discipline(
    proposals: dict[str, tuple[int, Signals]],
) -> dict[str, int]:
    """Cap 5 to the iteration's exceptional **relative** performers (distribution
    discipline). 5 is reserved — it is not handed out for merely-clean work.

    ``proposals`` maps name → (proposed_new_score, signals). A proposed 5 is
    allowed only for the engineer(s) whose composite signal score is the
    iteration maximum AND strictly positive; every other proposed 5 is capped to
    4. Scores of 4 and below pass through untouched.
    """

    def composite(s: Signals) -> int:
        # Reward output + good reviewing; penalise the negatives. Pure ranking
        # key, not a trust score.
        return (
            s.prs_merged
            + s.must_fix_caught
            - s.must_fix_received
            - 2 * s.ci_red_merges
            - 2 * s.review_false_positives
        )

    if not proposals:
        return {}
    top = max(composite(s) for _, (_, s) in proposals.items())
    out: dict[str, int] = {}
    for name, (proposed, sig) in proposals.items():
        if proposed >= MAX_SCORE and not (composite(sig) == top and top > 0):
            out[name] = MAX_SCORE - 1
        else:
            out[name] = proposed
    return out


def negative_signal_line(name: str, sig: Signals) -> str:
    """The forced negative-signal pass line for one engineer.

    Bans the bare ``None``: every active engineer gets either a specific,
    evidence-backed gap OR an explicit ``metrics clean: {numbers}`` statement
    that still shows the receipts. Never returns an empty / "None" string.
    """
    if sig.has_negative():
        gaps = []
        if sig.ci_red_merges:
            gaps.append(f"{sig.ci_red_merges} CI-red merge(s)")
        if sig.must_fix_received:
            gaps.append(f"{sig.must_fix_received} must-fix received")
        if sig.review_false_positives:
            gaps.append(f"{sig.review_false_positives} review false-positive(s)")
        return f"{name}: " + ", ".join(gaps)
    return (
        f"{name}: metrics clean: prs_merged={sig.prs_merged}, "
        f"must_fix_received=0, ci_red_merges=0, false_positives=0, "
        f"must_fix_caught={sig.must_fix_caught}"
    )


# Bare-"None" detector for the forced negative-signal pass. A negative-signal
# entry of exactly "None" / "n/a" / "-" (case-insensitive, optional bullet /
# trailing punctuation) is the banned shape.
_BARE_NONE_RE = re.compile(r"^\s*[-*]?\s*(none|n/?a|-+)\s*[.;]?\s*$", re.IGNORECASE)


def validate_negative_signal_pass(lines: list[str]) -> list[str]:
    """Return the offending lines that are a bare "None" (forced-pass violation).

    Empty return == the pass is clean. Used by a retro to mechanically reject a
    pass that left a bare "None" in the negative-signal column.
    """
    return [ln for ln in lines if _BARE_NONE_RE.match(ln)]


def retirement_trigger(
    score_history: list[int],
    ci_red_history: list[int],
    *,
    k: int = RETIRE_AFTER_WAVES,
) -> tuple[bool, str]:
    """Performance-triggered exit. Returns (should_retire, reason).

    Two independent triggers over the most recent ``k`` iterations (oldest→newest):
      * sustained bottom-tier: score <= BOTTOM_TIER in each of the last k.
      * repeated CI-red merges: >=1 CI-red merge in each of the last k.

    Fewer than k iterations of history never triggers — there isn't enough
    evidence.
    """
    recent_scores = score_history[-k:]
    if len(recent_scores) >= k and all(s <= BOTTOM_TIER for s in recent_scores):
        return True, (
            f"sustained bottom-tier: score <= {BOTTOM_TIER} for {k} consecutive "
            f"iterations ({recent_scores})"
        )
    recent_ci = ci_red_history[-k:]
    if len(recent_ci) >= k and all(c >= 1 for c in recent_ci):
        return True, (
            f"repeated CI-red merges: >=1 in each of {k} consecutive iterations ({recent_ci})"
        )
    return False, ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _default_status() -> Path | None:
    """Configured state-file path (``paths.state_file``), or None if unset."""
    raw = config().get("paths.state_file")
    return Path(raw) if raw else None


def _cmd_extract(args: argparse.Namespace) -> int:
    sigs = extract_signals(args.wave, args.status, label=args.label)
    print(json.dumps({n: asdict(s) for n, s in sigs.items()}, indent=2, sort_keys=True))
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    sigs = extract_signals(args.wave, args.status, label=args.label)
    proposals = {n: (NEUTRAL + score_delta(s), s) for n, s in sigs.items()}
    disciplined = apply_distribution_discipline(proposals)
    report = {
        n: {
            "signals": asdict(s),
            "delta": score_delta(s),
            "proposed_from_neutral": disciplined[n],
            "negative_signal_line": negative_signal_line(n, s),
        }
        for n, s in sigs.items()
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("wave", help="iteration / wave id")
        p.add_argument(
            "--label",
            default=None,
            help="optional issue/PR label to additionally filter the merged-PR set",
        )
        p.add_argument(
            "--status",
            type=Path,
            default=_default_status(),
            help="path to the project state file (default: config paths.state_file)",
        )

    p_extract = sub.add_parser("extract", help="emit per-engineer signals as JSON")
    _add_common(p_extract)
    p_extract.set_defaults(func=_cmd_extract)

    p_score = sub.add_parser("score", help="emit signals + proposed deltas as JSON")
    _add_common(p_score)
    p_score.set_defaults(func=_cmd_score)
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except subprocess.TimeoutExpired as exc:
        print(
            f"ERROR: gh call timed out after {exc.timeout}s: {' '.join(exc.cmd)}",
            file=sys.stderr,
        )
        return 1
    except subprocess.CalledProcessError as exc:
        print(
            f"ERROR: gh call failed (exit {exc.returncode}): {' '.join(exc.cmd)}\n{exc.stderr}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
