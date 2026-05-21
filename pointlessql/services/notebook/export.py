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
<html lang="en" data-pql-theme="auto">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  :root {{
    /* PointlesSQL brand palette — light defaults. */
    --pql-bg:            #ffffff;
    --pql-bg-elev:       #f8f9fa;
    --pql-bg-tertiary:   #f1f3f5;
    --pql-text:          #1f2328;
    --pql-text-muted:    #6e7781;
    --pql-border:        #d0d7de;
    --pql-accent:        #76b900;
    --pql-accent-bg:     rgba(118, 185, 0, 0.12);
    --pql-code-fg:       #0969da;
    --pql-sql-fg:        #8250df;
    --pql-stderr-bg:     #fff8c5;
    --pql-stderr-bdr:    #d4a72c;
    --pql-tb-bg:         #ffebe9;
    --pql-tb-bdr:        #ff8182;
  }}
  @media (prefers-color-scheme: dark) {{
    :root[data-pql-theme="auto"] {{
      --pql-bg:          #0d1117;
      --pql-bg-elev:     #161b22;
      --pql-bg-tertiary: #1c2128;
      --pql-text:        #e6edf3;
      --pql-text-muted:  #8b949e;
      --pql-border:      #30363d;
      --pql-accent:      #76b900;
      --pql-accent-bg:   rgba(118, 185, 0, 0.18);
      --pql-code-fg:     #7fb1ff;
      --pql-sql-fg:      #c084fc;
      --pql-stderr-bg:   rgba(255, 192, 77, 0.15);
      --pql-stderr-bdr:  rgba(255, 192, 77, 0.45);
      --pql-tb-bg:       rgba(255, 122, 136, 0.15);
      --pql-tb-bdr:      rgba(255, 122, 136, 0.45);
    }}
  }}
  :root[data-pql-theme="dark"] {{
    --pql-bg:          #0d1117;
    --pql-bg-elev:     #161b22;
    --pql-bg-tertiary: #1c2128;
    --pql-text:        #e6edf3;
    --pql-text-muted:  #8b949e;
    --pql-border:      #30363d;
    --pql-accent:      #76b900;
    --pql-accent-bg:   rgba(118, 185, 0, 0.18);
    --pql-code-fg:     #7fb1ff;
    --pql-sql-fg:      #c084fc;
    --pql-stderr-bg:   rgba(255, 192, 77, 0.15);
    --pql-stderr-bdr:  rgba(255, 192, 77, 0.45);
    --pql-tb-bg:       rgba(255, 122, 136, 0.15);
    --pql-tb-bdr:      rgba(255, 122, 136, 0.45);
  }}
  html, body {{
    background: var(--pql-bg);
    color: var(--pql-text);
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    line-height: 1.5;
    margin: 0;
    padding: 2rem 3rem;
    max-width: 960px;
  }}
  .pql-export__topbar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: -1rem -1rem 1.25rem -1rem;
    padding: 0.4rem 0.85rem;
    background: var(--pql-bg-elev);
    border: 1px solid var(--pql-border);
    border-radius: 0.5rem;
    font-size: 0.85rem;
  }}
  .pql-export__brand {{
    color: var(--pql-accent);
    font-weight: 600;
    letter-spacing: 0.02em;
  }}
  .pql-export__theme-toggle {{
    background: var(--pql-bg-tertiary);
    color: var(--pql-text);
    border: 1px solid var(--pql-border);
    border-radius: 0.3rem;
    padding: 0.15rem 0.55rem;
    font-size: 0.78rem;
    cursor: pointer;
    font-family: inherit;
  }}
  .pql-export__theme-toggle:hover {{ background: var(--pql-accent-bg); }}
  h1.pql-export__title {{
    font-size: 1.75rem;
    margin: 0 0 0.25rem 0;
    color: var(--pql-text);
  }}
  .pql-export__meta {{
    color: var(--pql-text-muted);
    font-size: 0.9rem;
    margin-bottom: 2rem;
  }}
  .pql-cell {{
    border-left: 3px solid var(--pql-border);
    padding: 0.5rem 0.75rem 0.5rem 1rem;
    margin: 0 0 1.25rem 0;
    page-break-inside: avoid;
  }}
  .pql-cell--code {{ border-left-color: var(--pql-code-fg); }}
  .pql-cell--sql {{ border-left-color: var(--pql-sql-fg); }}
  .pql-cell--markdown {{ border-left: none; padding-left: 0; }}
  pre {{
    background: var(--pql-bg-elev);
    border: 1px solid var(--pql-border);
    border-radius: 6px;
    padding: 0.75rem;
    overflow: auto;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    font-size: 0.875rem;
    color: var(--pql-text);
  }}
  code {{ color: var(--pql-text); }}
  a {{ color: var(--pql-accent); }}
  .pql-output {{
    margin-top: 0.5rem;
    padding: 0.5rem 0;
  }}
  .pql-output--stream-stderr pre {{
    background: var(--pql-stderr-bg);
    border-color: var(--pql-stderr-bdr);
  }}
  .pql-output--traceback pre {{
    background: var(--pql-tb-bg);
    border-color: var(--pql-tb-bdr);
  }}
  table {{
    border-collapse: collapse;
    margin: 0.5rem 0;
    background: var(--pql-bg);
  }}
  th, td {{
    border: 1px solid var(--pql-border);
    padding: 0.25rem 0.5rem;
    font-size: 0.875rem;
    color: var(--pql-text);
  }}
  th {{ background: var(--pql-bg-tertiary); }}
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
    body {{ padding: 0; max-width: none; background: #ffffff; color: #1f2328; }}
    .pql-export__topbar, .pql-export__theme-toggle {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="pql-export__topbar">
  <span class="pql-export__brand">PointlesSQL · shared notebook</span>
  <button type="button" class="pql-export__theme-toggle"
          id="pql-export-theme-toggle"
          aria-label="Toggle dark / light theme">Theme: auto</button>
</div>
<h1 class="pql-export__title">{title}</h1>
<div class="pql-export__meta">Exported {exported_at} · {cell_count} cells</div>
<script>
(function () {{
  var root = document.documentElement;
  var btn  = document.getElementById('pql-export-theme-toggle');
  if (!btn) return;
  var stored = null;
  try {{ stored = localStorage.getItem('pql-export-theme'); }} catch (_) {{}}
  if (stored === 'dark' || stored === 'light') root.setAttribute('data-pql-theme', stored);
  var labelFor = function (v) {{ return 'Theme: ' + v; }};
  btn.textContent = labelFor(root.getAttribute('data-pql-theme') || 'auto');
  btn.addEventListener('click', function () {{
   var cur = root.getAttribute('data-pql-theme') || 'auto';
   var next = cur === 'auto' ? 'light' : cur === 'light' ? 'dark' : 'auto';
   root.setAttribute('data-pql-theme', next);
   try {{ localStorage.setItem('pql-export-theme', next); }} catch (_) {{}}
   btn.textContent = labelFor(next);
  }});
}})();
</script>
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


def render_notebook_body_html(
    *,
    cells: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
) -> str:
    """Render only the inner cells + outputs as an HTML fragment.

    Returns the same per-cell markup as :func:`render_notebook_html`
    but without the surrounding ``<!DOCTYPE>`` / ``<head>`` / inline
    ``<style>`` envelope, so it can be slotted into a Jinja template
    that brings its own theme + chrome (the public share viewer does
    this so it can reuse the main app's base.css palette instead of
    duplicating an offline-friendly inline copy).

    Args:
        cells: One dict per cell — same shape as
            :func:`render_notebook_html`.
        outputs: ``notebook_outputs`` rows.

    Returns:
        HTML fragment (no top-level wrapper).
    """
    pieces: list[str] = []
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
    return "\n".join(pieces)


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
    pieces.append(
        render_notebook_body_html(cells=cells, outputs=outputs)
    )
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
        # bare-broad-ok: weasyprint is optional; callers fall back to HTML render
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


__all__ = [
    "render_notebook_body_html",
    "render_notebook_html",
    "render_notebook_pdf",
]
