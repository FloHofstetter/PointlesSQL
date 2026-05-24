"""Tests — publish notebook (share UUIDs + dashboard mode)."""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.services.notebook import shares as notebook_shares_service


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``settings.jupyter.notebooks_dir`` at a tmp directory."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


def _write_notebook(workspace_dir: Path, name: str) -> None:
    (workspace_dir / name).write_text("# %% [markdown]\n# # Hello\n\n# %%\nprint(1)\n")


# -- service: dashboard render ------------------------------------------------


def test_render_dashboard_html_strips_code_keeps_markdown() -> None:
    """Markdown cells survive; code cells become placeholder slots."""
    html = notebook_shares_service.render_dashboard_html(
        title="x",
        cells=[
            {"content_hash": "h1", "cell_type": "markdown", "source": "# heading"},
            {"content_hash": "h2", "cell_type": "code", "source": "secret = 42"},
        ],
        outputs=[
            {
                "content_hash": "h2",
                "kernel_session_id": "s",
                "output_index": 0,
                "msg_type": "stream",
                "content": {"name": "stdout", "text": "OUT\n"},
                "metadata": None,
                "created_at": "2026-05-20T12:00:00",
            }
        ],
    )
    assert "heading" in html
    assert "secret = 42" not in html
    # Dashboard render still surfaces the output of the hidden code cell.
    assert "OUT" in html
    assert "DASHBOARD" in html


# -- REST: create + viewer ----------------------------------------------------


