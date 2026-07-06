#!/usr/bin/env python3
"""Explicit opt-in consent for installer writes that touch user space (``~/.claude``).

Part of the reusable user-space install toolkit introduced for #107 (consented
user-level install) and reused by #108 (repo-level pattern). Stdlib-only, no deps.

Public API
==========
``prompt_consent(summary, *, non_interactive, prompt=None) -> bool``
    Return ``True`` **only** on an explicit interactive opt-in. The write policy is
    fail-safe by construction — the function returns ``False`` (do not write) unless a
    human is present and answers yes:

    * ``non_interactive=True``           -> ``False`` (never prompt, never write).
    * stdin is not a TTY                 -> ``False`` (no human to consent).
    * answer is empty / not an explicit yes -> ``False`` (default is no).
    * answer is ``y`` / ``yes`` (case-insensitive) -> ``True``.

    ``summary`` is printed verbatim above the prompt so the caller controls exactly
    what the user is consenting to (which file, which keys). Keep it specific.
    ``prompt`` overrides the question line so the same gate serves user-space (#107,
    the default ``~/.claude`` wording) and repo-level (#108) writes; omit it for the
    user-space default.

Contract note for callers (#108): treat a ``False`` return as "leave everything
untouched". Never write to user space without a ``True`` from this function.
"""

from __future__ import annotations

import sys
from typing import Callable

#: Default question line (user-space #107 wording). ``prompt_consent(prompt=...)``
#: overrides it for repo-level (#108) writes.
_DEFAULT_PROMPT = "Proceed with the above write to ~/.claude? [y/N]: "


def prompt_consent(
    summary: str,
    *,
    non_interactive: bool,
    prompt: str | None = None,
    _input: Callable[[str], str] = input,
    _isatty: bool | None = None,
) -> bool:
    """Opt-in consent gate. See the module docstring for the exact policy.

    ``prompt`` overrides the question line (defaults to the user-space wording).
    ``_input`` / ``_isatty`` are injection seams for tests only; production callers
    pass just ``summary`` and ``non_interactive`` (plus ``prompt`` for repo-level).
    """
    if non_interactive:
        return False
    isatty = _isatty if _isatty is not None else sys.stdin.isatty()
    if not isatty:
        return False
    print(summary)
    try:
        answer = _input(prompt or _DEFAULT_PROMPT)
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")
