# Generic Library Prompt: Mechanical Trust Signals

## Purpose

Replace narrative, self-graded peer/teammate trust scores with **countable,
evidence-anchored** signals derived mechanically from a delivery iteration's
merged change-set. Every trust delta then cites a number instead of a vibe.

Use this when a team-coordination framework keeps a "trust matrix" (a per-author
competence/reliability score) and you want each score change to be defensible
and reproducible from artifacts (merged pull requests + their review records)
rather than from subjective assessment.

## Reusable pattern

Split the module into two cleanly separated layers:

1. **Extraction (I/O-dependent).** Build a `{author_name: Signals}` map from the
   iteration's merged-PR set. Reuse the same merged-PR enumerator the rest of the
   framework uses (so cross-window filters and the no-shell argument-vector
   contract are inherited). For each PR, parse its review/verdict comments for a
   structured field shape (reviewer, reviewee, verdict) and read the PR's CI
   status rollup.
2. **Scoring (pure, no I/O).** Every scoring function is pure so the model is
   unit-testable without touching the issue tracker / CI. This includes the
   per-iteration delta, the staleness decay, the distribution-discipline cap, the
   forced negative-signal line, and the retirement trigger.

### Countable signals (all integers, all derivable from the merged-PR set)

| Signal | Meaning | Sign |
|---|---|---|
| `prs_merged` | PRs merged this iteration with this person as commit author | output |
| `must_fix_received` | "changes requested" verdicts on PRs they authored | negative (author) |
| `must_fix_caught` | "changes requested" verdicts they issued as reviewer | positive (review) |
| `ci_red_merges` | PRs they authored that merged with a failing required check | negative (hard) |
| `rework_cycles` | PRs they authored that needed ≥1 rework round | negative |
| `review_false_positives` | review findings they raised that were later self-retracted | negative (review quality) |

### Scoring rules (symmetric, clamped)

A single iteration must not swing trust across the whole scale, so clamp the
delta to `[-2, +2]`:

- **negative:** −1 per CI-red merge; −1 per review false-positive; −1 if
  `must_fix_received >= 3`.
- **positive (only when the iteration is clean of all negatives):** +1 for
  `prs_merged >= 2`; +1 for `must_fix_caught >= 2`.

### Supporting pure functions

- **Decay:** no trust-relevant signal for N iterations drifts the score one step
  toward NEUTRAL (a stale high/low score is no longer earned). One step per call,
  never a reset.
- **Distribution discipline:** the top score (5) is reserved for the
  iteration's exceptional *relative* performer(s) — the one(s) whose composite
  ranking key is the strict maximum AND positive. Every other proposed top score
  is capped one below. Prevents grade inflation for merely-clean work.
- **Forced negative-signal line:** bans a bare "None". Every active person gets
  either a specific evidence-backed gap OR an explicit `metrics clean: {numbers}`
  statement that still shows the receipts.
- **Retirement trigger:** performance-triggered exit over the last K iterations —
  sustained bottom-tier score, OR repeated CI-red merges. Fewer than K iterations
  of history never triggers (insufficient evidence).

## Key correctness notes (carry these into any port)

- **Reviewer identity comes from the verdict comment's `Reviewer:` field, not the
  comment author.** In many automation setups the principal posting the comment
  is an orchestrator bot, not the human reviewer.
- **Author identity is the head commit's author name** — the same identity any
  concentration/ownership metric uses.
- **A retraction ("false positive") only counts when the reviewer explicitly
  self-withdraws a finding** (withdrawn / false-positive / retracted). Approvals
  are never retractions. Strip fenced code blocks and inline code spans before
  matching the retraction vocabulary, so symbol/test names like
  `test_no_false_positive_type` are not mistaken for genuine withdrawal language.
- **The verdict-field regex must accept both bare (`Reviewer: Name`) and bold
  (`**Reviewer:** Name`) forms** so it matches whatever a review-format gate
  accepts.
- **An empty/undetermined CI rollup is not a pass** — but post-merge the rollup
  on the merged head is the closest mechanical proxy for "merged with red CI"
  available after the fact.

## Code template (stdlib + an issue/CI CLI wrapper)

```python
"""Per-author mechanical trust signals + evidence-anchored scoring."""
from __future__ import annotations
import re
from dataclasses import dataclass, field

NEUTRAL, MIN_SCORE, MAX_SCORE = 3, 1, 5
DECAY_AFTER, RETIRE_AFTER, BOTTOM_TIER = 3, 3, 2

_FIELD_RE = {
    "reviewer": re.compile(r"^\**Reviewer\**:\**\s*(.+?)\**\s*$", re.MULTILINE),
    "reviewee": re.compile(r"^\**Reviewee\**:\**\s*(.+?)\**\s*$", re.MULTILINE),
    "verdict":  re.compile(r"^\**Verdict\**:\**\s*(\w+)", re.MULTILINE),
}
_RETRACTED_RE = re.compile(
    r"\b(false[\s-]?positive|withdrawn|retracted|invalid finding)\b", re.IGNORECASE)


def _strip_code(text: str) -> str:
    text = re.sub(r"```.*?```|~~~.*?~~~", lambda m: " " * len(m.group()), text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]+`", lambda m: " " * len(m.group()), text)


@dataclass
class Signals:
    prs_merged: int = 0
    must_fix_received: int = 0
    must_fix_caught: int = 0
    ci_red_merges: int = 0
    rework_cycles: int = 0
    review_false_positives: int = 0
    authored: list[int] = field(default_factory=list)

    def has_negative(self) -> bool:
        return bool(self.must_fix_received or self.ci_red_merges or self.review_false_positives)


def score_delta(s: Signals) -> int:
    delta = -s.ci_red_merges - s.review_false_positives
    if s.must_fix_received >= 3:
        delta -= 1
    if not s.has_negative():
        if s.prs_merged >= 2:
            delta += 1
        if s.must_fix_caught >= 2:
            delta += 1
    return max(-2, min(2, delta))


def decay(old: int, idle_iterations: int, *, after: int = DECAY_AFTER) -> int:
    if idle_iterations < after:
        return old
    return old - 1 if old > NEUTRAL else old + 1 if old < NEUTRAL else NEUTRAL


def retirement_trigger(scores: list[int], ci_red: list[int], *, k: int = RETIRE_AFTER):
    if len(scores) >= k and all(x <= BOTTOM_TIER for x in scores[-k:]):
        return True, f"sustained bottom-tier for {k} iterations"
    if len(ci_red) >= k and all(c >= 1 for c in ci_red[-k:]):
        return True, f"repeated CI-red merges in {k} iterations"
    return False, ""
```

The extraction layer (`extract_signals`) iterates the merged-PR set, fetches each
PR's comment bodies + CI rollup via the issue/CI CLI, parses verdicts, and tallies
the signals. Keep it thin; keep all judgement in the pure functions.

## Adaptation notes

- Rename "iteration/wave" to whatever cadence unit the host framework uses
  (sprint, cycle, release). The model is cadence-agnostic.
- The verdict field labels (`Reviewer`/`Reviewee`/`Verdict`) must match the
  review-format convention enforced elsewhere in the framework.
- NEUTRAL/MIN/MAX and the decay/retirement windows are policy knobs; expose them
  as module constants.
- If your CI exposes a richer per-required-check signal, prefer it over the
  status rollup for `ci_red_merges`.
