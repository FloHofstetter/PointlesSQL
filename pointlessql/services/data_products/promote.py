"""Promote-to-DP candidate scanner + draft yaml builder (Phase 73.1).

Two callables:

* :func:`scan_candidates` — periodic scan of
  ``agent_run_operations`` that UPSERTs one
  ``DataProductPromotionCandidate`` per
  ``(workspace, catalog, schema)`` triple whose write pattern
  has stabilised (≥ ``min_runs`` distinct runs and ≥
  ``min_ops`` rows in the window).  Schemas already covered by
  an active ``DataProduct`` row are skipped.  Dismissed
  candidates stay dismissed.
* :func:`build_draft_yaml` — turns one candidate into a draft
  ``pointlessql.yaml`` payload by reading live Delta schemas
  for every table the candidate's schema observed.

The scanner is intentionally heuristic — it relies on the
``target_table`` column being ``"catalog.schema.table"`` and
on the existing index for the prefix LIKE.  Cross-workspace
isolation is provided by the explicit ``workspace_id`` filter
on every join.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
from typing import Any

from sqlalchemy import distinct, func, select

from pointlessql.models.agent._audit import AgentRunOperation
from pointlessql.models.catalog._data_product_candidate import (
    DataProductPromotionCandidate,
)
from pointlessql.models.catalog._data_products import DataProduct

logger = logging.getLogger(__name__)


def _signature_hash(table_columns: dict[str, list[tuple[str, str]]]) -> str:
    """SHA-256 of the schema's sorted ``(table, column, type)`` shape."""
    payload: list[str] = []
    for table_name in sorted(table_columns):
        for col_name, col_type in sorted(table_columns[table_name]):
            payload.append(f"{table_name}|{col_name}|{col_type}")
    digest = hashlib.sha256("\n".join(payload).encode("utf-8")).hexdigest()
    return digest


def _split_fqn(target: str) -> tuple[str, str, str] | None:
    """Split ``catalog.schema.table`` into a 3-tuple, or ``None``."""
    parts = target.split(".")
    if len(parts) != 3:
        return None
    if not all(parts):
        return None
    return parts[0], parts[1], parts[2]


