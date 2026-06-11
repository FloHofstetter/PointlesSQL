"""Delta Sharing consumer — read remote shares over the open protocol.

A minimal protocol client (httpx, sync — it feeds the sync PQL
world) plus provider-profile CRUD.  The protocol is small: bearer
auth, ``GET shares/schemas/tables`` listings, and a ``POST …/query``
that answers NDJSON whose ``file`` lines carry pre-signed parquet
URLs.  ``query_table_as_pandas`` downloads those files and
concatenates them — which covers every file:// -backed soyuz share
and any other protocol-conformant server.

Tokens rest Fernet-encrypted on the provider row and are decrypted
per request; they never leave the service.
"""

from __future__ import annotations

import datetime
import json
import re
from io import BytesIO
from typing import TYPE_CHECKING, Any, cast

import httpx
import pandas as pd
from sqlalchemy import select

from pointlessql.models.sharing_providers import SharingProvider
from pointlessql.services.secrets import decrypt_value, encrypt_value

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")

_TIMEOUT = httpx.Timeout(30.0)

MAX_RESULT_BYTES = 256 * 1024 * 1024
"""Refuse to materialise shared tables beyond this total file size."""


def _utcnow() -> datetime.datetime:
    """Return the current UTC wall-clock."""
    return datetime.datetime.now(datetime.UTC)


# ---------------------------------------------------------------------------
# provider CRUD
# ---------------------------------------------------------------------------


