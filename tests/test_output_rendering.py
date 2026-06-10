"""Unit tests for the server-side notebook output-frame renderer.

Covers the mime-bundle priority order, the stream / error branches, and
the list-vs-string payload coercion that the run-detail view relies on.
The module is pure (no I/O, no fixtures), so every branch is exercised
directly through the public :func:`render_output_frame` dispatch plus the
two public helpers.
"""

from __future__ import annotations

from pointlessql.services.output_rendering import (
    RenderedOutput,
    render_markdown_source,
    render_output_frame,
)


def _display(data: dict[str, object]) -> RenderedOutput:
    """Render a ``display_data`` frame carrying ``data`` as its mime bundle."""
    return render_output_frame("display_data", {"data": data})


# --- stream frames --------------------------------------------------------


def test_stream_stdout_default_variant() -> None:
    out = render_output_frame("stream", {"name": "stdout", "text": "hello"})
    assert out.kind == "stream"
    assert out.variant == "stdout"
    assert "hello" in out.html


def test_stream_stderr_variant() -> None:
    out = render_output_frame("stream", {"name": "stderr", "text": "boom"})
    assert out.variant == "stderr"


def test_stream_text_list_is_joined() -> None:
    out = render_output_frame("stream", {"name": "stdout", "text": ["a", "b", "c"]})
    assert "abc" in out.html


def test_stream_escapes_html_metacharacters() -> None:
    out = render_output_frame("stream", {"text": "<script>x</script>"})
    assert "<script>" not in out.html
    assert "&lt;script&gt;" in out.html


# --- error frames ---------------------------------------------------------


def test_error_with_traceback_renders_lines() -> None:
    out = render_output_frame(
        "error",
        {"ename": "ValueError", "evalue": "bad", "traceback": ["line1", "line2"]},
    )
    assert out.kind == "error"
    assert out.variant == "traceback"
    assert "line1" in out.html
    assert "line2" in out.html


def test_error_without_traceback_falls_back_to_ename_evalue() -> None:
    out = render_output_frame("error", {"ename": "KeyError", "evalue": "missing"})
    assert out.html == "KeyError: missing"


def test_error_missing_fields_uses_defaults() -> None:
    out = render_output_frame("error", {})
    assert out.html == "Error: "


def test_error_escapes_ename_evalue() -> None:
    out = render_output_frame("error", {"ename": "<b>", "evalue": "<i>"})
    assert "<b>" not in out.html
    assert "&lt;b&gt;" in out.html


# --- mime bundle priority -------------------------------------------------


def test_empty_bundle_is_empty_variant() -> None:
    out = _display({})
    assert out.kind == "display_data"
    assert out.variant == "empty"
    assert out.html == ""


def test_widget_bundle_renders_placeholder() -> None:
    out = _display({"application/vnd.jupyter.widget-view+json": {"model_id": "abcdef1234567890"}})
    assert out.variant == "widget"
    assert "not rendered" in out.html
    # model_id is truncated to the first 8 chars.
    assert "abcdef12" in out.html
    assert "abcdef1234567890" not in out.html


def test_markdown_branch_uses_markdown_kind() -> None:
    out = _display({"text/markdown": "# Title"})
    assert out.kind == "markdown"
    assert out.variant == "markdown"
    assert "<h1>" in out.html


def test_html_branch_passes_through_verbatim() -> None:
    out = _display({"text/html": "<div class='x'>raw</div>"})
    assert out.variant == "html"
    assert out.html == "<div class='x'>raw</div>"


def test_svg_branch() -> None:
    svg = "<svg><rect/></svg>"
    out = _display({"image/svg+xml": svg})
    assert out.variant == "svg"
    assert out.html == svg


def test_png_string_payload_builds_data_uri() -> None:
    out = _display({"image/png": "QUJD"})
    assert out.variant == "png"
    assert "data:image/png;base64,QUJD" in out.html
    assert "<img" in out.html


def test_png_bytes_payload_is_base64_encoded() -> None:
    out = _display({"image/png": b"ABC"})
    assert out.variant == "png"
    # base64 of b"ABC" is "QUJD".
    assert "QUJD" in out.html


def test_jpeg_branch() -> None:
    out = _display({"image/jpeg": "QUJD"})
    assert out.variant == "jpeg"
    assert "data:image/jpeg;base64," in out.html


def test_json_branch_pretty_prints() -> None:
    out = _display({"application/json": {"k": "v"}})
    assert out.variant == "json"
    assert "&quot;k&quot;" in out.html or '"k"' in out.html
    assert "<pre" in out.html


def test_plain_branch_is_escaped() -> None:
    out = _display({"text/plain": "<tag> & more"})
    assert out.variant == "plain"
    assert "&lt;tag&gt;" in out.html
    assert "&amp;" in out.html


def test_unknown_mime_only_yields_unknown_variant() -> None:
    out = _display({"application/x-weird": "?"})
    assert out.variant == "unknown"
    assert out.html == ""


def test_markdown_outranks_html() -> None:
    out = _display({"text/markdown": "**bold**", "text/html": "<i>x</i>"})
    assert out.kind == "markdown"


def test_html_outranks_svg_and_png() -> None:
    out = _display({"text/html": "<b>x</b>", "image/svg+xml": "<svg/>", "image/png": "QUJD"})
    assert out.variant == "html"


def test_png_outranks_jpeg() -> None:
    out = _display({"image/png": "QUJD", "image/jpeg": "QUJD"})
    assert out.variant == "png"


def test_execute_result_uses_same_mime_dispatch() -> None:
    out = render_output_frame("execute_result", {"data": {"text/plain": "42"}})
    assert out.kind == "display_data"
    assert out.variant == "plain"
    assert "42" in out.html


# --- dispatch fallbacks ---------------------------------------------------


def test_unknown_msg_type_is_empty() -> None:
    out = render_output_frame("clear_output", {"wait": True})
    assert out.kind == "display_data"
    assert out.variant == "unknown"
    assert out.html == ""


def test_display_data_without_data_key_is_empty() -> None:
    out = render_output_frame("display_data", {})
    assert out.variant == "empty"


# --- public markdown alias ------------------------------------------------


def test_render_markdown_source_renders_tables() -> None:
    html = render_markdown_source("| a | b |\n| - | - |\n| 1 | 2 |")
    assert "<table>" in html


def test_render_markdown_source_strikethrough() -> None:
    html = render_markdown_source("~~gone~~")
    assert "<s>" in html
