"""Unit tests for the pql helper library.

All tests mock the soyuz-catalog HTTP calls so no live server is needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.list_catalogs_response import ListCatalogsResponse
from soyuz_catalog_client.models.list_schemas_response import ListSchemasResponse
from soyuz_catalog_client.models.list_tables_response import ListTablesResponse
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.models.table_info import TableInfo

from pointlessql.config import Settings
from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
    ValidationError,
)
from pointlessql.pql import PQL, DuckDBEngine, Engine, PandasEngine, PolarsEngine
from pointlessql.pql._columns import columns_from_dataframe
from pointlessql.pql._parsing import parse_full_name

# ------------------------------------------------------------------
# parse_full_name
# ------------------------------------------------------------------


class TestParseFullName:
    def test_valid_three_parts(self) -> None:
        assert parse_full_name("cat.sch.tbl") == ("cat", "sch", "tbl")

    def test_whitespace_stripping(self) -> None:
        assert parse_full_name(" cat . sch . tbl ") == ("cat", "sch", "tbl")

    def test_two_parts_raises(self) -> None:
        with pytest.raises(ValidationError, match="2 part"):
            parse_full_name("cat.sch")

    def test_four_parts_raises(self) -> None:
        with pytest.raises(ValidationError, match="4 part"):
            parse_full_name("a.b.c.d")

    def test_one_part_raises(self) -> None:
        with pytest.raises(ValidationError, match="1 part"):
            parse_full_name("table")

    def test_empty_part_raises(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            parse_full_name("cat..tbl")


# ------------------------------------------------------------------
# columns_from_dataframe
# ------------------------------------------------------------------


class TestColumnsFromDataframe:
    def test_int64_maps_to_long(self) -> None:
        df = pd.DataFrame({"x": pd.array([1], dtype="int64")})
        cols = columns_from_dataframe(df)
        assert cols[0].type_name == "LONG"
        assert cols[0].type_text == "long"

    def test_float64_maps_to_double(self) -> None:
        df = pd.DataFrame({"x": pd.array([1.0], dtype="float64")})
        cols = columns_from_dataframe(df)
        assert cols[0].type_name == "DOUBLE"
        assert cols[0].type_text == "double"

    def test_string_maps_to_string(self) -> None:
        df = pd.DataFrame({"x": ["hello"]})
        cols = columns_from_dataframe(df)
        assert cols[0].type_name == "STRING"
        assert cols[0].type_text == "string"

    def test_bool_maps_to_boolean(self) -> None:
        df = pd.DataFrame({"x": pd.array([True], dtype="bool")})
        cols = columns_from_dataframe(df)
        assert cols[0].type_name == "BOOLEAN"
        assert cols[0].type_text == "boolean"

    def test_mixed_columns_positions(self) -> None:
        df = pd.DataFrame(
            {
                "id": pd.array([1], dtype="int64"),
                "name": ["alice"],
                "score": pd.array([9.5], dtype="float64"),
            }
        )
        cols = columns_from_dataframe(df)
        assert len(cols) == 3
        assert cols[0].position == 0
        assert cols[0].name == "id"
        assert cols[1].position == 1
        assert cols[1].name == "name"
        assert cols[2].position == 2
        assert cols[2].name == "score"
        # All should be nullable and have type_json set
        for c in cols:
            assert c.nullable is True
            assert c.type_json is not None


# ------------------------------------------------------------------
# PQL constructor
# ------------------------------------------------------------------

_MOD = "pointlessql.pql.pql"
_READ = "pointlessql.pql._read"
_WRITE = "pointlessql.pql._write"
_LIST = "pointlessql.pql._list"


class TestPQLConstructor:
    @patch(f"{_MOD}.make_soyuz_client")
    def test_default_creates_client(self, mock_factory: MagicMock) -> None:
        mock_factory.return_value = MagicMock()
        pql = PQL()
        mock_factory.assert_called_once()
        assert pql._client is mock_factory.return_value

    def test_with_explicit_client(self) -> None:
        client = MagicMock()
        pql = PQL(client=client)
        assert pql._client is client

    def test_default_engine_is_pandas(self) -> None:
        pql = PQL(client=MagicMock())
        assert isinstance(pql._engine, PandasEngine)

    def test_engine_from_string(self) -> None:
        pql = PQL(client=MagicMock(), engine="duckdb")
        assert isinstance(pql._engine, DuckDBEngine)

    def test_engine_from_instance(self) -> None:
        engine = PandasEngine()
        pql = PQL(client=MagicMock(), engine=engine)
        assert pql._engine is engine

    def test_engine_polars_from_string(self) -> None:
        pql = PQL(client=MagicMock(), engine="polars")
        assert isinstance(pql._engine, PolarsEngine)

    @patch(f"{_MOD}.make_soyuz_client")
    def test_engine_polars_from_settings(self, mock_factory: MagicMock) -> None:
        mock_factory.return_value = MagicMock()
        settings = Settings(delta={"engine": "polars"})
        pql = PQL(settings=settings)
        assert isinstance(pql._engine, PolarsEngine)

    @patch(f"{_MOD}.make_soyuz_client")
    def test_engine_from_settings(self, mock_factory: MagicMock) -> None:
        mock_factory.return_value = MagicMock()
        settings = Settings(delta={"engine": "duckdb"})
        pql = PQL(settings=settings)
        assert isinstance(pql._engine, DuckDBEngine)


# ------------------------------------------------------------------
# PQL.table()
# ------------------------------------------------------------------


class TestPQLTable:
    @patch(f"{_READ}._get_table")
    def test_reads_via_engine(self, mock_get: MagicMock) -> None:
        expected_df = pd.DataFrame({"a": [1, 2]})
        mock_engine = MagicMock(spec=Engine)
        mock_engine.read.return_value = expected_df
        mock_get.sync.return_value = TableInfo(
            storage_location="/tmp/delta/tbl",
            name="tbl",
        )
        pql = PQL(client=MagicMock(), engine=mock_engine)
        result = pql.table("cat.sch.tbl")

        mock_engine.read.assert_called_once_with("/tmp/delta/tbl")
        pd.testing.assert_frame_equal(result, expected_df)

    @patch(f"{_READ}._get_table")
    def test_not_found_raises(self, mock_get: MagicMock) -> None:
        mock_get.sync.return_value = None
        pql = PQL(client=MagicMock())
        with pytest.raises(CatalogNotFoundError, match="not found"):
            pql.table("cat.sch.tbl")

    @patch(f"{_READ}._get_table")
    def test_no_storage_location_raises(self, mock_get: MagicMock) -> None:
        mock_get.sync.return_value = TableInfo(name="tbl")
        pql = PQL(client=MagicMock())
        with pytest.raises(CatalogNotFoundError, match="no storage_location"):
            pql.table("cat.sch.tbl")

    def test_invalid_name_raises(self) -> None:
        pql = PQL(client=MagicMock())
        with pytest.raises(ValidationError, match="three-part"):
            pql.table("only_two.parts")


# ------------------------------------------------------------------
# PQL.write_table()
# ------------------------------------------------------------------


class TestPQLWriteTable:
    @patch(f"{_WRITE}._get_table")
    def test_existing_table_writes_only(self, mock_get: MagicMock) -> None:
        mock_get.sync.return_value = TableInfo(
            storage_location="/data/cat/sch/tbl",
            name="tbl",
        )
        mock_engine = MagicMock(spec=Engine)
        df = pd.DataFrame({"x": [1]})

        with patch(f"{_WRITE}._create_table") as mock_create:
            pql = PQL(client=MagicMock(), engine=mock_engine)
            pql.write_table(df, "cat.sch.tbl")
            mock_engine.write.assert_called_once_with(df, "/data/cat/sch/tbl", "overwrite")
            mock_create.sync.assert_not_called()

    @patch(f"{_WRITE}._create_table")
    @patch(f"{_WRITE}._get_schema")
    @patch(f"{_WRITE}._get_table")
    def test_new_table_creates_metadata(
        self,
        mock_get_table: MagicMock,
        mock_get_schema: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        mock_get_table.sync.side_effect = UnexpectedStatus(404, b"Not Found")
        mock_get_schema.sync.return_value = SchemaInfo(
            storage_root="/data/warehouse/cat/sch",
        )
        mock_create.sync.return_value = TableInfo(name="tbl")

        mock_engine = MagicMock(spec=Engine)
        mock_engine.columns_info.return_value = [
            ("id", "LONG", "long", True),
            ("name", "STRING", "string", True),
        ]

        df = pd.DataFrame({"id": pd.array([1], dtype="int64"), "name": ["a"]})
        pql = PQL(client=MagicMock(), engine=mock_engine)
        pql.write_table(df, "cat.sch.tbl")

        mock_engine.write.assert_called_once()
        call_args = mock_engine.write.call_args
        assert call_args[0][1] == "/data/warehouse/cat/sch/tbl"

        mock_create.sync.assert_called_once()
        body = mock_create.sync.call_args.kwargs["body"]
        assert body.catalog_name == "cat"
        assert body.schema_name == "sch"
        assert body.name == "tbl"
        assert body.table_type == "MANAGED"
        assert body.data_source_format == "DELTA"
        assert body.storage_location == "/data/warehouse/cat/sch/tbl"
        assert len(body.columns) == 2

    @patch(f"{_WRITE}._get_schema")
    @patch(f"{_WRITE}._get_table")
    def test_new_table_no_schema_storage_raises(
        self, mock_get_table: MagicMock, mock_get_schema: MagicMock
    ) -> None:
        mock_get_table.sync.side_effect = UnexpectedStatus(404, b"Not Found")
        mock_get_schema.sync.return_value = SchemaInfo(name="sch")

        df = pd.DataFrame({"x": [1]})
        pql = PQL(client=MagicMock(), engine=MagicMock(spec=Engine))
        with pytest.raises(CatalogNotFoundError, match="storage_root"):
            pql.write_table(df, "cat.sch.tbl")

    @patch(f"{_WRITE}._get_table")
    def test_mode_forwarded(self, mock_get: MagicMock) -> None:
        mock_get.sync.return_value = TableInfo(storage_location="/data/tbl", name="tbl")
        mock_engine = MagicMock(spec=Engine)
        df = pd.DataFrame({"x": [1]})
        pql = PQL(client=MagicMock(), engine=mock_engine)
        pql.write_table(df, "cat.sch.tbl", mode="append")
        mock_engine.write.assert_called_once_with(df, "/data/tbl", "append")


# ------------------------------------------------------------------
# PQL.list_*()
# ------------------------------------------------------------------


class TestPQLListMethods:
    @patch(f"{_LIST}._list_catalogs")
    def test_list_catalogs(self, mock_list: MagicMock) -> None:
        cat = MagicMock()
        cat.to_dict.return_value = {"name": "my_cat"}
        mock_list.sync.return_value = ListCatalogsResponse(catalogs=[cat])
        pql = PQL(client=MagicMock())
        result = pql.list_catalogs()
        assert result == [{"name": "my_cat"}]

    @patch(f"{_LIST}._list_schemas")
    def test_list_schemas(self, mock_list: MagicMock) -> None:
        sch = MagicMock()
        sch.to_dict.return_value = {"name": "my_sch", "catalog_name": "cat"}
        mock_list.sync.return_value = ListSchemasResponse(schemas=[sch])
        pql = PQL(client=MagicMock())
        result = pql.list_schemas("cat")
        mock_list.sync.assert_called_once_with(client=pql._client, catalog_name="cat")
        assert result == [{"name": "my_sch", "catalog_name": "cat"}]

    @patch(f"{_LIST}._list_tables")
    def test_list_tables(self, mock_list: MagicMock) -> None:
        tbl = MagicMock()
        tbl.to_dict.return_value = {"name": "t1"}
        # soyuz-catalog-client ``ListTablesResponse`` renamed
        # ``identifiers`` → ``tables`` in v0.2 (matches UC's
        # ``/tables`` wire format). Keep the test in sync.
        mock_list.sync.return_value = ListTablesResponse(tables=[tbl])
        pql = PQL(client=MagicMock())
        result = pql.list_tables("cat", "sch")
        mock_list.sync.assert_called_once_with(
            client=pql._client, catalog_name="cat", schema_name="sch"
        )
        assert result == [{"name": "t1"}]


# ------------------------------------------------------------------
# PQL — ConnectionError when soyuz is unreachable
# ------------------------------------------------------------------


class TestPQLConnectionError:
    @patch(f"{_READ}._get_table")
    def test_table_raises_catalog_unavailable(self, mock_get: MagicMock) -> None:
        import httpx

        mock_get.sync.side_effect = httpx.ConnectError("Connection refused")
        client = MagicMock()
        client._base_url = "http://127.0.0.1:8080"
        pql = PQL(client=client, engine=MagicMock(spec=Engine))
        with pytest.raises(CatalogUnavailableError, match="Cannot reach soyuz-catalog"):
            pql.table("cat.sch.tbl")

    @patch(f"{_WRITE}._get_table")
    def test_write_table_raises_catalog_unavailable(self, mock_get: MagicMock) -> None:
        import httpx

        mock_get.sync.side_effect = httpx.ConnectError("Connection refused")
        client = MagicMock()
        client._base_url = "http://127.0.0.1:8080"
        pql = PQL(client=client, engine=MagicMock(spec=Engine))
        df = pd.DataFrame({"x": [1]})
        with pytest.raises(CatalogUnavailableError, match="Cannot reach soyuz-catalog"):
            pql.write_table(df, "cat.sch.tbl")
