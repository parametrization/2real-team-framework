# Generic Hook: Block "Iteration Concluded" Claims Until Open-Item Audit Clears

## Purpose

A `PreToolUse` hook on **Skill** calls that gates iteration-lifecycle skills
(wrap-up, retrospective, handoff) from claiming an iteration is
"concluded / complete / done" until a cross-repo **open-item audit** proves the
open-item count is zero — OR the skill's `args` carry an explicit
**carry-forward** list naming what is deferred.

It exists because a charter rule alone ("audit before you claim done") failed:
a wrap-up emitted "iteration concluded" while many items were still open across
repos, and a human had to prompt for the truth. Per the enforcement hierarchy
(hook > skill > charter), a rule that failed once becomes a hook. It must be
`PreToolUse`, not `PostToolUse`: by the time the skill output renders, the false
claim is already on screen.

## Rule

Fires on a `Skill` tool call whose `skill` name is in a gated set
(`{wrap-up, retro, handoff}` or your equivalents).

- Determine the active iteration's label(s) from a status file.
- Run a cross-repo audit: count open issues carrying the active iteration
  label across all known repos.
- **Block** when: gated skill AND open-count > 0 AND `args` lacks a
  carry-forward marker.
- **Allow** when: skill not gated; open-count == 0; `args` has a carry-forward
  marker (warn-allow with a summary); or the audit cannot run for infrastructure
  reasons (fail-open with a warning — never a silent drop).

Exit `0` = allow, `2` = block. There is deliberately **no in-band override
flag** — the only paths are close the items, add a carry-forward block, or
remove the hook entry from settings (emergency).

### Carry-forward markers (any one suffices, case-insensitive)

- `Carry-forward:` / `Carry forward:` inline
- a `## Carry-forward` markdown heading
- `#<N> → <destination>` arrow patterns naming items individually

### Merge-ready-PR exemption (optional)

An open iteration issue does NOT count against the blocking total if it has a
**merge-ready PR** targeting the iteration branch: open, not draft, base ==
iteration branch, mergeable (no conflicts), all checks green, AND the PR body
declares it closes the issue via a closing keyword (`Closes/Fixes/Resolves #N`).
This resolves a chicken-and-egg where the wrap-up's own close-on-merge work is
counted as still-open and blocks the wrap-up from running. Fail toward the
stricter count (never false-exempt) on any query failure.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""PreToolUse hook: gate iteration-conclusion skills on a cross-repo open-item audit."""
import json
import re
import subprocess
import sys
from pathlib import Path

_GATED = frozenset({"wave-wrapup", "wave-retro", "handoff"})   # adapt names
_REPOS = ("repo-a", "repo-b", "repo-c")                        # adapt
_STATUS = Path(__file__).resolve().parents[2] / "cross-repo-status.json"

_CARRY_FORWARD = (
    re.compile(r"carry[\s-]forward\s*:", re.IGNORECASE),
    re.compile(r"^#{1,6}\s+carry[\s-]forward\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"#\d+\s*(?:->|→)\s*[A-Za-z_]", re.IGNORECASE),
)

def _active_labels() -> list[str] | None:
    try:
        data = json.loads(_STATUS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not data.get("wave_active"):
        return None
    m = re.fullmatch(r"wave-(\d+)", str(data.get("current_wave", "")))
    if not m:
        return None
    n = m.group(1)
    return [f"wave-{n}"]   # plus any legacy label forms you still accept

def _open_count(repo: str, labels: list[str]) -> int | None:
    union = set()
    for label in labels:
        try:
            r = subprocess.run(
                ["gh", "issue", "list", "--repo", repo, "--state", "open",
                 "--label", label, "--json", "number"],
                capture_output=True, text=True, timeout=3)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None
        if r.returncode != 0:
            return None
        try:
            union.update(item["number"] for item in json.loads(r.stdout or "[]"))
        except (json.JSONDecodeError, TypeError, KeyError):
            return None
    return len(union)

def _has_carry_forward(args: str) -> bool:
    return bool(args) and any(p.search(args) for p in _CARRY_FORWARD)

def check(data: dict) -> dict | None:
    if data.get("tool_name") != "Skill":
        return None
    ti = data.get("tool_input", {})
    skill = ti.get("skill", "")
    if skill not in _GATED:
        return None

    labels = _active_labels()
    if labels is None:
        return {"decision": "allow",
                "systemMessage": "WARNING: no active iteration label; running audit-free."}

    per_repo, successes = {}, 0
    for repo in _REPOS:
        c = _open_count(repo, labels)
        if c is None:
            continue
        successes += 1
        if c > 0:
            per_repo[repo] = c
    if successes == 0:
        return {"decision": "allow",
                "systemMessage": "WARNING: could not query any repo; running audit-free."}

    total = sum(per_repo.values())
    if total == 0:
        return None
    if _has_carry_forward(ti.get("args", "")):
        return {"decision": "allow",
                "systemMessage": f"NOTE: {total} open item(s); carry-forward marker present."}
    return {"decision": "block",
            "reason": f"BLOCKED: /{skill} cannot claim conclusion — {total} open item(s): "
                      + ", ".join(f"{r}:{n}" for r, n in sorted(per_repo.items()))
                      + ". Close them or add a carry-forward list to args."}

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

- **Gated skill set, repo list, status-file schema, and label scheme** are all
  project-specific — replace them.
- **PreToolUse, not PostToolUse.** The whole value is gating the claim *before* it
  renders; a post-hoc scan is too late.
- **Fail-open on infrastructure failure** (CLI missing, network, malformed
  status) with a visible warning — never silently block or silently allow.
- **No in-band override flag** is a deliberate design choice: the override is to
  fix reality (close items / declare carry-forward), not to silence the gate.
- **Wall-clock budget**: N repos × per-repo timeout; set the settings timeout
  above that.
- The **merge-ready-PR exemption** is optional and adds real complexity (PR
  listing, mergeable + green-checks classification, closing-keyword parsing of
  the PR body because the structured "closing references" API field is empty for
  PRs based on a non-default branch). Add it only if your wrap-up flow hits the
  same chicken-and-egg.
```
