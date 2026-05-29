# Data Mesh — Plattform-Anforderungen & Gap-Analyse für PointlesSQL

> Arbeitsdokument. Quelle: Zhamak Dehghani, *Data Mesh* (dt. Ausgabe,
> O'Reilly 2023). Kapitelweise durchgearbeitet: Teil I (Prinzipien
> Kap 1–5), Teil III (Logische Architektur Kap 9–10), Teil IV
> (Affordances Kap 11–14), Teil V (Reifegradmodell Kap 15).
> Ist-Zustand: Codebase-Inventur PointlesSQL + soyuz-catalog, Mai 2026.
>
> Ziel: ableiten, welche Plattform-Capabilities PointlesSQL noch
> braucht, um eine erstklassige Data-Mesh-Plattform zu sein — und wo
> wir schon Bausteine haben. Legende: ✅ vorhanden · 🟡 teilweise ·
> ❌ fehlt.

---

## TL;DR

PointlesSQL hat einen **überraschend starken Unterbau** für Data Mesh:
Datenprodukt als First-Class-Objekt mit Schema-Contract + Versionierung
+ Steward + Freshness-SLA, dreistufige Katalog-Discovery, Lineage
(Tabelle/Spalte/Row), PQL-Zugriffsbrücke + SQL-API, Notebooks/dbt/
Scheduler als Self-Serve-Transform, Audit-Log + PII-Masking + Anomaly-
Inbox, Delta-Branching + Time-Travel, und — als Alleinstellungsmerkmal —
eine **Agent-Supervision-Ebene** (`agent_run_operations`), die exakt zur
agent-nativen Data-Mesh-Vision passt.

Es fehlen drei **strukturelle** Dinge, die das Buch ins Zentrum stellt:

1. **Domain Ownership als Entität** (Prinzip 1). Heute ist Ownership
   nur user-skaliert (`steward_user_id`). Es gibt kein `Domain`/`Team`,
   keine Zuordnung „Domäne besitzt Katalog/Schema/Produkt". → Verifiziert
   leer: kein `Domain`/`Team`-Modell in `pointlessql/models/`.
2. **Das Datenprodukt ist heute *passive Metadaten*, kein aktives
   *Architekturquantum*.** Es gibt Contract + Freshness-SLA, aber keine
   Input-/Output-/Discovery-/Control-Ports, kein gebündeltes
   Transformations-Code-Artefakt, keine eingebetteten Policies, keinen
   multimodalen Zugriff, keine Selbst-Registrierung über eine
   standardisierte Discovery-URI.
3. **Federated *Computational* Governance** (Prinzip 4). Heute zentrale
   PQL-/UC-Privilege-Checks + Write-Contract-Enforcement. Es fehlt
   Policy-as-Code pro Produkt (PII-Klassifizierung, Retention,
   Encryption-Klasse, Consent, Residency), ein Control-Port und ein
   Sidecar-Mechanismus, der Policies *am Zugriffspunkt* ausführt.

Der Rest ist großteils Ausbau auf vorhandenem Fundament.

---

## 1. Das Data-Mesh-Mentalmodell (für Kontext)

**Vier Prinzipien:** Domain Ownership · Data as a Product · Self-Serve
Data Platform · Federated Computational Governance.

**Datenprodukt = Architekturquantum** (Kap 9): kleinste unabhängig
deploybare Einheit aus **Code** (Transformation + Schnittstellen +
Policy-Ausführung + Doku-Generierung), **Daten + Metadaten** (polyglott,
Datenmodelle, Doku, SLOs, Lineage, Policy-Configs) und
**Infrastruktur-Abhängigkeiten** (Compute, Storage). Es exponiert vier
**Ports**: Input · Output · Discovery/Observability · Control. Ein
**Sidecar** (von der Plattform injiziert) führt querschnittliche Policies
einheitlich aus; ein **Container** kapselt alles.

**Drei Plattform-Ebenen** (nicht-hierarchische *Planes*):
Dateninfrastruktur · Datenprodukt · Mesh.

**Kernmaxime:** Linksverschiebung (Discovery/Quality/Policy entstehen
*am Produkt*, nicht nachträglich zentral); kein zentraler Koordinator;
Mesh-Eigenschaften (Lineage-Graph, Wissensgraph, Mesh-Health)
*emergieren* aus lokalen Regeln pro Produkt.

