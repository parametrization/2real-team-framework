"""Hermetic tests for the #153 real-repo provisioner (clone-at-pinned-SHA + --include-real).

Everything is proven against a throwaway LOCAL git repo built in ``tmp_path`` — no network, no
real noorinalabs/botfarm fixtures (those runs are #101/#109). We assert the load-bearing safety
property (the live source is byte-identical before/after a provision), that a dirty source still
clones clean at the pin, that ``--include-real`` actually executes the B10/B11 real-bucket path
(not ``NotImplementedError``), that a genuinely unresolvable fixture degrades to a skip, and that
teardown leaves zero residue on both the scratch clone and the source. Stdlib + pytest only.
"""

from __future__ import annotations

import subprocess
import sys
import warnings
from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _FRAMEWORK_ROOT.parent
sys.path.insert(0, str(_REPO_ROOT))  # make `framework.harness` importable (namespace package)

from framework.harness import real_provision  # noqa: E402
from framework.harness.real_provision import (  # noqa: E402
    MissingFixtureError,
    RealChildSpec,
    RealFixtureSpec,
    provision_real,
    resolve_pin,
    source_fingerprint,
)
from framework.harness.runner import run_matrix  # noqa: E402


# --------------------------------------------------------------- synthetic git fixtures


def _git(cwd: Path, *args: str) -> str:
    cp = subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)
    return cp.stdout


def _commit(cwd: Path, msg: str) -> str:
    subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=Fixture", "-c", "user.email=fx@example.com",
         "commit", "-q", "-m", msg],
        check=True, capture_output=True,
    )
    return _git(cwd, "rev-parse", "HEAD").strip()


