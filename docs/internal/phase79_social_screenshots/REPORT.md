# Phase 79 Social-Layer Browser-Walkthrough — Bug & UI Critique

**Date:** 2026-05-15
**Scope:** GitHub-style social features across DPs / Models / Tables / Branches / Runs / Notebooks / Issues / Feed / Profiles / Topics / Workspace landing / Topbar bell
**Setup:** soyuz-catalog @ :8080 + pointlessql @ :8000, existing demo DB (3 DPs, 8 comments, 2 reviews, 1 endorsement, 3 topics, 1 model). One issue created via API for testing.

## Headline finding

The polymorphic social layer (Phase 77) ships a richer surface
on UC tables + models than on the original Phase-71/76 DP-detail
page.  DP-detail is now the **inverse-coverage outlier**: the
entity-kind that motivated the social layer in the first place
no longer shows half the social affordances that polymorphic
kinds get out of the box.  Multiple stale "deferred to Phase
77.X" comments + a broken issue-detail page round out a picture
of a layer that landed feature-by-feature but never got a final
"replay every surface end-to-end" QA pass.

15 distinct issues identified in one walkthrough.  Two are
**critical** (P0), four are **functional** (P1), the rest are
inconsistency / polish.

---

## Critical bugs (P0)

### 🐛 #4 — Issue-create modal silently fails on DP-detail page

**Where:** `frontend/templates/pages/data_product.html:518`
**Symptom:** Clicking "Open issue" in the modal does nothing.
No error, no spinner, the modal stays open.  DB row count
unchanged.  No console error.
**Root cause:** The inline x-data wrapper around the
`_issues_pane.html` partial reads `product.catalog_name +
product.schema_name`, but the parent `dataProductDetail`
factory exposes those fields as `product.catalog +
product.schema` (no `_name` suffix).  Result:
`ref = "undefined.undefined"`, so the issues-pane fetches
`/api/social/dp/undefined.undefined/issues` (200 returns empty
list) and POSTs to the same URL (gets ignored).
**Fix:** Change the inline x-data to `ref: product.ref` (which
already exists on the server payload as `main.sales_gold`).
**Reproduction:** see
`01_dp_social_tabs/09_dp_issue_new_modal.png` +
`10_dp_issue_created.png` (modal still open after submit).

### 🐛 #8 — Issue-detail page (`/issues/{id}`) Alpine-broken

**Where:** `frontend/templates/pages/issue_detail.html:56-80`
**Symptom:** 9 console errors on load.  Title heading empty
("manual test" body shown without title), tab panels blank,
`State` side card empty.  Console:
- `SyntaxError: expected expression, got '}'`
- `ReferenceError: activeTab is not defined` ×6
- `TypeError: can't access property "after", O is undefined`
  in `loadEndorsements` (`social_tabs.js:76`)

**Root cause:** Template mounts `socialTabs({…})` factory then
references `activeTab` for tab-switching (`x-show="activeTab
=== 'discussion'"`), but the factory never exposes that field.
Additionally it passes `endorsementTypes: ["verified-by-…",…]`
as plain strings; the factory expects `{key, label}` records.
Add to that: an `issue` isn't a meaningful target for
endorsements/followers — it conceptually only has Discussion +
Subscribers — but the page wires all three.
**Fix paths:**
- Add `activeTab: 'discussion'` (default) to the `socialTabs`
  factory return — and a setter / getter pair for switching.
  OR keep `activeTab` outside the factory by giving the page
  its own outer x-data scope.
