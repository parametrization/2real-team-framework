#!/usr/bin/env python3
# ruff: noqa: E501
"""P3W4 kickoff: label + kickoff comment for 31 issues across 6 repos.

Frozen historical script: long lines inside the kickoff-comment f-string
body preserve the exact text that was posted on GH issues at the time
(comment-headers, charter section names) — reflowing would distort the
audit-trail record. Per-file E501 exemption is the right granularity.
"""

import json
import subprocess

# (repo_short, issue_num, assignee_label, branch_slug, reviewers, tier, bundled_with, wave_bootstrap)
ISSUES = [
    # T1 — bundle PR (1 PR closing 3 issues): A.Virtanen/0244-pr-review-canonicalization
    (
        "noorinalabs-main",
        244,
        "AINO_VIRTANEN",
        "A.Virtanen/0244-pr-review-canonicalization",
        ("Wanjiku.Mwangi", "Nadia.Khoury"),
        1,
        "#233 #228",
        False,
    ),
    (
        "noorinalabs-main",
        233,
        "AINO_VIRTANEN",
        "A.Virtanen/0244-pr-review-canonicalization",
        ("Wanjiku.Mwangi", "Nadia.Khoury"),
        1,
        "#244 #228",
        False,
    ),
    (
        "noorinalabs-main",
        228,
        "AINO_VIRTANEN",
        "A.Virtanen/0244-pr-review-canonicalization",
        ("Wanjiku.Mwangi", "Nadia.Khoury"),
        1,
        "#244 #233",
        False,
    ),
    # T2 — main: bundle PR closing 7 issues: A.Virtanen/0226-hook-matcher-sanitization
    (
        "noorinalabs-main",
        226,
        "AINO_VIRTANEN",
        "A.Virtanen/0226-hook-matcher-sanitization",
        ("Nadia.Khoury", "Wanjiku.Mwangi"),
        2,
        "#227 #223 #216 #188 #144 #189",
        False,
    ),
    (
        "noorinalabs-main",
        227,
        "AINO_VIRTANEN",
        "A.Virtanen/0226-hook-matcher-sanitization",
        ("Nadia.Khoury", "Wanjiku.Mwangi"),
        2,
        "#226 #223 #216 #188 #144 #189",
        False,
    ),
    (
        "noorinalabs-main",
        223,
        "AINO_VIRTANEN",
        "A.Virtanen/0226-hook-matcher-sanitization",
        ("Nadia.Khoury", "Wanjiku.Mwangi"),
        2,
        "#226 #227 #216 #188 #144 #189",
        False,
    ),
    (
        "noorinalabs-main",
        216,
        "AINO_VIRTANEN",
        "A.Virtanen/0226-hook-matcher-sanitization",
        ("Nadia.Khoury", "Wanjiku.Mwangi"),
        2,
        "#226 #227 #223 #188 #144 #189",
        False,
    ),
    (
        "noorinalabs-main",
        188,
        "AINO_VIRTANEN",
        "A.Virtanen/0226-hook-matcher-sanitization",
        ("Nadia.Khoury", "Wanjiku.Mwangi"),
        2,
        "#226 #227 #223 #216 #144 #189",
        False,
    ),
    (
        "noorinalabs-main",
        144,
        "AINO_VIRTANEN",
        "A.Virtanen/0226-hook-matcher-sanitization",
        ("Nadia.Khoury", "Wanjiku.Mwangi"),
        2,
        "#226 #227 #223 #216 #188 #189",
        False,
    ),
    (
        "noorinalabs-main",
        189,
        "AINO_VIRTANEN",
        "A.Virtanen/0226-hook-matcher-sanitization",
        ("Nadia.Khoury", "Wanjiku.Mwangi"),
        2,
        "#226 #227 #223 #216 #188 #144",
        False,
    ),
    # T2 — isnad-graph: 1 PR closing 2 issues: L.Pham/0819-hook-cross-repo-roster
    (
        "noorinalabs-isnad-graph",
        819,
        "LINH_PHAM",
        "L.Pham/0819-hook-cross-repo-roster",
        ("Jelani.Mwangi", "Arjun.Raghavan"),
        2,
        "#814",
        False,
    ),
    (
        "noorinalabs-isnad-graph",
        814,
        "LINH_PHAM",
        "L.Pham/0819-hook-cross-repo-roster",
        ("Jelani.Mwangi", "Arjun.Raghavan"),
        2,
        "#819",
        False,
    ),
    # T3 — 3 PRs in main
    (
        "noorinalabs-main",
        238,
        "WANJIKU_MWANGI",
        "W.Mwangi/0238-wave-kickoff-multi-repo",
        ("Aino.Virtanen", "Nadia.Khoury"),
        3,
        "(standalone)",
        False,
    ),
    (
        "noorinalabs-main",
        158,
        "AINO_VIRTANEN",
        "A.Virtanen/0158-promotion-audit-fallback",
        ("Wanjiku.Mwangi", "Santiago.Ferreira"),
        3,
        "(standalone)",
        False,
    ),
    (
        "noorinalabs-main",
        196,
        "WANJIKU_MWANGI",
        "W.Mwangi/0196-wave-scope-skill",
        ("Nadia.Khoury", "Aino.Virtanen"),
        3,
        "(standalone)",
        False,
    ),
    # T4 — main bundle PR: A.Virtanen/0225-charter-docs-sweep (closes 6)
    (
        "noorinalabs-main",
        225,
        "AINO_VIRTANEN",
        "A.Virtanen/0225-charter-docs-sweep",
        ("Wanjiku.Mwangi", "Nadia.Khoury"),
        4,
        "#239 #240 #200 #201 #197",
        False,
    ),
    (
        "noorinalabs-main",
        239,
        "AINO_VIRTANEN",
        "A.Virtanen/0225-charter-docs-sweep",
        ("Wanjiku.Mwangi", "Nadia.Khoury"),
        4,
        "#225 #240 #200 #201 #197",
        False,
    ),
    (
        "noorinalabs-main",
        240,
        "AINO_VIRTANEN",
        "A.Virtanen/0225-charter-docs-sweep",
        ("Wanjiku.Mwangi", "Nadia.Khoury"),
        4,
        "#225 #239 #200 #201 #197",
        False,
    ),
    (
        "noorinalabs-main",
        200,
        "AINO_VIRTANEN",
        "A.Virtanen/0225-charter-docs-sweep",
        ("Wanjiku.Mwangi", "Nadia.Khoury"),
        4,
        "#225 #239 #240 #201 #197",
        False,
    ),
    (
        "noorinalabs-main",
        201,
        "AINO_VIRTANEN",
        "A.Virtanen/0225-charter-docs-sweep",
        ("Wanjiku.Mwangi", "Nadia.Khoury"),
        4,
        "#225 #239 #240 #200 #197",
        False,
    ),
    (
        "noorinalabs-main",
        197,
        "AINO_VIRTANEN",
        "A.Virtanen/0225-charter-docs-sweep",
        ("Wanjiku.Mwangi", "Nadia.Khoury"),
        4,
        "#225 #239 #240 #200 #201",
        False,
    ),
    # T4 — child doc-sync (single-reviewer wave-bootstrap-class)
    (
        "noorinalabs-isnad-graph",
        852,
        "INGRID_LINDQVIST",
        "I.Lindqvist/0852-claude-md-branching-sync",
        ("Anya.Kowalczyk",),
        4,
        "(child sync)",
        True,
    ),
    (
        "noorinalabs-user-service",
        90,
        "MATEO_SALAZAR",
        "M.Salazar/0090-claude-md-branching-sync",
        ("Anya.Kowalczyk",),
        4,
        "(child sync)",
        True,
    ),
    (
        "noorinalabs-design-system",
        62,
        "KOFI_MENSAH",
        "K.Mensah/0062-claude-md-branching-sync",
        ("Maeve.Callahan",),
        4,
        "(child sync)",
        True,
    ),
    (
        "noorinalabs-data-acquisition",
        33,
        "SOFIA_CARDOSO",
        "S.Cardoso/0033-claude-md-branching-sync",
        ("Dilara.Erdogan",),
        4,
        "(child sync)",
        True,
    ),
    # T5 — firm scope per owner directive
    (
        "noorinalabs-main",
        214,
        "AINO_VIRTANEN",
        "A.Virtanen/0214-parent-canonical-hook-paths",
        ("Wanjiku.Mwangi", "Nadia.Khoury"),
        5,
        "(standalone)",
        False,
    ),
    (
        "noorinalabs-main",
        215,
        "AINO_VIRTANEN",
        "A.Virtanen/0215-settings-json-fanout",
        ("Wanjiku.Mwangi", "Santiago.Ferreira"),
        5,
        "(standalone)",
        False,
    ),
    (
        "noorinalabs-main",
        236,
        "NADIA_KHOURY",
        "N.Khoury/0236-pattern-c-promotion",
        ("Aino.Virtanen", "Santiago.Ferreira"),
        5,
        "(standalone)",
        False,
    ),
    (
        "noorinalabs-main",
        198,
        "AINO_VIRTANEN",
        "A.Virtanen/0198-validate-edit-completion",
        ("Wanjiku.Mwangi", "Nadia.Khoury"),
        5,
        "(standalone)",
        False,
    ),
    (
        "noorinalabs-main",
        203,
        "AINO_VIRTANEN",
        "A.Virtanen/0203-validate-workflow-paths-coverage",
        ("Wanjiku.Mwangi", "Nadia.Khoury"),
        5,
        "(standalone)",
        False,
    ),
    (
        "noorinalabs-main",
        219,
        "AINO_VIRTANEN",
        "A.Virtanen/0219-hook14-neutral-bypass",
        ("Wanjiku.Mwangi", "Santiago.Ferreira"),
        5,
        "(standalone)",
        False,
    ),
]

