# `PQL` class

The primary public Python API. 19 methods covering
catalog browsing, Delta read / write / merge / aggregate,
time-travel, rollback, and Delta-branching.

## Usage

```python
from pointlessql import PQL

pql = PQL() # picks up POINTLESSQL_AGENT_RUN_ID + connects to soyuz

# Browse
pql.list_catalogs()
pql.list_schemas("demo")
pql.list_tables("demo", "sales")

# Read
df = pql.table("demo.sales.orders")
df = pql.read_table_at_version("demo.sales.orders", version=4)

# Write (always emits an audit row)
pql.write_table(df, "demo.gold.daily_summary",
 mode="overwrite",
 source_table_fqn="demo.silver.events")

# Merge with row-level lineage
pql.merge("demo.silver.dim_customer", df,
 key=["customer_id"],
 track_value_changes=True)

# Aggregate fan-in
pql.aggregate("demo.gold.summary", df,
 group_by=["date"],
 source_table_fqn="demo.silver.events")

# Rollback (, admin-only at the HTTP layer)
pql.rollback("demo.gold.daily_summary", run_id="r-123")

# Delta-branching
pql.branch("main", "agent-run-123")
#... agent writes to demo.sales.foo on the branch...
pql.promote("agent-run-123")
# or: pql.discard("agent-run-123")

# Training audit
with pql.training_context(framework="sklearn") as ctx:
 model.fit(X, y) # mlflow.autolog wraps under the hood
# op_name="train_model" row written, training_params_json populated
```

## Reference

::: pointlessql.pql.pql.PQL
 options:
 docstring_style: google
 show_root_heading: false
 show_source: false
 show_signature_annotations: true
 separate_signature: true
 members_order: source
 filters:
 - "!^_"
