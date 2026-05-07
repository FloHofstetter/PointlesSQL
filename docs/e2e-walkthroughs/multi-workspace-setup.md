# Multi-workspace setup walkthrough

> **Mode:** `browser` · **Phase:** 29 · **Surface:** /admin/workspaces CRUD

End-to-end exercise for the Phase-28 workspace surface: create a
second workspace, add a member, switch between them in the UI,
verify isolation, and exercise the cross-workspace lens.

## Preconditions

* PointlesSQL is running on `http://127.0.0.1:8000`.
* You're signed in as a tenant admin (the first-registered user
  bootstraps with `is_admin=True`).
* The seeded `default` workspace (id=1) already exists from the
  Sprint-28.0 bootstrap migration.
* At least one historical agent_run exists so the cockpit has
  something to display (any prior `pql.write_table` /
  `pql.merge` call will have created one).

## Walkthrough

1. **Create a second workspace from the admin UI.**
   - Action: navigate to <http://127.0.0.1:8000/admin/workspaces>.
   - Fill in *Slug* `sandbox-a`, *Name* `Sandbox A`, *Description*
     `Phase-28 walkthrough sandbox`, click **Create workspace**.
   - Assert: page reloads with toast "Workspace created.";
     `sandbox-a` appears in the active-workspaces table with
     `Members = 1` (you, automatically added as admin).

2. **Add a member.**
   - Action: in the same browser tab, the test user
     `nonadmin@test.com` already exists from the standard fixture
     setup.  POST a member via the admin API:
     ```bash
     curl -sS -X POST http://127.0.0.1:8000/api/admin/workspaces/2/members \
       -H 'Content-Type: application/json' \
       -H "X-CSRF-Token: $(curl -s http://127.0.0.1:8000/admin/workspaces \
                            -c /tmp/c -b /tmp/c -o /dev/null \
                            -w '%{header_csrf-token}')" \
       --cookie /tmp/c \
       -d '{"user_email": "nonadmin@test.com", "role": "member"}'
     ```
   - Assert: response carries `"user_email": "nonadmin@test.com"`,
     `"role": "member"`.  In the audit log
     (<http://127.0.0.1:8000/admin/audit>) a new row appears with
     `action=workspace.member_added` and the new user's email in
     the detail JSON.

3. **Pin a primary catalog.**
   - Action: pick any catalog from your soyuz-catalog install,
     e.g. `main`:
     ```bash
     curl -sS -X POST http://127.0.0.1:8000/api/admin/workspaces/2/pins \
       -H 'Content-Type: application/json' \
       --cookie /tmp/c \
       -d '{"catalog_name": "main", "mode": "primary"}'
     ```
   - Assert: response shows `"mode": "primary"`.

4. **Switch to the new workspace via the topbar dropdown.**
   - Action: refresh the home page.  The topbar now shows a
     workspace switcher (folder icon + workspace name) — it was
     hidden before because you only had one workspace.  Click it
     and choose **Sandbox A**.
   - Assert: page reloads.  Look in the page source: the
     `<meta name="workspace-slug">` tag's content is now
     `sandbox-a`; the `<meta name="workspace-primary-catalog">`
     content is `main`.

5. **Verify audit isolation: cockpit shows no historical data.**
   - Action: navigate to <http://127.0.0.1:8000/audit/inbox>.
   - Assert: the inbox is empty (no anomaly cards).  Even if you
     had warn / critical anomalies as workspace=1, the workspace
     filter has scoped them away.

6. **Verify cross-workspace lens: admin sees everything.**
   - Action: with `?workspace=all` (admin-only):
     ```bash
     curl -sS 'http://127.0.0.1:8000/api/audit/summary?workspace=all' \
       --cookie /tmp/c
     ```
   - Assert: response has `"lens_mode": "all"` and the metric
     counts include rows from both workspaces.  Then
     <http://127.0.0.1:8000/admin/audit> shows a fresh row
     `read_kind=audit_api_cross_workspace` recording your
     escalation into the god-eye view.

7. **Cross-workspace data sharing still works.**
   - Action: from any sandbox-A page, run a SQL execute against
     a table in `prod.silver.*` (or whichever catalog is
     reachable to your install).
   - Assert: the query succeeds.  `agent_run_operations` rows
     for this read carry `workspace_id=2` (sandbox-A's audit),
     even though the source table lives outside the workspace.

8. **Switch back to the default workspace.**
   - Action: open the topbar switcher again, choose **Default
     workspace**.
   - Assert: page reloads, audit cockpit shows historical data
     again.  The `pql_workspace` cookie's value flipped back to
     `default`.

9. **Archive the sandbox workspace (optional).**
   - Action: `/admin/workspaces` → click **Archive** on the
     `sandbox-a` row.
   - Assert: confirmation dialog, page reloads, the row moves to
     the *Archived* table at the bottom.  The switcher dropdown
     no longer offers it; the audit log carries a
     `workspace.archived` entry.

10. **Negative test: non-admin cannot lift the workspace filter.**
    - Action: sign out, sign back in as `nonadmin@test.com`
      (password `password123` from the fixture).  Curl with that
      session:
      ```bash
      curl -sS 'http://127.0.0.1:8000/api/audit/summary?workspace=all' \
        --cookie /tmp/nonadmin
      ```
    - Assert: HTTP 403 with detail `"?workspace=all requires admin"`.

## Playwright MCP script

Condensed browser replay (curl member-add stays as a shell call
above):

1. `browser_navigate('http://127.0.0.1:8000/admin/workspaces')`
   — assert table renders the seeded `default` workspace.
2. `browser_fill_form([{name: "slug", value: "sandbox-a"}, {name: "name", value: "Sandbox A"}])`
   — fill out the create form.
3. `browser_click("Create workspace")`
   — `browser_wait_for("Workspace created.")` (toast); assert
   `sandbox-a` appears in the table with `Members = 1`.
4. **(curl member-add via shell, then)**
   `browser_navigate('http://127.0.0.1:8000/admin/audit')`
   — assert the latest row's `action` column reads
   `workspace.member_added`.
5. `browser_click(".workspace-switcher")` (topbar dropdown)
   — assert it lists both `default` and `Sandbox A`.
6. `browser_click("Sandbox A")`
   — assert URL becomes `/?workspace=2` (or equivalent
   workspace-scoped redirect); the topbar pill shows
   `Sandbox A`.
7. `browser_navigate('http://127.0.0.1:8000/runs')`
   — assert no rows visible (the existing runs belong to the
   `default` workspace; isolation guarantee).
8. `browser_click(".workspace-switcher")`,
   `browser_click("default")`
   — assert URL becomes `/?workspace=1`; runs reappear.
9. `browser_navigate('http://127.0.0.1:8000/admin/workspaces')`,
   `browser_click("Sandbox A")` (row link)
   — assert detail page shows the pinned `main` catalog with
   `mode = primary`.

## Cleanup

```bash
# Soft-archive the sandbox so it doesn't bleed into other tests.
# (Step 9 above already did this if you ran it.)
curl -sS -X POST http://127.0.0.1:8000/api/admin/workspaces/2/archive \
  --cookie /tmp/c
```

The seeded `default` workspace cannot be archived — the API
returns 422 if you try.

## See also

* [Workspaces concept](../concepts/workspaces.md)
* [ADR-0008 — workspace soft isolation](../decisions/0008-workspace-soft-isolation.md)
* [Admin runbook](../admin/workspace-management.md)
