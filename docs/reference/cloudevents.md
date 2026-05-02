# CloudEvents reference

Every interesting state change in PointlesSQL fans out as a
[CloudEvents 1.0](https://cloudevents.io/) envelope, posted to
the configured webhook destinations. This page lists every
`type` PointlesSQL emits, with payload schema and example.

## Envelope shape

All events share the same envelope:

```json
{
 "specversion": "1.0",
 "type": "pointlessql.<domain>.<verb>",
 "source": "/api/<endpoint-path>",
 "id": "<unique-id>",
 "time": "2026-04-30T12:34:56Z",
 "datacontenttype": "application/json",
 "data": {... type-specific payload... }
}
```

Webhook destinations sign the body with HMAC-SHA-256 using the
optional `webhook_hmac_secret` (sub-model
[`AuditStreamSettings`](configuration.md#audit-stream-forwarder)
or
[`AgentRunsSettings`](configuration.md#agent-run-lifecycle-webhooks)).
The signature lands in `X-PointlesSQL-Signature: sha256=<hex>`.

## Event types

PointlesSQL currently emits **12** event types across five
domains. + candidates (drift alerts, dataset
certification) will add more.

### Agent-run lifecycle

| Type | Fired when | Source |
|---|---|---|
| `pointlessql.agent_run.started` | agent run row INSERTed (PQL constructor or plugin pre_llm_call) | `/api/runs` |
| `pointlessql.agent_run.completed` | run finished cleanly with `exit_code=0` | `/api/runs/<id>` |
| `pointlessql.agent_run.failed` | run finished with `exit_code != 0` | `/api/runs/<id>` |
| `pointlessql.agent_run.tool_call` | `agent_run_tool_calls` row INSERTed (from plugin lifecycle hook) | `/api/runs/<id>/tool-calls` |

Example payload (`agent_run.completed`):

```json
{
 "run_id": "r-2026-04-30-1",
 "principal": "agent-claude-sonnet",
 "agent_id": "hermes:bot-7",
 "started_at": "2026-04-30T11:22:00Z",
 "finished_at": "2026-04-30T11:32:14Z",
 "exit_code": 0,
 "tables_touched": ["demo.gold.daily_summary"],
 "cost_est": "0.0234"
}
```

### Cost gate

| Type | Fired when |
|---|---|
| `pointlessql.cost_gate.denied` | DuckDB EXPLAIN row estimate ≥ `POINTLESSQL_SQL_COST_GATE_THRESHOLD_ROWS` and the user did not confirm |

Example:

```json
{
 "run_id": "r-2026-04-30-1",
 "query": "SELECT * FROM demo.silver.events",
 "estimated_rows": 12345678,
 "threshold": 1000000,
 "denied_at": "2026-04-30T11:25:33Z"
}
```

### Rollback

| Type | Fired when |
|---|---|
| `pointlessql.rollback.executed` | admin executes `pql.rollback(run_id=...)` and the Delta restore commits |

Example:

```json
{
 "run_id": "r-2026-04-29-3",
 "table_fqn": "demo.gold.daily_summary",
 "delta_version_before": 42,
 "delta_version_after_restore": 42,
 "rolled_back_by": "admin@example.com",
 "rolled_back_at": "2026-04-30T13:00:00Z",
 "reason": "ETL bug — negative amounts not filtered"
}
```

### Lineage retention

| Type | Fired when |
|---|---|
| `pointlessql.lineage.pruned` | scheduler tick deletes rows older than the per-axis TTL |

Example:

```json
{
 "axis": "value_changes",
 "rows_deleted": 12345,
 "ttl_days": 730,
 "pruned_at": "2026-04-30T03:00:00Z"
}
```

### External-write detection

| Type | Fired when |
|---|---|
| `pointlessql.external_write.detected` | scanner finds a Delta commit not matched by any `agent_run_operations` row |

Example:

```json
{
 "table_fqn": "demo.silver.events",
 "delta_version": 99,
 "operation": "WRITE",
 "user_metadata": "{\"job\": \"upstream-spark-pipe\"}",
 "detected_at": "2026-04-30T13:15:00Z"
}
```

### Policy violations

| Type | Fired when |
|---|---|
| `pointlessql.policy.violated` | a write hits a guard (e.g. PQL writes outside the run-context, missing source_table_fqn on a derived write) |

### Audit export

| Type | Fired when |
|---|---|
| `pointlessql.audit_export.issued` | admin exports an audit-cockpit slice to CSV / JSON |

### MLflow link

| Type | Fired when |
|---|---|
| `pointlessql.mlflow.linked` | `agent_run_operations` row gains `mlflow_run_id` (the cross-link bridge fires on first detect) |

Example:

```json
{
 "agent_run_id": "r-2026-04-30-1",
 "op_id": 42,
 "mlflow_run_id": "abc123def456",
 "linked_at": "2026-04-30T11:30:00Z"
}
```

### Model promotion

| Type | Fired when |
|---|---|
| `pointlessql.model.promoted` | supervisor flips champion via `/api/models/<name>/promote` |

Example:

```json
{
 "review_id": 17,
 "model_full_name": "demo.fraud.classifier",
 "previous_champion": 1,
 "champion_version": 2,
 "promoted_by": "promotion-bot@example.com",
 "promoted_at": "2026-04-30T13:30:00Z",
 "reason": "Beats v1 on val accuracy by 4 pp"
}
```

## Subscribing

Two subscription mechanisms:

1. **Single webhook URL** —
 `POINTLESSQL_AGENT_RUNS_WEBHOOK_URL` for the four
 `agent_run.*` types. Fast path; one URL only.
2. **`audit_sinks` table** — the forwarder. Multiple
 destinations, per-event-type filters, optional HMAC. See
 [audit-sinks walkthrough](../e2e-walkthroughs/audit-sinks.md).

## Stable contract

Event-type strings are part of the public API. Adding fields
to `data.*` is a backwards-compatible change; renaming a type
or removing a field is a breaking change and gets a deprecation
notice in the CHANGELOG.

## Where to read next

- [Audit-stream walkthrough](../e2e-walkthroughs/audit-sinks.md)
 — the multi-destination forwarder end-to-end
- [Configuration → Audit-stream](configuration.md#audit-stream-forwarder)
- [Agent supervision](../concepts/agent-supervision.md) — how
 the `agent_review.*` events fan out to operator dashboards
