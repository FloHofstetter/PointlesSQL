"""Persistence-layer settings: PointlesSQL's own SQLAlchemy DB and Delta engine selection.

Two stateless sub-models that don't share validators or coupling, but
sit together because they both describe *where data lives* (the
metadata DB) and *how it is read* (the Delta compute engine). Anything
about lakehouse metadata is owned by soyuz-catalog — see the project
CLAUDE.md.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from pointlessql.config._settings._paths import PROJECT_ROOT


class DatabaseSettings(BaseSettings):
    """PointlesSQL's own SQLAlchemy database.

    Reads ``POINTLESSQL_DB_*`` environment variables.  Only covers
    PointlesSQL's metadata (sessions, saved queries, audit log,
    scheduler state) — soyuz-catalog owns the lakehouse metadata.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_DB_")

    # Anchored to the repo root so the default DB location is stable
    # no matter which CWD the server was started from.  Override via
    # ``POINTLESSQL_DB_URL`` when a different location is needed
    # (Docker volumes, multi-tenant installs).
    url: str = f"sqlite:///{PROJECT_ROOT / 'pointlessql.db'}"

    # Pool sizing.  Ignored on SQLite (StaticPool by default for
    # ``:memory:``, or a tiny QueuePool for file DBs); applied to
    # QueuePool on Postgres.
    pool_size: int = 5
    max_overflow: int = 10
    # Recycle connections every N seconds to dodge MITM proxies and
    # PG ``idle_in_transaction_session_timeout`` settings.  30 min
    # default — see docs/admin/postgres-deployment.md for tuning.
    pool_recycle_seconds: int = 1800

    # SQLite-only.  How long a writer waits for a competing writer's
    # lock before raising ``database is locked``.  WAL allows one writer
    # at a time, and PointlesSQL runs ~17 background loops that all write
    # the metadata DB, so a non-zero busy_timeout is what keeps a
    # concurrent write from failing outright.  5 s default; ignored on PG.
    sqlite_busy_timeout_ms: int = 5000

    # PG-only.  Applied per-connection via a SET statement_timeout
    # event listener; SQLite has no equivalent and ignores this.
    # 30 s default fits the cockpit's p95 budget; bump for ad-hoc
    # report queries.
    statement_timeout_ms: int = 30000


class DeltaSettings(BaseSettings):
    """Delta-Lake compute engine selection.

    Reads ``POINTLESSQL_DELTA_*`` environment variables.  Currently
    ``pandas`` is the only supported ``engine`` value; reserved for
    future ``spark`` / ``daft`` / ``polars`` backends.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_DELTA_")

    engine: str = "pandas"


class CanvasFileIoSettings(BaseSettings):
    """Sandbox for the canvas FileInput / FileOutput blocks.

    These blocks let a data-product pipeline read and write plain files
    (CSV / Parquet) on the server's filesystem, which sits *outside* Unity
    Catalog governance — a deliberate escape hatch, and a filesystem-reach
    surface that has to be fenced off.  All file paths are resolved
    relative to ``root`` and rejected if they escape it, so the blocks can
    only ever touch a directory an administrator has opted into.

    The feature is dormant by default: with ``root`` unset, both file
    blocks are disabled.  Reads are allowed once a root is configured;
    writes stay denied until ``allow_output`` is explicitly turned on,
    because exporting data out of the lakehouse is the riskier direction.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_CANVAS_FILE_")

    # Sandbox root.  ``None`` (the default) disables the file blocks
    # entirely; set it to a directory to opt in.
    root: Path | None = None
    allow_input: bool = True
    allow_output: bool = False


class S3Settings(BaseSettings):
    """S3 (and S3-compatible) credentials and connection options.

    Reads ``POINTLESSQL_OBJECT_STORE_S3_*`` environment variables.
    These feed the Delta engine's ``storage_options`` so tables whose
    ``storage_location`` is an ``s3://`` URI can be read and written.

    ``endpoint_url`` + ``allow_http`` are what make a non-AWS,
    HTTP-only store (a local moto-server or SeaweedFS gateway) reachable
    — they are properties of the endpoint, not of any one credential, so
    they live here rather than being vended with the keys.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_OBJECT_STORE_S3_")

    access_key_id: str | None = None
    secret_access_key: str | None = None
    session_token: str | None = None
    region: str = "us-east-1"
    # Override for S3-compatible stores (moto-server, SeaweedFS, R2, MinIO).
    # Unset means real AWS S3.
    endpoint_url: str | None = None
    # Permit plain HTTP — required for local endpoints that don't serve TLS.
    allow_http: bool = False
    # Skip the conditional-put / locking provider on commit.  Safe only for
    # single-writer use (local dev, the test fixtures); never for shared
    # production writers.  See docs / ROADMAP for the multi-writer story.
    allow_unsafe_rename: bool = False


class AzureSettings(BaseSettings):
    """Azure Blob Storage / ADLS Gen2 credentials.

    Reads ``POINTLESSQL_OBJECT_STORE_AZURE_*`` environment variables.
    Feeds the Delta engine's ``storage_options`` for ``abfss://`` URIs.
    Either an account key or a SAS token authorises access; a delegation
    SAS is what credential vending mints, so both shapes are accepted.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_OBJECT_STORE_AZURE_")

    account_name: str | None = None
    account_key: str | None = None
    sas_token: str | None = None


class GCSSettings(BaseSettings):
    """Google Cloud Storage credentials.

    Reads ``POINTLESSQL_OBJECT_STORE_GCS_*`` environment variables.
    Feeds the Delta engine's ``storage_options`` for ``gs://`` URIs.
    The service account may be given inline as a JSON blob or as a path
    to a key file; vending supplies a short-lived OAuth token instead.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_OBJECT_STORE_GCS_")

    service_account_path: Path | None = None
    service_account_key: str | None = None
    bearer_token: str | None = None


class ObjectStoreSettings(BaseSettings):
    """Object-store credentials for Delta tables on S3 / Azure / GCS.

    Reads ``POINTLESSQL_OBJECT_STORE_*`` environment variables.  Each
    cloud has its own nested sub-model; the Delta engine resolves a
    table's ``storage_location`` scheme to the matching block and turns
    it into the ``storage_options`` dict the ``deltalake`` library
    expects.  All blocks unset (the default) means no cloud config, so
    the engine stays byte-for-byte on its prior local-filesystem path.

    These static credentials are also the bootstrap and fallback for
    Unity Catalog credential vending: until soyuz-catalog mints real
    short-lived tokens, the vending resolver falls back to these.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_OBJECT_STORE_")

    s3: S3Settings = Field(default_factory=S3Settings)
    azure: AzureSettings = Field(default_factory=AzureSettings)
    gcs: GCSSettings = Field(default_factory=GCSSettings)
