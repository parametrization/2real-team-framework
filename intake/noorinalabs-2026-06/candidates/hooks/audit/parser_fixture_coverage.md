# Parser-Fixture Coverage Audit — noorinalabs-main

**Audit date:** 2026-05-07
**Auditor:** Wanjiku Mwangi (Technical Program Manager, Staff)
**Wave:** P3W7
**Meta-issue:** noorinalabs/noorinalabs-main#300
**Charter ref:** `.claude/team/charter/hooks.md` § Parser-Fixture Coverage Requirements

---

## Summary

| Metric | Count |
|--------|-------|
| Hook files at top level (`.claude/hooks/*.py`) | 31 |
| Parser-class hooks | 14 |
| Non-parser hooks | 17 |
| Parser-class hooks WITH fixture coverage | 9 |
| Parser-class hooks WITH GAPS | 5 |
| Gap count (distinct uncovered shapes) | 17 |
| In-wave Pattern G fixes | 0 |
| Backport issues filed | 5 |

**Coverage rate (parser-class hooks):** 9/14 = 64% have at least some coverage
**Gap rate:** 5/14 = 36% of parser-class hooks have fixture gaps

> **Note on hook count reconciliation:** Meta-issue #300 cites 48 hooks for noorinalabs-main. This audit finds 31 hooks under `.claude/hooks/*.py`. The discrepancy is likely the meta-issue counting all hooks across child repos accessible from the orchestrator (7 repos × ~6-7 hooks average ≈ 48) rather than the noorinalabs-main top-level count only. This Tier-1 scope is per-repo; 31 is the correct noorinalabs-main count.

---

## Parser-Class Definition (charter hooks.md)

A hook is **parser-class** if it performs input parsing of any of:
- Shell argv / shlex tokenization
- Git output / ref names / commit messages
- GitHub Actions YAML (`on.pull_request.paths:` etc.)
- PR body markdown (Requestor/Requestee/TechDebt fields)
- JSON API responses from gh api / gh pr view
- Transcript JSONL (session transcript parsing)
- Carry-forward marker patterns in skill args

A hook is **non-parser** if it performs only:
- Simple config/env-var checks
- Regex allowlist matching on a single known-shape input
- File hash computation
- Time/staleness checks
- Network calls to external APIs (Cloudflare, GHCR) without parsing structured input

---

## Hook Classification

### Non-Parser Hooks (17)

| Hook | Reason |
|------|--------|
| `_shell_parse.py` | Shared library (tested via consumers); not a hook itself |
| `annunaki_log.py` | Shared utility — appends JSONL records, no input parsing |
| `annunaki_monitor.py` | Pattern matching on stdout/stderr text; regex patterns, not structured parsing |
| `auto_add_issue_to_board.py` | Regex URL extraction from `gh issue create` stdout; single known shape |
| `block_gh_pr_review.py` | Simple regex match for `gh pr review` command; no structured parsing |
| `block_shutdown_without_retro.py` | Uses `_shell_parse.is_shutdown_request_message`; has full test coverage |
| `dispatcher.py` | Routing/orchestration only; no input parsing |
| `enforce_ontology_context.py` | String marker scan on Agent prompt text; no structured parsing |
| `no_worktree_self_delete.py` | Uses `_shell_parse` tokenizer; full test coverage |
| `ontology_tracker.py` | SHA256 hash computation; path filtering via prefix/substring match |
| `session_handoff.py` | Collects git/gh state via subprocess; no structured input parsing |
| `session_start.py` | Reads JSON status files; emits directives; no command-shape parsing |
| `suggest_generic_prompt.py` | File path string matching; no input parsing |
| `validate_lockfile_paths.py` | Regex scan for `/tmp/` and `file:/` in file contents; simple pattern |
| `validate_vps_host.py` | IP range lookup; no command-structure parsing |
| `validate_wave_context.py` | Reads JSON status file; no command-shape parsing |
| `warn_ghcr_image.py` | Regex match for `gh workflow run`; simple string extraction |

---

### Parser-Class Hooks (14)

---

#### 1. `_shell_parse.py` — Core Shell Parser Library

