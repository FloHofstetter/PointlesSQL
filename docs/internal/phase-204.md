---
title: "Phase 204 — Data-Quality- & Expectations-Tiefe (plan)"
audience: contributor
---

# Phase 204 — Data-Quality- & Expectations-Tiefe

**Status: ⏳ planned (geplant 2026-06-06).** Detail-Sidecar; siehe
[ROADMAP.md](../../ROADMAP.md) (Differentiator-Tiefe-Cluster 197–206).

## Warum

Phase 36 brachte deklarative Pipelines + Expectations, Phase 144
Schema-Contract-Versioning, Phase 146 die Mesh-Health-Bänder. Die
*Bausteine* für Data-Quality sind also da — aber sie sind **fragmentiert
und flach**: 6 Contract-Assertion-Kinds hier, z-Score-Drift dort,
light-shape-Statistiken beim Write, Mesh-Health-Bänder (green/red/unknown)
woanders. Was fehlt, ist die **Verdichtung zu einem konsumierbaren
Qualitäts-Bild pro Data-Product** — ein Scorecard, der mehrere Dimensionen
zu einer Zahl/Bewertung rollt — und ein **harter Quality-Gate**, der einen
Write blockiert, wenn die Qualität unter Schwelle fällt.

Diese Phase macht aus verstreuten Checks eine **Qualitäts-Tiefe**:
reichere Profilierung, Anomalie-Erkennung als laufende Signale, ein
per-Product-Scorecard, und ein vor-dem-Write durchsetzbares Quality-Gate.

## Ausgangslage (Fakten)

- **Contract-Tests (Phase 36)**
  ([`models/catalog/_contract_test.py:38-50`](../../pointlessql/models/catalog/_contract_test.py)):
  6 Assertion-Kinds (row_count_range, column_present, value_distribution,
  null_rate, referential, freshness), Severities info/warn/error.
  Evaluator [`services/contract_tests/_assertions.py:43`](../../pointlessql/services/contract_tests/_assertions.py),
  Runner [`_runner.py:66-158`](../../pointlessql/services/contract_tests/)
  (synthetic + live), Result-Ledger.
- **Profilierung heute:** `table_stats.py` (on-demand DuckDB: count/null/
  distinct≈/min/max/mean/top_5, Ceiling 10k),
  [`data_product_stats.py`](../../pointlessql/services/data_product_stats.py)
  (`light_shape` beim Write: null_count + distinct je Spalte,
  `DataProductStatistics`-Snapshot).
- **Anomalie-Heuristiken vorhanden:** z-Score-Drift
  ([`services/slo/_drift.py:26-145`](../../pointlessql/services/slo/_drift.py),
  row_count + null_ratio:* gegen N Snapshots), Audit-Anomalie
  ([`audit_aggregator/_anomaly.py:47-238`](../../pointlessql/services/audit_aggregator/),
  rolling-window σ-Klassifikation), API-Key-WoW + 3σ
  ([`api_keys/_usage.py:142-239`](../../pointlessql/services/api_keys/)).
- **Before-Write-Hooks** ([`pql/_hooks.py`](../../pointlessql/pql/_hooks.py)):
  geordnete Kette (bitemporal → ISO-8601 → schema-versioning → policy);
  `run_before_write(frame, context)` darf abbrechen — **der
  Einklink-Punkt für ein Quality-Gate.** Registrierung nur additiv.
- **Mesh-Health (Phase 146)**
  ([`services/mesh/_health.py:33-105`](../../pointlessql/services/mesh/_health.py)):
  pro Product band (green/red/unknown) + pass/fail/unmeasured + pass_rate;
  Worst-Offenders. Routes [`api/mesh_routes.py`](../../pointlessql/api/mesh_routes.py).
- **SLO-Kinds** ([`services/slo/_kinds.py`](../../pointlessql/services/slo/_kinds.py)):
  6 messbar (freshness/volume/completeness/statistical_shape/lineage/
  interval_of_change), 4 declaration-only.
- **Signals-Ledger** ([`services/signals.py:77-226`](../../pointlessql/services/signals.py)):
  open/resolved-Karten, dedupe je (kind, workspace, entity), SSE-Publish.
- **Freshness-SLA-Scanner**
  ([`data_product_freshness_scanner.py:106-224`](../../pointlessql/services/data_product_freshness_scanner.py)):
  Delta-`history()` → `sla_violated`-CloudEvent.
