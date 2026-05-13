"""Tests for the Phase 75.1 verifiable audit export.

Covers:

* :func:`export_audit_to_files` writes the data + sha256 + manifest
  sidecar trio.
* sha256 sidecar matches ``sha256sum -c`` expectations (single line,
  ``<hex>  <basename>\\n`` shape).
* Manifest carries filter + count + tool_version + data_sha256.
* All three sidecars land at mode 0o600.
* Tarball variant of the web endpoint streams the same trio.
"""

from __future__ import annotations

import datetime
import hashlib
import io
import json
import stat
import tarfile
from pathlib import Path

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.cli.audit_export import (
    ExportFilters,
    export_audit_to_files,
)
from pointlessql.models.audit._log import AuditLog


def _seed_audit_rows(n: int = 5) -> list[int]:
    """Insert *n* audit rows; return their ids in insertion order."""
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    ids: list[int] = []
    with factory() as session:
        for i in range(n):
            row = AuditLog(
                workspace_id=1,
                user_id=1,
                user_email=f"alice-{i}@test.com",
                actor_role="user",
                action="catalog.viewed",
                target=f"main.sales_{i}",
                client_ip="127.0.0.1",
                detail="{}",
                created_at=now - datetime.timedelta(minutes=i),
            )
            session.add(row)
            session.flush()
            ids.append(row.id)
        session.commit()
    return ids


def test_export_audit_to_files_writes_three_sidecars(tmp_path: Path) -> None:
    _seed_audit_rows(3)
    factory = app.state.session_factory
    out = tmp_path / "pql-audit.json"
    result = export_audit_to_files(
        factory,
        out=out,
        fmt="json",
        filters=ExportFilters(
            since=None,
            until=None,
            action=None,
            actor=None,
            target=None,
        ),
    )
    assert out.exists()
    assert (out.with_name("pql-audit.json.sha256")).exists()
    assert (out.with_name("pql-audit.json.manifest.json")).exists()
    assert result["entry_count"] >= 3
    payload = out.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == result["sha256"]


def test_export_sha256_sidecar_matches_sha256sum_format(
    tmp_path: Path,
) -> None:
    _seed_audit_rows(2)
    factory = app.state.session_factory
    out = tmp_path / "pql-audit.json"
    result = export_audit_to_files(
        factory,
        out=out,
        fmt="json",
        filters=ExportFilters(
            since=None, until=None, action=None, actor=None, target=None
        ),
    )
    sha_path = Path(result["sha256_path"])
    sha_line = sha_path.read_text(encoding="ascii")
    # sha256sum format: <hex>  <basename>\n
    expected = f"{result['sha256']}  pql-audit.json\n"
    assert sha_line == expected


def test_export_manifest_carries_filters_and_count(tmp_path: Path) -> None:
    _seed_audit_rows(4)
    factory = app.state.session_factory
    out = tmp_path / "filtered.json"
    result = export_audit_to_files(
        factory,
        out=out,
        fmt="json",
        filters=ExportFilters(
            since=None,
            until=None,
            action="catalog.viewed",
            actor="alice-1",
            target=None,
        ),
    )
    manifest = json.loads(
        Path(result["manifest_path"]).read_text(encoding="utf-8")
    )
    assert manifest["entry_count"] == result["entry_count"]
    assert manifest["data_sha256"] == result["sha256"]
    assert manifest["fmt"] == "json"
    assert manifest["filters"]["action"] == "catalog.viewed"
    assert manifest["filters"]["actor"] == "alice-1"
    assert manifest["schema_version"] == "1"
    assert manifest["tool_version"]


def test_export_writes_mode_0600(tmp_path: Path) -> None:
    _seed_audit_rows(1)
    factory = app.state.session_factory
    out = tmp_path / "p.json"
    result = export_audit_to_files(
        factory,
        out=out,
        fmt="json",
        filters=ExportFilters(
            since=None, until=None, action=None, actor=None, target=None
        ),
    )
    for path_key in ("data_path", "sha256_path", "manifest_path"):
        path = Path(result[path_key])
        mode = stat.S_IMODE(path.stat().st_mode)
        # Mode should equal 0o600 (owner read+write only).
        assert mode == 0o600, f"{path_key} has mode {oct(mode)}"


def test_export_csv_round_trip(tmp_path: Path) -> None:
    _seed_audit_rows(2)
    factory = app.state.session_factory
    out = tmp_path / "data.csv"
    result = export_audit_to_files(
        factory,
        out=out,
        fmt="csv",
        filters=ExportFilters(
            since=None, until=None, action=None, actor=None, target=None
        ),
    )
    body = out.read_text(encoding="utf-8")
    # Header line + N data rows.
    lines = body.splitlines()
    assert lines[0].startswith("id,created_at,user_id")
    assert len(lines) == 1 + result["entry_count"]


@pytest.mark.asyncio
async def test_tarball_endpoint_streams_three_member_archive(
    admin_client: httpx.AsyncClient,
) -> None:
    _seed_audit_rows(3)
    resp = await admin_client.get(
        "/admin/audit/export.tar.gz?fmt=json&since=all"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/gzip"
    tar = tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz")
    members = tar.getnames()
    sha_members = [m for m in members if m.endswith(".sha256")]
    manifest_members = [m for m in members if m.endswith(".manifest.json")]
    data_members = [
        m for m in members
        if m not in sha_members and m not in manifest_members
    ]
    assert len(data_members) == 1
    assert len(sha_members) == 1
    assert len(manifest_members) == 1
    # Manifest's data_sha256 must match the actual sha of the data file.
    data_file = tar.extractfile(data_members[0])
    manifest_file = tar.extractfile(manifest_members[0])
    assert data_file is not None
    assert manifest_file is not None
    data_bytes = data_file.read()
    manifest = json.loads(manifest_file.read())
    assert manifest["data_sha256"] == hashlib.sha256(data_bytes).hexdigest()
    assert manifest["entry_count"] >= 3
