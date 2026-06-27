"""Tests for pre_commit_ci_sync — the pre-commit <-> CI drift gate (#327).

Verifies:
  1. Canonical kind extraction from both pre-commit configs and CI workflows.
  2. The drift direction that gates: CI-enforced-but-not-local is harmful;
     local-but-not-CI is stricter-local (informational, never a gate fail).
  3. ruff-format vs ruff-lint are not conflated.
  4. The real parent (noorinalabs-main) config mirrors its CI kinds (no drift).
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

# Helper lives at .claude/lib/pre_commit_ci_sync.py; test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pre_commit_ci_sync import (  # noqa: E402
    check_repo,
    compute_drift,
    kinds_from_ci,
    kinds_from_precommit,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]


class PrecommitKindExtraction(unittest.TestCase):
    def test_ruff_format_and_lint_both_detected(self) -> None:
        cfg = """
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    hooks:
      - id: ruff-format
      - id: ruff
"""
        kinds = kinds_from_precommit(cfg)
        self.assertIn("ruff-format", kinds)
        self.assertIn("ruff-lint", kinds)

    def test_mypy_and_pytest_local_hooks(self) -> None:
        cfg = """
repos:
  - repo: local
    hooks:
      - id: mypy
        entry: python3 -m mypy
      - id: pytest-unit
        entry: pytest
"""
        kinds = kinds_from_precommit(cfg)
        self.assertIn("mypy", kinds)
        self.assertIn("pytest", kinds)

    def test_frontend_kinds(self) -> None:
        cfg = """
repos:
  - repo: local
    hooks:
      - id: eslint
      - id: typecheck
        entry: tsc --noEmit
      - id: prettier
"""
        kinds = kinds_from_precommit(cfg)
        self.assertIn("eslint", kinds)
        self.assertIn("typescript", kinds)
        self.assertIn("prettier", kinds)

    def test_comments_ignored(self) -> None:
        cfg = "# id: mypy is just a comment\nrepos: []\n"
        self.assertNotIn("mypy", kinds_from_precommit(cfg))


class CiKindExtraction(unittest.TestCase):
    def test_run_steps_detected(self) -> None:
        wf = """
jobs:
  lint:
    steps:
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy src/
      - run: pytest -q
"""
        kinds = kinds_from_ci(wf)
        self.assertEqual(
            kinds & {"ruff-lint", "ruff-format", "mypy", "pytest"},
            {"ruff-lint", "ruff-format", "mypy", "pytest"},
        )

    def test_uses_actions_detected(self) -> None:
        wf = """
jobs:
  scan:
    steps:
      - uses: gitleaks/gitleaks-action@v2
"""
        self.assertIn("gitleaks", kinds_from_ci(wf))

    def test_ruff_format_line_not_counted_as_lint(self) -> None:
        # A format-only line must NOT register ruff-lint.
        kinds = kinds_from_ci("      - run: ruff format --check .\n")
        self.assertIn("ruff-format", kinds)
        self.assertNotIn("ruff-lint", kinds)


class CspellKindClassification(unittest.TestCase):
    """#684: the spell-check blind spot. A CI Spellcheck job must classify as
    the `cspell` kind on EITHER expression — the `streetsidesoftware/cspell-action`
    `uses:` ref, the bundled-CLI `cspell` step/run, or the generic `spellcheck`
    word — and a pre-commit cspell hook must classify too, so a CI spell gate
    with no local mirror produces harmful drift instead of silence."""

    def test_cspell_action_uses_ref_classified(self) -> None:
        wf = """
jobs:
  spellcheck:
    name: Spellcheck (cspell)
    steps:
      - name: cspell
        uses: streetsidesoftware/cspell-action@de2a73e # v8.4.0
"""
        self.assertIn("cspell", kinds_from_ci(wf))

    def test_cspell_cli_run_step_classified(self) -> None:
        wf = """
jobs:
  spell:
    steps:
      - run: npx cspell --config .cspell.json "**/*.md"
"""
        self.assertIn("cspell", kinds_from_ci(wf))

    def test_generic_spellcheck_word_classified(self) -> None:
        # A repo that names the step/run with the generic word still registers.
        self.assertIn("cspell", kinds_from_ci("      - run: make spellcheck\n"))

    def test_precommit_cspell_hook_classified(self) -> None:
        cfg = """
repos:
  - repo: https://github.com/streetsidesoftware/cspell-cli
    rev: v8.4.0
    hooks:
      - id: cspell
        name: cspell
"""
        self.assertIn("cspell", kinds_from_precommit(cfg))

    def test_ci_cspell_without_precommit_is_harmful_drift(self) -> None:
        # The exact divergence #684 exists to catch: CI enforces cspell, the
        # pre-commit config does not mirror it.
        wf = """
jobs:
  spellcheck:
    steps:
      - uses: streetsidesoftware/cspell-action@de2a73e
"""
        cfg = """
