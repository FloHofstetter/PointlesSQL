"""Static notebook → HTML (and PDF-via-print) export (Phase 98.D).

The DBX-parity "Download as HTML / PDF" surface produces a single
self-contained HTML document from a ``.py`` notebook plus its
persisted outputs.  The HTML carries inline CSS and an ``@page``
print stylesheet so the browser's *Print → Save as PDF* path works
without a second round-trip; an optional WeasyPrint server-side
render produces a real ``application/pdf`` response when WeasyPrint
is installed.

Design notes:

* No new tables.  The export joins the existing on-disk ``.py``
  (via :mod:`pointlessql.services.notebook._doc`) with the
  ``notebook_outputs`` rows already persisted by the WS pump.
* Output mime-bundle rendering goes through
  :func:`pointlessql.services.output_rendering.render_output_frame`
  so the run-detail / job-detail / inline-editor surfaces all share
  the same HTML.
* Latest kernel session wins when a cell has output frames from
  several sessions — matches the editor mount path
  (:func:`pointlessql.services.notebook.outputs.outputs.load_outputs_for_path`
  returns every row; we filter to the most recent per cell here).
* PDF rendering uses WeasyPrint when importable and falls back to
  the print-stylesheet HTML when WeasyPrint is not on PYTHONPATH —
  the project does not pin WeasyPrint as a hard dep because the
  underlying Cairo/Pango stack is awkward on minimal hosts.
"""

from __future__ import annotations

import html as _html
import io
import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from pointlessql.services import output_rendering as render_service

logger = logging.getLogger(__name__)


