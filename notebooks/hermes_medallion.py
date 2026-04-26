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

# Sprint 13.10: PQL lazy-inits the metadata DB when a run id is
# resolved (env or kwarg), so subprocess-spawned notebooks like
# this one no longer need an explicit ``init_db`` boilerplate —
# the FastAPI-lifespan-or-bust constraint is gone for the
# Hermes terminal-tool spawn path.

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
    source_path=str(VOLUME_PATH),
    target=BRONZE_TABLE,
)
print(f"Bronze: {bronze_result['rows_ingested']} rows added across "
      f"{bronze_result['files_ingested']} file(s)")

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
# ``pql.merge`` requires the target to exist (Sprint 13.5.2 contract);
# on the very first run we fall back to ``write_table`` to bootstrap
# silver, then subsequent runs follow the upsert path.  A future
# ``pql.merge(..., create=True)`` flag would collapse this into one
# call but it is not in scope for Sprint 13.10.
#
# Sprint 15.5.3: ``track_rejects=True`` records source rows that won't
# land (NULL on-key, duplicate within source) into ``lineage_row_rejects``
# so the run-detail Reject tab can explain dropped rows.
try:
    silver_result = pql.merge(
        source=silver_source,
        target=SILVER_TABLE,
        on=["order_id"],
        strategy="upsert",
        source_table_fqn=BRONZE_TABLE,
        track_rejects=True,
    )
    print(f"Silver: {silver_result.get('num_target_rows_inserted', 0)} inserted, "
          f"{silver_result.get('num_target_rows_updated', 0)} updated")
except Exception as exc:  # noqa: BLE001 — bootstrap path; see comment above
    if "does not exist" not in str(exc):
        raise
    print(f"Silver: bootstrap (target missing) — {exc.__class__.__name__}")
    pql.write_table(silver_source, SILVER_TABLE, mode="overwrite", source_table_fqn=BRONZE_TABLE)
    print(f"Silver: bootstrapped {len(silver_source)} row(s)")

# %% [markdown] pql_cell_id="11111111-1111-4111-8111-aaaaaaaaaaaa"
# ## Gold — fan-in aggregation via ``pql.aggregate``
#
# Daily revenue per product, materialised through Sprint-15.5.1's
# ``pql.aggregate`` primitive so each gold row carries deterministic
# ``_lineage_row_id`` AND records N→1 fan-in edges back to silver in
# ``lineage_row_edges``.  Sprint 15.5.2's row-trace UI surfaces those
# fan-in edges as collapsible "Aggregated from N rows" blocks.

# %% pql_cell_id="22222222-2222-4222-8222-bbbbbbbbbbbb"
silver_df = pql.table(SILVER_TABLE)
# Sprint 15.6.2: ``derivations={...}`` declares pre-aggregate
# ``.assign(...)`` mappings so the column-trace UI can walk
# ``revenue → line_revenue → (qty, unit_price)`` and
# ``placed_day → placed_at`` even though ``pql.aggregate`` itself
# only sees the already-derived columns.
gold_result = pql.aggregate(
    source_df=silver_df.assign(
        placed_day=silver_df["placed_at"].dt.floor("D"),
        line_revenue=silver_df["qty"] * silver_df["unit_price"],
    ),
    target=GOLD_TABLE,
    group_by=["placed_day", "product"],
    aggs={
        "units_sold": ("qty", "sum"),
        "revenue": ("line_revenue", "sum"),
    },
    source_table_fqn=SILVER_TABLE,
    derivations={
        "placed_day": ["placed_at"],
        "line_revenue": ["qty", "unit_price"],
    },
)
print(
    f"Gold: {GOLD_TABLE} refreshed with {gold_result['rows_written']} aggregate "
    f"row(s); {gold_result['edges_emitted']} fan-in edge(s) recorded"
)

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
