# %% [markdown]
# # ETL pipeline starter
#
# Read → transform → write.  Replace catalog/schema/table names with
# real ones before running and tag the notebook ``etl`` once the
# pipeline is stable.

# %%
from pointlessql.pql import PQL

# %%
# Source extraction
src = PQL.read("main.bronze.events")

# %%
# Transform
out = src  # add filters / aggregations here

# %%
# Sink write
PQL.write("main.silver.events", out, mode="overwrite")
