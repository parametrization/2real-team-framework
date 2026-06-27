#!/usr/bin/env python3
"""PostToolUse hook: Annunaki error monitor.

Fires after every Bash tool call. Inspects the output for error signals
(non-zero exit code, stderr content, common error patterns) and appends
each error to .claude/annunaki/errors.jsonl for later analysis by
/annunaki-attack.

Input Language:
  Fires on:      PostToolUse Bash
  Matches:       Bash with non-zero exit_code OR stdout/stderr matching any
                 ERROR_PATTERNS regex (Traceback, fatal:, ModuleNotFoundError,
                 etc.) and NOT matching IGNORE_PATTERNS
  Does NOT match: any non-Bash tool, command-text containing grep-for-error /
                  --error flags / error-named paths (false-positive guards),
                  silent-boolean-test idioms (`[`, `[[`, `test`, `grep -q`,
                  `pgrep`, `pkill`, `which`, `command -v`, `diff --quiet`,
                  `git diff --quiet`, `if [...]`) when their ONLY error signal
                  is a non-zero exit code, probe-with-fallback idioms (#517 —
                  exit=0 + `2>&1` + (`||` OR `| head`/`| tail`) when the ONLY
                  matched pattern is `stdout:No such file or directory`),
                  content-display commands (#596 — exit=0 cat/head/tail/less,
                  `gh api .../contents/...`, or a read of errors.jsonl when the
                  ONLY signals are stdout-pattern matches in displayed content),
                  session-dedup hits
  Flag pass-through: stdin JSON is forwarded verbatim to `check()` by the
                     PostToolUse dispatcher (`post_dispatcher.py`)
  Confidence tag (#729): every logged record carries `confidence` in
                     {"high", "low"}. An exit-0 stdout-only match that is
                     echoed content (displayed source `except ImportError:`,
                     a `gh pr view --json` body) is "low" and excluded from the
                     genuine-error count by annunaki_parse, but retained for
                     forensics; a STRONG masked-failure signal (e.g. a `git
                     push | tail` REJECTED push) stays "high" and counted.
  rc=0 precision (#835): every logged record also carries a `hook` field
                     (always "annunaki_monitor" for command-failure captures,
                     so the /annunaki breakdown stops bucketing them as
                     "unknown") and a `category` triage label. The P6W16 retro
                     found 85% of captures were exit-0 stdout-pattern matches
                     (a pytest `FAILED` line surfacing through `… | tail`
                     rc-masking, or benign demo output containing the literal)
                     that #729's recall-preserving default tagged "high" and
                     counted. #835 demotes that residual class — exit-0,
                     stdout-only, NOT a STRONG masked-failure signal, NOT
                     positively-recognized echoed content — to
                     `confidence="low"` + `category="pipe-mask-suspect"`:
                     retained for forensics and specifically triageable, but
                     excluded from the count. The genuine exit-0-failure
                     carve-out (STRONG masked-failure) stays "high"/counted as
                     `category="masked-failure"`.

Exit codes:
  0 — always (advisory hook, never blocks)
"""

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from annunaki_log import append_jsonl_record

# Where we log errors — JSONL for easy dedup and processing
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ERRORS_FILE = REPO_ROOT / ".claude" / "annunaki" / "errors.jsonl"

# Hook attribution (#835): command-failure captures from this monitor carry a
# `hook` field so /annunaki's `rec.get("hook", "unknown")` breakdown attributes
# them to the monitor instead of bucketing them all as "unknown". The pretooluse
# / posttooluse records written by annunaki_log set `hook` to the blocking hook
# name; this is the analogous attribution for the auto-capture path.
MONITOR_HOOK_NAME = "annunaki_monitor"

# Triage categories (#835) — a coarse classification of WHY a record was logged,
# orthogonal to `confidence`. Lets /annunaki-attack triage by class (e.g. batch-
# dismiss `pipe-mask-suspect`, prioritize `masked-failure`) instead of re-deriving
# it from the raw fields. `confidence` decides COUNTING; `category` describes KIND.
CATEGORY_NONZERO_EXIT = "nonzero-exit"  # exit_code != 0 — hard failure (high)
CATEGORY_STDERR_MATCH = "stderr-match"  # stderr pattern matched (high)
CATEGORY_MASKED_FAILURE = "masked-failure"  # STRONG exit-0 masked failure (high)
CATEGORY_ECHOED_CONTENT = "echoed-content"  # #729 displayed source/body (low)
# The dominant P6W16 false-positive class: exit-0, stdout-only, no strong signal,
# not positively-recognized echoed content — e.g. a pytest `FAILED` surfacing
# through `… | tail` rc-masking, or benign demo output. Retained but NOT counted.
CATEGORY_PIPE_MASK_SUSPECT = "pipe-mask-suspect"

