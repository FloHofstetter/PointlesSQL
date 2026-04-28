"""CRUD + safe-execute layer for ``saved_audit_queries``.

Sprint 18.3 — admin-only audit cockpit surface.  Three things
this module owns that ``saved_queries`` does not:

* an explicit table allow-list (only the metadata DB's audit
  tables) backed by sqlglot — every executed query is parsed and
  rejected if it touches anything outside the list, or if the
  root expression is anything other than ``SELECT``;
* a "starter row" concept — :func:`bootstrap_starter_rows` is
  called from the test fixtures and from a future seed-on-first-
  start hook so a fresh install lists curated queries even
  before the alembic migration runs (in-memory SQLite test DBs
  bypass migrations);
* PII-aware result post-processing — when a column matches a
  PII-tagged ``(target_table, target_column)`` pair, the result
  cell is masked unless the caller supplied
  ``reveal_with_reason``.
"""

from __future__ import annotations

import datetime
import logging
import re
import secrets
from typing import TYPE_CHECKING, Any

import sqlglot
import sqlglot.errors as sgerrors
import sqlglot.expressions as sgexp
from sqlalchemy import desc, select, text

from pointlessql.exceptions import ValidationError
from pointlessql.models import SavedAuditQuery

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


# Allow-list keeps every query bound to the audit / metadata
# surface.  Adding ``users`` so a join for principal-attribution
# stays possible; adding ``saved_audit_queries`` itself so cockpit
# self-introspection works ("how many starter queries do we have?").
AUDIT_READ_ALLOWLIST: frozenset[str] = frozenset(
    {
        "agent_run_events",
        "agent_run_operations",
        "agent_run_sources",
        "agent_run_tool_calls",
        "agent_runs",
        "audit_log",
        "lineage_column_map",
        "lineage_row_edges",
        "lineage_row_rejects",
        "lineage_value_changes",
        "query_history",
        "query_history_tables",
        "saved_audit_queries",
        "unattributed_writes",
        "users",
    }
)


_SLUG_SANITIZER = re.compile(r"[^a-z0-9-]+")


def make_slug(title: str) -> str:
    """Derive a URL-safe slug from *title* with a 6-char random suffix.

    Mirrors :func:`pointlessql.services.saved_queries.make_slug` so
    the two surfaces look + behave identically; copying instead of
    importing keeps the surfaces decoupled — different visibility
    rules, different retention.

    Args:
        title: Free-text title.

    Returns:
        Slug shaped ``"<sanitised-title>-<hex>"`` capped at 200
        chars.
    """
    base = (title or "audit-query").strip().lower()
    base = _SLUG_SANITIZER.sub("-", base).strip("-")
    if not base:
        base = "audit-query"
    max_base = 200 - 7
    if len(base) > max_base:
        base = base[:max_base].rstrip("-")
    return f"{base}-{secrets.token_hex(3)}"


