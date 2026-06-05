"""Mutation-killing tests for the replay worker's pure logic.

Covers the cell-skip predicate, kernel-env preparation, iopub message
routing (parent match, idle status, output classification), the
error-detection short-circuit, content serialisation, and the
output/error frame builders — the I/O-free pieces the worker delegates
to :mod:`pointlessql.services.notebook._replay_logic`.
"""

from __future__ import annotations

from typing import Any

import pytest

from pointlessql.services.notebook._replay_logic import (
    build_error_frame,
    build_output_frame,
    frame_has_error,
    is_idle_status,
    is_output_message,
    message_matches_parent,
    prepare_kernel_env,
    serialise_content,
    should_execute_cell,
)

_PRINCIPAL = "replay-worker@pointlessql.local"


# --- should_execute_cell --------------------------------------------------


@pytest.mark.parametrize(
    "cell_type,source,expected",
    [
        ("code", "print(1)", True),
        ("sql", "SELECT 1", True),
        ("markdown", "# heading", False),
        ("code", "   \n\t", False),
        ("code", "", False),
    ],
)
def test_should_execute_cell(cell_type: str, source: str, expected: bool) -> None:
    assert should_execute_cell(cell_type, source) is expected


# --- prepare_kernel_env ---------------------------------------------------


def test_prepare_kernel_env_sets_branch_and_default_principal() -> None:
    env = prepare_kernel_env({"PATH": "/x"}, "dev")
    assert env == {
        "PATH": "/x",
        "POINTLESSQL_BRANCH": "dev",
        "POINTLESSQL_PRINCIPAL": _PRINCIPAL,
    }


def test_prepare_kernel_env_no_branch_omits_key() -> None:
    env = prepare_kernel_env({"PATH": "/x"}, None)
    assert "POINTLESSQL_BRANCH" not in env
    assert env["POINTLESSQL_PRINCIPAL"] == _PRINCIPAL


def test_prepare_kernel_env_keeps_inherited_principal() -> None:
    env = prepare_kernel_env({"POINTLESSQL_PRINCIPAL": "alice@x"}, "dev")
    assert env["POINTLESSQL_PRINCIPAL"] == "alice@x"


def test_prepare_kernel_env_does_not_mutate_input() -> None:
    base = {"PATH": "/x"}
    prepare_kernel_env(base, "dev")
    assert base == {"PATH": "/x"}


# --- message_matches_parent -----------------------------------------------


def test_message_matches_parent_true() -> None:
    assert message_matches_parent({"parent_header": {"msg_id": "abc"}}, "abc") is True


def test_message_matches_parent_wrong_id() -> None:
    assert message_matches_parent({"parent_header": {"msg_id": "abc"}}, "xyz") is False


@pytest.mark.parametrize("msg", [{}, {"parent_header": None}, {"parent_header": {}}])
def test_message_matches_parent_missing_header(msg: dict[str, Any]) -> None:
    assert message_matches_parent(msg, "abc") is False


# --- is_idle_status -------------------------------------------------------


def test_is_idle_status_true() -> None:
    assert is_idle_status("status", {"execution_state": "idle"}) is True


@pytest.mark.parametrize(
    "msg_type,content",
    [
        ("status", {"execution_state": "busy"}),
        ("stream", {"execution_state": "idle"}),
        ("status", {}),
    ],
)
def test_is_idle_status_false(msg_type: str, content: dict[str, Any]) -> None:
    assert is_idle_status(msg_type, content) is False


# --- is_output_message ----------------------------------------------------


@pytest.mark.parametrize("msg_type", ["stream", "execute_result", "display_data", "error"])
def test_is_output_message_true(msg_type: str) -> None:
    assert is_output_message(msg_type) is True


@pytest.mark.parametrize("msg_type", ["status", "execute_input", "comm_msg"])
def test_is_output_message_false(msg_type: str) -> None:
    assert is_output_message(msg_type) is False


# --- frame_has_error ------------------------------------------------------


def test_frame_has_error_true() -> None:
    assert frame_has_error([{"msg_type": "stream"}, {"msg_type": "error"}]) is True


def test_frame_has_error_false() -> None:
    assert frame_has_error([{"msg_type": "stream"}]) is False


def test_frame_has_error_empty() -> None:
    assert frame_has_error([]) is False


# --- serialise_content ----------------------------------------------------


def test_serialise_stream() -> None:
    assert serialise_content("stream", {"name": "stderr", "text": "oops"}) == {
        "name": "stderr",
        "text": "oops",
    }


def test_serialise_stream_defaults() -> None:
    assert serialise_content("stream", {}) == {"name": "stdout", "text": ""}


def test_serialise_error() -> None:
    out = serialise_content("error", {"ename": "X", "evalue": "y", "traceback": ["a"]})
    assert out == {"ename": "X", "evalue": "y", "traceback": ["a"]}


def test_serialise_error_defaults_traceback() -> None:
    assert serialise_content("error", {}) == {
        "ename": None,
        "evalue": None,
        "traceback": [],
    }


def test_serialise_execute_result_passes_mime_bundle() -> None:
    out = serialise_content("execute_result", {"data": {"text/plain": "5"}, "execution_count": 3})
    assert out == {"data": {"text/plain": "5"}, "execution_count": 3}


def test_serialise_display_data_defaults() -> None:
    assert serialise_content("display_data", {}) == {"data": {}, "execution_count": None}


# --- build_output_frame ---------------------------------------------------


def test_build_output_frame() -> None:
    frame = build_output_frame(
        content_hash="h1",
        kernel_session_id="s1",
        output_index=2,
        msg_type="stream",
        content={"text": "hi"},
        metadata={"m": 1},
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert frame == {
        "content_hash": "h1",
        "kernel_session_id": "s1",
        "output_index": 2,
        "msg_type": "stream",
        "content": {"text": "hi"},
        "metadata": {"m": 1},
        "created_at": "2026-01-01T00:00:00+00:00",
    }


# --- build_error_frame ----------------------------------------------------


def test_build_error_frame_defaults() -> None:
    frame = build_error_frame(
        content_hash="__worker__",
        kernel_session_id="s1",
        ename="RuntimeError",
        evalue="boom",
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert frame == {
        "content_hash": "__worker__",
        "kernel_session_id": "s1",
        "output_index": 0,
        "msg_type": "error",
        "content": {"ename": "RuntimeError", "evalue": "boom", "traceback": []},
        "metadata": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def test_build_error_frame_with_traceback() -> None:
    frame = build_error_frame(
        content_hash="h",
        kernel_session_id="s",
        ename="E",
        evalue="v",
        created_at="t",
        traceback=["line1", "line2"],
    )
    assert frame["content"]["traceback"] == ["line1", "line2"]
