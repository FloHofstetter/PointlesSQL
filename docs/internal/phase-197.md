---
title: "Phase 197 — Lineage-Korrektheits-Verifikations-Engine (plan)"
audience: contributor
---

# Phase 197 — Lineage-Korrektheits-Verifikations-Engine

**Status: ⏳ planned (geplant 2026-06-06).** Detail-Sidecar für den
ROADMAP-Eintrag; siehe [ROADMAP.md](../../ROADMAP.md) für den
Cluster-Kontext (Differentiator-Tiefe-Cluster 197–206). Diese Phase
realisiert die in Phase 192 vorgemerkte „End-to-End-Lineage-Korrektheit
über *alle* PQL-Pfade".

## Warum

Row-/Column-/Value-Level-Lineage ist der härteste DBX-Differenzierer der
Plattform — und genau deshalb der teuerste, wenn er still falsch ist. Der
Lineage-Wiring-Audit (Phase 15.8) fand einen **echten** Korrektheits-Bug:
ein silver-`PQL.sql`-SELECT droppte `_lineage_row_id` aus der Projektion,
wodurch `demo_ml.silver.*` **0 Edges** produzierte. Heute existiert dafür
genau eine INFO-Log-Diagnose
([`_sql.py:172-183`](../../pointlessql/pql/_sql.py)) plus ein einzelner
Negativ-Test
([`test_lineage_wiring_contract.py:341`](../../pointlessql/tests/test_lineage_wiring_contract.py)).

