"""Unit tests for the Phase 56.5 display-layer Jinja filters.

Covers ``format_uuid`` (Phase-53 Pattern 6) and ``format_hash``
(Phase-53 Pattern 7) registered against the FastAPI Jinja2Templates
environment in :mod:`pointlessql.api.main`.
"""

from __future__ import annotations

from pointlessql.api._template_filters import (  # noqa: PLC2701  # tests reach private helpers
    _format_hash,
    _format_uuid,
)


class TestFormatUuid:
    def test_packed_32_char_hex(self) -> None:
        assert (
            _format_uuid("dbca5242d30d4686b4683acc417277eb")
            == "dbca5242-d30d-4686-b468-3acc417277eb"
        )

    def test_already_hyphenated_passes_through(self) -> None:
        assert (
            _format_uuid("8ebb2e9f-d170-41b6-82ec-1f70470a5fcc")
            == "8ebb2e9f-d170-41b6-82ec-1f70470a5fcc"
        )

    def test_mixed_hyphens_normalised(self) -> None:
        # Hypothetical: dashes in non-canonical positions still come out
        # as canonical 8-4-4-4-12.
        assert (
            _format_uuid("dbca-5242d30d4686b4683acc417277eb")
            == "dbca5242-d30d-4686-b468-3acc417277eb"
        )

    def test_empty_returns_empty_string(self) -> None:
        assert _format_uuid("") == ""
        assert _format_uuid(None) == ""

    def test_non_uuid_passes_through(self) -> None:
        # Non-UUID strings must round-trip unchanged so the filter is
        # safe to apply blanket-style.
        assert _format_uuid("not-a-uuid") == "not-a-uuid"
        assert _format_uuid("42") == "42"


class TestFormatHash:
    def test_zero_sentinel_returns_label(self) -> None:
        assert _format_hash("0" * 64) == "(no source captured)"

    def test_real_hash_passes_through(self) -> None:
        h = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert _format_hash(h) == h

    def test_empty_returns_empty_string(self) -> None:
        assert _format_hash("") == ""
        assert _format_hash(None) == ""

    def test_custom_label(self) -> None:
        assert (
            _format_hash("0" * 64, sentinel_label="—")
            == "—"
        )

    def test_short_zero_string_also_caught(self) -> None:
        # The sentinel could be 32 hex (md5) or 64 (sha256); the filter
        # treats any all-zero string as the sentinel.
        assert _format_hash("0" * 32) == "(no source captured)"


def test_filters_registered_on_jinja_env() -> None:
    """Round-trip via the live Jinja2Templates env."""
    from pointlessql.api.main import _TEMPLATES

    env = _TEMPLATES.env
    template = env.from_string(
        "{{ uid|format_uuid }} | {{ h|format_hash }}"
    )
    rendered = template.render(
        uid="dbca5242d30d4686b4683acc417277eb",
        h="0" * 64,
    )
    assert rendered == (
        "dbca5242-d30d-4686-b468-3acc417277eb"
        " | (no source captured)"
    )
