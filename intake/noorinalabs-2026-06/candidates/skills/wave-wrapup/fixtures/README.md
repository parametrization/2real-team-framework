Test fixtures for /wave-wrapup tests.

Each fixture mirrors the `gh pr list ... --json number,headRefOid,mergedAt`
output shape. Used by `test_cross_window_filter.py` to verify the Option A
kickoff-timestamp filter scoped the PR set to the canonical wave window.
