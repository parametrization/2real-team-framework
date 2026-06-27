#!/usr/bin/env python3
"""Deterministic helpers for the /promotion-audit skill.

Every function in this module is a pure function: same inputs -> same
outputs. No clocks, no randomness, no transcript reads, no network.

The skill's SKILL.md drives these helpers in order. Tests live in
`.claude/skills/promotion-audit/tests/` and cover each helper plus a
smoke test on the current repo state.

Glossary
========
Memory
    A file under `~/.claude/projects/<proj>/memory/*.md` (the project's
    auto-memory area). Carries YAML frontmatter (schema in issue #152).

Section
    A level-2 heading (`## ...`) inside a charter file. Procedural
    sections are tagged with an HTML comment marker:
        ## Some procedural section <!-- promotion-target: skill -->
    Non-procedural sections MAY be tagged `<!-- promotion-target: none -->`
    for explicit opt-out. Untagged sections are treated as `none`.

Skill
    A subdirectory under `.claude/skills/{name}/` with `SKILL.md`. The
    SKILL.md may declare `promotion-target: hook` in its frontmatter to
    opt into hook-promotion audit.

Already-promoted
    A source (memory name or skill name) whose content has already been
    codified via the pipeline. Recognized by scanning charter/hooks.md
    for `Promotion provenance:` blocks (the format established by
    Hook 15 in PR #153, the worked example).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Frontmatter parsing (no PyYAML dependency — do it by hand for portability)
# ---------------------------------------------------------------------------

_FM_DELIM = "---"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a markdown doc into (frontmatter_dict, body).

    Returns ({}, text) if there is no frontmatter block. Parses a small
    subset of YAML: scalars, quoted strings, simple lists `['a', 'b']`,
    and nested one-level maps (indented two-space `key: value`).

    This is intentionally minimal — memory frontmatter schema is stable
    and well-defined in issue #152.
    """
    if not text.startswith(_FM_DELIM + "\n") and not text.startswith(_FM_DELIM + "\r\n"):
        return {}, text

    lines = text.splitlines(keepends=False)
    if not lines or lines[0].strip() != _FM_DELIM:
        return {}, text

    # Find the closing `---`
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FM_DELIM:
            close_idx = i
            break
    if close_idx is None:
        return {}, text

    fm_lines = lines[1:close_idx]
    body = "\n".join(lines[close_idx + 1 :])

    return _parse_simple_yaml(fm_lines), body


def _parse_simple_yaml(lines: list[str]) -> dict[str, Any]:
    """Parse a minimal YAML subset sufficient for memory/skill frontmatter."""
    result: dict[str, Any] = {}
    current_map: dict[str, Any] | None = None

    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        # Detect indentation — a two-space indent under a "key:" (no value)
        # means we are in a sub-map.
        stripped = raw.lstrip()
        indent = len(raw) - len(stripped)

        if indent >= 2 and current_map is not None:
            # Sub-map entry
            if ":" in stripped:
                k, _, v = stripped.partition(":")
                current_map[k.strip()] = _coerce_scalar(v.strip())
            continue

        # Top-level entry
        current_map = None
        if ":" not in stripped:
            continue
        k, _, v = stripped.partition(":")
        k = k.strip()
        v = v.strip()

        if not v:
            # Either a sub-map or an empty list placeholder.
            current_map = {}
            result[k] = current_map
            continue

        result[k] = _coerce_scalar(v)

    return result


_LIST_RE = re.compile(r"^\[(.*)\]$")


def _coerce_scalar(v: str) -> Any:
    """Turn a YAML scalar string into its Python value."""
    if not v:
        return ""
    # Quoted string
    if (v[0], v[-1]) in (('"', '"'), ("'", "'")):
        return v[1:-1]
    # Inline list
    m = _LIST_RE.match(v)
    if m:
        inner = m.group(1).strip()
        if not inner:
            return []
        parts = [p.strip() for p in inner.split(",")]
        return [_coerce_scalar(p) for p in parts]
    # Bool
    if v.lower() in ("true", "yes"):
        return True
    if v.lower() in ("false", "no"):
        return False
    # Int
    try:
        return int(v)
    except ValueError:
        return v


# ---------------------------------------------------------------------------
# Memory reading
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Memory:
    path: str
    name: str
    description: str
    type_: str
    promotion_target: Literal["charter", "skill", "hook", "none"]
    promotion_threshold: dict[str, int]
    referenced_in_retros: tuple[str, ...]
    status: Literal["active", "enforced-elsewhere", "superseded"]
    superseded_by: str
    supersedes: str
    requires_decision: bool
    body: str

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)


