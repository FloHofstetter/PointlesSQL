# Audit

The base audit-log writer. Every privileged action goes through
`audit()` to emit a row that downstream sinks (audit stream,
Grafana dashboards) can read.

::: pointlessql.services.audit
    options:
      show_root_heading: false
      filters:
        - "!^_"
