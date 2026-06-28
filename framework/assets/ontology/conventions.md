# Conventions (hand-curated semantic overlay)

The conventions this project holds itself to — the "how we do things here" that isn't
enforceable purely by linters. Keep entries short and actionable; link to the code or hook that
enforces each where one exists. Replace the examples with your project's real conventions.

Tracked by `checksums.json` (edit → dirty → `/ontology-rebuild` reconciles against the code).

## Code

- _Example:_ Public functions carry type hints and a one-line docstring stating intent.
- _Example:_ Prefer the standard library; new third-party deps need a reason.

## Architecture

- _Example:_ Configuration is read through one shared loader, never hard-coded.
- _Example:_ New behaviour is added behind the existing extension seam, not by forking it.

## Process

- _Example:_ Every change lands via a reviewed PR; the default branch is always releasable.
- _Example:_ Commits attribute their author; CI must be green before merge.
