"""Schema diff between yaml contract and actual write payload / Delta table.

Two entry points share the same pure ``_diff_columns`` core:

* :func:`diff_contract_against_engine_columns` — pre-write hook
  fed the tuples from ``Engine.columns_info(df)``.  Used by the
  enforcement service to refuse a write whose frame
  drops a required contract column or swaps a type incompatibly.
* :func:`diff_contract_against_delta_table` — live diff fed the
  on-disk schema via ``deltalake.DeltaTable(...).schema()``.  Used
  by ``GET /api/data-products/{ref}/diff`` to surface
  drift between the deployed table and the latest yaml.

Both adapters normalise the actual side into a list of
``ActualColumn`` triples then defer to the core.  Type comparison
is name-based after normalisation (``int`` widens to ``long``,
``decimal`` collapses scale, etc.) so the diff doesn't false-positive
on Delta's pyarrow-flavoured aliases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pointlessql.data_products._schema import (
    DataProductColumnSpec,
    DataProductTableContract,
)


@dataclass(frozen=True)
class ActualColumn:
    """One column as observed on the actual side of a diff.

    Captures only the fields the diff core needs to compare.  Both
    adapters (engine tuples + Delta schema) produce instances; the
    core never sees the raw upstream shape.
    """

    name: str
    type: str
    nullable: bool


@dataclass(frozen=True)
class ContractDiffResult:
    """Structured diff outcome.

    ``is_breaking`` is set when a contract-required column is
    missing on the actual side, when a type mismatch crosses an
    incompatible boundary (e.g. ``string`` ↔ ``long``), or when a
    primary-key column is dropped.  Other diffs (extra columns,
    type-widening, nullability widening) are captured as drift
    warnings and DO NOT set ``is_breaking``.
    """

    missing_columns: tuple[str, ...]
    extra_columns: tuple[str, ...]
    type_mismatches: tuple[tuple[str, str, str], ...]  # (name, contract_type, actual_type)
    nullability_mismatches: tuple[tuple[str, bool, bool], ...]  # (name, contract, actual)
    dropped_pk_columns: tuple[str, ...]
    is_breaking: bool

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dict (used by HTTP + audit-event payloads)."""
        return {
            "missing_columns": list(self.missing_columns),
            "extra_columns": list(self.extra_columns),
            "type_mismatches": [
                {"name": n, "contract": c, "actual": a}
                for (n, c, a) in self.type_mismatches
            ],
            "nullability_mismatches": [
                {"name": n, "contract": c, "actual": a}
                for (n, c, a) in self.nullability_mismatches
            ],
            "dropped_pk_columns": list(self.dropped_pk_columns),
            "is_breaking": self.is_breaking,
        }


# Canonicalisation map: anything in the value list collapses to the
# key.  Two types compare equal iff their canonical forms match.
_CANONICAL_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "string": ("str", "varchar", "text", "utf8", "large_string"),
    "long": ("int64", "bigint"),
    "integer": ("int", "int32"),
    "double": ("float64",),
    "boolean": ("bool",),
    "timestamp": ("timestamp[us]", "timestamp[ns]", "timestamp[ms]", "datetime"),
    "date": ("date32", "date64"),
    "decimal": ("decimal128", "decimal256"),
    "binary": ("bytes", "large_binary"),
}


def _canonical(type_name: str) -> str:
    """Collapse a type token into its canonical contract form.

    The contract uses 11 stable type names; the on-the-wire actual
    side may report any of a wider set (pyarrow logical types,
    deltalake-internal aliases).  We use canonical names so the diff
    isn't fooled by surface variation.
    """
    lowered = type_name.lower().strip()
    for canonical, aliases in _CANONICAL_TYPE_ALIASES.items():
        if lowered == canonical or lowered in aliases:
            return canonical
        # decimal(10,2) etc. all collapse to "decimal"
        if canonical == "decimal" and lowered.startswith("decimal"):
            return "decimal"
        if canonical == "timestamp" and lowered.startswith("timestamp"):
            return "timestamp"
    return lowered


def _types_compatible(contract_type: str, actual_type: str) -> bool:
    """Return ``True`` when the actual type satisfies the contract.

    Compatibility is symmetric for now — every type widening that
    Delta accepts in a non-overwrite write would also produce a
    type mismatch on read, so we don't try to be clever.  Future
    refinement (e.g. accept ``int`` where ``long`` is declared) is
    a backwards-compatible loosening.
    """
    return _canonical(contract_type) == _canonical(actual_type)


