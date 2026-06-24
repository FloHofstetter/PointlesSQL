"""Pydantic request / response models for ``/api/sql/vector_search/*``."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# The column name becomes a path segment in ``_vss/<column>.duckdb``; a
# separator or ``..`` would let a request read/unlink files outside the
# index directory, so restrict it to a plain identifier.
_VECTOR_COLUMN_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,255}$")


def _check_vector_column(value: str) -> str:
    """Reject a vector-search column that is not a plain identifier.

    Args:
        value: The proposed column name.

    Returns:
        The value unchanged when safe.

    Raises:
        ValueError: When the name carries a path separator or other
            non-identifier character.
    """
    if not _VECTOR_COLUMN_RE.match(value):
        raise ValueError(
            "column must be a plain identifier (letters, digits, '_' or '-'); "
            "path separators are not allowed"
        )
    return value


class VectorSearchRequest(BaseModel):
    """Body for ``POST /api/sql/vector_search``."""

    table: str = Field(..., description="Three-part UC FQN: catalog.schema.table.")
    column: str = Field(..., description="Indexed text column on the table.")

    _validate_column = field_validator("column")(_check_vector_column)
    query: str = Field(..., min_length=1, description="Free-text query string.")
    top_k: int = Field(10, ge=1, le=200, description="Number of hits to return.")
    hybrid: bool = Field(
        False,
        description="Fuse vector similarity with keyword relevance (RRF) before ranking.",
    )


class VectorSearchHit(BaseModel):
    """One result row in a vector-search response."""

    score: float
    pk: dict[str, Any]
    snippet: str
    keyword_score: float | None = None
    fused_score: float | None = None


class VectorSearchResponse(BaseModel):
    """Response shape for ``POST /api/sql/vector_search``."""

    table: str
    column: str
    model: str
    embedder: str
    metric: str
    delta_version_indexed: int
    hits: list[VectorSearchHit]


class VectorIndexCreateRequest(BaseModel):
    """Body for ``POST /api/sql/vector_search/indices``."""

    table: str
    column: str
    model: str = "all-MiniLM-L6-v2"
    embedder: str = "sentence_transformers"

    _validate_column = field_validator("column")(_check_vector_column)
    metric: Literal["cosine", "l2", "ip"] = "cosine"
    hnsw_m: int = Field(16, ge=4, le=128)
    hnsw_ef_construction: int = Field(128, ge=16, le=1024)
    rebuild: bool = False


class VectorIndexSummary(BaseModel):
    """One row in the index listing response."""

    id: int
    table: str
    column: str
    dim: int
    model: str
    embedder: str
    metric: str
    delta_version_indexed: int | None
    last_built_at: str | None
    last_built_rows: int | None
    last_error: str | None
