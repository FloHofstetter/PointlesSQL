"""Mutation-killing tests for the papermill executor's pure logic.

Covers config validation + timeout resolution, the run-artefact path
builders, the engine-error message, the code-cell predicate, and the
nbformat output-frame transform — the I/O-free pieces the executor
delegates to
:mod:`pointlessql.services.scheduler.executors._papermill_logic`.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pointlessql.exceptions import ValidationError
from pointlessql.services.scheduler.executors._papermill_logic import (
    is_code_cell,
    papermill_error_message,
    papermill_input_temp_path,
    papermill_output_path,
    transform_output_frame,
    validate_papermill_config,
)

# --- validate_papermill_config --------------------------------------------


def test_validate_config_minimal_uses_default_timeout() -> None:
    assert validate_papermill_config({"notebook_path": "a.ipynb"}, 600) == (
        "a.ipynb",
        {},
        600,
    )


def test_validate_config_full() -> None:
    cfg = {"notebook_path": "p/e.ipynb", "parameters": {"d": "x"}, "timeout_seconds": 30}
    assert validate_papermill_config(cfg, 600) == ("p/e.ipynb", {"d": "x"}, 30)


@pytest.mark.parametrize("cfg", [{}, {"notebook_path": 5}, {"notebook_path": None}])
def test_validate_config_bad_notebook_path(cfg: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="notebook_path"):
        validate_papermill_config(cfg, 600)


def test_validate_config_params_must_be_object() -> None:
    with pytest.raises(ValidationError, match="'parameters' must be an object"):
        validate_papermill_config({"notebook_path": "a.ipynb", "parameters": [1]}, 600)


@pytest.mark.parametrize("timeout", [0, -5, "30", 1.5])
def test_validate_config_timeout_must_be_positive_int(timeout: Any) -> None:
    with pytest.raises(ValidationError, match="positive int"):
        validate_papermill_config({"notebook_path": "a.ipynb", "timeout_seconds": timeout}, 600)


# --- path builders --------------------------------------------------------


def test_papermill_output_path() -> None:
    assert papermill_output_path(Path("/runs"), 42) == Path("/runs/42.ipynb")


def test_papermill_input_temp_path() -> None:
    assert papermill_input_temp_path(Path("/runs"), 42) == Path("/runs/42.input.ipynb")


# --- papermill_error_message ----------------------------------------------


def test_papermill_error_message() -> None:
    assert papermill_error_message(3, "ValueError", "boom") == (
        "papermill execution failed in cell 3: ValueError: boom"
    )


# --- is_code_cell ---------------------------------------------------------


def test_is_code_cell_true_for_code() -> None:
    assert is_code_cell(SimpleNamespace(cell_type="code")) is True


@pytest.mark.parametrize("cell_type", ["markdown", "raw"])
def test_is_code_cell_false_for_non_code(cell_type: str) -> None:
    assert is_code_cell(SimpleNamespace(cell_type=cell_type)) is False


def test_is_code_cell_defaults_missing_attr_to_code() -> None:
    assert is_code_cell(object()) is True


# --- transform_output_frame -----------------------------------------------


def test_transform_stream_frame() -> None:
    raw = {"output_type": "stream", "name": "stdout", "text": "hi"}
    assert transform_output_frame(raw) == ("stream", {"name": "stdout", "text": "hi"}, None)


def test_transform_result_lifts_metadata() -> None:
    raw = {
        "output_type": "execute_result",
        "data": {"text/plain": "5"},
        "metadata": {"foo": 1},
    }
    msg_type, content, metadata = transform_output_frame(raw)
    assert msg_type == "execute_result"
    assert content == {"data": {"text/plain": "5"}}
    assert metadata == {"foo": 1}


def test_transform_missing_output_type_defaults() -> None:
    assert transform_output_frame({}) == ("execute_result", {}, None)


def test_transform_non_dict_metadata_becomes_none() -> None:
    raw = {"output_type": "error", "metadata": "weird", "data": {}}
    msg_type, content, metadata = transform_output_frame(raw)
    assert msg_type == "error"
    assert content == {"data": {}}  # output_type + metadata stripped
    assert metadata is None


def test_transform_does_not_mutate_input() -> None:
    raw = {"output_type": "stream", "text": "x", "metadata": {"a": 1}}
    transform_output_frame(raw)
    assert raw == {"output_type": "stream", "text": "x", "metadata": {"a": 1}}
