"""Tests for the Sprint 13.11.5 _json_safe coercion helper.

Sprint 13.11.5 hotfix: the validation-error handler used to crash
when a request validator surfaced raw ``bytes`` in the ``input``
slot (happens when a client posts a JSON body without
``Content-Type: application/json`` — FastAPI then returns the
payload verbatim).  ``_json_safe`` coerces those values into
JSON-encodable shapes so the 422 actually reaches the caller
instead of becoming an opaque 500.
"""

from __future__ import annotations

import json

from pointlessql.api.error_handlers import _json_safe


def test_passes_through_json_native_scalars() -> None:
    assert _json_safe(42) == 42
    assert _json_safe("plain") == "plain"
    assert _json_safe(None) is None
    assert _json_safe(True) is True
    assert _json_safe(3.14) == 3.14


def test_decodes_bytes_to_utf8() -> None:
    assert _json_safe(b"hello") == "hello"
    # invalid utf-8 → replacement chars, never raises
    decoded = _json_safe(b"\xff\xfe")
    assert isinstance(decoded, str)


def test_clips_long_bytes_payloads() -> None:
    huge = _json_safe(b"x" * 5000)
    assert isinstance(huge, str)
    assert len(huge) == 500


def test_recurses_into_dicts_and_lists() -> None:
    nested = {"a": b"x", "b": [b"y", 1, {"c": b"z"}]}
    out = _json_safe(nested)
    assert out == {"a": "x", "b": ["y", 1, {"c": "z"}]}


def test_falls_back_to_repr_for_unknown_types() -> None:
    class _Opaque:
        def __repr__(self) -> str:
            return "<Opaque thing>"

    out = _json_safe(_Opaque())
    assert isinstance(out, str)
    assert "Opaque" in out


def test_output_is_always_json_encodable() -> None:
    """The actual contract: whatever comes out can be json.dumps'd.

    Mirrors the live-Hermes session crash where FastAPI's
    validation errors carried bytes in the ``input`` field and the
    422 response itself failed to serialise.
    """
    pathological = {
        "input": b"raw bytes with no Content-Type header",
        "loc": ["body"],
        "msg": "JSON decode failed",
        "type": "json_invalid",
        "extra": [b"more bytes", {"nested": b"also bytes"}],
    }
    sanitized = {k: _json_safe(v) for k, v in pathological.items()}
    # If this raises the regression is back.
    json.dumps(sanitized)
