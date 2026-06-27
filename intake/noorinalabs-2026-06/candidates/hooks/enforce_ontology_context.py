#!/usr/bin/env python3
"""PreToolUse hook: Require ontology context in Agent spawn prompts.

Blocks worktree-isolated Agent tool calls unless the prompt either contains
ontology context markers (indicating the orchestrator ran
`/ontology-librarian` before spawning) OR the prompt opens with a
coordinator-class role declaration (Manager, Pipeline Manager, Project
Lead, Program Director, TPM, Release Coordinator).

Coordinator-class exemption (#466, expanded via Aino + Santiago review)
======================================================================

Coordinators communicate via SendMessage and rarely Edit/Write directly.
Hook 15 (`enforce_librarian_consulted`) covers the Edit/Write surface for
the few cases where a coordinator does edit. Requiring ontology context in
every coordinator spawn brief adds ceremony without preventive value — and
when orchestrators forget (as in the P3W11 wave-tail re-spawn burst that
captured 8 blocks 2026-05-17 03:54Z), the hook produces noise rather than
catching real risk.

Implementer-class roles (Engineer, Tech Lead, Standards & Quality Lead,
Security Engineer, etc.) are NOT exempt — they Edit/Write code as the
primary task.

Title taxonomy is enumerative (not heuristic): each role string here
corresponds to an actual canonical-composer output observed in spawn
briefs across the 7 child rosters. Compound titles that the composer
flattens to a different name (e.g., Bereket's "Infrastructure Manager"
→ composer emits `, Manager`; Marcia's "Project Lead / Manager" →
composer emits `, Project Lead`) match by their composer-output form.

Exit codes:
  0 — allow (not an Agent call, non-worktree isolation, coordinator-class
      spawn, or ontology context present)
  2 — block (implementer-class spawn without ontology context)
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from annunaki_log import log_pretooluse_block  # noqa: E402

ONTOLOGY_MARKERS = [
    "Ontology Status",
    "ontology is current",
    "files pending resolution",
    "ontology/domain.yaml",
    "ontology/services.yaml",
    "ontology/conventions.md",
    "## Ontology Context",
]

# Canonical coordinator-class opener: `You are **{Name}**, {Role}[ for {repo}]`
# where {Role} is one of the pure-coordination titles. Bold-markdown around
# the name is optional. The `(?:\A|\n)You are` anchor matches the opener only
# when it sits at an EXACT line start (start of prompt, or immediately after a
# newline) — no leading-whitespace tolerance. This still handles briefs that
# prepend a header / task framing / role-card excerpt before the opener
# (the opener line itself is at column 0; only the prepended content is above
# it — see CoordinatorExemptHandlesPrependedHeader tests), while NOT exempting
# a `You are X, Manager` line that appears INDENTED inside the prompt body
# (4-space code blocks, YAML-indented examples). The old `^\s*` + re.MULTILINE
# matched those indented lines and falsely exempted the spawn (#471).
#
# Title list is enumerative — see module docstring. Multi-word titles
# precede single-word `Manager` alternation so the regex engine doesn't
# half-consume "Pipeline Manager" as `Manager` (it wouldn't anyway because
# `Manager` requires position right after `, `, but the explicit ordering
# documents the intent for future maintainers).
COORDINATOR_ROLE_OPENER = re.compile(
    r"(?:\A|\n)You are\s+\*{0,2}[^,\n]+?\*{0,2},\s*"
    r"(Pipeline\s+Manager"
    r"|Project\s+Lead"
    r"|Program\s+Director"
    r"|Technical\s+Program\s+Manager"
    r"|TPM"
    r"|Release\s+Coordinator"
    r"|Manager)\b",
    re.IGNORECASE,
)


def check(input_data: dict) -> dict | None:
    """Pure decision function. Returns None to allow, or a block-dict.

    Returns None for malformed inputs (non-dict tool_input, non-str prompt,
    etc.) rather than crashing — PreToolUse hooks that raise are surfaced
    to the user as block-with-error, which is worse than allowing through
    a malformed shape that the tool itself will reject.
    """
    if input_data.get("tool_name", "") != "Agent":
        return None

    tool_input = input_data.get("tool_input")
    if not isinstance(tool_input, dict):
        return None

    isolation = tool_input.get("isolation", "")
    prompt = tool_input.get("prompt", "")
    if not isinstance(isolation, str) or not isinstance(prompt, str):
        return None

    if isolation != "worktree":
        return None

    if COORDINATOR_ROLE_OPENER.search(prompt):
        return None

    prompt_lower = prompt.lower()
    for marker in ONTOLOGY_MARKERS:
        if marker.lower() in prompt_lower:
            return None

    return {
        "decision": "block",
        "reason": (
            "BLOCKED: Implementation agent spawned without ontology context.\n"
            "The charter requires: 'Every agent MUST consult /ontology-librarian "
            "{topic} before making code changes.'\n\n"
            "Before spawning, run `/ontology-librarian {topic}` and include "
            "the output in the agent's prompt under a '## Ontology Context' heading."
        ),
    }


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result is None:
        sys.exit(0)

    print(json.dumps(result))
    prompt = ""
    tool_input = input_data.get("tool_input")
    if isinstance(tool_input, dict):
        raw = tool_input.get("prompt", "")
        if isinstance(raw, str):
            prompt = raw[:200]
    log_pretooluse_block("enforce_ontology_context", prompt, result["reason"])
    sys.exit(2)


if __name__ == "__main__":
    main()
