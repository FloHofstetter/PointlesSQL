# Visual DP Canvas Builder — block-and-wire authoring

> **Mode:** `live` · **Surface:** standalone Rete-style editor at `/dp/{id}/canvas`

Replays the path a domain engineer takes when authoring a data
product visually instead of via a notebook or raw SQL: drop input,
filter, output blocks; wire pins; save; run the graph; observe
the resulting Delta materialise through the registered output port.

## Setup

1. Start PointlesSQL + soyuz-catalog (default ports):

   ```bash
   uv run soyuz-catalog          # terminal 1
   uv run pointlessql            # terminal 2
   ```

2. Seed two UC tables to read from. The canvas needs the source
   tables to already exist in UC; the target table is auto-created
   on first materialise.

   ```bash
   mkdir -p /tmp/canvas-walk/{src_orders,src_customers}

   uv run python <<'PY'
   import pandas as pd, deltalake
   deltalake.write_deltalake(
       "/tmp/canvas-walk/src_orders",
       pd.DataFrame({
           "order_id":    [1, 2, 3, 4],
           "customer_id": [10, 20, 10, 30],
           "amount":      [9.99, 19.99, 29.99, 4.99],
       }),
       mode="overwrite",
   )
   deltalake.write_deltalake(
       "/tmp/canvas-walk/src_customers",
       pd.DataFrame({
           "customer_id": [10, 20, 30],
           "tier":        ["gold", "silver", "bronze"],
       }),
       mode="overwrite",
   )
   PY

   curl -X POST "http://127.0.0.1:8080/api/2.1/unity-catalog/tables" \
        -H "Content-Type: application/json" \
        -d '{
          "name":"orders","catalog_name":"main","schema_name":"canvas_walk",
          "table_type":"MANAGED","data_source_format":"DELTA",
          "storage_location":"/tmp/canvas-walk/src_orders",
          "columns":[
            {"name":"order_id","type_name":"INT","type_text":"BIGINT","nullable":false},
            {"name":"customer_id","type_name":"INT","type_text":"BIGINT","nullable":false},
            {"name":"amount","type_name":"DOUBLE","type_text":"DOUBLE","nullable":true}
          ]
        }'

   curl -X POST "http://127.0.0.1:8080/api/2.1/unity-catalog/tables" \
        -H "Content-Type: application/json" \
        -d '{
          "name":"customers","catalog_name":"main","schema_name":"canvas_walk",
          "table_type":"MANAGED","data_source_format":"DELTA",
          "storage_location":"/tmp/canvas-walk/src_customers",
          "columns":[
            {"name":"customer_id","type_name":"INT","type_text":"BIGINT","nullable":false},
            {"name":"tier","type_name":"STRING","type_text":"VARCHAR","nullable":true}
          ]
        }'
   ```

3. Seed an empty data product to hang the canvas off
   (`/tmp/canvas-walk/pointlessql.yaml`):

   ```yaml
   data_product:
     name: Canvas Walk
     version: "1.0.0"
     description: Canvas builder walkthrough fixture.
     catalog: main
     schema: canvas_walk
     steward_email: test@test.com
     sla_minutes: 60
     tables:
       - name: orders
         primary_key: [order_id]
         columns:
           - {name: order_id,    type: long,   nullable: false}
           - {name: customer_id, type: long,   nullable: false}
           - {name: amount,      type: double, nullable: true}
   ```

   Reload the yaml:

   ```bash
   curl -X POST http://127.0.0.1:8000/api/data-products/reload \
        --cookie "<admin-session>"
   ```

   Note the returned `data_product_id` (or look it up from the
   `/api/data-products` listing); the editor URL uses it.

## Browser flow

