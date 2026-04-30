# Concepts

Deep-dive pages on how PointlesSQL is built and why.  Read in
this order if you want the full mental model:

1. **[Architecture](architecture.md)** — the four logical
   layers (routes, services, PQL bridge, storage), the
   soyuz-catalog boundary, two key sequence flows
   (`pql.write_table` and supervisor-promotes-a-model), the
   Python-only stance, and the module map.
2. **[Audit trail](audit-trail.md)** — the
   `agent_run_operations` schema, the forced-audit pattern that
   makes every PQL write replayable, the cells / operations /
   queries 3-level model, the rollback action loop, and the
   limits of what PointlesSQL records (vs what shoreguard's
   Provenance Log records).
3. **[Lineage](lineage.md)** — the four-level row → column →
   value → inference chain, when each level fires, how to walk
   the chain backwards (impact analysis) or forwards (blast
   radius), aggregate fan-in, and rejects.
4. **[Agent supervision](agent-supervision.md)** — Family A/B/C
   privilege tiers, supervisor + auditor scopes, the wake-gate
   optimisation, the `agent_reviews` table and CloudEvents
   webhook fan-out, and the four canonical bot personas.

The remaining pages are reference-style:

- **[Auth](auth.md)** — session cookies vs API keys, scope
  flags, key rotation, env-var seeding.
- **[Data layers](data-layers.md)** — Medallion conventions
  (bronze / silver / gold) and how to override the defaults
  per-namespace.
- **[PII modes](pii-modes.md)** — three masking modes for
  value-level lineage (`none`, `hash_only` default, `full`).

For implementation decisions worth re-reading later, see the
[ADR index](../decisions/index.md).
