"""Tests for require_load_bearing_test — the pre-review gate (#167, plus Wave 3
S2 #174 per-file pairing, S3 #176 seeded refactor exception, and #284 the
automatic docs/comment-only per-file exception).

Exercised entirely via check() with `_fetch_compare_files` monkeypatched (no
network) and an injected config (tmp_path/.claude/framework.config.json) for the
override tests. `--repo`/`--head` are passed explicitly on the command so repo/head
resolution never shells out to git. Stdlib + pytest only.

The load-bearing (revert->fail) property for this suite: `test_blocks_new_behavior_
without_test_file`, `test_blocks_when_diff_unverifiable`, and
`test_blocks_new_behavior_when_paired_test_is_for_an_unrelated_file` (#174) fail if
the core `check()` gate in require_load_bearing_test.py is neutered/reverted to its
pre-#174 whole-diff-boolean behavior (verified manually during development — see PR
description for the revert transcript). They are NOT tautological: each asserts a
specific `"block"` decision with reason content tied to the exact code path under
test, not merely "no exception raised".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))

import _framework_config  # noqa: E402
import require_load_bearing_test as rlbt  # noqa: E402


def _bash(command: str, *, cwd: str | None = None, env: dict | None = None) -> dict:
    d: dict = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        d["cwd"] = cwd
    if env is not None:
        d["env"] = env
    return d


def _write_config(tmp: Path, *, exceptions: dict | None = None) -> None:
    claude = tmp / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "framework.config.json").write_text(
        json.dumps(
            {
                "version": 1,
                "scm": {"provider": "github", "owner": "acme"},
                "policy": {"load_bearing_test_exceptions": exceptions or {}},
            }
        )
    )
    _framework_config.clear_cache()


_CREATE_CMD = 'gh pr create --repo acme/demo --base main --head feat --title x --body y'


def _fake_files(entries: list[dict]):
    return lambda repo, base, head: entries


def _behavior_entry(patch: str, filename: str = "framework/assets/hooks/foo.py") -> dict:
    return {"filename": filename, "status": "modified", "patch": patch}


def _test_entry(patch: str, filename: str = "framework/tests/test_foo.py") -> dict:
    return {"filename": filename, "status": "modified", "patch": patch}


_SUBSTANTIVE_PATCH = "@@ -1,2 +1,3 @@\n line1\n+def new_behavior():\n+    return 42\n"
_TRIVIAL_PATCH = "@@ -1,1 +1,3 @@\n line1\n+   \n+# just a comment\n"

# Single-line docstring addition — the exact Wave 20 (#279/#284) shape: a
# cross-reference docstring added to an existing behavior file, no code.
_DOCSTRING_PATCH = (
    '@@ -1,2 +1,3 @@\n'
    ' def foo():\n'
    '+    """Cross-reference: see bar() for the paired implementation."""\n'
    '     return 1\n'
)

# Multi-line docstring addition, plus a blank line and a `#` comment inside —
# exercises the open/interior/close state machine and comment-inside-docstring.
_MULTILINE_DOCSTRING_PATCH = (
    '@@ -1,1 +1,6 @@\n'
    ' def foo():\n'
    '+    """Longer explanation.\n'
    '+\n'
    '+    # not a real comment, just docstring text\n'
    '+    See bar() for details.\n'
    '+    """\n'
    '     return 1\n'
)

# A docstring addition that ALSO smuggles in a real statement on its own added
# line — the anti-loophole shape: mixing doc content with a hidden behavior
# line in the same file must NOT read as docs-only.
_DOCSTRING_WITH_HIDDEN_CODE_PATCH = (
    '@@ -1,2 +1,4 @@\n'
    ' def foo():\n'
    '+    """Cross-reference: see bar()."""\n'
    '+    _secret_state.append(1)\n'
    '     return 1\n'
)


# --------------------------------------------------------------- command matching