repos:
  - repo: local
    hooks:
      - id: ruff
"""
        harmful, _ = compute_drift(kinds_from_precommit(cfg), kinds_from_ci(wf))
        self.assertIn("cspell", harmful)

    def test_ci_cspell_with_precommit_mirror_no_drift(self) -> None:
        wf = """
jobs:
  spellcheck:
    steps:
      - uses: streetsidesoftware/cspell-action@de2a73e
"""
        cfg = """
repos:
  - repo: https://github.com/streetsidesoftware/cspell-cli
    rev: v8.4.0
    hooks:
      - id: cspell
"""
        harmful, _ = compute_drift(kinds_from_precommit(cfg), kinds_from_ci(wf))
        self.assertNotIn("cspell", harmful)


class OfficeDriftKind(unittest.TestCase):
    """#781: the generated-Office-binary drift gate must be a classified kind so
    the sync-drift gate DEMANDS a pre-commit mirror of the CI job (an un-mirrored
    office gate lets a stale binary fail only at PR time)."""

    def test_ci_office_drift_run_step_classified(self) -> None:
        wf = """
jobs:
  office-drift:
    steps:
      - run: |
          scripts/gen-office.sh
          git diff --exit-code -- 'docs/office/*.docx'
"""
        self.assertIn("office-drift", kinds_from_ci(wf))

    def test_precommit_office_drift_hook_classified(self) -> None:
        cfg = """
repos:
  - repo: local
    hooks:
      - id: office-drift
        name: office-drift (pre-push)
        entry: bash -c 'scripts/gen-office.sh && git diff --exit-code'
"""
        self.assertIn("office-drift", kinds_from_precommit(cfg))

    def test_ci_office_drift_without_precommit_is_harmful_drift(self) -> None:
        wf = """
jobs:
  office-drift:
    steps:
      - run: scripts/gen-office.sh
"""
        cfg = """
repos:
  - repo: local
    hooks:
      - id: ruff
"""
        harmful, _ = compute_drift(kinds_from_precommit(cfg), kinds_from_ci(wf))
        self.assertIn("office-drift", harmful)

    def test_ci_office_drift_with_precommit_mirror_no_drift(self) -> None:
        wf = """
jobs:
  office-drift:
    steps:
      - run: scripts/gen-office.sh
"""
        cfg = """
repos:
  - repo: local
    hooks:
      - id: office-drift
        entry: bash -c 'scripts/gen-office.sh'
"""
        harmful, _ = compute_drift(kinds_from_precommit(cfg), kinds_from_ci(wf))
        self.assertNotIn("office-drift", harmful)


class MermaidKind(unittest.TestCase):
    """#787: the mermaid render gate must be a classified kind so the sync-drift
    gate DEMANDS a pre-commit mirror of the CI render job (an un-mirrored gate
    lets a non-rendering diagram fail only at PR time)."""

    def test_ci_mermaid_run_step_classified(self) -> None:
        wf = """
jobs:
  mermaid-render:
    steps:
      - run: npm install -g @mermaid-js/mermaid-cli@11.12.0
      - run: python3 scripts/check-mermaid.py
"""
        self.assertIn("mermaid", kinds_from_ci(wf))

    def test_precommit_mermaid_hook_classified(self) -> None:
        cfg = """
repos:
  - repo: local
    hooks:
      - id: mermaid-render
        name: mermaid-render (pre-push)
        entry: python3 scripts/check-mermaid.py
"""
        self.assertIn("mermaid", kinds_from_precommit(cfg))

    def test_ci_mermaid_without_precommit_is_harmful_drift(self) -> None:
        wf = """
jobs:
  mermaid-render:
    steps:
      - run: python3 scripts/check-mermaid.py
"""
        cfg = """
repos:
  - repo: local
    hooks:
      - id: ruff
"""
        harmful, _ = compute_drift(kinds_from_precommit(cfg), kinds_from_ci(wf))
        self.assertIn("mermaid", harmful)

    def test_ci_mermaid_with_precommit_mirror_no_drift(self) -> None:
        wf = """
jobs:
  mermaid-render:
    steps:
      - run: python3 scripts/check-mermaid.py
"""
        cfg = """
repos:
  - repo: local
    hooks:
      - id: mermaid-render
        entry: python3 scripts/check-mermaid.py
"""
        harmful, _ = compute_drift(kinds_from_precommit(cfg), kinds_from_ci(wf))
        self.assertNotIn("mermaid", harmful)


class HeadcountBudgetKind(unittest.TestCase):
    """#841: the persona-roster headcount gate must be a classified kind so the
    sync-drift gate DEMANDS a pre-commit mirror of the CI budget job (an
    un-mirrored gate lets roster drift fail only at PR time) — same #684
    contract as the memory-budget kind."""

    def test_ci_headcount_budget_run_step_classified(self) -> None:
        wf = """
jobs:
  headcount-budget:
    steps:
      - run: python3 .claude/lib/headcount_budget.py .