# Session-level dedup: skip errors we've already logged this session
_seen_hashes: set = set()

# Patterns that indicate errors even when exit code is 0
ERROR_PATTERNS = [
    re.compile(r"^error\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^fatal:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^FAILED", re.MULTILINE),
    re.compile(r"Traceback \(most recent call last\)", re.MULTILINE),
    re.compile(r"^E\s+\w+Error:", re.MULTILINE),  # pytest-style
    re.compile(r"panic:", re.MULTILINE),
    re.compile(r"ENOENT|EACCES|EPERM", re.MULTILINE),
    re.compile(r"command not found", re.IGNORECASE | re.MULTILINE),
    re.compile(r"No such file or directory", re.MULTILINE),
    re.compile(r"Permission denied", re.MULTILINE),
    re.compile(r"ModuleNotFoundError:", re.MULTILINE),
    re.compile(r"ImportError:", re.MULTILINE),
    re.compile(r"SyntaxError:", re.MULTILINE),
    re.compile(r"TypeError:|ValueError:|KeyError:|AttributeError:", re.MULTILINE),
    re.compile(r"npm ERR!", re.MULTILINE),
    re.compile(r"exit status [1-9]", re.MULTILINE),
    re.compile(r"failed with exit code", re.IGNORECASE | re.MULTILINE),
]

# Patterns to IGNORE (not real errors)
IGNORE_PATTERNS = [
    re.compile(r"grep.*error", re.IGNORECASE),  # grep searching for "error"
    re.compile(r"--error", re.IGNORECASE),  # flags containing "error"
    re.compile(r"error_log|error\.log|errorhandl", re.IGNORECASE),  # filenames
]

# Silent-boolean-test idioms (#474, tightened #490): commands whose ONLY
# failure signal is a non-zero exit code with empty stdout/stderr — by
# design, not an error. After #473 closed the silent-failure blind spot,
# these idioms became noise. Apply ONLY when matched_patterns is exactly
# ["exit_code=..."] (no stdout or stderr pattern matched) — pattern
# matches always win, ignore-on-silent-exit never suppresses a real error.
#
# #490 changes vs #474:
#   - Removed `^\s*if\s+\[` and `^\s*if\s+\[\[` (gap #3): outer `if [` matched
#     even when the body — a real deploy step — was the failing command, so
#     silenced genuine failures. The `[ ... ]` regex still covers bare
#     condition-only commands; if-bodies now log on their own merit.
#   - Removed redundant `^\s*\[\[` (micro-cleanup): `^\s*\[` already matches
#     `[[` (both start with `[`).
#   - Extended grep regex to handle split-flag forms (`grep -E -q ...`) in
#     addition to combined-flag forms (`grep -qE`, `grep -Eq`).
SILENT_BOOLEAN_TEST_PATTERNS = [
    re.compile(r"^\s*\["),  # POSIX `[ ... ]` test (also matches `[[`)
    re.compile(r"^\s*test\b"),  # explicit `test` builtin
    # grep with -q anywhere in the flag sequence: combined (-qE, -Eq, -qi)
    # or split (-E -q, -i -q). Non-capturing repeated `-flags \s+` prefix
    # allows any number of intermediate flag tokens before the -*q* terminal.
    re.compile(r"\bgrep\s+(?:-[a-zA-Z]+\s+)*-[a-zA-Z]*q"),
    re.compile(r"^\s*(pgrep|pkill)\b"),  # process find/signal, exit 1 on no match
    re.compile(r"^\s*(which|command\s+-v)\b"),  # which/command -v not-found
]

# Idioms with exit-code-conditional skip (#490 gap #2): these tools use
# exit_code as a SIGNAL channel where some codes are by-design and others
# are real errors. Listed here as (pattern, by_design_codes) so the skip
# only fires when the exit_code is in the by-design set. Any other exit
# code falls through to LOG.
#
# `diff` and `git diff --quiet` exit-code semantics:
#   0 — identical
#   1 — files differ (by-design idiom; suppress)
#   2 — trouble (couldn't open, permission denied, etc.; LOG)
SILENT_BOOLEAN_TEST_PATTERNS_BY_EXIT_CODE = [
    (re.compile(r"\bdiff\s+--quiet\b"), {1}),
    (re.compile(r"\bgit\s+diff\s+--quiet\b"), {1}),
]

