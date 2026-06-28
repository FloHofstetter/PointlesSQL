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

from typing import TYPE_CHECKING, Protocol, runtime_checkable
from urllib.parse import urlparse

if TYPE_CHECKING:
    from soyuz_catalog_client import Client

    from pointlessql.config import AzureSettings, GCSSettings, ObjectStoreSettings, S3Settings

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
    client: Client | None = None,  # noqa: ARG001 — used by the vending resolver
) -> StorageOptionsResolver:
    """Build the resolver a :class:`PQL` instance uses for its engine.

    Centralised so the credential *source* can change in one place.
    Today it returns a static (config-driven) resolver; the vending
    resolver — which uses ``client`` to fetch short-lived Unity Catalog
    credentials — layers on here with the static resolver as its
    fallback.

    Args:
        object_store: The instance's resolved object-store settings.
        client: The soyuz-catalog client (used once vending lands).

    Returns:
        A resolver bound to this instance's settings.
    """
    return StaticResolver(object_store)