"""
        self.assertIn("headcount-budget", kinds_from_ci(wf))

    def test_precommit_headcount_budget_hook_classified(self) -> None:
        cfg = """
repos:
  - repo: local
    hooks:
      - id: headcount-budget
        name: headcount-budget (pre-push)
        entry: python3 .claude/lib/headcount_budget.py .
"""
        self.assertIn("headcount-budget", kinds_from_precommit(cfg))

    def test_ci_headcount_budget_without_precommit_is_harmful_drift(self) -> None:
        wf = """
jobs:
  headcount-budget:
    steps:
      - run: python3 .claude/lib/headcount_budget.py .
"""
        cfg = """
repos:
  - repo: local
    hooks:
      - id: ruff
"""
        harmful, _ = compute_drift(kinds_from_precommit(cfg), kinds_from_ci(wf))
        self.assertIn("headcount-budget", harmful)

    def test_ci_headcount_budget_with_precommit_mirror_no_drift(self) -> None:
        wf = """
jobs:
  headcount-budget:
    steps:
      - run: python3 .claude/lib/headcount_budget.py .
"""
        cfg = """
repos:
  - repo: local
    hooks:
      - id: headcount-budget
        entry: python3 .claude/lib/headcount_budget.py .
"""
        harmful, _ = compute_drift(kinds_from_precommit(cfg), kinds_from_ci(wf))
        self.assertNotIn("headcount-budget", harmful)


class DockerfileBasePinKind(unittest.TestCase):
    """#735: the dockerfile-base-pin charter-prose→code gate must be a classified
    kind so the sync-drift gate DEMANDS a pre-commit mirror of the CI lint job (an
    un-mirrored gate lets an unpinned base image fail only at PR time)."""

    def test_ci_dockerfile_base_pin_run_step_classified(self) -> None:
        wf = """
jobs:
  dockerfile-base-pin:
    steps:
      - run: python3 .claude/lib/check_dockerfile_base_pin.py $files
"""
        self.assertIn("dockerfile-base-pin", kinds_from_ci(wf))

    def test_precommit_dockerfile_base_pin_hook_classified(self) -> None:
        cfg = """
repos:
  - repo: local
    hooks:
      - id: dockerfile-base-pin
        name: dockerfile-base-pin
        entry: python3 .claude/lib/check_dockerfile_base_pin.py
"""
        self.assertIn("dockerfile-base-pin", kinds_from_precommit(cfg))

    def test_ci_dockerfile_base_pin_without_precommit_is_harmful_drift(self) -> None:
        wf = """
jobs:
  dockerfile-base-pin:
    steps:
      - run: python3 .claude/lib/check_dockerfile_base_pin.py $files
"""
        cfg = """
repos:
  - repo: local
    hooks:
      - id: ruff
"""
        harmful, _ = compute_drift(kinds_from_precommit(cfg), kinds_from_ci(wf))
        self.assertIn("dockerfile-base-pin", harmful)

    def test_ci_dockerfile_base_pin_with_precommit_mirror_no_drift(self) -> None:
        wf = """
jobs:
  dockerfile-base-pin:
    steps:
      - run: python3 .claude/lib/check_dockerfile_base_pin.py $files
"""
        cfg = """
repos:
  - repo: local
    hooks:
      - id: dockerfile-base-pin
        entry: python3 .claude/lib/check_dockerfile_base_pin.py
"""
        harmful, _ = compute_drift(kinds_from_precommit(cfg), kinds_from_ci(wf))
        self.assertNotIn("dockerfile-base-pin", harmful)


class FixtureRealismKind(unittest.TestCase):
    """#735: the fixture-realism charter-prose→code gate must be a classified kind
    so the sync-drift gate DEMANDS a pre-commit mirror of the CI lint job (an
    un-mirrored gate lets an un-voweled Arabic fixture fail only at PR time)."""

    def test_ci_fixture_realism_run_step_classified(self) -> None:
        wf = """
jobs:
  fixture-realism:
    steps:
      - run: python3 .claude/lib/check_fixture_realism.py $files
"""
        self.assertIn("fixture-realism", kinds_from_ci(wf))

    def test_precommit_fixture_realism_hook_classified(self) -> None:
        cfg = """
repos:
  - repo: local
    hooks:
      - id: fixture-realism
        name: fixture-realism
        entry: python3 .claude/lib/check_fixture_realism.py
"""
        self.assertIn("fixture-realism", kinds_from_precommit(cfg))

    def test_ci_fixture_realism_without_precommit_is_harmful_drift(self) -> None:
        wf = """
jobs:
  fixture-realism:
    steps:
      - run: python3 .claude/lib/check_fixture_realism.py $files
"""
        cfg = """
repos:
  - repo: local
    hooks:
      - id: ruff
"""
        harmful, _ = compute_drift(kinds_from_precommit(cfg), kinds_from_ci(wf))
        self.assertIn("fixture-realism", harmful)

    def test_ci_fixture_realism_with_precommit_mirror_no_drift(self) -> None:
        wf = """
