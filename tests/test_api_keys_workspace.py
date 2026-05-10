"""Sprint 28.0 wiring tests for ``api_keys.workspace_id``.

Confirms three properties:

1. The bootstrap migration shape is mirrored by the test fixture —
   every existing API key has ``workspace_id=1`` after seed.
2. :func:`api_keys_service.create_api_key` honours an explicit
   ``workspace_id`` argument and defaults to 1.
3. :func:`api_keys_service.verify_bearer` propagates
   ``workspace_id`` onto the :class:`KeyEntry` returned to the
   middleware.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pointlessql.api.main import app
from pointlessql.models import ApiKey
from pointlessql.services import api_keys as api_keys_service
from pointlessql.services.workspace import _crud as workspaces_service


def _factory():
    return app.state.session_factory


def _wipe_api_keys() -> None:
    factory = _factory()
    with factory() as session:
        session.query(ApiKey).delete()
        session.commit()
    api_keys_service.invalidate_cache()


@pytest.fixture(autouse=True)
def _isolation() -> Iterator[None]:
    _wipe_api_keys()
    try:
        yield
    finally:
        _wipe_api_keys()


def test_create_api_key_defaults_workspace_to_one() -> None:
    row, _ = api_keys_service.create_api_key(_factory(), name="default-ws")
    assert row.workspace_id == 1


def test_create_api_key_honours_explicit_workspace() -> None:
    ws = workspaces_service.create_workspace(_factory(), slug="other", name="x")
    row, _ = api_keys_service.create_api_key(_factory(), name="other-ws", workspace_id=ws.id)
    assert row.workspace_id == ws.id


def test_verify_bearer_carries_workspace_id_into_key_entry() -> None:
    ws = workspaces_service.create_workspace(_factory(), slug="bearer-ws", name="x")
    _, plaintext = api_keys_service.create_api_key(
        _factory(), name="bearer", auditor=True, workspace_id=ws.id
    )
    entry = api_keys_service.verify_bearer(f"Bearer {plaintext}", _factory())
    assert entry is not None
    assert entry.workspace_id == ws.id
    assert entry.auditor is True


def test_bootstrap_from_env_pins_to_default_workspace() -> None:
    inserted = api_keys_service.bootstrap_from_env(
        _factory(),
        env={"POINTLESSQL_API_KEYS": "boot:bootsecret123:auditor"},
    )
    assert inserted == 1
    with _factory()() as session:
        row = session.query(ApiKey).filter(ApiKey.name == "boot").one()
        assert row.workspace_id == 1
        assert row.auditor is True


def test_key_entry_default_workspace_id_is_one() -> None:
    """Defensive — code paths that build a KeyEntry without a workspace land at 1."""
    entry = api_keys_service.KeyEntry(name="x", supervisor=False)
    assert entry.workspace_id == 1
