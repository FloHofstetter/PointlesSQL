---
title: "Cluster 09 — Phase 23–44 (Admin + Federation + DBT + CDF) (dev-log)"
audience: contributor
cluster_id: "09"
phases: "23-44"
closed: "2026-05-07"
---

# Cluster 09 — Phase 23–44 (Admin + Federation + DBT + CDF) (dev-log)

> Long span covering admin landing + audit-sinks + API-Keys UI (Phase 33), Grafana governance panels (Phase 34), DBT integration (Phase 36 Stream A + auto-rollback), and Sprint 40.6 CDF events tab + subscriptions admin.

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 50 — Native Data-Product support closed.**  PointlesSQL
  now treats any UC schema as an opt-in data product when its
  data team commits a ``pointlessql.yaml`` declaring steward,
  SemVer version, freshness-SLA and per-table schema contract.
  Yaml is canonical; git-blame is the audit log.  Six surfaces
  shipped across five sub-sprints:

  - **50.1 — Foundation.**  New ``pointlessql/data_products/``
    package: ``DataProductColumnSpec``/``TableContract``/
    ``Contract`` Pydantic models (11 column types),
    ``DataProductRef(str)`` validation type (mirrors Phase-49c
    TableFqn), four ``DataProductError`` subclasses (RFC 9457
    integration), yaml loader with idempotent UPSERT +
    steward-FK resolution against ``users``.  Two new ORM
    tables (``data_products`` + ``data_product_contract_events``)
    via Alembic ``rr8u0w2y4a6c``.  4 new ``ErrorCode`` members,
    ``DataProductsSettings`` under env prefix
    ``POINTLESSQL_DATA_PRODUCTS_*``.

  - **50.3 — Enforcement.**  Pure-functional
    ``ContractDiffResult`` core in ``data_products/_diff.py``
    + two adapters (engine-tuples for pre-write, Delta-schema
    for live diff).  Type canonicalisation collapses
    ``int64``↔``long`` / ``float64``↔``double`` / ``decimal*``
    aliases.  ``check_contract_for_write`` resolves workspace
    from ``agent_run_id``, looks up the cached contract,
    classifies into ``compliant`` / ``schema_drift_warning`` /
    ``violated`` / ``no_contract``.  Pre-write hooks in
    ``pql/_write.py`` + ``pql/_merge.py`` raise
    ``DataProductContractViolation`` *before* any Delta IO
    when the diff is breaking.  ``OperationRecorder.
    pending_contract_event`` tuple +
    ``record_contract_event_after_commit`` post-commit hook
    persist one event row per check; the exception path also
    persists so the audit trail shows refused attempts.

  - **50.4 — Freshness Scanner.**  Background loop walks every
    cached ``DataProduct`` whose ``sla_minutes`` is set,
    observes the latest write timestamp via
    ``DeltaTable.history()`` per UC table, emits one
    ``pointlessql.data_product.sla_violated`` CloudEvent
    when the age exceeds the SLA.  ``last_alerted_at`` is
    stamped after each emit; the re-alert window (default 60
    min via ``re_alert_suppress_minutes``) suppresses event
    storms.  Opt-in via
    ``POINTLESSQL_DATA_PRODUCTS_SCAN_INTERVAL_SECONDS≥60``.
    New ``EVENT_TYPE_DATA_PRODUCT_SLA_VIOLATED`` registered
    in the governance-events registry.

  - **50.2 — Web UI.**  ``/data-products`` index +
    ``/data-products/{catalog}/{schema}`` 5-tab detail page
    (Overview / Contract / Diff / Lineage / Compliance), with
    cytoscape mini-DAG of producers/consumers via
    ``lineage_row_edges``.  Five JSON endpoints:
    ``GET /api/data-products`` (workspace-scoped list),
    ``GET /api/data-products/{cat}/{schema}`` (detail incl.
    last-50 events), ``GET /.../diff`` (live yaml↔Delta diff
    per table), ``GET /.../lineage`` (cytoscape graph),
    ``POST /.../reload`` (admin-gated yaml re-load).
    Icon-rail entry between SQL and Dashboards.

  - **50.5 — Plugin tools.**  Five new LLM-callable Hermes
    tools in ``hermes-plugin-pointlessql``:
    ``pql_list_data_products``, ``pql_get_data_product``,
    ``pql_get_data_product_contract`` (lighter contract-only
    surface), ``pql_check_contract_compliance`` (live diff),
    ``pql_data_product_compliance_history`` (recent events
    with per-call limit).  All five wired into ``register_all``
    so any keyed agent can use them; plugin client gains four
    new methods hitting ``/api/data-products/*``.

  Pyright budget unchanged at 497.  PointlesSQL test suite
  gained 31 new tests (10 ref-validation + 13 loader + 15
  enforcement + 5 scanner + 11 routes); plugin gained 7 new
  tests.  ``Mapped[str]`` columns stay unchanged —
  ``DataProductRef`` is-a ``str`` so SQLAlchemy absorbs it
  transparently.  Anti-goals preserved: no DLT-bundle-
  generator (PointlesSQL **is** the platform), no
  ``Mapped[NewType-or-subclass]`` on models, no domain-
  specific RBAC ladder (Workspace + scope surface gates
  everything).

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 49c — TableFqn validation type closed.**  Introduces
  ``pointlessql/table_fqn.py`` with a ``str``-subclass validation
  type for ``catalog.schema.table`` UC identifiers.
  ``TableFqn.parse(s)`` validates + raises ``ValidationError`` on
  malformed input; ``TableFqn.from_parts(c, s, t)`` skips
  validation for callers that already split the components.  Two
  byte-for-byte duplicate ``_split_three_part`` validators in
  ``api/pql_introspect_routes.py`` + ``api/pql_write_routes.py``
  consolidated into the single type.  13 producer sites
  (f-string FQN constructions in api/, services/, pql/) wrapped
  via ``TableFqn.from_parts``.  ``services/external_write_scanner``
  signatures fully typed end-to-end as a Step C reference example;
  remaining ~36 consumer signatures stay on plain ``str`` for
  incremental migration in future phases.  Anti-goal preserved:
  ``Mapped[str]`` columns on the 7 model classes carrying FQN
  semantics stay unchanged (``TableFqn`` is-a ``str`` so SQLAlchemy
  reads/writes the underlying string transparently).  Pyright
  budget unchanged at 497.  10 new ``tests/test_table_fqn.py``
  sanity tests pin the contract: subclass identity, JSON round-
  trip, f-string interpolation, parse/from_parts factories,
  segment properties, equality with plain ``str``.  3 commits:
  ``feat(types)`` (additive), ``chore(types)`` (migration),
  ``docs(roadmap)`` (close).

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 49b — Service-File Splits closed.**  Two oversize service
  files migrated into Phase-35-style per-axis subpackages.
  ``services/agent_runs/operations.py`` (929 LOC) → six-file
  subpackage: ``__init__`` (re-exports), ``_common`` (recorder
  + helpers), ``_rollback`` (5 exception classes), ``_lifecycle``
  (record_operation + operation_context), ``_lineage`` (3
  post-commit hooks), ``_rejects`` (1 hook), ``_value_changes``
  (1 hook).  ``services/audit_aggregator.py`` (913 LOC) →
  four-file subpackage: ``_query_builder`` (MetricSpec + the
  ~150-LOC metric-spec switch + filter helpers), ``_summary``,
  ``_timeseries``, ``_anomaly`` (rolling-baseline detection +
  per-run verdict + backfill).  Cross-module helpers dropped
  leading underscores per Phase 35 convention; module-internal
  helpers kept theirs.  Public API surface unchanged via
  ``__init__.py`` re-exports — every existing
  ``from pointlessql.services...operations import X`` continues
  to work.  Two tests updated (``test_operation_warnings.py``
  and ``test_dbt_test_failure_bridge.py``) for renamed cross-
  module helpers.  Pyright budget unchanged at 497.  1686 tests
  pass.  Two commits, one per file split.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 49a — Repo-wide Lint-Sweep closed.**  Two-commit cleanup
  pass clearing pre-existing ruff E501 + pydoclint
  DOC502 / DOC503 / DOC601 / DOC603 violations accumulated since
  Phase 35.  119 ruff hits cleared via ``uv run ruff format``
  (68 files reformatted, mostly test-function signatures wrapped
  to satisfy the 100-char limit); 36 pydoclint hits cleared by
  realigning Raises sections from the framework-rendered
  ``HTTPException`` view to the body-literal typed-error view
  (``AuthenticationError`` / ``ResourceNotFoundError`` /
  ``ValidationError`` / etc.) and by filling in missing
  ``Attributes:`` lines for newer ``Mapped[]`` columns
  (``ApiKey.lineage_inbound``, ``LineageRowEdge.producer`` /
  ``.external_event_id``, ``LineageColumnMap.producer`` /
  ``.external_event_id``) plus the explicit ``status_code`` /
  ``error_code`` class vars on ``RollbackAmbiguous`` /
  ``RollbackStale``.  Pyright budget unchanged at 497.  1686
  tests pass.  Pre-commit was bypassed on the originating
  commits — running ``ruff format`` repo-wide once removes the
  accumulated drift in one pass.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 48 — Primitive-Obsession StrEnum Sweep closed.**
  Five-sub-sprint refactor (1 additive + 4 batch migrations + 1
  CloudEvents registry) in one autonomous run.  Introduces nine
  StrEnums at ``pointlessql/enums.py``
  (``RunStatus`` / ``OpName`` / ``ReadKind`` / ``QueryStatus`` /
  ``ReviewSeverity`` / ``ReviewKind`` / ``AuditSinkType`` /
  ``EventOutcome`` / ``BranchAction``) covering every
  enum-shaped string column in the project.  StrEnum members
  compare equal to their string value, so DB-stored values,
  JSON wire format, and SQL CHECK constraint matching keep
  working unchanged: ``RunStatus.RUNNING == "running"`` is
  ``True`` and JSON serialises as ``'"running"'`` not
  ``'"RunStatus.RUNNING"'``.  Models stay on plain
  ``Mapped[str]`` per anti-goal.  Sprint 48.1 added the
  registry plus 13 sanity tests pinning every value
  byte-for-byte against the legacy ``frozenset`` / tuple
  constants
  (``VALID_STATUSES`` / ``VALID_OP_NAMES`` / ``VALID_READ_KINDS`` /
  ``REVIEW_SEVERITIES`` / ``REVIEW_KINDS`` / ``SINK_TYPES`` /
  ``BRANCH_ACTIONS``).  Sprint 48.2 migrated consumers in four
  batches by field-family: batch 1 RunStatus + QueryStatus
  (~11 files), batch 2 OpName + BranchAction (~13 files),
  batch 3 ReadKind (~5 files), batch 4
  AuditSinkType + EventOutcome + ReviewSeverity (~4 files).
  ``VALID_READ_KINDS`` is now derived from the StrEnum so the
  two cannot drift apart.  Sprint 48.3 introduced
  ``pointlessql/services/cloudevents/`` as the single import
  path for the 17 CloudEvents type literals; the legacy
  ``EVENT_TYPE_*`` aliases on ``services.agent_runs.events``
  and ``services.governance_events`` stay valid for
  back-compat.  Pyright budget unchanged at 497.  1686 tests
  pass (1673 baseline + 13 new enum sanity tests).

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 47 — NewType ID Hardening closed.**  Two-sprint
  refactor in one autonomous run.  Introduces
  ``RunId`` / ``OpId`` / ``QueryHistoryId`` / ``WorkspaceId``
  NewType aliases at ``pointlessql/identifiers.py`` and wires
  them through the public-API entry points of the agent-run
  audit pipeline and the query_history service.  Pyright now
  treats the four IDs as distinct nominal types — passing an
  ``OpId`` where a ``QueryHistoryId`` was expected fails type
  check, even though both erase to ``int`` at runtime.  Models
  stay on plain ``Mapped[str]`` / ``Mapped[int]`` per anti-goal
  (ORM integration with NewType is unspec'd).  Pyright budget
  unchanged at 497.  1673 tests pass (1667 baseline + 6 new
  identifier sanity tests).  Wraps land at the FastAPI
  Path/Query boundary (``RunId(run_id)``,
  ``QueryHistoryId(history_id)``) and at the
  ``operation_context`` cascade across 10 PQL primitives via
  ``cast(RunId | None, ...)``.  Wire format and DB-stored
  values are byte-identical.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 46 — Test-Auth-Fixture Centralization closed.**
  Two-sprint refactor in one autonomous run.  Eliminates ~48
  local ``_admin_client()`` / ``_non_admin_client()`` /
  ``_bearer_client()`` / ``_client(**kwargs)`` helpers and ~7
  local ``Iterator[str]``-shaped ``supervisor_secret`` /
  ``auditor_secret`` / ``normal_secret`` API-key fixtures across
  55 test files.  Net delta -2027 / +1721 LOC across the
  six route-family batches.  1667 tests pass (1661 baseline + 6
  sanity tests).  No production-app changes; production ``app``
  remains the SUT.  Sprint 46.1 added six fixtures to
  ``tests/conftest.py``: ``admin_client``, ``non_admin_client``,
  ``anonymous_client`` (all yielding ``httpx.AsyncClient`` with
  pre-set cookies — or no cookies for ``anonymous_client``); and
  ``supervisor_secret`` / ``auditor_secret`` / ``api_key_secret``
  yielding the new ``ApiKeyFixture`` NamedTuple of
  ``(secret, row, headers)``.  Sprint 46.2 migrated the test
  files in six route-family batches: admin (2), audit (6),
  branch/rollback/promotion (3), models/ML (4),
  supervisor/scheduler (4), catch-all (36).  Four files
  deliberately kept local helpers per the plan's
  "different test pattern" carve-out: ``test_csrf.py`` (raw JWT
  injection), ``test_lineage_inbound_routes.py`` (custom
  ``federation_secret`` Bearer scope),
  ``test_api_key_gate.py`` (interleaved inline AsyncClient
  blocks reusing one ``transport`` variable),
  ``test_training_log_route.py`` (per-call ``X-Agent-Run-Id``
  header injection).  New ``tests/test_auth_fixtures.py`` (6
  cases) pins the fixture contract.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 45 — Pyright Hot-Spot Cleanup closed.**  Five
  file-scoped sprints in one autonomous run, all at JSON / soyuz
  / DuckDB-plan deserialisation seams.  Pyright budget 559 → 497
  (62 warnings closed, 11.1% reduction).  No production-code
  refactor — pure type-narrowing via ``cast(dict[str, Any], …)``
  and ``cast(list[dict[str, Any]], …)`` at boundaries the
  ``isinstance`` narrower can't reach.  No runtime semantics
  change.  Sprint 45.1 narrowed ``audit_sinks_routes.py``
  (12 → 0) with two helpers ``_loads_obj`` / ``_loads_list``
  absorbing every ``json.loads(...) -> Any`` boundary.  Sprint
  45.2 narrowed ``services/sql/cost_estimator.py`` (14 → 0) and
  parenthesised two ``except TypeError, ValueError:`` (PEP 758
  lenient form, valid in Python 3.14) → ``except (TypeError,
  ValueError):`` so ``ValueError`` no longer shadows the
  built-in inside the handler.  Sprint 45.3 narrowed
  ``governance_routes.py`` (10 → 0) on UC ``columns`` /
  ``options`` payloads.  Sprint 45.4 narrowed
  ``volumes_routes.py`` (13 → 3 — three remaining are PyArrow /
  deltalake stub-gap, anti-goal compliant).  Sprint 45.5
  narrowed ``home_routes.py`` (16 → 0) on the UC ``get_tree()``
  cascade and the notebook ``_walk`` recursion.  Skipped the
  three biggest stub-gap files (``pql/_merge.py``,
  ``pql/_autoload.py``, ``services/lineage/inbound_parser.py``,
  197 warnings combined) per memory
  ``feedback_pyright_thirdparty_stubs.md`` — those need custom
  ``.pyi`` stubs for PyArrow / deltalake / OpenLineage, multi-week
  scope, queued for Phase 47 if/when the ROI becomes real.  No
  new tests; annotations don't add behaviour.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 44 — Structured logging + traceback preservation
  closed.**  Five sub-sprints in one autonomous run.  Four gaps
  closed: ``JSONFormatter`` ignored ``extra={...}`` (half-done
  structured logs); 36 lossy broad-except sites
  (``logger.warning("op failed: %s", exc)``) dropped tracebacks;
  47 silent broad-except sites had no opt-out marker (deliberate
  best-effort renders weren't distinguishable from accidental
  silent failures); zero third-party loggers were quieted (httpx
  / urllib3 / sqlalchemy.engine debug noise drowning the
  application's own structured lines).  No Alembic.  Wire format
  strictly additive (legacy seven-field JSON envelope preserved
  when caller passes no ``extra=``).  16 new pytest cases.
  Pyright budget unchanged at 559/559.  Sprint 44.1 added
  ``_harvest_extras`` + ``_RESERVED_LOGRECORD_ATTRS`` so caller-
  supplied ``extra={"run_id": "..."}`` lands as top-level JSON
  keys; reserved attrs stay filtered.  Sprint 44.2 converted lossy
  Bucket-C logs (``logger.warning("...", exc)`` → ``logger.exception("...")``,
  ``logger.debug("...", exc)`` → ``logger.debug("...", exc_info=True)``)
  and added ``# bare-broad-ok: <reason>`` allowlist comments to
  silent Bucket-D sites; new AST-based
  ``tests/test_no_lossy_broad_except.py`` enforces both
  invariants.  Sprint 44.3 retrofitted nine high-value sites
  (scheduler / soyuz-lineage / ml-context / training-context /
  notebook-render / alert-dispatcher / audit self-track /
  read-audit) to use ``extra={...}`` so Grafana/Loki can key off
  ``run_id`` / ``op_name`` / ``webhook_url`` etc.  Sprint 44.4
  added per-library quieting (``httpx`` / ``urllib3`` /
  ``sqlalchemy.engine`` → WARNING; ``mlflow`` / ``dbt`` /
  ``papermill`` → INFO) with override via
  ``POINTLESSQL_LOG_THIRD_PARTY_LEVELS`` env var.  Global
  ``POINTLESSQL_LOG_LEVEL=DEBUG`` bypasses the quieting entirely.
  Sprint 44.5 added ``"BLE"`` to ``[tool.ruff.lint] select`` and
  closed two missing-noqa sites — the linter now catches
  broad-except regressions in addition to the AST quality lint.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 43 — Error envelope + exception hierarchy unification
  closed.**  Five sub-sprints in one autonomous run.  Three
  asymmetries closed: zero-enum-for-error-codes, three orphan
  exception families, 42 bare-string ``HTTPException`` sites.
  Sprint 43.1 introduced the central ``ErrorCode`` ``StrEnum`` in
  ``pointlessql/error_codes.py`` (35 members grouped by domain);
  every ``PointlessSQLError`` subclass now references an enum
  member via ``error_code: ErrorCode = ErrorCode.X`` instead of a
  raw string.  Sprint 43.2 reparented ``BranchError`` (×6),
  ``RollbackError`` (×4), ``DBTStartupError`` /
  ``DBTExecutionError`` / ``MLflowStartupError`` (dual-parent with
  ``RuntimeError``), ``AuditIntegrityError``,
  ``BranchTagsCorruptError``, ``SQLParseError`` under
  ``PointlessSQLError`` so the centralised handler picks them up
  directly; new ``extension_members()`` hook on the base class
  surfaces structured fields automatically (replaces the inline
  ``isinstance(AuthorizationError)`` branch).  ``RollbackStale``
  flips 422 → 409 and ``RollbackAmbiguous`` 422 → 409 (semantic
  conflict, not request-validation).  Sprint 43.3 converted 42 →
  2 bare-string ``HTTPException`` sites; new
  ``PermissionDeniedError``/``ResourceNotFoundError``/``ConflictError``
  in ``pointlessql/exceptions.py``; ``DBTExecutionError``
  ``except`` blocks deleted (subclass now self-renders); 2 proxy-
  upstream 502s allowlisted via ``# bare-http-ok`` comment +
  ``tests/test_no_bare_http_exception.py`` lint test.  Sprint 43.4
  added ``ErrorEnvelope`` Pydantic models in
  ``pointlessql/api/error_envelope.py`` and
  ``STANDARD_ERROR_RESPONSES`` constants in
  ``pointlessql/api/error_responses.py``; applied selectively to
  13 plugin-facing routes so OpenAPI exposes the envelope.
  Sprint 43.5 (plugin-side) extended ``run()`` helper in
  ``hermes-plugin-pointlessql/.../tools/_common.py`` to parse
  ``application/problem+json`` body and surface ``code`` plus 11
  extension members to the agent envelope; falls back to legacy
  text shape for non-problem responses.  No Alembic migrations.
  Wire format strictly additive (StrEnum subclasses ``str``;
  legacy assertions stay green).  ~57 new pytest cases (5 +
  ~28 + ~19 + 4 PointlesSQL-side; 5 plugin-side).  Pyright
  budget unchanged at 559/559.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 42 — Anomaly-Inbox System-Errors band closed.**  Single
  sprint (42.1) that surfaces foreign-Delta CDF subscriptions with
  ``last_error IS NOT NULL`` on ``/audit/inbox``.  New
  server-rendered ``<section data-inbox-section="system-errors">``
  above the existing filter form / sigma anomaly table on
  ``frontend/templates/pages/audit_inbox.html``; conditional on
  ``{% if system_errors %}`` so a healthy workspace renders zero
  noise.  Loader ``_load_system_errors`` in
  ``pointlessql/api/audit_inbox_routes.py`` queries
  ``cdf_tail_subscriptions WHERE workspace_id=? AND last_error IS NOT NULL``
  ordered ``last_tailed_at DESC NULLS LAST``.  Each row shows the
  truncated error, paused-badge if ``is_active=False``, last-attempt
  ISO timestamp, producer label, and an "Open admin" cross-link
  (auditor sees, admin clears — auditor scope stays read-only).
  No new Alembic migration, no new sigma metric (CDF errors are
  point-in-time state, not event counts), no acknowledge table
  (errors clear automatically on the next successful tail tick).
  4 new pytest cases (renders, hides, workspace-isolation,
  paused-marker).  Walkthrough ``audit-cockpit-deep.md`` extended
  with Part E (3 steps).

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 40.7 — Row-Trace fold-in of CDF events closed.**  Single
  sprint that resolves Phase-40.6's deferred boundary discussion.
  Foreign-Delta CDF events captured by the Phase-40.5 tail now
  fold into the existing row-trace walkback as contextual metadata
  per step — every walkback step gets a ``cdf_events: []`` field
  populated from
  ``cdf_tail_events WHERE workspace_id=? AND table_full_name=? AND row_id=?``.
  Walkback semantics stay unchanged (predecessors come exclusively
  from ``lineage_row_edges``); CDF captures are pure context, never
  new walkback steps.  New service helper
  ``pointlessql.services.cdf_tail.fetch_events_for_row`` mirrors
  ``fetch_value_changes_for_row``; new route helper
  ``_attach_cdf_events`` mirrors ``_attach_value_changes``.
  Template adds a new ``<details>`` block on
  ``pages/row_trace.html`` with version pill + change-type pill +
  timestamps; change-type pill extracted into reusable
  ``partials/_cdf_change_type_pill.html`` and shared with the
  Phase-40.6 table-detail CDF events tab.  No new Alembic
  migration, no new credential surface, no new plugin tool — the
  existing ``pql_row_trace`` ships ``cdf_events`` per step
  transparently.  3 new pytest cases (attach, empty-list-default,
  workspace-isolation).

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 40.6 — CDF Tail UI integration closed.**  Three thin
  sprints turn the Phase-40.5 capture surface into a fully
  browsable + agent-readable governance surface.  Sprint 40.6.1
  ships the admin subscriptions page at
  ``/admin/cdf-subscriptions`` (CRUD + ``Run tail now`` +
  table-FQN filter + only-active toggle) and adds an 8th card
  to the admin landing with active-count + with-errors badges.
  Sprint 40.6.2 mounts a 7th "CDF events" tab on the
  table-detail page, gated server-side on
  ``cdf_subscription is not None`` so tables without a
  subscription still show 6 tabs.  Sprint 40.6.3 ships two new
  auditor-scope read endpoints
  (``GET /api/audit/cdf-subscriptions`` +
  ``GET /api/audit/cdf-events``) and two new plugin tools
  (``pql_list_cdf_subscriptions`` +
  ``pql_recent_cdf_events_for_table``).  No new Alembic
  migrations, no new credential surface — the UI just
  surfaces what 40.5 captured.  9 new pytest cases
  PointlesSQL-side + 6 plugin-side.  50th end-to-end
  walkthrough at ``docs/e2e-walkthroughs/admin-cdf-tail.md``.
  Anti-goal kept: row-trace fold-in of CDF events stays
  deferred — they're a different boundary from
  ``lineage_row_edges`` and forcing the merge needs its own
  Phase 40.7 scope.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 40.5 — Foreign-Delta CDF tail (pull-modell) closed.**
  Closes the deferred Sprint-40.2 sketch as a single sprint.
  New Alembic ``qq7t9v1x3z5b`` adds ``cdf_tail_subscriptions``
  (opt-in registry, ``UNIQUE(workspace_id, table_full_name)``)
  and ``cdf_tail_events`` (capture log, ``UNIQUE`` on
  ``(table_full_name, delta_version, row_id, change_type)``)
  so re-tails are idempotent.  ``services/cdf_tail.py`` exposes
  ``tail_subscription`` (sync) + ``tail_all`` (async walker that
  resolves ``storage_location`` via ``uc.get_table`` per tick
  and stamps ``last_error`` on failure).  Admin CRUD lives under
  ``/api/admin/cdf-subscriptions`` (GET / POST / toggle / DELETE)
  plus a manual ``POST /run-now``.  New ``CDFTailSettings``
  (``POINTLESSQL_CDF_TAIL_INTERVAL_SECONDS`` /
  ``..._HISTORY_LIMIT``) joins the root settings tree; the
  ``_cdf_tail_loop`` worker registers in the lifespan next to
  the external-writes scanner with the same opt-in
  (``interval_seconds == 0`` → off) + cancel-on-shutdown
  discipline.  Anti-goal "no new credential surface" preserved:
  the worker reuses whatever soyuz's ``storage_location`` already
  exposes; un-readable tables stamp ``last_error`` rather than
  failing the whole tick.  9 pytest cases.  Also closes a stale
  fixture gap — the autouse conftest now stubs
  ``app.state.uc_client`` with a default ``MagicMock`` so any
  test rendering ``/runs/{id}`` (which now reads UC mutations
  via ``soyuz_audit.fetch_for_run``) doesn't crash on a missing
  attribute.  ``test_run_detail_renders_operations_and_source_tabs``
  is back to green; full pytest sweep 1587/1587.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 41 — Sprint 17.6 promote: Lineage sub-panes closed.**
  Single-sprint UX-consolidation phase post the
  "plane phase 41 komplett aus" plan.  Three new drill-down
  sub-pills (Row trace / Column trace / Value changes) live next
  to the existing Summary + Graph pills inside the Lineage
  top-tab on ``/runs/{id}``.  Each pane wraps one of the
  existing ``GET /api/lineage/{row-trace,column-trace,
  value-changes}`` endpoints; no new SQL surface, no new routes.
  The standalone ``/catalogs/.../rows/{id}/trace`` and
  ``/catalogs/.../columns/{name}/trace`` pages stay
  route-mounted for direct-link compatibility.  New file
  ``frontend/js/components/lineage_panes.js`` carries the three
  Alpine factories (``rowTracePane`` / ``columnTracePane`` /
  ``valueChangesPane``) plus a ``bindLineageTraceButtons()`` one-shot
  initialiser that exposes ``window.pqlLineageTraceRow / Column /
  Value`` helpers and event-delegates clicks on
  ``button[data-pql-trace-row="1"]``.  Three custom window events
  (``pql:trace-row`` / ``pql:trace-column`` / ``pql:trace-value``)
  stitch Summary "Trace target row" buttons + Graph side-panel
  "Trace this column" buttons into the corresponding sub-pill,
  flipping the active tab via Bootstrap 5's ``Tab.show()`` JS
  API and pre-populating the picker.  ``load_lineage_summary_for_run``
  gained one ``func.min(LineageRowEdge.target_row_id)`` column
  (``sample_target_row_id``) so Summary deep-links carry a
  representative row id; the new key flows through to
  ``GET /api/agent-runs/{id}/audit/lineage`` additively.  3
  pytest cases (loader, HTML mount, deep-link button attrs); 138
  pre-existing run-detail / lineage tests stay green.  Browser
  replay against the rebuilt e2e container confirmed zero
  console errors and end-to-end Summary-click → Row-trace-pane
  fetch.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 40 — Lakehouse Federation reads (OpenLineage) closed.**
  Four sub-sprints landed in one autonomous session post the
  "plane phase 40 aus" plan; Sprint 40.2 (foreign-Delta CDF tail
  worker) was deliberately deferred to Phase 40.5 at plan time.
  Sprint 40.0 (Alembic ``oo5q7s9u1x3z``) relaxed ``run_id`` /
  ``op_id`` to nullable on ``lineage_row_edges`` /
  ``lineage_column_map`` and added ``producer`` +
  ``external_event_id`` columns; ``api_keys.lineage_inbound``
  added a third API-key scope independent of supervisor /
  auditor.  Sprint 40.1 added ``POST /api/lineage/openlineage``,
  the inbound surface — external producers (Kafka-Connect,
  Airflow, dbt-cloud, peer PointlesSQL installs) push OpenLineage
  1.x ``RunEvent`` envelopes that normalise into the existing
  shadow tables tagged with ``producer = event.job.namespace``,
  with idempotency on ``(producer, external_event_id, ...)``
  composite keys and forward-compat ``extra="allow"`` on the
  Pydantic models.  Sprint 40.3 wired an "External producers"
  block into ``components/lineage_card.html`` on the table-detail
  page, rendered with amber Bootstrap badges to visually
  distinguish federated edges from internal ones.  Sprint 40.4
  added ``expected_lineage_inbound`` (Alembic ``pp6r8t0v2x4z``)
  + ``services/lineage_freshness.py`` (compute, alert-candidate
  selection, ``stamp_alerted``, CloudEvents envelope) + the
  ``/api/admin/expected-producers`` CRUD surface.  Pyright budget
  bumped 528 → 559 (inbound parser walks ``Any``-typed JSON,
  same shape as the Phase-36.2 dbt-bridge bump).  27 new pytest
  cases (8 inbound, 6 table-detail aggregator, 13 freshness +
  CRUD) all green.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 39 — Agent EXPLAIN-driven self-rewrite loop closed.**
  Four sub-sprints landed in one autonomous session.  The Hermes
  plugin's ``pql_query`` tool now hits ``GET /api/sql/explain``
  before ``POST /api/sql/execute``.  When the cost-gate verdict
  says ``needs_approval=True`` the tool returns a structured
  ``cost_gate_denied`` envelope carrying the EXPLAIN tree + a
  rewrite hint so the LLM can revise and retry.  Per-run state
  on the client tracks attempts + the original SQL hash; at
  attempt 4 the envelope flips to ``human_approval_required``
  and the plugin POSTs one ``rewrite_attempts`` row to PointlesSQL.
  A subsequent successful rewrite writes a second
  ``auto_rewrite_succeeded`` row.  Sprint 39.1 plumbed the
  per-run audit (new ``op_name='sql_explain'`` op rows when
  ``X-Agent-Run-Id`` is set, Alembic ``mm3o5q7s9u1x``).
  Sprint 39.2 added the ``rewrite_attempts`` table + route
  + run-detail "Rewrites" sub-pane on the Operations top-tab
  (Alembic ``nn4p6r8t0v2y``).  Sprint 39.3 wired the plugin loop
  (cross-repo commit ``576c5dc`` in ``hermes-plugin-pointlessql``).
  Sprint 39.4 added the
  ``docs/e2e-walkthroughs/explain-rewrite.md`` playbook (49th)
  and Grafana panel id 21 ("Rewrite savings — averted cost-gate
  denials per week") in both the SQLite and Postgres audit
  dashboards.  Audit POSTs are fail-soft so an older
  PointlesSQL server lacking the route doesn't crash the agent
  turn.  Pyright + file-size + Grafana-lint budgets all hold;
  10 new pytest cases on the PointlesSQL side, 5 on the
  plugin side.

- **Roadmap — three queued feature pillars after Phase 38.**
  Records the next forward-motion candidates surfaced after the
  Phase-38 sprint sweep closed everything carryable from the
  cleanup track.  Phase 39 (Agent EXPLAIN-driven self-rewrite
  loop) revives the Phase-13 EXPLAIN-loop sketch — agents read
  ``EXPLAIN (FORMAT JSON)`` pre-execution, see the cost-gate
  verdict, and self-rewrite SQL before submission instead of
  bouncing off ``cost_gate_trigger``.  Phase 40 (Lakehouse
  Federation reads — OpenLineage / CDF) closes the inbound side
  of the federation story: today PointlesSQL emits OpenLineage
  outbound and registers federated tables via soyuz, but the
  audit-graph stops at the soyuz boundary on read; this phase
  adds an OpenLineage inbound endpoint, a CDF tail worker, and
  a merged-lineage card on table-detail pages.  Phase 41 promotes
  Sprint 17.6 (lineage trace sub-panes) out of the Phase-17
  sub-tree into its own phase so the smallest UX-only track
  doesn't get lost behind the two larger feature pillars.  No
  order enforcement between 39 / 40 / 41 — all three carry ``⏳``.

- **Sprint 36.7 — dbt end-to-end walkthrough + Phase 36 close.**
  Phase 36 closes ✅ in the same session Phase 38.2 had marked
  it ``⏸ upstream``.  Trigger was the dbt-labs/dbt-core#12098
  link surfaced via web search: ``mashumaro 3.17`` carries the
  Python-3.14 ``Optional[str]`` fix.  ``dbt-core 1.11`` still
  declares ``mashumaro<3.15``, but force-installing 3.17 runs
  clean against ``dbt-core 1.11.8`` + ``dbt-adapters 1.22.10``.
  The override now lives in ``pyproject.toml`` as
  ``[tool.uv] override-dependencies = ["mashumaro[msgpack]>=3.17"]``
  so ``uv sync --extra dbt`` produces a working environment on
  Python 3.14 without manual intervention.  Walkthrough
  ``dbt-pipeline.md`` Part C grew from 4 steps to 5 (added the
  ``pip install --no-deps mashumaro==3.17`` step + the
  ``dbt docs generate`` step that lands ``catalog.json``).
  End-to-end verified live in Firefox via Playwright MCP: the
  Phase-36.4 cockpit chrome populates with ``models=3 /
  tests=6 / coverage=66.7%``, both Recent runs + Test failures
  sub-tabs lazy-load with empty-state messages, 0 console
  errors on ``/dbt``.  Drop the override once dbt-core ships
  a release that bumps its own pin.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 38 — Sprint-Sweep (35.4 close + 36.7 defer + cockpit
  data-path).**  One autonomous session post the "plane die
  restliche aufgaben aus" plan.  Three sub-sprints, three
  commits.  Sprint 38.1 closes the deferred Sprint 35.4: the
  1467-LOC ``run_view.html`` is now a 229-LOC parent +
  eight partials in ``frontend/templates/partials/_run_*.html``
  (header, metadata, conformance, approval form, four tab
  panes).  Behaviour-equivalent; verified end-to-end via
  Playwright MCP — all four top-tabs and 13 sub-tabs render
  with 0 console errors, the URL-hash deeplink activator
  promotes both parent and leaf tabs, and the ``rollbackPanel``
  Alpine factory binds cleanly with the ``:class="{ 'd-block':
  modalOpen }"`` modal toggle preserved (BUG-67-01-class
  regression check).  Sprint 38.2 ran the upfront feasibility
  check for Sprint 36.7 (dbt end-to-end walkthrough) and
  confirmed the upstream blocker still holds: ``dbt-duckdb
  1.10.1`` + ``dbt-core 1.11.8`` + ``mashumaro 3.14`` on
  Python 3.14.4 still raises ``UnserializableField: Field
  "schema" of type Optional[str] in JSONObjectSchema`` at
  import time — root cause is mashumaro's unpacker compiler
  not handling ``Optional[str]`` annotations under Python
  3.14, with no downstream workaround.  Sprint 36.7 status
  flipped from ``⏸ Playwright`` to ``⏸ upstream``;
  ``dbt-pipeline.md`` Part C Caveat now records the exact
  pins + trace + verification date.  Sprint 38.3 verified
  the data path of the Phase-37 ``audit-cockpit-deep.md``
  walkthrough against ``seed-broken-run.py`` + a partial
  ``seed-full-stack-demo.py`` run: ``/audit/inbox`` shows
  "2 of 2 breach(es)", ``/api/audit/search?q=silver`` returns
  1 hit (custom tokenizer), ``/audit/by-table/demo.incidents.broken_orders``
  serves the populated cockpit ("2 run(s) touched …"), and
  the ``top-mutating-principals-30d`` starter query returns
  200 with 2 rows.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 37.1 — Phase-37 BUG sweep.**  Closes the five open
  BUG-37-NN tickets surfaced during the Phase-37 walkthrough
  replay.  BUG-37-04 (HTMX null-deref on
  ``/audit/inbox`` / ``/audit/search`` / ``/alerts``
  page-load) fixed via a CDN pin bump from htmx 2.0.3 to
  2.0.6, which added the ``if (o == null || o === "") …``
  guard before the offending ``o.includes("?")`` call.
  BUG-37-05 (``/audit/by-table`` empty path renders three
  user-visible ``Error 422`` rows from the tab loaders)
  fixed by adding a no-FQN handler that serves an FQN
  picker form instead of the tab chrome.  BUG-37-02 (admin
  context-panel missing five entries) and BUG-37-03
  (mobile-drawer Admin link with ``href="#"``) fixed in
  ``components/context_panel.html`` and
  ``components/nav_links.html``.  BUG-37-06 (Phase-36.4
  dbt cockpit chrome missing) closed by landing the
  manifest summary card-row + 3-tab nav (Pipeline docs /
  Recent runs / Test failures) on ``/dbt`` plus a new
  ``GET /api/dbt/runs`` route and the ``agent_run_id``
  query param made optional on ``GET /api/dbt/test-failures``.
  Sprint 36.4 flipped from ``⏸ Playwright`` to ``✅``.
  All five fixes verified end-to-end via Playwright MCP
  (zero console errors across the touched pages).

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 37 — Playwright coverage refresh (post-Phase-22/23).**
  Brings ``docs/e2e-walkthroughs/`` back to complete UI
  coverage after Phase 14, 17, 18.6+, 28, 33, and 36 features
  landed pages without dedicated playbooks.  Wave 0a rewrites
  ``audit-sinks.md`` from a curl-only operational runbook into
  a UI-driven walkthrough (Phase 33.2 added the admin page that
  the original playbook said didn't exist) — surfacing
  BUG-37-01 (Alpine ``x-data`` attribute escaping on four admin
  row templates, fixed in ``a744b52``).  Wave 0b applies three
  surgical updates to ``grand-tour.md`` for Phase-28 workspace
  switcher and Phase-33 admin landing.  Wave 1 lands
  ``admin-console.md`` covering the Phase-33 landing 7-card
  grid + 5 sub-pages (the API-keys plaintext-secret modal
  carries the strongest redaction property: the secret lives
  in the ``<input>``'s ``.value`` DOM property only and is
  never serialised into ``outerHTML``).  Wave 2 lands
  ``audit-cockpit-deep.md`` for the four Phase-18.6 → 18.x
  cockpit pages.  Wave 3 lands ``run-comparisons.md`` covering
  both compare surfaces (audit run-diff + jobs run-compare).
  Wave 4 lands ``alerts.md``.  Wave 5 lands ``dbt-pipeline.md``
  via the D3b path — covers the iframe-only chrome that exists
  today + files BUG-37-06 for the still-paused Phase-36.4
  cockpit chrome (manifest summary card + test-failures table
  + run-view sub-tab).  Five additional bugs filed during live
  replay (BUG-37-02 through 06).  README index updated with
  the five new entries; CLAUDE.md playbook count refreshed
  to 48.

- **Sprint 36.D — dbt bridge captures Delta versions for rollback
  anchors.**  Closes the production-side gap surfaced after 36.C
  landed: ``pql.rollback`` was refusing every dbt-driven rollback
  with ``RollbackInvalid`` because the bridge wrote
  ``delta_version_before=None`` / ``delta_version_after=None`` on
  every ``dbt_model`` op (the gate reads ``before is None`` as
  "this op created the table" → drop is out of v1 scope).  Auto-
  rollback (36.C) was therefore an API hull, not a working feature.

  New ``services/dbt_bridge.capture_delta_versions(uc_client,
  relations) -> {relation: version|None}`` helper looks up each
  relation's soyuz-catalog ``storage_location`` and reads
  :class:`deltalake.DeltaTable.version()`.  Best-effort: catalog
  miss, missing location, non-Delta target, or transport hiccup
  all map to ``None`` so a partial capture (some Delta-backed,
  some DuckDB-native) keeps the rollback gate honest per row.

  ``/api/dbt/{run,test}`` now runs the helper twice:
  pre-execution (against the existing manifest, populating
  ``delta_version_before``) and post-execution (against the
  freshly-written manifest, populating ``delta_version_after``).
  ``emit_operations_for_dbt_run`` accepts new ``pre_versions`` /
  ``post_versions`` keyword args and stamps each ``dbt_model``
  row's columns from those maps.  ``dbt_test`` rows never pull
  from the maps — tests don't materialise targets.

  Limitation, documented in the helper docstring: dbt-duckdb's
  default ``table`` materialisation writes DuckDB-native tables,
  not Delta — for those, ``DeltaTable(loc)`` raises and the
  relation maps to ``None``.  Auto-rollback continues to fail for
  pure-DuckDB targets; the fix is meaningful for projects that
  opt into the Delta materialisation adapter or write through
  PointlesSQL's PQL primitives.

  3 new pytest cases:
  ``test_capture_delta_versions_returns_none_for_unresolvable_relations``
  exercises the except clause; the bridge test
  ``test_emit_operations_populates_delta_versions_from_pre_post_maps``
  asserts the maps land on the persisted rows; the route-level
  ``test_run_populates_delta_versions_when_capture_succeeds``
  proves the wiring end-to-end through ``/api/dbt/run``.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 36 Restabschluss — Stream A backend close (sub-sprints
  36.A / 36.B / 36.C).**  Closes the gaps that 36.1–36.6 deferred
  inside individual sprints, leaving only the Playwright-gated UI
  (36.4) + e2e walkthrough (36.7) for a separate session.

  - **36.A — Sample dbt project + real-binary integration test.**
    A 3-model / 5-test demo project lands at ``dbt_project/`` (bronze
    → silver → gold pipeline plus ``not_null`` / ``unique`` /
    ``accepted_values`` / ``relationships`` tests against a 10-row
    seed).  ``tests/test_dbt_real_subprocess.py`` (marked
    ``@pytest.mark.integration``) runs real ``dbt compile`` and a
    full ``dbt seed → run → test`` against the project, asserts
    against the bridge's :func:`parse_manifest` /
    :func:`merge_manifest_and_results` projection, and skips
    cleanly when ``dbt-duckdb`` isn't importable for the active
    Python interpreter (Python-3.14 + dbt-duckdb-1.9 currently
    raises ``mashumaro.UnserializableField`` during CLI module
    import; the wrapper handles non-``ImportError`` failures).
    A new public ``DBTExecutor.seed`` method lets the test (and
    future agent flows) materialise CSV seeds without reaching
    into ``_run``.

  - **36.B — Read-only API + read-only plugin tools.**  Three new
    GET routes on PointlesSQL: ``/api/dbt/manifest`` (any
    authenticated user — projects ``target/manifest.json`` to a
    model summary with attached tests), ``/api/dbt/coverage``
    (test-coverage ratio + untested-model list), and
    ``/api/dbt/test-failures`` (joins ``lineage_row_rejects``
    where ``reason='expectation_failed'`` with
    ``agent_run_operations``; supervisor or auditor scope).  The
    manifest-projection logic lifts to
    :mod:`pointlessql.services.dbt_bridge` (``as_dict`` /
    ``as_list`` / ``project_models``) so the plugin's
    ``pql_dbt_show_lineage`` reuses the same canonical projection.
    Three new Hermes tools land in
    ``hermes-plugin-pointlessql``: ``pql_dbt_list_models``
    (no-arg manifest summary), ``pql_dbt_show_lineage``
    (parents/children walk, accepts unique_id or short name),
    and ``pql_dbt_get_test_failures``
    (per-run failing tests with model relation, severity, and
    op id).  Closes the trigger → inspect loop without re-spawning
    a dbt subprocess.

  - **36.C — Auto-rollback on error-severity test failures.**
    ``POST /api/dbt/test`` accepts a new ``auto_rollback: bool``
    body parameter (default ``False``).  When set and the run has
    at least one error-severity failing test, the route walks every
    ``dbt_model`` op in the run (newest-first) and invokes
    ``pql.rollback`` for each — collecting per-target outcomes
    (``succeeded`` vs. ``failed``) into the response envelope's new
    ``auto_rollback`` block.  Per-target refusals (``RollbackStale``,
    ``RollbackInvalid``, …) land in ``failed`` rather than aborting
    the sweep — auto-rollback is best-effort by design.  A new
    ``pointlessql.dbt.auto_rollback.executed`` CloudEvent fires
    once per attempted unwind with the aggregate counts.  Auto-
    rollback fires *only* on the test path: model writes are
    reverted because tests failed, never as a side-effect of the
    run itself.

  Plus housekeeping: ``pointlessql/api/dbt_routes.py`` joins the
  file-size allowlist (cohesive dbt orchestration surface; manifest
  projection already lives in the bridge); ``services/dbt_bridge.py``
  gains ``as_dict`` / ``as_list`` / ``project_models``;
  ``pointlessql/services/governance_events.py`` adds
  ``EVENT_TYPE_DBT_AUTO_ROLLBACK_EXECUTED``; pyright budget held at
  528 across the three sub-sprints.

- **Sprint 36.6 — Hermes plugin: dbt-pipeline trigger tools.**
  Three new tools land in ``hermes-plugin-pointlessql``:
  ``pql_dbt_compile`` (read-only manifest refresh, any user),
  ``pql_dbt_run`` (materialise models, supervisor scope),
  ``pql_dbt_test`` (evaluate tests, supervisor scope).  Each forwards
  ``POINTLESSQL_AGENT_RUN_ID`` via the ``X-Agent-Run-Id`` header so
  the dbt subprocess's emitted operations attribute under the same
  forced-audit-trail run as the rest of the agent's work; absent
  the env var, PointlesSQL auto-creates a run keyed to the calling
  user's email.  Per-test failure rejects (one
  ``lineage_row_rejects`` per failing test) are surfaced via the
  existing ``pql_query_rejects`` auditor tool.  The plan's three
  read-only tools (``pql_dbt_list_models`` /
  ``pql_dbt_show_lineage`` / ``pql_dbt_get_test_failures``) need
  new manifest-introspection endpoints on the PointlesSQL side
  and are deferred to a follow-up sprint.

- **Sprint 36.5 — severity enforcement + dbt CloudEvents.**  Three
  new governance event types: ``pointlessql.dbt.run.completed``
  fires once per ``/api/dbt/run`` and ``/api/dbt/test`` invocation;
  ``pointlessql.dbt.test.failed`` fires once per error-severity
  failing test (these are the run-failing ones);
  ``pointlessql.dbt.test.warned`` fires once per warn-severity
  failing test (run still succeeds — anomaly-only).  New
  ``_classify_severity`` helper buckets failures by severity; auto-
  created runs finish as ``failed`` only when ``err_failures > 0``,
  so a project with ``severity: warn`` tests keeps deploying while
  the cockpit's anomaly inbox surfaces the warning.  Auto-rollback
  on error-severity failure (``pql.rollback`` per affected model)
  is deferred — the four refusal modes in ``RollbackError`` need
  per-test gating that exceeds this sprint's scope.  7 new tests
  cover both the classifier and the end-to-end event emission.

- **Sprint 36.3 — dbt test-failure → lineage_row_rejects +
  ``expectation_failures`` anomaly axis.**  ``REJECT_REASONS`` +
  the SQL CHECK constraint on ``lineage_row_rejects`` gain
  ``expectation_failed`` (alembic ``ll2n4p6r8t0w``).
  ``services/dbt_bridge.emit_test_failure_rejects`` walks the
  per-node results paired with their ``agent_run_operations.id``
  values and inserts one reject row per failing dbt test
  (``status='fail'``).  ``source_row_id`` is the test's
  ``unique_id``, ``detail`` carries dbt's failure message verbatim.
  Per-row extraction (one reject per failing data row) is deferred
  — capturing those needs ``dbt test --store-failures`` plus a
  follow-up SELECT against ``dbt_test__audit.<test_name>``.
  ``services/audit_aggregator`` gains an ``expectation_failures``
  metric: a row-level WHERE filter on
  ``lineage_row_rejects.reason`` that lets the cockpit show
  dbt-side data-quality failures separately from merge-time
  rejects.  ``/api/dbt/run`` and ``/api/dbt/test`` summaries now
  carry ``rejects_inserted``.  4 new tests, all green.

- **Sprint 36.2 — on-demand ``dbt run/test/compile`` + manifest
  bridge.**  Three new POST routes — ``/api/dbt/compile`` (auth-
  only), ``/api/dbt/run`` and ``/api/dbt/test`` (supervisor scope) —
  plus an admin-only ``/api/dbt/deps`` for package installs.  The
  shared ``services/dbt_executor.py`` spawns dbt as an async
  subprocess with a configurable timeout, captures stdout/stderr
  with a 256 KiB-per-stream cap, and never raises on non-zero exit
  codes (those land on ``DBTRunResult.exit_code``).  The shared
  ``services/dbt_bridge.py`` parses ``target/manifest.json`` +
  ``target/run_results.json`` and emits one ``agent_run_operations``
  row per executed model or test (op_names ``dbt_model`` / ``dbt_test``
  added to ``VALID_OP_NAMES`` + the SQL CHECK via alembic
  ``kk1m3o5q7s9v``).  ``params_json`` captures the manifest-side
  fields (``unique_id``, ``materialization``, ``execution_time``,
  ``severity``, ``depends_on``) so a reviewer can see why each row
  exists without joining back to the manifest.  Routes that auto-
  create an ``AgentRun`` (``agent_id="dbt-cli"``) finish it on exit;
  caller-supplied run ids stay caller-managed.  Failure visibility
  for tests + severity enforcement land in 36.3 / 36.5.  19 new
  unit + integration tests; pyright budget bumped 522 → 528 to
  cover the JSON-parse cascade in dbt_bridge.

- **Sprint 36.1 — dbt-docs subprocess + reverse-proxy** (Phase 36
  start).  Mirrors the MLflow integration: ``DBTSettings`` block
  (``POINTLESSQL_DBT_*`` env prefix, default ``docs_port=5002``,
  ``project_dir=dbt_project/``), ``services/dbt_subprocess.py``
  with async spawn of ``dbt docs serve`` + HTTP health-poll + PID
  file + SIGTERM-then-SIGKILL shutdown, ``api/dbt_proxy.py``
  reverse-proxy at ``/dbt-docs/`` with ``X-DBT-User`` header
  injection, ``api/dbt_html_routes.py`` chrome page at ``/dbt``
  plus icon-rail entry.  Pre-flight ``project_ready()`` check
  skips the spawn when no compiled ``target/manifest.json``
  exists, so a freshly-cloned repo logs a friendly info message
  instead of a noisy startup error.  Optional extra ``[dbt]``
  adds ``dbt-duckdb >= 1.9, < 2.0`` (``dbt-expectations`` and
  ``dbt-utils`` are dbt packages installed via ``dbt deps``,
  not pip).  14 new unit tests (8 subprocess + 6 proxy);
  pre-commit chain green, pyright budget unchanged at 522/0.

- **Docstring overhaul (2026-05-06)** — Two-stream cleanup pass over
  ``pointlessql/`` docstrings and inline code comments.  Stream A
  stripped 220+ project-history references (``Phase X``, ``Sprint Y``,
  ``ADR-NNNN``, ``BUG-NN-NN``, parenthesized variants) that described
  *when* a piece of code was written rather than *what* it does or
  *why* — those tokens age the moment the next phase ships.  Stream B
  added Why-bodies to three high-summary-only modules: 15 of 22
  routes in ``api/federation_routes.py`` (audit + soyuz-outage
  handling), 8 of 12 helpers in ``api/jobs_routes.py`` (visibility
  + scheduler-effect notes), and 6 of 10 helpers in
  ``services/run_diff.py`` (alignment-strategy + diff-shape
  rationale).  Globally, summary-only ratio drops from 22.8% to
  17.7%; ``alembic/versions/*`` migration docstrings stay as-is
  (legitimately time-locked records).  All gates green: pydoclint
  0 violations, ruff clean, pyright 0/522 unchanged, full SQLite
  suite 1478 passed / 6 skipped.

- **Sprint 35.8 closed (2026-05-06)** — Two CI regression guards
  added so the Phase-35 modularization + type-hardening don't
  decay over time.  ``scripts/check-file-size-budget.sh`` (~75
  LOC) fails CI when any ``pointlessql/**.py`` exceeds 800 LOC
  unless it appears in an explicit allow-list with a comment
  explaining why it's big-by-design.  Today's allow-list:
  ``pql.py`` (788), ``api/main.py`` (785), ``settings.py`` (721),
  the alembic squash (713), ``services/scheduler/runs.py`` (849),
  ``api/jobs_routes.py`` (804), ``api/sql_routes.py`` (766),
  ``pql/_merge.py`` (731), and the three Sprint-35-audit
  cohesive files (``audit_routes.py`` 1103, ``audit_aggregator.py``
  897, ``services/agent_runs/operations.py`` 874).
  ``scripts/check-pyright-budget.sh`` (~50 LOC) parses the
  trailing ``N errors, M warnings`` summary line and fails when
  warnings exceed the budget (frozen at 522 post-35.6) or errors
  are non-zero.  Both scripts wired into ``.pre-commit-config.yaml``
  and ``.github/workflows/test.yml`` (lint+type+docstring+alembic
  job).  Closes Phase 35.

- **Sprint 35.7 skipped (2026-05-06)** — Investigation found the
  ``_frame_to_arrow(frame: Any) -> pa.Table`` function already
  produces a typed return; callers see correct types.  The
  "partially unknown" warnings inside the function come from
  ``pa.array(...)`` and ``pa.Table.from_pandas(...)`` returning
  ``Unknown`` due to incomplete pyarrow stubs — ``@overload`` on
  the public surface cannot reach that cascade.  Adding
  ``@overload`` for pandas / polars / DuckDB inputs would not
  reduce warnings because callers pass ``Any`` from upstream
  ``_resolve_source_frame``.  Real reduction would need custom
  pyarrow ``.pyi`` stubs — out of scope for a single sprint.
  Sprint marked skipped; warning floor freezes at 522.

- **Sprint 35.6 closed (2026-05-06)** — Type-hardening:
  ``services/value_change_capture.py`` got explicit annotations on
  the locals where pyright lost type information: ``column_names:
  set[str]``, ``data: dict[str, list[Any]]``, ``diff_columns:
  list[str]``, ``row_id_raw: Any``.  Plan estimated ≥18 fewer
  warnings; **actual is 9** — pyright stays uncertain on
  ``data[col][i]`` indexing patterns even with the dict typed,
  because the inner ``list[Any]`` indexing yields ``Any`` which
  pyright then flags as "partially unknown" downstream.  Global
  pyright drops from 531 → 522 warnings (-9).  Per-file warnings
  in ``value_change_capture.py``: 22 → 13.  16 lineage-value tests
  green; ruff + pydoclint clean.

- **Sprint 35.5 closed (2026-05-06)** — Architectural cleanup: hoist
  every lazy ``import deltalake`` from function bodies to module
  top in ``pql/_merge.py`` (3 lazy imports), ``pql/_autoload.py``
  (2 lazy imports), ``pql/engine.py`` (7 lazy imports), and
  ``pql/_cdf.py`` (1 lazy + the ``try / except ImportError`` guard
  was dead code since deltalake is a hard dep).  **Plan estimated
  ≥40 fewer pyright warnings; actual is 0** — ``deltalake``'s
  signatures already had type hints, and pyright's "Type is
  partially unknown" warnings come from pyarrow's
  ``pa.dataset.Dataset`` stubs being incomplete, not from the
  imports being lazy.  The hoist remains valuable as code-quality
  cleanup (Python-level architecture, fewer per-call imports) even
  without the warning reduction.  Lesson recorded in
  ``feedback_pyright_pyarrow_stubs.md``: third-party-API-heavy
  modules need either custom ``.pyi`` stubs or accepted warnings;
  Python type annotations alone don't move the needle.  Verification:
  1478 SQLite tests green, ruff + pyright + pydoclint clean (0
  errors / 531 warnings, unchanged).

- **Sprint 35.4 deferred (2026-05-06)** — Extracting
  ``run_view.html`` (1467 LOC) into tab partials needs a live
  browser-playbook replay (``audit-reviewer-daily.md``) before
  commit per the Phase-35 plan's mandatory verification gate.
  Alpine ``x-data`` scope changes can pass server-side tests but
  break the side-panel factory in the browser (memory rule:
  ``feedback_run_playbook_as_gate.md``).  Re-pick when a
  Playwright MCP session is up alongside the refactor.  Stream-B
  / 35.8 do not depend on this — proceeding without 35.4.

- **Sprint 35.3 closed (2026-05-06)** — Targeted modularization: split
  ``pointlessql/services/audit_fts.py`` (973 LOC) per dialect into a
  ``pointlessql/services/audit_fts/`` package.  ``__init__.py`` keeps
  the public surface (``is_available`` / ``search`` /
  ``install_index`` / ``rebuild_index``), the dialect dispatcher,
  the query sanitiser, the time-filter post-processor, and the
  ``Axis`` / ``VALID_AXES`` typing.  ``_sqlite.py`` (~330 LOC) owns
  the FTS5 virtual-table DDL, the per-source trigger generation
  (5 ``CREATE TRIGGER`` axes × 3 events each), the ``MATCH``-based
  search, and the rebuild path.  ``_postgres.py`` (~330 LOC) owns
  the ``audit_search_index`` table layout, the per-axis PL/pgSQL
  upsert + delete trigger functions, the ``ts_rank`` /
  ``plainto_tsquery`` search with ``ts_headline`` snippets, and the
  same rebuild path.  Cross-dialect parity helpers
  (``_merge_pg_marks`` for snippet-mark normalization) live with
  the PG layer.  ``services/audit_fts.py`` was deleted (replaced by
  the package); all three importing call sites
  (``audit_search_routes``, ``cli/migrate_to_postgres``, two test
  files) keep their ``from pointlessql.services import audit_fts``
  pattern unchanged because the package's ``__init__.py`` exposes
  the same name.  Behaviour byte-identical — refactor only.
  Verification: 25 audit-fts tests green
  (``test_audit_fts`` + ``test_agent_runs_workspace_isolation``);
  1478 SQLite suite tests pass; pyright errors stay 0, warnings
  unchanged at 531; ruff + pydoclint clean.

- **Sprint 35.2 closed (2026-05-06)** — Targeted modularization: split
  ``pointlessql/services/lineage_edges.py`` (1137 LOC) into a
  per-stream ``pointlessql/services/lineage/`` subpackage.
  ``_types.py`` keeps the shared dataclasses (``PredecessorRef``,
  ``LineageStep``, ``ColumnEdgeSpec``, ``ColumnPredecessorRef``,
  ``ColumnTraceStep``, ``ValueChangeSpec``), exception sentinels
  (``ColumnEdgeCapExceeded``, ``ValueChangeCapExceeded``), per-op
  caps (``MAX_COLUMN_EDGES_PER_OP``, ``MAX_VALUE_CHANGES_PER_OP``),
  the deterministic-id helpers (``synth_target_row_id``,
  ``synth_aggregate_target_row_id``), and the workspace-id resolver
  (``workspace_id_for_op``, dropped leading ``_`` since cross-module).
  ``rows.py`` owns ``record_edges`` / ``record_rejects`` /
  ``walk_back`` / ``fetch_target_row_predecessors`` /
  ``fetch_source_row_descendants`` / ``count_edges_for_op`` and the
  bronze ``lookup_bronze_source_file`` helper used by the row-trace
  UI.  ``columns.py`` owns the column-level analogs
  (``record_column_edges`` / ``walk_back_columns`` /
  ``fetch_target_column_predecessors`` /
  ``count_column_edges_for_op``).  ``values.py`` owns
  ``record_value_changes`` (with the ``hash_only`` /
  ``redact_with_audit_log`` PII hook), ``count_value_changes_for_op``,
  ``fetch_value_changes_for_row``.  ``lineage_edges.py`` becomes a
  60-LOC re-export shim that keeps every old import path working
  (12 import sites across PQL primitives, lineage routes, agent-run
  operations, run-detail loaders, value-change-capture, sql parser,
  column-lineage diff, plus 4 test files).  Behaviour byte-identical;
  58 lineage tests + full 1478 SQLite suite green.  Pyright errors
  stay 0, warnings unchanged at 531; ruff + pydoclint clean.  No-net-LOC:
  ~1137 LOC moved across 5 files.

- **Sprint 35.1 closed (2026-05-06)** — Targeted modularization: split
  ``pointlessql/pql/_branch.py`` (1310 LOC) into a per-workflow
  ``pointlessql/pql/branch/`` subpackage.  ``_common.py`` keeps the
  soyuz-API references + shared helpers (URI classification, schema
  lookup, audit-log + CloudEvent emission); ``_create.py`` owns the
  create flow + table-cloning helpers; ``_discard.py`` owns the
  discard flow + storage cleanup; ``_promote.py`` owns the
  pointer-swap promote + dry-run preview + version-equality conflict
  gate.  ``_branch.py`` is now a thin re-export shim
  (``# pyright: reportPrivateUsage=false`` to silence intentional
  private-symbol exposure for tests).  Cross-module helpers in
  ``_common.py`` dropped their leading underscore
  (``classify_storage_scheme``, ``uri_to_local_path``,
  ``derive_branch_storage_root``, ``split_two_part``,
  ``ensure_source_schema``, ``resolve_storage_root``,
  ``emit_branch_event``, ``record_branch_audit_log``,
  ``rename_schema``); module-internal helpers
  (``_clone_table_local``, ``_pick_strategy``,
  ``_check_promotion_conflicts``, ``_delete_branch_storage``, etc.)
  keep theirs.  Test imports updated: ``from pointlessql.pql import
  _branch as branch_mod`` → ``from pointlessql.pql.branch import
  _create as branch_mod`` (and similar for discard / promote);
  ``patch.object(branch_mod, "_emit_branch_event")`` →
  ``patch.object(branch_mod, "emit_branch_event")``, etc.  Behaviour
  is byte-identical — refactor only.  All 81 branch tests still
  green; 1478 SQLite suite tests pass; pyright errors stay 0,
  warnings unchanged at 531.  No-net-LOC: ~1310 LOC moved across 5
  files (shim + 4 workflow modules).

- **Sprint 34.2 closed (2026-05-05)** — Governance + Compliance panel
  set; closes Phase 34 with 8 new panels (4 from 34.1 + 4 from 34.2,
  matched IDs across SQLite + Postgres dashboards).  Picks for the
  governance row, all dialect-aware:
  (1) **Audit retention horizon (oldest row, days)** — stat over
  ``MIN(audit_log.created_at)`` rendered as days; thresholds at
  300 (yellow) and 365 (red, the default
  ``POINTLESSQL_AUDIT_RETENTION_DAYS``).  SQLite uses
  ``julianday('now') - julianday(MIN(...))``; PG uses
  ``EXTRACT(epoch FROM NOW() - MIN(...)) / 86400.0``.  Filtered by
  ``$workspace``.
  (2) **FTS index lag (rows behind)** — stat showing
  ``COUNT(audit_log) - COUNT(audit_search[_index])``; 0 = triggers
  in sync, anything else means the FTS-trigger stalled.  Cross-
  workspace by design (FTS is install-global).  SQLite reads
  ``audit_search`` (FTS5 virtual); PG reads ``audit_search_index``
  (Phase 30 ``hh8j0l2n4p6r``).
  (3) **Audit exports issued (selected window)** — stat counting
  ``governance_events`` rows with ``event_type='pointlessql.
  audit_export.issued'`` in the dashboard's time window, blue
  threshold (informational, not alertable).  Filtered by
  ``$workspace``.
  (4) **Agent reviews per day (by severity)** — full-width stacked
  vertical bar of ``agent_reviews.created_at`` grouped by
  ``severity`` (ok / warn / critical).  Filtered by ``$workspace``.
  Plus a section header (id=16) labelling the row "Phase 19/20
  Governance + compliance".  Originally the plan included an OIDC-
  login-volume panel; the audit verified that login events are NOT
  written to ``audit_log`` (no instrumented login path), so the
  slot was redirected to the audit-export trail panel — a
  comparable compliance signal that DOES have data behind it.  Net
  result: dashboards now have 20 panels each (10 baseline + 5
  Sprint-34.1 + 5 Sprint-34.2).  Panel-ID space distinct, structural
  gate (``scripts/check-grafana-dashboards.sh``) green.  Phase 34
  closes.
- **Sprint 34.1 closed (2026-05-05)** — Cross-Workspace Observability
  MVP: 4 new operator-pain panels added to both Grafana dashboards
  (SQLite at ``grafana/dashboards/pointlessql_audit.json`` +
  Postgres at ``grafana/postgres-dashboards/pointlessql_audit.json``,
  matched IDs).  Each filters by the existing ``$workspace`` template
  variable.  Panel set, queries against the metadata DB directly:
  (1) **Sink delivery health (last 1h)** — stat showing
  ``governance_events`` ``outcome='delivered'`` ratio over the
  last hour, threshold-coloured (red <95%, yellow 95-99%, green
  ≥99%); (2) **Open anomaly verdicts (7d)** — stat counting
  ``agent_runs`` rows whose cached ``anomaly_severity`` is
  ``warn`` or ``critical`` in the trailing 7 days, threshold-
  coloured (green=0, yellow≥1, red≥10); (3) **Rollbacks per
  day** — vertical bar of ``agent_run_events.event_type =
  'pointlessql.rollback.executed'`` count per day; (4) **Sink
  errors per day (by event type)** — stacked vertical bar of
  ``governance_events.outcome='delivery_failed'`` per day,
  broken out by ``event_type``.  A markdown header panel
  separates these from the Phase-19 baseline.  Per-dialect
  queries: SQLite uses ``datetime('now', '-N hours')`` /
  ``date(fired_at)``; Postgres uses ``NOW() - INTERVAL 'N hour'``
  / ``::float8`` casts.  New gate ``scripts/check-grafana-
  dashboards.sh`` parses both JSONs, requires non-empty panels
  array, asserts each panel has ``id`` + ``type`` + ``title`` +
  ``gridPos`` plus distinct IDs.  Local result: both dashboards
  parse, 15 panels each (10 baseline + 5 new), distinct IDs.
- **Sprint 33.4 closed (2026-05-05)** — Admin Console polish.  Closes
  the two remaining gaps that Phase 33's first cut deferred as
  "curl-only stays acceptable" / "out of scope":
  ``GET /admin/api-keys`` (list + create-with-modal +
  revoke-with-confirm), ``GET /admin/system-info`` (read-only:
  PII mode + active hash-secret presence, OIDC group→workspace+
  scope mapping with restart-required hint, ``system_keys`` row
  inventory by name + ``created_at`` only, API-key scope counts).
  Two new cards on ``/admin`` ("API keys", "System info") with the
  active-key-count badge.  ``POST /api/admin/api-keys`` JSON
  route now also accepts an optional ``workspace_id`` field
  (defaults to ``1``) so the UI's workspace chooser is honoured;
  the audit-log entry carries the chosen workspace.  Two
  load-bearing assertions in the new test files prove the page
  never re-leaks a secret: the hashed
  ``ApiKey.secret_hash`` value (64-char SHA-256 hex) and the
  ``system_keys.value`` cleartext both must be absent from the
  rendered HTML — only the literal ``present`` badge + the
  ``created_at`` date surface.  9 new pytest cases across two new
  test files (``test_admin_api_keys_page.py``,
  ``test_admin_system_info_page.py``); the existing 6
  ``test_admin_api_keys_routes.py`` JSON tests stay unchanged and
  green.  **Still out of scope** (with rationale): system-keys
  rotation (sec-critical write needs re-hash backfill, dedicated
  phase), editable PII-mode / OIDC-mapping forms (both
  env-restart-gated; a writable UI would silently desync from
  ``os.environ``).  Net effect: Phase 33 now closes with all four
  sub-sprints landed; admin-test count goes from 38 → 50 in this
  session.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 33 closed (2026-05-05)** — Admin Console: every operator
  surface unified behind one ``/admin`` landing.  Three sub-sprints
  + a Mini-Sprint 0 cleanup.  Mini-Sprint 0 retired two stale
  ROADMAP markers (Sprint 19.2 ``⏳ in progress`` → ``✅ closed
  (995490b)``; Phase 12.9 ``🔜 in progress`` → ``✅ closed
  2026-05-05 (Sprint 76–95: 90d40b8)`` with a closing note that
  documents why ``help_popovers.js`` deliberately stays IIFE and
  why ``bootstrap.js`` is a permanent fixture).  33.1 introduces
  ``GET /admin`` with a five-card grid (audit log, external
  writes, workspaces, audit sinks, review destinations) and
  retargets the icon-rail's admin pill from ``/admin/audit`` to
  ``/admin``; the three existing admin pages now back-link via
  ``Admin → /admin`` in the breadcrumb so the landing becomes the
  canonical hub.  33.2 ships ``GET /admin/audit-sinks``: list of
  every sink with its redacted config, type-conditional create
  form (webhook / s3 / aws_cloudtrail), per-row active toggle,
  test-envelope button (``/api/admin/audit-sinks/{id}/test``),
  delete button, and workspace-filter chip selector — the
  underlying JSON CRUD has been live since Phase 19.1 / 29.2; only
  the chrome was missing.  33.3 ships
  ``GET /admin/review-destinations`` with the same shape: list of
  destinations with min-severity dropdown, HMAC-secret presence
  badge (cleartext **never** reaches the page), workspace-filter
  chips, active toggle, delete button, and inline create form.
  Twelve new pytest cases across three new test files
  (``test_admin_index.py``, ``test_admin_audit_sinks_page.py``,
  ``test_admin_review_destinations_page.py``) verify auth gates,
  HTML rendering, and secret-redaction; the existing JSON-route
  tests stay unchanged and green.  **Out of scope for Phase 33**:
  System-keys rotation UI (security-sensitive write needs
  dedicated phase), PII-mode / OIDC-group-mapping editing
  (env-restart-gated; UI would lie), API-keys HTML wrapper
  (curl-only stays acceptable), Playwright smoke (route-level
  pytest sufficient for chrome).  Net effect: full SQLite suite
  ``1467 passed, 6 skipped`` (+ 12 over Phase 32's 1455), no
  regressions in any of the 33 admin / audit-sinks / review-dest
  tests.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 32 closed (2026-05-05)** — PG test quality cleanup, no
  quality loss.  Once Phase 31 made the PG suite runnable
  end-to-end (~7 minutes), it surfaced **45 pre-existing PG
  failures**.  Phase 32 closes them all in one autonomous run:
  PG suite goes from **45 failed → 0 failed** (1457 / 1457 pass,
  4 skip, 9 deselect).  Three sub-sprints: 32.0 inserts
  ``session.flush()`` between parent ``add()`` and child ``add()``
  in 11 fixtures across 10 test files — the SQLAlchemy unit-of-work
  topo-sort doesn't reliably order cross-class inserts on PG when
  no ``relationship()`` is declared (production is unaffected, it
  commits parent and child in separate transactions); the same
  pass also widens ``query_history.read_kind`` from ``VARCHAR(20)``
  to ``VARCHAR(32)`` (alembic ``ii9k1m3o5q7s``, batch-mode on
  SQLite for table-recreate + drift-clean, plain ALTER on PG)
  because Sprint 28.7's ``audit_api_cross_workspace`` (25 chars)
  was silently truncating on PG, and rewrites
  ``test_fts_vtable_carries_workspace_id_column`` to be
  dialect-aware (PG inspects the ``audit_search_index`` table from
  Sprint 30.1's FTS migration; SQLite still uses ``PRAGMA
  table_info(audit_search)``).  32.1 makes the
  ``saved_audit_queries`` migration ``j0e1f2a3b4c5`` dialect-aware:
  the four ``datetime('now', '-N days')`` SQLite-only fragments in
  ``STARTER_ROWS`` become ``NOW() - INTERVAL 'N days'`` on PG via
  a ``starter_rows(dialect_name)`` helper, and ``services/saved_audit_queries.py``'s
  ``bootstrap_starter_rows`` plumbs the session's dialect through.
  A new alembic migration ``jj0l2n4p6r8u`` repairs already-deployed
  PG installs in place via ``UPDATE saved_audit_queries SET
  sql_text = REPLACE(...)`` (no-op on SQLite).  32.2 verifies the
  killer gate (``1457 passed`` on PG, ``1455 passed`` on SQLite,
  ``alembic check`` clean, ``pyright`` clean on touched files) and
  closes the phase with this entry plus the ROADMAP and memory
  updates.  Production was untouched in 32.0 (test fixtures only),
  fixed correctly in 32.1 (real seed-SQL bug), and the ``read_kind``
  widening removes a real PG-only truncation that was silently
  failing on every cross-workspace audit-summary read.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 31 closed (2026-05-05)** — Test-suite speed
  optimisation, no quality loss.  The full SQLite suite went from
  ~30 minutes to **~68 seconds** (≈27×), and the PG suite from
  the aborted ~3 hour single-worker run down to roughly 7
  minutes.  All 1455 tests still run; no test was dropped or
  marked slow.  Six sub-sprints: 31.0 ships the baseline bench
  script (``scripts/bench_test_suite.sh`` → ``.bench/<ts>-<backend>.txt``);
  31.1 monkey-patches ``pointlessql.services.auth._hasher`` to
  ``BcryptHasher(rounds=4)`` at conftest-import time, dropping
  per-test bcrypt cost from ~1.0 s to ~64 ms (algorithm + cookie
  format unchanged, production untouched); 31.2 splits the
  conftest's autouse fixture into a session-scope ``_test_engine``
  (one ``Base.metadata.create_all`` per worker, dropped on session
  exit) plus a function-scope ``_auth_db`` that does a per-test
  ``TRUNCATE TABLE … RESTART IDENTITY CASCADE`` on PG and a
  reverse-FK ``DELETE FROM …`` cascade on SQLite, then re-seeds
  the workspace + admin/non-admin users from a hash cached at
  module import — eliminating ~90 DDL statements per test (the
  single biggest cost on PG); 31.3 adds a
  ``POINTLESSQL_TEST_LIFESPAN_FAST=1`` env var that
  ``pointlessql.api.main._lifespan`` honours by short-circuiting
  the alembic-upgrade-on-default-URL ``init_db`` and the audit /
  lineage / external-writes / branch-cleanup background asyncio
  tasks (production startup is untouched — the env var is only set
  inside the test process).  31.4 flips ``-n auto`` on for the
  SQLite CI lane via ``.github/workflows/test.yml`` and ships
  [`docs/development/test-suite.md`](docs/development/test-suite.md)
  documenting the bench script, the env var, and the safe-edit
  rules; PG xdist is deferred (workers can't share a live PG
  database without per-worker DB provisioning).  31.5 closes the
  phase with the CHANGELOG / ROADMAP / memory entry.  ``ruff``,
  ``ruff format --check``, ``pyright``, and ``mkdocs build
  --strict`` all clean on Phase-31-touched files (the four
  pre-existing pyright errors in ``conftest.py`` and the lint
  errors elsewhere in the repo are unchanged).

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 30 closed (2026-05-05)** — Postgres production-readiness
  for the audit lake.  Six sub-sprints close the cliffs that
  stood between "swap a URL and pray" and "production default".
  30.0 adds a CI Postgres lane in ``.github/workflows/test.yml``
  spinning up ``postgres:17-alpine``, teaches ``alembic env.py``
  to honour ``POINTLESSQL_DB_URL`` for shell-driven runs, and
  fixes three pre-existing dialect bugs that broke
  ``alembic upgrade head`` against fresh PG (literal
  ``DEFAULT 0``/``1`` boolean defaults in 28.1a / 29.3 / 13.11
  / 18 migrations, plus the Phase-18.7 ``audit_search``
  migration's time-travel import of the workspace-aware
  ``audit_fts`` module — the migration now inlines a snapshot of
  the original SQL).  30.1 ships the PG-side full-text search
  (alembic ``hh8j0l2n4p6r``: ``audit_search_index`` table with a
  generated ``tsvector`` + GIN index, five PL/pgSQL trigger
  sets) so ``/api/audit/search`` returns ``available=true`` on PG
  with the same ``(snippet, rank)`` envelope; ``audit_fts.py``
  becomes a dialect router behind unchanged public surface.  30.2
  swaps Grafana onto the built-in PostgreSQL datasource via a new
  ``docker-compose.grafana.postgres.yml`` overlay + a
  dialect-clean dashboard JSON in ``grafana/postgres-dashboards/``
  (Panel 5's reject-rate baseline rewritten with PG
  ``INTERVAL '7 days'`` arithmetic).  30.3 ships the
  ``pointlessql migrate-to-postgres`` CLI: refuses non-empty
  targets, runs alembic upgrade head, bulk-copies tables in a
  hard-coded FK-respecting order, syncs PG sequences past the
  largest copied id, rebuilds the FTS index, and verifies row
  counts plus a 1%-sample-hash for tables ≥100 rows.  30.4 adds
  four pool / timeout knobs to ``DatabaseSettings`` (``pool_size``,
  ``max_overflow``, ``pool_recycle_seconds``, ``statement_timeout_ms``)
  + a per-connection ``SET statement_timeout`` event listener +
  the ``docs/admin/postgres-deployment.md`` ops playbook
  (autovacuum hints for ``lineage_row_edges`` /
  ``agent_run_tool_calls`` / ``lineage_value_changes``, backup
  via ``pg_dump --format=custom``, monitoring signals).  30.5
  ships ``scripts/seed_audit_lake.py`` (deterministic synthetic
  load at 10 k / 100 k / 1 M scales, runs against either
  backend) + the ``docs/admin/performance.md`` baseline
  template.  Phase 19.0.1's deferral is closed — Postgres is
  now a first-class deployment target; SQLite stays the laptop
  default per the Decision-C dual-track pick.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 29 closed (2026-05-05)** — workspace polish pass.  Five
  sub-sprints fix the cross-cutting tenancy gaps left after Phase
  28 shipped soft isolation: 29.1 routes audit-sinks per workspace
  via a new ``workspace_filter`` JSON column on ``audit_sinks``;
  29.2 mirrors the same shape on ``review_destinations`` plus adds
  ``agent_reviews.workspace_id`` so reviews carry the routing key;
  29.3 wires OIDC group → workspace + scope mapping via the new
  ``POINTLESSQL_OIDC_GROUP_MAP_RAW`` env var (parser fails loud on
  malformed input; ``users.is_supervisor`` / ``is_auditor`` /
  ``oidc_groups_json`` columns let session-cookie callers hold the
  scopes API keys already could); 29.4 adds a ``$workspace``
  template variable to the Grafana audit dashboard with the
  ``(0 IN ($workspace) OR <table>.workspace_id IN ($workspace))``
  predicate pattern so "All" stays the default.  Three alembic
  migrations (``ee5g7i9k1m3o``, ``ff6h8j0l2n4p``, ``gg7i9k1m3o5q``);
  ``system_keys`` deliberately stays install-global so PII anomaly
  aggregation still aligns across tenants.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 23 closed (2026-05-05)** — contextual help-popovers
  rolled out across the entire UI.  ~40 new slugs land across
  catalog tree + table-detail (23.1), models index + detail
  (23.2), audit cockpit + branches + home (23.3), SQL editor +
  admin (23.4), plus a doc-link sweep + registry/template
  cross-check (23.5).  Phase 23 closes with ~50 popovers
  total, every "Learn more →" pointing at a real mkdocs page.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 28 closed (2026-05-05)** — soft workspace isolation in
  the Databricks Unity-Catalog mental model: catalogs stay global,
  workspaces own audit/jobs/saved-queries/recents.  9 sub-sprints
  landed in one autonomous run (28.0 through 28.8).  Single-tenant
  installs see zero behaviour change — the topbar switcher hides
  itself when ≤1 workspace exists.  ADR at
  ``docs/decisions/0008-workspace-soft-isolation.md``; concept doc
  at ``docs/concepts/workspaces.md``; admin runbook at
  ``docs/admin/workspace-management.md``.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 24 — every rail icon now opens a useful context-panel.**
  Six previously-static or fall-through panels became navigable
  surfaces, mirroring the catalog tree's role for Federation:
  - **Runs** — recent agent runs grouped into Needs approval /
    Running / Recent buckets, 8-char short-IDs + status badges +
    relative timestamps.  Source: ``GET /api/runs?limit=15``.
  - **Branches** — Delta-branches grouped Active / Promoted /
    Discarded with strategy + timing tags.  Source:
    ``GET /api/branches`` (supervisor-gated; rail item is admin-
    only).
  - **Workspace** — flat alphabetical list of every ``.py`` /
    ``.ipynb`` notebook the scheduler can pick up; format badge
    per row.  Source: ``GET /api/notebooks/tree`` (admin-only).
  - **Jobs** — split into Active (with last-run-status badge) and
    Paused.  Source: ``GET /api/jobs``.
  - **Alerts** — split into Enabled (green bell) and Disabled
    (muted).  Source: ``GET /api/alerts``.
  - **MLflow** — recent UC-registered models with latest-version
    + status badge; "Open MLflow UI →" link to ``/ml``.  Source:
    ``GET /api/models?enrich_latest=true&limit=10``.

  Each panel is a small Alpine factory at
  ``frontend/js/components/sidebars/<section>_sidebar.js``
  imported through ``bootstrap.js``, paired with a partial at
  ``frontend/templates/components/sidebars/<section>_sidebar.html``
  included from ``components/context_panel.html``.  Pattern
  mirrors :func:`catalogTree` exactly (sessionStorage instant-
  paint, async refetch with refresh button, ``htmx:after-swap``
  re-binds active-row highlight from the URL).  Shared row
  styles live in
  ``frontend/css/components/context_sidebars.css``.

  Each panel header carries a Phase-23 contextual help-icon
  (slugs ``runs.context-panel`` / ``branches.context-panel`` /
  …) explaining what the panel shows and linking to the matching
  mkdocs concept page.  ``docs/e2e-walkthroughs/contextual-
  panels.md`` records the replayable verification sequence; it
  is wired into ``mkdocs.yml`` under "Getting around".
