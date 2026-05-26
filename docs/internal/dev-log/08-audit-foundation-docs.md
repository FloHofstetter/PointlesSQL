---
title: "Cluster 08 — Phase 21–22 Audit-Foundation + Docs (dev-log)"
audience: contributor
cluster_id: "08"
phases: "21-22"
closed: "2026-04-30"
---

# Cluster 08 — Phase 21–22 Audit-Foundation + Docs (dev-log)

> Phase 21 audit-foundation (cross-repo agent-ml-registry walkthrough), Phase 22 (docs landing page + quickstart + concepts overview).

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Added**)

- **Phase 21 closed — ML Registry + Auditable Training.** Eight
  sub-sprints landed in two autonomous sessions on 2026-04-30:
  21.0 (MLflow subprocess + `/mlflow/` proxy + tab), 21.1 (soyuz
  UC-OSS `MODEL` Securable), 21.2 (cross-link `agent_run` ↔ MLflow
  run ↔ ModelVersion), 21.3 (forced autolog), 21.4 (hardware
  fingerprint), 21.5 (Models browse + 5-tab detail + compare),
  21.6 (champion/challenger promotion-hop), 21.7 (inference
  lineage). All eight share the audit-of-intent framing — capture
  enough to answer "wie wurde das Modell trainiert + wo schreibt
  es seine Predictions?" without claiming bit-identical replay.

- **Sprint 21.4 — Hardware/Library Fingerprint.** Adds a nullable
  `agent_run_operations.env_snapshot` Text column (Alembic
  `u1q3r5s7t9v1`) carrying an advisory JSON blob with three
  sub-keys: `python` (version + platform + cpu_count), `packages`
  (top-200 distributions via `importlib.metadata`, capped at
  4 KiB), `gpu` (when torch + CUDA available, per-device name +
  total memory). The snapshot is built once at module-import
  time and cached for the whole PointlesSQL process so subsequent
  `record_operation` calls don't re-walk `importlib.metadata` on
  every write — appropriate for an advisory fingerprint where a
  fork-side package add doesn't justify the per-op cost. The
  Run-detail Operations tab now renders a collapsed "Environment
  fingerprint" accordion under each op row showing the Python
  banner, the GPU list (if any), and the package list as an inner
  collapsed details block. End-to-end best-effort: every sub-step
  is wrapped in try/except and degrades to `None` rather than
  blocking the audit row. Honest reproducibility caveat: the
  blob captures the engineer's declared intent, not provability
  of bitwise reproducibility (CUDA non-determinism, parallel
  dataloaders, atomic-add ordering all leak through). 9 new
  pytest cases.

- **Sprint 21.3 — Forced Autolog (training param/metric capture).**
  New `pql.training_context()` context-manager wraps a training
  block, calls `mlflow.autolog()` for the requested framework hint
  (`"auto"` covers sklearn/xgboost/torch/tf out of the box), opens
  an MLflow run (or nests under an outer one), and at exit copies
  `run.data.params + run.data.metrics` into a JSON blob on
  `agent_run_operations.training_params_json` (new Alembic migration
  `t0p2q4r6s8u0`). The op_name enum gained `train_model`. The
  Run-detail Operations tab now renders a collapsed "Training
  params + metrics" accordion underneath each `train_model` row
  with the snapshot rendered as two side-by-side tables. The
  whole layer is best-effort: works without the mlflow extra
  (audit row still lands, snapshot stays empty), with an
  unreachable tracking server, and when the wrapped training body
  raises (partial autolog state is captured before re-raise so
  the audit trail never loses a training-event). 7 new pytest
  cases. Fail-loud `UnauditedTrainingError` and seed-interceptor
  capture deferred — the best-effort path here covers the
  audit-of-intent goal without blocking training when MLflow
  misbehaves.

- **Sprint 21.7 — Inference-Lineage (model → prediction tables).**
  Closes the second half of the model-lineage graph: when
  `pql.write_table(predictions, target, source_model_uri="models:/
  cat.sch.model/3")` runs, every row-edge it produces carries the
  originating model URI on a new `lineage_row_edges.source_model_uri`
  column (Alembic `s9o1p3r5t7u9`). The model-detail Lineage tab is
  now bidirectional: source-tables upstream with solid green
  `trained_from` edges, prediction-tables downstream with dashed
  blue `inferred_to` edges, plus a new "Prediction tables" card
  underneath the cytoscape view that lists each target FQN with its
  edge count. New `GET /api/models/{full_name}/predictions`
  endpoint reads `lineage_row_edges` directly (no soyuz round-trip,
  cost is O(R · E) on the audit DB rather than O(C · M · V)).
  `aggregate_prediction_tables_for_model` matches by
  `models:/{fqn}/%` so any version of the model contributes. The
  `build_model_lineage_graph` builder gained a `kind` field
  (`"model"` / `"table"` / `"prediction"`) on every node so the
  cytoscape style branches three ways. 10 new pytest cases.
  Drift alerts and a dedicated `pql.predict` helper are deferred
  to Phase 22+.

