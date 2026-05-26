# Writes &amp; contracts

Two lower-level write helpers that the `PQL` facade composes:

- `pointlessql.pql._write` — `write_table()` performs a direct
  Delta write with audit-row emission, bypassing the `PQL`
  facade when no agent-run context is in scope (data-product
  enforcement tests use this). `safe_delta_version()` returns
  the current Delta version of a storage path without
  instantiating a full `PQL` — handy when checking
  table-existence preflight conditions.
- `pointlessql.pql._contracts` — the `DraftContract` /
  `contract()` pair that records a write's schema + properties
  intent before the write happens, so a subsequent inspection
  can compare what was written against what was promised.

## `pointlessql.pql._write`

::: pointlessql.pql._write
    options:
      show_root_heading: false
      filters:
        - "!^_"
      members:
        - write_table
        - safe_delta_version

## `pointlessql.pql._contracts`

::: pointlessql.pql._contracts
    options:
      show_root_heading: false
      filters:
        - "!^_"
      members:
        - DraftContract
        - contract
