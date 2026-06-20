---
title: "Cluster 17 — Phase 90–94 NL→SQL + Memory + Vector-Search (dev-log)"
audience: contributor
cluster_id: "17"
phases: "90-94"
closed: "2026-05-19"
---

# Cluster 17 — Phase 90–94 NL→SQL + Memory + Vector-Search (dev-log)

> Phase 90 (pql.memory facade + /memory/<agent-id> brain browser), Phase 91 (NL→SQL chat panel via in-process hermes-agent), Phase 92 (vector-search compute primitive + 5 follow-ups).

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Added**)

- **Phase 92 — UI to create a vector index from the Table page
  (2026-05-19).**  When a table has at least one text column and the
  user has ``MANAGE_GRANTS``, the ``Semantic search`` tab is now
  visible even with zero indices and renders an empty-state card
  with a column dropdown + embedder selector + ``Build index``
  button.  Eliminates the prior need for REPL or hand-crafted REST
  calls to bootstrap the first index.  Tab badge shows the index
  count when ≥1, or a ``+`` chip in the empty case.

> from CHANGELOG.md (bucket: **Fixed**)

- **Phase 92 ``_vss/`` cleanup on index delete (2026-05-19).**
  ``DELETE /api/sql/vector_search/indices/{id}`` now also ``rmdir``s
  the parent ``_vss/`` directory when it is the last index for the
  table — previously the empty directory lingered on disk.

> from CHANGELOG.md (bucket: **Fixed**)

- **Phase 91 ``chatPanel`` Alpine race latent bug (2026-05-19).**
  Same architectural issue as Phase 92's ``semanticSearch``: the
  per-page ``<script type="module">`` for ``chat.js`` raced Alpine's
  CDN bundle.  Masked in practice because the chat drawer is hidden
  until clicked.  ``chatPanel`` now ships via
  ``frontend/js/bootstrap.js`` — same shape as every other Alpine
  factory in the project.  Memory rule:
  ``feedback_alpine_factories_via_bootstrap.md`` (see ``.claude/``).

> from CHANGELOG.md (bucket: **Docs**)

- **Phase 92 walkthrough Step 4 + prereq clarification (2026-05-19).**
  Step 4's "Run a merge — confirm auto-rebuild" now spells out that
  the post-commit hook only fires inside the FastAPI lifespan (in-
  process notebook kernel or REST write path), not from a bare
  ``uv run python`` REPL where ``_session_factory_or_none()``
  returns ``None``.  Prereq section corrected: the "fake embedder"
  exists only in the pytest suite, not the live walkthrough — users
  need either ``pip install pointlessql[vector]`` (sentence-
  transformers) or an ``OPENAI_API_KEY`` to run the walkthrough.

> from CHANGELOG.md (bucket: **Fixed**)

