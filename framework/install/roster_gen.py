#!/usr/bin/env python3
"""Repo-introspecting roster generator for the 2real framework bootstrap.

Generates a simulated-team roster BY EXAMINING THE TARGET REPO at install time:

  1. Detect the repo model — single repo, or a meta-repo with child repos.
  2. For each repo, sniff the tech stack from marker files (Python, Node/TS,
     frontend frameworks, Rust/Go/Java, Docker/Terraform/K8s, CI, data, auth).
  3. Derive a role/persona mix that fits what was found (a small focused team for
     a single library; a cross-repo org with per-domain engineers for a
     meta+children layout).
  4. Assign personas (names from a built-in diverse pool, emails from the
     configured ``identity.email_pattern``) and write the roster artifacts into
     ``<repo>/.claude/team/``: ``roster.json`` (the name->email allowlist the
     commit-identity hook reads), one persona card per member, a seeded
     ``trust_matrix.md``, and an empty ``feedback_log.md``.

Determinism is the priority: given the same repo + flags the output is identical
(personas are drawn from the pool in a stable order). An interactive mode lets
the operator review/adjust the detected model and proposed roles before writing.

Stdlib only. Importable (``plan`` / ``apply``) and used by ``bootstrap.py``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------- name pool

# A diverse, deterministic pool. Assigned in order; stable across runs so a
# re-bootstrap reproduces the same roster. Extend freely.
_NAME_POOL: list[str] = [
    "Aria Okafor", "Mateo Reyes", "Nadia Haddad", "Kenji Watanabe",
    "Priya Nair", "Lucas Almeida", "Ingrid Larsson", "Omar Farouk",
    "Mei Lin", "Sofia Castellanos", "Dmitri Volkov", "Amara Diallo",
    "Tomas Novak", "Yuki Tanaka", "Leila Karimi", "Kofi Mensah",
    "Hana Park", "Diego Moreno", "Freya Andersen", "Rashid Al-Amin",
    "Camila Rossi", "Jian Wei", "Noa Cohen", "Thabo Nkosi",
    "Elena Petrova", "Arjun Mehta", "Saoirse Walsh", "Tariq Hassan",
    "Lin Chen", "Marisol Vega", "Bjorn Eriksson", "Aisha Bello",
]


def _split_name(full: str) -> tuple[str, str]:
    parts = full.split()
    return parts[0], parts[-1]


def _email_for(full: str, pattern: str) -> str:
    first, last = _split_name(full)
    return pattern.replace("{First}", first).replace("{Last}", last)


def _agent_name(full: str) -> str:
    first, last = _split_name(full)
    return f"{first.lower()}-{last.lower()}"


# --------------------------------------------------------------- role → domains

# Org-level coordination roles: they live in the META roster only and (via the
# parent-merge in validate_commit_identity) may commit in any child repo. They
# are NOT scoped to a single child's stacks.
_ORG_ROLES: set[str] = {
    "Program Director",
    "Technical Program Manager",
    "QA Engineer",
    "Standards & Quality Lead",
}

# The Tech Lead spans every repo — it appears in the meta roster AND every child
# roster (so a child cloned in isolation still has a lead identity).
_LEAD_ROLE = "Tech Lead"

# Domain engineer role -> the stack tags it serves. A persona is assigned to a
# child repo iff its domains intersect that child's sniffed stacks. Keep this in
# sync with derive_roles (the roles it can emit).
_ROLE_DOMAINS: dict[str, set[str]] = {
    "Frontend Engineer": {"frontend"},
    "Data Engineer": {"data", "database"},
    "DevOps Engineer": {"infra", "docker", "kubernetes", "ci"},
    "Security Engineer": {"security"},
    "Software Engineer": {"python", "node", "typescript", "go", "rust", "java", "backend"},
}


def _role_domains(role: str) -> set[str]:
    """Stack tags a role serves (empty for org-level / lead roles)."""
    return _ROLE_DOMAINS.get(role, set())


# --------------------------------------------------------------- stack sniffing

# marker (relative path or glob) -> stack tag
_STACK_MARKERS: list[tuple[str, str]] = [
    ("pyproject.toml", "python"), ("setup.py", "python"), ("requirements.txt", "python"),
    ("package.json", "node"), ("tsconfig.json", "typescript"),
    ("Cargo.toml", "rust"), ("go.mod", "go"),
    ("pom.xml", "java"), ("build.gradle", "java"),
    ("Dockerfile", "docker"), ("docker-compose.yml", "docker"), ("compose.yaml", "docker"),
    ("Chart.yaml", "kubernetes"),
]
_GLOB_MARKERS: list[tuple[str, str]] = [
    ("*.tf", "infra"), ("**/*.tf", "infra"),
    ("**/migrations", "database"), ("alembic.ini", "database"), ("prisma/schema.prisma", "database"),
    (".github/workflows/*.yml", "ci"), (".github/workflows/*.yaml", "ci"),
]
# package.json dependency substrings -> stack tag
_FRONTEND_DEPS = ("react", "vue", "svelte", "next", "astro", "@angular")
# repo-name substrings -> stack tag (the cheapest signal for domain)
_NAME_HINTS: list[tuple[str, str]] = [
    ("auth", "security"), ("user", "security"), ("identity", "security"),
    ("web", "frontend"), ("ui", "frontend"), ("frontend", "frontend"), ("landing", "frontend"),
    ("api", "backend"), ("service", "backend"), ("server", "backend"),
    ("data", "data"), ("ingest", "data"), ("pipeline", "data"), ("etl", "data"),
    ("deploy", "infra"), ("infra", "infra"), ("ops", "infra"),
    ("design", "frontend"), ("ml", "data"),
]


def sniff_stacks(repo_path: Path) -> set[str]:
    """Return the set of stack tags detected under ``repo_path`` (shallow + cheap)."""
    stacks: set[str] = set()
    if not repo_path.is_dir():
        return stacks
    for marker, tag in _STACK_MARKERS:
        if (repo_path / marker).exists():
            stacks.add(tag)
    for pattern, tag in _GLOB_MARKERS:
        try:
            if next(repo_path.glob(pattern), None) is not None:
                stacks.add(tag)
        except (OSError, ValueError):
            pass
    # frontend detection via package.json deps
    pj = repo_path / "package.json"
    if pj.is_file():
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if any(any(fd in d for fd in _FRONTEND_DEPS) for d in deps):
                stacks.add("frontend")
        except (OSError, json.JSONDecodeError):
            pass
    # name hints
    name_lc = repo_path.name.lower()
    for hint, tag in _NAME_HINTS:
        if hint in name_lc:
            stacks.add(tag)
    return stacks


def detect_child_repos(target: Path) -> list[Path]:
    """Child repos = immediate subdirs that are their own git repo (have .git)."""
    children: list[Path] = []
    for child in sorted(target.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if (child / ".git").exists():
            children.append(child)
    return children


# --------------------------------------------------------------- introspection


@dataclass
class RepoInfo:
    name: str
    path: Path
    stacks: set[str] = field(default_factory=set)


@dataclass
class Introspection:
    model: str  # "single-repo" | "meta-and-children"
    repos: list[RepoInfo]

    @property
    def all_stacks(self) -> set[str]:
        out: set[str] = set()
        for r in self.repos:
            out |= r.stacks
        return out


def introspect(target: Path, *, declared_model: str | None = None,
               declared_repos: list[str] | None = None) -> Introspection:
    """Examine ``target`` and return its model + per-repo stacks.

    A declared model/repos from config wins over filesystem detection (so an
    operator can override). A declared repo LIST is used verbatim — even when
    empty, it never falls back to detection (no detection surprises for a
    config-driven meta install). Otherwise: child repos present ->
    meta-and-children; a declared ``child`` model is single-repo-shaped.
    """
    target = target.resolve()
    if declared_repos is not None:
        children = [target / r for r in declared_repos if (target / r).is_dir()]
    else:
        children = detect_child_repos(target)

    model = declared_model or ("meta-and-children" if children else "single-repo")

    repos: list[RepoInfo] = []
    if model == "meta-and-children" and children:
        # include the meta repo itself (often holds shared config) + children
        repos.append(RepoInfo(target.name, target, sniff_stacks(target)))
        for c in children:
            repos.append(RepoInfo(c.name, c, sniff_stacks(c)))
    else:
        repos.append(RepoInfo(target.name, target, sniff_stacks(target)))
    return Introspection(model=model, repos=repos)


# --------------------------------------------------------------- role derivation


def derive_roles(intro: Introspection, *, team_size: int | None = None) -> list[tuple[str, str]]:
    """Derive a fitting (role, level) list from the introspection.

    Deterministic. The mix reflects detected model + stacks; ``team_size`` (if
    given) trims or pads the engineer ranks to hit the target headcount.
    """
    roles: list[tuple[str, str]] = []
    stacks = intro.all_stacks
    n_repos = len(intro.repos)

    if intro.model == "meta-and-children":
        roles.append(("Program Director", "Senior VP"))
        roles.append(("Technical Program Manager", "Staff"))
    roles.append(("Tech Lead", "Staff"))

    # domain engineers from detected stacks
    if stacks & {"python", "node", "go", "rust", "java", "backend"}:
        roles.append(("Software Engineer", "Senior"))
    if "frontend" in stacks:
        roles.append(("Frontend Engineer", "Senior"))
    if "data" in stacks:
        roles.append(("Data Engineer", "Senior"))
    if stacks & {"infra", "docker", "kubernetes"}:
        roles.append(("DevOps Engineer", "Senior"))
    if "security" in stacks:
        roles.append(("Security Engineer", "Senior"))

    # always have at least one generalist engineer
    if not any(r[0].endswith("Engineer") for r in roles):
        roles.append(("Software Engineer", "Senior"))

    # scale engineers with repo count (one extra SWE per ~2 child repos)
    extra = max(0, (n_repos - 1) // 2)
    roles.extend([("Software Engineer", "Mid")] * extra)

    # quality roles
    roles.append(("QA Engineer", "Senior"))
    if intro.model == "meta-and-children" or len(roles) >= 6:
        roles.append(("Standards & Quality Lead", "Staff"))

    # honour an explicit team_size by trimming/padding the non-required ranks
    if team_size is not None and team_size > 0:
        if len(roles) > team_size:
            # keep the leading (more senior / required) roles
            roles = roles[:team_size]
        else:
            while len(roles) < team_size:
                roles.append(("Software Engineer", "Mid"))
    return roles


# --------------------------------------------------------------- persona assembly


@dataclass
class Persona:
    name: str
    role: str
    level: str
    email: str
    agent_name: str
    domains: set[str] = field(default_factory=set)

    @property
    def is_org(self) -> bool:
        """Org-level coordination role — meta roster only, commits anywhere."""
        return self.role in _ORG_ROLES

    @property
    def is_lead(self) -> bool:
        """Spans every repo (meta + every child roster)."""
        return self.role == _LEAD_ROLE


def assign_personas(roles: list[tuple[str, str]], email_pattern: str) -> list[Persona]:
    """Map roles onto distinct names from the pool, deterministically."""
    personas: list[Persona] = []
    for i, (role, level) in enumerate(roles):
        if i >= len(_NAME_POOL):
            # pool exhausted — synthesize stable filler names
            name = f"Member {i + 1}"
        else:
            name = _NAME_POOL[i]
        personas.append(
            Persona(
                name=name,
                role=role,
                level=level,
                email=_email_for(name, email_pattern),
                agent_name=_agent_name(name),
                domains=_role_domains(role),
            )
        )
    return personas


def partition_for_children(
    personas: list[Persona], intro: Introspection
) -> tuple[list[Persona], dict[str, list[Persona]]]:
    """Split personas into the meta roster + a per-child roster (union model).

    Returns ``(meta_personas, {child_name: [personas]})`` where:

      * **meta_personas** — org-level coordination roles + the Tech Lead, plus
        any domain engineer that matched no child (fallback so nobody is
        dropped). These are the META roster; via the parent-merge in
        ``validate_commit_identity`` they may commit in any child.
      * **child rosters** — for each child repo: the Tech Lead (so a child
        cloned alone has a lead identity) + every domain engineer whose
        ``domains`` intersect that child's sniffed stacks.

    The full per-child allowlist the identity gate enforces is
    ``meta ∪ child`` (reconstructed at validate time), so a child PR is signable
    by that child's engineers AND the org leads, but not by another child's
    engineers. Single-repo introspections never call this (only one repo).

    Deterministic: input persona order is preserved in every output list.
    """
    # The meta/target repo is repos[0]; children are repos[1:]. Domain engineers
    # are scoped to CHILDREN, not the meta repo (which typically holds only
    # shared config).
    children = [r for r in intro.repos[1:]]
    leads = [p for p in personas if p.is_lead]
    org = [p for p in personas if p.is_org]
    engineers = [p for p in personas if not p.is_org and not p.is_lead]

    child_rosters: dict[str, list[Persona]] = {}
    assigned: set[str] = set()
    for child in children:
        members = list(leads)  # the lead spans every child
        for eng in engineers:
            if eng.domains & child.stacks:
                members.append(eng)
                assigned.add(eng.name)
        child_rosters[child.name] = members

    # Engineers that matched no child fall back into the meta roster so they are
    # never silently dropped from the allowlist.
    unassigned = [e for e in engineers if e.name not in assigned]
    meta_personas = leads + org + unassigned
    return meta_personas, child_rosters


@dataclass
class RosterPlan:
    intro: Introspection
    personas: list[Persona]

    def summary(self) -> str:
        lines = [f"model: {self.intro.model}  ({len(self.intro.repos)} repo(s))"]
        for r in self.intro.repos:
            stacks = ", ".join(sorted(r.stacks)) or "—"
            lines.append(f"  - {r.name}: [{stacks}]")
        lines.append(f"proposed team ({len(self.personas)}):")
        for p in self.personas:
            lines.append(f"  - {p.name} — {p.role} ({p.level}) <{p.email}>")
        return "\n".join(lines)


def plan(target: Path, *, email_pattern: str, declared_model: str | None = None,
         declared_repos: list[str] | None = None, team_size: int | None = None) -> RosterPlan:
    """Introspect + derive + assign, without writing anything."""
    intro = introspect(target, declared_model=declared_model, declared_repos=declared_repos)
    roles = derive_roles(intro, team_size=team_size)
    personas = assign_personas(roles, email_pattern)
    return RosterPlan(intro=intro, personas=personas)


# --------------------------------------------------------------- writers

_CARD_TEMPLATE = """# Team Member Roster Card

