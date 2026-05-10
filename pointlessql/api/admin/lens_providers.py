"""Admin CRUD for Lens BYO LLM provider credentials (Phase 65.5).

Admin-only routes that store / replace / drop the workspace's
Fernet-encrypted credential per ``(workspace, provider)``.  The
cleartext API key is never echoed back; once written it can only be
overwritten via this same endpoint.

The route layer enforces ``require_admin``.  Test-mode connectivity
checks (``POST /admin/lens-providers/{provider}/test``) deliberately
*do not* call the LLM — provider live-pinging is a follow-up; we
just confirm the cred decrypts cleanly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from pointlessql.api.dependencies import current_workspace_id, require_admin
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models import LENS_PROVIDERS
from pointlessql.services.lens import (
    decrypt_provider_key,
    delete_provider_creds,
    list_provider_creds,
    upsert_provider_creds,
)
from pointlessql.services.lens._provider_creds import UnknownLensProviderError

router = APIRouter()


class ProviderCredsBody(BaseModel):
    """Input for ``POST /api/admin/lens-providers``."""

    provider: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    default_model: str | None = None
    enabled: bool = True


class ProviderCredsRow(BaseModel):
    """API response shape — does NOT carry the cleartext."""

    workspace_id: int
    provider: str
    default_model: str | None
    enabled: bool
    created_at: str
    updated_at: str


class ProviderList(BaseModel):
    """List response."""

    providers: list[ProviderCredsRow]


@router.get(
    "/api/admin/lens-providers",
    response_model=ProviderList,
    dependencies=[Depends(require_admin)],
)
def list_providers_endpoint(request: Request) -> ProviderList:
    """List every credential stored for the active workspace.

    Args:
        request: FastAPI request.

    Returns:
        :class:`ProviderList` with one row per stored credential.
        Cleartext is never exposed.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    rows = list_provider_creds(factory, workspace_id=workspace_id)
    return ProviderList(
        providers=[
            ProviderCredsRow(
                workspace_id=int(r.workspace_id),
                provider=str(r.provider),
                default_model=r.default_model,
                enabled=bool(r.enabled),
                created_at=r.created_at.isoformat() if r.created_at else "",
                updated_at=r.updated_at.isoformat() if r.updated_at else "",
            )
            for r in rows
        ]
    )


@router.post(
    "/api/admin/lens-providers",
    response_model=ProviderCredsRow,
    dependencies=[Depends(require_admin)],
)
def upsert_provider_endpoint(
    request: Request,
    body: ProviderCredsBody,
) -> ProviderCredsRow:
    """Insert or rotate the workspace's credential for *body.provider*.

    Args:
        request: FastAPI request.
        body: Provider + cleartext API key + optional default model.

    Returns:
        The persisted :class:`ProviderCredsRow` (cleartext stripped).

    Raises:
        UnknownLensProviderError: When the provider is not in
            :data:`LENS_PROVIDERS`.
    """  # noqa: DOC502 — UnknownLensProviderError raised by service
    if body.provider not in LENS_PROVIDERS:
        raise UnknownLensProviderError(
            f"Provider {body.provider!r} is not recognised; valid: "
            f"{sorted(LENS_PROVIDERS)}"
        )
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    row = upsert_provider_creds(
        factory,
        workspace_id=workspace_id,
        provider=body.provider,
        api_key=body.api_key,
        default_model=body.default_model,
        enabled=body.enabled,
    )
    return ProviderCredsRow(
        workspace_id=int(row.workspace_id),
        provider=str(row.provider),
        default_model=row.default_model,
        enabled=bool(row.enabled),
        created_at=row.created_at.isoformat() if row.created_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


@router.delete(
    "/api/admin/lens-providers/{provider}",
    status_code=204,
    dependencies=[Depends(require_admin)],
)
def delete_provider_endpoint(
    request: Request,
    provider: str,
) -> None:
    """Drop the workspace's credential for *provider*.

    Args:
        request: FastAPI request.
        provider: One of :data:`LENS_PROVIDERS`.

    Raises:
        ResourceNotFoundError: When no credential exists for the
            provider.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    deleted = delete_provider_creds(
        factory, workspace_id=workspace_id, provider=provider
    )
    if not deleted:
        raise ResourceNotFoundError(f"lens_provider_creds: {provider}")


@router.post(
    "/api/admin/lens-providers/{provider}/test",
    dependencies=[Depends(require_admin)],
)
def test_provider_endpoint(
    request: Request,
    provider: str,
) -> dict[str, object]:
    """Confirm the credential decrypts cleanly (no live API call).

    A real ping to the provider is intentionally deferred — this
    endpoint just verifies that:

    * a credential row exists for the active workspace + provider,
    * the row is ``enabled``,
    * the Fernet-decrypted cleartext is non-empty.

    Args:
        request: FastAPI request.
        provider: One of :data:`LENS_PROVIDERS`.

    Returns:
        ``{"ok": true, "key_prefix": "<first-8-chars>"}`` on
        success; ``{"ok": false, "reason": "..."}`` on missing /
        disabled / unreadable credential.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    try:
        cleartext = decrypt_provider_key(
            factory, workspace_id=workspace_id, provider=provider
        )
    except UnknownLensProviderError as exc:
        return {"ok": False, "reason": str(exc)}
    if not cleartext:
        return {"ok": False, "reason": "no enabled credential stored"}
    return {"ok": True, "key_prefix": cleartext[:8]}
