# Vector search

Phase 92 lands PointlesSQL's third PQL compute primitive — semantic
retrieval over a Delta table's text column.  Together with Phase 90
([Agent memory](agent-memory.md)) and Phase 91
([NL → SQL chat](nl-to-sql.md)), it completes the
**persistent memory for agents** loop:

* Phase 90 — *what to remember* (`/memory/<agent-id>`)
* Phase 91 — *how to ask* (chat panel WebSocket)
* **Phase 92 — *how to retrieve semantically*** (`pql.vector_index`)

A side-by-side `.duckdb` file holds an HNSW index over embeddings of
the source column.  Delta stays source-of-truth; the index is a
secondary structure rebuilt automatically on every `pql.merge` write
via the post-commit hook in
`pointlessql.services.agent_runs.operations._vector_rebuild`.

## Storage layout

For a Delta table at
`<storage_root>/<table>` with text column `description`, the index
file lives at

```
<storage_root>/<table>/_vss/description.duckdb
```

Inside the file:

* `embeddings(rowid BIGINT PK, pk_json VARCHAR, source_text VARCHAR,
  vector FLOAT[dim])` — one row per non-null source row.
* `meta(key VARCHAR PK, value VARCHAR)` — opaque key/value store
  carrying `dim`, `model`, `embedder`, `metric`, HNSW params,
  `delta_version_indexed`, `built_at`, `rows_indexed`.
* `hnsw_idx` — the HNSW index built with the configured `m` and
  `ef_construction`.

The DuckDB extension `vss` is `INSTALL`-ed once per process and
`LOAD`-ed on every connection.  Persistent HNSW indices need the
flag `hnsw_enable_experimental_persistence = true`, set
automatically in `pointlessql.pql._vss_engine.load_vss_extension`.

## Embedder strategy

The ROADMAP anticipated a hermes-agent `embed` tool as the default
provider.  That tool does not yet exist, so Phase 92 ships with
the order **inverted**:

| Provider | Status | Use when |
|---|---|---|
| `sentence_transformers` | **Default** — local; needs `pointlessql[vector]` (PyTorch, ~700 MB) | Air-gapped boxes; zero-config |
| `openai` | Optional — already-installed `openai` SDK + `OPENAI_API_KEY` | Hosted embeddings; smaller install |
| `hermes` | **Stub** — raises `NotImplementedError` | Reserved for the future hermes-agent embed tool |

Resolve order: explicit `embedder=` argument > `POINTLESSQL_VECTOR_DEFAULT_EMBEDDER`
env > `sentence_transformers`.

## Privilege model

* **Index creation / rebuild / delete** is workspace-admin only.
  Mirrors other privileged write surfaces — index build burns CPU
  and storage, so the gate stops casual misuse.
* **Search** is open to any caller with `SELECT` on the table.
  Implemented by re-using
  `pointlessql.api.sql._dispatcher._privilege.enforce_select_per_table`
  inside `POST /api/sql/vector_search`.
* The hermes-plugin tool `pql_vector_search` registers
  unconditionally so batch agent runs (no chat session) can call
  it too.

## REST surface

| Verb | Path | Auth |
|---|---|---|
| POST | `/api/sql/vector_search` | `SELECT` on target |
| POST | `/api/sql/vector_search/indices` | workspace admin |
| GET  | `/api/sql/vector_search/indices?table=` | any user |
| DELETE | `/api/sql/vector_search/indices/{id}` | workspace admin |
| GET  | `/embed/semantic_search/{table_fqn}?column=&q=&k=` | any user with workspace access |

## Auto-rebuild on merge

The post-commit hook in
[`_lifecycle.py`](../../pointlessql/services/agent_runs/operations/_lifecycle.py)
calls
`rebuild_vss_indices_after_commit` after the contract-event hook.
Rebuild fires on these trigger op_names:

`merge`, `write_table`, `autoload`, `update`, `delete`, `sql`,
`aggregate`, `rollback`, `branch_promote`, `dbt_model`.

Failure is **non-fatal**: the source operation has already
committed, so the hook logs, stamps
`vector_indices.last_error`, and continues.  Successful rebuilds
clear the error column and update `delta_version_indexed`.

## UI surface

A "Semantic search" tab appears on
`/catalogs/{c}/schemas/{s}/tables/{t}` when at least one index
exists for the table.  The Alpine factory
`semanticSearch()` in
[`frontend/js/table/semantic_search.js`](../../frontend/js/table/semantic_search.js)
owns the column picker, query input, and result rendering.  A
"Copy share URL" button produces a deep link to
`/embed/semantic_search/<fqn>?column=&q=&k=` that an outside doc
can `<iframe>` for a read-only result snippet.

## Limitations + future work

* **Cleanup on table-drop** — orphan `_vss/*.duckdb` files leak
  when a table is dropped outside PQL.  A reconciler + a
  `pql.drop_table` post-hook are planned for a follow-up phase.
* **Concurrent rebuild** — two parallel merges on the same indexed
  table run their rebuilds serially via a process-local lock; a
  Postgres advisory lock is on the follow-up list.
* **Persistent HNSW** — the duckdb-vss feature is still marked
  experimental.  The on-disk format is stable enough for our
  rebuilt-on-write model, but a corruption recovery story would
  need a dedicated checkpoint.
* **Hermes embed tool** — once hermes-agent exposes an `embed`
  endpoint, replacing
  [`_hermes.py`](../../pointlessql/pql/embedders/_hermes.py)'s
  body is the only change needed; the registry slot is reserved.