def create_provider(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    name: str,
    endpoint_url: str,
    token: str,
    comment: str | None,
    principal: str | None,
) -> SharingProvider:
    """Register a remote provider profile.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Owning workspace.
        name: Provider alias (validated).
        endpoint_url: Base URL of the remote ``/delta-sharing``
            prefix.
        token: Plaintext bearer token; encrypted before persistence.
        comment: Optional note.
        principal: Registering principal's e-mail.

    Returns:
        The persisted row (detached).

    Raises:
        ValueError: On a malformed name/URL, an empty token, or a
            name already taken in the workspace.
    """
    alias = name.strip()
    if not _NAME_RE.match(alias):
        raise ValueError(f"provider name must be 1-128 chars from [A-Za-z0-9_.-], got {name!r}")
    url = endpoint_url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise ValueError("endpoint_url must be an http(s) URL")
    if not token.strip():
        raise ValueError("bearer token must be non-empty")
    now = _utcnow()
    with factory() as session:
        existing = session.scalar(
            select(SharingProvider).where(
                SharingProvider.workspace_id == workspace_id,
                SharingProvider.name == alias,
            )
        )
        if existing is not None:
            raise ValueError(f"sharing provider {alias!r} already exists")
        row = SharingProvider(
            workspace_id=workspace_id,
            name=alias,
            endpoint_url=url,
            encrypted_token=encrypt_value(token.strip(), session_factory=factory),
            comment=comment,
            created_by=principal,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def list_providers(factory: sessionmaker[Session], *, workspace_id: int) -> list[SharingProvider]:
    """List the workspace's providers ordered by name.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.

    Returns:
        Detached provider rows (tokens stay encrypted).
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(SharingProvider)
                .where(SharingProvider.workspace_id == workspace_id)
                .order_by(SharingProvider.name)
            )
        )
        for row in rows:
            session.expunge(row)
    return rows


def get_provider(
    factory: sessionmaker[Session], *, workspace_id: int, name: str
) -> SharingProvider | None:
    """Return the workspace's provider by alias, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.
        name: Provider alias.

    Returns:
        The detached row, or ``None`` when absent.
    """
    with factory() as session:
        row = session.scalar(
            select(SharingProvider).where(
                SharingProvider.workspace_id == workspace_id,
                SharingProvider.name == name,
            )
        )
        if row is not None:
            session.expunge(row)
    return row


def delete_provider(factory: sessionmaker[Session], *, provider_id: int) -> bool:
    """Delete a provider profile.

    Args:
        factory: SQLAlchemy session factory.
        provider_id: Primary key.

    Returns:
        ``True`` when a row was deleted.
    """
    with factory() as session:
        row = session.get(SharingProvider, provider_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
    return True


# ---------------------------------------------------------------------------
# protocol client
# ---------------------------------------------------------------------------


class SharingProtocolError(RuntimeError):
    """Raised when the remote sharing server answers outside the protocol."""


def _client_for(factory: sessionmaker[Session], provider: SharingProvider) -> httpx.Client:
    """Build a bearer-authenticated client for *provider*."""
    token = decrypt_value(provider.encrypted_token, session_factory=factory)
    return httpx.Client(
        base_url=provider.endpoint_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=_TIMEOUT,
    )


def _get_json(client: httpx.Client, path: str) -> dict[str, Any]:
    """GET *path* and return the parsed JSON object.

    Args:
        client: Bearer-authenticated protocol client.
        path: Path below the provider endpoint.

    Returns:
        The parsed response object.

    Raises:
        SharingProtocolError: On non-2xx answers or non-object JSON.
    """
    response = client.get(path)
    if response.status_code != 200:
        raise SharingProtocolError(
            f"GET {path} answered {response.status_code}: {response.text[:300]}"
        )
    body = response.json()
    if not isinstance(body, dict):
        raise SharingProtocolError(f"GET {path} returned non-object JSON")
    return cast("dict[str, Any]", body)


def list_remote_shares(factory: sessionmaker[Session], provider: SharingProvider) -> list[str]:
    """List share names offered to this recipient.

    Args:
        factory: SQLAlchemy session factory (token decrypt).
        provider: The provider profile.

    Returns:
        Share names.
    """
    with _client_for(factory, provider) as client:
        body = _get_json(client, "/shares")
    return [str(item.get("name", "")) for item in body.get("items", [])]


def list_remote_tables(
    factory: sessionmaker[Session], provider: SharingProvider, share: str
) -> list[dict[str, str]]:
    """List every table of one share (across its schemas).

    Args:
        factory: SQLAlchemy session factory (token decrypt).
        provider: The provider profile.
        share: Remote share name.

    Returns:
        ``{"share", "schema", "name"}`` dicts.
    """
    with _client_for(factory, provider) as client:
        body = _get_json(client, f"/shares/{share}/all-tables")
    return [
        {
            "share": str(item.get("share", share)),
            "schema": str(item.get("schema", "")),
            "name": str(item.get("name", "")),
        }
        for item in body.get("items", [])
    ]


def query_table_as_pandas(
    factory: sessionmaker[Session],
    provider: SharingProvider,
    *,
    share: str,
    schema: str,
    table: str,
    limit_hint: int | None = None,
) -> pd.DataFrame:
    """Materialise one shared table as a pandas DataFrame.

    Speaks the protocol's ``POST …/query`` (NDJSON: ``protocol``,
    ``metaData``, then ``file`` lines with pre-signed URLs),
    downloads every file, and concatenates the parquet contents.

    Args:
        factory: SQLAlchemy session factory (token decrypt).
        provider: The provider profile.
        share: Remote share name.
        schema: Remote schema name.
        table: Remote table name.
        limit_hint: Advisory row limit forwarded to the server.

    Returns:
        The shared table's rows (possibly more than ``limit_hint`` —
        the hint is advisory per protocol).

    Raises:
        SharingProtocolError: On protocol errors or when the
            combined file size exceeds :data:`MAX_RESULT_BYTES`.
    """
    payload: dict[str, Any] = {}
    if limit_hint is not None:
        payload["limitHint"] = int(limit_hint)
    path = f"/shares/{share}/schemas/{schema}/tables/{table}/query"
    with _client_for(factory, provider) as client:
        response = client.post(path, json=payload)
        if response.status_code != 200:
            raise SharingProtocolError(
                f"POST {path} answered {response.status_code}: {response.text[:300]}"
            )
        file_actions: list[dict[str, Any]] = []
        for line in response.text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError as exc:
                raise SharingProtocolError(f"non-JSON NDJSON line: {line[:120]}") from exc
            if "file" in record:
                file_actions.append(record["file"])

        total_size = sum(int(action.get("size", 0)) for action in file_actions)
        if total_size > MAX_RESULT_BYTES:
            raise SharingProtocolError(
                f"shared table is {total_size} bytes — beyond the "
                f"{MAX_RESULT_BYTES}-byte consumer cap"
            )

        frames: list[pd.DataFrame] = []
        for action in file_actions:
            url = str(action.get("url", ""))
            if not url:
                continue
            download = (
                client.get(url)
                if url.startswith(provider.endpoint_url)
                else httpx.get(url, timeout=_TIMEOUT)
            )
            if download.status_code != 200:
                raise SharingProtocolError(
                    f"file download answered {download.status_code} for {url[:120]}"
                )
            frames.append(pd.read_parquet(BytesIO(download.content)))  # pyright: ignore[reportUnknownMemberType]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
