r"""Smoke/lint gate for the main#663 gh-command parser invariant.

Charter rule: `charter/hooks.md` § Hook Authorship Requirements
              "7. gh-command Parser Invariant".

> Any hook that parses a `gh` command (`gh issue`/`gh pr`/`gh workflow`/`gh
> api`) MUST scope label/repo extraction to the actual flag VALUES (via the
> shared `_shell_parse` / `_wave_label_parse` / `_repo_flag_parse` tokenizer)
> and resolve the flag-omitted (ambient git-context) case — never reimplement
> the shell tokenizer privately, and never match flag-shaped / label-shaped
> strings elsewhere in the command (especially `--body`/`--body-file` content).

This gate is the machine-enforcement of that invariant (per
`feedback_enforcement_hierarchy.md`: "Charter rules without enforcement
decay"). It is the gh-command analogue of the deferred grep-gate noted in
§5a, scoped to the gh-command value-flag parser class the invariant governs.

Mechanics
=========

For every top-level hook in `.claude/hooks/*.py` (excluding the three
sanctioned shared parsers, which ARE the canonical tokenizer/flag-walker),
classify whether it is a **gh-command parser** — i.e. it reads the incoming
Bash command (`tool_input` / `command`) AND matches a
`gh issue`/`gh pr`/`gh workflow`/`gh api` shape. For each such hook assert
BOTH:

  A. It does NOT call `shlex.split` / `shlex.shlex` directly — all shell
     tokenization must route through `_shell_parse.tokenize` (which carries
     the line-continuation #287 and heredoc fixes a private reimplementation
     would miss).

  C. It contains no ad-hoc flag-value-capturing regex literal (a regex that
     captures the value following `--repo`/`--label`/`--add-label`/
     `--remove-label`/`-R`/`-l`). Such extraction is the #650/#659/#661 bug
     class — it leaks label-shaped tokens out of `--body` content. Pure
     shape-detection regexes (`\bgh\s+issue\s+create\b`) are allowed.

Scope: the full gh-command value-flag parser class — `gh issue`/`gh pr`
(the original invariant) PLUS `gh workflow`/`gh api` (e.g. `warn_ghcr_image`
extracting `-R` from `gh workflow run`), which main#663 (wave-16) migrated
onto the shared parser and folded into enforcement here, closing the
follow-up the original `gh issue`/`gh pr`-scoped gate had deferred.
"""

from __future__ import annotations

import ast
import os
import re
import unittest

_HOOKS_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# The canonical shared parsers — they ARE the tokenizer / flag-walker /
# ambient-repo resolver. They are allowed to call shlex and carry the
# sanctioned regex fallbacks, so they are exempt from the gate.
_SHARED_PARSERS = {"_shell_parse.py", "_wave_label_parse.py", "_repo_flag_parse.py"}

# gh value/identity flags whose VALUE a parser might (wrongly) regex out.
_FLAG_ALT = r"--repo|--add-label|--remove-label|--label|-R|-l"

# Heuristic: a regex SOURCE literal that captures the value FOLLOWING a gh
# value-flag — `--flag( |=|\s)*( capture | \S | . | [ )`. Validated against the
# live corpus: matches the `-R\s+[\"']?(\S+)` ad-hoc shape; does NOT match the
# sanctioned `(?:--repo|-R)(?:=|\s+)(\S+)` form in `_repo_flag_parse` (a `)`
# follows the flag there, outside the allowed separator run) — and that module
# is exempt anyway.
_FORBIDDEN_FLAG_REGEX = re.compile(r"(?:%s)(?:\\?=|\\s|\\ |\s|=)*\(?\\?[Ss.\[(]" % _FLAG_ALT)

# re.* functions whose FIRST positional arg is a regex pattern source.
_RE_PATTERN_FUNCS = {
    "compile",
    "search",
    "match",
    "fullmatch",
    "findall",
    "finditer",
    "split",
    "sub",
}

# Minimum gh-command parsers the classifier must find. Guards against a
# refactor that silently breaks the classifier into matching nothing (which
# would make this gate vacuously green). The live set is 14 (P6W16); 10 leaves
# margin for legitimate hook removal while still catching a classifier regress.
_MIN_GH_HOOKS = 10


def _iter_hook_files() -> list[str]:
    return sorted(
        f
        for f in os.listdir(_HOOKS_DIR)
        if f.endswith(".py") and not f.startswith("_consultation") and f not in {"__init__.py"}
    )


