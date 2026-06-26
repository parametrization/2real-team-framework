# Generic Library Prompt: Idempotently Ensure a Project Single-Select Option Exists

## Purpose

A project-board automation that tags work items with an iteration label
(`iteration-18`, `cycle-3`, etc.) also wants the board's single-select field
(e.g. an "Iteration" column) to carry a matching option, so the label-apply step
can immediately set the field. If the option does not yet exist, every label-apply
emits a repeated "field has no option X" error.

This helper **pre-creates the board option BEFORE the labels are applied**, as an
idempotent step in the iteration-kickoff flow. It is the project-management API
counterpart of "create the enum value before you reference it."

## Reusable design

- **Idempotent:** read the field's current options first; if the target option
  already exists, return `present` and make no mutation. Safe to call repeatedly.
- **Full-list-preserve (critical):** the single-select field update mutation
  **REPLACES the entire options list**. You must read all existing options and
  re-send them in full plus the new entry — omitting any existing option WIPES it.
  Preserve each existing option's name, color, and description.
- **Read-back-verified:** after the mutation, re-introspect the field and confirm
  the new option actually appears before reporting success.
- **Auth-preflight:** check that the CLI token carries the scope the project API
  requires *before* attempting any mutation; fail with a clear, actionable message
  if it is missing.
- **Label → option-name grammar:** a small pure function maps an iteration label to
  its board option name (e.g. `iteration-18 → I18`, a phase-qualified
  `p6-iteration-17 → P6I17`, a placeholder `iteration-x → IX`). Return `None` for
  an unrecognized label shape. Keep this grammar identical to whatever the rest of
  the framework uses to derive option names; if a hook owns the canonical copy,
  the duplication here is intentional to keep the lib module self-contained and
  avoid a cross-layer import — just keep them in sync.

## Reusable algorithm (`ensure_option`)

1. Map label → option name (pure); error on unrecognized shape.
2. Introspect the project field → `{project_id, field_id, options[]}`. On failure,
   error (auth/network).
3. If the option name is already among `options`, return `present` (no-op).
4. Auth-scope preflight; error if the required project scope is absent.
5. Build the replacement list = all existing options (name+color+description) +
   the new option; send the replace-whole-list mutation.
6. Re-introspect; confirm the new option is present → `created`, else error with
   the current option list for diagnosis.

A read-only `check_option` variant does steps 1–3 only and never mutates.

## Code template (stdlib + a GraphQL-capable issue/project CLI)

```python
"""Idempotently ensure a project single-select field has an option for a label."""
from __future__ import annotations
import json, re, subprocess

_PHASE_RE  = re.compile(r"^p(\d+)-iteration-(\d+)$")
_PLAIN_RE  = re.compile(r"^iteration-(\d+)$")
NEW_OPTION_COLOR = "PURPLE"


def label_to_option_name(label: str) -> str | None:
    if label == "iteration-x":
        return "IX"
    if (m := _PHASE_RE.match(label)):
        return f"P{m.group(1)}I{m.group(2)}"
    if (m := _PLAIN_RE.match(label)):
        return f"I{m.group(1)}"
    return None


def ensure_option(label, *, introspect, has_scope, mutate) -> dict:
    name = label_to_option_name(label)
    if name is None:
        return {"status": "error", "detail": f"not a valid label: {label!r}"}
    field = introspect()
    if field is None:
        return {"status": "error", "detail": "failed to introspect field (auth/network)"}
    if any(o.get("name") == name for o in field["options"]):
        return {"status": "present", "option_name": name}
    if not has_scope():
        return {"status": "error", "detail": "project scope required; refresh auth then retry"}
    all_options = [                       # REPLACE whole list — preserve every existing
        {"name": o.get("name", ""), "color": o.get("color", "GRAY"),
         "description": o.get("description", "")}
        for o in field["options"]
    ] + [{"name": name, "color": NEW_OPTION_COLOR, "description": ""}]
    result = mutate(field["field_id"], all_options)
    if not result or "errors" in result:
        return {"status": "error", "detail": "update mutation failed"}
    after = introspect()                  # read-back verify
    if after and any(o.get("name") == name for o in after["options"]):
        return {"status": "created", "option_name": name}
    return {"status": "error", "detail": "mutation succeeded but option not found on read-back"}
```

`introspect` / `has_scope` / `mutate` are the I/O seams (real implementations call
the project GraphQL API and `auth status`; tests inject fakes). The GraphQL reads
use scalar `-f/-F` flags; the replace-whole-list mutation needs nested
array input, so post a full JSON body via stdin (`--input -`).

## Adaptation notes

- The label grammar, the project number/org, and the new-option color are policy;
  parameterize them.
- CLI exit codes that pair well with a kickoff flow: `0` present-or-created,
  `2` (check mode) option absent, `1` any error.
- Wire `ensure` between the label-create step and the label-apply step of the
  iteration-kickoff flow, so the field-sync automation finds the option already
  present when it fires on label-apply.
- The same full-list-preserve caution applies to ANY replace-whole-collection
  project mutation — never send a partial list to a replace-semantics endpoint.
