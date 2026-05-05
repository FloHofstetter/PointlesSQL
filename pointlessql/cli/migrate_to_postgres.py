r"""SQLite → Postgres metadata-DB migration (Sprint 30.3).

One-shot bulk-copy from a fresh SQLite PointlesSQL deployment to a
fresh Postgres target.  Intentionally narrow scope:

* Refuses to run against a non-empty target — operators have to
  point at a freshly-provisioned PG with no audit/app-state rows.
* Runs ``alembic upgrade head`` against the target first so the
  schema matches the source's chain end.
* Copies tables in a hard-coded FK-respecting order, streaming
  rows in batches via SQLAlchemy core.
* Syncs Postgres sequences past the largest copied id so
  subsequent INSERTs don't collide.
* Rebuilds the Postgres FTS index (Sprint 30.1) from the freshly-
  copied source rows.
* Verifies row counts per table; emits a sample-hash comparison
  for tables larger than 100 rows.

Usage:

.. code-block:: shell

    pointlessql migrate-to-postgres \\
        --source sqlite:////app/data/pointlessql.db \\
        --target postgresql+psycopg://pointlessql:s3cret@db/pointlessql

The CLI subcommand is registered in :mod:`pointlessql.api.main`'s
top-level Typer app so the existing ``[project.scripts]``
console-script entry covers it.
"""

from __future__ import annotations

import hashlib
import logging
import sys
import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.engine import Engine

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger(__name__)


#: Tables copied in this exact order so FK references resolve
#: against rows that already exist in the target.  Children
#: appear after their parents.  ``alembic_version`` and the FTS
#: indexes (``audit_search``/``audit_search_index`` family) are
#: *not* in this list — alembic rebuilds the version row, and
#: 30.1's ``audit_fts.install_index`` rebuilds the FTS index
#: from the freshly-copied source rows.
_FK_ORDERED_TABLES: tuple[str, ...] = (
    # Workspace + auth roots
    "workspaces",
    "workspace_members",
    "workspace_catalog_pins",
    "users",
    "api_keys",
    "system_keys",
    # Catalog UX state
    "saved_audit_queries",
    "recent_tables",
    "table_stats",
    # Scheduler
    "jobs",
    "job_runs",
    "job_steps",
    # Sync
    "sync_runs",
    # Notebook UX state
    "notebook_cell_runs",
    "notebook_cell_run_sources",
    "notebook_outputs",
    # Agent runs (parents)
    "agent_runs",
    "agent_run_sources",
    "agent_run_operations",
    "agent_run_events",
    "agent_run_tool_calls",
    # Lineage (children of agent_runs / agent_run_operations)
    "lineage_row_edges",
    "lineage_row_rejects",
    "lineage_column_map",
    "lineage_value_changes",
    # Audit + governance + reviews
    "audit_log",
    "governance_events",
    "audit_sinks",
    "agent_reviews",
    "review_destinations",
    "query_history",
    # External writes / anomalies / branches
    "unattributed_writes",
    "anomaly_acks",
    "branch_audit_log",
    # Alerts (depend on jobs + workspaces + users)
    "alerts",
    "alert_destinations",
    "alert_events",
)


class MigrationError(RuntimeError):
    """Raised when the migration cannot proceed safely."""


def _ensure_dialects(source_url: str, target_url: str) -> None:
    """Validate the source URL is SQLite and the target is Postgres.

    Args:
        source_url: SQLAlchemy URL pointing at the existing
            PointlesSQL SQLite metadata DB.
        target_url: SQLAlchemy URL pointing at a fresh Postgres
            metadata DB.

    Raises:
        MigrationError: When either URL points at the wrong
            backend — the bulk-copy logic only handles
            SQLite → Postgres in this direction.
    """
    if not source_url.startswith("sqlite"):
        raise MigrationError(f"--source must be a sqlite URL, got {source_url!r}")
    if not (target_url.startswith("postgresql") or target_url.startswith("postgres+")):
        raise MigrationError(f"--target must be a postgresql URL, got {target_url!r}")


