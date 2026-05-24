"""``DataProductRef`` validation type for ``catalog.schema`` identifiers.

A data product is identified by the two-part UC name of its schema.
This module mirrors :mod:`pointlessql.table_fqn` —
``DataProductRef`` is a ``str`` subclass so JSON / repr / logging
produce the underlying string verbatim, ``Mapped[str]`` columns
absorb it transparently, and pyright treats it as nominally
distinct so passing a bare ``str`` where ``DataProductRef`` is
expected fails type-check.
"""

from __future__ import annotations

from typing import Self

from pointlessql.exceptions import ValidationError


class DataProductRef(str):
    """A validated ``catalog.schema`` data-product reference.

    Instances should be constructed via :meth:`parse` (raises
    :class:`ValidationError` on malformed input) or
    :meth:`from_parts` (skips validation; for callers that have
    already split the name upstream).  Direct ``DataProductRef(s)``
    construction skips validation per ``str`` subclass semantics —
    callers should prefer the explicit factories.
    """

    __slots__ = ()

    @classmethod
    def parse(cls, full_name: str) -> Self:
        """Validate + return a :class:`DataProductRef`.

        Args:
            full_name: Two-part period-separated UC schema name;
                leading / trailing whitespace on each segment is
                stripped.

        Returns:
            A validated :class:`DataProductRef` instance.

        Raises:
            ValidationError: ``full_name`` is not exactly two
                non-empty period-separated parts.
        """
        parts = [p.strip() for p in full_name.split(".")]
        if len(parts) != 2 or not all(parts):
            raise ValidationError(
                "data product must be a two-part UC name 'catalog.schema'"
            )
        return cls(".".join(parts))

    @classmethod
    def from_parts(cls, catalog: str, schema: str) -> Self:
        """Construct without validation (caller-checked path).

        Args:
            catalog: UC catalog name.
            schema: UC schema name.

        Returns:
            ``DataProductRef`` instance equal to
            ``f"{catalog}.{schema}"``.
        """
        return cls(f"{catalog}.{schema}")

    @property
    def catalog(self) -> str:
        """Return the catalog segment."""
        return self.split(".", 1)[0]

    @property
    def schema(self) -> str:
        """Return the schema segment."""
        return self.split(".", 1)[1]

    def parts(self) -> tuple[str, str]:
        """Return ``(catalog, schema)`` as a tuple."""
        c, s = self.split(".", 1)
        return c, s
