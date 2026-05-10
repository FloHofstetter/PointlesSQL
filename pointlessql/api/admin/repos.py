"""Admin JSON API for workspace-repo management (Phase 51.5).

Endpoints (all gated by :func:`require_admin`):

* ``GET /api/admin/repos`` — list every repo registered to the
  active workspace.
* ``POST /api/admin/repos`` — create a new repo + optional first
  secret.  Reveals the freshly-generated webhook secret exactly
  once.
* ``GET /api/admin/repos/{repo_id}`` — detail with secrets
  metadata (kind / created / rotated; never plaintext).
* ``POST /api/admin/repos/{repo_id}/sync`` — manual sync.
* ``POST /api/admin/repos/{repo_id}/secrets`` — add or rotate a
  secret of the given kind.  Plaintext flows in once.
* ``DELETE /api/admin/repos/{repo_id}/secrets/{kind}`` — revoke.
* ``POST /api/admin/repos/{repo_id}/rotate-webhook-secret``.
* ``DELETE /api/admin/repos/{repo_id}`` — cascade-delete the row
  + secrets + clone dir.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import current_workspace_id, get_user, require_admin
from pointlessql.exceptions import ResourceNotFoundError, ValidationError
from pointlessql.models.workspace._repos import (
    WORKSPACE_REPO_PROVIDER_KINDS,
    WORKSPACE_REPO_SECRET_KINDS,
    WorkspaceRepo,
    WorkspaceRepoSecret,
)
from pointlessql.services.workspace.repos import (
    add_secret,
    build_post_pull_loader_hook,
    create_repo,
    delete_repo,
    list_repos_for_workspace,
    rotate_webhook_secret,
    sync_repo,
)

router = APIRouter(tags=["admin-repos"])


def _serialize(repo: WorkspaceRepo) -> dict[str, Any]:
    """Render one repo row as a JSON-friendly dict."""
    return {
        "id": repo.id,
        "workspace_id": repo.workspace_id,
        "slug": repo.slug,
        "url": repo.url,
        "default_branch": repo.default_branch,
        "provider_kind": repo.provider_kind,
        "sync_state": repo.sync_state,
        "last_synced_sha": repo.last_synced_sha,
        "last_synced_at": (
            repo.last_synced_at.isoformat() if repo.last_synced_at else None
        ),
        "last_sync_error": repo.last_sync_error,
        "created_at": repo.created_at.isoformat(),
    }


def _serialize_secret(secret: WorkspaceRepoSecret) -> dict[str, Any]:
    """Render one secret row — never includes plaintext."""
    return {
        "kind": secret.kind,
        "created_at": secret.created_at.isoformat(),
        "rotated_at": secret.rotated_at.isoformat() if secret.rotated_at else None,
    }


def _load_repo(request: Request, repo_id: int) -> WorkspaceRepo:
    """Fetch *repo_id* enforced to live in the active workspace."""
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(WorkspaceRepo, repo_id)
        if row is None or row.workspace_id != workspace_id:
            raise ResourceNotFoundError(f"workspace_repo {repo_id} not found")
        session.expunge(row)
    return row


@router.get("/api/admin/repos")
async def list_repos(request: Request) -> dict[str, Any]:
    """List every repo registered to the active workspace.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"workspace_id": int, "repos": [...]}`` ordered by slug.
    """
    require_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    repos = list_repos_for_workspace(factory, workspace_id=workspace_id)
    return {
        "workspace_id": workspace_id,
        "repos": [_serialize(r) for r in repos],
    }


@router.post("/api/admin/repos")
async def create_repo_route(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Register a new repo.  Returns the freshly-generated webhook secret.

    Args:
        request: Incoming FastAPI request.
        body: JSON
            ``{slug, url, default_branch?, provider_kind?,
            initial_secret_kind?, initial_secret_plaintext?}``.

    Returns:
        Detail dict + ``"webhook_secret"`` plaintext.  The secret
        is shown exactly once; subsequent ``GET`` calls do not
        reveal it again.

    Raises:
        ValidationError: Body shape invalid.
    """
    require_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    user = get_user(request)

    slug = body.get("slug")
    url = body.get("url")
    if not isinstance(slug, str) or not slug.strip():
        raise ValidationError("slug must be a non-empty string")
    if not isinstance(url, str) or not url.strip():
        raise ValidationError("url must be a non-empty string")

    default_branch_raw = body.get("default_branch") or "main"
    if not isinstance(default_branch_raw, str) or not default_branch_raw.strip():
        raise ValidationError("default_branch must be a non-empty string when provided")
    provider_kind = body.get("provider_kind") or "generic"
    if provider_kind not in WORKSPACE_REPO_PROVIDER_KINDS:
        raise ValidationError(
            f"provider_kind must be one of {WORKSPACE_REPO_PROVIDER_KINDS}"
        )
    initial_secret_kind = body.get("initial_secret_kind")
    initial_secret_plaintext = body.get("initial_secret_plaintext")
    if initial_secret_kind is not None and not isinstance(initial_secret_kind, str):
        raise ValidationError("initial_secret_kind must be a string when provided")
    if initial_secret_plaintext is not None and not isinstance(initial_secret_plaintext, str):
        raise ValidationError("initial_secret_plaintext must be a string when provided")

    try:
        out = create_repo(
            factory,
            workspace_id=workspace_id,
            slug=slug.strip(),
            url=url.strip(),
            default_branch=default_branch_raw.strip(),
            provider_kind=provider_kind,
            created_by_user_id=user.get("id") or None,
            initial_secret_kind=initial_secret_kind,
            initial_secret_plaintext=initial_secret_plaintext,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    await audit(
        request,
        "workspace_repo.created",
        f"workspace_repo:{slug}",
        {"provider_kind": provider_kind},
    )
    return {
        **_serialize(out.repo),
        "webhook_secret": out.webhook_secret_plaintext,
    }


@router.get("/api/admin/repos/{repo_id}")
async def get_repo(repo_id: int, request: Request) -> dict[str, Any]:
    """Detail for *repo_id*.

    Args:
        repo_id: ``WorkspaceRepo.id``.
        request: Incoming FastAPI request.

    Returns:
        Detail dict including secret metadata (no plaintext).
        ``_load_repo`` raises :class:`ResourceNotFoundError` for
        unknown repos.
    """
    require_admin(request)
    repo = _load_repo(request, repo_id)
    factory = request.app.state.session_factory
    with factory() as session:
        secrets_rows = list(
            session.execute(
                select(WorkspaceRepoSecret).where(
                    WorkspaceRepoSecret.workspace_repo_id == repo.id
                )
            ).scalars()
        )
    return {
        **_serialize(repo),
        "secrets": [_serialize_secret(s) for s in secrets_rows],
    }


@router.post("/api/admin/repos/{repo_id}/sync")
async def sync_repo_route(repo_id: int, request: Request) -> dict[str, Any]:
    """Trigger a manual sync of *repo_id*.

    Args:
        repo_id: ``WorkspaceRepo.id``.
        request: Incoming FastAPI request.

    Returns:
        :class:`SyncOutcome` rendered as a dict — succeeds even when
        the underlying ``git`` operation failed (the failure is
        recorded on the row and surfaced via ``ok=False``).
        ``_load_repo`` raises :class:`ResourceNotFoundError` when
        ``repo_id`` is unknown to the active workspace.
    """
    require_admin(request)
    repo = _load_repo(request, repo_id)
    factory = request.app.state.session_factory
    settings = request.app.state.settings
    user = get_user(request)
    actor_user_id = user.get("id") or None
    hook = build_post_pull_loader_hook(factory, settings=settings)
    outcome = await sync_repo(
        factory,
        repo_id=repo.id,
        base_dir=settings.workspace_repos.base_dir,
        trigger="manual",
        actor_user_id=actor_user_id,
        on_post_pull=hook,
    )
    await audit(
        request,
        "workspace_repo.sync_triggered",
        f"workspace_repo:{repo.slug}",
        {"ok": outcome.ok, "operation": outcome.operation, "head_sha": outcome.head_sha},
    )
    return {
        "ok": outcome.ok,
        "operation": outcome.operation,
        "head_sha": outcome.head_sha,
        "changed": outcome.changed,
        "loaded_data_products": outcome.loaded_data_products,
        "loaded_conventions": outcome.loaded_conventions,
        "error": outcome.error,
    }


@router.post("/api/admin/repos/{repo_id}/secrets")
async def add_secret_route(
    repo_id: int,
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Add or rotate a secret of the given kind.

    Args:
        repo_id: ``WorkspaceRepo.id``.
        request: Incoming FastAPI request.
        body: JSON ``{kind, plaintext}``.

    Returns:
        ``{kind, created_at, rotated_at}``.  Plaintext echoed back
        once for symmetry with :func:`create_repo_route`.
        ``_load_repo`` raises :class:`ResourceNotFoundError` for
        unknown repos.

    Raises:
        ValidationError: Body shape invalid.
    """
    require_admin(request)
    repo = _load_repo(request, repo_id)
    factory = request.app.state.session_factory
    kind = body.get("kind")
    plaintext = body.get("plaintext")
    if not isinstance(kind, str) or kind not in WORKSPACE_REPO_SECRET_KINDS:
        raise ValidationError(
            f"kind must be one of {WORKSPACE_REPO_SECRET_KINDS}"
        )
    if not isinstance(plaintext, str) or not plaintext:
        raise ValidationError("plaintext must be a non-empty string")
    secret = add_secret(factory, repo_id=repo.id, kind=kind, plaintext=plaintext)
    await audit(
        request,
        "workspace_repo.secret_set",
        f"workspace_repo:{repo.slug}",
        {"kind": kind},
    )
    return _serialize_secret(secret)


@router.delete("/api/admin/repos/{repo_id}/secrets/{kind}")
async def delete_secret_route(
    repo_id: int,
    kind: str,
    request: Request,
) -> dict[str, Any]:
    """Revoke the *kind* secret on *repo_id*.

    Args:
        repo_id: ``WorkspaceRepo.id``.
        kind: One of :data:`WORKSPACE_REPO_SECRET_KINDS`.
        request: Incoming FastAPI request.

    Returns:
        ``{"revoked": True}`` on success.

    Raises:
        ResourceNotFoundError: Repo or secret missing.
        ValidationError: Unknown ``kind``.
    """
    require_admin(request)
    repo = _load_repo(request, repo_id)
    if kind not in WORKSPACE_REPO_SECRET_KINDS:
        raise ValidationError(
            f"kind must be one of {WORKSPACE_REPO_SECRET_KINDS}"
        )
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(WorkspaceRepoSecret).where(
                WorkspaceRepoSecret.workspace_repo_id == repo.id,
                WorkspaceRepoSecret.kind == kind,
            )
        ).scalar_one_or_none()
        if row is None:
            raise ResourceNotFoundError(
                f"workspace_repo {repo_id!r} has no {kind!r} secret to revoke"
            )
        session.delete(row)
        session.commit()
    await audit(
        request,
        "workspace_repo.secret_revoked",
        f"workspace_repo:{repo.slug}",
        {"kind": kind},
    )
    return {"revoked": True}


@router.post("/api/admin/repos/{repo_id}/rotate-webhook-secret")
async def rotate_webhook_route(repo_id: int, request: Request) -> dict[str, Any]:
    """Generate a fresh webhook secret and reveal it once.

    Args:
        repo_id: ``WorkspaceRepo.id``.
        request: Incoming FastAPI request.

    Returns:
        ``{"webhook_secret": "<plaintext>"}`` — show once; the
        previous value is destroyed.
    """
    require_admin(request)
    repo = _load_repo(request, repo_id)
    factory = request.app.state.session_factory
    new_secret = rotate_webhook_secret(factory, repo_id=repo.id)
    await audit(
        request,
        "workspace_repo.webhook_rotated",
        f"workspace_repo:{repo.slug}",
        {},
    )
    return {"webhook_secret": new_secret}


@router.delete("/api/admin/repos/{repo_id}")
async def delete_repo_route(repo_id: int, request: Request) -> dict[str, Any]:
    """Cascade-delete *repo_id* + its secrets + the on-disk clone.

    Args:
        repo_id: ``WorkspaceRepo.id``.
        request: Incoming FastAPI request.

    Returns:
        ``{"deleted": True}`` on success.
        ``_load_repo`` raises :class:`ResourceNotFoundError` for
        unknown repos; the post-cascade race surfaces as a 404
        ``HTTPException``.

    Raises:
        HTTPException: A concurrent delete vanished the row
            between :func:`_load_repo` and the cascade.
    """
    require_admin(request)
    repo = _load_repo(request, repo_id)
    factory = request.app.state.session_factory
    settings = request.app.state.settings
    deleted = delete_repo(
        factory, repo_id=repo.id, base_dir=settings.workspace_repos.base_dir
    )
    if not deleted:
        # bare-http-ok: race or concurrent delete.
        raise HTTPException(status_code=404, detail=f"workspace_repo {repo_id} disappeared")
    await audit(
        request,
        "workspace_repo.deleted",
        f"workspace_repo:{repo.slug}",
        {},
    )
    return {"deleted": True}


__all__ = ["router"]
