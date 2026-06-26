# Generic Lib Prompt: Dockerfile Base-Image Pin + Distro-Upgrade Lint

## Purpose

Enforce that every `FROM` in a Dockerfile uses a **digest-pinned tag**
(`image:tag@sha256:<digest>`) **combined with an in-image package upgrade**,
closing the two supply-chain drift modes a floating tag leaves open:
floating-tag drift (the tag moves under you) and within-tag package drift (the
OS packages inside a pinned tag still carry new CVEs until you upgrade them).

It is a deterministic, stdlib-only gate with the conventional `0/1/2` exit-code
shape so it wires identically into a pre-commit hook and a CI job.

## Reusable Pattern

- **Parse only the keyword you care about** (`FROM`), case-insensitively. Strip a
  leading `--platform=` flag and a trailing `AS <stage>` to isolate the image ref.
- **Distro family inferred from the image name**, each with its own required
  upgrade signature searched over that stage's body:
  - Alpine → `apk upgrade`;
  - Debian/glibc default → `apt`/`apt-get … upgrade` (NOT bare `apt-get update`);
  - Distroless → no package manager, pin-only is sufficient.
- **Explicit exemptions:** `scratch`; a `FROM` that references an earlier build
  stage (it inherits the upstream pin); and a vendor image documented with an
  inline `# RATIONALE:` comment on the `FROM` line or the line directly above.
- **Stage-aware:** record each stage's name so a later `FROM <stage>` is
  recognised as a stage reference, not an unpinned external image.
- **Each violation is one human-readable `path:line: FROM <image> — <why>` line.**

## Algorithm

1. Regex-match each `FROM` line; capture the rest, strip inline comment, strip
   `--platform=`, split off `AS <stage>`, take the first token as the image.
2. Compute exemption: `scratch`, or image name is a previously-defined stage, or
   a `# RATIONALE:` is present on/above the line. Then register this stage's name.
3. If not exempt: require `@sha256:` in the image; otherwise emit a not-pinned
   violation.
4. Slice the stage body (from this `FROM` to the next `FROM`/EOF). Distroless →
   skip upgrade check. Alpine → require the `apk upgrade` signature. Else →
   require the apt-upgrade signature.
5. Exit 1 if any violations, 0 if clean, 2 on usage / file-not-found.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Lint Dockerfile FROM statements for digest-pin + distro-upgrade compliance.

Exit codes: 0 compliant/exempt, 1 violation(s), 2 usage/file-not-found.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_FROM_RE = re.compile(r"^\s*FROM\s+(?P<rest>\S.*?)\s*$", re.IGNORECASE)
_PLATFORM_RE = re.compile(r"^--platform=\S+\s+", re.IGNORECASE)
_AS_RE = re.compile(r"\s+AS\s+(?P<stage>\S+)\s*$", re.IGNORECASE)
_ALPINE_UPGRADE_RE = re.compile(r"\bapk\s+upgrade\b", re.IGNORECASE)
_DEBIAN_UPGRADE_RE = re.compile(r"\bapt(?:-get)?\s+(?:-{1,2}\S+\s+)*upgrade\b", re.IGNORECASE)
_RATIONALE_RE = re.compile(r"#\s*RATIONALE:", re.IGNORECASE)


class FromStmt:
    def __init__(self, lineno: int, image: str, stage: str | None, rationale: bool):
        self.lineno, self.image, self.stage, self.has_rationale = lineno, image, stage, rationale


def _preceding_has_rationale(lines: list[str], idx: int) -> bool:
    j = idx - 1
    while j >= 0:
        s = lines[j].strip()
        if s == "":
            j -= 1
            continue
        return bool(_RATIONALE_RE.search(s)) if s.startswith("#") else False
    return False


def parse_froms(text: str) -> list[FromStmt]:
    lines, out = text.splitlines(), []
    for idx, raw in enumerate(lines):
        m = _FROM_RE.match(raw)
        if not m:
            continue
        rest = m.group("rest")
        rationale = bool(_RATIONALE_RE.search(raw)) or _preceding_has_rationale(lines, idx)
        code = _PLATFORM_RE.sub("", rest.split("#", 1)[0].strip()).strip()
        stage = None
        am = _AS_RE.search(code)
        if am:
            stage = am.group("stage")
            code = code[:am.start()].strip()
        image = code.split()[0] if code.split() else ""
        out.append(FromStmt(idx + 1, image, stage, rationale))
    return out


def check_dockerfile_text(path: str, text: str) -> list[str]:
    lines, froms, defined, violations = text.splitlines(), parse_froms(text), set(), []
    for i, stmt in enumerate(froms):
        nxt = froms[i + 1].lineno if i + 1 < len(froms) else None
        img = stmt.image.lower()
        exempt = img == "scratch" or img in defined or stmt.has_rationale
        if stmt.stage:
            defined.add(stmt.stage.lower())
        if exempt:
            continue
        if "@sha256:" not in stmt.image:
            violations.append(f"{path}:{stmt.lineno}: FROM {stmt.image} — not digest-pinned")
        body = "\n".join(lines[stmt.lineno:(nxt - 1) if nxt else len(lines)])
        if "distroless" in img:
            continue
        if "alpine" in img:
            if not _ALPINE_UPGRADE_RE.search(body):
                violations.append(f"{path}:{stmt.lineno}: FROM {stmt.image} — missing apk upgrade")
        elif not _DEBIAN_UPGRADE_RE.search(body):
            violations.append(f"{path}:{stmt.lineno}: FROM {stmt.image} — missing apt upgrade")
    return violations


def main(argv: list[str]) -> int:
    paths = argv[1:]
    if not paths:
        print("usage: check_dockerfile_base_pin.py <Dockerfile> ...", file=sys.stderr)
        return 2
    all_v: list[str] = []
    for p in paths:
        path = Path(p)
        if not path.is_file():
            print(f"ERROR: not a file: {p}", file=sys.stderr)
            return 2
        all_v += check_dockerfile_text(str(path), path.read_text(encoding="utf-8"))
    if all_v:
        print("Base-image pinning violations:")
        for v in all_v:
            print(f"  {v}")
        return 1
    print("OK: all FROM statements are digest-pinned with the required upgrade.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

## Adaptation Notes

- **Adjust the distro table to your base images.** Add families (e.g. a yum/dnf
  upgrade signature for RHEL-family bases) by adding one regex and one branch.
- **The exemption set is policy.** Keep `scratch` + stage-reference inheritance;
  decide whether you allow the `# RATIONALE:` escape hatch and what marker spells
  it.
- **`apt-get update` is deliberately not a match.** "update" refreshes the index;
  only "upgrade" installs newer packages — the regex demands the latter.
- **Same CLI/exit shape as your other gates** so the pre-commit and CI wiring is
  copy-paste, and a sync-drift gate can classify it as a known check kind.
```
