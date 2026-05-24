"""Pydantic models for the ``pointlessql.yaml`` data-product contract.

The four models mirror :mod:`pointlessql.conventions._schema` in shape
— pydantic v2, ``ConfigDict(frozen=True)`` so callers can rely on the
parsed contract being immutable for the lifetime of the load.

The contract grammar is deliberately small so a data team can write
one by hand without consulting documentation:

* :class:`DataProductColumnSpec` — one column's expected name + type
  + nullability.  The 11-element ``type`` literal covers the
  commonly-used Delta / Arrow primitives.
* :class:`DataProductTableContract` — one table's expected columns +
  optional primary-key list.
* :class:`DataProductContract` — top-level: name + SemVer version +
  steward email + freshness SLA + table contracts list.

Validation lives in :mod:`pointlessql.data_products._loader` rather
than here so the schema models stay pure data carriers.  The loader
catches :class:`pydantic.ValidationError` and rewraps it as
:class:`pointlessql.data_products.DataProductYamlInvalid`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DataProductColumnType = Literal[
    "string",
    "integer",
    "long",
    "double",
    "boolean",
    "timestamp",
    "date",
    "decimal",
    "binary",
    "array",
    "struct",
]


class DataProductColumnSpec(BaseModel):
    """One column's expected shape inside a table contract.

    The ``type`` literal is intentionally narrower than the full
    Delta / Arrow type system — adding union types or parametrised
    decimals is a backwards-compatible change a future phase can
    make once the simpler grammar is shipped and proven.

    ``name`` is the column name as it appears in the Delta table;
    ``type`` is one of the 11 supported primitive types; ``nullable``
    defaults to ``True`` to match Delta's permissive default; and
    ``description`` is a free-form note surfaced in the Contract tab
    of the detail page.  ``model_config`` freezes the model so parsed
    instances are hashable and immutable.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    type: DataProductColumnType
    nullable: bool = True
    description: str | None = None


class DataProductTableContract(BaseModel):
    """One table's expected schema inside a product contract.

    The ``primary_key`` list is the contract author's promise that
    these columns identify a row uniquely — used by the diff helper
    to escalate a "PK column dropped" diff to ``is_breaking`` and
    by the merge primitive's contract check.

    ``name`` is the UC table name (last segment, not the full
    ``catalog.schema.table``); ``columns`` is an ordered tuple of
    :class:`DataProductColumnSpec` whose order is preserved in the
    Contract tab UI; ``primary_key`` is an optional tuple of column
    names — ``None`` means "no PK declared".  ``model_config``
    freezes the model so parsed instances are hashable + immutable.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    columns: tuple[DataProductColumnSpec, ...]
    primary_key: tuple[str, ...] | None = None


class DataProductContract(BaseModel):
    """Top-level contract for one UC schema declared as a product.

    The yaml file lives in the data team's repo at the root or
    under a documented path; the loader resolves it via
    ``Settings.data_products.yaml_search_paths`` or
    via an explicit path argument.  Git-blame on the file is the
    audit log — the loader does not version contracts in DB.

    ``name`` is a human-readable product name (e.g. "Sales orders"),
    distinct from the UC schema name; ``version`` is the SemVer
    string (the loader does not enforce SemVer arithmetic — convention
    is "bump major when a contract change would break consumers");
    ``description`` is a one-paragraph product description.
    ``catalog`` and ``schema_name`` together identify the UC schema
    this contract describes; ``schema_name`` is stored under that
    attribute name rather than ``schema`` because pydantic reserves
    ``schema`` for its own internals, and the yaml accepts the alias
    ``schema:`` thanks to ``populate_by_name=True``.

    ``steward_email`` is optional — when the email resolves to a
    persisted ``users`` row the loader sets the FK on the cache,
    otherwise the FK stays NULL and the UI falls back to a mailto
    link.  ``sla_minutes`` is the optional freshness SLA in minutes;
    products without one are skipped by the freshness scanner.
    ``tables`` is the per-table contract list — a product may
    declare contracts for a subset of its UC tables, the enforcement
    hook treats undeclared tables as ``"no_contract"``.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    name: str
    version: str
    description: str
    catalog: str
    schema_name: str = Field(alias="schema")
    steward_email: str | None = None
    sla_minutes: int | None = Field(default=None, ge=1)
    tables: tuple[DataProductTableContract, ...] = ()

    def get_table(self, table_name: str) -> DataProductTableContract | None:
        """Return the contract for ``table_name`` or ``None``.

        Used by the enforcement hook when resolving a write target
        to its expected schema.

        Args:
            table_name: UC table name, last segment only.

        Returns:
            DataProductTableContract | None: Matching contract, or
                ``None`` if the product does not declare one for
                this table.
        """
        for table in self.tables:
            if table.name == table_name:
                return table
        return None
