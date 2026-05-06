"""Server-side renderer for persisted notebook output frames.

The supervision view at ``/runs/{id}`` renders the ``.py`` source +
per-cell outputs as plain Jinja HTML rather than streaming WebSocket
frames into a browser editor. This module is the server-side port of
the mime-bundle priority logic that used to live in
``frontend/js/notebook/output_renderer.js``.

Each iopub message persisted by
:mod:`pointlessql.services.notebook_outputs.outputs` carries a
``msg_type`` and a ``content`` dict. :func:`render_output_frame`
inspects ``msg_type`` + ``content`` and returns a
:class:`RenderedOutput` the template can drop into the page without
further escaping — the same mime-priority order the JS renderer used
(html > svg > png > jpeg > markdown > json > plain), plus a dedicated
branch for ``stream`` / ``error``.

HTML payloads are passed through verbatim: the kernel already executes
arbitrary user code and therefore sits inside the same trust boundary
as the template. Any future sandboxing would need to land at the
kernel layer, not at the render layer.
"""

from __future__ import annotations

import base64
import html
import json
from dataclasses import dataclass
from typing import Any

from ansi2html import Ansi2HTMLConverter
from markdown_it import MarkdownIt

_MD = MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True})
_MD.enable("table")
_MD.enable("strikethrough")

_ANSI = Ansi2HTMLConverter(inline=True, scheme="ansi2html")


@dataclass(frozen=True)
class RenderedOutput:
    """One output frame ready for Jinja inclusion.

    Attributes:
        kind: Template-partial selector —
            ``"stream"`` / ``"display_data"`` / ``"error"`` /
            ``"markdown"``. Drives which
            ``partials/output_<kind>.html`` the run-detail view
            includes.
        html: Pre-rendered HTML fragment for the body of the partial.
            Always safe to emit with ``| safe`` — either escaped at
            source (``stream``, ``plain``) or produced from a trusted
            kernel payload (``html`` / ``svg``).
        variant: Optional sub-kind the template can use for CSS
            tweaks. ``"stderr"`` distinguishes red stream frames from
            default stdout; ``"html"`` / ``"svg"`` / ``"png"`` /
            ``"jpeg"`` / ``"json"`` / ``"plain"`` annotate
            display-data branches so the partial can attach a
            wrapper class.
    """

    kind: str
    html: str
    variant: str


