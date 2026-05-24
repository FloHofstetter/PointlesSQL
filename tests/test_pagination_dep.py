"""Tests for the pagination() FastAPI dependency added in Phase 121.2."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from pointlessql.api.dependencies import PaginationParams, pagination


def _build_app() -> FastAPI:
    """Tiny FastAPI app that echoes the resolved pagination params."""
    app = FastAPI()

    @app.get("/items")
    def list_items(p: PaginationParams = Depends(pagination)) -> dict[str, int]:
        return {"offset": p.offset, "limit": p.limit}

    return app


def test_pagination_defaults() -> None:
    """No query string → offset=0, limit=100."""
    client = TestClient(_build_app())
    r = client.get("/items")
    assert r.status_code == 200
    assert r.json() == {"offset": 0, "limit": 100}


def test_pagination_custom_values() -> None:
    """Explicit values pass through unchanged when within bounds."""
    client = TestClient(_build_app())
    r = client.get("/items", params={"offset": 25, "limit": 50})
    assert r.status_code == 200
    assert r.json() == {"offset": 25, "limit": 50}


def test_pagination_rejects_negative_offset() -> None:
    """offset<0 → 422 from FastAPI's Query(ge=0) validator."""
    client = TestClient(_build_app())
    r = client.get("/items", params={"offset": -1})
    assert r.status_code == 422


def test_pagination_rejects_zero_limit() -> None:
    """limit=0 → 422 (limit has ge=1)."""
    client = TestClient(_build_app())
    r = client.get("/items", params={"limit": 0})
    assert r.status_code == 422


def test_pagination_rejects_limit_above_ceiling() -> None:
    """limit>1000 → 422 (limit has le=1000)."""
    client = TestClient(_build_app())
    r = client.get("/items", params={"limit": 1001})
    assert r.status_code == 422


def test_pagination_accepts_ceiling_limit() -> None:
    """limit=1000 is the inclusive ceiling."""
    client = TestClient(_build_app())
    r = client.get("/items", params={"limit": 1000})
    assert r.status_code == 200
    assert r.json() == {"offset": 0, "limit": 1000}


def test_pagination_params_dataclass_is_frozen() -> None:
    """PaginationParams is frozen — accidental mutation surfaces."""
    p = PaginationParams(offset=10, limit=20)
    import dataclasses

    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        p.offset = 0  # type: ignore[misc]
