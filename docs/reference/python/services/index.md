# Service modules

Internal modules you'd call from an admin script or a custom
plugin. Most users go through the [`PQL` class](../pql/index.md)
instead.

Five modules are documented here:

- **[Operations](operations.md)** — the `record_operation`
  context manager every PQL write-side primitive uses to
  emit its audit row. Exposed for custom operations (e.g. a
  job-kind plugin that wants the same audit shape).
- **[Training context](training_context.md)** — the
  `mlflow.autolog`-wrapping context manager that captures
  hyperparameters, metrics, and hardware fingerprint on every
  model training run.
- **[Audit](audit.md)** — the base audit-log writer. Every
  privileged action goes through `audit()` to emit a row that
  downstream sinks (audit stream, Grafana dashboards) can read.
- **[Branch tags](branch_tags.md)** — Delta-branching at the
  service layer: branch / promote / discard plus the
  conflict-detection that makes promotion fail-loud. Sits
  beneath the [`pql.branch`](../pql/branching.md) primitives.
- **[MLflow subprocess](mlflow_subprocess.md)** — lazy-spawned
  MLflow Tracking subprocess. Lifespan-managed by the FastAPI
  app; never started until a notebook or training-context call
  needs it.