- **Sprint 21.6 — Champion/Challenger Promotion-Hop.** Operators (or
  supervisor-scoped agents) can now promote a `READY` model version
  to *champion* through `POST /api/models/{full_name}/promote`. The
  swap writes a `_pql_promotion` JSON marker into the registered
  model's `comment` (mirrors the Phase-21.2 `_pql_link` convention so
  the read-side parsers stay independent), inserts an `AgentReview`
  row with `kind="model_promotion"` so the Phase-19 cockpit fan-out
  can notify subscribers, and emits a `pointlessql.model.promoted`
  CloudEvent envelope. The 21.5 Permissions stub on
  `/models/{full_name}` is replaced by a Promotion tab: current
  champion card, per-version `[Promote]` button, mandatory-reason
  modal, and a collapsed promotion-history list. Champion badge
  also renders on the Versions tab. Supervisor or admin scope
  required (mirrors the Phase 13.11 ladder). New Alembic migration
  `r8n0p2q4s6u8` adds a non-null `kind` column to `agent_reviews`
  with `audit_review` as the default for backfill. New service
  module `pointlessql/services/model_promotion.py` carries the
  marker round-trip, current-champion resolver (falls back to
  highest-numbered READY version when no marker exists),
  `promote_version` service, history aggregator, and CloudEvent
  builder. `ModelsMixin` gains `update_registered_model`. First-
  class soyuz aliases deferred — the marker convention gives
  equivalent semantics without a soyuz schema bump and a future
  one-shot script can re-emit markers as real catalog tags once
  soyuz adds them. 17 new pytest cases.

- **Sprint 21.5 — registered-models browse surface.** Models now
  appear in the catalog tree per schema (alongside tables) and have
  a top-level `/models` index page in the icon rail. Each registered
  model has a detail page at `/models/{full_name}` with five tabs
  (Overview, Versions, Lineage, MLflow, Permissions); the Versions
  tab pulls params/metrics/tags from the linked MLflow run via
  `MlflowClient.get_run`, the Lineage tab renders a focused
  cytoscape DAG showing the model node + the source tables consumed
  by any Hermes-agent-run linked to a version of the model. A
  side-by-side compare view at `/models/{full_name}/compare?v1=N&v2=M`
  highlights metric deltas with a `lower-better`/`higher-better`
  classification heuristic and lists added/removed/changed params
  and tags. Anonymous access is gated by the existing auth
  middleware. New `ModelsMixin` on `UnityCatalogClient` exposes the
  four typed soyuz model RPCs the routes depend on
  (`list_registered_models`, `get_registered_model`,
  `list_model_versions`, `get_model_version`). The browser
  walkthrough at `docs/e2e-walkthroughs/models-tab.md` replays the
  full flow.

> from CHANGELOG.md (bucket: **Closed**)

### Closed — Phase 21 audit-foundation: 21.0 + 21.1 + 21.2 (2026-04-30)

Vertical slice "audit-foundation for ML" landed in one autonomous
session: a Hermes-driven training run now records its MLflow context
into PointlesSQL's audit trail, the soyuz-catalog model-version row,
and a single-call cross-link aggregator. Three sub-sprints, install
`pip install pointlessql[ml]` to opt in.

* **Sprint 21.1 — soyuz UC-OSS MODEL Securable wire-compat for
  MLflow.** Soyuz commit `248f73f` (tag `v0.3.0rc1` local).
  Closes the wire-compat gap so MLflow's UC-OSS client
  (`mlflow.set_registry_uri("uc:http://...")`) can roundtrip:
  create model → create version (PENDING) → upload → finalize →
  READY → get/list/update/delete. Three additive endpoints
  (`finalizeModelVersion`, `temporary-model-version-credentials`)
  + status-state-machine fix + schema accommodation for the proto's
  URL-redundant body fields. Aliases stay out-of-scope — UC-OSS
  proto has no alias RPCs (only the Databricks variant).
* **Sprint 21.0 — MLflow Tracking subprocess + UI tab + reverse-proxy.**
  `MLflowSubprocess` lifecycle manager (HTTP health-check, PID file,
  graceful SIGTERM → SIGKILL) wired into the FastAPI `lifespan`.
  `/ml` HTML page mounts an iframe at `/mlflow/` which is served
  by a `httpx`-based reverse-proxy that injects the authenticated
  user as `X-MLflow-User` so the soyuz-side audit trail can
  correlate. New `MLflowSettings` (`POINTLESSQL_MLFLOW_*`) with
  optional URI overrides. Tab branded "ML" in the icon-rail.
* **Sprint 21.2 — Cross-link agent_run ↔ MLflow ↔ MODEL.**  Alembic
  `q7m9o1p3r5t7` adds `mlflow_run_id` columns to `agent_runs`
  and `agent_run_operations`. The op-recorder hot path sniffs
  `mlflow.active_run()` and stamps the run-id on both rows so a
  single SQL join answers "how was this model trained?". New
  `GET /api/runs/{id}/ml-context` aggregator returns the three-way
  join of agent-run + MLflow run + soyuz model-versions. Soyuz
  model-versions are tagged via a JSON marker in the `comment`
  field as a bridge until soyuz Sprint-25 tags-on-models lands.
  New CloudEvents type `pointlessql.mlflow.linked`.

22 new unit/integration tests + 4 live-soyuz smoke tests
(`test_mlflow_uc_oss_smoke.py`). Hermes-plugin `pql_mlflow_link_model`
tool deferred — auto-link via the recorder hook covers the core
flow; explicit linkage tool can land in a polish sprint once we
see the agent-pattern that needs it.
