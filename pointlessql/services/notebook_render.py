"""Render executed Papermill output notebooks as inline HTML.

Sprint 24 lands executed notebooks at ``{notebooks_dir}/runs/{job_run_id}.ipynb``.
Sprint 26 surfaces those outputs on the job-detail page through an
iframe pointed at :func:`render_run_notebook`. nbconvert's ``lab``
template produces near-identical styling to the JupyterLab alternative
view, so the toggle between ``Rendered`` and ``JupyterLab`` modes is
purely a question of who serves the bytes.

Sprint 28 adds an ``exclude_input=True`` variant for dashboards: the
same executed notebook rendered with code cells hidden so consumers
see only outputs. The two variants cache to sibling sidecars
(``{run_id}.html`` and ``{run_id}.dashboard.html``) so switching modes
never evicts the other's cache.

The first request for a given ``run_id`` writes a ``.html`` sidecar
next to the ``.ipynb``; subsequent requests read the sidecar directly.
An executed notebook is immutable once the Papermill executor has
closed it, so invalidation by mtime is not needed — the sidecar's
existence is enough.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from pointlessql.exceptions import CatalogNotFoundError, EngineError

logger = logging.getLogger(__name__)


def render_run_notebook(
    runs_dir: Path, run_id: int, *, exclude_input: bool = False
) -> str:
    """Return rendered HTML for ``runs/{run_id}.ipynb``, caching a sidecar.

    The sidecar is written atomically via a ``.tmp`` rename so concurrent
    requests for the same run can't observe a half-written file. When
    ``exclude_input`` is true, the sidecar path becomes
    ``{run_id}.dashboard.html`` so the dashboard-mode and default-mode
    caches coexist.

    Args:
        runs_dir: Directory containing ``{run_id}.ipynb`` output files.
            Typically ``settings.notebooks_dir / "runs"``.
        run_id: The :class:`~pointlessql.models.JobRun` id whose output
            notebook should be rendered.
        exclude_input: When true, render with ``exclude_input=True`` so
            code cells are hidden. Used by the Sprint 28 dashboards
            surface to publish output-only views.

    Returns:
        The nbconvert-rendered HTML body as a string.

    Raises:
        CatalogNotFoundError: When ``runs/{run_id}.ipynb`` does not
            exist. Surfaces as a 404 via the centralized error handler.
        EngineError: When nbconvert raises while rendering the notebook.
    """
    ipynb_path = runs_dir / f"{run_id}.ipynb"
    if not ipynb_path.is_file():
        raise CatalogNotFoundError(f"Run {run_id} output notebook not found")

    suffix = "dashboard.html" if exclude_input else "html"
    html_path = runs_dir / f"{run_id}.{suffix}"
    if html_path.is_file():
        return html_path.read_text(encoding="utf-8")

    # Lazy import: nbconvert pulls in jinja2 template discovery which
    # is non-trivial. Most requests hit the sidecar above.
    from nbconvert import HTMLExporter  # type: ignore[import-untyped]

    try:
        exporter = HTMLExporter(
            template_name="lab", exclude_input=exclude_input
        )
        body, _resources = exporter.from_filename(str(ipynb_path))  # type: ignore[no-untyped-call]
    except Exception as exc:
        logger.exception("nbconvert failed rendering run %d", run_id)
        raise EngineError(f"Failed to render run {run_id} notebook: {exc}") from exc

    body_str: str = body if isinstance(body, str) else str(body)
    tmp_path = html_path.parent / f"{html_path.name}.tmp"
    tmp_path.write_text(body_str, encoding="utf-8")
    os.replace(tmp_path, html_path)
    return body_str


__all__ = ["render_run_notebook"]