def read_memory(path: str) -> Memory:
    """Parse a single memory file into a Memory record."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    fm, body = parse_frontmatter(text)

    thresh = fm.get("promotion_threshold")
    if not isinstance(thresh, dict):
        thresh = {}
    # Normalize threshold subkeys.
    thresh_norm = {
        "retro_citations": int(thresh.get("retro_citations", 3) or 3),
        "skill_invocations": int(thresh.get("skill_invocations", 5) or 5),
    }

    refs = fm.get("referenced_in_retros", ())
    if isinstance(refs, str):
        # Tolerate a single-string shape.
        refs = (refs,) if refs else ()
    else:
        refs = tuple(refs or ())

    status = fm.get("status", "active")
    if status not in ("active", "enforced-elsewhere", "superseded"):
        status = "active"

    pt = fm.get("promotion_target", "none")
    if pt not in ("charter", "skill", "hook", "none"):
        pt = "none"

    return Memory(
        path=path,
        name=str(fm.get("name", os.path.basename(path))),
        description=str(fm.get("description", "")),
        type_=str(fm.get("type", "project")),
        promotion_target=pt,  # type: ignore[arg-type]
        promotion_threshold=thresh_norm,
        referenced_in_retros=refs,
        status=status,  # type: ignore[arg-type]
        superseded_by=str(fm.get("superseded_by", "")),
        supersedes=str(fm.get("supersedes", "")),
        requires_decision=bool(fm.get("requires_decision", False)),
        body=body,
    )


def read_all_memories(memory_dir: str) -> list[Memory]:
    """Read every `*.md` memory except the `MEMORY.md` index and `session_handoff.md`.

    Sorted deterministically by filename.
    """
    results: list[Memory] = []
    if not os.path.isdir(memory_dir):
        return results
    for name in sorted(os.listdir(memory_dir)):
        if not name.endswith(".md"):
            continue
        if name == "MEMORY.md":
            continue
        if name == "session_handoff.md":
            # Auto-generated; never promoted.
            continue
        path = os.path.join(memory_dir, name)
        if os.path.isfile(path):
            results.append(read_memory(path))
    return results


# ---------------------------------------------------------------------------
# Charter section reading
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CharterSection:
    path: str
    heading: str
    # Marker value: "skill", "hook", "none", or "" if no marker.
    promotion_target: str
    body: str
    # Any `<!-- promoted-to: skills/{slug} -->` back-reference found.
    promoted_to: str = ""


_SECTION_MARKER_RE = re.compile(
    r"^##\s+(?P<heading>.+?)\s*<!--\s*promotion-target:\s*(?P<target>skill|hook|none)\s*-->\s*$",
    re.MULTILINE,
)
_PROMOTED_TO_RE = re.compile(r"<!--\s*promoted-to:\s*(?P<dest>[^\s]+)\s*-->")


def read_charter_sections(charter_path: str) -> list[CharterSection]:
    """Extract level-2 sections that carry a promotion-target marker."""
    if not os.path.isfile(charter_path):
        return []
    with open(charter_path, encoding="utf-8") as f:
        src = f.read()

    # Find all level-2 headings (whether tagged or not) so we can slice bodies.
    headings = list(re.finditer(r"^(## .+)$", src, re.MULTILINE))

    results: list[CharterSection] = []
    for i, m in enumerate(headings):
        line = m.group(1)
        tag = _SECTION_MARKER_RE.match(line)
        if not tag:
            continue
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(src)
        body = src[start:end].strip()
        promoted = _PROMOTED_TO_RE.search(body)
        results.append(
            CharterSection(
                path=charter_path,
                heading=tag.group("heading").strip(),
                promotion_target=tag.group("target"),
                body=body,
                promoted_to=promoted.group("dest") if promoted else "",
            )
        )
    return results


def read_all_charter_sections(charter_parent: str) -> list[CharterSection]:
    """Scan charter.md + charter/*.md for marked sections.

    `charter_parent` is the directory **containing** the `charter/` subdir
    (typically `.claude/team`), NOT the `charter/` directory itself. Sibling
    of `find_already_promoted_in_charter` — same parameter semantics, same
    silent-empty failure mode if the caller passes the charter dir instead
    of its parent (issue #418).

    Sorted by (path, heading) for determinism.

    Raises:
        ValueError: if `charter_parent` is itself named `charter` — see #418.
    """
    if os.path.isdir(charter_parent) and (
        os.path.basename(os.path.normpath(charter_parent)) == "charter"
    ):
        raise ValueError(
            f"read_all_charter_sections({charter_parent!r}): "
            "argument is the charter directory itself — pass its parent "
            "(e.g. '.claude/team', not '.claude/team/charter'). "
            "See issue #418."
        )

    candidates: list[str] = []
    root_file = os.path.join(charter_parent, "charter.md")
    if os.path.isfile(root_file):
        candidates.append(root_file)

    subdir = os.path.join(charter_parent, "charter")
    if os.path.isdir(subdir):
        for name in sorted(os.listdir(subdir)):
            if name.endswith(".md"):
                candidates.append(os.path.join(subdir, name))

    results: list[CharterSection] = []
    for p in candidates:
        results.extend(read_charter_sections(p))

    results.sort(key=lambda s: (s.path, s.heading))
    return results


# ---------------------------------------------------------------------------
# Skill reading
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Skill:
    name: str
    path: str  # path to SKILL.md
    promotion_target: Literal["hook", "none"]
    description: str
    body: str


def read_all_skills(skills_dir: str) -> list[Skill]:
    """Discover skills in `.claude/skills/`. Sorted by name."""
    results: list[Skill] = []
    if not os.path.isdir(skills_dir):
        return results
    for name in sorted(os.listdir(skills_dir)):
        skill_md = os.path.join(skills_dir, name, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        with open(skill_md, encoding="utf-8") as f:
            text = f.read()
        fm, body = parse_frontmatter(text)
        pt = fm.get("promotion_target", "none")
        if pt not in ("hook", "none"):
            pt = "none"
        results.append(
            Skill(
                name=name,
                path=skill_md,
                promotion_target=pt,  # type: ignore[arg-type]
                description=str(fm.get("description", "")),
                body=body,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Signal counting
# ---------------------------------------------------------------------------


def count_retro_citations(memory: Memory, feedback_log_path: str) -> int:
    """Count occurrences of the memory name or filename in the feedback log.

    Counts the larger of:
      - occurrences of `memory.name` (title string)
      - occurrences of `memory.filename` (e.g., feedback_enforcement_hierarchy.md)

    Also adds `len(memory.referenced_in_retros)` as a floor — authors can
    manually record retro citations in frontmatter for cases where the log
    doesn't spell out the filename.
    """
    if not os.path.isfile(feedback_log_path):
        return len(memory.referenced_in_retros)
    with open(feedback_log_path, encoding="utf-8") as f:
        text = f.read()
    by_title = text.count(memory.name) if memory.name else 0
    by_file = text.count(memory.filename)
    return max(by_title, by_file, len(memory.referenced_in_retros))


def count_skill_invocations(skill_name: str, repo_root: str) -> int:
    """Count git log commits that reference the skill by slash-name.

    D4 lightweight: we do NOT scan transcripts. `git log --grep="/{skill}"`
    finds commit messages that reference the skill, which is a stable and
    durable signal for "this skill got invoked during real work."

    An empty or whitespace-only `skill_name` returns 0 — never the full
    commit count. `git log --grep=/` matches (nearly) every commit because
    almost all commit messages contain a slash, so a blank slug would
    report a huge invocation count and spuriously cross any threshold.
    This guard is the root-cause fix for the P5W4 24-spurious-AUTO mis-fire
    (main#690): hand-rolled callers passed an empty `section.promoted_to`
    slug straight through to this counter.
    """
    if not skill_name or not skill_name.strip():
        return 0
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                repo_root,
                "log",
                "--oneline",
                f"--grep=/{skill_name}",
                "--all",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 0
    if result.returncode != 0:
        return 0
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    return len(lines)


# ---------------------------------------------------------------------------
# Already-promoted detection (Q5)
# ---------------------------------------------------------------------------

_PROVENANCE_RE = re.compile(
    r"\*\*Promotion provenance:\*\*\s*(?P<body>.+?)(?:\n\n|\Z)",
    re.DOTALL,
)

# `<!-- Promoted from memory: <name>[.md] (optional trailing context) -->`
# The new charter-tier promotion marker (issue #283), used inline after a
# charter section heading instead of a `Promotion provenance:` block. The
# captured body runs until the closing `-->` so trailing context (date,
# rationale, retro reference) is included in the regex sweep that
# follows.
_HTML_COMMENT_PROMOTED_RE = re.compile(
    r"<!--\s*Promoted from memory:\s*(?P<body>.+?)\s*-->",
    re.DOTALL,
)

# Memory filenames can be cited with or without the `.md` suffix in
# charter prose (e.g. hooks.md L169 cites `feedback_honest_audit_over_conclusion_claim`
# unsuffixed inside a backticked span). The regex makes the `.md` optional
# and the caller backfills the suffix into the returned set so both forms
# are recognized in membership checks.
#
# Slash-command branch shape (#419): `(?<![\w/])/[a-z][a-z0-9-]{2,}` —
# kebab-case slash-commands, alpha-leading, length >= 3, AND preceded by
# a non-word/non-slash boundary. The alpha-leading filter rejects
# URL-path-fragment hits like `/198` (numeric issue IDs from gh URLs);
# the length-3 minimum rejects `/a`, `/b1`; and the lookbehind rejects
# mid-token slashes like `/supersedes` inside the prose `augments/supersedes`
# in charter/skills.md. Combined with `_strip_url_bodies` (applied to the
# block body BEFORE the regex runs), this rejects the 11 URL-fragment
# false positives documented in #419 plus the `augments/supersedes` 12th.
_SOURCE_HINT_RE = re.compile(
    r"""
    (?:
        (?:feedback|project|reference)_[a-z0-9_]+(?:\.md)?  # memory filenames (with or without .md)
        |
        (?<![\w/])/[a-z][a-z0-9-]{2,}                       # slash-commands at word boundary
    )
    """,
    re.VERBOSE,
)


# URL-stripping regexes (#419). Applied to provenance-block bodies BEFORE
# `_SOURCE_HINT_RE.finditer` so URL path fragments never reach the slash-
# command branch. Three forms:
#   - markdown link bodies: `[text](url)` → `[text]()` (preserves link text)
#   - autolinks: `<url>` → ``
#   - bare URLs: `https://...` → ``
# The link-text preservation matters because some link labels themselves
# contain a memory filename or slash-command reference that IS load-bearing.
_MD_LINK_URL_RE = re.compile(r"\]\(\s*<?(?:https?|ftp)://[^\s)>]+>?\s*\)")
_AUTOLINK_URL_RE = re.compile(r"<(?:https?|ftp)://[^>\s]+>")
_BARE_URL_RE = re.compile(r"(?<![\[\(])(?:https?|ftp)://[^\s)>]+")


def _strip_url_bodies(text: str) -> str:
    """Remove URL bodies from `text` while preserving non-URL prose.

    Applied to provenance-block bodies before `_SOURCE_HINT_RE.finditer`
    so URL path fragments (`/198`, `/issues`, `/noorinalabs-main`, etc.)
    never reach the slash-command branch as false positives (#419).
    Markdown link text is preserved by replacing `(url)` with `()`,
    leaving `[text]` intact — if a link label cites a real memory
    filename or slash-command, that reference still surfaces in the
    downstream regex sweep.
    """
    text = _MD_LINK_URL_RE.sub("]()", text)
    text = _AUTOLINK_URL_RE.sub("", text)
    text = _BARE_URL_RE.sub("", text)
    return text


# Memory-filename prefixes the parser recognizes. Used by
# `_normalize_memory_hit` to decide whether a no-suffix hit should be
# backfilled with `.md`.
_MEMORY_PREFIXES = ("feedback_", "project_", "reference_")


# Narrative words that indicate a forward-reference rather than a
# backward-looking promotion claim. A slash-command within a few words of
# any of these is excluded from the already-promoted set.
_FORWARD_REFERENCE_MARKERS = (
    "future",
    "planned",
    "design",
    "upcoming",
    "referenced by",
    "will reference",
    "proposed",
    "TBD",
)


def _is_forward_reference(body: str, match_start: int) -> bool:
    """Return True if `body[match_start:]` sits inside a forward-reference phrase.

    Looks backward up to 60 chars from the match position and forward up to
    20 chars; if any marker appears in that window, this is NOT a promotion
    claim — the hook author is just citing the future artifact by name.
    """
    start = max(0, match_start - 60)
    end = min(len(body), match_start + 20)
    window = body[start:end].lower()
    return any(marker in window for marker in _FORWARD_REFERENCE_MARKERS)


def _normalize_memory_hit(hit: str) -> tuple[str, ...]:
    """Return both forms (with and without `.md`) of a memory filename hit.

    The caller adds all returned strings to the already-promoted set so
    membership checks via `memory.filename` (always `.md`-suffixed) and
    via raw-name citation work transparently.

    For non-memory hits (slash-commands, anything else), returns a single-
    element tuple containing the hit unchanged.
    """
    if hit.startswith(_MEMORY_PREFIXES):
        if hit.endswith(".md"):
            return (hit, hit[:-3])
        return (hit, hit + ".md")
    return (hit,)


def find_already_promoted(charter_path: str) -> set[str]:
    """Return the set of source identifiers already promoted in `charter_path`.

    Recognizes BOTH provenance formats used across the charter:

    1. **Block style** (charter/hooks.md, the format Hook 15 established
       in PR #153):

           **Promotion provenance:** First end-to-end execution of the
           memory -> charter -> hook promotion pattern ratified by the
           owner on 2026-04-19. Rule lived in CLAUDE.md § Ontology ...

    2. **HTML-comment marker** (newer charter-tier-only promotions, per
       issue #283):

           <!-- Promoted from memory: feedback_X.md (P3W5 retro 2026-05-06) -->

       Used inline after a charter section heading when a memory is
       promoted into the charter without a corresponding hook.

    Slash-commands that appear inside forward-reference phrases (e.g.
    "referenced by the future `/promotion-audit` skill design") are
    EXCLUDED — those are narrative cross-references, not promotion claims.
    See `_FORWARD_REFERENCE_MARKERS`.

    Memory-filename citations are recognized in BOTH `.md`-suffixed and
    suffix-less forms (the latter appears in hooks.md L169's backticked
    cite of `feedback_honest_audit_over_conclusion_claim`). Both forms
    land in the returned set so callers using `memory.filename in
    already_promoted` continue to match transparently.

    For the aggregating scan across the full charter directory, use
    `find_already_promoted_in_charter()` — this single-path entry point
    is retained for the smoke test and for callers that want to scope
    the scan to a specific file.

    The returned set contains strings like:
        - "feedback_enforcement_hierarchy.md" / "feedback_enforcement_hierarchy"
        - "/ontology-librarian" (skill slash-commands with backward semantics)
        - "CLAUDE.md § Ontology" (rule references, when the Ontology
          section is cited in any provenance block)
    """
    refs: set[str] = set()
    if not os.path.isfile(charter_path):
        return refs
    with open(charter_path, encoding="utf-8") as f:
        text = f.read()

    # Block-style `**Promotion provenance:**` entries (hooks.md format).
    # URL bodies stripped first (#419) so gh-issue-link path fragments
    # never reach the slash-command branch.
    for block in _PROVENANCE_RE.finditer(text):
        body = _strip_url_bodies(block.group("body"))
        for hit in _SOURCE_HINT_RE.finditer(body):
            if _is_forward_reference(body, hit.start()):
                continue
            refs.update(_normalize_memory_hit(hit.group(0)))

    # HTML-comment style `<!-- Promoted from memory: X -->` (charter-tier
    # promotion marker, issue #283). Forward-reference filtering is
    # unnecessary for this format — the marker is by definition a
    # backward-looking promotion claim.
    for block in _HTML_COMMENT_PROMOTED_RE.finditer(text):
        body = _strip_url_bodies(block.group("body"))
        for hit in _SOURCE_HINT_RE.finditer(body):
            refs.update(_normalize_memory_hit(hit.group(0)))

    # The librarian rule's provenance cites CLAUDE.md § Ontology; capture
    # it as a synonym for the enforcement-hierarchy memory.
    if "CLAUDE.md § Ontology" in text:
        refs.add("CLAUDE.md § Ontology")
        refs.add("feedback_enforcement_hierarchy.md")
    return refs


def find_already_promoted_in_charter(charter_parent: str) -> set[str]:
    """Aggregate already-promoted refs across the full charter directory.

    `charter_parent` is the directory **containing** the `charter/` subdir
    (typically `.claude/team`), NOT the `charter/` directory itself.

    Scans `<charter_parent>/charter/*.md` (and the optional
    `<charter_parent>/charter.md` top-level file, if present) using the same
    recognition rules as `find_already_promoted()`. Returns the union of
    all per-file results.

    This is the entry point the /promotion-audit skill should use — single-
    file scope (charter/hooks.md only) misses charter-tier-only promotions
    that land via the HTML-comment marker in other sub-docs (issue #283).

    Raises:
        ValueError: if `charter_parent` is itself a directory named `charter`
            — a strong hint the caller passed the charter dir instead of its
            parent (issue #418 silent-zero bug). Returns set() for any other
            non-existent path (defensive contract preserved).
    """
    refs: set[str] = set()
    if not os.path.isdir(charter_parent):
        return refs

    if os.path.basename(os.path.normpath(charter_parent)) == "charter":
        raise ValueError(
            f"find_already_promoted_in_charter({charter_parent!r}): "
            "argument is the charter directory itself — pass its parent "
            "(e.g. '.claude/team', not '.claude/team/charter'). "
            "See issue #418."
        )

    candidates: list[str] = []
    root_file = os.path.join(charter_parent, "charter.md")
    if os.path.isfile(root_file):
        candidates.append(root_file)

    subdir = os.path.join(charter_parent, "charter")
    if os.path.isdir(subdir):
        for name in sorted(os.listdir(subdir)):
            if name.endswith(".md"):
                candidates.append(os.path.join(subdir, name))

    for path in candidates:
        refs.update(find_already_promoted(path))

    return refs


# ---------------------------------------------------------------------------
# Classification (Q1–Q5 locked)
# ---------------------------------------------------------------------------


DecisionKind = Literal["AUTO", "DECIDE", "KEPT", "SUPERSEDED", "ALREADY-PROMOTED"]


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    item_id: str  # display identifier (memory filename, section heading, skill name)
    from_tier: str  # "memory" | "charter" | "skill"
    to_tier: str  # "charter" | "skill" | "hook" | "-"
    signal: str
    reason: str
    # For AUTO: path to the source; for DECIDE: set by the caller to the
    # issue URL after creation.
    artifact_ref: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def classify_memory(
    memory: Memory,
    signals: dict[str, int],
    already_promoted: set[str],
) -> Decision:
    """Classify a memory for the memory → charter transition."""
    # ALREADY-PROMOTED always wins.
    if memory.filename in already_promoted or memory.name in already_promoted:
        return Decision(
            kind="ALREADY-PROMOTED",
            item_id=memory.filename,
            from_tier="memory",
            to_tier="charter",
            signal="provenance block in charter/hooks.md",
            reason="Source codified via Promotion provenance entry",
        )

    if memory.status == "superseded":
        return Decision(
            kind="SUPERSEDED",
            item_id=memory.filename,
            from_tier="memory",
            to_tier="-",
            signal=f"superseded_by: {memory.superseded_by or '(unset)'}",
            reason="Memory explicitly marked superseded",
        )

    if memory.status == "enforced-elsewhere":
        return Decision(
            kind="SUPERSEDED",
            item_id=memory.filename,
            from_tier="memory",
            to_tier="-",
            signal=f"enforced-elsewhere -> {memory.superseded_by or '(unset)'}",
            reason="Memory enforced via another artifact (charter / hook)",
        )

    citations = signals.get("retro_citations", 0)
    threshold = memory.promotion_threshold.get("retro_citations", 3)

    if memory.promotion_target == "none":
        # STALE-OPT-OUT informational class (#158): a memory marked
        # `promotion_target: none` is authoritative — the opt-out stands.
        # But when citations reach 2× the threshold, surface the entry in
        # an informational sub-list so operators can reconsider during
        # wave-retro. No auto-action, no issue filed; the kind stays KEPT.
        if citations >= 2 * threshold:
            return Decision(
                kind="KEPT",
                item_id=memory.filename,
                from_tier="memory",
                to_tier="-",
                signal=f"retro_citations={citations} >= 2 * {threshold}",
                reason=(
                    f"promotion_target=none, but cited {citations}x — "
                    "consider reviewing the opt-out"
                ),
                extra={"stale_opt_out": True},
            )
        return Decision(
            kind="KEPT",
            item_id=memory.filename,
            from_tier="memory",
            to_tier="-",
            signal=f"retro_citations={citations}",
            reason="promotion_target=none (informational memory)",
        )

    if memory.promotion_target != "charter":
        # Memories only promote to charter (skills promote to hook).
        return Decision(
            kind="KEPT",
            item_id=memory.filename,
            from_tier="memory",
            to_tier=memory.promotion_target,
            signal=f"retro_citations={citations}",
            reason=f"promotion_target={memory.promotion_target} is not a valid memory transition",
        )

    if citations < threshold:
        return Decision(
            kind="KEPT",
            item_id=memory.filename,
            from_tier="memory",
            to_tier="charter",
            signal=f"retro_citations={citations} < {threshold}",
            reason="Threshold not met",
        )

    if memory.requires_decision:
        return Decision(
            kind="DECIDE",
            item_id=memory.filename,
            from_tier="memory",
            to_tier="charter",
            signal=f"retro_citations={citations} >= {threshold}",
            reason="requires_decision=true escape hatch set",
        )

    return Decision(
        kind="AUTO",
        item_id=memory.filename,
        from_tier="memory",
        to_tier="charter",
        signal=f"retro_citations={citations} >= {threshold}",
        reason="Thresholds met; charter additions are safe to auto-apply",
    )


def classify_section(
    section: CharterSection,
    signals: dict[str, int],
) -> Decision:
    """Classify a charter section for the charter → skill transition."""
    if section.promoted_to:
        return Decision(
            kind="ALREADY-PROMOTED",
            item_id=f"{os.path.basename(section.path)} § {section.heading}",
            from_tier="charter",
            to_tier="skill",
            signal=f"promoted-to: {section.promoted_to}",
            reason="Section has a promoted-to back-reference",
        )

    if section.promotion_target == "none":
        return Decision(
            kind="KEPT",
            item_id=f"{os.path.basename(section.path)} § {section.heading}",
            from_tier="charter",
            to_tier="-",
            signal="promotion-target: none",
            reason="Section explicitly opted out of promotion",
        )

    if section.promotion_target != "skill":
        return Decision(
            kind="KEPT",
            item_id=f"{os.path.basename(section.path)} § {section.heading}",
            from_tier="charter",
            to_tier=section.promotion_target,
            signal=f"promotion-target: {section.promotion_target}",
            reason="Charter sections only promote to skill",
        )

    invocations = signals.get("skill_invocations", 0)
    threshold = signals.get("threshold", 5)

    if invocations < threshold:
        return Decision(
            kind="KEPT",
            item_id=f"{os.path.basename(section.path)} § {section.heading}",
            from_tier="charter",
            to_tier="skill",
            signal=f"skill_invocations={invocations} < {threshold}",
            reason="Invocation threshold not met; wait for more operator-invoked runs",
        )

    return Decision(
        kind="AUTO",
        item_id=f"{os.path.basename(section.path)} § {section.heading}",
        from_tier="charter",
        to_tier="skill",
        signal=f"skill_invocations={invocations} >= {threshold}",
        reason="Thresholds met; skill scaffold is safe to auto-generate",
    )


def classify_skill(
    skill: Skill,
    signals: dict[str, int],
    already_promoted: set[str],
) -> Decision:
    """Classify a skill for the skill → hook transition.

    Skill → hook is ALWAYS DECIDE per D6 (hooks are security-sensitive).
    """
    slash_name = f"/{skill.name}"
    if slash_name in already_promoted:
        return Decision(
            kind="ALREADY-PROMOTED",
            item_id=skill.name,
            from_tier="skill",
            to_tier="hook",
            signal=f"provenance block references {slash_name}",
            reason="Skill already enforced via a registered hook",
        )

    if skill.promotion_target != "hook":
        return Decision(
            kind="KEPT",
            item_id=skill.name,
            from_tier="skill",
            to_tier="-",
            signal="promotion-target != hook",
            reason="Skill not opted into hook promotion",
        )

    invocations = signals.get("skill_invocations", 0)
    threshold = signals.get("threshold", 5)

    if invocations < threshold:
        return Decision(
            kind="KEPT",
            item_id=skill.name,
            from_tier="skill",
            to_tier="hook",
            signal=f"skill_invocations={invocations} < {threshold}",
            reason="Invocation threshold not met",
        )

    # Always DECIDE — D6 locked.
    return Decision(
        kind="DECIDE",
        item_id=skill.name,
        from_tier="skill",
        to_tier="hook",
        signal=f"skill_invocations={invocations} >= {threshold}",
        reason="Skill → hook is always DECIDE (security-sensitive, D6)",
    )


# ---------------------------------------------------------------------------
# Audit table rendering
# ---------------------------------------------------------------------------


_KIND_ORDER = {
    "AUTO": 0,
    "DECIDE": 1,
    "KEPT": 2,
    "SUPERSEDED": 3,
    "ALREADY-PROMOTED": 4,
}


def render_audit_table(decisions: list[Decision], wave_name: str, audit_date: str) -> str:
    """Deterministic markdown rendering of the audit outcome.

    `audit_date` is passed in (not read from the clock) to preserve
    re-run determinism. Callers pin it to the wave boundary date from
    `cross-repo-status.json`.
    """
    auto = [d for d in decisions if d.kind == "AUTO"]
    decide = [d for d in decisions if d.kind == "DECIDE"]
    kept = [d for d in decisions if d.kind == "KEPT"]
    supers = [d for d in decisions if d.kind in ("SUPERSEDED", "ALREADY-PROMOTED")]

    # Deterministic sort within each bucket.
    for bucket in (auto, decide, kept, supers):
        bucket.sort(key=lambda d: (d.from_tier, d.item_id))

    out: list[str] = []
    out.append(f"## Promotion Audit — {wave_name} ({audit_date})")
    out.append("")
    out.append(
        f"**Summary:** {len(auto)} AUTO · {len(decide)} DECIDE · "
        f"{len(kept)} KEPT · {len(supers)} SUPERSEDED/ALREADY-PROMOTED"
    )
    out.append("")

    out.append("### AUTO-PROMOTED (artifacts generated this run)")
    if auto:
        out.append("| Item | From → To | Signal | Artifact |")
        out.append("|---|---|---|---|")
        for d in auto:
            artifact = d.artifact_ref or "-"
            row = f"| {d.item_id} | {d.from_tier} → {d.to_tier} | {d.signal} | {artifact} |"
            out.append(row)
    else:
        out.append("_None this run._")
    out.append("")

    out.append("### REQUIRES DECISION (issues filed)")
    if decide:
        out.append("| Item | Candidate target | Signal | Issue |")
        out.append("|---|---|---|---|")
        for d in decide:
            issue_ref = d.artifact_ref or "(pending)"
            row = f"| {d.item_id} | {d.from_tier} → {d.to_tier} | {d.signal} | {issue_ref} |"
            out.append(row)
    else:
        out.append("_None this run._")
    out.append("")

    out.append("### KEPT (no action — informational)")
    # Split KEPT into stale-opt-out flagged vs the rest. STALE-OPT-OUT
    # entries (#158) are informational callouts — high-citation memories
    # whose `promotion_target: none` opt-out has crossed 2× the threshold.
    # They render as a separate sub-list so operators can spot drift
    # without changing how the rest of KEPT is presented.
    stale = [d for d in kept if d.extra.get("stale_opt_out")]
    others = [d for d in kept if not d.extra.get("stale_opt_out")]

    if not kept:
        out.append("_None._")
    else:
        if others:
            for d in others:
                out.append(f"- `{d.item_id}` ({d.from_tier}): {d.reason} [{d.signal}]")
        if stale:
            if others:
                out.append("")
            out.append("**STALE-OPT-OUT (review the opt-out — informational only):**")
            for d in stale:
                out.append(f"- `{d.item_id}` ({d.from_tier}): {d.reason} [{d.signal}]")
    out.append("")

    out.append("### SUPERSEDED / ALREADY-PROMOTED (no action — informational)")
    if supers:
        for d in supers:
            out.append(f"- `{d.item_id}` ({d.from_tier}): {d.reason} [{d.signal}]")
    else:
        out.append("_None._")
    out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Artifact generation (templated)
# ---------------------------------------------------------------------------


def _read_template(template_dir: str, name: str) -> str:
    with open(os.path.join(template_dir, name), encoding="utf-8") as f:
        return f.read()


def generate_charter_section(memory: Memory, template_dir: str) -> str:
    """Render a charter-section artifact from a memory using the template.

    The template emits the canonical HTML-comment provenance marker per
    charter/skills.md § Promotion Pipeline Marker Convention (#393); the
    italic-prose `_Promoted from memory ..._` line that this template used
    pre-#393 was not parser-recognized and is now banned.
    """
    tpl = _read_template(template_dir, "charter-section.md")
    return (
        tpl.replace("{{MEMORY_NAME}}", memory.name)
        .replace("{{MEMORY_FILENAME}}", memory.filename)
        .replace("{{BODY}}", memory.body.strip())
    )


def generate_skill_scaffold(section: CharterSection, template_dir: str) -> str:
    """Render a SKILL.md scaffold from a charter section using the template."""
    tpl = _read_template(template_dir, "skill-scaffold.md")
    slug = _slugify(section.heading)
    return (
        tpl.replace("{{SECTION_HEADING}}", section.heading)
        .replace("{{SECTION_BODY}}", section.body.strip())
        .replace("{{SOURCE_CHARTER}}", os.path.basename(section.path))
        .replace("{{SKILL_SLUG}}", slug)
    )


def generate_hook_draft_issue(skill: Skill, template_dir: str) -> dict[str, str]:
    """Render a hook-draft issue body; returns {'title': ..., 'body': ...}."""
    tpl = _read_template(template_dir, "hook-draft.md")
    body = (
        tpl.replace("{{SKILL_NAME}}", skill.name)
        .replace("{{SKILL_DESCRIPTION}}", skill.description)
        .replace("{{SKILL_BODY}}", skill.body.strip())
    )
    title = f"feat(hooks): draft — promote /{skill.name} skill to hook (promotion-audit)"
    return {"title": title, "body": body}


def _slugify(text: str) -> str:
    """Turn a heading like 'Load-Bearing Followups' into 'load-bearing-followups'."""
    t = text.lower().strip()
    t = re.sub(r"[^a-z0-9]+", "-", t)
    t = t.strip("-")
    return t or "section"