jobs:
  fixture-realism:
    steps:
      - run: python3 .claude/lib/check_fixture_realism.py $files
"""
        cfg = """
repos:
  - repo: local
    hooks:
      - id: fixture-realism
        entry: python3 .claude/lib/check_fixture_realism.py
"""
        harmful, _ = compute_drift(kinds_from_precommit(cfg), kinds_from_ci(wf))
        self.assertNotIn("fixture-realism", harmful)


class SkillGraphqlPaginationKind(unittest.TestCase):
    """#888/#893: the skill-markdown GraphQL over-cap lint must be a classified kind
    so the sync-drift gate DEMANDS a pre-commit mirror of the CI lint job (an
    un-mirrored gate lets a `first: > 100` over-cap reintroduce the silent
    zero-row read that made `/board-audit` treat every issue as an orphan)."""

    def test_ci_skill_graphql_pagination_run_step_classified(self) -> None:
        wf = """
jobs:
  skill-graphql-pagination:
    steps:
      - run: python3 .claude/lib/lint_skill_graphql_pagination.py $files
"""
        self.assertIn("skill-graphql-pagination", kinds_from_ci(wf))

    def test_precommit_skill_graphql_pagination_hook_classified(self) -> None:
        cfg = """
repos:
  - repo: local
    hooks:
      - id: skill-graphql-pagination
        name: skill-graphql-pagination
        entry: python3 .claude/lib/lint_skill_graphql_pagination.py
"""
        self.assertIn("skill-graphql-pagination", kinds_from_precommit(cfg))

    def test_ci_skill_graphql_pagination_without_precommit_is_harmful_drift(self) -> None:
        wf = """
jobs:
  skill-graphql-pagination:
    steps:
      - run: python3 .claude/lib/lint_skill_graphql_pagination.py $files
"""
        cfg = """
repos:
  - repo: local
    hooks:
      - id: ruff
"""
        harmful, _ = compute_drift(kinds_from_precommit(cfg), kinds_from_ci(wf))
        self.assertIn("skill-graphql-pagination", harmful)

    def test_ci_skill_graphql_pagination_with_precommit_mirror_no_drift(self) -> None:
        wf = """
jobs:
  skill-graphql-pagination:
    steps:
      - run: python3 .claude/lib/lint_skill_graphql_pagination.py $files
"""
        cfg = """
repos:
  - repo: local
    hooks:
      - id: skill-graphql-pagination
        entry: python3 .claude/lib/lint_skill_graphql_pagination.py
"""
        harmful, _ = compute_drift(kinds_from_precommit(cfg), kinds_from_ci(wf))
        self.assertNotIn("skill-graphql-pagination", harmful)


class BuildKindTightening(unittest.TestCase):
    """#576: runtime `docker build` / `docker buildx` steps are image-MOVING,
    not a build-QUALITY gate a local pre-commit hook can mirror — they must
    NOT classify as the `build` kind, or any docker-image repo gets a
    permanent un-mirrorable drift. Real build-quality gates still register."""

    def test_docker_buildx_not_build_kind(self) -> None:
        wf = """
jobs:
  publish:
    steps:
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Build and push
        run: docker buildx build --push -t img:latest .
"""
        self.assertNotIn("build", kinds_from_ci(wf))

    def test_bare_docker_build_not_build_kind(self) -> None:
        self.assertNotIn("build", kinds_from_ci("      - run: docker build -t img .\n"))

    def test_real_build_quality_gates_still_detected(self) -> None:
        # Structural parse classifies ONLY a step's run:/uses: value, never its
        # name: — so the build-quality markers are exercised in run position. (A
        # build gate named purely via `- name: build-and-validate` with an
        # unrelated run is intentionally NOT a `build` kind now; that name-only
        # match was the false-positive class #748 removes — see
        # FalsePositiveDemo below.)
        for line in (
            "      - run: ./scripts/build-and-validate.sh\n",
            "      - run: ./scripts/build-and-test.sh\n",
            "      - run: npm run build\n",
        ):
            with self.subTest(line=line):
                self.assertIn("build", kinds_from_ci(line))

    def test_docker_publish_workflow_has_no_build_drift(self) -> None:
        # End-to-end: a publish-only workflow (docker buildx) against a config
        # that does NOT mirror a build kind produces NO harmful drift.
        wf = """
jobs:
  publish:
    steps:
      - run: docker buildx build --push -t img .
"""
        cfg = """
repos:
  - repo: local
    hooks:
      - id: ruff
"""
        harmful, _ = compute_drift(kinds_from_precommit(cfg), kinds_from_ci(wf))
        self.assertNotIn("build", harmful)


class MultiLineRunBlockScanning(unittest.TestCase):
    """#577: tools invoked on a CONTINUATION line of a multi-line `run: |` /
    `run: >` block must be classified — else the gate has a silent blind spot
    where a future `ruff`/`mypy` expressed multi-line drops out of the mirror
    check."""

    def test_pipe_block_continuation_lines_classified(self) -> None:
        wf = """