Das ist ein *punktueller* Fix, keine *Garantie*. Die Lineage-Korrektheit
hängt heute an ~12 Beispiel-Tests (~2885 LOC, alle „happy path"), nicht an
einer systematischen Eigenschaft. Jeder neue PQL-Operator, jede
sqlglot-Version, jeder Merge-Pfad kann Lineage lautlos brechen. Diese Phase
baut eine **Verifikations-Engine**, die Lineage-Korrektheit als
*Invariante* über alle PQL-Pfade beweist — property-based (Hypothesis) +
Golden-Corpus — statt sie pro Beispiel zu hoffen.

## Ausgangslage (Fakten)

- **4 Lineage-Tabellen** ([`models/lineage/_core.py`](../../pointlessql/models/lineage/_core.py)):
  `LineageRowEdge` (65-144), `LineageRowReject` (146-201),
  `LineageColumnMap` (203-288), `LineageValueChange` (290-352).
- **Row-ID-Propagation:** `_prepare_lineage()`
  ([`_merge/_lineage.py:174-207`](../../pointlessql/pql/_merge/_lineage.py))
  extrahiert Source-`_lineage_row_id`, synthetisiert deterministisch
  `synth_target_row_id(source_row_id, target_table)` (SHA-256,
  [`services/lineage/_types.py:247`](../../pointlessql/services/lineage/_types.py)).
- **Operator-Oberfläche** ([`pql/_pql_data.py:42-61`](../../pointlessql/pql/_pql_data.py)):
  `_ReadMixin`, `_WriteMixin`, `_SqlMixin`, `_AggregateMixin`,
  `_UpdateDeleteMixin`, `_AutoloadMixin`, `_VectorMixin`; Governance
  (`rollback`/`branch`/`promote`/`discard`) in
  [`_pql_governance.py`](../../pointlessql/pql/_pql_governance.py).
- **Value-Capture** ([`value_change_capture.py:42-112`](../../pointlessql/services/value_change_capture.py)):
  paart `update_preimage`/`update_postimage` via CDF auf `_lineage_row_id`.
- **Post-Commit-Hook-Kette**
  ([`services/agent_runs/operations/_lifecycle.py:343-355`](../../pointlessql/services/agent_runs/operations/_lifecycle.py)):
  `record_rejects_after_commit` → `record_edges` →
  `record_value_changes_after_commit`.
- **OpenLineage-Emission:** `emit_event_sync()`
  ([`soyuz_lineage.py:135-229`](../../pointlessql/services/soyuz_lineage.py)),
  POST via `_ingest.sync` — best-effort, nie blockierend.
- **Hypothesis ist KEINE Dependency** (geprüft in `pyproject.toml`); kein
  Golden-/Snapshot-Muster im Repo. Beides ist neu zu legen.
- **Bekannter Bug-Detektor** stempelt nur `lineage_row_id_dropped_at_select`
  in `params_json` — er *meldet*, er *verhindert* nicht.

## Scope (Wellen)

### W1 — Lineage-Invarianten formalisieren
- Ein `docs/internal/lineage-invariants.md`: die N harten Invarianten
  präzise (Bsp.: *„Jede Output-Zeile eines lineage-tragenden Writes hat
  genau eine row-edge-Kette zurück zu mindestens einer Source-Zeile, außer
  sie steht im Reject-Ledger mit Grund."*, *„column_map deckt jede
  nicht-konstante Output-Spalte ab."*, *„value_changes ⊆ CDF-update-Paare."*).
- Pro Invariante ein **Checker** (`services/lineage/verify/_invariants.py`):
  reine Funktion `(operation_result, lineage_tables) -> list[Violation]`.
  Keine I/O, voll unit-testbar — das ist der Kern, den alles andere füttert.

### W2 — Hypothesis-Generatoren für PQL-Pipelines
- `hypothesis>=6` als Test-Dependency (dev-group).
- `tests/lineage_verify/strategies.py`: Strategien, die *gültige* kleine
  Medallion-Pipelines erzeugen — DataFrames (Schema + Zeilen) × Operator-
  Ketten (autoload → sql/aggregate/merge/update → write). Deterministisch
  geseedet (CI-stabil, kein `Date.now`/`random` in Fixtures).
- Property-Test: für jede generierte Pipeline laufen alle W1-Checker grün.
  Shrinking liefert das minimale brechende Beispiel automatisch.

### W3 — Operator-Abdeckung (eine Welle Tiefe pro Operator)
- Je Operator-Mixin eine eigene Property-Klasse, in Reihenfolge der
  Bruch-Wahrscheinlichkeit: **sql** (Projektion/Join/CTE — der 15.8-Pfad,
  inkl. sqlglot-AST-Spaltenauflösung), **merge** (inkl. rejects:
  `on_key_null`, `duplicate_in_source`), **aggregate** (Group-Key-Lineage-
  Synthese), **update/delete**, **autoload** (Initial-ID-Prägung),
  **branch/promote/discard** + **time-travel** (row-ID-Stabilität über
  Versionen), **federation/CDF-Tail** (Foreign-Delta).
- Jede Welle schließt mit: brechende Fälle an der **Quelle** gefixt (nie
  maskiert — der `_sql.py`-Detektor wird von „melden" zu „korrekt
  projizieren oder bewusst-explizit verwerfen" gehärtet).

### W4 — Golden-Corpus + Differential-Harness
- Kuratiertes `tests/lineage_verify/corpus/`: deterministische Pipelines
  mit eingefrorenen erwarteten Edge-/Column-/Value-Mengen (JSON-Snapshots,
  diff-bar reviewbar). Fängt Regressionen, die Hypothesis statistisch
  verpassen könnte (seltene Spaltennamen, Unicode-Keys, NULL-Keys).
- Differential-Check: die in `soyuz_lineage.emit_event_sync` emittierten
  OpenLineage-Facets müssen mit den lokalen Lineage-Tabellen
  übereinstimmen (kein Drift zwischen interner Wahrheit und exportiertem
  Graph).

### W5 — CI-Verdrahtung
- Property-Suite + Golden-Corpus als eigener pytest-Marker
  (`@pytest.mark.lineage_verify`), im PR-Gate (begrenztes Hypothesis-
  `max_examples`) + Nightly (großes Budget, mehr Beispiele).
- Coverage-Ledger: welche Operatoren/Invarianten property-gedeckt sind
  (verhindert stille Lücken bei neuen Operatoren).

## Akzeptanzkriterien
- Jeder PQL-Operator aus `pql/_pql_data.py` + Governance hat mindestens
  eine grüne Property-Klasse; der Coverage-Ledger zeigt 100 %.
- Ein absichtlich wieder eingebauter „SELECT droppt `_lineage_row_id`"
  lässt die Property-Suite (nicht nur den INFO-Log) **fehlschlagen**.
- Golden-Corpus-Snapshots sind committet und im PR-Gate grün.
- Lokale Lineage-Tabellen und emittierte OpenLineage-Facets stimmen im
  Differential-Check bit-genau überein.
- Kein neuer `# type: ignore`, keine stillen Caps, keine maskierten Brüche.

## Risiken / Notizen
- **Nicht-Determinismus** ist der Hauptfeind: SHA-256-IDs sind
  deterministisch, aber CDF-Reihenfolge + dict-Ordering müssen in Checkern
  sortiert verglichen werden.
- Hypothesis-Pipelines müssen *gültig* bleiben (kein Test der Fehlerpfade
  hier) — invalide Eingaben gehören in separate Negativ-Tests.
- Federation/CDF-Pfade brauchen ggf. den `requires_soyuz`-Marker (siehe
  Phase 198); reine PQL-Pfade laufen ohne Live-Server.
- Verwandt: Phase 15.5–15.8 (Lineage-Aufbau), Phase 192 (Differentiator-
  Wette), [[mutmut-harness-setup]] (Mutation-Gate deckt die Checker-Logik).
