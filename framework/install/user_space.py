#!/usr/bin/env python3
"""Consented, idempotent user-level install step (``~/.claude/settings.json``).

Closes G1 from the #106 user-space audit: the framework's simulated-team workflow
silently depends on harness-global settings the repo installer never writes — chiefly
``env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1``. A fresh clone + ``2real-team init`` on a
clean machine produces a correct project ``.claude/`` but a harness that cannot spawn a
team. This step fills that gap **safely**: check-existing first, consent-gated, merge-only,
never clobbering a user's own value.

Stdlib-only, fail-open consistent with the rest of the installer.

Reusable API (imported by the repo-level pattern, #108)
=======================================================
``merge_settings(path, desired, *, non_interactive) -> Result``
    The full idempotent merge operation for a JSON settings file. Reads ``path``, plans a
    deep merge of ``desired`` against it, and applies the plan **only after consent**,
    following these per-key rules (owner-mandated, "check-existing FIRST"):

    * key already present AND **equal** to desired -> no-op, not offered, reported as
      *matched*. If every desired key matches, the function returns without prompting or
      writing (``status="already-configured"``).
    * key **missing** -> offered in the consent summary; on consent it is added.
    * key present but a **different** scalar (or a type mismatch) -> surfaced as a
      *conflict* and **never written** — the user's value is left exactly as-is.
    * list values (e.g. ``permissions.allow``) are **unioned** — desired entries not
      already present are appended; existing entries and order are preserved. Union is
      non-destructive, so it is applied as an addition (still consent-gated).

    Writing happens iff there is at least one addition AND consent is granted. Before any
    write, the existing file (if present) is backed up via ``backup.backup_file``. The
    merge is applied to an in-memory copy, so a declined/skipped run touches nothing.
    ``non_interactive=True`` guarantees zero writes (consent is denied unprompted).

    Composes the two lower-level primitives so #108 can reuse the whole flow:
    ``consent.prompt_consent`` (opt-in gate) and ``backup.backup_file`` (restorable backup).
    A ``consent_fn`` seam is provided for tests; production callers omit it.

``Result`` (dataclass) — machine-readable outcome:
    ``status``   : ``"already-configured" | "written" | "skipped" | "no-target"
                    | "conflicts-only" | "error"``
    ``added``    : dotted paths (and ``list[]=…`` entries) that were / would be added
    ``matched``  : dotted paths already equal to desired
    ``conflicts``: ``Conflict(path, existing, desired)`` divergences left untouched
    ``backup``   : ``Path`` of the timestamped backup, or ``None``
    ``written``  : whether the file was actually modified

``DESIRED_USER_SETTINGS`` — the G1..G4-user set this step installs (see the audit).
``user_settings_path(home=None)`` — resolve ``<home>/.claude/settings.json``.
``install_user_space(*, home=None, non_interactive, ...)`` — convenience wrapper that
targets the real user settings file.
"""

from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from atomic_io import atomic_write_text
from backup import backup_file
from consent import prompt_consent

# --------------------------------------------------------------------------- desired set

#: The generically-useful, load-bearing user-space settings the installer owns (#106 audit).
#: G1: the agent-teams flag the whole team workflow depends on. G2: teammate spawn UX.
#: G3: the mandated worktree isolation default. G4-user: the ``~/.claude/**`` permission
#: globs (owner-approved split — repo-relative ``.claude/**`` perms stay in the repo
#: installer's settings.template.json and are intentionally NOT duplicated here).
DESIRED_USER_SETTINGS: dict[str, Any] = {
    "env": {
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",  # G1 — enables team spawning
    },
    "teammateMode": "auto",  # G2 — teammate spawn UX
    "worktree": {
        "baseRef": "fresh",  # G3 — mandated worktree isolation base
    },
    "permissions": {
        # G4-user — absolute home globs so orchestrator writes to user space
        # don't prompt. Kept generic (``~``-anchored, no machine paths); union-merged.
        "allow": [
            "Edit(~/.claude/**)",
            "Read(~/.claude/**)",
            "Write(~/.claude/**)",
        ],
    },
}


