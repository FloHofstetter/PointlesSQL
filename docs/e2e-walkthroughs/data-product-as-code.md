# Data-Product-as-Code walkthrough

> **Mode:** `agent` · **Surface:** three `pql_*` DP-as-Code tools

End-to-end replay of a Family-A agent reconciling a YAML
`DataProductSpec` into the catalog — plan, apply, export, and
round-trip — through the `hermes-plugin-pointlessql` tool
surface.  Browser-pendant: the `/admin/data-product-apply` page
that ships the same flow with a YAML editor + diff view.

Data-Product-as-Code converts the imperative create/update CRUD
routes into a single declarative spec the team can keep next to
their code.  This playbook exercises the three tools that wrap
the surface:

* `pql_data_product_plan` — compute the additions / modifications
  / removals without writing (dry-run).
* `pql_data_product_apply` — execute the plan; idempotent on
  re-run.
* `pql_data_product_export` — snapshot a live product back into
  spec form.

## Prerequisites

- A running PointlesSQL with the API key reaching the admin
  surface (or steward on the target product for the apply step).
- A `hermes-agent` session loaded with the
  `hermes-plugin-pointlessql` plugin (`uv pip install -e
  ~/git/hermes-plugin-pointlessql`).
- A workspace where the agent may create / update one data
  product at `main.silver` (or substitute your own
  catalog / schema below).

## Steps

### 1. Author a minimal spec

Hold the following spec string in agent memory:

```yaml
name: orders_silver
catalog: main
schema: silver
owner_email: alice@example.com
domains:
  - sales
output_ports:
  - port_name: orders
    table_name: orders
    description: Curated orders feed
input_ports:
  - port_name: raw_orders
    source_catalog: raw
    source_schema: bronze
    source_table: orders
slos:
  - port_name: orders
    kind: freshness
    target: "24h"
```

### 2. Dry-run the plan

Drive `pql_data_product_plan` with:

```json
{ "spec_yaml": "<...the YAML above as a JSON-encoded string...>" }
```

Verify `{ok: true, data: {plan: {ops: [...]}}}`.  In a workspace
that does not have an `orders_silver` product, the plan returns
one `product / add` op plus one op per output port / input port /
slo, all with `action: "add"`.  No DB row is written — this is
purely a preview.

### 3. Apply the plan

Drive `pql_data_product_apply` with the same `spec_yaml`.  Verify
the envelope:

```json
{
  "ok": true,
  "data": {
    "plan": { "ops": [ ... ] },
    "outcome": {
      "dry_run": false,
      "applied": <n>,
      "errors": []
    }
  }
}
```

The product, output port, input port, and SLO rows are now in
the catalog.  `outcome.errors` is empty on success; partial
failures land here without rolling back the prior ops (the
re-run is the recovery story).

### 4. Re-apply (idempotent)

Drive `pql_data_product_apply` again with the same `spec_yaml`.
Verify `outcome.applied == 0` and `plan.ops` is empty — the
applier saw no diff against the catalog state.

### 5. Export the product back to spec form

Drive `pql_data_product_export` with:

```json
{ "catalog": "main", "schema": "silver" }
```

Verify `data.spec_yaml` contains a YAML block that re-encodes
the live state.  The exported spec is a superset of the input
(it may include DB-assigned defaults like `slo.unit` resolution
or empty optional sub-lists).

### 6. Round-trip — plan against the exported spec

Take the YAML string from step 5 and drive
`pql_data_product_plan` against it.  Verify `plan.ops == []` —
the export is faithful enough that re-planning is a no-op.  This
is the round-trip guarantee that makes "store the spec in git"
safe.

### 7. Modify and re-apply

Edit the in-memory spec (e.g. add a second output port or
change a SLO target) and drive `pql_data_product_apply` again.
The plan now contains exactly one op (the diff), and the apply
writes only that op.  Re-export and re-plan to confirm the
new state is round-trip-clean.

### 8. Tear down (optional)

Removing a product through the spec surface is intentionally
not exposed — destructive ops route through the matching
browser surface or the per-resource DELETE endpoints.  Re-apply
an empty spec without `output_ports` / `input_ports` to clear
those rows only; the product row itself stays.

## Found bugs

(none at time of writing — fill in during the first live replay)