def _make_repo(path: Path, files: dict[str, str]) -> str:
    """Build a tiny real git repo on branch ``main``; return the HEAD sha."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    for rel, content in files.items():
        fp = path / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
    _git(path, "add", "-A")
    sha = _commit(path, "init")
    _git(path, "branch", "-M", "main")
    return sha


def _existing_repo(path: Path) -> str:
    """A foreign existing project (no .claude) — the B11 standalone clone source."""
    return _make_repo(path, {"src/main.py": "print('app')\n", "README.md": "# real project\n"})


# --------------------------------------------------------------- pin resolution


def test_resolve_pin_explicit_is_verbatim(tmp_path: Path) -> None:
    assert resolve_pin("ignored", pin="deadbeef") == "deadbeef"  # no ls-remote when pinned


def test_resolve_pin_reads_remote_main_not_local_checkout(tmp_path: Path) -> None:
    src = tmp_path / "src"
    main_sha = _existing_repo(src)
    # move the local checkout onto a feature branch with a NEW commit — main must NOT follow it
    _git(src, "checkout", "-q", "-b", "feature/wip")
    (src / "src" / "extra.py").write_text("x = 1\n", encoding="utf-8")
    _git(src, "add", "-A")
    feature_sha = _commit(src, "wip on a feature branch")

    resolved = resolve_pin(str(src), "refs/heads/main")
    assert resolved == main_sha        # the remote ref, not the checked-out feature branch
    assert resolved != feature_sha


def test_resolve_pin_unresolvable_source_raises_missing(tmp_path: Path) -> None:
    with pytest.raises(MissingFixtureError):
        resolve_pin(str(tmp_path / "nope"), "refs/heads/main")


# --------------------------------------------------------------- clone-at-pin


def test_clone_at_pin_checks_out_the_pinned_commit(tmp_path: Path) -> None:
    src = tmp_path / "src"
    first = _existing_repo(src)
    # a second commit that adds a file — pinning to `first` must NOT include it
    (src / "later.py").write_text("y = 2\n", encoding="utf-8")
    _git(src, "add", "-A")
    second = _commit(src, "second")
    assert first != second

    dest = tmp_path / "clone"
    real_provision.clone_at(str(src), first, dest)

    assert (dest / "src" / "main.py").is_file()
    assert not (dest / "later.py").exists()                 # pinned before the 2nd commit
    assert _git(dest, "rev-parse", "HEAD").strip() == first  # detached at the pin


def test_dirty_source_clones_clean_at_pin(tmp_path: Path) -> None:
    src = tmp_path / "src"
    pin = _existing_repo(src)
    # dirty the live source: an uncommitted edit + an untracked file
    (src / "src" / "main.py").write_text("print('LOCAL EDIT')\n", encoding="utf-8")
    (src / "scratch.tmp").write_text("junk\n", encoding="utf-8")
    assert _git(src, "status", "--porcelain").strip()  # source IS dirty

    dest = tmp_path / "clone"
    real_provision.clone_at(str(src), pin, dest)

    assert _git(dest, "status", "--porcelain").strip() == ""       # clone is clean
    assert (dest / "src" / "main.py").read_text() == "print('app')\n"  # committed content, not dirt
    assert not (dest / "scratch.tmp").exists()                     # untracked dirt not carried


# --------------------------------------------------------------- source-unchanged invariant


def test_provision_leaves_source_byte_identical(tmp_path: Path) -> None:
    src = tmp_path / "src"
    _existing_repo(src)
    # put the source on a feature branch AND make it dirty — the exact real-world condition
    _git(src, "checkout", "-q", "-b", "W.Mwangi/0322-spec")
    (src / "dirty.py").write_text("d = 1\n", encoding="utf-8")

    before = source_fingerprint(str(src))
    spec = RealFixtureSpec(bucket="B11", source=str(src), ref="refs/heads/main")
    ctx = provision_real(spec, tmp_path / "wd")
    after = source_fingerprint(str(src))

    assert before == after                       # HEAD + porcelain byte-identical (the invariant)
    assert ctx["extra"]["source_unchanged"] is True


def test_source_fingerprint_none_for_nonlocal() -> None:
    assert source_fingerprint("git@github.com:noorinalabs/noorinalabs-main.git") is None


def test_source_mutation_mid_provision_raises_source_mutated(tmp_path: Path, monkeypatch) -> None:
    """Negative-path guard for the load-bearing invariant: if the source is mutated BETWEEN the
    before/after fingerprints, provision_real MUST raise SourceMutatedError. Injects a real
    concurrent-writer mutation mid-provision (a stand-in for another session dirtying the live
    tree) by wrapping clone_at. This is NOT a tautology — with the invariant check removed,
    provision_real would return normally and this test would FAIL."""
    src = tmp_path / "src"
    _existing_repo(src)
    before = source_fingerprint(str(src))

    real_clone = real_provision.clone_at

    def mutating_clone(source: str, sha: str, dest: Path) -> None:
        # another session writes into the live source AFTER the `before` fingerprint is taken
        (Path(source) / "intruder.txt").write_text("written mid-provision\n", encoding="utf-8")
        real_clone(source, sha, dest)  # the clone itself still succeeds

    monkeypatch.setattr(real_provision, "clone_at", mutating_clone)

    spec = RealFixtureSpec(bucket="B11", source=str(src), ref="refs/heads/main")
    with pytest.raises(real_provision.SourceMutatedError) as ei:
        provision_real(spec, tmp_path / "wd")

    # the raise is driven by the after-fingerprint mismatch, and names the mutated source
    assert str(src) in str(ei.value)
    after = source_fingerprint(str(src))
    assert after != before and after is not None  # the source genuinely changed (guard is real)


# --------------------------------------------------------------- --include-real wiring


def _b11_opts(source: Path, *, pin: str | None = None) -> dict:
    return {
        "buckets": ["B11"], "installers": ["bootstrap"], "dogfood": False,
        "include_real": True,
        "real_fixtures": {"B11": RealFixtureSpec(
            bucket="B11", source=str(source), pin=pin, ref="refs/heads/main")},
    }


def test_include_real_executes_b11_real_path_all_green(tmp_path: Path) -> None:
    src = tmp_path / "botfarm-synthetic"
    _existing_repo(src)
    before = source_fingerprint(str(src))

    env = run_matrix(_b11_opts(src))
    b11 = [r for r in env.records if r.bucket == "B11"]

    assert b11, "B11 produced no records — real path did not run"
    # the real path RAN (not the pre-#153 stub skip): install_exit_status graded, not observed.stub
    exit_rec = next(r for r in b11 if r.metric == "install_exit_status")
    assert exit_rec.passed is True
    assert not (exit_rec.observed or {}).get("stub")
    graded = [r for r in b11 if r.passed is not None and r.kind in ("pass_fail", "scored")]
    assert graded and all(r.passed for r in graded), \
        f"real B11 failures: {[r.record_id for r in graded if not r.passed]}"
    # teardown residue metric proves the symmetric-diff is empty for a real bucket
    residue = next(r for r in b11 if r.metric == "teardown_residue_zero")
    assert residue.passed is True
    # the live source is byte-identical after the whole matrix run
    assert source_fingerprint(str(src)) == before


def test_include_real_with_explicit_pin(tmp_path: Path) -> None:
    src = tmp_path / "src"
    pin = _existing_repo(src)
    (src / "drift.py").write_text("z = 3\n", encoding="utf-8")  # advance main past the pin
    _git(src, "add", "-A")
    _commit(src, "drift")

    env = run_matrix(_b11_opts(src, pin=pin))
    exit_rec = next(r for r in env.records if r.bucket == "B11" and r.metric == "install_exit_status")
    assert exit_rec.passed is True


def test_missing_fixture_degrades_to_skip_not_crash(tmp_path: Path) -> None:
    opts = {
        "buckets": ["B11"], "installers": ["bootstrap"], "dogfood": False, "include_real": True,
        "real_fixtures": {"B11": RealFixtureSpec(bucket="B11", source=str(tmp_path / "absent"))},
    }
    env = run_matrix(opts)  # must not raise
    b11 = [r for r in env.records if r.bucket == "B11"]
    assert len(b11) == 1
    assert b11[0].passed is None
    assert (b11[0].expected or {}).get("stub") is True  # runner's stub-skip record
    assert "ls-remote" in (b11[0].observed or {}).get("reason", "")


def test_scratch_clone_fully_removed_after_run(tmp_path: Path) -> None:
    src = tmp_path / "src"
    _existing_repo(src)
    scratch = tmp_path / "scratch"
    opts = _b11_opts(src)
    opts.update({"scratch": str(scratch), "cleanup_scratch": True})
    run_matrix(opts)
    # explicit scratch is preserved by run_matrix, but every per-cell workdir clone is gone
    leftovers = [p for p in scratch.glob("harness-B11-*")]
    assert leftovers == [], f"scratch clone residue: {leftovers}"


# --------------------------------------------------------------- B10 meta (parent + children)


def test_meta_provision_clones_parent_and_children(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    _make_repo(parent, {"pyproject.toml": "[project]\nname='root'\n"})
    api = tmp_path / "api-src"
    _make_repo(api, {"pyproject.toml": "[project]\nname='api'\n"})
    web = tmp_path / "web-src"
    _make_repo(web, {"index.html": "<h1>web</h1>\n"})

    spec = RealFixtureSpec(
        bucket="B10", source=str(parent), model="meta-and-children",
        children=(RealChildSpec("api", str(api), flavor="product"),
                  RealChildSpec("web", str(web), flavor="infra")),
    )
    wd = tmp_path / "wd"
    ctx = provision_real(spec, wd)

    assert (wd / "pyproject.toml").is_file()          # parent clone
    assert (wd / "api" / ".git").is_dir()             # child clones, independently git'd
    assert (wd / "web" / ".git").is_dir()
    assert (wd / "install.meta.yaml").is_file()
    yaml = (wd / "install.meta.yaml").read_text()
    assert "path: api" in yaml and "path: web" in yaml and "flavor: infra" in yaml
    labels = {c["path"]: c["flavor"] for c in ctx["child"]["children"]}
    assert labels == {"api": "product", "web": "infra"}


def test_meta_zero_children_warns(tmp_path: Path) -> None:
    """#155 item 4: a ``meta-and-children`` spec that resolves to ZERO children is a degenerate
    meta install — ``provision_real`` must surface it with a warning (not silently degrade). This
    is a real guard: with the ``warnings.warn`` removed, ``pytest.warns`` finds no match and FAILS.
    """
    parent = tmp_path / "parent"
    _make_repo(parent, {"pyproject.toml": "[project]\nname='root'\n"})
    spec = RealFixtureSpec(bucket="B10", source=str(parent), model="meta-and-children", children=())

    with pytest.warns(UserWarning, match=r"meta-and-children with zero children"):
        ctx = provision_real(spec, tmp_path / "wd")

    # the degenerate install still succeeds (a childless meta is valid, just trivial)
    assert (parent / "pyproject.toml").is_file() or (tmp_path / "wd" / "pyproject.toml").is_file()
    assert ctx["child"]["children"] == []  # no children provisioned
    assert ctx["extra"]["source_unchanged"] is True


def test_meta_with_children_does_not_warn(tmp_path: Path) -> None:
    """Symmetric control: a populated ``meta-and-children`` spec must NOT emit the zero-children
    warning — proves the guard is scoped to the degenerate case, not every meta provision."""
    parent = tmp_path / "parent"
    _make_repo(parent, {"pyproject.toml": "[project]\nname='root'\n"})
    api = tmp_path / "api-src"
    _make_repo(api, {"pyproject.toml": "[project]\nname='api'\n"})
    spec = RealFixtureSpec(
        bucket="B10", source=str(parent), model="meta-and-children",
        children=(RealChildSpec("api", str(api), flavor="product"),),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning would raise → test fails if the guard misfires
        ctx = provision_real(spec, tmp_path / "wd")
    assert [c["path"] for c in ctx["child"]["children"]] == ["api"]


def test_meta_zero_children_strict_guard_raises(tmp_path: Path) -> None:
    """#244: the zero-children case has a STRONGER, opt-in guard. With
    ``opts['real_require_children']`` set, a degenerate zero-children ``meta-and-children`` provision
    must RAISE ``MissingFixtureError`` (runner degrades to a skip) instead of shipping the empty meta
    install — a real run that must have children fails visibly rather than silently provisioning
    nothing. Load-bearing: remove the ``real_require_children`` branch in ``_guard_zero_children`` and
    this provision no longer raises (it only warns), so ``pytest.raises`` finds nothing and FAILS."""
    parent = tmp_path / "parent"
    _make_repo(parent, {"pyproject.toml": "[project]\nname='root'\n"})
    spec = RealFixtureSpec(bucket="B10", source=str(parent), model="meta-and-children", children=())

    with pytest.raises(MissingFixtureError, match=r"zero children"):
        provision_real(spec, tmp_path / "wd", opts={"real_require_children": True})


def test_meta_zero_children_strict_guard_default_off(tmp_path: Path) -> None:
    """Control for #244: WITHOUT ``real_require_children`` the guard stays a warn-and-proceed (the
    legitimate bare ``--include-real`` smoke-test flow), so the hard guard is genuinely opt-in and
    does not change the default behavior."""
    parent = tmp_path / "parent"
    _make_repo(parent, {"pyproject.toml": "[project]\nname='root'\n"})
    spec = RealFixtureSpec(bucket="B10", source=str(parent), model="meta-and-children", children=())
    with pytest.warns(UserWarning, match=r"zero children"):
        ctx = provision_real(spec, tmp_path / "wd", opts={"real_require_children": False})
    assert ctx["child"]["children"] == []  # still a (trivial) degenerate install, not a raise


def test_include_real_executes_b10_meta_path_all_green(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    _make_repo(parent, {"pyproject.toml": "[project]\nname='root'\n"})
    api = tmp_path / "api-src"
    _make_repo(api, {"pyproject.toml": "[project]\nname='api'\n"})
    web = tmp_path / "web-src"
    _make_repo(web, {"pyproject.toml": "[project]\nname='web'\n"})
    sources = [parent, api, web]
    before = [source_fingerprint(str(p)) for p in sources]

    opts = {
        "buckets": ["B10"], "installers": ["bootstrap"], "dogfood": False, "include_real": True,
        "real_fixtures": {"B10": RealFixtureSpec(
            bucket="B10", source=str(parent), model="meta-and-children",
            children=(RealChildSpec("api", str(api), flavor="product"),
                      RealChildSpec("web", str(web), flavor="infra")))},
    }
    env = run_matrix(opts)
    b10 = [r for r in env.records if r.bucket == "B10"]
    assert b10, "B10 produced no records"
    graded = [r for r in b10 if r.passed is not None and r.kind in ("pass_fail", "scored")]
    assert graded and all(r.passed for r in graded), \
        f"real B10 failures: {[r.record_id for r in graded if not r.passed]}"
    assert [source_fingerprint(str(p)) for p in sources] == before  # every source untouched


# --------------------------------------------------------------- registry as data


def test_registry_default_and_sidecar_override(tmp_path: Path) -> None:
    default = real_provision.real_registry({})
    assert set(default) == {"B10", "B11"}
    assert default["B10"].model == "meta-and-children"
    assert default["B11"].pin is None  # resolve live main at run time by default

    sidecar = tmp_path / "real.json"
    sidecar.write_text(
        '{"B11": {"source": "/x", "pin": "abc123", "ref": "refs/heads/release"}}',
        encoding="utf-8",
    )
    reg = real_provision.real_registry({"real_config": str(sidecar)})
    assert reg["B11"].source == "/x" and reg["B11"].pin == "abc123"
    assert reg["B11"].ref == "refs/heads/release"
    assert reg["B10"].model == "meta-and-children"  # untouched default survives


def test_new_bucket_partial_patch_without_source_friendly_error(tmp_path: Path) -> None:
    """#243: a ``--real-config`` / ``real_fixtures`` partial patch that CREATES a new bucket (one not
    in the defaults) with no ``source`` key must raise a friendly ``MissingFixtureError`` NAMING the
    bucket and asking for a ``source`` — not the bare ``KeyError('source')`` the unconditional
    ``from_dict`` used to raise. Load-bearing: drop the ``'source' not in override`` guard in
    ``_apply`` and the call raises a bare ``KeyError`` (not ``MissingFixtureError``), so this fails."""
    # (a) via the sidecar JSON
    sidecar = tmp_path / "real.json"
    sidecar.write_text('{"BZ9": {"pin": "cafef00d", "ref": "refs/heads/main"}}', encoding="utf-8")
    with pytest.raises(MissingFixtureError, match=r"BZ9.*source"):
        real_provision.real_registry({"real_config": str(sidecar)})

    # (b) via real_fixtures as a dict
    with pytest.raises(MissingFixtureError, match=r"BZ9.*source"):
        real_provision.real_registry({"real_fixtures": {"BZ9": {"pin": "beadfeed"}}})

    # a new bucket that DOES carry a source still works (guard is scoped to the missing-source case)
    ok = real_provision.real_registry({"real_fixtures": {"BZ9": {"source": "/some/repo"}}})
    assert ok["BZ9"].source == "/some/repo"


# --------------------------------------------------------------- #155 item 1: partial-clone invariant


def test_partial_clone_failure_still_runs_after_fingerprint(tmp_path: Path, monkeypatch) -> None:
    """#155 item 1: when a clone raises PARTWAY through a multi-clone (a child unreachable after
    the parent already cloned), the read-only after-fingerprint assertion must STILL run. Here the
    parent's source is mutated right after it clones, so the invariant is violated ON the partial
    failure — ``provision_real`` must raise ``SourceMutatedError`` (proving the after-check ran
    despite the child failure), NOT the child's ``MissingFixtureError``. With the pre-#155 layout
    (after-check skipped once a clone raised) this would surface ``MissingFixtureError`` and FAIL."""
    parent = tmp_path / "parent"
    _make_repo(parent, {"pyproject.toml": "[project]\nname='root'\n"})

    real_clone = real_provision.clone_at

    def clone_then_mutate_parent(source: str, sha: str, dest: Path) -> None:
        real_clone(source, sha, dest)
        if Path(source) == parent:  # a concurrent writer dirties the parent right after it clones
            (parent / "intruder.txt").write_text("mid-provision\n", encoding="utf-8")

    monkeypatch.setattr(real_provision, "clone_at", clone_then_mutate_parent)

    spec = RealFixtureSpec(
        bucket="B10", source=str(parent), model="meta-and-children",
        children=(RealChildSpec("api", str(tmp_path / "absent-child"), flavor="product"),),
    )
    with pytest.raises(real_provision.SourceMutatedError):
        provision_real(spec, tmp_path / "wd")


def test_partial_clone_failure_preserves_error_and_checks_invariant(
        tmp_path: Path, monkeypatch) -> None:
    """Companion to the above: when the source is NOT mutated, a mid-sequence clone failure still
    runs the after-fingerprint check (call-count proof) but, finding the source unchanged, lets the
    ORIGINAL ``MissingFixtureError`` propagate — the invariant check must not mask genuine failures."""
    parent = tmp_path / "parent"
    _make_repo(parent, {"pyproject.toml": "[project]\nname='root'\n"})

    calls = {"n": 0}
    real_fp = real_provision.source_fingerprint

    def counting_fp(source: str):
        calls["n"] += 1
        return real_fp(source)

    monkeypatch.setattr(real_provision, "source_fingerprint", counting_fp)

    spec = RealFixtureSpec(
        bucket="B10", source=str(parent), model="meta-and-children",
        children=(RealChildSpec("api", str(tmp_path / "absent-child"), flavor="product"),),
    )
    with pytest.raises(MissingFixtureError):
        provision_real(spec, tmp_path / "wd")
    # before(parent+child) AND after(parent+child) both fingerprinted → the after-check ran
    assert calls["n"] == 4


# --------------------------------------------------------------- #155 item 2: portable defaults


def test_default_fixtures_carry_no_hardcoded_home_paths() -> None:
    """#155 item 2: neither the provisioner source nor the example sidecar may bake in a
    machine-specific absolute-home path — real runs supply sources via ``--real-config``."""
    mod_src = Path(real_provision.__file__).read_text(encoding="utf-8")
    assert "/home/" not in mod_src
    example = _FRAMEWORK_ROOT / "tests" / "install_quality" / "real-config.botfarm.example.json"
    assert "/home/" not in example.read_text(encoding="utf-8")


def test_default_sources_are_portable_and_env_overridable(monkeypatch) -> None:
    """The DEFAULT specs DISCOVER their sources (portable), honoring ``REAL_FIXTURE_BASE``, rather
    than embedding this dev box's absolute paths."""
    monkeypatch.setenv("REAL_FIXTURE_BASE", "/somewhere/else")
    assert real_provision._default_source("botfarm_inc") == "/somewhere/else/botfarm_inc"
    monkeypatch.delenv("REAL_FIXTURE_BASE", raising=False)
    derived = real_provision._default_source("botfarm_inc")
    assert Path(derived).is_absolute() and derived.endswith("/botfarm_inc")
    assert real_provision.DEFAULT_REAL_FIXTURES["B11"].source.endswith("/botfarm_inc")
    assert real_provision.DEFAULT_REAL_FIXTURES["B10"].source.endswith("/noorinalabs-main")


