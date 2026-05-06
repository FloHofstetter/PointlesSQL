# Audit-stream sinks walkthrough

Exercises the admin Audit-sinks UI at `/admin/audit-sinks`: create
a webhook sink with HMAC secret, verify secret redaction in the
rendered HTML, fire a synthetic test envelope, toggle the sink
on/off, and delete it. Phase 33.2 added the browser surface; this
playbook drives it end-to-end and asserts the no-secret-in-DOM
contract that admin pages share with `/admin/api-keys` and
`/admin/review-destinations`.

## Preconditions

- E2E stack up:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d
  docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
  ```
- [`auth.md`](auth.md) ran first (admin@pql.test exists, logged in).
- Playwright MCP Firefox: if launch fails with `process did exit:
  exitCode=0` immediately after `<launched>`, check
  `~/.cache/ms-playwright/mcp-firefox-*/lock` (a symlink whose
  target encodes the owning PID). If `ps -p <pid>` shows no row,
  `rm` the symlink and retry. Use the bundled Playwright Firefox
  (`--browser firefox`), not the system Firefox channel — see
  CLAUDE.md line 227-235.

## Walkthrough

1. **Land on the empty sinks page**.
   - Action: `browser_navigate('http://127.0.0.1:8000/admin/audit-sinks')`.
   - Assert: page title `Audit sinks · PointlesSQL`. Heading reads
     "Audit sinks". Counter top-right: `0 sinks`. The "Existing
     sinks" card shows the empty placeholder
     `No audit sinks configured. Add one below to start
     forwarding governance events.` Below it is the "Create sink"
     card with three default-visible fields (Name, Type, Event
     types) plus the type-conditional webhook block (URL + HMAC
     secret).

2. **Create a webhook sink with HMAC secret**.
   - Action: `browser_fill_form` filling
     - Name = `phase37-webhook`
     - Event types = `pointlessql.audit_sink.test`
     - URL = `https://httpbin.org/post`
     - HMAC secret = `hunter2-hmac-do-not-leak`
   - Action: click "Create sink".
   - Assert (network): `POST /api/admin/audit-sinks` returns 200
     and the response body's `config.hmac_secret` equals
     `<redacted>` (server-side redaction happens at API write).
   - Assert (page): the page reloads via `pqlApi.reloadWithToast`
     and the "Existing sinks" card now shows one row with
     `phase37-webhook | webhook | url: https://httpbin.org/post |
     hmac_secret: <set>`. The Active toggle is checked.

3. **Load-bearing redaction assertion** — the cleartext HMAC
   secret MUST NOT appear anywhere in the rendered DOM.
   - Action:
     ```js
     () => {
       const html = document.documentElement.outerHTML;
       return {
         secretLeaked: html.includes('hunter2-hmac-do-not-leak'),
         redactedMarkers: (html.match(/&lt;set&gt;|<set>/g) || []).length,
       };
     }
     ```
   - Assert: `secretLeaked === false`,
     `redactedMarkers >= 1`. The `<set>` marker tells admins a
     secret is configured without leaking the value. This
     assertion is shared with `admin-api-keys.md`,
     `admin-review-destinations.md`, and `admin-system-info.md`
     (when those playbooks land — Wave 1) — every page that
     displays redacted secrets gets the same regex check.