# Probe-with-fallback shell idiom (#517): commands that intentionally swallow
# a not-found error via stdout-merge (`2>&1`) followed by either a fallback
# (`|| echo "..."`) or output truncation (`| head` / `| tail`). The error
# text ends up on captured stdout and trips ERROR_PATTERNS' "No such file or
# directory" line, but the command itself exits 0 because the failure was
# explicitly caught. After #473 closed the silent-failure blind spot these
# probe idioms became noise (~14 events in one W11 session).
#
# Conservative classifier: ignore only when ALL hold:
#   - exit_code == 0 (probe completed cleanly)
#   - command contains `2>&1` (stdout-merge present — required marker)
#   - command contains `||` OR a pipe to `head` / `tail` (the fallback/truncate
#     suffix that makes this a probe rather than a real read)
#   - the ONLY matched pattern is `stdout:No such file or directory`
#
# Sibling families: #474/#481 silent-boolean-tests (`grep -q`, `[ ... ]`)
# fire on a different signal (exit-code-only, empty output), so they live in
# their own classifier branch. #473 silent-failure capture is the path this
# IGNORE protects from over-logging.
PROBE_WITH_FALLBACK_STDOUT_MERGE = re.compile(r"2>&1")
PROBE_WITH_FALLBACK_TRAILERS = re.compile(r"\|\||\|\s*head\b|\|\s*tail\b")
PROBE_WITH_FALLBACK_ONLY_PATTERN = "stdout:No such file or directory"

# Content-display false positives (#596): commands that DISPLAY file/record
# content which itself contains error-shaped strings (e.g. `cat` of a Python
# source file with `except ImportError:`, `gh api .../contents/...` echoing
# source that contains `except ValueError:`, displaying errors.jsonl whose
# records contain "Traceback"). The command succeeded (exit 0) and only emits
# the requested content — the matched pattern lives in the *displayed content*,
# not in a real failure. ~25% of W15-window captures were this class, plus the
# meta-capture case where the retro displayed the error log itself.
#
# Distinct from #517 (probe-with-fallback): that fires on an `ls`/`cat` of a
# MISSING path whose "No such file or directory" stderr is merged onto stdout
# via `2>&1` + a fallback trailer. This class fires on a SUCCESSFUL read whose
# content happens to look like an error. Different signal, different marker set.
#
# Conservative classifier: suppress stdout-pattern matching (keep exit-code and
# stderr detection) only when ALL hold:
#   - exit_code == 0 (the read succeeded)
#   - NO stderr pattern matched and NO exit_code marker present — i.e. the ONLY
#     signals are stdout-pattern matches (the displayed content)
#   - the command's leading verb is a pure content-display verb, OR the command
#     reads the annunaki errors log itself (self-referential meta-capture guard)
#
# Leading-verb match is anchored: the display verb must be the command's first
# token (allowing a single leading `cd ... &&`/`REPO_ROOT=... &&` setup prefix
# is intentionally NOT supported here — a compound command that *also* runs a
# real build/test step should still log on that step's merits, same precedence
# rule as the silent-boolean-test family).
CONTENT_DISPLAY_VERBS = re.compile(
    r"""
    ^\s*
    (?:
        cat | head | tail | less | more | bat        # file pagers/dumpers
      | git\s+show | git\s+diff | git\s+log          # git content display
      | gh\s+pr\s+diff | gh\s+pr\s+view              # gh PR content display
    )
    \b
    """,
    re.VERBOSE,
)

# `gh api .../contents/...` reads a file's content (base64 or, with a jq/-q
# content selector, decoded source). Matched anywhere in the command because gh
# api invocations are commonly preceded by a variable-assignment prefix and the
# `contents/` path segment is an unambiguous content-read marker.
CONTENT_DISPLAY_GH_API_CONTENTS = re.compile(r"\bgh\s+api\b.*\bcontents/")

# Self-referential meta-capture guard (#596): a command that reads the annunaki
# error log itself will echo historical records containing "Traceback" etc.
# Reading errors.jsonl is never itself an error.
CONTENT_DISPLAY_ERRORS_LOG = re.compile(r"errors\.jsonl")

