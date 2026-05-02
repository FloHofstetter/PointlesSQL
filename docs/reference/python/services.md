# Service modules

Internal modules you'd call from an admin script or a custom
plugin. Most users go through the [`PQL` class](pql.md)
instead.

## `pointlessql.services.agent_runs.operations`

The `record_operation` context manager every PQL write-side
primitive uses to write its audit row. Exposed for custom
operations (e.g. a job-kind plugin that wants the same audit
shape).

::: pointlessql.services.agent_runs.operations
 options:
 docstring_style: google
 show_root_heading: false
 show_source: false
 members_order: source
 filters:
 - "!^_"

## `pointlessql.services.agent_runs.training_context`

The `mlflow.autolog`-wrapping context manager that
captures hyperparameters + metrics + hardware fingerprint on
every model training run.

::: pointlessql.services.agent_runs.training_context
 options:
 docstring_style: google
 show_root_heading: false
 show_source: false
 members_order: source
 filters:
 - "!^_"

## `pointlessql.services.audit`

The base audit-log writer. Every privileged action goes through
`audit()` to emit a row that downstream sinks ( audit-
stream, Grafana dashboards) can read.

::: pointlessql.services.audit
 options:
 docstring_style: google
 show_root_heading: false
 show_source: false
 members_order: source
 filters:
 - "!^_"

## `pointlessql.services.branch_tags`

Delta-branching — branch / promote / discard plus
the conflict-detection that makes promotion fail-loud.

::: pointlessql.services.branch_tags
 options:
 docstring_style: google
 show_root_heading: false
 show_source: false
 members_order: source
 filters:
 - "!^_"

## `pointlessql.services.mlflow_subprocess`

Lazy-spawned MLflow Tracking subprocess. Lifespan-
managed by the FastAPI app.

::: pointlessql.services.mlflow_subprocess
 options:
 docstring_style: google
 show_root_heading: false
 show_source: false
 members_order: source
 filters:
 - "!^_"
