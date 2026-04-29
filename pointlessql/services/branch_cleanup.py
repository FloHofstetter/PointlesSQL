"""Auto-cleanup of stale Delta branches (Sprint 16.5.6).

Walks the UC schema set, picks branches in ``status='active'`` whose
``created_at`` is older than ``settings.branch.auto_cleanup_retention_days``,
and calls :func:`pql.branch_discard` on each.

Default-disabled: operators flip ``branch.auto_cleanup_enabled=true``
before this job actually deletes anything.  When disabled the job
short-circuits with zero side effects and a structured log line so
the audit trail records the no-op.

The job is registered under kind ``"branch_cleanup"`` in the
scheduler registry.  Scheduler ticks call it via the standard
:data:`JobExecutor` signature; the executor lives in
``services/scheduler/executors.py`` and delegates here.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from soyuz_catalog_client import Client

from pointlessql.pql._branch import discard_branch_schema
from pointlessql.pql._branch_errors import BranchError
from pointlessql.services import branch_tags
from pointlessql.services.unitycatalog._api import (
    _list_catalogs as list_catalogs_api,
)
from pointlessql.services.unitycatalog._api import (
    _list_schemas as list_schemas_api,
)
from pointlessql.settings import Settings

logger = logging.getLogger(__name__)


def _parse_iso8601(value: str) -> datetime.datetime | None:
    """Parse an ISO-8601 UTC string; return ``None`` on garbage input.

    Args:
        value: Tag value as written by :func:`apply_branch_tags_sync`.

    Returns:
        Parsed datetime or ``None`` when the string is malformed.
    """
    try:
        return datetime.datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _is_eligible_for_cleanup(
    tags: branch_tags.BranchTags,
    *,
    now: datetime.datetime,
    retention_days: int,
) -> bool:
    """Return ``True`` when *tags* describe an active branch past retention.

    Branches in any non-``active`` status are skipped — promoted ones
    are intentionally permanent, discarded ones are no-ops anyway,
    pre-promote backups are operator-recoverable archives.

    Args:
        tags: Parsed branch metadata.
        now: Reference timestamp (injectable for tests).
        retention_days: Threshold in days.

    Returns:
        ``True`` when the branch should be discarded.
    """
    if tags.status != branch_tags.STATUS_ACTIVE:
        return False
    if tags.is_pre_promote_backup:
        return False
    created_at = _parse_iso8601(tags.created_at)
    if created_at is None:
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=datetime.UTC)
    age = now - created_at
    return age >= datetime.timedelta(days=retention_days)


def cleanup_old_branches(
    *,
    client: Client,
    settings: Settings,
    now: datetime.datetime | None = None,
) -> dict[str, int]:
    """Walk every UC schema and discard active branches past retention.

    A no-op (`{deleted: 0, skipped: 0, errored: 0}`) when
    ``settings.branch.auto_cleanup_enabled`` is ``False``.  Single
    discard failures are logged + counted but never abort the loop —
    one corrupt branch must not stop the rest of the install from
    being cleaned.

    Args:
        client: Configured soyuz client.
        settings: Resolved :class:`Settings`.
        now: UTC reference timestamp; defaults to
            :func:`datetime.datetime.now`.

    Returns:
        ``{"deleted": int, "skipped": int, "errored": int,
        "enabled": bool}``.  Stable shape for telemetry.
    """
    if not settings.branch.auto_cleanup_enabled:
        logger.info(
            "cleanup_old_branches: skipped (auto_cleanup_enabled=False)"
        )
        return {"deleted": 0, "skipped": 0, "errored": 0, "enabled": False}

    reference = now or datetime.datetime.now(datetime.UTC)
    retention_days = settings.branch.auto_cleanup_retention_days

    deleted = 0
    skipped = 0
    errored = 0

    catalogs_response = list_catalogs_api.sync(client=client)
    catalog_rows: list[Any] = []
    if catalogs_response is not None:
        catalogs_attr = getattr(catalogs_response, "catalogs", None)
        if isinstance(catalogs_attr, list):
            catalog_rows = catalogs_attr

    for catalog in catalog_rows:
        catalog_name = getattr(catalog, "name", None)
        if not isinstance(catalog_name, str):
            continue
        try:
            schemas_response = list_schemas_api.sync(
                client=client, catalog_name=catalog_name
            )
        except Exception:  # noqa: BLE001 — keep loop going
            logger.warning(
                "cleanup_old_branches: list_schemas failed for catalog=%s",
                catalog_name,
                exc_info=True,
            )
            errored += 1
            continue
        if schemas_response is None:
            continue
        schema_rows = getattr(schemas_response, "schemas", None)
        if not isinstance(schema_rows, list):
            continue
        for schema in schema_rows:
            schema_name = getattr(schema, "name", None)
            if not isinstance(schema_name, str):
                continue
            schema_fqn = f"{catalog_name}.{schema_name}"
            try:
                tags = branch_tags.read_branch_tags_sync(client, schema_fqn)
            except Exception:  # noqa: BLE001 — corrupt tag set logged below
                logger.warning(
                    "cleanup_old_branches: read_branch_tags failed for %s",
                    schema_fqn,
                    exc_info=True,
                )
                errored += 1
                continue
            if tags is None:
                continue
            if not _is_eligible_for_cleanup(
                tags, now=reference, retention_days=retention_days
            ):
                skipped += 1
                continue
            try:
                discard_branch_schema(
                    client=client,
                    branch_schema_fqn=schema_fqn,
                    settings=settings,
                    agent_run_id=None,
                )
                deleted += 1
                logger.info(
                    "cleanup_old_branches: discarded %s (age past %dd retention)",
                    schema_fqn,
                    retention_days,
                )
            except BranchError:
                logger.warning(
                    "cleanup_old_branches: BranchError discarding %s",
                    schema_fqn,
                    exc_info=True,
                )
                errored += 1
            except Exception:  # noqa: BLE001 — never abort the loop
                logger.exception(
                    "cleanup_old_branches: unexpected failure discarding %s",
                    schema_fqn,
                )
                errored += 1

    summary = {
        "deleted": deleted,
        "skipped": skipped,
        "errored": errored,
        "enabled": True,
    }
    logger.info("cleanup_old_branches: %s", summary)
    return summary
