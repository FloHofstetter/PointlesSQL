"""Schema-level smoke tests for the Phase 120 ACL + usage tables."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import (
    ApiKey,
    ApiKeyCatalogGrant,
    ApiKeyIpGrant,
    ApiKeyUsageBucket,
)
from pointlessql.services import api_keys as api_keys_service


def _wipe() -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.query(ApiKeyUsageBucket).delete()
        session.query(ApiKeyIpGrant).delete()
        session.query(ApiKeyCatalogGrant).delete()
        session.query(ApiKey).delete()
        session.commit()
    api_keys_service.invalidate_cache()


def test_catalog_grant_unique_per_key_catalog_schema() -> None:
    """The composite unique constraint blocks exact duplicates."""
    import pytest
    from sqlalchemy.exc import IntegrityError

    _wipe()
    row, _ = api_keys_service.create_api_key(app.state.session_factory, name="acl-k")
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            ApiKeyCatalogGrant(
                api_key_id=row.id,
                catalog_name="main",
                schema_name="sales",
                granted_at=datetime.now(UTC),
            )
        )
        session.commit()
        session.add(
            ApiKeyCatalogGrant(
                api_key_id=row.id,
                catalog_name="main",
                schema_name="sales",
                granted_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    _wipe()


def test_ip_grant_unique_per_key_cidr() -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    _wipe()
    row, _ = api_keys_service.create_api_key(app.state.session_factory, name="ip-k")
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            ApiKeyIpGrant(
                api_key_id=row.id,
                cidr="10.0.0.0/8",
                label="office",
                granted_at=datetime.now(UTC),
            )
        )
        session.commit()
        session.add(
            ApiKeyIpGrant(
                api_key_id=row.id,
                cidr="10.0.0.0/8",
                label="duplicate-attempt",
                granted_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    _wipe()


def test_usage_bucket_round_trip() -> None:
    _wipe()
    row, _ = api_keys_service.create_api_key(app.state.session_factory, name="usage-k")
    factory = app.state.session_factory
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    with factory() as session:
        session.add(
            ApiKeyUsageBucket(
                api_key_id=row.id,
                bucket_minute=now,
                source_ip="127.0.0.1",
                count=5,
                last_seen_at=now,
            )
        )
        session.commit()
        roundtrip = session.scalar(
            select(ApiKeyUsageBucket).where(ApiKeyUsageBucket.api_key_id == row.id)
        )
        assert roundtrip is not None
        assert roundtrip.count == 5
        assert roundtrip.source_ip == "127.0.0.1"
    _wipe()
