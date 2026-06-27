"""Isolate temp-repo git tests from an inherited git environment (main#719).

git exports ``GIT_DIR``/``GIT_WORK_TREE``/``GIT_INDEX_FILE`` (and friends) into
hook subprocesses — notably the pre-push ``pytest`` hook. Tests in this package
build throwaway repos and run git against them via ``git -C <tmp>``, which sets
the working directory but does **not** override an inherited ``GIT_DIR``. Without
this fixture those commits target the *parent* repo (whose pre-commit hook then
fires with the wrong cwd → "No .pre-commit-config.yaml found"), so the whole
suite fails when run as a git hook even though it passes standalone and in CI.

Stripping the ``GIT_*`` namespace before every test makes temp-repo git hermetic
regardless of how the suite was launched. ``monkeypatch`` restores the real
environment afterwards.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key, raising=False)
