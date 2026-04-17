"""Tests for the Sprint 26 notebook-render service."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pointlessql.exceptions import CatalogNotFoundError, EngineError
from pointlessql.services import notebook_render


def _minimal_ipynb() -> dict[str, object]:
    """Return the smallest valid ipynb-4.5 document.

    Good enough for nbconvert's ``lab`` template — produces HTML that
    contains the source string so assertions can look for it.
    """
    return {
        "cells": [
            {
                "cell_type": "code",
                "source": "print('sprint-26-smoke')",
                "outputs": [],
                "execution_count": 1,
                "metadata": {},
            }
        ],
        "metadata": {
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


@pytest.fixture
def runs_dir(tmp_path: Path) -> Path:
    """A clean ``runs/`` directory isolated per test."""
    root = tmp_path / "runs"
    root.mkdir()
    return root


def test_missing_ipynb_raises_not_found(runs_dir: Path) -> None:
    """Calling the renderer before the executor writes the ipynb 404s."""
    with pytest.raises(CatalogNotFoundError, match="Run 7 output"):
        notebook_render.render_run_notebook(runs_dir, 7)


def test_render_writes_sidecar_and_returns_html(runs_dir: Path) -> None:
    """First call runs nbconvert, writes a sidecar, returns HTML containing the cell source."""
    (runs_dir / "42.ipynb").write_text(json.dumps(_minimal_ipynb()))

    html = notebook_render.render_run_notebook(runs_dir, 42)

    assert "sprint-26-smoke" in html
    sidecar = runs_dir / "42.html"
    assert sidecar.is_file()
    assert sidecar.read_text() == html
    # Temp file is cleaned up by the atomic rename.
    assert not (runs_dir / "42.html.tmp").exists()


def test_sidecar_is_reused_on_second_call(runs_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Second call skips nbconvert entirely, reading the sidecar instead."""
    (runs_dir / "42.ipynb").write_text(json.dumps(_minimal_ipynb()))

    # First call: real nbconvert writes the sidecar.
    first = notebook_render.render_run_notebook(runs_dir, 42)
    assert (runs_dir / "42.html").is_file()

    # Now patch HTMLExporter so any second invocation would explode. If
    # the sidecar cache works, it should not be touched.
    import nbconvert  # type: ignore[import-untyped]

    def _exploding_exporter(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("sidecar cache miss: HTMLExporter was re-instantiated")

    monkeypatch.setattr(nbconvert, "HTMLExporter", _exploding_exporter)

    second = notebook_render.render_run_notebook(runs_dir, 42)
    assert second == first


def test_nbconvert_error_becomes_engine_error(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A raising ``HTMLExporter`` surfaces as ``EngineError``."""
    (runs_dir / "42.ipynb").write_text(json.dumps(_minimal_ipynb()))

    import nbconvert  # type: ignore[import-untyped]

    fake = MagicMock()
    fake.from_filename.side_effect = RuntimeError("template not found")
    monkeypatch.setattr(nbconvert, "HTMLExporter", lambda **_kwargs: fake)

    with pytest.raises(EngineError, match="Failed to render run 42"):
        notebook_render.render_run_notebook(runs_dir, 42)
    # No sidecar should have been written on failure.
    assert not (runs_dir / "42.html").exists()
