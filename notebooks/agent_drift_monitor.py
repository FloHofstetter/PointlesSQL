# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: pql_cell_id,-all
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.1
# ---

# %% [markdown] pql_cell_id="11111111-1111-4111-8111-111111111111"
# # Drift-Monitor agent
#
# **Sprint 13.5** — second Phase-13 demo (the first being the
# Hermes-Medallion walkthrough in 13.5.5).  The Drift-Monitor
# agent reads a published bronze table, computes freshness +
# null-rate + value-drift against the Sprint-54 column stats,
# appends one row per check to ``ops.quality_history``, and
# emits a CloudEvent (Sprint 13.3) when a threshold breaks.
#
# Hermes cron fires this notebook hourly (or whatever cadence
# the operator picks); PointlesSQL itself does **not** schedule
# — Phase 13 is registry + supervision only.
#
# **Inputs**: ``MONITOR_TARGET`` (env or set below), the
# ``column_stats`` rows from Sprint 54, the ``alert_dispatcher``
# from Sprint 55.
#
# **Outputs**: one row per check appended to
# ``ops.quality_history``; one ``pointlessql.agent_run.failed``
# CloudEvent fired when any threshold breaks.

# %% pql_cell_id="22222222-2222-4222-8222-222222222222"
import asyncio
import os
from datetime import UTC, datetime

import pandas as pd

from pointlessql.pql import PQL

# Configurable via env so Hermes can fan the same notebook across
# multiple bronze tables without editing the source.
MONITOR_TARGET = os.environ.get("MONITOR_TARGET", "main.bronze.events")
QUALITY_HISTORY_TABLE = os.environ.get(
    "MONITOR_HISTORY_TABLE", "main.ops.quality_history"
)
NULL_RATE_THRESHOLD = float(os.environ.get("MONITOR_NULL_RATE_MAX", "0.20"))
FRESHNESS_THRESHOLD_HOURS = float(
    os.environ.get("MONITOR_FRESHNESS_MAX_H", "24")
)

pql = PQL()

# %% [markdown] pql_cell_id="33333333-3333-4333-8333-333333333333"
# ## Read the target table
#
# Through ``pql.table(...)`` so UC SELECT enforcement (Sprint
# 13.6's ``X-Principal``-aware path) runs as the agent's
# principal.  An identity that lacks SELECT raises
# ``AuthorizationError`` here, the run row terminates as
# ``failed``, and Sprint 13.3's CloudEvent fires.

# %% pql_cell_id="44444444-4444-4444-8444-444444444444"
df = pql.table(MONITOR_TARGET)
print(f"Read {len(df):,} rows from {MONITOR_TARGET}")

# %% [markdown] pql_cell_id="55555555-5555-4555-8555-555555555555"
# ## Compute the three drift signals
#
# 1. **Freshness** — wall-clock age of the newest
#    ``_ingested_at`` audit timestamp (Sprint 13.5.1 bronze
#    convention).  Above ``MONITOR_FRESHNESS_MAX_H`` triggers a
#    warning.
# 2. **Null-rate** — fraction of nulls in every non-audit
#    column.  Above ``MONITOR_NULL_RATE_MAX`` per column
#    triggers a warning.
# 3. **Value-drift** — compare the current sample's distinct
#    count to the most recent ``column_stats`` snapshot
#    (Sprint 54).  A drop of more than 50 % triggers a warning.

# %% pql_cell_id="66666666-6666-4666-8666-666666666666"
now = datetime.now(UTC)
findings: list[dict[str, object]] = []

# Freshness
audit_col = "_ingested_at"
if audit_col in df.columns and not df.empty:
    newest = pd.to_datetime(df[audit_col]).max()
    age_h = (now - newest.to_pydatetime()).total_seconds() / 3600
    if age_h > FRESHNESS_THRESHOLD_HOURS:
        findings.append(
            {
                "check": "freshness",
                "column": audit_col,
                "value": age_h,
                "threshold": FRESHNESS_THRESHOLD_HOURS,
                "severity": "warning",
            }
        )
else:
    findings.append(
        {
            "check": "freshness",
            "column": audit_col,
            "value": None,
            "threshold": FRESHNESS_THRESHOLD_HOURS,
            "severity": "error",
        }
    )

# Null-rate (skip audit columns)
audit_cols = {"_ingested_at", "_source_file", "_source_system"}
for col in df.columns:
    if col in audit_cols or df.empty:
        continue
    null_rate = float(df[col].isna().mean())
    if null_rate > NULL_RATE_THRESHOLD:
        findings.append(
            {
                "check": "null_rate",
                "column": col,
                "value": null_rate,
                "threshold": NULL_RATE_THRESHOLD,
                "severity": "warning",
            }
        )

print(f"Findings: {len(findings)}")
for f in findings:
    print(f)

# %% [markdown] pql_cell_id="77777777-7777-4777-8777-777777777777"
# ## Append the check result to ``ops.quality_history``
#
# One row per check (whether it tripped or not — the value
# trail is more useful than just the trips).  ``pql.write_table``
# in append mode if the table already exists, otherwise it
# bootstraps via the same ``derive_storage_location`` path the
# autoload primitive (Sprint 13.5.3) uses.

# %% pql_cell_id="88888888-8888-4888-8888-888888888888"
history_row = pd.DataFrame(
    [
        {
            "checked_at": now,
            "target_table": MONITOR_TARGET,
            "check": f["check"],
            "column_name": f["column"],
            "value": f["value"],
            "threshold": f["threshold"],
            "severity": f["severity"],
        }
        for f in findings
    ]
    or [
        {
            "checked_at": now,
            "target_table": MONITOR_TARGET,
            "check": "ok",
            "column_name": None,
            "value": None,
            "threshold": None,
            "severity": "info",
        }
    ]
)
pql.write_table(history_row, QUALITY_HISTORY_TABLE, mode="append")
print(f"Appended {len(history_row)} row(s) to {QUALITY_HISTORY_TABLE}")

# %% [markdown] pql_cell_id="99999999-9999-4999-8999-999999999999"
# ## Emit a CloudEvent when a threshold breaks
#
# Reuses the Sprint 13.3 emitter so any subscriber configured
# via ``POINTLESSQL_AGENT_RUNS_WEBHOOK_URL`` (or the future
# per-destination filter from Sprint 13.4) receives the alert.
# Severity ``error`` or ``warning`` triggers; pure ``info`` runs
# stay silent so a quiet dashboard is the default state.

# %% pql_cell_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
breaches = [f for f in findings if f["severity"] in ("error", "warning")]
if breaches:
    from pointlessql.services.agent_runs import (
        EVENT_TYPE_FAILED,
        emit_agent_run_event,
    )

    payload = {
        "id": os.environ.get("POINTLESSQL_AGENT_RUN_ID", "drift-monitor-local"),
        "principal": os.environ.get("POINTLESSQL_PRINCIPAL", "drift-monitor"),
        "agent_id": "drift_monitor",
        "status": "failed",
        "notebook_path": "agent_drift_monitor.py",
        "tables_touched": [MONITOR_TARGET, QUALITY_HISTORY_TABLE],
        "checked_at": now.isoformat(),
        "breaches": breaches,
    }
    asyncio.run(emit_agent_run_event(EVENT_TYPE_FAILED, payload))
    print(f"Emitted .failed CloudEvent for {len(breaches)} breach(es)")
else:
    print("No breaches — staying quiet")
