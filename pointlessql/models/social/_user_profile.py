"""Per-user profile row.

One row per ``users.id`` carrying the editable profile fields the
``/users/{id}`` page surfaces.  Lazily created on first PUT — a
missing row is rendered as the default empty profile so we don't
have to seed one for every existing user at migration time.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class UserProfile(Base):
    """Editable profile fields for one user.

    Attributes:
        user_id: PK + FK on ``users.id`` (``ondelete='CASCADE'``).
        bio_md: Free-form markdown bio rendered on the profile
            page.  Empty by default.
        avatar_url: Optional override for the gravatar fallback.
        location: Optional free-form location text.
        links_json: JSON-encoded list of ``{label, url}`` entries
            rendered as a small chip-row on the profile.
        updated_at: Wall-clock at the latest PUT.
    """

    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    bio_md: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    links_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