def _diff_columns(
    contract: DataProductTableContract,
    actual: list[ActualColumn],
    *,
    check_nullability: bool = True,
) -> ContractDiffResult:
    """Pure diff logic — no IO, no engine awareness.

    The actual list is iterated in order; column lookup is by name
    so position-shifts don't false-positive (Delta tolerates column
    re-ordering in append mode).  Casing is significant — Delta
    column names are case-sensitive on the wire.

    ``check_nullability`` is the engine-vs-Delta-schema escape
    hatch.  In-memory frames (pandas / arrow / polars) report every
    column as nullable because the engine has no constraint
    metadata; passing ``False`` skips nullability comparison so the
    pre-write hook isn't paralysed by a sentinel.  The live-diff
    helper that reads the on-disk Delta schema keeps the default
    ``True`` and surfaces real mismatches.
    """
    actual_by_name: dict[str, ActualColumn] = {col.name: col for col in actual}
    contract_by_name: dict[str, DataProductColumnSpec] = {
        col.name: col for col in contract.columns
    }

    missing: list[str] = []
    type_mismatches: list[tuple[str, str, str]] = []
    nullability_mismatches: list[tuple[str, bool, bool]] = []
    for spec in contract.columns:
        actual_col = actual_by_name.get(spec.name)
        if actual_col is None:
            missing.append(spec.name)
            continue
        if not _types_compatible(spec.type, actual_col.type):
            type_mismatches.append((spec.name, spec.type, actual_col.type))
        if check_nullability and not spec.nullable and actual_col.nullable:
            nullability_mismatches.append((spec.name, spec.nullable, actual_col.nullable))

    extra: list[str] = [c.name for c in actual if c.name not in contract_by_name]

    declared_pk = contract.primary_key or ()
    dropped_pk = [pk for pk in declared_pk if pk not in actual_by_name]

    is_breaking = bool(missing or type_mismatches or dropped_pk)

    return ContractDiffResult(
        missing_columns=tuple(missing),
        extra_columns=tuple(extra),
        type_mismatches=tuple(type_mismatches),
        nullability_mismatches=tuple(nullability_mismatches),
        dropped_pk_columns=tuple(dropped_pk),
        is_breaking=is_breaking,
    )


def diff_contract_against_engine_columns(
    contract: DataProductTableContract,
    columns: list[tuple[str, str, str, bool]],
) -> ContractDiffResult:
    """Diff a yaml contract against ``Engine.columns_info(df)`` tuples.

    Args:
        contract: The yaml table contract.
        columns: Tuples in the
            ``(name, type_name, type_text, nullable)`` shape returned
            by the engine.  ``type_text`` is the lowercase form
            ("long", "string", …) used for canonicalisation.

    Returns:
        Structured diff with ``is_breaking`` set when the engine
        frame would drop a required column or swap a type
        incompatibly.
    """
    actual = [
        ActualColumn(name=name, type=type_text, nullable=nullable)
        for (name, _type_name, type_text, nullable) in columns
    ]
    # Engine-derived tuples can't express non-nullable — every pandas
    # / arrow / polars column is nullable=True by default.  Skip the
    # comparison so the pre-write hook doesn't false-positive on the
    # contract's ``nullable: false`` columns.
    return _diff_columns(contract, actual, check_nullability=False)


def diff_contract_against_delta_table(
    contract: DataProductTableContract,
    storage_location: str,
) -> ContractDiffResult:
    """Diff a yaml contract against the on-disk Delta schema.

    Reads ``deltalake.DeltaTable(storage_location).schema()`` and
    extracts the ``(name, type, nullable)`` tuples.  Used by the
    live-diff endpoint and by the enforcement service when the
    target table already exists (overwrite mode).

    Args:
        contract: The yaml table contract.
        storage_location: Filesystem path or URI of the Delta table.

    Returns:
        Structured diff result.

    The deltalake client raises its own exceptions when the path is
    missing or unreadable; the helper propagates them so callers can
    map them onto a "Delta table unavailable, drift=unknown" envelope
    rather than panicking.
    """
    import deltalake

    table = deltalake.DeltaTable(storage_location)
    schema = table.schema()
    actual = [
        ActualColumn(name=field.name, type=str(field.type), nullable=field.nullable)
        for field in schema.fields
    ]
    return _diff_columns(contract, actual)
