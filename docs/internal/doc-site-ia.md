# Documentation-site Information Architecture

> **Status**: authoritative contract for the `docs/` tree on
> gh-pages.  Every markdown file under `docs/` either has a nav
> entry in [`mkdocs.yml`](../../mkdocs.yml) or is listed under that
> file's `not_in_nav:` block.  Drift is caught by
> [`scripts/check-doc-orphans.sh`](../../scripts/check-doc-orphans.sh).
>
> Introduced 2026-05-25 in W1 of the seven-wave Documentation
> Master-Plan, alongside [ADR-0009](../decisions/0009-doc-publication-decisions.md).

## This document is not the frontend UI IA

[`navigation_ia.md`](navigation_ia.md) covers the **web app's** four-
chrome-slot nav model (top bar · primary rail · context panel ·
footer).  Two completely different contracts:

| File                  | Surface                                             |
|-----------------------|-----------------------------------------------------|
| `navigation_ia.md`    | Frontend UI navigation (web app)                    |
| `doc-site-ia.md`      | Documentation tree on gh-pages (this file)          |

A page added to the web app updates `navigation_ia.md`.  A markdown
file added under `docs/` updates this file (or rather, fits into one
of the subdirs it already defines and gets a nav entry in
`mkdocs.yml`).

## Subdirectory contract

Every `docs/<subdir>/` has a purpose, a primary audience, and a
"when to add a page here" rule.  Pages that don't fit cleanly into
one of these subdirs are a smell — either re-scope the page or
extend this contract.

| Subdir                  | Purpose                                                    | Audience                | Owner-wave | When to add a page here                                            |
|-------------------------|------------------------------------------------------------|-------------------------|-----------:|--------------------------------------------------------------------|
| `getting-started/`      | Install, quickstart, first-5-minute concepts               | outsider                | W6         | First-touch user content.  If a page assumes existing install, it isn't getting-started — it's concepts or guides. |
| `concepts/`             | What PointlesSQL *is* — the noun-vocabulary                | outsider                | —          | New cross-cutting concept the rest of the docs reference.  One concept per file; no how-tos. |
| `guides/`               | How-to narratives, longer than concept pages               | outsider                | —          | Multi-step recipe spanning several concept pages.  If it's a single concept, it's `concepts/`. |
| `e2e-walkthroughs/`     | Deterministic Markdown playbooks for every UI surface      | outsider, contributor   | W5         | A specific user journey (UI surface, multi-step) that a human or Playwright agent can replay. |
| `admin/`                | Operational guides for installation administrators         | operator                | —          | "How to configure / operate X in production".  Not user-facing. |
| `integrations/`         | Third-party integration setup + usage                      | operator                | —          | A new system PointlesSQL talks to (Hermes, MLflow, Grafana, soyuz-catalog, etc.) |
| `reference/`            | Auto-generated + curated API surface                       | contributor             | W4         | New API surface (Python, REST, CLI, configuration).  Hand-written stubs live here; auto-gen subpages too. |
| `development/`          | Maintainer-facing conventions, architecture, test surface  | contributor             | —          | New "how the codebase works" doc.  ADR-worthy decisions go in `decisions/`, not here. |
| `decisions/`            | ADRs (MADR / loose Nygard format)                          | contributor             | —          | A decision worth re-reading in six months.  One file per ADR; numbered sequentially. |
| `research/`             | Design-research artifacts (gap analyses, proposals)        | outsider, contributor   | —          | Reviewable design input that hasn't ossified into an ADR yet. |
| `internal/`             | Maintainer-only artifacts                                  | internal                | —          | **Always** `not_in_nav` (see below). |

## The `internal/` carve-out

Files under `docs/internal/` are never linked from public-facing
pages, are listed in `mkdocs.yml not_in_nav:`, and surface only to
contributors who read the repo directly.

What lives here today:

- IA contracts (`navigation_ia.md`, this file)
- Audit reports (`doc-audit.md`, `doc-audit.tsv`,
  `quality_final.md`)