def _read(name: str) -> str:
    with open(os.path.join(_HOOKS_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def _docstring_constant_ids(tree: ast.AST) -> set[int]:
    """ids() of string Constant nodes that are module/func/class docstrings."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                out.add(id(body[0].value))
    return out


def _code_signal_text(src: str) -> str:
    """Join code identifiers + non-docstring string constants into one blob.

    Used only for cheap substring/regex SIGNAL checks (classification), not for
    semantics. Docstrings are excluded so a hook that merely *documents* a gh
    command in its module docstring is not misclassified as a parser of one.
    """
    tree = ast.parse(src)
    doc_ids = _docstring_constant_ids(tree)
    parts: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in doc_ids
        ):
            parts.append(node.value)
        elif isinstance(node, ast.Attribute):
            parts.append(node.attr)
        elif isinstance(node, ast.Name):
            parts.append(node.id)
    return " ".join(parts)


def _is_gh_command_parser(src: str) -> bool:
    """True if the hook reads the incoming command AND matches a gh issue/pr shape."""
    code = _code_signal_text(src)
    reads_command = ("tool_input" in code) and ("command" in code)
    if not reads_command:
        return False
    gh_shape = (
        re.search(r"gh\s+(?:issue|pr|workflow|api)\b", code) is not None
        or "is_gh_subcommand" in code
        or "find_gh_subcommand" in code
        or "--add-label" in code
        or "--remove-label" in code
    )
    return gh_shape


def _calls_shlex_directly(src: str) -> bool:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            base = node.func.value
            if (
                isinstance(base, ast.Name)
                and base.id == "shlex"
                and node.func.attr in {"split", "shlex"}
            ):
                return True
        if isinstance(node, ast.ImportFrom) and node.module == "shlex":
            if any(a.name in {"split", "shlex"} for a in node.names):
                return True
    return False


def _adhoc_flag_value_regexes(src: str) -> list[str]:
    """Regex SOURCE literals (re.* first arg) that capture a gh flag VALUE."""
    tree = ast.parse(src)
    hits: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _RE_PATTERN_FUNCS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "re"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            pat = node.args[0].value
            if _FORBIDDEN_FLAG_REGEX.search(pat):
                hits.append(pat)
    return hits


def _gh_command_parser_hooks() -> list[str]:
    out = []
    for name in _iter_hook_files():
        if name in _SHARED_PARSERS:
            continue
        if _is_gh_command_parser(_read(name)):
            out.append(name)
    return out


class GhCommandParserInvariantTests(unittest.TestCase):
    def test_classifier_finds_the_gh_parser_class(self):
        hooks = _gh_command_parser_hooks()
        self.assertGreaterEqual(
            len(hooks),
            _MIN_GH_HOOKS,
            f"Classifier found only {len(hooks)} gh-command parsers ({hooks}); "
            f"expected >= {_MIN_GH_HOOKS}. The classifier likely regressed — "
            "this gate would be vacuously green.",
        )

    def test_migrated_hook_is_classified(self):
        # Regression guard: the hook migrated for main#663 must stay in scope.
        self.assertIn("validate_wave_label_evidence.py", _gh_command_parser_hooks())

    def test_workflow_api_class_is_classified(self):
        # Regression guard for the main#663 (wave-16) scope extension: the
        # `gh workflow run` parser must stay enforced, not slip back out of
        # scope (the deferred-follow-up state the original gate had).
        self.assertIn("warn_ghcr_image.py", _gh_command_parser_hooks())

    def test_shared_parsers_present(self):
        for name in _SHARED_PARSERS:
            self.assertTrue(
                os.path.exists(os.path.join(_HOOKS_DIR, name)),
                f"sanctioned shared parser missing: {name}",
            )

    def test_no_gh_parser_calls_shlex_directly(self):
        offenders = []
        for name in _gh_command_parser_hooks():
            if _calls_shlex_directly(_read(name)):
                offenders.append(name)
        self.assertEqual(
            offenders,
            [],
            "gh-command parser hooks must tokenize via `_shell_parse.tokenize`, "
            f"not call shlex directly (main#663 invariant): {offenders}",
        )

    def test_no_gh_parser_has_adhoc_flag_value_regex(self):
        offenders = {}
        for name in _gh_command_parser_hooks():
            hits = _adhoc_flag_value_regexes(_read(name))
            if hits:
                offenders[name] = hits
        self.assertEqual(
            offenders,
            {},
            "gh-command parser hooks must extract flag values via the shared "
            "tokenizer (walk_flag_values / extract_repo), not a private "
            f"flag-value-capturing regex (main#663 invariant): {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
