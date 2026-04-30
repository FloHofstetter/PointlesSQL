---
title: ADR-0004 Public-flip checklist
status: Accepted
date: 2026-04-30
---

# ADR-0004 — Public-flip checklist

## Status

**Accepted** (2026-04-30).  Codifies the procedure the launch
sprint will follow when flipping PointlesSQL from private to
public.

## Context

Phase 22 builds the docs site with a deliberate "local-only"
deploy posture (user pick 2026-04-30): the
`.github/workflows/docs.yml` workflow stays on
`workflow_dispatch` only, the `gh-deploy` line is commented
out, the README points at `mkdocs serve` rather than a URL.
This is to avoid leaking the project before launch is ready.

The launch sprint (post-Phase-22) flips that posture.  This ADR
is the **canonical procedure** for that flip — to document
exactly what changes, in what order, and why.

## Decision

Flip in **three commits**, gated by a four-item pre-flight
checklist.  No partial flips — either everything happens, or
nothing does.

### Pre-flight checklist (must complete before commit 1)

1. **EUIPO trademark check** — search the
   [EUIPO eSearch](https://euipo.europa.eu/eSearch) database for
   "PointlesSQL".  No exact-match hit ⇒ proceed.  Hit ⇒ either
   rebrand or pay the €2,550 EUTM filing fee first (see
   [memory: GTM strategy](https://github.com/FloHofstetter/PointlesSQL/blob/main/CLAUDE.md)
   for the rationale).
2. **NOTICE file** — add `NOTICE` to the repo root listing
   transitive Apache-2.0 + MIT + BSD-3 deps that require
   attribution.  Generate with
   `uv run pip-licenses --format=plain-vertical --with-license-file`.
3. **CLA decision** — pick "no CLA" (default; Apache 2.0 is
   sufficient) or DCO sign-off or full CLA.  No-CLA is the
   recommended choice; document in `CONTRIBUTING.md`.
4. **Custom domain decision** — `flohofstetter.github.io/PointlesSQL/`
   (default; works immediately) or a custom domain like
   `pointlessql.dev` (requires DNS + SSL cert + EUIPO trademark
   on the domain name).  Default = github.io subdomain.

### Commit 1 — Workflow flip

`.github/workflows/docs.yml`:

- Replace `workflow_dispatch:` with the commented-out `push:`
  block.
- Uncomment the `gh-deploy` step.
- Remove the launch-sprint TODO marker comments.

This commit alone produces no public site yet because the repo
is still private.  GH Actions runs the build, succeeds, but the
gh-pages branch can't be served publicly.

### Commit 2 — Repo visibility

Run separately (not a code commit):

```bash
gh repo edit FloHofstetter/PointlesSQL --visibility public
gh repo edit FloHofstetter/soyuz-catalog --visibility public
gh repo edit FloHofstetter/hermes-plugin-pointlessql --visibility public
gh repo edit FloHofstetter/shoreguard-fresh --visibility public
```

The four flip together — there's no point making PointlesSQL
public if soyuz-catalog stays private (the wheel pin would
fail).

### Commit 3 — README badge + announcement

- `README.md`:
  - Replace the "run `uv run mkdocs serve`" pointer with a
    "Documentation: <https://flohofstetter.github.io/PointlesSQL/>"
    badge.
  - Add the standard CI / coverage / license badges at the top.
  - Add a short "Announcing PointlesSQL" pointer to the
    HN / Twitter / blog post.
- `docs/index.md`:
  - Remove the launch-sprint TODO HTML comment.
  - Optional: add the same badges row.

After this commit, social-post copy (HN top + Twitter thread +
blog) goes out per the [memory: GTM
strategy](https://github.com/FloHofstetter/PointlesSQL/blob/main/CLAUDE.md).

## Consequences

### Positive

- One coherent moment of public visibility — README, docs site,
  repo all flip together.
- Pre-flight checklist forces explicit decisions on EUIPO,
  NOTICE, CLA, domain.  No surprises.
- Reversible at the repo-visibility level (`gh repo edit
  --visibility private`) within ~5 minutes.

### Negative

- Coordination cost: four repos must flip simultaneously.
  Mitigated by scripting the four `gh repo edit` calls.
- Custom domain ergonomics: if "default github.io" is chosen at
  flip time and we later decide to bring up
  `pointlessql.dev`, the URL changes break external bookmarks.
  Mitigated by setting the canonical URL in `mkdocs.yml`'s
  `site_url` from day one and using rel="canonical".

### Neutral

- The docs site URL becomes search-indexed within ~24 h of
  flipping public.  Plan for that — make sure the landing page
  is the version you want strangers to read first.

## What's *not* in this ADR

- **Cut a v1.0.0 tag**.  Defer to after public soak.  The launch
  flip is just visibility — no semver promise.
- **Versioned docs (`mike` plugin)**.  Defer to v1.0.0.
- **Algolia DocSearch**.  mkdocs-material's built-in is fine for
  ~50 pages.

## References

- [memory: project_gtm_strategy_2026_04_27.md](https://github.com/FloHofstetter/PointlesSQL/blob/main/CLAUDE.md)
  — repo ownership, two-stack model, EUIPO €2,550 filing fee,
  CLA / NOTICE hygiene
- [memory: project_phase10_packaging.md](https://github.com/FloHofstetter/PointlesSQL/blob/main/CLAUDE.md)
  — private-GHCR + dual-auth Dockerfile (Sprint 40)
- [Phase 22 plan](https://github.com/FloHofstetter/PointlesSQL/blob/main/.claude/plans/dann-plane-diese-vollst-ndig-stateful-music.md) —
  the deploy-strategy decision (local-only vs deploy-now) that
  set up this ADR
