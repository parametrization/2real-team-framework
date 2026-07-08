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
- **Verdict-comment attribution (Requestor/Requestee) — DON'T SWAP.** `Requestor:` = the
  **reviewer** (comment author); `Requestee:` = the **PR author** being addressed. `trust_signals.py`
  keys reviewer identity off `Requestor:` (charter `issues.md` §Verdict-Comment Grammar), so a swap
  mis-attributes the review to the author and corrupts retro scoring. When spawning reviewer agents,
  instruct them `Requestor: <Reviewer>.<Name>` / `Requestee: <PRAuthor>.<Name>` /
  `RequestOrReplied: Request` (`Replied` only for a clean/approval turn). Caught Phase-6-W1 on
  #159/#160 where I handed reviewers swapped fields; fixed in place via
  `gh api repos/.../issues/comments/<id> -X PATCH -f body=...` (edit only the two header lines).
- **An AUTHOR reply to a must-fix is a PLAIN comment — never `Requestor:`/`RequestOrReplied:` grammar.**
  That grammar is reviewer-only. A W21 (#287) author reply wearing verdict headers made
  `trust_signals`/`review_load` count the PR author as a third reviewer of their own PR → spurious
  `missed_catches`/`verified_reviews`. The merge gate is author-exclusive and wasn't fooled, but the
  scorer is not (yet) — see #288. Strip the headers if it recurs, then re-`extract` to confirm.
- **`gh api -X PATCH` bodies from a file: use `-F body=@file`, NEVER `-f body=@file`.** `-f`/`--raw-field`
  sends the LITERAL string (`@path` lands verbatim as the comment body — a silent corruption caught only
  by re-reading); only `-F`/`--field` expands `@file`. Hit twice in W21 (Tariq + Ibrahim). Inline strings
  (`-f body="..."`) are fine; the `@file` expansion is the trap. Also valid: `--field body=@file`.

State + queue: [[project_framework_extraction_state]].
