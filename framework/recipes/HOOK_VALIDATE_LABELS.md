# HOOK: validate_labels

## Purpose

Block `gh issue create` when any `--label` / `-l` value does not exist in the
target repo — a typo'd or not-yet-created label fails fast with a
`gh label create` suggestion instead of a server-side rejection mid-flow.

## Enforces

A missing label on issue-create is a PreToolUse **block** (exit 2). Unverifiable
labels (couldn't fetch the repo's label list) → an advisory warning, not a block.

## Trigger / scope

Fires only on a command-position `gh issue create`. Does NOT match `gh issue
list/view/edit`, `gh label create`, or `gh pr create`. A `--label` substring
*inside* another flag's value (e.g. `--body`) is never treated as a label —
`shlex` tokenization + preceding-flag matching guarantees it. `--repo`/`-R` is
forwarded to `gh label list` so the labels of the repo being created in are
checked, not the cwd-resolved repo.

## Config

None — this hook has no project-specific values. The only external seam is the
shared `_framework_log` audit sink. Enable/disable/reorder via `hooks.pre_bash`.

## Fail posture

Fails **open**: on a tokenize failure (unbalanced quote in `--body` prose) or an
unfetchable label list it allows (warning), since `gh` rejects a genuinely-missing
label server-side and a false block stops valid work.

## Adapt

- Different SCM CLI: swap the `gh label list` call + the `gh issue create`
  matcher for your provider's equivalents (the tokenization is generic).