def _coerce_str(value: Any) -> str:
    """Join nbformat-style list payloads back into a plain string.

    nbformat allows ``text/*`` and HTML mime-type values to be either
    a string or a list of strings (historical split-on-newline
    encoding). Both shapes should render identically.

    Args:
        value: A string, a list of strings, or any other JSON scalar.

    Returns:
        ``value`` joined into a single string when a list; ``value``
        itself when a string; the JSON dump when anything else.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(str(item) for item in value)
    return json.dumps(value)


def _render_ansi(text: str) -> str:
    """Convert ANSI escape sequences to inline-styled HTML spans.

    Args:
        text: Raw text potentially containing ANSI colour / style
            codes (tracebacks, coloured stream output).

    Returns:
        HTML with ANSI codes replaced by inline-styled ``<span>``
        elements. Characters that are not part of an ANSI sequence
        are HTML-escaped.
    """
    return _ANSI.convert(text, full=False)


def _render_markdown(source: str) -> str:
    """Render Markdown to HTML using markdown-it-py.

    Args:
        source: Raw Markdown source.

    Returns:
        HTML string produced by the CommonMark-plus-tables renderer.
    """
    return _MD.render(source)


def render_markdown_source(source: str) -> str:
    """Render raw Markdown to HTML (public alias of the internal helper).

    Intended for registration as a Jinja global in
    :mod:`pointlessql.api.main` so the run-detail template can render
    Markdown cells inline without the route handler having to
    pre-compute a per-cell HTML map.

    Args:
        source: Raw Markdown source.

    Returns:
        HTML string produced by the CommonMark-plus-tables renderer.
    """
    return _render_markdown(source)


def _render_stream(content: dict[str, Any]) -> RenderedOutput:
    """Render a ``stream`` iopub frame (stdout / stderr text).

    Args:
        content: The Jupyter ``content`` dict; expected keys are
            ``name`` (``"stdout"`` or ``"stderr"``) and ``text`` (the
            captured output).

    Returns:
        A :class:`RenderedOutput` with ``kind="stream"``; ``variant``
        is ``"stderr"`` when the ``name`` field says so, else
        ``"stdout"``.
    """
    name = content.get("name", "stdout")
    raw = _coerce_str(content.get("text", ""))
    # ANSI renderer already HTML-escapes plain text, so pipe through
    # it even when no escape codes are present — the common case
    # produces a trivial escape-only transform.
    body = _render_ansi(raw)
    variant = "stderr" if name == "stderr" else "stdout"
    return RenderedOutput(kind="stream", html=body, variant=variant)


def _render_error(content: dict[str, Any]) -> RenderedOutput:
    """Render an ``error`` iopub frame (exception traceback).

    Args:
        content: The Jupyter ``content`` dict; expected keys are
            ``ename`` (exception class), ``evalue`` (message), and
            ``traceback`` (list of ANSI-coloured lines).

    Returns:
        A :class:`RenderedOutput` with ``kind="error"`` and
        ``variant="traceback"``. The body is the ANSI-rendered
        traceback when present, otherwise ``ename: evalue`` escaped.
    """
    traceback = content.get("traceback") or []
    if traceback:
        joined = "\n".join(str(line) for line in traceback)
        body = _render_ansi(joined)
    else:
        ename = html.escape(str(content.get("ename", "Error")))
        evalue = html.escape(str(content.get("evalue", "")))
        body = f"{ename}: {evalue}"
    return RenderedOutput(kind="error", html=body, variant="traceback")


def _render_mime_bundle(data: dict[str, Any]) -> RenderedOutput:
    """Pick the richest representation from a mime bundle.

    Priority mirrors the historical browser renderer:
    ``text/markdown`` → ``text/html`` →
    ``image/svg+xml`` → ``image/png`` → ``image/jpeg`` →
    ``application/json`` → ``text/plain``. ``ipywidgets`` placeholder
    is rendered as a notice card — live widget rendering is not
    supported here.

    Args:
        data: The ``content.data`` dict from a ``display_data`` or
            ``execute_result`` message. May be empty.

    Returns:
        A :class:`RenderedOutput` with ``kind="display_data"`` (or
        ``kind="markdown"`` when the richest branch is
        ``text/markdown``) and a ``variant`` that identifies the
        mime branch for CSS hooks.
    """
    if not isinstance(data, dict) or not data:
        return RenderedOutput(kind="display_data", html="", variant="empty")

    if "application/vnd.jupyter.widget-view+json" in data:
        spec = data["application/vnd.jupyter.widget-view+json"] or {}
        model_id = html.escape(str(spec.get("model_id", "")))[:8] if isinstance(spec, dict) else ""
        body = (
            '<div class="pql-run-widget-placeholder">'
            f'<code class="small text-muted">widget model_id: {model_id}…</code>'
            '<p class="small mb-0 mt-1">Interactive widgets are not rendered in the '
            "run-detail view. Open the notebook in a live kernel to see updates.</p>"
            "</div>"
        )
        return RenderedOutput(kind="display_data", html=body, variant="widget")

    if "text/markdown" in data:
        source = _coerce_str(data["text/markdown"])
        return RenderedOutput(
            kind="markdown",
            html=_render_markdown(source),
            variant="markdown",
        )

    if "text/html" in data:
        return RenderedOutput(
            kind="display_data",
            html=_coerce_str(data["text/html"]),
            variant="html",
        )

    if "image/svg+xml" in data:
        return RenderedOutput(
            kind="display_data",
            html=_coerce_str(data["image/svg+xml"]),
            variant="svg",
        )

    for mime in ("image/png", "image/jpeg"):
        if mime in data:
            payload = data[mime]
            if isinstance(payload, (bytes, bytearray)):
                payload = base64.b64encode(bytes(payload)).decode("ascii")
            src = f"data:{mime};base64,{html.escape(str(payload))}"
            body = f'<img class="pql-run-output-image" src="{src}" alt="output image">'
            return RenderedOutput(
                kind="display_data",
                html=body,
                variant=mime.split("/", 1)[1],
            )

    if "application/json" in data:
        pretty = html.escape(json.dumps(data["application/json"], indent=2))
        body = f'<pre class="pql-run-output-json mb-0">{pretty}</pre>'
        return RenderedOutput(kind="display_data", html=body, variant="json")

    if "text/plain" in data:
        escaped = html.escape(_coerce_str(data["text/plain"]))
        body = f'<pre class="pql-run-output-plain mb-0">{escaped}</pre>'
        return RenderedOutput(kind="display_data", html=body, variant="plain")

    return RenderedOutput(kind="display_data", html="", variant="unknown")


def render_output_frame(msg_type: str, content: dict[str, Any]) -> RenderedOutput:
    """Dispatch a persisted iopub frame to the matching renderer.

    The :mod:`pointlessql.services.notebook_outputs.outputs` module
    persists a content dict per iopub frame; this function is the
    read-side mirror used by the run-detail template.

    Args:
        msg_type: The Jupyter ``msg_type`` string.
            ``"stream"`` / ``"execute_result"`` / ``"display_data"``
            / ``"error"`` are the persistable shapes; anything else
            returns an empty output.
        content: The ``content`` dict from the message.

    Returns:
        A :class:`RenderedOutput`. Unknown message types return an
        empty placeholder so the caller does not need to branch.
    """
    if msg_type == "stream":
        return _render_stream(content)
    if msg_type == "error":
        return _render_error(content)
    if msg_type in ("execute_result", "display_data"):
        return _render_mime_bundle(content.get("data", {}))
    return RenderedOutput(kind="display_data", html="", variant="unknown")
