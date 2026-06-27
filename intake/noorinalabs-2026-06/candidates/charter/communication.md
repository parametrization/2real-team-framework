# Cross-Repo Communication Protocol

## Overview <!-- promotion-target: none -->
This protocol replaces the hub-and-spoke model (everything routes through the orchestrator) with direct manager-to-manager messaging, shared state, and dependency contracts. The goal is to reduce orchestrator bottleneck and enable managers to coordinate directly.

## Shared State: `cross-repo-status.json` <!-- promotion-target: none -->
A live status file in `noorinalabs-main` that all agents read/write. Location: `cross-repo-status.json` in the repository root.

- Agents check this file **before** asking the orchestrator for status
- Agents update it **after** significant events (PR merged, package published, deploy completed)
- Each repo entry includes: current status, deployments branch, wave status, blockers, and last-updated timestamp

See the `cross-repo-status.json` file for the current schema and values.

## Dependency Contracts: `dependencies.yml` <!-- promotion-target: none -->
Each repo declares what it **provides** and what it **needs** in `dependencies.yml` (repository root). This is the single source of truth for cross-repo dependencies.

Each entry includes:
- **provides** — artifacts the repo produces (npm packages, Docker images, services, data)
- **needs** — artifacts the repo consumes, with version constraints, trigger events, and actions

See the `dependencies.yml` file for the current contracts.

## Direct Manager-to-Manager Messaging <!-- promotion-target: none -->
All repo managers are on the same team (`noorinalabs`) and can SendMessage directly:

| Agent Name | Role |
|-----------|------|
| `main-nadia` | Program Director — coordinates priorities |
| `isnad-graph-{manager}` | isnad-graph manager |
| `design-system-{manager}` | design-system manager |
| `landing-page-{manager}` | landing-page manager |
| `deploy-{manager}` | deploy manager |
| `ingestion-{manager}` | ingest-platform manager |

### When to message directly (not through PD)
- "My package is published, you can integrate now"
- "I need your API to add an endpoint before I can proceed"
- "My CI is broken because of your package — can you check?"

The PD (Nadia) coordinates priorities and resolves conflicts but does not relay routine status.

## Topic Channels (Conventions in `cross-repo-status.json`) <!-- promotion-target: none -->
Instead of literal pub/sub, use conventions in the shared state file:

| Channel | Write event | Who reads |
|---------|------------|-----------|
| releases | Package published, version bumped | All consumers of that package |
| blockers | CI broken, dependency missing | Owner of the blocking repo |
| deployments | Service deployed, health verified | Deploy team, dependent services |
| dependencies | New dependency needed, contract changed | All affected repos |

## Event-Driven Spawn Triggers <!-- promotion-target: none -->
These events should trigger automatic agent spawning:

| Trigger | Action |
|---------|--------|
| design-system tags a release | Spawn integration agents in consumer repos |
| All wave PRs merged | Auto-create wave merge PR |
| Wave merge PR merged to main | Update `cross-repo-status.json` |
| CI failure on deployments branch | Notify the PR author agent |
| Manifest changed in B2 | Trigger ingest-platform reload |

## Protocol Rules <!-- promotion-target: none -->
1. **Check shared state first.** Before asking the orchestrator or another manager for status, read `cross-repo-status.json`.
2. **Update shared state promptly.** After any significant event (merge, publish, deploy, blocker), update the relevant entry in `cross-repo-status.json` with a current timestamp.
3. **Direct messages for action items.** Use SendMessage for requests that need a response or action from a specific manager.
4. **Shared state for broadcasts.** Use `cross-repo-status.json` updates for information that multiple teams need to see.
5. **Escalate to PD for conflicts.** If two managers disagree on priority or sequencing, escalate to the Program Director.
6. **Dependency contracts are binding.** If a repo's `dependencies.yml` says it needs an artifact at a certain version, the providing repo must not break that contract without coordinating with all consumers.