| Attribute | Value |
|-----------|-------|
| **Input kind** | Shell argv (shlex tokenization), heredoc stripping, git subcommand extraction, gh subcommand extraction |
| **Fixtures present** | `tests/test_shell_parse.py` |
| **Test count** | 41 tests |
| **Priority** | HIGH — foundation for 7+ hooks; parser bugs here propagate everywhere |

**Input shapes known:**
- Simple single-command (`git commit -m "msg"`)
- Quoted argument values (`-c user.name="Firstname Lastname"`)
- Heredoc bodies (`$(cat <<'EOF' ... EOF)`)
- Compound commands with `&&`, `||`, `|`, `;`
- Leading env-var assignments (`FOO=bar git commit`)
- `-c=key=value` equals-form git globals
- Unbalanced quotes (shlex parse failure → `None`)

**Gaps:**
- Nested command substitutions (`$(cmd1 $(cmd2))`) — only top-level heredocs stripped
- Windows-style CRLF line endings in heredoc bodies
- Tab-indented heredoc (`<<-EOF`) with mixed-indent content

**Gap priority:** MEDIUM — edge cases not observed in production; no filed bugs yet.

---

#### 2. `validate_commit_identity.py` — Git Commit Identity Validation

| Attribute | Value |
|-----------|-------|
| **Input kind** | git argv (shlex), `-c user.name=` / `-c user.email=` flag extraction, roster JSON, cross-repo `cd` path detection |
| **Fixtures present** | `tests/test_validate_commit_identity.py` |
| **Test count** | 19 tests |
| **Priority** | HIGH — security-relevant; W6 sibling bug #287 |

**Input shapes known:**
- `git -c user.name="Name" -c user.email="email" commit -m "msg"`
- Cross-repo: `cd /path && git ... commit`
- Heredoc body containing `git commit` (should NOT match)
- Parse failure with commit-looking text (fail-closed)
- Repeated `-c user.name=` (last-wins semantics)

**Gaps (production-discovered shapes):**
- `#287` — backslash line continuation in commit command (e.g., `git \\\n -c user.name="Name" \\\n commit`). Filed as backport issue — **OPEN** (Tier-2 work item).
- Multi-line `git commit -F /tmp/msg.txt` where identity flags span compound command (roster loaded from wrong repo)
- `git -c user.name='Name With Apostrophe' commit` — single-quoted name with shlex interactions

**Gap priority:** HIGH — `#287` is a known production bug. Single-quote variant is medium.

---

#### 3. `block_no_verify.py` — Block --no-verify Flag

| Attribute | Value |
|-----------|-------|
| **Input kind** | git argv (shlex), `--no-verify` / `-n` flag detection in commit/push segments |
| **Fixtures present** | `tests/test_block_no_verify.py` |
| **Test count** | 12 tests |
| **Priority** | MEDIUM |

**Input shapes known:**
- `git commit --no-verify` (long form)
- `git commit -n` (short form, commit-only)
- `git push --no-verify` (long form)
- Command with `-c` globals before commit
- Heredoc body mentioning `--no-verify` (should NOT match)
- `gh issue` body mentioning `--no-verify` (should NOT match)
- `echo "..."` mentioning phrase (should NOT match)

**Gaps:**
- `git commit --no-verify` with `=` form (if ever used)
- Chained command where `--no-verify` appears in a later segment after a non-git command

**Gap priority:** LOW — all observed production shapes covered; gaps are purely theoretical.

---

#### 4. `block_git_config.py` — Block git config Writes

| Attribute | Value |
|-----------|-------|
| **Input kind** | git argv (shlex), `git config` subcommand detection, read-only flag checking |
| **Fixtures present** | `tests/test_block_git_config.py` |
| **Test count** | 14 tests |
| **Priority** | MEDIUM |

**Input shapes known:**
- `git config user.name "Name"` (write)
- `git config --global user.email "..."` (write)
- `git -C /path config ...` (with `-C` global)
- `git -c user.name=X commit` (per-commit flag — NOT a config write)
- `--get`, `--list`, `-l` read-only flags (allowed)
- Heredoc body mentioning `git config` (should NOT match)
- `grep "git config" /tmp/x` (should NOT match)
- `echo "..."` mentioning phrase (should NOT match)

**Gaps:**
- `git config --add` form (additive config; currently likely blocked, but not explicitly tested)
- `git config --unset` form (deletion, should be blocked)
- `git config --edit` form (launches editor; should be blocked but currently not specifically tested)