def scan_candidates(
    session_factory: Any,
    *,
    window_days: int = 14,
    min_runs: int = 3,
    min_ops: int = 10,
    now: datetime.datetime | None = None,
) -> int:
    """Refresh the promote-to-DP candidate cache.

    Args:
        session_factory: SQLAlchemy session factory.
        window_days: Rolling window over ``agent_run_operations``.
        min_runs: Minimum distinct ``agent_run_id`` values that
            must touch the schema for it to qualify.
        min_ops: Minimum ``agent_run_operations`` row count.
        now: Optional "now" override for tests.

    Returns:
        Total UPSERTed row count (sum across workspaces).
    """
    now = now or datetime.datetime.now(datetime.UTC)
    window_start = now - datetime.timedelta(days=window_days)
    upserted = 0

    with session_factory() as session:
        existing_dp_keys: set[tuple[int, str, str]] = {
            (dp.workspace_id, dp.catalog_name, dp.schema_name)
            for dp in session.execute(select(DataProduct)).scalars()
        }

        rows = session.execute(
            select(
                AgentRunOperation.workspace_id,
                AgentRunOperation.target_table,
                AgentRunOperation.agent_run_id,
                AgentRunOperation.started_at,
            ).where(
                AgentRunOperation.target_table.is_not(None),
                AgentRunOperation.started_at >= window_start,
                AgentRunOperation.started_at < now,
            )
        ).all()

        # Group by (workspace, catalog, schema).
        per_schema: dict[
            tuple[int, str, str],
            dict[str, Any],
        ] = {}
        for workspace_id, target_table, run_id, started_at in rows:
            if not target_table:
                continue
            split = _split_fqn(target_table)
            if split is None:
                continue
            catalog_name, schema_name, table_name = split
            key = (workspace_id, catalog_name, schema_name)
            if key in existing_dp_keys:
                continue
            entry = per_schema.setdefault(
                key,
                {
                    "first_seen_at": started_at,
                    "last_seen_at": started_at,
                    "run_ids": set(),
                    "tables": set(),
                    "op_count": 0,
                    "sample_target_table": target_table,
                },
            )
            if started_at < entry["first_seen_at"]:
                entry["first_seen_at"] = started_at
            if started_at > entry["last_seen_at"]:
                entry["last_seen_at"] = started_at
            entry["run_ids"].add(run_id)
            entry["tables"].add(table_name)
            entry["op_count"] += 1

        existing_candidates = session.execute(
            select(DataProductPromotionCandidate)
        ).scalars().all()
        existing_by_key = {
            (c.workspace_id, c.catalog_name, c.schema_name): c
            for c in existing_candidates
        }

        for (workspace_id, catalog_name, schema_name), entry in per_schema.items():
            distinct_runs = len(entry["run_ids"])
            op_count = int(entry["op_count"])
            if distinct_runs < min_runs or op_count < min_ops:
                continue

            sig = _signature_hash(
                {table: [(table, "unknown")] for table in entry["tables"]}
            )
            existing = existing_by_key.get(
                (workspace_id, catalog_name, schema_name)
            )

            if existing is None:
                session.add(
                    DataProductPromotionCandidate(
                        workspace_id=workspace_id,
                        catalog_name=catalog_name,
                        schema_name=schema_name,
                        table_signature_hash=sig,
                        first_seen_at=entry["first_seen_at"],
                        last_seen_at=entry["last_seen_at"],
                        distinct_run_count=distinct_runs,
                        write_op_count=op_count,
                        distinct_table_count=len(entry["tables"]),
                        sample_target_table=entry["sample_target_table"],
                        status="open",
                        refreshed_at=now,
                    )
                )
                upserted += 1
            else:
                # Never resurrect a dismissed row: just refresh counts.
                existing.table_signature_hash = sig
                existing.last_seen_at = entry["last_seen_at"]
                existing.distinct_run_count = distinct_runs
                existing.write_op_count = op_count
                existing.distinct_table_count = len(entry["tables"])
                existing.sample_target_table = entry["sample_target_table"]
                existing.refreshed_at = now
                session.add(existing)
                upserted += 1

        session.commit()

    return upserted


def _delta_schema_for_table(target_table: str) -> list[tuple[str, str, bool]]:
    """Return ``(column_name, type_str, nullable)`` for one Delta table.

    Resolves the table's Delta path via the live UC client and
    reads the schema with ``deltalake.DeltaTable``.  Returns an
    empty list when the table does not exist yet — callers
    handle this as a candidate with no concrete columns.

    Args:
        target_table: ``"catalog.schema.table"`` FQN.

    Returns:
        ``[(column_name, normalised_type, nullable), ...]``.
    """
    try:
        from pointlessql import pql as pql_module

        split = _split_fqn(target_table)
        if split is None:
            return []
        catalog_name, schema_name, table_name = split
        uc: Any = pql_module._get_default_uc()  # type: ignore[attr-defined]
        info: Any = uc.get_table_sync(  # pyright: ignore[reportUnknownMemberType]
            catalog_name=catalog_name,
            schema_name=schema_name,
            table_name=table_name,
        )
        columns: list[tuple[str, str, bool]] = []
        raw_columns: Any = getattr(info, "columns", ()) or ()  # pyright: ignore[reportUnknownArgumentType]
        for col in raw_columns:  # pyright: ignore[reportUnknownVariableType]
            type_text = getattr(col, "type_text", None)
            type_name = getattr(col, "type_name", None)
            type_str = str(type_text or type_name or "string").lower()
            primitive = _normalise_delta_type(type_str)
            col_name = str(getattr(col, "name", ""))
            col_nullable = bool(getattr(col, "nullable", True))
            columns.append((col_name, primitive, col_nullable))
        return columns
    except Exception:  # noqa: BLE001
        logger.exception("dp_promote: could not read schema for %s", target_table)
        return []


