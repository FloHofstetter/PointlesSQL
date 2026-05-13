# Social — full social network around data products

> **Mode:** `browser` · **Phase:** 76 · **Surface:** `/data-products/{cat}/{sch}` Discussion + Reviews tabs · `/users/{id}` · `/agents/{slug}` · `/topics/{slug}` · `/feed` · `/notifications` · `/me/settings` · `/data-products/trending` · `/data-products/candidates`

Replays the Phase-76 happy path: the data-product surface is now a
full social network. Users follow other users, topics aggregate
data products, agents post first-class comments / reviews /
endorsements (always alongside a human principal), and cross-DP
citation tokens (`#dp:`, `#topic:`, `#user:`, `#agent:`) render
as internal anchors in every body field. The Discussion tab
supports `@`-mention typeahead, deep-linking via `?tab=discussion`,
threaded replies, accepted-answer marking on questions, and emoji
reactions. The bell in the topbar fans out notifications in real
time over SSE, and `/feed` aggregates everything you follow.

## Preconditions

1. `auth.md` has been run — `admin@pql.test` exists and is logged
   in; `user@pql.test` exists.
2. `data_products.md` has been run at least once — at least one
   data product (typical: `main.sales_gold`) is cached.
3. A second cached data product makes the cross-DP citation step
   testable. If only one DP is cached, drop a second
   `pointlessql.yaml` (e.g. `main.customer_360`) and POST to
   `/api/data-products/reload`.

## Walkthrough

### 1. Cite-token render in a fresh comment

Intent: confirm that `#dp:cat.sch` / `#topic:slug` /
`#user:email` / `#agent:slug` tokens are server-resolved at
serialise time and rendered as safe internal anchors in the UI.

1. `browser_navigate('http://127.0.0.1:8000/data-products/main/sales_gold')`
   - Assert: page loads, 9 tabs visible
     (Overview / Contract / Diff / Lineage / Compliance /
     Activity / Discussion / Reviews / README).
2. `browser_click('button[data-pql-tab-key="discussion"]')`
   - Assert: Discussion tab activates;
     `textarea.pql-comment-new` is rendered with the placeholder
     "Markdown supported · @email · #dp: · #topic: · #agent:
     typeahead".
3. `browser_fill_form` the new-comment textarea with:
   `see #dp:main.customer_360 for context and ping #topic:finance`
4. `browser_click('button.pql-comment-submit')`
   - Assert: a new `div.pql-comment-card` appears at the top of
     the list, body contains **clickable anchors**
     `<a class="pql-citation" href="/data-products/main/customer_360">#main.customer_360</a>`
     and a topic anchor — **not** literal `#dp:` text.
5. `browser_evaluate('() => document.querySelectorAll("a.pql-citation").length')`
   - Assert: ≥ 2 (two tokens rendered).
6. Hover over the DP citation; assert the cursor flips to
   pointer + the link target is `/data-products/main/customer_360`.

> **Why this works**: Phase 76.7 added a parallel
> `body_md_resolved` field to the comment / reply / review /
> endorsement serialiser; `frontend/js/citation_render.js` HTML-
> escapes the body, then rewrites markdown anchors
> `[label](/path)` to safe `<a>` elements. The regex only matches
> hrefs starting with `/` — `javascript:` URIs and external hosts
> can never reach the DOM.

### 2. `@`-mention picker typeahead

Intent: regression-guard for Phase 76.6.3 (mention-picker
response-key drift).

1. With the Discussion tab still active, click into
   `textarea.pql-comment-new`.
2. `browser_type` the text `@adm`.
3. `browser_wait_for` the dropdown (`ul.pql-mention-dropdown` or
   the equivalent floating div rendered by
   `mention_autocomplete.js`).
   - Assert: ≥ 1 row containing `admin@pql.test`.
4. Press `Tab` or click the matching row.
   - Assert: textarea content reads
     `@admin@pql.test ` (trailing space).
5. Erase, type `@nope-no-such-user-`, wait 250 ms.
   - Assert: dropdown closes or shows the empty-state row
     ("No matches"); no JS console error.

### 3. Agent author badge on a new comment

Intent: confirm Bug 12 (Phase 76.5 agent first-class actor) is
visible in the UI — agent posts always render the human author
**plus** an `<a>`-linked agent badge to its right.

1. Open a terminal next to the browser; export the admin's JWT
   cookie value (from the browser's DevTools → Application →
   Cookies → `pql_session`).
2. Post a comment as the `nightly-bot` agent:

   ```bash
   curl -X POST \
        "http://127.0.0.1:8000/api/data-products/main/sales_gold/comments?as_agent=nightly-bot" \
        -H "Cookie: pql_session=<value>" \
        -H "Content-Type: application/json" \
        -d '{"body_md": "Agent posting — sanity check"}'
   ```

   - Assert: 200 response carries
     `agent: {slug: "nightly-bot", display_name: ..., is_verified: ...}`.