def test_non_gh_pr_create_ignored(monkeypatch) -> None:
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH)]))
    assert rlbt.check(_bash("gh pr list")) is None
    assert rlbt.check(_bash("gh pr view 5")) is None
    assert rlbt.check(_bash("git push origin feat")) is None


# --------------------------------------------------------------- core diff-substance gate


def test_no_behavior_file_allows(monkeypatch) -> None:
    monkeypatch.setattr(
        rlbt, "_fetch_compare_files", _fake_files([{"filename": "README.md", "status": "modified", "patch": "@@ -1 +1,2 @@\n-old\n+new\n"}])
    )
    assert rlbt.check(_bash(_CREATE_CMD)) is None


def test_blocks_new_behavior_without_test_file(monkeypatch) -> None:
    """The core gate: new behavior, zero test-file changes -> hard block."""
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH)]))
    r = rlbt.check(_bash(_CREATE_CMD))
    assert r is not None
    assert r["decision"] == "block"
    assert "framework/assets/hooks/foo.py" in r["reason"]
    assert "load-bearing" in r["reason"].lower()


def test_allows_when_test_file_touched_alongside(monkeypatch) -> None:
    monkeypatch.setattr(
        rlbt,
        "_fetch_compare_files",
        _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH), _test_entry(_SUBSTANTIVE_PATCH)]),
    )
    assert rlbt.check(_bash(_CREATE_CMD)) is None


def test_trivial_behavior_patch_does_not_trip_gate(monkeypatch) -> None:
    """A behavior file with only blank/comment added lines is not 'new behavior'."""
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_TRIVIAL_PATCH)]))
    assert rlbt.check(_bash(_CREATE_CMD)) is None


def test_trivial_test_patch_does_not_satisfy_gate(monkeypatch) -> None:
    """A test file touched with only blank/comment lines does not count as 'test touched'."""
    monkeypatch.setattr(
        rlbt,
        "_fetch_compare_files",
        _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH), _test_entry(_TRIVIAL_PATCH)]),
    )
    r = rlbt.check(_bash(_CREATE_CMD))
    assert r is not None and r["decision"] == "block"


def test_removed_file_ignored(monkeypatch) -> None:
    monkeypatch.setattr(
        rlbt,
        "_fetch_compare_files",
        _fake_files([{"filename": "framework/assets/hooks/foo.py", "status": "removed", "patch": _SUBSTANTIVE_PATCH}]),
    )
    assert rlbt.check(_bash(_CREATE_CMD)) is None


def test_non_python_and_out_of_scope_paths_ignored(monkeypatch) -> None:
    monkeypatch.setattr(
        rlbt,
        "_fetch_compare_files",
        _fake_files(
            [
                {"filename": "framework/assets/hooks/foo.sh", "status": "modified", "patch": _SUBSTANTIVE_PATCH},
                {"filename": "intake/candidate/foo.py", "status": "modified", "patch": _SUBSTANTIVE_PATCH},
                {"filename": "framework/assets/hooks/__init__.py", "status": "modified", "patch": _SUBSTANTIVE_PATCH},
            ]
        ),
    )
    assert rlbt.check(_bash(_CREATE_CMD)) is None


def test_conftest_and_test_dir_recognized_as_test(monkeypatch) -> None:
    monkeypatch.setattr(
        rlbt,
        "_fetch_compare_files",
        _fake_files(
            [
                _behavior_entry(_SUBSTANTIVE_PATCH),
                {"filename": "framework/tests/conftest.py", "status": "modified", "patch": _SUBSTANTIVE_PATCH},
            ]
        ),
    )
    assert rlbt.check(_bash(_CREATE_CMD)) is None


# --------------------------------------------------------------- per-file pairing (S2, #174)


