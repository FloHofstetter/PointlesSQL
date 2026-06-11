# Admin secrets walkthrough

> **Mode:** `browser` · **Surface:** /admin/secrets + /api/secrets

End-to-end exercise of the secret-scopes cockpit: create a scope,
store a write-only value, verify the value never appears in any
management response, grant a READ ACL, and clean up. The JSON
surface under `/api/secrets` is the same one non-admin users and
connector runtimes script against; the cockpit is just admin
chrome over it.

## Preconditions

- E2E stack up:
  ```bash
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml up -d
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
  ```
- [`auth.md`](auth.md) ran first (admin@pql.test exists and is
  signed in).
- Playwright MCP Firefox (`--browser firefox`); see
  [admin-console.md](admin-console.md) for the stale-profile-lock
  recovery note.

## Walkthrough

### Part A — Scope lifecycle (4 steps)

1. **Land on the cockpit**.
   - Action: `browser_navigate('http://127.0.0.1:8000/admin/secrets')`.
   - Assert: title `Secrets · PointlesSQL`, heading "Secrets",
     breadcrumb Home → Admin → Secrets, counter reads
     "0 scopes" on a fresh stack, and the intro paragraph shows the
     literal `{{secrets/<scope>/<key>}}` reference syntax.

2. **Create a scope**.
   - Action: click "New scope"; in the modal type name
     `e2e-warehouse`, description `E2E walkthrough scope`; click
     "Create scope".
   - Assert: page reloads with toast "Secret scope created."; the
     table now lists `e2e-warehouse` with 0 keys and the admin's
     e-mail under "Created by".

3. **Reject a malformed name**.
   - Action: open "New scope" again, type name `has space`, click
     "Create scope".
   - Assert: the modal's red alert shows the `1-128 characters from
     [A-Za-z0-9_.-]` validation message; no scope is created (close
     the modal).

4. **Open the manage drawer**.
   - Action: click "Manage" on the `e2e-warehouse` row.
   - Assert: drawer expands with a "Secrets" section ("No secrets
     yet.") and an "Access" section showing exactly one grant:
     the admin principal with badge `MANAGE` (creator grant).

### Part B — Write-only values (3 steps)

5. **Put a secret**.
   - Action: in the drawer's Secrets row, key `db-password`,
     value `hunter2-e2e`; click "Put".
   - Assert: the list shows `db-password` with the admin e-mail;
     the value input field is of type `password`.

6. **Verify the management API never returns the value**
   (load-bearing — the write-only invariant).
   - Action:
     ```js
     async () => {
       const r = await fetch('/api/secrets/scopes/e2e-warehouse/secrets',
                             {headers: {'Accept': 'application/json'}});
       return await r.text();
     }
     ```
   - Assert: the response body contains `"db-password"` but
     neither `hunter2-e2e` nor any `value`/`encrypted_value`
     field.

7. **Verify the audited runtime getter decrypts**.
   - Action: same pattern against
     `/api/secrets/scopes/e2e-warehouse/secrets/db-password/value`.
   - Assert: JSON `{"scope": "e2e-warehouse", "key": "db-password",
     "value": "hunter2-e2e"}`. Then open `/admin/audit` and assert
     the newest rows include `secret.accessed` on target
     `secret_scope:e2e-warehouse` (plus the earlier
     `secret_scope.created` / `secret.put`).

### Part C — ACLs + cleanup (3 steps)

8. **Grant READ to a second principal**.
   - Action: back on `/admin/secrets`, drawer open, Access row:
     principal `member@pql.test`, permission `READ`, click "Grant".
   - Assert: the grants list shows `member@pql.test` with badge
     `READ` next to the admin's `MANAGE`.

9. **Revoke the grant**.
   - Action: click "Revoke" on the `member@pql.test` row.
   - Assert: the row disappears; the admin `MANAGE` row remains.

10. **Delete the scope**.
    - Action: click "Delete" on the row, accept the confirm
      dialog.
    - Assert: reload with toast "Secret scope deleted."; the table
      shows the empty state again. Console stays free of errors
      for the whole walkthrough.
