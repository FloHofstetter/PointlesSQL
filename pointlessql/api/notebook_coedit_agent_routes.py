"""agent presence on the co-edit channel.

Lets an agent (hermes-plugin-pointlessql, future first-party
copilots, etc.) advertise that it is currently operating on a
specific cell of a specific notebook.  Every connected browser
tab then sees the agent as a pseudo-peer in the Phase-105.4
avatar rail — same UI surface as a human collaborator, with a
robot icon swap-in.

The endpoint is intentionally REST + JSON: agents are backend
processes without a long-lived WebSocket, so a full-duplex
session would be wasteful.  The server-side broadcast helper
(``apply_save_remap``'s sibling, ``_broadcast_to_all`` ) handles the fanout to every subscriber.

Wire format extension: a new tag byte ``0x05 TAG_AGENT_PRESENCE``
carries a UTF-8 JSON payload with the shape::

    {
      "agent_run_id": <str>,
      "name": <str>,           # display label, e.g. "hermes"
      "cell_uuid": <str|null>, # currently-edited cell, null = clear
      "action": <str>          # "editing" | "thinking" | "clear"
    }

Clients decode this in ``coedit_client.js`` and merge the result
into the peer rail; no y-protocols encoding involved on either
side, which keeps the agent path independent of the awareness
schema for future reshaping.
"""

from __future__ import annotations

import json
import logging
from typing import Final, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from pointlessql.api import notebook_coedit_ws
from pointlessql.api.dependencies import require_user
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models import Notebook

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])

TAG_AGENT_PRESENCE: Final[int] = 0x05


class AgentPresenceRequest(BaseModel):
    """Payload for ``POST /api/notebooks/{nb}/coedit/agent-presence``."""

    agent_run_id: str = Field(..., min_length=1, max_length=128)
    name: str = Field("agent", min_length=1, max_length=64)
    cell_uuid: str | None = Field(default=None, max_length=64)
    action: Literal["editing", "thinking", "clear"] = "editing"


@router.post("/api/notebooks/{notebook_id}/coedit/agent-presence")
async def api_agent_presence(
    request: Request,
    notebook_id: str,
    body: AgentPresenceRequest,
) -> dict[str, str]:
    """Broadcast an agent-presence update to every connected client.

    Args:
        request: Incoming request; must carry a cookie or Bearer
            auth (no anonymous traffic) so the broadcast can be
            attributed back to a workspace member.
        notebook_id: 36-char :class:`Notebook` UUID the agent is
            operating on.
        body: Validated :class:`AgentPresenceRequest`.

    Returns:
        ``{"status": "broadcast"}`` when the hub broadcast the
        frame; ``{"status": "no-hub"}`` when no clients are
        currently connected.  Both are 200 — agent-presence is
        best-effort and the API contract treats the no-hub case
        as success rather than 404 (the canonical state is the
        agent_run_id itself, not the broadcast).

    Raises:
        ResourceNotFoundError: When the notebook id does not
            resolve to a stored notebook (rendered as 404).
    """
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        notebook = session.get(Notebook, notebook_id)
        if notebook is None:
            raise ResourceNotFoundError("notebook not found.")

    payload = {
        "agent_run_id": body.agent_run_id,
        "name": body.name,
        "cell_uuid": body.cell_uuid,
        "action": body.action,
    }
    encoded = bytes([TAG_AGENT_PRESENCE]) + json.dumps(payload).encode("utf-8")
    delivered = await notebook_coedit_ws.broadcast_agent_presence(notebook_id, encoded)
    if not delivered:
        return {"status": "no-hub"}
    return {"status": "broadcast"}


__all__ = ["TAG_AGENT_PRESENCE", "router"]
