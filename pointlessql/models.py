"""SQLAlchemy ORM models for PointlesSQL's own metadata database."""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all PointlesSQL models."""


class User(Base):
    """A local user account with email/password authentication.

    Attributes:
        id: Auto-incremented primary key.
        email: Unique email address (max 254 chars).
        display_name: Human-readable name shown in the navbar.
        password_hash: Bcrypt-hashed password string.
        is_admin: Whether the user has administrator privileges.
        created_at: Timestamp when the user was created.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
