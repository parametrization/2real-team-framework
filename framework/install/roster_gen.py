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
    operator can override). Otherwise: child repos present -> meta-and-children.
    """
    target = target.resolve()
    children = detect_child_repos(target)
    if declared_repos:
        child_paths = [target / r for r in declared_repos if (target / r).is_dir()]
        children = child_paths or children

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
            )
        )
    return personas


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


def write_roster(team_dir: Path, plan_: RosterPlan, *, force: bool, dry_run: bool) -> dict:
    """Write roster.json + persona cards + trust_matrix.md + feedback_log.md."""
    report: dict = {"written": [], "skipped": [], "would_write": []}
    roster_dir = team_dir / "roster"

    def _emit(path: Path, content: str) -> None:
        rel = str(path.relative_to(team_dir.parent.parent)) if team_dir.parent.parent in path.parents else str(path)
        if path.exists() and not force:
            report["skipped"].append(rel)
            return
        if dry_run:
            report["would_write"].append(rel)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        report["written"].append(rel)

    # roster.json — the name->email allowlist
    roster_map = {p.name: p.email for p in plan_.personas}
    _emit(team_dir / "roster.json", json.dumps(roster_map, indent=2) + "\n")

    # persona cards
    for p in plan_.personas:
        _emit(roster_dir / _card_filename(p), _CARD_TEMPLATE.format(name=p.name, role=p.role, level=p.level, email=p.email))

    # trust matrix seed (all start neutral = 3)
    tm = ["# Trust Matrix", "", "Mechanical 1-5 scores, updated from countable wave signals.", "",
          "| Member | Role | Score | Last updated |", "|--------|------|:-----:|--------------|"]
    for p in plan_.personas:
        tm.append(f"| {p.name} | {p.role} | 3 | (seed) |")
    _emit(team_dir / "trust_matrix.md", "\n".join(tm) + "\n")

    # feedback log seed
    _emit(team_dir / "feedback_log.md", "# Feedback Log\n\nPer-wave retros: going-well, pain points, proposed changes.\n")

    return report
