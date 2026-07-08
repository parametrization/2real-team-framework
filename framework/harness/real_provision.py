"""Real-repo provisioner (#153): clone a live source at a pinned SHA into scratch, read-only.

B10 (``meta-real-world``) and B11 (``standalone-real-world``) run the harness against REAL
checkouts instead of synthesized fixtures. The live source trees are under concurrent work by
other sessions, so provisioning MUST be read-only w.r.t. the source:

  * ``git clone --no-local <source> <scratch>`` forces a full object copy — never a hardlink
    into the source ``.git`` (the plain local-clone default) and never a worktree/copy of the
    live working tree. Uncommitted dirt in the source is therefore never carried into the clone;
    a locally-dirty source still clones clean at the pinned commit.
  * The pin is resolved from the source's default branch via ``git ls-remote`` at run time (an
    explicit SHA may be pinned instead) — never trusted from whatever branch happens to be
    checked out locally, since several sources sit on in-progress feature branches.
  * The source's ``HEAD`` + ``git status --porcelain`` are fingerprinted before and after the
    provision and asserted byte-identical — the load-bearing safety property.

Which source/pin each bucket uses is DATA (a ``RealFixtureSpec`` registry), overridable via a
sidecar JSON (``--real-config``) or ``opts['real_fixtures']`` (tests), so the mechanism is
proven hermetically against a throwaway local git repo — the real multi-GB noorinalabs/botfarm
runs are #101 / #109 and are never cloned in CI. Stdlib only.
"""

from __future__ import annotations

import json
import os
import subprocess
import warnings
from dataclasses import dataclass, replace
from pathlib import Path


class MissingFixtureError(NotImplementedError):
    """A real fixture is genuinely unresolvable (no registry entry, or source unreachable).

    Subclasses ``NotImplementedError`` so the runner's existing stub-skip path
    (``runner.run_cell``) degrades it to a *skipped* record instead of a crash — keeping CI and
    machines that lack the local checkouts green, exactly as the pre-#153 stub did.
    """


class SourceMutatedError(RuntimeError):
    """The source repo's HEAD/porcelain changed across a provision — read-only invariant broken.

    A plain ``Exception`` (NOT a skip): with ``git clone --no-local`` this can only happen if
    something outside the harness wrote to the live source mid-provision, and the runner isolates
    it to a single errored cell rather than trusting a moved-under-us source.
    """


# --------------------------------------------------------------------- spec model


@dataclass(frozen=True)
class RealChildSpec:
    """A nested, independently-``git``'d child of a meta parent (a gitignored sibling dir)."""

    path: str            # relative dir under the parent workdir the child is cloned into
    source: str          # local path or git remote URL
    pin: str | None = None
    ref: str = "refs/heads/main"
    flavor: str = "product"

    def to_dict(self) -> dict:
        return {"path": self.path, "source": self.source, "pin": self.pin,
                "ref": self.ref, "flavor": self.flavor}

    @classmethod
    def from_dict(cls, d: dict) -> RealChildSpec:
        return cls(path=d["path"], source=d["source"], pin=d.get("pin"),
                   ref=d.get("ref", "refs/heads/main"), flavor=d.get("flavor", "product"))


@dataclass(frozen=True)
class RealFixtureSpec:
    """Data-only description of a real clone source for a bucket (inspectable/diffable, #104 §6).

    ``pin=None`` means "resolve ``ref`` from the source at run time" (the AC default — never trust
    the locally checked-out branch). An explicit ``pin`` SHA is honored verbatim (reproducible
    real runs; #101/#109 pass one via ``--real-config``).
    """

    bucket: str
    source: str
    pin: str | None = None
    ref: str = "refs/heads/main"
    model: str = "single-repo"                 # "single-repo" | "meta-and-children"
    children: tuple[RealChildSpec, ...] = ()
    require_children: bool = False             # #251: per-bucket opt-in zero-children hard guard

    def to_dict(self) -> dict:
        return {"bucket": self.bucket, "source": self.source, "pin": self.pin,
                "ref": self.ref, "model": self.model,
                "children": [c.to_dict() for c in self.children],
                "require_children": self.require_children}

    @classmethod
    def from_dict(cls, bucket: str, d: dict) -> RealFixtureSpec:
        return cls(
            bucket=bucket, source=d["source"], pin=d.get("pin"),
            ref=d.get("ref", "refs/heads/main"), model=d.get("model", "single-repo"),
            children=tuple(RealChildSpec.from_dict(c) for c in d.get("children", ())),
            require_children=bool(d.get("require_children", False)),
        )

    def merge(self, d: dict) -> RealFixtureSpec:
        """Return a copy with ONLY the keys present in ``d`` overridden (#155 item 3).

        A ``--real-config`` / ``real_fixtures`` override is a partial patch, not a wholesale
        replacement: overriding just ``pin`` must preserve the existing ``children`` (and
        ``source``/``ref``/``model``) rather than silently resetting them to their empty defaults.
        ``children`` is only replaced when the override explicitly carries a ``children`` key.
        """
        children = self.children
        if "children" in d:
            children = tuple(RealChildSpec.from_dict(c) for c in d["children"])
        require_children = self.require_children
        if "require_children" in d:
            require_children = bool(d["require_children"])
        return replace(
            self,
            source=d.get("source", self.source),
            pin=d.get("pin", self.pin),
            ref=d.get("ref", self.ref),
            model=d.get("model", self.model),
            children=children,
            require_children=require_children,
        )


