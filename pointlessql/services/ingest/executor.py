"""Scheduler executor + manual-pull entry point for ``"ingest_pull"``.

:func:`run_pull` carries the full pull lifecycle (load source → run
DuckDB reader → call PQL → record stats → emit fanout) and is
intentionally reusable: both the scheduler executor and the manual
"Pull now" route call into it.

The scheduler executor wrapper :func:`ingest_pull_executor` matches the
:data:`pointlessql.services.scheduler.registry.JobExecutor` signature
and is registered in :func:`build_default_registry`.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from sqlalchemy import select

from pointlessql.exceptions import ValidationError
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


async def run_pull(
    *,
    source_id: int,
    mapping_index: int,
    user_email: str,
    job_run_id: int,
    session_factory: Any = None,
) -> dict[str, Any]:
    """Execute one mapping pull end-to-end.

    Args:
        source_id: IngestSource primary key.
        mapping_index: Position inside the source's ``table_mappings``.
        user_email: The principal under which the PQL write runs.  An
            empty string is accepted (PQL falls back to unprincipal'd).
        job_run_id: Owning JobRun id (0 for manual pulls).
        session_factory: Optional SQLAlchemy session factory.  Falls
            back to :func:`pointlessql.db.get_session_factory` when
            ``None``; the manual-pull route passes the request-bound
            ``app.state.session_factory`` so tests aren't bound to
            the module-level singleton.

    Returns:
        A serialised :class:`pointlessql.services.ingest.pull.PullResult`
        dict on success.

    Raises:
        ValidationError: When the source / mapping cannot be loaded.
        PullError: When the pull itself fails — the manual route
            catches and surfaces it; the scheduler wrapper lets it
            propagate so ``JobRun.error`` captures the failure.
    """
    from pointlessql.models import IngestSource
    from pointlessql.pql.pql import PQL
    from pointlessql.services.ingest.pull import (
        PullError,
        load_mappings,
        pull_mapping,
    )

    if session_factory is None:
        from pointlessql.db import get_session_factory

        factory = get_session_factory()
    else:
        factory = session_factory

    with factory() as session:
        source = session.get(IngestSource, int(source_id))
        if source is None or not source.is_active:
            raise ValidationError(f"IngestSource {source_id} not found or inactive.")
        try:
            config_dict = json.loads(source.config or "{}")
            secrets_dict = json.loads(source.secrets or "{}")
        except (ValueError, TypeError) as exc:
            raise ValidationError(f"IngestSource {source_id} has malformed JSON: {exc}.") from exc
        mappings = load_mappings(source.table_mappings)
        if not 0 <= mapping_index < len(mappings):
            raise ValidationError(
                f"mapping_index {mapping_index} out of range for source {source_id}."
            )
        mapping = mappings[mapping_index]
        source_kind = source.kind
        source_name = source.name
        workspace_id = source.workspace_id
        owner_user_id = source.owner_user_id

    pql_instance = PQL(principal=user_email or None)

    try:
        result = pull_mapping(
            kind=source_kind,
            config=config_dict,
            secrets=secrets_dict,
            mapping=mapping,
            pql_instance=pql_instance,
        )
    except PullError as exc:
        _record_pull_outcome(
            factory=factory,
            source_id=int(source_id),
            mapping_index=mapping_index,
            job_run_id=job_run_id,
            ok=False,
            reason=exc.reason,
            hint=exc.hint,
            rows_written=0,
            duration_ms=0,
            target_fqn=str(mapping.get("target_fqn") or ""),
            new_high_water=None,
        )
        _fanout_pull(
            factory=factory,
            event_type="pointlessql.ingest.failed",
            workspace_id=workspace_id,
            owner_user_id=owner_user_id,
            source_name=source_name,
            target_fqn=str(mapping.get("target_fqn") or ""),
            summary=f"Pull from {source_name} failed: {exc.reason}",
        )
        raise

    _record_pull_outcome(
        factory=factory,
        source_id=int(source_id),
        mapping_index=mapping_index,
        job_run_id=job_run_id,
        ok=True,
        reason=None,
        hint=None,
        rows_written=result.rows_written,
        duration_ms=result.duration_ms,
        target_fqn=result.target_fqn,
        new_high_water=result.new_high_water_value,
    )
    _fanout_pull(
        factory=factory,
        event_type="pointlessql.ingest.pulled",
        workspace_id=workspace_id,
        owner_user_id=owner_user_id,
        source_name=source_name,
        target_fqn=result.target_fqn,
        summary=(f"Pulled {result.rows_written} rows from {source_name} → {result.target_fqn}"),
    )
    return result.to_dict()


async def ingest_pull_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Scheduler-side wrapper around :func:`run_pull`.

    Matches the
    :data:`pointlessql.services.scheduler.registry.JobExecutor` signature.
    Reads ``source_id`` + ``mapping_index`` from ``config`` and
    delegates to :func:`run_pull`; the scheduler captures any raised
    exception on ``JobRun.error``.

    Args:
        job_run_id: Current ``JobRun.id``.
        user_info: The run-as user's :class:`UserInfo`.
        config: Must carry ``source_id`` and ``mapping_index``.
        uc_client: Principal-forwarded facade.  Unused — PQL builds
            its own internally based on ``user_info.email``.

    Raises:
        ValidationError: When *config* is missing required keys.
    """
    del uc_client
    source_id = config.get("source_id")
    mapping_index = config.get("mapping_index")
    if source_id is None or mapping_index is None:
        raise ValidationError("ingest_pull job config must carry 'source_id' and 'mapping_index'.")
    if not isinstance(mapping_index, int):
        raise ValidationError("mapping_index must be an integer.")
    await run_pull(
        source_id=int(source_id),
        mapping_index=int(mapping_index),
        user_email=user_info.get("email") or "",
        job_run_id=job_run_id,
    )


def _record_pull_outcome(
    *,
    factory: Any,
    source_id: int,
    mapping_index: int,
    job_run_id: int,
    ok: bool,
    reason: str | None,
    hint: str | None,
    rows_written: int,
    duration_ms: int,
    target_fqn: str,
    new_high_water: str | None,
) -> None:
    """Persist per-pull stats on the IngestSource row.

    Updates ``table_mappings[mapping_index]["last_pull_stats"]`` and,
    on incremental success, the mapping's ``last_high_water_value``.

    Args:
        factory: SQLAlchemy session factory.
        source_id: IngestSource primary key.
        mapping_index: Index inside ``table_mappings``.
        job_run_id: Owning JobRun id (0 marks a manual pull).
        ok: ``True`` for a successful pull, ``False`` otherwise.
        reason: Failure reason (``None`` on success).
        hint: Optional failure hint.
        rows_written: Number of rows landed on success.
        duration_ms: Wall-clock duration.
        target_fqn: Target Delta table FQN.
        new_high_water: New high-water value when applicable.
    """
    from pointlessql.models import IngestSource
    from pointlessql.services.ingest.pull import dump_mappings, load_mappings

    with factory() as session:
        source = session.get(IngestSource, int(source_id))
        if source is None:
            return
        mappings = load_mappings(source.table_mappings)
        if not 0 <= mapping_index < len(mappings):
            return
        now = datetime.datetime.now(datetime.UTC)
        stats: dict[str, Any] = {
            "ok": bool(ok),
            "rows_written": int(rows_written),
            "duration_ms": int(duration_ms),
            "target_fqn": target_fqn,
            "job_run_id": int(job_run_id),
            "ts": now.isoformat(),
        }
        if reason:
            stats["error"] = reason
        if hint:
            stats["hint"] = hint
        mappings[mapping_index]["last_pull_stats"] = stats
        if ok and new_high_water is not None:
            mappings[mapping_index]["last_high_water_value"] = new_high_water
        source.table_mappings = dump_mappings(mappings)
        source.updated_at = now
        session.commit()


def _fanout_pull(
    *,
    factory: Any,
    event_type: str,
    workspace_id: int,
    owner_user_id: int,
    source_name: str,
    target_fqn: str,
    summary: str,
) -> None:
    """Emit a feed-level event for the pull lifecycle.

    The recipient set is:

    * The source owner (always).
    * Followers of the target DP, when one exists for ``target_fqn``.

    We look the DP up by ``(workspace_id, catalog_name, schema_name)``
    — DPs are keyed at the schema level.  Missing-DP is fine — the
    event still fans to the owner so the actor always sees pull
    outcomes.

    Args:
        factory: Session factory.
        event_type: ``pointlessql.ingest.pulled`` or ``.failed``.
        workspace_id: Tenant scope.
        owner_user_id: Source creator's user id; always notified.
        source_name: Human-readable source name for the summary.
        target_fqn: ``catalog.schema.table`` of the Delta target.
        summary: Pre-formatted one-line markdown summary.
    """
    from pointlessql.models import DataProduct
    from pointlessql.services.notifications.fanout import fanout_event

    data_product_id: int | None = None
    entity_kind = "table"
    parts = target_fqn.split(".") if target_fqn else []
    if len(parts) == 3:
        try:
            with factory() as session:
                dp = session.execute(
                    select(DataProduct).where(
                        DataProduct.workspace_id == int(workspace_id),
                        DataProduct.catalog_name == parts[0],
                        DataProduct.schema_name == parts[1],
                    )
                ).scalar_one_or_none()
                if dp is not None:
                    data_product_id = int(dp.id)
                    entity_kind = "dp"
        except Exception:  # noqa: BLE001 — DP lookup is best-effort
            logger.exception("ingest fanout: DP lookup failed for %s", target_fqn)

    if entity_kind == "dp" and len(parts) == 3:
        source_url = f"/data-products/{parts[0]}/{parts[1]}"
    elif len(parts) == 3:
        source_url = f"/catalogs/{parts[0]}/schemas/{parts[1]}/tables/{parts[2]}"
    else:
        source_url = "/admin/sources"
    try:
        fanout_event(
            factory,
            event_type=event_type,
            entity_kind=entity_kind,
            entity_ref=target_fqn,
            workspace_id=int(workspace_id),
            actor_user_id=None,
            source_url=source_url,
            summary_md=summary,
            data_product_id=data_product_id,
            extra_recipients=[int(owner_user_id)],
        )
    except Exception:  # noqa: BLE001 — fanout is best-effort
        logger.exception("ingest fanout failed for event=%s target=%s", event_type, target_fqn)
