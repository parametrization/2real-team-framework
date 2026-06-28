"""Pytest configuration for the framework test-suite.

Force hook events-log suppression for the entire run so any test that fires a hook without an
isolated ``cwd`` cannot write the real ``.claude/framework/events.jsonl``. Set at import time
(before collection) and via the environment so subprocess-spawned dispatchers (e.g. the
bootstrap smoke test) inherit it too. Complements the in-code ``PYTEST_CURRENT_TEST`` check in
``_framework_log._is_test_mode`` (belt-and-suspenders).
"""

import os

os.environ.setdefault("FRAMEWORK_HOOK_TEST_MODE", "1")
