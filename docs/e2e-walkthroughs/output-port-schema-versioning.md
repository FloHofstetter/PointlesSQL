# Output-port schema versioning walkthrough

> **Mode:** `agent` · **Surface:** three `pql_*` schema-versioning tools

End-to-end replay of a Family-A agent inspecting and advancing
the MAJOR.MINOR.PATCH version of an output-port schema, then
attempting a write that the breaking-change-policy enforcer
rejects.  The browser-pendant lives on the data-product detail
page (output port → version history list, diff viewer, propose-
bump form).

Schema versioning lets downstream consumers pin a contract.
Breaking changes (column removal, type narrowing, NOT-NULL
tightening) trigger MAJOR bumps; additive changes (new nullable
column) trigger MINOR; description-only edits trigger PATCH.  A
`breaking_change_policy` of `block` causes the before_write
hook to refuse writes that diverge from the registered head.

This playbook exercises the three tools shipped to close the
deferred plugin scope:

* `pql_get_schema_version_history` — read the per-port history.
* `pql_propose_schema_bump` — register a new version and surface
  the diff.
* `pql_compute_schema_diff` — diff any two registered versions.

## Prerequisites

- A running PointlesSQL with the API key reaching a steward or
  admin principal for the target product.
- A `hermes-agent` session loaded with the
  `hermes-plugin-pointlessql` plugin.
- A data product registered at `main.silver` with at least one
  output port (the agent reads `port_id` via
  `pql_get_data_product_discovery`).

## Steps

### 1. Resolve the output-port id

Drive `pql_get_data_product_discovery` for `main.silver`.  In
the response envelope, locate the `output_ports` list and pick
one entry — its `id` is the `port_id` argument below.  Keep
this in agent memory.

### 2. List the schema-version history

Drive `pql_get_schema_version_history` with:

```json
{ "catalog": "main", "schema": "silver", "port_id": <id> }
```

Verify `{ok: true, data: {versions: [...]}}`.  On a fresh port
the list contains exactly one entry, `version_semver: "0.1.0"`,
`change_kind: "patch"` (the seed row created by the bootstrap).
Each row carries `schema_json`, `bumped_at`, `change_summary`,
and the bumping user.

### 3. Propose a backwards-compatible (MINOR) bump

Drive `pql_propose_schema_bump` with a schema that **adds** a
nullable column to the prior shape:

```json
{
  "catalog": "main",
  "schema": "silver",
  "port_id": <id>,
  "new_schema": {
    "columns": [
      {"name": "order_id", "type": "string", "nullable": false,
       "description": "Order PK"},
      {"name": "amount", "type": "decimal(10,2)", "nullable": false,
       "description": "Order total"},
      {"name": "refund_reason", "type": "string", "nullable": true,
       "description": "Set when an order is refunded"}
    ]
  },
  "change_summary": "Add nullable refund_reason for tracking"
}
```

Verify `data.version.change_kind == "minor"` and
`data.version.version_semver == "0.2.0"`.  The diff envelope
lists exactly one entry in `columns_added`.

### 4. Propose a breaking (MAJOR) bump

Drive `pql_propose_schema_bump` again with a schema that
**removes** a previously-existing column:

```json
{
  "catalog": "main",
  "schema": "silver",
  "port_id": <id>,
  "new_schema": {
    "columns": [
      {"name": "order_id", "type": "string", "nullable": false},
      {"name": "amount", "type": "decimal(10,2)", "nullable": false}
    ]
  },
  "change_summary": "Drop refund_reason — never populated downstream"
}
```

Verify `data.version.change_kind == "major"` and
`data.version.version_semver == "1.0.0"` (major-bump resets
minor + patch).  The diff lists `refund_reason` in
`columns_removed`.

### 5. Diff two specific versions

Drive `pql_compute_schema_diff` with:

```json
{
  "catalog": "main",
  "schema": "silver",
  "port_id": <id>,
  "from_version": "0.2.0",
  "to_version": "1.0.0"
}
```

Verify the response shape `{from_version, to_version, diff}`
with `diff.change_kind == "major"`.  The from / to fields are
optional — omit `from_version` to diff against the empty prior;
omit `to_version` to diff against the current head.

### 6. Trigger a before_write block (optional)

If the workspace governance carries `breaking_change_policy:
block` (set via the workspace governance form), the agent's
next `pql_write_table` attempt against the port's table with a
schema that does not match the registered head triggers a 403
envelope with code `permission_denied` and
`detail: schema breaking change blocked (...)`.  This closes
the loop — the policy is enforced at write time, not just at
declaration time.

### 7. PATCH bump for a description-only edit

Drive `pql_propose_schema_bump` again with the same column
shape but an updated description on one column:

```json
{
  "catalog": "main",
  "schema": "silver",
  "port_id": <id>,
  "new_schema": {
    "columns": [
      {"name": "order_id", "type": "string", "nullable": false,
       "description": "Order PK (UUID v7 since 2026-04)"},
      {"name": "amount", "type": "decimal(10,2)", "nullable": false}
    ]
  },
  "change_summary": "Document UUID v7 convention"
}
```

Verify `data.version.change_kind == "patch"` and
`data.version.version_semver == "1.0.1"`.

### 8. Tear down (optional)

Schema history rows are immutable by design — there is no
delete tool.  To roll back, propose a bump that reproduces the
target prior shape; the diff will surface as a fresh major or
minor entry rather than an in-place rewrite.

## Found bugs

(none at time of writing — fill in during the first live replay)
