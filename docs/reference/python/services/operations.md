# Operations

The `record_operation` context manager every PQL write-side
primitive uses to write its audit row. Exposed for custom
operations (e.g. a job-kind plugin that wants the same audit
shape).

::: pointlessql.services.agent_runs.operations
    options:
      show_root_heading: false
      filters:
        - "!^_"
