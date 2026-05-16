"""Audit + lineage + agent-run-stream + audit-stream sink settings.

Four sub-models around the cross-cutting "what did the system observe
and how long do we keep it?" axis. ``AuditSettings`` is the top-level
retention + cockpit knobs; ``LineageRetentionSettings`` is a nested
field-by-field TTL on the four lineage tables;
``AgentRunsSettings`` is the lifecycle-webhook destination; and
``AuditStreamSettings`` is the audit-sink fan-out gate.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LineageRetentionSettings(BaseSettings):
    """Per-axis TTL on the four lineage tables.

    Reads ``POINTLESSQL_AUDIT_LINEAGE_RETENTION_*`` environment
    variables.  Each ``*_days`` field is either a positive integer
    (rows older than ``now - N days`` get pruned at the next tick)
    or ``None`` / ``0`` (axis never pruned).

    Defaults follow the  plan:

    * ``row_edges`` and ``row_rejects`` — 365 days (one operating
      year, enough for compliance retrospectives).
    * ``value_changes`` — 730 days (longer because value-level
      auditing is the strongest forensic surface; doubling the
      window costs little if redaction is on).
    * ``column_map`` — never (small volume, useful as a stable
      schema-evolution record).

    The pruner runs as a scheduler job at 03:00 UTC daily by default
    (off-peak for most operating timezones).
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_AUDIT_LINEAGE_RETENTION_")

    row_edges_days: int | None = 365
    row_rejects_days: int | None = 365
    column_map_days: int | None = None
    value_changes_days: int | None = 730
    cron: str = "0 3 * * *"


class AuditSettings(BaseSettings):
    """Audit-log retention, cleanup, and cockpit configuration.

    Reads ``POINTLESSQL_AUDIT_*`` environment variables. Rows older
    than ``retention_days`` are deleted by the scheduler's periodic
    audit-cleanup tick.  Set ``retention_days=0`` to keep every
    audit row forever (disables retention entirely).

     added cockpit knobs:

    * ``anomaly_baseline_window_days`` — N-day rolling window the
      ``/api/audit/anomalies`` endpoint compares observed values
      against.  7 days mirrors the  Grafana panel.
    * ``anomaly_threshold_sigma`` — observations more than this many
      standard deviations above the baseline mean count as ``warn``
      (≥ σ) or ``critical`` (≥ 2σ × this).  Default 2.0 matches the
      common "two-sigma rule" most operators expect.
    * ``pii_mask_default`` — when ``True`` (the default) values whose
      target column is tagged ``PII`` in soyuz are rendered masked.
      Set to ``False`` to disable masking globally (single-tenant
      deployments where every viewer is already trusted).
    * ``pii_cache_ttl_seconds`` — how long the PII tag resolver
      caches a ``(table, column)`` lookup before re-querying soyuz.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_AUDIT_")

    retention_days: int = 365
    cleanup_interval_seconds: int = 86400  # once per day
    anomaly_baseline_window_days: int = 7
    anomaly_threshold_sigma: float = 2.0
    pii_mask_default: bool = True
    pii_cache_ttl_seconds: int = 600
    pii_mode: Literal["store_clear", "hash_only", "redact_with_audit_log"] = "hash_only"
    pii_hash_secret: str | None = None
    lineage_retention: LineageRetentionSettings = Field(default_factory=LineageRetentionSettings)


class AgentRunsSettings(BaseSettings):
    """Agent-run lifecycle webhook configuration.

    Reads ``POINTLESSQL_AGENT_RUNS_*`` environment variables.  When
    ``webhook_url`` is set, the lifecycle emitter POSTs a
    CloudEvents envelope (``pointlessql.agent_run.started`` /
    ``.completed`` / ``.failed``) to it on every lifecycle
    transition.  Optional ``webhook_hmac_secret`` populates the
    ``X-PointlesSQL-Signature: sha256=<hex>`` header so the receiver
    can verify the payload.

    The single-URL shape is deliberately small — a richer
    per-destination subscription model (multiple URLs, per-event-type
    filters) is a future extension once the control-room UI surfaces it.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_AGENT_RUNS_")

    webhook_url: str | None = None
    webhook_hmac_secret: str | None = None


class AuditStreamSettings(BaseSettings):
    """audit-stream forwarder configuration.

    Reads ``POINTLESSQL_AUDIT_STREAM_*`` environment variables.  All
    sinks are off by default — the stream only fires when at least
    one ``is_active`` row exists in the ``audit_sinks`` table AND
    the corresponding ``*_enabled`` toggle here is ``True``.  The
    two-gate design lets an admin pre-configure destinations without
    accidentally turning on outbound traffic.

    For the agent-run lifecycle events (``started`` / ``completed``
    / ``failed`` / ``tool_call`` / ``rollback.executed``) the
    existing single-URL pipeline at
    :class:`AgentRunsSettings` keeps working unchanged; flip
    ``mirror_lifecycle_to_sinks`` to ``True`` to additionally fan
    those envelopes into the audit-sinks table for a unified trail.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_AUDIT_STREAM_")

    enabled: bool = False
    mirror_lifecycle_to_sinks: bool = False
