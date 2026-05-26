# Engines

The engine abstraction lets the same `PQL` facade run over
different DataFrame backends (pandas, DuckDB, polars) without the
caller noticing. `make_engine()` is the name-keyed factory; each
concrete `Engine` implementation is exported for direct
instantiation when type-narrowing matters.

`register_delta_view()` registers a Delta table as a queryable
view inside a DuckDB connection — used by the SQL routes and
table-stats services to expose UC-managed Delta tables to
ad-hoc SQL.

::: pointlessql.pql.engine
    options:
      show_root_heading: false
      filters:
        - "!^_"
