"""Catalog browsing tools for the Lens read-only Q&A surface.

Provides ``list_catalogs``, ``list_schemas``, ``list_tables``,
``describe_table``.  Every tool dispatches through
:class:`SessionContext.uc_client` (an
async :class:`UnityCatalogClient` wired with the analyst principal).
The UC server enforces SELECT privileges per-table; tools never have
to consult ACLs themselves.

When ``ctx.uc_client`` is ``None`` (test paths) the tools fall back to
empty responses so unit tests can exercise the audit-hook without
spinning up soyuz.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from pointlessql.services.lens.tools._base import SessionContext, ToolDef

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# list_catalogs
# ---------------------------------------------------------------------------


class ListCatalogsArgs(BaseModel):
    """Input for ``list_catalogs`` (no parameters)."""


class CatalogSummary(BaseModel):
    """One catalog row."""

    name: str
    comment: str | None = None
    owner: str | None = None


class ListCatalogsResult(BaseModel):
    """Output: every UC catalog the analyst principal can see."""

    catalogs: list[CatalogSummary] = Field(default_factory=list)


async def _execute_list_catalogs(ctx: SessionContext, args: ListCatalogsArgs) -> ListCatalogsResult:
    """List every catalog visible to the analyst principal."""
    del args  # no parameters
    if ctx.uc_client is None:
        return ListCatalogsResult()
    rows = await ctx.uc_client.list_catalogs()
    return ListCatalogsResult(
        catalogs=[
            CatalogSummary(
                name=str(r.get("name", "")),
                comment=_opt_str(r.get("comment")),
                owner=_opt_str(r.get("owner")),
            )
            for r in rows
            if r.get("name")
        ]
    )


LIST_CATALOGS_TOOL = ToolDef(
    name="list_catalogs",
    description=(
        "List every Unity Catalog the analyst can see.  Use this as "
        "the first step when you need to know what catalogs exist; "
        "do not guess catalog names."
    ),
    input_model=ListCatalogsArgs,
    output_model=ListCatalogsResult,
    executor=_execute_list_catalogs,
)


# ---------------------------------------------------------------------------
# list_schemas
# ---------------------------------------------------------------------------


class ListSchemasArgs(BaseModel):
    """Input for ``list_schemas``."""

    catalog: str = Field(min_length=1, description="Catalog name to list")


class SchemaSummary(BaseModel):
    """One schema row."""

    name: str
    full_name: str
    comment: str | None = None


class ListSchemasResult(BaseModel):
    """Output: every schema in the requested catalog."""

    schemas: list[SchemaSummary] = Field(default_factory=list)


async def _execute_list_schemas(ctx: SessionContext, args: ListSchemasArgs) -> ListSchemasResult:
    """List every schema in the requested catalog."""
    if ctx.uc_client is None:
        return ListSchemasResult()
    rows = await ctx.uc_client.list_schemas(args.catalog)
    return ListSchemasResult(
        schemas=[
            SchemaSummary(
                name=str(r.get("name", "")),
                full_name=str(r.get("full_name", f"{args.catalog}.{r.get('name', '')}")),
                comment=_opt_str(r.get("comment")),
            )
            for r in rows
            if r.get("name")
        ]
    )


LIST_SCHEMAS_TOOL = ToolDef(
    name="list_schemas",
    description=(
        "List every schema inside a catalog.  Pair with list_catalogs "
        "to discover the catalog name first."
    ),
    input_model=ListSchemasArgs,
    output_model=ListSchemasResult,
    executor=_execute_list_schemas,
)


# ---------------------------------------------------------------------------
# list_tables
# ---------------------------------------------------------------------------


class ListTablesArgs(BaseModel):
    """Input for ``list_tables``."""

    catalog: str = Field(min_length=1)
    schema_name: str = Field(min_length=1, description="Schema name (not catalog)")


class TableSummary(BaseModel):
    """One table row."""

    name: str
    full_name: str
    table_type: str | None = None
    comment: str | None = None


class ListTablesResult(BaseModel):
    """Output: every table in the requested ``catalog.schema``."""

    tables: list[TableSummary] = Field(default_factory=list)


async def _execute_list_tables(ctx: SessionContext, args: ListTablesArgs) -> ListTablesResult:
    """List every table in the requested ``catalog.schema``."""
    if ctx.uc_client is None:
        return ListTablesResult()
    rows = await ctx.uc_client.list_tables(args.catalog, args.schema_name)
    return ListTablesResult(
        tables=[
            TableSummary(
                name=str(r.get("name", "")),
                full_name=str(
                    r.get(
                        "full_name",
                        f"{args.catalog}.{args.schema_name}.{r.get('name', '')}",
                    )
                ),
                table_type=_opt_str(r.get("table_type")),
                comment=_opt_str(r.get("comment")),
            )
            for r in rows
            if r.get("name")
        ]
    )


LIST_TABLES_TOOL = ToolDef(
    name="list_tables",
    description=(
        "List every table inside a UC schema.  Pair with list_schemas "
        "to discover the schema first.  The 'schema_name' argument is "
        "the schema portion of the FQN, not the column-schema of the "
        "tables."
    ),
    input_model=ListTablesArgs,
    output_model=ListTablesResult,
    executor=_execute_list_tables,
)


# ---------------------------------------------------------------------------
# describe_table
# ---------------------------------------------------------------------------


class DescribeTableArgs(BaseModel):
    """Input for ``describe_table``."""

    table_fqn: str = Field(
        min_length=3,
        description="Three-part UC name catalog.schema.table",
    )


class ColumnInfo(BaseModel):
    """One column row in a ``describe_table`` response."""

    name: str
    type_name: str | None = None
    nullable: bool | None = None
    comment: str | None = None


class DescribeTableResult(BaseModel):
    """Output: column list + table-level metadata."""

    table_fqn: str
    table_type: str | None = None
    comment: str | None = None
    columns: list[ColumnInfo] = Field(default_factory=list)


async def _execute_describe_table(
    ctx: SessionContext, args: DescribeTableArgs
) -> DescribeTableResult:
    """Return column-level metadata for the requested UC table."""
    if ctx.uc_client is None:
        return DescribeTableResult(table_fqn=args.table_fqn)
    parts = args.table_fqn.split(".")
    if len(parts) != 3:
        return DescribeTableResult(
            table_fqn=args.table_fqn,
            comment="invalid FQN: expected catalog.schema.table",
        )
    catalog, schema_name, table = parts
    row = await ctx.uc_client.get_table(catalog, schema_name, table)
    cols_raw: list[dict[str, Any]] = list(row.get("columns") or [])
    return DescribeTableResult(
        table_fqn=args.table_fqn,
        table_type=_opt_str(row.get("table_type")),
        comment=_opt_str(row.get("comment")),
        columns=[
            ColumnInfo(
                name=str(c.get("name", "")),
                type_name=_opt_str(c.get("type_name") or c.get("type_text")),
                nullable=_opt_bool(c.get("nullable")),
                comment=_opt_str(c.get("comment")),
            )
            for c in cols_raw
            if c.get("name")
        ],
    )


DESCRIBE_TABLE_TOOL = ToolDef(
    name="describe_table",
    description=(
        "Return column-level metadata for one Unity Catalog table.  "
        "Use this to learn column names + types before writing a "
        "SELECT against the table."
    ),
    input_model=DescribeTableArgs,
    output_model=DescribeTableResult,
    executor=_execute_describe_table,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _opt_str(value: Any) -> str | None:
    """Coerce a UC field to ``str | None`` without empty strings."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _opt_bool(value: Any) -> bool | None:
    """Coerce a UC nullable flag to ``bool | None``."""
    if value is None:
        return None
    return bool(value)
