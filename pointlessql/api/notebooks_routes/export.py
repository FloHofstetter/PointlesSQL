"""Notebook export routes.

Two endpoints surface the same notebook → static-document pipeline:

* ``GET /api/notebooks/export.html?path=…`` — returns
  ``text/html; charset=utf-8`` with the rendered notebook embedded.
* ``GET /api/notebooks/export.pdf?path=…`` — returns
  ``application/pdf`` when WeasyPrint is available; falls back to the
  HTML body with a ``Content-Type: text/html`` header so the browser
  can produce the PDF via its own *Save as PDF* flow.

Both routes share the same loader: parse the ``.py`` via the standard
notebook-doc service, read the persisted ``notebook_outputs`` rows for
the path, hand the pair to
:mod:`pointlessql.services.notebook.export`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from pointlessql.api.dependencies import require_user
from pointlessql.config import Settings
from pointlessql.services.notebook import _doc as notebook_doc_service
from pointlessql.services.notebook import export as notebook_export_service
from pointlessql.services.notebook import outputs as notebook_outputs_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


def _build_payload(
    request: Request, path: str
) -> tuple[str, list[dict[str, object]], list[dict[str, object]]]:
    """Load and prepare the title, cells, and outputs for one notebook.

    Args:
        request: Incoming request — for settings + session factory.
        path: Relative notebook path.

    Returns:
        ``(title, cells, outputs)``.
    """
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(notebooks_dir, path, must_exist=True)
    relative = str(absolute.relative_to(notebooks_dir))
    document = notebook_doc_service.load_document(absolute, relative)
    outputs = notebook_outputs_service.load_outputs_for_path(
        request.app.state.session_factory, relative
    )
    cells: list[dict[str, object]] = [
        {
            "content_hash": cell.content_hash,
            "cell_type": cell.cell_type,
            "source": cell.source,
        }
        for cell in document.cells
    ]
    title = relative.removesuffix(".py") or relative
    return title, cells, outputs


@router.get("/api/notebooks/export.html")
async def api_export_notebook_html(
    request: Request,
    path: str = Query(..., min_length=1),
) -> Response:
    """Return a self-contained HTML snapshot of the notebook.

    Args:
        request: Incoming request; any authenticated user.
        path: Relative notebook path under ``notebooks_dir``.

    Returns:
        ``text/html`` document with cells + outputs inlined.
    """
    require_user(request)
    title, cells, outputs = _build_payload(request, path)
    body = notebook_export_service.render_notebook_html(title=title, cells=cells, outputs=outputs)
    filename = title.replace("/", "_") + ".html"
    return Response(
        content=body,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/api/notebooks/export.pdf")
async def api_export_notebook_pdf(
    request: Request,
    path: str = Query(..., min_length=1),
) -> Response:
    """Return the notebook as PDF (WeasyPrint) or HTML fallback.

    Args:
        request: Incoming request; any authenticated user.
        path: Relative notebook path under ``notebooks_dir``.

    Returns:
        ``application/pdf`` bytes when WeasyPrint is available on the
        host; otherwise the HTML body so the browser's *Save as PDF*
        flow can finish the job.
    """
    require_user(request)
    title, cells, outputs = _build_payload(request, path)
    pdf_bytes = notebook_export_service.render_notebook_pdf(
        title=title, cells=cells, outputs=outputs
    )
    safe_title = title.replace("/", "_")
    if pdf_bytes is not None:
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (f'attachment; filename="{safe_title}.pdf"'),
            },
        )
    body = notebook_export_service.render_notebook_html(title=title, cells=cells, outputs=outputs)
    return Response(
        content=body,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": (f'inline; filename="{safe_title}.html"'),
            "X-PointlesSQL-Export-Fallback": "weasyprint-unavailable",
        },
    )
