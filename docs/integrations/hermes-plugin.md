# Hermes plugin

[`hermes-plugin-pointlessql`](https://github.com/FloHofstetter/hermes-plugin-pointlessql)
is the agent-side surface for PointlesSQL.  An httpx-only
plugin (~1200 LOC client + ~50 tools) that registers Family
A/B/C tools at session start based on env-var flags.

## Install

```bash
git clone git@github.com:FloHofstetter/hermes-plugin-pointlessql.git \
  ~/git/hermes-plugin-pointlessql
cd ~/git/hermes-plugin-pointlessql
uv sync
```

Add to `~/.hermes/config.toml`:

```toml
[[plugins]]
path = "/home/<you>/git/hermes-plugin-pointlessql/hermes_plugin_pointlessql"
```

Wire env in `~/.hermes/.env`:

```bash
POINTLESSQL_BASE_URL=http://127.0.0.1:8000
POINTLESSQL_API_KEY=<token>
# Optional family gates:
POINTLESSQL_SUPERVISOR_MODE=1   # registers 4 supervisor tools
POINTLESSQL_AUDITOR_MODE=1      # registers 22 auditor tools
```

For the full bring-up, see the
[Agent bring-up recipe](../guides/agent-bring-up.md).

## Tool count by family

| Family | Tools | Gate | Examples |
|---|---|---|---|
| **A — Always-on** | 16 | none | `pql_list_catalogs`, `pql_list_schemas`, `pql_list_tables`, `pql_get_table`, `pql_get_run`, `pql_log_training_run`, `pql_list_models`, `pql_get_model`, `pql_get_model_predictions`, `pql_get_model_lineage`, `pql_get_model_runs`, `pql_get_promotion_history`, `pql_autoload`, `pql_write_table`, `pql_merge`, `pql_drop_table` |
| **B — Supervisor** | 4 | `POINTLESSQL_SUPERVISOR_MODE=1` | `pql_promote_model`, `pql_rollback`, `pql_post_audit_review`, `pql_branch_promote` |
| **C — Auditor** | 22 | `POINTLESSQL_AUDITOR_MODE=1` | `pql_audit_summary`, `pql_anomaly_check`, `pql_list_recent_runs`, `pql_query_history_audit`, `pql_query_row_lineage`, `pql_query_column_lineage`, `pql_query_value_changes`, `pql_query_rejects`, `pql_query_external_writes`, ... |

Total: **42 tools** post-Sprint 21.8 (was 16 in Sprint 13.11.4
when the plugin was first built; nine sub-sprints worth of
extensions since).

## Conventions

Every tool follows the same shape:

```python
_SCHEMA = {
    "name": "pql_<verb>",
    "description": "Args:\n  ...\nExample:\n  ...",
    "input_schema": {...},  # JSONSchema
}

def build_handler(client):
    def handler(args):
        # validate args via arg_error envelopes
        # call client method
        # return run() envelope
    return handler

def register(ctx, client):
    ctx.register_tool(_SCHEMA, build_handler(client))
```

Errors are returned as `{"ok": false, "error": "...", "detail": "..."}`
envelopes (mirrors the server's error contract).  Validation
errors become `arg_error` envelopes with `field`, `expected`,
`hint` fields so the LLM can self-correct.

See [`tools/_common.py`](https://github.com/FloHofstetter/hermes-plugin-pointlessql/blob/main/hermes_plugin_pointlessql/tools/_common.py)
for the shared helpers.

## Lifecycle hooks

The plugin's `lifecycle.pre_llm_call` hook resurrects the
`POINTLESSQL_AGENT_RUN_ID` env var per turn.  This is what
makes operations stamped with the run id work even when the
agent's session crosses LLM round-trips.

Without this hook, the run id would only be set in the parent
process and not visible inside the plugin's httpx call — the
audit row would attribute to "external".

## Why httpx, not import

The plugin is **httpx-only**.  It does **not** import
PointlesSQL Python.  Two reasons:

1. **Process boundary** — the agent runtime might be a
   different Python version, in a different container, on a
   different host.  HTTP is the universal lingua franca.
2. **Deployment isolation** — bumping PointlesSQL doesn't
   force a plugin reinstall.  As long as the REST contract
   stays compatible, the plugin keeps working.

The cost is that the plugin can't share Python objects with
PointlesSQL — no shared connection pool, no shared SQLAlchemy
session.  That's fine for an agent-side surface.

## Where to read next

- [Hermes jobs index](hermes-jobs/README.md) — the four
  canonical bot personas + manifest format
- [Agent bring-up](../guides/agent-bring-up.md) — bring up an
  agent end-to-end in 30 minutes
- [Permissions](../reference/permissions.md) — what each
  family / scope can do
- [Plugin repo](https://github.com/FloHofstetter/hermes-plugin-pointlessql)
  (private during Phase 22; public after the launch sprint)