# A `2>&1` stdout-merge marks the #517 probe-with-fallback domain, not a content
# display: you only redirect stderr onto stdout when you EXPECT a read might fail
# and want to catch/inspect its error text. A genuine content display (`cat
# docs.yml`, `gh api .../contents/x.py`) reads a file it expects to exist and has
# no `2>&1`. Deferring `2>&1` shapes to the probe classifier (which has its own
# conservative trailer guard) keeps the two classifiers from overlapping on the
# failed-read case — e.g. `cat missing.py 2>&1 | head` leads with a display verb
# but is a failed read whose merged error text (or an unrelated Traceback in the
# merged stream) must still log on its own merits (#517 regression guard).
CONTENT_DISPLAY_STDOUT_MERGE = re.compile(r"2>&1")

# The `No such file or directory` stdout match always signals a FAILED
# filesystem read (a missing path), never error-shaped *content* we want to
# suppress — no source file we display legitimately emits that exact phrase as
# its content. It is the #517 probe family's signal, so a content-display read
# whose only match is this line defers to the probe classifier rather than being
# silenced here. This is the marker-level guard complementing the `2>&1`
# command-shape guard: a non-`2>&1` `gh api .../contents/... > /tmp && base64 -d`
# that nonetheless emitted a No-such-file failure must still log (#517 outlier).
CONTENT_DISPLAY_EXCLUDED_PATTERN = "stdout:No such file or directory"

# Confidence classification (#729) -------------------------------------------
# A record matched purely by a stdout pattern at exit 0 is ambiguous. The
# trigger word may be a REAL failure masked by a pipe — `git push ... | tail`
# swallows a REJECTED push because the pipeline rc is the pager's 0, not git's
# (feedback_push_pipe_masks_rejection) — OR it may be a trigger word sitting in
# ECHOED OUTPUT the command merely displayed: source code (`except ImportError:`,
# a `re.compile(...)` from this monitor's own body), a `gh pr view --json` PR
# body, an issue body quoting "ERROR: ...". The second class is not a failure;
# it drowned the real signal (85% / 40-of-47 of the P5W5 window — #729).
#
# Rather than DROP these (the #517/#596 ignore families do that for the cases
# they can prove benign), we TAG every surviving record with a `confidence`
# field and let the reader (annunaki_parse) exclude the low-confidence sub-class
# from the genuine-error COUNT while keeping every record for forensics:
#   high — a hard failure signal (non-zero exit, a stderr-pattern match) OR an
#          exit-0 stdout match carrying a STRONG masked-failure signal.
#   low  — exit-0, stdout-only, no strong signal, and the matched line is
#          positively recognized as echoed content (displayed source / body).
# An exit-0 stdout match we CANNOT positively recognize as echoed stays `high`:
# we only ever demote display we are confident about, never an unclassified
# failure (recall-preserving — the precision pass must not silence real errors).

# Strong masked-failure signals: phrases marking a REAL failure even when the
# pipeline exited 0. Kept counted — this is the acceptance-criterion carve-out
# preserving the genuine exit-0-failure class (the `git push | tail` REJECTED
# case and script self-reports like "... failed (exit 1)"). A real Python
# `Traceback` is included so its source frames (a `  raise ValueError(...)`
# line) cannot mis-trip the echoed-source signal below; pure cat/gh-api
# displays of error-shaped content were already dropped upstream by #596.
STRONG_MASKED_FAILURE = re.compile(
    r"failed to push"  # git push rejection masked by a pager pipe
    r"|\[rejected\]|\[remote rejected\]|non-fast-forward"
    r"|exit status [1-9]"
    r"|failed with exit code"
    r"|\(exit [1-9][0-9]*\)"  # self-report: "ERROR: gh call failed (exit 1)"
    r"|Traceback \(most recent call last\)",
    re.IGNORECASE,
)

# Echoed-content signal 1: the matched line is a Python source clause being
# DISPLAYED (a `cat`/`echo`/diff/`gh api .../contents` dump), not a raised
# error. `except ImportError:` / a displayed `re.compile(...)` are the dominant
# #729 false class. A genuinely-raised error reads `ImportError: <msg>` (or
# pytest `E   ImportError:`) — start-of-line error name then a message — which
# this deliberately does NOT match. `raise`/`except` lines inside a genuine
# traceback are guarded by the STRONG `Traceback` keeper, which wins first.
SOURCE_CLAUSE_LINE = re.compile(
    r"^\s*[+-]?\s*(?:except|raise)\s+[\w.(]"  # except/raise <Error>[(]
    r"|^\s*[+-]?\s*re\.compile\(",  # displayed monitor/source regex
)

