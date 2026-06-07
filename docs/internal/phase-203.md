---
title: "Phase 203 — Vollständige MCP-Agent-Oberfläche (plan)"
audience: contributor
---

# Phase 203 — Vollständige MCP-Agent-Oberfläche

**Status: ⏳ planned (geplant 2026-06-06).** Detail-Sidecar; siehe
[ROADMAP.md](../../ROADMAP.md) (Differentiator-Tiefe-Cluster 197–206). Die
strategische Wette des Clusters — passt zum Agent-first-Pivot (Phase
12.12) und der Differentiator-Vorgabe aus Phase 192.

## Warum

PointlesSQL hat sich auf agent-first gedreht (Browser-Editor gelöscht,
read-only Run-View gebaut), aber die **MCP-Oberfläche bleibt ein schmaler
Lesefenster**: 7 Lens-Tools (4× Katalog, Lineage-Nachbarn, Provenance,
Query) über einen 128-Zeilen-FastMCP-Wrapper. Ein Agent kann *fragen*, aber
kaum *handeln* — und das, obwohl die Plattform die volle governte
Schreib-/Governance-Maschinerie (PQL-Writes mit Lineage, Data-Products,
Policy-as-Code, Branching, Audit) bereits hat, nur eben nicht als
Agent-Tools exponiert.

Diese Phase macht die MCP-Oberfläche zur **vollwertigen, conformance-
getesteten Agent-API** auf die Plattform: Lesen *und* governtes Schreiben,
jede Mutation mit erzwungener Agent-Provenance, eine versionierte Tool-
Coverage-Matrix als Kontrakt — der eigentliche DBX-Differenzierer „agent-
native lakehouse".

## Ausgangslage (Fakten)

- **MCP-Transport vorhanden**
  ([`api/mcp/__init__.py`](../../pointlessql/api/mcp/__init__.py), 128 LOC):
  FastMCP SSE/HTTP — `/mcp/sse`, `/mcp/messages`, `/mcp/health`,
  `/mcp/info`. Bearer-Gate (`resolve_lens_key`, analyst+auditor). stdio
  via `LENS_API_KEY`; CLI `lens-mcp`
  ([`api/main.py:299`](../../pointlessql/api/main.py)). Dependency
  `mcp[cli]>=1.2`,
  [`services/lens/mcp_server.py:28`](../../pointlessql/services/lens/mcp_server.py).
- **7 Live-Tools (read-only)**
  ([`services/lens/tools/_registry.py:23-31`](../../pointlessql/services/lens/tools/_registry.py)):
  list_catalogs/schemas/tables, describe_table, lineage_neighbors,
  provenance (row+column+value), query (SELECT + cost-gate). Schema-
  Konverter `to_mcp_schemas`/`to_anthropic_schemas`/`to_openai_schemas`
  ([`tools/_base.py`](../../pointlessql/services/lens/tools/)). Jeder
  Dispatch → `execute_tool_with_audit` → `lens_messages`-Zeile
  ([`tools/_audit_hook.py:44`](../../pointlessql/services/lens/tools/)).
- **Agent-Provenance schon stark** ([`models/agent/`](../../pointlessql/models/agent/)):
  `AgentRun`, `AgentRunSource` (Quell-SHA, Tamper-Detection),
  `AgentRunOperation` (PQL-Primitive: input_sha/target/Delta-pre-post/
  rowcount), `AgentRunToolCall`, `AgentRunEvent` (CloudEvents).
  Tool-Call-Endpoint
  ([`api/agent_runs_routes/tools.py:29`](../../pointlessql/api/agent_runs_routes/tools.py)).
- **UC-Facade** ([`services/unitycatalog/`](../../pointlessql/services/unitycatalog/)):
  `UnityCatalogClient` + 6 Mixins (catalogs/metadata/permissions/lineage/
  federation/models), `wrap_catalog_errors`, per-Request `X-Principal`. **Der
  Aufruf-Layer, auf den MCP-Tools aufsetzen.**
- **Governte Schreib-Surface vorhanden** (heute nicht als MCP-Tool):
  PQL-Writes mit Before-Write-Hooks
  ([`pql/_hooks.py`](../../pointlessql/pql/_hooks.py): bitemporal,
  ISO-8601, schema-versioning, policy-as-code), SQL-Chat
  propose/accept-Flow, Data-Products, Branching.
- **Reflexive Tools (Phase 13.11):** `pql_*`-Schreib-Primitive über den
  Tool-Call-Endpoint; Hermes-Runtime besitzt die Ausführung, PointlesSQL
  Registry + Audit + CloudEvents-Fan-out.

