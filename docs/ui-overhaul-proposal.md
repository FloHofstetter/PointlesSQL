# UI Overhaul Proposal

> Phase 53 Sprint C — Synthesis of replay screenshots
> ([_notes.md](e2e-walkthroughs/screenshots/phase53-replay/_notes.md))
> + Bootstrap 5.3 gap analysis
> ([bootstrap53-gap-analysis.md](research/bootstrap53-gap-analysis.md)).
> Date: 2026-05-07.

## Executive Summary

PointlesSQL's UI is **structurally healthy and visually coherent**.
Phase 17 (icon-rail + context-panel + tab-aware run-detail + 6-tab
table-detail) delivered a modern dashboard pattern that is well
ahead of typical "FastAPI admin shell" baselines. The replay sweep
across 35 browser surfaces did not surface any
"the UI is rotten" finding.

It surfaced **one recurring visual-quality bug** (outline buttons
that read as disabled), **one architectural gap** (error pages drop
the sidebar), and **one half-finished Bootstrap 5.3 feature** (the
`data-bs-theme` color-modes API is wired in CSS but has no toggle
UI). It also surfaced 10 medium-severity functional bugs
(BUG-53-01 .. BUG-53-10) — most are walkthrough-doc drift or
missing routes, not visual-quality issues.

**Recommendation: Overhaul size M — Modernize.** Rationale below.

## Visual Debt — from screenshots

Ten distinct patterns observed across 50 screenshots in 25 surface
subdirectories. Detail in
[_notes.md](e2e-walkthroughs/screenshots/phase53-replay/_notes.md);
summary here:

| # | Pattern | Severity | Where it shows up |
|---|---|---|---|
| 1 | Outline buttons render at low opacity, look disabled | High | Home, run-detail, table-detail, branches list, ≥5 surfaces |
| 2 | Error pages (404/403/500/invalid-input) have NO sidebar | High | All error responses |
| 3 | Mobile cards have unlabelled em-dashes | Medium | `/runs` mobile, list pages |
| 4 | Long descriptive alerts at top of admin pages | Medium | `/admin/audit-sinks`, `/admin/api-keys`, `/admin/system-info`, `/admin/external-writes` |
| 5 | Pagination component missing on long lists | High | `/audit/search`, `/audit/queries`, `/runs`, `/jobs/.../runs`, `/admin/audit` |
| 6 | Inconsistent UUID formats in `/api/runs` | Low | `/api/runs` JSON shape (display-layer fix) |
| 7 | Sentinel SHA-256 of all zeros displayed unfiltered | Low | Run-detail Source sub-tab |
| 8 | Tab badges only on first sub-tab, not others | Low | Run-detail Operations, Compare-runs |
| 9 | Test-data leakage (`cat0..catN`) in Cmd-K palette | Low | Demo seed (not UI) |
| 10 | Em-dashes scattered densely in tables | Low | `/runs`, `/admin/audit`, table-detail |

**Pages that look polished (no debt):** `/catalogs/{name}`,
`/runs/{id}/diff/{id}` (compare-runs), `/admin` (landing card grid),
`/branches`, `/connections`, `/dbt`, table-detail Overview.

## Bootstrap 5.3 Gap Analysis — from research

Detail in
[bootstrap53-gap-analysis.md](research/bootstrap53-gap-analysis.md).

Top-3 adoption opportunities (ranked by impact/effort):

1. **`data-bs-theme` color-modes toggle** — Bootstrap 5.3's
   flagship feature. Our CSS is 95% ready (full light-mode override
   block in `base.css`). What's missing: ~30 LOC inline JS in
   `base.html` + a 3-button `<div id="bd-theme">` in the user
   dropdown. **Effort: ½ day.**
2. **Bootstrap `accordion` for stacked detail blocks** — replaces
   our verbose admin-page header alerts (Pattern 4) and the
   flat-stack-of-cards on run-detail Operations tab. **Effort: 1-2
   days.**
3. **Bootstrap `pagination` component** — closes Pattern 5.
   Server-side already supports offset/limit. **Effort: ½-1 day.**

Two patterns deliberately marked **out of scope**:

- `scrollspy` — would force tab-to-section reflow; our `nav-tabs`
  is canonical.
- Bootstrap dashboard col-grid (`col-md-3 col-lg-2` sidebar) —
  Phase 17 chose CSS Grid icon-rail because the col-grid wastes
  horizontal real-estate at < 1280px viewport.

## Half-finished Features — from codebase audit

| Feature | State | What's missing | Effort |
|---|---|---|---|
| Light/dark theme toggle | CSS done (`:root[data-bs-theme="light"]` block) | Toggle UI + `localStorage` persist + `prefers-color-scheme` listener | ½ day |
| `lg+`/`xl` responsive breakpoints | `col-md-*` deep, no `col-lg-*` patterns, 0 `d-none d-md-block` | Audit each list/grid for 1440px+ viewport optimization | 2-3 days |
| Pagination on long lists | Server-side exists, render missing | Render `<nav><ul.pagination>` on 5+ pages | ½-1 day |

## Three Overhaul Sizes

### S — Polish (1-2 days)

Fix the highest-visibility issues from the replay sweep. No new
patterns adopted.

- ✅ Fix Pattern 1 (outline-button opacity). Find the CSS rule
  that lowers `.btn-outline-*` opacity, restore Bootstrap stock.
  Single CSS edit, no template changes.
- ✅ Fix Pattern 2 (error pages drop sidebar). Make `403.html`,
  `404.html`, `5xx.html`, `validation.html` extend `base.html`
  with the rail+context-panel slots populated.