def _normalise_delta_type(raw: str) -> str:
    """Map a Delta / UC type string to our 11-element literal."""
    raw = raw.lower().strip()
    mapping: dict[str, str] = {
        "string": "string",
        "varchar": "string",
        "char": "string",
        "text": "string",
        "int": "integer",
        "integer": "integer",
        "tinyint": "integer",
        "smallint": "integer",
        "long": "long",
        "bigint": "long",
        "double": "double",
        "float": "double",
        "real": "double",
        "boolean": "boolean",
        "bool": "boolean",
        "timestamp": "timestamp",
        "timestamp_ntz": "timestamp",
        "date": "date",
        "binary": "binary",
    }
    if raw in mapping:
        return mapping[raw]
    if raw.startswith("decimal"):
        return "decimal"
    if raw.startswith("array"):
        return "array"
    if raw.startswith("struct"):
        return "struct"
    return "string"


def build_draft_yaml(
    session: Any,
    *,
    workspace_id: int,
    candidate: DataProductPromotionCandidate,
    schema_reader: Any = None,
) -> str:
    """Build a draft ``pointlessql.yaml`` payload from one candidate.

    Reads the live Delta schema for every distinct
    ``target_table`` observed in the candidate's schema (within
    a recent window) and emits a yaml string the admin can
    edit.

    Args:
        session: Live SQLAlchemy session.
        workspace_id: Active workspace.
        candidate: The candidate row.
        schema_reader: Optional override for the Delta-schema
            reader (used by tests to inject a stub instead of
            hitting the live UC client).  Must be a callable
            taking ``target_table`` and returning
            ``list[(column_name, type, nullable)]``.

    Returns:
        Yaml content as a string.  Round-trippable through
        ``yaml.safe_load`` + :class:`DataProductContract`
        validation.
    """
    import yaml

    reader = schema_reader if schema_reader is not None else _delta_schema_for_table

    # Find every distinct target_table observed in the
    # candidate's schema during the last 30d so the draft
    # captures every table that hashes to the signature.
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=30)
    prefix = f"{candidate.catalog_name}.{candidate.schema_name}."
    targets = (
        session.execute(
            select(distinct(AgentRunOperation.target_table)).where(
                AgentRunOperation.workspace_id == workspace_id,
                AgentRunOperation.target_table.like(f"{prefix}%"),
                AgentRunOperation.started_at >= cutoff,
            )
        )
        .scalars()
        .all()
    )
    table_targets: list[str] = sorted({t for t in targets if t})
    if candidate.sample_target_table not in table_targets:
        table_targets.append(candidate.sample_target_table)

    tables_payload: list[dict[str, Any]] = []
    for target in sorted(table_targets):
        split = _split_fqn(target)
        if split is None:
            continue
        _, _, table_name = split
        schema = reader(target)
        columns: list[dict[str, Any]] = []
        for col_name, col_type, col_null in schema:
            entry: dict[str, Any] = {
                "name": col_name,
                "type": col_type,
                "nullable": col_null,
            }
            columns.append(entry)
        tables_payload.append({"name": table_name, "columns": columns})

    payload: dict[str, Any] = {
        "name": f"{candidate.catalog_name}.{candidate.schema_name}",
        "version": "0.1.0-draft",
        "description": (
            f"Auto-generated draft for {candidate.catalog_name}."
            f"{candidate.schema_name} after {candidate.distinct_run_count} "
            f"distinct agent runs / {candidate.write_op_count} write ops."
        ),
        "catalog": candidate.catalog_name,
        "schema": candidate.schema_name,
        "tables": tables_payload,
    }
    yaml_text = yaml.safe_dump({"data_product": payload}, sort_keys=False)
    return yaml_text


def candidate_row_count(
    session: Any,
    *,
    workspace_id: int,
    status: str | None = None,
) -> int:
    """Convenience: count candidate rows for tests + tab badge.

    Args:
        session: Live SQLAlchemy session.
        workspace_id: Active workspace.
        status: Optional status filter; ``None`` counts all.

    Returns:
        Row count.
    """
    stmt = select(func.count(DataProductPromotionCandidate.id)).where(
        DataProductPromotionCandidate.workspace_id == workspace_id
    )
    if status is not None:
        stmt = stmt.where(DataProductPromotionCandidate.status == status)
    return int(session.execute(stmt).scalar_one() or 0)
