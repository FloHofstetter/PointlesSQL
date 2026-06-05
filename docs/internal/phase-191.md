---
title: "Phase 191 — Pyright-Warning-Floor-Sweep (962 → Ratsche) (plan)"
audience: contributor
---

# Phase 191 — Pyright-Warning-Floor-Sweep

**Status: 🔜 next (geplant 2026-06-05).** Detail-Sidecar; siehe
[ROADMAP.md](../../ROADMAP.md) (Cluster Quality-Consolidation 189–191).

## Warum

Pyright-Errors stehen auf 0 (Hard-Gate). Warnings sind bei **exakt
962** eingefroren ([check-pyright-budget.sh](../../scripts/check-pyright-budget.sh),
`BUDGET=962`) — die Ratsche ist also bereits straff, kein Schlupf.
Aber ~894/962 sind die `reportUnknown*`-Familie, viel davon verwurzelt
in **untypisierten Nahtstellen**, wo unser Code Third-Party-`Any`
berührt (json/yaml/OpenLineage-Payloads, pyarrow/duckdb/pandas/
pycrdt-Ergebnisse).

Die bewiesene Methode (laut Budget-Skript-Changelog schon zweimal
angewandt: papermill-output-frame → typed helper killte eine Naht;
replay-worker frame-builders → drei) ist, **typisierte Grenzen an den
Unknown-Quellen einzuziehen.** Jede typisierte Grenze killt ein Bündel
kaskadierender Unknown*-Warnings und verbessert die Agent- und
Menschen-Wartbarkeit — direkt relevant, weil dies ein agent-first-
Codebase ist (starke Typen = Sicherheitsnetz für die Agents selbst).
Komponiert mit der NewType-ID-Härtung (Phase 47) — gleiche Richtung.

## Ausgangslage (gemessen 2026-06-05)

`uv run pyright pointlessql`: **0 errors, 962 warnings, 0 info.**

Regel-Verteilung:

| Anzahl | Regel | adressierbar? |
|-------:|-------|---------------|
| 374 | `reportUnknownVariableType` | teils (unsere Dicts/Parser) |
| 333 | `reportUnknownMemberType`   | teils |
| 187 | `reportUnknownArgumentType` | teils |
|  55 | `reportUnnecessaryIsInstance` | **nein** — bewusste defensive Checks (in pyproject dokumentiert) |
|  13 | `reportUnknownParameterType` | teils |

Top-Hotspot-Dateien (Warnings je Datei):

| n | Datei |
|--:|-------|
| 47 | `services/contract_tests/_assertions.py` |
| 31 | `services/lineage/inbound_parser.py` |
| 27 | `api/notebooks_routes/io.py` |
| 24 | `api/data_products_routes/_proposals_diff.py` |
| 24 | `pql/_merge/_lineage.py` |
| 24 | `services/lens/tools/query.py` |
| 22 | `pql/engine.py` |
| 20 | `api/catalog_routes/browse.py` |
| 19 | `api/notebook_coedit_ws/_remap.py` |
| 18 | `services/agent_runs/operations/_vector_rebuild.py` |
| 18 | `services/data_product_as_code/_planner.py` |
| 17 | `services/dp_canvas/_blocks/_columns.py` |
| 17 | `services/governance/_port_identity.py` |
| 15 | `pql/_vector.py`, `services/notebook/coedit.py` |
| 14 | `pql/_hashing.py`, `services/bitemporal/_stamp.py`, `services/notebook/_doc.py`, `value_change_capture.py` |

Der **irreduzible Floor** (laut Budget-Skript-Header, nicht anfassen):
pyarrow/pandas/Delta `pa.Table`/`ChunkedArray`-Interna,
DuckDB-Result-Objekte, pycrdt `Doc[Unknown]`, nbformat-Seams, plus
die 55 bewussten `isInstance`-Checks. Nur mit eigenen `.pyi`-Stubs
killbar → out of scope.

## Methode (das Typed-Boundary-Pattern)

Pro Hotspot die **Quelle** des Unknown finden — meist ein
`json.loads`/`yaml.safe_load`/Generated-Client-Response/pyarrow-
Result, das als `Any`/`Unknown` eintritt und dann durch `.get()`-Ketten
kaskadiert. Fix an der Naht:

