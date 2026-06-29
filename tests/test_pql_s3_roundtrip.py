"""Integration round-trip for Delta tables on S3-compatible object storage.

Exercises the real engine + helper threading (``engine.read``/``write``,
``safe_delta_version``, the merge strategy) against a *live* S3 endpoint —
write, append, time-travel by version, and upsert — proving the
``storage_options`` plumbing actually reads and writes ``s3://`` Delta.

A real server is required: the deltalake Rust reader issues HTTP Range
GETs that mock S3 (moto) does not honour, so this targets a SeaweedFS (or
any S3-compatible) endpoint supplied via env and **skips** when none is
configured — the same opt-in shape as the live-soyuz integration tests.

Env contract (set by the CI ``integration`` job's SeaweedFS service, or a
local ``docker compose`` S3 service):

* ``POINTLESSQL_TEST_S3_ENDPOINT``    e.g. ``http://127.0.0.1:8333``
* ``POINTLESSQL_TEST_S3_ACCESS_KEY``  (default ``pointlessql``)
* ``POINTLESSQL_TEST_S3_SECRET_KEY``  (default ``pointlessql``)
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pandas as pd
import pytest

pytestmark = pytest.mark.integration

boto3 = pytest.importorskip("boto3")

_ENDPOINT = os.environ.get("POINTLESSQL_TEST_S3_ENDPOINT")
_ACCESS_KEY = os.environ.get("POINTLESSQL_TEST_S3_ACCESS_KEY", "pointlessql")
_SECRET_KEY = os.environ.get("POINTLESSQL_TEST_S3_SECRET_KEY", "pointlessql")

if not _ENDPOINT:
    pytest.skip(
        "POINTLESSQL_TEST_S3_ENDPOINT unset — no S3 endpoint to test against",
        allow_module_level=True,
    )


@pytest.fixture
def s3_table(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Provision a fresh bucket + table prefix and configure the resolver.

    Creates a uniquely-named bucket on the test S3 endpoint, points the
    object-store settings at that endpoint (so the default resolver vends
    the right ``storage_options``), and yields the ``s3://`` table URI.

    Yields:
        The ``s3://bucket/tbl`` storage location for the test table.
    """
    from pointlessql.config import reset_settings_cache

    bucket = f"pql-test-{uuid.uuid4().hex[:12]}"
    s3 = boto3.client(
        "s3",
        endpoint_url=_ENDPOINT,
        aws_access_key_id=_ACCESS_KEY,
        aws_secret_access_key=_SECRET_KEY,
        region_name="us-east-1",
    )
    s3.create_bucket(Bucket=bucket)

    monkeypatch.setenv("POINTLESSQL_OBJECT_STORE_S3_ENDPOINT_URL", _ENDPOINT)
    monkeypatch.setenv("POINTLESSQL_OBJECT_STORE_S3_ACCESS_KEY_ID", _ACCESS_KEY)
    monkeypatch.setenv("POINTLESSQL_OBJECT_STORE_S3_SECRET_ACCESS_KEY", _SECRET_KEY)
    monkeypatch.setenv("POINTLESSQL_OBJECT_STORE_S3_ALLOW_HTTP", "true")
    monkeypatch.setenv("POINTLESSQL_OBJECT_STORE_S3_ALLOW_UNSAFE_RENAME", "true")
    reset_settings_cache()

    yield f"s3://{bucket}/tbl"


def test_engine_write_read_append(s3_table: str) -> None:
    """Overwrite then append round-trip through the pandas engine on S3."""
    from pointlessql.pql._write import safe_delta_version
    from pointlessql.pql.engine import make_engine

    engine = make_engine("pandas")
    engine.write(pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}), s3_table, "overwrite")

    back = engine.read(s3_table)
    assert sorted(back["a"].tolist()) == [1, 2, 3]
    assert safe_delta_version(s3_table) == 0

    engine.write(pd.DataFrame({"a": [4], "b": ["w"]}), s3_table, "append")
    assert len(engine.read(s3_table)) == 4
    assert safe_delta_version(s3_table) == 1


def test_time_travel_by_version(s3_table: str) -> None:
    """An older version is still readable via deltalake on S3."""
    import deltalake

    from pointlessql.pql._storage_options import storage_options_for
    from pointlessql.pql.engine import make_engine

    engine = make_engine("pandas")
    engine.write(pd.DataFrame({"a": [1, 2]}), s3_table, "overwrite")
    engine.write(pd.DataFrame({"a": [9]}), s3_table, "append")

    dt = deltalake.DeltaTable(s3_table, storage_options=storage_options_for(s3_table))
    dt.load_as_version(0)
    assert sorted(dt.to_pandas()["a"].tolist()) == [1, 2]


def test_merge_upsert(s3_table: str) -> None:
    """The upsert merge strategy commits against an S3 Delta table."""
    import pyarrow as pa

    from pointlessql.pql._merge._strategies import _do_upsert
    from pointlessql.pql.engine import make_engine

    engine = make_engine("pandas")
    engine.write(pd.DataFrame({"id": [1, 2], "v": ["a", "b"]}), s3_table, "overwrite")

    source = pa.table({"id": [2, 3], "v": ["B", "c"]})
    _do_upsert(s3_table, source, on=["id"])

    rows = {r["id"]: r["v"] for _, r in engine.read(s3_table).iterrows()}
    assert rows == {1: "a", 2: "B", 3: "c"}