def _refuse_non_empty_target(target_engine: Engine) -> None:
    """Refuse to overwrite an existing PG with rows.

    Counts rows in every table in :data:`_FK_ORDERED_TABLES`.  If
    *any* table reports > 0 rows we abort — operators must hand
    us a freshly-provisioned PG (no migrations run yet, or only
    alembic upgrade with empty seeds).

    Args:
        target_engine: Engine bound to the Postgres target.

    Raises:
        MigrationError: When at least one table is non-empty.
    """
    inspector = inspect(target_engine)
    existing = set(inspector.get_table_names())
    # Tables that alembic seeds at upgrade time — operators can't
    # avoid having a few rows here even on a fresh target.  We
    # overwrite the seeded rows when the source rows are copied
    # (PKs collide, sequences sync afterwards).
    seeded_allow = {
        "workspaces": 1,  # bootstrap default workspace (id=1)
        "saved_audit_queries": 5,  # 5 starter queries from j0e1f2a3b4c5
    }
    with target_engine.connect() as conn:
        for tname in _FK_ORDERED_TABLES:
            if tname not in existing:
                continue
            count = conn.execute(text(f"SELECT COUNT(*) FROM {tname}")).scalar() or 0
            allowed = seeded_allow.get(tname, 0)
            if int(count) <= allowed:
                continue
            raise MigrationError(
                f"target {tname} already has {count} rows — refuse "
                f"to overwrite a populated PG.  Drop the database "
                f"and re-create before re-running."
            )


def _run_alembic_upgrade_head(target_url: str) -> None:
    """Apply the alembic chain to the target."""
    from alembic import command  # noqa: PLC0415

    from pointlessql.db import (  # noqa: PLC0415  # heavy import deferred
        _alembic_config,  # pyright: ignore[reportPrivateUsage]
    )

    cfg = _alembic_config(target_url)
    command.upgrade(cfg, "head")


def _copy_table(
    source_engine: Engine,
    target_engine: Engine,
    table_name: str,
    *,
    batch_size: int,
    dry_run: bool,
) -> int:
    """Stream-copy one table.

    Args:
        source_engine: SQLite source.
        target_engine: Postgres target.
        table_name: Name of the table to copy.
        batch_size: Rows per INSERT statement.
        dry_run: When ``True``, execute the SELECT but skip the
            INSERT and return the row count without writing.

    Returns:
        Total rows copied (or that would be copied in dry-run).

    Raises:
        MigrationError: When the target schema is missing the
            named table — the operator must run alembic upgrade
            head against the target before bulk copy.
    """
    src_inspector = inspect(source_engine)
    if table_name not in src_inspector.get_table_names():
        return 0
    src_md = MetaData()
    src_table = Table(table_name, src_md, autoload_with=source_engine)

    with source_engine.connect() as src_conn:
        total = src_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0
    if total == 0:
        return 0
    if dry_run:
        # Don't touch the target on dry-run — just count source rows.
        return int(total)

    tgt_md = MetaData()
    try:
        tgt_table = Table(table_name, tgt_md, autoload_with=target_engine)
    except Exception as exc:  # noqa: BLE001 — surface both SAWarning/NoSuchTable cleanly
        raise MigrationError(
            f"target schema is missing table {table_name} — "
            f"alembic upgrade head must run before bulk copy"
        ) from exc

    with source_engine.connect() as src_conn:
        result = src_conn.execution_options(stream_results=True).execute(select(src_table))
        copied = 0
        with target_engine.begin() as tgt_conn:
            batch: list[dict[str, Any]] = []
            for row in result.mappings():
                batch.append(dict(row))
                if len(batch) >= batch_size:
                    tgt_conn.execute(tgt_table.insert(), batch)
                    copied += len(batch)
                    batch = []
            if batch:
                tgt_conn.execute(tgt_table.insert(), batch)
                copied += len(batch)
        return copied


