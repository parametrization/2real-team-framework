# wave-kickoff parser fixtures

Covers the EXISTING_SHA capture in Step 1 (branch existence probe via `gh api .../git/refs/heads/<branch>`).

| File | Shape | Expected EXISTING_SHA after validator |
|------|-------|--------------------------------------|
| `existing_sha_404.json` | 404 error body (live-trigger: e906e135) | `""` (empty) |
| `existing_sha_happy.json` | Valid commit ref response | 40-hex SHA |
| `existing_sha_null_jq.json` | Response where `.object.sha` is JSON null (jq yields string "null") | `""` (empty) |
| `existing_sha_tag_ref.json` | Tag ref (annotated tag SHA — valid 40-hex, different object type) | 40-hex SHA |

## Validator invariant

After `EXISTING_SHA=$(gh api ... --jq '.object.sha' 2>/dev/null || true)`:

```bash
[[ "$EXISTING_SHA" =~ ^[0-9a-f]{40}$ ]] || EXISTING_SHA=""
```

- Any non-40-hex value (JSON error body, "null" string, empty) → `EXISTING_SHA=""`
- Valid commit or tag SHA → preserved as-is
