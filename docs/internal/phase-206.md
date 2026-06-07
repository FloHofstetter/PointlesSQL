---
title: "Phase 206 — Cost/FinOps- & Kapazitäts-Tiefe (plan)"
audience: contributor
---

# Phase 206 — Cost/FinOps- & Kapazitäts-Tiefe

**Status: ⏳ planned (geplant 2026-06-06).** Detail-Sidecar; siehe
[ROADMAP.md](../../ROADMAP.md) (Differentiator-Tiefe-Cluster 197–206).
Abschluss des Clusters — schließt die FinOps-Klammer um einen
„Databricks-Klon".

## Warum

Phase 14 brachte den cost-gate-EXPLAIN, Phase 146 Cost-Attribution +
Quotas + Mesh-Health. Die *Messung + Durchsetzung* steht also — pro Query
ein Kostensatz, hourly-Rollup, daily/hourly-Quoten in off/warn/strict. Was
fehlt, ist die **FinOps-Tiefe darüber**: Niemand kann heute eine
Chargeback-Übersicht ziehen („was kostet Team X / Product Y diesen
Monat?"), niemand setzt ein **Budget** mit Vorwarnung, und niemand sieht
eine **Forecast/Kapazitäts**-Aussage („bei diesem Trend reißen wir das
Quota in N Tagen"). Für einen Lakehouse-Klon ist genau das der
FinOps-Wert.

Diese Phase baut auf der vorhandenen Cost-Maschinerie auf: Chargeback-
Reports, Budgets mit Burn-Vorwarnung, und Forecast/Kapazitäts-Planung aus
den schon vorhandenen Rollups + Trend-/Perf-Samples.

## Ausgangslage (Fakten)

- **Cost-Service** ([`services/cost/`](../../pointlessql/services/cost/)):
  `_meter` (record_query_cost → `DataProductQueryCost`: estimated_cost,
  duration_ms, bytes_scanned, rows_returned, table_list, authoring_product,
  principal), `_quota` (check_quota aggregiert hourly+daily, off/warn/strict),
  `_rollup` (`roll_up_hourly_buckets` → `DataProductCostBucketHourly`,
  UNIQUE(bucket_hour, product, consumer)), `_dashboard`
  (`cost_by_product`/`cost_by_consumer`/`mesh_health_full`),
  `_bootstrap` (quota-check als before-read-Hook).
- **Cost-Gate-EXPLAIN** ([`services/lens/cost_gate.py:92-150`](../../pointlessql/services/lens/cost_gate.py)):
  read-only-AST → auto-LIMIT → EXPLAIN-Cap → Session-Budget. Formel
  `cost = max_cardinality × (1 + join_depth)`
  ([`services/sql/cost_estimator.py:159`](../../pointlessql/services/sql/cost_estimator.py)),
  EXPLAIN-JSON via [`services/sql/explain.py:49-118`](../../pointlessql/services/sql/explain.py).
- **Modelle/Migration (Phase 146)**
  ([`models/catalog/_cost.py:46-175`](../../pointlessql/models/catalog/_cost.py)):
  raw-Ledger + hourly-Bucket; Quota-Policy-Spalten (`max_cost_per_day`,
  `max_queries_per_hour`, `quota_enforcement`) an workspace- **und**
  product-Policies.
- **Cost-Routen** ([`api/admin/cost_routes.py:57-140`](../../pointlessql/api/admin/cost_routes.py)):
  `/api/mesh/health/full`, `/api/cost/by-product`, `/api/cost/by-consumer`,
  `PUT /api/admin/governance/quota` (alle admin-only).
- **Attribution-Dimensionen:** product (authoring_product_id), consumer
  (principal_user_id / consumer_product_id), workspace (Phase 28, via
  [`api/_consumption_hook.py`](../../pointlessql/api/_consumption_hook.py)).
- **Query-History** ([`services/query_history.py:75-191`](../../pointlessql/services/query_history.py)):
  duration/rowcount/tables/read_kind/agent_run_id — **kein cost-Feld**
  (cost liegt separat im Meter).
- **Trend-/Forecast-Bausteine vorhanden:**
  [`services/data_products/trending.py`](../../pointlessql/services/data_products/trending.py)
  (top-N rolling 7d), `DataProductQueryPerfSample`
  ([`models/catalog/_runtime_slo.py:61-89`](../../pointlessql/models/catalog/_runtime_slo.py)),
  WoW+3σ-Muster ([`api_keys/_usage.py`](../../pointlessql/services/api_keys/)),
  z-Score-Drift (`slo/_drift.py`). **Aber keine Cost-Forecast/Budget-
  Logik.**
- **Scheduler-Executor** `cost_rollup_hourly`
  ([`services/scheduler/executors/`](../../pointlessql/services/scheduler/executors/))
  — das Muster für periodische FinOps-Jobs.

## Scope (Wellen)

### W1 — Chargeback-Reports
- `services/cost/_chargeback.py`: pivotiert `DataProductCostBucketHourly`
  über (consumer, authoring_product, workspace) × Zeitfenster (Tag/Woche/
  Monat). Routen `/api/cost/chargeback` (+ HTML-Seite) + Export (CSV/JSON)
  — admin- + steward-scoped. Liest Buckets, nicht raw-Rows (Perf, wie das
  vorhandene Dashboard).

### W2 — Budgets + Burn-Vorwarnung
- Budget als erstklassiges Objekt (eigenes Modell + Migration): pro
  workspace/product/consumer ein periodisches Budget (z. B. monatlich).
  Quota-Enforcement erweitern: **warn bei 80 %, block bei 100 %** des
  Budgets (heute nur harte daily/hourly-Caps). Verletzung → Signals-Karte
  (vorhandener Ledger) + optional CloudEvent (vorhandener
  `alert_dispatcher`).

### W3 — Forecast + Kapazitäts-Planung
- `services/cost/_forecast.py`: aus den hourly-Buckets eine
  Trend-/Linear-Regression + WoW-Wachstum (vorhandenes Muster
  wiederverwenden), Projektion „bei diesem Trend Budget/Quota erreicht in N
  Tagen". Kapazität: bytes_scanned/rows je Tabelle aggregieren, 30/90-Tage-
  Projektion, Breach-Vorwarnung.

### W4 — Cost am Agent-Run + vollständigere Attribution
- estimated_cost (und ggf. Laufzeit-Metriken) auf der Agent-Run-Ebene
  sichtbar machen (Agent-Ökonomie: „was kostet dieser Agent-Lauf"),
  konsistent mit der Provenance aus Phase 203. Query-History und
  Cost-Ledger über `agent_run_id` verknüpfbar machen.

### W5 — Dashboards + Doku + e2e
- FinOps-Grafana-Panels (teilt die Infra von Phase 200): Cost-Trend,
  Top-Consumer, Budget-Burndown, Forecast — mit `$workspace`-Variable.
  mkdocs „FinOps": Chargeback lesen, Budget setzen, Forecast deuten.
  e2e-Playbook (Phase 198): Budget setzen → überfahren → Warn→Block +
  Signal.

## Akzeptanzkriterien
- `/api/cost/chargeback` liefert korrekte Pivots über consumer/product/
  workspace × Zeitfenster, exportierbar; lädt gegen SQLite + Postgres.
- Ein Budget mit 80/100-%-Schwellen warnt bzw. blockt verifizierbar und
  erzeugt eine Signal-Karte.
- Forecast projiziert aus echten Buckets ein „erreicht in N Tagen" und
  fängt einen synthetischen Aufwärtstrend.
- Agent-Run-Detail zeigt aggregierte Kosten; Query↔Cost über agent_run_id
  verknüpft.
- FinOps-Dashboards laden in beiden Dialekten; Doku in mkdocs `--strict`.

## Risiken / Notizen
- **estimated_cost ist eine EXPLAIN-Schätzung, kein realer $-Betrag** —
  Reports müssen das klar als „Kosteneinheiten/Schätzung" labeln (keine
  irreführende Währung; vgl. user-facing-string-Regel).
- Forecast auf wenigen Buckets ist unsicher — Konfidenz/Datenbasis
  ausweisen, nicht über-versprechen.
- Budget-Block kann Nutzer überraschen → default warn, block opt-in;
  Admin-Override-Pfad.
- Bucket-Rollup-Idempotenz (UNIQUE-Constraint) bei neuen Aggregationen
  wahren.
- Verwandt: Phase 14 (cost-gate), Phase 146 (Attribution/Quotas), Phase
  28 (Workspace-Isolation), Phase 200 (Dashboards/Signals), Phase 203
  (Agent-Run-Kosten).
