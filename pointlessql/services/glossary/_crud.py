"""Glossary CRUD + term-to-column binding primitives.

Single write path for the business-glossary layer — the admin CRUD
routes, the browse API, and the per-column badge lookup all go
through these so slug validation lives in one place.  Returns
detached ORM rows so callers can serialise after the session closes.
"""

from __future__ import annotations

import datetime
import re

from sqlalchemy import select, tuple_

from pointlessql.models import GlossaryTerm, GlossaryTermColumn
from pointlessql.types import SessionFactory

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}[a-z0-9]$|^[a-z0-9]$")


def _validate_slug(slug: str) -> str:
    """Return *slug* lowered + trimmed, or raise on shape violation.

    Glossary slugs share the workspace-/domain-slug grammar so they
    are safe to drop into ``/glossary/{slug}`` URLs without escaping.

    Args:
        slug: Caller-supplied term slug.

    Returns:
        The cleaned slug (lower-cased, trimmed).

    Raises:
        ValueError: When the slug is empty, longer than 64 chars, or
            contains characters outside ``[a-z0-9_-]`` / starts / ends
            with a separator.
    """
    cleaned = slug.strip().lower()
    if not cleaned or len(cleaned) > 64:
        raise ValueError("glossary slug must be 1..64 chars")
    if not _SLUG_RE.match(cleaned):
        raise ValueError(
            f"glossary slug {cleaned!r} must match [a-z0-9_-] and not start/end with - or _"
        )
    return cleaned


