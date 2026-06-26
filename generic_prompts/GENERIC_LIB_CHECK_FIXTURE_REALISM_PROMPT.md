# Generic Lib Prompt: Production-Realism Fixture Lint

## Purpose

Flag test fixtures that are **greener than real production data** — toy inputs
that lack the characteristics of a real upstream sample and therefore exercise a
code path the production input never takes. The recurring failure mode: a
simplified fixture passes a parser/extractor/transform, the same code silently
mis-handles the real (messier) input in production, and the bug ships. A fixture
"cleaner than reality" is masking the next bug in that path.

This is a cheap **static review-lens**: for a given domain, encode the
distinguishing markers that real data always carries but a toy fixture often
strips, and flag any in-scope fixture missing them.

## Reusable Pattern

- **Scope gate first.** Decide whether a file is even *in this domain* before
  judging it. A file with none of the domain's signal (e.g. no domain-specific
  characters/tokens at all) is simply skipped — the lens only judges fixtures it
  recognizes as belonging to the domain. This keeps the false-positive rate low.
- **One or more "realism markers."** Each marker is a property real data reliably
  has (a required structural token, a high-frequency element, an
  encoding/normalization characteristic). A fixture missing ANY marker is flagged,
  and the diagnostic names which marker(s) failed.
- **Normalize before matching where the markers interact.** If one marker
  (e.g. "must be richly annotated") would, by being satisfied, break a naive
  search for another marker (a token that real data writes with annotations
  interleaved), strip/normalize a *copy* of the text before the second check — so
  a genuinely production-realistic fixture can satisfy both simultaneously rather
  than the two criteria being mutually unsatisfiable.
- **Standard `0/1/2` exit shape** for identical pre-commit + CI wiring.

## Algorithm

For each file handed in:

1. If the text contains none of the domain's defining signal → return clean
   (not an in-domain fixture; skip).
2. Otherwise evaluate each realism marker:
   - Marker A: presence of the required structural/annotation characteristic.
   - Marker B: presence of the required high-frequency token — searched over a
     *normalized* copy if normalization is needed for the two markers to coexist.
3. Any failed marker → one violation line naming the file and the failed
   marker(s). Either marker alone flags the file.
4. Exit 1 if any violations, 0 if all clean/skipped, 2 on usage/file-not-found.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Lint domain fixtures for production-realism.

Replace the DOMAIN MARKERS below with the properties real data in YOUR domain
reliably carries. Files with no in-domain signal are skipped.

Exit codes: 0 clean/skipped, 1 unrealistic fixture, 2 usage/file-not-found.
"""
from __future__ import annotations

import sys
from pathlib import Path

# --- DOMAIN MARKERS (the only project-specific part) ----------------------- #
# Example shape: a required high-frequency token that real samples always
# contain, and a required annotation/encoding characteristic real samples carry.
REQUIRED_TOKEN = "<token-real-data-always-contains>"


def is_in_domain(text: str) -> bool:
    """True if this file is a fixture in the domain this lens judges."""
    # e.g. contains at least one character/token from the domain's alphabet.
    return REQUIRED_TOKEN[:1] in text  # replace with a real domain predicate


def has_annotation_characteristic(text: str) -> bool:
    """Marker A: real data carries this annotation/encoding property."""
    raise NotImplementedError  # e.g. any char in a required range


def normalize(text: str) -> str:
    """Strip the annotation so an interleaved token collapses to its bare form,
    letting Marker A and Marker B be satisfiable at once."""
    return text  # e.g. drop the annotation codepoints


def has_required_token(text: str) -> bool:
    """Marker B: searched over the NORMALIZED copy."""
    return REQUIRED_TOKEN in normalize(text)
# --------------------------------------------------------------------------- #


def check_fixture_text(path: str, text: str) -> list[str]:
    if not is_in_domain(text):
        return []  # not an in-domain fixture — this lens does not judge it
    reasons = []
    if not has_annotation_characteristic(text):
        reasons.append("missing the required annotation/encoding characteristic")
    if not has_required_token(text):
        reasons.append(f"missing required token {REQUIRED_TOKEN!r}")
    if not reasons:
        return []
    return [f"{path}: fixture is not production-realistic — {'; '.join(reasons)}"]


def main(argv: list[str]) -> int:
    paths = argv[1:]
    if not paths:
        print("usage: check_fixture_realism.py <fixture> ...", file=sys.stderr)
        return 2
    all_v: list[str] = []
    for p in paths:
        path = Path(p)
        if not path.is_file():
            print(f"ERROR: not a file: {p}", file=sys.stderr)
            return 2
        all_v += check_fixture_text(str(path), path.read_text(encoding="utf-8"))
    if all_v:
        print("Fixture-realism violations:")
        for v in all_v:
            print(f"  {v}")
        return 1
    print("OK: all in-domain fixtures are production-realistic.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

## Adaptation Notes

- **The markers are the whole adaptation.** Replace the placeholder predicates
  with the properties real data in *your* domain always has. Worked instances of
  this pattern have used: a required high-frequency particle/token, a required
  rich-annotation characteristic (data that is vocalized / fully-typed /
  fully-populated rather than skeletal), and an encoding-normalization step so the
  two interact correctly.
- **Always include the scope gate.** Without "is this even an in-domain fixture?",
  the lens fires on every unrelated file. Skipping non-domain files is what keeps
  it high-signal.
- **Normalize a copy, never the source.** Normalization exists only to make the
  markers co-satisfiable; do not mutate or rewrite the fixture.
- **Keep the per-file diagnostic specific** — name which marker failed, so the
  author knows exactly how the fixture diverges from reality.
```