# Echoed-content signal 2: the matched line opens a JSON object/array body —
# `{"` or `[{` / `["` at line start (after an optional diff +/-). A
# `gh ... --json` / `gh api` body dump that quotes an error string inside the
# emitted JSON lands here. The trailing quote is required so a bare `[]` array,
# a `[WARNING] ...` log prefix, or a markdown `[link]` line does NOT match
# (recall guard — those appear in genuine failure output). A genuinely-raised
# error never starts its extracted line with a quoted-key JSON brace (it leads
# with an error name, `error:`/`fatal:`, or pytest `E `). Keyed on the LINE
# shape, not the command, so a compound command that buries a `gh pr view`
# alongside a real failing build/test step is NOT demoted on that substring.
JSON_BODY_LINE = re.compile(r'^\s*[+-]?\s*[{\[]\s*["{]')


def _is_content_display(command: str, exit_code: int, matched_patterns: list[str]) -> bool:
    """Return True if this matches the #596 content-display idiom.

    All of the following must hold:
      1. exit_code == 0 (the read/display succeeded)
      2. EVERY matched pattern is a `stdout:` pattern — no `stderr:` match and
         no `exit_code=` marker. A stderr pattern or non-zero exit means a real
         failure occurred alongside the display, so this skip does NOT apply.
      3. the command does NOT contain a `2>&1` stdout-merge AND no matched
         pattern is the `No such file or directory` line. Both mark the #517
         probe-with-fallback domain (an intentional/failed read of a missing
         path) rather than displayed error-shaped content, so those cases are
         left to the probe classifier. The `2>&1` guard catches the command
         shape; the No-such-file guard catches the matched-signal even when the
         command shape is absent (e.g. a bare `gh api .../contents/... > file`
         that failed). Together they keep `cat missing.py 2>&1 | head` and the
         non-trailer probe outliers from being mis-classified as displays.
      4. the command is a recognized content-display operation: a leading
         display verb (cat/head/tail/less/more/bat, git show|diff|log,
         gh pr diff|view), a `gh api .../contents/...` read, OR a read of the
         annunaki errors.jsonl log (self-referential meta-capture).

    Condition 2 is the precedence guard mirroring the silent-boolean-test and
    probe-with-fallback families: any real failure signal bypasses the skip.
    """
    if exit_code != 0:
        return False
    if not matched_patterns:
        return False
    if not all(p.startswith("stdout:") for p in matched_patterns):
        return False
    if CONTENT_DISPLAY_STDOUT_MERGE.search(command):
        return False
    if CONTENT_DISPLAY_EXCLUDED_PATTERN in matched_patterns:
        return False
    if CONTENT_DISPLAY_VERBS.search(command):
        return True
    if CONTENT_DISPLAY_GH_API_CONTENTS.search(command):
        return True
    if CONTENT_DISPLAY_ERRORS_LOG.search(command):
        return True
    return False


def _is_probe_with_fallback(command: str, exit_code: int, matched_patterns: list[str]) -> bool:
    """Return True if this matches the #517 probe-with-fallback idiom.

    All four conditions must hold:
      1. exit_code == 0
      2. command contains `2>&1` (stdout-merge present)
      3. command contains `||` OR a pipe to `head`/`tail`
      4. matched_patterns is exactly the No-such-file-or-directory stdout match

    Condition 4 is the strict-singleton guard: if any other signal fired
    (stderr pattern, ModuleNotFoundError, exit_code marker), this idiom skip
    does NOT apply and the record logs on its own merits.
    """
    if exit_code != 0:
        return False
    if matched_patterns != [PROBE_WITH_FALLBACK_ONLY_PATTERN]:
        return False
    if not PROBE_WITH_FALLBACK_STDOUT_MERGE.search(command):
        return False
    if not PROBE_WITH_FALLBACK_TRAILERS.search(command):
        return False
    return True


