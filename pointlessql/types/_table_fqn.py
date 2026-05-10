"""``TableFqn`` validation type for ``catalog.schema.table`` identifiers.

UC three-part names are exchanged across ~13 producers in
``api/`` / ``services/`` / ``pql/`` and consumed by ~38 function
signatures.  Until Phase 49c they were typed plain ``str``
everywhere, with two duplicated ``_split_three_part`` validators
in the introspect / write route modules as the only structural
gate.

This module collapses both validators into a single type.
:class:`TableFqn` is a ``str`` subclass — ``Mapped[str]`` columns
absorb it transparently, JSON / repr / logging produce the
underlying string, and pyright treats it as nominally distinct
so passing a bare ``str`` where ``TableFqn`` is expected fails
type-check.
"""

from __future__ import annotations

from typing import Self


class TableFqn(str):
    """A validated ``catalog.schema.table`` UC identifier.

    Instances should be constructed via :meth:`parse` (raises
    :class:`ValidationError` on malformed input) or
    :meth:`from_parts` (skips validation; for callers that have
    already split the name upstream).  Direct ``TableFqn(s)``
    construction skips validation per ``str`` subclass semantics
    — callers should prefer the explicit factories.
    """

    __slots__ = ()

    @classmethod
    def parse(cls, full_name: str) -> Self:
        """Validate + return a :class:`TableFqn`.

        Args:
            full_name: Three-part period-separated UC name; leading
                / trailing whitespace on each segment is stripped.

        Returns:
            A validated :class:`TableFqn` instance.

        Raises:
            ValidationError: ``full_name`` is not exactly three
                non-empty period-separated parts.
        """
        from pointlessql.exceptions import (
            ValidationError,  # noqa: PLC0415  # break exceptions↔types cycle
        )

        parts = [p.strip() for p in full_name.split(".")]
        if len(parts) != 3 or not all(parts):
            raise ValidationError(
                "table must be a three-part UC name 'catalog.schema.table'"
            )
        return cls(".".join(parts))

    @classmethod
    def from_parts(cls, catalog: str, schema: str, table: str) -> Self:
        """Construct without validation (caller-checked path).

        Args:
            catalog: UC catalog name.
            schema: UC schema name.
            table: UC table name.

        Returns:
            ``TableFqn`` instance equal to ``f"{catalog}.{schema}.{table}"``.
        """
        return cls(f"{catalog}.{schema}.{table}")

    @property
    def catalog(self) -> str:
        """Return the catalog segment."""
        return self.split(".", 2)[0]

    @property
    def schema(self) -> str:
        """Return the schema segment."""
        return self.split(".", 2)[1]

    @property
    def table(self) -> str:
        """Return the table segment."""
        return self.split(".", 2)[2]

    def parts(self) -> tuple[str, str, str]:
        """Return ``(catalog, schema, table)`` as a tuple."""
        c, s, t = self.split(".", 2)
        return c, s, t
