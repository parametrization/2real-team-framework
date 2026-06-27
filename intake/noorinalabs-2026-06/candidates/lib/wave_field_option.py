#!/usr/bin/env python3
"""Ensure the Project-2 Wave single-select field has an option for a wave label.

Used by /wave-kickoff to pre-create the Wave board option BEFORE wave labels
are applied to issues — eliminating the repeated "Project 2 Wave field has no
option 'W{X}'" PostToolUse captures (8 such in P6W17 alone, issue #868).

Design
======
- Idempotent: exits 0 / returns ``status="present"`` when the option already
  exists. No-op on repeated calls.
- Full-list-preserve: ``updateProjectV2Field`` REPLACES the whole options list,
  so existing options are read first and re-sent in full plus the new entry.
  Omitting any existing option would wipe it (memory
  ``feedback_projectv2_field_option``).
- Read-back-verified: after the mutation the field is re-introspected to
  confirm the option appears.
- Auth-preflight: checks ``gh auth status`` for ``project`` scope before any
  mutation; fails with a clear message if missing.

Option-name grammar (#810)
==========================
  ``wave-{X}``       →  ``W{X}``      (e.g. ``wave-18`` → ``W18``)
  ``p{N}-wave-{M}``  →  ``P{N}W{M}``  (e.g. ``p6-wave-17`` → ``P6W17``)
  ``wave-x``         →  ``WX``

This grammar mirrors ``wave_label_to_option_name`` in
``.claude/hooks/_wave_label_parse.py`` (the canonical authoritative copy);
the duplication is intentional to keep this lib module self-contained and
avoid a cross-layer hooks→lib import.

CLI
===
::

    python3 wave_field_option.py ensure <wave-label>  [--project N] [--org ORG]

        Ensures the Wave option for ``<wave-label>`` exists on the project.
        Exits 0 on success (present or created+verified), 1 on error.

    python3 wave_field_option.py check <wave-label>   [--project N] [--org ORG]

        Read-only check: exits 0 if option present, 2 if absent, 1 on error.

Integration
===========
Called in ``/wave-kickoff`` Step 2a (between label-create and auth-scope audit)
so that ``post_label_change_wave_field_sync`` finds the option already present
when it fires on the label-apply in Step 7.

Provenance: issue #868, P6W17 retro proposed change #1, owner-adopted
2026-06-25. Implemented in P7W18 framework wave by Nurul Hakim
(Observability Engineer).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Option-name grammar (#810) — mirrors _wave_label_parse.wave_label_to_option_name
# ---------------------------------------------------------------------------

_LEGACY_WAVE_RE = re.compile(r"^p(\d+)-wave-(\d+)$")
_GLOBAL_WAVE_RE = re.compile(r"^wave-(\d+)$")
_PLACEHOLDER_LABEL = "wave-x"


def _wave_label_to_option_name(label: str) -> str | None:
    """Convert a wave label to the Project-2 Wave single-select option name.

    Returns ``None`` when ``label`` is not a recognised wave label shape.
    Duplicates ``wave_label_to_option_name`` from ``.claude/hooks/_wave_label_parse``
    so this lib module is self-contained.
    """
    if label == _PLACEHOLDER_LABEL:
        return "WX"
    m = _LEGACY_WAVE_RE.match(label)
    if m:
        return f"P{m.group(1)}W{m.group(2)}"
    m = _GLOBAL_WAVE_RE.match(label)
    if m:
        return f"W{m.group(1)}"
    return None


# ---------------------------------------------------------------------------
# GraphQL helpers
# ---------------------------------------------------------------------------

ORG = "noorinalabs"
PROJECT_NUMBER = 2

# Default color for newly-created Wave options.  PURPLE matches the wave-label
# badge colour (``8B5CF6``) set in ``gh label create`` at wave-kickoff Step 2.
NEW_OPTION_COLOR = "PURPLE"
NEW_OPTION_DESCRIPTION = ""

_INTROSPECT_QUERY = """
query($org: String!, $project: Int!) {
  organization(login: $org) {
    projectV2(number: $project) {
      id
      field(name: "Wave") {
        ... on ProjectV2SingleSelectField {
          id
          options { id name color description }
        }
      }
    }
  }
}
"""

# The mutation replaces the ENTIRE options list; callers must include all
# existing options plus the new one in the ``singleSelectOptions`` input.
_UPDATE_FIELD_MUTATION = """
mutation($input: UpdateProjectV2FieldInput!) {
  updateProjectV2Field(input: $input) {
    projectV2Field {
      ... on ProjectV2SingleSelectField {
        id
        options { id name }
      }
    }
  }
}
"""


def _run_graphql_simple(
    query: str,
    variables: dict[str, Any],
    runner: Any = None,
) -> dict | None:
    """Run a simple GraphQL query/mutation via ``gh api graphql -f/-F``.

    Suitable for queries whose variables are all scalars (strings + ints).
    Returns the parsed response dict or ``None`` on error.

    *runner* is an injection point for tests: it receives ``(query, variables)``
    and must return the raw stdout string (or raise on error).
    """
    if runner is not None:
        try:
            raw = runner(query, variables)
        except Exception:  # noqa: BLE001
            return None
    else:
        argv = ["gh", "api", "graphql"]
        for k, v in variables.items():
            if isinstance(v, bool):
                argv += ["-F", f"{k}={'true' if v else 'false'}"]
            elif isinstance(v, int):
                argv += ["-F", f"{k}={v}"]
            else:
                argv += ["-f", f"{k}={v}"]
        argv += ["-f", f"query={query}"]
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=20)
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            return None
        if result.returncode != 0:
            return None
        raw = result.stdout

    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _run_graphql_stdin(
    body: str,
    stdin_runner: Any = None,
) -> dict | None:
    """Run a GraphQL mutation by posting a full JSON body via stdin.

    Used for mutations whose variables contain nested objects/arrays that
    ``-f``/``-F`` cannot express (e.g. ``singleSelectOptions``).

    *stdin_runner* is the injection point for tests: it receives the raw
    JSON body string and must return the raw stdout string (or raise).
    """
    if stdin_runner is not None:
        try:
            raw = stdin_runner(body)
        except Exception:  # noqa: BLE001
            return None
    else:
        try:
            result = subprocess.run(
                ["gh", "api", "graphql", "--input", "-"],
                input=body,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            return None
        if result.returncode != 0:
            return None
        raw = result.stdout

    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _has_project_scope(auth_runner: Any = None) -> bool:
    """True iff ``gh auth status -h github.com`` reports the ``project`` scope."""
    if auth_runner is not None:
        try:
            stdout = auth_runner()
        except Exception:  # noqa: BLE001
            return False
    else:
        try:
            result = subprocess.run(
                ["gh", "auth", "status", "-h", "github.com"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            stdout = (result.stdout or "") + (result.stderr or "")
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            return False

    return "'project'" in stdout


def _introspect_field(
    org: str = ORG,
    project: int = PROJECT_NUMBER,
    runner: Any = None,
) -> dict | None:
    """Return ``{project_id, field_id, options: [{id, name, color, description}]}``
    or ``None`` on failure.

    *runner* — same injection point as ``_run_graphql_simple``.
    """
    data = _run_graphql_simple(
        _INTROSPECT_QUERY,
        {"org": org, "project": project},
        runner=runner,
    )
    if not data:
        return None
    proj = (data.get("data") or {}).get("organization", {}).get("projectV2")
    if not proj:
        return None
    project_id = proj.get("id")
    field = proj.get("field") or {}
    field_id = field.get("id")
    options = field.get("options") or []
    if not project_id or not field_id:
        return None
    return {"project_id": project_id, "field_id": field_id, "options": options}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_wave_option(
    wave_label: str,
    org: str = ORG,
    project: int = PROJECT_NUMBER,
    runner: Any = None,
) -> dict:
    """Read-only check: is the Wave option for *wave_label* present on the board?

    Returns a result dict::

        {"status": "present",  "option_name": "W18", "option_id": "..."}
        {"status": "absent",   "option_name": "W18"}
        {"status": "error",    "detail": "..."}

    Never modifies the board.
    """
    option_name = _wave_label_to_option_name(wave_label)
    if option_name is None:
        return {"status": "error", "detail": f"Not a valid wave label: {wave_label!r}"}

    field = _introspect_field(org=org, project=project, runner=runner)
    if field is None:
        return {"status": "error", "detail": f"Failed to introspect project {project} Wave field"}

    for opt in field["options"]:
        if opt.get("name") == option_name:
            return {"status": "present", "option_name": option_name, "option_id": opt.get("id", "")}

    return {"status": "absent", "option_name": option_name}


def ensure_wave_option(
    wave_label: str,
    org: str = ORG,
    project: int = PROJECT_NUMBER,
    auth_runner: Any = None,
    runner: Any = None,
    stdin_runner: Any = None,
) -> dict:
    """Idempotently ensure the Wave option for *wave_label* exists on the board.

    Returns a result dict::

        {"status": "present",  "option_name": "W18"}   # already existed — no-op
        {"status": "created",  "option_name": "W18"}   # created + read-back-verified
        {"status": "error",    "detail": "..."}

    Injection points for tests:

    - *auth_runner*   — callable ``() -> str`` returning ``gh auth status`` output
    - *runner*        — callable ``(query, variables) -> str`` for GraphQL reads
    - *stdin_runner*  — callable ``(body_json) -> str`` for GraphQL mutations
    """
    option_name = _wave_label_to_option_name(wave_label)
    if option_name is None:
        return {"status": "error", "detail": f"Not a valid wave label: {wave_label!r}"}

    # Step 1: check if already present (idempotent fast path).
    field = _introspect_field(org=org, project=project, runner=runner)
    if field is None:
        return {
            "status": "error",
            "detail": (
                f"Failed to introspect project {project} Wave field (auth issue or network error)"
            ),
        }

    for opt in field["options"]:
        if opt.get("name") == option_name:
            return {"status": "present", "option_name": option_name}

    # Step 2: auth scope check before any mutation.
    if not _has_project_scope(auth_runner=auth_runner):
        return {
            "status": "error",
            "detail": ("gh project scope required; run 'gh auth refresh -s project' then retry."),
        }

    # Step 3: build the full options list = existing + new.
    # updateProjectV2Field REPLACES the whole list — re-send every existing
    # option (preserving name/color/description) plus the new entry.
    existing_options = [
        {
            "name": opt.get("name", ""),
            "color": opt.get("color", "GRAY"),
            "description": opt.get("description", ""),
        }
        for opt in field["options"]
    ]
    new_option: dict[str, str] = {
        "name": option_name,
        "color": NEW_OPTION_COLOR,
        "description": NEW_OPTION_DESCRIPTION,
    }
    all_options = existing_options + [new_option]

    mutation_body = json.dumps(
        {
            "query": _UPDATE_FIELD_MUTATION,
            "variables": {
                "input": {
                    "fieldId": field["field_id"],
                    "singleSelectOptions": all_options,
                }
            },
        }
    )

    result = _run_graphql_stdin(mutation_body, stdin_runner=stdin_runner)
    if not result or "errors" in result:
        errors_str = json.dumps(result.get("errors") if result else [])[:300]
        return {
            "status": "error",
            "detail": f"updateProjectV2Field mutation failed: {errors_str}",
        }

    # Step 4: read-back verify the option stuck.
    field_after = _introspect_field(org=org, project=project, runner=runner)
    if field_after is None:
        return {
            "status": "error",
            "detail": (
                "Option create mutation appeared to succeed but read-back introspection failed"
            ),
        }
    for opt in field_after["options"]:
        if opt.get("name") == option_name:
            return {"status": "created", "option_name": option_name}

    return {
        "status": "error",
        "detail": (
            f"Mutation appeared to succeed but option {option_name!r} "
            f"not found on read-back; current options: "
            f"{[o.get('name') for o in field_after['options']]}"
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Entry point for CLI use from ``/wave-kickoff`` Step 2a.

    Exit codes:
      0  — success (present or created)
      1  — error (bad label, auth failure, network, mutation failed, etc.)
      2  — ``check`` subcommand: option absent (no mutation performed)
    """
    parser = argparse.ArgumentParser(
        description=(
            "Ensure the Project-2 Wave single-select field has an option for a wave label."
        )
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name, help_text in [
        ("ensure", "Create the option if absent (idempotent)."),
        ("check", "Read-only check: exit 0 present, 2 absent, 1 error."),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("wave_label", help="Wave label, e.g. wave-18 or p6-wave-17")
        p.add_argument(
            "--project",
            type=int,
            default=PROJECT_NUMBER,
            help="GitHub project number",
        )
        p.add_argument("--org", default=ORG, help="GitHub org login")

    args = parser.parse_args(argv)

    if args.cmd == "check":
        res = check_wave_option(args.wave_label, org=args.org, project=args.project)
        if res["status"] == "present":
            print(
                f"PRESENT: Wave option '{res['option_name']}' "
                f"already exists on project {args.project}."
            )
            return 0
        if res["status"] == "absent":
            print(
                f"ABSENT: Wave option '{res['option_name']}' not found on project {args.project}."
            )
            return 2
        print(f"ERROR: {res['detail']}", file=sys.stderr)
        return 1

    # ensure
    res = ensure_wave_option(args.wave_label, org=args.org, project=args.project)
    if res["status"] == "present":
        print(
            f"OK (present): Wave option '{res['option_name']}' "
            f"already exists on project {args.project}."
        )
        return 0
    if res["status"] == "created":
        print(
            f"OK (created): Wave option '{res['option_name']}' created on "
            f"project {args.project} and read-back verified."
        )
        return 0
    print(f"ERROR: {res['detail']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
