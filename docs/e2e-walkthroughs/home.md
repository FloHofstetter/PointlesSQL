# Home dashboard walkthrough

> **Mode:** `browser` · **Surface:** / landing + sparkline + recent-cards

Covers the home page: welcome header, 7-day success-rate
sparkline, latest-runs table, Recent catalogs card driven by
`localStorage["pql.recentCatalogs"]`, Your-dashboards card, Quick
actions (including the admin-only foreign-catalog modal), and the
empty-state onboarding checklist. Also verifies the
`/api/home/summary` error-resilience contract: a soyuz outage must
downgrade to `catalogs.unavailable=true` rather than 502'ing the
whole page.

## Preconditions

- Stack up via `docker/docker-compose.yml` + `docker/docker-compose.e2e.yml`.
- Run [`auth.md`](auth.md) once so `admin@pql.test` and
 `user@pql.test` exist.
- Run [`jobs-dag.md`](jobs-dag.md) so there is at least one job
 owned by `admin@pql.test` with a handful of runs (required for
 the sparkline and latest-runs assertions).
- Run [`dashboards.md`](dashboards.md) so at least one Dashboard
 exists — it drives the Your-dashboards card.
- Browser: launch with `--browser firefox` per
 [CLAUDE.md](https://github.com/FloHofstetter/PointlesSQL/blob/main/CLAUDE.md).

## Walkthrough

1. **Home dashboard renders for an admin user.**
 - Action: log in as `admin@pql.test`; the post-login redirect
 lands on `/`.
 - Assert: `<h1>` text matches `Welcome, …` (the trailing fragment
 is the admin's display name or email).
 - Assert: no onboarding card is present (seed data from the two
 playbooks above guarantees every `have_*` flag is true).

2. **Quick actions card shows per-user counters.**
 - Assert: the Quick actions card exposes four action buttons —
 `Open notebook`, `View jobs`, `View dashboards`, and the
 admin-only `Create foreign catalog`.
 - Assert: the counter grid displays three values (`Catalogs`,
 `Jobs`, `Dashboards`) all ≥ 1.

3. **Sparkline renders seven `<rect>` bars with meta.**
 - Action: `browser_evaluate(function='() => document.querySelectorAll(".pql-sparkline rect").length')`.
 - Assert: returns `7`.
 - Assert: the meta `<dl>` shows three rows (`Total terminal runs`,
 `Succeeded`, `Overall rate`); `Overall rate` is not `—` (at
 least one succeeded run exists from `jobs-dag.md`).

4. **Latest job runs table lists the 10 most recent runs.**
 - Assert: the Latest job runs card lists at most 10 rows.
 - Assert: each row has a status dot element
 (`.pql-status-dot.pql-status-dot--<status>`) and a
 relative-time cell whose text ends in `ago` or the ISO date
 (for older runs).
 - Assert: clicking a row's job-name anchor navigates to
 `/jobs/{job_id}`.

5. **Recent catalogs card is empty on first visit.**
 - Action: `browser_evaluate(function='() => JSON.parse(localStorage.getItem("pql.recentCatalogs") || "null")')`.
 - Assert: returns `null` or an empty array.
 - Assert: the Recent catalogs card renders the italic empty-state
 copy ("Browse a catalog from the sidebar to see it here.").

6. **Visiting a catalog promotes it into Recent catalogs.**
 - Action: click into a catalog from the sidebar (or
 `browser_navigate('http://127.0.0.1:8000/catalogs/demo')`).
 - Action: `browser_navigate('http://127.0.0.1:8000/')`.
 - Assert: `browser_evaluate('() => JSON.parse(localStorage.getItem("pql.recentCatalogs"))[0].name')`
 returns `"demo"`.
 - Assert: the Recent catalogs card now shows one `<li>` with a
 monospace link to `/catalogs/demo`.

7. **Drilling into a schema still promotes the parent catalog.**
 - Action: navigate to `/catalogs/demo/schemas/<any>` then back
 to `/`.
 - Assert: `pql.recentCatalogs[0].name` is still `"demo"` (the
 schema-page visit did not displace it).
 - Assert: visiting a second catalog (e.g.
 `/catalogs/pg_foreign`) then reloading `/` pushes the new name
 to the top; the list now has two entries.

8. **Your dashboards card lists the admin's dashboards.**
 - Assert: the Your dashboards card shows at least one `<li>`
 whose anchor points at `/dashboards/{slug}`.
 - Assert: the card footer renders `All (N) ›` with N equal to
 the total dashboard count (including those owned by other
 users).

9. **Admin-only: Create foreign catalog modal opens from Quick actions.**
 - Action: click the `Create foreign catalog` button.
 - Assert: the Bootstrap modal `#createForeignCatalogModal` becomes
 visible; the `<select>` contains at least one connection.
 - Action: press `Escape` or click the close icon.
 - Assert: the modal is dismissed; no network request fired.

10. **Onboarding checklist triggers only when the *system* is empty.**
 The trigger is `not have_catalogs AND not have_jobs AND not
 have_dashboards AND not catalogs.unavailable`, where
 `have_catalogs = catalogs.count > 0` is a system-level truth —
 registering a new non-admin user against a populated stack does
 NOT show onboarding, because catalogs exist.
 - Setup: empty compose stack (`docker compose down -v` between
 sessions; no seed script run). Register the first user — they
 become admin via the bootstrap path, `catalogs.count == 0`
 while soyuz is still reachable, no jobs, no dashboards.
 - Action: log in as that admin; navigate to `/`.
 - Assert: the onboarding card is visible with three numbered
 steps (`Create a catalog`, `Schedule a notebook job`,
 `Publish a dashboard`).
 - Assert: the admin Create-foreign-catalog button is rendered
 inside step 1's body; non-admin would see the "ask an admin"
 fallback in its place.
 - Assert: cards 3–7 (sparkline, quick actions, latest runs,
 recent catalogs, your dashboards) are NOT present on the page.

11. **`/api/home/summary` JSON shape is stable.**
 - Action: `browser_evaluate('() => fetch("/api/home/summary").then(r => r.json())')`
 (or the equivalent `browser_network_requests` inspection on
 a plain page load).
 - Assert: the returned object has top-level keys
 `user`, `catalogs`, `jobs`, `dashboards`, `latest_runs`,
 `sparkline`, `onboarding`.
 - Assert: `sparkline.days` is an array of length 7; each
 element has keys `date`, `total`, `succeeded`, `rate`.
 - Assert: `onboarding.show === false` for the admin user.

12. **Soyuz-down pass — home still renders at 200.**
 - Action: `docker compose stop soyuz-catalog` (or the
 equivalent compose command in your harness).
 - Action: reload `/` as `admin@pql.test`.
 - Assert: HTTP status is 200 (via
 `browser_network_requests()` on the document request).
 - Assert: the red `Failed to reach Unity Catalog: …` banner is
 rendered at the top of the page.
 - Assert: the Quick actions counter for `Catalogs` reads `0`;
 the Latest runs and Your dashboards cards still render
 (local DB only).
 - Assert: onboarding does NOT show for the existing seeded
 admin — the `unavailable` flag suppresses it even though
 `have_catalogs` is false.
 - Cleanup: `docker compose start soyuz-catalog`.

## Found bugs

- **BUG-32-01** (fixed same-sprint): the sparkline SVG rendered
 zero bars because Alpine's `<template x-for="(d, i) in days">`
 inside `<svg>` fails — `<template>.content` is an HTML-namespaced
 DocumentFragment, so the inner `<rect>` elements get parsed as
 unknown HTML and never bind. Fixed by computing `bar_height`,
 `bar_class`, and `bar_title` server-side in
 `_build_home_summary` and rendering the seven `<rect>`s via a
 plain Jinja `{% for %}` loop. The `homeSparkline()` Alpine
 factory survives only for the meta counters.
- **BUG-32-02** (fixed same-sprint): the two-column CSS Grid used
 `align-items: stretch` (the default), which dehned the Job
 activity card and the Quick actions card to the same height as
 whichever neighbour was tallest. With `grid-row: 2 / span 2` on
 the Latest runs card in the left column, the Job activity card
 acquired a dead lower half. Fixed by switching to two flex
 columns (`.pql-home-col--primary` / `--secondary`) so each card
 hugs its natural height; reordered the source so the primary
 column holds Sparkline + Runs and the secondary holds Quick
 actions + Recent catalogs + Your dashboards.