- JSON/YAML-Payload mit bekannter Form → **TypedDict** (oder
  pydantic-Modell) + eine typisierte Parse-Funktion; Downstream liest
  typisierte Felder, Kaskade verschwindet. **`total=False` / extra-
  tolerant** für producer-emittierte Dokumente (OpenLineage), damit
  ein neuer Facet nicht *errort*.
- pyarrow/duckdb/pandas-Result → dünner typisierter Wrapper/Adapter,
  der konkrete Typen an der Aufruf-Grenze zurückgibt (papermill/
  replay-worker-Präzedenz).
- Echt-Third-Party-Stub-verwurzelt → liegenlassen (irreduzibler Floor).

## Scope (Wellen — BUDGET je Welle senken)

### W1 — Lineage / OpenLineage-Payload-Naht (höchste Konzentration)
- `inbound_parser.py` (31) + `pql/_merge/_lineage.py` (24) +
  angrenzendes `soyuz_lineage`: die OpenLineage-Facet-Dokumente, die
  der Parser konsumiert, als TypedDicts modellieren (run/job/dataset-
  Facets), einmal in typisierte Strukturen parsen.
- `BUDGET` um den gemessenen Drop senken, mit Einzeiler-Notiz im
  Skript (Stil wie die bestehenden `966 -> 965`-Kommentare).

### W2 — Contract-Tests + Data-Product-YAML-Naht
- `contract_tests/_assertions.py` (47) — die größte Einzeldatei; die
  Assertions konsumieren geparste Contract/Spec-Dokumente → TypedDict
  für die Contract-Spec-Form.
- `_proposals_diff.py` (24) + `data_product_as_code/_planner.py` (18) —
  der DP-as-Code-YAML-Round-Trip; typisiertes Modell fürs DP-as-Code-
  Dokument.
- `BUDGET` senken.

### W3 — Notebook + Co-Edit-JSON-Naht
- `notebooks_routes/io.py` (27) + `notebook_coedit_ws/_remap.py` (19)
  + `notebook/_doc.py` (14) — nbformat / percent-Grammatik / CRDT-
  Remap-Payloads. nbformat ist teils Third-Party-Stub-verwurzelt
  (Budget-Skript erwähnt es) → das Eigene typisieren (percent-cell/
  doc-Strukturen), die irreduzible nbformat-Naht lassen.
- `BUDGET` senken.

### W4 — Lens/Query + Catalog-Browse + Rest-Tail
- `lens/tools/query.py` (24), `catalog_routes/browse.py` (20),
  `value_change_capture.py` (13), `bitemporal/_stamp.py` (14),
  `governance/_port_identity.py` (17), `dp_canvas/_blocks/_columns.py`
  (17) — typisierte Grenzen, wo die Quelle ein **eigenes** Dict ist;
  reine pyarrow/duckdb-Stub-Warnings überspringen.
- Finaler Ratschen-Schritt; den Rest-Floor (irreduzibel + 55 bewusste
  isInstance) als neues permanentes Budget mit der Begründung
  (steht schon im Skript-Header) dokumentieren.

## Akzeptanzkriterien
- Nach jeder Welle: `bash scripts/check-pyright-budget.sh` grün mit
  **gesenktem** Budget; die Senkung inline notiert.
- 0 errors durchgängig erhalten (Hard).
- **Keine pauschalen `# type: ignore`-Suppressions** — Fixes sind echte
  typisierte Grenzen. Ein gezieltes `ignore` mit Begründung ist nur für
  eine dokumentierte Third-Party-Stub-Naht akzeptabel.
- pydoclint + ruff bleiben grün (neue öffentliche TypedDicts bekommen
  Google-style-Docstrings).
- Ziel: 962 → dokumentierter Rest-Floor (Schätzung ~650–700 nach den
  vier Wellen; die exakte Zahl ist, was die Grenzen real killen — **kein
  Target-Padding, keine stillen Caps**).

## Risiken / Notizen
- „Unser untypisiertes Dict" vs. „Third-Party-Stub-Lücke" pro Warning
  zu unterscheiden braucht Urteil — der Budget-Skript-Header zählt die
  irreduziblen Quellen auf; als Do-not-bother-Liste nutzen.
- Manche Unknown-Warnings verschwinden erst, wenn die Naht typisiert
  **und** die nachgelagerte `.get()`-Kette auf typisierte Felder
  umgeschrieben ist — den Rewrite mit einbudgetieren, nicht nur das
  TypedDict.
- OpenLineage-TypedDicts: `total=False`/extra-tolerant gegen
  Producer-Drift (neuer Facet darf nicht erroren).
