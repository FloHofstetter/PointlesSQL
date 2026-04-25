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

# %% [markdown] pql_cell_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
# # Hermes-Medallion walkthrough
#
# **Sprint 13.5.5** — the "done" moment for Phase 13 / 13.5: a real
# Hermes agent (running in a sandbox of its choice) authors a
# three-layer Medallion lakehouse from a CSV in a UC Volume,
# without any human writing transformation code.
#
# Hermes' ``terminal`` tool (or any subprocess shape) executes
# this notebook end-to-end.  Each ``pql.*`` primitive auto-emits
# an ``agent_run_operations`` row because
# ``POINTLESSQL_AGENT_RUN_ID`` was set by the
# ``hermes-plugin-pointlessql`` ``on_session_start`` hook
# (Sprint 13.7.1).
#
# **Inputs**:
#
# - ``MEDALLION_CATALOG`` (default ``main``) — UC catalog the run
#   writes into.  The Medallion schemas (``bronze`` / ``silver``
#   / ``gold``) must already exist.
# - ``MEDALLION_VOLUME_PATH`` — local-volume directory with the
#   raw orders CSV.  The walkthrough seeds it with the in-tree
#   ``notebooks/hermes_medallion_data/orders.csv``.
#
# **Outputs**:
#
# - ``main.bronze.orders_raw`` — append-only fidelity layer
#   (``pql.autoload`` injects audit columns from
#   :data:`pointlessql.conventions._defaults.DEFAULT_CONVENTIONS`).
# - ``main.silver.orders`` — deduped + typed (``pql.merge`` on
#   ``order_id`` with ``strategy="upsert"``).
# - ``main.gold.orders_summary`` — daily revenue per product
#   (``pql.sql`` aggregation).

# %% pql_cell_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
import os
from pathlib import Path

from pointlessql.pql import PQL

CATALOG = os.environ.get("MEDALLION_CATALOG", "main")
VOLUME_PATH = Path(
    os.environ.get(
        "MEDALLION_VOLUME_PATH",
        str(
            Path(__file__).resolve().parent
            / "hermes_medallion_data"
        ),
    )
)
BRONZE_TABLE = f"{CATALOG}.bronze.orders_raw"
SILVER_TABLE = f"{CATALOG}.silver.orders"
GOLD_TABLE = f"{CATALOG}.gold.orders_summary"

pql = PQL()
print(
    f"Hermes-Medallion: catalog={CATALOG}, volume={VOLUME_PATH}, "
    f"bronze={BRONZE_TABLE}, silver={SILVER_TABLE}, gold={GOLD_TABLE}"
)

# %% [markdown] pql_cell_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc"
# ## Bronze — autoload raw CSV
#
# ``pql.autoload`` scans ``VOLUME_PATH`` for files DuckDB can
# read (``read_csv_auto`` / ``read_parquet`` / ``read_json_auto``),
# de-duplicates by SHA-256 against ``autoload_checkpoints``
# (Alembic 021), injects the Sprint-13.5.1 audit columns, and
# appends to ``BRONZE_TABLE`` via ``deltalake.write_deltalake``.

# %% pql_cell_id="dddddddd-dddd-4ddd-8ddd-dddddddddddd"
bronze_result = pql.autoload(
    source=str(VOLUME_PATH),
    target=BRONZE_TABLE,
)
print(f"Bronze: {bronze_result.rows_ingested} rows added across "
      f"{bronze_result.files_ingested} file(s)")

# %% [markdown] pql_cell_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
# ## Silver — dedup + type via ``pql.merge``
#
# ``pql.merge`` runs an upsert on ``order_id`` so a re-run of the
# same source file does not produce duplicate silver rows even
# though bronze is append-only.

# %% pql_cell_id="ffffffff-ffff-4fff-8fff-ffffffffffff"
import pandas as pd  # noqa: E402 — stays inside the agent's notebook

bronze_df = pql.table(BRONZE_TABLE)
silver_source = (
    bronze_df.assign(
        qty=lambda d: pd.to_numeric(d["qty"], errors="coerce")
        .fillna(0)
        .astype(int),
        unit_price=lambda d: pd.to_numeric(
            d["unit_price"], errors="coerce"
        ).fillna(0.0),
        placed_at=lambda d: pd.to_datetime(d["placed_at"], utc=True),
    )
)
silver_result = pql.merge(
    source=silver_source,
    target=SILVER_TABLE,
    on=["order_id"],
    strategy="upsert",
)
print(f"Silver: {silver_result.rows_affected} row(s) merged")

# %% [markdown] pql_cell_id="11111111-1111-4111-8111-aaaaaaaaaaaa"
# ## Gold — aggregation via ``pql.sql``
#
# Daily revenue per product, materialised as a ``CREATE OR
# REPLACE TABLE`` so a re-run produces a fresh gold snapshot
# without manual cleanup.

# %% pql_cell_id="22222222-2222-4222-8222-bbbbbbbbbbbb"
gold_sql = f"""
CREATE OR REPLACE TABLE {GOLD_TABLE} AS
SELECT
    DATE_TRUNC('day', placed_at) AS placed_day,
    product,
    SUM(qty)               AS units_sold,
    ROUND(SUM(qty * unit_price), 2) AS revenue
FROM {SILVER_TABLE}
GROUP BY 1, 2
ORDER BY 1, 2
"""
pql.sql(gold_sql)
print(f"Gold: {GOLD_TABLE} refreshed")

# %% [markdown] pql_cell_id="33333333-3333-4333-8333-cccccccccccc"
# ## Done
#
# Open ``http://127.0.0.1:8000/runs/${POINTLESSQL_AGENT_RUN_ID}``
# in a browser to verify:
#
# - **Source** tab carries the verbatim notebook bytes + SHA.
# - **Operations** tab lists three rows
#   (``autoload`` / ``merge`` / ``sql``) with input SHAs +
#   Delta versions pre/post.
# - **Tool calls** tab lists the LLM's exploration calls
#   (``pql_conventions``, ``pql_list_tables``, …) if the
#   ``hermes-plugin-pointlessql`` ``post_tool_call`` hook is
#   wired (Sprint 13.7.4).
# - **Queries** tab shows the gold ``CREATE OR REPLACE TABLE``
#   statement plus any ad-hoc ``pql_query`` exploration the
#   LLM ran.
# - **Conformance** tab grades each layer against the
#   Sprint-13.5.4 contract (bronze must have audit columns,
#   silver must have a key, gold should stay narrow).