jobs:
  security-audit:
    steps:
      - name: audit
        run: |
          uv sync
          uv run pip-audit
"""
        self.assertIn("pip-audit", kinds_from_ci(wf))

    def test_multiple_tools_in_one_block(self) -> None:
        wf = """
jobs:
  checks:
    steps:
      - name: lint+type+test
        run: |
          ruff check .
          mypy src/
          pytest -q
"""
        kinds = kinds_from_ci(wf)
        self.assertEqual(
            kinds & {"ruff-lint", "mypy", "pytest"},
            {"ruff-lint", "mypy", "pytest"},
        )

    def test_folded_block_scalar_also_scanned(self) -> None:
        # `run: >` (folded) and chomping indicators (`|-`) open a block too.
        wf = """
jobs:
  x:
    steps:
      - run: >-
          mypy src/
"""
        self.assertIn("mypy", kinds_from_ci(wf))

    def test_block_ends_at_dedented_sibling_key(self) -> None:
        # A less-indented sibling key (here `uses:` + its `with:`) closes the
        # block — its `fetch-depth` body must not leak a spurious classification
        # and the block's own `ruff check` is still caught.
        wf = """
jobs:
  x:
    steps:
      - name: a
        run: |
          ruff check .
      - name: b
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
"""
        kinds = kinds_from_ci(wf)
        self.assertIn("ruff-lint", kinds)

    def test_single_line_run_unaffected(self) -> None:
        # Regression: the common single-line `run:` form still classifies.
        wf = """
jobs:
  x:
    steps:
      - run: ruff check .
      - run: mypy .
"""
        kinds = kinds_from_ci(wf)
        self.assertEqual(kinds & {"ruff-lint", "mypy"}, {"ruff-lint", "mypy"})

    def test_comment_in_block_not_classified(self) -> None:
        # A commented continuation line inside the block is not a real
        # invocation and must not register.
        wf = """
jobs:
  x:
    steps:
      - run: |
          # pytest is mentioned here but commented out
          echo hi