_HTML_HEADER = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    color: #1f2328;
    line-height: 1.5;
    margin: 0;
    padding: 2rem 3rem;
    max-width: 960px;
  }}
  h1.pql-export__title {{
    font-size: 1.75rem;
    margin: 0 0 0.25rem 0;
  }}
  .pql-export__meta {{
    color: #6e7781;
    font-size: 0.9rem;
    margin-bottom: 2rem;
  }}
  .pql-cell {{
    border-left: 3px solid #d0d7de;
    padding: 0.5rem 0.75rem 0.5rem 1rem;
    margin: 0 0 1.25rem 0;
    page-break-inside: avoid;
  }}
  .pql-cell--code {{ border-left-color: #0969da; }}
  .pql-cell--sql {{ border-left-color: #8250df; }}
  .pql-cell--markdown {{ border-left: none; padding-left: 0; }}
  pre {{
    background: #f6f8fa;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 0.75rem;
    overflow: auto;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    font-size: 0.875rem;
  }}
  .pql-output {{
    margin-top: 0.5rem;
    padding: 0.5rem 0;
  }}
  .pql-output--stream-stderr pre {{
    background: #fff8c5;
    border-color: #d4a72c;
  }}
  .pql-output--traceback pre {{
    background: #ffebe9;
    border-color: #ff8182;
  }}
  table {{
    border-collapse: collapse;
    margin: 0.5rem 0;
  }}
  th, td {{
    border: 1px solid #d0d7de;
    padding: 0.25rem 0.5rem;
    font-size: 0.875rem;
  }}
  @page {{
    margin: 1.5cm;
    @top-right {{
      content: "{title}";
      color: #6e7781;
      font-size: 9pt;
    }}
    @bottom-right {{
      content: counter(page) " / " counter(pages);
      color: #6e7781;
      font-size: 9pt;
    }}
  }}
  @media print {{
    body {{ padding: 0; max-width: none; }}
  }}
</style>
</head>
<body>
<h1 class="pql-export__title">{title}</h1>
<div class="pql-export__meta">Exported {exported_at} · {cell_count} cells</div>
"""

_HTML_FOOTER = "</body>\n</html>\n"


def _latest_outputs_for(
    outputs: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group output frames by ``content_hash`` keeping only the latest session.

    Args:
        outputs: Rows from :func:`load_outputs_for_path`; each one has
            ``content_hash`` / ``kernel_session_id`` / ``output_index``
            / ``msg_type`` / ``content`` / ``metadata`` / ``created_at``.

    Returns:
        Mapping ``content_hash → [frame, …]`` where frames are
        ordered by ``output_index`` and only the most-recent
        ``kernel_session_id`` per cell is included.
    """
    by_cell: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    latest_session: dict[str, tuple[str, str]] = {}
    for row in outputs:
        cell = row["content_hash"]
        sess = row["kernel_session_id"]
        by_cell[cell][sess].append(row)
        cur = latest_session.get(cell)
        ts = row.get("created_at") or ""
        if cur is None or ts > cur[1]:
            latest_session[cell] = (sess, ts)
    out: dict[str, list[dict[str, Any]]] = {}
    for cell, sessions in by_cell.items():
        sess, _ts = latest_session[cell]
        frames = sorted(sessions[sess], key=lambda r: r["output_index"])
        out[cell] = frames
    return out


def _render_cell_source(source: str) -> str:
    """Render a code/SQL cell's source as a syntax-naïve ``<pre>`` block."""
    escaped = _html.escape(source.rstrip("\n"))
    return f"<pre><code>{escaped}</code></pre>"


def _render_output_frame(frame: dict[str, Any]) -> str:
    """Render one persisted output frame to inline HTML.

    Delegates to :func:`render_output_frame`; wraps its
    :class:`RenderedOutput` payload in a per-kind ``<div>`` so the
    export's CSS can target stderr / traceback styling.

    Args:
        frame: Row from :func:`load_outputs_for_path`.

    Returns:
        HTML snippet.
    """
    msg_type = frame.get("msg_type") or ""
    content = frame.get("content") or {}
    if not isinstance(content, dict):
        return ""
    rendered = render_service.render_output_frame(msg_type, content)
    kind_class = f"pql-output pql-output--{rendered.kind}"
    if rendered.variant:
        kind_class += f"-{rendered.variant}"
    body = rendered.html or ""
    if rendered.kind == "stream":
        body = f"<pre>{body}</pre>"
    return f'<div class="{kind_class}">{body}</div>'


def render_notebook_html(
    *,
    title: str,
    cells: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    exported_at: datetime | None = None,
) -> str:
    """Render a complete notebook + outputs as a self-contained HTML doc.

    Args:
        title: Page ``<title>`` + ``<h1>`` — typically the notebook
            relative path with the ``.py`` suffix stripped.
        cells: One dict per cell with keys ``content_hash`` /
            ``cell_type`` / ``source``.  Markdown cells get rendered
            via the existing CommonMark pipeline; code / SQL cells
            land as ``<pre><code>`` blocks.
        outputs: ``notebook_outputs`` rows; filtered down to the most
            recent kernel session per cell before rendering.
        exported_at: Wall-clock the export was generated; ``None``
            defaults to ``datetime.utcnow()``.

    Returns:
        A self-contained ``<!DOCTYPE html>`` string.  No external
        assets — every style is inline so the file opens without
        network access (DBX parity for "Download as HTML").
    """
    stamp = (exported_at or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC")
    pieces: list[str] = [
        _HTML_HEADER.format(
            title=_html.escape(title),
            exported_at=_html.escape(stamp),
            cell_count=len(cells),
        )
    ]
    by_cell = _latest_outputs_for(outputs)
    for cell in cells:
        cell_type = cell.get("cell_type") or "code"
        content_hash = cell.get("content_hash") or ""
        source = cell.get("source") or ""
        wrap_class = f"pql-cell pql-cell--{cell_type}"
        pieces.append(f'<div class="{wrap_class}">')
        if cell_type == "markdown":
            pieces.append(render_service.render_markdown_source(source))
        else:
            pieces.append(_render_cell_source(source))
        for frame in by_cell.get(content_hash, []):
            pieces.append(_render_output_frame(frame))
        pieces.append("</div>")
    pieces.append(_HTML_FOOTER)
    return "\n".join(pieces)


def render_notebook_pdf(
    *,
    title: str,
    cells: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    exported_at: datetime | None = None,
) -> bytes | None:
    """Render the same notebook as a PDF if WeasyPrint is importable.

    Args:
        title: Same as :func:`render_notebook_html`.
        cells: Same as :func:`render_notebook_html`.
        outputs: Same as :func:`render_notebook_html`.
        exported_at: Same as :func:`render_notebook_html`.

    Returns:
        PDF bytes when WeasyPrint is available; ``None`` when the
        WeasyPrint import fails.  Callers fall back to serving the
        HTML doc with the print stylesheet and let the browser
        produce the PDF client-side.
    """
    try:
        from weasyprint import HTML  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 — optional dep
        return None
    body = render_notebook_html(
        title=title,
        cells=cells,
        outputs=outputs,
        exported_at=exported_at,
    )
    buf = io.BytesIO()
    HTML(string=body).write_pdf(buf)  # type: ignore[reportUnknownMemberType]
    return buf.getvalue()


__all__ = ["render_notebook_html", "render_notebook_pdf"]