## Scope (Wellen)

### W1 — Tool-Spezifikations-Framework + Coverage-Matrix
- Eine einheitliche Tool-Spec (Name, Kategorie, Input/Output-Schema,
  benötigter Scope, read|write, Audit-Pflicht, Idempotenz) — das
  bestehende `tools/_base.py` zur generischen Basis ausbauen (heute
  lens-spezifisch). `docs/internal/mcp-tool-matrix.md` generiert aus der
  Registry: der versionierte Kontrakt.
- Scope-Modell erweitern: heute analyst/auditor (read). Neue Schreib-/
  Governance-Scopes auf die vorhandene API-Key-Scope-Maschinerie + die 11
  `require_*`-Dependencies abbilden (kein paralleles Rechtemodell).

### W2 — Read-Surface vervollständigen
- Über die 7 Tools hinaus: Audit-Suche/Aggregation, SLO/Quality-Status,
  Cost-Status, Data-Product-Detail, Branch-Liste, Federation-Connections,
  Policy-Auswertung. Alle über die UC-Facade + vorhandene Services; alle
  mit Audit-Hook.

### W3 — Governtes Schreiben als Tools (der Sprung)
- Schreib-Tools, die durch **dieselbe** Hook-/Provenance-Kette laufen wie
  menschliche Writes: `pql_*` (autoload/merge/write/update), Tag-/Comment-
  Edits, Data-Product-Authoring, Branch create/promote/discard. Jeder
  Schreib-Tool-Call **erzeugt einen `AgentRun`/`AgentRunOperation`** (keine
  Mutation ohne Provenance — erzwungen, nicht optional).
- Approval-Gate-Hook: gefährliche Mutationen können `queued→approved`
  durchlaufen (das vorhandene AgentRun-Lifecycle), remote bestätigbar.

### W4 — Provenance-Erzwingung als Invariante
- Test/Checker: **keine** über MCP ausgelöste Mutation darf ohne
  `AgentRunOperation` + CloudEvent committen. Property-artig über alle
  Schreib-Tools (analog Phase 197).

### W5 — Conformance-Suite
- `tests/mcp_conformance/`: jedes Tool gegen sein deklariertes Schema
  (Input-Validierung, Output-Shape, Scope-Enforcement, Audit-Zeile
  geschrieben, Fehler-Envelope). Tabellengetrieben aus der Registry — neues
  Tool ohne Conformance-Eintrag failt.
- MCP-Protokoll-Smoke über echten Client (stdio + SSE): list_tools,
  call_tool, Auth-Reject.

### W6 — Doku + e2e
- mkdocs „Agent/MCP-Surface": Tool-Katalog, Scopes, Provenance-Garantie,
  Anschluss eines externen MCP-Clients. Hermes-/MCP-Playbooks (Phase 198)
  gegen die neue Surface.

## Akzeptanzkriterien
- Die generierte Tool-Coverage-Matrix listet jedes Tool mit Schema +
  Scope + read/write + Audit-Pflicht; CI failt bei Drift Registry↔Matrix.
- Lesen **und** governtes Schreiben sind über MCP möglich; ein
  MCP-ausgelöster Write durchläuft die volle Hook-Kette (bitemporal,
  schema-versioning, policy) identisch zum menschlichen Pfad.
- Keine MCP-Mutation ohne `AgentRunOperation` + CloudEvent (Checker grün;
  bewusst gebrochener Pfad failt).
- Conformance-Suite grün; ein Tool mit Schema-Mismatch failt.
- stdio- + SSE-Smoke gegen einen echten MCP-Client grün.

## Risiken / Notizen
- **Sicherheit zuerst:** Schreib-Tools erweitern die Angriffsfläche —
  Scopes strikt, Approval-Gate für destruktive Ops, alles auditiert.
  Eng mit Phase 202 (Authz-Matrix muss MCP-Routen/Scopes abdecken).
- Bug-an-der-Quelle: Schreib-Tools rufen *dieselben* Services wie die UI,
  kein paralleler Schreibpfad (sonst Lineage/Provenance-Drift).
- MCP-Spec-Versionsdrift (`mcp[cli]`): Conformance-Smoke fängt
  Protokoll-Brüche.
- Verwandt: Phase 12.12 (Agent-Pivot), Phase 13.11 (reflexive Tools),
  Phase 65 (Lens), Phase 197 (Provenance-Invarianten), Phase 202.
