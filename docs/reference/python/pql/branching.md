# Branching

Delta-branching primitives operate on UC schemas — a branch is a
zero-copy clone of a schema, scoped to one agent-run, into which
the agent can write freely without affecting the trunk. Promote
merges the branch back; discard throws it away. See
[ADR-0003](../../../decisions/0003-delta-branching-spike.md) for
the design.

The `pointlessql.pql.branch` module exposes the four lifecycle
operations; `pointlessql.pql._branch_errors` carries the
typed exception family that every operation can raise.

## `pointlessql.pql.branch`

::: pointlessql.pql.branch
    options:
      show_root_heading: false
      filters:
        - "!^_"

## Branch error family

::: pointlessql.pql._branch_errors
    options:
      show_root_heading: false
      filters:
        - "!^_"