def create_term(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    slug: str,
    term: str,
    definition: str | None = None,
    creator_user_id: int | None = None,
) -> GlossaryTerm:
    """Insert a new :class:`GlossaryTerm`.

    Args:
        session_factory: Sessionmaker callable.
        workspace_id: Owning workspace.
        slug: URL-safe identifier; see :func:`_validate_slug`.
        term: Human-readable label (max 200 chars).
        definition: Optional free-form definition.
        creator_user_id: User who created the term.

    Returns:
        The detached :class:`GlossaryTerm` row.

    Raises:
        ValueError: On bad slug / term, or a slug already taken in the
            workspace.
    """
    cleaned_slug = _validate_slug(slug)
    cleaned_term = term.strip()
    if not cleaned_term or len(cleaned_term) > 200:
        raise ValueError("glossary term must be 1..200 chars")
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        existing = session.scalar(
            select(GlossaryTerm).where(
                GlossaryTerm.workspace_id == workspace_id,
                GlossaryTerm.slug == cleaned_slug,
            )
        )
        if existing is not None:
            raise ValueError(f"glossary slug {cleaned_slug!r} already exists in this workspace")
        row = GlossaryTerm(
            workspace_id=workspace_id,
            slug=cleaned_slug,
            term=cleaned_term,
            definition=definition.strip() if definition else None,
            created_by_user_id=creator_user_id,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def list_terms(session_factory: SessionFactory, *, workspace_id: int) -> list[GlossaryTerm]:
    """Return the workspace's glossary terms ordered by term."""
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(GlossaryTerm)
                .where(GlossaryTerm.workspace_id == workspace_id)
                .order_by(GlossaryTerm.term.asc())
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows


def get_term_by_slug(
    session_factory: SessionFactory, *, workspace_id: int, slug: str
) -> GlossaryTerm | None:
    """Return the workspace glossary term with *slug* or ``None``."""
    cleaned = slug.strip().lower()
    with session_factory() as session:
        row = session.scalar(
            select(GlossaryTerm).where(
                GlossaryTerm.workspace_id == workspace_id,
                GlossaryTerm.slug == cleaned,
            )
        )
        if row is not None:
            session.expunge(row)
        return row


def delete_term(session_factory: SessionFactory, *, term_id: int) -> bool:
    """Delete a glossary term (and, via CASCADE, its column bindings).

    Returns:
        ``True`` when a row was deleted, ``False`` when none existed.
    """
    with session_factory() as session:
        row = session.get(GlossaryTerm, term_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def bind_column(
    session_factory: SessionFactory,
    *,
    term_id: int,
    catalog: str,
    schema: str,
    table: str,
    column: str,
) -> GlossaryTermColumn:
    """Bind a glossary term to one UC column.

    Idempotent: re-binding the same column returns the existing row.

    Args:
        session_factory: Sessionmaker callable.
        term_id: FK to :class:`GlossaryTerm`.
        catalog: UC catalog segment.
        schema: UC schema segment.
        table: UC table name (last segment).
        column: UC column name.

    Returns:
        The detached :class:`GlossaryTermColumn` row.

    Raises:
        ValueError: When the term does not exist, or any ref segment
            is empty.
    """
    parts = {"catalog": catalog, "schema": schema, "table": table, "column": column}
    cleaned = {key: value.strip() for key, value in parts.items()}
    if not all(cleaned.values()):
        raise ValueError("catalog, schema, table and column are all required")
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        if session.get(GlossaryTerm, term_id) is None:
            raise ValueError(f"glossary term id={term_id} not found")
        existing = session.scalar(
            select(GlossaryTermColumn).where(
                GlossaryTermColumn.glossary_term_id == term_id,
                GlossaryTermColumn.catalog == cleaned["catalog"],
                GlossaryTermColumn.schema_name == cleaned["schema"],
                GlossaryTermColumn.table_name == cleaned["table"],
                GlossaryTermColumn.column_name == cleaned["column"],
            )
        )
        if existing is not None:
            session.expunge(existing)
            return existing
        row = GlossaryTermColumn(
            glossary_term_id=term_id,
            catalog=cleaned["catalog"],
            schema_name=cleaned["schema"],
            table_name=cleaned["table"],
            column_name=cleaned["column"],
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def unbind_column(session_factory: SessionFactory, *, binding_id: int) -> bool:
    """Remove a term-to-column binding.

    Returns:
        ``True`` when a row was deleted, ``False`` when none existed.
    """
    with session_factory() as session:
        row = session.get(GlossaryTermColumn, binding_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def list_bindings(session_factory: SessionFactory, *, term_id: int) -> list[GlossaryTermColumn]:
    """Return every column binding for *term_id*."""
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(GlossaryTermColumn)
                .where(GlossaryTermColumn.glossary_term_id == term_id)
                .order_by(GlossaryTermColumn.id.asc())
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows


def terms_for_schema(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    catalog: str,
    schema: str,
) -> dict[str, list[str]]:
    """Return a ``"table.column" -> [term, ...]`` map for one schema.

    The batch reverse-lookup that powers the contract-tab glossary
    badges without a per-column round-trip.

    Args:
        session_factory: Sessionmaker callable.
        workspace_id: Active workspace (terms are workspace-scoped).
        catalog: UC catalog segment.
        schema: UC schema segment.

    Returns:
        Dict keyed by ``"<table>.<column>"`` mapping to the sorted
        list of bound term labels.
    """
    out: dict[str, list[str]] = {}
    with session_factory() as session:
        rows = list(
            session.execute(
                select(
                    GlossaryTermColumn.table_name,
                    GlossaryTermColumn.column_name,
                    GlossaryTerm.term,
                )
                .join(GlossaryTerm, GlossaryTerm.id == GlossaryTermColumn.glossary_term_id)
                .where(
                    GlossaryTerm.workspace_id == workspace_id,
                    GlossaryTermColumn.catalog == catalog,
                    GlossaryTermColumn.schema_name == schema,
                )
                .order_by(GlossaryTerm.term.asc())
            ).all()
        )
    for table_name, column_name, term in rows:
        out.setdefault(f"{table_name}.{column_name}", []).append(term)
    return out


def terms_for_schema_with_slugs(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    catalog: str,
    schema: str,
) -> dict[str, list[dict[str, str]]]:
    """Return a ``"table.column" -> [{term, slug}, ...]`` map for one schema.

    The slug-carrying sibling of :func:`terms_for_schema`, so the
    Data-tab glossary badges can deep-link to ``/glossary/{slug}``
    instead of rendering a bare label.

    Args:
        session_factory: Sessionmaker callable.
        workspace_id: Active workspace (terms are workspace-scoped).
        catalog: UC catalog segment.
        schema: UC schema segment.

    Returns:
        Dict keyed by ``"<table>.<column>"`` mapping to a list of
        ``{"term", "slug"}`` dicts, sorted by term.
    """
    out: dict[str, list[dict[str, str]]] = {}
    with session_factory() as session:
        rows = list(
            session.execute(
                select(
                    GlossaryTermColumn.table_name,
                    GlossaryTermColumn.column_name,
                    GlossaryTerm.term,
                    GlossaryTerm.slug,
                )
                .join(GlossaryTerm, GlossaryTerm.id == GlossaryTermColumn.glossary_term_id)
                .where(
                    GlossaryTerm.workspace_id == workspace_id,
                    GlossaryTermColumn.catalog == catalog,
                    GlossaryTermColumn.schema_name == schema,
                )
                .order_by(GlossaryTerm.term.asc())
            ).all()
        )
    for table_name, column_name, term, slug in rows:
        out.setdefault(f"{table_name}.{column_name}", []).append({"term": term, "slug": slug})
    return out


def terms_for_schemas(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    pairs: list[tuple[str, str]],
) -> dict[tuple[str, str], list[str]]:
    """Return a ``(catalog, schema) -> [term, ...]`` map for many schemas.

    The bulk sibling of :func:`terms_for_schema`, powering the
    marketplace listing's glossary-aware search: every product on the
    page gets the set of business terms bound to any of its columns in
    one round-trip rather than a per-product lookup.

    Args:
        session_factory: Sessionmaker callable.
        workspace_id: Active workspace (terms are workspace-scoped).
        pairs: ``(catalog, schema)`` tuples identifying the products.

    Returns:
        Dict keyed by ``(catalog, schema)`` mapping to the sorted,
        de-duplicated list of bound term labels.  Pairs with no bound
        term are absent from the map.
    """
    if not pairs:
        return {}
    out: dict[tuple[str, str], list[str]] = {}
    with session_factory() as session:
        rows = list(
            session.execute(
                select(
                    GlossaryTermColumn.catalog,
                    GlossaryTermColumn.schema_name,
                    GlossaryTerm.term,
                )
                .join(GlossaryTerm, GlossaryTerm.id == GlossaryTermColumn.glossary_term_id)
                .where(
                    GlossaryTerm.workspace_id == workspace_id,
                    tuple_(GlossaryTermColumn.catalog, GlossaryTermColumn.schema_name).in_(pairs),
                )
                .order_by(GlossaryTerm.term.asc())
            ).all()
        )
    for catalog, schema_name, term in rows:
        bucket = out.setdefault((catalog, schema_name), [])
        if term not in bucket:
            bucket.append(term)
    return out


def terms_for_column(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    catalog: str,
    schema: str,
    table: str,
    column: str,
) -> list[GlossaryTerm]:
    """Return the glossary terms bound to one UC column.

    The reverse lookup that powers the per-column glossary badges on
    a product's Contract tab.

    Args:
        session_factory: Sessionmaker callable.
        workspace_id: Active workspace (terms are workspace-scoped).
        catalog: UC catalog segment.
        schema: UC schema segment.
        table: UC table name (last segment).
        column: UC column name.

    Returns:
        Detached :class:`GlossaryTerm` rows ordered by term.
    """
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(GlossaryTerm)
                .join(GlossaryTermColumn, GlossaryTermColumn.glossary_term_id == GlossaryTerm.id)
                .where(
                    GlossaryTerm.workspace_id == workspace_id,
                    GlossaryTermColumn.catalog == catalog,
                    GlossaryTermColumn.schema_name == schema,
                    GlossaryTermColumn.table_name == table,
                    GlossaryTermColumn.column_name == column,
                )
                .order_by(GlossaryTerm.term.asc())
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows
