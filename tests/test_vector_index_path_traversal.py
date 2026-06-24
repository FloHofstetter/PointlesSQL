"""Vector-index column names cannot traverse out of the index directory.

``column`` becomes the ``_vss/<column>.duckdb`` filename, so an
unvalidated ``../`` let a request read or unlink ``.duckdb`` files
elsewhere on disk.  These tests pin the request-model validator and the
``_index_file_path`` backstop.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from pointlessql.api.sql.vector_search._models import (
    VectorIndexCreateRequest,
    VectorSearchRequest,
)
from pointlessql.pql._vector import _index_file_path  # pyright: ignore[reportPrivateUsage]

_BAD = ["../evil", "a/b", "..", "x/../y", "with space", "weird;rm", ""]


@pytest.mark.parametrize("column", _BAD)
def test_create_request_rejects_unsafe_column(column: str) -> None:
    """The create model rejects a column with a path separator."""
    with pytest.raises(ValidationError):
        VectorIndexCreateRequest(table="main.s.t", column=column)


@pytest.mark.parametrize("column", _BAD)
def test_search_request_rejects_unsafe_column(column: str) -> None:
    """The search model rejects a column with a path separator."""
    with pytest.raises(ValidationError):
        VectorSearchRequest(table="main.s.t", column=column, query="hi")


def test_index_file_path_rejects_traversal() -> None:
    """_index_file_path refuses a traversal column outright."""
    with pytest.raises(ValueError):
        _index_file_path("/data/tbl", "../../etc/evil")


def test_index_file_path_builds_under_vss() -> None:
    """A normal column resolves under the table's _vss directory."""
    path = _index_file_path("file:///data/tbl", "body_text")
    assert path == Path("/data/tbl/_vss/body_text.duckdb")