| Step | Expect |
|---|---|
| Open `/data-products/main/canvas_walk` | DP detail page with eleven tabs. Last tab labelled "Canvas" |
| Click **Canvas** tab | Card showing "No canvas saved yet — open the editor to create one." + "Open editor" button |
| Click **Open editor** | Full-screen editor renders. Topbar with Save + Run buttons, left palette with three groups (Sources / Transforms / Sinks), centre canvas empty, right drawer showing the overview |
| Drag **Input port** from the palette onto the canvas | Block appears. Selecting it shows a single `UC table` text field in the right drawer |
| Set the table to `main.canvas_walk.orders` | Within 1.5 s, the topbar shows "Saving…" → "Saved · v1". Within ~1 s after that, the status bar shows `no errors` and the block body summarises the FQN |
| Drag **Filter** onto the canvas, wire `Input.out → Filter.in` | Connection appears as a blue line |
| Select the Filter block and set predicate `amount > 5` | Auto-save fires; no errors |
| Drag **Output port**, wire `Filter.out → OutputPort.in` | Three-block chain |
| Set OutputPort `port_name=primary`, `materialized_table=main.canvas_walk.tgt_filtered`, `mode=overwrite` | Save state updates, error count stays 0 |
| Click **Run ▶** in the topbar | Modal opens with target FQN, mode, and "SQL preview is rendered server-side on Run" placeholder. Confirm |
| The modal flips to the success banner | "Materialized 3 rows → main.canvas_walk.tgt_filtered (graph vN)" |
| Close the modal, navigate to the DP detail page → **Lineage** tab | The target table appears as a downstream node fed by the source |
| Reload the editor page | The full graph reloads from version N; positions, configs, and edges are preserved |

## Agent flow

```python
import httpx

# Bearer-auth as any user with steward/admin rights on the DP.
client = httpx.Client(base_url="http://127.0.0.1:8000",
                     headers={"Authorization": "Bearer <api-key>"})

dp_id = 1  # from /api/data-products listing

# Load the latest canvas document.
print(client.get(f"/api/dp/{dp_id}/canvas").json())

# Save a new graph version.
doc = {
    "schema_version": 1,
    "nodes": [
        {"id": "inp", "block_type": "InputPort",
         "config": {"table_fqn": "main.canvas_walk.orders"}},
        {"id": "out", "block_type": "OutputPort",
         "config": {"port_name": "primary",
                    "materialized_table": "main.canvas_walk.tgt_all",
                    "mode": "overwrite"}},
    ],
    "edges": [
        {"id": "e", "source_node_id": "inp", "source_pin": "out",
         "target_node_id": "out", "target_pin": "in"},
    ],
}
r = client.post(f"/api/dp/{dp_id}/canvas", json={"document": doc})
print(r.json())  # {"version": N, "created_at": "..."}

# Validate without writing.
v = client.post(f"/api/dp/{dp_id}/canvas/validate", json={"document": doc})
print(v.json())  # {"pin_schemas": {...}, "errors": []}

# Materialise.
m = client.post(f"/api/dp/{dp_id}/canvas/materialize", json={"document": doc})
print(m.json())  # {"rows_written": 4, "target_fqn": "...", ...}
```

## Live preview + CodeMirror predicates (Wave C)

Once a `Filter` block is selected and configured, click the new
**Preview** button in the right drawer to run the upstream slice
through DuckDB and inspect the first 100 rows. The button is
disabled for the `OutputPort` block (use **Run** for that path)
and whenever the topbar shows validation errors.

| Step | Expect |
|---|---|
| Select the **Filter** block | The predicate field renders as a CodeMirror editor (single-line, SQL grammar) instead of a plain textarea |
| Type `am` then press <kbd>Ctrl-Space</kbd> | Autocomplete pop-up offers `amount` (and any other upstream column) sourced from the cached pin-schema |
| Click **Preview** in the right drawer | Modal opens, shows columns + rows queried from `main.canvas_walk.orders`, filtered by the current predicate |
| Change the **Rows** input to 2 and press **Refresh** | Modal re-fires; only 2 rows + a "Showing first 2 rows" badge appear; the truncation flag drives that badge |
| Add an **SQL** block, wire `Filter.out → SQL.in`, type `SELECT customer_id, SUM(amount) AS total FROM {{in}} GROUP BY customer_id` | The downstream block accepts the inferred schema; if you wire a Project block after it, `customer_id` + `total` are offered in the autocomplete (proves the SQL block runs DuckDB `DESCRIBE`) |
| Select the **SQL** block and click **Preview** | Modal returns the aggregated rows; "Compiled SQL" `<details>` shows the rendered `WITH … SELECT *` text wrapped in `LIMIT N` |

The preview path is **read-only**: no Delta write, no UC mutation,
no canvas-graph version bump. It is the fastest way to debug a
predicate or an SQL expression before clicking Run.

