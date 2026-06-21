"""Tests for contextual agent guardrails.

The service-level tests each run in a freshly-created workspace so the
session-scoped test DB (no per-test rollback) cannot leak policy modules
between cases; the route tests hit the admin endpoint in the default
workspace and assert shape + auth rather than a specific verdict.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

import httpx
import pytest

from pointlessql.api.main import app as fastapi_app
from pointlessql.models import Workspace
from pointlessql.services.policy_as_code import (
    create_module,
    evaluate_agent_action,
    invalidate_cache,
)

_PERMIT_AGENT_ACTION = 'permit(principal, action == Action::"agent_action", resource);'
_PERMIT_WITH_APPROVAL = (
    'permit(principal, action == Action::"agent_action_with_approval", resource);'
)
_FORBID_ON_UNSAFE = (
    'forbid(principal, action == Action::"agent_action", resource) '
    "when { context.unsafe_content == true };"
)
_FORBID_ON_GROK = (
    'forbid(principal, action == Action::"agent_action", resource) '
    'when { context.model == "grok" };'
)


def _fresh_workspace() -> int:
    """Create an isolated workspace and return its id."""
    factory = fastapi_app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        ws = Workspace(
            slug=f"guardrail-{uuid.uuid4().hex[:10]}",
            name="Guardrail test workspace",
            created_at=now,
        )
        session.add(ws)
        session.commit()
        session.refresh(ws)
        return int(ws.id)


def _add_module(workspace_id: int, name: str, cedar_source: str) -> None:
    """Create one enabled policy module in *workspace_id*."""
    create_module(
        fastapi_app.state.session_factory,
        workspace_id=workspace_id,
        name=name,
        cedar_source=cedar_source,
        created_by_user_id=None,
    )


def _evaluate(
    workspace_id: int,
    *,
    principal_id: int | None = None,
    model: str | None = None,
    mcp_service: str | None = None,
    tool: str | None = None,
    content_flags: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Invalidate the parse cache and evaluate an agent action."""
    invalidate_cache()
    return evaluate_agent_action(
        fastapi_app.state.session_factory,
        workspace_id=workspace_id,
        principal_id=principal_id,
        model=model,
        mcp_service=mcp_service,
        tool=tool,
        content_flags=content_flags,
    )


def test_empty_workspace_allows() -> None:
    ws = _fresh_workspace()
    result = _evaluate(ws, principal_id=1, model="grok")
    assert result["verdict"] == "allow"
    assert result["empty"] is True


def test_permit_module_allows() -> None:
    ws = _fresh_workspace()
    _add_module(ws, "permit-agent", _PERMIT_AGENT_ACTION)
    result = _evaluate(ws, principal_id=1, model="claude")
    assert result["verdict"] == "allow"
    assert result["empty"] is False


def test_hard_forbid_denies() -> None:
    ws = _fresh_workspace()
    _add_module(ws, "base-permit", _PERMIT_AGENT_ACTION)
    _add_module(ws, "block-unsafe", _FORBID_ON_UNSAFE)

    blocked = _evaluate(ws, principal_id=1, content_flags={"unsafe_content": True})
    assert blocked["verdict"] == "deny"

    clean = _evaluate(ws, principal_id=1, content_flags={"unsafe_content": False})
    assert clean["verdict"] == "allow"


def test_forbid_with_approval_path_requires_approval() -> None:
    ws = _fresh_workspace()
    _add_module(ws, "base-permit", _PERMIT_AGENT_ACTION)
    _add_module(ws, "review-grok", _FORBID_ON_GROK)
    _add_module(ws, "approval-permit", _PERMIT_WITH_APPROVAL)

    review = _evaluate(ws, principal_id=1, model="grok")
    assert review["verdict"] == "require_approval"

    allowed = _evaluate(ws, principal_id=1, model="claude")
    assert allowed["verdict"] == "allow"


@pytest.mark.asyncio
async def test_route_evaluate_shape(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.post(
        "/api/admin/agent-guardrails/evaluate",
        json={
            "principal_id": "1",
            "model": "grok",
            "mcp_service": "database",
            "tool": "pql_query",
            "content_flags": {"pii": True, "unsafe_content": False},
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["verdict"] in {"allow", "require_approval", "deny"}
    assert payload["context"]["model"] == "grok"
    assert payload["context"]["pii"] is True
    assert payload["context"]["unsafe_content"] is False


@pytest.mark.asyncio
async def test_route_page_renders(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get("/admin/agent-guardrails")
    assert response.status_code == 200, response.text
    assert "Agent guardrails" in response.text


@pytest.mark.asyncio
async def test_route_requires_admin(non_admin_client: httpx.AsyncClient) -> None:
    response = await non_admin_client.post(
        "/api/admin/agent-guardrails/evaluate",
        json={"model": "grok"},
    )
    assert response.status_code in {401, 403}