"""
        self.assertNotIn("pytest", kinds_from_ci(wf))


class DriftDirection(unittest.TestCase):
    def test_ci_enforced_not_local_is_harmful(self) -> None:
        harmful, stricter = compute_drift(
            precommit_kinds={"ruff-lint"},
            ci_kinds={"ruff-lint", "mypy", "pytest"},
        )
        self.assertEqual(harmful, {"mypy", "pytest"})
        self.assertEqual(stricter, set())

    def test_local_not_ci_is_stricter_only(self) -> None:
        harmful, stricter = compute_drift(
            precommit_kinds={"ruff-lint", "gitleaks"},
            ci_kinds={"ruff-lint"},
        )
        self.assertEqual(harmful, set())
        self.assertEqual(stricter, {"gitleaks"})

    def test_perfect_mirror_no_drift(self) -> None:
        harmful, stricter = compute_drift(
            precommit_kinds={"ruff-lint", "ruff-format", "mypy"},
            ci_kinds={"ruff-lint", "ruff-format", "mypy"},
        )
        self.assertEqual(harmful, set())
        self.assertEqual(stricter, set())


class RealParentRepoHasNoDrift(unittest.TestCase):
    """The parent noorinalabs-main config must mirror its CI kinds — this is
    the gate running against the very repo that ships it."""

    def test_parent_precommit_mirrors_parent_ci(self) -> None:
        precommit = _REPO_ROOT / ".pre-commit-config.yaml"
        ci = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(precommit.is_file(), "parent must have a pre-commit config")
        self.assertTrue(ci.is_file(), "parent must have ci.yml")
        harmful, _ = check_repo(precommit, [ci])
        self.assertEqual(
            harmful,
            set(),
            f"parent pre-commit must mirror CI; missing locally: {sorted(harmful)}",
        )

    def test_parent_precommit_mirrors_all_workflows(self) -> None:
        # The CLI gate globs ALL workflow files, so the parent must have no
        # harmful drift across the full set — in particular docs.yml carries the
        # cspell + actionlint jobs (#684/#571). This is the gate exactly as the
        # `Pre-commit ⇄ CI sync-drift gate` CI job runs it.
        precommit = _REPO_ROOT / ".pre-commit-config.yaml"
        wf_dir = _REPO_ROOT / ".github" / "workflows"
        ci_paths = sorted(wf_dir.glob("*.y*ml"))
        self.assertTrue(ci_paths, "parent must have workflow files")
        harmful, _ = check_repo(precommit, ci_paths)
        self.assertEqual(
            harmful,
            set(),
            f"parent pre-commit must mirror ALL CI workflows; missing locally: {sorted(harmful)}",
        )

    def test_parent_ci_enforces_cspell(self) -> None:
        # Guard against the docs.yml cspell job being removed/renamed without the
        # mirror+kind being revisited: the kind must actually appear in CI.
        # Workflows are independent YAML documents, so we union per-file kinds
        # (structural parse cannot concatenate them into one parse — duplicate
        # top-level keys would either raise or silently drop a document).
        wf_dir = _REPO_ROOT / ".github" / "workflows"
        ci_kinds: set[str] = set()
        for p in wf_dir.glob("*.y*ml"):
            if p.is_file():
                ci_kinds |= kinds_from_ci(p.read_text(encoding="utf-8"))
        self.assertIn("cspell", ci_kinds)


# ---------------------------------------------------------------------------
# Reference copy of the OLD line-scanner (verbatim from main @ a7d7b2e), kept
# ONLY so the #748 D3 tests can prove (a) byte-for-byte kind-set parity with the
# pre-structural-parse classifier across real configs and (b) the precise
# false-positive class the structural parse removes. Production code no longer
# contains any of this; do not import it elsewhere.
# ---------------------------------------------------------------------------
_OLD_KIND_PATTERNS = {
    "ruff-format": ("ruff-format", "ruff format"),
    "ruff-lint": ("ruff check", "id: ruff", "- ruff"),
    "mypy": ("mypy",),
    "pytest": ("pytest",),
    "eslint": ("eslint",),
    "typescript": ("tsc", "typecheck", "type-check", "astro check"),
    "prettier": ("prettier",),
    "terraform-fmt": ("terraform fmt", "terraform_fmt", "id: terraform"),
    "gitleaks": ("gitleaks",),
    "actionlint": ("actionlint",),
    "pip-audit": ("pip-audit", "pip audit"),
    "build": ("build-and-validate", "build-and-test", "npm run build"),
    "cspell": ("cspell", "spellcheck", "streetsidesoftware/cspell"),
    # Kept in lock-step with the production _KIND_PATTERNS so the OLD-vs-NEW
    # parity proof stays valid as new kinds are added (cf. memory-budget, #733).
    "memory-budget": ("memory-budget", "memory_budget"),
    "headcount-budget": ("headcount-budget", "headcount_budget"),
    "doc-freshness": ("doc-freshness", "doc_freshness"),
    "office-drift": ("office-drift", "gen-office"),
    "mermaid": ("mermaid", "check-mermaid"),
    "dockerfile-base-pin": ("check_dockerfile_base_pin", "dockerfile-base-pin"),
    "fixture-realism": ("check_fixture_realism", "fixture-realism"),
    "skill-graphql-pagination": (
        "lint_skill_graphql_pagination",
        "skill-graphql-pagination",
    ),
}
_OLD_RUN_BLOCK_OPEN_RE = re.compile(r"^(?P<indent>\s*)-?\s*run:\s*[|>][+\-0-9]*\s*$")


def _old_classify_line(line: str) -> set:
    low = line.lower()
    kinds: set = set()
    if any(p in low for p in _OLD_KIND_PATTERNS["ruff-format"]):
        kinds.add("ruff-format")
    for kind, patterns in _OLD_KIND_PATTERNS.items():
        if kind == "ruff-format":
            continue
        if kind == "ruff-lint":
            if ("ruff format" in low) and ("ruff check" not in low and "id: ruff" not in low):
                continue
        if any(p in low for p in patterns):
            kinds.add(kind)
    return kinds


def _old_kinds_from_precommit(text: str) -> set:
    kinds: set = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if re.match(r"^(-\s*)?(id|entry|name|repo):", line) or line.startswith("- "):
            kinds |= _old_classify_line(line)
    return kinds


def _old_kinds_from_ci(text: str) -> set:
    kinds: set = set()
    run_block_indent = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if run_block_indent is not None:
            if stripped:
                line_indent = len(raw) - len(raw.lstrip())
                if line_indent <= run_block_indent:
                    run_block_indent = None
                else:
                    if not stripped.startswith("#"):
                        kinds |= _old_classify_line(stripped)
                    continue
        if not stripped or stripped.startswith("#"):
            continue
        block_match = _OLD_RUN_BLOCK_OPEN_RE.match(raw)
        if block_match is not None:
            run_block_indent = len(block_match.group("indent"))
            continue
        if (
            "run:" in stripped
            or stripped.startswith("- run:")
            or "uses:" in stripped
            or stripped.startswith("-")
        ):
            kinds |= _old_classify_line(stripped)
    return kinds


# Documented expected kind-set (#748 D3 parity proof). The ONLY repo whose
# configs are version-controlled IN this repo is the parent (noorinalabs-main),
# so it is the only one with a stable, hardcoded kind snapshot. The NEW
# structural classifier must reproduce this snapshot exactly, and must equal the
# retired OLD line-scanner on it — the false-positive class the structural parse
# removes is therefore LATENT (no real config exercises a step-name/comment
# false-match today, proven directly by FalsePositiveDemo).
#
# Child repos are deliberately NOT given a documented snapshot (#816, relates to
# #744). They are independent gitignored repos whose local checkout beside the
# parent can sit on any branch / lag origin by an arbitrary amount, so a
# hardcoded snapshot of THEIR files is not a property of this repo: it false-fails
# the parent-only pre-push suite whenever a child checkout is stale (the original
# #816 symptom — isnad-graph/user-service checked out behind origin). Present
# child configs are instead covered by the checkout-INDEPENDENT OLD==NEW parity
# invariant (test_new_equals_old_on_present_configs), which needs no snapshot and
# is correct regardless of how stale the local child checkouts are.
_EXPECTED_KINDS = {
    ".": {
        "precommit": {
            "actionlint",
            "cspell",
            "dockerfile-base-pin",
            "doc-freshness",
            "fixture-realism",
            "headcount-budget",
            "memory-budget",
            "mermaid",
            "mypy",
            "office-drift",
            "pytest",
            "ruff-format",
            "ruff-lint",
            "skill-graphql-pagination",
        },
        "ci": {
            "actionlint",
            "cspell",
            "dockerfile-base-pin",
            "doc-freshness",
            "fixture-realism",
            "headcount-budget",
            "memory-budget",
            "mermaid",
            "mypy",
            "office-drift",
            "pytest",
            "ruff-format",
            "ruff-lint",
            "skill-graphql-pagination",
        },
    },
}

# Child repo directory names, used ONLY to LOCATE sibling configs for the
# checkout-independent OLD==NEW parity scan — never to assert a hardcoded kind
# snapshot (see the _EXPECTED_KINDS note above). A child is scanned when its
# checkout is present beside the parent and skipped when absent, so this can
# never false-fail in the parent-less CI checkout. Keep in step with the
# Repository Map in the org CLAUDE.md.
_CHILD_REPO_DIRS = (
    "noorinalabs-isnad-graph",
    "noorinalabs-user-service",
    "noorinalabs-deploy",
    "noorinalabs-design-system",
    "noorinalabs-data-acquisition",
    "noorinalabs-isnad-ingest-platform",
    "noorinalabs-landing-page",
)


class ParityAcrossRealConfigs(unittest.TestCase):
    """(#748 D3 deliverable c) The NEW structural classifier must produce the
    documented kind-set for the parent config, and must equal the OLD line
    scanner on every config present — proving the refactor is behavior
    preserving.

    Two distinct guarantees, deliberately decoupled (#816):

    * Documented-snapshot — asserted for the PARENT ONLY, whose configs are
      version-controlled in this repo so the snapshot is checkout-stable.
    * OLD==NEW parity — asserted for every PRESENT config (parent always; each
      sibling child repo when its checkout is present beside the parent). This
      is checkout-INDEPENDENT: it compares two classifiers on the same bytes, so
      it holds no matter how stale a child checkout is. Children are skipped when
      absent (this repo's CI checkout has none), so neither test false-fails."""

    def _documented_roots(self):
        # Only repos with a checkout-stable documented snapshot: the parent.
        for repo, expected in _EXPECTED_KINDS.items():
            root = _REPO_ROOT if repo == "." else _REPO_ROOT / repo
            pc = root / ".pre-commit-config.yaml"
            if pc.is_file():
                yield repo, root, pc, expected

    def _present_config_roots(self):
        # Every present config: the parent (always) plus any sibling child repo
        # physically checked out beside it. Child repos live at <REPO_ROOT>/<repo>/
        # and are present only in a full multi-repo checkout, never in CI.
        candidates = [(".", _REPO_ROOT)]
        candidates += [(repo, _REPO_ROOT / repo) for repo in _CHILD_REPO_DIRS]
        for repo, root in candidates:
            pc = root / ".pre-commit-config.yaml"
            if pc.is_file():
                yield repo, root, pc

    def test_new_matches_documented_expectations(self) -> None:
        seen = []
        for repo, root, pc, expected in self._documented_roots():
            seen.append(repo)
            new_pc = kinds_from_precommit(pc.read_text(encoding="utf-8"))
            new_ci: set = set()
            wf_dir = root / ".github" / "workflows"
            for w in sorted(wf_dir.glob("*.y*ml")):
                new_ci |= kinds_from_ci(w.read_text(encoding="utf-8"))
            with self.subTest(repo=repo):
                self.assertEqual(new_pc, expected["precommit"], f"{repo} pre-commit kinds")
                self.assertEqual(new_ci, expected["ci"], f"{repo} CI kinds")
        self.assertIn(".", seen, "parent config must always be present and checked")

    def test_new_equals_old_on_present_configs(self) -> None:
        # Behavior-preservation: identical kind-sets to the retired line scanner
        # on every config present — the checkout-independent guarantee for child
        # repos (no hardcoded snapshot, so staleness cannot false-fail it).
        for repo, root, pc in self._present_config_roots():
            pc_text = pc.read_text(encoding="utf-8")
            wf_dir = root / ".github" / "workflows"
            new_ci: set = set()
            for w in sorted(wf_dir.glob("*.y*ml")):
                new_ci |= kinds_from_ci(w.read_text(encoding="utf-8"))
            # OLD scanner concatenated workflows into one scan (line-based, so
            # duplicate keys were harmless); reproduce that to compare fairly.
            old_ci_text = "\n".join(
                w.read_text(encoding="utf-8") for w in sorted(wf_dir.glob("*.y*ml"))
            )
            with self.subTest(repo=repo):
                self.assertEqual(
                    kinds_from_precommit(pc_text),
                    _old_kinds_from_precommit(pc_text),
                    f"{repo} pre-commit: NEW must equal OLD",
                )
                self.assertEqual(
                    new_ci,
                    _old_kinds_from_ci(old_ci_text),
                    f"{repo} CI: NEW must equal OLD",
                )


class FalsePositiveDemo(unittest.TestCase):
    """(#748 D3 deliverable d) The defect the structural parse fixes: the OLD
    line scanner classified a tool token appearing in a step `name:` or a YAML
    `#` comment as a real check; the NEW parser inspects only `run:`/`uses:`
    values, so it does not. These synthetic configs do not occur in any real
    repo today (parity proves it), which is why the fix is latent — but they ARE
    the class of false-positive the structural parse makes impossible."""

    def test_tool_token_in_step_name_is_a_false_positive_old_not_new(self) -> None:
        # A step NAMED after ruff, doing something unrelated. The classifier must
        # key off run:, which here is not a ruff invocation.
        wf = """
jobs:
  ci:
    steps:
      - name: run ruff check on the changed files
        run: echo "this step only prints a message"
"""
        self.assertIn("ruff-lint", _old_kinds_from_ci(wf))  # OLD false-matches the name
        self.assertNotIn("ruff-lint", kinds_from_ci(wf))  # NEW ignores name:

    def test_build_token_in_step_name_is_a_false_positive_old_not_new(self) -> None:
        wf = """
jobs:
  deploy:
    steps:
      - name: build-and-validate the rendered manifest
        run: terraform validate
"""
        self.assertIn("build", _old_kinds_from_ci(wf))  # OLD false-matches the name
        self.assertNotIn("build", kinds_from_ci(wf))  # NEW ignores name:

    def test_tool_token_in_yaml_comment_is_a_false_positive_old_not_new(self) -> None:
        # The `# ruff check ...` is a YAML comment: the parser strips it, so the
        # run value is just `echo hi`. The OLD line scanner saw the raw line.
        wf = """
jobs:
  ci:
    steps:
      - run: echo hi  # ruff check goes here once we wire it up
"""
        self.assertIn("ruff-lint", _old_kinds_from_ci(wf))  # OLD false-matches the comment
        self.assertNotIn("ruff-lint", kinds_from_ci(wf))  # NEW: comment is gone after parse


class RobustnessAgainstFalseGreen(unittest.TestCase):
    """A parse failure or a non-structural document must FAIL LOUDLY, never
    degrade into an empty kind-set (a silent false-green that hides drift)."""

    def test_malformed_yaml_raises_not_empty(self) -> None:
        bad = "jobs:\n  ci:\n    steps:\n      - run: x\n  : : bad\n"
        with self.assertRaises(ValueError):
            kinds_from_ci(bad)

    def test_scalar_document_raises_not_empty(self) -> None:
        # A workflow that parses to a bare scalar is malformed; refuse to call it
        # "no checks".
        with self.assertRaises(ValueError):
            kinds_from_ci("just a string, not a mapping or list")

    def test_empty_document_is_genuinely_empty(self) -> None:
        # A truly empty/whitespace/comment-only file has no checks to mirror.
        self.assertEqual(kinds_from_ci(""), set())
        self.assertEqual(kinds_from_ci("\n  \n"), set())
        self.assertEqual(kinds_from_precommit("# only a comment\n"), set())

    def test_precommit_malformed_yaml_raises(self) -> None:
        with self.assertRaises(ValueError):
            kinds_from_precommit("repos:\n  - repo: x\n   bad-indent: y\n")

    def test_main_exits_2_on_unparseable_ci(self) -> None:
        # End-to-end: the CLI must return 2 (error), not 0 (clean), when a
        # workflow cannot be parsed — a false-green here would defeat the gate.
        import tempfile

        from pre_commit_ci_sync import main

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".pre-commit-config.yaml").write_text(
                "repos:\n  - repo: local\n    hooks:\n      - id: ruff\n",
                encoding="utf-8",
            )
            wf_dir = root / ".github" / "workflows"
            wf_dir.mkdir(parents=True)
            (wf_dir / "ci.yml").write_text("this: is: not: valid: yaml:\n", encoding="utf-8")
            self.assertEqual(main(["prog", str(root)]), 2)


if __name__ == "__main__":
    unittest.main()
