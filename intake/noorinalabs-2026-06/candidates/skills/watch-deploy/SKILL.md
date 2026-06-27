---
name: watch-deploy
description: Monitor (and, within bounds, remediate) a deploy triggered by a merge — staging automatically post-merge, production only after the owner approves the queued deploy. Polls the deploy run to a terminal state, classifies failures, attempts bounded fix-forward, and escalates with a precise diagnosis.
args: env (stg|prod), optional triggering sha, optional run-id
---

Watch a deploy that a merge to `main` triggered, confirm it reaches a healthy terminal state, and fix-forward or escalate when it does not. This is the active counterpart to `/wave-wrapup` Step 11.6's passive "latest run is green" check: it follows the *specific* deploy a merge kicked off, rather than inspecting only the most-recent run.

Motivation: deploy#418 — a user-service merge silently broke the staging deploy at the image-pull step and only self-healed because an isnad-graph push happened to follow. Nothing watched the dispatched run or remediated. See also main#623 (this skill's tracking issue) and the P3W14-retro session-start "red default-branch publish" check, which is passive and does not follow a fresh deploy.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149).

## When to use

- **Automatically after a merge that triggers a staging deploy** — any merge to `main` in a fan-in repo (`noorinalabs-isnad-graph`, `noorinalabs-user-service`) fires a `repository_dispatch` to `noorinalabs-deploy/.github/workflows/deploy-stg.yml`. Call `/watch-deploy stg <sha>` to follow it.
- **From `/wave-wrapup` Step 11.6** — once per wave→main merge in a deploy-triggering repo, so a wave is not declared green until *its* triggered deploys are confirmed healthy (not just the latest run on the board).
- **For production — only after the owner has approved the queued prod deploy.** Prod deploys wait on a manual approval gate (owner directive 2026-06-09). This skill MUST NOT approve, trigger, or otherwise advance a prod deploy. Once the owner approves, call `/watch-deploy prod <sha>` to monitor the approved run.

## Environment contract

| env | Workflow (in `noorinalabs-deploy`) | Trigger | This skill may act before owner? |
|-----|------------------------------------|---------|----------------------------------|
| `stg` | `deploy-stg.yml` | auto — `repository_dispatch` from a service repo's `ghcr-publish.yml` after both images publish | **Yes** — staging is auto-deploy; bounded remediation is allowed |
| `prod` | `deploy-prod.yml` | `workflow_dispatch` from `promote.yml`, **gated on owner approval** | **No** — never approve/trigger; monitor only after approval, never auto-remediate prod |

## Instructions

### 1. Resolve the run to watch

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
DEPLOY_REPO="noorinalabs/noorinalabs-deploy"
ENV="{stg|prod}"                     # first arg
SHA="{triggering sha or empty}"      # optional second arg
RUN_ID="{run-id or empty}"           # optional third arg

case "$ENV" in
  stg)  WORKFLOW="deploy-stg.yml";  RUN_NAME="Deploy to staging" ;;
  prod) WORKFLOW="deploy-prod.yml"; RUN_NAME="Deploy to production" ;;
  *) echo "ERROR: env must be stg or prod"; exit 1 ;;
esac
```

Find the run. Note two facts that make naive matching wrong:

- A `$WORKFLOW` run's `headSha` is the **deploy repo's** sha, and its `displayTitle` is the **event-type** (`deploy-noorinalabs-<service>`) — neither is the triggering **service** sha. So you cannot filter `gh run list` by the service sha.
- The service sha lives in the dispatch `client_payload`, which is not exposed by `gh run list`.

Correlate by **time** instead (deploys are serialized — `deploy-stg.yml` uses `concurrency: deploy-staging, cancel-in-progress: false`): the run a merge triggered is the **earliest `$WORKFLOW` run whose `createdAt` is at/after the merge commit's timestamp**.

```bash
if [ -n "$RUN_ID" ]; then
  RUN=$(gh run view "$RUN_ID" --repo "$DEPLOY_REPO" --json databaseId,status,conclusion,url,headSha,createdAt)
elif [ -n "$SHA" ]; then
  # Resolve the service commit's timestamp. We don't know which fan-in repo the
  # sha belongs to, so probe them (the sha is unique across repos in practice).
  MERGE_TS=""
  for r in noorinalabs-isnad-graph noorinalabs-user-service; do
    ts=$(gh api "repos/noorinalabs/$r/commits/$SHA" --jq '.commit.committer.date' 2>/dev/null || true)
    [ -n "$ts" ] && { MERGE_TS="$ts"; SRC_REPO="$r"; break; }
  done
  if [ -z "$MERGE_TS" ]; then
    echo "Could not resolve $SHA in any fan-in repo — falling back to latest $WORKFLOW run."
    RUN=$(gh run list --repo "$DEPLOY_REPO" --workflow "$WORKFLOW" --limit 1 \
      --json databaseId,status,conclusion,url,headSha,createdAt --jq '.[0] // empty')
  else
    echo "Merge $SHA in $SRC_REPO at $MERGE_TS — selecting earliest $WORKFLOW run at/after that."
    RUN=$(gh run list --repo "$DEPLOY_REPO" --workflow "$WORKFLOW" --limit 30 \
      --json databaseId,status,conclusion,url,headSha,createdAt \
      --jq "[.[] | select(.createdAt >= \"$MERGE_TS\")] | sort_by(.createdAt) | .[0] // empty")
  fi
else
  # No sha — watch the latest run, and say so (not a specific merge's deploy).
  echo "No sha given — watching the latest $WORKFLOW run."
  RUN=$(gh run list --repo "$DEPLOY_REPO" --workflow "$WORKFLOW" --limit 1 \
    --json databaseId,status,conclusion,url,headSha,createdAt --jq '.[0] // empty')
