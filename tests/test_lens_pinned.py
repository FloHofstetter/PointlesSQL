"""pinned-answer routes + service tests."""

from __future__ import annotations

import datetime

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import LensMessage, LensPinnedAnswer, LensSession


def _wipe_pin_state() -> None:
    """Clear lens session/message/pin tables."""
    factory = app.state.session_factory
    with factory() as s:
        s.query(LensPinnedAnswer).delete()
        s.query(LensMessage).delete()
        s.query(LensSession).delete()
        s.commit()


def _seed_session_with_assistant(*, owner_id: int = 1) -> tuple[int, int]:
    """Create one session + one assistant message; return (session_id, msg_id)."""
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        sess = LensSession(
            workspace_id=1,
            owner_id=owner_id,
            title="pin-test",
            llm_provider="anthropic",
            llm_model="claude-haiku-4-5-20251001",
            total_cost_estimate=0.0,
            created_at=now,
            updated_at=now,
        )
        s.add(sess)
        s.commit()
        s.refresh(sess)
        sid = int(sess.id)
        # tool row first
        tool = LensMessage(
            session_id=sid,
            role="tool",
            content="ran query",
            tool_name="query",
            tool_args={"sql": "SELECT 42"},
            tool_result={
                "columns": [{"name": "answer"}],
                "rows": [[42]],
                "row_count": 1,
                "executed_sql": "SELECT 42 LIMIT 1000",
            },
            tool_status="ok",
            cost_estimate=1.0,
            created_at=now,
        )
        s.add(tool)
        s.commit()
        # assistant row after
        assistant = LensMessage(
            session_id=sid,
            role="assistant",
            content="The answer is 42.",
            tokens_in=10,
            tokens_out=5,
            cost_estimate=0.001,
            created_at=now + datetime.timedelta(seconds=1),
        )
        s.add(assistant)
        s.commit()
        s.refresh(assistant)
        return (sid, int(assistant.id))


@pytest.mark.asyncio
async def test_create_pin_returns_201(admin_client: httpx.AsyncClient) -> None:
    """Pin creation returns the new row + a stable slug."""
    _wipe_pin_state()
    _, msg_id = _seed_session_with_assistant()
    resp = await admin_client.post(
        "/api/lens/pinned",
        json={
            "title": "Top revenue regions",
            "source_message_id": msg_id,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Top revenue regions"
    assert body["slug"].startswith("top-revenue")


@pytest.mark.asyncio
async def test_pin_slug_collision_appends_suffix(
    admin_client: httpx.AsyncClient,
) -> None:
    """Two pins with the same title → second gets ``-2`` slug."""
    _wipe_pin_state()
    _, msg_id = _seed_session_with_assistant()
    first = await admin_client.post(
        "/api/lens/pinned",
        json={"title": "Same Title", "source_message_id": msg_id},
    )
    second = await admin_client.post(
        "/api/lens/pinned",
        json={"title": "Same Title", "source_message_id": msg_id},
    )
    s1 = first.json()["slug"]
    s2 = second.json()["slug"]
    assert s1 != s2
    assert s2.endswith("-2")


@pytest.mark.asyncio
async def test_get_pin_returns_snapshot_and_preview(
    admin_client: httpx.AsyncClient,
) -> None:
    """Pin detail carries the snapshot + executed_sql + result_preview."""
    _wipe_pin_state()
    _, msg_id = _seed_session_with_assistant()
    create = await admin_client.post(
        "/api/lens/pinned",
        json={"title": "ans-42", "source_message_id": msg_id},
    )
    slug = create.json()["slug"]
    resp = await admin_client.get(f"/api/lens/pinned/{slug}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["content_snapshot"] == "The answer is 42."
    assert "SELECT 42" in (body["sql_text"] or "")
    assert body["result_preview"]["row_count"] == 1


@pytest.mark.asyncio
async def test_list_pins_returns_visible_rows(
    admin_client: httpx.AsyncClient,
) -> None:
    """Listing returns pins for the current workspace."""
    _wipe_pin_state()
    _, msg_id = _seed_session_with_assistant()
    await admin_client.post(
        "/api/lens/pinned",
        json={"title": "p1", "source_message_id": msg_id},
    )
    await admin_client.post(
        "/api/lens/pinned",
        json={"title": "p2", "source_message_id": msg_id},
    )
    resp = await admin_client.get("/api/lens/pinned")
    assert resp.status_code == 200
    titles = {p["title"] for p in resp.json()["pins"]}
    assert {"p1", "p2"} <= titles


@pytest.mark.asyncio
async def test_delete_pin_returns_204(admin_client: httpx.AsyncClient) -> None:
    """Delete removes the pin from listings."""
    _wipe_pin_state()
    _, msg_id = _seed_session_with_assistant()
    create = await admin_client.post(
        "/api/lens/pinned",
        json={"title": "to-delete", "source_message_id": msg_id},
    )
    slug = create.json()["slug"]
    resp = await admin_client.delete(f"/api/lens/pinned/{slug}")
    assert resp.status_code == 204
    listed = await admin_client.get("/api/lens/pinned")
    assert all(p["slug"] != slug for p in listed.json()["pins"])


@pytest.mark.asyncio
async def test_get_pin_404_for_unknown_slug(
    admin_client: httpx.AsyncClient,
) -> None:
    """Unknown slug → 404 envelope."""
    _wipe_pin_state()
    resp = await admin_client.get("/api/lens/pinned/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pin_view_html_renders(admin_client: httpx.AsyncClient) -> None:
    """The HTML view renders the snapshot + Back link."""
    _wipe_pin_state()
    _, msg_id = _seed_session_with_assistant()
    create = await admin_client.post(
        "/api/lens/pinned",
        json={"title": "html-render", "source_message_id": msg_id},
    )
    slug = create.json()["slug"]
    resp = await admin_client.get(f"/api/lens/pinned/{slug}/view")
    assert resp.status_code == 200
    assert "html-render" in resp.text
    assert "Back to Lens" in resp.text


@pytest.mark.asyncio
async def test_pin_assistant_message_required(
    admin_client: httpx.AsyncClient,
) -> None:
    """Pin source_message_id pointing at a non-assistant row → 404."""
    _wipe_pin_state()
    sid, _ = _seed_session_with_assistant()
    factory = app.state.session_factory
    # Find the tool-row id; pinning it should fail with 404.
    with factory() as s:
        tool_row = (
            s.query(LensMessage)
            .filter(
                LensMessage.session_id == sid,
                LensMessage.role == "tool",
            )
            .first()
        )
        assert tool_row is not None
        tool_id = int(tool_row.id)
    resp = await admin_client.post(
        "/api/lens/pinned",
        json={"title": "wrong-source", "source_message_id": tool_id},
    )
    assert resp.status_code == 404
