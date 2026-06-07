---
title: "Phase 201 — Disaster-Recovery & Daten-Lebenszyklus (Backup/Restore + PITR) (plan)"
audience: contributor
---

# Phase 201 — Disaster-Recovery & Daten-Lebenszyklus

**Status: ⏳ planned (geplant 2026-06-06).** Detail-Sidecar; siehe
[ROADMAP.md](../../ROADMAP.md) (Differentiator-Tiefe-Cluster 197–206).

## Warum

Phase 30 machte Postgres *production-ready*, Phase 20 brachte
*Retention/TTLs*, Phase 16/16.5 *Rollback + Branching*. Was fehlt, ist die
Klammer: **Was passiert, wenn die Metadaten-DB stirbt?** Heute gibt es
keinen Backup-, keinen Restore-, keinen Point-in-Time-Recovery-Pfad und
keine Übung, die beweist, dass ein Restore *funktioniert*. Die
Lakehouse-Daten (Delta) und die Branch-/Lineage-/Audit-Wahrheit (eigene
DB) sind zwei separate Konsistenz-Domänen, die nach einem Restore
zueinander passen müssen — sonst zeigt das Audit-Cockpit auf Delta-Versionen,
die es nicht mehr gibt.

Diese Phase liefert verifizierbares DR: konsistente Snapshots beider
Domänen, PITR der eigenen DB, end-to-end durchgesetzte Retention, und einen
**Restore-Game-Day als CI-Job**, der regelmäßig beweist, dass ein Backup
wiederherstellbar *und* in sich konsistent ist.

## Ausgangslage (Fakten)

- **Eigene DB** ([`db.py:57-131`](../../pointlessql/db.py)): SQLite (WAL,
  default `sqlite:///{PROJECT_ROOT}/pointlessql.db`) oder Postgres
  (`POINTLESSQL_DB_URL`, pool recycle 1800s); Alembic-Migration bei Init.
  ~100+ ORM-Modelle ([`models/`](../../pointlessql/models/)), ~140+
  Migrationsdateien.
- **Retention/TTL existiert, aber verstreut:**
  - LineageRetentionSettings
    ([`config/_settings/_audit.py:19-48`](../../pointlessql/config/_settings/_audit.py)):
    row_edges/row_rejects 365d, value_changes 730d; Pruner täglich 03:00.
  - AuditSettings (50-97): audit_log 365d, cleanup täglich.
  - API-Key-Lifecycle-Sweep
    ([`services/api_keys/_lifecycle_sweep.py:41-142`](../../pointlessql/services/api_keys/_lifecycle_sweep.py)):
    Auto-Quarantäne expired keys.
  - SQL-Result-Retention 24h
    ([`config/_settings/_features.py:60-70`](../../pointlessql/config/_settings/_features.py)).
- **Bitemporal** ([`services/bitemporal/`](../../pointlessql/services/bitemporal/)):
  processing-time-Stempel + event-time-Validierung — die Basis für PITR-
  Semantik der Daten.
- **Branch-State in UC-Tags** ([`services/branch_tags.py`](../../pointlessql/services/branch_tags.py)):
  parent_schema, parent_version_at_create, status, strategy (symlink/
  deep_copy). Branch-Storage-Roots
  ([`pql/branch/_common.py:49-100`](../../pointlessql/pql/branch/_common.py)).
  Cleanup ([`services/branch_cleanup.py:87-203`](../../pointlessql/services/branch_cleanup.py))
  via Scheduler-Executor.
- **PG-Sync** ([`services/pg_sync/`](../../pointlessql/services/pg_sync/)):
  Foreign-Postgres-Mirror, `SyncRun`-Ledger.
- **Storage-Config**
  ([`config/_settings/_storage.py`](../../pointlessql/config/_settings/_storage.py)):
  DB-URL, Delta-Engine (nur pandas), Canvas-File-IO-Sandbox.
- **Export-Bausteine** (Phase 75): Audit-Sinks (webhook/s3/cloudtrail/
  syslog/stdout_json), `GovernanceEvent` (CloudEvents-Ledger). Notebook-
  Export, DP-as-Code-Exporter. **Aber kein DB-Snapshot/Restore.**
- **Scheduler** ([`services/scheduler/`](../../pointlessql/services/scheduler/)):
  KindRegistry + Executoren (pg_sync, papermill, branch_cleanup,
  cost_rollup, …) — das Muster, in das DR-Jobs sich einklinken.

## Scope (Wellen)