# --------------------------------------------------------------- #155 item 3: merge, not replace


def test_override_pin_merges_preserving_children(tmp_path: Path, monkeypatch) -> None:
    """#155 item 3: overriding only ``pin`` (via ``--real-config`` or ``real_fixtures``) must
    PRESERVE the bucket's existing ``children``/``source``/etc — a merge, not a wholesale replace
    that resets ``children`` to ``()``. A FULL ``RealFixtureSpec`` value stays a whole-spec replace."""
    seeded = RealFixtureSpec(
        bucket="B10", source="/seed/parent", model="meta-and-children",
        children=(RealChildSpec("api", "/seed/api", flavor="product"),
                  RealChildSpec("web", "/seed/web", flavor="infra")))
    monkeypatch.setitem(real_provision.DEFAULT_REAL_FIXTURES, "B10", seeded)

    # (a) partial patch via the sidecar JSON: only pin
    sidecar = tmp_path / "real.json"
    sidecar.write_text('{"B10": {"pin": "cafef00d"}}', encoding="utf-8")
    reg = real_provision.real_registry({"real_config": str(sidecar)})
    assert reg["B10"].pin == "cafef00d"                            # override applied
    assert [c.path for c in reg["B10"].children] == ["api", "web"]  # children PRESERVED (merge)
    assert reg["B10"].source == "/seed/parent"                     # untouched keys preserved
    assert reg["B10"].model == "meta-and-children"

    # (b) partial patch via real_fixtures as a dict: only pin
    reg2 = real_provision.real_registry({"real_fixtures": {"B10": {"pin": "beadfeed"}}})
    assert reg2["B10"].pin == "beadfeed"
    assert [c.path for c in reg2["B10"].children] == ["api", "web"]

    # (c) a FULL RealFixtureSpec value is still a wholesale replace (back-compat)
    reg3 = real_provision.real_registry(
        {"real_fixtures": {"B10": RealFixtureSpec(bucket="B10", source="/new")}})
    assert reg3["B10"].children == ()                              # explicit full spec resets children


