"""Per-(product,user) rating upsert + summary aggregate."""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import func, select

from pointlessql.models import DataProductRating
from pointlessql.types import SessionFactory


def upsert_rating(
    factory: SessionFactory,
    *,
    data_product_id: int,
    user_id: int,
    score: int,
    comment: str | None = None,
) -> dict[str, Any]:
    """Insert or update a (product, user) rating.

    Args:
        factory: SQLAlchemy sessionmaker for the metadata DB.
        data_product_id: Product the rating targets.
        user_id: Author of the rating; one row per (product, user)
            pair — a repeat call overwrites the previous rating.
        score: Star rating, 1..5 inclusive.
        comment: Optional free-text remark; blank / whitespace-only
            values are stored as ``None``.

    Returns:
        The persisted rating serialised as a dict (product, user,
        score, comment, ISO-formatted ``updated_at``).

    Raises:
        ValueError: When *score* is outside 1..5.
    """
    if not (1 <= int(score) <= 5):
        raise ValueError("score must be in 1..5")
    cleaned_comment = comment.strip() if isinstance(comment, str) and comment.strip() else None
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = session.scalar(
            select(DataProductRating).where(
                DataProductRating.data_product_id == data_product_id,
                DataProductRating.user_id == user_id,
            )
        )
        if row is None:
            row = DataProductRating(
                data_product_id=data_product_id,
                user_id=user_id,
                score=int(score),
                comment=cleaned_comment,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            row.score = int(score)
            row.comment = cleaned_comment
            row.updated_at = now
        session.commit()
        session.refresh(row)
        return {
            "data_product_id": row.data_product_id,
            "user_id": row.user_id,
            "score": row.score,
            "comment": row.comment,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }


def list_rating_summary(factory: SessionFactory, *, data_product_id: int) -> dict[str, Any]:
    """Return ``{avg, count}`` aggregate for one product."""
    with factory() as session:
        result = session.execute(
            select(
                func.avg(DataProductRating.score),
                func.count(DataProductRating.user_id),
            ).where(DataProductRating.data_product_id == data_product_id)
        ).one()
    avg_raw, count = result
    return {
        "avg": float(avg_raw) if avg_raw is not None else None,
        "count": int(count or 0),
    }