#: Base directory the DEFAULT specs discover their sibling checkouts under. Env-overridable
#: (``REAL_FIXTURE_BASE``); otherwise derived from THIS file's location — the real checkouts sit
#: as siblings of the framework repo (``<parent-of-repo-root>/<name>``). This keeps the defaults
#: portable: no machine-specific absolute-home literal is baked into version control (#155 item 2).
#: They remain a best-effort LOCAL-ONLY convenience — real runs MUST supply sources via
#: ``--real-config`` (#101/#109); a dev box that lacks the sibling checkout degrades to a skip.
def _default_source(name: str) -> str:
    base = os.environ.get("REAL_FIXTURE_BASE")
    root = Path(base) if base else Path(__file__).resolve().parents[3]
    return str(root / name)


#: Documented current HEADs (from #150 discovery), kept for reference/reproducibility only —
#: the DEFAULT specs resolve the LIVE ``refs/heads/main`` at run time (``pin=None``) so a dev
#: run never trusts a locally checked-out feature branch. #101 supplies noorinalabs' in-scope
#: nested children (and #101/#109 an explicit pin) via ``--real-config``.
DEFAULT_REAL_FIXTURES: dict[str, RealFixtureSpec] = {
    # B11 standalone-real-world -> botfarm_inc (HEAD a4e622dde79436ee8230de662020c3f3f0ee7e9d)
    "B11": RealFixtureSpec(
        bucket="B11", source=_default_source("botfarm_inc"),
        pin=None, ref="refs/heads/main", model="single-repo",
    ),
    # B10 meta-real-world -> noorinalabs-main (HEAD 582416e85413f52b2972ae8def36a37eb486f818)
    "B10": RealFixtureSpec(
        bucket="B10", source=_default_source("noorinalabs-main"),
        pin=None, ref="refs/heads/main", model="meta-and-children", children=(),
    ),
}


# --------------------------------------------------------------------- git plumbing


def _git(cwd: Path | None, *args: str) -> str:
    cmd = ["git", *(["-C", str(cwd)] if cwd else []), *args]
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.returncode != 0:
        raise subprocess.CalledProcessError(cp.returncode, cmd, cp.stdout, cp.stderr)
    return cp.stdout


def _is_local(source: str) -> bool:
    return Path(source).exists()


def resolve_pin(source: str, ref: str = "refs/heads/main", pin: str | None = None) -> str:
    """Return the SHA to clone at: an explicit ``pin`` verbatim, else ``git ls-remote`` of ``ref``.

    Reads the source's *ref* (not its checked-out branch); raises ``MissingFixtureError`` when the
    source is unreachable or the ref is absent, so the runner degrades to a skip.
    """
    if pin:
        return pin
    try:
        out = _git(None, "ls-remote", source, ref)
    except (subprocess.CalledProcessError, OSError) as exc:
        detail = getattr(exc, "stderr", "") or exc
        raise MissingFixtureError(
            f"cannot resolve pin: git ls-remote {source!r} {ref!r} failed: "
            f"{str(detail).strip()}") from None
    for line in out.splitlines():
        sha, _, name = line.partition("\t")
        if name.strip() == ref:
            return sha.strip()
    first = out.split("\t", 1)[0].strip() if out.strip() else ""
    if not first:
        raise MissingFixtureError(f"ref {ref!r} not found in source {source!r}")
    return first


