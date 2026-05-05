"""Tests for the preview-card error humaniser.

Pin the contract that ``humanize_preview_error`` rewrites the most
common deltalake/duckdb failure shapes into one-line human-readable
text + a slug the frontend can use to render an actionable hint.

The user-visible motivation: querying a table whose ``storage_root``
no longer exists on disk used to render the raw Rust-style error
verbatim ("Invalid table location: file:///tmp/demo/orders Error:
Os { code: 2, kind: NotFound, message: \"No such file or
directory\" }"); now it's a one-line "Table data is missing on
disk" plus a "How to fix" hint pointing at the seed script.
"""

from __future__ import annotations

import pytest

from pointlessql.api.catalog_routes import humanize_preview_error


class TestHumanizePreviewError:
    """``humanize_preview_error`` classifies the well-known failures."""

    def test_missing_storage_path_with_file_uri_extracts_path(self) -> None:
        exc = Exception(
            "Invalid table location: file:///var/lake/orders Error: "
            'Os { code: 2, kind: NotFound, message: "No such file or directory" }'
        )
        detail, kind = humanize_preview_error(exc)
        assert kind == "missing_storage"
        assert "/var/lake/orders" in detail
        assert "missing on disk" in detail.lower()
        # No raw Rust noise leaks through.
        assert "Os { code:" not in detail
        assert "NotFound" not in detail

    def test_message_does_not_couple_to_demo_seed(self) -> None:
        """The hint copy must not assume the user ran a demo seed script.

        Catalog data is independent of integration tests / walkthroughs
        — references to ``seed``, the ``scripts/seed-*.py`` family, or
        ``demo data`` would mislead users whose tables are real
        production data, not seeded fixtures.
        """
        exc = Exception(
            "Invalid table location: file:///var/lake/orders Error: "
            'Os { code: 2, kind: NotFound, message: "No such file or directory" }'
        )
        detail, _kind = humanize_preview_error(exc)
        lowered = detail.lower()
        assert "seed" not in lowered, f"hint mentions 'seed': {detail!r}"
        assert "demo" not in lowered, f"hint mentions 'demo': {detail!r}"
        assert "scripts/" not in lowered, f"hint mentions a script path: {detail!r}"

    def test_missing_storage_path_without_file_uri_falls_to_generic_text(self) -> None:
        exc = Exception("Storage error: NotFound — No such file or directory")
        detail, kind = humanize_preview_error(exc)
        assert kind == "missing_storage"
        assert "missing on disk" in detail.lower()

    def test_unknown_failure_passes_through_as_str(self) -> None:
        exc = Exception("DuckDB Error: Out of memory")
        detail, kind = humanize_preview_error(exc)
        assert kind is None
        assert detail == "DuckDB Error: Out of memory"

    def test_partial_match_does_not_misclassify(self) -> None:
        # "NotFound" alone (without the "No such file..." second
        # phrase) is too weak — fall through to the unknown bucket.
        exc = Exception("HTTP 404 NotFound for blob")
        detail, kind = humanize_preview_error(exc)
        assert kind is None
        assert "HTTP 404 NotFound for blob" == detail

    @pytest.mark.parametrize(
        "path",
        [
            "/tmp/demo/orders",
            "/var/lake/silver_tab",
            "/home/flo/data/x.delta",
        ],
    )
    def test_path_extraction_preserves_unicode_and_dashes(self, path: str) -> None:
        exc = Exception(
            f"Invalid table location: file://{path} "
            'Error: Os { code: 2, kind: NotFound, message: "No such file or directory" }'
        )
        detail, kind = humanize_preview_error(exc)
        assert kind == "missing_storage"
        assert path in detail
