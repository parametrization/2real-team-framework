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
import subprocess
import warnings
from dataclasses import dataclass
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

    def to_dict(self) -> dict:
        return {"bucket": self.bucket, "source": self.source, "pin": self.pin,
                "ref": self.ref, "model": self.model,
                "children": [c.to_dict() for c in self.children]}

    @classmethod
    def from_dict(cls, bucket: str, d: dict) -> RealFixtureSpec:
        return cls(
            bucket=bucket, source=d["source"], pin=d.get("pin"),
            ref=d.get("ref", "refs/heads/main"), model=d.get("model", "single-repo"),
            children=tuple(RealChildSpec.from_dict(c) for c in d.get("children", ())),
        )


#: Documented current HEADs (from #150 discovery), kept for reference/reproducibility only —
#: the DEFAULT specs resolve the LIVE ``refs/heads/main`` at run time (``pin=None``) so a dev
#: run never trusts a locally checked-out feature branch. #101 supplies noorinalabs' in-scope
#: nested children (and #101/#109 an explicit pin) via ``--real-config``.
DEFAULT_REAL_FIXTURES: dict[str, RealFixtureSpec] = {
    # B11 standalone-real-world -> botfarm_inc (HEAD a4e622dde79436ee8230de662020c3f3f0ee7e9d)
    "B11": RealFixtureSpec(
        bucket="B11", source="/home/parameterization/code/botfarm_inc",
        pin=None, ref="refs/heads/main", model="single-repo",
    ),
    # B10 meta-real-world -> noorinalabs-main (HEAD 582416e85413f52b2972ae8def36a37eb486f818)
    "B10": RealFixtureSpec(
        bucket="B10", source="/home/parameterization/code/noorinalabs-main",
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
    """
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


def provision_real(spec: RealFixtureSpec | None, wd: Path, opts: dict | None = None) -> dict:
    """Clone ``spec``'s source (+ children for meta) at its pin into ``wd``; return fixture ctx.

    Read-only w.r.t. the source and asserted so: every local source's ``{head, porcelain}`` is
    fingerprinted before and after and must be byte-identical (``SourceMutatedError`` otherwise).
    """
    if spec is None:
        raise MissingFixtureError("no real-fixture spec registered for this bucket")

    before = {s: source_fingerprint(s) for s in _all_sources(spec)}

    sha = resolve_pin(spec.source, spec.ref, spec.pin)
    clone_at(spec.source, sha, wd)

    ctx: dict = {"extra": {"machine_root": str(wd), "real": True,
                           "source": spec.source, "pin": sha}}

    if spec.model == "meta-and-children":
        if not spec.children:
            # #155 item 4: a bare --include-real B10 with no --real-config resolves to a
            # degenerate zero-children meta install. Not fatal (a childless meta is a valid,
            # if trivial, install), but surface it instead of silently degrading — #101 supplies
            # children explicitly via --real-config.
            warnings.warn(
                f"real fixture {spec.bucket!r} is meta-and-children with zero children — "
                "degenerate meta install; supply children via --real-config (#155 item 4).",
                stacklevel=2,
            )
        children_ctx = []
        for child in spec.children:
            child_sha = resolve_pin(child.source, child.ref, child.pin)
            clone_at(child.source, child_sha, wd / child.path)
            children_ctx.append({"path": child.path, "rel": "..", "flavor": child.flavor})
        ctx["child"] = {"children": children_ctx}
        ctx["yaml"] = str(_write_meta_yaml(wd, spec))

    after = {s: source_fingerprint(s) for s in _all_sources(spec)}
    unchanged = before == after
    ctx["extra"]["source_unchanged"] = unchanged
    if not unchanged:
        changed = [s for s in before if before[s] != after[s]]
        raise SourceMutatedError(
            f"source(s) mutated during provision (read-only invariant violated): {changed}")
    return ctx


# --------------------------------------------------------------------- registry + factory


def real_registry(opts: dict | None = None) -> dict[str, RealFixtureSpec]:
    """The effective bucket->spec map: DEFAULTs overlaid by a ``--real-config`` sidecar JSON
    (``opts['real_config']``) then by an in-process ``opts['real_fixtures']`` (tests)."""
    opts = opts or {}
    reg = dict(DEFAULT_REAL_FIXTURES)
    cfg_path = opts.get("real_config")
    if cfg_path:
        data = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
        for bucket, d in data.items():
            reg[bucket] = RealFixtureSpec.from_dict(bucket, d)
    for bucket, spec in (opts.get("real_fixtures") or {}).items():
        reg[bucket] = spec
    return reg


def make_real_provisioner(bucket_id: str):
    """A ``(wd, opts) -> ctx`` provisioner bound to ``bucket_id`` (looks its spec up per-run)."""

    def _provision(wd: Path, opts: dict) -> dict:
        return provision_real(real_registry(opts).get(bucket_id), wd, opts)

    _provision.__name__ = f"_prov_real_{bucket_id}"
    _provision.__qualname__ = _provision.__name__
    _provision.__doc__ = f"Real-repo provisioner for {bucket_id} (clone-at-pinned-SHA, #153)."
    return _provision