---

## 2. Was PointlesSQL heute schon kann (gemappt auf die Prinzipien)

| Data-Mesh-Baustein | Status | Wo in PointlesSQL |
|---|---|---|
| Datenprodukt als benanntes Objekt + Schema-Contract + SemVer + Steward | ✅ | `models/catalog/_data_products.py`, `data_products/_schema.py` (yaml-kanonisch) |
| Write-Contract-Enforcement (compliant/drift/violated) | ✅ | `data_products/_enforce.py`, `data_product_contract_events` |
| Katalog-Discovery (Catalog→Schema→Table→Column) + Suche + Feed + Follows | ✅ | `catalog_html_routes.py`, `/api/tree/search`, `/data-products`, `/feed` |
| Lineage Tabelle + Spalte + Row (CDF) + Cross-Federation | ✅ | `models/lineage/`, `/api/lineage*` |
| Multi-Persona-Zugriff (SQL-IDE, Preview, PQL-DataFrame, externe SQL-API) | 🟡 | `pql/`, `/api/sql/*`, `/sql` (kein File-/Event-Port) |
| Self-Serve-Transform (Notebooks, dbt, Scheduler, Dataflow-Canvas) | ✅ | `/notebooks`, `/api/dbt/*`, `models/scheduler.py`, `/canvas` |
| Audit-Log + PII-Masking + Anomaly-Inbox | 🟡 | `models/audit/_log.py`, `_pii.py`, `_anomaly.py` |
| Zugriffskontrolle (UC-Privilegien, Effective Permissions) | 🟡 | `authorization.py` (zentral, nicht pro-Produkt-Policy-as-Code) |
| Freshness-SLA + Scanner | 🟡 | `sla_minutes`, Freshness-Loop (nur 1 von ~8 SLO-Typen) |
| Versionierung (Delta Time-Travel, Branching, Notebook-Revisions) | ✅ | `time_travel_routes.py`, `branches_routes.py`, `_revisions.py` |
| Föderation über Fremdkataloge | 🟡 | UC Foreign Catalogs, `models/catalog/_sync.py` |
| **Agent-Supervision (Runs/Operations, Approvals, NL→SQL)** | ✅ | `models/agent/_runs.py`, `agent_run_operations`, Hermes-Plugin |

---

## 3. Gap-Analyse nach Capability-Bereichen

### A. Domain Ownership (Prinzip 1) — größte konzeptionelle Lücke

| # | Data-Mesh-Anforderung | Status | Was zu bauen ist |
|---|---|---|---|
| A1 | `Domain`/`Team` als Entität; Domäne besitzt Kataloge/Schemas/Produkte | ❌ | Neues `domains` + `domain_members` Modell; Datenprodukt + Katalog erhalten `domain_id` |
| A2 | Rollen **Data Product Owner** (Verantwortung) + **Data Product Developer** (Bau) pro Domäne | 🟡 | Steward → Owner-Rolle erweitern; Developer-Rolle ergänzen; mehrere Personen pro Produkt |
| A3 | Domänen-Archetypen (quellen-/aggregat-/konsumentenorientiert) als Klassifizierung | ❌ | Enum-Feld am Produkt; UI-Badge; steuert Discovery-Filter |
| A4 | Ownership-Heuristik für aggregierte Produkte (föderale Entscheidung) | ❌ | Governance-Workflow (siehe E) |

> Begründung: ohne Domänen-Entität bleibt „Federated" leer — das
> föderale Governance-Team (E) und lokale vs. globale Policies brauchen
> Domänen als Adressaten. **Das ist der Grundstein für Phase 2.**

### B. Datenprodukt-Quantum: strukturelle Komponenten & Ports (Kap 9)

