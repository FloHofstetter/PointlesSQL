# E2E walkthrough — Agent-driven ML Registry flow

> **Mode:** `hermes` · **Surface:** Hermes plugin tools

This playbook validates the eight Hermes-plugin tools that close
out cross-repo. The vertical slice: an agent connected
through `hermes-plugin-pointlessql` browses registered models,
trains and registers a new version, logs a one-shot training-run
snapshot, writes inference predictions tagged with the model URI,
and finally promotes the new version to champion. At every step
the audit trail + lineage DAG stay coherent.

The walkthrough assumes / 21.6 / 21.7 e2e have been
replayed at least once (the prerequisite registered model
`pql_test.mlflow_smoke.smoke_model` exists with two `READY`
versions).

Pinned at:
- PointlesSQL commit `5919c63` ( server side)
- Plugin commit `f01d4e0` ( tool side)

## Setup

```bash
# Terminal 1 — soyuz-catalog
cd ~/git/soyuz-catalog
uv run soyuz-catalog # http://127.0.0.1:8080

# Terminal 2 — PointlesSQL
cd ~/git/PointlesSQL
uv run pointlessql # http://127.0.0.1:8000

# Terminal 3 — Hermes (loads the plugin from sibling checkout)
cd ~/git/hermes-agent
uv run hermes
```

In Hermes, set the supervisor flag on the agent's session env so
`pql_promote_model` registers:

```bash
export POINTLESSQL_SUPERVISOR_MODE=1
export POINTLESSQL_API_KEY=<supervisor-scoped key>
```

The api-key needs the supervisor scope on the PointlesSQL side
(see admin → API keys). Without it, every promote call returns
403 with a `supervisor required` envelope — by design.

## Step 1 — `pql_list_models` enumerates the namespace

Agent prompt:
> `pql_list_models with catalog_name="pql_test", enrich_latest=true`

Expect: JSON envelope `{"ok": true, "data": {"models": [{...}]}}`
with at least one entry whose `full_name` ends in
`mlflow_smoke.smoke_model` and whose `latest_version` /
`latest_status` fields are filled in.

## Step 2 — `pql_get_model` drills into versions

Agent prompt:
> `pql_get_model full_name="pql_test.mlflow_smoke.smoke_model"`

Expect: `{"model": {...}, "versions": [{...}]}` — every version
carries a parsed `link_marker` (the `_pql_link` JSON bridge to
`agent_run_id` + `mlflow_run_id`). The agent now knows which
versions are Hermes-authored.

## Step 3 — `pql_log_training_run` after a local mlflow.autolog block

In a Python kernel attached to the same Hermes session (or in a
dev shell with `POINTLESSQL_AGENT_RUN_ID` exported):

```python
import mlflow
mlflow.autolog(disable_for_unsupported_versions=True)
with mlflow.start_run() as run:
 #... agent's training code: model.fit(X, y)...
 pass
print(run.info.run_id, run.data.params, run.data.metrics)
```

Then via Hermes:

> `pql_log_training_run framework="sklearn", params={"learning_rate": "0.01"}, metrics={"accuracy": 0.92}, mlflow_run_id="<id from above>"`

Expect: `{"op_id": <int>, "agent_run_id": "<run-uuid>",
"training_params_json": "{...}"}`. The agent run's
`/runs/<uuid>` page now shows a new `train_model` operation row
with the `training_params_json` accordion ( UI) filled
in from the post-hoc log.

## Step 4 — `pql_write_table` with `source_model_uri` lands inference

Agent prompt:

> `pql_write_table sql="SELECT * FROM pql_test.silver.features", target="pql_test.gold.preds_v3", mode="overwrite", source_model_uri="models:/pql_test.mlflow_smoke.smoke_model/2"`

Expect: `{"target": "pql_test.gold.preds_v3", "mode": "overwrite",
"rows_written": <N>}`. The audit op-row's `extra_params` now
carries `source_model_uri`; the `lineage_row_edges` rows produced
by this write each have the same URI in their `source_model_uri`
column ( schema).

## Step 5 — `pql_get_model_predictions` confirms the inference attribution

Agent prompt:
> `pql_get_model_predictions full_name="pql_test.mlflow_smoke.smoke_model"`

Expect: `{"predictions": [{"target_table":
"pql_test.gold.preds_v3", "edge_count": <N>}]}`. Step 4's write
shows up here with the row count from the source SELECT.

## Step 6 — `pql_get_model_lineage` shows bidirectional DAG

Agent prompt:
> `pql_get_model_lineage full_name="pql_test.mlflow_smoke.smoke_model"`

Expect: `{"nodes": [...], "edges": [...]}`. Three node kinds:

- `kind="model"` — the model itself (one node).
- `kind="table"` — every training-source table found via the
 agent runs that produced versions.
- `kind="prediction"` — `pql_test.gold.preds_v3` (Step 4).

Two edge labels: `trained_from` (source → model) and
`inferred_to` (model → prediction).

## Step 7 — `pql_get_promotion_history` reads the current champion

Agent prompt:
> `pql_get_promotion_history full_name="pql_test.mlflow_smoke.smoke_model"`

Expect: `{"champion_version": <N>, "history": [...]}`. When no
manual promotion has happened the history is empty and
champion_version is the highest-numbered `READY` version (Sprint
21.6 fallback).

## Step 8 — `pql_promote_model` flips champion (supervisor)

Agent prompt:
> `pql_promote_model full_name="pql_test.mlflow_smoke.smoke_model", target_version=<other-version>, reason="E2E test promote — beats v1 on val accuracy"`

Expect: `{"champion_version": <other>, "previous_champion": <N>,
"promoted_at": "...", "review_id": <int>, "event": {...}}`. The
embedded `event` is a CloudEvents 1.0 envelope of
`type="pointlessql.model.promoted"` ready for webhook fan-out.

A re-call of `pql_get_promotion_history` now returns the new
champion + a `history[0]` entry naming the supervisor + reason.

The `/models/pql_test.mlflow_smoke.smoke_model` UI in the browser
shows the migrated `★ Champion` badge on the Versions tab.

## Step 9 — Failure modes

Test the visible-error envelopes:

a) Without `POINTLESSQL_SUPERVISOR_MODE=1`: `pql_promote_model` is
 not registered. The Hermes tool list won't include it.

b) With supervisor flag but a non-supervisor api-key:
 `pql_promote_model` registers but the call returns
 `{"ok": false, "error": "http 403", "detail": "..."}`.

c) `pql_promote_model target_version=999` (non-existent):
 `{"ok": false, "error": "http 400", "detail": "promotion:..."}`.

d) `pql_promote_model reason=""`: client-side `arg_error` envelope
 with `expected` schema hint, no server round-trip.

e) `pql_log_training_run` without `params` dict:
 `{"ok": false, "error": "params must be an object..."}`.

## Closure

 is fully closed cross-repo after this walkthrough plays
green. The eight new tools push the plugin to 42 total; the
agent flow `train → log → predict → promote` now lives entirely
inside the audited surface.

Pinned commits:
- PointlesSQL `5919c63` — server gap-fill + training-log endpoint.
- Plugin `f01d4e0` — 8 new tools + 2 extended.
