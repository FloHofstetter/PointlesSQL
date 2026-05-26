# Alerts walkthrough

> **Mode:** `browser` · **Surface:** /alerts + /alerts/{id}

End-to-end exercise of the alert subscription surfaces:

- [`alerts.html`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/alerts.html)
  — `/alerts` list with the New-alert modal + feed-URLs panel
- [`alert_detail.html`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/alert_detail.html)
  — `/alerts/{slug}` detail with destination CRUD, history,
  and condition / cron editing
- `/alerts/feed.atom` + `/alerts/feed.json` — pull-feed URLs
  bound to a per-user token; subscribe any RSS / Atom / JSON
  Feed reader

Alerts are referenced in `grand-tour.md` Act 9 but had no
dedicated deep-dive playbook Wave 4.

## Preconditions

- Stack up + seed:
  ```bash
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml up -d
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
  ```
  `seed-e2e.py` is enough — alerts only need a saved audit
  query as their data source. The 5 starter saved queries ship with every fresh DB.
- [`auth.md`](auth.md) ran first.
- Playwright MCP Firefox lock-file gotcha: see CLAUDE.md
  line 227-235.

## Walkthrough

1. **Land on the empty alerts page**.
   - Action: `browser_navigate('http://127.0.0.1:8000/alerts')`.
   - Assert: title `Alerts · PointlesSQL`. Heading reads
     "Alerts". Two top-level buttons: "Feed URLs" and "New
     alert". Empty-state placeholder reads "No alerts yet.
     Create your first alert".

2. **Open the New-alert modal**.
   - Action: click "New alert" (or "Create your first alert" —
     same modal).
   - Assert: modal opens with these fields:
     - Title (text)
     - Saved query (dropdown — sourced from
       `GET /api/saved-audit-queries`)
     - Cron expression (5-field, text input)
     - Condition (dropdown: `row_count > / < / = / ≠ threshold`)
     - Threshold (number)
     - Cancel / Create buttons

3. **Create an alert against a starter query**.
   - Action: fill Title = `phase37-test-alert`, pick saved
     query = `unacknowledged-external-writes`, cron = `0 9 * * *`
     (every day at 09:00), condition = `row_count > threshold`,
     threshold = `0`. Click Create.
   - Assert (network): `POST /api/alerts` returns 201 with
     `{slug, name, ...}`. Slug is generated from the title.
     Page reloads via `pqlApi.reloadWithToast`. The list now
     shows one entry.

4. **Drill into the alert detail**.
   - Action: click the alert title in the list.
   - Assert: arrives at `/alerts/{slug}`. Page shows the alert's
     metadata header (saved-query name, cron, condition, last
     fired), a Destinations card, a History card, and an
     Edit / Delete button row.

5. **Add a webhook destination**.
   - Action: from the Destinations card click "Add destination",
     fill URL = `https://httpbin.org/post`, HMAC secret =
     `alert-webhook-secret-must-not-leak`, min severity =
     `warn`. Click Save.
   - Assert (network): `POST /api/alerts/{slug}/destinations`
     returns 201. Page reloads; row appears with `<set>` marker
     for the HMAC column.

6. **Load-bearing redaction assertion**:
   - Action:
     ```js
     () => document.documentElement.outerHTML.includes('alert-webhook-secret-must-not-leak')
     ```
   - Assert: `false`. Same contract as
     [audit-sinks.md](audit-sinks.md) and
     [admin-console.md](admin-console.md) — alert webhook
     secrets are redacted on read.

7. **Open the Feed URLs panel**.
   - Action: click "Feed URLs" button on the list page.
   - Assert: modal shows two URLs:
     - `/alerts/feed.atom?token=<your-feed-token>`
     - `/alerts/feed.json?token=<your-feed-token>`
   - The token is bound to the current user; rotating it via
     `POST /api/me/feed-token/rotate` invalidates all
     previously-shared subscribe URLs.

8. **Subscribe in a feed reader**.
   - Action: copy the Atom URL, open it directly in a new
     browser tab.
   - Assert: Firefox renders an Atom feed preview (or raw XML
     in Chrome — both are valid). The feed includes at minimum
     the alert's title and a `<link>` back to its detail page.
     Empty stack: feed has zero entries until the alert fires
     for the first time.

9. **Trigger the alert manually** (optional — needs a real
   matching row in the saved query).
   - The seed-e2e stack does not seed any external-write rows,
     so `unacknowledged-external-writes` returns 0 → the
     `row_count > 0` condition is false → no fire.
   - To exercise the fire path, switch the alert's saved query
     to one that always returns ≥ 1 row, or seed external
     writes via `seed-full-stack-demo.py --demo-rollback`.

## Playwright MCP script

Condensed browser replay for the alert lifecycle:

1. `browser_navigate('http://127.0.0.1:8000/alerts')`
   — assert the page renders the alerts table.
2. `browser_click("Create alert")`
   — `browser_wait_for(".modal.show")`.
3. `browser_fill_form([{name:"slug", value:"phase37-test-alert"}, {name:"name", value:"Test alert"}])`
   then `browser_click("Save")` — assert table now has a row with
   slug `phase37-test-alert`.
4. `browser_navigate('http://127.0.0.1:8000/alerts/phase37-test-alert')`
   — assert detail page header and tabs render.
5. `browser_click("Destinations")`,
   `browser_click("Add destination")`,
   `browser_fill_form([{name:"url", value:"https://example.com/hook"}, {name:"hmac_secret", value:"s3cr3t"}])`,
   `browser_click("Save")` — assert destination row appears with
   masked HMAC.
6. `browser_evaluate('() => fetch("/alerts/feed.atom").then(r => ({status: r.status, ct: r.headers.get("Content-Type")}))')`
   — assert `status === 200` and content-type is
   `application/atom+xml`.
7. `browser_evaluate('() => fetch("/alerts/feed.json").then(r => r.json())')`
   — assert response has key `items` (array).

## Found bugs

- **BUG-37-04** ✅ Fixed — the htmx 2.0.3 `o.includes("?")`
  null-deref happened on every boost-eligible page that
  htmx synthesised a load-time GET for. Fix was a one-line
  CDN pin bump to htmx 2.0.6, which wraps the call in
  `if (o == null || o === "") o = location.href` before
  the `.includes`. Verified zero errors on `/audit/inbox`,
  `/audit/search`, `/alerts`, `/audit/by-table`, `/dbt`.

## Cleanup

```bash
# Delete the test alert (cascades to destinations + history)
curl -sS -X DELETE http://127.0.0.1:8000/api/alerts/phase37-test-alert -b cookies.txt
```
