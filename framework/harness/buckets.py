"""Repo-type buckets (#103 taxonomy) as DATA — provisioners, legs, permutations, applicability.

Each ``Bucket`` names a fixture the harness synthesizes into a disposable tmp workdir and one
or more ``Leg`` s — an installer permutation plus the #103 metric ids applicable to it. The
matrix is inspectable/diffable data (#104 §6 handoff items 2+3): bucket→installers,
bucket→permutation-flags, bucket→[metric-id]. Metric ids are #103 verbatim.

Owner decisions bound into this wave:
  * Default run = hermetic **B1-B9** + **B12 dogfood INLINE** (reinstall --check on this repo).
  * **B10/B11** are DEFINED but flag-gated OFF (``real=True``); ``--include-real`` opts in, and
    their provisioning clones the live source at a pinned SHA into scratch, read-only w.r.t. the
    source (never the live working tree). See ``real_provision`` (#153).
Stdlib only.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .real_provision import make_real_provisioner

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _FRAMEWORK_ROOT.parent
_BOOTSTRAP = _FRAMEWORK_ROOT / "install" / "bootstrap.py"

#: Repo-root data dirs the CLI resolves via ``parents[2]`` in a source checkout. The
#: soft-degrade fixture copies these (so team scaffolding still works) but deliberately
#: OMITS ``framework/`` so the bridge's ``resolve_framework_root()`` returns None.
_CLI_SOURCE_DATA_DIRS = ("presets", "templates", "skills")

#: Default B9 scale (trivial .py files). #103 proposes ~2000; kept lower for CI wall-clock,
#: overridable via ``--scale`` so the scale check can be dialed up on demand.
DEFAULT_B9_FILES = 300


# --------------------------------------------------------------------- git helpers


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _git_init(path: Path, *, commit: bool = False) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    if commit:
        (path / "README.md").write_text("hello\n", encoding="utf-8")
        _git(path, "add", "-A")
        subprocess.run(
            ["git", "-C", str(path), "-c", "user.name=T", "-c", "user.email=t@e.com",
             "commit", "-q", "-m", "init"],
            check=True, capture_output=True,
        )


def _install_parent_framework(parent: Path) -> None:
    """Install the framework into ``parent`` (a prerequisite for B7 child mode)."""
    subprocess.run(
        [sys.executable, str(_BOOTSTRAP), str(parent), "--owner", "acme",
         "--no-team", "--non-interactive", "--no-ontology"],
        check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )


# --------------------------------------------------------------------- model types


@dataclass
class Leg:
    """One installer permutation of a bucket + the metric ids it exercises."""

    perm_label: str
    installers: tuple[str, ...]
    metrics: list[str]
    permutation: dict
    build_flags: Callable[[Path], list[str]] = lambda _wd: []
    #: CLI-bridge flag builder (``2real-team init`` flag vocabulary). Only consulted for the
    #: ``cli`` installer; falls back to ``build_flags`` when unset.
    cli_flags: Callable[[Path], list[str]] | None = None
    expect_exit: int = 0
    gate_expect: str | None = None
    teardown_proof: bool = False
    target_subdir: str = "."  # install target relative to the workdir (B7 child = "svc")


@dataclass
class Bucket:
    id: str
    label: str
    provision: Callable[[Path, dict], dict]  # (workdir, opts) -> fixture context
    legs: list[Leg]
    real: bool = False
    installers_hint: tuple[str, ...] = ("bootstrap",)


# --------------------------------------------------------------------- provisioners


def _prov_empty(wd: Path, opts: dict) -> dict:
    return {}


def _prov_fresh_git(wd: Path, opts: dict) -> dict:
    _git_init(wd)
    return {}


def _prov_single_lang(wd: Path, opts: dict) -> dict:
    (wd / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    (wd / "module.py").write_text("def greet(name):\n    return f'hi {name}'\n", encoding="utf-8")
    (wd / "pkg").mkdir()
    (wd / "pkg" / "__init__.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    # Unified config for the CLI leg: the `2real-team init` bridge has no --expect flag, so an
    # existing-repo install is expressed through repo.expect in a forwarded --config YAML.
    (wd / "cli.yaml").write_text(
        "version: 1\nrepo:\n  expect: existing\nscm:\n  owner: acme\n"
        "ontology:\n  enabled: true\nteam:\n  enabled: true\n  preset: library\n",
        encoding="utf-8",
    )
    return {"extra": {"expect_source_path": "module.py"}}


def _prov_existing_foreign(wd: Path, opts: dict) -> dict:
    (wd / "src").mkdir()
    (wd / "src" / "main.py").write_text("print('app')\n", encoding="utf-8")
    (wd / "README.md").write_text("# real project\n", encoding="utf-8")
    _git_init(wd, commit=True)
    return {}


def _prov_preexisting_claude(wd: Path, opts: dict) -> dict:
    content = b"my own hand-written project notes\n"
    (wd / "CLAUDE.md").write_bytes(content)
    (wd / ".claude").mkdir()
    foreign = '{"foreignKey": "keep-me", "hooks": {"PreToolUse": [{"matcher": "Grep", "hooks": []}]}}'
    (wd / ".claude" / "settings.json").write_text(foreign, encoding="utf-8")
    return {
        "preexisting": {
            "claude_md": content,
            "settings_foreign_key": ("foreignKey", "keep-me"),
        }
    }


def _prov_meta(wd: Path, opts: dict) -> dict:
    _git_init(wd / "api")
    (wd / "api" / "pyproject.toml").write_text("[project]\nname='api'\n", encoding="utf-8")
    _git_init(wd / "web")
    yaml = wd / "install.meta.yaml"
    yaml.write_text(
        "repo:\n  expect: any\nscm:\n  owner: acme\n"
        "project:\n  model: meta\n"
        "children:\n  - path: api\n  - path: web\n    flavor: infra\n",
        encoding="utf-8",
    )
    return {
        "child": {"children": [
            {"path": "api", "rel": "..", "flavor": "product"},
            {"path": "web", "rel": "..", "flavor": "infra"},
        ]},
        "extra": {"machine_root": str(wd)},
        "yaml": str(yaml),
    }


def _prov_child_ok(wd: Path, opts: dict) -> dict:
    """Parent WITH framework + a child git repo at ``svc`` (target)."""
    _install_parent_framework(wd)
    _git_init(wd / "svc")
    yaml = wd / "child.yaml"
    yaml.write_text(
        "project:\n  model: child\n  flavor: infra\nparent:\n  path: ..\n", encoding="utf-8"
    )
    return {
        "child": {"children": [{"path": ".", "rel": "..", "flavor": "infra"}]},
        "extra": {"machine_root": str(wd), "child_expect": {"parent": "..", "flavor": "infra"}},
        "yaml": str(yaml),
    }


def _prov_child_no_parent(wd: Path, opts: dict) -> dict:
    """BARE parent (no framework) + child git repo at ``svc`` — child install must refuse."""
    _git_init(wd / "svc")
    yaml = wd / "child.yaml"
    yaml.write_text("project:\n  model: child\nparent:\n  path: ..\n", encoding="utf-8")
    return {"yaml": str(yaml)}


def _prov_adversarial(wd: Path, opts: dict) -> dict:
    (wd / "ontology").mkdir()
    (wd / "ontology" / "structural").write_text("not a directory\n", encoding="utf-8")
    return {}


def _prov_invalid_config(wd: Path, opts: dict) -> dict:
    bad = wd / "bad.config.json"
    bad.write_text('{"version": 0}\n', encoding="utf-8")
    return {"config_json": str(bad)}


def _prov_cli_soft_degrade(wd: Path, opts: dict) -> dict:
    """Isolated *source-checkout* fixture MISSING the framework payload.

    Lays ``<wd>/iso/python/src/real_team`` (a copy of the CLI package) plus the
    ``presets/templates/skills`` data dirs at the package's ``parents[2]`` — but NO
    ``framework/``. Run through ``run_cli_soft_degrade`` (which puts ``iso/python/src`` on
    ``PYTHONPATH``), ``resolve_framework_root()`` finds neither ``_bundled/framework`` nor a
    repo-root ``framework/``, so the bridge soft-degrades while team scaffolding still lands.
    Returns the importable package root in ``extra.iso_src`` for the runner.
    """
    iso = wd / "iso"
    src = iso / "python" / "src"
    src.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_REPO_ROOT / "python" / "src" / "real_team", src / "real_team")
    for data in _CLI_SOURCE_DATA_DIRS:
        origin = _REPO_ROOT / data
        if origin.is_dir():
            shutil.copytree(origin, iso / data)
    return {"extra": {"iso_src": str(src)}}


def _prov_large(wd: Path, opts: dict) -> dict:
    n = int(opts.get("scale", DEFAULT_B9_FILES))
    gen = wd / "gen"
    gen.mkdir()
    for i in range(n):
        (gen / f"f{i:05d}.py").write_text(f"def fn_{i}():\n    return {i}\n", encoding="utf-8")
    return {"extra": {"expect_source_path": "gen/f00000.py"}, "n_files": n}


# B10/B11 real-world provisioning (clone-at-pinned-SHA into scratch, read-only w.r.t. the live
# source) lives in ``real_provision`` and is bound per-bucket by ``make_real_provisioner`` — the
# source/pin registry is DATA there (#153), overridable via ``--real-config`` for #101/#109.


# --------------------------------------------------------------------- the matrix


def _bootstrap_flags(*flags: str) -> Callable[[Path], list[str]]:
    return lambda _wd: list(flags)


# Common metric groups (kept DRY; #103 ids verbatim).
_CORE_STANDALONE = [
    "install_exit_status", "non_interactive_zero_prompts", "no_unexpected_files",
    "install_snapshot_recorded", "settings_hooks_wired", "permissions_allowlist_present",
    "config_module_lists_complete", "files_installed_complete", "install_duration_s",
]
_BEHAVIORAL = ["gate_blocks_no_verify", "gate_passes_benign", "identity_gate_active"]


def build_buckets() -> list[Bucket]:
    return [
        Bucket("B1", "empty-non-git", _prov_empty, [
            Leg("default", ("bootstrap",),
                _CORE_STANDALONE + _BEHAVIORAL + ["reinstall_idempotent", "no_backup_litter"],
                {"model": "single-repo", "expect": "fresh", "ontology": False, "team": True},
                _bootstrap_flags("--expect", "fresh", "--owner", "acme", "--no-ontology")),
        ]),
        Bucket("B2", "fresh-git", _prov_fresh_git, [
            Leg("default", ("bootstrap", "cli"),
                _CORE_STANDALONE + _BEHAVIORAL
                + ["reinstall_idempotent", "dry_run_writes_nothing", "no_backup_litter",
                   "teardown_residue_zero", "shell_gate_respected"],
                {"model": "single-repo", "expect": "fresh", "ontology": True, "team": True,
                 "shell": "zsh"},
                _bootstrap_flags("--owner", "acme", "--shell", "zsh"),
                cli_flags=lambda wd: ["--preset", "library", "--owner", "acme"],
                teardown_proof=True),
        ], installers_hint=("bootstrap", "cli")),
        Bucket("B3", "single-language-app", _prov_single_lang, [
            Leg("with-ontology", ("bootstrap", "cli"),
                _CORE_STANDALONE
                + ["ontology_overlay_seeded", "ontology_structural_generated",
                   "ontology_gen_duration_s", "reinstall_idempotent", "no_backup_litter"],
                {"model": "single-repo", "expect": "existing", "ontology": True, "team": True},
                _bootstrap_flags("--with-ontology", "--expect", "existing", "--owner", "acme"),
                cli_flags=lambda wd: ["--config", str(wd / "cli.yaml")]),
        ], installers_hint=("bootstrap", "cli")),
        Bucket("B4", "existing-foreign-no-claude", _prov_existing_foreign, [
            Leg("refuse", ("bootstrap",),
                ["install_exit_status", "repo_state_gate_correct", "non_interactive_zero_prompts"],
                {"model": "single-repo", "expect": "fresh", "gate": "refuse"},
                _bootstrap_flags("--expect", "fresh", "--no-team"),
                expect_exit=1, gate_expect="refuse"),
            Leg("proceed", ("bootstrap",),
                _CORE_STANDALONE + ["repo_state_gate_correct", "no_backup_litter"],
                {"model": "single-repo", "expect": "existing", "gate": "proceed", "team": True},
                _bootstrap_flags("--expect", "existing", "--owner", "acme"),
                gate_expect="proceed"),
        ]),
        Bucket("B5", "preexisting-claude-settings", _prov_preexisting_claude, [
            Leg("bootstrap-merge", ("bootstrap",),
                # NOTE: settings_hooks_wired is a CLEAN-install assertion (exact matcher set);
                # B5 deliberately merges a foreign matcher (Grep), so the union is a superset —
                # that survival IS the point, asserted by settings_merge_preserves_foreign.
                ["install_exit_status", "non_interactive_zero_prompts",
                 "settings_merge_preserves_foreign", "config_module_lists_complete"],
                {"model": "single-repo", "expect": "any", "team": True},
                _bootstrap_flags("--expect", "any", "--owner", "acme", "--no-ontology")),
            Leg("cli-claude-backup", ("cli",),
                ["install_exit_status", "claude_md_backup_safe", "non_interactive_zero_prompts"],
                {"model": "single-repo", "installer_writes_claude_md": True, "team": True},
                lambda wd: ["--preset", "library", "--no-ontology"]),
        ]),
        Bucket("B6", "meta-and-children", _prov_meta, [
            Leg("meta", ("bootstrap",),
                ["install_exit_status", "non_interactive_zero_prompts",
                 "child_wiring_portable", "child_flavor_filtered",
                 "no_unexpected_files", "reinstall_idempotent", "no_backup_litter",
                 "teardown_residue_zero", "install_duration_s"],
                {"model": "meta-and-children", "expect": "any", "team": True},
                lambda wd: ["--install-config", str(wd / "install.meta.yaml"), "--model",
                            "meta-and-children"],
                teardown_proof=True),
        ]),
        Bucket("B7", "standalone-child", _prov_child_ok, [
            Leg("child", ("bootstrap",),
                ["install_exit_status", "non_interactive_zero_prompts",
                 "child_wiring_portable", "child_config_inherits"],
                {"model": "child", "flavor": "infra", "team": True},
                lambda wd: ["--install-config", str(wd / "child.yaml")],
                target_subdir="svc"),
        ]),
        Bucket("B7b", "child-missing-parent", _prov_child_no_parent, [
            Leg("no-parent", ("bootstrap",),
                ["install_exit_status", "child_parent_precondition",
                 "non_interactive_zero_prompts"],
                {"model": "child", "parent_missing": True},
                lambda wd: ["--install-config", str(wd / "child.yaml")],
                expect_exit=1, target_subdir="svc"),
        ]),
        Bucket("B8", "adversarial-degraded", _prov_adversarial, [
            Leg("ontology-fail-open", ("bootstrap",),
                ["install_exit_status", "ontology_fail_open", "non_interactive_zero_prompts",
                 "settings_hooks_wired"],
                {"model": "single-repo", "ontology": True, "team": True},
                _bootstrap_flags("--with-ontology", "--owner", "acme")),
        ]),
        Bucket("B8b", "invalid-config", _prov_invalid_config, [
            Leg("invalid-config", ("bootstrap",),
                ["install_exit_status", "invalid_config_refused",
                 "non_interactive_zero_prompts"],
                {"model": "single-repo", "invalid_version": True},
                lambda wd: ["--config", str(wd / "bad.config.json"), "--expect", "any",
                            "--no-team"],
                expect_exit=1),
        ]),
        Bucket("B9", "large-repo", _prov_large, [
            Leg("scale", ("bootstrap",),
                ["install_exit_status", "install_duration_s", "ontology_gen_duration_s",
                 "ontology_structural_generated", "non_interactive_zero_prompts"],
                {"model": "single-repo", "ontology": True, "team": True, "scale": True,
                 "expect": "any"},
                # A nonempty non-git dir classifies as EXISTING, so --expect any keeps the gate
                # out of the way — B9 stresses scale/timing, not the fresh-vs-existing verdict.
                _bootstrap_flags("--with-ontology", "--expect", "any", "--owner", "acme")),
        ]),
        Bucket("B13", "cli-bridge-soft-degrade", _prov_cli_soft_degrade, [
            Leg("soft-degrade", ("cli_soft_degrade",),
                ["cli_bridge_soft_degrade", "install_exit_status",
                 "non_interactive_zero_prompts"],
                {"model": "single-repo", "installer": "cli", "bundled_assets": "absent",
                 "team": True},
                _bootstrap_flags("--preset", "library", "--owner", "acme"),
                target_subdir="proj"),
        ], installers_hint=("cli_soft_degrade",)),
        # --- [real] flag-gated OFF by default (owner-decision 1); provisioned by cloning the
        # live source at a pinned SHA into scratch (#153) only under --include-real. ---
        Bucket("B10", "meta-real-world", make_real_provisioner("B10"), [
            Leg("meta-real", ("bootstrap",),
                ["install_exit_status", "non_interactive_zero_prompts",
                 "child_wiring_portable", "child_flavor_filtered", "no_unexpected_files",
                 "reinstall_idempotent", "no_backup_litter", "teardown_residue_zero",
                 "install_duration_s"],
                {"model": "meta-and-children", "expect": "any", "team": True, "real": True},
                lambda wd: ["--install-config", str(wd / "install.meta.yaml"), "--model",
                            "meta-and-children"],
                teardown_proof=True),
        ], real=True),
        Bucket("B11", "standalone-real-world", make_real_provisioner("B11"), [
            Leg("existing-real", ("bootstrap",),
                _CORE_STANDALONE + ["repo_state_gate_correct", "reinstall_idempotent",
                                    "no_backup_litter", "teardown_residue_zero"],
                {"model": "single-repo", "expect": "existing", "team": True, "real": True},
                _bootstrap_flags("--expect", "existing", "--owner", "acme", "--no-ontology"),
                gate_expect="proceed", teardown_proof=True),
        ], real=True),
    ]


# B12 dogfood is special-cased in the runner (read-only reinstall --check on THIS repo;
# no fixture, no teardown), not a synthesized bucket.
B12_METRIC = "reinstall_parity_clean"
