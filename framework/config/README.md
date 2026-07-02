# Framework config (`framework.config.json`)

The single shared-config object every genericised artifact reads. Installed by
the bootstrapper at `<repo>/.claude/framework.config.json`. The authoritative,
fully-documented contract is **`framework.config.schema.json`** (each field
carries a `description` and `default`); `framework.config.example.json` is a
filled `meta-and-children` example. This file is the orientation.

## Minimal valid config

Everything except `version` has a default, so the smallest useful config is:

```json
{ "version": 1, "scm": { "provider": "github", "owner": "my-org" } }
```

Without `scm.owner`, the gh-calling hooks (the CI merge gate) run with reduced
capability but do not error.

## The fields you will most likely tune

| Key | Why you'd change it |
|-----|---------------------|
| `scm.owner` | Your GitHub org/user. Needed by every `gh`-calling hook. |
| `project.model` | `single-repo` vs `meta-and-children` (a meta-repo + child repos). |
| `shell` | Set `zsh` to activate the zsh bash-ism advisory. |
| `policy.reviewers_required` | The N-reviewer-before-merge threshold. |
| `policy.merge_model` | `wave-branch` vs `direct-to-main`. |
| `policy.admin_merge_exceptions` | The only `--admin` bypass classes the CI gate accepts (empty = none). |
| `ci.merge_requires_green` | Master switch for the CI merge gate. |
| `ci.empty_rollup_is_blocking` | Treat "no checks reported" as not-ready (recommended `true`). |
| `ci.neutral_pending_check_prefixes` | Services whose `NEUTRAL` means "review pending" (e.g. `["chromatic"]`). |
| `ci.tooling` | The full CI check-set the local⇄CI parity gate expects mirrored. |
| `hooks.pre_bash` / `hooks.post_bash` | Which checks run, in what order (the dispatcher seam). |
| `hooks.pre_push_commands` | Checks the enforce-mode pre-push git hook runs (read at push time; empty = pass). |

## How reads work

Hooks call `_framework_config.config(input_data).get("dotted.key", default)`.
The loader walks up from the tool-call cwd to find `.claude/framework.config.json`,
parses it, and merges it over the schema defaults — so an omitted key always
resolves to its documented default, and a malformed file fails open to defaults
(never crashes a hook). `config()` is cached per resolved path.

## Validation

`bootstrap.py` validates the config before writing: full JSON-Schema validation
if `jsonschema` is installed, else a structural sanity check (it is stdlib-only
by default). An invalid `version` is fatal; other problems are reported but
non-fatal.
