# Computational Policy-as-Code walkthrough

> **Mode:** `agent` · **Surface:** four `pql_*` policy-module tools

End-to-end replay of a Family-A agent authoring, dry-running,
linking, and inspecting Cedar policy modules through the
`hermes-plugin-pointlessql` tool surface — the agent-flow
complement to the browser walkthrough
[admin-policy-modules.md](admin-policy-modules.md).

Cedar modules layer ABAC permit/forbid rules on top of the static
product⇐workspace policy fields.  This playbook exercises the four
tools shipped to close the deferred plugin scope:

* `pql_create_policy_module` — author a module.
* `pql_test_policy_module` — dry-run before linking.
* `pql_link_policy_module_to_product` — attach to one product.
* `pql_list_policy_decisions` — read the per-module ledger.

The fifth tool, `pql_list_policy_modules`, was shipped in the
first Surface-Welle batch (commit `0af50d0` in
`hermes-plugin-pointlessql`).

## Prerequisites

- A running PointlesSQL with the API key reaching the admin
  surface (the four tools are admin-gated except the link route,
  which is steward-or-admin).
- A `hermes-agent` session loaded with the
  `hermes-plugin-pointlessql` plugin (`uv pip install -e
  ~/git/hermes-plugin-pointlessql`).
- A data product registered at `main.silver` (or substitute your
  own catalog/schema below).
- An admin principal — the API-key principal must carry
  `is_admin=True`.

## Steps

### 1. List existing modules (sanity check)

Drive `pql_list_policy_modules` with empty args.  Verify the
envelope is `{ok: true, data: {modules: [...]}}`.  On a fresh
workspace the list is empty; an existing workspace returns the
prior modules.

### 2. Create a forbid-on-write module

Drive `pql_create_policy_module` with:

```json
{
  "name": "block_write_main_silver",
  "cedar_source": "forbid(principal, action == Action::\"write\", resource);",
  "enabled": true
}
```

Verify the response is `{ok: true, data: {module: {id, name:
"block_write_main_silver", version: 1, enabled: true, ...}}}`.
Remember the `module.id` — every later step references it.

### 3. Dry-run the module

Drive `pql_test_policy_module` with the id from step 2 and the
intended request shape:

```json
{
  "module_id": <id>,
  "principal": "User::\"alice\"",
  "action": "Action::\"write\"",
  "resource": "DataProduct::\"main.silver\""
}
```

Verify `data.decision.effect == "forbid"` and
`data.decision.latency_ms` is set.  Re-run with `action`
flipped to `Action::"read"` — verify the effect flips to
`permit` (Cedar's default-allow semantic when no rule matches
the read action).

### 4. Link the module to the product

Drive `pql_link_policy_module_to_product`:

```json
{
  "catalog": "main",
  "schema": "silver",
  "module_ids": [<id>]
}
```

Verify `data.linked_module_ids` is `[<id>]`.  The link is now
live on the next `pql.read_table` / `pql.write_table` call
against `main.silver`.

### 5. Trigger a write to surface the forbid

From the same agent session (or any PQL caller bound to the
linked product), invoke `pql_write_table` against
`main.silver.events`.  The call returns an error envelope:

```json
{
  "ok": false,
  "error": "http 403",
  "code": "permission_denied",
  "detail": "Cedar policy denied write on main.silver.events (cedar_fail_closed)"
}
```

The fail-closed reason text disambiguates: a forbid here means
the policy explicitly denied; a `cedar_parse_error` or
`cedar_runtime_error` reason would mean Cedar itself failed
closed.

### 6. Inspect the decision log

Drive `pql_list_policy_decisions`:

```json
{ "module_id": <id>, "limit": 10 }
```

Verify the newest row carries `effect == "forbid"`,
`action == "write"`, `resource_id == "main.silver"`, and a
non-zero `latency_ms`.  The dry-run from step 3 does **not**
appear in this list — only the hook-driven evaluations at
`pql.write_table` time persist a decision row.

### 7. Tear down (optional)

Unlink with an empty list:

```json
{ "catalog": "main", "schema": "silver", "module_ids": [] }
```

Then drop the module via the admin route or
`/admin/policy-modules` UI; the plugin does not expose a
delete tool by design (deletes go through the browser surface).

## Found bugs

* **Admin policy-modules surface at `/admin/policy-modules` would
  never render any module, decision, or dry-run verdict**
  (2026-05-31 replay). Three sites in the Alpine factory read
  `res.json?.modules / decision / decisions`, but
  `window.pqlApi.fetch` puts the parsed body under `res.data`.
  Switched to `res.data?.…` for all three reads, recreated a
  module via the UI, and verified the dry-run modal correctly
  returned `permit`. Fixed at source in
  [frontend/js/pages/admin_policy_modules.js](../../frontend/js/pages/admin_policy_modules.js).
