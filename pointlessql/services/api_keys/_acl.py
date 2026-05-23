"""Phase 120 — per-API-key ACL check helpers.

Pure functions with no I/O.  Callers fetch the grants list once via
:func:`load_grants_for` and pass it into the check functions.  Both
checks are zero-row-permissive: a key with no rows in the grants
table is unrestricted (back-compat for every pre-120 key).

The catalog check walks the parsed SQL AST via ``sqlglot`` (same
pattern as Phase 117's :func:`pointlessql.services.sql_statements.qualify_sql`),
inspects every ``exp.Table`` reference, and rejects on the first
match-failure.  Default catalog/schema is applied when the
statement uses 1-/2-part refs, so a key whose grants are
``[("main", "sales")]`` can still issue ``SELECT * FROM orders``
provided ``default_catalog="main"`` and ``default_schema="sales"``
are passed in.

The IP check uses :mod:`ipaddress` to parse each grant CIDR and the
caller-supplied source IP.  Invalid CIDRs in the DB are skipped
silently (logged); validation is the service-layer's job at insert
time.
"""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Iterable
from typing import Any, NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

from pointlessql.models import ApiKeyCatalogGrant, ApiKeyIpGrant

logger = logging.getLogger(__name__)


class CatalogGrant(NamedTuple):
    """Lightweight projection of an :class:`ApiKeyCatalogGrant` row."""

    catalog_name: str
    schema_name: str | None


class IpGrant(NamedTuple):
    """Lightweight projection of an :class:`ApiKeyIpGrant` row."""

    cidr: str


class CatalogCheckResult(NamedTuple):
    """Outcome of :func:`check_catalog_allowed`.

    Attributes:
        allowed: ``True`` when every referenced ``(catalog, schema)``
            tuple is covered by at least one grant (or when the
            grants list is empty — unrestricted default).
        denied_catalog: Catalog name of the first denied table when
            ``allowed`` is ``False``; ``None`` otherwise.
        denied_schema: Schema name (possibly ``None``) of the same
            denied table.
    """

    allowed: bool
    denied_catalog: str | None = None
    denied_schema: str | None = None


def load_catalog_grants_for(
    session_factory: sessionmaker[Session], *, api_key_id: int
) -> list[CatalogGrant]:
    """Fetch ``(catalog, schema)`` grants for an API key.

    Args:
        session_factory: SQLAlchemy session factory.
        api_key_id: Key whose grants to read.

    Returns:
        List of :class:`CatalogGrant` named-tuples; empty when the
        key has no grants (= unrestricted access in the check).
    """
    with session_factory() as session:
        rows = session.scalars(
            select(ApiKeyCatalogGrant).where(ApiKeyCatalogGrant.api_key_id == api_key_id)
        ).all()
        return [CatalogGrant(r.catalog_name, r.schema_name) for r in rows]


def load_ip_grants_for(
    session_factory: sessionmaker[Session], *, api_key_id: int
) -> list[IpGrant]:
    """Fetch CIDR grants for an API key.

    Args:
        session_factory: SQLAlchemy session factory.
        api_key_id: Key whose grants to read.

    Returns:
        List of :class:`IpGrant` named-tuples; empty when the key
        has no grants (= unrestricted access in the check).
    """
    with session_factory() as session:
        rows = session.scalars(
            select(ApiKeyIpGrant).where(ApiKeyIpGrant.api_key_id == api_key_id)
        ).all()
        return [IpGrant(r.cidr) for r in rows]