def _is_silent_boolean_test(command: str, exit_code: int = 0) -> bool:
    """Return True if command matches a documented silent-boolean-test idiom.

    Caller must additionally verify that the ONLY failure signal is exit_code
    (no stdout/stderr pattern match) — pattern matches always take precedence.

    For exit-code-conditional idioms (diff --quiet, git diff --quiet), the
    skip only fires when exit_code is in the by-design set documented for
    that tool. Any other non-zero code falls through to LOG.
    """
    for pattern in SILENT_BOOLEAN_TEST_PATTERNS:
        if pattern.search(command):
            return True
    for pattern, by_design_codes in SILENT_BOOLEAN_TEST_PATTERNS_BY_EXIT_CODE:
        if pattern.search(command) and exit_code in by_design_codes:
            return True
    return False


def _extract_error_lines(text: str, max_lines: int = 10) -> list[str]:
    """Extract the most relevant error lines from output."""
    lines = text.strip().splitlines()
    error_lines = []
    for i, line in enumerate(lines):
        for pattern in ERROR_PATTERNS:
            if pattern.search(line):
                # Grab this line and up to 2 lines of context after
                context_end = min(i + 3, len(lines))
                error_lines.extend(lines[i:context_end])
                break
        if len(error_lines) >= max_lines:
            break
    return error_lines[:max_lines]


def _should_ignore(command: str, output: str) -> bool:
    """Return True if this looks like a false positive."""
    for pattern in IGNORE_PATTERNS:
        if pattern.search(command):
            return True
    return False


def _is_echoed_content(command: str, error_lines: list[str]) -> bool:
    """Return True if the trigger match looks like displayed content (#729).

    Two positive signals on the matched line(s): a displayed Python source
    clause (`except`/`raise`/`re.compile(` — signal 1), or a JSON-data-shaped
    line (`{`/`[` at line start — signal 2, a `gh --json`/body dump). Either
    marks the trigger as echoed output rather than a failure. `command` is
    accepted for signature symmetry with the other classifiers but the
    decision is line-shape-based (see JSON_BODY_LINE for why).
    """
    for line in error_lines:
        if SOURCE_CLAUSE_LINE.search(line) or JSON_BODY_LINE.search(line):
            return True
    return False


