# Noorina Labs — Contributor Toolchain

What a fresh clone needs installed, the shell we run under, and which tool to
reach for when you need to scan or rewrite code structurally rather than by
regex. This is the org-level companion to each child repo's own `CLAUDE.md`;
it documents the tools `noorinalabs-main` `.claude/` + CI already depend on
(inventory from [#748](https://github.com/noorinalabs/noorinalabs-main/issues/748))
plus the structural-tooling guidance from
[#759](https://github.com/noorinalabs/noorinalabs-main/issues/759) (shell) and
[#760](https://github.com/noorinalabs/noorinalabs-main/issues/760) (`ast-grep`).

The matching org-wide conventions live in
[`../ontology/conventions.md`](../ontology/conventions.md) (§ Shell environment,
§ Structural search & replace); this doc is the install-and-examples form.

---

## Shell environment: zsh

> **The org dev environment's shell — interactive AND the agent Bash tool — is
> `zsh`, not bash.** Commands you run are executed by `zsh`. Bash-only idioms
> silently break or behave differently. Write zsh-safe (ideally POSIX-portable)
> commands.

This lesson previously lived only in project memory
(`.claude/memory/feedback_zsh_shell_environment.md`); per the enforcement
hierarchy a convention that lives only in a memory file decays, so it is
documented here and codified in `../ontology/conventions.md`.

**Do / don't:**

- **Don't** use `declare -A name` associative arrays or `${!arr[@]}` key
  expansion — `zsh` rejects/treats them differently (the P3W12
  `(eval):3: bad substitution` failure that started this). Use paired strings
  with a `while IFS=: read -r k v` loop, or plain newline-delimited lists.
- **Do** quote URLs and globs. An unquoted argument containing `?` or `*`
  (a query string, a wildcard) is pathname-expanded by `zsh` and fails with
  `no matches found`. Quote it: `gh api "repos/o/r/issues?state=open"`.
- **Remember** `zsh` arrays are 1-indexed and don't word-split unquoted
  variables by default — prefer explicit loops over relying on bash
  word-splitting.
- **Default** to POSIX-portable constructs (`for x in …; do`, `case`, `[ … ]`)
  — they run identically under `zsh` and bash.
- **When** a one-off genuinely needs bash, invoke `bash -c '…'` explicitly and
  leave a comment saying why, rather than assuming the default shell is bash.

---

## Prerequisites — install commands

Pick the line that matches your platform / package manager. The local dev box
is Linux (WSL2); macOS contributors use Homebrew. Most Python tooling is
provisioned per-repo by `uv`/`pre-commit`, and most Node tooling by
`npm`/`corepack`, so the table's "How it's installed" column tells you when you
need to install a binary yourself versus when a repo bootstraps it for you.

### Org-level — what `noorinalabs-main` `.claude/` + CI invoke

| Tool | Purpose | How it's installed |
|------|---------|--------------------|
| `git` | branch/remote/commit checks (hooks, CI) | system / OS package manager |
| `gh` | GitHub API via CLI (issues, PRs, project board) | `brew install gh` · `apt install gh` |
| `python3` | run `.claude/` hooks + lib + skills (3.12+) | system / `uv python install` |
| `uv` | Python package manager | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `pre-commit` | local hook framework (mirrors CI) | `uv tool install pre-commit` · `pipx install pre-commit` |
| `ruff` | Python lint + format (pinned `v0.15.11`) | provisioned by `pre-commit`; standalone `uv tool install ruff` |
| `mypy` | Python typecheck | provisioned at pre-push (`language: system`); `uv tool install mypy` |
| `pytest` | hook + lib + skill test suites | system Python (`uv pip install pytest`) |
| `actionlint` | workflow YAML lint (pinned `v1.7.12`) | provisioned by `pre-commit`; `brew install actionlint` |
| `shellcheck` | shell lint — **must be on PATH** so `actionlint` runs its embedded shellcheck instead of silently skipping | `brew install shellcheck` · `apt install shellcheck` |
| `cspell` | spellcheck authored prose (pinned `v8.4.0`) | provisioned by `pre-commit` (`language: node`) |
| `lychee` | internal markdown link-check (CI only) | `cargo install lychee` · `brew install lychee` |
| `markdownlint-cli2` | markdown lint (CI only) | `npm install -g markdownlint-cli2` |

> `ruff`, `actionlint`, and `cspell` are provisioned by `pre-commit` from the
> pinned `rev` in `.pre-commit-config.yaml` — install `pre-commit` and run
> `pre-commit install && pre-commit install --hook-type pre-push` once and they
> come with it. `mypy`/`pytest` run as `language: system` at pre-push, so they
> use your system Python — install them there. `lychee` + `markdownlint-cli2`
> are not in `pre-commit` yet (they run in `docs.yml` CI); install them if you
> want to reproduce those gates locally.

### Child-repo build / test / lint / deploy toolchains

Each child repo bootstraps its own toolchain; this is the cross-repo superset
so you know what a given clone will ask for.

| Tool | Repos | Purpose | Install |
|------|-------|---------|---------|
| `ruff` / `mypy` / `pytest` | ig, us, da, ingest, deploy | Python lint/typecheck/test | via `uv` per repo |
| `uv` | ig, us, da, ingest | Python package manager | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `pip-audit` | ig, da | dependency vuln scan | `uv tool install pip-audit` |
| `npm` / `npx` | ds, ig, lp | Node package manager / runner | ships with Node |
| `eslint` / `prettier` / `tsc` | ds, ig, lp | JS/TS lint / format / typecheck | `npm install` (devDeps) per repo |
| `vitest` | ds, ig | JS/TS unit tests | `npm install` (devDeps) |
| `vite` / `astro` | ig, lp | frontend bundler / static site gen | `npm install` (devDeps) |
| `playwright` | ig | E2E browser tests | `npx playwright install` |
| `actionlint` | all 7 | workflow lint (pinned `1.7.12`) | via `pre-commit` per repo |
| `gitleaks` | all 7 | secret scan (pinned `8.24.3`) | `brew install gitleaks` |
| `cspell` / `lychee` / `markdownlint` | all 7 | docs lint/spell/link | see org table above |
| `terraform` | deploy | IaC | `brew install terraform` |
| `docker` / `compose` | da, ig, us, ingest, deploy, lp | containers | Docker Desktop / `docker` engine |
| `trivy` | deploy | image vuln scan | `brew install trivy` |
| `cosign` | deploy | image signing | `brew install cosign` |
| `shfmt` | (proposed) | shell formatter (completes `shellcheck`) | `brew install shfmt` |

Repo keys: `ig` = isnad-graph, `us` = user-service, `da` = data-acquisition,
`ingest` = isnad-ingest-platform, `ds` = design-system, `lp` = landing-page,
`deploy` = deploy.

---

## Structural & AST tooling

Every code/YAML/shell-scanning gate we run today is Python regex / line-scan,
and that is our recurring failure class: a regex misses a syntactic variant, so
"local clean" diverges from reality (`feedback_lint_gate_cover_all_syntactic_forms`,
the nine-issue `_shell_parse.py` bug trail). Structural tools match the **syntax
tree**, not the text, so they are correct-by-construction for structure-dependent
work.

**Rule of thumb:** reach for a structural tool when the thing you're matching
depends on code/markup *structure* (a call form, a YAML key path, an AST node);
keep `rg`/`sed`/`sd` for *literal* / line-oriented work.

### `ast-grep` — structural source-code search & replace

`ast-grep` is a tree-sitter structural search / lint / rewrite tool for
Python / TS / JS / bash. Use it for interactive code navigation and codemods
where `grep`/`sed` are syntactically blind — it matches the tree, so a single
rule catches the dotted **and** from-import call forms a regex would miss.

**Install:** `brew install ast-grep` · `cargo install ast-grep` ·
`npm install -g @ast-grep/cli` · `pipx install ast-grep-cli`

> ⚠ **`sg` name collision — invoke it as `ast-grep`, never `sg`.**
> `/usr/bin/sg` is shadow-utils (`sg` = run-a-command-with-a-different-group-id),
> **not** `ast-grep`. A script, hook, or skill block that shells `sg …` silently
> runs shadow-utils instead. Always use the full binary name `ast-grep`.

**Worked example 1 — structural search (dotted call form):**

```bash
# every call to requests.get(...), regardless of argument shape or line breaks
ast-grep --lang python --pattern 'requests.get($$$ARGS)'
```

**Worked example 2 — match BOTH the dotted and the from-import form in one
rule** (the `lint_gate_cover_all_syntactic_forms` class a single regex misses):

```yaml
# find-json-load.yml
id: find-json-load
language: python
rule:
  any:
    - pattern: json.load($$$ARGS)   # import json;            json.load(f)
    - pattern: load($$$ARGS)        # from json import load;  load(f)
```

```bash
ast-grep scan --rule find-json-load.yml
```

**Worked example 3 — codemod (structural search + replace):**

```bash
# rename the deprecated logger.warn(...) to logger.warning(...) across the tree
ast-grep --lang python --pattern 'logger.warn($$$A)' \
         --rewrite 'logger.warning($$$A)' --update-all
```

Metavariables: `$NAME` matches one node, `$$$NAME` matches zero-or-more
(argument lists, statement blocks). Patterns are real code, so reformatting and
line breaks don't defeat the match the way they defeat a regex.

### Other structural tools (recommended in #748)

Documented here so the choice is discoverable; adoption depth (documented
convenience vs. a wired proof-of-pattern gate) is tracked in #748 / #760.

| Tool | For | Install |
|------|-----|---------|
| `yq` (mikefarah) | real YAML query/eval — kills the `re.match`-over-workflow-lines class (`feedback_sync_gate_build_kind_false_match`) | `brew install yq` · `go install github.com/mikefarah/yq/v4@latest` |
| `semgrep` | semantic pattern lint + autofix + SARIF; policy hooks as declarative rules | `pipx install semgrep` · `brew install semgrep` |
| `sd` | literal-by-default find/replace (no `sed` regex foot-guns) — the literal companion to `ast-grep` | `cargo install sd` · `brew install sd` |
| `gron` | JSON → greppable assignments; deterministic JSON assertions | `brew install gron` · `go install github.com/tomnomnom/gron@latest` |
| `difftastic` (`difft`) | structural/AST diff — review correctness, ignores reformatting noise | `cargo install difftastic` · `brew install difftastic` |
| `comby` | language-aware structural search/replace for cross-repo codemods | `brew install comby` |
| `shfmt` | shell formatter (completes `shellcheck`) | `brew install shfmt` |
| `bashlex` | Python lib — proper Bash AST for the identity/shell hooks (wired in #757) | `pip install bashlex` |

---

## Document generation (markdown → MS Office)

Microsoft Office documents (Word `.docx`, PowerPoint `.pptx`, Excel `.xlsx`)
are **generated from markdown**, which stays the single source of truth — the
office binaries are build artifacts and are never hand-edited
([#767](https://github.com/noorinalabs/noorinalabs-main/issues/767)). Generated
files live under [`office/`](office/README.md); the source→target mapping is the
manifest [`office/office-docs.json`](office/office-docs.json).

**Engine — `pandoc`.** One tool renders both `.docx` and `.pptx` natively from
GitHub-Flavored Markdown, so there is no per-format Python glue to maintain.
`.xlsx` is the exception: spreadsheets are tabular data, not prose, so they use
`openpyxl` from a structured source rather than pandoc (wired when a first
spreadsheet source exists). `python-docx` / `python-pptx` remain available as
escape hatches when a specific document needs finer control than pandoc gives.

**Install `pandoc`:**

| Platform | Command |
|----------|---------|
| Debian / Ubuntu / WSL | `apt install pandoc` |
| macOS | `brew install pandoc` |
| Any (no system package) | `pip install pypandoc-binary` — ships a pandoc binary the generator auto-detects |

`scripts/gen-office.sh` resolves pandoc from `$PANDOC`, then `PATH`, then the
pip-bundled `pypandoc` binary, so `make docs` works with whichever of the above
you have.

**Regenerate:**

```sh
make docs                 # regenerate every enabled doc in the manifest
scripts/gen-office.sh     # same, without make
```

Output is reproducible: the embedded OOXML timestamp is pinned to each source's
last git commit time (`SOURCE_DATE_EPOCH`). A CI check that flags a committed
binary as drifted from its markdown is a tracked follow-up (it needs the pandoc
version pinned in CI, since bytes differ across pandoc versions).

---

## See also

- [`../ontology/conventions.md`](../ontology/conventions.md) — § Shell
  environment (zsh) and § Structural search & replace (the org-wide convention
  form of this doc).
- [`../CLAUDE.md`](../CLAUDE.md) — § Developer Tooling & Orchestration, § Shell
  environment: zsh.
- `.claude/memory/feedback_zsh_shell_environment.md` — the originating memory.
