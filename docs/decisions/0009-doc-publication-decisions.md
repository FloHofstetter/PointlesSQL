---
title: ADR-0009 Doc-publication architectural decisions
status: Accepted
date: 2026-05-25
---

# ADR-0009 — Doc-publication architectural decisions

## Status

**Accepted** (2026-05-25).  Locks eight cross-cutting decisions that
shape the seven-wave documentation overhaul plan (W1–W7).  Subsequent
wave detail-plans cite this ADR rather than re-litigate any item.

## Context

The codebase reached publication-ready state code-wise (Phase 123
closed the eight-wave Frontend modernisation).  The documentation
landscape did not keep pace: `ROADMAP.md` is 6,327 LOC with one
phase carrying 2,146 LOC alone, `CHANGELOG.md` is 14,277 LOC of which
~12,600 sit in a single flat `[Unreleased]` block, the mkdocs site
is configured but `gh-deploy` is gated behind `workflow_dispatch`,
26 markdown files are orphan from the `mkdocs.yml` nav, and 95 % of
the CHANGELOG body is phase/sprint/rc-keyed (developer-log shape)
rather than Keep-a-Changelog release-notes shape.

Seven master-plan waves attack different surfaces of this gap:

| Wave | Surface |
|------|---------|
| W1   | Doc-audit & navigation IA refresh |
| W2   | `ROADMAP.md` restructure |
| W3   | `CHANGELOG.md` split + release-notes shape |
| W4   | Generated-doc coverage (Python API + REST API) |
| W5   | E2E-walkthrough theme-grouping + naming |
| W6   | `README.md` + `CONTRIBUTING.md` + getting-started polish |
| W7   | mkdocs go-live + link-hygiene CI gate |

Eight architectural decisions span more than one wave and could not
be punted to per-wave detail-planning without producing inconsistent
or non-composable per-wave outcomes.  This ADR records them up front
so each downstream wave inherits a fixed answer.

## Decision 1 — CHANGELOG granularity

