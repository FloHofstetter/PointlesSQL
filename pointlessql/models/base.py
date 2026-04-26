"""Declarative base for every PointlesSQL ORM model.

Lives in its own module so domain modules can
``from pointlessql.models.base import Base`` without dragging the
full schema into their import graph.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all PointlesSQL models."""
