"""Unit tests for the ingest connector probe's error envelope.

The probe's load-bearing security invariant is that a raw ``duckdb.Error``
— which can embed connection strings or credentials in its message — is
never surfaced to the HTTP caller. ``probe_source`` must replace it with a
generic :class:`ProbeError`, logging the real cause server-side only. The
route-level smoke tests live in ``test_ingest_routes_probe.py``; these
exercise the redaction + empty/no-SELECT branches directly.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from pointlessql.services.ingest import probe as probe_module
from pointlessql.services.ingest.connectors import ReaderSpec
from pointlessql.services.ingest.probe import (
    ProbeError,
    _run_listing_or_probe,
    probe_source,
)

_SECRET = "AKIAEXAMPLEsupersecret0987654321"


def test_probe_redacts_duckdb_credential_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A duckdb.Error carrying a credential is replaced with a generic ProbeError."""
    csv = tmp_path / "tiny.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")

    def _boom(_cursor: object, _spec: object) -> object:
        raise duckdb.Error(f"HTTP 403 signature mismatch for access key {_SECRET}")

    monkeypatch.setattr(probe_module, "_run_listing_or_probe", _boom)

    with pytest.raises(ProbeError) as excinfo:
        probe_source("file_upload", {"path": str(csv)}, {})

    err = excinfo.value
    surfaced = f"{err.reason} {err.hint or ''}"
    # The raw driver detail (and the embedded secret) must not leak out.
    assert _SECRET not in surfaced
    assert "signature mismatch" not in surfaced
    # ...and the caller still gets an actionable, generic message.
    assert "file_upload" in err.reason
    assert err.hint


def test_probe_unexpected_error_is_also_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-DuckDB driver error is likewise wrapped, not surfaced raw."""
    csv = tmp_path / "tiny.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")

    def _boom(_cursor: object, _spec: object) -> object:
        raise RuntimeError(f"boto credential {_SECRET} rejected")

    monkeypatch.setattr(probe_module, "_run_listing_or_probe", _boom)

    with pytest.raises(ProbeError) as excinfo:
        probe_source("file_upload", {"path": str(csv)}, {})

    assert _SECRET not in f"{excinfo.value.reason} {excinfo.value.hint or ''}"


def test_run_probe_empty_sql_raises() -> None:
    """A spec with empty SQL raises the empty-reader ProbeError."""
    conn = duckdb.connect(":memory:")
    try:
        with pytest.raises(ProbeError, match="Empty reader SQL"):
            _run_listing_or_probe(conn.cursor(), ReaderSpec(sql="   "))
    finally:
        conn.close()


def test_run_probe_no_select_raises() -> None:
    """A spec whose statements contain no SELECT raises before executing them."""
    conn = duckdb.connect(":memory:")
    try:
        with pytest.raises(ProbeError, match="no SELECT statement"):
            _run_listing_or_probe(conn.cursor(), ReaderSpec(sql="CREATE TABLE x (a INTEGER)"))
    finally:
        conn.close()
