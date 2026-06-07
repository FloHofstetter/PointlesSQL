---
title: "Phase 199 — Performance- & Skalierungs-Härtung (Latenz-Budget-Gate) (plan)"
audience: contributor
---

# Phase 199 — Performance- & Skalierungs-Härtung

**Status: ⏳ planned (geplant 2026-06-06).** Detail-Sidecar; siehe
[ROADMAP.md](../../ROADMAP.md) (Differentiator-Tiefe-Cluster 197–206).

## Warum

Die Plattform ist über 188 Phasen breit gewachsen, aber **Performance ist
nirgends als Vertrag fixiert**. Es gibt drei Drift-Ratschen (file-size,
pyright, mutation) — aber **keine für Latenz**. Hot Paths wie Audit-FTS,
Lineage-Graph-Aufbau und große Previews haben heute *null* Instrumentierung
(keine per-Route-Latenz, keine Query-Dauer-Histogramme). Eine Regression,
die `/api/audit/search` von 100 ms auf 3 s schiebt, würde niemand bemerken,
bis ein Nutzer es meldet.

Diese Phase macht aus „fühlt sich schnell an" einen **messbaren, in CI
durchgesetzten Vertrag**: erst instrumentieren, dann Budgets einfrieren
(Muster der vorhandenen Budget-Gates), dann die heißesten Pfade gezielt
härten — unter Wahrung der software-composited-UI-Regel.

## Ausgangslage (Fakten)

- **Budget-Gate-Muster zum Spiegeln:**
  [`scripts/check-file-size-budget.sh`](../../scripts/check-file-size-budget.sh)
  (800-LOC-Cap + Allowlist),
  [`scripts/check-pyright-budget.sh`](../../scripts/check-pyright-budget.sh)
  (eingefrorener Floor + Bump-Historie),
  [`scripts/bench_test_suite.sh`](../../scripts/bench_test_suite.sh)
  (Wall-Clock-Snapshots nach `.bench/`, keine CI-Ratsche).
- **Backend-Hot-Paths ohne Instrumentierung:**
  - Audit-FTS ([`services/audit_fts/`](../../pointlessql/services/audit_fts/)):
    SQLite-FTS5 + PG-tsvector/GIN, 15 Trigger über 5 Achsen (jeder
    Audit-Write zahlt Trigger-Overhead), offset/limit bis 1000.
  - Audit-Aggregator
    ([`services/audit_aggregator/`](../../pointlessql/services/audit_aggregator/)):
    pure-SQL `summary`/`timeseries`/`anomalies` auf Live-Tabellen, keine
    Materialisierung.
  - Lineage-Graph-Builder
    ([`services/lineage/graph_builder.py:39-80`](../../pointlessql/services/lineage/graph_builder.py)):
    Bulk-Load Row+Column-Maps je Run → cytoscape-Render.
  - Table-Stats ([`table_stats.py:30-322`](../../pointlessql/services/table_stats.py)):
    GROUP-BY-Risiko über high-cardinality-Spalten (Skip-Ceiling 10k,
    Zeile 33).
  - Query-History-List
    ([`query_history.py:194-258`](../../pointlessql/services/query_history.py)):
    begrenztes N+1 (Zeilen + Loop-Join, limit ≤ 200).
- **Metrics heute** ([`services/metrics.py`](../../pointlessql/services/metrics.py)):
  nur 3 Scheduler-Metriken (`job_runs_total`, `job_run_duration_seconds`,
  `scheduler_tick_lag_seconds`); **keine per-Route-Latenz, keine
  Query-Dauer**. Prometheus-Client ist Dependency; eigener REGISTRY.
- **Pagination-Dependency**
  ([`api/dependencies/_pagination.py`](../../pointlessql/api/dependencies/_pagination.py)):
  offset/limit (1–1000), kein Cursor.
- **Frontend-Perf-Regel** ([`base.css:100-108`](../../frontend/css/base.css)):
  **kein backdrop-filter/CSS-filter/Live-Blur** (software-composited
  Maschine; Repaint-Killer). `MIN_FIT_ZOOM=0.5`
  ([`canvas/viewport.js:47`](../../frontend/js/canvas/viewport.js)).
  Vgl. [[ui-perf-no-backdrop-filter]].
- **Kein Last-Test-Harness** (kein locust/k6/pytest-benchmark in
  `pyproject.toml`).