def check_catalog_allowed(
    grants: Iterable[CatalogGrant],
    sql: str,
    *,
    default_catalog: str | None = None,
    default_schema: str | None = None,
) -> CatalogCheckResult:
    """Walk *sql* and verify every table ref is allowlisted.

    A grant with ``schema_name=None`` matches **any** schema in the
    listed catalog.  A grant with both fields set matches only that
    exact ``(catalog, schema)`` pair.

    Args:
        grants: Iterable of :class:`CatalogGrant`.  Zero grants =
            unrestricted (returns allowed-True).
        sql: SQL statement to inspect.  Parsed once via sqlglot.
        default_catalog: Used to qualify 2-part table refs in *sql*.
        default_schema: Used in concert with ``default_catalog`` to
            qualify 1-part table refs.

    Returns:
        :class:`CatalogCheckResult` with the first denied
        ``(catalog, schema)`` pair when ``allowed=False``.
    """
    grant_list = list(grants)
    if not grant_list:
        return CatalogCheckResult(allowed=True)

    # Build a fast-lookup index of allowed targets.
    catalog_wildcards: set[str] = set()
    catalog_schemas: set[tuple[str, str]] = set()
    for g in grant_list:
        if g.schema_name is None:
            catalog_wildcards.add(g.catalog_name)
        else:
            catalog_schemas.add((g.catalog_name, g.schema_name))

    try:
        parsed = parse_one(sql, dialect="duckdb")
    except ParseError:
        # Parse failures will fail elsewhere with a proper DBX error;
        # treat ACL check as not-applicable rather than masking the
        # real error code.
        return CatalogCheckResult(allowed=True)

    for table in parsed.find_all(exp.Table):
        catalog_arg = table.args.get("catalog")
        schema_arg = table.args.get("db")
        catalog_str: str | None = catalog_arg.name if catalog_arg else default_catalog
        schema_str: str | None = schema_arg.name if schema_arg else default_schema
        # Tables without a resolvable catalog can't be checked; let
        # downstream UC enforcement fail closed instead.
        if catalog_str is None:
            continue
        if catalog_str in catalog_wildcards:
            continue
        if schema_str is not None and (catalog_str, schema_str) in catalog_schemas:
            continue
        return CatalogCheckResult(
            allowed=False, denied_catalog=catalog_str, denied_schema=schema_str
        )
    return CatalogCheckResult(allowed=True)


def check_ip_allowed(grants: Iterable[IpGrant], source_ip: str | None) -> bool:
    """Return ``True`` when *source_ip* matches at least one CIDR grant.

    Zero grants = unrestricted (returns ``True``).  A grant with an
    unparseable CIDR is skipped (logged at debug); validation
    happens at insert time in the service layer.  ``source_ip=None``
    fails closed when grants are non-empty (we can't verify, so we
    refuse) — admins behind a stripping reverse-proxy should set the
    global ``enforce_ip_grants=False`` kill-switch.

    Args:
        grants: Iterable of :class:`IpGrant`.
        source_ip: Client IPv4 or IPv6 address, or ``None`` when the
            middleware couldn't resolve it.

    Returns:
        ``True`` when allowed; ``False`` when blocked.
    """
    grant_list = list(grants)
    if not grant_list:
        return True
    if source_ip is None:
        return False
    try:
        ip = ipaddress.ip_address(source_ip)
    except ValueError:
        logger.debug("Unparseable source_ip %r — denying", source_ip)
        return False
    for g in grant_list:
        try:
            network = ipaddress.ip_network(g.cidr, strict=False)
        except ValueError:
            logger.debug("Unparseable CIDR grant %r — skipping", g.cidr)
            continue
        if ip in network:
            return True
    return False


def validate_cidr(value: str) -> str:
    """Parse + normalise a CIDR for insert.  Raises on invalid input.

    Args:
        value: User-supplied CIDR string.

    Returns:
        Canonical form (``ipaddress.ip_network`` round-tripped via
        ``str``) — e.g. ``"10.0.0.0/8"``.  Strips host bits when
        ``strict=False`` accepts them.

    Raises:
        ValueError: When *value* isn't a parseable IPv4 or IPv6 CIDR.
    """
    try:
        network = ipaddress.ip_network(value.strip(), strict=False)
    except ValueError as exc:
        raise ValueError(f"invalid CIDR: {exc}") from exc
    return str(network)


__all__: list[Any] = [
    "CatalogCheckResult",
    "CatalogGrant",
    "IpGrant",
    "check_catalog_allowed",
    "check_ip_allowed",
    "load_catalog_grants_for",
    "load_ip_grants_for",
    "validate_cidr",
]
