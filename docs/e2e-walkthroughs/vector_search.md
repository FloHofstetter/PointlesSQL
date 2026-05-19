# Vector search walkthrough

Phase 92 ships the third PQL compute primitive next to
`pql.merge` and `pql.autoload`: an HNSW vector index over a Delta
table's text column, with a `pql.vector_search` query path, REST
endpoints, a hermes-plugin tool, and a per-table UI tab.

Concept: [`docs/concepts/vector-search.md`](../concepts/vector-search.md).

This playbook walks the end-to-end loop in 8 steps.

The pytest suite (`tests/test_vector_*.py`) uses an in-test
`_FakeEmbedder` so it runs without any embedder backend; the
walkthrough below requires a real embedder (an in-registry
``fake``-style stub does **not** exist by design — registries
shipped to end users only expose production embedders).

## Prerequisites

- A running PointlesSQL with `POINTLESSQL_SQL_ENABLED=true`.
- An admin browser session (index creation is admin-gated).
- A non-empty Delta table reachable via UC.  This playbook uses
  `main.silver.docs`; substitute any 3-part FQN with a text column.
- **One of**:
  - `pip install pointlessql[vector]` for the default
    `sentence_transformers` embedder (local, ~700 MB pulled in
    via PyTorch — recommended for one-machine setups), OR
  - `OPENAI_API_KEY` set in the server's environment if you want
    to use the hosted `openai` embedder instead.

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

The auto-rebuild is implemented as a **server-side post-commit
hook** (sixth hook in
`pointlessql.services.agent_runs.operations._lifecycle`).  Triggering
it from a Python session requires the FastAPI app's session factory
to be bound, which is the case when the merge runs inside the
in-process notebook kernel (``Notebooks`` tab) or via a write through
``POST /api/sql/write``.  A bare ``uv run python`` REPL has no bound
session factory, so the hook short-circuits — the index file stays
at its pre-merge Delta version until you call ``pql.vector_index``
again to force a rebuild.

To verify the hook from this walkthrough: either re-run the merge
from a PointlesSQL notebook cell, or trigger any write via the SQL
editor.  Tail the server logs for ``vss_rebuild`` entries.  Then
re-run ``pql.vector_search`` with a query that should hit one of
the new rows; the row should appear with a non-zero score.

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