- **Phase 92 walkthrough fixes (2026-05-19).**  Two bugs surfaced by
  the first end-to-end Playwright replay of
  [`docs/e2e-walkthroughs/vector_search.md`](docs/e2e-walkthroughs/vector_search.md):
  1. ``pql.vector_index`` failed with
     ``IOException: Cannot open file …/_vss/<col>.duckdb`` when
     ``soyuz-catalog`` returned ``storage_location`` as a
     ``file://`` URI.  ``deltalake`` handles the URI scheme natively
     but DuckDB's ``connect()`` does not.
     [`pointlessql/pql/_vector.py`](pointlessql/pql/_vector.py)'s
     ``_index_file_path`` now strips the ``file://`` prefix before
     constructing the on-disk index path.
  2. The conditional ``Semantic search`` tab on table-detail pages
     threw ``ReferenceError: semanticSearch is not defined`` because
     the ``<script type="module">`` raced Alpine's ``x-data`` walk.
     The factory now ships via
     [`frontend/js/bootstrap.js`](frontend/js/bootstrap.js) — the
     existing ESM-bridge pattern that lands every Alpine factory on
     ``window`` BEFORE Alpine's CDN bundle fires (same shape as
     ``pqlToast`` / ``pqlApi`` / ``editable`` etc.).  Per-page
     script tag dropped from ``table.html``.

  ``asset_version`` bumped to ``0.1.0rc10`` to invalidate cached
  ``bootstrap.js`` + ``semantic_search.js`` in Firefox's ES-module
  cache.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 92 vector-search compute primitive closed (2026-05-19).**
  Third PQL primitive next to ``pql.merge`` / ``pql.autoload``.
  Backed by the DuckDB ``vss`` extension; the HNSW index file
  lives at ``<table.storage_location>/_vss/<column>.duckdb`` and
  is rebuilt automatically on every merge / write / autoload via
  the sixth post-commit hook in
  ``pointlessql.services.agent_runs.operations._lifecycle``.

  Five sub-strands shipped (92.0–92.4) + docs + tests:

  1. **92.0 / 92.1 — Primitive + embedder registry.**
     [`pointlessql/pql/_vector.py`](pointlessql/pql/_vector.py) +
     [`pointlessql/pql/_vss_engine.py`](pointlessql/pql/_vss_engine.py)
     add ``PQL.vector_index(...)`` and ``PQL.vector_search(...)``.
     Embedders live under
     [`pointlessql/pql/embedders/`](pointlessql/pql/embedders/) —
     ``SentenceTransformersEmbedder`` (default; new ``[vector]``
     extra), ``OpenAIEmbedder`` (optional; ``OPENAI_API_KEY``),
     and a documented ``HermesEmbedder`` stub reserved for a
     future hermes-agent ``embed`` tool.  ROADMAP-adjustment:
     the originally-planned default (route through hermes-agent
     ``embed``) had to invert because the tool does not yet
     exist — the rationale is captured in
     [`docs/concepts/vector-search.md`](docs/concepts/vector-search.md).
     Alembic migration ``r6t8v0x2z4a6`` creates ``vector_indices``
     and extends the ``op_name`` CHECK with ``vector_index`` +
     ``vector_search``.
  2. **92.2 — REST surface.**
     [`pointlessql/api/sql/vector_search/`](pointlessql/api/sql/vector_search/)
     adds ``POST /api/sql/vector_search`` (re-uses the SQL
     dispatcher's ``enforce_select_per_table``),
     ``POST /api/sql/vector_search/indices`` +
     ``GET`` + ``DELETE …/{id}`` (workspace-admin), and
     ``GET /embed/semantic_search/{fqn}`` for the iframe share
     URL.  Audit-mirrors via ``record_query_async`` +
     ``audit("sql.vector_search", ...)``.
  3. **92.3 — Hermes-plugin tool.**
     ``hermes_plugin_pointlessql.tools.vector_search`` ships
     ``pql_vector_search`` (registered unconditionally — unlike
     the chat-gated ``pql_propose_sql``).  Closes the RAG loop:
     chat-panel agents can retrieve semantically before
     generating SQL.
  4. **92.4 — UI tab on Table-detail.**
     Conditional ``Semantic search`` tab on
     [`frontend/templates/pages/table.html`](frontend/templates/pages/table.html)
     guarded by ``{% if vector_indices %}``.  Alpine factory
     ``semanticSearch()`` in
     [`frontend/js/table/semantic_search.js`](frontend/js/table/semantic_search.js)
     owns column picker / query / result rendering + a
     "Copy share URL" → embeddable iframe via
     [`semantic_search_embed.html`](frontend/templates/pages/semantic_search_embed.html).
     ``asset_version`` bumped to ``0.1.0rc8``.
  5. **92.5 — Docs + tests.** Concept doc
     [`docs/concepts/vector-search.md`](docs/concepts/vector-search.md)
     and 8-step playbook
     [`docs/e2e-walkthroughs/vector_search.md`](docs/e2e-walkthroughs/vector_search.md).
     19 new pytest cases across embedder registry, primitive,
     merge-hook, and REST route — all green; ``alembic check``
     clean.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 91 NL→SQL chat panel closed (2026-05-19).**  Ships the
  DBX "Genie" equivalent: an in-editor chat drawer that talks to
  an in-process ``hermes_agent.AIAgent`` over a JSON-RPC
  WebSocket.  Five sub-strands (91.0–91.4), ~2700 LOC, 52 new
  tests across PointlesSQL + hermes-plugin-pointlessql, all
  gates green (ruff / pyright / pydoclint / alembic / pytest).

  1. **91.0** — WebSocket transport + drawer.
     [`pointlessql/api/sql_chat_ws.py`](pointlessql/api/sql_chat_ws.py)
     mounts ``/ws/sql/chat/{editor_session_id}`` with the
     notebook-WS JSON-RPC envelope (``prompt`` / ``cancel`` /
     ``refine`` / ``reset``).  Per-turn ``AIAgent`` runs on a
     dedicated ``ThreadPoolExecutor``; the streaming callback
     bridges through the per-session broker
     ([`pointlessql/services/sql_chat/_broker.py`](pointlessql/services/sql_chat/_broker.py))
     so tokens, tool-phase sentinels, and proposals all pass
     through one ordered queue.  Alembic migration
     ``q5s7u9w1y3a5`` adds ``editor_chat_sessions`` (1:1 with
     ``agent_runs``) + ``chat_proposals`` (CHECK on kind +
     status).  WS-auth helper lifted to
     [`pointlessql/api/ws_auth.py`](pointlessql/api/ws_auth.py)
     and shared with ``notebook_kernel_ws``.  Right-side drawer
     template
     ([`frontend/templates/pages/_partials/sql_editor/chat_drawer.html`](frontend/templates/pages/_partials/sql_editor/chat_drawer.html))
     + ``chatPanel()`` Alpine factory
     ([`frontend/js/sql_editor/chat.js`](frontend/js/sql_editor/chat.js))
     wired into the SQL editor header.  ``asset_version``
     bumped to 0.1.0rc7.

  2. **91.1** — Tool-set hardening.  Three new tools in
     `hermes-plugin-pointlessql`:
     ``pql_describe_columns_with_stats`` (live PQL→pandas
     reduction backed by new
     [`pointlessql/services/column_stats/`](pointlessql/services/column_stats/)
     service + ``GET .../tables/{t}/stats`` route with 5-min
     LRU cache); ``pql_save_query`` (wraps existing
     ``POST /api/views``); ``pql_propose_sql`` (registered only
     when ``POINTLESSQL_CHAT_SESSION_ID`` env var is set).
     ``pql_run_select_capped`` dropped — semantic duplicate of
     existing ``pql_query`` which already enforces the 10K-row
     cap and the EXPLAIN-first cost-gate loop.  Server-side
     [`pointlessql/api/sql_chat_routes/_propose.py`](pointlessql/api/sql_chat_routes/_propose.py)
     classifies via ``sqlglot`` (rejects SELECT/EXPLAIN with
     400), enforces ``X-Agent-Run-Id`` ownership against the
     chat session, and dedupes identical SQL within 60 s.

  3. **91.2** — Run-it gate + audit-mirroring.
     [`pointlessql/api/sql_chat_routes/_accept.py`](pointlessql/api/sql_chat_routes/_accept.py)
     adds ``POST .../proposals/{id}/accept|discard``; accept
     returns the chat session's ``agent_run_id`` so the editor's
     normal Run path stamps ``X-Agent-Run-Id`` and the DML
     operation lands on the chat run alongside every tool-call.
     Stale proposals (>24h) auto-flip to ``expired`` instead of
     running.  ``frontend/js/sql_editor/execute.js`` now reads
     ``_chatAgentRunId`` off ``$root`` and forwards the header
     once per accepted proposal.  Shoreguard policy cross-link
     deferred to a follow-up sprint; hook point documented in
     the new concept doc.

  4. **91.3** — Conversational refinement loop.  ``refine``
     WS method templates structured user prompts for the two
     canonical failure modes (``zero_rows``, ``error``) and
     runs them through the normal turn pipeline.  Each refine
     appends to the same ``conversation_json`` so Phase 90's
     ``/memory/<agent-id>`` timeline shows the full
     refinement trace.  Frontend ``Refine`` buttons appear next
     to 0-row results and error banners.

  5. **91.4** — Concept doc + walkthrough + nav.
     [`docs/concepts/nl-to-sql.md`](docs/concepts/nl-to-sql.md)
     frames the architecture, the DML gate, and the LLM-config
     env vars.
     [`docs/e2e-walkthroughs/sql_chat.md`](docs/e2e-walkthroughs/sql_chat.md)
     is the 6-step Playwright playbook (drawer open → SELECT →
     propose → accept → refine → reset).  Cross-link from
     ``agent-supervision.md``; new nav entries under
     ``Concepts`` and the "Working with data" walkthrough
     cluster in ``mkdocs.yml``.

  Scope note: every chat turn shares a single ``agent_run`` with
  ``agent_id="sql-chat-{editor_session_id_short}"``; the WS
  closes with code 1011 + reason ``LLM_NOT_CONFIGURED`` when no
  provider env var is set (verified before the first token).

> from CHANGELOG.md (bucket: **Added**)

- **Phase 90 Agent-Memory as first-class primitive closed
  (2026-05-19).**  Frames the existing audit + branching
  infrastructure (``agent_runs``, ``agent_run_operations``,
  ``branch_audit_log``) as the agent's persistent memory and
  ships a five-function API matching what Lakebase markets as
  "persistent memory for AI agents" on its Postgres-OLTP
  backend.  Three sub-strands, ~2510 LOC total, 62 new tests
  (49 unit + 13 route), all gates green (ruff / pyright /
  pydoclint / alembic / pytest).

  1. **90.0** — ``pql.memory`` facade + replay-dispatcher.
     [`pointlessql/pql/memory.py`](pointlessql/pql/memory.py)
     exposes ``record`` / ``recall`` / ``branch`` / ``fork``
     / ``replay``.  The
     [`services/agent_runs/memory/`](pointlessql/services/agent_runs/memory/)
     package backs each method with a thin SELECT (recall),
     a ``create_branch_schema`` wrapper that derives source
     schema from the run's first write op + stamps
     ``pinned_delta_version`` into the BranchAuditLog payload
     (branch / fork), and a dispatcher that buckets every
     ``OpName`` member into REPLAYABLE (sql / sql_explain /
     autoload) / DATA_UNAVAILABLE (merge / write_table /
     aggregate) / UNSAFE (branch_* / dbt_* / train_model /
     update / delete / rollback / drop_table / DDL).
     ``ReplayPolicy`` enum gates the unsafe path:
     ``STRICT`` raises, ``SKIP_UNSAFE`` records the skip
     reason, ``LENIENT`` accepts.  Replay-execution scoped
     to *intent-only* for Phase 90 — re-records ops against
     the replay run with ``_replay_recorded_only: true``
     stamped in params; real DuckDB execution lands with
     Phase 91 (which needs the same approved-tables map
     for the branch schema).  Version-pinning ships as
     payload metadata + branch-tag stamp; true per-table
     time-travel cloning is a follow-up.
  2. **90.1** — ``/memory/<agent-id>`` UI + polymorphic
     comment surface.  Alembic ``p4r6t8v0x2z4`` extends
     ``social_targets.entity_kind`` CHECK to accept
     ``agent_memory`` (round-trip downgrade-tested).
     ``entity_registry`` gets a new ``agent_memory`` spec
     with discussion / endorsements / followers tab strip
     (matches the ``run`` shape — memory is transient
     activity, not a curated artefact).
     [`memory_html_routes.py`](pointlessql/api/memory_html_routes.py)
     renders the brain-browser page with four top-tabs;
     [`memory_routes/`](pointlessql/api/memory_routes/)
     ships the recall / branch / replay JSON endpoints.
     [`memory.html`](frontend/templates/pages/memory.html)
     plus 5 page-scoped partials
     ([`pages/_partials/memory/`](frontend/templates/pages/_partials/memory/))
     and [`memory_brain.js`](frontend/js/memory_brain.js)
     (Alpine factories + replay-button HX-Redirect handler).
     ``pyproject.toml`` version bumped 0.1.0rc5 → 0.1.0rc6 to
     bust the frontend ES-module cache.
  3. **90.2** — Counter-pitch concept doc at
     [`docs/concepts/agent-memory.md`](docs/concepts/agent-memory.md)
     frames the Delta-first / append-only angle against
     Lakebase's Postgres-first.  Walkthrough at
     [`docs/e2e-walkthroughs/agent_memory.md`](docs/e2e-walkthroughs/agent_memory.md)
     captures the four-step Playwright replay (navigate →
     filter → branch+replay → post comment).  Cross-link
     from ``agent-supervision.md``; new ``Agent memory``
     nav entry in ``mkdocs.yml`` and concept-index.

  ROADMAP.md sketch grew from ~400 LOC to ~2510 LOC because
  the user picked Voll-Scope (real replay dispatcher with
  policy gate, polymorphic comment integration with Alembic
  migration, full Playwright walkthrough); the original 400-
  LOC budget assumed pure pass-through with no scope-trim
  expansions.
