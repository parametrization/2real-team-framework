#!/usr/bin/env python3
"""PreToolUse hook: Validate git commit identity flags.

Opt-in commit-identity gate. When `identity.enforce` is true in the framework
config, every `git commit` must set its author via per-commit
`-c user.name=... -c user.email=...` flags (NEVER global/repo git config), and
the (name, email) pair must match a known team member from the roster. This
makes every commit attributable to a persona.

The hook is OFF by default: with `identity.enforce` false (the schema default)
`check()` returns None immediately and no enforcement happens. Enable it by
setting `identity.enforce: true` and wiring this module into `hooks.pre_bash`.

Roster
======

The roster is a flat JSON object mapping full name → email::

    { "Ada Lovelace": "team+Ada.Lovelace@example.com", ... }

Its repo-relative path comes from `identity.roster_source` (default
`.claude/team/roster.json`). A commit's `-c user.name`/`-c user.email` pair is
valid iff (name, email) matches a roster entry, OR the email is listed in
`identity.allow_emails` (e.g. the repo owner, who need not appear in the
roster).

Parent+child roster merge (meta-and-children model):
  When the repo whose roster is loaded is itself a child of another git repo
  that hosts the same roster file, the parent roster is loaded and merged with
  the child roster. Same-name entries in the child override the parent (child
  wins). Walk-up is limited to ONE level to avoid false positives in nested
  source trees. This lets meta-level coordinators commit in child repos without
  duplicating their entries into every child roster. The merge is keyed off the
  generic `roster_source` path, not any hard-coded repo name.

cwd / cd-target resolution:
  PreToolUse hooks need to know which repo a commit will land in. The target
  repo is resolved via `resolve_invocation_cwd` (a literal `cd <path> && git
  ...` prefix, else the tool-call cwd). If that target dir hosts its own roster
  it is used as the child repo; otherwise the config root (the directory holding
  the framework config) is used.

Indirect-exec bypass detection:
  PreToolUse hooks only see the literal outer Bash `command`. Wrappers that hide
  the real `git commit` from the outer-command tokenizer are detected pre-tokenize
  and BLOCKED::

      printf '<git-commit-cmd>' | bash        (also sh/zsh/dash/ksh; also echo)
      bash -c '<git-commit-cmd>'               (shell -c)
      bash <(echo '<git-commit-cmd>')          (process substitution)
      bash <<EOF...git commit...EOF            (heredoc body)
      bash <<<'git commit ...'                 (here-string)
      eval 'git commit ...'                    (shell builtin)
      bash <script-with-git-commit>            (extension-agnostic script read)

  Each detector returns the inner payload; if any payload looks like a git
  commit the command is blocked, since the identity flags cannot be inspected.

Structural Bash-AST parse:
  The direct `git commit` detector prefers a real Bash AST parse via bashlex
  (`_shell_parse.iter_command_segments_ast`) over the shlex tokenizer — a true
  grammar distinguishes a command-position `git commit` from the literal phrase
  inside a heredoc body / quoted arg / `--body` value, and surfaces commits
  hidden inside `$(...)` substitutions. bashlex is OPTIONAL: when absent (a bare
  zero-setup checkout) the hook prints one stderr warning and falls back to the
  shlex/regex path. The indirect-exec layer is unchanged — bashlex does not
  re-parse a shell's own `-c '...'` string arg, so those wrappers are still
  caught by the regex detectors that run first.

Fail-closed posture:
  This is a security-relevant matcher. On a tokenize failure it does NOT fail
  open: if the malformed command still looks like a git commit it is BLOCKED.

Exit codes:
  0 — allow (enforcement off, not a git commit, or identity is valid)
  2 — block (missing/invalid identity flags, OR an indirect-exec wrapper hiding
       a git commit from outer-command inspection)
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _framework_config import config  # noqa: E402
from _framework_log import log_pretooluse_block  # noqa: E402
from _shell_parse import (  # noqa: E402
    bashlex_available,
    extract_dash_c_pairs,
    find_git_subcommand,
    iter_command_segments,
    iter_command_segments_ast,
    resolve_invocation_cwd,
    strip_heredocs,
    tokenize,
)

# Emitted at most once per process when bashlex is unavailable so the degraded
# parse mode is visible rather than silent. Each PreToolUse invocation is its
# own short-lived process, so this is effectively once per checked command.
_DEGRADED_WARNED = False


def _warn_degraded_mode_once() -> None:
    """Print a single concise stderr warning that the structural parse is off."""
    global _DEGRADED_WARNED
    if _DEGRADED_WARNED:
        return
    _DEGRADED_WARNED = True
    print(
        "warning: bashlex not installed — shell-identity check running in degraded "
        "regex mode (install bashlex for structural Bash-AST parsing).",
        file=sys.stderr,
    )


# ============================================================================
# Roster loading
# ============================================================================


def _read_roster(roster_path: Path) -> dict[str, str]:
    """Read a roster JSON file, returning {} on any failure (fail-open)."""
    try:
        data = json.loads(roster_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    # Keep only name -> str-email entries (a flat object).
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def _load_merged_roster(repo_dir: Path, roster_source: str) -> dict[str, str]:
    """Load `repo_dir`'s roster, merged with its parent repo's roster if any.

    Parent detection (ONE level up only):
      1. `repo_dir/..` must be a directory containing `.git` (a git repo).
      2. `repo_dir/../<roster_source>` must be a file.
    If both hold, the parent roster is loaded and merged UNDER the child roster
    — child keys override parent keys, so a same-name entry in the child wins.
    Any OSError / malformed JSON at any step is swallowed; a broken parent
    roster must never block a child repo's valid commit.
    """
    child_roster = _read_roster(repo_dir / roster_source)

    try:
        parent_dir = repo_dir.parent
        parent_roster_path = parent_dir / roster_source
        if (
            parent_dir != repo_dir
            and (parent_dir / ".git").exists()
            and parent_roster_path.is_file()
        ):
            parent_roster = _read_roster(parent_roster_path)
        else:
            parent_roster = {}
    except OSError:
        parent_roster = {}

    # Child wins on key collision.
    return {**parent_roster, **child_roster}


def _config_root(cfg, input_data: dict) -> Path:
    """Repo root that hosts the framework config.

    The config loader's `path` is `<root>/.claude/framework.config.json`, so the
    root is `path.parent.parent`. When no config file was found, fall back to the
    invocation cwd.
    """
    if cfg.path is not None:
        return cfg.path.parent.parent
    return Path(resolve_invocation_cwd(input_data))


def _resolve_roster(cfg, input_data: dict, roster_source: str) -> dict[str, str]:
    """Resolve and load the merged roster for the repo the commit lands in.

    Resolution order for the repo dir:
      1. The invocation target (a literal `cd <path>` prefix, else the tool-call
         cwd) — used when it hosts its own `<roster_source>` (cross-repo commit
         into a child worktree).
      2. Otherwise the config root (`<root>` of the framework config).
    The chosen dir is then merged one level up (meta-and-children model).
    """
    target = Path(resolve_invocation_cwd(input_data)).expanduser()
    try:
        target = target.resolve()
    except OSError:
        pass

    if target.is_dir() and (target / roster_source).is_file():
        repo_dir = target
    else:
        repo_dir = _config_root(cfg, input_data)

    return _load_merged_roster(repo_dir, roster_source)


# ============================================================================
# Indirect-exec bypass detection
# ============================================================================

# Wrapper interpreters we recognise (POSIX shells operators may use as `-c`).
_INTERPRETERS = r"(?:bash|sh|zsh|dash|ksh)"

# printf/echo … | <interpreter>. Captures the printf/echo argument body.
_PIPE_TO_SHELL_RE = re.compile(
    r"\b(?:printf|echo)\b(?P<payload>.+?)\|\s*" + _INTERPRETERS + r"\b",
    re.DOTALL,
)

# <interpreter> -c '<payload>' or "<payload>" — captures the -c argument
# verbatim, including surrounding quotes (stripped before scanning).
_DASH_C_RE = re.compile(
    r"\b" + _INTERPRETERS + r"\s+-c\s+(?P<payload>(?P<q>['\"]).*?(?P=q)|\S+)",
    re.DOTALL,
)

# <interpreter> <(...) — process substitution. Captures the inner content.
_PROCESS_SUB_RE = re.compile(
    r"\b" + _INTERPRETERS + r"\s+<\(\s*(?P<payload>[^)]+?)\s*\)",
    re.DOTALL,
)

# <interpreter> <scriptpath> — extension-agnostic. Any token whose first char is
# not a flag (`-`), redirect (`<>|;&`), or process-substitution opener (`(`) is a
# candidate script path read for content inspection. The leading char class
# rejects `bash -c '…'` (first char is `-`).
_SCRIPT_INVOKE_RE = re.compile(
    r"\b" + _INTERPRETERS + r"\s+(?P<path>[^\s\-<>|;&(][^\s|;&<>]*)",
)

# <interpreter> <<DELIM ... DELIM (heredoc body fed as stdin to a shell). Must
# anchor on an interpreter; `cat <<EOF\ngit commit\nEOF` is data-only.
_HEREDOC_RE = re.compile(
    r"\b" + _INTERPRETERS + r"\b[^\n]*?<<-?\s*['\"]?(?P<delim>\w+)['\"]?[^\n]*\n"
    r"(?P<payload>.*?)\n\t*(?P=delim)\b",
    re.DOTALL,
)

# <interpreter> <<<'<payload>' (here-string) — same exec semantics as a heredoc.
_HERESTRING_RE = re.compile(
    r"\b" + _INTERPRETERS + r"\s+<<<\s*(?P<payload>(?P<q>['\"]).*?(?P=q)|\S+)",
    re.DOTALL,
)

# eval '<payload>' — shell builtin that re-parses + executes its argument string.
# Variable-substituted eval strings (`eval "$cmd"`) are not inspected (the
# substitution happens at shell-runtime, after the hook fires).
_EVAL_RE = re.compile(
    r"\beval\s+(?P<payload>(?P<q>['\"]).*?(?P=q)|\S+)",
    re.DOTALL,
)

# Inner-payload commit-shape: a simple `git ... commit` bridge bounded to a
# single segment via `[^;&|]`, with a path-suffix exclusion so `commit/foo`
# branch-paths don't false-match.
_INNER_COMMIT_RE = re.compile(
    r"\bgit\b[^;&|]*?\bcommit\b(?!\S*/)",
    re.DOTALL,
)


def _payload_looks_like_commit(payload: str) -> bool:
    """Return True if the (already-extracted) inner payload contains git commit."""
    if not payload:
        return False
    return bool(_INNER_COMMIT_RE.search(strip_heredocs(payload)))


def _strip_outer_quotes(s: str) -> str:
    """If `s` is wrapped in matching single or double quotes, strip one layer."""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def _read_script_if_safe(script_path: str, cwd: str | None) -> str | None:
    """Read script content for inspection. Returns None on any error.

    The path is resolved against `cwd` if relative. Reads are restricted to
    regular files under 256 KiB; anything larger is treated as "don't inspect"
    (the caller treats that as no payload extracted → no block).
    """
    try:
        p = Path(script_path)
        if not p.is_absolute() and cwd:
            p = (Path(cwd) / p).resolve()
        else:
            p = p.resolve()
        if not p.is_file():
            return None
        if p.stat().st_size > 256 * 1024:
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None


def _detect_indirect_commit(command: str, *, cwd: str | None = None) -> str | None:
    """Detect indirect-exec wrappers carrying a hidden git commit.

    Returns a short label describing the matched shape (used in the block
    message) when the inner payload looks like a git commit, else None.
    Pattern-only checks run before the script-path check, which needs disk I/O.
    """
    for m in _PIPE_TO_SHELL_RE.finditer(command):
        if _payload_looks_like_commit(m.group("payload")):
            return "printf/echo piped to shell"

    for m in _DASH_C_RE.finditer(command):
        if _payload_looks_like_commit(_strip_outer_quotes(m.group("payload"))):
            return "shell -c"

    for m in _PROCESS_SUB_RE.finditer(command):
        if _payload_looks_like_commit(m.group("payload")):
            return "process substitution"

    for m in _HEREDOC_RE.finditer(command):
        if _payload_looks_like_commit(m.group("payload")):
            return "heredoc"

    for m in _HERESTRING_RE.finditer(command):
        if _payload_looks_like_commit(_strip_outer_quotes(m.group("payload"))):
            return "here-string"

    for m in _EVAL_RE.finditer(command):
        if _payload_looks_like_commit(_strip_outer_quotes(m.group("payload"))):
            return "eval"

    for m in _SCRIPT_INVOKE_RE.finditer(command):
        content = _read_script_if_safe(m.group("path"), cwd)
        if content and _payload_looks_like_commit(content):
            return f"shell script ({m.group('path')})"

    return None


# ============================================================================
# Direct git-commit detection
# ============================================================================

_PARSE_FAILURE = object()  # sentinel: tokenize returned None


def _find_commit_segment(command: str) -> list[str] | None | object:
    """Find the `git ... commit ...` segment in `command`.

    Returns:
      - list[str]      — the commit segment tokens (allow identity validation)
      - None           — tokenize succeeded but no commit subcommand found
      - _PARSE_FAILURE — tokenize failed (unbalanced quotes); caller must use
                         the regex fallback (which fails CLOSED for commits)

    Prefers a structural bashlex AST parse; falls back to shlex tokenize +
    segment split (heredocs stripped first) when bashlex is unavailable or
    cannot parse the command.
    """
    if bashlex_available():
        ast_segments = iter_command_segments_ast(command)
        if ast_segments is not None:
            for segment in ast_segments:
                decoded = find_git_subcommand(segment)
                if decoded is None:
                    continue
                _globals, rest = decoded
                if rest and rest[0] == "commit":
                    return segment
            return None
        # bashlex present but could not parse → fall through to shlex/regex.
    else:
        _warn_degraded_mode_once()

    cleaned = strip_heredocs(command)
    tokens = tokenize(cleaned)
    if tokens is None:
        return _PARSE_FAILURE
    for segment in iter_command_segments(tokens):
        decoded = find_git_subcommand(segment)
        if decoded is None:
            continue
        _globals, rest = decoded
        if rest and rest[0] == "commit":
            return segment
    return None


# Regex-only heuristic for the parse-failure fallback: a standalone `git commit`
# subcommand (not embedded in a path/branch-name), anchored at start-of-line or
# after a shell operator.
_COMMIT_FALLBACK_RE = re.compile(
    r"(?:^|[;&|]\s*|&&\s*|\|\|\s*)\s*git\b[^;&|]*?(?<!\S)\bcommit\b(?!\S*/)",
    re.MULTILINE,
)


def _looks_like_git_commit(command: str) -> bool:
    """Regex fallback used when shlex.split fails (unbalanced quotes etc.).

    Fail-CLOSED: a parse-failure-with-commit-looking command blocks; a
    parse-failure-and-no-commit-looking command falls through to allow.
    """
    return bool(_COMMIT_FALLBACK_RE.search(strip_heredocs(command)))


# ============================================================================
# Main check
# ============================================================================

_EXAMPLE = (
    'git -c user.name="Ada Lovelace" '
    '-c user.email="team+Ada.Lovelace@example.com" commit -F /tmp/msg.txt'
)


def check(input_data: dict) -> dict | None:
    """Check commit identity. Returns a block dict, or None to allow."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    cfg = config(input_data)
    # GATE: opt-in. With identity.enforce off, do nothing.
    if not cfg.get("identity.enforce", False):
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    cwd = resolve_invocation_cwd(input_data)

    # Indirect-exec bypass detection runs BEFORE the segment tokenizer because
    # wrappers hide the actual git invocation from the outer-command parser.
    indirect_shape = _detect_indirect_commit(command, cwd=cwd)
    if indirect_shape is not None:
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: indirect-exec wrapper detected ({indirect_shape}) "
                "carrying a hidden `git commit`. The framework identity gate only "
                "sees the outer Bash command, so wrappers like "
                "`printf '...' | bash`, `bash -c '...'`, `bash <script>`, "
                "`bash <(...)`, `bash <<EOF...EOF`, `bash <<<'...'`, and "
                "`eval '...'` would let an unvalidated commit through.\n\n"
                "Run the git command directly so the hook can inspect the "
                "identity flags:\n"
                f"  {_EXAMPLE}\n\n"
                "If you need a different working directory, prefix with "
                "`cd <path> && git -c ... commit ...`."
            ),
        }
        log_pretooluse_block(
            "validate_commit_identity", command, result["reason"], input_data=input_data
        )
        return result

    commit_segment = _find_commit_segment(command)
    if commit_segment is _PARSE_FAILURE:
        # shlex could not parse the command. Fail CLOSED: if it looks like a
        # git commit, block; otherwise allow non-commit commands.
        if not _looks_like_git_commit(command):
            return None
        result = {
            "decision": "block",
            "reason": (
                "BLOCKED: git commit detected but the command failed shell parsing "
                "(likely unbalanced quotes — common when embedding heredocs inside "
                '`-m "$(cat <<EOF...EOF)"` next to `-c user.name=` flags). '
                "Cannot validate identity flags from a malformed command.\n\n"
                "Fix: write the message to a file and use `-F /path/to/msg.txt`:\n"
                "  printf '%s\\n' \"your commit message\" > /tmp/msg.txt\n"
                f"  {_EXAMPLE}"
            ),
        }
        log_pretooluse_block(
            "validate_commit_identity", command, result["reason"], input_data=input_data
        )
        return result
    if commit_segment is None:
        # Tokenize succeeded but no git commit subcommand was found.
        return None

    assert isinstance(commit_segment, list)  # _PARSE_FAILURE and None handled above

    roster_source = cfg.get("identity.roster_source", ".claude/team/roster.json")
    allow_emails = cfg.get("identity.allow_emails", []) or []
    email_pattern = cfg.get("identity.email_pattern", "")
    roster = _resolve_roster(cfg, input_data, roster_source)

    pairs = dict(extract_dash_c_pairs(commit_segment))
    name = pairs.get("user.name")
    email = pairs.get("user.email")

    pattern_hint = f" (convention: {email_pattern})" if email_pattern else ""

    if not name:
        result = {
            "decision": "block",
            "reason": (
                "BLOCKED: git commit missing `-c user.name=` flag. "
                "Project policy requires per-commit identity via -c flags. "
                f"Example: {_EXAMPLE}"
            ),
        }
        log_pretooluse_block(
            "validate_commit_identity", command, result["reason"], input_data=input_data
        )
        return result

    if not email:
        result = {
            "decision": "block",
            "reason": (
                "BLOCKED: git commit missing `-c user.email=` flag. "
                "Project policy requires per-commit identity via -c flags. "
                f"Example: {_EXAMPLE}"
            ),
        }
        log_pretooluse_block(
            "validate_commit_identity", command, result["reason"], input_data=input_data
        )
        return result

    # allow_emails bypass: an explicitly allowlisted author email (e.g. the repo
    # owner) is accepted without a roster match. Both -c flags are still required.
    if email in allow_emails:
        return None

    if name not in roster:
        valid = ", ".join(sorted(roster.keys())) or "(roster empty)"
        result = {
            "decision": "block",
            "reason": (
                f'BLOCKED: user.name="{name}" is not a recognized roster member'
                f"{pattern_hint}. Valid names: {valid}"
            ),
        }
        log_pretooluse_block(
            "validate_commit_identity", command, result["reason"], input_data=input_data
        )
        return result

    expected_email = roster[name]
    if email != expected_email:
        result = {
            "decision": "block",
            "reason": (
                f'BLOCKED: user.email="{email}" does not match the roster for {name}. '
                f"Expected: {expected_email}"
            ),
        }
        log_pretooluse_block(
            "validate_commit_identity", command, result["reason"], input_data=input_data
        )
        return result

    return None


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result and result.get("decision") == "block":
        print(json.dumps(result))
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
