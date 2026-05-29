"""Per-product infrastructure-declaration CRUD."""

from __future__ import annotations

from pointlessql.services.infrastructure._crud import (
    get_infrastructure,
    set_infrastructure,
)

__all__ = ["get_infrastructure", "set_infrastructure"]