| # | Data-Mesh-Anforderung | Status | Was zu bauen ist |
|---|---|---|---|
| B1 | **Output-Ports**: extern adressierbare APIs, mehrere Zugriffsmodi (SQL ✅, spaltenbasierte Files, Event-Stream) | 🟡 | Output-Port-Deklaration im Contract; File-Export-Port (Parquet); optionaler Event/Pub-Sub-Port |
| B2 | **Input-Ports**: deklarierte Upstream-Quellen (op. System / Upstream-Produkt / extern); Input triggert Transformation | ❌ | `inputs:`-Block im Contract → daraus *deklarierter* Lineage-Graph (statt nur Runtime-Capture) |
| B3 | **Discovery-Port + globale URI**: standardisierte Selbstbeschreibung als Einstiegspunkt | 🟡 | `/api/data-products/{id}/discovery` als standardisierter, maschinenlesbarer Vertrag (Semantik, Doku, Output-Ports, SLOs, Stats); stabile URI/IRI je Produkt |
| B4 | **Control-Port**: Policy-Konfiguration + privilegierte Ops (z.B. Right-to-be-forgotten) | ❌ | Neuer Endpunkt-Satz pro Produkt (siehe E) |
| B5 | **Code als Teil des Quantums**: Transformation gebündelt mit Produkt | 🟡 | Notebook/dbt-Model **an Produkt binden** (FK), sodass „dieses Produkt = diese Transformation + dieser Output" |
| B6 | **Sidecar**: plattform-injizierte, einheitliche Querschnittsfunktionen (SLO-Reporting, Policy-Ausführung) | ❌ | Logisches Sidecar = gemeinsamer Service-Layer, der bei jedem Read/Write des Produkts Policies + Metriken ausführt |
| B7 | Selbst-erzeugte Metadaten (Produkt generiert eigene Stats/SLOs, nicht extern extrahiert) | 🟡 | Beim Write Statistical-Shape + SLO-Metriken am Produkt stempeln (analog `contract_events`) |
| B8 | Plattform-Abhängigkeiten deklarativ (Retention, Zugriffsmethoden, Storage) | ❌ | `infrastructure:`-Block im Contract |

### C. Die acht Usability-Attribute (Kap 3)

| Attribut | Status | Lücke / To-Build |
|---|---|---|
| Auffindbar (discoverable) | ✅/🟡 | Katalog + Suche + Feed da; fehlt *self-publish* Discovery-Vertrag (B3) + konsumenten-beigesteuerte Use-Cases |
| Adressierbar (addressable) | 🟡 | `catalog.schema` als Adresse; fehlt globale stabile URI + adressierbarer „Aggregate Root" über alle Facetten |
| Verständlich (understandable) | 🟡 | Spalten-Beschreibungen + Comments da; fehlt **semantisches Modell** (Entitäten/Beziehungen), Sample-Data + Sample-Code im Vertrag, „benachbarte Produkte" |
| Vertrauenswürdig (trustworthy) | 🟡 | Freshness-SLA + Contract-Events + Lineage da; fehlt voller **SLO-Satz** (s.u. D8) |
| Nativ zugreifbar (natively accessible) | 🟡 | SQL/DataFrame da; fehlt File- + Event-Modus (multimodal, B1) |
| Interoperabel (interoperable) | ❌ | Fehlt: gemeinsames Typsystem, **polysemer Identifikator** (entity ID über Produkte), gemeinsame Metadatenfelder (business time + processing time), Schema-/Data-Linking, Schema-Stabilitätsregeln |
| Eigenständig nützlich (valuable on its own) | 🟡 | Konvention; Plattform sollte Glue-/Fact-Tables verstecken statt als Produkt zu führen |
| Sicher (secure) | 🟡 | UC-Privilegien + PII-Masking da; fehlt Policy-as-Code am Zugriffspunkt, Encryption-Klassen, „shape-but-not-rows"-Zugriff (E) |

### D. Die acht Affordances (Kap 11–14)