- **DP-Detail-Tabs** ([`api/data_products_html_routes.py`](../../pointlessql/api/data_products_html_routes.py)):
  Overview/Contract/Diff/Lineage/Compliance/Discussion — **kein
  Quality/Scorecard-Tab.**

## Scope (Wellen)

### W1 — Reichere Profilierung
- `table_stats`/`data_product_stats` um quantile (p25/50/75/95), Pattern-/
  Format-Verteilung (z. B. Regex-Konformität für Email/Datum), Häufigkeit
  führender Kategorien, und einen reproduzierbaren Profil-Snapshot
  erweitern. High-cardinality-Ceiling respektieren (kein GROUP-BY-Blowup).
- Snapshot-Versionierung an `delta_log_version` koppeln (Cache-Konsistenz).

### W2 — Erweiterbares Expectation-Vokabular
- Über die 6 Kinds hinaus: uniqueness, monotonic, set-membership,
  cross-column (a≤b), conditional (wenn X dann Y), regex_match. Als
  Plugins ins vorhandene `_assertions.py`-Dispatch (gleiches AssertionVerdict-
  Shape, gleiche Severities) — keine neue Engine.

### W3 — Anomalie-Erkennung als laufendes Signal
- Die vorhandene z-Score-Drift + Audit-σ zu einem `services/` -Job
  zusammenführen, der je Product/Tabelle Metrik-Anomalien erkennt und in
  den **Signals-Ledger** emittiert (open/resolved, dedupe) — statt nur
  ad-hoc berechnet zu werden. Re-Alert-Suppression wie beim Freshness-
  Scanner.

### W4 — Quality-Scorecard pro Data-Product
- `services/quality/_scorecard.py`: rollt Contract-Test-Ergebnisse +
  SLO-Verdicts + Drift + Freshness zu einem per-Dimension- und einem
  Gesamt-Score je Product (gewichtet, transparent — kein Black-Box-Index).
  Erweitert `mesh/_health.py` um die Dimensions-Aufschlüsselung.
- Neuer **Quality-Tab** auf der DP-Detail-Seite + `/api/.../quality`-Route
  + `/api/.../scorecard`. Mesh-Health-Seite zeigt Scorecard-Rollup.

### W5 — Quality-Gate vor dem Write
- Before-Write-Hook `quality_gate`: liest den letzten Scorecard/relevante
  Live-Assertions; im Modus off/warn/block (analog schema-versioning
  `_enforcer.py`). Block → `QualityGateError`, Signal emittiert, Write
  abgebrochen. Standard warn (nicht überraschend brechen).

### W6 — Doku + e2e
- mkdocs „Data Quality": Expectation-Katalog, Scorecard-Lesen, Gate-Modi.
  e2e-Playbook (Phase 198): Expectation deklarieren → verletzen →
  Scorecard rot → Gate blockt.

## Akzeptanzkriterien
- Neue Expectation-Kinds evaluieren über denselben Runner + Ledger; ein
  verletzter Check erscheint im Result-Ledger.
- Anomalien erscheinen als Signal-Karten (open/resolved, dedupe), nicht
  nur als Einmal-Berechnung.
- Jedes Data-Product hat einen Scorecard (per-Dimension + Gesamt) im neuen
  Quality-Tab und über `/api/.../scorecard`.
- Der Quality-Gate blockt im `block`-Modus einen Write unter Schwelle und
  emittiert ein Signal; `warn` lässt durch + warnt; `off` ist no-op.
- Mesh-Health zeigt den Scorecard-Rollup; lädt gegen SQLite + Postgres.

## Risiken / Notizen
- **Scoring-Transparenz:** Gewichtung explizit + dokumentiert; ein
  undurchschaubarer „Quality 73"-Index ist wertlos für Stewards.
- Profilierungs-Kosten: schwere Profile nur on-demand/scheduled, nicht im
  Write-Hot-Path (Phase 199 misst).
- Gate-Default `warn` — `block` ist opt-in pro Product/Workspace, sonst
  überraschende Write-Abbrüche.
- Verwandt: Phase 36 (Expectations), Phase 144 (schema-versioning als
  Gate-Vorbild), Phase 146 (Mesh-Health), Phase 200 (SLO/Signals teilen
  Infra), Phase 197 (Lineage als eigene Korrektheits-Achse).
