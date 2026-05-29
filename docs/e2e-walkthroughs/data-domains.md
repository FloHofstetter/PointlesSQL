# Data Domains — owning teams for data products

> **Mode:** `hybrid` · **Surface:** `/admin/domains` CRUD + `/domains` browse + `/domains/{slug}` detail + product Overview domain panel

A **domain** is the owning team for a set of data products. Each
domain carries an *archetype* (source-aligned, aggregate, or
consumer-aligned) and owner / developer members; products are
assigned to a domain from the product's Overview tab. This playbook
exercises the full domain lifecycle: admin-create, browse, detail,
and the per-product assignment panel.

## Preconditions

1. `auth.md` has run — log in as the admin (`replay@pointlessql.local`
   in the local harness, or any first-registered → auto-admin user).
2. `scripts/seed-e2e.py` has created the `demo` catalog + `sales` / `hr`
   schemas.
3. `scripts/seed-mesh-demo.py` has created the two data products
   `demo.sales` (upstream) and `demo.hr` (downstream) — the assignment
   step needs at least one product to attach a domain to.

   ```bash
   uv run python scripts/seed-e2e.py
   uv run python scripts/seed-mesh-demo.py
   ```

## Walkthrough

1. **Admin CRUD — create a domain.**
   - Action: `browser_navigate('http://127.0.0.1:8000/admin/domains')`.
   - Assert: the page heading "Domains", a "New domain" button, and an
     "Active domains" table.
   - Action: click "New domain"; in the modal fill Slug `analytics`,
     Name `Analytics`, Archetype `Consumer-aligned`, an optional
     description; click "Create domain" (disabled until slug + name
     are set).
   - Assert: `POST /api/admin/domains` → 200; the table gains an
     `analytics` row with archetype `consumer-aligned`.

2. **Members popover.**
   - Action: on the new row click "Members".
   - Assert: the owners/developers editor renders without console error
     (`GET /api/admin/domains/{id}/members` → 200).

3. **Browse page.**
   - Action: `browser_navigate('http://127.0.0.1:8000/domains')`.
   - Assert: archetype filter chips (All / Source / Aggregate /
     Consumer); a card for **Analytics** (consumer-aligned, owner shown,
     "0 products") linking to `/domains/analytics`.

4. **Detail page.**
   - Action: `browser_navigate('http://127.0.0.1:8000/domains/analytics')`.
   - Assert: heading "Analytics", the `consumer-aligned` chip, OWNERS
     listing the admin, "No developers assigned.", and "No products
     assigned to this domain yet."

5. **Assign a product (Overview domain panel).**
   - Action: `browser_navigate('http://127.0.0.1:8000/data-products/demo/sales?tab=overview')`.
   - In the **Domain** panel, select `Analytics (consumer-aligned)` in
     the "Owning domain" dropdown and click "Save domain".
   - Assert: `PATCH /api/data-products/demo/sales/domain` → 200; the
     panel header now reads "Analytics consumer-aligned".

## Playwright MCP notes

- The product-detail page drives its tabs from a `?tab=` query param.
  Navigate to `…?tab=overview` (or click the Overview tab button) before
  asserting on the Domain panel — a bare product URL may leave a
  different pane active.
- Alpine `<select>` bindings (`x-model`) only update on a real `change`
  event. When setting a select value via `browser_evaluate`, dispatch
  both `input` and `change` before clicking the save button.

## Anti-goals

- No domain-level RBAC ladder — workspace membership + scopes
  (admin / supervisor / auditor) gate everything. A domain is an
  ownership label, not an access boundary.
- The browse + detail pages are read-only; all mutation lives under
  `/admin/domains` (admin) or the per-product Overview panel
  (steward / admin).
