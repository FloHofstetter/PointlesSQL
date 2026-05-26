---
title: "Cluster 18 — Phase 95–106 Notebook v3 (Cell-social + Co-edit composite) (dev-log)"
audience: contributor
cluster_id: "18"
phases: "95-106"
closed: "2026-05-21"
---

# Cluster 18 — Phase 95–106 Notebook v3 (Cell-social + Co-edit composite) (dev-log)

> Largest single cluster: Phase 95 (cell-level social), Phase 96 (inline AI-Assistant + sql_chat→editor_chat rename), Phase 97 (revision history + cell-diff), Phase 98 (notebook tags + magic + cell-lineage + export), Phase 99 (widgets + permissions), Phase 100 (publish/snapshot), Phase 101 (per-cell authorship + AI-acceptance hook), Phase 102 (branch-aware notebooks), Phase 103-104 (replay/scenario + NL→Notebook sequence proposals), Phase 105 (real-time co-edit via Y.Doc + awareness + agent-presence + compaction scheduler), Phase 106 hygiene close.

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 106.5 typed proposal bodies — closes the open dict[str, Any]
  erosion line item (2026-05-22).**  The 4 chat-proposal routes
  (notebook-chat ``propose-cell`` / ``fix-cell`` / ``explain-cell``
  + sql-chat ``propose``) parsed their JSON body as ``dict[str,
  Any]`` and reached for fields via ``body.get(...)`` with
  hand-rolled type checks — typos like ``rationael`` for
  ``rationale`` would silently drop the field and persist a
  half-filled ``NotebookCellProposal`` / ``ChatProposal`` row.
  Replaced with Pydantic ``BaseModel`` typed bodies:
  - ``ProposeCellBody`` (``cell_type`` Literal["code","markdown"],
    ``source`` non-blank str, optional positioning + rationale)
  - ``FixCellBody`` (``target_cell_uuid``, ``new_source`` non-blank,
    optional rationale)
  - ``ExplainCellBody`` (``target_cell_uuid``, ``explanation``
    non-blank, optional rationale)
  - ``ProposeSqlBody`` (``sql`` with ``sql_text`` alias coalesced
    in a model-validator so the legacy plugin wire contract still
    works, optional rationale)
  Body-validation now lands as standard FastAPI 422 with a
  per-field error map (forwarded through the existing
  ``_handle_request_validation_error`` envelope as a problem-body
  ``errors`` extension); the route bodies dropped the hand-rolled
  400-raising guard layer.  The one existing test asserting 400
  on bad ``cell_type`` was updated to 422 with a comment explaining
  the migration.  7 new pytest cover the typo class: missing /
  blank fields surface as 422, ``sql_text`` legacy alias still
  works, blank ``rationale`` is normalised to ``None``.  No
  schema change.  Asset 0.1.0rc86 → 0.1.0rc87.
  *Deferred (correctly):* Lineage inbound facets stay
  ``dict[str, Any]`` for OpenLineage 2.x vendor-extension
  forward-compat (the parser comment makes that explicit);
  ``admin/console.py`` carries only two ``dict[str, Any]``
  helper signatures with zero mutation routes, nothing to tighten
  there.  PQL mixin extraction (106.4) stays deferred — the 24
  ``PQL`` methods are already a thin parameter-forwarding facade
  to ``_vector.py`` / ``_merge.py`` / etc; a mixin would shuffle
  74 LOC without reducing the ``self._client`` coupling.

> from CHANGELOG.md (bucket: **Fixed**)

