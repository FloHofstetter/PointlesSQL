"""Declarative pipelines — CRUD + the refresh engine.

Package layout:

* ``_crud``   — pipeline/dataset persistence + validation + the DAG
  derivation (topological order from the SELECTs' table refs).
* ``_engine`` — the synchronous refresh engine: materialized views
  recompute in full, streaming tables read the source's change feed
  from a per-dataset cursor, expectations gate every batch
  (warn / drop / fail) before the governed PQL write.
"""

from __future__ import annotations

from pointlessql.services.pipelines._crud import (
    PipelineValidationError,
    create_pipeline,
    delete_pipeline,
    get_pipeline,
    list_pipelines,
    list_runs,
    parse_datasets,
    topological_order,
    update_pipeline,
    validate_datasets,
)
from pointlessql.services.pipelines._engine import (
    PipelineExpectationError,
    run_pipeline_sync,
)
from pointlessql.services.pipelines._executor import pipeline_run_executor

__all__ = [
    "PipelineExpectationError",
    "PipelineValidationError",
    "create_pipeline",
    "delete_pipeline",
    "get_pipeline",
    "list_pipelines",
    "list_runs",
    "parse_datasets",
    "pipeline_run_executor",
    "run_pipeline_sync",
    "topological_order",
    "update_pipeline",
    "validate_datasets",
]
