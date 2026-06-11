# Delta Sharing walkthrough

> **Mode:** `browser` · **Surface:** /admin/sharing + /shared-with-me + /api/sharing

End-to-end exercise of both sharing directions: the provider cockpit
(create a share, add a table, mint a recipient and capture its
one-time token) and the consumer browser (register the local install
as its own remote provider with that token — loopback federation —
then browse share → tables → 50-row preview over the open protocol).

## Preconditions

- E2E stack up with seeded Delta tables:
  ```bash
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml up -d
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
  ```
- [`auth.md`](auth.md) ran first (admin@pql.test exists and is
  signed in). Part A needs the admin; Part B works for any
  signed-in user.
- Playwright MCP Firefox (`--browser firefox`); see
  [admin-console.md](admin-console.md) for the stale-profile-lock
  recovery note.

## Walkthrough

### Part A — Provider cockpit (6 steps)

1. **Land on the cockpit through the admin grid**.
   - Action: `browser_navigate('http://127.0.0.1:8000/admin')`,
     click the card with `data-admin-card="sharing"`.
   - Assert: lands on `/admin/sharing`; title
     `Delta Sharing · PointlesSQL`, heading "Delta Sharing",
     breadcrumb Home → Admin → Delta Sharing, counter reads
     "0 shares · 0 recipients" on a fresh stack.

2. **Create a share**.
   - Action: in the Shares card fill Name = `e2e-share`,
     Comment = `E2E walkthrough share`; click "Create share".
   - Assert: the table lists `e2e-share` with 0 objects.

3. **Add a table to the share**.
   - Action: click "Manage" on the `e2e-share` row; in the
     drawer's Objects row enter the three-part FQN of a seeded
     table (e.g. `main.default.numbers`), leave shared-as empty,
     click "Add table".
   - Assert: the object list shows the FQN; the row's Objects
     count flips to 1. Entering a two-part name first shows the
     "must be three-part" inline error and fires no request.

4. **Create a recipient — one-time token modal** (load-bearing).
   - Action: in the Recipients card fill Name = `e2e-recipient`,
     click "Create recipient".
   - Assert: the token modal opens (`.modal.d-block`) with the
     warning "Copy this token now. It is shown exactly once…";
     the readonly input's `.value` property holds the plaintext
     bearer token. Click "Copy" (label flips to "Copied"), store
     the value, then "I have copied the token".
   - Assert (write-only invariant): `GET /api/sharing/recipients`
     returns `e2e-recipient` with **no** `token` field — the
     plaintext never appears in any later management response.

5. **Grant the share to the recipient**.
   - Action: back in the `e2e-share` drawer's Grants row, type
     `e2e-recipient`, click "Grant".
   - Assert: success toast "Granted "e2e-share" to
     e2e-recipient."; `/admin/audit` shows a `share.granted`
     entry. The drawer notes that grants don't list on this
     surface — the audit log is the review path.

6. **Rotate the token**.
   - Action: click "Rotate token" on the `e2e-recipient` row,
     accept the confirm dialog.
   - Assert: the same one-time modal opens with a *new* token
     (different from step 4's); the old token stops authenticating
     on the protocol surface. Copy the new value for Part B.

### Part B — Consumer browser (5 steps)

7. **Land on the consumer page**.
   - Action: `browser_navigate('http://127.0.0.1:8000/shared-with-me')`.
   - Assert: heading "Shared with me", provider counter "0
     providers", registration form with Name / Endpoint URL /
     Token / Comment; the token input is `type="password"`.

8. **Register the loopback provider**.
   - Action: fill Name = `self`, Endpoint URL =
     `http://soyuz-catalog:8080/delta-sharing` (the compose-network
     address of the local soyuz protocol prefix; from the host use
     `http://127.0.0.1:8080/delta-sharing`), Token = the value
     copied in step 6; click "Register".
   - Assert: the provider row appears with the endpoint; the
     token never renders anywhere
     (`document.documentElement.outerHTML.includes(token) === false`).

9. **Browse shares**.
   - Action: click "Browse" on the `self` row.
   - Assert: the browsing card opens; the Shares pane lists
     `e2e-share` (only granted shares are visible to the token).

10. **Drill into tables**.
    - Action: click `e2e-share`.
    - Assert: the Tables pane lists `default.numbers` (the
      protocol's schema.table coordinates for the object added in
      step 3).

11. **Preview rows**.
    - Action: click the table.
    - Assert: the Preview pane renders a striped table with the
      seeded columns and rows, capped at 50; the note "preview
      truncated to the first 50 rows" appears only when the table
      has more than 50 rows. `/admin/audit` gains a
      `sharing_provider.read` entry.

### Part C — Cleanup (2 steps)

12. **Delete the provider profile**.
    - Action: on `/shared-with-me` click "Delete" on the `self`
      row, accept the confirm.
    - Assert: the list returns to the empty state.

13. **Delete share + recipient**.
    - Action: on `/admin/sharing` delete `e2e-share` and
      `e2e-recipient` (confirm dialogs note that objects/grants
      cascade).
    - Assert: both tables show their empty states; console stays
      free of errors for the whole walkthrough.

## Cleanup

```bash
# In case rows survived the UI pass:
curl -sS -X DELETE http://127.0.0.1:8000/api/sharing/providers/self -b cookies.txt
curl -sS -X DELETE http://127.0.0.1:8000/api/sharing/shares/e2e-share -b cookies.txt
curl -sS -X DELETE http://127.0.0.1:8000/api/sharing/recipients/e2e-recipient -b cookies.txt
```