def clone_at(source: str, sha: str, dest: Path) -> None:
    """``git clone [--no-local] <source> <dest>`` then detach ``HEAD`` at ``sha``.

    ``--no-local`` (local sources only) forces a real object copy so the source ``.git`` is never
    hardlinked or otherwise touched. ``dest`` must be empty or nonexistent (git's requirement).

    A nested child ``path`` (e.g. ``packages/api``) needs its leading dirs to exist; #155 item 5
    makes that explicit via ``mkdir(parents=True)`` so a multi-level child clones rather than
    degrading to a skip, and raises a clean ``MissingFixtureError`` if the parent is genuinely
    uncreatable (e.g. a path element is an existing file) instead of a cryptic git error.
    """
    dest = Path(dest)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise MissingFixtureError(
            f"cannot create parent directory for clone dest {str(dest)!r}: {exc}") from None
    args = ["git", "clone", "-q"]
    if _is_local(source):
        args.append("--no-local")
    args += [source, str(dest)]
    cp = subprocess.run(args, capture_output=True, text=True)
    if cp.returncode != 0:
        raise MissingFixtureError(f"git clone of {source!r} failed: {cp.stderr.strip()}")
    co = subprocess.run(["git", "-C", str(dest), "checkout", "-q", "--detach", sha],
                        capture_output=True, text=True)
    if co.returncode != 0:
        raise MissingFixtureError(
            f"git checkout {sha} in clone of {source!r} failed: {co.stderr.strip()}")


def source_fingerprint(source: str) -> dict | None:
    """``{head, porcelain}`` of a LOCAL source's live working tree, or ``None`` for a remote URL.

    The pair the read-only invariant asserts is byte-identical before and after a provision.
    ``None`` for a remote (no local tree to protect) — the invariant is vacuously held.
    """
    if not _is_local(source):
        return None
    p = Path(source)
    try:
        head = _git(p, "rev-parse", "HEAD").strip()
        porcelain = _git(p, "status", "--porcelain")
    except (subprocess.CalledProcessError, OSError):
        return None
    return {"head": head, "porcelain": porcelain}


# --------------------------------------------------------------------- provisioning


def _all_sources(spec: RealFixtureSpec) -> list[str]:
    return [spec.source, *(c.source for c in spec.children)]


def _write_meta_yaml(wd: Path, spec: RealFixtureSpec) -> Path:
    """Emit the ``install.meta.yaml`` the meta install reads (mirrors the synthetic ``_prov_meta``)."""
    lines = ["repo:", "  expect: any", "scm:", "  owner: acme",
             "project:", "  model: meta", "children:"]
    for child in spec.children:
        lines.append(f"  - path: {child.path}")
        if child.flavor and child.flavor != "product":
            lines.append(f"    flavor: {child.flavor}")
    yaml = wd / "install.meta.yaml"
    yaml.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return yaml


def _guard_zero_children(spec: RealFixtureSpec, opts: dict) -> None:
    """#155 item 4 / #244: handle a ``meta-and-children`` spec provisioned with no children.

    A bare ``--include-real`` B10 with no ``--real-config`` resolves to a degenerate
    zero-children meta install. By DEFAULT this is surfaced with a ``warnings.warn`` and the
    trivial install proceeds — a childless meta is a valid (if trivial) install, and a smoke-test
    ``--include-real`` run should degrade rather than crash. A real provisioning run that MUST have
    children (``#101``/``#109``) can opt into a HARD guard two equivalent ways: the global
    ``opts['real_require_children']`` (all buckets), OR the bucket spec's own ``require_children``
    flag (#251 — settable per bucket through the ``--real-config`` sidecar JSON, e.g.
    ``{"B10": {"require_children": true}}``, so an operator toggles the guard without editing code).
    Either enabled, the harness raises ``MissingFixtureError`` (degraded to a *skip* by the runner)
    instead of shipping the degenerate zero-children install, so a misconfigured real run fails
    visibly rather than silently provisioning an empty meta. Both surfaces default OFF (#244): the
    guard stays a warn-and-proceed unless one is explicitly enabled.
    """
    if opts.get("real_require_children") or spec.require_children:
        raise MissingFixtureError(
            f"real fixture {spec.bucket!r} is meta-and-children with zero children and "
            "real_require_children is set — refusing the degenerate zero-children meta install; "
            "supply children via --real-config (#155 item 4 / #244 / #251)."
        )
    warnings.warn(
        f"real fixture {spec.bucket!r} is meta-and-children with zero children — "
        "degenerate meta install; supply children via --real-config (#155 item 4 / #244).",
        stacklevel=3,
    )


