"""soyuz model-version cross-link helpers (Phase 21.2).

When a Hermes-driven training run produces a registered model in
soyuz, the
:func:`link_model_version_to_run` helper writes a JSON blob into
the model-version's ``comment`` field that pins the agent-run-id +
MLflow-run-id to the catalog row. This is a *bridge* implementation:
soyuz Sprint-25 tags currently exclude ``registered_model`` from
``TagSecurableType``, so we use ``comment`` as a tag-equivalent
until tags-on-models lands. The marker prefix ``_pql_link`` makes
the future migration trivial — a one-shot script can read every
``comment`` for the prefix and re-emit as a real tag.

The CloudEvent ``pointlessql.mlflow.linked`` fires once per
successful linkage so Phase-19 audit-reviewer agents can flag
training-without-linkage anomalies.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from soyuz_catalog_client import Client
from soyuz_catalog_client.api.model_versions import (
    get_model_version_api_2_1_unity_catalog_models_full_name_versions_version_get as _get_mv,
)
from soyuz_catalog_client.api.model_versions import (
    update_model_version_api_2_1_unity_catalog_models_full_name_versions_version_patch as _update_mv,
)
from soyuz_catalog_client.models.update_model_version import UpdateModelVersion

_logger = logging.getLogger(__name__)

_MARKER_KEY = "_pql_link"

EVENT_TYPE_MLFLOW_LINKED = "pointlessql.mlflow.linked"


def _serialize_link(
    *,
    agent_run_id: str,
    mlflow_run_id: str,
    mlflow_experiment_id: str | None,
    existing_comment: str | None,
) -> str:
    """Build the new ``comment`` payload, preserving any user prose.

    The marker JSON is appended (or replaced if already present) so a
    user-written comment is never silently destroyed: the prose
    portion is kept verbatim before the marker.

    Args:
        agent_run_id: Owning PointlesSQL agent-run UUID.
        mlflow_run_id: MLflow run-id captured from
            :func:`detect_mlflow_run_id`.
        mlflow_experiment_id: Optional MLflow experiment id.
        existing_comment: Whatever currently lives in the model
            version's ``comment`` field, possibly ``None``.

    Returns:
        str: The new ``comment`` value to PATCH back.
    """
    link_blob: dict[str, Any] = {
        "agent_run_id": agent_run_id,
        "mlflow_run_id": mlflow_run_id,
        "linked_at": datetime.now(UTC).isoformat(),
    }
    if mlflow_experiment_id is not None:
        link_blob["mlflow_experiment_id"] = mlflow_experiment_id

    marker = json.dumps({_MARKER_KEY: link_blob}, sort_keys=True)
    if not existing_comment:
        return marker

    # Replace any prior marker so re-linking is idempotent.
    parts = existing_comment.split("\n\n")
    cleaned = [p for p in parts if _MARKER_KEY not in p]
    cleaned.append(marker)
    return "\n\n".join(cleaned)


def link_model_version_to_run(
    soyuz: Client,
    model_full_name: str,
    version: int,
    *,
    agent_run_id: str,
    mlflow_run_id: str,
    mlflow_experiment_id: str | None = None,
) -> None:
    """Patch a soyuz model-version's ``comment`` with the linkage marker.

    Idempotent — re-linking replaces any prior ``_pql_link`` marker
    in the comment field while preserving user-written prose.

    Args:
        soyuz: Configured soyuz-catalog client.
        model_full_name: ``catalog.schema.model`` of the registered
            model.
        version: Integer version number.
        agent_run_id: Owning PointlesSQL agent-run UUID.
        mlflow_run_id: MLflow run-id active when the version was
            created.
        mlflow_experiment_id: Optional MLflow experiment id.
    """
    # Read current comment so we can preserve any user prose around
    # the marker.  A 404 here is a real error — the caller asked us to
    # link a version that does not exist in soyuz.
    current = _get_mv.sync(
        client=soyuz,
        full_name=model_full_name,
        version=version,
    )
    existing_comment: str | None = None
    if current is not None and getattr(current, "comment", None):
        existing_comment = current.comment  # type: ignore[assignment]

    new_comment = _serialize_link(
        agent_run_id=agent_run_id,
        mlflow_run_id=mlflow_run_id,
        mlflow_experiment_id=mlflow_experiment_id,
        existing_comment=existing_comment,
    )

    _update_mv.sync(
        client=soyuz,
        full_name=model_full_name,
        version=version,
        body=UpdateModelVersion(comment=new_comment),
    )

    _logger.info(
        "Linked model-version %s/v%d to agent_run %s + mlflow_run %s",
        model_full_name,
        version,
        agent_run_id,
        mlflow_run_id,
    )


def parse_link_marker(comment: str | None) -> dict[str, Any] | None:
    """Extract the ``_pql_link`` marker from a comment, if present.

    Counterpart to :func:`_serialize_link` for the read-side
    aggregator endpoint (Phase 21.2 ``/api/runs/{id}/ml-context``).

    Args:
        comment: A model-version ``comment`` value, possibly ``None``.

    Returns:
        The marker payload, or ``None`` if the comment doesn't carry
        a marker.
    """
    if not comment:
        return None
    for chunk in comment.split("\n\n"):
        chunk = chunk.strip()
        if _MARKER_KEY not in chunk:
            continue
        try:
            parsed = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        marker = parsed.get(_MARKER_KEY)
        if isinstance(marker, dict):
            return marker
    return None


def build_mlflow_linked_event(
    *,
    agent_run_id: str,
    mlflow_run_id: str,
    model_full_name: str,
    model_version: int,
    mlflow_experiment_id: str | None = None,
) -> dict[str, Any]:
    """Build the CloudEvents 1.0 envelope for ``pointlessql.mlflow.linked``.

    Phase 21.2 emits this event after every successful linkage so
    the Phase-19 audit-reviewer agents (and external webhook
    consumers) can correlate training to catalog state.

    Args:
        agent_run_id: Owning PointlesSQL agent-run UUID.
        mlflow_run_id: MLflow run-id.
        model_full_name: ``catalog.schema.model`` of the linked
            registered model.
        model_version: Integer version number.
        mlflow_experiment_id: Optional MLflow experiment id.

    Returns:
        A CloudEvents 1.0 envelope dict ready for webhook dispatch.
    """
    data: dict[str, Any] = {
        "agent_run_id": agent_run_id,
        "mlflow_run_id": mlflow_run_id,
        "model_full_name": model_full_name,
        "model_version": model_version,
    }
    if mlflow_experiment_id is not None:
        data["mlflow_experiment_id"] = mlflow_experiment_id

    return {
        "specversion": "1.0",
        "id": uuid.uuid4().hex,
        "source": f"/pointlessql/agent_runs/{agent_run_id}",
        "type": EVENT_TYPE_MLFLOW_LINKED,
        "time": datetime.now(UTC).isoformat(),
        "datacontenttype": "application/json",
        "subject": f"{model_full_name}@v{model_version}",
        "data": data,
    }