def test_blocks_new_behavior_when_paired_test_is_for_an_unrelated_file(monkeypatch) -> None:
    """The S2 (#174) fix: pairing is per behavior file. A substantive test-file
    change for an UNRELATED module elsewhere in the same diff no longer
    satisfies this behavior file's own requirement — this is the exact
    loophole #174 closes (pre-#174, ANY touched test file passed the WHOLE
    diff)."""
    monkeypatch.setattr(
        rlbt,
        "_fetch_compare_files",
        _fake_files(
            [
                _behavior_entry(_SUBSTANTIVE_PATCH, filename="framework/assets/hooks/foo.py"),
                _test_entry(_SUBSTANTIVE_PATCH, filename="framework/tests/test_unrelated_bar.py"),
            ]
        ),
    )
    r = rlbt.check(_bash(_CREATE_CMD))
    assert r is not None
    assert r["decision"] == "block"
    assert "framework/assets/hooks/foo.py" in r["reason"]


def test_blocks_only_the_specific_unpaired_behavior_file(monkeypatch) -> None:
    """Two new-behavior files in one diff: only ONE has a paired test change.
    The gate must block on the unpaired file specifically, not on both and not
    on neither — this is the per-file granularity, not a per-diff boolean."""
    monkeypatch.setattr(
        rlbt,
        "_fetch_compare_files",
        _fake_files(
            [
                _behavior_entry(_SUBSTANTIVE_PATCH, filename="framework/assets/hooks/foo.py"),
                _behavior_entry(_SUBSTANTIVE_PATCH, filename="framework/assets/lib/bar.py"),
                _test_entry(_SUBSTANTIVE_PATCH, filename="framework/tests/test_foo.py"),
            ]
        ),
    )
    r = rlbt.check(_bash(_CREATE_CMD))
    assert r is not None
    assert r["decision"] == "block"
    assert "framework/assets/lib/bar.py" in r["reason"]
    assert "framework/assets/hooks/foo.py" not in r["reason"]


def test_allows_when_each_behavior_file_has_its_own_paired_test(monkeypatch) -> None:
    """The positive counterpart: every behavior file paired with its own
    test -> allow, even though no single test file covers the whole diff."""
    monkeypatch.setattr(
        rlbt,
        "_fetch_compare_files",
        _fake_files(
            [
                _behavior_entry(_SUBSTANTIVE_PATCH, filename="framework/assets/hooks/foo.py"),
                _behavior_entry(_SUBSTANTIVE_PATCH, filename="framework/assets/lib/bar.py"),
                _test_entry(_SUBSTANTIVE_PATCH, filename="framework/tests/test_foo.py"),
                _test_entry(_SUBSTANTIVE_PATCH, filename="framework/tests/test_bar.py"),
            ]
        ),
    )
    assert rlbt.check(_bash(_CREATE_CMD)) is None


def test_same_directory_test_change_satisfies_pairing(monkeypatch) -> None:
    """Fallback rule 2 (same directory): repos that co-locate tests beside
    source (unlike this repo's separate-tree layout) still get a meaningful
    pairing check without matching the mapped-test-path naming convention."""
    monkeypatch.setattr(
        rlbt,
        "_fetch_compare_files",
        _fake_files(
            [
                _behavior_entry(_SUBSTANTIVE_PATCH, filename="framework/assets/hooks/foo.py"),
                _test_entry(
                    _SUBSTANTIVE_PATCH, filename="framework/assets/hooks/something_else_test.py"
                ),
            ]
        ),
    )
    assert rlbt.check(_bash(_CREATE_CMD)) is None


def test_mapped_test_path_stem_variants() -> None:
    assert rlbt._mapped_test_basenames("framework/assets/hooks/foo.py") == (
        "test_foo.py",
        "foo_test.py",
    )


def test_behavior_file_paired_helper() -> None:
    behavior = "framework/assets/hooks/foo.py"
    assert rlbt._behavior_file_paired(behavior, ["framework/tests/test_foo.py"])
    assert rlbt._behavior_file_paired(behavior, ["framework/tests/foo_test.py"])
    assert rlbt._behavior_file_paired(behavior, ["framework/tests/conftest.py"])
    assert rlbt._behavior_file_paired(behavior, ["framework/assets/hooks/bar_test.py"])
    assert not rlbt._behavior_file_paired(behavior, ["framework/tests/test_bar.py"])
    assert not rlbt._behavior_file_paired(behavior, [])


