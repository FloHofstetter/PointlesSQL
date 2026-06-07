---
title: "Phase 200 — Observability- & SLO-Vollständigkeit (OTel + Burn-Rate) (plan)"
audience: contributor
---

# Phase 200 — Observability- & SLO-Vollständigkeit

**Status: ⏳ planned (geplant 2026-06-06).** Detail-Sidecar; siehe
[ROADMAP.md](../../ROADMAP.md) (Differentiator-Tiefe-Cluster 197–206).
Teilt sich die per-Route-Metrics-Infra mit Phase 199 — 199 misst Latenz für
*Budgets*, diese Phase macht daraus *Distributed Tracing + Dashboards +
Burn-Rate-Alerting*.

## Warum

Die Plattform hat die *Bausteine* für Observability, aber kein
*durchgängiges Bild*. Tracing ist hausgemachte Correlation-ID-Weitergabe
(kein OTel), Metrics decken nur den Scheduler ab, SLOs werden
*punktuell* (pass/fail) bewertet — **ohne Burn-Rate / Error-Budget**, also
ohne die eine Zahl, die sagt „verbrennen wir unser Fehlerbudget zu
schnell". Das eine Grafana-Dashboard ist audit-zentriert, nicht
RED/USE-orientiert. Verfügbarkeits-Probes existieren als *Tabelle*
(`DataProductAvailabilityProbe`), sind aber nicht verdrahtet.

Diese Phase schließt das Bild: OTel-Tracing über alle Routes, RED/USE-
Dashboards, SLO-Burn-Rate mit Error-Budget, und die schon modellierten
synthetischen Probes scharf geschaltet.

## Ausgangslage (Fakten)

- **Tracing = Correlation-IDs, kein OTel**
  ([`services/tracing/_context.py`](../../pointlessql/services/tracing/_context.py)):
  ContextVar-basiert; vier IDs (request/job_run/task/correlation) in
  [`config/_logging.py:21-28`](../../pointlessql/config/_logging.py),
  JSON-Formatter stempelt sie. **`opentelemetry` ist KEINE Dependency.**
- **Metrics = 3 Scheduler-Metriken**
  ([`services/metrics.py`](../../pointlessql/services/metrics.py));
  `/metrics`-Route admin-only
  ([`api/main.py:183-195`](../../pointlessql/api/main.py)). **Keine
  RED-Metriken** (per-Route rate/errors/duration).
- **SLO-Maschinerie** ([`services/slo/`](../../pointlessql/services/slo/)):
  9 Kinds, 6 messbar (freshness/volume/completeness/statistical_shape/
  lineage/interval_of_change), 4 declaration-only. `_evaluate.py` liefert
  pass/fail/unmeasured — **point-in-time, keine Burn-Rate/Velocity**.
  Routes in [`api/data_products_routes/slo.py`](../../pointlessql/api/data_products_routes/slo.py).
- **Grafana** ([`examples/grafana/dashboards/pointlessql_audit.json`](../../examples/grafana/dashboards/pointlessql_audit.json),
  1588 Zeilen): ein audit/lineage-Dashboard, `$workspace`-Variable, liest
  Metadaten-DB direkt. **Kein RED/USE, keine SLO/Burn-Rate-Panels, keine
  Alert-Rules.**
- **Middleware-Stack** ([`api/middleware.py`](../../pointlessql/api/middleware.py)):
  request_id → csrf → rate_limit → auth; setzt request/correlation-IDs —
  **der Hook-Punkt** für Span-Erzeugung + RED-Metriken.
- **Probe-Tabellen schon da, nicht verdrahtet**
  ([`models/catalog/_runtime_slo.py`](../../pointlessql/models/catalog/_runtime_slo.py)):
  `DataProductAvailabilityProbe` (ok/fail/timeout/error, latency_ms),
  `DataProductQueryPerfSample` (SELECT-Dauer).
- **Alert-Dispatch** ([`services/alert_dispatcher.py`](../../pointlessql/services/alert_dispatcher.py)):
  CloudEvents/HMAC-Webhook, nur query-result-Bedingungen — **kein
  SLO-basiertes Alerting**. Signals-Ledger ([`services/signals.py`](../../pointlessql/services/signals.py))
  existiert (open/resolved, dedupe).