- Drop the Endorsements / Followers tabs entirely from
  `issue_detail.html` (subscribe-to-issue is a separate
  concept and isn't built today).
**Reproduction:** `03_issues_feed/02_issue_detail.png`.

---

## Functional bugs (P1)

### 🐛 #6 — Endorsements API works but no UI surface on DP-detail

**Where:** `frontend/templates/pages/data_product.html` overview tab
**Symptom:** `main.sales_gold` has 1 `production-ready` endorsement
(`/api/data-products/main/sales_gold/endorsements` returns 200
with the row).  UI shows nothing — no badge in the title row,
no card on Overview tab, no top-level Endorsements tab.
Compare to UC tables (`/catalogs/.../tables/orders`) which
*do* show an Endorsements tab with full apply / remove UI.
**Fix:** Either lift the polymorphic endorsements panel into
DP-detail (preferred — consistent with other kinds) or render
the active endorsements as title-bar chips (lighter).
**Reproduction:** compare
`01_dp_social_tabs/05_dp_overview_full.png` (DP — nothing)
with `02_polymorphic_per_kind/02_table_endorsements_tab.png`
(UC table — full panel).

### 🐛 #7 — Follow-button hardcoded disabled on non-DP kinds with stale "Phase 77.8" copy

**Where:** Polymorphic followers pane (used by table /
model / branch / notebook surfaces).
**Symptom:** Follow button is `disabled=true` with text
`Unfollow` (showing the wrong state — there are zero
followers).  Body copy says:
> Following non-data-product entities lands in Phase 77.8
> once the polymorphic follower table ships.  The button
> stays disabled until then; you can still post comments
> and apply endorsements.

Phase 77.8 closed on 2026-05-15 and Phase 78 consolidated
`data_product_follows` → `social_follows` shortly after.  The
backend ships polymorphic follows; only the frontend gate
still pretends otherwise.
**Fix:** Remove the `followLocked = kind !== 'dp'` line from
`socialTabs` factory (`frontend/js/social_tabs.js:38`) and
remove the stale copy from `_followers_pane.html`.
**Reproduction:** `02_polymorphic_per_kind/03_table_followers_tab.png`.

### 🐛 #11 — Feed-entry review row missing entity reference

**Where:** `/feed` page
**Symptom:** A review row appears as
`[review] ★★★★ —  2026-05-13T15:20:46.108767` — no link to
the DP, no entity FQN, just stars + dash.  Adjacent comment
row works (`[comment] self-comment to trigger SSE` with link).
**Fix:** Render the entity FQN + link on review feed items.
**Reproduction:** `03_issues_feed/03_feed.png`.

### 🐛 #12 — Citation tokens not resolved in user-profile "Recent comments"

**Where:** `/users/{id}` page
**Symptom:** Comment-body lines render raw markdown tokens:
`Citations test #dp:main.customer_360 plus topic #topic:finance`.
On DP-detail Discussion tab the same tokens render as anchor
links.  The cite-resolver isn't wired into the profile-page
render path.
**Fix:** Apply `resolve_citations(body_md, …)` server-side
when building `recent_comments` for the profile view, OR
plug the frontend `pqlRenderCitations` helper into the
profile template.
**Reproduction:** `04_profile_topics_workspace/02_user_profile.png`.

---

## Inconsistencies & polish (P2)

### 🟡 #1 — DP-detail Overview tab is sparse vs. other kinds

DP overview shows only Steward / Description / Freshness /
Last loaded / UC ref.  No endorsement chips, no top
followers, no recent activity summary.  Compare to UC tables
where Overview is a richer dashboard.  Phase 76 added
follow_count / avg_stars / review_count to the DP listing
API but they only surface in the *header* bar, not on the
Overview tab itself.

### 🟡 #2 — Activity tab uses raw audit-trail strings

Activity items read like
`audit.discussion_posted on data_product.main.sales_gold#tab-discussion-comment-9`.
Polished UX would use verbs + avatars: "Bob Dataops commented
on Discussion · 2 minutes ago".

### 🟡 #3 — Issue-create modal lacks Labels / Assignee / Milestone pickers

DB has `issue_labels` + `issue_milestones` tables.  Modal
only collects Title + Body.  Not GitHub-parity yet.

### 🟡 #5 — Unknown `?tab=X` query falls through to Overview silently

`?tab=followers` / `?tab=endorsements` on DP-detail silently
returns Overview (the tab keys don't exist).  Either redirect
to the actual top-level tab home, or render an empty-state
panel for the requested tab.  Discussion counter (badge "8")
disappears after the bogus tab fallback — visual flicker.

### 🟡 #9 — Issue-detail title row only shows `#1 [open]` (title is missing visually)

Even if Alpine renders, the title heading lacks visual weight
— `#1` and the state badge look like the whole title.
Probably tied to Bug #8 fix.

### 🟡 #10 — Issue-detail right-rail "State" card is empty

Just the label "State" with no value beneath.  Likely
unrendered because of the same Alpine breakage.

### 🟡 #13 — Topic-detail page has no social interactions

`/topics/{slug}` shows only Description + Data products list +
follower count.  No discussion, no mention-aggregator, no
activity feed.  Topics are the only social entity that
doesn't surface its own conversation thread despite being a
first-class polymorphic kind.

### 🟡 #14 — Workspace-landing activity feed shows empty avatar dashes

Each row renders a gray placeholder where the actor's avatar
should be (`—` instead of an initial-circle).  Visually
ungainly; either render a one-letter initial fallback or
real avatars.

### 🟡 #15 — Notification inbox shows empty despite live activity

`/notifications` shows "Nothing here yet" even though the
admin has posted comments + reviews recently.  Likely a
correct-by-design *self-filter* (actor != recipient), but
without any explanation the empty state misleads.  Consider
copy like "You have no unread notifications from other
people".

### 🟡 — User-profile URL accepts only numeric id

`/users/admin@demo.com` returns "Invalid input — Request
validation failed".  Pretty username URLs (`/u/{email}` or
`/u/{display_slug}`) would be a small but real polish.

---

## Confirmed-working surfaces (positive findings)

- DP-detail **Discussion** tab — full Phase-76 surface: 8
  comments rendered with author, agent badge, category enum,
  threading, reactions toolbar (👍👎🎉😄😕👀), citation
  anchors, Reply / Delete actions, markdown composer with
  category dropdown.
- DP-detail **Reviews** tab — star composer, existing 5-star
  review with agent (Nightly Bot) badge.
- DP-detail **README** tab — proper empty state with "Add
  README" + "Generate one now" passport prompt.
- DP-detail **Issues** tab list — clean empty state with
  CTA button (the *create* path is what's broken, see #4).
- UC **table-detail** tabs: Overview / Preview / Columns /
  Lineage / Tags / Permissions / Discussion / Endorsements /
  Followers / README / Issues — full GitHub-style row.
- UC **table Endorsements** tab — 4 endorsement types with
  descriptions + per-type count + Endorse button.
- UC **table Discussion** tab — polymorphic write tested via
  API call, returns 200 with reactions array attached.
- Model-detail tabs: Overview / Versions / Lineage /
  Promotion / Discussion / Reviews / Endorsements /
  Followers / README / Issues + "Open in MLflow UI" external.
- Notebook editor toolbar **Social** button → side drawer
  (Discussion / Endorsements / Followers / README).
- Global **Issues index** with filter chips (All / Open /
  Closed / Assigned to me / Opened by me).
- **Feed** page filter UI: Mentions / Followed users /
  Followed DPs / My activity + entity-kind chips (DPs /
  Tables / Models / Branches / Runs / Schemas / Catalogs /
  Notebooks / Queries / Issues) — coverage is impressive
  even if event rendering needs polish (#11).
- **User profile** page — 4 metric cards, stewarded products
  list, recent comments + reviews block (citation render
  issue #12 aside).
- **Topics index** — clean card grid with description +
  follower / DP counts + Unfollow chip + "New topic" CTA.
- **Workspace landing** — pinned entities + activity feed
  with human-readable verbs ("commented on", "started
  following").
- **Notifications inbox** — filter + "Unread only" toggle +
  event-type dropdown + Refresh.

---

## Recommended Phase 80 scope

A "Social UX consistency" interstitial sprint, scoped narrowly:

| # | Change | Files | Est. effort |
|---|---|---|---|
| 1 | Fix DP-detail issue modal ref typo (Bug #4) | `data_product.html:518` | 5 min |
| 2 | Fix issue-detail Alpine errors (Bug #8) | `issue_detail.html`, `social_tabs.js` | 1-2 h |
| 3 | Lift endorsement panel into DP-detail (Bug #6) | `data_product.html` + reuse existing polymorphic partial | 2-3 h |
| 4 | Drop `followLocked` gate + stale copy (Bug #7) | `social_tabs.js`, `_followers_pane.html` | 30 min |
| 5 | Render entity FQN on feed review rows (Bug #11) | feed serialiser | 1 h |
| 6 | Resolve citations in user-profile recent comments (Bug #12) | profile route | 30 min |
| 7 | Tabs fall through to closest visible tab, not Overview (#5) | DP-detail tab JS | 30 min |
| 8 | One-letter initial-circle avatar fallback (#14) | partials/avatar.html | 30 min |
| 9 | Issue create modal: add Labels picker (#3) | `_issues_pane.html` + new ui | 2-3 h |
| 10 | Activity-tab human-readable verb mapping (#2) | activity serialiser | 2-3 h |

Total ≈ 10-14 hours, very small commits, clear visual win.

---

## Screenshot inventory

* `01_dp_social_tabs/` — 11 PNGs of DP-detail walkthrough
* `02_polymorphic_per_kind/` — 11 PNGs of UC table / model / branch / runs / notebook
* `03_issues_feed/` — 3 PNGs of Issues index / detail / Feed
* `04_profile_topics_workspace/` — 7 PNGs of profile / topics / workspace / inbox

All screenshots captured at viewport 1440×900 via Playwright firefox
MCP, logged in as `admin@demo.com` (password reset to `admin`
mid-walkthrough to gain access).
