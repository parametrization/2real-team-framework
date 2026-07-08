#!/usr/bin/env python3
"""Per-engineer mechanical trust signals + evidence-anchored scoring.

Replaces narrative self-grading in a trust matrix with **countable** signals
derived from an iteration's merged-PR set. The trust delta a retro records is no
longer "felt" — it is derived from numbers and must cite them.

Two cleanly separated layers:

  * **Extraction** (SCM-dependent) — :func:`extract_signals` builds a
    ``{engineer_name: Signals}`` map from the merged-PR set, reading the repo
    list and integration-branch convention from the framework config and parsing
    each PR's verdict comments for the charter's ``Requestor:`` /
    ``Requestee:`` / ``RequestOrReplied:`` shape. The charter carries review
    *severity* in the comment **body** — an enumerated ``Must-fix:`` list — not
    in the verdict token, so a ``Request`` verdict whose body lists must-fix
    items is the changes-requested signal, while ``Replied`` (and a ``Request``
    with ``Must-fix: None`` / no must-fix section) is clean. The legacy
    explicit-token vocabulary (``ChangesRequested`` / ``Approved``) is still
    recognized so a project that emits a machine verdict token directly also
    scores.

  * **Scoring** (pure, no I/O) — :func:`score_delta`, :func:`decay`,
    :func:`apply_distribution_discipline`, :func:`negative_signal_line`,
    :func:`validate_negative_signal_pass`, :func:`retirement_trigger`. Every one
    is a pure function so the model is unit-testable, and usable standalone on a
    hand-built signal dict, without touching the SCM at all.

Durable review-catch ledger (#164)
-----------------------------------
The charter's verdict-amendment convention has a reviewer edit their blocking
``Request``/``Must-fix:`` comment **in place** to ``Replied``/``Must-fix: None``
once the fix lands. Because extraction used to derive ``must_fix_caught`` /
``must_fix_received`` purely by re-parsing the PR's *current* comment bodies,
an amendment silently erased the historic catch — the reviewer's signal
vanished and, if they authored no PRs of their own, they dropped out of the
engineer map entirely (Phase 6 Wave 1: the wave's standout reviewer scored
``must_fix_caught=0``).

Fix (design option (b) from #164/#165 — chosen over reading GitHub comment
edit-history or a distinct ``Replied``-follow-up convention change: it needs no
new SCM/API dependency and keeps the signal durable at the moment it is
created): :func:`record_review_catch` durably appends one entry per
changes-requested verdict to ``wave_{wave}_review_catches`` in the project
state file, **at issue time** — i.e. the moment the blocking verdict comment is
posted, before any later amendment can erase it. :func:`extract_signals` reads
this ledger (:func:`_review_catches_for_wave`) and, for any PR that has >=1
recorded catch, treats the ledger as **authoritative** for that PR's
changes-requested accounting instead of re-deriving it from the (possibly
already-amended) live comment body. A PR with no ledger entry falls back to the
legacy live-comment-parsing path unchanged, so projects/waves that predate this
ledger keep scoring exactly as before.

CLI: ``trust_signals.py record-catch <wave> --repo O/N --pr P --requestor R
--requestee E`` — meant to be invoked immediately after posting a blocking
verdict comment (see the module CLI section below).

Edit-history catch crediting + difficulty weight (#229)
-------------------------------------------------------
The #164 ledger only credits a catch that someone *remembered* to record at
issue time. Wave 13 exposed the gap: the merge-gate oracle (``pr_review_state``)
REQUIRES a reviewer to resolve a blocking ``Request`` by editing it in place to
``Replied`` / ``Must-fix: None`` (any *current* comment parsing as a Must-fix
blocks the merge), but the scorer read that same current state — so once the
reviewer amended their comment the catch scored ``must_fix_caught=0`` (reviewer)
and ``must_fix_received=0`` (author). The wave's single most valuable review — a
real data-loss catch — scored mechanically zero.

Fix (design option (a), complementary to the #164 ledger): source the catch from
GitHub's comment **edit history**. :func:`_pr_comment_histories` fetches, per
comment, its current body plus every prior revision (``userContentEdits.diff``,
the full body at each revision). :func:`verdicts_from_histories` /
:func:`_collapse_history` collapse each comment to one Verdict that credits a
changes-requested catch if ANY revision was blocking — so an amended-away
``Request`` still counts. FAIL-OPEN: an unavailable history degrades to the live
comment bodies; the scorer never crashes. This is deliberately NOT wired into
:func:`parse_verdicts` (the oracle depends on that reading current state so an
amended-clean Request clears the gate) — only the scorer's extraction path uses
it. The ledger and edit-history paths are belts-and-braces: the ledger survives a
comment *deleted outright*; the edit-history path recovers a catch nobody
recorded.

The same wave also could not mechanically justify the reserved-5:
:func:`difficulty_weight` derives a coarse per-PR tier (1-3) from diff magnitude
(changed lines / files), summed per engineer into ``difficulty_points`` and fed
into the distribution-discipline composite (:func:`apply_distribution_discipline`)
so a flagship correctness fix outranks a one-liner without a narrative argument.
Difficulty feeds ONLY the reserved-5 tiebreak, never :func:`score_delta`, so a
clean no-diffstat wave scores exactly as before.

Signals per engineer (all integers, all countable from the merged-PR set):

  ===========================  ============================================
  prs_merged                   PRs merged this iteration with them as commit
                               author.
  must_fix_received            changes-requested verdicts on PRs they
                               authored (negative — author signal). A
                               changes-requested verdict is a ``Request`` with
                               body must-fix items, or a legacy
                               ``ChangesRequested`` token.
  must_fix_caught              changes-requested verdicts they issued as the
                               Requestor/reviewer (positive — review
                               signal).
  ci_red_merges                PRs they authored that merged with a failing
                               required check (negative — hard ding).
  rework_cycles                PRs they authored that needed >=1 rework
                               round (received >=1 changes-requested verdict).
  review_false_positives       must-fix items they raised that were later
                               marked withdrawn/false-positive (negative —
                               review-quality signal).
  verified_reviews             clean verdicts they issued as Requestor whose
                               body carried a concrete ``Verified:`` block
                               (>=1 real check, e.g. revert→red / Nx
                               determinism / byte-parity) (positive —
                               QA-rigor review signal).
  difficulty_points            summed coarse difficulty weight (1-3 per PR,
                               :func:`difficulty_weight`) over authored PRs;
                               feeds the reserved-5 tiebreak, not score_delta.
  ===========================  ============================================

CLI:
  trust_signals.py extract <wave> [--label L] [--status PATH]   # signals JSON
  trust_signals.py score   <wave> [--label L] [--status PATH]   # signals +
                                                                # proposed deltas
                                                                # + forced
                                                                # negative line
  trust_signals.py record-catch <wave> --repo O/N --pr P --requestor R
                                 --requestee E [--at TS] [--status PATH]
                                                                # durably record
                                                                # one changes-
                                                                # requested catch
                                                                # at issue time
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# The shared config loader lives in the framework's hooks dir. This lib lives in
# the sibling lib/ dir; mirror pr_ci_state.py's lib->hooks import bridge so the
# scoring half stays importable wherever the framework is deployed. lifecycle.py
# is a same-dir sibling (both land side-by-side in the bundled framework tree
# too — see lifecycle.py's own self-insert), so this dir is put on the path
# explicitly rather than relying on script-adjacent defaults.
_LIB_DIR = Path(__file__).resolve().parent
_HOOKS_DIR = _LIB_DIR.parent / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))
sys.path.insert(0, str(_LIB_DIR))

from _framework_config import config  # noqa: E402
from lifecycle import persist as _persist_state  # noqa: E402

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

# The charter carries review severity in the comment BODY, not the verdict token:
# a ``Must-fix:`` label (optionally bold) introduces an enumerated list of
# blocking findings. ``_MUST_FIX_LABEL_RE`` matches that label line and captures
# any same-line remainder; ``_LIST_ITEM_RE`` recognizes an enumerated / bulleted
# item; ``_EMPTY_MUST_FIX_RE`` recognizes an explicit "no findings" value
# (``None`` / ``N/A`` / ``-`` / ``0``, e.g. ``Must-fix: None (all resolved)``).
_MUST_FIX_LABEL_RE = re.compile(r"^\s*\**must[\s-]?fix\**:\s*(.*?)\s*$", re.IGNORECASE)
_LIST_ITEM_RE = re.compile(r"^\s*(?:\d+[.)]|[-*+])\s+\S")
_EMPTY_MUST_FIX_RE = re.compile(r"^(none|n/?a|-+|0)(?:\W|$)", re.IGNORECASE)

# A reviewer's clean verdict may carry a ``Verified:`` block enumerating the
# concrete checks they actually ran (the QA-rigor receipt). ``_VERIFIED_LABEL_RE``
# matches that label line and captures any same-line remainder; the block runs
# until a blank line or the next charter section label (``_SECTION_LABEL_RE``).
# ``_VERIFIED_CHECK_RE`` recognizes >=1 CONCRETE verification token inside that
# block — a boilerplate / empty ``Verified:`` with no such token does not count
# (anti-gaming).
_VERIFIED_LABEL_RE = re.compile(r"^\s*\**verified\**:\s*(.*?)\s*$", re.IGNORECASE)
_SECTION_LABEL_RE = re.compile(
    r"^\s*\**(?:requestor|requestee|requestorreplied|must[\s-]?fix|tech[\s-]?debt|review)\b",
    re.IGNORECASE,
)
_VERIFIED_CHECK_RE = re.compile(
    r"revert\s*(?:→|-+|to)?\s*red"  # revert→red / revert to red / revert-red
    r"|byte[\s-]?parity"  # byte-parity
    r"|\d+\s*[x×]\s*determinism"  # Nx / N× determinism (substantive, quantified)
    r"|ci[\s-]?rollup"  # CI-rollup ...
    r"|(?:ci|rollup)\b[^\n]*\bsuccess",  # CI/rollup ... SUCCESS
    re.IGNORECASE,
)
# #259: the bare ``determinism`` and bare ``green ci`` / ``ci green`` alternations
# were dropped — they let a NEGATING / non-substantive mention satisfy the gate
# (e.g. "no determinism check run", "ci green not verified" both matched). Only
# the substantive forms above are creditable now: the quantified ``Nx
# determinism`` (a bare "determinism" no longer counts) and a ``CI ... SUCCESS``
# rollup receipt (a bare "ci green" / "green ci" no longer counts). Genuine
# blocks — ``revert→red``, ``byte-parity``, ``5× determinism``, ``CI rollup
# SUCCESS`` — are unaffected.


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
    # Clean reviewer verdicts (as Requestor) whose comment body carried a
    # parseable ``Verified:`` block enumerating >=1 concrete check
    # (:func:`_has_verified_checks`, e.g. ``revert→red`` / ``Nx determinism`` /
    # ``byte-parity`` / ``CI-rollup SUCCESS``). Positive — the QA-rigor review
    # signal that credits demonstrated verification when there were no must-fixes
    # to catch. An empty / boilerplate ``Verified:`` line does NOT count
    # (anti-gaming). Feeds :func:`score_delta` (clean +1 at >=2) and the
    # reserved-5 composite; never counted as a negative.
    verified_reviews: int = 0
    # Summed coarse per-PR difficulty weight over the engineer's authored PRs
    # (:func:`difficulty_weight`, #229). A flagship correctness fix accrues 3, a
    # one-line config change 1, so a wave of hard work outranks a wave of trivial
    # churn even at equal PR *count*. Feeds the distribution-discipline composite
    # (reserved-5 tiebreak) — NOT :func:`score_delta`, which stays purely
    # negative/positive-signal driven, so a clean no-diffstat wave scores exactly
    # as before (difficulty defaults to 0).
    difficulty_points: int = 0
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
                self.verified_reviews,
            )
        )

    def has_negative(self) -> bool:
        return bool(
            self.must_fix_received
            or self.ci_red_merges
            or self.review_false_positives
            or self.rework_cycles
        )


@dataclass
class Verdict:
    """A parsed verdict comment: who reviewed whom, the call, and retraction.

    ``changes_requested`` is the resolved blocking-review signal — it is derived
    at parse time from the verdict token *and* the comment body (the charter
    keeps severity in the body, so the token alone is not enough). Downstream
    scoring reads this flag, never the raw token.
    """

    requestor: str | None
    requestee: str | None
    verdict: str | None
    false_positive: bool
    changes_requested: bool = False
    # True when the comment body carried a parseable ``Verified:`` block
    # enumerating >=1 concrete check (:func:`_has_verified_checks`). Credited as
    # a ``verified_reviews`` signal to the Requestor only on a CLEAN verdict
    # (``changes_requested`` is False).
    verified: bool = False


def _has_must_fix_items(body: str) -> bool:
    """True when *body* carries a ``Must-fix:`` section with >=1 real item.

    The charter's review convention writes severity in the comment body: a
    ``Must-fix:`` label (bare or bold) followed by an enumerated list of blocking
    findings. An explicit empty value (``Must-fix: None`` / ``N/A`` / ``-`` /
    ``0``, including ``Must-fix: None (all resolved)``) is NOT a must-fix. Code
    spans / fenced blocks are stripped first so a ``must-fix`` token inside code
    or a test name is never counted.
    """
    lines = _strip_code_markup(body).splitlines()
    for i, line in enumerate(lines):
        label_m = _MUST_FIX_LABEL_RE.match(line)
        if not label_m:
            continue
        inline = label_m.group(1).strip()
        if inline:
            # Value on the label line itself: an item unless it's an explicit
            # "no findings" marker.
            if not _EMPTY_MUST_FIX_RE.match(inline):
                return True
            continue
        # Bare label: the value is on the following line(s). Skip blank lines,
        # then require the next non-blank line to be an enumerated/bulleted item.
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines) and _LIST_ITEM_RE.match(lines[j]):
            return True
    return False


def _has_verified_checks(body: str) -> bool:
    """True when *body* carries a ``Verified:`` block enumerating >=1 concrete check.

    The charter's QA-rigor convention writes the checks a reviewer actually ran
    in a ``Verified:`` block (bare or bold label, value inline or on following
    list lines). The block is credited as a ``verified_reviews`` signal only when
    it names >=1 CONCRETE verification token (:data:`_VERIFIED_CHECK_RE` — e.g.
    ``revert→red``, ``Nx determinism``, ``byte-parity``, ``CI-rollup SUCCESS``).
    An empty ``Verified:`` line, or one whose items name no concrete token, does
    NOT count (anti-gaming). The block ends at a blank line or the next charter
    section label so a token in a later section (e.g. Tech-debt) is not borrowed.
    Code spans / fenced blocks are stripped first so a token inside code or a
    test name is never counted.
    """
    lines = _strip_code_markup(body).splitlines()
    for i, line in enumerate(lines):
        label_m = _VERIFIED_LABEL_RE.match(line)
        if not label_m:
            continue
        block = [label_m.group(1)]
        j = i + 1
        while j < len(lines) and lines[j].strip() and not _SECTION_LABEL_RE.match(
            lines[j]
        ):
            block.append(lines[j])
            j += 1
        if _VERIFIED_CHECK_RE.search("\n".join(block)):
            return True
    return False


def _is_changes_requested(verdict: str | None, body: str = "") -> bool:
    """True when a verdict comment represents a changes-requested / must-fix call.

    Two accepted vocabularies:
      * **charter convention** — a ``Request`` verdict whose *body* enumerates
        one or more ``Must-fix:`` items. Severity lives in the body, so a
        ``Request`` with ``Must-fix: None`` (or no must-fix section) is a clean
        review, not a changes-requested.
      * **legacy machine token** — a literal ``ChangesRequested`` verdict (the
        GitHub review-state vocabulary), kept so a project that emits the token
        directly still scores.

    ``Replied`` / ``Approved`` are clean unless carrying the legacy token.
    """
    if verdict is None:
        return False
    token = verdict.strip().lower()
    if token == "changesrequested":
        return True
    if token == "request":
        return _has_must_fix_items(body)
    return False


def parse_verdicts(comment_bodies: list[str]) -> list[Verdict]:
    """Parse the review-verdict comment shape out of a PR's comment bodies.

    Pure function — no I/O. Accepts both the bare (``Requestor: Name``) and bold
    (``**Requestor:** Name``) forms. A comment with no ``RequestOrReplied`` line
    is not a verdict and is skipped. The blocking-review call is resolved here
    (:func:`_is_changes_requested`) because the charter carries severity in the
    body, not the verdict token.
    """
    out: list[Verdict] = []
    for body in comment_bodies:
        verdict_m = _FIELD_RE["verdict"].search(body)
        if not verdict_m:
            continue
        req_m = _FIELD_RE["requestor"].search(body)
        ree_m = _FIELD_RE["requestee"].search(body)
        verdict_str = verdict_m.group(1).strip()
        changes_requested = _is_changes_requested(verdict_str, body)
        # A review false-positive is, by definition (see the module
        # docstring), a ``Must-fix:`` item the reviewer *raised* that was
        # later withdrawn — so a retraction only counts when THIS SAME
        # comment actually enumerated >=1 must-fix finding. A comment with
        # ``Must-fix: None`` / no must-fix section raised zero findings, so
        # retraction vocabulary elsewhere in its body (e.g. a forward-looking
        # Tech-debt "false-positive watch" note) is not a retraction and must
        # not score. Approvals never raise must-fix items. Code spans /
        # fenced blocks are stripped first so symbol/test names that contain
        # the retraction vocabulary (e.g. `test_no_false_positive_*`) are not
        # matched.
        if verdict_str.lower() == "approved" or not _has_must_fix_items(body):
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
                changes_requested=changes_requested,
                verified=_has_verified_checks(body),
            )
        )
    return out


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


class _PartialTokens(dict):
    """Format map that leaves unknown ``{token}`` placeholders literal.

    Mirrors the shell skills' ``sed "s/{phase}/…/; s/{wave}/…/"`` behaviour:
    known tokens are substituted, anything else is passed through verbatim
    instead of raising ``KeyError``. Keeps template rendering fail-safe.
    """

    def __missing__(self, key: str) -> str:  # noqa: D105
        return "{" + key + "}"


def _render_branch_template(template: str, **tokens) -> str:
    """Substitute *tokens* into *template*, leaving unknown placeholders literal."""
    try:
        return str(template).format_map(_PartialTokens(**tokens))
    except (KeyError, IndexError, ValueError):
        return str(template)


def _phase_for_wave(wave: str, status_path: Path | None) -> str | int | None:
    """The phase a wave belongs to (``wave_<id>_phase`` in state), or None.

    PROJECT-COUPLING: keyed on a state-file entry named ``wave_<id>_phase``
    stamped by the wave allocator (see ``lifecycle.py``). Absent in a generic
    project (or when the state file is missing/unreadable) → None, so a template
    that references ``{phase}`` degrades gracefully rather than crashing.
    """
    if status_path is None:
        return None
    try:
        data = json.loads(Path(status_path).read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    val = data.get(f"wave_{wave}_phase")
    return val if val is not None else None


def _wave_ordinal_for_wave(wave: str, status_path: Path | None) -> str | int | None:
    """The phase-local ordinal of a wave (``wave_<id>_phase_ordinal``), or None.

    PROJECT-COUPLING: keyed on a state-file entry named
    ``wave_<id>_phase_ordinal`` stamped by the wave allocator alongside
    ``wave_<id>_phase`` (see ``lifecycle.py``). A phase-namespaced project numbers
    its integration branches by the position of the wave *within its phase*
    (``deployments/phase4/wave-1`` is the first wave of phase 4), not by the
    monotonic global wave id, so the ``{wave}`` token must resolve to this
    ordinal. Absent in a generic (non-phased) project — or when the state file is
    missing/unreadable — → None, and the caller falls back to the global wave id.
    """
    if status_path is None:
        return None
    try:
        data = json.loads(Path(status_path).read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    val = data.get(f"wave_{wave}_phase_ordinal")
    return val if val is not None else None


def _integration_base(
    cfg,
    wave: str,
    phase: str | int | None = None,
    wave_ordinal: str | int | None = None,
) -> str:
    """The merged-PR base branch for *wave*, from the integration-branch template.

    PROJECT-COUPLING: the original tool scoped the base to a phase+wave path
    (``deployments/phase-<P>/wave-<M>``). Here the base is derived generically
    from the configured ``branch.integration`` template (default
    ``deployments/wave-{wave}``) so it tracks whatever branching scheme a project
    declares. Both ``{phase}`` and ``{wave}`` tokens are substituted; a project
    that namespaces waves by phase (``deployments/phase{phase}/wave-{wave}``) is
    resolved correctly when *phase* is supplied (from ``wave_<id>_phase`` state).

    The ``{wave}`` token resolves to the **phase-local ordinal** when
    *wave_ordinal* is supplied (from ``wave_<id>_phase_ordinal`` state), NOT the
    global wave id: a phase-namespaced project names its first phase-4 branch
    ``deployments/phase4/wave-1`` even when that is global wave 2. Falling back to
    the global *wave* id keeps generic (non-phased) projects — which do not stamp
    an ordinal — rendering ``deployments/wave-<id>`` unchanged.

    A project whose merges target the default branch directly should set
    ``branch.integration`` to that branch name. Unknown/unresolved tokens are
    left literal rather than raising.
    """
    template = cfg.get("branch.integration", "deployments/wave-{wave}")
    wave_token = wave_ordinal if wave_ordinal is not None else wave
    tokens: dict[str, str | int] = {"wave": wave_token}
    if phase is not None:
        tokens["phase"] = phase
    return _render_branch_template(str(template), **tokens)


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


def _now_iso(at: str | None = None) -> str:
    """An ISO-8601 UTC timestamp; ``at`` overrides for deterministic tests."""
    if at:
        return at
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _review_catches_for_wave(wave: str, status_path: Path | None) -> list[dict]:
    """The durable per-PR must-fix catch ledger for *wave* (#164).

    Reads ``wave_<id>_review_catches`` — a list of ``{"repo", "pr",
    "requestor", "requestee", "recorded_at"}`` entries appended by
    :func:`record_review_catch` at issue time. Absent/unreadable state file, or
    no entries recorded for this wave, → ``[]`` (fail-open: a project/wave that
    never called :func:`record_review_catch` falls back entirely to the legacy
    live-comment-parsing path in :func:`extract_signals`).
    """
    if status_path is None:
        return []
    try:
        data = json.loads(Path(status_path).read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    val = data.get(f"wave_{wave}_review_catches")
    return list(val) if isinstance(val, list) else []


def record_review_catch(
    status_path: str | Path,
    wave: str,
    *,
    repo: str,
    pr: int,
    requestor: str,
    requestee: str | None = None,
    at: str | None = None,
) -> list[dict]:
    """Durably record one changes-requested catch **at issue time** (#164).

    Call this the moment a blocking (``Request`` + enumerated ``Must-fix:``)
    verdict comment is posted — before any later in-place amendment to
    ``Replied``/``Must-fix: None`` can erase the historic signal. The entry is
    appended (never deduplicated: N calls for the same PR/reviewer are N
    distinct changes-requested cycles) to ``wave_<id>_review_catches`` in the
    project state file via :func:`lifecycle.persist`, which preserves the
    file's compact-inline shape and validates JSON before and after the write.

    Returns the full updated list for that wave (post-append).
    """
    status_path = Path(status_path)
    key = f"wave_{wave}_review_catches"
    existing = _review_catches_for_wave(wave, status_path)
    entry = {
        "repo": repo,
        "pr": int(pr),
        "requestor": requestor,
        "requestee": requestee,
        "recorded_at": _now_iso(at),
    }
    updated = [*existing, entry]
    _persist_state(status_path, {key: updated})
    return updated


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


# GraphQL query fetching every issue-comment on a PR together with its full
# edit history. GitHub exposes each prior revision's *entire body* (not a unified
# diff) as ``userContentEdits.diff`` — so the union of a comment's current body
# and every ``diff`` is every body that comment has ever carried. ``{repo}`` /
# ``{owner}`` / ``{number}`` are substituted by :func:`_pr_comment_histories`.
_COMMENT_HISTORY_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      comments(first: 100) {
        nodes {
          body
          userContentEdits(first: 100) {
            nodes { diff }
          }
        }
      }
    }
  }
}
"""


def _pr_comment_histories(repo: str, number: int) -> list[list[str]] | None:
    """Per-comment body revisions on a PR — current body + every prior revision.

    Returns one list per issue-comment: ``[current_body, *historical_bodies]``,
    where the historical bodies come from GitHub's comment edit API
    (``userContentEdits.diff`` — the full body at each prior revision, not a
    unified diff). A comment never edited yields a single-element list. This is
    the durable signal #229 needs: a blocking ``Request`` / ``Must-fix:`` later
    amended in place to ``Replied`` / ``Must-fix: None`` (the charter Reply
    Protocol the oracle requires) still leaves its original changes-requested
    body in the edit history, so the catch survives the amendment.

    FAIL-OPEN: any error — a ``gh`` failure/timeout, malformed JSON, or an
    unexpected shape — returns ``None`` (not ``[]``), the sentinel telling
    :func:`extract_signals` "edit history is unavailable, fall back to the live
    comment bodies". Never raises; the scorer must never crash on a history
    fetch. (``[]`` is a legitimate value — a PR with zero comments — and is
    therefore distinct from the unavailable sentinel.)
    """
    if "/" not in repo:
        return None
    owner, name = repo.split("/", 1)
    try:
        raw = _run_gh(
            [
                "api",
                "graphql",
                "-f",
                f"query={_COMMENT_HISTORY_QUERY}",
                "-F",
                f"owner={owner}",
                "-F",
                f"name={name}",
                "-F",
                f"number={int(number)}",
            ]
        )
        data = json.loads(raw or "{}")
        nodes = (
            data["data"]["repository"]["pullRequest"]["comments"]["nodes"]
        )
    except (
        subprocess.SubprocessError,
        OSError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        return None
    histories: list[list[str]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        revisions = [str(node.get("body") or "")]
        edits = ((node.get("userContentEdits") or {}).get("nodes")) or []
        for edit in edits:
            if isinstance(edit, dict) and edit.get("diff") is not None:
                revisions.append(str(edit["diff"]))
        histories.append(revisions)
    return histories


def _pr_diffstat(pr: dict) -> tuple[int, int, int]:
    """Extract ``(additions, deletions, changed_files)`` from a merged-PR record.

    The diffstat travels on the ``pr list --json`` record :func:`merged_prs`
    builds, so no extra network call is needed. Fail-open: any missing/non-int
    field degrades to 0 (→ the minimum difficulty tier), never raises.
    """

    def _int(key: str) -> int:
        try:
            return int(pr.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    return _int("additions"), _int("deletions"), _int("changedFiles")


def difficulty_weight(additions: int, deletions: int, changed_files: int) -> int:
    """Coarse per-PR difficulty tier in ``{1, 2, 3}`` from diff magnitude. Pure.

    Deliberately three buckets, not a continuous score — the point (#229) is to
    tell a flagship correctness fix apart from a one-line config change so the
    reserved-5 rotation is mechanical, NOT to pretend line count measures value
    precisely. The thresholds are intentionally generous and defensible:

      * **3 (substantial / flagship):** >= 200 changed lines OR >= 8 files —
        a cross-cutting change (e.g. #227 was 1101 additions across 6 files).
      * **2 (moderate):** >= 40 changed lines OR >= 3 files.
      * **1 (trivial):** anything smaller — a one-liner, a config bump, a doc
        typo.

    "Changed lines" is additions + deletions (a large deletion is still work).
    Negative/garbage inputs are clamped to 0, so the worst case is tier 1 — it
    never raises and never returns outside ``{1, 2, 3}``.
    """
    lines = max(0, additions) + max(0, deletions)
    files = max(0, changed_files)
    if lines >= 200 or files >= 8:
        return 3
    if lines >= 40 or files >= 3:
        return 2
    return 1


def _collapse_history(revisions: list[str]) -> "Verdict | None":
    """Collapse one comment's body revisions to a single durable-credit Verdict.

    *revisions* is ``[current_body, *historical_bodies]`` (see
    :func:`_pr_comment_histories`). The rule (#229): if ANY revision was a real
    changes-requested verdict (a ``Request`` + enumerated ``Must-fix:``), the
    returned Verdict carries ``changes_requested=True`` attributed to that
    revision's ``Requestor:`` / ``Requestee:`` — **even if the current body was
    amended clean**. Otherwise the current revision's verdict is returned
    unchanged. A comment no revision of which parses as a verdict → ``None``.

    ``false_positive`` is always taken from the CURRENT body: a retraction
    ("withdrawn" / "false-positive") is only ever expressed in the live comment,
    never recovered from history. Pure — no I/O.

    Backward-compatible by construction: a comment never edited has a
    single-element *revisions* list, so this returns exactly
    ``parse_verdicts([body])[0]`` (or ``None``) — a clean no-amend wave is
    scored identically to the legacy live-comment path.
    """
    parsed = [
        (vs[0] if (vs := parse_verdicts([rev])) else None) for rev in revisions
    ]
    current = parsed[0] if parsed else None
    catch = next((v for v in parsed if v is not None and v.changes_requested), None)
    if catch is None:
        return current
    return Verdict(
        requestor=catch.requestor,
        requestee=catch.requestee,
        verdict=catch.verdict,
        false_positive=current.false_positive if current is not None else False,
        changes_requested=True,
    )


def verdicts_from_histories(comment_histories: list[list[str]]) -> list[Verdict]:
    """History-aware analogue of :func:`parse_verdicts`, one Verdict per comment.

    Maps each comment's revision list through :func:`_collapse_history` and drops
    the non-verdict comments. The result is the same ``list[Verdict]`` shape
    :func:`parse_verdicts` returns, so :func:`_account_pr` consumes it unchanged
    — but a catch that was amended away in the live comment body is preserved
    here from the edit history. Pure — no I/O.

    NOTE: this is intentionally NOT wired into :func:`parse_verdicts` itself,
    because ``pr_review_state`` (the merge-gate oracle) depends on
    ``parse_verdicts`` reading the CURRENT state — an amended-clean Request must
    parse clean there so the gate clears. The scorer wants the opposite (durable
    credit), so only the scorer's extraction path uses this function.
    """
    out: list[Verdict] = []
    for revisions in comment_histories:
        v = _collapse_history(revisions)
        if v is not None:
            out.append(v)
    return out


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
    base = _integration_base(
        cfg,
        wave,
        phase=_phase_for_wave(wave, status_path),
        wave_ordinal=_wave_ordinal_for_wave(wave, status_path),
    )
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
            "number,headRefOid,mergedAt,author,additions,deletions,changedFiles",
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
                    "additions": pr.get("additions"),
                    "deletions": pr.get("deletions"),
                    "changedFiles": pr.get("changedFiles"),
                }
            )
    return out


# A trailing role/annotation parenthetical on a captured name, e.g. the
# ``(QA)`` in ``Tariq Morales (QA)`` or ``(Principal SWE)``. Stripped before a
# name is matched against the roster so the role does not fork the identity.
_ROLE_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _name_key(name: str) -> str:
    """Fold a captured name to a roster-match key.

    Collapses the ways one person's name is written across a wave's PRs and
    verdict comments to a single key: a trailing role parenthetical is dropped
    (``Tariq Morales (QA)`` → ``Tariq Morales``), dotted separators become spaces
    (``Tariq.Morales`` → ``Tariq Morales``) while hyphens are preserved
    (``Ibrahim.El-Amin`` → ``Ibrahim El-Amin``), interior whitespace is collapsed,
    and the result is lower-cased. Pure — no I/O.
    """
    name = _ROLE_SUFFIX_RE.sub("", name)
    name = name.replace(".", " ")
    return re.sub(r"\s+", " ", name).strip().lower()


def _roster_names(cfg) -> list[str]:
    """Canonical team names (the roster JSON's keys), or ``[]`` if unavailable.

    Reads ``identity.roster_source`` (default ``.claude/team/roster.json``)
    relative to the repo root (``cfg.path.parent.parent`` — the config lives at
    ``<repo>/.claude/framework.config.json``). Fail-open: a missing/unreadable or
    non-object roster yields ``[]`` so normalization simply passes names through.
    """
    if getattr(cfg, "path", None) is None:
        return []
    roster_source = cfg.get("identity.roster_source", ".claude/team/roster.json")
    roster_path = cfg.path.parent.parent / roster_source
    try:
        data = json.loads(roster_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    return [str(k) for k in data]


def _canonicalizer(cfg):
    """Return a ``name -> canonical_name`` mapper keyed off the roster.

    Builds ``{_name_key(roster_name): roster_name}`` once, then returns a closure
    that maps any captured name to its canonical roster identity via
    :func:`_name_key`. A name absent from the roster is returned unchanged
    (fail-open) — never dropped, never crashes.
    """
    canon_by_key = {_name_key(n): n for n in _roster_names(cfg)}

    def canon(name: str) -> str:
        return canon_by_key.get(_name_key(name), name)

    return canon


def _account_pr(
    signals: dict[str, Signals],
    canon,
    *,
    author: str,
    repo: str,
    number: int,
    comment_bodies: list[str] | None = None,
    comment_histories: list[list[str]] | None = None,
    ci_red: bool,
    difficulty: int = 0,
    review_catches: list[dict] | None = None,
) -> None:
    """Fold one merged PR's contribution into *signals* (mutates in place).

    Pure aside from the ``canon`` callable (itself pure) — no I/O. Shared by
    :func:`extract_signals` (live gh-backed) and tests (hand-built PR data), so
    the two never drift.

    Verdicts are derived from ``comment_histories`` when supplied
    (edit-history-aware, #229 — see :func:`verdicts_from_histories`) so a catch
    amended away in the live comment body is still credited; otherwise from
    ``comment_bodies`` via the legacy :func:`parse_verdicts` path. Exactly one of
    the two should be supplied (histories preferred); an empty/absent pair yields
    no verdicts.

    ``review_catches`` is the full wave-scoped durable ledger (#164,
    :func:`_review_catches_for_wave`); entries are filtered here to this
    ``(repo, number)``. When that filtered set is non-empty it is
    **authoritative** for this PR's changes-requested accounting
    (``must_fix_received`` / ``must_fix_caught`` / ``rework_cycles``) — it
    supersedes re-deriving those from the comments, so a verdict comment later
    amended in place (the charter's amendment convention) cannot erase a catch
    that was durably recorded at issue time. The ledger and the #229 edit-history
    path are complementary belts-and-braces: the ledger credits a catch recorded
    at issue time even if the comment is later deleted outright; the edit-history
    path recovers a catch nobody remembered to record, straight from GitHub. A PR
    covered by neither falls back to the legacy live-comment-parsing path
    unchanged. False-positive detection is untouched by the ledger — it is always
    read from the (current) comment body (a retraction is itself only ever
    expressed there).

    ``difficulty`` is the PR's coarse difficulty weight (:func:`difficulty_weight`,
    #229); it accrues to the author's ``difficulty_points`` and feeds only the
    distribution-discipline reserved-5 tiebreak, never :func:`score_delta`.
    """

    def bucket(name: str) -> Signals:
        return signals.setdefault(canon(name), Signals())

    author_sig = bucket(author)
    author_sig.prs_merged += 1
    author_sig.authored_prs.append(number)
    author_sig.difficulty_points += difficulty

    if ci_red:
        author_sig.ci_red_merges += 1

    if comment_histories is not None:
        verdicts = verdicts_from_histories(comment_histories)
    else:
        verdicts = parse_verdicts(comment_bodies or [])
    catches = [
        c
        for c in (review_catches or [])
        if c.get("repo") == repo and str(c.get("pr")) == str(number)
    ]

    pr_had_changes_requested = False
    if catches:
        for c in catches:
            pr_had_changes_requested = True
            author_sig.must_fix_received += 1
            requestor = c.get("requestor")
            if requestor:
                bucket(requestor).must_fix_caught += 1
    else:
        for v in verdicts:
            if v.changes_requested:
                pr_had_changes_requested = True
                author_sig.must_fix_received += 1
                if v.requestor:
                    bucket(v.requestor).must_fix_caught += 1

    # #258: dedup ``verified_reviews`` per (reviewer, PR). ``_account_pr`` handles
    # a single (repo, number), so a reviewer counted once here == counted once for
    # this PR; distinct reviewers on this PR, and the same reviewer on other PRs
    # (separate ``_account_pr`` calls), still count independently. Keyed on the
    # CANONICAL reviewer identity so two spellings of one name
    # (``Tariq.Morales`` / ``Tariq Morales (QA)``) fold to a single credit.
    credited_verified: set[str] = set()
    for v in verdicts:
        if v.false_positive and v.requestor:
            bucket(v.requestor).review_false_positives += 1
        # Credit a verified review only on a CLEAN verdict (not a blocking
        # Must-fix Request) whose body carried a concrete ``Verified:`` block —
        # and at most ONCE per reviewer for this PR (#258).
        if v.verified and not v.changes_requested and v.requestor:
            reviewer = canon(v.requestor)
            if reviewer not in credited_verified:
                credited_verified.add(reviewer)
                bucket(v.requestor).verified_reviews += 1

    if pr_had_changes_requested:
        author_sig.rework_cycles += 1


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

    Both identities are normalized against the roster before bucketing
    (:func:`_canonicalizer`): a person written ``Tariq.Morales`` in one comment,
    ``Tariq Morales`` in another, and ``Tariq Morales (QA)`` in a third folds to a
    single ledger entry instead of splitting their signals across variants. A
    name absent from the roster passes through unchanged (fail-open).

    Per-PR changes-requested accounting prefers the durable review-catch ledger
    (:func:`_review_catches_for_wave`, #164) over live comment parsing when the
    ledger has entries for a PR — see :func:`_account_pr`.
    """
    cfg = cfg or config()
    prs = merged_prs(wave, status_path, label=label, cfg=cfg)
    canon = _canonicalizer(cfg)
    review_catches = _review_catches_for_wave(wave, status_path)
    signals: dict[str, Signals] = {}

    for pr in prs:
        author = pr.get("commit_author_name") or "(unknown)"
        repo = pr["repo"]
        number = pr["number"]
        # Prefer the edit-history-aware path (#229): a catch amended away in the
        # live comment body is recovered from GitHub's comment edit history. On
        # any history-fetch failure (returns None) fall back to the live comment
        # bodies — never crash, never lose the legacy behaviour.
        histories = _pr_comment_histories(repo, number)
        kwargs: dict = {"comment_histories": histories}
        if histories is None:
            kwargs = {"comment_bodies": _pr_comment_bodies(repo, number)}
        _account_pr(
            signals,
            canon,
            author=author,
            repo=repo,
            number=number,
            ci_red=_pr_ci_is_red(repo, number),
            difficulty=difficulty_weight(*_pr_diffstat(pr)),
            review_catches=review_catches,
            **kwargs,
        )

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
        - 2+ must-fix items received as author:   -1
        - 2+ rework cycles as author:             -1
      positive (only when the iteration is clean of the negatives above)
        - 2+ PRs merged clean:                    +1
        - 2+ must-fix items caught as reviewer:   +1
        - 2+ verified reviews as reviewer:        +1  (QA-rigor path — a
          reviewer's clean verdicts carrying concrete ``Verified:`` receipts;
          credits demonstrated verification when there were no must-fixes to
          catch)

    ``rework_cycles`` and ``must_fix_received`` are both in
    :meth:`Signals.has_negative`, so a rework-/must-fix-heavy wave can never also
    collect the clean-wave positives above.
    """
    delta = 0
    delta -= sig.ci_red_merges
    delta -= sig.review_false_positives
    if sig.must_fix_received >= 2:
        delta -= 1
    if sig.rework_cycles >= 2:
        delta -= 1

    clean = not sig.has_negative()
    if clean:
        if sig.prs_merged >= 2:
            delta += 1
        if sig.must_fix_caught >= 2:
            delta += 1
        if sig.verified_reviews >= 2:
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
        # Reward output + good reviewing (must-fix caught + verified reviews) +
        # difficulty of the work shipped; penalise the negatives. Pure ranking
        # key, not a trust score. Adding
        # ``difficulty_points`` (#229) is what makes the reserved-5 mechanical: a
        # flagship correctness fix (weight 3) outranks a one-liner (weight 1) at
        # equal PR count, so the top slot is not a narrative argument. Waves with
        # no diffstat plumbed (``difficulty_points == 0`` for everyone — e.g. a
        # hand-built Signals dict) rank exactly as before.
        return (
            s.prs_merged
            + s.must_fix_caught
            + s.verified_reviews
            + s.difficulty_points
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
        if sig.rework_cycles:
            gaps.append(f"{sig.rework_cycles} rework cycle(s)")
        if sig.review_false_positives:
            gaps.append(f"{sig.review_false_positives} review false-positive(s)")
        return f"{name}: " + ", ".join(gaps)
    return (
        f"{name}: metrics clean: prs_merged={sig.prs_merged}, "
        f"must_fix_received=0, ci_red_merges=0, false_positives=0, "
        f"must_fix_caught={sig.must_fix_caught}, "
        f"verified_reviews={sig.verified_reviews}"
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


def _cmd_record_catch(args: argparse.Namespace) -> int:
    if args.status is None:
        print(
            "ERROR: --status (or configured paths.state_file) is required",
            file=sys.stderr,
        )
        return 2
    updated = record_review_catch(
        args.status,
        args.wave,
        repo=args.repo,
        pr=args.pr,
        requestor=args.requestor,
        requestee=args.requestee,
        at=args.at,
    )
    print(json.dumps(updated, indent=2, sort_keys=True))
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

    p_catch = sub.add_parser(
        "record-catch",
        help="durably record a changes-requested catch at issue time (#164)",
    )
    p_catch.add_argument("wave", help="iteration / wave id")
    p_catch.add_argument("--repo", required=True, help="owner/name")
    p_catch.add_argument("--pr", required=True, type=int, help="PR number")
    p_catch.add_argument(
        "--requestor",
        required=True,
        help="reviewer identity, as in the verdict comment's Requestor: field",
    )
    p_catch.add_argument(
        "--requestee",
        default=None,
        help="PR-author identity, as in the verdict comment's Requestee: field",
    )
    p_catch.add_argument(
        "--at", default=None, help="ISO-8601 UTC timestamp override (tests)"
    )
    p_catch.add_argument(
        "--status",
        type=Path,
        default=_default_status(),
        help="path to the project state file (default: config paths.state_file)",
    )
    p_catch.set_defaults(func=_cmd_record_catch)
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
