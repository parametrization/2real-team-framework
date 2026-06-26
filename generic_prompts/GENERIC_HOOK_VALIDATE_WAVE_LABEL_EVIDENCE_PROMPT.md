# Generic Hook: Verify Cited File Paths at Origin Before Applying an Iteration Label

## Purpose

A `PreToolUse` hook that, when an issue is being created or edited with an
**iteration label**, verifies that any source-file paths the issue body *cites*
actually **exist at origin** (at the default branch and/or the iteration branch).
If every cited path is a 404 at both refs, the label application is blocked.

It exists because a recurring failure mode is an issue body asserting that some
file/artifact exists when it does not at origin's current commit. Manual review
catches some; the missed cases waste implementer cycles chasing phantom files.
Per the enforcement hierarchy (hook > skill > charter), the discipline is
promoted to a hook.

## Rule

Fires on a `Bash` command that applies an iteration label to an issue:

- `gh issue create … --label '…<iteration-label>…'`
- `gh issue edit <NUM> … --add-label '…<iteration-label>…'`

Algorithm:

1. Tokenize the command via a shared, segment-aware parser. Extract flag VALUES
   so that label-shaped or repo-shaped tokens inside `--body`/`--body-file`
   content cannot leak into extraction.
2. Detect an iteration-label value (your label grammar).
3. Resolve the target repo from `--repo`/`-R`, else recover it from the
   invocation cwd's `origin` remote. If unresolvable, log a skip diagnostic and
   ALLOW (fail-open) — never a silent drop.
4. Resolve the issue body (from `--body`/`--body-file`/stdin for create; via an
   API fetch for edit).
5. If the body has an `Origin-Verification:` override line → ALLOW.
6. Extract cited source-file paths from the body.
7. If none → ALLOW (pure-policy issue, nothing to verify).
8. For each cited path, check existence at origin's default branch and at the
   iteration branch (contents API, 200 = exists, 404 = absent).
9. If EVERY cited path 404s at BOTH refs → BLOCK with an override directive.
   Otherwise ALLOW.

Exit `0` = allow, `2` = block.

### Override

Include `Origin-Verification: <reason>` in the issue body. Typical values:
`Origin-Verification: <path> exists at <ref>` or
`Origin-Verification: not-applicable — <reason>` for a proposed-new-file issue.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""PreToolUse hook: block iteration-labeling of an issue citing non-existent paths."""
import json
import re
import subprocess
import sys

# Adapt: your iteration-label grammar and your cited-path grammar.
_ITERATION_LABEL_RE = re.compile(r"\bwave-\d+\b")
_CITED_PATH_RE = re.compile(r"\b[\w./-]+/(?:src|tests)/[\w./-]+\.py\b")
_OVERRIDE_RE = re.compile(r"^Origin-Verification:\s*\S", re.MULTILINE)

def _find_issue_command(command: str):
    """Return ('create'|'edit', issue_num_or_None, rest_tokens) or None.
    Use a real tokenizer (shlex / shared parser) so a `gh issue create` inside a
    quoted --body value is not mistaken for a real invocation."""
    import shlex
    try:
        toks = shlex.split(command)
    except ValueError:
        return None
    if "gh" not in toks:
        return None
    i = toks.index("gh")
    rest = toks[i + 1:]
    if len(rest) >= 2 and rest[0] == "issue" and rest[1] == "create":
        return "create", None, rest
    if len(rest) >= 3 and rest[0] == "issue" and rest[1] == "edit" and rest[2].isdigit():
        return "edit", rest[2], rest
    return None

def _flag_values(rest, flags):
    out, i = [], 0
    while i < len(rest):
        t = rest[i]
        if t in flags and i + 1 < len(rest):
            out.append(rest[i + 1]); i += 2
        elif "=" in t and t.split("=", 1)[0] in flags:
            out.append(t.split("=", 1)[1]); i += 1
        else:
            i += 1
    return out

def _extract_repo(rest):
    vals = _flag_values(rest, {"--repo", "-R"})
    return vals[0] if vals else None

def _path_exists(repo, path, ref) -> bool:
    try:
        r = subprocess.run(
            ["gh", "api", f"repos/{repo}/contents/{path}", "-f", f"ref={ref}", "--silent"],
            capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False

def check(data: dict) -> dict | None:
    if data.get("tool_name") != "Bash":
        return None
    command = data.get("tool_input", {}).get("command", "")
    found = _find_issue_command(command)
    if not found:
        return None
    kind, num, rest = found

    label_flags = {"--label", "-l"} if kind == "create" else {"--add-label"}
    labels = []
    for raw in _flag_values(rest, label_flags):
        labels.extend(p for p in raw.split(",") if p)
    if not any(_ITERATION_LABEL_RE.search(l) for l in labels):
        return None

    repo = _extract_repo(rest)
    if not repo:
        # Recover from cwd origin; if unresolvable -> log skip + allow.
        return None

    body = None
    if kind == "create":
        bv = _flag_values(rest, {"--body"})
        if bv:
            body = bv[0]
    else:
        try:
            r = subprocess.run(
                ["gh", "issue", "view", num, "--repo", repo, "--json", "body", "--jq", ".body"],
                capture_output=True, text=True, timeout=10)
            body = r.stdout if r.returncode == 0 else None
        except (subprocess.TimeoutExpired, OSError):
            body = None
    if not body or _OVERRIDE_RE.search(body):
        return None

    cited = list(set(_CITED_PATH_RE.findall(body)))
    if not cited:
        return None

    wave_branch = None  # derive `deployments/.../wave-N` from status if you can
    unverified = [
        p for p in cited
        if not (_path_exists(repo, p, "main") or (wave_branch and _path_exists(repo, p, wave_branch)))
    ]
    if unverified == cited:
        return {"decision": "block",
                "reason": "BLOCKED: every cited path 404s at origin.\n"
                          + "\n".join(f"  - {p}" for p in unverified)
                          + "\nVerify a real path, or add `Origin-Verification: <reason>` to the body."}
    return None

if __name__ == "__main__":
    d = json.load(sys.stdin)
    result = check(d)
    if result is None:
        sys.exit(0)
    print(json.dumps(result))
    sys.exit(2 if result.get("decision") == "block" else 0)
```

## Adaptation Notes

- **Cited-path grammar** is the tuning knob: broad enough to catch the real
  reproducer shapes, narrow enough not to match arbitrary `foo.py` prose
  mentions. Anchor on known source subdirs.
- **Flag-value extraction must be scoped** so label/repo/path-shaped tokens
  inside `--body`/`--body-file` payloads do not leak into extraction. Use the
  shared parser invariant, not ad-hoc regex over the raw string.
- **Two refs**: check both the default branch and the iteration branch, because a
  freshly-created file may exist only on the iteration branch. Derive the
  iteration branch from your status file when the label form doesn't carry it.
- **Fail-open on unresolvable repo / unreadable body** with a logged diagnostic.
  Block ONLY the affirmative "all cited paths are phantom" case.
- The `Origin-Verification:` override is a substring match — keep it simple and
  document the canonical values.
```