### W1 — Konsistentes Backup der eigenen Metadaten-DB
- `cli/`-Kommando + `services/backup/`: dialekt-bewusster konsistenter
  Dump (SQLite: `VACUUM INTO`/Online-Backup-API; Postgres: `pg_dump`
  bzw. snapshot-isolierter Export), versioniert mit Alembic-Revision +
  Zeitstempel (Zeitstempel von außen reingereicht, nicht `Date.now` im
  Code). Optional in einen Audit-Sink-kompatiblen Store (S3) schreiben
  (vorhandene `aws_sigv4`-Signierung wiederverwenden).
- Integritäts-Manifest: Alembic-Head, Tabellen-Rowcounts, Hash.

### W2 — Restore + Schema-Kompatibilitäts-Gate
- Restore-Kommando: Dump einspielen, `alembic upgrade head`, Manifest
  verifizieren. Refusal, wenn Dump-Revision neuer als Code-Head
  (verhindert stillen Daten-Verlust).
- Dry-Run-Modus (Restore in temporäre DB + Validierung, ohne die
  Live-DB anzufassen).

### W3 — Cross-Domain-Konsistenz (DB ↔ Delta ↔ Branches)
- Konsistenz-Checker `services/backup/_consistency.py`: prüft nach
  Restore, dass referenzierte Delta-Versionen/Branch-Tags existieren und
  Lineage-/Audit-Zeiger nicht ins Leere zeigen. Report über Drift
  (verwaiste Edges, fehlende Branch-Roots).
- „Coordinated snapshot": optionaler Modus, der DB-Dump + Delta-Version-
  Pins + Branch-Tag-Export als *ein* wiederherstellbares Set bündelt.

### W4 — Retention end-to-end vereinheitlichen
- Die verstreuten Pruner (lineage/audit/api-key/sql-result) hinter einer
  gemeinsamen `services/lifecycle/`-Sicht zusammenführen: ein Scheduler-
  Job-Kind „retention_sweep" mit Dry-Run + Report + Audit-Eintrag pro
  Lauf. Keine Verhaltensänderung der einzelnen Policies — nur Sichtbarkeit
  + ein Schalt-/Reporting-Punkt. Branch-Cleanup bleibt eigenständig, wird
  aber im selben Report sichtbar.

### W5 — Restore-Game-Day als CI-Job
- `.github/workflows/dr-gameday.yml` (Nightly/wöchentlich, nicht-
  blockierend): seedet eine realistische DB (`seed-full-stack-demo`),
  backupt, restored in frische DB, fährt den Konsistenz-Checker, lädt den
  Report als Artifact. **Beweist regelmäßig, dass Restore funktioniert.**
- Postgres-Lane analog (der DR-Pfad muss in beiden Dialekten grün sein).

### W6 — Runbook + Doku
- `docs/operations/disaster-recovery.md`: RPO/RTO-Annahmen, Backup-
  Zeitplan, Restore-Schritte, Konsistenz-Verifikation, bekannte
  Grenzen (Delta-Daten liegen außerhalb der eigenen DB).

## Akzeptanzkriterien
- `backup` → `restore` in frische DB reproduziert Rowcounts + Alembic-Head
  bit-genau (Manifest grün) für SQLite **und** Postgres.
- Der Konsistenz-Checker meldet 0 verwaiste Zeiger auf einer sauberen
  Seed-DB und fängt einen absichtlich entfernten Branch-Root.
- Der DR-Game-Day-Job läuft grün und lädt einen Konsistenz-Report hoch.
- Ein vereinheitlichter `retention_sweep`-Dry-Run listet alle ablaufenden
  Datensätze über alle Policies ohne zu löschen.
- Runbook ist in der mkdocs-Site (`--strict`) gebaut.

## Risiken / Notizen
- **Delta-Daten sind nicht in der eigenen DB** — DR deckt eigene Metadaten
  + Konsistenz-Zeiger; Delta-Storage-Backup ist Storage-Layer-Aufgabe
  (dokumentieren, nicht reimplementieren).
- SQLite-Online-Backup vs. WAL: korrekte API nutzen (kein nackter
  Datei-Copy unter WAL).
- Retention-Vereinheitlichung darf bestehende Policy-Defaults **nicht**
  ändern — reine Sichtbarkeits-/Orchestrierungs-Schicht.
- Verwandt: Phase 16/16.5 (Rollback/Branching), Phase 20 (Retention),
  Phase 30 (PG-Readiness), Phase 75 (Audit-Export/Sinks).
