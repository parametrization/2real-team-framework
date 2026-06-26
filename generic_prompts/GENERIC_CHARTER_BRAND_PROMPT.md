# Generic Charter: Branding Conventions Template

## Purpose

A project usually has **two distinct forms of its name**: a human-facing
**display name** and a machine-facing **code identifier**. These look similar
but obey different rules, and the most common branding bug is using one where
the other belongs (or inventing a third camel-cased hybrid). This template is
the *pattern* of keeping a single, spell-checked source of truth for both — fill
in your own brand.

This is intentionally about the **convention**, not any particular brand name.

## The two forms

| Form | Where it appears | Shape | Example shape |
|------|------------------|-------|---------------|
| **Display name** | All user-facing text: page titles, headings, meta tags, copy, docs, error messages | Human-readable, with spacing/casing as designed | `Acme Widgets` |
| **Code identifier** | Org/repo/package names, import paths, CSS classes, URLs, domain | Lowercase, no spaces, slug form | `acmewidgets` |

Rules:

- **All user-facing text MUST use the display name** exactly (correct spacing,
  correct casing).
- **Code identifiers remain the slug** — never spaced, never title-cased.
- **Do not invent a third hybrid form** (e.g. a camel-cased mashup of the two).
  That hybrid is the canonical wrong answer and is what a spell gate should
  flag.

## Correct vs wrong table (template — replace with your brand)

| Context | Correct | Wrong |
|---------|---------|-------|
| Page heading | `<Display Name>` | `<CamelHybrid>` |
| Meta `og:site_name` | `<Display Name>` | `<CamelHybrid>` |
| Package scope | `@<slug>/<pkg>` | `@<wrong-slug>/<pkg>` |
| Repo host org | `<slug>` | `<wrong-slug>` |

## Spell-gate enforcement

Make the wrong form **machine-detectable**:

- Do **not** add the camel-cased hybrid to the project spell-check dictionary.
  Leaving it un-blessed means the spell gate flags it everywhere.
- The slug form is a legitimate dictionary entry (it is a real identifier); the
  display name's words are ordinary words. Only the hybrid stays unrecognized.
- The one file allowed to contain the wrong form is **this conventions doc
  itself**, because it documents the form *as wrong*. Guard that single
  exception with an inline spell-checker ignore directive scoped to this file —
  never a global dictionary entry, which would un-gate the typo project-wide.

## Adaptation notes

- Fill in your actual display name, slug, package scope, and host org.
- If you have more than two forms (e.g. a separate short name or ticker), add a
  row per form and state which contexts each governs.
- The load-bearing idea is the **spell-gate-as-enforcement**: a branding rule
  with no automated check decays. Wire the wrong form to a failing spell check
  rather than relying on reviewer memory.