3. `browser_navigate` back to the DP detail page, open Discussion.
   - Assert: the newest comment carries both the strong-tag
     human author **and** a `<span class="badge bg-info pql-comment-agent-badge">`
     to its right, with a bot icon and a clickable
     `/agents/nightly-bot` link.
4. Click the agent name.
   - Assert: URL is `/agents/nightly-bot`; page shows
     `h3.pql-agent-display-name`, `h4.pql-agent-run-count`,
     `ul.list-group.pql-agent-comments`.

> **Why this works**: Phase 76.5 enforced the "human always
> accountable" rule — every comment / review / endorsement keeps
> `author_user_id NOT NULL` and adds `author_agent_id` as an
> optional column. The serialiser returns both objects; the
> template renders them side-by-side, never one replacing the
> other.

### 4. Discussion tab deep-link via `?tab=discussion`

Intent: regression-guard for Phase 76.6.4 — the lazy-loader for
the Discussion tab now fires on init activation, not only on
manual `shown.bs.tab` events.

1. `browser_navigate('http://127.0.0.1:8000/data-products/main/sales_gold?tab=discussion')`
   - Assert: page loads with Discussion tab **already active**
     (no manual click required).
2. `browser_wait_for` the comment list to render (the
   "Loading…" placeholder disappears within ~1 s).
   - Assert: existing comments visible; `textarea.pql-comment-new`
     present.
3. `browser_evaluate('() => document.body.querySelectorAll(".pql-comment-card").length')`
   - Assert: count > 0 (the Step-1 cite-token comment is still
     there).

### 5. Threaded reply + `@`-mention notification fan-out

Intent: confirm replies thread under the parent and notify the
parent's author.

1. With Discussion tab open, click the **Reply** button on the
   Step-1 comment.
2. `browser_type` `@admin@pql.test thanks!` into
   `textarea.pql-comment-reply`.
3. Click "Post reply".
   - Assert: reply card appears nested under the parent with
     `data-pql-comment-depth="2"` and the citation rendered as
     a `mailto:` or `/users/<id>` anchor (mentions resolve to
     user profile links).
4. Click the topbar bell badge
   (`div.pql-notif-bell span.pql-notif-bell-badge`).
   - Assert: bell shows ≥ 1, dropdown lists the mention.

### 6. Review with cite-token + agent author

Intent: same render-completeness assertions on the Reviews tab.

1. `browser_click('button[data-pql-tab-key="reviews"]')`
2. Click the 4th star (`i.bi-star[data-star-value="4"]`).
3. Type
   `solid DP — see also #dp:main.customer_360`
   into `textarea.pql-review-body`.
4. Click `button.pql-review-submit`.
   - Assert: `div.pql-review-card` appears with `★★★★☆`, body
     contains the `pql-citation` anchor for the cited DP.
5. Re-post the review via `?as_agent=nightly-bot` (same curl
   pattern as Step 3).
6. Reload.
   - Assert: the review card shows the agent badge
     (`span.pql-review-agent-badge`) next to the human reviewer
     identity.

### 7. Endorsements (server-side only, no UI yet)

Intent: confirm the endorsement serialiser carries
`note_md_resolved` + `agent` even though the DP detail page
currently has no render block for endorsements. This stays
deferred as Phase 77 territory.

1. Curl as admin:

   ```bash
   curl -X POST \
        "http://127.0.0.1:8000/api/data-products/main/sales_gold/endorsements" \
        -H "Cookie: pql_session=<value>" \
        -H "Content-Type: application/json" \
        -d '{
            "endorsement_type": "verified-by-steward",
            "note_md": "ref #dp:main.customer_360"
        }'
   ```

   - Assert: 200; payload carries `note_md_resolved` with the
     anchor, and `agent: null` (because no `?as_agent=`).
2. Re-issue with `?as_agent=nightly-bot`.
   - Assert: `agent: {slug: "nightly-bot", ...}` is present.
3. Browser: no UI surface to verify — the DP detail page has no
   endorsement render block. This is by design until a future
   sprint wires it.

### 8. User profile + follow-user

Intent: walk Phase 76.2 (profiles + user-to-user follows).

1. `browser_navigate('http://127.0.0.1:8000/users/me')`
   - Assert: `h4.pql-profile-display-name`,
     `p.pql-profile-email`,
     `div.pql-profile-counts` (4 stat cells:
     `pql-counts-followers`, `pql-counts-following`,
     `pql-counts-reviews`, `pql-counts-stewarded`).
2. Click `button.pql-profile-edit-btn`.
   - Assert: bio input + location input show
     (`textarea.pql-profile-bio-input`,
     `input.pql-profile-location-input`).
3. Fill bio "playbook replay", save.
   - Assert: `span.pql-profile-bio` reflects the new value;
     the form collapses.
