"""Inbound webhook receiver for git-host push events.

Phase 51.4 — accepts ``POST /webhook/git/{repo_id}`` from
GitHub (today) / GitLab / Gitea (later) when the repo's
``provider_kind`` registers a verifiable signature scheme.  The
endpoint is unauthenticated at the middleware layer (the HMAC
signature *is* the auth) and runs the body-verify + parse +
fire-and-forget sync sequence below.

Flow:

1. Look up :class:`WorkspaceRepo` by ``repo_id``; 404 when
   absent.
2. Resolve the provider (``generic`` rejects all signatures, so
   ``generic`` repos always 401 here).
3. Verify the signature against ``repo.webhook_secret``; 401 on
   mismatch.
4. Parse the payload; non-push events get a 202 with
   ``status='ignored'`` (no sync triggered).
5. For pushes that target the repo's ``default_branch``, schedule
   :func:`sync_repo` as an async task and return 202 immediately.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.git import resolve_provider
from pointlessql.models.workspace._repos import WorkspaceRepo
from pointlessql.services.workspace.repos import (
    build_post_pull_loader_hook,
    sync_repo,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workspace-repos-webhook"])


@router.post("/webhook/git/{repo_id}", status_code=202)
async def receive_repo_webhook(
    repo_id: int,
    request: Request,
) -> dict[str, Any]:
    """Receive an inbound git-host webhook for *repo_id*.

    Args:
        repo_id: ``WorkspaceRepo.id`` from the URL.
        request: Incoming FastAPI request.  Body and headers are
            consumed for signature verification.

    Returns:
        Always a 202 envelope describing what happened
        (``verified`` / ``parsed_kind`` / ``branch`` / ``status``).
        Sync work runs in the background; the caller never blocks.

    Raises:
        HTTPException: 404 when the repo is unknown, 401 when the
            signature did not verify or the provider does not
            implement a signature scheme.
    """
    factory = request.app.state.session_factory
    settings = request.app.state.settings

    with factory() as session:
        repo = session.get(WorkspaceRepo, repo_id)
        if repo is None:
            raise ResourceNotFoundError.not_found(
                what=f"workspace_repo id={repo_id}"
            )
        provider_kind = repo.provider_kind
        webhook_secret = repo.webhook_secret
        default_branch = repo.default_branch
        slug = repo.slug

    body = await request.body()
    provider = resolve_provider(provider_kind)
    verification = provider.verify_webhook_signature(
        body, dict(request.headers), webhook_secret
    )
    if not verification.verified:
        # bare-http-ok: signature failures are 401-by-protocol; the
        # WorkspaceRepoWebhookInvalid domain class would be redundant
        # for a path that is unauthenticated by design.
        raise HTTPException(status_code=401, detail=verification.reason)

    event = provider.parse_webhook(body, dict(request.headers))
    if event is None:
        return {
            "verified": True,
            "status": "ignored",
            "reason": "opaque payload",
            "repo_id": repo_id,
            "slug": slug,
        }
    if event.kind != "push" or event.branch != default_branch:
        return {
            "verified": True,
            "status": "ignored",
            "reason": f"event {event.kind!r} on branch {event.branch!r} not actionable",
            "repo_id": repo_id,
            "slug": slug,
        }

    base_dir = settings.workspace_repos.base_dir
    hook = build_post_pull_loader_hook(factory, settings=settings)

    async def _runner() -> None:
        try:
            await sync_repo(
                factory,
                repo_id=repo_id,
                base_dir=base_dir,
                trigger="webhook",
                actor_user_id=None,
                on_post_pull=hook,
            )
        except Exception:  # noqa: BLE001
            # bare-broad-ok: fire-and-forget — sync failures persist
            # to ``WorkspaceRepo.last_sync_error`` already, and the
            # webhook caller cannot do anything with the diagnostic.
            logger.exception("webhook-triggered sync of repo %s failed", repo_id)

    # Schedule but do not await — the webhook caller gets 202 immediately.
    asyncio.create_task(_runner())
    return {
        "verified": True,
        "status": "scheduled",
        "kind": event.kind,
        "branch": event.branch,
        "head_sha": event.head_sha,
        "repo_id": repo_id,
        "slug": slug,
    }


# Avoid mypy/pyright unused-import flagging.
_ = Response