- ✅ Wire the Light/Dark toggle (Bootstrap 5.3 color-modes API,
  ~30 LOC).
- ✅ Fix BUG-53-01 (escaped HTML in `/audit/search` description).
- ✅ Fix BUG-53-02 / BUG-53-04 (walkthrough-doc drift).
- ✅ Fix BUG-53-09 / BUG-53-10 (re-document missing list views).

**Outcome:** Same UI, fewer rough edges. The recurring "is this
button disabled?" friction goes away. Light-mode becomes a
selectable feature instead of dead code.

### M — Modernize (1 week) ⭐ RECOMMENDED

S + adopt the three high-value Bootstrap 5.3 patterns.

- ✅ All of S.
- ✅ Adopt Bootstrap `accordion` for: admin-page header alerts
  (Pattern 4), run-detail Operations buckets (Added/Removed/
  Changed cards stack), Compare-runs sub-axis breakdowns.
- ✅ Adopt Bootstrap `pagination` for: `/audit/search`,
  `/audit/queries`, `/runs`, `/jobs/.../runs`, `/admin/audit`.
- ✅ Fix Pattern 3 (mobile cards): convert run-list mobile cards
  to labelled `<dl>` pairs.
- ✅ Fix Pattern 8 (tab badges everywhere not just first sub-tab).
- ✅ Fix Pattern 6 (UUID format normalization at display layer).
- ✅ Fix Pattern 7 (sentinel SHA-256 → "(no source captured)").
- ✅ Fix BUG-53-03 (`/workspace` icon-rail link broken).
- ✅ Fix BUG-53-07 (`/jobs/new` form route).
- ✅ Fix BUG-53-08 (`/dashboards/new` form route).

**Outcome:** UI feels noticeably richer and less cluttered.
Long-list pages get proper navigation. Bug count drops from 10
to ~3 (the data-products / cdf-tail / route-realignment items).

**Why this is the recommended size:**

1. **Color-modes is a feature users will actually flip on.** The
   toggle gives the app a "modernity check-mark" without changing
   any layout.
2. **Pagination is a known UX gap** — every long-list page today
   forces URL editing for offset navigation. Closing this kills
   the worst real-user pain point.
3. **Accordion compresses admin-page first-fold real-estate** by
   collapsing 4-line info-alerts into a single header. Direct
   information-density win.
4. **The bug-fix subset (BUG-53-03/07/08) is small** but each is
   a "broken on first click" path that hurts new-user tours.

### L — Reflow (2-3 weeks)

M + structural moves that touch every page.

- ✅ All of M.
- ✅ Density toggle (compact / comfy) wired via a second
  `data-bs-density` attribute on `<html>` plus a CSS-vars
  override block. Comparable to Phase 17 ux-overhaul groundwork.
- ✅ `lg+/xl` breakpoint sweep: every list and grid gets a
  4-column variant at ≥ 1440px. Touch ~10 templates.
- ✅ Page-header convention sweep: every detail page gets a
  consistent `border-bottom` + `py-3` + flex-wrap header with
  title + actions + meta-pills. Touch ~25 templates.
- ✅ Mobile drawer overhaul: replace current offcanvas with a
  Bootstrap canonical `navbar-expand-lg` + `offcanvas` pair so
  the sidebar collapses earlier and re-expands on tablet
  landscape.
- ✅ Empty-state library: every "no items yet" panel gets a
  consistent icon + title + body + 1-CTA pattern (replaces the
  ad-hoc empty states that vary across pages).

**Outcome:** Every page feels redesigned. But: the changes go
into ~40 templates and every Phase 17 / 12.x decision gets
reopened. Risk of regressing things that currently work.

**Why NOT recommended now:** Phase 17 already did the heavy lift.
Overhauling again so soon is double-work. Better to ship M and
let real users surface what's wrong with the M layer before
rebuilding everything.

## Anti-Goals

| What we will NOT do in any of S/M/L | Why |
|---|---|
| Tailwind migration | Bootstrap 5.3 covers our needs; switching is multi-week churn for cosmetic gain. |
| React/Vue migration | HTMX + Alpine is the right fit for our supervision-first UX. SPAs add complexity our agent-readable HTML doesn't need. |
| Custom component library replacing Bootstrap | We already wrap with `.pql-stack`/`.pql-cluster`/`.pql-card` — that's the right amount of layering. |
| Visual-regression test suite | Markdown playbooks + Phase 53 screenshots are the canonical evidence trail; Cypress/Percy adds CI complexity for marginal benefit. |
| Storybook / component gallery | We have ~30 Jinja partials, not a 200-component design system. Storybook is overkill. |
| Marketing-page patterns (hero, album, multi-column footer) | Wrong genre — PointlesSQL is a webapp, the docs site is the marketing surface. |

## Recommendation

**Phase 54 = Overhaul size M (Modernize), 1 week.**

Two argument lines drive this pick:

1. **Color-modes + pagination + accordion are three Bootstrap 5.3
   features that map cleanly to existing pain points** — they
   aren't speculative. Every one of them has a concrete page
   that visibly improves the moment we adopt it.
2. **The "outline button looks disabled" bug is recurring across
   ≥ 5 surfaces.** Fixing it once in CSS lifts every page
   simultaneously — that's the highest leverage edit available.

S would leave the pagination + accordion wins on the table.
L would reopen Phase 17 unnecessarily.

**User decision needed:** if M is the pick, should Phase 54 start
in the next session or wait?

(If you'd rather do something different — e.g. skip the overhaul
entirely and prioritize the BUG-53-NN list as a doc-only Phase 54
fixup pass — say so. The proposal isn't load-bearing on Phase 54
existing.)