- Archive material (`roadmap_archive.md`)
- Per-cluster dev-log files (W3 deliverable; lives at
  `docs/internal/dev-log/<cluster>.md`)

What does **not** belong here:

- Concept primers (move to `concepts/`)
- Operational how-tos (move to `admin/`)
- ADRs (move to `decisions/`)
- Anything an outside reader would benefit from (move to the
  appropriate public subdir)

If you find yourself wanting to link from a public page to an
internal/ page, that's the signal the file is mis-located.  Hoist
the relevant content out of `internal/`.

## When adding a new page

1. **Pick the subdir** using the table above.  If nothing fits,
   propose extending this contract (PR with both the new entry
   and the rationale).
2. **Pick the filename** — hyphen-separated lower-case
   (`foo-bar.md`, not `foo_bar.md`); for ADRs use
   `NNNN-kebab-case.md` with the next sequential number.
3. **Add the nav entry** in
   [`mkdocs.yml`](../../mkdocs.yml) under the right group.
   If the page is genuinely contributor-only, add it to
   `not_in_nav:` instead — never both.
4. **Cross-link** from the subdir's `index.md` if one exists.
5. **Run** `uv run mkdocs build --strict` locally before committing
   so a broken link surfaces before CI.

The orphan-guard hook [`check-doc-orphans.sh`](../../scripts/check-doc-orphans.sh)
runs on every commit and fails if a file under `docs/` is
neither in nav nor in `not_in_nav:`.

## Audience tagging

Audience is implicit in the subdir choice (the table's third
column is the contract).  No per-file front-matter tag is required.
Pages that legitimately span two audiences should pick the
narrower one — `e2e-walkthroughs/` is the documented exception
because the same playbook serves both an outside-reader who's
learning the UI and a contributor who's writing a Playwright
replay.

## Naming convention

| Pattern                          | Used for                                           |
|----------------------------------|----------------------------------------------------|
| `lower-case-with-hyphens.md`     | Default for all pages                              |
| `NNNN-short-title.md`            | ADRs (sequential, never reuse a number)            |
| `index.md`                       | Section landing page (one per subdir)              |
| `README.md`                      | Currently used in `e2e-walkthroughs/` and `integrations/hermes-jobs/`; keep `README.md` for index-shaped narratives, `index.md` for navigation-shaped landing pages |

Underscores in filenames are legacy.  Ten e2e-walkthrough files
predate this rule (logged in
[`doc-audit.md`](doc-audit.md#naming-convention-drift)) and get
renamed in W5.

## `not_in_nav` discipline

Adding a file to `not_in_nav:` is an explicit statement that the
file is shipped on disk but should not appear on gh-pages.
Reasons:

- The file is `internal/` (contributor-only)
- The file is a maintained-on-disk asset (excalidraw source,
  JSON sample) that other pages reference

Putting an outsider-facing page in `not_in_nav:` to avoid linking
it is **wrong** — either delete the page or fix the page so it
deserves nav.  The orphan-guard hook doesn't enforce this
distinction (it can't); we rely on PR review to catch it.

## Versioning

Until ADR-0009 / D3 is revisited, the docs site is **un-versioned**
(rolling latest on gh-pages).  No `mike` setup, no
`/0.1.0rcXXX/` prefix on URLs.  A future ADR (likely
post-publication) flips this.

## Maintenance discipline

When this contract is extended (new subdir, new naming convention,
new audience tag), open a new ADR or amend ADR-0009 — never silently
edit this file.  The contract is the schema; the schema is versioned
through decisions.

### See also

- [ADR-0009 — Doc-publication decisions](../decisions/0009-doc-publication-decisions.md)
- [Documentation audit](doc-audit.md)
- [Frontend UI navigation IA](navigation_ia.md)
- [`mkdocs.yml`](../../mkdocs.yml)
- [`scripts/doc-inventory.py`](../../scripts/doc-inventory.py)
- [`scripts/check-doc-orphans.sh`](../../scripts/check-doc-orphans.sh)