| Affordance | Status | Lücke / To-Build |
|---|---|---|
| D1 Daten **bereitstellen** (immutable, **bitemporal**, read-only, multimodal) | 🟡 | Delta liefert immutable + Versions-Zeit; fehlt **Bitemporalität** (business/event time + processing time) + multimodale Output-Ports |
| D2 Daten **konsumieren** (nur deklarierte Quellen) | ❌ | Input-Ports (B2); heute konsumieren Notebooks/dbt frei, ohne deklarierten Vertrag |
| D3 Daten **transformieren** (Code/ML/Query, gekapselt im Produkt) | ✅/🟡 | Transform da (Notebooks/dbt/PQL); fehlt Bindung an Produkt (B5) |
| D4 Daten **finden/verstehen/vertrauen** | 🟡 | siehe C (discoverable/understandable/trustworthy) |
| D5 Daten **kombinieren** (Set- + **Graph**-Operationen, Cross-Produkt-Join) | 🟡 | SQL-Join innerhalb Katalog da; fehlt Graph-/Property-Graph-Zugriff, Schema-/Data-Linking-Helfer über Produkte |
| D6 **Lebenszyklus verwalten** (Build/Test/Deploy/Run-Configs) | 🟡 | Scheduler + dbt-Lifecycle da; fehlt einheitlicher Produkt-Lifecycle (init→build→test→deploy→retire) über alle Produkte |
| D7 Daten **beobachten/debuggen/auditieren** (Logs, Runtime-Metriken, Lineage, Access-Logs, Traces, Correlation-IDs) | 🟡 | Audit-Log + Anomaly + Lineage da; fehlt einheitliche Runtime-Metriken + Correlation-IDs + Mesh-Health (G) |
| D8 Daten **regeln** (Policies-as-Code, build-time konfiguriert, runtime am Zugriff ausgeführt) | ❌ | siehe E |

### E. Federated Computational Governance (Kap 5 + Control-Port)

| # | Data-Mesh-Anforderung | Status | Was zu bauen ist |
|---|---|---|---|
| E1 **Policies-as-Code** pro Produkt: versioniert, getestet, deployt, überwacht | ❌ | Policy-Block im Contract (deklarativ) + Engine, die ihn ausführt |
| E2 **PII-/Vertraulichkeits-Klassifizierung** als Produkt-Deklaration | 🟡 | Masking existiert reaktiv am API-Rand; fehlt deklarative Klassifizierung (PII/PHI/Public) am Spalten-/Produkt-Contract → treibt Masking + Differential Privacy |
| E3 **Retention-Fristen** pro Produkt | ❌ | `retention:` im Contract + Enforcement-Loop |
| E4 **Encryption-Klassen** (at rest/in transit/in memory) + Key-Mgmt | ❌ | Deklaration + (mind.) at-rest/in-transit-Durchsetzung |
| E5 **Consent / Einwilligung** als wandernde Policy | ❌ | Consent-Tracking; Policy-Linking über Lineage hinweg |
| E6 **Data Residency / Sovereignty** | ❌ | Geo-Constraint-Deklaration (relevant erst bei Multi-Region) |
| E7 **Right-to-be-forgotten** als privilegierte Mesh-Op über alle Produkte | ❌ | Control-Port-Op + Mesh-weiter Fan-out + Lineage-getriebenes Löschen |
| E8 **Föderales Governance-Team + globale vs. lokale Policies** | ❌ | Modell + Workflow: globale Policy-Definition (Mesh-Ebene) → lokale Anwendung pro Produkt |
| E9 **Automatisiertes Monitoring der Policy-Compliance** (SLO-Scan, Toleranzen, Alerts, Trust-Downgrade) | 🟡 | Anomaly-Inbox da; fehlt Compliance-Scanner über SLO-APIs + Trust-Downgrade-Mechanik |
| E10 **Standardisierte Identität** (technologieunabhängig, OIDC/JWT) für Berechtigungen über Produkte | 🟡 | OIDC vorhanden (compose-overlay); fehlt einheitlicher Identitäts-/Berechtigungsvertrag pro Output-Port |

### F. Interoperabilität — die unterschätzte Querschnitts-Lücke

| # | Anforderung | Status | To-Build |
|---|---|---|---|
| F1 **Bitemporalität** (event/business time + processing time) als allgegenwärtiger Parameter | ❌ | Konvention + Helfer: jede Produkt-Tabelle führt beide Zeitstempel; PQL-API defaultet auf „latest/now" |
| F2 **Point-in-time-konsistente Cross-Produkt-Reads** (Reproduzierbarkeit, z.B. ML-Training) | 🟡 | Delta-Versionen da; fehlt produktübergreifender „as-of"-Snapshot-Read |
| F3 **Polysemer Identifikator** (globale Entity-ID über Produkte) | ❌ | Entity-Registry + Linking; Voraussetzung für sinnvolle Joins über Domänen |
| F4 **Semantischer Layer / Business-Glossar / Wissensgraph** | ❌ | Glossar-Entität + Term→Spalte-Bindung; emergenter Wissensgraph aus lokaler Semantik |
| F5 Gemeinsame Metadatenfelder + ISO-8601/SQL:2011-Zeitstandard | ❌ | Standard-Konvention, von Plattform erzwungen |

