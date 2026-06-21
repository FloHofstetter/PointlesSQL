# pyright: reportPrivateUsage=false
"""Event-trigger evaluation for non-cron jobs.

Two trigger kinds beyond cron:

* ``file_arrival`` — the configured glob is fingerprinted every tick
  (sorted ``name:mtime_ns:size`` lines, SHA-256).  The job fires when
  the fingerprint changes *after* a baseline has been established.
* ``table_update`` — the configured Delta table's version is polled
  through the run-as user's catalog client.  The job fires when the
  version advances past the recorded cursor.

Both kinds store their change-detection state in ``Job.trigger_cursor``
and treat the very first evaluation as a baseline (recorded, never
fired) so enabling a trigger on a directory full of historical files
does not immediately launch the job.  Cursor updates are persisted at
fire-decision time — at-least-once semantics: a run that fails will
not re-fire until the source changes again.
"""

from __future__ import annotations

import datetime
import glob
import hashlib
import json
import logging
import os
from typing import Any, cast

from sqlalchemy.orm import Session, sessionmaker

from pointlessql.config import Settings
from pointlessql.models import Job

logger = logging.getLogger(__name__)


def file_set_fingerprint(entries: list[tuple[str, int, int]]) -> str:
    """Hash a file listing into a stable change-detection fingerprint.

    Args:
        entries: ``(path, mtime_ns, size)`` triples for every match.

    Returns:
        A SHA-256 hex digest over the sorted listing; the digest of an
        empty listing is well-defined and stable.
    """
    lines = sorted(f"{path}:{mtime}:{size}" for path, mtime, size in entries)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _glob_fingerprint(pattern: str) -> str:
    """Fingerprint the current state of *pattern* on the local filesystem."""
    entries: list[tuple[str, int, int]] = []
    for path in glob.glob(pattern, recursive=True):
        try:
            stat = os.stat(path)
        except OSError:
            continue
        entries.append((path, stat.st_mtime_ns, stat.st_size))
    return file_set_fingerprint(entries)


async def _table_version(
    factory: sessionmaker[Session],
    settings: Settings,
    job: Job,
    table: str,
) -> str | None:
    """Return the Delta version of *table* as seen by the job's run-as user.

    Resolution failures (missing user, unknown table, no storage
    location, unreadable Delta log) log a warning and return ``None``
    so the tick treats the trigger as "no change" instead of crashing
    the loop.

    Args:
        factory: Session factory for the run-as user lookup.
        settings: Application settings for the principal client.
        job: The job whose run-as user scopes the catalog lookup.
        table: Three-part ``catalog.schema.table`` name.

    Returns:
        The stringified Delta version, or ``None`` when unresolvable.
    """
    from pointlessql.services.scheduler.runs._db import _load_user_info
    from pointlessql.services.unitycatalog import UnityCatalogClient

    parts = table.split(".")
    if len(parts) != 3:
        logger.warning("table_update trigger: invalid table %r on job %s", table, job.id)
        return None
    with factory() as session:
        user_info = _load_user_info(session, job.run_as_user_id)
    if user_info is None:
        logger.warning("table_update trigger: run-as user missing on job %s", job.id)
        return None
    try:
        client = UnityCatalogClient.for_principal(settings, user_info["email"])
        info = await client.get_table(*parts)
        storage_location = (info or {}).get("storage_location")
        if not storage_location:
            logger.warning("table_update trigger: %r has no storage_location", table)
            return None
        import deltalake

        version = deltalake.DeltaTable(storage_location).version()
        return str(version)
    except Exception:  # noqa: BLE001 — trigger polling must not crash the tick
        logger.warning(
            "table_update trigger: polling %r failed for job %s",
            table,
            job.id,
            exc_info=True,
        )
        return None


