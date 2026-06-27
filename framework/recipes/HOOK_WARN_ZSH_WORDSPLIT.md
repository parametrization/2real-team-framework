# Recipe: `warn_zsh_wordsplit` hook

**Purpose**
Advisory (never-blocking) warning when a Bash command uses bash-only
word-splitting idioms that silently misbehave under zsh.

**What it enforces / matches**
- Flags four patterns: `set -- $scalar`, `for VAR in $scalar` (bare standalone
  unquoted scalar), `${!var}`/`${!arr[@]}` indirect/keys expansion, and
  `mapfile`/`readarray`. Emits `{"systemMessage": ...}` with zsh-safe fixes.
- False-positive guards: quoted forms (`"$@"`, `"$list"`, `"${arr[@]}"`); globs,
  `$(...)`, brace/literal lists; path/concat prefixes where `$VAR` is only part
  of a word (`$dir/*.py`, `$HOME/.config`) — the scalar must be a STANDALONE
  word; heredoc bodies are stripped before scanning; `declare -A`/`typeset` ok.

**Config keys used**
- `shell` (`"bash"`|`"zsh"`, default `"bash"`) — `check()` returns `None`
  (no-op) unless `shell == "zsh"`.

**Adaptation notes**
- Only active for zsh projects; set `shell: "zsh"` in the framework config.
- Advisory by design — it never blocks; no logging call.
