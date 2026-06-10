"""Per-query cost meter that writes raw ledger rows."""

from __future__ import annotations

import dataclasses
import datetime
import json
from decimal import Decimal

from pointlessql.models import DataProductQueryCost
from pointlessql.types import SessionFactory


@dataclasses.dataclass(slots=True, frozen=True)
class MeterContext:
    """Per-query attribution passed to :func:`record_query_cost`.

    Attributes:
        started_at: Wall-clock when execution started.
        completed_at: Wall-clock when execution finished (or None on error).
        duration_ms: Total duration; None on error before runtime.
        estimated_cost: Cost-gate estimate value.
        bytes_scanned: Optional bytes-scanned counter.
        rows_returned: Optional rows-returned counter.
        tables: List of UC ``catalog.schema.table`` refs the query touched.
        principal_user_id: Caller user PK.
        api_key_id: API key PK when the call was bearer-auth.
        authoring_product_id: Product the read targeted.
        consumer_product_id: Product the caller represented.
        query_kind: Free-form query kind (default ``select``).
        error_class: Non-empty when the query failed.
    """

    started_at: datetime.datetime
    completed_at: datetime.datetime | None
    duration_ms: int | None
    estimated_cost: Decimal | float
    bytes_scanned: int | None
    rows_returned: int | None
    tables: list[str]
    principal_user_id: int | None
    api_key_id: int | None
    authoring_product_id: int | None
    consumer_product_id: int | None
    query_kind: str = "select"
    error_class: str | None = None


def record_query_cost(session_factory: SessionFactory, ctx: MeterContext) -> int:
    """Insert one :class:`DataProductQueryCost` row and return its id."""
    cost_value = (
        ctx.estimated_cost
        if isinstance(ctx.estimated_cost, Decimal)
        else Decimal(str(ctx.estimated_cost))
    )
    with session_factory() as session:
        row = DataProductQueryCost(
            started_at=ctx.started_at,
            completed_at=ctx.completed_at,
            duration_ms=ctx.duration_ms,
            estimated_cost=cost_value,
            bytes_scanned=ctx.bytes_scanned,
            rows_returned=ctx.rows_returned,
            table_list_json=json.dumps(ctx.tables, separators=(",", ":")),
            principal_user_id=ctx.principal_user_id,
            api_key_id=ctx.api_key_id,
            authoring_product_id=ctx.authoring_product_id,
            consumer_product_id=ctx.consumer_product_id,
            query_kind=ctx.query_kind,
            error_class=ctx.error_class,
        )
        session.add(row)
        session.commit()
        return int(row.id)
