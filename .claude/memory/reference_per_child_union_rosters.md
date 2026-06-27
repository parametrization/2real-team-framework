---
name: reference_per_child_union_rosters
description: roster_gen.py per-child union rosters + how the identity gate enforces meta∪child so a child PR is signable by that child's engineers + org leads only.
metadata:
  type: reference
---

`framework/install/roster_gen.py` introspects the target repo and writes a fitting team
roster. The non-obvious part is the **per-child union roster** model for meta+children repos.

**Role/domain model:**
- `_ORG_ROLES = {Program Director, Technical Program Manager, QA Engineer, Standards & Quality Lead}`;
  `_LEAD_ROLE = "Tech Lead"`.
- `_ROLE_DOMAINS`: Frontend→{frontend}, Data→{data,database}, DevOps→{infra,docker,kubernetes,ci},
  Security→{security}, Software Engineer→{python,node,typescript,go,rust,java,backend}.
- `Persona` has `domains: set[str]` + `is_org`/`is_lead`; `assign_personas` sets domains via `_role_domains(role)`.

**Partition** — `partition_for_children(personas, intro)` → `(meta_personas, {child: [personas]})`:
- children = `intro.repos[1:]`.
- meta = leads + org roles + unassigned engineers.
- each child = leads + engineers whose `domains & child.stacks` intersect.

**Write dispatch** (`write_roster`):
- single-repo → `_write_team(...all...)`.
- meta+children → meta gets the org allowlist + ALL cards + org artifacts; each child gets its
  own `<child>/.claude/team/roster.json` + only its cards, **no org artifacts**.

**Why union works:** `validate_commit_identity` does a parent∪child roster merge (child wins,
walk up ONE level). So a child PR is signable by that child's engineers **plus** the org leads
in the meta roster — but NOT by another child's engineers. The gate is enabled by setting
`identity.enforce=true` and placing `validate_commit_identity` first in `hooks.pre_bash`.

Trust is scored mechanically from wave signals (`lib/trust_signals.py`); the merged-PR
extraction is config-driven and reads the lifecycle/state file ([[reference_lifecycle_state_machine]]).
