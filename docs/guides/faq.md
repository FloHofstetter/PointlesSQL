# FAQ

Non-error questions that come up often.

## What

### What is PointlesSQL, in one sentence?

A web UI and Python bridge over Unity Catalog (via soyuz-
catalog), Delta Lake, and MLflow — with a forced audit trail
every agent action falls into.

### Is PointlesSQL a Databricks replacement?

No. PointlesSQL covers the **management plane and audit
record** of a small lakehouse. It does not replace Spark, the
DBSQL warehouse engine, or Unity Catalog (the Databricks
proprietary edition). The Python-only stack tops out at ~100 GB
working sets — see
[Architecture → Why Python-only](../concepts/architecture.md#why-python-only).

### Is it production-ready?

**Alpha.** All features have e2e tests + walkthroughs
and run reliably on Flo's daily-driver setup. But the
project is < 1 year old, the user count is 1, and the public
docs site (this site) is brand-new. Expect rough edges and
breaking changes between minor versions.

### Why "PointlesSQL"?

A self-deprecating name — the joke being that there's nothing
"pointless" about an audited Python lakehouse, but the
abbreviation reads well. Also a Databricks pun.

### Who built it?

[Florian Hofstetter](https://github.com/FloHofstetter). See
the [Relationship to other repos](https://github.com/FloHofstetter/PointlesSQL/blob/main/README.md#relationship-to-other-repos)
section for the four-repo ecosystem
(soyuz-catalog · PointlesSQL · shoreguard · hermes plugin).

## Why this and not …

### Why not vanilla Unity Catalog + DBR?

Closed-source proprietary stack. PointlesSQL is Apache-2.0 with
no JVM dependency.

### Why not raw Delta + DuckDB?

You'd build the catalog browser, the audit trail, the lineage
chain, the supervisor model, and the model-registry surface
yourself. PointlesSQL is opinionated defaults for those
specifically.

### Why not Snowflake or BigQuery?

Different layer. Snowflake/BigQuery own compute + storage +
catalog. PointlesSQL is the management plane on top of *your
own* storage + UC. The [Concepts overview](../getting-started/concepts.md)
table compares them directly.

### Why not Iceberg?

Delta Lake first because soyuz-catalog speaks UC's REST API and
UC's `delta` profile is mature. Iceberg support is unscheduled
— not opposed, just not started.

### Why not Airflow / Dagster for orchestration?

PointlesSQL ships an in-process scheduler for cron-shaped Python
jobs. For full DAG orchestration, you'd run Airflow or Dagster
*alongside* PointlesSQL — they call the PQL bridge from inside
their tasks. See [Jobs](jobs.md).

## How

### How do I add a new agent to the audit loop?

Read the [agent bring-up recipe](agent-bring-up.md). ~30
minutes end-to-end.

### How do I roll back a bad ETL?

Find the run → **Rollback preview** → admin-only **Execute
rollback**. See [rollback walkthrough](../e2e-walkthroughs/rollback.md).

### How do I change the data layer conventions?

Set `POINTLESSQL_CONVENTIONS_PATH=/path/to/pointlessql.yaml` and
override the medallion defaults. See
[Data layers](../concepts/data-layers.md).

### How do I expose PointlesSQL to the public internet?

You shouldn't, in this version. No tenant isolation, no
deny-by-default ACLs, no rate-limit on the data plane.
Designed for trusted-network deployment (corporate VPN, internal
k8s). Public-facing hardening is a + topic.

### How do I back up the metadata DB?

It's just SQLite or Postgres. For SQLite:
`docker compose exec pointlessql sqlite3 /app/data/pointlessql.db
".backup /app/data/backup.db"`. For Postgres:
`pg_dump --format=custom`.

### Can I run two PointlesSQL instances against the same lakehouse?

Two `pointlessql` processes against the same soyuz-catalog and
the same Delta files — yes, because each PointlesSQL only
*reads* the lakehouse. Two PointlesSQL instances each writing
to their own metadata DB but pointing at the same Delta files
would have **conflicting audit trails** for the same Delta
versions. Don't do that.

## When

### When will the docs site go public?

The docs site is published to GitHub Pages as part of the public
launch. Until then, browse the Markdown sources under `docs/` or
run `uv run --group docs --no-default-groups mkdocs serve` locally.

### When will PointlesSQL hit `1.0.0`?

After the launch sprint and at least one external user runs
through the install flow on a clean machine. No earlier.

### When does the daily Audit-Reviewer fire?

`0 6 * * *` (06:00 UTC daily) by default. Configure via the
manifest's `cron` field at
[`docs/integrations/hermes-jobs/audit-reviewer-daily.json`](../integrations/hermes-jobs/audit-reviewer-daily.json).

## Should I

### Should I store secrets in `.env`?

Yes for development, **no** in production. Every env-var
through to `Settings()` is read at instantiation; secrets-
management (Vault / SSM / AWS Secrets Manager) is on you.

### Should I run PointlesSQL behind a reverse proxy?

Recommended for any non-localhost deployment. Set
`POINTLESSQL_RATE_LIMIT_TRUST_X_FORWARDED_FOR=true` only when
the proxy itself is trusted to set that header.

### Should I expose `/metrics` publicly?

No — admin-only by default. Prometheus scrape it from inside
the trusted network using a service-account API key with admin
scope, or run a `/metrics` proxy.

### Should I add my own custom audit tables?

Probably not — extend the `agent_run_events` `event_type`
discriminator instead. See
[Audit trail → CloudEvents](../concepts/audit-trail.md).

### Should I commit `.env`?

**No.** `.env` is in `.gitignore` for a reason. Use
`.env.example` as the template + your secrets manager.

## Where to read next

- [Concepts overview](../getting-started/concepts.md) — the
 ten-minute mental model
- [Architecture](../concepts/architecture.md) — system design
- [Troubleshooting](troubleshooting.md) — when things break
- [Operator cookbook](operator-cookbook.md) — proactive
 recipes
- [GitHub repo](https://github.com/FloHofstetter/PointlesSQL) —
 source, ROADMAP, CHANGELOG
