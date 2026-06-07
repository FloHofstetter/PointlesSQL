---
title: Disaster recovery — backup & restore
audience: operator
---

# Disaster recovery: backing up and restoring the metadata DB

PointlesSQL keeps **its own** metadata — user sessions, workspace
membership, UI preferences, saved queries, the scheduler tables, the
audit/lineage rows — in a SQLAlchemy-managed database (SQLite by default, a
Postgres lane for larger deployments). The lakehouse metadata (catalogs,
schemas, tables) lives in **soyuz-catalog**, and the table data lives in
**Delta Lake** storage. This runbook covers backing up and restoring the
PointlesSQL metadata DB only; the lakehouse and Delta layers are backed up
through their own storage mechanisms (object-store versioning / snapshots).

## What a backup contains

`pointlessql.services.backup.dump_db` produces two artefacts:

- **the payload** — a consistent dump of the metadata DB (SQLite online
  backup, or a `pg_dump` custom-format archive for Postgres), and
- **the manifest** (`<payload>.manifest.json`) — the Alembic revision the
  dump was taken at, per-table row counts, the payload SHA-256, the source
  dialect, and the timestamp.

The manifest makes the backup *verifiable* (hash) and *safe to restore*
(schema-compat check), the same discipline as the audit export.

## Taking a backup

```bash
python -m pointlessql.cli.backup backup --out /backups/pql-$(date +%Y%m%d-%H%M%S).dump
```

This writes the payload (mode 0600) plus its `.manifest.json` sidecar. Use
`--db-url` to back up a DB other than the configured one. Schedule it with
your platform's cron / job runner. (Wiring a `backup_db` scheduler executor
and an optional S3 destination is a follow-up; the service primitives are in
place.)

## Restoring

Always **dry-run first** — it restores into a throwaway copy, runs
`alembic upgrade head`, and re-counts rows against the manifest, all without
touching the live DB:

```bash
python -m pointlessql.cli.backup restore --from /backups/pql-….dump --dry-run
```

When the dry-run is clean, restore for real:

```bash
python -m pointlessql.cli.backup restore --from /backups/pql-….dump --to-db "$POINTLESSQL_DB_URL"
```

The restore is **guarded**:

- the payload hash must match the manifest (corruption check);
- the dump's Alembic revision must be one the running code knows — a backup
  taken on a *newer* schema is refused, because older code cannot migrate it
  forward (override only with `--skip-validation`, at your own risk);
- a cross-dialect restore (SQLite dump into Postgres or vice versa) is
  refused.

After restoring an *older* backup, `alembic upgrade head` runs
automatically to bring the schema current.

## Schema-version reference

The code's current head revision (compare against a manifest's
`alembic_revision`):

```bash
bash scripts/check-alembic-head.sh
```

## Post-restore consistency

`pointlessql.services.backup.check_consistency(engine)` runs best-effort
cross-domain checks (Alembic stamping, referential integrity of workspace
membership, and an extension point for Delta-version / branch-tag
reachability) and returns a structured report rather than raising. Run it
after a restore to confirm the metadata DB is coherent before re-pointing
the app at it.

## RPO / RTO

- **RPO** (data loss window) is the backup cadence — schedule to match your
  tolerance (hourly for active installs, daily for quiet ones).
- **RTO** (time to recover) for SQLite is seconds (file overwrite +
  `upgrade head`); for Postgres it is `pg_restore` time plus the upgrade.

## Known limitations

- Delta table data and soyuz-catalog metadata are **not** in this payload.
- The Postgres dry-run validates the manifest + payload but does not apply
  `pg_restore` to a scratch DB (that needs `createdb`); restore into a
  dedicated scratch database to rehearse a Postgres recovery.
- Backup payloads are not encrypted at rest — store them on encrypted
  media; restrict permissions (the tool writes mode 0600).
