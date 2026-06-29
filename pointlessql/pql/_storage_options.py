"""Resolve a Delta table's storage URI into ``deltalake`` storage_options.

Every Delta read or write in the PQL bridge hands a ``storage_location``
to the ``deltalake`` library.  For a local ``file://`` path that needs no
extra configuration, but an ``s3://`` / ``abfss://`` / ``gs://`` URI needs
a ``storage_options`` dict carrying credentials and connection settings
(endpoint, region, http-vs-https).  This module is the single place that
turns a location into that dict.

The seam is a small :class:`StorageOptionsResolver` protocol so the
*source* of the credentials can vary without touching the call sites:

* :class:`NullResolver` — never supplies options (pure local behaviour).
* :class:`StaticResolver` — reads credentials from
  :class:`~pointlessql.config.ObjectStoreSettings` (env-driven).  This is
  the default and the bootstrap/fallback for vending.
* a vending resolver (added on top of this seam) fetches short-lived
  credentials from Unity Catalog and falls back to the static path.

The key invariant: for a local path every resolver returns ``{}``, and
:func:`storage_options_for` turns that into ``None`` — byte-for-byte the
same call the engines made before object storage existed.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from urllib.parse import urlparse

from soyuz_catalog_client.types import Unset

if TYPE_CHECKING:
    from soyuz_catalog_client import Client
    from soyuz_catalog_client.models.aws_credentials import AwsCredentials
    from soyuz_catalog_client.models.temporary_credentials import TemporaryCredentials

    from pointlessql.config import AzureSettings, GCSSettings, ObjectStoreSettings, S3Settings

logger = logging.getLogger(__name__)

# Scheme groupings.  ``s3a`` is the Hadoop alias; the Azure family covers
# both ABFS(S) and the legacy WASB(S) / adl forms; ``gcs`` aliases ``gs``.
S3_SCHEMES = frozenset({"s3", "s3a"})
AZURE_SCHEMES = frozenset({"abfss", "abfs", "az", "wasbs", "wasb", "adl"})
GCS_SCHEMES = frozenset({"gs", "gcs"})
OBJECT_STORE_SCHEMES = S3_SCHEMES | AZURE_SCHEMES | GCS_SCHEMES


def scheme_of(location: str) -> str:
    """Return the lower-cased URI scheme of a storage location.

    A bare local path (no ``scheme://``) yields the empty string, which
    is exactly what distinguishes it from an object-store URI.

    Args:
        location: A Delta table storage location (path or URI).

    Returns:
        The lower-cased scheme, or ``""`` for a bare local path.
    """
    return urlparse(location).scheme.lower()


def is_object_storage(location: str) -> bool:
    """Report whether a location lives on cloud object storage.

    Args:
        location: A Delta table storage location (path or URI).

    Returns:
        ``True`` for an ``s3``/``abfss``/``gs`` (and aliases) URI, else
        ``False`` (local filesystem, ``file://`` or a bare path).
    """
    return scheme_of(location) in OBJECT_STORE_SCHEMES


def build_s3_storage_options(cfg: S3Settings) -> dict[str, str]:
    """Build the ``deltalake`` storage_options for an S3 location.

    An *entirely default* block yields ``{}`` even though ``region`` has
    a default value: emitting region alone would override a real-AWS
    user's ambient ``AWS_REGION`` and break their setup.  Only once a
    credential or endpoint is configured does the block take over, and
    region is then included.  ``endpoint_url`` + ``allow_http`` are what
    point delta-rs at a local S3-compatible server (moto-server,
    SeaweedFS) instead of real AWS.

    Args:
        cfg: The resolved S3 settings block.

    Returns:
        A ``storage_options`` dict using delta-rs ``AWS_*`` keys, empty
        when nothing meaningful is configured.
    """
    configured = any(
        (cfg.access_key_id, cfg.secret_access_key, cfg.session_token, cfg.endpoint_url)
    )
    if not configured:
        return {}
    opts: dict[str, str] = {}
    if cfg.access_key_id:
        opts["AWS_ACCESS_KEY_ID"] = cfg.access_key_id
    if cfg.secret_access_key:
        opts["AWS_SECRET_ACCESS_KEY"] = cfg.secret_access_key
    if cfg.session_token:
        opts["AWS_SESSION_TOKEN"] = cfg.session_token
    if cfg.region:
        opts["AWS_REGION"] = cfg.region
    if cfg.endpoint_url:
        opts["AWS_ENDPOINT_URL"] = cfg.endpoint_url
    if cfg.allow_http:
        opts["AWS_ALLOW_HTTP"] = "true"
    if cfg.allow_unsafe_rename:
        opts["AWS_S3_ALLOW_UNSAFE_RENAME"] = "true"
    return opts


def build_azure_storage_options(cfg: AzureSettings) -> dict[str, str]:
    """Build the ``deltalake`` storage_options for an Azure location.

    Args:
        cfg: The resolved Azure settings block.

    Returns:
        A ``storage_options`` dict using delta-rs ``AZURE_*`` keys, empty
        when the block is unconfigured.
    """
    opts: dict[str, str] = {}
    if cfg.account_name:
        opts["AZURE_STORAGE_ACCOUNT_NAME"] = cfg.account_name
    if cfg.account_key:
        opts["AZURE_STORAGE_ACCOUNT_KEY"] = cfg.account_key
    if cfg.sas_token:
        opts["AZURE_STORAGE_SAS_TOKEN"] = cfg.sas_token
    return opts


def build_gcs_storage_options(cfg: GCSSettings) -> dict[str, str]:
    """Build the ``deltalake`` storage_options for a GCS location.

    Args:
        cfg: The resolved GCS settings block.

    Returns:
        A ``storage_options`` dict using delta-rs ``GOOGLE_*`` keys, empty
        when the block is unconfigured.
    """
    opts: dict[str, str] = {}
    if cfg.service_account_path:
        opts["GOOGLE_SERVICE_ACCOUNT"] = str(cfg.service_account_path)
    if cfg.service_account_key:
        opts["GOOGLE_SERVICE_ACCOUNT_KEY"] = cfg.service_account_key
    if cfg.bearer_token:
        opts["GOOGLE_BEARER_TOKEN"] = cfg.bearer_token
    return opts


@runtime_checkable
class StorageOptionsResolver(Protocol):
    """Strategy that maps a storage location to ``deltalake`` options.

    Implementations decide *where* the credentials come from (static
    config, vended short-lived tokens, …); the call sites only depend on
    this one method.
    """

    def resolve(self, location: str) -> dict[str, str]:
        """Return the storage_options for ``location`` (``{}`` if local).

        Args:
            location: A Delta table storage location (path or URI).

        Returns:
            The ``storage_options`` dict, empty for a local path.
        """
        ...


class NullResolver:
    """Resolver that never supplies options — pure local-filesystem mode.

    Used as the explicit "no object storage" choice (and the historical
    behaviour) where a caller wants to be sure no credentials leak in.
    """

    def resolve(self, location: str) -> dict[str, str]:
        """Return an empty dict for every location.

        Args:
            location: Ignored.

        Returns:
            An empty dict.
        """
        return {}


class StaticResolver:
    """Resolver backed by :class:`~pointlessql.config.ObjectStoreSettings`.

    Reads the per-scheme credential block from settings and turns it into
    a ``storage_options`` dict.  With no config the dict is empty, so the
    engine stays on its local path.  When ``config`` is omitted the
    resolver reads the cached process settings *lazily on every call*, so
    test env-var monkeypatching (which resets the settings cache) keeps
    working.

    Args:
        config: A pinned settings block; when ``None`` the resolver
            reads the live process settings on each call.
    """

    def __init__(self, config: ObjectStoreSettings | None = None) -> None:
        self._config = config

    @property
    def _object_store(self) -> ObjectStoreSettings:
        if self._config is not None:
            return self._config
        from pointlessql.config import get_settings

        return get_settings().object_store

    def resolve(self, location: str) -> dict[str, str]:
        """Resolve options from the matching per-scheme settings block.

        Args:
            location: A Delta table storage location (path or URI).

        Returns:
            The ``storage_options`` dict, empty for a local path.
        """
        scheme = scheme_of(location)
        cfg = self._object_store
        if scheme in S3_SCHEMES:
            return build_s3_storage_options(cfg.s3)
        if scheme in AZURE_SCHEMES:
            return build_azure_storage_options(cfg.azure)
        if scheme in GCS_SCHEMES:
            return build_gcs_storage_options(cfg.gcs)
        return {}


def _bucket_key(location: str) -> str:
    """Return the ``scheme://netloc`` cache key (bucket) for a location.

    Vended credentials are scoped to a storage root, not a single
    object, so all paths under one bucket share a cache entry.

    Args:
        location: A Delta table storage location (URI).

    Returns:
        The ``scheme://netloc`` prefix used as the cache key.
    """
    parsed = urlparse(location)
    return f"{parsed.scheme}://{parsed.netloc}"


def fetch_path_credentials(client: Client, url: str) -> TemporaryCredentials | None:
    """Fetch Unity Catalog temporary credentials for a storage path.

    Calls soyuz-catalog's url-keyed ``temporary-path-credentials``
    endpoint synchronously (PQL is a sync surface, mirroring the
    ``_get_table.sync`` calls the read/write paths already make).

    Args:
        client: The configured soyuz-catalog client.
        url: The storage path to vend credentials for.

    Returns:
        The vended credentials, or ``None`` when soyuz returned an
        unexpected response shape.
    """
    from soyuz_catalog_client.api.temporary_credentials import (
        generate_temporary_path_credentials_api_2_1_unity_catalog_temporary_path_credentials_post as _gen,  # noqa: E501
    )
    from soyuz_catalog_client.models.generate_temporary_path_credential import (
        GenerateTemporaryPathCredential,
    )
    from soyuz_catalog_client.models.generate_temporary_path_credential_operation import (
        GenerateTemporaryPathCredentialOperation,
    )
    from soyuz_catalog_client.models.temporary_credentials import TemporaryCredentials

    body = GenerateTemporaryPathCredential(
        url=url,
        operation=GenerateTemporaryPathCredentialOperation.PATH_READ_WRITE,
    )
    response = _gen.sync(client=client, body=body)
    return response if isinstance(response, TemporaryCredentials) else None


class VendingResolver:
    """Resolver that vends short-lived UC credentials, else falls back.

    The primary path: ask soyuz-catalog for temporary credentials scoped
    to the storage location (Unity Catalog credential vending). When
    soyuz returns real keys — today only for S3 paths governed by an
    IAM-role external location with vending enabled — they are merged
    with the connection params (endpoint / region / http) from
    :class:`~pointlessql.config.ObjectStoreSettings` and used. Otherwise
    (no vended keys, a non-S3 scheme soyuz does not vend, an unreachable
    catalog, or any error) it falls back to the static resolver, so a
    local / dev store backed by config keeps working.

    Results are cached per bucket: a positive vend until just before its
    expiry, a negative outcome for a short TTL so a dev store doesn't
    re-hit the catalog on every Delta call. The static fallback is always
    re-read live, so it still reflects current settings.

    Args:
        client: The configured soyuz-catalog client.
        object_store: Pinned object-store settings; ``None`` reads the
            live process settings.
        negative_ttl_seconds: How long a "nothing vended" outcome is
            cached before the catalog is asked again.
    """

    def __init__(
        self,
        client: Client,
        object_store: ObjectStoreSettings | None = None,
        *,
        negative_ttl_seconds: float = 60.0,
    ) -> None:
        self._client = client
        self._config = object_store
        self._fallback = StaticResolver(object_store)
        self._negative_ttl = negative_ttl_seconds
        self._cache: dict[str, tuple[dict[str, str] | None, float]] = {}

    @property
    def _s3_settings(self) -> S3Settings:
        if self._config is not None:
            return self._config.s3
        from pointlessql.config import get_settings

        return get_settings().object_store.s3

    def resolve(self, location: str) -> dict[str, str]:
        """Resolve options, preferring vended credentials over static.

        Args:
            location: A Delta table storage location (path or URI).

        Returns:
            The ``storage_options`` dict, empty for a local path.
        """
        scheme = scheme_of(location)
        if scheme not in OBJECT_STORE_SCHEMES:
            return {}
        key = _bucket_key(location)
        now = time.time()
        entry = self._cache.get(key)
        if entry is None or now >= entry[1]:
            entry = self._refresh(location, scheme, now)
            self._cache[key] = entry
        vended = entry[0]
        if vended is not None:
            return dict(vended)
        return self._fallback.resolve(location)

    def _refresh(
        self, location: str, scheme: str, now: float
    ) -> tuple[dict[str, str] | None, float]:
        """Re-query the catalog and compute the cache entry for a bucket.

        Args:
            location: The storage location being resolved.
            scheme: Its already-parsed scheme.
            now: Current epoch seconds.

        Returns:
            ``(options, expires_at)`` — ``options`` is ``None`` to signal
            "use the static fallback" (cached for ``negative_ttl``).
        """
        # Soyuz only vends real credentials for S3 today; for Azure / GCS
        # it returns empty stubs, so skip the round-trip entirely.
        if scheme not in S3_SCHEMES:
            return (None, now + self._negative_ttl)
        try:
            credentials = fetch_path_credentials(self._client, location)
        except Exception:  # noqa: BLE001 — vending is best-effort; fall back to static
            logger.debug(
                "credential vending failed for %s; using static config",
                location,
                exc_info=True,
            )
            return (None, now + self._negative_ttl)
        aws = _real_aws_credentials(credentials)
        if aws is None:
            return (None, now + self._negative_ttl)
        return (self._s3_options(aws), _expiry_seconds(credentials, now, self._negative_ttl))

    def _s3_options(self, aws: AwsCredentials) -> dict[str, str]:
        """Merge vended S3 keys with the configured connection params.

        The vended object carries only the secret material; the
        endpoint / region / http flags are properties of the store, so
        they come from settings regardless of where the keys originate.

        Args:
            aws: The vended ``AwsCredentials`` (validated non-empty).

        Returns:
            A complete S3 ``storage_options`` dict.
        """
        cfg = self._s3_settings
        opts: dict[str, str] = {}
        if cfg.region:
            opts["AWS_REGION"] = cfg.region
        if cfg.endpoint_url:
            opts["AWS_ENDPOINT_URL"] = cfg.endpoint_url
        if cfg.allow_http:
            opts["AWS_ALLOW_HTTP"] = "true"
        if cfg.allow_unsafe_rename:
            opts["AWS_S3_ALLOW_UNSAFE_RENAME"] = "true"
        opts["AWS_ACCESS_KEY_ID"] = str(aws.access_key_id)
        secret = aws.secret_access_key
        if secret and not isinstance(secret, Unset):
            opts["AWS_SECRET_ACCESS_KEY"] = str(secret)
        token = aws.session_token
        if token and not isinstance(token, Unset):
            opts["AWS_SESSION_TOKEN"] = str(token)
        return opts


def _real_aws_credentials(credentials: TemporaryCredentials | None) -> AwsCredentials | None:
    """Return the vended ``AwsCredentials`` only when it carries real keys.

    soyuz returns an empty ``aws_temp_credentials`` stub when it is not
    vending; that must be treated as "nothing vended" so the caller
    falls back to static config.

    Args:
        credentials: The vended response, or ``None``.

    Returns:
        The populated ``AwsCredentials`` object, or ``None`` when the
        response is missing, a stub, or keyless.
    """
    if credentials is None:
        return None
    aws = credentials.aws_temp_credentials
    if aws is None or isinstance(aws, Unset):
        return None
    access_key = aws.access_key_id
    if isinstance(access_key, Unset) or not access_key:
        return None
    return aws


def _expiry_seconds(
    credentials: TemporaryCredentials | None, now: float, default_ttl: float
) -> float:
    """Compute the cache-until time from a vended ``expiration_time``.

    Args:
        credentials: The vended response.
        now: Current epoch seconds.
        default_ttl: Fallback TTL when no usable expiry is present.

    Returns:
        Epoch seconds at which the cached vend should be refreshed — a
        minute before the real expiry, never in the past.
    """
    expiration = None if credentials is None else credentials.expiration_time
    if not expiration or isinstance(expiration, Unset):
        return now + default_ttl
    return max(now, expiration / 1000 - 60)


# Shared default used when a call site has no resolver of its own.  It is
# stateless (settings are read lazily), so a module-level singleton is safe.
_DEFAULT_RESOLVER: StorageOptionsResolver = StaticResolver()


def storage_options_for(
    location: str,
    *,
    resolver: StorageOptionsResolver | None = None,
) -> dict[str, str] | None:
    """Resolve the ``storage_options`` to pass to ``deltalake``, or ``None``.

    This is the convenience every call site uses.  An empty resolution
    (a local path, or unconfigured cloud) collapses to ``None`` so the
    ``deltalake`` call is identical to the pre-object-storage one.

    Args:
        location: A Delta table storage location (path or URI).
        resolver: The resolver to use; defaults to the shared static
            resolver when omitted.

    Returns:
        The ``storage_options`` dict, or ``None`` when there is nothing to
        configure.
    """
    active = resolver if resolver is not None else _DEFAULT_RESOLVER
    opts = active.resolve(location)
    return opts or None


def make_resolver(
    object_store: ObjectStoreSettings,
    client: Client | None = None,
) -> StorageOptionsResolver:
    """Build the resolver a :class:`PQL` instance uses for its engine.

    Centralised so the credential *source* changes in one place. With a
    ``client`` it returns a :class:`VendingResolver` — Unity Catalog
    credential vending is the primary path, with the static config
    resolver as its fallback. Without one (the rare clientless engine) it
    returns the plain static resolver.

    Args:
        object_store: The instance's resolved object-store settings.
        client: The soyuz-catalog client used to vend credentials.

    Returns:
        A resolver bound to this instance's settings and client.
    """
    if client is not None:
        return VendingResolver(client, object_store)
    return StaticResolver(object_store)
