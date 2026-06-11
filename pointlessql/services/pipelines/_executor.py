"""Scheduler executor for the ``"pipeline_run"`` job kind."""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select

from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models.pipelines import Pipeline, PipelineRun
from pointlessql.pql._policies import extract_table_policy
from pointlessql.services.authorization import SELECT, check_privilege
from pointlessql.services.pipelines._crud import PipelineValidationError, parse_datasets
from pointlessql.services.pipelines._engine import run_pipeline_sync
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo


async def pipeline_run_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Run one pipeline from the scheduler (as the job's run-as user).

    Mirrors the route's groundwork — async SELECT enforcement +
    policy collection per external reference — then dispatches the
    synchronous engine in a worker thread.

    Args:
        job_run_id: Current ``JobRun.id`` (unused — the pipeline
            keeps its own run history).
        user_info: The run-as user; reads enforce against them.
        config: Must carry ``pipeline_id``.
        uc_client: Principal-forwarded facade for the enforcement
            hops.

    Raises:
        ValidationError: When ``pipeline_id`` is missing/unknown or
            the stored definition no longer validates.
        CatalogNotFoundError: When an external reference is unknown.
        RuntimeError: When the run finished ``failed`` — surfacing
            the error on ``JobRun.error``.
    """
    del job_run_id
    from pointlessql.config import get_settings
    from pointlessql.db import get_session_factory
    from pointlessql.services.soyuz_client import make_principal_client

    pipeline_id = config.get("pipeline_id")
    if not isinstance(pipeline_id, int):
        raise ValidationError("pipeline_run jobs need an integer pipeline_id in config")
    factory = get_session_factory()
    with factory() as session:
        pipeline = session.get(Pipeline, pipeline_id)
        if pipeline is None:
            raise ValidationError(f"pipeline id={pipeline_id} not found")
        session.expunge(pipeline)

    try:
        datasets = parse_datasets(pipeline)
    except PipelineValidationError as exc:
        raise ValidationError(str(exc)) from exc
    dataset_names = {d["name"] for d in datasets}
    external_refs = sorted({ref for d in datasets for ref in d["refs"] if ref not in dataset_names})

    email = str(user_info.get("email") or "")
    is_admin = bool(user_info.get("is_admin"))
    external: dict[str, str] = {}
    policies: dict[str, Any] = {}
    for fqn in external_refs:
        parts = fqn.split(".")
        info = await uc_client.get_table(parts[0], parts[1], parts[2])
        if not info:
            raise CatalogNotFoundError(f"Table not found: {fqn!r}")
        storage = info.get("storage_location")
        if not isinstance(storage, str) or not storage:
            raise CatalogNotFoundError(f"Table {fqn!r} has no storage_location.")
        await check_privilege(uc_client, email, is_admin, "table", fqn, SELECT)
        external[fqn] = storage
        is_owner = bool(email) and info.get("owner") == email
        if not is_admin and not is_owner:
            policy = extract_table_policy(info, principal=email)
            if policy is not None:
                policies[fqn] = policy

    client = make_principal_client(get_settings(), email)
    run_id = await asyncio.to_thread(
        run_pipeline_sync,
        factory,
        pipeline_id=pipeline_id,
        triggered_by=email or "scheduler",
        external=external,
        external_policies=policies,
        client=client,
    )
    with factory() as session:
        run = session.scalar(select(PipelineRun).where(PipelineRun.id == run_id))
        if run is not None and run.status == "failed":
            raise RuntimeError(run.error or "pipeline run failed")