def _classify_confidence(
    command: str, exit_code: int, matched_patterns: list[str], error_lines: list[str]
) -> tuple[str, str]:
    """Return (confidence, category) for a logged error record (#729, #835).

    `confidence` ∈ {"high", "low"} decides whether annunaki_parse COUNTS the
    record as a genuine error. `category` (#835) is a coarse triage label for
    WHY it was logged. The branches, in precedence order:

      nonzero-exit     — exit_code != 0                          → high
      stderr-match     — a stderr-pattern match                  → high
      masked-failure   — exit-0 stdout match with a STRONG       → high
                         masked-failure signal (the genuine
                         exit-0-failure carve-out, e.g. a
                         `git push | tail` masking a REJECTED push)
      echoed-content   — exit-0 stdout match positively          → low
                         recognized as displayed source/body (#729)
      pipe-mask-suspect — exit-0, stdout-only, no strong signal,  → low
                         not recognized as echoed (#835). This is the
                         dominant P6W16 false-positive class (a pytest
                         `FAILED` surfacing through `… | tail` rc-masking,
                         or benign demo output containing the literal).

    #835 supersedes #729's recall-preserving "unrecognized exit-0 stdout match
    defaults high" policy: the P6W16 retro measured that class at 85% false
    positive, so it is now demoted to low/pipe-mask-suspect — retained in the
    log for forensics (and specifically triageable by category) but excluded
    from the genuine-error count. Recall is preserved for any RECOGNIZABLE
    failure signal: a non-zero exit, a stderr pattern, or a STRONG masked-
    failure phrase all still count.
    """
    if exit_code and exit_code != 0:
        return "high", CATEGORY_NONZERO_EXIT
    if any(p.startswith("stderr:") for p in matched_patterns):
        return "high", CATEGORY_STDERR_MATCH
    if STRONG_MASKED_FAILURE.search("\n".join(error_lines)):
        return "high", CATEGORY_MASKED_FAILURE
    if _is_echoed_content(command, error_lines):
        return "low", CATEGORY_ECHOED_CONTENT
    return "low", CATEGORY_PIPE_MASK_SUSPECT


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry point for PostToolUse Bash.

    Returns None when no error is detected (or input doesn't apply); returns
    an advisory dict describing the logged record when an error is appended
    to the JSONL log. The dispatcher treats non-None as advisory only.
    """
    if input_data.get("tool_name", "") != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    # Claude Code's PostToolUse contract passes `tool_response`. Legacy hook
    # fixtures used `tool_output`; we accept both so old tests still pass.
    tool_output = input_data.get("tool_response") or input_data.get("tool_output", {})
    stdout = tool_output.get("stdout", "")
    stderr = tool_output.get("stderr", "")
    exit_code = tool_output.get("exit_code", 0)

    combined_output = f"{stdout}\n{stderr}".strip()

    if _should_ignore(command, combined_output):
        return None

    is_error = False
    matched_patterns: list[str] = []

    # Check exit_code first so silent failures (commands that exit non-zero
    # with no stdout/stderr — `false`, `kill -9 $$`, exit-1-no-output) are
    # captured. Previously an empty-output early-return short-circuited this
    # branch and dropped them on the floor (#472).
    if exit_code and exit_code != 0:
        is_error = True
        matched_patterns.append(f"exit_code={exit_code}")

    if combined_output:
        if stderr and stderr.strip():
            for pattern in ERROR_PATTERNS:
                if pattern.search(stderr):
                    is_error = True
                    matched_patterns.append(f"stderr:{pattern.pattern}")
                    break

        for pattern in ERROR_PATTERNS:
            if pattern.search(stdout):
                is_error = True
                matched_patterns.append(f"stdout:{pattern.pattern}")
                break

    if not is_error:
        return None

    # #474 silent-boolean-test filter: when the ONLY signal is a non-zero
    # exit code (no stderr/stdout pattern matched), suppress documented
    # boolean-test idioms whose failure branch is by-design. Stderr/stdout
    # pattern matches always win — a `[ -f x ]` that somehow emits a real
    # Traceback still logs.
    if matched_patterns == [f"exit_code={exit_code}"] and _is_silent_boolean_test(
        command, exit_code
    ):
        return None

    # #517 probe-with-fallback filter: when a command intentionally swallows
    # a not-found error via `2>&1` + (`||` OR `| head`/`| tail`) and exits 0,
    # the "No such file or directory" text ends up on captured stdout but is
    # not a real failure. The helper requires the only-pattern guard, so any
    # additional signal (stderr pattern, non-zero exit) bypasses this skip.
    if _is_probe_with_fallback(command, exit_code, matched_patterns):
        return None

    # #596 content-display filter: a command that DISPLAYS content (cat/head/
    # tail/less of a file, `gh api .../contents/...`, a read of errors.jsonl)
    # and exits 0 with only stdout-pattern matches is echoing error-shaped
    # content, not failing. The helper requires exit==0 AND every matched
    # pattern be a stdout one, so a real stderr/exit-code signal bypasses this.
    if _is_content_display(command, exit_code, matched_patterns):
        return None

    error_lines = _extract_error_lines(combined_output)

    # #729/#835 confidence + category tag: exit-0 stdout-only matches that are
    # echoed content (displayed source/body, #729) OR an unrecognized rc=0
    # stdout match (the P6W16 pipe-mask-suspect class, #835) are low-confidence;
    # the reader excludes them from the genuine-error count but keeps every
    # record for forensics. The category labels WHY each was logged.
    confidence, category = _classify_confidence(command, exit_code, matched_patterns, error_lines)

    dedup_input = command[:200] + "|||" + "\n".join(error_lines)[:500]
    dedup_hash = hashlib.md5(dedup_input.encode("utf-8")).hexdigest()
    if dedup_hash in _seen_hashes:
        return None
    _seen_hashes.add(dedup_hash)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # #835: attribute the capture to this monitor so /annunaki's by-hook
        # breakdown stops bucketing command-failure records as "unknown".
        "hook": MONITOR_HOOK_NAME,
        "command": command[:500],
        "exit_code": exit_code,
        "matched_patterns": matched_patterns[:5],
        "confidence": confidence,
        "category": category,
        "error_lines": error_lines,
        "stderr_excerpt": stderr[:300] if stderr else "",
        "_dedup_hash": dedup_hash,
    }

    append_jsonl_record(ERRORS_FILE, record)

    return {
        "action": "logged",
        "dedup_hash": dedup_hash,
        "confidence": confidence,
        "category": category,
    }


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    check(input_data)
    sys.exit(0)


if __name__ == "__main__":
    main()