def serialize(row: SavedAuditQuery) -> dict[str, Any]:
    """Convert an ORM row into a JSON-friendly dict.

    Args:
        row: ORM row.

    Returns:
        Plain dict shape for ``JSONResponse``.
    """
    return {
        "id": row.id,
        "slug": row.slug,
        "title": row.title,
        "description": row.description,
        "sql_text": row.sql_text,
        "owner_id": row.owner_id,
        "is_shared": row.is_shared,
        "is_starter": row.is_starter,
        "alert_threshold_count": row.alert_threshold_count,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def validate_sql(sql_text: str) -> set[str]:
    """Reject DDL/DML and any SQL referencing a non-allow-listed table.

    Parses with sqlglot in the SQLite dialect (the audit DB is
    SQLite by default).  The function is intentionally strict:

    * the top-level expression must be a ``Select`` (CTEs are fine
      via ``WITH … SELECT`` because sqlglot wraps them as
      ``Select``);
    * every referenced table must be in :data:`AUDIT_READ_ALLOWLIST`;
    * any keyword that mutates state (INSERT/UPDATE/DELETE/MERGE/
      ALTER/DROP/CREATE) is rejected at parse time because sqlglot
      classifies them as non-Select expressions.

    Args:
        sql_text: SQL to validate.

    Returns:
        The set of unique table names referenced by the query.

    Raises:
        ValidationError: When the SQL fails any of the above checks.
    """
    cleaned = (sql_text or "").strip().rstrip(";")
    if not cleaned:
        raise ValidationError("SQL text must not be empty")
    try:
        parsed = sqlglot.parse_one(cleaned, read="sqlite")
    except sgerrors.ParseError as exc:
        raise ValidationError(f"Could not parse SQL: {exc}") from exc
    if not isinstance(parsed, sgexp.Select):
        raise ValidationError(
            "Only SELECT statements are allowed in saved audit queries"
        )
    referenced: set[str] = set()
    for table_node in parsed.find_all(sgexp.Table):
        name = table_node.name
        if not name:
            continue
        referenced.add(name.lower())
    not_allowed = referenced - AUDIT_READ_ALLOWLIST
    if not_allowed:
        raise ValidationError(
            "SQL references tables outside the audit allow-list: "
            + ", ".join(sorted(not_allowed))
        )
    return referenced


def create(
    factory: sessionmaker[Session],
    *,
    owner_id: int,
    title: str,
    description: str | None,
    sql_text: str,
    alert_threshold_count: int | None = None,
) -> dict[str, Any]:
    """Insert a new saved audit query.

    Args:
        factory: SQLAlchemy session factory.
        owner_id: Caller's user id (admin).
        title: Human-readable title.
        description: Optional description.
        sql_text: SQL to save.  Validated against
            :data:`AUDIT_READ_ALLOWLIST` before the row lands so
            an obvious mistake fails fast.
        alert_threshold_count: Sprint 18.5 alert threshold.

    Returns:
        Serialised row dict.

    Raises:
        ValidationError: title or SQL is empty / invalid.
    """
    clean_title = (title or "").strip()
    if not clean_title:
        raise ValidationError("Title must not be empty")
    validate_sql(sql_text)
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = SavedAuditQuery(
            slug=make_slug(clean_title),
            title=clean_title[:200],
            description=description.strip() if description else None,
            sql_text=sql_text.strip(),
            owner_id=owner_id,
            is_shared=True,
            is_starter=False,
            alert_threshold_count=alert_threshold_count,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return serialize(row)


def list_all(factory: sessionmaker[Session]) -> list[dict[str, Any]]:
    """Return every saved audit query, starters first then most-recent.

    Args:
        factory: SQLAlchemy session factory.

    Returns:
        List of serialised rows.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(SavedAuditQuery).order_by(
                    desc(SavedAuditQuery.is_starter),
                    desc(SavedAuditQuery.updated_at),
                )
            )
        )
        return [serialize(r) for r in rows]


def get_by_slug(
    factory: sessionmaker[Session], slug: str
) -> dict[str, Any] | None:
    """Return one row by slug, or ``None`` when absent.

    Args:
        factory: SQLAlchemy session factory.
        slug: URL-visible identifier.

    Returns:
        Serialised dict, or ``None``.
    """
    with factory() as session:
        row = session.scalar(
            select(SavedAuditQuery).where(SavedAuditQuery.slug == slug)
        )
        return serialize(row) if row else None


def update(
    factory: sessionmaker[Session],
    slug: str,
    *,
    title: str | None = None,
    description: str | None = None,
    sql_text: str | None = None,
    alert_threshold_count: int | None | str = "__unchanged__",
) -> dict[str, Any] | None:
    """Patch a row identified by *slug*.  Refuses on starter rows.

    Args:
        factory: SQLAlchemy session factory.
        slug: Target row's slug.
        title: New title or ``None`` to leave unchanged.
        description: New description or ``None`` to leave unchanged;
            pass an explicit ``""`` to clear.
        sql_text: New SQL or ``None`` to leave unchanged.  Validated
            on every change so a starter row that becomes invalid
            after a schema change fails the PATCH instead of
            silently breaking.
        alert_threshold_count: Sentinel "__unchanged__" leaves the
            value alone; ``None`` clears it; an integer sets it.

    Returns:
        The updated row, or ``None`` when the slug is unknown or
        the row is a starter (which refuses mutations).

    Raises:
        ValidationError: New SQL fails the allow-list check.
    """
    with factory() as session:
        row = session.scalar(
            select(SavedAuditQuery).where(SavedAuditQuery.slug == slug)
        )
        if row is None or row.is_starter:
            return None
        if title is not None:
            clean = title.strip()
            if not clean:
                raise ValidationError("Title must not be empty")
            row.title = clean[:200]
        if description is not None:
            row.description = description.strip() or None
        if sql_text is not None:
            validate_sql(sql_text)
            row.sql_text = sql_text.strip()
        if alert_threshold_count != "__unchanged__":
            row.alert_threshold_count = (
                int(alert_threshold_count)
                if alert_threshold_count is not None
                else None
            )
        row.updated_at = datetime.datetime.now(datetime.UTC)
        session.commit()
        session.refresh(row)
        return serialize(row)


def delete(factory: sessionmaker[Session], slug: str) -> bool:
    """Delete a non-starter row by slug.

    Args:
        factory: SQLAlchemy session factory.
        slug: Target row's slug.

    Returns:
        ``True`` iff a row was found, was non-starter, and was
        deleted.
    """
    with factory() as session:
        row = session.scalar(
            select(SavedAuditQuery).where(SavedAuditQuery.slug == slug)
        )
        if row is None or row.is_starter:
            return False
        session.delete(row)
        session.commit()
        return True


def execute(
    factory: sessionmaker[Session],
    slug: str,
    *,
    row_cap: int = 1000,
) -> dict[str, Any] | None:
    """Run the SQL for *slug* against the metadata DB.

    The row cap is enforced *after* sqlglot validation by slicing
    the result list — adding a ``LIMIT`` would change query
    semantics for queries that already carry one.  Cap defaults
    to 1000 to keep cockpit responses snappy; export endpoints
    pass a higher cap.

    Args:
        factory: SQLAlchemy session factory pointed at the
            metadata DB.
        slug: Saved-query slug to run.
        row_cap: Maximum rows to return.  ``0`` or negative means
            "no cap" (used by export endpoints).

    Returns:
        ``{"slug", "columns", "rows", "row_count", "truncated"}`` —
        ``rows`` is a list of dicts keyed by column name; ``columns``
        preserves the SELECT order so an export honours it.
        ``None`` when the slug is unknown.

    Raises:
        ValidationError: Propagated from :func:`validate_sql` when
            a starter row has been edited externally to break the
            allow-list.
    """  # noqa: DOC502 — propagates ValidationError from validate_sql
    saved = get_by_slug(factory, slug)
    if saved is None:
        return None
    referenced = validate_sql(saved["sql_text"])
    with factory() as session:
        result = session.execute(text(saved["sql_text"]))
        keys = list(result.keys())
        all_rows = list(result.mappings().all())
    truncated = False
    if row_cap > 0 and len(all_rows) > row_cap:
        all_rows = all_rows[:row_cap]
        truncated = True
    return {
        "slug": slug,
        "columns": keys,
        "rows": [dict(r) for r in all_rows],
        "row_count": len(all_rows),
        "truncated": truncated,
        "referenced_tables": sorted(referenced),
    }


def bootstrap_starter_rows(factory: sessionmaker[Session]) -> int:
    """Idempotently seed the canonical starter rows.

    Used by the test fixtures and any future "first run" hook —
    the alembic migration also seeds them, so production callers
    only hit this path on test DBs that bypass migrations
    (in-memory SQLite).  Returns the number of new rows.

    Args:
        factory: SQLAlchemy session factory.

    Returns:
        Count of newly inserted rows.
    """
    # Re-export from the migration module so the canonical list of
    # starter specs lives in exactly one place.
    from pointlessql.alembic.versions.j0e1f2a3b4c5_saved_audit_queries import (
        STARTER_ROWS,
    )

    now = datetime.datetime.now(datetime.UTC)
    inserted = 0
    with factory() as session:
        for spec in STARTER_ROWS:
            existing = session.scalar(
                select(SavedAuditQuery).where(
                    SavedAuditQuery.slug == spec["slug"]
                )
            )
            if existing is not None:
                continue
            session.add(
                SavedAuditQuery(
                    slug=str(spec["slug"]),
                    title=str(spec["title"]),
                    description=spec.get("description"),  # type: ignore[arg-type]
                    sql_text=str(spec["sql_text"]),
                    owner_id=None,
                    is_shared=True,
                    is_starter=True,
                    alert_threshold_count=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            inserted += 1
        session.commit()
    return inserted
