# Vector search walkthrough

Phase 92 ships the third PQL compute primitive next to
`pql.merge` and `pql.autoload`: an HNSW vector index over a Delta
table's text column, with a `pql.vector_search` query path, REST
endpoints, a hermes-plugin tool, and a per-table UI tab.

Concept: [`docs/concepts/vector-search.md`](../concepts/vector-search.md).

This playbook walks the end-to-end loop in 7 steps; a fake
embedder lets the suite run without `sentence-transformers`.

## Prerequisites

- A running PointlesSQL with `POINTLESSQL_SQL_ENABLED=true`.
- An admin browser session (index creation is admin-gated).
- A non-empty Delta table reachable via UC.  This playbook uses
  `main.silver.docs`; substitute any 3-part FQN with a text column.
- Optional: `pip install pointlessql[vector]` if you want the
  default `sentence_transformers` embedder.  The Playwright path
  works without it because the REST creator accepts any registered
  embedder name.

## Steps

### 1. Bootstrap a Delta table with a text column

From a Python REPL on the host (notebook or `uv run python`):

```python
from pointlessql import PQL
import pandas as pd

pql = PQL()
df = pd.DataFrame(
    {
        "id": [1, 2, 3, 4, 5],
        "description": [
            "users churn signals",
            "monthly retention",
            "agent retrieval augmented generation",
            "vector search demo row",
            "outlier removal pipeline",
        ],
    }
)
pql.write_table(df, "main.silver.docs", mode="overwrite")
```

### 2. Build the index from the REPL

```python
pql.vector_index("main.silver.docs", "description")
```

Returns a dict carrying `path`, `rows_indexed`, `dim`,
`built_at`, `delta_version_indexed`.  Verify the on-disk file:

```bash
ls <warehouse>/silver/docs/_vss/description.duckdb
```

### 3. Search from the REPL

```python
pql.vector_search("main.silver.docs", "description",
                  query="agent retrieval", top_k=3)
```

Returns the top-3 rows ranked by cosine similarity.  Each hit
carries `score`, `pk`, `snippet`.

### 4. Run a merge — confirm auto-rebuild

```python
pql.merge(
    pd.DataFrame({"id": [6, 7], "description": ["new row one", "new row two"]}),
    "main.silver.docs",
    on=["id"],
)
```

Tail the server logs for `vss_rebuild` entries.  Re-run
`pql.vector_search` from step 3 with a query that should hit one
of the new rows; the row should appear with a non-zero score.

### 5. UI tab via Playwright MCP

```text
mcp__playwright__browser_navigate
  url=http://localhost:8000/catalogs/main/schemas/silver/tables/docs

mcp__playwright__browser_snapshot
  # confirm "Semantic search" tab is visible in the nav-tabs

mcp__playwright__browser_click
  ref=button#tab-semantic-search-btn

mcp__playwright__browser_type
  ref=input[type=text]
  text="agent retrieval"

mcp__playwright__browser_click
  ref=button:has-text("Search")

mcp__playwright__browser_snapshot
  # confirm the hits table appears, with scores in DESC order
```

### 6. Copy + open embed URL

```text
mcp__playwright__browser_click
  ref=button:has-text("Copy share URL")

# Paste the URL into a new tab; verify the read-only iframe
# renders the same hits.
```

The embed URL shape is:

```
/embed/semantic_search/main.silver.docs?column=description&q=agent+retrieval&k=10
```

### 7. Invoke the hermes tool

From a chat session loaded with `hermes-plugin-pointlessql`:

```text
pql_vector_search args=
  {"table": "main.silver.docs", "column": "description",
   "query": "agent retrieval", "top_k": 5}
```

The plugin's JSON envelope returns `{ok: true, data: {hits: [...]}}`.

### 8. Cleanup

```bash
curl -X DELETE \
  -H "Cookie: …" \
  http://localhost:8000/api/sql/vector_search/indices/<id>
```

Confirm the `.duckdb` file is gone and the "Semantic search" tab
disappears from the table-detail page after a refresh.