**Gap priority:** LOW — `--add`/`--unset`/`--edit` are not observed in production; all common write patterns covered.

---

#### 5. `block_stale_tmp_message_file.py` — Block Stale /tmp Body Files

| Attribute | Value |
|-----------|-------|
| **Input kind** | Shell command segment detection (`git commit`, `gh pr/issue create/comment/edit`), `-F`/`--file`/`--body-file` flag + path extraction |
| **Fixtures present** | `tests/test_block_stale_tmp_message_file.py` |
| **Test count** | 21 tests |
| **Priority** | MEDIUM — surfaced in production (2026-05-03 ontology-rebuild incident) |

**Input shapes known:**
- `git commit -F /tmp/msg.txt` (fresh → allow; stale → block)
- `git commit --file /tmp/msg.txt`
- `gh pr create --body-file /tmp/body.md`
- `gh issue create --body-file /tmp/body.md`
- `gh pr comment N --body-file /tmp/body.md`
- `gh issue comment N --body-file /tmp/body.md`
- `gh pr create --body-file /tmp/body.md` (edit form)
- Non-/tmp paths (should NOT match)
- Inline `--body "..."` / `--message` (should NOT match)

**Gaps:**
- `git commit --body-file /tmp/...` (not a real git flag; probably fine to not cover)
- `gh pr edit N --body-file /tmp/...` — `gh pr edit` variant; not in current test corpus
- Multi-segment command where the `commit -F` is after a `&&` with a quoted multi-word path

**Gap priority:** LOW — primary production shapes covered; gaps are theoretical edge cases.

---

#### 6. `validate_labels.py` — Validate gh issue create Labels

| Attribute | Value |
|-----------|-------|
| **Input kind** | Shell argv (shlex), `--label`/`-l` flag extraction, `--repo`/`-R` flag extraction, comma-separated label values |
| **Fixtures present** | `tests/test_validate_labels.py` |
| **Test count** | 29 tests |
| **Priority** | MEDIUM |

**Input shapes known:**
- `gh issue create --label tech-debt`
- `gh issue create -l tech-debt`
- `gh issue create --label "tech-debt,phase-3"` (comma-separated)
- `--repo OWNER/REPO` flag
- `-R OWNER/REPO` flag
- Body content containing example label flags (should NOT extract as labels)
- Code blocks inside body mentioning labels (should NOT extract)

**Gaps:**
- `gh issue create --label=tech-debt` (equals-form; shlex produces `--label=tech-debt` as one token; label extraction may not handle this)
- Multiple repos in the same command (chained `gh issue create`)

**Gap priority:** MEDIUM — `--label=` equals form is plausible and may silently skip validation.

---

#### 7. `validate_branch_freshness.py` — Branch Freshness Before PR

| Attribute | Value |
|-----------|-------|
| **Input kind** | Shell argv (shlex), `--repo`/`-R`, `--base`/`-B`, `--head`/`-H` flag extraction, OWNER:branch cross-fork prefix stripping |
| **Fixtures present** | `tests/test_validate_branch_freshness.py` |
| **Test count** | 40 tests |
| **Priority** | MEDIUM |

**Input shapes known:**
- `gh pr create --base main --head feature-branch`
- `--repo OWNER/REPO` flag (long and short)
- `--head OWNER:branch` cross-fork form (OWNER: prefix stripped)
- `--base`/`--head` with equals form
- Implicit repo resolution from cwd remote URL
- `--base/-B`, `--head/-H` short forms

**Gaps:**
- `gh pr create` with no flags (all defaults; uses cwd — tested but API path may have edge cases)
- Quoted flag values with spaces inside (e.g., `--head "feature branch with spaces"`)
- `gh pr ready N` triggering the branch freshness check

**Gap priority:** LOW — core flag shapes well covered; edge cases are low-probability.

---

#### 8. `validate_pr_review.py` — Two-Reviewer Enforcement

| Attribute | Value |
|-----------|-------|
| **Input kind** | Shell command shape (regex), `gh pr merge` detection, PR number extraction, `--repo` extraction, charter-format PR body parsing (Requestor/Requestee/RequestOrReplied/TechDebt fields), branch head ref parsing for author lastname, JSON API responses |
| **Fixtures present** | `tests/test_validate_pr_review.py` |
| **Test count** | 55 tests |
| **Priority** | HIGH — W6 production bug #294 (wave-branch head_ref misparse) |