4. **Fire a synthetic test envelope**.
   - Action: click the per-row "Test" button.
   - Assert (network): `POST /api/admin/audit-sinks/1/test`
     returns `200 {ok: true}`. The dispatcher fires a CloudEvent
     of `type=pointlessql.audit_sink.test` at the configured URL.
     Httpbin echoes back; the `ok` flag in the response confirms
     a 2xx from the upstream sink.
   - Note: test envelopes are NOT persisted to the
     `governance_events` table (see
     [pointlessql/api/audit_sinks_routes.py:411](../../pointlessql/api/audit_sinks_routes.py#L411))
     because they bypass the standard dispatch path. So
     `GET /api/admin/audit-sinks/recent-events` stays empty until
     a real governance event fires (audit export, external-write
     detection, cost-gate denial, etc.).

5. **Toggle the sink off, then on**.
   - Action: click the Active toggle in the row's Active column.
   - Assert (network): `PATCH /api/admin/audit-sinks/1` returns
     200 with `is_active: false` echoed in the response. UI
     toggle visibly flips off.
   - Action: click the toggle again.
   - Assert: `PATCH` returns 200 with `is_active: true`. Toggle
     flips back on.
   - Why: inactive sinks are skipped by the dispatcher
     (`outcome=no_destination` on each fan-out attempt) but the
     row stays so admins can re-enable without retyping config.

6. **Delete the sink** (cleanup).
   - Action: click the trash icon. Browser `confirm()` dialog
     prompts `Delete sink "phase37-webhook"?`. Accept.
   - Assert (network): `DELETE /api/admin/audit-sinks/1` returns
     200 with `{deleted: 1, name: "phase37-webhook"}`.
   - Assert (page): `pqlApi.reloadWithToast` triggers; on reload
     the "Existing sinks" card shows the empty placeholder
     again. Counter back to `0 sinks`.
   - Why: historical fan-out lines on
     `governance_events.delivered_to_json` survive deletion
     because the sink's id + name are stamped on each entry.

## Optional: trigger a real governance event

The test envelope in step 4 is synthetic. To exercise the full
sink → dispatcher → `governance_events` audit trail, fire an
actual governance event in a second sink that does NOT filter on
`pointlessql.audit_sink.test`:

1. Recreate the sink without the `event_types` filter (leave the
   Event types field empty in step 2's form).
2. Trigger an audit export:
   ```bash
   curl -sS -b cookies.txt \
     'http://127.0.0.1:8000/admin/audit/export?fmt=json&since=24h' \
     -o /tmp/audit.json
   ```
3. `GET /api/admin/audit-sinks/recent-events` now returns one row
   with `event_type=pointlessql.audit_export.issued`,
   `outcome=delivered`. The same row appears in the
   `governance_events` table.

## Optional: S3 / CloudTrail sinks

The webhook flow above stresses every UI control. S3 and
aws_cloudtrail sinks reuse the same row UI; only the type-
conditional form block differs. To exercise them, pick the type
from the Type dropdown in step 2 and supply real credentials.
The redaction assertion in step 3 also covers `secret_access_key`
and `session_token` — the `_redact_config` helper in
`audit_sinks_routes.py` shares one set of sensitive keys across
all three sink types.

## Found bugs

- **BUG-37-01** — Phase 37 Wave 0a, fixed in [a744b52](https://github.com/FloHofstetter/PointlesSQL/commit/a744b52).
  Each existing-sink row's `x-data` attribute interpolated
  `{{ s.name|tojson }}` (a double-quoted JSON string) inside a
  double-quoted HTML attribute, breaking the attribute parser:
  ```
  x-data="auditSinkRow(1, "phase37-webhook", true)"
                            ^ premature close
  ```
  Alpine then threw `SyntaxError: expected expression, got '}'`
  + `ReferenceError: isActive is not defined` and the row's
  toggle / Test / Delete buttons were dead. Fix: switch the
  `x-data` attribute's outer quotes from `"` to `'` so JSON
  double-quotes pass through unescaped. Same fix landed for the
  three sibling admin pages that had the identical pattern:
  - `admin_review_destinations.html`
  - `admin_workspaces.html`
  - `admin_api_keys.html`
  None of these had been live-browser-tested before — pytest
  asserted the rendered HTML contained the right tokens but
  never executed the page's Alpine layer.

- **BUG-37-02** — admin sidebar (the icon-rail context-panel on
  every `/admin/*` page) lists only "Audit log", "Audit cockpit",
  and "External writes" but is missing entries for "Audit sinks",
  "Review destinations", "API keys", "Workspaces", and "System
  info" — yet those pages exist and this playbook exercises one
  of them. Filed for the Wave 1 `admin-console.md` walkthrough to
  surface a fix in
  [pointlessql/api/dependencies.py](../../pointlessql/api/dependencies.py)
  or the relevant context-panel partial; do not block Wave 0a.
