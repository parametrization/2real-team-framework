# Generic Hook: Warn If Container Image May Not Exist Before Deploy

## Purpose

A warning-only `PreToolUse` hook that fires when a command triggers a
**deploy-related CI workflow** and the container image that deploy expects might
not have been published yet. It does not block — it surfaces a heads-up so a
deploy doesn't fail late because the image was never built.

It exists because triggering a deploy before the image is published is a common,
silently-late failure; a cheap pre-check warns the operator to run the build
workflow first.

## Rule

Fires on a `Bash` command that runs a CI workflow (e.g. `gh workflow run`):

1. Confirm the command is a real workflow-run invocation in command position
   (a mention inside a quoted arg or heredoc is not a real invocation).
2. Confirm the workflow looks **deploy-related** (name/file matches
   `deploy|release|cd[.-]|deliver`).
3. Resolve the target repo from `-R`/`--repo` value, else from the cwd's ambient
   git context. If unresolvable, emit a generic "verify the image exists" warning
   (fail-open, never a silent drop).
4. Map the repo to its expected image reference. If the image registry reports
   the image/tag does not exist, emit a warning naming the image and the build
   step to run first.

Exit code is **always `0`** — this hook only ever warns.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""PreToolUse hook: warn when a deploy workflow may run against a missing image."""
import json
import re
import subprocess
import sys

_DEPLOY_RE = re.compile(r"deploy|release|cd[.-]|deliver", re.IGNORECASE)

# Adapt: map your repo short-names to their published image references.
_REPO_IMAGE = {
    # "my-service": "registry.example.com/org/my-service",
}

def _is_workflow_run(command: str) -> bool:
    """Command-position check. Prefer a real tokenizer over substring match."""
    import shlex
    try:
        toks = shlex.split(command)
    except ValueError:
        return False
    return "gh" in toks and "workflow" in toks and "run" in toks

def _target_repo(command: str) -> str | None:
    m = re.search(r"(?:-R|--repo)[=\s]+(\S+)", command)
    if m:
        repo = m.group(1)
        return repo.split("/")[-1] if "/" in repo else repo
    return None  # else resolve from cwd ambient git context

def _image_exists(image: str, tag: str = "latest") -> bool:
    parts = image.split("/")
    if len(parts) < 2:
        return True
    org, package = parts[-2], parts[-1]
    try:
        r = subprocess.run(
            ["gh", "api", f"orgs/{org}/packages/container/{package}/versions",
             "--jq", ".[0].metadata.container.tags[]"],
            capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            return True  # transient API error — don't warn
        tags = r.stdout.strip().splitlines()
        return tag in tags or len(tags) > 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return True

def check(data: dict) -> dict | None:
    if data.get("tool_name") != "Bash":
        return None
    command = data.get("tool_input", {}).get("command", "")
    if not _is_workflow_run(command) or not _DEPLOY_RE.search(command):
        return None

    repo = _target_repo(command)
    if not repo:
        return {"decision": "allow",
                "systemMessage": "WARNING: triggering a deploy workflow — verify the "
                                 "image exists; run the build workflow first if needed."}
    image = _REPO_IMAGE.get(repo)
    if not image:
        return None
    if not _image_exists(image):
        return {"decision": "allow",
                "systemMessage": f"WARNING: {image}:latest may not exist; deploy may fail. "
                                 "Run the service's build workflow first."}
    return None

def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    result = check(data)
    if result:
        print(json.dumps(result))
    sys.exit(0)

if __name__ == "__main__":
    main()
```

## Adaptation Notes

- **Registry API** (the container-image existence check) is registry-specific.
  Swap the query for your registry's "list tags / versions" endpoint.
- **Repo→image map** is the project knob — populate it with your services and
  their image references.
- **Command-position detection** matters: route the shape check through a real
  tokenizer and the repo-flag value through a scoped flag parser, so a workflow
  name mentioned inside a quoted `--field` value doesn't false-trigger.
- **Always exit 0.** Warnings here are advisory; a transient registry error
  returns "assume exists" so the hook never nags on flaky infra.
```