- **Health** ([`api/health_routes.py`](../../pointlessql/api/health_routes.py)):
  `/healthz` (public liveness), `/api/health/backends` (soyuz/mlflow/dbt/
  hermes-Probe).

## Scope (Wellen)

### W1 — OpenTelemetry-Backbone (Bridge zu vorhandenen IDs)
- `opentelemetry-sdk` + FastAPI/SQLAlchemy/httpx-Instrumentierung als
  opt-in Dependency-Extra. OTLP-Exporter konfigurierbar
  ([`config/`](../../pointlessql/config/)), default off (kein Zwang im
  Clean-Run).
- Bridge: die vorhandenen ContextVars (request/correlation/job_run/task)
  als Span-Attribute setzen — Logs und Spans teilen dieselbe trace_id, kein
  paralleles ID-System.

### W2 — RED-Metriken (teilt W1 von Phase 199)
- Per-Route Rate/Errors/Duration-Histogram im vorhandenen REGISTRY (eine
  Implementierung, zwei Konsumenten: Budget-Gate 199 + Dashboards hier).
- DB-/Backend-Dependency-Latenz (soyuz, DuckDB, Delta) als USE-nahe
  Metriken.

### W3 — SLO-Burn-Rate + Error-Budget
- `services/slo/_burn_rate.py`: aus den messbaren SLO-Verdicts über ein
  rollendes Fenster eine Burn-Rate + Restfehlerbudget berechnen (Multi-
  Window-Multi-Burn-Rate-Muster: schnelle + langsame Fenster).
- `_evaluate.py`/Route erweitern: neben pass/fail auch
  burn_rate + budget_remaining liefern; in den vorhandenen Signals-Ledger
  emittieren bei Schwellverletzung (kein neuer Alert-Kanal nötig).

### W4 — Synthetische Monitore scharf schalten
- Scheduler-Executor, der `DataProductAvailabilityProbe` +
  `DataProductQueryPerfSample` periodisch befüllt (Port-Probe + Test-SELECT
  je SLA-Produkt) — die Tabellen existieren, nur der Producer fehlt.
- Ergebnisse fließen in availability/performance-SLO-Kinds (heute
  declaration-only) → werden damit *messbar*.

### W5 — Dashboards (RED/USE + SLO) + Alert-Rules
- Neue Grafana-Dashboards neben dem Audit-Dashboard: RED (per-Route),
  USE (Ressourcen/Backends), SLO-Health + Burn-Rate + Error-Budget, alle
  mit `$workspace`-Variable (Konsistenz mit Phase 34).
- Provisionierte Alert-Rules (Burn-Rate-Alerts) → Webhook via vorhandenen
  `alert_dispatcher` (CloudEvents-Envelope wiederverwenden).

### W6 — Doku + e2e
- Operator-Doku (mkdocs): OTLP anschließen, Dashboards importieren,
  Burn-Rate-Alerts lesen. e2e-Playbook (Phase 198) für die neuen
  SLO/Observability-Surfaces.

## Akzeptanzkriterien
- Mit aktiviertem OTLP erscheint ein Request als zusammenhängender Trace
  (HTTP → SQLAlchemy → httpx-zu-soyuz), trace_id = Log-correlation_id.
- `/metrics` exponiert per-Route RED-Metriken.
- SLO-Route liefert burn_rate + budget_remaining; eine simulierte
  SLO-Verletzung erzeugt eine Signals-Karte + (bei Webhook-Config) ein
  CloudEvent.
- Synthetische Probes befüllen beide Runtime-SLO-Tabellen; availability/
  performance-SLOs werden „measured".
- Die neuen Grafana-Dashboards laden gegen SQLite **und** Postgres.

## Risiken / Notizen
- OTel default-off halten — der Clean-Machine-Run (`uv run pointlessql`)
  darf keinen Collector brauchen.
- Burn-Rate braucht eine stabile Verdict-Historie; Fenster + Schwellen
  konservativ wählen (Alert-Fatigue vermeiden).
- Metrics-Kardinalität: Route-Template-Labels, niemals IDs/FQNs.
- Verwandt: Phase 19/34 (Grafana), Phase 44 (structured logging), Phase
  146 (cost-rollup teilt Scheduler-Executor-Muster), Phase 199 (Metrics-
  Infra).