fi
[ -z "$RUN" ] && { echo "No $WORKFLOW run found to watch (env=$ENV, sha=${SHA:-none})."; exit 0; }
RUN_DB=$(echo "$RUN" | jq -r '.databaseId'); RUN_URL=$(echo "$RUN" | jq -r '.url')
echo "Watching: $RUN_URL"
```

For **prod**, the `$WORKFLOW` is dispatched by `promote.yml` (a `workflow_dispatch`, not a service-repo push), so the sha-correlation above does not apply — pass the `RUN_ID` of the approved prod run, or omit the sha to watch the latest prod run.

### 2. Production approval guard (prod only — HARD STOP)

For `prod`, before watching, confirm the run is **past** the owner-approval gate. If the run is `waiting`/`action_required` (pending approval), **STOP and report** — do not poll, do not nudge, do not approve. Surface the approval URL and wait for the owner.

```bash
if [ "$ENV" = "prod" ]; then
  ST=$(echo "$RUN" | jq -r '.status')
  if [ "$ST" = "waiting" ] || [ "$ST" = "action_required" ]; then
    echo "PROD DEPLOY AWAITING OWNER APPROVAL — $RUN_URL"
    echo "This skill will NOT approve or advance it. Re-invoke /watch-deploy prod once you have approved."
    exit 0
  fi
fi
```

### 3. Poll to a terminal state

Poll the run until `status == completed` (bounded wait; deploys are minutes, not hours). Prefer `gh run watch` where available; otherwise poll.

```bash
gh run watch "$RUN_DB" --repo "$DEPLOY_REPO" --exit-status >/dev/null 2>&1 || true
RUN=$(gh run view "$RUN_DB" --repo "$DEPLOY_REPO" --json status,conclusion,url,databaseId)
CONCLUSION=$(echo "$RUN" | jq -r '.conclusion')
echo "Terminal conclusion: $CONCLUSION — $RUN_URL"
```

If `CONCLUSION == success`: for stg, confirm the post-deploy verifier is also green (the `Verify Deployment` / health-check run). Report success and stop.

### 4. Classify the failure

If `CONCLUSION != success`, pull the failed step log and classify:

```bash
LOG=$(gh run view "$RUN_DB" --repo "$DEPLOY_REPO" --log-failed 2>/dev/null || true)
```

| Class | Signal in failed log | Meaning |
|-------|----------------------|---------|
| **image-not-found** | `failed to resolve reference`, `: not found`, `manifest unknown`, or a `MISS ` line from the deploy-stg pre-flight | A resolved image tag is absent in GHCR (deploy#418 class) |
| **health-check** | `health check failed`, `kafka` healthcheck flap | Container came up but a healthcheck did not pass (often the pipeline-only kafka flap — deploy#393 class, non-blocking) |
| **migrate-gate** | `alembic`, `upgrade head`, advisory-lock contention | Pre-deploy DB migration failed |
| **infra/ssh** | `ssh`, `connection refused`, `Permission denied`, runner/network error | Transient or host-level infra problem |
| **other** | none of the above | Unknown — escalate with the raw failing step |

### 5. Remediate (bounded) or escalate

**Staging** — bounded fix-forward is allowed:

| Class | Action |
|-------|--------|
| **image-not-found** | Re-dispatch the last-good stg images: `gh workflow run deploy-stg.yml --repo "$DEPLOY_REPO"` (defaults to `stg-latest` for every service). Then re-watch ONCE. If the original was a per-sha deploy whose image never published, also surface the upstream publish run so the real gap is filed. (Post-deploy#418 this class should be caught by the pre-flight with a readable `MISS`; if it still reaches a deploy, that is itself worth a follow-up.) |
| **health-check** | If it is the known kafka pipeline-only flap (deploy#393 class), note it as non-blocking and do **not** count it as a wave-blocking failure; confirm the app containers (api, user-service) are healthy. Otherwise re-watch ONCE; if still red, escalate. |
| **migrate-gate** | Do **not** auto-retry migrations. Escalate with the alembic error and the failing revision. |
| **infra/ssh** | Re-watch / re-dispatch ONCE (likely transient). If it recurs, escalate. |
| **other** | Escalate with the raw failing step. |

After **one** remediation attempt, re-resolve and re-poll (Steps 1–3) exactly once. Do **not** loop indefinitely — a second failure escalates.

**Production** — NO auto-remediation. On any prod failure: report the class + failing step, and recommend the owner-gated path (`rollback.yml` to the prior `prod-<short>`, or fix-forward + re-promote via `promote.yml`). Never trigger a prod redeploy or rollback yourself.

### 6. Report

```
**watch-deploy: {env} — {merge sha or "latest"}**

- Run: {url}
- Terminal: {success | <class> failure}
- Verifier (stg): {green | red | n/a}
- Remediation: {none | re-dispatched stg-latest, re-watched → green | escalated}
- Escalation: {none | <what the owner/operator must do>}
```

If a real defect surfaced (a publish gap, a recurring health failure, an infra problem), file it per `/file-bug` and link it. Do not silently swallow a failure that self-healed on retry — record it so the underlying flake is tracked.

## What this skill does NOT do

- It never approves, triggers, or advances a **production** deploy — that gate is the owner's. It only monitors after approval.
- It does not loop more than one remediation attempt — a second failure is an escalation, not another retry.
- It does not edit code or workflows — fixes to the deploy mechanics themselves are filed as issues (e.g. deploy#418) and go through the normal PR path.
- It does not roll back production — it recommends `rollback.yml`; the owner runs it.
