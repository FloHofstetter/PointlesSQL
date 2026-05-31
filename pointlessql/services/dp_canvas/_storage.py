"""Persistence facade for ``data_product_canvas_graph`` rows.

Two functions plus a tiny load helper — the editor saves the graph
on every materialise (executor side) and reads back the latest
version on editor open (route layer consumer).
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from pointlessql.models import DataProductCanvasGraph
from pointlessql.services.dp_canvas._types import CanvasDoc

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def save_graph(
    factory: sessionmaker[Session],
    *,
    data_product_id: int,
    doc: CanvasDoc,
    author_user_id: int | None,
) -> int:
    """Persist *doc* as the next version under *data_product_id*.

    ``version`` is monotonic per product — ``max(version) + 1`` over the
    existing rows.  The UNIQUE constraint on the table guarantees the
    same number never lands twice even under concurrent saves; the
    second writer to commit raises ``IntegrityError`` and should retry.

    Returns:
        The newly-minted ``version`` integer.
    """
    payload = doc.model_dump_json()
    with factory.begin() as session:
        current = session.execute(
            select(DataProductCanvasGraph.version)
            .where(DataProductCanvasGraph.data_product_id == data_product_id)
            .order_by(DataProductCanvasGraph.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        next_version = (current or 0) + 1
        row = DataProductCanvasGraph(
            data_product_id=data_product_id,
            version=next_version,
            document=payload,
            author_user_id=author_user_id,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(row)
        session.flush()
        return next_version


def load_latest_graph(
    factory: sessionmaker[Session],
    *,
    data_product_id: int,
) -> tuple[CanvasDoc, int] | None:
    """Return the most recent ``(doc, version)`` for *data_product_id*.

    ``None`` when the product has no saved graph yet — the editor renders
    an empty canvas in that case.
    """
    with factory() as session:
        row = session.execute(
            select(DataProductCanvasGraph)
            .where(DataProductCanvasGraph.data_product_id == data_product_id)
            .order_by(DataProductCanvasGraph.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None
        doc = CanvasDoc.model_validate_json(row.document)
        return doc, row.version


__all__ = ["save_graph", "load_latest_graph"]