async def _sharing_table_version(
    factory: sessionmaker[Session],
    job: Job,
    config: dict[str, Any],
) -> str | None:
    """Return a Delta-Sharing-shared table's version for a ``table_update`` job.

    Resolves the workspace's sharing provider by alias and polls the
    shared table's version over the OpenSharing protocol.  Any
    resolution / transport failure logs a warning and returns ``None``
    so the tick treats it as "no change".

    Args:
        factory: Session factory for provider lookup + token decrypt.
        job: The job whose workspace scopes the provider lookup.
        config: The ``table_update`` trigger config, expected to carry
            ``provider`` / ``share`` / ``schema`` / ``table``.

    Returns:
        The stringified shared-table version, or ``None``.
    """
    from pointlessql.services import delta_sharing_consumer

    fields = {key: config.get(key) for key in ("provider", "share", "schema", "table")}
    if not all(isinstance(value, str) and value.strip() for value in fields.values()):
        logger.warning(
            "table_update(sharing) trigger: missing provider/share/schema/table on job %s",
            job.id,
        )
        return None
    provider = delta_sharing_consumer.get_provider(
        factory, workspace_id=int(job.workspace_id), name=str(fields["provider"]).strip()
    )
    if provider is None:
        logger.warning(
            "table_update(sharing) trigger: provider %r not found on job %s",
            fields["provider"],
            job.id,
        )
        return None
    try:
        version = delta_sharing_consumer.remote_table_version(
            factory,
            provider,
            share=str(fields["share"]).strip(),
            schema=str(fields["schema"]).strip(),
            table=str(fields["table"]).strip(),
        )
    except Exception:  # noqa: BLE001 — trigger polling must not crash the tick
        logger.warning(
            "table_update(sharing) trigger: version poll failed for job %s",
            job.id,
            exc_info=True,
        )
        return None
    return None if version is None else str(version)


async def evaluate_event_trigger(
    factory: sessionmaker[Session],
    settings: Settings,
    job: Job,
    now: datetime.datetime,
) -> bool:
    """Decide whether an event-triggered *job* should fire this tick.

    Args:
        factory: Session factory for cursor persistence.
        settings: Application settings.
        job: A detached job row with ``trigger_kind`` of
            ``file_arrival`` or ``table_update``.
        now: The tick's notion of "now" (unused today; threaded so a
            future debounce window has the clock it needs).

    Returns:
        ``True`` when the job should launch.  The cursor is persisted
        whenever it changed — including the silent baseline write on
        the first evaluation.
    """
    del now
    try:
        config = json.loads(job.trigger_config or "{}")
    except json.JSONDecodeError:
        logger.warning("event trigger: invalid trigger_config on job %s", job.id)
        return False
    if not isinstance(config, dict):
        logger.warning("event trigger: trigger_config is not an object on job %s", job.id)
        return False
    config = cast("dict[str, Any]", config)

    observed: str | None = None
    if job.trigger_kind == "file_arrival":
        pattern = config.get("path")
        if not isinstance(pattern, str) or not pattern.strip():
            logger.warning("file_arrival trigger: missing 'path' on job %s", job.id)
            return False
        observed = _glob_fingerprint(pattern.strip())
    elif job.trigger_kind == "table_update":
        raw_source = config.get("source")
        source = (
            raw_source.strip() if isinstance(raw_source, str) and raw_source.strip() else "local"
        )
        if source == "sharing":
            # A Delta-Sharing-shared table/view: version comes from the
            # OpenSharing protocol rather than the local Delta log.
            observed = await _sharing_table_version(factory, job, config)
        else:
            # Local tables and soyuz system tables share the catalog +
            # Delta-log version path; "system" only pre-fills the FQN.
            table = config.get("table")
            if not isinstance(table, str) or not table.strip():
                logger.warning("table_update trigger: missing 'table' on job %s", job.id)
                return False
            observed = await _table_version(factory, settings, job, table.strip())
    else:
        logger.warning("unknown trigger_kind %r on job %s", job.trigger_kind, job.id)
        return False

    if observed is None:
        return False
    if job.trigger_cursor == observed:
        return False

    is_baseline = job.trigger_cursor is None
    _store_cursor(factory, job.id, observed)
    if is_baseline:
        logger.info("event trigger: baseline recorded for job %s", job.id)
        return False
    return True


def _store_cursor(factory: sessionmaker[Session], job_id: int, cursor: str) -> None:
    """Persist the new trigger cursor for *job_id*."""
    with factory() as session:
        row = session.get(Job, job_id)
        if row is None:  # pragma: no cover — job deleted mid-tick
            return
        row.trigger_cursor = cursor
        session.commit()
