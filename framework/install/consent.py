#!/usr/bin/env python3
"""Explicit opt-in consent for installer writes that touch user space (``~/.claude``).

Part of the reusable user-space install toolkit introduced for #107 (consented
user-level install) and reused by #108 (repo-level pattern). Stdlib-only, no deps.

Public API
==========
``prompt_consent(summary, *, non_interactive) -> bool``
    Return ``True`` **only** on an explicit interactive opt-in. The write policy is
    fail-safe by construction — the function returns ``False`` (do not write) unless a
    human is present and answers yes:

    * ``non_interactive=True``           -> ``False`` (never prompt, never write).
    * stdin is not a TTY                 -> ``False`` (no human to consent).
    * answer is empty / not an explicit yes -> ``False`` (default is no).
    * answer is ``y`` / ``yes`` (case-insensitive) -> ``True``.

    ``summary`` is printed verbatim above the prompt so the caller controls exactly
    what the user is consenting to (which file, which keys). Keep it specific.

Contract note for callers (#108): treat a ``False`` return as "leave everything
untouched". Never write to user space without a ``True`` from this function.
"""

from __future__ import annotations

import sys
from typing import Callable


def prompt_consent(
    summary: str,
    *,
    non_interactive: bool,
    _input: Callable[[str], str] = input,
    _isatty: bool | None = None,
) -> bool:
    """Opt-in consent gate. See the module docstring for the exact policy.

    ``_input`` / ``_isatty`` are injection seams for tests only; production callers
    pass just ``summary`` and ``non_interactive``.
    """
    if non_interactive:
        return False
    isatty = _isatty if _isatty is not None else sys.stdin.isatty()
    if not isatty:
        return False
    print(summary)
    try:
        answer = _input("Proceed with the above write to ~/.claude? [y/N]: ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")