# --------------------------------------------------------------- fail-closed posture


def test_blocks_when_repo_unresolvable(tmp_path: Path) -> None:
    # tmp_path is not a git repo, so --repo-less resolution via `git remote get-url
    # origin` fails -> repo stays unresolvable -> fail-closed block.
    r = rlbt.check(_bash("gh pr create --head feat --title x --body y", cwd=str(tmp_path)))
    assert r is not None and r["decision"] == "block"
    assert "fail-closed" in r["reason"].lower()


def test_blocks_when_diff_unverifiable(monkeypatch) -> None:
    monkeypatch.setattr(rlbt, "_fetch_compare_files", lambda repo, base, head: None)
    r = rlbt.check(_bash(_CREATE_CMD))
    assert r is not None and r["decision"] == "block"
    assert "fail-closed" in r["reason"].lower()


# --------------------------------------------------------------- override


def test_override_valid_class_allows(monkeypatch, tmp_path: Path) -> None:
    _write_config(tmp_path, exceptions={"tech-debt-cleanup": "pure refactor, no behavior change"})
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH)]))
    r = rlbt.check(
        _bash(
            _CREATE_CMD,
            cwd=str(tmp_path),
            env={"LOAD_BEARING_TEST_EXCEPTION": "tech-debt-cleanup:pure refactor, no behavior change"},
        )
    )
    assert r is not None
    assert r["decision"] == "allow"
    assert "overridden" in r["systemMessage"].lower()
    _framework_config.clear_cache()


def test_override_unknown_class_blocks(monkeypatch, tmp_path: Path) -> None:
    _write_config(tmp_path, exceptions={"tech-debt-cleanup": "rationale"})
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH)]))
    r = rlbt.check(
        _bash(_CREATE_CMD, cwd=str(tmp_path), env={"LOAD_BEARING_TEST_EXCEPTION": "bogus-class:some reason"})
    )
    assert r is not None and r["decision"] == "block"
    assert "not a valid override" in r["reason"]
    _framework_config.clear_cache()


def test_override_empty_rationale_blocks(monkeypatch, tmp_path: Path) -> None:
    _write_config(tmp_path, exceptions={"tech-debt-cleanup": "rationale"})
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH)]))
    r = rlbt.check(
        _bash(_CREATE_CMD, cwd=str(tmp_path), env={"LOAD_BEARING_TEST_EXCEPTION": "tech-debt-cleanup:"})
    )
    assert r is not None and r["decision"] == "block"
    _framework_config.clear_cache()


def test_override_unrecognized_class_blocks_even_with_seeded_default(
    monkeypatch, tmp_path: Path
) -> None:
    """A repo's own config carries just one custom class (`tech-debt-cleanup`);
    the runtime-seeded `refactor` default (#176) is additive (dict-valued
    config keys merge over `_DEFAULTS`, they don't replace it — see
    `_framework_config._deep_merge`), so BOTH classes are valid, but a THIRD,
    unrecognized class must still block."""
    _write_config(tmp_path, exceptions={"tech-debt-cleanup": "rationale"})
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH)]))
    r = rlbt.check(
        _bash(_CREATE_CMD, cwd=str(tmp_path), env={"LOAD_BEARING_TEST_EXCEPTION": "anything:rationale"})
    )
    assert r is not None and r["decision"] == "block"
    assert "not a valid override" in r["reason"]
    _framework_config.clear_cache()


