"""HTTP routes for the visual data-product canvas editor.

Thin adapters over the ``pointlessql.services.dp_canvas`` surface, split
by concern across sibling modules and re-assembled here into one router:

* ``_crud``        — load / save / list / fetch-version of the document.
* ``_validate``    — read-only validate / ghost-diff / preview.
* ``_versions``    — pin / unpin a production version, diff two versions.
* ``_materialize`` — compile + execute the canvas to Delta + UC.
* ``_picker``      — the DataProduct compound-block dropdown feed.

Shared request/response models live in ``_schemas`` and the cross-handler
helpers (auth, DP resolution, the soyuz client, the document pre-passes)
in ``_helpers``.

Path scheme uses the integer ``data_products.id`` rather than
``{catalog}/{schema}`` because the canvas storage layer keys on that
id; the visual editor is reached via the standalone editor page rather
than the existing tab strip, so the URL shape never collides with the
canonical DP browsing URLs.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.data_products_routes.canvas import (
    _crud,
    _materialize,
    _picker,
    _validate,
    _versions,
)
from pointlessql.api.data_products_routes.canvas._schemas import (
    CanvasDiffResponse,
    CanvasGhostDiffRequest,
    CanvasGhostDiffResponse,
    CanvasLoadResponse,
    CanvasLoadVersionResponse,
    CanvasMaterializeRequest,
    CanvasMaterializeResponse,
    CanvasMaterializeSink,
    CanvasPreviewRequest,
    CanvasPreviewResponse,
    CanvasSaveRequest,
    CanvasSaveResponse,
    CanvasValidateRequest,
    CanvasValidateResponse,
    CanvasVersionEntry,
    CanvasVersionsResponse,
    DataProductPickerEntry,
    DataProductPickerResponse,
)

router = APIRouter()
router.include_router(_crud.router)
router.include_router(_validate.router)
router.include_router(_versions.router)
router.include_router(_materialize.router)
router.include_router(_picker.router)

__all__ = [
    "CanvasDiffResponse",
    "CanvasGhostDiffRequest",
    "CanvasGhostDiffResponse",
    "CanvasLoadResponse",
    "CanvasLoadVersionResponse",
    "CanvasMaterializeRequest",
    "CanvasMaterializeResponse",
    "CanvasMaterializeSink",
    "CanvasPreviewRequest",
    "CanvasPreviewResponse",
    "CanvasSaveRequest",
    "CanvasSaveResponse",
    "CanvasValidateRequest",
    "CanvasValidateResponse",
    "CanvasVersionEntry",
    "CanvasVersionsResponse",
    "DataProductPickerEntry",
    "DataProductPickerResponse",
    "router",
]
