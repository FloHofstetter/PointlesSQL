"""Tests for Phase 98.D — notebook → static HTML/PDF export."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.services.notebook import export as notebook_export_service

# -- service: HTML rendering --------------------------------------------------


def test_render_html_includes_title_and_meta() -> None:
    """Title + cell count surface in the rendered ``<head>`` / meta line."""
    body = notebook_export_service.render_notebook_html(
        title="demo",
        cells=[
            {"content_hash": "abc", "cell_type": "code", "source": "1+1"},
        ],
        outputs=[],
    )
    assert "<title>demo</title>" in body
    assert "1 cells" in body
    assert "1+1" in body


def test_render_html_escapes_source() -> None:
    """Code cell source is HTML-escaped so ``<script>`` cannot inject."""
    body = notebook_export_service.render_notebook_html(
        title="x",
        cells=[
            {
                "content_hash": "abc",
                "cell_type": "code",
                "source": '<script>alert(1)</script>',
            }
        ],
        outputs=[],
    )
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_render_html_markdown_cell_rendered_via_commonmark() -> None:
    """Markdown cells run through the existing CommonMark pipeline."""
    body = notebook_export_service.render_notebook_html(
        title="x",
        cells=[
            {
                "content_hash": "abc",
                "cell_type": "markdown",
                "source": "# heading\n\nbody.",
            }
        ],
        outputs=[],
    )
    assert "<h1>heading</h1>" in body
    assert "body." in body


def test_render_html_includes_stream_output() -> None:
    """A ``stream`` output frame surfaces inline as a ``<pre>`` block."""
    body = notebook_export_service.render_notebook_html(
        title="x",
        cells=[
            {"content_hash": "abc", "cell_type": "code", "source": "print(1)"},
        ],
        outputs=[
            {
                "content_hash": "abc",
                "kernel_session_id": "s1",
                "output_index": 0,
                "msg_type": "stream",
                "content": {"name": "stdout", "text": "hello\n"},
                "metadata": None,
                "created_at": "2026-05-20T12:00:00",
            }
        ],
    )
    assert "hello" in body


def test_latest_session_wins_over_older_session() -> None:
    """If the same cell has output frames from two sessions, only latest renders."""
    body = notebook_export_service.render_notebook_html(
        title="x",
        cells=[
            {"content_hash": "abc", "cell_type": "code", "source": "x"},
        ],
        outputs=[
            {
                "content_hash": "abc",
                "kernel_session_id": "s_old",
                "output_index": 0,
                "msg_type": "stream",
                "content": {"name": "stdout", "text": "OLD_OUTPUT\n"},
                "metadata": None,
                "created_at": "2026-05-20T10:00:00",
            },
            {
                "content_hash": "abc",
                "kernel_session_id": "s_new",
                "output_index": 0,
                "msg_type": "stream",
                "content": {"name": "stdout", "text": "NEW_OUTPUT\n"},
                "metadata": None,
                "created_at": "2026-05-20T12:00:00",
            },
        ],
    )
    assert "NEW_OUTPUT" in body
    assert "OLD_OUTPUT" not in body


def test_render_pdf_returns_none_when_weasyprint_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When WeasyPrint import fails, the helper returns ``None``."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "weasyprint":
            raise ImportError("weasyprint disabled for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    out = notebook_export_service.render_notebook_pdf(
        title="x",
        cells=[
            {"content_hash": "abc", "cell_type": "code", "source": "x"},
        ],
        outputs=[],
    )
    assert out is None


# -- REST: GET /api/notebooks/export.html ------------------------------------


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``settings.jupyter.notebooks_dir`` at a tmp directory."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


async def test_api_export_html(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """HTML export endpoint returns the full document + attachment header."""
    nb = workspace_dir / "report.py"
    nb.write_text("# %% [markdown]\n# # Hello\n\n# %%\nprint(1)\n")
    resp = await admin_client.get(
        "/api/notebooks/export.html", params={"path": "report.py"}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "report.html" in resp.headers.get("content-disposition", "")
    body = resp.text
    assert "<!DOCTYPE html>" in body
    assert "Hello" in body


async def test_api_export_pdf_fallback_marks_header(
    workspace_dir: Path,
    admin_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When WeasyPrint is missing the PDF route falls back to HTML."""
    nb = workspace_dir / "x.py"
    nb.write_text("# %%\nprint(1)\n")

    def fake_render_pdf(*, title: str, cells: list, outputs: list, **_: object):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(
        notebook_export_service, "render_notebook_pdf", fake_render_pdf
    )
    resp = await admin_client.get(
        "/api/notebooks/export.pdf", params={"path": "x.py"}
    )
    assert resp.status_code == 200
    # Fallback always sets the diagnostic header so a UI can offer
    # "use your browser to Save as PDF" copy when this is set.
    assert resp.headers.get("X-PointlesSQL-Export-Fallback") == (
        "weasyprint-unavailable"
    )
    assert resp.headers["content-type"].startswith("text/html")


async def test_api_export_rejects_missing_notebook(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Unknown path → 422 via the resolver guard."""
    resp = await admin_client.get(
        "/api/notebooks/export.html", params={"path": "nope.py"}
    )
    assert resp.status_code == 422