assert len(ISSUES) == 31, f"Expected 31 issues, got {len(ISSUES)}"


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


results: dict[str, list] = {
    "labeled": [],
    "label_failed": [],
    "commented": [],
    "comment_failed": [],
}

for repo, num, assignee, branch, revs, tier, bundled, wave_bs in ISSUES:
    # Step 1: label
    label_cmd = [
        "gh",
        "issue",
        "edit",
        str(num),
        "--repo",
        f"noorinalabs/{repo}",
        "--add-label",
        "p3-wave-4",
        "--add-label",
        assignee,
    ]
    if wave_bs:
        label_cmd += ["--add-label", "wave-bootstrap"]
    r = run(label_cmd)
    if r.returncode == 0:
        results["labeled"].append(f"{repo}#{num}")
    else:
        results["label_failed"].append(f"{repo}#{num}: {r.stderr.strip()[:120]}")

    # Step 2: kickoff comment
    rev_str = ", ".join(revs) + (
        " (single-reviewer per wave-bootstrap exception)" if wave_bs else ""
    )
    body = f"""Requestor: Nadia.Khoury
Requestee: {assignee.replace("_", ".").title().replace("Mwangi", "Mwangi").replace("Khoury", "Khoury")}
RequestOrReplied: Request

**Wave 4 Kickoff — Phase 3**

This issue is assigned to you for p3-wave-4.

- **Tier:** {tier}
- **Bundled with:** {bundled}
- **Branch from:** `deployments/phase-3/wave-4`
- **Suggested branch name:** `{branch}`
- **Reviewers:** {rev_str}
- **Priority:** tech-debt

**Wave theme:** Tooling and process-discipline cleanup — hook bug-class consolidation + charter docs sweep.

Please begin implementation per the charter (`pull-requests.md`, `commits.md`, `branching.md`). Note the **new charter sections** that landed today (commit `8deb979`):
- § Comment-Based Reviews — canonical Requestor=comment-author / Requestee=comment-target
- § Additive Commits on ChangesRequested — no force-push during a CR cycle
- § Pre-Flight Checklist — applied at this kickoff (see meta-issue)

— Nadia Khoury, Program Director"""

    comment_cmd = [
        "gh",
        "issue",
        "comment",
        str(num),
        "--repo",
        f"noorinalabs/{repo}",
        "--body",
        body,
    ]
    r = run(comment_cmd)
    if r.returncode == 0:
        results["commented"].append(f"{repo}#{num}")
    else:
        results["comment_failed"].append(f"{repo}#{num}: {r.stderr.strip()[:200]}")

print(json.dumps({k: len(v) for k, v in results.items()}, indent=2))
print()
if results["label_failed"]:
    print("LABEL FAILURES:")
    for x in results["label_failed"]:
        print(" ", x)
if results["comment_failed"]:
    print("COMMENT FAILURES:")
    for x in results["comment_failed"]:
        print(" ", x)
