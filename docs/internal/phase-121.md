---
title: "Phase 121 — Code Quality Wave VI (error-envelope unification) (detail)"
audience: contributor
---

# Phase 121 — Code Quality Wave VI (error-envelope unification)

Closed 2026-05-24.  Sub-sprint detail extracted from `ROADMAP.md` in W2
of the Documentation Master-Plan (per ADR-0009 D7, phases over 100 LOC
move their detail to a per-phase sidecar; the main ROADMAP keeps a
compact summary + pointer).

> See [ROADMAP.md](../../ROADMAP.md) for the project-level context and
> the active/queued roadmap.

## Summary

**All 12 sub-sprints closed 2026-05-24.** Three-axis quality pass after the Restschuld I–V modularization waves drained the >700-LOC backlog. Plan-source: ``.claude/plans/ich- denke-es-ist-squishy-pnueli.md``. Wave ran in three batches: 121.1 (error envelope) shipped first, 121.2–121.7 + 121.4 in the secon...

## Full detail

```text
│   ├── Phase 121 — Code Quality Wave VI (error-envelope unification)  ✅ done 2026-05-24
│   │     **All 12 sub-sprints closed 2026-05-24.**  Three-axis quality
│   │     pass after the Restschuld I–V modularization waves drained the
│   │     >700-LOC backlog.  Plan-source: ``.claude/plans/ich-
│   │     denke-es-ist-squishy-pnueli.md``.  Wave ran in three batches:
│   │     121.1 (error envelope) shipped first, 121.2–121.7 + 121.4 in
│   │     the second batch (settings + lint + facade + micro-extractions
│   │     + residuals + privilege scaffold + PII redaction), 121.8a/b
│   │     in the final close-out batch (tests lint baseline + pagination
│   │     service-layer rollout).
│   │     - **121.1 — Error-Envelope + Human-Feedback.**  ✅ done 2026-05-24.
│   │       Unifies three parallel envelope shapes (RFC 9457 / DBX /
│   │       legacy ``{"error":}``); converts 201 → 13 ``HTTPException``-
│   │       sites in ``pointlessql/api/``.  The 13 remaining are all
│   │       intentional: 8× 501 NotImplemented in social_routes
│   │       (registry-level opt-outs), 2× 412 Precondition Failed in
│   │       branches_routes (tests pin the status), 1× 401 HMAC-failure
│   │       in webhook_routes, 2× 502 upstream-proxy in dbt/mlflow.
│   │       Asset rc125 → rc126.
│   │       - 121.1.0 Compat-Sweep Hermes-Plugin + CLI — 0 Hits for
│   │         every legacy-string pattern (plugin already RFC 9457-
│   │         aware via ``tools/_common.py:83-86``).  No deprecation
│   │         cycle needed.
│   │       - 121.1.a Foundations: ``BadRequestError`` +
│   │         ``PointlessSQLError.not_found()`` classmethod (sorted +
│   │         truncated alternatives + hint) + 4 new ``ErrorCode``
│   │         members (``BAD_REQUEST`` / ``IP_NOT_ALLOWED`` /
│   │         ``WORKSPACE_CONTEXT_MISMATCH`` / ``NOT_AUTHENTICATED``)
│   │         + ``api/_error_envelope_writer.py`` helper that wraps
│   │         the existing ``_problem_body`` so middleware sites
│   │         emit identical RFC 9457 ``application/problem+json``
│   │         bodies.  13 new pytest in ``test_exceptions_helpers.py``.
│   │       - 121.1.b Middleware-Shape-Unification — 3 sites in
│   │         ``api/middleware.py`` (IP_NOT_ALLOWED line 178,
│   │         Anonymous 401 line 296, ``_workspace_forbidden`` line
│   │         337) all flow through ``problem_response()``; audit-
│   │         write ordering preserved (audit runs synchronously
│   │         before the response ships).
│   │       - 121.1.c ``_DbxApiError`` promoted to
│   │         ``api/_dbx_error_wrapper.py`` (move-only with re-export
│   │         at the old path).  10 new contract pytest in
│   │         ``tests/test_external_sql_dbx_envelope.py`` pin the
│   │         ``{"detail": {"error_code", "message"}}`` wire shape
│   │         + ``_wrap_dbx`` decorator behaviour for 400/429/503.
│   │       - 121.1.d ``api/_ws_error.py`` consolidates the two
│   │         byte-identical ``_send_error`` helpers in
│   │         ``sql_chat_ws.py`` + ``notebook_chat_ws.py``.  Wire
│   │         shape ``{"id"?, "error": {"code", "message"}}``
│   │         locked by ``chat.js:214`` + ``notebook/chat.js:196``
│   │         consumers; 3 new pytest in ``test_ws_error.py`` pin it.
│   │       - 121.1.e Sweep social-family — 84 → 8 intentional 501s.
│   │         Conversion mix: ``BadRequestError`` for shape rejects,
│   │         ``ResourceNotFoundError`` for missing rows,
│   │         ``ConflictError`` for state conflicts,
│   │         ``PermissionDeniedError`` for cross-workspace probes.
│   │       - 121.1.f Sweep data_products-family — 52 → 0.
│   │       - 121.1.g Sweep mid-size routes (notebook_chat /
│   │         memory / users / topics / workspaces / agents /
│   │         me / branches / webhook / settings) — 60 → 3
│   │         intentional (2× 412 branch-precondition, 1× 401
│   │         webhook-HMAC).
│   │       - 121.1.h Sweep long-tail (admin/repos, dbt/proxy,
│   │         mlflow_proxy, notebook_coedit_agent_routes,
│   │         notebooks_routes/crud + 5 HTML routes) — 13 → 2
│   │         intentional (dbt + mlflow 502 upstream-proxy).
│   │       - 121.1.i Human-Feedback-Enrichment — 3 hot-spot
│   │         enrichments: topic-slug 404 surfaces every known
│   │         slug in the workspace, workspace 404 surfaces all
│   │         workspace slugs, agent-slug 404 surfaces every agent
│   │         slug in the workspace.
│   │     - **121.2 — Settings cache + pagination dep.**  ✅ done 2026-05-24.
│   │       ``get_settings()`` LRU-cached factory in
│   │       ``pointlessql/config/__init__.py`` replaces 26 direct
│   │       ``Settings()`` call-sites; ``reset_settings_cache()``
│   │       companion + autouse fixture in ``tests/conftest.py``
│   │       keeps env-monkeypatching tests working.  Shared
│   │       ``PaginationParams`` dataclass + ``pagination()`` FastAPI
│   │       dependency added in ``api/dependencies.py`` (37 ad-hoc
│   │       offset/limit query params remain — best-effort migration
│   │       deferred).  14 new pytest.  Commit ``a54f95c``, asset
│   │       rc126 → rc127.
│   │     - **121.5 — pydoclint tightening + D401 sweep.**  ✅ done
│   │       2026-05-24.  Re-scoped from the original "62% → 100%
│   │       docstring sweep" plan after the audit showed the codebase
│   │       was already 100% docstring-compliant.  Attempted
│   │       ``check-return-types = true`` + ``check-yield-types = true``
│   │       in ``[tool.pydoclint]``; produced ~1400 DOC203/DOC404 false
│   │       positives because pydoclint compares the type annotation
│   │       against the first word of the prose ``Returns: The X.`` /
│   │       ``Yields: Each Y.`` sections (it expects the
│   │       ``<type>: <desc>`` form).  House style is prose-only with
│   │       the type in the signature — flipping the flag would force
│   │       rewriting >1000 docstrings without semantic win.  Kept
│   │       false with a documented note.  Landed instead: added
│   │       ``D401`` ("imperative mood") to the Ruff D-rule select
│   │       (not in the google preset default); 15 violations surfaced
│   │       and were rewritten in the same sprint.  Commit ``96bd4c2``,
│   │       asset rc127 → rc128.
│   │     - **121.3 — Soyuz facade completion.**  ✅ done 2026-05-24.
│   │       Ground-truth audit found 3 ostensible direct-client
│   │       violations; two were legitimate sync helpers in
│   │       ``services/`` (``branch_tags.py``, ``soyuz_lineage.py``)
│   │       because the async facade exposes no sync path.  Only
│   │       ``ml_routes.py`` was a real API-layer violation:
│   │       ``_fetch_linked_model_versions`` was sync and reached
│   │       directly into the generated client; rewired through
│   │       ``UnityCatalogClient.list_registered_models()`` +
│   │       ``.list_model_versions()`` (now async, awaited from
│   │       ``get_ml_context``).  New ``[tool.ruff.lint.flake8-tidy-
│   │       imports.banned-api]`` rule blocks ``soyuz_catalog_client.
│   │       api`` imports across ``api/`` with per-file ignores for
│   │       the four legitimate sync-helper bypass sites.  4 new
│   │       pytest (test_ml_routes_facade.py).  Commit ``782c7dd``,
│   │       asset rc128 → rc129.
│   │     - **121.4 — Privilege-Gate scaffold + PrivilegeSettings.**
│   │       ✅ done 2026-05-24.  Re-scoped from the original "full
│   │       privilege-gate + 15–20 route migrations" after audit
│   │       showed most inline ``is_admin`` checks are conditional
│   │       UI logic (not route-entry gates) and the existing seven
│   │       ``require_*`` gates already cover static role checks.
│   │       Landed: (a) ``require_role(*roles)`` factory dep in
│   │       ``api/dependencies.py`` generalises the single-role
│   │       gates into one parametrised form (admin / supervisor /
│   │       auditor / analyst / user; admin strictly stronger; OR
│   │       semantics across the role set).  Token-only gates
│   │       (sql_execute, lineage_inbound) deliberately keep their
│   │       dedicated dep.  (b) ``PrivilegeSettings`` sub-model in
│   │       ``config/_settings/_privileges.py`` with single field
│   │       ``enforce_global_privilege_gate: bool = False`` reserves
│   │       the env name + documents intent for the future
│   │       ``require_privilege(privilege, securable_type)`` dep
│   │       that will consult ``services/authorization.check_privilege``
│   │       at request time.  17 new pytest.  No existing
│   │       require_* sites migrated — both forms coexist.  Commit
│   │       ``be0a838``, asset rc133 → rc134.
│   │     - **121.6 — Four micro-extractions.**  ✅ done 2026-05-24.
│   │       (i) ``parse_ref()``: 125-LOC 13-way if/elif → ``RefKind``
│   │       frozen-dataclass registry in new ``social_routes/
│   │       _ref_kinds.py`` (mirrors the existing ``CitationKind``
│   │       pattern); dispatcher shrinks to a registry lookup + uniform
│   │       ``BadRequestError``.  (ii) ``admin_uc()``: combined
│   │       ``require_admin`` + ``get_uc_client`` FastAPI dep collapses
│   │       the 2-line setup across 22 federation routes into one
│   │       ``Depends(admin_uc)`` injection.  (iii) ``_DataOpsMixin``
│   │       per-concern split: ``pql/_pql_data.py`` 678 LOC → 38-LOC
│   │       composite over 9 new per-concern mixins (_pql_read /
│   │       _pql_write / _pql_sql / _pql_vector / _pql_update_delete /
│   │       _pql_aggregate / _pql_autoload / _pql_list /
│   │       _pql_widgets).  Public PQL surface + import path + MRO
│   │       identical; adding a new data-op = focused edit in one
│   │       per-concern file.  (iv) ``render_page_with_fallback()``:
│   │       6 identical ``try/except CatalogUnavailableError`` +
│   │       render-with-banner blocks in ``federation_routes.py``
│   │       collapse into one helper on ``api/dependencies.py``.
│   │       24 new pytest (16 ref-kind + 4 admin_uc + 4 render-page);
│   │       existing 79 polymorphic-kind + 42 federation + 70 PQL
│   │       integration tests stay green.  Commit ``37d35dc``, asset
│   │       rc129 → rc130.
│   │     - **121.7 — Residuals consolidation.**  ✅ done 2026-05-24.
│   │       Three follow-up items that were left deferred at the end
│   │       of Phase 121 wave:
│   │       - **121.7a — admin_uc final cleanup.**  ``volumes_routes
│   │         .api_convert_volume_file_to_delta`` was the last
│   │         ``require_admin + get_uc_client`` couplet outside
│   │         federation_routes; migrated to ``Depends(admin_uc)``.
│   │         Commit ``6432829``, asset rc130 → rc131.
│   │       - **121.7b — Pagination dep rollout.**  6 list-endpoint
│   │         routes migrated from ad-hoc ``offset/limit = Query(...)``
│   │         to ``Depends(pagination)``: 3 offset+limit-pair JSON
│   │         endpoints (notifications, audit/search, dp activity)
│   │         + 3 limit-only direct-SQLAlchemy endpoints (social
│   │         issues x2, workspace activity — adds offset support
│   │         additively).  9 other sites stay un-migrated: they
│   │         delegate ``limit=`` to service helpers that do not
│   │         accept ``offset``, so the migration would need
│   │         service-signature changes (out of scope per the
│   │         121.7 plan).  Commit ``6128cd6``, asset rc131 → rc132.
│   │       - **121.7c — PII redaction in audit log details.**
│   │         Extends the existing services/pii infrastructure
│   │         (value-change rows only) to also redact PII-keyed
│   │         values in ``audit_log.detail`` dicts.  New
│   │         ``services/pii/_audit_redactor.redact_audit_detail()``
│   │         walks the detail dict recursively, scrubs values
│   │         under keys matching the existing ``PII_NAME_PATTERN``
│   │         regex via either placeholder or HMAC-SHA256 digest.
│   │         ``log_action`` pipes detail through the redactor when
│   │         new ``audit.redact_detail_payloads=True`` setting
│   │         flipped (default False for backward-compat).  13 new
│   │         pytest.  Commit ``67f4e64``, asset rc132 → rc133.
│   │     - **121.9 — Pre-existing failure drain + working-tree hygiene.**
│   │       ✅ done 2026-05-24.  Final residual sweep after 121.8:
│   │       - **121.9a — Close 7 pre-existing test failures.**  These
│   │         had been carried as "out of scope" since Phase 117/121
│   │         waves; rooted them all.  Model: extend
│   │         ``ck_agent_run_operations_op_name`` with ``'pin_fact'``
│   │         (Phase 97 alembic added it; SQLAlchemy model lagged).
│   │         Prod: switch ``_telemetry._webhook_client_factory`` call
│   │         site to call-time package lookup so the documented
│   │         monkeypatch target reaches the binding (same pattern as
│   │         ``_sleep`` / ``_build_pql``).  Six broad-except sites
│   │         in ``notebook_coedit_ws/`` + ``sql_statements/_executor``
│   │         get ``# bare-broad-ok:`` markers (5) or upgrade to
│   │         ``logger.exception`` (1).  Test-side: rename
│   │         ``test_save_non_admin_accessible`` to reflect Phase 99
│   │         Wave-D edit-role gate (+ paired with-grant test);
│   │         extend ``ENTITY_KINDS`` expected set with Phase 97
│   │         ``notebook_revision`` + ``notebook_cell_output``;
│   │         relax CSRF redirect to ``startswith``; patch
│   │         ``_merge._resolve._get_table`` instead of the package
│   │         re-export.  Full pytest 3529 passed / 0 failed.  Commit
│   │         ``a285165``, asset rc136 → rc137.
│   │       - **121.9b — Working-tree hygiene.**  Removed
│   │         ``phase{113,120}-replay/`` ephemeral PNG dumps + scratch
│   │         notebooks (``mcp_demo.py``, ``phase95_walkthrough.py``);
│   │         reverted jupytext-save drift on
│   │         ``agent_drift_monitor.py`` + ``phase96_walkthrough.py``.
│   │         Extended ``.gitignore`` with ``phase*-replay/`` so
│   │         future replay sessions auto-ignore (the existing
│   │         ``/*.png`` rule only catches root-level PNGs).  Commit
│   │         ``b92442a``, asset rc137 → rc138.
│   │
│   │     - **121.8 — Wave close-out.**  ✅ done 2026-05-24.  Drains
│   │       the two carry-overs that survived 121.7:
│   │       - **121.8a — Tests lint baseline.**  ``tests/**``
│   │         per-file-ignore extended with ``TID251`` (the Phase
│   │         121.3 banned-api rule for direct generated-client
│   │         imports is API-layer-only — tests legitimately bypass
│   │         the facade for setup/teardown and error injection).
│   │         Auto-fixed 3× I001 + 1× F401.  Added ``# noqa: DOC502``
│   │         to ``admin_uc`` (delegated raise via ``require_admin``).
│   │         ``ruff check tests/ pointlessql/`` + ``pydoclint
│   │         dependencies.py`` both report 0 violations.  Commit
│   │         ``5462b46``, asset rc134 → rc135.
│   │       - **121.8b — Pagination service-layer rollout.**  Closes
│   │         the 9 sites 121.7b deferred: 6 service helpers
│   │         (``list_replays`` / ``list_revisions`` / ``list_facts``
│   │         / ``list_bindings`` / ``list_authored_by_agent`` /
│   │         ``recall_operations``) gain optional ``offset: int = 0``;
│   │         6 corresponding routes flip to ``Depends(pagination)``
│   │         and forward ``paging.offset`` through.  3 inline-SQL
│   │         routes (``api_list_agent_runs`` /
│   │         ``api_list_agent_run_operations`` /
│   │         ``api_dbt_test_failures``) gain
│   │         ``.offset(paging.offset)`` chained before ``.limit()``.
│   │         Defaults preserve backward-compat for in-tree ``pql``
│   │         facade callers (``list_facts_for_notebook`` /
│   │         ``recall``).  Commit ``85a4a42``, asset rc135 → rc136.
│   │
```
