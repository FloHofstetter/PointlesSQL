"""Public read-only ``/api/conventions`` route.

Lets the ``hermes-plugin-pointlessql`` ``pql_conventions`` tool drop
PointlesSQL's Medallion contract straight into an LLM's system
prompt without bundling a copy.  The endpoint serves whatever
:func:`pointlessql.conventions.load_conventions` resolves —
defaults plus any ``pointlessql.yaml`` overrides — alongside an
excerpt of ``docs/data-layers.md`` so the agent has both the
machine-readable shape and the prose contract.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request

from pointlessql.conventions import load_conventions

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conventions"])


_DOCS_PATH = Path(__file__).resolve().parents[2] / "docs" / "data-layers.md"


def _load_doc_excerpt() -> str:
    """Return the prose contract for the ``pointlessql.yaml`` shape.

    Reads ``docs/data-layers.md`` once per call (file is small;
    the LRU is the OS page cache). Missing file collapses to an
    empty string so the route never 500s when running from a
    wheel install that did not ship the docs directory.

    Returns:
        Markdown text with the prose layer contract, or ``""``
        when the file is unavailable in this deployment.
    """
    try:
        return _DOCS_PATH.read_text(encoding="utf-8")
    except OSError:
        logger.debug("data-layers.md not present at %s", _DOCS_PATH)
        return ""


@router.get("/api/conventions")
async def api_conventions(request: Request) -> dict[str, object]:
    """Return the resolved Medallion conventions + prose contract.

    Args:
        request: Incoming FastAPI request. ``app.state.settings``
            is honoured so a ``POINTLESSQL_CONVENTIONS_PATH``
            override flows through.

    Returns:
        ``{"yaml": <ConventionsConfig dump>, "doc_markdown": ...}``.
        ``yaml`` is the pydantic ``model_dump()`` of the merged
        config; ``doc_markdown`` is the verbatim text of
        ``docs/data-layers.md`` so the LLM gets the prose
        explanation in the same response.
    """
    settings = getattr(request.app.state, "settings", None)
    config = load_conventions(settings=settings)
    return {
        "yaml": config.model_dump(mode="json"),
        "doc_markdown": _load_doc_excerpt(),
    }
