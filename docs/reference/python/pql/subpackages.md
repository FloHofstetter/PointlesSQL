# Sub-packages

Four sub-packages cover PQL-adjacent surface that is not part of
the `PQL` facade itself:

- `pointlessql.pql.context` — agent-run context binding
  (`POINTLESSQL_AGENT_RUN_ID` env var plumbing, branch-binding
  thread-local) consumed by the `PQL` constructor.
- `pointlessql.pql.facts` — fact-table helpers (pin / unpin /
  list) that surface as the in-notebook "Facts" panel.
- `pointlessql.pql.memory` — agent-memory accessors (write to /
  read from the per-agent memory store).
- `pointlessql.pql.widgets` — notebook widget primitives (the
  param-cell API the editor surfaces as parameter widgets).

## `pointlessql.pql.context`

::: pointlessql.pql.context
    options:
      show_root_heading: false
      filters:
        - "!^_"

## `pointlessql.pql.facts`

::: pointlessql.pql.facts
    options:
      show_root_heading: false
      filters:
        - "!^_"

## `pointlessql.pql.memory`

::: pointlessql.pql.memory
    options:
      show_root_heading: false
      filters:
        - "!^_"

## `pointlessql.pql.widgets`

::: pointlessql.pql.widgets
    options:
      show_root_heading: false
      filters:
        - "!^_"