def test_zero_configured_classes_still_blocks_the_general_mechanism(monkeypatch) -> None:
    """General mechanism check, independent of the shipped seed: if a
    project's own config resolution ever yields ZERO exception classes (e.g.
    a repo that forks the schema without the seed), an override attempt still
    hard-blocks with the "(none configured)" message. #176 pre-seeds one class
    by default; it does not make the underlying "no bypass without a
    configured class" mechanism impossible to reach."""

    class _EmptyExceptionsConfig:
        def get(self, dotted: str, default=None):
            if dotted == "policy.load_bearing_test_exceptions":
                return {}
            return default

    monkeypatch.setattr(rlbt, "config", lambda input_data=None: _EmptyExceptionsConfig())
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH)]))
    r = rlbt.check(
        _bash(_CREATE_CMD, env={"LOAD_BEARING_TEST_EXCEPTION": "anything:rationale"})
    )
    assert r is not None and r["decision"] == "block"
    assert "none configured" in r["reason"].lower()


# --------------------------------------------------------------- seeded refactor exception (S3, #176)


def test_seeded_refactor_class_allows_pure_refactor_with_no_repo_config(
    monkeypatch, tmp_path: Path
) -> None:
    """The S3 (#176) fix, end to end: `policy.load_bearing_test_exceptions`
    ships pre-seeded with a `refactor` class in `_framework_config._DEFAULTS`
    — a repo needs ZERO config of its own for a documented pure-refactor PR
    (new behavior, no test) to have a valid bypass. `tmp_path` has no
    `.claude/framework.config.json` at all, so this exercises the real
    shipped default, not an injected test fixture."""
    _framework_config.clear_cache()
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH)]))
    r = rlbt.check(
        _bash(
            _CREATE_CMD,
            cwd=str(tmp_path),
            env={"LOAD_BEARING_TEST_EXCEPTION": "refactor:extracted _helper() from _bar(), no behavior change"},
        )
    )
    assert r is not None
    assert r["decision"] == "allow"
    assert "overridden" in r["systemMessage"].lower()
    _framework_config.clear_cache()


def test_seeded_refactor_class_would_be_rejected_without_the_seed(monkeypatch) -> None:
    """The load-bearing counterpart of the test above: confirm the SAME
    override attempt is rejected when `load_bearing_test_exceptions` resolves
    to zero classes -- i.e. it is the #176 seed itself making the override
    valid, not something inherent to the `refactor` string or the override
    mechanism in general."""

    class _EmptyExceptionsConfig:
        def get(self, dotted: str, default=None):
            if dotted == "policy.load_bearing_test_exceptions":
                return {}
            return default

    monkeypatch.setattr(rlbt, "config", lambda input_data=None: _EmptyExceptionsConfig())
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH)]))
    r = rlbt.check(
        _bash(
            _CREATE_CMD,
            env={"LOAD_BEARING_TEST_EXCEPTION": "refactor:extracted _helper() from _bar(), no behavior change"},
        )
    )
    assert r is not None
    assert r["decision"] == "block"
    assert "not a valid override" in r["reason"]


def test_seeded_default_matches_schema_default_exactly() -> None:
    """Sync guard: the runtime seed and the schema-documented default for this
    one key must agree (the broader `test_config_schema_sync.py` pins the
    whole `policy` block; this pins the specific seeded value close to the
    hook it governs)."""
    schema = json.loads(
        (_FRAMEWORK_ROOT / "config" / "framework.config.schema.json").read_text(encoding="utf-8")
    )
    schema_default = schema["properties"]["policy"]["properties"]["load_bearing_test_exceptions"][
        "default"
    ]
    assert schema_default == _framework_config._DEFAULTS["policy"]["load_bearing_test_exceptions"]
    assert "refactor" in schema_default


# --------------------------------------------------------------- automatic docs/comment-only exception (#284)


def test_docstring_only_addition_allowed_when_docs_class_configured(
    monkeypatch, tmp_path: Path
) -> None:
    """The #284 fix, end to end: a behavior file whose only added line is a
    docstring is exempted automatically (no LOAD_BEARING_TEST_EXCEPTION env
    var) once the repo's config seeds a `docs` class."""
    _write_config(tmp_path, exceptions={"docs": "auto docs exception"})
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_DOCSTRING_PATCH)]))
    assert rlbt.check(_bash(_CREATE_CMD, cwd=str(tmp_path))) is None
    _framework_config.clear_cache()


