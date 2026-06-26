# Generic Hook: Require Two Peer Reviews Before Merge

## Purpose

A `PreToolUse` hook that blocks a PR-merge command unless the PR has at least
**two reviews from distinct non-authors**. Reviews count from either formal
platform reviews or **structured review comments** in a fixed field format. It
also enforces a tech-debt attestation line on every verdict, supports a
single-reviewer exception for bootstrap PRs reviewed by a designated enforcer
role, and hard-blocks a **batch-loop merge shape** that would fail the gate open.

It exists because review attribution is easy to get wrong (reviewer vs. author
swap, "looks good" prose that isn't a verdict, fictional reviewer names) and
because a `for pr in …; do merge "$pr"; done` loop silently disables a gate that
parses a *literal* PR number.

## Rule

For a literal merge command targeting one PR:

1. Collect reviewers from (a) formal platform reviews by non-authors and
   (b) structured review comments whose verdict field marks an **approval**.
2. The comment author of an approval is the **reviewer** (not the addressee).
3. Reviewers are deduped on full name; only names matching a real **roster**
   entry count (reject fictional reviewers).
4. Merge requires **2 distinct approving reviewers**, neither being the PR author.
5. Every verdict comment (approve / changes-requested) MUST carry a tech-debt
   attestation line (e.g. `TechDebt: none` or `TechDebt: #15, #16`); a missing
   line blocks.
6. **Single-reviewer exception**: a PR labeled as a bootstrap PR, reviewed by
   exactly one designated **enforcer-role** roster member, may merge with one
   approval.
7. **Batch-loop guard**: a merge whose PR argument is non-literal (`$pr`,
   `${prs[$i]}`, `$(get_pr)`, subshell-wrapped) AND sits inside a `do … done`
   loop body is HARD BLOCKED — instruct one literal merge per call.
8. An emergency override flag (`--admin`) bypasses the whole gate.

Exit `0` = allow, `2` = block.

### Structured review-comment format

```
Requestor: <comment author>            # the person POSTING
Requestee: <comment target>            # the person ADDRESSED
RequestOrReplied: <Request|Reply|Approved|ChangesRequested>
TechDebt: none | #15, #16, ...
```

Only `Approved` comments count toward the 2-reviewer threshold (the reviewer is
the **Requestor**). `Request`/`Reply` are process metadata, not verdicts. Parse
fields from a **trailer block** (after the last `---` separator) and strip code
fences/inline code first, so prose that merely *quotes* the field syntax is not
captured as a real verdict.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""PreToolUse hook: require two distinct peer reviews before merge."""
import json
import re
import subprocess
import sys
from pathlib import Path

_ROSTER_DIR = Path(__file__).resolve().parent.parent / "team" / "roster"  # adapt
_ENFORCER_PREFIXES = ("standards_lead_", "manager_", "tech_lead_")        # adapt

def is_merge_command(command: str) -> bool:
    for seg in re.split(r"\s*(?:&&|\|\||\||;)\s*", command):
        s = seg.lstrip()
        while re.match(r"[A-Za-z_]\w*=\S*\s+", s):
            s = re.sub(r"^[A-Za-z_]\w*=\S*\s+", "", s)
        if re.match(r"gh\s+pr\s+merge\b", s):
            return True
    return False

# Non-literal merge arg (not a flag, not a bare integer) inside a do…done loop.
_NONLITERAL_ARG = re.compile(r"\bgh\s+pr\s+merge\s+(?![-\d])[^\s;&|()]")
_DO_DONE = re.compile(r"(?:^|[\s;])(done|do)(?=[\s;]|$)")

def _loop_spans(view: str) -> list[tuple[int, int]]:
    spans, stack = [], []
    for m in _DO_DONE.finditer(view):
        if m.group(1) == "do":
            stack.append(m.end(1))
        elif stack:
            spans.append((stack.pop(), m.start(1)))
    return spans

def is_loop_merge(command: str) -> bool:
    merges = list(_NONLITERAL_ARG.finditer(command))
    spans = _loop_spans(command)
    return any(a <= m.start() < b for m in merges for (a, b) in spans)

def extract_pr(command: str) -> str | None:
    m = re.search(r"\bgh\s+pr\s+merge\s+(\d+)", command) or re.search(r"/pull/(\d+)", command)
    return m.group(1) if m else None

# --- structured field extraction ----------------------------------------
def _trailer(body: str) -> str:
    lines = body.splitlines(keepends=True)
    last = max((i for i, ln in enumerate(lines) if ln.strip() == "---"), default=-1)
    return body if last == -1 else "".join(lines[last + 1:])

def _field(name: str, body: str) -> str | None:
    scope = _trailer(re.sub(r"`[^`]*`", " ", body))   # strip inline code first
    ms = list(re.finditer(rf"\*{{0,2}}{re.escape(name)}:\*{{0,2}}\s*(.+)", scope))
    if not ms:
        return None
    v = ms[-1].group(1).split("\n", 1)[0].strip().strip("*").strip()
    return re.sub(r"\s*\(.*?\)\s*$", "", v).strip() or None

def _roster_names(prefixes=None) -> set[str]:
    names = set()
    if not _ROSTER_DIR.is_dir():
        return names
    for f in _ROSTER_DIR.glob("*.md"):
        if prefixes and not any(f.name.startswith(p) for p in prefixes):
            continue
        m = re.search(r"\*\*Name:\*\*\s*([^\n]+)", f.read_text(encoding="utf-8"))
        if m:
            names.add(m.group(1).strip().lower())
    return names

def check(data: dict) -> dict | None:
    if data.get("tool_name") != "Bash":
        return None
    command = data.get("tool_input", {}).get("command", "")
    if "--admin" in command:
        return None
    if is_loop_merge(command):
        return {"decision": "block",
                "reason": "BLOCKED: batch-loop merge with a non-literal PR arg fail-opens "
                          "the review gate. Run one literal `merge <N>` per call."}
    if not is_merge_command(command):
        return None

    pr = extract_pr(command)
    # ... fetch PR author + reviews + comments via your platform CLI ...
    # Build `reviewers`: formal non-author reviews + Approved-comment Requestors
    # filtered to roster_names. Then:
    #   - if len(reviewers)==1 and bootstrap-label and sole reviewer in enforcer
    #     set -> allow (after TechDebt check)
    #   - elif len(reviewers) < 2 -> block with a 2-reviewer diagnostic
    #   - if any verdict comment missing TechDebt line -> block
    return None

def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    result = check(data)
    if result is None:
        sys.exit(0)
    print(json.dumps(result))
    sys.exit(2 if result.get("decision") == "block" else 0)

if __name__ == "__main__":
    main()
```

## Adaptation Notes

- **Reviewer counting is the subtle part.** The verdict comment's *author* is the
  reviewer; counting the *addressee* collapses every approval to the PR author's
  name. Dedup on full name, not surname, so two reviewers who share a surname
  both count. (Surname is only used to compare a reviewer against the branch
  author when the branch encodes `{Initial}.{Surname}`.)
- **Roster filtering** rejects fictional reviewer names — only count Requestors
  that match a real roster persona file.
- **Trailer-block + code-strip discipline** prevents prose that quotes the field
  syntax from being read as a verdict; use last-match-wins within the trailer.
- **Pagination**: fetch ALL PR comments (paginate) or you miss reviews past the
  first page.
- **Batch-loop guard** must run BEFORE the `is_merge_command` early-return,
  because in a loop the merge segment leads with the `do` keyword and the
  per-segment check would not see it. Match the argument's leading character
  (not a fully-shaped `$var`) to cover subshell/subscript/command-sub forms.
- **Enforcer roles** and the bootstrap label are project policy; map them to your
  roster filename conventions and labels.
```
