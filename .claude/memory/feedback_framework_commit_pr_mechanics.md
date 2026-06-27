---
name: feedback_framework_commit_pr_mechanics
description: Commit/PR mechanics for this repo — owner commit identity, -F file for messages, gh pr --title fails on projects-classic (use gh api PATCH), push without piping.
metadata:
  type: feedback
---

Working conventions established while building PR #41 in this repo.

**Why:** these mechanics avoid identity-hook trips, silent no-ops, and masked failures that
otherwise cost a round-trip each.

**How to apply:**
- **Owner commits** as `git -c user.name="Steven French" -c user.email="parametrization@gmail.com"`
  — never set global/repo git config. (Team-member commits use their roster identity per the
  repo's charter.)
- **Commit messages via `-F <file>`**, not inline `-m "$(cat <<EOF…)"` — the heredoc form trips
  the identity-hook parser.
- **PR title edits:** `gh pr edit --title` fails on this repo (projects-classic). Use
  `gh api -X PATCH repos/parametrization/2real-team-framework/pulls/N -f title=...` instead.
- **Pushing:** don't pipe `git push` through `tail`/`head` — a piped push returns the pipe's 0
  and hides a REJECTED push. Run it bare and check `; echo rc=$?`.
- **CI for this repo** runs `ruff check` (NOT `ruff format --check`) on `framework/`, so avoid
  gratuitous format churn; the `python/` package is line-length=100. There's a `framework` CI
  job (matrix py3.10–3.13) running `ruff check framework/` + `pytest framework/tests/` with
  `ENVIRONMENT: test`.
- **.pyc hygiene:** `__pycache__/*.pyc` was committed once then removed; `.gitignore` now covers
  it — don't re-add. A `git checkout` restore can resurrect them, so make pyc removal a
  deliberate separate commit if it recurs.

State + queue: [[project_framework_extraction_state]].
