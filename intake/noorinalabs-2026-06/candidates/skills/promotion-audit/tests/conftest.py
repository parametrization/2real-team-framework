"""Isolate temp-repo git tests from an inherited git environment (main#719).

git exports ``GIT_DIR``/``GIT_WORK_TREE``/``GIT_INDEX_FILE`` into hook
subprocesses (notably the pre-push ``pytest`` hook). ``test_run.py`` builds a
throwaway repo and runs ``git -C <tmp> commit`` — which sets cwd but does not
override an inherited ``GIT_DIR`` — so without this the commit targets the
parent repo and fails ("No .pre-commit-config.yaml found") whenever the suite
is run as a git hook, even though it passes standalone and in CI.

Stripping the ``GIT_*`` namespace before every test makes temp-repo git
hermetic regardless of launch context. ``monkeypatch`` restores afterwards.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key, raising=False)
