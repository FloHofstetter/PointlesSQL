"""Infrastructure settings: HTTP server, logging, rate limits, schedulers, scanners.

Six sub-models that describe *how PointlesSQL runs* — the binding
address, the log format, the rate-limit buckets, the background-tick
cadence, and the two opt-in scanners (external Delta writes + CDF
tail). All stateless, none share validators.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    """HTTP server bind address and public URL.

    Reads ``POINTLESSQL_SERVER_*`` environment variables.  ``host`` and
    ``port`` drive uvicorn; ``base_url`` is the public URL used when
    constructing OIDC callback URIs (``None`` means derive from the
    incoming request).
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_SERVER_")

    host: str = "127.0.0.1"
    port: int = 8000
    base_url: str | None = None


class EgressSettings(BaseSettings):
    """SSRF guard for user-supplied outbound destination URLs.

    Reads ``POINTLESSQL_EGRESS_*`` environment variables.  ``enabled``
    (default ``True``) governs the whole check; ``allow_private`` is the
    explicit escape hatch for installs that deliberately reach an
    internal relay; ``allowed_hosts`` is an optional comma-separated
    hostname allowlist that further narrows what may be contacted (empty
    means "any public host").  See
    :func:`pointlessql.services.egress_guard.assert_public_http_url`.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_EGRESS_")

    enabled: bool = True
    allow_private: bool = False
    allowed_hosts: str = ""


class ExecutorSettings(BaseSettings):
    """Sizing for the app-owned request-path thread pool.

    Reads ``POINTLESSQL_EXECUTOR_*`` environment variables.  The pool
    backs :func:`pointlessql.services._executor.run_sync` — the bridge
    routes use to run blocking work (PQL reads, ORM queries, audit
    writes) off the event loop.  ``max_workers=0`` keeps Python's own
    ``ThreadPoolExecutor`` heuristic (``min(32, cpu+4)``), matching the
    sizing the loop default executor had; set a positive integer to
    bound request-path threads explicitly.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_EXECUTOR_")

    max_workers: int = 0


class LoggingSettings(BaseSettings):
    """Runtime logging configuration.

    Reads ``POINTLESSQL_LOG_*`` environment variables.  ``level`` is a
    Python logging-level name (``DEBUG``, ``INFO``, …).  ``format``
    controls whether log records render as human-readable text or
    single-line JSON for ingestion.  ``third_party_levels`` overrides
    the per-library default suppression installed by
    :func:`pointlessql.config.configure_logging` —
    ``POINTLESSQL_LOG_THIRD_PARTY_LEVELS='{"httpx":"DEBUG"}'`` lifts
    the default WARNING gate for one upstream when debugging a
    transport issue.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_LOG_")

    level: str = "INFO"
    format: Literal["text", "json"] = "text"
    third_party_levels: dict[str, str] = {}


class RateLimitSettings(BaseSettings):
    """Rate limits on ``/auth/*``.

    Reads ``POINTLESSQL_RATE_LIMIT_*`` environment variables.  Fixed-
    window counters in ``rate_limit_events``; defaults are tuned for a
    single-node deploy — ten login attempts per IP every ten minutes is
    well above any human retry pattern but below what a credential-
    stuffing script expects.  ``trust_x_forwarded_for`` stays OFF by
    default because trusting it unconditionally would let any client
    forge the header and escape the per-IP bucket.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_RATE_LIMIT_")

    enabled: bool = True
    login_ip_count: int = 10
    login_ip_window_s: int = 600
    login_email_count: int = 5
    login_email_window_s: int = 600
    register_ip_count: int = 5
    register_ip_window_s: int = 3600
    oidc_ip_count: int = 20
    oidc_ip_window_s: int = 600
    # public SQL Statement Execution API.  Bucketed per
    # API key id so one noisy integration cannot starve others.
    # Generous default (60/min) fits a typical dbt run; restrictive
    # enough to bound runaway scripts.
    sql_statements_apikey_count: int = 60
    sql_statements_apikey_window_s: int = 60
    trust_x_forwarded_for: bool = False


class SchedulerSettings(BaseSettings):
    """Background job scheduler configuration.

    Reads ``POINTLESSQL_SCHEDULER_*`` environment variables.  Tests
    flip ``enabled=False`` in ``conftest.py`` so the background loop
    never ticks during normal runs; dedicated scheduler tests flip it
    back on.  ``max_concurrent_runs`` is a global ceiling across every
    job; a per-job semaphore (``Job.max_parallel_runs``) layers on top.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_SCHEDULER_")

    enabled: bool = True
    tick_seconds: int = 30
    max_concurrent_runs: int = 4


class ExternalWritesSettings(BaseSettings):
    """External-write detection scanner configuration.

    Reads ``POINTLESSQL_EXTERNAL_WRITES_*`` environment variables.
    The  scanner walks ``DeltaTable.history()`` per UC
    table and INSERT-OR-IGNOREs into ``unattributed_writes`` for
    every commit not matched by an ``agent_run_operations`` row.

    ``scan_interval_seconds`` defaults to ``0`` (disabled) because
    on a single-node vServer the per-table ``DeltaTable.history()``
    cost adds up; admins enable it deliberately.  The on-demand
    ``POST /api/admin/external-writes/scan`` route works regardless.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_EXTERNAL_WRITES_")

    scan_interval_seconds: int = 0
    history_limit: int = 200


class CDFTailSettings(BaseSettings):
    """CDF tail subscription worker configuration.

    Reads ``POINTLESSQL_CDF_TAIL_*`` environment variables.  The
    Phase-40.5 background worker periodically reads
    ``DeltaTable.load_cdf()`` per active
    :class:`CdfTailSubscription` and INSERT-OR-IGNOREs every CDF row
    into ``cdf_tail_events``.

    ``interval_seconds`` defaults to ``0`` (disabled) — same opt-in
    discipline as :class:`ExternalWritesSettings`.  ``history_limit``
    caps the per-tick commit-version range so a long-idle
    subscription doesn't spike memory on its first catch-up tick.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_CDF_TAIL_")

    interval_seconds: int = 0
    history_limit: int = 200


class ObservabilitySettings(BaseSettings):
    """OpenTelemetry tracing configuration (opt-in, default off).

    Reads ``POINTLESSQL_OBSERVABILITY_*`` environment variables.  When
    ``enabled`` is ``False`` (the default) the runtime never imports the
    OpenTelemetry SDK and emits no spans — a clean ``uv run pointlessql``
    has zero observability dependencies and needs no collector.

    When ``enabled`` is ``True``, spans are exported over OTLP to
    ``tracing_endpoint`` (e.g. an OpenTelemetry Collector on
    ``http://127.0.0.1:4317``), tagged with ``service_name`` and carrying
    the request/correlation IDs already threaded through the logging
    context so traces and structured logs share the same identifiers.
    ``sample_ratio`` is the head-based sampling probability (``1.0`` keeps
    every trace; lower it under high load).
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_OBSERVABILITY_")

    enabled: bool = False
    tracing_endpoint: str | None = None
    service_name: str = "pointlessql"
    sample_ratio: float = 1.0
