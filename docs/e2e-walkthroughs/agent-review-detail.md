# Agent-review detail walkthrough

> **Mode:** `browser` · **Phase:** 19 · **Surface:** `/agent-reviews/{review_id}`

Covers the per-review detail page surfaced by Phase 19's
Audit-Reviewer-Agent: a markdown summary card, an optional raw
replay-payload card (tool-call transcript), a metadata sidebar,
and a dispatcher fan-out card listing every webhook destination
the review was delivered to with its HTTP status. The
list-of-reviews lives on the audit cockpit; this page is the
deep-dive for one row.

## Preconditions

- Stack up via `docker/docker-compose.yml` + `docker/docker-compose.e2e.yml`.
- [`auth.md`](auth.md) ran first — `admin@pql.test` is signed in.
- At least one review row exists in `agent_reviews`. The
  cleanest seed is to run
  [`audit-reviewer-daily.md`](audit-reviewer-daily.md) once
  (Hermes-cron path), which posts a fresh review via
  `POST /api/agent-reviews`; the response carries the
  `review_id` you'll need.
  Alternatively, post a synthetic review:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/agent-reviews \
       -H 'Content-Type: application/json' \
       -H "Cookie: <admin-session>" \
       -d '{
         "summary_md": "## Daily review\n\n- 3 critical\n- 7 warn",
         "severity": "critical",
         "period_start": "2026-05-06T00:00:00",
         "period_end":   "2026-05-07T00:00:00",
         "payload_json": {"audit_count": 42}
       }'
  ```
- Optional: ≥1 row in `review_destinations` so the dispatcher
  fan-out card has content. Configure via
  `/admin/review-destinations` — see
  [`admin-console.md`](admin-console.md).
- Browser: `--browser firefox` per CLAUDE.md.

## Walkthrough

1. **Land on the detail page from the cockpit.**
   - Action: `browser_navigate('http://127.0.0.1:8000/audit/queries')`
     (the cockpit landing).
   - Action: click the latest review's `View` link (or use the
     `review_id` from the seed step).
   - Assert: URL becomes `/agent-reviews/<id>`.
   - Assert: page title ends with `Audit review #<id> · PointlesSQL`.

2. **Header carries severity badge.**
   - Assert: `<h1>` reads `Audit review #<id>`.
   - Assert: a Bootstrap badge sits next to it; class is
     `bg-danger` for `critical`, `bg-warning text-dark` for
     `warn`, `bg-success` for everything else.
   - Assert: the right-side text-muted span shows the period
     window in ISO form, e.g.
     `2026-05-06T00:00:00Z → 2026-05-07T00:00:00Z`.

3. **Markdown summary card renders rendered HTML, not raw bytes.**
   - Assert: the left column has a card with header
     `Markdown summary`.
   - Assert: the body element carries class `markdown-body` and
     contains rendered HTML (`<h2>`, `<ul>`, `<li>`, etc.) — not
     the raw `## Daily review` source.
   - Assert: `browser_evaluate('() => document.querySelector(".markdown-body").innerText')`
     contains the heading text from the seed.

4. **Replay-payload card appears only when `payload_json` is non-null.**
   - Assert: a second card titled `Replay payload` is present
     when the seed posted a `payload_json`.
   - Assert: the body is a `<pre>` with `white-space: pre-wrap`;
     contents match the JSON dump (indented).
   - Setup variant: post a review without `payload_json`; reload.
   - Assert: the Replay-payload card is absent.

5. **Metadata sidebar lists four rows.**
   - Assert: the right-column Metadata card has a
     `list-group-flush` with `Created`, `Run ID`,
     `Severity`, `Window`.
   - Assert: when `run_id` is non-null, the cell renders an
     anchor to `/runs/<run_id>` showing the first 8 hex chars
     followed by `…`.
   - Assert: when `run_id` is null, the cell shows a muted `—`.

6. **Dispatcher fan-out card — populated path.**
   - Setup: at least one configured `review_destinations` row +
     one delivery attempt (the dispatcher fires on
     `POST /api/agent-reviews`).
   - Assert: the Dispatcher fan-out card header has a Bootstrap
     badge with the count of `delivered_to` entries.
   - Assert: each `<li>` shows the destination name, an
     HTTP-status badge (`bg-success` for 200, `bg-danger` for
     anything else), the URL hash (truncated, with `title=` for
     full hash), and the delivery timestamp (ISO + `Z`).

7. **Dispatcher fan-out card — empty path.**
   - Setup: no `review_destinations` rows.
   - Assert: the card body reads `No webhook destinations
     configured at the time of dispatch.`; mentions
     `/admin/review-destinations` in a `<code>` span.

8. **404 for non-existent review.**
   - Action: `browser_navigate('http://127.0.0.1:8000/agent-reviews/999999')`.
   - Assert: HTTP status is 404; the page renders the standard
     404 template.

9. **403 for non-admin user.**
   - Action: log out, log in as `user@pql.test`, navigate to the
     same `/agent-reviews/<id>`.
   - Assert: HTTP status is 403; the page renders the standard
     403 template (the route is admin/auditor-gated).

10. **JSON shape parity — `/api/agent-reviews/{id}` matches the UI.**
    - Action: `browser_evaluate('() => fetch("/api/agent-reviews/<id>").then(r => r.json())')`.
    - Assert: keys `id`, `severity`, `summary_md`,
      `payload_json`, `period_start`, `period_end`, `run_id`,
      `delivered_to`, `created_at`.
    - Assert: `delivered_to` is an array of objects each
      carrying `name`, `status_code`, `url_hash`,
      `delivered_at`.

## Playwright MCP script

```text
1. browser_navigate /audit/queries
2. browser_click <latest review View link>
3. browser_wait_for ".markdown-body"
4. browser_evaluate ".badge:nth-child(3)" -> "critical|warn|success"
5. browser_navigate /agent-reviews/999999  -> 404
6. <logout, login as user@pql.test>
7. browser_navigate /agent-reviews/<id>    -> 403
```

## Found bugs

_None recorded yet — first replay is part of the Phase 41
Playwright-coverage pass._
