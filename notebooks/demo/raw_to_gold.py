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

# %% [markdown] pql_cell_id="00000000-0000-4000-8000-000000000001"
# # raw → gold demo agent
#
# Reads CSV files from `volumes/raw_orders/`, lifts them into
# `main.bronze.orders` with audit columns (Sprint 13.5.3 autoload),
# upserts into `main.silver.orders` (Sprint 13.5.2 merge), and
# aggregates daily revenue into `main.gold.daily_revenue`.

# %% pql_cell_id="00000000-0000-4000-8000-000000000002"
import os

from pointlessql.db import init_db

init_db("sqlite:////tmp/pql_demo/db/pointlessql.db")
from pointlessql.pql import PQL  # noqa: E402

PRINCIPAL = os.environ.get("POINTLESSQL_PRINCIPAL", "demo-agent@flo")
RAW_DIR = "/tmp/pql_demo/volumes/raw_orders"

pql = PQL(principal=PRINCIPAL)

# %% [markdown] pql_cell_id="00000000-0000-4000-8000-000000000003"
# ## Step 1 — raw → bronze (autoload, exactly-once via SHA)

# %% pql_cell_id="00000000-0000-4000-8000-000000000004"
result = pql.autoload(
    source_path=RAW_DIR,
    target="main.bronze.orders",
    source_system="shop",
    file_format="csv",
)
print(result)

# %% [markdown] pql_cell_id="00000000-0000-4000-8000-000000000005"
# ## Step 2 — bronze → silver (upsert merge on order_id)

# %% pql_cell_id="00000000-0000-4000-8000-000000000006"
bronze = pql.table("main.bronze.orders")
silver_src = bronze.drop(
    columns=["_ingested_at", "_source_file", "_source_system"], errors="ignore"
)
# Bootstrap silver with first 4 rows so merge has a target
pql.write_table(silver_src.iloc[:4].copy(), "main.silver.orders", mode="overwrite")
merge_result = pql.merge(
    source=silver_src,
    target="main.silver.orders",
    on=["order_id"],
    strategy="upsert",
)
print(
    f"upsert: inserted={merge_result['num_target_rows_inserted']}, "
    f"updated={merge_result['num_target_rows_updated']}, "
    f"copied={merge_result['num_target_rows_copied']}"
)

# %% [markdown] pql_cell_id="00000000-0000-4000-8000-000000000007"
# ## Step 3 — silver → gold (daily revenue aggregation)

# %% pql_cell_id="00000000-0000-4000-8000-000000000008"
silver = pql.table("main.silver.orders")
gold = (
    silver.assign(line_total=silver["qty"] * silver["price"])
    .groupby("order_date", as_index=False)["line_total"]
    .sum()
    .rename(columns={"line_total": "revenue"})
    .sort_values("order_date")
    .reset_index(drop=True)
)
pql.write_table(gold, "main.gold.daily_revenue", mode="overwrite")
print(gold.to_string())