# ------------------------------------------------------------------------------- results


@dataclass(frozen=True)
class Conflict:
    """A desired key that diverges from an existing user value (left untouched)."""

    path: str
    existing: Any
    desired: Any


@dataclass
class Result:
    """Machine-readable outcome of :func:`merge_settings`. See module docstring."""

    status: str
    added: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    backup: Path | None = None
    written: bool = False


# --------------------------------------------------------------------------------- merge


def _plan_merge(
    existing: dict,
    desired: dict,
    prefix: str,
    added: list[str],
    matched: list[str],
    conflicts: list[Conflict],
) -> None:
    """Deep-merge ``desired`` into ``existing`` (mutated in place), recording the plan.

    Applies additions and list-unions to ``existing``; records — but does NOT apply —
    divergent scalars / type mismatches as conflicts. See module docstring for the rules.
    """
    for key, dval in desired.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if key not in existing:
            existing[key] = copy.deepcopy(dval)
            _collect_added(dotted, dval, added)
            continue
        eval_ = existing[key]
        if isinstance(dval, dict) and isinstance(eval_, dict):
            _plan_merge(eval_, dval, dotted, added, matched, conflicts)
        elif isinstance(dval, list) and isinstance(eval_, list):
            for item in dval:
                if item in eval_:
                    matched.append(f"{dotted}[]={item!r}")
                else:
                    eval_.append(item)
                    added.append(f"{dotted}[]={item!r}")
        elif isinstance(dval, (dict, list)) or isinstance(eval_, (dict, list)):
            # container-vs-scalar (or list-vs-dict) type mismatch — never coerce.
            conflicts.append(Conflict(dotted, eval_, dval))
        elif eval_ == dval:
            matched.append(dotted)
        else:
            conflicts.append(Conflict(dotted, eval_, dval))


def _collect_added(dotted: str, value: Any, added: list[str]) -> None:
    """Record a freshly-added subtree as individual leaf paths (for a readable summary)."""
    if isinstance(value, dict):
        for k, v in value.items():
            _collect_added(f"{dotted}.{k}", v, added)
    elif isinstance(value, list):
        for item in value:
            added.append(f"{dotted}[]={item!r}")
    else:
        added.append(f"{dotted}={value!r}")


def _summary(path: Path, added: list[str], conflicts: list[Conflict]) -> str:
    """Human-readable consent summary of exactly what will change."""
    lines = [f"About to amend {path} (merge-only; your other settings are preserved):"]
    lines.append("  ADD:")
    for a in added:
        lines.append(f"    + {a}")
    if conflicts:
        lines.append("  CONFLICT (left as-is, NOT changed):")
        for c in conflicts:
            lines.append(f"    ! {c.path}: yours={c.existing!r} (desired {c.desired!r})")
    lines.append("A timestamped backup of the current file is taken before writing.")
    return "\n".join(lines)


def merge_settings(
    path: Path | str,
    desired: dict,
    *,
    non_interactive: bool,
    consent_fn: Callable[[str], bool] | None = None,
) -> Result:
    """Idempotently, consent-gated, merge ``desired`` into the JSON file at ``path``.

    See the module docstring for the full contract. ``consent_fn`` (test seam) overrides
    the default :func:`consent.prompt_consent`; it receives the summary and returns the
    opt-in decision.
    """
    path = Path(path)
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return Result(status="error")
        if not isinstance(existing, dict):
            return Result(status="error")

    merged = copy.deepcopy(existing)
    added: list[str] = []
    matched: list[str] = []
    conflicts: list[Conflict] = []
    _plan_merge(merged, desired, "", added, matched, conflicts)

    # Check-existing FIRST: nothing to add -> never prompt, never write.
    if not added:
        status = "conflicts-only" if conflicts else "already-configured"
        return Result(status=status, matched=matched, conflicts=conflicts)

    summary = _summary(path, added, conflicts)
    granted = (consent_fn or _default_consent(non_interactive))(summary)
    if not granted:
        return Result(
            status="skipped", added=added, matched=matched, conflicts=conflicts
        )

    backup = backup_file(path)  # None if the file does not exist yet
    # Atomic write (#145): temp file in the same dir + os.replace, so an interrupt
    # can never leave a truncated settings.json (the backup above stays a fallback).
    atomic_write_text(path, json.dumps(merged, indent=2) + "\n")
    return Result(
        status="written",
        added=added,
        matched=matched,
        conflicts=conflicts,
        backup=backup,
        written=True,
    )


