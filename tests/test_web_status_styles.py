"""Tests for the centralised status → badge class mapping."""

from __future__ import annotations

import pytest

from pointlessql.web.status_styles import status_class


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("succeeded", "bg-success"),
        ("ok", "bg-success"),
        ("approved", "bg-success"),
        ("READY", "bg-success"),
        ("running", "bg-info text-dark"),
        ("queued", "bg-info text-dark"),
        ("failed", "bg-danger"),
        ("rolled_back", "bg-danger"),
        ("FAILED_REGISTRATION", "bg-danger"),
        ("needs_approval", "bg-warning text-dark"),
        ("PENDING_REGISTRATION", "bg-warning text-dark"),
        ("denied", "bg-secondary"),
        ("discarded", "bg-secondary"),
    ],
)
def test_known_status_returns_expected_class(status: str, expected: str) -> None:
    assert status_class(status) == expected


def test_unknown_status_falls_back_to_secondary() -> None:
    assert status_class("frobulated") == "bg-secondary"


def test_none_status_falls_back_to_secondary() -> None:
    assert status_class(None) == "bg-secondary"


def test_empty_status_falls_back_to_secondary() -> None:
    assert status_class("") == "bg-secondary"
