# Concepts

Deep-dive pages on how PointlesSQL is built and how it behaves.

Already filled in:

- [Auth](auth.md) — session cookies, API keys, scopes
- [Data layers](data-layers.md) — bronze / silver / gold
  medallion default and how to override
- [PII modes](pii-modes.md) — value-change masking modes

Sprint 22.2 will add: Architecture (component graph + sequence
diagrams), Audit trail (cells / operations / queries 3-level
model), Lineage (row → column → value → inference chain), Agent
supervision (Family A/B/C tiers + the four daily bots).
