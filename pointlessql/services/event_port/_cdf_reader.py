"""Delta Change Data Feed reader for the event-stream output port.

Reads one window of CDF rows for ``catalog.schema.table`` starting at
*since_version*.  The window is bounded by ``max_versions`` to keep a
single pump cycle predictable — the pump invokes this repeatedly until
no new versions exist.

This module never broadcasts; it only returns rows.  The pump
(:mod:`._pump`) decides how to fan them out (WS hub + delivery ledger).
"""

from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass(frozen=True)
class ChangeRow:
    """One CDF row tagged with its commit version + change type.

    Attributes:
        version: Delta commit version this row was emitted from.
        commit_timestamp: ISO-8601 commit timestamp, or ``None`` when
            unavailable from the metadata.
        change_type: One of ``insert`` / ``update_preimage`` /
            ``update_postimage`` / ``delete`` (per Delta CDF schema).
        data: The data columns, keyed by name.
    """

    version: int
    commit_timestamp: str | None
    change_type: str
    data: dict[str, Any]


def read_changes(
    location: str,
    *,
    since_version: int,
    max_versions: int = 100,
) -> list[ChangeRow]:
    """Read CDF rows for the Delta table at *location*.

    The Delta table must already have CDF enabled (the write path
    invokes :func:`pointlessql.pql._cdf.ensure_cdf_enabled` on first
    write of a managed product table).  When *since_version* is past
    the head, an empty list is returned.

    Args:
        location: Delta table storage URI.
        since_version: Inclusive start commit version.
        max_versions: Cap on versions to read in one call — bounds
            pump cycle work.

    Returns:
        A list of :class:`ChangeRow`, ordered by ``(version,
        seq)``.  Empty when the table has no new versions, or when
        :mod:`deltalake` is not installed (best-effort import).

    Raises:
        ValueError: When ``since_version < 0`` or ``max_versions <= 0``.
    """
    if since_version < 0:
        raise ValueError("since_version must be >= 0")
    if max_versions <= 0:
        raise ValueError("max_versions must be > 0")

    try:
        from deltalake import DeltaTable  # noqa: PLC0415 — optional engine
    except ImportError:  # pragma: no cover — deltalake ships with the project
        return []

    try:
        table = DeltaTable(location)
    # bare-broad-ok: missing / unreadable table is normal "no CDF" return path
    except Exception:  # noqa: BLE001
        return []

    head_version: int | None = None
    try:
        head_version = int(table.version())
    # bare-broad-ok: version() may raise on storage stalls; None falls back below
    except Exception:  # noqa: BLE001
        head_version = None
    if head_version is not None and since_version > head_version:
        return []

    ending = (
        min(head_version, since_version + max_versions - 1)
        if head_version is not None
        else since_version + max_versions - 1
    )

    try:
        arrow = table.load_cdf(
            starting_version=since_version,
            ending_version=ending,
        ).read_all()
    # bare-broad-ok: CDF disabled on this table = empty result, not an error
    except Exception:  # noqa: BLE001
        return []

    rows: list[ChangeRow] = []
    columns = arrow.column_names
    for batch in arrow.to_batches():
        for i in range(batch.num_rows):
            row: dict[str, Any] = {}
            version = 0
            ts: str | None = None
            change_type = "insert"
            for col in columns:
                value = batch[col][i].as_py()
                if col == "_commit_version":
                    version = int(value) if value is not None else 0
                elif col == "_commit_timestamp":
                    ts = str(value) if value is not None else None
                elif col == "_change_type":
                    change_type = str(value) if value is not None else "insert"
                else:
                    row[col] = value
            rows.append(
                ChangeRow(
                    version=version,
                    commit_timestamp=ts,
                    change_type=change_type,
                    data=row,
                )
            )
    return rows
