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

## Found bugs

_None yet — populate after the first replay pass uncovers any._
