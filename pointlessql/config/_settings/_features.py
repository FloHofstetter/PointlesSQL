"""Feature-flag and feature-tuning settings.

Six sub-models that gate or tune user-facing features rather than
infrastructure: ad-hoc SQL editor, Delta-Branching, medallion
conventions, data-products + their freshness/passport loops, the
notification digest, and the Lens read-only Q&A surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from pointlessql.config._settings._paths import PROJECT_ROOT


class SQLSettings(BaseSettings):
    """Ad-hoc SQL editor configuration.

    Reads ``POINTLESSQL_SQL_*`` environment variables.  ``enabled``
    hides ``/sql`` and rejects ``/api/sql/*`` at the route layer when
    ``False``.  ``max_rows`` caps the LIMIT DuckDB applies to every
    query; ``query_timeout_seconds`` aborts a long-running query so
    operators can set it once and forget.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_SQL_")

    enabled: bool = True
    max_rows: int = 10_000
    query_timeout_seconds: int = 60
    cost_gate_threshold_rows: int = 1_000_000


class EditorChatSettings(BaseSettings):
    """Editor-chat configuration — shared by SQL + notebook surfaces.

    Phase 91 introduced this as ``SqlChatSettings`` for the NL→SQL
    drawer.  Phase 96 added the notebook-editor AI assistant, which
    consumes the exact same provider / model / executor config —
    there is no axis on which an operator would want different
    model defaults per surface, so the setting is shared and the
    class was renamed.  The env prefix moved to
    ``POINTLESSQL_EDITOR_CHAT_*`` in the same cut-over (no shim).

    Reads ``POINTLESSQL_EDITOR_CHAT_*`` environment variables.  The
    drawer is gated behind ``enabled`` so admins can stand the
    feature down per-deploy without touching the frontend; the
    same flag also gates the notebook-editor AI button.

    ``default_model`` + ``provider`` route to the in-process
    :class:`hermes_agent.AIAgent` instance built per turn.  Both
    are typed as strings rather than enums because Hermes
    auto-detects the provider from the base URL when ``provider``
    is empty — only set it if you must override.

    ``max_turns_per_session`` bounds the conversation history so
    the token window doesn't drift indefinitely; after the limit
    the WS layer emits a warning notify and resets the row.

    ``executor_workers`` sizes the dedicated thread pool that
    backs the synchronous ``AIAgent.run_conversation`` calls.
    Two workers is the right shape: one runs the active turn, one
    stays reserved for the cancel-handshake from the WS side.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_EDITOR_CHAT_")

    enabled: bool = True
    default_model: str = "claude-haiku-4-5-20251001"
    provider: str = ""
    base_url: str = ""
    max_turns_per_session: int = 20
    executor_workers: int = 2


class BranchSettings(BaseSettings):
    """Delta-Branching strategy + auto-cleanup configuration.

    Reads ``POINTLESSQL_BRANCH_*`` environment variables.  Two
    independent concerns:

    * ``cloud_strategy`` — how :func:`pql.branch` handles a parent
      schema whose ``storage_root`` is on object storage (``s3://``,
      ``gs://``, ``abfss://``, ``wasbs://``).  Cloud has no symlink
      primitive so the zero-copy local-FS path is unavailable
      there.  ``"error"`` (the default) refuses cloud branching
      outright; ``"deep_copy"`` opts into the bigger storage cost so
      branching works everywhere.  Local FS always uses the
      symlink path.
    * ``auto_cleanup_*`` — opt-in scheduler job that discards old
      ``status=active`` branches so storage doesn't drift.  Default
      disabled (``auto_cleanup_enabled=False``); operators flip it
      on once they trust the discard primitive.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_BRANCH_")

    cloud_strategy: Literal["deep_copy", "error"] = "error"
    auto_cleanup_enabled: bool = False
    auto_cleanup_retention_days: int = 30
    auto_cleanup_cron: str = "0 2 * * *"


class ConventionsSettings(BaseSettings):
    """Medallion conventions config-file pointer.

    Reads ``POINTLESSQL_CONVENTIONS_*`` environment variables.  When
    ``path`` is ``None`` (the default) the loader returns the built-
    in Medallion defaults from
    :mod:`pointlessql.conventions._defaults`; when set it points at
    a ``pointlessql.yaml`` whose top-level fields shallow-merge over
    those defaults.  See
    [`docs/data-layers.md`](../../docs/data-layers.md) for the prose
    contract and ADR ``0002-duckdb-first`` for the compute opinion
    this codifies.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_CONVENTIONS_")

    path: Path | None = None


class DataProductsSettings(BaseSettings):
    """Data-product loader + freshness-scanner configuration.

    Reads ``POINTLESSQL_DATA_PRODUCTS_*`` environment variables.  The
    loader walks ``yaml_search_paths`` for ``pointlessql.yaml`` files
    whose top-level ``data_product:`` block declares a UC schema as
    a product (Sprint 50.1).  The freshness scanner (Sprint 50.4)
    iterates every cached product whose ``sla_minutes`` is non-NULL.

    ``scan_interval_seconds`` defaults to ``0`` (dormant) — same
    opt-in discipline as :class:`ExternalWritesSettings` and
    :class:`CDFTailSettings`.  ``yaml_search_paths`` defaults to an
    empty list; admins point it at the data-team repos that ship
    ``pointlessql.yaml``.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_DATA_PRODUCTS_")

    scan_interval_seconds: int = 0
    yaml_search_paths: list[Path] = Field(default_factory=list[Path])
    re_alert_suppress_minutes: int = 60
    # Phase 72.3 — cached "trending" rank refresh.  Default 0
    # keeps the loop dormant so single-tenant installs don't run
    # the join continuously; flipping to 900 (15 min) starts the
    # standard cadence.
    trending_refresh_interval_seconds: int = 0
    trending_window_days: int = 7
    trending_top_n: int = 10
    # Phase 73.1 — promote-to-DP candidate scanner.
    promote_enabled: bool = False
    promote_scan_interval_seconds: int = 1800
    promote_window_days: int = 14
    promote_min_runs: int = 3
    promote_min_ops: int = 10
    draft_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "dp_drafts")
    # Phase 73.4 — auto-passport background refresh loop.
    passport_loop_enabled: bool = False
    passport_loop_interval_seconds: int = 86_400
    passport_loop_stale_threshold_seconds: int = 86_400
    # Phase 73.5 — cross-DP co-occurrence cache.
    cooccurrence_enabled: bool = False
    cooccurrence_refresh_interval_seconds: int = 21_600
    cooccurrence_window_days: int = 7
    cooccurrence_top_n: int = 10
    # Phase 74.1 — active reviewer (in-proc daily steward delegate).
    active_reviewer_enabled: bool = False
    active_reviewer_trigger_hour: int = 3  # UTC
    active_reviewer_llm_provider: str = "anthropic"
    active_reviewer_model: str = "claude-haiku-4-5-20251001"
    active_reviewer_max_concurrent: int = 3


class NotificationsSettings(BaseSettings):
    """Per-user notification + daily-digest configuration (Phase 71.4).

    The ``digest_email_optin`` column on the User model is the
    per-user opt-in.  ``digest_enabled`` is the install-level
    master switch: existing deployments don't suddenly start
    firing a daily loop after upgrade.  When both are true *and*
    the user has unread notifications from the prior 24h, the
    :func:`_user_notification_digest_loop` emits one
    ``pointlessql.notification.digest`` governance event per
    eligible recipient — the audit-stream forwarder's webhook /
    SES-bound sink does the actual mail delivery.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_NOTIFICATIONS_")

    digest_enabled: bool = False
    digest_trigger_hour: int = 6
    digest_poll_interval_seconds: int = 300


class LensSettings(BaseSettings):
    """Lens read-only Q&A surface configuration (Phase 65).

    Reads ``POINTLESSQL_LENS_*`` environment variables.  Lens hosts a
    chat-style analyst UI at ``/lens`` and an MCP (Model Context
    Protocol) server for IDE consumers.  Both transports share the
    same tool registry; the safety knobs below apply to every entry
    point.

    ``default_query_limit`` is the LIMIT auto-injected on every SELECT
    that does not carry an explicit one (see
    :func:`pointlessql.pql.sql_parser.inject_limit`).  ``max_query_cost``
    + ``max_session_cost`` are the EXPLAIN-derived cost caps; queries
    whose plan exceeds the per-query cap are denied outright, sessions
    whose accumulated cost exceeds the per-session cap stop accepting
    new tool calls until a new session is opened.

    Provider model defaults are surfaced when the workspace's
    :class:`LensProviderCreds.default_model` is ``NULL``.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_LENS_")

    enabled: bool = True
    default_query_limit: int = 1000
    max_query_cost: float = 1_000_000.0
    max_session_cost: float = 10_000_000.0
    max_messages_per_session: int = 100
    openai_model_default: str = "gpt-4o-mini"
    anthropic_model_default: str = "claude-haiku-4-5-20251001"
