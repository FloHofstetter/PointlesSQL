"""Tests for the Phase 40.5 CDF tail subscriptions + worker."""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import deltalake
import httpx
import pyarrow as pa
import pytest

from pointlessql.api.main import app
from pointlessql.models import CdfTailEvent, CdfTailSubscription
from pointlessql.pql._cdf import cdf_creation_config
from pointlessql.services import cdf_tail


def _seed_subscription(
    *,
    table_full_name: str = "demo.silver.orders",
    row_id_column: str = "id",
    is_active: bool = True,
) -> int:
    """Insert one CdfTailSubscription and return its id."""
    factory = app.state.session_factory
    with factory() as session:
        sub = CdfTailSubscription(
            workspace_id=1,
            table_full_name=table_full_name,
            row_id_column=row_id_column,
            producer_label=f"cdf-tail:{table_full_name}",
            is_active=is_active,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(sub)
        session.commit()
        session.refresh(sub)
        return sub.id


def _make_cdf_table(tmp_path: Path) -> str:
    """Write a small two-version Delta table with CDF on; return path."""
    target = tmp_path / "cdf_demo"
    deltalake.write_deltalake(
        str(target),
        pa.table({"id": [1, 2], "amount": [10, 20]}),
        configuration=cdf_creation_config(),
    )
    deltalake.write_deltalake(
        str(target),
        pa.table({"id": [3, 4], "amount": [30, 40]}),
        mode="append",
    )
    return str(target)


# ---------------------------------------------------------------------------
# Service: tail_subscription
# ---------------------------------------------------------------------------


class TestTailSubscription:
    """``cdf_tail.tail_subscription`` advances pointer + dedupes."""

    def test_returns_zero_when_paused(self, tmp_path: Path) -> None:
        sub_id = _seed_subscription(is_active=False)
        loc = _make_cdf_table(tmp_path)
        inserted = cdf_tail.tail_subscription(
            app.state.session_factory,
            sub_id,
            history_limit=10,
            storage_location=loc,
        )
        assert inserted == 0

    def test_captures_insert_events_and_advances_pointer(self, tmp_path: Path) -> None:
        sub_id = _seed_subscription()
        loc = _make_cdf_table(tmp_path)
        inserted = cdf_tail.tail_subscription(
            app.state.session_factory,
            sub_id,
            history_limit=10,
            storage_location=loc,
        )
        assert inserted >= 4  # 4 inserts across versions 0+1
        with app.state.session_factory() as session:
            events = list(
                session.query(CdfTailEvent).filter(CdfTailEvent.subscription_id == sub_id).all()
            )
            sub = session.get(CdfTailSubscription, sub_id)
        assert sub is not None
        assert sub.last_version_processed == 1
        assert sub.last_error is None
        assert sub.last_tailed_at is not None
        change_types = {e.change_type for e in events}
        assert change_types == {"insert"}
        row_ids = sorted(int(e.row_id) for e in events)
        assert row_ids == [1, 2, 3, 4]

    def test_re_tail_is_idempotent(self, tmp_path: Path) -> None:
        sub_id = _seed_subscription()
        loc = _make_cdf_table(tmp_path)
        first = cdf_tail.tail_subscription(
            app.state.session_factory,
            sub_id,
            history_limit=10,
            storage_location=loc,
        )
        # Reset pointer so the second call replays the same range.
        with app.state.session_factory() as session:
            sub = session.get(CdfTailSubscription, sub_id)
            assert sub is not None
            sub.last_version_processed = -1  # type: ignore[assignment]
            session.commit()
        second = cdf_tail.tail_subscription(
            app.state.session_factory,
            sub_id,
            history_limit=10,
            storage_location=loc,
        )
        assert first >= 4
        assert second == 0  # every row UNIQUE-deduped


# ---------------------------------------------------------------------------
# Service: tail_all (UC integration shape)
# ---------------------------------------------------------------------------


class TestTailAll:
    """``cdf_tail.tail_all`` walks active subs + stamps errors."""

    @pytest.mark.asyncio
    async def test_skips_when_no_subscriptions(self) -> None:
        # Confirm the empty-registry fast path returns 0.
        uc = AsyncMock()
        inserted = await cdf_tail.tail_all(app.state.session_factory, uc)
        assert inserted == 0
        uc.get_table.assert_not_called()

    @pytest.mark.asyncio
    async def test_stamps_error_when_uc_lookup_fails(self) -> None:
        sub_id = _seed_subscription()
        uc = AsyncMock()
        uc.get_table = AsyncMock(side_effect=RuntimeError("uc down"))
        inserted = await cdf_tail.tail_all(app.state.session_factory, uc)
        assert inserted == 0
        with app.state.session_factory() as session:
            sub = session.get(CdfTailSubscription, sub_id)
        assert sub is not None
        assert sub.last_error is not None
        assert "uc.get_table failed" in sub.last_error

    @pytest.mark.asyncio
    async def test_resolves_storage_and_inserts(self, tmp_path: Path) -> None:
        sub_id = _seed_subscription()
        loc = _make_cdf_table(tmp_path)
        uc = AsyncMock()
        uc.get_table = AsyncMock(return_value={"storage_location": loc})
        inserted = await cdf_tail.tail_all(app.state.session_factory, uc)
        assert inserted >= 4
        with app.state.session_factory() as session:
            sub = session.get(CdfTailSubscription, sub_id)
        assert sub is not None
        assert sub.last_version_processed == 1
        assert sub.last_error is None


# ---------------------------------------------------------------------------
# Admin CRUD routes
# ---------------------------------------------------------------------------


class TestAdminCdfSubscriptions:
    """``/api/admin/cdf-subscriptions`` happy path + scoping."""

    @pytest.mark.asyncio
    async def test_create_list_toggle_delete_round_trip(
        self, admin_client: httpx.AsyncClient
    ) -> None:
        create = await admin_client.post(
            "/api/admin/cdf-subscriptions",
            json={
                "table_full_name": "demo.silver.orders",
                "row_id_column": "id",
            },
        )
        assert create.status_code == 200, create.text
        payload = create.json()
        assert payload["table_full_name"] == "demo.silver.orders"
        assert payload["producer_label"] == "cdf-tail:demo.silver.orders"
        assert payload["is_active"] is True
        assert payload["last_version_processed"] is None
        sub_id = payload["id"]

        listing = await admin_client.get("/api/admin/cdf-subscriptions")
        assert listing.status_code == 200
        ids = [r["id"] for r in listing.json()["subscriptions"]]
        assert sub_id in ids

        toggle = await admin_client.post(f"/api/admin/cdf-subscriptions/{sub_id}/toggle")
        assert toggle.status_code == 200
        assert toggle.json()["is_active"] is False

        delete = await admin_client.delete(f"/api/admin/cdf-subscriptions/{sub_id}")
        assert delete.status_code == 200
        assert delete.json() == {"id": sub_id, "deleted": True}

    @pytest.mark.asyncio
    async def test_create_rejects_invalid_payload(self, admin_client: httpx.AsyncClient) -> None:
        missing_row_id = await admin_client.post(
            "/api/admin/cdf-subscriptions",
            json={"table_full_name": "demo.silver.orders"},
        )
        two_part = await admin_client.post(
            "/api/admin/cdf-subscriptions",
            json={"table_full_name": "demo.orders", "row_id_column": "id"},
        )
        assert missing_row_id.status_code == 422
        assert two_part.status_code == 422

    @pytest.mark.asyncio
    async def test_create_rejects_duplicate(self, admin_client: httpx.AsyncClient) -> None:
        first = await admin_client.post(
            "/api/admin/cdf-subscriptions",
            json={
                "table_full_name": "demo.silver.dupes",
                "row_id_column": "id",
            },
        )
        second = await admin_client.post(
            "/api/admin/cdf-subscriptions",
            json={
                "table_full_name": "demo.silver.dupes",
                "row_id_column": "id",
            },
        )
        assert first.status_code == 200
        assert second.status_code == 422