- **Phase 106 lint-baseline hygiene (2026-05-22).**  Two stale
  module-level ``logger = logging.getLogger(__name__)`` placements
  left over from the 106.1 docstring sweep (``agent_runs_routes/
  ingestion.py`` and ``social_routes/issues.py``) tripped E402 on
  every subsequent ``ruff check`` — moved both assignments below
  the import block.  Wrapped three over-100-char source lines
  (``catalog_html_routes.logger.exception`` call and two minified
  CSS rules inside ``services/notebook/export.py``'s f-string
  scaffold) onto their natural line breaks.  Added a
  ``pointlessql/data/notebook_templates/**`` per-file-ignore for
  ``D`` / ``F401`` / ``F821`` in ``pyproject.toml`` — these are
  jupytext-percent starter snippets that legitimately reference
  variables (``features``, ``df``) the user wires up at kernel
  runtime via ``%sql -o features`` magics in earlier cells; same
  rationale already applied to Pyright in 106.2.  Closes the
  106.6 line item that the prior CHANGELOG hand-wave marked as
  a no-op — the AST scan correctly reported zero missing module
  docstrings, but the actual lint baseline still wasn't green.
  Net: ``uv run ruff check pointlessql/`` 28 errors → 0.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 102 Track-I closes branch-aware notebooks (2026-05-22).**
  The kernel env-bridge had already been wired during Wave-D —
  ``PQL.read_table`` / ``PQL.write_table`` call
  ``_branch_remap``, which consults
  ``pointlessql.pql.context.current_branch()``;
  ``KernelSession.start()`` injects ``POINTLESSQL_BRANCH`` into
  the subprocess env when a binding is active; the registry
  propagates ``branch_name`` from the WS open path.  What was
  missing was test coverage proving the chain end-to-end (the
  ROADMAP still flagged Phase 102 as ``⏳ partial`` because no
  test demonstrated the routing).  Added 9 pytest:
  - ``TestPQLBranchRemap`` in ``tests/test_pql.py`` covers the
    routing layer — no-branch passthrough, schema rewrite (``cat.
    main.tbl`` → ``cat.feature_x.tbl``), two-part-name
    passthrough, env-var seeds context on import, and
    mid-session ``_set_context`` updates routing on the next
    call.
  - ``tests/test_kernel_session_branch_env.py`` covers the
    kernel start-path with a faked ``AsyncKernelManager`` —
    ``POINTLESSQL_BRANCH`` is forwarded when set; absent when
    ``branch_name=None``; works without a notebook id for
    replay-mode spawns; and the chain ``KernelRegistry.get_or_start``
    → ``KernelSession.start()`` → ``start_kernel(env=...)``
    end-to-end carries the value through.
  Flips Phase 102 to ✅ done and removes the "still deferred"
  paragraph from the ROADMAP.
  Asset 0.1.0rc85 → 0.1.0rc86.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 102 Track-H promote-reviewer webhook landed (2026-05-22).**
  Closes the shoreguard-promote-gate item of Phase 102's "still
  deferred" list.  ``promote_binding`` now consults an external
  reviewer webhook (``POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_URL``)
  before recording the lifecycle transition.  2xx approves; 4xx
  denies with the reviewer's response body surfaced on the UI; any
  transport error denies-by-default so the gate stays closed.  When
  ``POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_SECRET`` is set, the call
  carries a GitHub/Stripe-shape ``X-PointlesSQL-Signature:
  sha256=<hex>`` over the raw JSON body so shoreguard's intake (or
  any HMAC-verifying receiver) can authenticate without bespoke
  code.  Payload now includes ``base_revision_uuid``,
  ``promoted_by_user_email``, and an ISO ``promote_intent_at``
  timestamp.  The API route forwards ``user["email"]`` to the
  service.  5 new pytest cover unset-skip, happy-path-with-HMAC,
  signature-omitted-without-secret, denial-blocks-promote, and
  network-failure-denies-by-default.  No DB change; shoreguard
  adapter remains config-only.
  Asset 0.1.0rc84 → 0.1.0rc85.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 101 reviewer-per-cell flow closed (2026-05-22).**
  Cross-repo.  Phase 101 was ``⏳ partial`` since 2026-05-20 — the
  per-cell authorship backbone, save-path wiring, header chip, and
  AI-acceptance hook all shipped earlier, leaving the
  reviewer-flow as the last deferred item.  Two changes close it:
  - **PointlesSQL:** ``post_polymorphic_comment`` now accepts
    ``?as_agent=<slug>`` for every entity kind.  Previously the
    polymorphic POST silently dropped the query param and only the
    DP-routes path (Phase 76.5) carried the speak-as-agent
    envelope.  The dispatcher in
    ``social_routes/comments.py`` extracts the param uniformly and
    forwards it, the polymorphic handler resolves it via
    ``resolve_agent_for_principal`` (principal-or-admin gate
    unchanged), and the serialised reply now contains the
    ``agent`` payload so the cell-thread review badge can render
    "decision by agent on behalf of <principal>".
  - **hermes-plugin:** new ``pql_review_cell`` tool that POSTs to
    ``/api/social/notebook_cell/{nb}:{cell}/comments`` with
    ``category=review`` and an optional ``as_agent`` slug.  Self-
    gates on ``POINTLESSQL_NOTEBOOK_ID`` (the env-var seam wired
    in Phase 105.6 for agent-presence broadcast) so SQL-chat
    sessions never see it.  The decision (``approved`` /
    ``changes-requested`` / ``commented``) is prepended to the
    body as a deterministic prefix line that the Wave-D
    ``cellThread`` UI renderer already extracts back into the
    badge — no schema change, no UI work.  ``agent_presence``
    pre/post broadcasts wrap the call so reviewers show up on the
    co-edit peer rail while the review is in flight.
  - 3 new PointlesSQL pytest (happy-path with agent envelope,
    non-principal 403, unknown-slug 404), 7 new plugin pytest
    (gating, schema validation, decision enum, URL + body shape,
    ``as_agent`` query-param threading, ``X-Agent-Run-Id`` header).
  - Asset 0.1.0rc83 → 0.1.0rc84.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 100 + 103 + 104 status flip in ROADMAP (2026-05-21).**
  No new code — these three phases were already closed by Wave-D
  in-flight commits (``e91da74`` share secret-scrub + iframe-embed;
  ``b9d67d8`` replay worker; plugin ``0147d29``
  ``pql_propose_cell_sequence``) but their entries in
  ``ROADMAP.md`` still carried ``⏳ partial`` markers + ``Still
  deferred`` paragraphs.  Flipped each to ``✅ done`` with a
  closure paragraph pointing at the landing commit.  Added a
  5-pytest closure suite for the previously-untested
  ``pql_propose_cell_sequence`` plugin tool (gating, schema
  rejection on empty/bad cells, happy-path URL + headers shape).
  Asset 0.1.0rc82 → rc83.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 99 + 105 follow-up closures (2026-05-21).**  Three small
  cross-cutting deferred items from the post-notebook-blitz hygiene
  backlog landed together; asset 0.1.0rc81 → 0.1.0rc82.
  - **Phase 105.6 closure — hermes-plugin agent-presence wiring.**
    Cross-repo.  The notebook chat WS at
    ``/ws/notebook/chat/{editor_session_id}`` now accepts an
    optional ``?notebook_id=`` query parameter; the chat-drawer
    template forwards the editor's ``notebook_uuid`` so the
    in-process agent factory can stamp
    ``POINTLESSQL_NOTEBOOK_ID`` for the plugin.  On the plugin
    side, ``hermes_plugin_pointlessql.tools._common.agent_presence``
    is a new context manager that sandwiches every
    ``propose_cell`` / ``fix_cell`` / ``explain_cell`` invocation
    with ``thinking`` → ``clear`` POSTs to
    ``/api/notebooks/{nb}/coedit/agent-presence``; failures are
    swallowed so the real tool path is never blocked by a presence
    5xx.  Robot pseudo-peer now lights up in real agent runs.  4
    new plugin pytest.
  - **Phase 105 sync-timing rebind on cellYBinding.**  Cells that
    mounted before the Y.Doc handshake completed got
    ``cellYBinding(cell)=null`` and stayed standalone — co-edit
    never picked them up without a manual reload.
    ``coedit_client.js`` now exposes an ``onSynced`` callback that
    fires once on ``TAG_SYNC_STEP2``; the mixin in ``coedit.js``
    wires ``_rebindCellEditorsAfterSync`` which walks the editor
    registry, destroys every un-bound CodeMirror view, and
    re-mounts it Y-bound from the canonical ``cell.source`` text
    the standalone update-listener kept current.
  - **Phase 99 closure — ``pql.widgets()`` kernel shim.**  The
    kernel session already stamped ``POINTLESSQL_NOTEBOOK_ID``
    via ``services/notebook/kernel_session/session.py``;
    ``PQL.widgets()`` reads the active id from
    :mod:`pointlessql.pql.context`, lazy-bootstraps the metadata
    DB if the subprocess doesn't have a bound session factory
    yet, and calls ``resolve_widget_values``.  Returns ``{}``
    outside the editor (REPL / unbound context) so
    ``params = pql.widgets()`` is safe unconditional.  Route-layer
    ``actor_has_role`` enforcement was already wired into the
    load / save / kernel-WS-open / coedit-WS-open paths at the
    Wave-C ship, so no further plumbing was needed there.  2 new
    pytest.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 106 — Hygiene-Wave nach Phase 95–105 (2026-05-21).**
  Two commits flip the post-notebook-blitz code-quality debt back
  to baseline.  No behaviour change, no asset bump.
  - **Phase 106.1 (pydoclint clean) + 106.2 (pyright 0 errors).**
    Commit ``28db246``.  Migrated the last 30 route docstrings off
    the legacy ``HTTPException`` Raises-section onto the actual
    domain-exception hierarchy (``ResourceNotFoundError``,
    ``ValidationError``, ``ConflictError``,
    ``PermissionDeniedError``) — the global exception handler in
    ``pointlessql/api/error_handlers.py`` already did the mapping,
    only the docstrings lagged behind.  Removed three stale Raises
    sections (``notebook_chat_routes/_propose`` ×2,
    ``services/notebook/replay.mark_running``,
    ``services/notebook/templates.create_from_template``) whose
    bodies no longer raised after earlier service-layer refactors.
    Added 4 missing ``Args:`` blocks (notebook-chat propose / fix /
    explain + ``KernelSession.__init__`` for ``branch_name`` +
    ``notebook_id``).  Pre-initialised ``verb`` in
    ``social_routes/issues.py`` outside the try-block so Pyright
    can prove it bound at the except-clause logger call.  Suppressed
    two unfixable ``jupyter_client`` stub gaps in
    ``replay_worker.py`` with inline ``pyright: ignore`` +
    why-comments.  Excluded
    ``pointlessql/data/notebook_templates/`` from Pyright in
    ``pyproject.toml`` — templates are intentionally incomplete
    plain-Python snippets resolved at kernel-runtime, not library
    code.  Pyright went 10 → 0 errors; pydoclint went 30 → 0
    violations.
  - **Phase 106.3 (models/notebook.py split).** Commit ``fef6d68``.
    Phase 95–105 stacked 18 SQLAlchemy classes into a single
    1343-LOC file.  Split into a per-phase subpackage:
    ``_core`` (Notebook + Cell + Output + Run + RunSource + JobLink),
    ``_provenance`` (96), ``_revisions`` (97), ``_tags`` (98.B),
    ``_share`` (99/100), ``_authorship`` (101), ``_branch`` (102),
    ``_replays`` (103), ``_proposals`` (104), ``_coedit`` (105).
    ``__init__.py`` re-exports every name verbatim so existing
    ``from pointlessql.models.notebook import …`` imports stay
    valid — no legacy shim, no compat alias (Memory
    ``feedback_no_legacy_shim``).  ``alembic check`` confirms the
    schema is byte-identical.
  - **Deferred (tracked, not landed).** 106.4 (PQL mixin
    extraction) — the 24 ``PQL`` methods all hard-depend on
    ``self._client``; no cluster scissors cleanly today, and the
    UnityCatalogClient-style mixin precedent would just shuffle
    code without removing coupling.  106.5 (``dict[str, Any]``
    hardening at LineageInboundEvent + AdminConsoleBody +
    Proposal-bodies) — the inbound-OpenLineage facet bag *must*
    stay ``Any``-shaped for forward-compat with vendor extensions
    (the parser's own comment makes that explicit).  106.6
    (missing module docstrings) collapsed to a no-op after an
    AST-based ``ast.get_docstring()`` scan replaced the initial
    grep heuristic — zero files actually lacked docstrings; the
    grep was tripped up by ``r"""`` / pragma-prefixed openers.
    106.7 (lifespan-loops reorg) deliberately deferred until a
    concrete new init step demands it; the current 33-step
    complexity is structural, not a smell.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 97 closure — Pin-to-memory shipped end-to-end
  (2026-05-21).**  Three commits + a feed-card polish flip
  Phase 97 from ⏳ partial → ✅ done.  Asset 0.1.0rc68 → rc72.
  - **Phase 97.X.1 (pin-to-memory backend, rc69).** Commit
    ``36dc878``.  New ``notebook_revision_facts`` table +
    migration ``d8f1a3b5c7e9``; ``OpName.PIN_FACT`` member +
    matching CHECK; ``services/notebook/facts.py`` idempotent
    on ``(workspace_id, revision_id, cell_content_hash)``
    partial-UNIQUE; four REST endpoints under
    ``/api/notebooks/facts``; ``pql.facts`` PQL facade with
    agent env-bridge via ``POINTLESSQL_AGENT_RUN_ID``;
    ``social_targets.entity_kind`` CHECK widened with
    ``notebook_revision`` + ``notebook_cell_output``;
    best-effort ``fanout_event('notebook_revision_pinned', …)``
    so pins land in the Phase-81 inbox.
  - **Phase 97.X.2 (pin-to-memory UI, rc70).** Commit
    ``cfaad5c``.  📌 button in the Phase-97 revisions panel +
    cell-header chip (lit ``btn-outline-warning`` when a fact
    exists) via outer-scope mixin (no nested-x-data trap); new
    ``frontend/js/notebook/cell_facts.js`` + extension of
    ``revisions.js``; bulk lookup at ``/api/notebooks/facts/bulk``
    for the per-cell hot-path; ``/library/facts`` browse page
    + ``library_facts.html`` + Alpine factory in
    ``bootstrap.js``.
  - **Phase 97.X.3 (pin feed-card, rc72).** Dedicated
    ``render_kind = "fact"`` branch in ``classify_notification``
    + SSE ``_classifyEvent`` mirror + new Alpine
    ``<template x-if="r.render_kind === 'fact'">`` block in
    ``activity_pane.html`` with ``bi-pin-angle-fill`` icon + summary.
    5 new pytest covering classify + envelope + e2e fanout +
    null-actor agent path.  Playwright-MCP playbook extended
    with Part P in ``notebook-editor.md`` + new
    ``library-facts.md``.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 105.8 — coedit compaction scheduler executor (2026-05-21).**
  Asset 0.1.0rc80 → rc81.  Closes the Phase-105 track.  New
  scheduler ``kind="coedit_compaction"`` registered in
  ``build_default_registry``; the executor walks every
  ``notebook_crdt_state`` row, skips notebooks with a live
  Sprint-105.2 hub (the hub's own teardown flush handles those),
  and compacts any inactive blob that has crossed the size or
  TTL gate already exposed by
  ``coedit_service.needs_compaction``.  Wraps the sync DB pass in
  ``asyncio.to_thread`` so it does not stall the scheduler loop;
  per-row failures are logged + skipped, the loop keeps going.
  Opt-in via the scheduler admin UI — no default cron entry.
  4 new pytest (compact-on-stale, skip-active-hub, swallow-fail,
  registry-binding).  Closes Phase 105 sub-phase backlog.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 105.7 — multi-tab co-edit Playwright playbook (2026-05-21).**
  Asset 0.1.0rc79 → rc80.  Closes the e2e-replay gate for the
  Phase-105 stack: a new ``docs/e2e-walkthroughs/notebook-coedit-multi-tab.md``
  playbook drives two browser tabs against the same notebook
  and verifies the full co-edit pipeline end-to-end.  Steps
  cover the toolbar live pill, peer-avatar rail population, A-
  to-B and B-to-A typing propagation under 2 s, save without
  editor reset on the peer (105.5 barrier), agent-presence
  REST broadcast (105.6 robot avatar) and tab-close peer
  cleanup (105.4 ``beforeunload``).  Selector table maps every
  Phase-105 ``data-testid`` to its source sub-phase so future
  selector sweeps have a single index.  Code-only change is the
  README index addition; no PointlesSQL runtime touched.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 105.6 — agent presence on co-edit (2026-05-21).**
  Asset 0.1.0rc78 → rc79.  Surfaces a backend agent as a
  pseudo-peer on the Phase-105.4 avatar rail.  New REST route
  ``POST /api/notebooks/{notebook_id}/coedit/agent-presence``
  accepts ``{agent_run_id, name, cell_uuid, action}`` (action ∈
  ``editing``/``thinking``/``clear``) and broadcasts a new
  ``0x05 TAG_AGENT_PRESENCE`` wire frame whose body is the
  JSON payload.  The hub helper
  ``broadcast_agent_presence(notebook_id, frame)`` reuses
  ``_broadcast_to_all`` from Sprint 105.5 and returns ``False``
  when no clients are open — the route surfaces that as
  ``{"status": "no-hub"}`` so agents can fire-and-forget without
  treating it as failure.  Client-side, ``coedit_client.js``
  decodes the JSON and forwards it to a new ``onAgentPresence``
  callback; the mixin tracks agents in ``_coeditAgentPeers``
  keyed by ``agent_run_id`` and merges them into ``coeditPeers``
  with an ``agent`` flag so the existing partial paints the
  robot-icon branch already shipped in 105.4.  No y-protocols
  encoding involved on either side — the agent path stays
  decoupled from the awareness schema so it can reshape
  independently.  5 new pytest (auth, unknown-notebook,
  no-hub, broadcast, clear).  hermes-plugin integration on the
  agent side is a follow-up commit on the plugin repo.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 105.3b — per-cell CodeMirror co-edit binding (2026-05-21).**
  Asset 0.1.0rc77 → rc78.  Co-edit goes from "Y.Doc syncs in the
  background" to "your typing appears in the other tab".  The
  ``y-codemirror.next`` extension lands in the importmap (lazily
  imported by ``cellEditor()`` so unauthenticated renders pay zero
  cost); the cell-editor factory now accepts an optional
  ``yBinding: { ytext, awareness, undoManager }`` triple that swaps
  the local CodeMirror ``history()`` extension for ``yCollab``,
  routing every transaction through the shared ``cells_text``
  Y.Map.  The coedit mixin gains a ``cellYBinding(cell)`` helper
  that returns the triple when the client is synced + the cell
  carries a stable ``cell_uuid`` (otherwise null → standalone
  CodeMirror, no co-edit).  Cells minted in-session seed a fresh
  ``Y.Text`` into the shared map so peers see the new cell within
  the same WS round-trip.  ``markdown_output.js`` passes the
  binding through for both code/sql mounts and the markdown
  ``enterMarkdownEdit`` path; a ``ytext.observe`` listener mirrors
  the live text onto ``cell.source`` so save still serialises the
  canonical text.  One new pytest asserts the importmap entry
  reaches the editor HTML; 19/19 105.1 + 105.2 regression + the
  Phase 105.5 save-barrier suite stay green.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 105.5 — save-path co-edit barrier (2026-05-21).**
  Asset 0.1.0rc76 → rc77.  Closes the cell_uuid race between the
  Sprint-95 ``cell_reconciliation.reconcile()`` three-pass pipeline
  and the live CRDT replica: when the reconciler returns a
  different ``cell_id`` than the client tracked, the save handler
  now emits an atomic remap onto the Phase-105.2 hub.  Mechanics
  ship in three pieces.  (1) ``/api/notebooks/save`` accepts an
  optional ``cell_uuid`` per cell — the save handler builds a
  ``{client_uuid: reconciled_uuid}`` dict from any pair that
  drifted and calls the new ``apply_save_remap`` helper.  (2) The
  WebSocket hub gained ``_broadcast_to_all`` (no-exclude fanout)
  + ``apply_save_remap(notebook_id, remap)`` which rewrites
  ``cells_text`` / ``cells_order`` under the hub lock with a
  ``pql-server-remap`` Y origin marker and broadcasts a new
  ``0x04 TAG_CELL_UUID_REMAP`` frame whose JSON body is the
  remap dict.  (3) Browser-side, ``coedit_client.js`` decodes
  the frame, patches the local Y.Doc under the same remote-
  origin marker so peers don't echo it, and invokes
  ``onCellRemap`` — the mixin then mirrors the new ids onto
  ``cells[].cell_uuid`` and the social ``cellCounts`` map and
  stashes the dict in ``_pendingCellRemap`` so the Phase-105.3b
  per-cell CodeMirror binding can rebind without a full mount.
  ``persistence.js`` now sends ``cell_uuid`` in every save body
  so the server has the input side of the remap.  5 new pytest
  + the 19/19 Phase-105.1+105.2 regression stays green.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 105.4 — co-edit awareness layer (2026-05-21).**
  Asset 0.1.0rc75 → rc76.  Browser-side awareness (cursor presence
  + peer-rail) wired against the Sprint-105.2 hub's existing
  ``tag=0x03`` relay — zero server changes other than threading
  the current user's id + name into the editor page context
  (``current_user_id`` / ``current_user_name`` in
  ``notebooks_routes/pages.py``) so the Alpine root knows whose
  cursor it is.  The mixin in ``frontend/js/notebook/coedit.js``
  now builds a y-protocols ``Awareness`` instance anchored to the
  live ``Y.Doc``, sets a deterministic per-user HSL colour
  (FNV-1a-32 over the user id), and bridges local awareness
  mutations onto the wire via ``encodeAwarenessUpdate`` —
  remote-origin updates carry the same ``pql-coedit-remote``
  marker as the doc layer so echoes early-return.  A new
  ``coedit_peers.html`` partial slots into the toolbar after the
  live pill and paints up to six avatar discs
  (``data-testid="notebook-coedit-peer-{id}"``) with initials +
  colour; agent peers (Phase 105.6) reuse the same rail with a
  robot-icon swap-in.  ``window.beforeunload`` clears the local
  state so closing a tab removes the avatar from every other
  peer's rail within a frame.  Two new pytest cases cover the
  user-context thread + peer-rail include; existing 105.1 + 105.2
  + 105.3 regression (19 + 1 cases) stays green.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 105.3 — co-edit Y.Doc client scaffold (2026-05-21).**
  Asset 0.1.0rc74 → rc75.  Browser-side scaffold for the Sprint
  105.2 ``/ws/notebook/coedit/{notebook_uuid}`` hub: new
  ``frontend/js/notebook/coedit_client.js`` owns a local ``Y.Doc``
  and the WebSocket lifecycle, including exponential-backoff
  reconnect (capped at 30 s) and a no-reconnect fast-path for the
  hub's auth/role/missing 4401/4403/4404 close codes.  Wire
  protocol mirrors the server exactly — sync_step1 / sync_step2 /
  sync_update / awareness — and the client suppresses local-update
  echoes via the ``pql-coedit-remote`` Y origin marker so remote
  updates are not bounced back as new frames.  Importmap in
  ``base.html`` extended with pinned esm.sh entries for
  ``yjs@13.6.18`` + ``y-protocols@1.0.6/{sync,awareness}`` +
  ``lib0@0.2.99/{encoding,decoding}`` (reserved for the 105.4
  awareness layer).  New ``installCoeditLifecycle`` mixin wires
  the client into ``notebookEditor`` ``init()`` / ``destroy()``
  and exposes the connection state via ``coeditStatus`` /
  ``coeditLabel`` / ``coeditDotClass`` / ``coeditTooltip``; the
  notebook toolbar now paints a small live pill
  (``data-testid="notebook-coedit-pill"``) so the user can see
  whether co-edit is live, reconnecting, view-only, or offline.
  Deliberate scope: the Y.Doc is kept in sync as a passive
  backbone — no CodeMirror binding yet.  Per-cell ``y-codemirror.next``
  wiring ships in Phase 105.3b once the Phase-105.5 save-path
  barrier removes the ``cell_uuid`` reconciler race.  One new
  pytest in ``test_api_notebook_load.py`` asserts the importmap
  + toolbar pill reach the rendered HTML.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 105.2 — co-edit WebSocket hub (2026-05-21).**
  Asset 0.1.0rc73 → rc74.  New ``/ws/notebook/coedit/{notebook_id}``
  endpoint built on the Sprint 105.1 storage primitive: per-notebook
  in-memory ``_NotebookHub`` keeps the authoritative ``pycrdt.Doc``
  warm while ≥1 client is connected, with a 1-s periodic flush + a
  synchronous final flush on last-subscriber-disconnect (plus an
  opportunistic ``coedit.compact`` when the size/TTL gate trips on
  teardown).  Wire format is binary, single-byte tag dispatch:
  ``0x00`` sync_step1 (client state vector → server diff), ``0x01``
  sync_step2 (server full state on connect or diff reply), ``0x02``
  sync_update (bidirectional incremental update, server applies +
  rebroadcasts to other subscribers), ``0x03`` awareness_update
  (opaque cursor / presence / agent attribution, relayed verbatim,
  never persisted).  Auth via ``resolve_websocket_user`` +
  ``actor_has_role(required="edit")``; api-key principals rejected
  with ``4403`` so the surface stays browser-only.  Backpressure is
  per-subscriber: a 256-frame outbound queue closes only the
  overflowed client with ``1011``, other peers keep flowing.  New
  ``coedit.flush_doc`` helper added to keep the hub's hot path
  in-process (no per-keystroke DB roundtrip).  Save-race safety with
  the existing ``/api/notebooks/save`` reconciliation pipeline lands
  in Sprint 105.5 (save-barrier); single-uvicorn-worker only until a
  Redis pub/sub broker is added.  8 new pytest covering anonymous /
  unknown-notebook / viewer-role rejection, the initial sync_step2
  push, sync_update fanout to other subscribers, awareness
  relay-without-persist, hub teardown on disconnect, and the
  final-flush path for updates received just before close.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 105.1 — pycrdt CRDT sidecar backend (2026-05-21).**
  Commit ``389f023``.  Asset 0.1.0rc70 → rc71.  Adds
  ``pycrdt>=0.10`` (Y.js-compatible Python binding); new
  ``notebook_crdt_state`` table + migration ``e9f2b4c6d8a0``
  with ``y_doc_blob`` LargeBinary + version + compaction
  timestamps; ``services/notebook/coedit.py`` locks the Y.Doc
  shape (``cells_order: Array<str>`` + ``cells_text: Map<str,
  Text>``) and exposes ``get_or_init_ydoc`` / ``apply_update`` /
  ``encode_state_as_update`` / ``compact`` / ``needs_compaction``
  for the upcoming Sprint 105.2 WS hub; 11 new pytest covering
  cold/warm load, cross-replica apply roundtrip, and the
  size/TTL compaction gates.  The WS endpoint, y-monaco
  binding, awareness layer, save-barrier, agent presence,
  multi-tab replay gate, and compaction worker (105.2 – 105.8)
  remain deferred.

- **Wave-D — every remaining deferred notebook item in one wave
  (2026-05-21).**  Six commits (D-1 → D-6a) closing the punch list
  the Wave-C handoff left open.  Asset 0.1.0rc56 → rc62.
  - **D-1 (rc57).** Workspace tag-pills + per-cell reviewer
    affordance.  New ``GET /api/notebooks/tags/bulk`` feeds tag-pills
    + filter dropdown on ``/notebooks/workspace``.  New per-cell
    "Review" chip + composer (✅ Approved / ⚠ Changes requested /
    💬 Comment-only); decision encoded as a body_md prefix on a
    ``category='review'`` comment.  Migration ``c4e7a91b2f60``
    extends ``ck_dp_comment_category`` with the ``review`` value.
  - **D-2 (rc58).** Cell-level lineage chip + revision-history
    drawer.  New ``GET /api/notebooks/cell/lineage/bulk`` returns
    ``{content_hash: [badge, ...]}`` for the whole notebook; chips
    paint in the cell header for write-op target tables.  New
    "History" toolbar drawer with snapshot / list / pin-two / diff;
    line-by-line unified diff in the Changed bucket (Monaco /
    CodeMirror-merge can drop in behind the same panel later).
  - **D-3 (rc59).** ``pointlessql.pql.widgets`` kernel shim
    (``widgets.value(name, default)``); ``pointlessql.pql.context``
    + ``PQL._branch_remap`` so a bound branch rewrites
    ``catalog.schema.table`` → ``catalog.<branch>.table`` on every
    read / write.  Phase 99 route-layer ``actor_has_role`` enforces
    ``view`` / ``run`` / ``edit`` at load / save / WS-open;
    workspace-default lets view + run through so existing tests
    pass.  Kernel session start now surfaces ``POINTLESSQL_NOTEBOOK_ID``
    + ``POINTLESSQL_BRANCH``.
  - **D-4 (rc60).** Secret-scrub for public share viewers (AWS /
    GitHub PAT / Slack / JWT / generic key=value patterns) + new
    ``GET /embed/notebook_share/{uuid}`` iframe-embed mirror.
    Added ``/embed/notebook_share/`` to ``PUBLIC_PREFIXES``.
  - **D-5 (rc61).** Phase-103 replay re-execution worker — serial
    loop in ``services/notebook/replay_worker.py`` that spins up an
    isolated ``jupyter_client.AsyncKernelManager`` per pending row,
    re-runs every cell, and records outputs back.  Optional
    ``branch_name`` flows via ``POINTLESSQL_BRANCH``.  Mounted in
    the FastAPI lifespan; opt-out via
    ``POINTLESSQL_REPLAY_WORKER_DISABLED=1``.
  - **D-6a (rc62).** Phase 97 sign-revision receive endpoint
    (``POST /api/notebooks/revisions/{uuid}/signature``, admin-only)
    so out-of-band signers can flip ``signed=true`` on a revision.
    Phase 102 ``promote_binding`` now consults
    ``POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_URL``; non-2xx denies the
    promote with the reviewer's reason.  ``POST .../propose-sequence``
    accepts ``editor_session_id`` UUID7 in the path so the
    hermes-plugin tool addresses it the same way as propose-cell.
  - **D-6 plugin commit** (cross-repo
    ``hermes-plugin-pointlessql`` ``0147d29``):
    ``pql_propose_cell_sequence`` LLM tool registered when the
    notebook chat session env is set — fires the
    ``pql:cell-sequence-proposed`` window event the Wave-C inbox
    has been waiting for.

- **Wave-C — three deferred Phase-102/103/104 notebook UIs + Phase 99
  UI shipped (2026-05-20).**  Four orphan backends (Branch-Binding /
  Replays / Cell-Sequence-Proposals / Widgets+Permissions) wired from
  the editor in one bundle.  Asset 0.1.0rc52 → rc56.
  - **Wave C.1 — Branch-Binding-Picker (Phase 102.UI).**  Toolbar
    "Branch" button opens an inline panel with three states (no
    binding / pending / promoted).  Bind form takes ``branch_name``
    + optional ``base_revision_uuid``; Promote + Discard actions
    flip lifecycle; expandable history list shows recent bindings.
    New ``installBranchBinding`` Alpine mixin + ``branch_binding.js``
    + ``branch_binding_panel.html``.  No backend change; wires
    ``GET|POST|DELETE /api/notebooks/branch`` + ``POST /promote`` +
    ``GET /history``.
  - **Wave C.2 — Replay-Run-Liste (Phase 103.UI).**  Toolbar
    "Replays" button opens an inline list (status pill + 8-char
    UUIDs + branch hint + relative timestamps).  Each row expands to
    a JSON-pretty-printed diff envelope (lazy-fetched).  A
    "Start replay" form posts a fresh ``pending`` row; the kernel
    worker that takes it to ``running``/``ok`` is still deferred.
    New ``installReplays`` mixin + ``replays.js`` +
    ``replays_panel.html``.
  - **Wave C.3 — Cell-Sequence-Proposal-Drawer (Phase 104.UI).**
    Toolbar "Proposals" button opens a passive inbox listening for
    ``pql:cell-sequence-proposed`` window events.  Each pending
    proposal shows prompt + rationale + cell preview + Accept-all /
    Discard.  Accept iterates the cells via the existing Phase-96
    ``insertCellFromProposal`` path so provenance fans out per cell
    once the save lands.  New ``installSequenceProposals`` mixin +
    ``sequence_proposals.js`` + ``sequence_proposals_drawer.html``.
    Until the hermes plugin LLM tool ships, the inbox stays empty —
    the empty-state copy says so.
  - **Phase 99.UI — Widget-Cells-Form + Permissions-Lattice.**  Two
    new toolbar buttons: "Widgets" opens a CRUD panel for
    dropdown / slider / text widgets with JSON config + default
    value + position, plus a resolved-values preview from
    ``POST /api/notebooks/widgets/resolve``.  "Access" opens a
    per-notebook grants table (``view < run < edit`` lattice) with
    inline role editing and revoke.  Backend untouched; wires
    ``GET|PUT|DELETE /api/notebooks/widgets`` and
    ``GET|PUT|DELETE /api/notebooks/permissions``.  New
    ``installWidgetsPanel`` + ``installPermissionsPanel`` mixins.
    Still deferred: ``pql.widgets`` kernel-side shim + route-layer
    enforcement of the role lattice.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 101 AI-acceptance authorship hook (2026-05-20).**  Wave-B
  scope-trim closed.  ``upsert_cell_authorship`` now accepts
  ``kind="agent"`` with ``agent_id=None`` when ``agent_run_id`` is
  set — inline editor chat has no registered ``Agent`` DB row, so
  the previous strict ``agent_id``-required contract blocked the
  hook entirely.  ``_write_proposal_provenance`` in
  ``api/notebooks_routes/io.py`` now upserts the agent authorship
  immediately after the ``NotebookCellProvenance`` insert.  Order
  matters: the call fires *before* the save-handler's user-
  authorship loop, so the row's ``first_author_*`` records the
  agent and the user loop only bumps ``last_modifier_*`` to the
  saver.  Net effect: the chip on a proposal-accepted cell now
  reads "minted by AI assistant • last edit by &lt;saver&gt;".  One
  new pytest plus a renamed old one (16 total).  Asset 0.1.0rc52.

- **Wave-B — three deferred notebook UIs shipped (2026-05-20).**
  Three Phase backends (98.B Tags, 101 Author-Chip, 100 Publish/Share)
  had green tests but no UI; this wave wires all three from the
  editor.  Asset 0.1.0rc46 → rc51 over four sub-bumps.
  - **Wave 1 — Notebook-Tags-Picker (Phase 98.B.UI).**  Toolbar
    button next to Variables/AI opens an inline panel mirroring the
    cell-tag-picker shape: curated chips (etl / draft / prod / wip /
    verified / broken / ml / report / scratch), custom-tag input,
    pill-list of active tags with one-click removal.  Count badge on
    the toolbar button.  Wires the existing
    ``GET/POST/DELETE /api/notebooks/tags`` REST surface (Phase 98.B
    backend, 13 pytest).  New ``notebookTagPicker`` panel + Alpine
    install-mixin ``installNotebookTags``.  Workspace-list tag-pills
    deferred — editor loop first.
  - **Wave 2 — Per-cell Author-Chip (Phase 101.UI).**  Small
    person/robot chip in each cell header between the dirty-dot and
    the tag-picker, showing the saver's email local-part and the
    full attribution (created / last-modified) on hover.  New bulk
    endpoint ``GET /api/notebooks/attribution/bulk?path=…`` returns
    ``{cell_uuid: envelope}`` so a 50-cell notebook costs one HTTP
    request instead of 50.  Service helper
    ``cell_authorship_service.list_for_notebook`` plus 2 new pytest
    (15 total in
    ``tests/test_notebook_cell_authorship.py``).  Frontend mixin
    ``installCellAuthorship`` reads envelopes lazily after load + on
    every save.  **Scope-trim:** the AI-acceptance path
    (``_write_proposal_provenance``) does NOT yet upsert
    ``kind="agent"`` authorship — the service contract requires an
    integer ``Agent.id`` and inline editor chat has no registered
    DB agent.  Tracked as a separate follow-up sprint (relax the
    contract to accept ``agent_run_id``-only, or introduce a
    "system AI" agent row).  Cell-provenance row already records
    the agent_run_id; the chip just stays in user-mode until the
    save-path runs.
  - **Wave 3 — Publish/Share-Dialog (Phase 100.UI).**  Share
    button in the Save+Run toolbar group opens a modal with a
    Snapshot/Live mode toggle, Dashboard-mode checkbox, an
    optional snapshot note, and a list of existing shares with
    Open-in-new-tab / Copy-URL / Toggle-Dashboard / Revoke per
    row.  Wires the existing
    ``GET/POST/PATCH/DELETE /api/notebooks/shares`` REST surface
    + the public-by-design ``/share/notebook/{uuid}`` viewer
    (Phase 100 backend, 8 pytest).  Modal uses the
    ``:class="{ 'show d-block': flag }"`` pattern per
    ``feedback_bootstrap_modal_x_show``.  New
    ``installShareDialog`` mixin + ``share_modal.html`` partial.

> from CHANGELOG.md (bucket: **Fixed**)

- **Phase 105 replay — notebook editor bug-hunt (2026-05-20).**
  Driven by a full Playwright-MCP replay of
  ``docs/e2e-walkthroughs/notebook-editor.md`` against the latest
  Phase-95/96/98 surfaces; five real bugs caught + fixed at source.
  Asset 0.1.0rc44.
  - **BUG-105-01** — ``/ws/notebook/chat/{id}`` and
    ``/ws/sql/chat/{id}`` closed the WebSocket *before*
    ``accept()`` for the disabled / unauthenticated / no-LLM gates.
    Browsers surface a closed-before-accept handshake as a generic
    "connection refused" — the WS close code + reason never reach
    the client.  Both handlers now ``accept()`` first then close
    with the meaningful code, so the AI-Assistant + SQL-chat drawers
    render an actionable "LLM not configured / chat disabled /
    session expired" error instead of looping infinite reconnect
    attempts with console spam.  Clients also stopped reconnecting
    on the 4503/4401 close codes.
  - **BUG-105-02** — The notebook editor's Variable Inspector
    looped: every cell ``execute_reply`` re-triggered
    ``requestVariableSnapshot()``, whose own ``__pql_inspect__()``
    execute_reply re-triggered the same path indefinitely.  The
    iopub frame handler now gates the auto-refresh on cells whose
    ``content_hash`` does NOT start with ``__pql_``.
  - **BUG-105-03** — The frontend already passed ``silent: true``
    on inspector probes; the WS handler dropped that flag and the
    kernel session always called ``kc.execute(silent=False,
    store_history=True)``.  IPython's ``_ih`` / ``_oh`` grew
    indefinitely and ``notebook_cell_runs`` got noise rows for
    every probe.  ``silent`` is now honored end-to-end: the WS
    handler skips ``upsert_cell_run`` / ``record_cell_run_start``
    + iopub / shell persistence for ``__pql_``-prefixed hashes;
    ``session.execute`` passes ``store_history=False`` (the
    Jupyter ``silent`` flag stays ``False`` because the custom-MIME
    iopub frame still needs to flow).
  - **BUG-105-04** — Cells minted before Phase 95 carry no stable
    ``cell_uuid``; the panel gated on ``cell.cell_uuid && open``
    silently refused to render and the 💬 chip stayed hidden.
    Clicking the tag-picker icon or the 💬 chip now calls
    ``save()`` first when ``cell_uuid`` is missing — the save-path
    reconciler mints the UUID, then the click-handler opens the
    panel / thread with the live UUID in scope.
  - **BUG-105-05** — ``cellThread.cellRef`` was meant to track the
    parent ``cells[i]`` proxy live; in practice it snapshotted at
    factory init time and the save-path UUID mint never propagated.
    ``cellUuid`` is now resolved via a DOM walk to the editor scope
    on every read, looking up the live cell by stable ``id``.  The
    cell-thread loads its comments / reactions / followers
    correctly after the first save.

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 105 UX wave (2026-05-20).**  Same Playwright-MCP replay
  that surfaced BUG-105-01..05 also caught five UX gaps; each
  addressed with the minimum-viable surface.  Asset 0.1.0rc46.
  - **Register → login confirmation.** ``/auth/register`` POST now
    redirects to ``/auth/login?flash=account_created`` and the
    login template renders a one-shot success alert above the
    form.  The silent post-register redirect read as a failure in
    the replay.  Test expectation in ``test_register_and_login``
    updated.
  - **Orphan font preload dropped.** ``auth_chromeless.html``
    pre-loaded ``inter-regular.woff2`` upfront; Firefox kept
    warning "preloaded but never used within a few seconds" because
    the actual @font-face request arrived from the @import chain
    seconds later and the preload's cross-origin match failed.
    ``font-display: swap`` in ``base.css`` already prevents FOIT,
    so the preload was pure waste — removed.
  - **Variable inspector → right-side drawer.** The Phase-67.5
    floating top-right popover clipped the toolbar buttons
    (Save / Schedule / Run-as-job sat behind it).
    ``.pql-notebook-inspector`` now uses the same fixed
    full-height right-edge drawer pattern as the Phase-91 AI
    assistant: ``top:0 right:0 bottom:0`` + ``width: min(420px,
    100vw)`` + ``border-left`` + matching shadow.  Falls back to
    100vw on mobile.
  - **Export dropdown in the notebook toolbar.** Phase 98.D shipped
    ``GET /api/notebooks/export.{html,pdf}`` but had no UI surface;
    added a Bootstrap dropdown button next to *Run as job* that
    opens both routes in a new tab.  No client-side conversion —
    server renders the self-contained HTML / WeasyPrint PDF.
  - **Template-gallery picker in the New-notebook dialog.**
    Phase 98.B shipped ``GET /api/notebooks/templates`` + ``POST
    /api/notebooks/from-template`` but the workspace's
    "New notebook…" flow still created an empty file.  The path
    modal now lazy-fetches the gallery and renders one chip per
    starter template (Blank / SQL exploration / ETL pipeline /
    ML quickstart); selecting a chip POSTs to
    ``/api/notebooks/from-template`` and opens the editor at the
    materialised path.  Expression uses ``$data.templates`` rather
    than a bare identifier to stay safe under Alpine's strict
    with-scope evaluation even if the dialogs mixin hasn't
    hydrated yet (e.g. stale browser cache).
  - **Static-import cache caveat.** The Phase-98.B mixin lives in
    ``frontend/js/pages/notebooks_workspace_dialogs.js`` and is
    statically imported from ``notebooks_workspace.js`` (which is
    statically imported from ``bootstrap.js``).  Static-import
    URLs don't inherit the ``?v={asset_version}`` cache-bust on
    the parent script tag, so existing browser sessions hold the
    pre-Phase-105 mixin in their ES-module cache until a hard
    refresh (Ctrl+Shift+R).  The defensive ``$data.templates ||
    []`` guard in the modal template ensures the page still
    renders without errors on the stale-cache path; the gallery
    just stays empty until the new mixin loads.  Long-term fix is
    a module-fingerprinting build step; out of scope for this
    wave.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 105 — Real-time co-edit parked on ice (2026-05-20).**
  ROADMAP marker flipped ⏳ planned → 🧊 on ice.  The phase was
  explicitly tagged "ship only if simpler async patterns prove
  insufficient" — today no user pain has surfaced around the
  turn-based async model used by Phases 95 / 96 / 101 / 104, and
  the CRDT infrastructure cost would deflect from the agent-native
  vision pillars.  Revisit only when a concrete pain story
  appears.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 101 follow-up — save-path authorship wiring (2026-05-20).**
  ``api/notebooks_routes/io.py`` now calls
  ``cell_authorship.upsert_cell_authorship`` for every reconciled
  cell with the saver's email as ``first_author`` / ``last_modifier``.
  The Phase-101 ``notebook_cell_authorship`` table starts filling
  from the next save; the dedicated agent-author attribution for
  Phase-96 proposal-accepted cells + the cell-header chip render
  remain follow-ups.  Asset 0.1.0rc42.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 104 — NL→Notebook cell-sequence proposals (backend,
  2026-05-20).**  Extends Phase 96's single-cell propose / fix /
  explain to a multi-cell code-gen flow.  New
  ``notebook_cell_sequence_proposals`` table (migration
  ``d737762ace76``) carries the full proposed sequence in
  ``cells_json`` so insertion is atomic.  Status lifecycle
  ``pending → {accepted, discarded, expired}``.  Service in
  ``services/notebook/cell_sequence_proposals.py`` (validates
  cell_type ∈ ``{code, markdown, sql}``, sorts by ``position``).
  REST under ``/api/notebook/chat/{chat_session_id}/propose-sequence``
  + ``/api/notebook/chat/sequences/{proposal_id}/{accept,discard}``.
  The hermes-plugin ``pql_propose_cell_sequence`` LLM tool that
  drives the code-gen stays as a follow-up.  10 new pytest.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 103 — Replay / Scenario-mode (backend, 2026-05-20).**  New
  ``notebook_replays`` table (migration ``311c87f25421``) records
  one row per replay of a Phase-97 ``NotebookRevision``.  Lifecycle
  encoded as ``status ∈ {pending, running, ok, error, cancelled}``;
  outputs land in ``outputs_json`` and a small ``{stable, changed,
  missing, new}`` digest in ``diff_summary_json``.  Optional
  ``branch_name`` routes the replay's writes to a Phase-102 branch
  so production stays untouched.  Service in
  ``services/notebook/replay.py`` (``start_replay`` /
  ``record_finished`` / ``compute_replay_diff`` etc.).  REST:
  ``POST /api/notebooks/replay``,
  ``POST .../replay/{uuid}/finish``,
  ``GET .../replay/{uuid}``,
  ``GET .../replay/{uuid}/diff``,
  ``GET /api/notebooks/replays``.  Worker that drives the
  re-execution remains a follow-up; the audit + diff scaffolding is
  the load-bearing piece.  8 new pytest.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 102 — Branch-aware notebooks (backend, 2026-05-20).**  New
  ``notebook_branch_bindings`` table (migration ``095e6a40fa0e``)
  records which Delta-branch a notebook writes to.  Lifecycle is
  encoded in four nullable timestamp columns: ``created_at`` /
  ``promoted_at`` / ``discarded_at`` / ``superseded_at``; every
  bind / promote / discard supersedes the prior row so only one
  binding is ever "current" while history rows stay queryable.
  Service in ``services/notebook/branch_bindings.py`` (validated
  branch-name pattern ``[A-Za-z0-9][A-Za-z0-9._-]*``).  REST:
  ``GET|POST|DELETE /api/notebooks/branch``,
  ``POST /api/notebooks/branch/promote``,
  ``GET /api/notebooks/branch/history``.  Kernel-side env-bridge
  (``POINTLESSQL_BRANCH``) + the shoreguard-gated promotion path
  remain follow-ups — today the binding is recorded but not yet
  consulted by ``pql.read_table`` / ``pql.write_table``.  11 new
  pytest.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 100 — Publish notebook (backend, 2026-05-20).**  New
  ``notebook_shares`` table (migration ``8c7c6eb5add5``) — one row
  per public share.  ``share_mode ∈ {snapshot, live}`` and a
  ``dashboard_mode`` boolean cover the four publish configurations.
  Snapshot publishes mint a fresh Phase-97 ``NotebookRevision`` and
  pin the share to it; live shares carry no pin.  Service
  ``services/notebook/shares.py`` exposes ``create_share`` /
  ``update_share`` (idempotent re-publish — keeps the same UUID) /
  ``revoke_share`` (soft-revoke; returns 410 Gone on the public
  viewer) / ``list_shares_for_notebook``.  Admin REST under
  ``/api/notebooks/shares`` (cookie-gated); public viewer at
  ``GET /share/notebook/{share_uuid}`` (no auth, hands off to the
  Phase-98.D HTML pipeline or to the new ``render_dashboard_html``).
  Dashboard render keeps markdown cells, replaces code cells with
  zero-source placeholders so their outputs still surface in
  original order, and prepends a "DASHBOARD" banner.  Publish-dialog
  UI + secret-scrub pre-filter remain follow-ups.  8 new pytest.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 99 — Notebook widgets + per-notebook permissions (backend,
  2026-05-20).**  Two new tables (migration ``b944b9be7e03``):
  ``notebook_widgets`` keys ``(notebook_id, name)`` to parameter
  widgets (``dropdown`` / ``slider`` / ``text``) with JSON-encoded
  ``config`` and ``default_value``; ``notebook_permissions`` carries
  the ``view`` / ``run`` / ``edit`` lattice as per-notebook grants
  layered on top of workspace membership.  Service modules
  ``services/notebook/widgets.py`` and
  ``services/notebook/permissions.py`` ship the CRUD + a
  ``resolve_widget_values`` helper (default ↔ override merge) and a
  ``role_satisfies`` lattice helper.  REST:
  ``GET|PUT|DELETE /api/notebooks/widgets``,
  ``POST /api/notebooks/widgets/resolve``, and
  ``GET|PUT|DELETE /api/notebooks/permissions``.  UI render + WS
  kernel-namespace bridge + permission enforcement on the load /
  save / execute paths are deferred follow-ups.  12 new pytest.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 101 — Per-cell authorship attribution (backend, 2026-05-20).**
  Adds the ``NotebookCellAuthorship`` table (migration
  ``805d36938963``) 1:1 with ``NotebookCellIdentity``.  Tracks both
  the first author (user email **or** ``agents.id`` + the originating
  ``agent_run_id``) and the most recent modifier so the editor's
  upcoming cell-header chip can render "minted by agent A • last
  edited by user B".  Service in
  ``services/notebook/cell_authorship.py``;
  :func:`upsert_cell_authorship` is the idempotent save-path /
  proposal-acceptance hook.  REST:
  ``GET /api/notebooks/cell/attribution?cell_uuid=…`` and
  ``GET /api/agents/{agent_id}/authored-cells``.  13 new pytest in
  ``tests/test_notebook_cell_authorship.py``.  Save-path wiring,
  reviewer-per-cell UI, and the header chip remain follow-ups.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 97 — Notebook revision history + diff (2026-05-20).**
  Save-snapshot machinery for the editor.  New ``NotebookRevision``
  table (migration ``47832b8d57ca``) stores canonical JSON
  encodings of cells + outputs plus a deterministic SHA-256.  New
  ``services/notebook/revisions.py`` is the create / list / get /
  diff service; ``create_revision`` is idempotent on the canonical
  hash so a re-save of an unchanged notebook collapses to the
  existing row, and each fresh snapshot chains via
  ``parent_revision_id``.  Cell-by-cell diff uses the stable
  ``content_hash`` identity to classify cells into ``added`` /
  ``removed`` / ``changed`` (paired add+remove at the same position)
  / ``moved`` / ``unchanged`` — Monaco-friendly envelopes.  REST:
  ``POST|GET /api/notebooks/revisions``, ``GET
  /api/notebooks/revisions/{uuid}``, ``GET
  /api/notebooks/revisions/diff?left=…&right=…``.  Shoreguard
  cryptographic signing is deferred (no public signing API in
  shoreguard-fresh yet); ``signature_alg`` and ``signature`` columns
  are reserved on the row so a follow-up sprint can sign historical
  rows without re-writing the payload.  14 new pytest in
  ``tests/test_notebook_revisions.py``.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 98.D — Notebook static HTML/PDF export (2026-05-20).**
  Adds ``GET /api/notebooks/export.html`` and
  ``GET /api/notebooks/export.pdf`` so users can download a self-
  contained snapshot of a notebook + its latest outputs.  The HTML
  document inlines its CSS (no external assets), uses an ``@page``
  print stylesheet so the browser's *Print → Save as PDF* path
  produces a clean PDF, and reuses
  :func:`pointlessql.services.output_rendering.render_output_frame`
  so the rendered output mime bundles match the inline-editor look.
  When WeasyPrint is importable, the PDF route returns
  ``application/pdf`` bytes; otherwise it falls back to HTML with
  ``X-PointlesSQL-Export-Fallback: weasyprint-unavailable`` so the
  UI can guide the user.  9 new pytest in
  ``tests/test_notebook_export.py``.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 98.C — Cell-level lineage badges (2026-05-20).**  Adds a
  read-only query helper +
  ``GET /api/notebooks/cell/lineage?path=…&content_hash=…`` that
  surfaces a per-cell list of Delta write events.  The implementation
  joins ``notebook_cell_runs`` (rows whose ``agent_run_id`` is non-
  null) with ``agent_run_operations`` filtered to the 13 WRITE op
  names (``write_table`` / ``merge`` / ``autoload`` / ``update`` /
  ``delete`` / ``drop_table`` / ``create_schema`` / ``drop_schema`` /
  ``alter_table`` / ``branch_create`` / ``branch_promote`` /
  ``branch_discard`` / ``dbt_model`` / ``train_model``) and collapses
  duplicate ``(op_name, target_table)`` pairs to the most-recent
  occurrence.  Backend-only ship; the cell-header chip render is a
  follow-up (deliberately deferred to avoid the x-data + ``|tojson``
  playbook-gate cost — the API is the load-bearing surface).  8 new
  pytest in ``tests/test_notebook_cell_lineage.py``.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 98.B — Notebook tags + template gallery (2026-05-20).**
  Two DBX-parity surfaces shipped together because they both live in
  the workspace tree:
    * **Notebook-level tags** — new ``notebook_tags`` table (migration
      ``b185acda50d7``) keyed on stable ``notebooks.id`` UUID with a
      ``(notebook_id, tag)`` unique constraint.  Curated vocabulary
      (``etl`` / ``draft`` / ``prod`` / ``wip`` / ``verified`` /
      ``broken`` / ``ml`` / ``report`` / ``scratch``) plus free-text
      ``[a-z0-9_-]{1,64}``; 16-tag cap per notebook.  Service in
      ``services/notebook/tags.py``; REST in
      ``api/notebooks_routes/tags.py``
      (``GET|POST|DELETE /api/notebooks/tags``).  Idempotent re-add.
      Distinct from the Phase-95.3 cell-tag picker which tags
      individual cells inside the ``.py`` marker grammar.
    * **Template gallery** — four shipped starter ``.py`` files under
      ``pointlessql/data/notebook_templates/`` (``blank``,
      ``sql_exploration``, ``etl_pipeline``, ``ml_quickstart``) driven
      by ``_manifest.json``.  Service in
      ``services/notebook/templates.py``; REST in
      ``api/notebooks_routes/templates.py``
      (``GET /api/notebooks/templates``,
      ``POST /api/notebooks/from-template``).
  13 new pytest in ``tests/test_notebook_tags_and_templates.py``.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 98.A — Notebook magic-command pre-processor (2026-05-20).**
  Adds four DBX-parity line-magics in front of the kernel execute
  path: ``%sql <query>`` (server-side ``approved_tables`` resolution
  + ``__pql_sql_run`` wrap, optional ``-o varname`` bind),
  ``%md <markdown>`` and the ``%%md`` block-form (rendered via
  ``IPython.display.Markdown``), ``%fs ls <path>`` (custom-MIME
  ``application/x-pql-fs-ls+json`` payload), and ``%timeit <expr>``
  (stdlib ``timeit`` with autoscaled ``number``, ``repeat=3``,
  human-readable best-of-3 line).  New
  ``pointlessql/services/notebook/magic_commands.py`` is the pure
  pre-processor (parsing + placeholder splicing); kernel-side helpers
  ride along in ``_NOTEBOOK_BOOTSTRAP_CODE``.  The WS execute handler
  only invokes the pre-processor when ``has_magics(source)`` is true,
  so plain Python cells pay no cost.  13 new pytest in
  ``tests/test_notebook_magic_commands.py``.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 96 — Inline AI-Assistant in the notebook editor
  (2026-05-19).**  Lifts the Phase-91 NL→SQL chat panel into the
  notebook editor with three new
  [hermes-plugin-pointlessql](../hermes-plugin-pointlessql) tools:
  ``pql_propose_cell`` (insert a new code/markdown cell),
  ``pql_fix_cell`` (replace an existing cell's source — 60 s
  server-side idempotency on identical fixes), and
  ``pql_explain_cell`` (auto-accepts on create; the explanation
  persists in the per-cell social drawer's new "AI Explanations"
  section).  Provenance lives in a new append-only
  ``notebook_cell_provenance`` table — one row per accepted
  proposal, keyed by the stable ``cell_uuid`` the save-path
  reconciler mints, with FK to the originating ``agent_run``.
  Phase 97 revision history will read this chain to render the
  per-cell agent timeline.

  New WS endpoint ``/ws/notebook/chat/{editor_session_id}`` (fork
  of the Phase-91 ``sql_chat_ws``; drops ``refine`` — notebook
  surface has no zero-row / error analog).  New REST routes
  ``/api/notebook/chat/{id}/{propose,fix,explain}-cell`` +
  ``/api/notebook/chat/proposals/{id}/{accept,discard}`` +
  ``GET /api/notebook/chat/cell/{cell_uuid}/explanations``.
  Frontend ships a new ``notebookChatPanel`` Alpine factory with
  three polymorphic proposal banner variants
  (Insert / Apply / explain-auto-attach), a toolbar **AI** button
  beside Variables/Jobs, and a ``pql:cell-proposal-accepted``
  window-event bus that bridges drawer accepts to the editor's
  ``cell_operations`` mixin.  ``/api/notebooks/save`` extended to
  accept ``proposal_acceptances`` in the body and flush
  provenance rows after the reconciler returns final UUIDs.

  As a Phase-96 preamble, the chat substrate that turned out to
  be generic (session table, broker, agent factory, turn runner)
  was renamed from ``pointlessql.services.sql_chat`` →
  ``pointlessql.services.editor_chat`` (and the corresponding
  models / settings).  Env prefix
  ``POINTLESSQL_SQL_CHAT_*`` → ``POINTLESSQL_EDITOR_CHAT_*``.
  No re-export shim per memory rule ``feedback_no_legacy_shim``.
  The SQL-specific surfaces (``api/sql_chat_ws.py``,
  ``api/sql_chat_routes/``, ``ChatProposal``, ``pql_propose_sql``)
  keep their SQL names.

  28 new tests across the two repos plus a Markdown walkthrough at
  [`docs/e2e-walkthroughs/notebook_assistant.md`](docs/e2e-walkthroughs/notebook_assistant.md)
  and a seed notebook at
  [`notebooks/phase96_walkthrough.py`](notebooks/phase96_walkthrough.py).
  Asset version bumped to ``0.1.0rc29``.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 95 — Cell-level social (comments / reactions / follows /
  tags per cell, 2026-05-19).**  Extends the Phase-77.6 polymorphic
  social schema down to single notebook cells via a new
  ``notebook_cell`` entity-kind anchored on composite
  ``{notebook_uuid}:{cell_uuid}`` refs.  Stable cell identity is
  minted by a save-path reconciler (exact-hash → similarity-gated
  ordinal fallback → fresh UUID) that keeps the ``.py`` file
  IDE-agnostic — no sidecar UUID tokens in the marker grammar.
  Inline ``💬 N`` chip + thread below each cell; six-emoji reactions
  + follow button piggyback on the existing polymorphic routes.
  Bulk-counts endpoint collapses N×3 queries into one
  ``GET /api/social/notebook_cell/_bulk_counts?notebook_id=…``.
  Cell-tags add a curated dropdown (``#etl``, ``#draft``, ``#prod``,
  ``#wip``, ``#verified``, ``#broken``) plus a "Custom…" escape for
  free-text entries — round-tripped through the existing
  ``tags=[...]`` marker.  26 new tests covering all 8 reconciliation
  scenarios from the plan.  Asset version bumped to ``0.1.0rc15``.
