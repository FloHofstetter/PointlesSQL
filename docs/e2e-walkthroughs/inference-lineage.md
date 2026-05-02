# E2E walkthrough — Inference-Lineage

This playbook validates the `models:/{fqn}/{version}` inference-
lineage path: the model-detail Lineage DAG must show source-tables
upstream (, solid green `trained_from`) **and**
prediction-tables downstream (, dashed blue
`inferred_to`).

It assumes the [`models-tab.md`](models-tab.md) and
[`models-promotion.md`](models-promotion.md) playbooks have been
replayed at least once so a registered model with one or more
versions exists in soyuz.

## Setup

```bash
# Terminal 1
cd ~/git/soyuz-catalog && uv run soyuz-catalog
# Terminal 2
cd ~/git/PointlesSQL && uv run pointlessql
```

Login as the bootstrap admin user.

## Step 1 — Seed an inference write

In a Python notebook (or `uv run python`):

```python
import pandas as pd

from pointlessql.pql.pql import PQL

pql = PQL(agent_run_id="seed-inference-21.7")

# Suppose the smoke_model is at models:/pql_test.mlflow_smoke.smoke_model/1
predictions = pd.DataFrame({"id": [1, 2, 3], "score": [0.91, 0.42, 0.78]})
pql.write_table(
 predictions,
 "pql_test.mlflow_smoke.smoke_predictions",
 source_table_fqn="pql_test.mlflow_smoke.features",
 source_model_uri="models:/pql_test.mlflow_smoke.smoke_model/1",
)
```

The call writes the DataFrame to a Delta table, registers it in
soyuz, and persists three `lineage_row_edges` rows whose
`source_model_uri = "models:/pql_test.mlflow_smoke.smoke_model/1"`.

## Step 2 — Predictions API

```bash
curl -s -b "pql_session=$(grep pql_session ~/.config/pointlessql/auth.cookie)" \
 http://127.0.0.1:8000/api/models/pql_test.mlflow_smoke.smoke_model/predictions | jq
```

Expect:

```json
{
 "predictions": [
 {"target_table": "pql_test.mlflow_smoke.smoke_predictions", "edge_count": 3}
 ]
}
```

## Step 3 — Bidirectional cytoscape DAG

Browse to
`http://127.0.0.1:8000/models/pql_test.mlflow_smoke.smoke_model`,
click the *Lineage* tab.

Expect:

- **Legend** at the top: green `Sources trained_from` + blue
 `Predictions inferred_to`.
- The orange-hexagon model node sits in the centre.
- A green round-rectangle node `features` upstream (left) with a
 solid edge `trained_from`.
- A blue round-rectangle node `smoke_predictions` downstream (right)
 with a dashed edge `inferred_to`.

Below the cytoscape view a "Prediction tables" card lists
`pql_test.mlflow_smoke.smoke_predictions` with `Edges = 3`.

## Step 4 — Multi-version aggregation

Re-run the seed snippet but bump the model version to v2 (assuming
v2 exists). Re-render the Lineage tab.

Expect: the Prediction-tables card now sums the edge counts across
both versions (the API matches via `models:/{fqn}/%` so version-
specific writes aggregate at the registered-model level).

## Step 5 — Negative test (non-inference write)

```python
pql.write_table(
 pd.DataFrame({"id": [1]}),
 "pql_test.mlflow_smoke.unrelated_table",
 source_table_fqn="pql_test.mlflow_smoke.features",
)
```

Without `source_model_uri`, the resulting row-edges leave the
column `NULL` and the Predictions card stays unchanged. Confirm:

```bash
sqlite3 ~/.local/share/pointlessql/auth.db \
 "SELECT target_table, source_model_uri FROM lineage_row_edges \
 WHERE target_table LIKE 'pql_test.mlflow_smoke.unrelated_table%'"
```

Expect: `target_table` populated, `source_model_uri = NULL`.

## Step 6 — Self-loop guard

If a model accidentally writes back into its own registered-model
FQN (rare; usually a misconfigured `target`), the bidirectional
graph silently skips the would-be self-loop edge. The log lines
remain visible in `lineage_row_edges`.

## Known limitations

- The bidirectional DAG currently aggregates at the registered-
 model level, not per-version. Per-version split (so the operator
 can see "v1 wrote to predictions_2026_q1, v2 wrote to
 predictions_2026_q2") is queued as a polish.
- A dedicated `pql.predict(model="…", input=df)` helper that
 auto-detects model context from `mlflow.active_run()` is also
 — the explicit `source_model_uri=` path covers the
 audit need today.