def _sync_sequences(target_engine: Engine) -> None:
    """Bump every PG sequence past the highest existing id.

    SQLAlchemy ``INSERT`` calls with explicit ``id`` values don't
    advance the underlying ``serial`` sequence on Postgres, so the
    next allocation collides.  Walking the schema once after a
    bulk copy keeps subsequent INSERTs safe.
    """
    sql = text(
        "SELECT pg_get_serial_sequence(c.relname, a.attname) AS seq, "
        "       c.relname AS table_name, "
        "       a.attname AS col "
        "FROM pg_attribute a "
        "JOIN pg_class c ON c.oid = a.attrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' "
        "  AND a.attnum > 0 "
        "  AND NOT a.attisdropped "
        "  AND pg_get_serial_sequence(c.relname, a.attname) IS NOT NULL"
    )
    with target_engine.begin() as conn:
        rows = conn.execute(sql).all()
        for row in rows:
            seq = row.seq
            tname = row.table_name
            col = row.col
            if seq is None:
                continue
            conn.execute(
                text(f"SELECT setval(:seq, COALESCE((SELECT MAX({col}) FROM {tname}), 1))"),
                {"seq": seq},
            )


def _verify_counts(
    source_engine: Engine,
    target_engine: Engine,
    *,
    sample_hash_min_rows: int = 100,
) -> dict[str, dict[str, int | str]]:
    """Compare per-table row counts; sample-hash large tables.

    Args:
        source_engine: SQLite source.
        target_engine: Postgres target.
        sample_hash_min_rows: Hash a 1% sample for tables with at
            least this many rows.  Smaller tables are covered by
            count-equality alone.

    Returns:
        Per-table verification dict ``{table: {"source": int,
        "target": int, "hash_match": "ok" | "drift" | "n/a"}}``.
    """
    out: dict[str, dict[str, int | str]] = {}
    src_inspector = inspect(source_engine)
    tgt_inspector = inspect(target_engine)
    src_tables = set(src_inspector.get_table_names())
    tgt_tables = set(tgt_inspector.get_table_names())

    with source_engine.connect() as sc, target_engine.connect() as tc:
        for tname in _FK_ORDERED_TABLES:
            if tname not in src_tables or tname not in tgt_tables:
                continue
            sc_count = int(sc.execute(text(f"SELECT COUNT(*) FROM {tname}")).scalar() or 0)
            tc_count = int(tc.execute(text(f"SELECT COUNT(*) FROM {tname}")).scalar() or 0)
            entry: dict[str, int | str] = {
                "source": sc_count,
                "target": tc_count,
                "hash_match": "n/a",
            }
            if sc_count >= sample_hash_min_rows and sc_count == tc_count:
                # Sample 1% of ids deterministically; hash row blobs.
                # Skip if no integer ``id`` column.
                cols = {c["name"] for c in src_inspector.get_columns(tname)}
                if "id" in cols:
                    src_md = MetaData()
                    src_t = Table(tname, src_md, autoload_with=source_engine)
                    tgt_md = MetaData()
                    tgt_t = Table(tname, tgt_md, autoload_with=target_engine)
                    sample_size = max(1, sc_count // 100)
                    src_rows = (
                        sc.execute(select(src_t).order_by(src_t.c.id).limit(sample_size))
                        .mappings()
                        .all()
                    )
                    tgt_rows = (
                        tc.execute(select(tgt_t).order_by(tgt_t.c.id).limit(sample_size))
                        .mappings()
                        .all()
                    )
                    src_hash = _hash_rows(src_rows)
                    tgt_hash = _hash_rows(tgt_rows)
                    entry["hash_match"] = "ok" if src_hash == tgt_hash else "drift"
            out[tname] = entry
    return out


def _hash_rows(rows: Iterable[Any]) -> str:
    """Stable hash of a row sample, ignoring dialect-specific repr.

    Casts every value through :func:`repr` so ``datetime`` /
    ``Decimal`` / ``bytes`` all hash the same on both sides.  The
    sample size is small (1% of source) so the cost is negligible.
    """
    h = hashlib.sha256()
    for row in rows:
        for key in sorted(row.keys()):
            h.update(key.encode("utf-8"))
            h.update(b"=")
            h.update(repr(row[key]).encode("utf-8"))
            h.update(b"|")
        h.update(b"\n")
    return h.hexdigest()


def _rebuild_pg_fts(target_engine: Engine) -> None:
    """Rebuild the Sprint-30.1 FTS index from the freshly-copied source rows."""
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from pointlessql.services import audit_fts  # noqa: PLC0415

    factory = sessionmaker(bind=target_engine)
    audit_fts.rebuild_index(factory)


def migrate(
    *,
    source_url: str,
    target_url: str,
    batch_size: int = 1000,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Drive the full migration end-to-end.

    Returns a summary dict suitable for printing or piping into
    structured-log post-processing.
    """
    _ensure_dialects(source_url, target_url)

    source_engine = create_engine(source_url, connect_args={"check_same_thread": False})
    target_engine = create_engine(target_url)

    started = time.monotonic()
    summary: dict[str, Any] = {
        "source": source_url.split("?")[0],
        "target": target_url.split("?")[0],
        "dry_run": dry_run,
        "batch_size": batch_size,
        "tables": {},
        "sequence_sync": False,
        "fts_rebuild": False,
        "elapsed_seconds": 0.0,
    }

    try:
        if not dry_run:
            _run_alembic_upgrade_head(target_url)
            _refuse_non_empty_target(target_engine)
            # Wipe the alembic-seeded rows so source rows can be
            # copied without PK collision.  Walk children → parents
            # so FK references survive.
            with target_engine.begin() as conn:
                for tname in reversed(_FK_ORDERED_TABLES):
                    inspector = inspect(target_engine)
                    if tname not in inspector.get_table_names():
                        continue
                    conn.execute(text(f"DELETE FROM {tname}"))

        for tname in _FK_ORDERED_TABLES:
            try:
                copied = _copy_table(
                    source_engine,
                    target_engine,
                    tname,
                    batch_size=batch_size,
                    dry_run=dry_run,
                )
                summary["tables"][tname] = copied
            except MigrationError:
                raise
            except Exception as exc:  # noqa: BLE001 — surface clearly
                logger.exception("copy failed for %s", tname)
                summary["tables"][tname] = f"error: {exc}"
                raise MigrationError(f"copy failed for {tname}: {exc}") from exc

        if not dry_run:
            _sync_sequences(target_engine)
            summary["sequence_sync"] = True

            try:
                _rebuild_pg_fts(target_engine)
                summary["fts_rebuild"] = True
            except Exception:  # noqa: BLE001 — non-fatal
                logger.exception("FTS rebuild failed (non-fatal)")
                summary["fts_rebuild"] = False

            summary["verify"] = _verify_counts(source_engine, target_engine)
    finally:
        source_engine.dispose()
        target_engine.dispose()
        summary["elapsed_seconds"] = round(time.monotonic() - started, 3)

    return summary


def print_summary(summary: dict[str, Any]) -> None:
    """Render :func:`migrate`'s return value to stdout."""
    print(f"source           = {summary['source']}")
    print(f"target           = {summary['target']}")
    print(f"dry_run          = {summary['dry_run']}")
    print(f"batch_size       = {summary['batch_size']}")
    print(f"elapsed_seconds  = {summary['elapsed_seconds']}")
    print(f"sequence_sync    = {summary['sequence_sync']}")
    print(f"fts_rebuild      = {summary['fts_rebuild']}")
    print()
    print(f"{'table':<35} {'rows':>10}")
    print("-" * 50)
    for tname, count in summary["tables"].items():
        print(f"{tname:<35} {count!s:>10}")
    if "verify" in summary:
        print()
        print(f"{'verification':<35} {'src':>8}  {'tgt':>8}  {'hash':>6}")
        print("-" * 60)
        for tname, info in summary["verify"].items():
            src = info["source"]
            tgt = info["target"]
            mark = "OK" if src == tgt else "DRIFT"
            hash_state = info["hash_match"]
            print(f"{tname:<35} {src!s:>8}  {tgt!s:>8}  {hash_state:>6}  [{mark}]")


def cli_entrypoint(  # pragma: no cover — exercised via the Typer wrapper
    *,
    source_url: str,
    target_url: str,
    batch_size: int = 1000,
    dry_run: bool = False,
) -> int:
    """Synchronous wrapper that the Typer command calls."""
    try:
        summary = migrate(
            source_url=source_url,
            target_url=target_url,
            batch_size=batch_size,
            dry_run=dry_run,
        )
    except MigrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print_summary(summary)
    return 0
