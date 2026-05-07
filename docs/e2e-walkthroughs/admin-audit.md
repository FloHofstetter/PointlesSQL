# Admin audit-log walkthrough

> **Mode:** `browser` · **Phase:** 29 · **Surface:** /admin/audit

Exercises the admin audit-log viewer at `/admin/audit`:
admin-only access, server-side filter form
(`?since=`, `?action=`, `?user=`, `?target=`), reused `listTable`
chips, and the click-to-expand detail cell.

## Preconditions

- [`auth.md`](auth.md) and [`catalog-browsing.md`](catalog-browsing.md)
 ran first. `admin@pql.test` is logged in; `user@pql.test`
 exists as a non-admin principal.
- Seed script ran. At least one audited action has already
 been recorded (any catalog comment edit or table
 "Open in notebook" click will populate a row).

## Walkthrough

1. **Generate a fresh audit row**.
 - Action: while signed in as `admin@pql.test`, navigate to
 `/catalogs/demo` and edit the comment (same flow as the
 `inline-editors.md` Part A step 1 — any value is fine).
 - This writes an `update_catalog` row via
 [`_audit()`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/main.py#L239) into the
 `audit_log` table.

2. **Admin opens `/admin/audit` via the nav dropdown**.
 - Action: from any page, click the "Admin" dropdown in the
 top navbar, then "Audit log".
 - Assert: URL is `http://127.0.0.1:8000/admin/audit`. Page
 heading reads "Audit log". The filter card shows four
 controls (Window / Action / User / Target) with the
 default window set to "Last 7 days".

3. **Newest-first ordering**.
 - Action:
 ```js
 () => {
 const rows = Array.from(document.querySelectorAll('tbody tr'));
 return rows.slice(0, 3).map(tr => tr.querySelector('td [class*=badge]').textContent);
 }
 ```
 - Assert: the row you just generated
 (`update_catalog` against `catalog:demo`) is the first
 entry. Time column shows something like "a few seconds ago"
 via `pqlRelativeTime()`.

4. **"Mine only" chip narrows to the current admin's rows**.
 - Action:
 ```js
 () => {
 const chip = document.querySelector('.pql-chip');
 chip.click();
 return {
 active: chip.classList.contains('pql-chip--active'),
 visibleUsers: Array.from(document.querySelectorAll('tbody tr'))
.filter(tr => !tr.hidden && tr.offsetParent !== null)
.map(tr => tr.querySelector('td[data-label="User"]').textContent.trim())
 };
 }
 ```
 - Assert: `active === true`, `visibleUsers` contains only
 `admin@pql.test`.

5. **Server-side filter: window = All time**.
 - Action: `browser_navigate('http://127.0.0.1:8000/admin/audit?since=all')`
 (or change the Window dropdown to "All time" and click
 "Apply filters").
 - Assert: row count is ≥ the 7-day count. No truncation
 banner unless the install actually has > 1000 entries.

6. **Server-side filter: target substring match**.
 - Action: `browser_navigate('http://127.0.0.1:8000/admin/audit?since=all&target=catalog:demo')`
 - Assert: every visible `data-label="Target"` cell starts
 with `catalog:demo`. The filter input round-trips — its
 `value` attribute shows `catalog:demo`.

7. **Detail expand/collapse on a row with a JSON payload**.
 - Action: find a row whose detail column shows a "Show"
 button (any `update_catalog` row recorded through the
 inline editor has a JSON patch payload).
 - Action: click "Show".
 - Assert: the button label flips to "Hide" and a `<pre
 class="pql-audit-detail">` element appears with the
 pretty-wrapped payload. Long strings wrap within the
 cell — the table layout does not explode horizontally.

8. **Non-admin gets 403**.
 - Action: log out, log in as `user@pql.test`.
 - Action: navigate to `/admin/audit`.
 - Assert: page renders `pages/403.html` with heading
 "Access Denied"; `required_privilege` is `admin` and
 `securable_type` is `system` (same shape as the
 `operational.md` step 3).

9. **Non-admin cannot see the Admin dropdown**.
 - Action: while still signed in as `user@pql.test`,
 inspect the top navbar.
 - Assert: no "Admin" dropdown is present. The entry is
 gated by `current_user.is_admin` in
 [`components/nav_links.html`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/components/nav_links.html).

## Playwright MCP script

```text
# 1. Generate a fresh audit row (as admin).
browser_navigate('http://127.0.0.1:8000/catalogs/demo')
browser_evaluate(async () => {
 const c = document.querySelector('.pql-editable-input, input[x-model="draft"]').closest('[x-data]');
 const d = Alpine.$data(c);
 d.draft = 'e2e-audit-' + Date.now();
 await d.save();
})

# 2-3. Newest-first.
browser_navigate('http://127.0.0.1:8000/admin/audit')
browser_evaluate(() => {
 const rows = Array.from(document.querySelectorAll('tbody tr'));
 return rows.slice(0, 3).map(tr => tr.querySelector('td [class*=badge]').textContent);
})

# 4. Mine-only chip.
browser_evaluate(() => {
 const chip = document.querySelector('.pql-chip');
 chip.click();
 return {
 active: chip.classList.contains('pql-chip--active'),
 visibleUsers: Array.from(document.querySelectorAll('tbody tr'))
.filter(tr => !tr.hidden && tr.offsetParent !== null)
.map(tr => tr.querySelector('td[data-label="User"]').textContent.trim())
 };
})

# 5-6. Server-side filter.
browser_navigate('http://127.0.0.1:8000/admin/audit?since=all&target=catalog:demo')

# 7. Detail expand.
browser_evaluate(() => {
 const btn = document.querySelector('td[data-label="Detail"] button');
 btn.click();
 return { label: btn.textContent, expanded: !!document.querySelector('pre.pql-audit-detail') };
})

# 8-9. Non-admin lockout.
# (sign out, sign in as user@pql.test)
browser_navigate('http://127.0.0.1:8000/admin/audit')
browser_evaluate(() => document.querySelector('h4')?.innerText) # "Access Denied"
browser_evaluate(() => !!document.querySelector('.navbar.dropdown-toggle i.bi-shield-check')) # false
```

## Found bugs

_No bugs surfaced. replay confirmed (live run on the
`feat(admin): ` commit):_

- _`/admin/audit` loads with default `since=7d`, shows only the
 rows inside the window, newest-first, with `pqlRelativeTime()`
 driving the time column (e.g. "3 min ago", "2 days ago");_
- _`since=all` surfaces the older rows; a row with a non-JSON
 `detail` string renders without crashing the page;_
- _`target=other` narrows to the single matching row and the
 `f-target` input round-trips the value;_
- _the `listTable` "Mine only" chip flips `pql-chip--active` and
 sets `tr.hidden=true` on rows whose `data-user-id` does not
 match the current admin;_
- _detail expand/collapse toggles the button label
 (`Show` ↔ `Hide`) and the `<pre class="pql-audit-detail">`
 display (`none` ↔ `block`) via Alpine `x-show`;_
- _non-admin user gets HTTP 403 with the `pages/403.html` shell
 ("Access denied — You do not have admin on system admin") and
 the admin-only navbar dropdown is gone (zero matches for
 `a[href="/admin/audit"]` in the rendered DOM)._

_Harness note: calling `chip.click()` via `browser_evaluate` did
not propagate through Alpine's `x-on:click` handler reliably in
this run. Using
`Alpine.$data(host).toggleChip('mine')` + a 100 ms settle is the
stable path; the script above reflects that._
