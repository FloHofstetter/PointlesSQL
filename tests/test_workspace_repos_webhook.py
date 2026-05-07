"""Phase 51.4 — inbound git webhook receiver.

Exercises the full path: signature verification (valid /
mutated / missing), provider-mismatch (generic refuses every
signature), event-kind / branch filtering, fire-and-forget sync
scheduling.  No real upstreams — payloads are constructed in
memory and signed with the repo's stored ``webhook_secret``.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.services.workspace_repos import create_repo


def _signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _push_body(branch: str = "main", sha: str = "deadbeef" + "0" * 32) -> bytes:
    return json.dumps({"ref": f"refs/heads/{branch}", "after": sha}).encode()


@pytest.mark.asyncio
async def test_webhook_404_unknown_repo() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/webhook/git/99999", content=b"{}")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_webhook_401_when_signature_missing() -> None:
    factory = app.state.session_factory
    out = create_repo(
        factory,
        workspace_id=1,
        slug="webhooked",
        url="file:///tmp/no-such-repo",
        provider_kind="github",
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/webhook/git/{out.repo.id}",
            content=_push_body(),
            headers={"X-GitHub-Event": "push"},
        )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_webhook_401_when_signature_mismatch() -> None:
    factory = app.state.session_factory
    out = create_repo(
        factory,
        workspace_id=1,
        slug="bad-sig",
        url="file:///tmp/no-such-repo",
        provider_kind="github",
    )
    body = _push_body()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/webhook/git/{out.repo.id}",
            content=body,
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": _signature("WRONG-SECRET", body),
            },
        )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_webhook_202_when_signature_ok_but_non_push_event() -> None:
    factory = app.state.session_factory
    out = create_repo(
        factory,
        workspace_id=1,
        slug="ping-only",
        url="file:///tmp/no-such-repo",
        provider_kind="github",
    )
    body = b'{"hook_id": 12345}'
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/webhook/git/{out.repo.id}",
            content=body,
            headers={
                "X-GitHub-Event": "ping",
                "X-Hub-Signature-256": _signature(out.webhook_secret_plaintext, body),
            },
        )
    assert res.status_code == 202
    payload = res.json()
    assert payload["status"] == "ignored"


@pytest.mark.asyncio
async def test_webhook_202_when_branch_mismatch() -> None:
    factory = app.state.session_factory
    out = create_repo(
        factory,
        workspace_id=1,
        slug="branch-mismatch",
        url="file:///tmp/no-such-repo",
        provider_kind="github",
        default_branch="main",
    )
    body = _push_body(branch="dev")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/webhook/git/{out.repo.id}",
            content=body,
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": _signature(out.webhook_secret_plaintext, body),
            },
        )
    assert res.status_code == 202
    payload = res.json()
    assert payload["status"] == "ignored"
    assert "dev" in payload["reason"]


@pytest.mark.asyncio
async def test_webhook_202_schedules_sync_on_valid_push() -> None:
    factory = app.state.session_factory
    out = create_repo(
        factory,
        workspace_id=1,
        slug="will-schedule",
        url="file:///tmp/no-such-repo",
        provider_kind="github",
        default_branch="main",
    )
    body = _push_body(branch="main")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/webhook/git/{out.repo.id}",
            content=body,
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": _signature(out.webhook_secret_plaintext, body),
            },
        )
    assert res.status_code == 202
    payload = res.json()
    assert payload["status"] == "scheduled"
    assert payload["branch"] == "main"
    assert payload["repo_id"] == out.repo.id
    # Give the fire-and-forget task a chance to run before the test finishes;
    # we don't assert on the sync outcome (the URL is bogus on purpose) but
    # giving it time prevents a "task was never awaited" warning.
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_webhook_generic_provider_always_401() -> None:
    factory = app.state.session_factory
    out = create_repo(
        factory,
        workspace_id=1,
        slug="generic-no-webhook",
        url="file:///tmp/no-such-repo",
        provider_kind="generic",
    )
    body = _push_body()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/webhook/git/{out.repo.id}",
            content=body,
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": _signature(out.webhook_secret_plaintext, body),
            },
        )
    assert res.status_code == 401