4. Visit another user's profile, e.g.
   `/users/2`.
   - Assert: `button.pql-profile-follow-btn` is enabled; click;
     it flips to `pql-profile-unfollow-btn` and the
     `pql-counts-followers` of the viewed user gains 1 on reload.

### 9. Agent profile

Intent: walk Phase 76.5 agent identity surface.

1. `browser_navigate('http://127.0.0.1:8000/agents/nightly-bot')`
   - Assert: `h3.pql-agent-display-name` with the agent slug
     (or `display_name` if set), `h4.pql-agent-run-count`,
     `p.pql-agent-principal` ("Posts attributed to … via
     principal …"), `ul.pql-agent-comments` listing the agent's
     recent comments / reviews.
2. `browser_evaluate('() => document.body.querySelectorAll(".pql-agent-comments li").length')`
   - Assert: ≥ 1 (Steps 3 + 6 above populated this).

### 10. Topic detail + follow-topic

Intent: walk Phase 76.3 (topics taxonomy + per-topic follows).

1. `browser_navigate('http://127.0.0.1:8000/topics')`
   - Assert: page loads with a list of topics; at minimum
     `finance` exists (the seed creates a small starter set).
2. Click into `finance`.
   - Assert: URL `/topics/finance`,
     `h3.pql-topic-name`, `span.pql-topic-followers` shows a
     count, `ul.pql-topic-dps` lists DPs tagged with this topic.
3. Click `button.pql-topic-follow-btn`.
   - Assert: button flips to `pql-topic-unfollow-btn` and the
     follower count gains 1 on reload.

### 11. `/feed` aggregation

Intent: confirm `/feed` paints comments / reviews / endorsements
from everything the viewer follows.

1. `browser_navigate('http://127.0.0.1:8000/feed')`
   - Assert: `ul.list-group.pql-feed-rows` non-empty (the cite-
     token comment + follow-user + follow-topic from earlier
     steps generated rows).
2. Click a `span.pql-feed-filter[data-kind="comment"]` chip.
   - Assert: rows narrow to comment-kind only; each row carries
     `span.pql-feed-kind` reading `comment`.
3. Type a substring in `input.pql-feed-search`.
   - Assert: rows further narrow client-side.
4. Click the first row's `a.pql-feed-row-link`.
   - Assert: deep-link lands on the relevant DP page on the
     Discussion tab.

### 12. Topbar bell + `/notifications`

Intent: regression-guard for Phase 76.6 (SSE bell).

1. From any social page,
   `browser_evaluate` the bell badge:
   `() => document.querySelector(".pql-notif-bell-badge")?.textContent`.
   - Assert: a number (the Step-5 reply mention fed it).
2. Click `div.pql-notif-bell`.
   - Assert: dropdown shows the unread notifications; clicking
     one navigates to the source comment.
3. `browser_navigate('http://127.0.0.1:8000/notifications')`
   - Assert: full list page renders.
4. Click "Mark all read".
   - Assert: bell badge disappears (page reload not required —
     the SSE channel pushes the zero-count update).

### 13. `/me/settings` digest toggle

Intent: walk Phase 76.4 (notification preferences).

1. `browser_navigate('http://127.0.0.1:8000/me/settings')`
   - Assert: `div.form-check.pql-me-digest-toggle` rendered with
     a checkbox.
2. Toggle the switch.
   - Assert: `PATCH /api/me/settings` fires (visible in
     `browser_network_requests`); response 200.
3. Reload.
   - Assert: the toggle's checked state persists.

### 14. Trending + Candidates

Intent: regression-guard the Phase 72.3 trending page and the
Phase 73.1 candidates page (both inherited the Phase 76.6.4
Alpine x-data quote fix).

1. `browser_navigate('http://127.0.0.1:8000/data-products/trending')`
   - Assert: no JS console errors;
     `table.pql-dp-trending-table` or
     `div.pql-dp-trending-empty` rendered.
2. Switch `select.pql-dp-trending-scope` between
   "Last 7 days" / "Last 30 days" / "All time".
   - Assert: rows update without console errors.
3. `browser_navigate('http://127.0.0.1:8000/data-products/candidates')`
   - Assert: `table.pql-dp-candidates-table` or
     `div.pql-dp-candidates-empty`.
4. Click `button.pql-dp-candidates-generate` (admin-only).
   - Assert: the scan kicks off; an `alert-info` polish row
     `div.pql-dp-candidates-draft-msg` renders ("Scanning
     workspace…" or equivalent).

### 15. Cross-page Alpine x-data sanity

Intent: regression-guard for Phase 76.6.2 + 76.6.4 — the same
Jinja `tojson` outer-quote bug would have broken every Alpine
component on these pages.

1. Visit each of these URLs and assert `browser_console_messages`
   carries zero `Alpine Expression Error`:
   - `/users/me`
   - `/agents/nightly-bot`
   - `/topics/finance`
   - `/me/settings`
   - `/data-products/trending`
   - `/data-products/candidates`
   - `/data-products/main/sales_gold`
2. On each, `browser_evaluate` the root scope is reactive:
   `() => Array.from(document.body.querySelectorAll("[x-data]"))`
   `.filter(el => el._x_dataStack && el._x_dataStack[0]).length`
   - Assert: > 0.

## Anti-goals

- **No public/anonymous social pages.** Every social surface
  requires a logged-in viewer; `/auth/login?next=...` always
  intercepts. Do not assert anonymous access.
- **No endorsement render block on the DP detail page.** The
  server serialiser is wired (`note_md_resolved` + `agent`) but
  the template has no Alpine block to render endorsements yet —
  Phase 77 territory. Step 7 stays a curl-only verification on
  purpose.
- **Mentions are always rendered alongside the human author,
  never instead of it.** If a future template change ever
  collapses the strong-tag, this playbook MUST fail at Step 3
  loudly.
- **No external href ever appears in a `pql-citation` anchor.**
  The regex in `citation_render.js` only matches `\(/[^)]+\)` —
  paths starting with `/`. Adding e.g. an `http://` prefix to
  the substitution would be a security regression.

## Found bugs

The following bugs surfaced in the Phase-76.7 replay session and
all landed in the same close-out push (`f8dbe2e..9bb9b11`):

- **Bug 1** — Alpine `x-data` SyntaxError on
  `data_product.html`. Root cause: Jinja `tojson` escapes `<>&'`
  but not `"`, so a double-quoted outer attribute swallowed the
  inner JSON. Fix: single-quote outer attribute on every
  Alpine root in `data_product.html`. Fixed in
  [`a7383ba`](https://github.com/FloHofstetter/PointlesSQL/commit/a7383ba).
- **Bug 4** — `resolve_citations()` had **zero** live callers;
  `#dp:` / `#topic:` / `#user:` / `#agent:` tokens rendered as
  literal text in every comment / review / endorsement body.
  Fix: parallel `body_md_resolved` / `note_md_resolved` field
  on the serialisers + new
  `frontend/js/citation_render.js` helper + `x-html` bindings.
  Fixed in
  [`b08e35a`](https://github.com/FloHofstetter/PointlesSQL/commit/b08e35a).
- **Bug 5** — `@`-mention picker returned 0 results for any
  query. Root cause: JS read `data.users` but the endpoint
  returns `{q, results: [...]}`. Fix: one-line parse swap.
  Fixed in
  [`ffd44ad`](https://github.com/FloHofstetter/PointlesSQL/commit/ffd44ad).
- **Bug 6** — Discussion tab stuck on "Loading…" forever when
  deep-linked via `?tab=discussion`. Root cause:
  `wireLazyTabs()` only listened to Bootstrap's
  `shown.bs.tab` (fired only on user-initiated switches), so
  `tab_sync.js`-driven init activations never triggered the
  loader. Fix: `maybeTriggerInitialTabLoad()` dispatches the
  right loader once on init based on the active tab's
  `data-pql-tab-key`. Fixed in
  [`a7383ba`](https://github.com/FloHofstetter/PointlesSQL/commit/a7383ba).
- **Bug 7** — Same Alpine quote-fix needed on 6 other social
  pages (`user_profile.html`, `agent_profile.html`,
  `topic_detail.html`, `me_settings.html`,
  `data_products_trending.html`,
  `data_products_candidates.html`). Fix: batch quote-swap.
  Fixed in
  [`54dfc27`](https://github.com/FloHofstetter/PointlesSQL/commit/54dfc27).
- **Bug 12** — Agent author badge missing on every comment /
  reply / review. The API already returned
  `c.agent: {slug, display_name, ...}` but the template
  rendered only the human author. Fix: three new
  `<template x-if="*.agent">` blocks in `data_product.html`,
  each rendering a `bg-info` badge with bot icon + linked
  agent name next to the human strong-tag. Fixed in
  [`b08e35a`](https://github.com/FloHofstetter/PointlesSQL/commit/b08e35a).
- **Bug 14** — Contract + Diff tabs rendered an empty card when
  the cached contract carried no table definitions. Fix:
  empty-state alerts gated on
  `<template x-if="detail && detail.tables.length === 0">`.
  Fixed in
  [`9bb9b11`](https://github.com/FloHofstetter/PointlesSQL/commit/9bb9b11).

Deferred (not blocking):

- **Bug 13** — Endorsements have no frontend render block in
  `data_product.html`. The server-side projection
  (`note_md_resolved` + `agent`) is in place ready for a future
  endorsements-UI surface (Phase 77 candidate). Step 7 above
  remains a curl-only verification until that surface lands.