## Scope (Wellen)

### W1 — Instrumentierung (vor jeder Optimierung)
- Per-Route-Latenz-Middleware (Hook im Stack neben
  [`api/middleware.py`](../../pointlessql/api/middleware.py)): Histogram
  `http_request_duration_seconds{route,method,status}` in den vorhandenen
  Prometheus-REGISTRY. Niedrige Kardinalität (Route-Template, nicht Pfad).
- Query-Dauer-Span um die DB-/DuckDB-Seams (Audit-FTS, Lineage-Build,
  Table-Stats). Erst messen → Baseline → dann härten.

### W2 — Benchmark-Harness + große Fixtures
- `tests/perf/` mit pytest-benchmark (oder schlankem eigenem Timer):
  reproduzierbare Lasten — Audit-Korpus 1M Zeilen, Lineage-DAG 10k Edges,
  Table-Stats 10k-distinct-Spalte, paginierte Audit-Suche.
- Deterministische Seed-Skripte (kein `random`/`Date.now`); Ergebnisse als
  Artifact + nach `.bench/` (Format von `bench_test_suite.sh` wiederverwenden).

### W3 — Latenz-Budget-Gate (die Ratsche)
- `scripts/check-perf-budget.sh` + CI-Step im Stil der bestehenden Budgets:
  eingefrorene p95-Floors je benannter Operation (z. B. „FTS-Suche auf 1M
  ≤ X ms", „Lineage-Build 10k Edges ≤ Y ms"), Allowlist + dokumentierte
  Bump-Historie mit Begründung. **Nicht-blockierend** zuerst (Daten
  sammeln), dann scharf.
- Nightly-Full-Lauf der schweren Fixtures (analog mutation-nightly).

### W4 — Backend-Hot-Path-Optimierung (eine Welle je Pfad)
- Audit-FTS: Index-/Query-Plan prüfen, Trigger-Overhead messen, ggf.
  Materialisierung ab Schwelle (>2 s p95 oder >100M Datenpunkte/Jahr —
  die im Aggregator notierte Grenze).
- Lineage-Build: Bulk-Load-Form + cytoscape-Payload-Größe begrenzen
  (Server-seitige Aggregation/Truncation statt Client-Überlast).
- Query-History-List: N+1 → Batch-`IN()`.
- Cursor-Pagination für tiefe Offsets, wo offset-Seek wehtut.

### W5 — Frontend-Render-Härtung (unter der UI-Perf-Regel)
- Canvas-Drag/Viewport, cytoscape-DAG, große DataFrame-Previews mit Event
  Timing API messen ([[ui-perf-no-backdrop-filter]] beschreibt die
  Mess-Methode + CSS-Cache-Falle). Virtualisierung großer Listen/Previews;
  keine neuen Filter/Animationen.
- Budget-Assertions in die e2e-Suite (Phase 198) einklinken, wo sinnvoll
  (Render-Zeit-Schwellen auf Schlüsselseiten).

## Akzeptanzkriterien
- Per-Route-Latenz + Query-Dauer erscheinen unter `/metrics`.
- `bash scripts/check-perf-budget.sh` grün auf sauberem main; ein bewusst
  eingebauter 3×-Regress auf einem budgetierten Pfad lässt es failen.
- Benchmark-Harness reproduziert die schweren Lasten lokal + im Nightly.
- Keine neue Nutzung von backdrop-filter/CSS-filter/Animation im Frontend
  (Regel bleibt gewahrt; ggf. Lint-Check ergänzen).
- Optimierte Pfade zeigen messbare p95-Verbesserung gegen die W2-Baseline.

## Risiken / Notizen
- **Messung vor Optimierung** ist nicht verhandelbar — ohne Baseline ist
  jede „Härtung" Glaube.
- Budget-Floors müssen maschinen-/CI-runner-tolerant sein (Varianz) →
  großzügige Schwellen, p95 statt max, mehrere Messungen.
- SQLite-vs-Postgres-Lane: Hot-Path-Budgets ggf. dialekt-spezifisch.
- Kardinalitäts-Explosion bei Route-Labels vermeiden (Route-Template,
  keine IDs).
- Verwandt: Phase 14 (cost-gate EXPLAIN), Phase 200 (Observability —
  teilt sich die Metrics-Infra), Phase 31 (Test-Suite-Speed).
