"""The /api/bundles surface: admin gate, plan / apply / export happy paths.

The bundles router ships unregistered (the navigation integration
wires it into the bootstrap block later), so this module mounts it
onto the app for its own duration and removes the routes on teardown
— the fixture no-ops once the router is registered for real.
"""

from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api import bundles_routes
from pointlessql.api.main import app
from pointlessql.models import Job


@pytest.fixture(autouse=True, scope="module")
def _mount_bundles_router():
    mounted = {getattr(route, "path", None) for route in app.router.routes}
    if "/admin/bundles" in mounted:
        yield
        return
    before = len(app.router.routes)
    app.include_router(bundles_routes.router)
    added = list(app.router.routes[before:])
    yield
    for route in added:
        app.router.routes.remove(route)


_BUNDLE_YAML = (
    "bundle: {name: routed-stack}\n"
    "jobs:\n"
    "  - name: routed-job\n"
    "    kind: python\n"
    "    cron: '0 4 * * *'\n"
    "    config: {script: routed.py}\n"
)


@pytest.mark.asyncio
async def test_admin_page_renders_for_admin(admin_client: httpx.AsyncClient) -> None:
    res = await admin_client.get("/admin/bundles")
    assert res.status_code == 200
    body = res.text
    assert 'data-pql-entry="admin_bundles.js' in body
    assert "adminBundles(" in body
    assert "Asset bundles" in body


@pytest.mark.asyncio
async def test_admin_page_403_for_non_admin(non_admin_client: httpx.AsyncClient) -> None:
    res = await non_admin_client.get("/admin/bundles")
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_plan_403_for_non_admin(non_admin_client: httpx.AsyncClient) -> None:
    res = await non_admin_client.post("/api/bundles/plan", json={"bundle_yaml": _BUNDLE_YAML})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_apply_403_for_non_admin(non_admin_client: httpx.AsyncClient) -> None:
    res = await non_admin_client.post("/api/bundles/apply", json={"bundle_yaml": _BUNDLE_YAML})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_export_403_for_non_admin(non_admin_client: httpx.AsyncClient) -> None:
    res = await non_admin_client.post("/api/bundles/export", json={})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_plan_happy_path(admin_client: httpx.AsyncClient) -> None:
    res = await admin_client.post("/api/bundles/plan", json={"bundle_yaml": _BUNDLE_YAML})
    assert res.status_code == 200, res.text
    plan = res.json()["plan"]
    assert plan["entries"] == [
        {"resource_type": "job", "identity": "routed-job", "action": "create", "changes": []}
    ]
    assert plan["is_noop"] is False


@pytest.mark.asyncio
async def test_plan_rejects_invalid_yaml(admin_client: httpx.AsyncClient) -> None:
    res = await admin_client.post("/api/bundles/plan", json={"bundle_yaml": "- not\n- a\n- bundle"})
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_apply_dry_run_then_real_then_unchanged(admin_client: httpx.AsyncClient) -> None:
    dry = await admin_client.post(
        "/api/bundles/apply?dry_run=true", json={"bundle_yaml": _BUNDLE_YAML}
    )
    assert dry.status_code == 200, dry.text
    assert dry.json()["outcome"]["dry_run"] is True
    with app.state.session_factory() as session:
        assert session.scalar(select(Job).where(Job.name == "routed-job")) is None

    real = await admin_client.post("/api/bundles/apply", json={"bundle_yaml": _BUNDLE_YAML})
    assert real.status_code == 200, real.text
    outcome = real.json()["outcome"]
    assert outcome["dry_run"] is False
    assert outcome["error_count"] == 0
    assert outcome["results"][0]["action"] == "created"
    with app.state.session_factory() as session:
        job = session.scalar(select(Job).where(Job.name == "routed-job"))
        assert job is not None
        assert json.loads(job.config) == {"script": "routed.py"}

    again = await admin_client.post("/api/bundles/apply", json={"bundle_yaml": _BUNDLE_YAML})
    assert again.status_code == 200
    assert again.json()["outcome"]["results"][0]["action"] == "unchanged"


@pytest.mark.asyncio
async def test_export_happy_path(admin_client: httpx.AsyncClient) -> None:
    applied = await admin_client.post("/api/bundles/apply", json={"bundle_yaml": _BUNDLE_YAML})
    assert applied.status_code == 200

    everything = await admin_client.post("/api/bundles/export", json={})
    assert everything.status_code == 200, everything.text
    assert "routed-job" in everything.json()["yaml"]

    nothing = await admin_client.post(
        "/api/bundles/export", json={"jobs": [], "pipelines": [], "dashboards": []}
    )
    assert nothing.status_code == 200
    assert "routed-job" not in nothing.json()["yaml"]


@pytest.mark.asyncio
async def test_export_rejects_bad_selector(admin_client: httpx.AsyncClient) -> None:
    res = await admin_client.post("/api/bundles/export", json={"jobs": "not-a-list"})
    assert res.status_code == 400