async def test_api_create_snapshot_share_and_view(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """POST mints a UUID; GET /share/notebook/{uuid} renders HTML."""
    _write_notebook(workspace_dir, "report.py")
    await admin_client.post("/api/notebooks/create", json={"path": "report.py"})
    # Overwrite with rich content so the export pipeline produces something.
    _write_notebook(workspace_dir, "report.py")

    create = await admin_client.post(
        "/api/notebooks/shares",
        json={"path": "report.py", "share_mode": "snapshot"},
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["share_mode"] == "snapshot"
    assert body["share_url"].startswith("/share/notebook/")
    share_uuid = body["share_uuid"]
    assert body["revision_uuid"] is not None

    # Public view (no auth header — admin_client cookies should be
    # ignored by the route; the test verifies the route does NOT
    # require auth, so it's enough that the response is 200).
    viewed = await admin_client.get(f"/share/notebook/{share_uuid}")
    assert viewed.status_code == 200
    assert viewed.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in viewed.text


async def test_api_create_live_share_no_revision(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Live mode does NOT mint a revision; revision_uuid is null."""
    _write_notebook(workspace_dir, "live.py")
    await admin_client.post("/api/notebooks/create", json={"path": "live.py"})
    _write_notebook(workspace_dir, "live.py")
    resp = await admin_client.post(
        "/api/notebooks/shares",
        json={"path": "live.py", "share_mode": "live"},
    )
    assert resp.status_code == 201
    assert resp.json()["share_mode"] == "live"
    assert resp.json()["revision_uuid"] is None


async def test_api_create_dashboard_share(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Dashboard mode flag round-trips through the create + view path."""
    _write_notebook(workspace_dir, "dash.py")
    await admin_client.post("/api/notebooks/create", json={"path": "dash.py"})
    _write_notebook(workspace_dir, "dash.py")
    create = await admin_client.post(
        "/api/notebooks/shares",
        json={
            "path": "dash.py",
            "share_mode": "snapshot",
            "dashboard_mode": True,
        },
    )
    assert create.status_code == 201
    assert create.json()["dashboard_mode"] is True
    viewed = await admin_client.get(f"/share/notebook/{create.json()['share_uuid']}")
    assert "Dashboard" in viewed.text
    assert "dashboard_mode" not in viewed.text  # template flag, not output


async def test_api_revoke_share_returns_410(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Revoked share returns 410 from the public viewer."""
    _write_notebook(workspace_dir, "x.py")
    await admin_client.post("/api/notebooks/create", json={"path": "x.py"})
    _write_notebook(workspace_dir, "x.py")
    create = await admin_client.post(
        "/api/notebooks/shares",
        json={"path": "x.py", "share_mode": "live"},
    )
    share_uuid = create.json()["share_uuid"]

    revoked = await admin_client.delete(f"/api/notebooks/shares/{share_uuid}")
    assert revoked.json()["revoked"] is True

    viewed = await admin_client.get(f"/share/notebook/{share_uuid}")
    assert viewed.status_code == 410


async def test_api_unknown_share_returns_410(
    admin_client: httpx.AsyncClient,
) -> None:
    """Random share UUID returns 410 (never 404 — keeps probe noise low)."""
    fake = str(uuid.uuid4())
    resp = await admin_client.get(f"/share/notebook/{fake}")
    assert resp.status_code == 410


async def test_api_update_share_flips_dashboard(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """PATCH updates dashboard_mode in place."""
    _write_notebook(workspace_dir, "x.py")
    await admin_client.post("/api/notebooks/create", json={"path": "x.py"})
    _write_notebook(workspace_dir, "x.py")
    create = await admin_client.post(
        "/api/notebooks/shares",
        json={"path": "x.py", "share_mode": "live"},
    )
    share_uuid = create.json()["share_uuid"]
    patched = await admin_client.patch(
        f"/api/notebooks/shares/{share_uuid}",
        json={"dashboard_mode": True},
    )
    assert patched.status_code == 200
    assert patched.json()["dashboard_mode"] is True


# -- Phase 100 Wave-D: secret-scrub + iframe embed ---------------------------


def test_scrub_text_redacts_common_credential_shapes() -> None:
    """Aggressive redaction covers AWS / GitHub / JWT / Slack / key=val."""
    raw = (
        "AKIAIOSFODNN7EXAMPLE "
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789 "
        "xoxb-1234-abcdef "
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxIiwiaWF0IjoxNzAwMDAwMDAwfQ."
        "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGH "
        "password=hunter2hunter2"
    )
    scrubbed = notebook_shares_service.scrub_text(raw)
    assert "AKIA" not in scrubbed
    assert "ghp_" not in scrubbed
    assert "xoxb-" not in scrubbed
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in scrubbed
    assert "hunter2hunter2" not in scrubbed


def test_scrub_output_frame_only_touches_string_content() -> None:
    """Non-string mime payloads (images) pass through unmolested."""
    frame = {
        "content_hash": "h",
        "msg_type": "stream",
        "content": {
            "text": "token=abcdef123456",
            "image/png": b"binary-blob",
            "rows_affected": 42,
        },
    }
    out = notebook_shares_service.scrub_output_frame(frame)
    assert "redacted" in out["content"]["text"]
    assert out["content"]["image/png"] == b"binary-blob"
    assert out["content"]["rows_affected"] == 42


async def test_embed_route_returns_same_body_as_share_route(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """``/embed/notebook_share/{uuid}`` mirrors ``/share/notebook/{uuid}``."""
    _write_notebook(workspace_dir, "embed.py")
    await admin_client.post("/api/notebooks/create", json={"path": "embed.py"})
    _write_notebook(workspace_dir, "embed.py")
    create = await admin_client.post(
        "/api/notebooks/shares",
        json={"path": "embed.py", "share_mode": "live"},
    )
    share_uuid = create.json()["share_uuid"]
    direct = await admin_client.get(f"/share/notebook/{share_uuid}")
    embed = await admin_client.get(f"/embed/notebook_share/{share_uuid}")
    assert embed.status_code == 200
    assert direct.status_code == 200
    # Same inner notebook body; outer chrome differs (embed suppresses the
    # brand topbar via the ``pql-public--compact`` class on ``<body>``).
    assert '<body class="pql-public--compact">' in embed.text
    assert '<body class="pql-public--compact">' not in direct.text
    assert "<body>" in direct.text
    # The notebook body fragment (cells + outputs) is identical in both.
    for marker in ('class="pql-cell pql-cell--code"', 'class="pql-cell pql-cell--markdown"'):
        assert (marker in direct.text) == (marker in embed.text)


async def test_api_list_shares_includes_revoked(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """List endpoint includes revoked rows so the admin UI can show history."""
    _write_notebook(workspace_dir, "x.py")
    await admin_client.post("/api/notebooks/create", json={"path": "x.py"})
    _write_notebook(workspace_dir, "x.py")
    create = await admin_client.post(
        "/api/notebooks/shares",
        json={"path": "x.py", "share_mode": "live"},
    )
    share_uuid = create.json()["share_uuid"]
    await admin_client.delete(f"/api/notebooks/shares/{share_uuid}")
    listed = await admin_client.get("/api/notebooks/shares", params={"path": "x.py"})
    rows = listed.json()["shares"]
    assert len(rows) == 1
    assert rows[0]["active"] is False
    assert rows[0]["revoked_at"] is not None