**Input shapes known:**
- `gh pr merge N` (direct number)
- `gh pr merge` (current branch)
- `gh pr merge --repo OWNER/REPO N`
- `--admin` override (short-circuit allow)
- Charter comment body: `Requestor:`, `Requestee:`, `RequestOrReplied:`, `TechDebt:`
- Markdown bold form: `**Requestor:**`, `**TechDebt:**`
- `Approved`, `ChangesRequested`, `Changes Requested`, `Changes` verdict values
- `Request`, `Reply`, `Replied` non-verdict values
- `deployments/phase-{N}/wave-{M}` wave-branch head ref (W6 bug #294 — fixed)
- `wave-bootstrap` label → Single-Reviewer Exception
- TechDebt issue numbers (`TechDebt: #15, #16`)

**Gaps:**
- **Reviewer dedup key collision:** Two reviewers with same lastname but different first initials (e.g., `A.Smith` and `B.Smith`) — `_name_lastname` returns identical lastname; both still count as distinct reviewers IF full names differ (correct), but the lowercase full-name dedup key may produce unexpected behavior with very similar names
- **Non-standard branch formats:** `deployments/phase-{N}/wave-{M}` is now covered (#294), but branches named directly without `{Initial}.{Lastname}` separator (e.g., hotfix branches `hotfix/some-fix`) → `branch_author_lastname` returns `None` → `check_comment_reviews` called with empty sentinel; behavior is to admit any reviewer — not explicitly tested
- **Paginated comments:** Hook fetches `per_page=100` but does not paginate; PRs with >100 comments may miss later reviews
- **Requestee field with parenthetical:** `Requestee: Nadia Khoury (Program Director)` — parenthetical stripping tested, but multi-word parentheticals with unicode or nested parens not covered

**Gap priority:** HIGH for pagination gap (production-scale PRs can exceed 100 comments); MEDIUM for others.

---

#### 9. `validate_pr_ci_status.py` — CI Status Before Merge

| Attribute | Value |
|-----------|-------|
| **Input kind** | Shell command shape (regex), `gh pr merge` detection, PR number extraction, `--repo` extraction, GitHub API `statusCheckRollup` JSON parsing |
| **Fixtures present** | `tests/test_validate_pr_ci_status.py` |
| **Test count** | 28 tests |
| **Priority** | MEDIUM |

**Input shapes known:**
- `gh pr merge N`, `gh pr merge --repo OWNER/REPO`
- `--admin` override, `--auto` flag (pending → warn-allow)
- `FAILURE`, `CANCELLED`, `TIMED_OUT`, `ACTION_REQUIRED` conclusions → block
- `SUCCESS`, `SKIPPED`, `NEUTRAL` conclusions → allow
- Chromatic `NEUTRAL` → pending (allowlist)
- `IN_PROGRESS`, `QUEUED`, `WAITING`, `REQUESTED`, `PENDING` statuses → pending

**Gaps:**
- `statusCheckRollup` with empty array `[]` — "no checks" state looks clean to this hook but may indicate uncovered workflow (root cause of deploy#153); currently a documented known gap
- Check names with unicode or very long names that may trip `check_name()` truncation

**Gap priority:** MEDIUM — empty rollup gap is documented; no fixture pinning the `[]` behavior.

---

#### 10. `validate_workflow_paths_coverage.py` — Workflow Paths Orphan Detection

| Attribute | Value |
|-----------|-------|
| **Input kind** | Shell command shape (regex), `gh pr create`/`gh pr ready` detection, `--repo`/`--base`/`--head` extraction, GitHub Actions YAML parsing (`on.pull_request.paths:` via regex state machine), fnmatch glob matching |
| **Fixtures present** | `tests/test_validate_workflow_paths_coverage.py` |
| **Test count** | 45 tests |
| **Priority** | HIGH — W6 production bug #289 (bare `on.pull_request:` misparse) |

**Input shapes known:**
- `gh pr create [--repo R] [--base B] [--head H]`
- `gh pr ready N`
- Chained commands with env-var prefixes
- Workflow YAML forms: `on: [push, pull_request]` (inline)
- `on: pull_request:` (block, no paths filter) → covers all
- `on: pull_request: paths: [...]` (inline list form)
- `on: pull_request: paths:` (block list form)
- `on: pull_request: paths-ignore:` (ignore form)
- `on:` at non-zero indent
- `pull_request:` as last child of `on:` without paths key (W6 bug #289 — fixed)
- fnmatch glob `**.github/workflows/**`

**Gaps:**
- **YAML anchor/alias forms** (`&anchor`, `*alias`) — not handled; parser returns `(set(), False)` = no coverage signal = fail-open. No fixture for anchored paths.
- **Flow-mapping form** (`on: {pull_request: {paths: [...]}}`) — not handled by current line-by-line parser
- **Multi-document YAML** (rare in workflows but possible) — parser starts from line 0 only
- **`paths:` filter with only negative patterns** (all entries are `!glob`) — currently treated as having paths but no positive globs; coverage check may over-block

**Gap priority:** MEDIUM — anchors/flow-maps are rare in this org's workflow style; the current parser handles all observed shapes. File as tech-debt for hardening.

---

#### 11. `validate_review_comment_format.py` — Requestor/Requestee Swap Detection

| Attribute | Value |
|-----------|-------|
| **Input kind** | Shell command segment detection (`gh pr comment`), PR body extraction (heredoc, single-quoted, double-quoted string forms), `Requestor:`/`Requestee:`/`RequestOrReplied:` field detection, branch name parsing for author lastname |
| **Fixtures present** | **NONE** |
| **Test count** | 0 |
| **Priority** | HIGH — parser-class hook with NO tests; branch name parsing is a known failure-prone pattern |

**Input shapes known (from code analysis):**
- `gh pr comment N --body "..."` (double-quoted)
- `gh pr comment N --body '...'` (single-quoted)
- `gh pr comment N --body "$(cat <<'EOF'\n...\nEOF)"` (heredoc)
- Branch name format `{Initial}.{Lastname}/...` → extract lastname

**Gaps (ALL gaps — no tests exist):**
- Heredoc delimiter variations (`<<EOF`, `<<-EOF`, `<<"EOF"`)
- `--body-file /tmp/...` (body from file; hook may not inspect file contents)
- Branch name with dash separator `{Initial}.{Lastname}-{number}-{name}` (vs slash)
- Env-var prefixed `gh pr comment` command
- `gh pr comment` with `--repo OWNER/REPO` flag (cross-repo PR comment)
- PR number from URL form (`https://github.com/.../pull/123`)
- Requestee field with parenthetical role: `Requestee: Nadia Khoury (Program Director)`

**Gap priority:** **HIGH** — zero coverage on a parser-class hook that controls merge traffic.

---

#### 12. `validate_wave_audit.py` — Wave Lifecycle Skill Gate

| Attribute | Value |
|-----------|-------|
| **Input kind** | `tool_input.skill` exact matching, `tool_input.args` carry-forward marker parsing (regex), `cross-repo-status.json` JSON parsing for wave label, `wave-<N>` / `phase-<N>` ref name parsing |
| **Fixtures present** | `tests/test_validate_wave_audit.py` |
| **Test count** | 26 tests |
| **Priority** | MEDIUM |

**Input shapes known:**
- `wave-wrapup`, `wave-retro`, `handoff` skill names
- Other skill names (should NOT match)
- Bash tool with wave-skill substrings (should NOT match)
- Carry-forward markers: `carry-forward:`, `carry forward:`, `## Carry-forward`, `## Carry forward`, `#N → dest`, `#N -> dest`
- No active wave (cross-repo-status.json `wave_active: false`) → allow with warning
- `current_wave: "wave-10"` → label `p2-wave-10`
- `current_wave: "wave-7"` with `phase: "phase-3"` → label `p3-wave-7`

**Gaps:**
- `current_wave` as integer rather than string (e.g., `"current_wave": 10`) — `re.fullmatch(r"wave-(\d+)", str(current))` handles via `str()` but the resulting label `wave-10` without phase prefix may not match actual labels
- Carry-forward args containing the marker in a code block (backtick-fenced) — hook may treat code block content as carry-forward intent
- `cross-repo-status.json` with `current_wave` as `null` — `str(None)` = `"None"` which won't match wave-N pattern → correct behavior but not explicitly tested

**Gap priority:** LOW — current shapes well covered; edge cases are not production-observed.

---

#### 13. `enforce_librarian_consulted.py` — Ontology Librarian Gate

| Attribute | Value |
|-----------|-------|
| **Input kind** | Transcript JSONL parsing (line-by-line JSON objects), `message.content` parsing (str or `list[dict]` block forms), `tool_use` block extraction for `Skill` tool calls, sentinel file hash computation |
| **Fixtures present** | `tests/test_enforce_librarian_consulted.py` |
| **Test count** | 29 tests |
| **Priority** | MEDIUM |

**Input shapes known:**
- Transcript JSONL with `type: "user"` / `type: "assistant"` objects
- Content as plain string with librarian markers
- Content as list with `type: "text"` blocks
- Content as list with `type: "tool_use"` blocks (`name: "Skill"`, `input.skill: "ontology-librarian"`)
- Sentinel file (`cwd | sha1sum | cut -c1-16`) attesting librarian consultation
- Allow-listed paths: `/tmp/**`, `**/memory/*.md`, `**/MEMORY.md`, `~/.claude/**`, `.claude/annunaki/*`

**Gaps:**
- Transcript JSONL with non-standard `type` values (e.g., `"system"`, `"tool_result"`) — should skip gracefully; not explicitly tested
- Content list with nested blocks (e.g., `tool_result` containing `text` blocks with librarian markers)
- Sentinel file with stale mtime (does the sentinel expire? Code shows no expiry check — potential false acceptance after long sessions)
- `file_path` with symlinks resolving to allow-listed paths but not matching string prefix

**Gap priority:** LOW — primary shapes covered; edge cases are theoretical.

---

#### 14. `validate_edit_completion.py` — Edit Error Sentinel

| Attribute | Value |
|-----------|-------|
| **Input kind** | Tool response `is_error` field (top-level and in `content` list), transcript JSONL parsing for acknowledgment detection (Read/Bash cat/head/tail/grep/less/ls), sentinel JSONL file format |
| **Fixtures present** | `tests/test_validate_edit_completion.py` |
| **Test count** | 39 tests |
| **Priority** | MEDIUM |

**Input shapes known:**
- `tool_response` with `is_error: true` at top level
- `tool_response` with `content: [{is_error: true, ...}]` list form
- `tool_response` with non-zero Bash exit code
- Bash acknowledgment: `cat /path`, `head /path`, `tail /path`, `grep ... /path`, `less /path`, `ls /path`
- `Read` tool_use on the errored file path
- `SendMessage` with body containing `"edit-error acknowledged" + file_path`
- Multi-error sentinel (multiple unacknowledged edits)
- Session-ID-keyed sentinel files

**Gaps:**
- Sentinel JSONL with malformed lines (partial writes from concurrent hook invocations)
- Bash acknowledgment with quoted path containing spaces (`cat "/path with spaces/file"`)
- Acknowledgment via `grep -r pattern /dir/` (directory path, not exact file path)
- `Write` tool_use on the errored file as acknowledgment (currently only `Read` counts)

**Gap priority:** LOW — primary shapes well covered; edge cases are theoretical.

---

## Coverage Table Summary

| Hook | Input Kind | Shapes Known | Fixture | Gaps | Priority |
|------|-----------|-------------|---------|------|----------|
| `_shell_parse.py` | Shell argv, heredoc | 7 shapes | ✓ (41 tests) | Nested subst, CRLF, tab-indent heredoc | MEDIUM |
| `validate_commit_identity.py` | git argv, roster JSON, cd-path | 5 shapes | ✓ (19 tests) | #287 backslash-cont, single-quote name | HIGH |
| `block_no_verify.py` | git argv | 8 shapes | ✓ (12 tests) | `=` form, late-segment position | LOW |
| `block_git_config.py` | git argv | 8 shapes | ✓ (14 tests) | `--add`, `--unset`, `--edit` forms | LOW |
| `block_stale_tmp_message_file.py` | Shell segment, `-F`/`--body-file` | 9 shapes | ✓ (21 tests) | `gh pr edit`, multi-segment quoted path | LOW |
| `validate_labels.py` | Shell argv (shlex) | 7 shapes | ✓ (29 tests) | `--label=` equals form | MEDIUM |
| `validate_branch_freshness.py` | Shell argv (shlex), gh flags | 6 shapes | ✓ (40 tests) | No-flag defaults, quoted-space values | LOW |
| `validate_pr_review.py` | Shell cmd, PR body markdown, JSON | 12 shapes | ✓ (55 tests) | Pagination >100 comments, non-std branches | HIGH |
| `validate_pr_ci_status.py` | Shell cmd, GitHub API JSON | 8 shapes | ✓ (28 tests) | Empty `statusCheckRollup: []` | MEDIUM |
| `validate_workflow_paths_coverage.py` | Shell cmd, GitHub Actions YAML | 10 shapes | ✓ (45 tests) | Anchors, flow-maps, multi-doc YAML | MEDIUM |
| `validate_review_comment_format.py` | Shell cmd, PR body (3 quote forms) | 7 shapes | **NONE** | ALL GAPS — zero coverage | **HIGH** |
| `validate_wave_audit.py` | Skill args, cross-repo-status JSON | 7 shapes | ✓ (26 tests) | Integer `current_wave`, null handling | LOW |
| `enforce_librarian_consulted.py` | Transcript JSONL, content blocks | 6 shapes | ✓ (29 tests) | Tool_result content, sentinel expiry | LOW |
| `validate_edit_completion.py` | Tool response JSON, transcript JSONL | 8 shapes | ✓ (39 tests) | Quoted-space paths, Write acknowledgment | LOW |

---

## Prioritized Gap List

### HIGH priority — file backport issues

1. **`validate_review_comment_format.py` — ZERO coverage** (backport issue filed: #[see below])
   - All 7 input shapes uncover
   - Branch name dash-separator variant uncover
   - `--body-file` form uncovered

2. **`validate_pr_review.py` — pagination gap** (backport issue filed: #[see below])
   - `per_page=100` limit not paginated; PRs with >100 comments may miss reviews
   - `statusCheckRollup: []` not a validate_pr_review gap (belongs to validate_pr_ci_status)

3. **`validate_commit_identity.py` — #287 backslash-continuation** (Tier-2 open work item)
   - Already tracked as main#287; no new issue needed

### MEDIUM priority — file backport issues

4. **`validate_labels.py` — `--label=` equals form** (backport issue filed: #[see below])
   - `gh issue create --label=tech-debt` may silently skip validation

5. **`validate_workflow_paths_coverage.py` — YAML anchor/flow-map forms** (backport issue filed: #[see below])
   - Workflow files using anchors or flow-mapping syntax would fail-open silently

6. **`validate_pr_ci_status.py` — empty statusCheckRollup** (backport issue filed: #[see below])
   - `[]` array = no checks = looks clean; documented gap but no pinning fixture

### LOW priority — not filing issues (carry to regular backlog)

- `_shell_parse.py`: nested subst, CRLF, tab-indent heredoc
- `block_no_verify.py`: equals form, late-segment position
- `block_git_config.py`: `--add`, `--unset`, `--edit` forms
- `block_stale_tmp_message_file.py`: `gh pr edit` variant
- `validate_branch_freshness.py`: no-flag defaults, quoted-space values
- `validate_wave_audit.py`: integer `current_wave`
- `enforce_librarian_consulted.py`: tool_result content, sentinel expiry
- `validate_edit_completion.py`: quoted-space paths, Write acknowledgment

---

## Pattern G Observations (in-wave bugs)

**None found during this audit pass.** All parser logic reviewed appeared correct for observed production input shapes. The high-priority gaps are absence-of-tests rather than incorrect behavior.

The `validate_review_comment_format.py` zero-coverage finding is the most concerning — it has no tests at all, meaning any parser bug would be invisible until production discovery.

---

## Backport Issues Filed

| # | Hook | Gap | Issue |
|---|------|-----|-------|
| 1 | `validate_review_comment_format.py` | Zero fixture coverage — all 7 input shapes | #302 |
| 2 | `validate_pr_review.py` | Comment pagination >100 not covered | #303 |
| 3 | `validate_labels.py` | `--label=` equals-form silently skips validation | #304 |
| 4 | `validate_workflow_paths_coverage.py` | YAML anchor and flow-mapping forms | #306 |
| 5 | `validate_pr_ci_status.py` | Empty `statusCheckRollup: []` not pinned | #307 |