def test_multiline_docstring_addition_allowed_when_docs_class_configured(
    monkeypatch, tmp_path: Path
) -> None:
    _write_config(tmp_path, exceptions={"docs": "auto docs exception"})
    monkeypatch.setattr(
        rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_MULTILINE_DOCSTRING_PATCH)])
    )
    assert rlbt.check(_bash(_CREATE_CMD, cwd=str(tmp_path))) is None
    _framework_config.clear_cache()


def test_docstring_only_addition_still_blocked_without_docs_class(monkeypatch) -> None:
    """Opt-in guard: a repo whose config resolution yields exception classes
    WITHOUT `docs` (e.g. a fork of the schema that keeps only `refactor`) does
    NOT get the automatic exemption — the same docstring-only diff still trips
    the gate. Uses a fully mocked config (mirrors
    test_seeded_refactor_class_would_be_rejected_without_the_seed) because a
    REAL config file cannot zero out a class that ships in
    _framework_config._DEFAULTS: dict-valued policy keys merge over the
    runtime defaults rather than replacing them (see `_deep_merge`) — so this
    is the only way to exercise "docs not configured" and pins that the
    exemption really is gated on config, not unconditional."""

    class _RefactorOnlyExceptionsConfig:
        def get(self, dotted: str, default=None):
            if dotted == "policy.load_bearing_test_exceptions":
                return {"refactor": "pure refactor"}
            return default

    monkeypatch.setattr(rlbt, "config", lambda input_data=None: _RefactorOnlyExceptionsConfig())
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_DOCSTRING_PATCH)]))
    r = rlbt.check(_bash(_CREATE_CMD))
    assert r is not None and r["decision"] == "block"


def test_real_behavior_change_still_blocked_under_docs_exception(
    monkeypatch, tmp_path: Path
) -> None:
    """ERR TIGHT: a real behavior change (new executable line, no docstring in
    sight) still trips the gate even with the `docs` class active — the
    automatic exception only ever exempts docs/comment-only diffs."""
    _write_config(tmp_path, exceptions={"docs": "auto docs exception"})
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_SUBSTANTIVE_PATCH)]))
    r = rlbt.check(_bash(_CREATE_CMD, cwd=str(tmp_path)))
    assert r is not None and r["decision"] == "block"
    assert "framework/assets/hooks/foo.py" in r["reason"]
    _framework_config.clear_cache()


def test_docstring_hiding_a_real_statement_still_blocked_under_docs_exception(
    monkeypatch, tmp_path: Path
) -> None:
    """Anti-loophole: a diff that pairs a genuine docstring line with a
    smuggled-in real statement in the SAME file must not read as docs-only —
    the classifier inspects every added line, not just the first/most-visible
    one, so mixing doc content with hidden behavior does not buy a pass."""
    _write_config(tmp_path, exceptions={"docs": "auto docs exception"})
    monkeypatch.setattr(
        rlbt,
        "_fetch_compare_files",
        _fake_files([_behavior_entry(_DOCSTRING_WITH_HIDDEN_CODE_PATCH)]),
    )
    r = rlbt.check(_bash(_CREATE_CMD, cwd=str(tmp_path)))
    assert r is not None and r["decision"] == "block"
    _framework_config.clear_cache()


def test_docs_exception_is_per_file_not_per_diff(monkeypatch, tmp_path: Path) -> None:
    """Two behavior files in one diff: one docs-only, one a real behavior
    change with no paired test. The docs-only file is exempted; the real one
    still blocks — per-file granularity, matching the #174 pairing check it
    sits alongside."""
    _write_config(tmp_path, exceptions={"docs": "auto docs exception"})
    monkeypatch.setattr(
        rlbt,
        "_fetch_compare_files",
        _fake_files(
            [
                _behavior_entry(_DOCSTRING_PATCH, filename="framework/assets/hooks/foo.py"),
                _behavior_entry(_SUBSTANTIVE_PATCH, filename="framework/assets/lib/bar.py"),
            ]
        ),
    )
    r = rlbt.check(_bash(_CREATE_CMD, cwd=str(tmp_path)))
    assert r is not None and r["decision"] == "block"
    assert "framework/assets/lib/bar.py" in r["reason"]
    assert "framework/assets/hooks/foo.py" not in r["reason"]
    _framework_config.clear_cache()