def _default_consent(non_interactive: bool) -> Callable[[str], bool]:
    """Bind :func:`consent.prompt_consent` to the run's interactivity."""
    return lambda summary: prompt_consent(summary, non_interactive=non_interactive)


# --------------------------------------------------------------------------- convenience


def user_settings_path(home: Path | None = None) -> Path:
    """Resolve ``<home>/.claude/settings.json`` (``home`` defaults to ``Path.home()``)."""
    return (home or Path.home()) / ".claude" / "settings.json"


def install_user_space(
    *,
    home: Path | None = None,
    non_interactive: bool,
    path: Path | None = None,
    consent_fn: Callable[[str], bool] | None = None,
) -> Result:
    """Install :data:`DESIRED_USER_SETTINGS` into the user's settings file.

    Wrapper over :func:`merge_settings` that resolves the real target
    (``~/.claude/settings.json``). ``path`` / ``home`` are override seams (tests pass a
    fake HOME so the real user space is never touched).
    """
    target = path or user_settings_path(home)
    return merge_settings(
        target, DESIRED_USER_SETTINGS, non_interactive=non_interactive, consent_fn=consent_fn
    )


# --------------------------------------------------------------------------------- report


def report(result: Result, path: Path) -> str:
    """One-block human summary of a :func:`merge_settings` outcome for installer output."""
    lines = ["-- user-level install (~/.claude/settings.json) --"]
    if result.status == "already-configured":
        lines.append(f"already configured: {path} has every desired key. No prompt, no write.")
        return "\n".join(lines)
    if result.status == "conflicts-only":
        lines.append("nothing to add; the following differ from your values (left as-is):")
        for c in result.conflicts:
            lines.append(f"  ! {c.path}: yours={c.existing!r} (desired {c.desired!r})")
        return "\n".join(lines)
    if result.status == "error":
        lines.append(f"skipped: {path} is not valid JSON — left untouched.")
        return "\n".join(lines)
    if result.status == "skipped":
        lines.append("skipped: no consent (or non-interactive). Nothing written.")
        lines.append(f"  would have added: {', '.join(result.added)}")
        if result.conflicts:
            for c in result.conflicts:
                lines.append(f"  ! conflict (untouched): {c.path} yours={c.existing!r}")
        return "\n".join(lines)
    # written
    lines.append(f"written: amended {path}")
    lines.append(f"  added: {', '.join(result.added)}")
    if result.backup is not None:
        lines.append(f"  backup: {result.backup}")
    if result.conflicts:
        for c in result.conflicts:
            lines.append(f"  ! conflict left untouched: {c.path} yours={c.existing!r}")
    return "\n".join(lines)


# --------------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Consented, idempotent user-level install of the framework's "
        "harness-global settings into ~/.claude/settings.json (closes #106 G1).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--non-interactive",
        action="store_true",
        help="Never prompt; the safe default is to SKIP (write nothing) unprompted.",
    )
    ap.add_argument(
        "--home",
        metavar="DIR",
        help="Override the home directory (targets <DIR>/.claude/settings.json). "
        "For testing / non-standard layouts; defaults to the real ~.",
    )
    args = ap.parse_args(argv)

    home = Path(args.home).resolve() if args.home else None
    target = user_settings_path(home)
    result = install_user_space(home=home, non_interactive=args.non_interactive)
    print(report(result, target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
