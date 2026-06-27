# Commit Identity

Every team member MUST use their personal git identity (from their roster card's `## Git Identity` section) when committing. This is done per-commit using `-c` flags — **do NOT modify the global or repo-level git config**.

Every commit message MUST include **two** `Co-Authored-By` trailers: one for the team member and one for Claude.

```bash
git -c user.name="Firstname Lastname" -c user.email="parametrization+Firstname.Lastname@gmail.com" commit -m "$(cat <<'EOF'
Commit message here.

Co-Authored-By: Firstname Lastname <parametrization+Firstname.Lastname@gmail.com>
Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

## Identity Table <!-- promotion-target: none -->
| Team Member | user.name | user.email |
|---|---|---|
| Nadia Khoury | `Nadia Khoury` | `parametrization+Nadia.Khoury@gmail.com` |
| Wanjiku Mwangi | `Wanjiku Mwangi` | `parametrization+Wanjiku.Mwangi@gmail.com` |
| Santiago Ferreira | `Santiago Ferreira` | `parametrization+Santiago.Ferreira@gmail.com` |
| Aino Virtanen | `Aino Virtanen` | `parametrization+Aino.Virtanen@gmail.com` |

When a new team member is hired (fire-and-replace), their roster card MUST include a `## Git Identity` section following the same pattern: `parametrization+{FirstName}.{LastName}@gmail.com` (diacritics removed from email, preserved in user.name).