# --------------------------------------------------------------- #155 item 5: nested child paths


def test_nested_child_path_clones_via_mkdir_parents(tmp_path: Path) -> None:
    """#155 item 5: a multi-level child path (``packages/api``) must clone — its leading dirs are
    created with ``mkdir(parents=True)`` — instead of degrading to a skip."""
    parent = tmp_path / "parent"
    _make_repo(parent, {"pyproject.toml": "[project]\nname='root'\n"})
    api = tmp_path / "api-src"
    _make_repo(api, {"pyproject.toml": "[project]\nname='api'\n"})
    spec = RealFixtureSpec(
        bucket="B10", source=str(parent), model="meta-and-children",
        children=(RealChildSpec("packages/api", str(api), flavor="product"),))
    wd = tmp_path / "wd"
    ctx = provision_real(spec, wd)
    assert (wd / "packages" / "api" / ".git").is_dir()             # nested child cloned
    assert [c["path"] for c in ctx["child"]["children"]] == ["packages/api"]


def test_clone_at_clean_error_when_parent_uncreatable(tmp_path: Path) -> None:
    """When a child's leading path is genuinely uncreatable (a path element is a file), ``clone_at``
    raises a clean ``MissingFixtureError`` (→ runner skip) rather than a cryptic git failure."""
    src = tmp_path / "src"
    _existing_repo(src)
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a dir\n", encoding="utf-8")  # blocks mkdir(parents=True)
    with pytest.raises(MissingFixtureError) as ei:
        real_provision.clone_at(str(src), "HEAD", blocker / "child" / "clone")
    assert "parent directory" in str(ei.value)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
