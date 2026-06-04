"""Use-case + vote CRUD with cached vote count."""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import func, select

from pointlessql.models import (
    DataProductUseCase,
    DataProductUseCaseVote,
)
from pointlessql.types import SessionFactory


def _serialise(uc: DataProductUseCase) -> dict[str, Any]:
    return {
        "id": uc.id,
        "title": uc.title,
        "body": uc.body,
        "author_user_id": uc.author_user_id,
        "votes": uc.votes,
        "created_at": uc.created_at.isoformat() if uc.created_at else None,
        "updated_at": uc.updated_at.isoformat() if uc.updated_at else None,
    }


def add_use_case(
    factory: SessionFactory,
    *,
    data_product_id: int,
    title: str,
    body: str,
    author_user_id: int | None,
) -> dict[str, Any]:
    """Insert one use-case row.

    Raises:
        ValueError: When *title* is empty or longer than 200 chars.
    """
    cleaned_title = title.strip()
    if not cleaned_title or len(cleaned_title) > 200:
        raise ValueError("title must be 1..200 chars")
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = DataProductUseCase(
            data_product_id=data_product_id,
            title=cleaned_title,
            body=body or "",
            author_user_id=author_user_id,
            votes=0,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _serialise(row)


def list_use_cases(
    factory: SessionFactory, *, data_product_id: int, limit: int | None = None
) -> list[dict[str, Any]]:
    """Return the product's use cases ordered by ``votes`` then newest."""
    with factory() as session:
        stmt = (
            select(DataProductUseCase)
            .where(DataProductUseCase.data_product_id == data_product_id)
            .order_by(DataProductUseCase.votes.desc(), DataProductUseCase.id.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = list(session.scalars(stmt).all())
    return [_serialise(r) for r in rows]


def delete_use_case(
    factory: SessionFactory, *, data_product_id: int, use_case_id: int
) -> bool:
    """Delete one use case.  Returns True when a row was removed."""
    with factory() as session:
        row = session.scalar(
            select(DataProductUseCase).where(
                DataProductUseCase.id == use_case_id,
                DataProductUseCase.data_product_id == data_product_id,
            )
        )
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def vote_use_case(
    factory: SessionFactory,
    *,
    use_case_id: int,
    user_id: int,
    upvote: bool = True,
) -> dict[str, Any]:
    """Toggle a vote and refresh the cached count.

    Args:
        factory: Sessionmaker callable.
        use_case_id: The use case to vote on.
        user_id: The voter.
        upvote: When True, record (or keep) the vote; when False,
            remove an existing vote.

    Returns:
        ``{"use_case_id": int, "voted": bool, "votes": int}``.
    """
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        existing = session.scalar(
            select(DataProductUseCaseVote).where(
                DataProductUseCaseVote.use_case_id == use_case_id,
                DataProductUseCaseVote.user_id == user_id,
            )
        )
        if upvote and existing is None:
            session.add(
                DataProductUseCaseVote(
                    use_case_id=use_case_id,
                    user_id=user_id,
                    created_at=now,
                )
            )
            voted = True
        elif not upvote and existing is not None:
            session.delete(existing)
            voted = False
        else:
            voted = existing is not None
        # Refresh cached count.
        count = (
            session.scalar(
                select(func.count())
                .select_from(DataProductUseCaseVote)
                .where(DataProductUseCaseVote.use_case_id == use_case_id)
            )
            or 0
        )
        uc = session.get(DataProductUseCase, use_case_id)
        if uc is not None:
            uc.votes = int(count)
            uc.updated_at = now
        session.commit()
        return {
            "use_case_id": use_case_id,
            "voted": voted,
            "votes": int(count),
        }