## Identity
- **Name:** {name}
- **Role:** {role}
- **Level:** {level}
- **Status:** Active

## Git Identity
- **user.name:** {name}
- **user.email:** {email}

## Personality Profile
*Seed this with the persona's communication style + background, or generate it.*

## Tech Preferences
*Evolves with project experience.*

## Learned Adjustments
*Evidence-fed, append-only. A retro appends a row only when a countable wave
signal supports it (PRs merged, must-fix items caught/received, CI-red merges,
rework cycles).*

| Wave | Adjustment | Evidence |
|------|-----------|----------|
"""


def _card_filename(p: Persona) -> str:
    role_slug = p.role.lower().replace(" & ", "_").replace(" ", "_")
    return f"{role_slug}_{p.agent_name}.md"


def _emit(report: dict, anchor: Path, path: Path, content: str, *, force: bool, dry_run: bool) -> None:
    """Write ``content`` to ``path`` honouring force/dry-run; record in report.

    ``anchor`` is the repo root the relative path in the report is computed
    against (so a child write reads ``.claude/team/roster.json`` not an absolute
    path).
    """
    rel = str(path.relative_to(anchor)) if anchor in path.parents else str(path)
    if path.exists() and not force:
        report["skipped"].append(rel)
        return
    if dry_run:
        report["would_write"].append(rel)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    report["written"].append(rel)


def _trust_matrix(personas: list[Persona]) -> str:
    tm = ["# Trust Matrix", "", "Mechanical 1-5 scores, updated from countable wave signals.", "",
          "| Member | Role | Score | Last updated |", "|--------|------|:-----:|--------------|"]
    for p in personas:
        tm.append(f"| {p.name} | {p.role} | 3 | (seed) |")
    return "\n".join(tm) + "\n"


def _write_team(
    team_dir: Path,
    *,
    allowlist: list[Persona],
    cards_for: list[Persona],
    org_artifacts_for: list[Persona] | None,
    report: dict,
    force: bool,
    dry_run: bool,
) -> None:
    """Write one team dir: roster.json + persona cards (+ org artifacts if asked).

    ``allowlist`` becomes ``roster.json`` (the name->email gate allowlist).
    ``cards_for`` get a persona card each. ``org_artifacts_for`` (when not None)
    seeds ``trust_matrix.md`` + ``feedback_log.md`` — meta-level only; per-child
    team dirs pass None (trust/feedback are org-wide, kept at the meta).
    """
    anchor = team_dir.parent.parent  # repo root
    roster_dir = team_dir / "roster"

    roster_map = {p.name: p.email for p in allowlist}
    _emit(report, anchor, team_dir / "roster.json", json.dumps(roster_map, indent=2) + "\n",
          force=force, dry_run=dry_run)

    for p in cards_for:
        _emit(report, anchor, roster_dir / _card_filename(p),
              _CARD_TEMPLATE.format(name=p.name, role=p.role, level=p.level, email=p.email),
              force=force, dry_run=dry_run)

    if org_artifacts_for is not None:
        _emit(report, anchor, team_dir / "trust_matrix.md", _trust_matrix(org_artifacts_for),
              force=force, dry_run=dry_run)
        _emit(report, anchor, team_dir / "feedback_log.md",
              "# Feedback Log\n\nPer-wave retros: going-well, pain points, proposed changes.\n",
              force=force, dry_run=dry_run)


def write_roster(team_dir: Path, plan_: RosterPlan, *, force: bool, dry_run: bool) -> dict:
    """Write the roster artifacts for the planned team.

    Single-repo: one team dir at ``team_dir`` with the full roster, all cards,
    and the org artifacts (trust_matrix + feedback_log).

    Child: one team dir with the roster + cards but NO org artifacts —
    trust/feedback are org-wide and live at the parent meta-repo; the identity
    gate's parent-merge unions this roster with the meta roster.

    Meta-and-children: the META roster (org roles + lead + unmatched engineers)
    plus org artifacts and ALL persona cards land at ``team_dir``; each child
    repo gets its own ``<child>/.claude/team/roster.json`` + that child's persona
    cards (Tech Lead + the child's domain engineers). The identity gate
    reconstructs each child's full allowlist as ``meta ∪ child`` via its
    parent-merge.
    """
    report: dict = {"written": [], "skipped": [], "would_write": []}

    if plan_.intro.model != "meta-and-children" or len(plan_.intro.repos) <= 1:
        org_for = None if plan_.intro.model == "child" else plan_.personas
        _write_team(team_dir, allowlist=plan_.personas, cards_for=plan_.personas,
                    org_artifacts_for=org_for, report=report, force=force, dry_run=dry_run)
        return report

    meta_personas, child_rosters = partition_for_children(plan_.personas, plan_.intro)

    # Meta team dir: org allowlist, org artifacts, but cards for the WHOLE org
    # (the meta dir documents every persona; the child dirs duplicate the cards
    # of their own members for self-containment).
    _write_team(team_dir, allowlist=meta_personas, cards_for=plan_.personas,
                org_artifacts_for=plan_.personas, report=report, force=force, dry_run=dry_run)

    # Per-child team dirs (children = intro.repos[1:]).
    for child in plan_.intro.repos[1:]:
        members = child_rosters.get(child.name, [])
        if not members:
            continue
        child_team_dir = child.path / ".claude" / "team"
        _write_team(child_team_dir, allowlist=members, cards_for=members,
                    org_artifacts_for=None, report=report, force=force, dry_run=dry_run)

    return report
