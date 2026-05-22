# pyright: reportUnusedFunction=false
"""``python`` job kind — runs a coroutine declared via ``pointlessql.jobs`` entry-points."""

from __future__ import annotations

import importlib.metadata as _md
import logging
from typing import Any

from pointlessql.exceptions import ValidationError
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


async def _python_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Execute a user-authored job published via a ``pointlessql.jobs`` entry point.

    The ``entry_point`` key in ``config`` selects the entry-point name;
    the loaded object must be a coroutine with the
    :data:`JobExecutor` signature. This keeps plug-in authorship simple:
    ship a wheel that declares

    .. code-block:: toml

        [project.entry-points."pointlessql.jobs"]
        my_job = "my_pkg.jobs:run_my_job"

    and PointlesSQL discovers it without further configuration.

    Args:
        job_run_id: Current run id, forwarded to the plug-in.
        user_info: The run-as user's :class:`UserInfo`.
        config: Must carry ``entry_point``.
        uc_client: Principal-forwarded facade.

    Raises:
        ValidationError: When ``entry_point`` is missing or the entry
            point resolution fails.
    """
    entry_point_name = config.get("entry_point")
    if not entry_point_name:
        raise ValidationError("python job config is missing required key 'entry_point'")

    try:
        entries = _md.entry_points(group="pointlessql.jobs")
    except TypeError:  # pragma: no cover — very old importlib.metadata
        entries = _md.entry_points().get("pointlessql.jobs", [])  # type: ignore[attr-defined]

    matches = [ep for ep in entries if ep.name == entry_point_name]
    if not matches:
        raise ValidationError(f"python job entry point not found: {entry_point_name!r}")

    fn = matches[0].load()
    await fn(job_run_id, user_info, config, uc_client)
