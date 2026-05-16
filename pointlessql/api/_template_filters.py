"""Jinja2 filters + globals registered onto the shared templates instance.

Phase 86 B4 lifted these out of ``main.py`` so the entrypoint shrinks
to its proper concern (app build + router wiring) and so the filter
behaviour gets its own unit-test target without paying the cost of
importing the whole FastAPI app.

Every filter is pure (input → string), so swapping one out is a
single-line edit here.  Renderers are wired via
:func:`register_template_filters` which mutates the
:class:`Jinja2Templates` env in place — same one-shot install order
the old monolith used.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt

import pointlessql
from pointlessql.web import get_help as _get_help
from pointlessql.web import status_class as _status_class


def _format_epoch_ms(value: Any) -> str:
    """Format Unity Catalog epoch-millisecond timestamps as a local datetime."""
    if value is None:
        return "—"
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError):
        return str(value)


def _format_uuid(value: Any) -> str:
    """Normalise UUID strings to canonical hyphenated form.

    PointlesSQL's API mixes hyphenated and packed UUID formats depending
    on the source row (some seeds, some FK inserts, some agent-emitted
    payloads). Templates use this filter so the user always sees the
    same shape regardless of source.
    """
    if not value:
        return ""
    s = str(value).replace("-", "")
    if len(s) != 32:
        return str(value)
    return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:32]}"


def _format_hash(value: Any, sentinel_label: str = "(no source captured)") -> str:
    """Hide the all-zeros SHA sentinel as a human-readable label.

    Run-source capture writes ``"0" * 64`` when no bytes were captured
    (e.g. agent-only flows that never hit ``capture_run_source``). The
    raw zero-hash leaks an implementation detail; this filter swaps it
    for a readable empty-state. Real hashes pass through unchanged.
    """
    if not value:
        return ""
    s = str(value)
    if s and all(c == "0" for c in s):
        return sentinel_label
    return s


_MARKDOWN_RENDERER = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable(
    ["table"]
)


def _render_markdown(value: Any) -> str:
    """Render saved-query Markdown descriptions to an HTML fragment.

    Uses markdown-it-py in CommonMark mode with ``html: false`` so any
    raw ``<script>`` / ``<iframe>`` in user input is escaped at parse
    time — descriptions are user-authored, so ``|safe`` would expose
    us to script injection without this guard.
    """
    if not value:
        return ""
    return _MARKDOWN_RENDERER.render(str(value))


def _paginate_url(base_url: str, query_params: Any, offset: int) -> str:
    """Return ``base_url`` plus ``query_params`` with ``offset`` overridden.

    Used by ``frontend/templates/_macros/pagination.html`` to build
    page-link hrefs without losing in-flight filter chips.

    Args:
        base_url: Path the page is served from (e.g. ``request.url.path``).
        query_params: Starlette ``QueryParams`` (or any iterable of
            ``(key, value)``).  Pre-existing ``offset`` keys are dropped.
        offset: New offset value.

    Returns:
        ``"path?offset=N&filter=foo"`` style URL.
    """
    from urllib.parse import urlencode

    items: list[tuple[str, str]] = []
    if query_params is not None:
        if hasattr(query_params, "multi_items"):
            iterator = list(query_params.multi_items())
        else:
            iterator = list(query_params)
        for key, val in iterator:
            if key == "offset":
                continue
            items.append((str(key), str(val)))
    items.append(("offset", str(offset)))
    return f"{base_url}?{urlencode(items)}"


def register_template_filters(templates: Jinja2Templates) -> None:
    """Attach every Jinja filter + global PointlesSQL templates need.

    Called once at app build time from
    :mod:`pointlessql.api.main` before any TemplateResponse is issued.
    Idempotent — reassigning a filter on the same env just overwrites
    the previous entry, which is what we want for the test harness's
    repeated app fixtures.

    Args:
        templates: The shared :class:`Jinja2Templates` instance.
    """
    templates.env.filters["epoch_ms"] = _format_epoch_ms
    templates.env.filters["format_uuid"] = _format_uuid
    templates.env.filters["format_hash"] = _format_hash
    templates.env.filters["render_markdown"] = _render_markdown

    # contextual help-popover registry (see ``pointlessql/web/
    # help.py``).  Templates resolve slugs via ``{{ help('runs.what-is-a-
    # run') }}`` and render through ``_macros/help_icon.html``.
    templates.env.globals["help"] = _get_help  # pyright: ignore[reportArgumentType]

    # Asset cache-bust token.  Bumps automatically with every release;
    # templates use ``?v={{ asset_version }}`` instead of hand-edited
    # per-edit strings.
    templates.env.globals["asset_version"] = pointlessql.__version__  # pyright: ignore[reportArgumentType]

    # Centralised status → Bootstrap badge class mapping.  Templates
    # call ``{{ status_class(run.status) }}`` instead of hand-rolling
    # {% if status == 'succeeded' %}bg-success{% elif … %} ladders.
    templates.env.globals["status_class"] = _status_class  # pyright: ignore[reportArgumentType]

    templates.env.globals["paginate_url"] = _paginate_url  # pyright: ignore[reportArgumentType]


__all__ = ["register_template_filters"]
