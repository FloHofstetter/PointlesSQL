"""Pydantic request / response models for ``/api/sql/vector_search/*``."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class VectorSearchRequest(BaseModel):
    """Body for ``POST /api/sql/vector_search``."""

    table: str = Field(..., description="Three-part UC FQN: catalog.schema.table.")
    column: str = Field(..., description="Indexed text column on the table.")
    query: str = Field(..., min_length=1, description="Free-text query string.")
    top_k: int = Field(10, ge=1, le=200, description="Number of hits to return.")


class VectorSearchHit(BaseModel):
    """One result row in a vector-search response."""

    score: float
    pk: dict[str, Any]
    snippet: str


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
