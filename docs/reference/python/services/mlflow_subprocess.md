# MLflow subprocess

Lazy-spawned MLflow Tracking subprocess. Lifespan-managed by the
FastAPI app; never started until a notebook or training-context
call needs it.

::: pointlessql.services.mlflow_subprocess
    options:
      show_root_heading: false
      filters:
        - "!^_"