def test_docstring_only_addition_allowed_with_no_repo_config_at_all(
    monkeypatch, tmp_path: Path
) -> None:
    """The #284 seed end to end, exercising the REAL shipped default (not an
    injected fixture): `tmp_path` has no `.claude/framework.config.json`, so
    `docs` is only present because it ships in `_framework_config._DEFAULTS`
    alongside `refactor` — mirrors
    test_seeded_refactor_class_allows_pure_refactor_with_no_repo_config."""
    _framework_config.clear_cache()
    monkeypatch.setattr(rlbt, "_fetch_compare_files", _fake_files([_behavior_entry(_DOCSTRING_PATCH)]))
    assert rlbt.check(_bash(_CREATE_CMD, cwd=str(tmp_path))) is None
    _framework_config.clear_cache()


def test_docs_class_seeded_in_runtime_defaults() -> None:
    """The #284 seed itself: `docs` ships in the runtime default map alongside
    `refactor` (#176), so a repo needs zero config of its own for the manual
    `LOAD_BEARING_TEST_EXCEPTION=docs:...` override to be valid, matching the
    pattern already established for `refactor` (see
    test_seeded_refactor_class_allows_pure_refactor_with_no_repo_config)."""
    assert "docs" in _framework_config._DEFAULTS["policy"]["load_bearing_test_exceptions"]


def test_patch_is_docs_only() -> None:
    assert rlbt._patch_is_docs_only(_DOCSTRING_PATCH) is True
    assert rlbt._patch_is_docs_only(_MULTILINE_DOCSTRING_PATCH) is True
    # A comment-only added line is genuinely docs/comment content...
    assert rlbt._patch_is_docs_only("@@ -1,1 +1,2 @@\n line1\n+# just a comment\n") is True
    # ...but an added blank-only line has NOTHING to exempt (no docs/comment
    # content was seen at all), so it does not count as "docs only" either.
    assert rlbt._patch_is_docs_only("@@ -1,1 +1,2 @@\n line1\n+   \n") is False
    assert rlbt._patch_is_docs_only(_SUBSTANTIVE_PATCH) is False
    assert rlbt._patch_is_docs_only(_DOCSTRING_WITH_HIDDEN_CODE_PATCH) is False
    assert rlbt._patch_is_docs_only(None) is False
    assert rlbt._patch_is_docs_only("") is False


# --------------------------------------------------------------- pure helpers


def test_is_behavior_path() -> None:
    assert rlbt._is_behavior_path("framework/assets/hooks/foo.py")
    assert rlbt._is_behavior_path("python/src/real_team/cli.py")
    assert not rlbt._is_behavior_path("framework/tests/test_foo.py")
    assert not rlbt._is_behavior_path("framework/assets/hooks/foo.md")
    assert not rlbt._is_behavior_path("docs/README.md")
    assert not rlbt._is_behavior_path("framework/assets/hooks/__init__.py")


def test_is_test_path() -> None:
    assert rlbt._is_test_path("framework/tests/test_foo.py")
    assert rlbt._is_test_path("python/tests/test_cli.py")
    assert rlbt._is_test_path("framework/tests/conftest.py")
    assert rlbt._is_test_path("some/dir/foo_test.py")
    assert not rlbt._is_test_path("framework/assets/hooks/foo.py")


def test_added_substantive_lines() -> None:
    assert rlbt._added_substantive_lines(_SUBSTANTIVE_PATCH) == [
        "def new_behavior():",
        "    return 42",
    ]
    assert rlbt._added_substantive_lines(_TRIVIAL_PATCH) == []
    assert rlbt._added_substantive_lines(None) == []
    assert rlbt._added_substantive_lines("") == []
