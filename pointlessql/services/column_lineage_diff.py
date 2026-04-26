"""Schema-diff helper that turns column lists into ``ColumnEdgeSpec``s.

Sprint 15.6.2 — used by ``pql.merge`` / ``pql.write_table`` /
``pql.autoload`` to populate the column-lineage table without
requiring the caller to spell every mapping out.  The algorithm is
plain set arithmetic on column-name lists; the DataFrame schema
itself is the contract:

1. Column appears in **both** source and target → ``identity`` edge.
2. Column is **target-only** and listed in ``derivations`` → one
   ``derived`` edge per declared source column.
3. Column is **target-only** and listed in ``audit_columns`` →
   ``unknown_origin`` edge with ``transform_detail="audit"``.
4. Column is **target-only** with no derivation declared →
   ``unknown_origin`` edge (the caller did not tell us where it
   came from).
5. Column is **source-only** ("dropped") → skipped in v1.  No UI
   surface consumes drop edges yet, and skipping keeps the CHECK
   enum tighter.  Reopen if a future "what columns did I drop"
   surface emerges.

When ``source_table`` is ``None`` (e.g. ``pql.write_table`` called
without ``source_table_fqn``), edges 1 / 2 collapse to
``unknown_origin`` because we cannot point at a real source.  Audit
edges still fire — they are intrinsic to the primitive, not the
caller's intent.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from pointlessql.services.lineage_edges import ColumnEdgeSpec


def infer_column_edges(
    *,
    source_columns: Sequence[str] | None,
    target_columns: Sequence[str],
    source_table: str | None,
    target_table: str,
    derivations: Mapping[str, Sequence[str]] | None = None,
    audit_columns: Iterable[str] = (),
) -> list[ColumnEdgeSpec]:
    """Turn source/target column lists into a list of column-edge specs.

    Args:
        source_columns: Column names on the upstream source frame.
            ``None`` when the primitive does not have a meaningful
            source schema (e.g. ``pql.write_table`` called without
            ``source_table_fqn`` or with a freshly built frame).
        target_columns: Column names that landed on the target
            table.  Empty input yields an empty result.
        source_table: Fully-qualified UC name of the source table,
            or ``None`` when the primitive ran without one.  When
            ``None``, identity / derived edges fall back to
            ``unknown_origin``.
        target_table: Fully-qualified UC name of the target table.
        derivations: Optional declarative mapping of derived target
            columns to their source column names — e.g. the
            ``.assign(placed_day=...)`` pattern.  Keys are target
            columns; values are lists of source column names that
            went into the derivation.  Source columns not present
            on ``source_columns`` still produce edges (with
            ``source_table=None`` / ``unknown_origin``) so the UI
            can surface that the caller declared a derivation for
            a column that wasn't on the source.
        audit_columns: Iterable of target column names that are
            primitive-injected audit fields (``_ingested_at``,
            ``_source_file``, etc.) — recorded as
            ``unknown_origin`` with ``transform_detail="audit"``.

    Returns:
        A list of :class:`ColumnEdgeSpec` ready to stash on the
        operation recorder.  Order is deterministic: identity
        edges in target order, then derived/audit/unknown_origin
        in target order.
    """
    if not target_columns:
        return []

    src_set: set[str] = set(source_columns or ())
    audit_set: set[str] = set(audit_columns)
    derivations = derivations or {}

    edges: list[ColumnEdgeSpec] = []
    for target_column in target_columns:
        if target_column in derivations:
            for source_column in derivations[target_column]:
                if source_column in src_set and source_table is not None:
                    edges.append(
                        ColumnEdgeSpec(
                            source_table=source_table,
                            source_column=source_column,
                            target_table=target_table,
                            target_column=target_column,
                            transform_kind="derived",
                            transform_detail=None,
                        )
                    )
                else:
                    edges.append(
                        ColumnEdgeSpec(
                            source_table=None,
                            source_column=None,
                            target_table=target_table,
                            target_column=target_column,
                            transform_kind="unknown_origin",
                            transform_detail=(
                                f"derivation references {source_column!r} "
                                f"which is not on source"
                            ),
                        )
                    )
            continue

        if target_column in audit_set:
            edges.append(
                ColumnEdgeSpec(
                    source_table=None,
                    source_column=None,
                    target_table=target_table,
                    target_column=target_column,
                    transform_kind="unknown_origin",
                    transform_detail="audit",
                )
            )
            continue

        if target_column in src_set and source_table is not None:
            edges.append(
                ColumnEdgeSpec(
                    source_table=source_table,
                    source_column=target_column,
                    target_table=target_table,
                    target_column=target_column,
                    transform_kind="identity",
                    transform_detail=None,
                )
            )
            continue

        edges.append(
            ColumnEdgeSpec(
                source_table=None,
                source_column=None,
                target_table=target_table,
                target_column=target_column,
                transform_kind="unknown_origin",
                transform_detail=None,
            )
        )

    return edges