### G. Observability auf Mesh-Ebene

| # | Anforderung | Status | To-Build |
|---|---|---|---|
| G1 Voller **SLO-Satz** je Produkt (Interval-of-Change, Timeliness, Completeness, Statistical Shape, Lineage, Precision/Accuracy, Freshness/Availability/Performance) | 🟡 | Nur Freshness; Rest deklarieren + messen + reporten |
| G2 **Mesh-Health-Dashboard** (aggregiert SLO/Quality/Freshness über alle Produkte) | ❌ | Aggregations-View über Produkt-SLO-Metriken |
| G3 **Statistical-Shape-Monitoring** (Verteilung/Volumen/Range-Drift) | 🟡 | Anomaly-Detection da; an SLO-Vertrag koppeln |
| G4 **Correlation-IDs** für Cross-Produkt-Tracing | ❌ | Trace-ID durch PQL/Agent-Ops propagieren |
| G5 Emergenter **mesh-weiter Lineage-Graph aus lokal deklarierten Ports** | 🟡 | Lineage da, aber Runtime-captured; mit B2 (deklarierte Input-Ports) emergent machen |

---

## 4. Vorgeschlagene Phasen (am Reifegradmodell aus Kap 15)

Das Buch (Kap 15) beschreibt evolutionäre Reifegrade pro Prinzip-
Dimension — Plattformfunktionen wachsen *parallel zu* den Datenprodukten,
nicht vorab. Vorschlag in dieser Reihenfolge:

**Phase α — Domänen-Fundament** (ROADMAP: Phase 124) (A1–A4, B5): `Domain`/`Team`-Entität,
Produkt↔Domäne↔Owner/Developer, Transformation an Produkt gebunden.
Macht „Federated" überhaupt adressierbar.

**Phase β — Quantum-Ports & Discovery-Linksverschiebung** (ROADMAP: Phase 125) (B1–B3, B7,
C-discoverable/addressable/understandable, F4-Anfang): Output-/Input-/
Discovery-Ports im Contract; self-publish Discovery-URI; semantisches
Modell + Sample-Code; Produkt-generierte Stats.

**Phase γ — Computational Governance** (ROADMAP: Phase 126) (E1–E9, B4, B6): Control-Port +
Sidecar-Layer; Policy-as-Code (PII-Klasse, Retention, Encryption,
Consent); Right-to-be-forgotten; Policy-Compliance-Monitoring.

**Phase δ — Interoperabilität & Mesh-Observability** (ROADMAP: Phase 127) (D1-bitemporal, D5-
Graph, F1–F3, F5, G1–G5): Bitemporalität, polysemer Identifikator,
point-in-time-Reads, voller SLO-Satz, Mesh-Health-Dashboard, multimodale
Output-Ports (File/Event).

---

## 5. PointlesSQL-spezifischer Hebel: agent-nativ

Das Buch denkt „Data Product Developer" als Mensch. PointlesSQL hat
bereits eine **Agent-Supervision-Ebene** (`agent_run_operations`,
Approvals/Denials, NL→SQL, Hermes-Plugin). Das ist der Differenzierer:

- Der **Data Product Developer kann ein Agent sein**, der Transformation
  + Contract + Ports + Policies *vorschlägt*, mit Mensch als Owner/
  Supervisor im Control-Room (deckt sich mit der AI-native-Lakehouse-
  Vision).
- Die DM-Maxime „Policies/SLOs/Discovery entstehen am Produkt" passt
  natürlich zu „Agent stempelt diese beim Schreiben" — die vorhandenen
  `contract_events`/Lineage-Hooks sind genau der richtige Andockpunkt.
- Supervisions-Granularität bleibt **Operations**, nicht Cells (siehe
  bestehende Konvention) — Datenprodukt-Lebenszyklus-Ops (build/deploy/
  forget-user) reihen sich dort ein.

Empfehlung: Phase α + β nicht als reine Metadaten-Features bauen, sondern
so, dass Agenten Domänen-Zuschnitt, Contracts und Ports vorschlagen und
der Owner sie freigibt — das verbindet Data Mesh mit dem
Alleinstellungsmerkmal der Plattform.
