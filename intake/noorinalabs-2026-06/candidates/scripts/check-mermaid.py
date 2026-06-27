#!/usr/bin/env python3
"""Validate every fenced ```mermaid block in the given docs by RENDERING it.

The #786 review surfaced that no CI job rendered mermaid diagrams, so a
syntactically-broken block (the L3 alertmanager `<unset>` case) shipped green —
markdown-lint, cspell, and lychee all pass a non-rendering diagram. This gate
closes that gap: it extracts each fenced mermaid block and renders it with
mermaid-cli (`mmdc`, headless Chromium), failing the build on any block that
does not render.

Scope (default): every tracked `*.md` in the parent tree that contains a fenced
mermaid block — discovered from the git index, not a fixed docs/ + ontology/
glob, so a diagram added to README.md, the charter, the lifecycle docs, or any
future authored doc is gated automatically instead of shipping unguarded (#795).
`.claude/memory/**` and `.claude/worktrees/**` are excluded (see _default_files).
Pass explicit file paths to override.

Detection: a block fails if `mmdc` exits non-zero (genuine syntax errors,
unknown diagram types, malformed structure) OR if the produced SVG carries a
mermaid error marker (defends against versions that emit an error-SVG with a
zero exit). KNOWN RESIDUAL (documented, not hidden): a literal `<` inside a
`[label]` is treated by mermaid as an HTML tag and renders DEGRADED with a clean
exit — render-gating cannot catch that via exit code. Authors must escape raw
angle brackets in labels (`#lt;`/`#gt;`), which is exactly the #786 fix. The
gate prints a warning when it sees a raw `<`/`>` inside a block so the footgun
is at least surfaced.

mmdc resolution order: $MMDC, then `mmdc` on PATH, then `npx -y
@mermaid-js/mermaid-cli`. Chromium is run with `--no-sandbox` (required in CI
containers) via a generated puppeteer config.

Exit codes:
    0 — every block rendered (gate green)
    1 — at least one block failed to render
    2 — no mmdc available / usage error
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_MERMAID_BLOCK = re.compile(r"^([ \t]*)```mermaid[ \t]*\n(.*?)^[ \t]*```", re.DOTALL | re.MULTILINE)
_ERROR_MARKERS = ("syntax error", "error in text", "aborted", "parse error")
# HTML line-break tags mermaid renders natively inside node labels (`<br>`,
# `<br/>`, `<br />`, any case). Stripped before the raw-angle scan so a valid
# multi-line label doesn't trip the advisory warning — the closing `>` of a
# break tag would otherwise match `_RAW_ANGLE` (#797).
_BR_TAG = re.compile(r"<br\s*/?>", re.IGNORECASE)
# A raw `<` or `>` that is not part of a mermaid edge token (`-->`, `<--`,
# `<==`, `-.->`). Break tags are removed by `_BR_TAG` first; what remains and
# matches here is a genuinely raw angle bracket (the #786 `<unset>` class).
# Used only for an advisory footgun warning, never to fail the gate (heuristic;
# full render is the gate).
_RAW_ANGLE = re.compile(r"<(?!/|--|==|\.)|(?<![-=.])>")


def _has_raw_angle(body: str) -> bool:
    """True if a mermaid block carries a raw `<`/`>` that renders degraded.

    Valid HTML break tags (`<br>`/`<br/>`/`<br />`) are stripped before the scan
    so multi-line labels don't false-warn (#797); a genuinely unescaped angle
    bracket in a label (the #786 `<unset>` class) still trips it.
    """
    return bool(_RAW_ANGLE.search(_BR_TAG.sub("", body)))


# Authored-doc scope exclusions. `.claude/memory/**` is excluded to match the
# markdown/cspell/lychee linters (dense append-only notes, not rendered docs);
# `.claude/worktrees/**` is excluded so a scratch worktree checkout isn't
# double-scanned. The gitignored child repos never appear in this repo's index,
# so they need no explicit exclusion under the git-ls-files path.
_SCOPE_EXCLUDE_PREFIXES = (".claude/memory/", ".claude/worktrees/")


def _has_mermaid_block(path: Path) -> bool:
    try:
        return "```mermaid" in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def _tracked_markdown() -> list[Path] | None:
    """Tracked `*.md` paths from the git index, or None if git is unavailable."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z", "*.md"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return [Path(p) for p in proc.stdout.split("\0") if p]


def _default_files() -> list[Path]:
    tracked = _tracked_markdown()
    if tracked is None:
        # Not a git work tree (never the case for the CI / pre-push gate): fall
        # back to the original docs/ + ontology/ glob so the gate still runs.
        candidates: list[Path] = []
        for d in ("docs", "ontology"):
            candidates.extend(Path(d).glob("*.md"))
    else:
        candidates = tracked
    files = [
        p
        for p in candidates
        if not p.as_posix().startswith(_SCOPE_EXCLUDE_PREFIXES) and _has_mermaid_block(p)
    ]
    return sorted(files)


def _workdir_base() -> str:
    """Base dir for the render scratch tree — snap-readable, never cwd-relative.

    The local `mmdc` is the mermaid-cli *snap*, which runs in a private mount
    namespace where `/tmp` is NOT the host `/tmp`. The earlier behaviour anchored
    the scratch dir under the cwd (`dir="."`); when an agent worktree's cwd is
    itself under `/tmp`, that scratch dir lands in the snap's private `/tmp` and
    mmdc reports `Input file doesn't exist` for *every* block — a content-
    independent false-fail of the whole gate (#817). The snap can read the real
    `$HOME`, so anchor the scratch tree there to make the gate location-agnostic.

    Fall back to the platform temp dir (`$TMPDIR`/…) only when `$HOME` is unusable
    (e.g. a CI runner without HOME), where mmdc is the unconfined `npx` build and
    any writable location renders fine. CI is unaffected either way.
    """
    home = os.path.expanduser("~")
    if home and home != "~" and os.path.isdir(home):
        return home
    return tempfile.gettempdir()


def _resolve_mmdc() -> list[str] | None:
    env = os.environ.get("MMDC")
    if env:
        return [env]
    if shutil.which("mmdc"):
        return ["mmdc"]
    if shutil.which("npx"):
        return ["npx", "-y", "@mermaid-js/mermaid-cli"]
    return None


def _iter_blocks(text: str) -> list[tuple[int, str]]:
    """Return (1-based start line of the ```mermaid fence, block body)."""
    blocks: list[tuple[int, str]] = []
    for m in _MERMAID_BLOCK.finditer(text):
        line_no = text.count("\n", 0, m.start()) + 1
        blocks.append((line_no, m.group(2)))
    return blocks


def _render(mmdc: list[str], mmd: Path, out: Path, pp: Path) -> tuple[bool, str]:
    """Render one block. Return (ok, detail)."""
    try:
        proc = subprocess.run(
            [*mmdc, "-i", str(mmd), "-o", str(out), "-p", str(pp)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return False, "mmdc timed out (>120s)"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, tail[0] if tail else f"mmdc exit {proc.returncode}"
    if out.is_file():
        svg = out.read_text(encoding="utf-8", errors="replace").lower()
        if any(mark in svg for mark in _ERROR_MARKERS):
            return False, "rendered SVG contains a mermaid error marker"
    return True, "ok"


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv[1:]] or _default_files()
    files = [f for f in files if f.is_file()]
    if not files:
        print("check-mermaid: no input files.", file=sys.stderr)
        return 0

    mmdc = _resolve_mmdc()
    if mmdc is None:
        print(
            "check-mermaid: mmdc not found. Install @mermaid-js/mermaid-cli "
            "(npm i -g @mermaid-js/mermaid-cli) or set $MMDC.",
            file=sys.stderr,
        )
        return 2

    # Scratch dir anchored under a snap-readable base ($HOME), NOT cwd-relative:
    # the local mmdc snap has a private /tmp namespace, so a cwd-under-/tmp
    # worktree made the old `dir="."` scratch tree invisible to mmdc (#817).
    workdir = Path(tempfile.mkdtemp(prefix=".mmcheck-", dir=_workdir_base()))
    pp = workdir / "puppeteer.json"
    pp.write_text('{"args":["--no-sandbox"]}', encoding="utf-8")

    failures: list[str] = []
    total = 0
    try:
        for f in files:
            text = f.read_text(encoding="utf-8")
            for idx, (line_no, body) in enumerate(_iter_blocks(text)):
                total += 1
                if _has_raw_angle(body):
                    print(
                        f"  warning {f}:{line_no} — raw '<'/'>' in a mermaid block; "
                        "escape as #lt;/#gt; in labels (renders degraded otherwise, #786)."
                    )
                mmd = workdir / f"b{total}.mmd"
                mmd.write_text(body, encoding="utf-8")
                ok, detail = _render(mmdc, mmd, workdir / f"b{total}.svg", pp)
                where = f"{f}:{line_no} (block #{idx + 1})"
                if ok:
                    print(f"  ok   {where}")
                else:
                    failures.append(f"{where} — {detail}")
                    print(f"  FAIL {where} — {detail}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print(f"\nchecked {total} mermaid block(s) across {len(files)} file(s).")
    if failures:
        print(f"\n{len(failures)} mermaid block(s) failed to render:", file=sys.stderr)
        for fail in failures:
            print(f"  - {fail}", file=sys.stderr)
        return 1
    print("all mermaid blocks render cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