def provision_real(spec: RealFixtureSpec | None, wd: Path, opts: dict | None = None) -> dict:
    """Clone ``spec``'s source (+ children for meta) at its pin into ``wd``; return fixture ctx.

    Read-only w.r.t. the source and asserted so: every local source's ``{head, porcelain}`` is
    fingerprinted before and after and must be byte-identical (``SourceMutatedError`` otherwise).
    """
    opts = opts or {}
    if spec is None:
        raise MissingFixtureError("no real-fixture spec registered for this bucket")

    before = {s: source_fingerprint(s) for s in _all_sources(spec)}

    def _assert_source_unchanged() -> bool:
        after = {s: source_fingerprint(s) for s in _all_sources(spec)}
        if before != after:
            changed = [s for s in before if before[s] != after[s]]
            raise SourceMutatedError(
                f"source(s) mutated during provision (read-only invariant violated): {changed}")
        return True

    ctx: dict | None = None
    try:
        sha = resolve_pin(spec.source, spec.ref, spec.pin)
        clone_at(spec.source, sha, wd)

        ctx = {"extra": {"machine_root": str(wd), "real": True,
                         "source": spec.source, "pin": sha}}

        if spec.model == "meta-and-children":
            if not spec.children:
                # #155 item 4 / #244: a bare --include-real B10 with no --real-config resolves to
                # a degenerate zero-children meta install. Default = warn-and-proceed; opt into a
                # hard MissingFixtureError guard via opts['real_require_children'] (see helper).
                _guard_zero_children(spec, opts)
            children_ctx = []
            for child in spec.children:
                child_sha = resolve_pin(child.source, child.ref, child.pin)
                clone_at(child.source, child_sha, wd / child.path)
                children_ctx.append({"path": child.path, "rel": "..", "flavor": child.flavor})
            ctx["child"] = {"children": children_ctx}
            ctx["yaml"] = str(_write_meta_yaml(wd, spec))
    finally:
        # #155 item 1: the read-only invariant is defense-in-depth, so the after-fingerprint
        # assertion MUST run even when a clone raised partway through a multi-clone (e.g. a child
        # unreachable after the parent already cloned) — otherwise a partial failure would skip
        # the check entirely. A genuine source mutation raises SourceMutatedError here, taking
        # priority over (and chaining from) any in-flight provisioning error; an unchanged source
        # lets the original error propagate untouched.
        unchanged = _assert_source_unchanged()
        if ctx is not None:
            ctx["extra"]["source_unchanged"] = unchanged
    return ctx


# --------------------------------------------------------------------- registry + factory


def real_registry(opts: dict | None = None) -> dict[str, RealFixtureSpec]:
    """The effective bucket->spec map: DEFAULTs overlaid by a ``--real-config`` sidecar JSON
    (``opts['real_config']``) then by an in-process ``opts['real_fixtures']`` (tests).

    #155 item 3 — overrides MERGE, they do not wholesale-replace: a partial patch (a ``dict``
    from the sidecar JSON, or a ``dict`` value in ``real_fixtures``) updates only its provided
    keys and preserves the rest of the existing bucket spec, so overriding just ``pin`` no longer
    silently drops ``children`` back to ``()``. A full ``RealFixtureSpec`` value in
    ``real_fixtures`` is still an explicit whole-spec replacement (back-compat for callers that
    build a complete spec). A partial patch for a bucket with no existing/default spec creates a
    brand-new bucket and therefore MUST carry a ``source`` — a source-less new-bucket patch raises
    a friendly ``MissingFixtureError`` naming the bucket (#243) rather than a bare ``KeyError``.
    """
    opts = opts or {}
    reg = dict(DEFAULT_REAL_FIXTURES)

    def _apply(bucket: str, override: dict | RealFixtureSpec) -> None:
        if isinstance(override, RealFixtureSpec):
            reg[bucket] = override                       # explicit whole-spec replacement
        elif bucket in reg:
            reg[bucket] = reg[bucket].merge(override)     # partial patch merges onto existing
        elif "source" not in override:
            # #243: a partial patch that CREATES a new bucket must carry a 'source'. Without it,
            # from_dict() would raise a bare KeyError('source'); surface a friendly, actionable
            # message naming the bucket instead (MissingFixtureError -> runner degrades to a skip).
            raise MissingFixtureError(
                f"real fixture override for new bucket {bucket!r} is a partial patch with no "
                "'source' key; creating a new bucket requires a 'source' (a local path or git "
                "remote URL). Add a 'source', or patch an already-registered bucket."
            )
        else:
            reg[bucket] = RealFixtureSpec.from_dict(bucket, override)  # brand-new bucket

    cfg_path = opts.get("real_config")
    if cfg_path:
        data = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
        for bucket, d in data.items():
            _apply(bucket, d)
    for bucket, override in (opts.get("real_fixtures") or {}).items():
        _apply(bucket, override)
    return reg


def make_real_provisioner(bucket_id: str):
    """A ``(wd, opts) -> ctx`` provisioner bound to ``bucket_id`` (looks its spec up per-run)."""

    def _provision(wd: Path, opts: dict) -> dict:
        return provision_real(real_registry(opts).get(bucket_id), wd, opts)

    _provision.__name__ = f"_prov_real_{bucket_id}"
    _provision.__qualname__ = _provision.__name__
    _provision.__doc__ = f"Real-repo provisioner for {bucket_id} (clone-at-pinned-SHA, #153)."
    return _provision