**Decision**: cluster the 172 release candidates (rc1 … rc173) into
**~20 release sections aligned to phase boundaries**.  Each cluster
covers contiguous rcs that ship a coherent phase (e.g. "Phase 95
Notebook v3, rc41 – rc92").

### Alternatives considered

- **per-rc (172 sections)** — maximum granularity, but unreadable.
  No reader scrolls through 172 release sections, and the per-rc
  body is usually a single conventional commit which lives in
  `git log` already.
- **per-month** — calendar-clean, but slices phases in half.
  Cluster boundaries should match the work, not the wall clock.
- **per-phase (~50 sections)** — too fine for the largest phases
  (Phase 95 alone is 2,146 LOC), too coarse for the smallest
  (Phase 30 was three commits).

### Why per-rc-cluster wins

A cluster maps 1:1 onto the unit of "what changed in PointlesSQL
between two consecutive readable releases" — exactly the question
release-notes answer.  Per-rc gives `git log`; per-phase requires
extracting some phases; per-cluster naturally splits the largest
phases and merges the smallest.

## Decision 2 — Dev-log location

**Decision**: the archived `[Unreleased]` block lives at
`docs/internal/dev-log/<cluster>.md`, **one file per release
cluster** from D1.

### Alternatives considered

- **Single `docs/internal/dev-log.md`** (12,600 LOC) — easy to
  find, but unwieldy and indexed by the mkdocs search as a single
  page-rank-1 result for every term in the project.
- **Repo-root `DEV-LOG.md`** — GitHub-front-page visible, but
  competes with `CHANGELOG.md` for outside-reader attention.  The
  dev-log is contributor-facing; the CHANGELOG is user-facing.
  Putting both on the GitHub root muddies that line.

### Why per-cluster split wins

Mirrors D1's cluster boundaries so the CHANGELOG release section
and its dev-log archive are sister files.  Files are
search-rankable individually (one cluster doesn't dominate
results).  `docs/internal/` is `not_in_nav` on gh-pages, so the
dev-log stays contributor-only without manual hide.

## Decision 3 — Versions schema

**Decision**: **keep the `rcXXX` numbering scheme**.  Any flip to
semver `0.x.y` is a separate, post-publication decision that this
plan does not undertake.

### Why keep rc

Every existing reference in `ROADMAP.md`, `CHANGELOG.md`, memory
notes, and conversation history uses `rcXXX`.  Flipping schemes
mid-doc-overhaul would invalidate ~thousand references and force
a `mike`-versioning migration on the docs site.  The W7 launch
target is "publish what we have", not "rebrand the versioning".
Re-evaluate post-launch when a 1.0.0 release narrative makes
sense.

## Decision 4 — Doc visibility

**Decision**:

- `docs/internal/**` — **`not_in_nav`** on gh-pages.  Dev-log,
  IA contracts, audit reports, archive.  Contributor-only.
- `docs/research/**` — **public** on gh-pages.  Design-research
  is outside-reader-relevant context.

### Why

`internal/` carries contributor-only artifacts that would confuse
or mislead a first-time visitor (dev-log entries reference closed
phases, audit tables surface temporary state, IA contracts are
maintainer guidance).  `research/` documents *why* certain
architectural directions were taken — that context is high-signal
for a reader evaluating the project for their own use, and
suppressing it reads as opaque.

## Decision 5 — Asset storage

**Decision**: screenshots, GIFs, diagrams live **in-repo at
`docs/assets/`**.  No Git-LFS, no external CDN.

### Why

Repo size sits comfortably in the MB range; LFS adds onboarding
friction for new contributors (one more install, one more credential
domain) without earning its keep.  External CDNs introduce link-rot
risk and a runtime dependency that we explicitly reject for an
offline-first dev story (same reasoning as ADR-0001 §"Consequences"
Monaco-vendoring).  Re-evaluate if assets cross ~100 MB.

## Decision 6 — Auto-generation balance (USER OVERRIDE)

**Decision**: **fully automatic** CHANGELOG + API documentation.

- CHANGELOG: `cliff.toml` already in repo; W3 wires it into a
  Conventional-Commits-driven generator.  No hand-written
  Highlights, no hand-written Breaking-Change sections.
- Python API: mkdocstrings (already configured) renders every
  module in `docs/reference/python/`.
- REST API: W4 picks a plugin (`neoteroi-mkdocs`,
  `mkdocs-render-swagger-plugin`, or `mkdocs-swagger-ui-tag`) and
  auto-renders the FastAPI OpenAPI schema.

### Alternatives considered

- **Hybrid** (planner's recommendation; user overrode) — cliff for
  Add/Change/Fix sections + handcurated Highlights/Breaking.  Higher
  quality release-notes, but every release adds a handwriting tax.
- **Fully handcurated** — maximum quality, maximum maintenance
  burden, drift risk if a release ships without notes.

### Why fully automatic wins for this project

User decision 2026-05-25.  Trade-off: release-notes read closer to
a categorised `git log` than to a marketing post, but the
maintenance tax is zero, and Conventional-Commits discipline (the
project already uses it) plus the W3 commit-message lint hook
described below gives section assignment for free.

### Load-bearing consequence: commit-message discipline becomes a CI gate

W3 adds a commit-message lint hook (commitlint, custom check, or
the cliff-config strict mode — picked in W3 detail-planning).
Failing the gate means failing CI.  Without the gate, the
auto-CHANGELOG quality degrades to whatever the laxest commit
message of the cluster looks like.

Retroactive cluster sections for the 172 existing rcs are
generated in a single cliff run, with anchor commits defined per
phase boundary in `cliff.toml`.  No manual rewriting of historical
release-notes.

## Decision 7 — Phase density norm

**Decision**: hard LOC budgets per entry:

- `ROADMAP.md` — **≤ 80 LOC per phase entry**.  Overflow forces
  extraction to a dedicated phase-detail file (mirror of the
  pattern Phase 95 will require in W2).
- `CHANGELOG.md` — **≤ 200 LOC per release cluster** (from D1).
  Overflow forces extraction to the dev-log file (from D2) with
  only a digest in the CHANGELOG.

### Why hard budgets

The current ROADMAP+CHANGELOG bloat is the historical artifact of
"no budget".  Soft norms have not worked: Phase 95 has been the
elephant in the room for many months without anyone splitting it.
A hard budget enforced by a future lint hook (out of W1 scope, but
W2 detail-planning will consider) makes the extraction non-optional.

### 2026-05-26 W2 amendment — soft ≤80 LOC, hard ≤100 LOC

W2 execution observed that several phases carry compact sub-sprint
tables that scan well at 80–100 LOC but compress poorly below 80
without losing the table shape.  The budget is therefore split:

- **≤ 80 LOC** remains the *aspiration* — phases that fit this
  ceiling without restructuring should.
- **≤ 100 LOC** is the *hard cap* — phases between 80–100 LOC stay
  in `ROADMAP.md` unchanged.
- **> 100 LOC** is non-negotiable extract to
  `docs/internal/phase-NN.md` (per-phase sidecar; main ROADMAP keeps
  the heading + status line + sub-sprint summary table + a one-line
  pointer to the sidecar).

The amendment does not relax D7; it codifies the layout reality
W2 surfaced and prevents counter-productive table-shredding to
chase a 78-LOC target.

## Decision 8 — Doc-vs-code scope separation

**Decision**: documentation waves produce **stub-lists only** for
missing Python docstrings; actual docstring edits are a separate
code wave (or never undertaken if the stub-list reveals coverage
is already acceptable).

### Why

Doc waves are markdown-only by invariant — they do not bump the
asset version, they do not touch pytest collection, they do not
risk source regressions.  Mixing docstring edits violates that
invariant and breaks the "doc-only → no asset bump → no PR-template
gate-flips" cleanliness of W1–W7.

W4 surfaces the coverage gap as a stub list in the audit; W4 does
not act on it.  A follow-on code wave may pick that list up; that
wave is out of master-plan scope.

## Consequences

- `cliff.toml` becomes load-bearing for W3 and must be configured
  with phase-boundary anchor commits.
- W3 grows a commit-message lint hook sub-sprint (deferred from
  W1 to keep W1 scope clean).
- W4 must pick a REST-API rendering plugin in its detail-plan
  before any generation can happen.
- W5 will rename underscored e2e-walkthroughs to hyphenated form
  per D7's implicit naming-consistency expectation (the explicit
  rule lives in `docs/internal/doc-site-ia.md` from W1.4).
- `docs/internal/` requires a `not_in_nav` block in `mkdocs.yml`
  (W1.5 introduces it).
- `docs/research/` is treated as public for all future wave
  scoping; its single current file (`bootstrap53-gap-analysis.md`)
  becomes a top-level nav-section entry rather than a hidden
  curio.
- The "no Highlights" choice means W6's README update points
  outside-readers at the auto-CHANGELOG with a one-line frame
  ("changes are categorised by Conventional-Commits prefix; the
  full per-rc dev-log lives in `docs/internal/dev-log/`").
- Asset budget for `docs/assets/` stays in `.pre-commit-config.yaml`
  `check-added-large-files` (current `--maxkb=512`); LFS-pivot
  trigger is "assets cross 100 MB or a single screenshot exceeds
  the 512 KB hook ceiling".

## Out of scope for this ADR

- The specific cliff-config cluster boundaries (W3 detail-plan).
- The choice of REST-API rendering plugin (W4 detail-plan).
- Whether `mike` versions the docs site (W7 detail-plan).
- The semver flip — explicitly deferred per D3.
- The follow-on code wave for docstring stubs from D8.

## 2026-05-26 W7 closure addendum

W7 resolved two items previously listed as "Out of scope":

- **mike-versioning** is now wired in `mkdocs.yml`
  (`extra.version.provider: mike`) and `.github/workflows/docs.yml`
  (commented `mike deploy` step ready for the launch-sprint flip).
  No public versions exist yet; the first `mike deploy` happens in
  the launch sprint, which also flips the `push:` trigger and
  activates the `pages: write` + `id-token: write` permissions.

- **Cross-repo link contract** — the strict-mode comment in
  `mkdocs.yml` L256-258 states cross-links resolve "either to a
  docs page or to the canonical GitHub URL".  W7 rewrote 97
  in-tree `../../pointlessql/*`, `../../frontend/*`, and stragglers
  (top-level `CLAUDE.md`, sibling `hermes-plugin-pointlessql`,
  `scripts/`) to `https://github.com/FloHofstetter/PointlesSQL/blob/main/...`
  form.  `mkdocs build --strict` now exits with zero warnings.

W7 also widened `scripts/check-no-phase-refs.sh` from
`frontend/`-only to `frontend/` + `pointlessql/` (excluding
`alembic/versions/`) after a mechanical strip of 107 historical
phase/sprint/wave refs from non-alembic Python docstrings + inline
comments.  The CLAUDE.md "future cleanup wave" stub is gone.

A new `link-check` job in `.github/workflows/docs.yml` runs the
[lychee](https://github.com/lycheeverse/lychee) link-checker over
`docs/`, `README.md`, `CHANGELOG.md`, and `CONTRIBUTING.md` to
catch future cross-link drift before it reaches main.

Still out of scope:
- Semver-flip — per D3, explicit defer to post-publication.
- First public mike-deploy — launch-sprint operator decision.
- Repo visibility flip — manual GitHub-Settings step.
