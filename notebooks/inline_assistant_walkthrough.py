# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: -all
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.1
# ---

# %% [markdown]
# # Inline AI-Assistant walkthrough
#
# Open this notebook in the editor and click the toolbar **AI**
# button to load the chat drawer.  Use the seed cells below as
# targets for the three new plugin tools:
#
# * **propose** — ask the assistant to add a cell.  It calls
#   `pql_propose_cell` and the drawer shows an "Insert" banner.
# * **fix** — ask the assistant to fix the failing cell below.
#   It calls `pql_fix_cell` and the drawer shows an "Apply"
#   banner with a diff-style preview.
# * **explain** — ask the assistant to explain the dataframe.
#   It calls `pql_explain_cell` and the explanation auto-attaches
#   to the cell (no Run button); open the per-cell social drawer
#   to see it under the new "AI Explanations" panel.

# %%
import pandas as pd

df = pd.DataFrame({"country": ["DE", "FR", "US", "JP"], "events": [120, 90, 240, 60]})
df

# %%
# This cell intentionally fails so you can ask the chat to fix it.
df["events"].mean(typo_kwarg=True)
