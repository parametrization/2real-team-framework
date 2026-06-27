import subprocess

ISSUES = [
    (
        "noorinalabs-main",
        [
            244,
            233,
            228,
            226,
            227,
            223,
            216,
            188,
            144,
            189,
            238,
            158,
            196,
            225,
            239,
            240,
            200,
            201,
            197,
            214,
            215,
            236,
            198,
            203,
            219,
        ],
    ),
    ("noorinalabs-isnad-graph", [819, 814, 852]),
    ("noorinalabs-user-service", [90]),
    ("noorinalabs-design-system", [62]),
    ("noorinalabs-data-acquisition", [33]),
]
total = 0
fail = []
for repo, nums in ISSUES:
    for n in nums:
        url = f"https://github.com/noorinalabs/{repo}/issues/{n}"
        r = subprocess.run(
            ["gh", "project", "item-add", "2", "--owner", "noorinalabs", "--url", url],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            total += 1
        else:
            err = r.stderr.strip()[:120]
            if "already exists" in err.lower() or "already added" in err.lower():
                total += 1
            else:
                fail.append(f"{repo}#{n}: {err}")
print(f"Added (or already on board): {total}")
if fail:
    print("FAILURES:")
    for f in fail:
        print(" ", f)
