"""Declarative base for every PointlesSQL ORM model.

Sprint 80 split out of the monolithic ``models.py`` so domain modules
can ``from pointlessql.models.base import Base`` without dragging the
full schema into their import graph.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all PointlesSQL models."""