## Compound blocks + editable mesh canvas (Wave D)

Once two data products exist in the workspace, a downstream DP can
reference an upstream's materialised table via the new **DataProduct
◫** compound block. The standalone mesh-level editor at
`/mesh/canvas` exposes the same wiring at the workspace scale:
each node is one DP, each wire is one declared
`upstream_product` input-port row.

| Step | Expect |
|---|---|
| In the leaf DP's canvas (`/dp/{leaf}/canvas`), drop **Data product ◫** from the Sources rail | Block appears with the DP-picker config form in the right drawer |
| Pick an upstream DP from the dropdown, then a port | The block's body summarises `<materialized_table>`; auto-save persists the resolved FQN |
| Double-click the DP◫ node on the canvas | Browser navigates to the upstream DP's canvas; topbar gains a "◀◀ `<previous-DP>`" breadcrumb |
| Click the breadcrumb button | Browser returns to the original canvas; the trail entry is popped |
| Navigate to `/mesh/canvas` | All workspace DPs render as Drawflow nodes; existing `upstream_product` bindings render as wires |
| Drag from one DP's output pin to another DP's input pin | New wire renders; status bar shows the in-memory diff (added: 1) |
| Click **Save** | Modal-less banner; "Last diff: added 1, removed 0"; the actual `DataProductInputPort` row is created via the existing CRUD service |
| Remove an existing wire and click **Save** | Diff reports `removed: 1`; the corresponding `DataProductInputPort` row is deleted |
| Click **Validate** (auto-runs on every change) | Self-loops + duplicate wires surface in the right rail without touching the DB |

The mesh canvas treats DP nodes as **read-only**: deleting a DP
itself stays on the catalog surface. Wires represent declared
upstream bindings only; no Delta data is moved on save.

## Expanded block library (Wave E)

The transforms rail of the palette now carries 16 blocks instead of
the original 6. The 10 new entries fall into four groups:

- **Window** — adds a windowed aggregation column over a
  PARTITION/ORDER spec; pick the function from a dropdown
  (`ROW_NUMBER`, `LAG`, etc.) and supply args / partition / order
  as comma-separated column lists.
- **Pivot + Unpivot** — DuckDB's PIVOT statement (with an
  aggregate picker) and its inverse UNPIVOT (configure which
  columns collapse into NAME/VALUE rows).
- **Union + Distinct + Sort + Sample** — Union takes two upstream
  inputs (left + right) and emits a `type_mismatch` error when
  the column lists differ; Distinct optionally keys on a subset;
  Sort takes a JSON list of column-or-`{column, direction}`
  entries; Sample picks N percent or N rows.
- **Cast + Rename + CalcColumn** — Cast accepts a JSON list of
  `{column, target_type}` (target_type validated against the
  DuckDB allowlist); Rename a `{old: new}` map; CalcColumn uses
  the same CodeMirror DuckDB-grammar editor as the Filter block
  for the expression input.

Wire a graph that mixes a few of these blocks together, click
**Preview** on any non-`OutputPort` node, and Wave-C's per-node
preview path now runs through the new compiler entries unchanged.

## DP-as-Code round-trip + version diff (Wave F)

Canvases are now git-trackable end-to-end. Export the DP YAML and
the saved canvas comes along as a `pipeline:` sub-tree; apply that
same YAML back in and the canvas restores with the same node ids,
configs, edges, and (cosmetic) positions.

| Step | Expect |
|---|---|
| `POST /api/data-products/{cat}/{schema}/export` for a DP with a saved canvas | Response YAML / dict carries a `pipeline: {version: 1, nodes: [...], edges: [...]}` sub-tree |
| Edit a config in the exported YAML, `POST /api/data-products/apply` with the changes | Apply succeeds; response includes `canvas_version` and a new row in `data_product_canvas_graph` appears |
| Open `/dp/{id}/canvas` for that DP | Editor loads the freshly-applied canvas; node ids and configs match the YAML |
| Open `/dp/{id}/canvas/diff?from=N&to=M` between two versions | Three columns render — added, removed, modified — with per-node JSON side-by-side for modified nodes; position-only changes are intentionally ignored |
| Diff between identical versions | "No structural changes" alert renders |

## Found bugs

_None yet — populate after the first replay pass uncovers any._
