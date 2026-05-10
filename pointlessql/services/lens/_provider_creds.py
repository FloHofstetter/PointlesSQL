"""Lens BYO LLM provider credential storage.

Wraps the :class:`LensProviderCreds` table with Fernet
encryption-at-rest using the install-scoped master key from
:mod:`pointlessql.services.secrets` (analog Phase 51 workspace-repo
secrets).  Cleartext API keys never enter the DB; the chat-loop
decrypts on demand for each LLM round-trip and discards.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from pointlessql.models import LENS_PROVIDERS, LensProviderCreds
from pointlessql.services.secrets import decrypt_value, encrypt_value

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


class UnknownLensProviderError(ValueError):
    """Raised when a provider string is not in :data:`LENS_PROVIDERS`."""


def _validate_provider(provider: str) -> None:
    """Raise :class:`UnknownLensProviderError` if *provider* is not recognised."""
    if provider not in LENS_PROVIDERS:
        raise UnknownLensProviderError(
            f"Lens provider {provider!r} is not recognised; "
            f"valid providers: {sorted(LENS_PROVIDERS)}"
        )


def upsert_provider_creds(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    provider: str,
    api_key: str,
    default_model: str | None = None,
    enabled: bool = True,
) -> LensProviderCreds:
    """Insert or rotate the workspace's credential for *provider*.

    The cleartext *api_key* is Fernet-encrypted before persistence;
    the row is detached + returned without the cleartext (callers
    should not echo it back).

    Args:
        factory: SQLAlchemy sessionmaker.
        workspace_id: Workspace owning the credential.
        provider: One of :data:`LENS_PROVIDERS`.
        api_key: Cleartext API key from the user.
        default_model: Optional override for the chat-loop default
            model.  ``None`` defers to install-wide settings.
        enabled: When ``False`` the chat-loop refuses this credential
            without revealing cleartext to revoke + re-add.

    Returns:
        The detached :class:`LensProviderCreds` row (no cleartext).

    Raises:
        UnknownLensProviderError: When *provider* is not in
            :data:`LENS_PROVIDERS`.
        ValueError: When *api_key* is empty or whitespace-only.
    """  # noqa: DOC502,DOC503 — UnknownLensProviderError via _validate_provider
    _validate_provider(provider)
    if not api_key or not api_key.strip():
        raise ValueError("Lens provider api_key must be a non-empty string")
    encrypted = encrypt_value(api_key.strip(), session_factory=factory)
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        existing = session.scalar(
            select(LensProviderCreds).where(
                LensProviderCreds.workspace_id == workspace_id,
                LensProviderCreds.provider == provider,
            )
        )
        if existing is not None:
            existing.api_key_encrypted = encrypted
            existing.default_model = default_model
            existing.enabled = enabled
            existing.updated_at = now
            row = existing
        else:
            row = LensProviderCreds(
                workspace_id=workspace_id,
                provider=provider,
                api_key_encrypted=encrypted,
                default_model=default_model,
                enabled=enabled,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def get_provider_creds(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    provider: str,
) -> LensProviderCreds | None:
    """Return the stored credential row for ``(workspace, provider)``.

    Args:
        factory: SQLAlchemy sessionmaker.
        workspace_id: Workspace filter.
        provider: One of :data:`LENS_PROVIDERS`.

    Returns:
        Detached :class:`LensProviderCreds` row or ``None`` when no
        credential is stored.

    Raises:
        UnknownLensProviderError: When *provider* is not in
            :data:`LENS_PROVIDERS`.
    """  # noqa: DOC502 — UnknownLensProviderError raised by _validate_provider
    _validate_provider(provider)
    with factory() as session:
        row = session.scalar(
            select(LensProviderCreds).where(
                LensProviderCreds.workspace_id == workspace_id,
                LensProviderCreds.provider == provider,
            )
        )
        if row is None:
            return None
        session.expunge(row)
        return row


def list_provider_creds(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
) -> list[LensProviderCreds]:
    """Return every credential row stored for *workspace_id*.

    Args:
        factory: SQLAlchemy sessionmaker.
        workspace_id: Workspace filter.

    Returns:
        Detached rows ordered by provider name.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(LensProviderCreds)
                .where(LensProviderCreds.workspace_id == workspace_id)
                .order_by(LensProviderCreds.provider.asc())
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows


def delete_provider_creds(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    provider: str,
) -> bool:
    """Drop the credential row for ``(workspace, provider)``.

    Args:
        factory: SQLAlchemy sessionmaker.
        workspace_id: Workspace filter.
        provider: One of :data:`LENS_PROVIDERS`.

    Returns:
        ``True`` when a row was deleted.

    Raises:
        UnknownLensProviderError: When *provider* is not in
            :data:`LENS_PROVIDERS`.
    """  # noqa: DOC502 — UnknownLensProviderError raised by _validate_provider
    _validate_provider(provider)
    with factory() as session:
        result = session.execute(
            delete(LensProviderCreds).where(
                LensProviderCreds.workspace_id == workspace_id,
                LensProviderCreds.provider == provider,
            )
        )
        session.commit()
        return int(getattr(result, "rowcount", 0) or 0) > 0


def decrypt_provider_key(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    provider: str,
) -> str | None:
    """Return the cleartext API key for ``(workspace, provider)``.

    Returns ``None`` when no credential is stored or when the row is
    disabled.  Callers should hold the cleartext only for the
    duration of one LLM round-trip and discard.

    Args:
        factory: SQLAlchemy sessionmaker.
        workspace_id: Workspace filter.
        provider: One of :data:`LENS_PROVIDERS`.

    Returns:
        Cleartext API key, or ``None`` when missing / disabled.

    Raises:
        UnknownLensProviderError: When *provider* is not in
            :data:`LENS_PROVIDERS`.
        SecretDecryptError: When the ciphertext fails authentication
            (master key rotated without re-encrypting dependents).
    """  # noqa: DOC502 — both errors bubble from helpers
    row = get_provider_creds(factory, workspace_id=workspace_id, provider=provider)
    if row is None or not row.enabled:
        return None
    return decrypt_value(row.api_key_encrypted, session_factory=factory)
