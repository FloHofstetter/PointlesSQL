"""Per-principal UC clients are cached, bounded, and closed — not leaked.

``get_uc_client`` used to mint a fresh ``UnityCatalogClient`` (and a fresh
httpx connection pool) on every authenticated request, never closing it —
a file-descriptor / connection leak under load. It now caches one client
per principal on ``app.state``, evicts the oldest past a cap, and closes
every pool at lifespan shutdown via ``close_principal_uc_clients``.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from pointlessql.api.dependencies import _principal
from pointlessql.api.dependencies._principal import (
    close_principal_uc_clients,
    get_uc_client,
)
from pointlessql.config import Settings
from pointlessql.services.unitycatalog import UnityCatalogClient


@pytest.fixture
def app_state() -> Any:
    """A fresh app-state namespace with its own client cache."""
    return SimpleNamespace(settings=Settings(), uc_client=object())


def _request(app_state: Any, principal: str | None) -> Any:
    """A duck-typed request bound to *app_state* with *principal* as the user."""
    user = {"email": principal} if principal else None
    return SimpleNamespace(
        headers={},
        state=SimpleNamespace(user=user),
        app=SimpleNamespace(state=app_state),
    )


@pytest.fixture
def created(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Stub ``for_principal`` to hand out closeable sentinels and record them."""
    made: list[Any] = []

    def _fake_for_principal(cls: Any, settings: Any, principal: str) -> Any:
        client = SimpleNamespace(principal=principal, aclose=AsyncMock())
        made.append(client)
        return client

    monkeypatch.setattr(UnityCatalogClient, "for_principal", classmethod(_fake_for_principal))
    return made


def test_no_principal_returns_default_client(app_state: Any) -> None:
    """An anonymous request gets the shared app-state client, no new pool."""
    assert get_uc_client(_request(app_state, None)) is app_state.uc_client


def test_same_principal_reuses_one_client(app_state: Any, created: list[Any]) -> None:
    """Repeated calls for one principal return the same cached client."""
    first = get_uc_client(_request(app_state, "alice@x.com"))
    second = get_uc_client(_request(app_state, "alice@x.com"))
    assert first is second
    assert len(created) == 1


def test_distinct_principals_get_distinct_clients(app_state: Any, created: list[Any]) -> None:
    """Each principal gets its own cached client."""
    get_uc_client(_request(app_state, "alice@x.com"))
    get_uc_client(_request(app_state, "bob@x.com"))
    assert len(created) == 2


async def test_close_closes_and_clears_every_cached_client(
    app_state: Any, created: list[Any]
) -> None:
    """Lifespan shutdown closes every cached pool and empties the cache."""
    get_uc_client(_request(app_state, "alice@x.com"))
    get_uc_client(_request(app_state, "bob@x.com"))

    await close_principal_uc_clients(app_state)

    for client in created:
        client.aclose.assert_awaited_once()
    assert app_state.principal_uc_clients == {}


async def test_cache_evicts_oldest_past_cap(
    app_state: Any, created: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Past the cap the oldest client is evicted and its pool closed."""
    monkeypatch.setattr(_principal, "_PRINCIPAL_CLIENT_CACHE_CAP", 2)
    get_uc_client(_request(app_state, "a@x.com"))
    get_uc_client(_request(app_state, "b@x.com"))
    get_uc_client(_request(app_state, "c@x.com"))  # evicts a@x.com

    # The eviction close is scheduled on the loop — let it run.
    await asyncio.sleep(0)

    assert set(app_state.principal_uc_clients) == {"b@x.com", "c@x.com"}
    evicted = created[0]
    evicted.aclose.assert_awaited_once()
