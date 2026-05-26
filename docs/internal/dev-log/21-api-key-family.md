---
title: "Cluster 21 — Phase 118–121 API-Key family + Restschuld V tail (dev-log)"
audience: contributor
cluster_id: "21"
phases: "118-121"
closed: "2026-05-24"
---

# Cluster 21 — Phase 118–121 API-Key family + Restschuld V tail (dev-log)

> Phase 118 (token format pql_{env}_v1_{body40}_{crc8} + admin surface), Phase 119 (API-key lifecycle: TTL + rotation + soft-quarantine), Phase 120 (API-key ACLs + usage dashboard: 3 CASCADE tables + 6 admin endpoints), Phase 121 (Restschuld V: 9 sub-sprints — error-envelope unification, pagination service-layer rollout, soyuz facade completion, pydoclint tightening, settings cache, micro-extractions, PII redaction in audit details).

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Fixed**)

- **Phase 121.9a — Close 7 pre-existing test failures (2026-05-24,
  rc136 → rc137).**  Drains the residual failures carried as "out
  of scope" since Phase 117/121 waves.  Root causes split between
  prod (3) and test maintenance (4):

  - **Model:**  ``ck_agent_run_operations_op_name`` CHECK extended
    with ``'pin_fact'`` — Phase 97 alembic migration added it but
    the SQLAlchemy model lagged, breaking the in-memory
    ``Base.metadata.create_all()`` test path.
  - **Prod:** ``services/scheduler/runs/_telemetry.py`` switches
    ``_webhook_client_factory()`` to a call-time package lookup
    so ``monkeypatch.setattr(scheduler_service.runs, ...)``
    reaches the call site (same pattern as ``_sleep`` /
    ``_build_pql`` after Phase 110/111 module splits).
  - **Prod:** 6 broad-except sites get either
    ``# bare-broad-ok:`` markers (5: ``notebook_coedit_ws/`` x4
    + ``sql_statements/_executor``) or upgrade to
    ``logger.exception`` (1: ``notebook_coedit_ws/_seed`` was
    bucket-C lossy).
  - **Test:**  ``test_api_notebook_save`` renamed +
    counterpart-added to reflect Phase 99 Wave-D's
    ``_enforce_notebook_role(required="edit")`` gate; the old
    "any authenticated user can save" contract was tightened.
  - **Test:**  ``ENTITY_KINDS`` expected set extended with
    Phase-97 ``notebook_revision`` + ``notebook_cell_output``.
  - **Test:**  CSRF redirect assertion relaxed to ``startswith``
    (the redirect now carries ``?flash=account_created``).
  - **Test:**  ``test_phase158`` patches
    ``pointlessql.pql._merge._resolve._get_table`` instead of
    the ``_merge`` package re-export so the local binding the
    resolver actually uses gets stubbed.

  Full pytest after the wave: 3529 passed, 9 skipped, 0 failed.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 121.8b — Pagination service-layer rollout (2026-05-24,
  rc135 → rc136).**  Closes the nine sites Phase 121.7b deferred
  because their service-helper signatures only accepted ``limit=``.
  Six service helpers (``list_replays`` / ``list_revisions`` /
  ``list_facts`` / ``list_bindings`` / ``list_authored_by_agent`` /
  ``recall_operations``) gain an optional ``offset: int = 0``
  parameter with ``max(0, int(offset))`` chained before
  ``.limit()``.  The six corresponding routes (replay / revisions /
  facts / branch-history / authored-cells / recall) flip from
  ``Query(default=…)`` to
  ``paging: PaginationParams = Depends(pagination)`` and forward
  ``paging.limit`` + ``paging.offset`` through.  The three
  inline-SQL routes (``api_list_agent_runs`` /
  ``api_list_agent_run_operations`` / ``api_dbt_test_failures``)
  gain ``.offset(paging.offset)`` chained before
  ``.limit(paging.limit)``.  Defaults preserve current behaviour
  for in-tree ``pql`` facade callers
  (``list_facts_for_notebook`` / ``recall``) that don't pass
  ``offset=``.  Default page size shifts 50/100 → 100, upper
  bound le=200/500 → le=1000 — same precedent as 121.7b.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 121.4 — require_role factory + PrivilegeSettings scaffold
  (2026-05-24, rc133 → rc134).**  Adds two pieces of privilege-
  subsystem groundwork that the existing seven hand-rolled
  ``require_*`` gates left missing.  (a) ``require_role(*roles)``
  factory dep in ``api/dependencies.py`` generalises the single-
  role gates into one parametrised form (admin / supervisor /
  auditor / analyst / user; admin strictly stronger; OR semantics
  across the role set).  Routes that need "admin OR auditor"
  declare ``Depends(require_role("admin", "auditor"))`` instead
  of hand-rolling an OR gate.  Token-only gates (sql_execute,
  lineage_inbound) keep their dedicated dep.  (b)
  ``PrivilegeSettings`` sub-model in
  ``config/_settings/_privileges.py`` with single field
  ``enforce_global_privilege_gate: bool = False`` reserves the
  env name + documents intent for the future
  ``require_privilege(privilege, securable_type)`` dep that will
  consult ``services/authorization.check_privilege`` at request
  time.  17 new pytest.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 121.7c — PII redaction in audit log details
  (2026-05-24, rc132 → rc133).**  Extends the existing
  services/pii infrastructure (value-change rows only) to also
  redact PII-keyed values in ``audit_log.detail`` dicts.  New
  ``services/pii/_audit_redactor.redact_audit_detail()`` walks
  the detail dict recursively and scrubs values under keys
  matching the existing ``PII_NAME_PATTERN`` regex via either
  ``REDACTED_PLACEHOLDER`` literal or HMAC-SHA256 digest.
  ``log_action`` pipes detail through the redactor when the new
  ``audit.redact_detail_payloads=True`` setting is flipped
  (default False for backward-compat; reuses ``audit.pii_mode``
  for the redaction shape).  13 new pytest.

> from CHANGELOG.md (bucket: **Removed**)

- **Phase 121.9b — Working-tree hygiene (2026-05-24, rc137 →
  rc138).**  Two weeks of ephemeral debug artefacts purged:
  ``phase113-replay/`` (43 PNGs + REPLAY_REPORT.md) and
  ``phase120-replay/`` (6 PNGs) deleted — the canonical playbooks
  live in ``docs/e2e-walkthroughs/``, not in per-session
  screenshot dumps.  Scratch notebooks ``mcp_demo.py`` +
  ``phase95_walkthrough.py`` removed; jupytext-save drift on
  ``agent_drift_monitor.py`` (stripped ``pql_cell_id`` metadata)
  + ``phase96_walkthrough.py`` (stray marker comment) reverted.
  ``.gitignore`` extended with ``phase*-replay/`` so future
  replay sessions don't slip past the existing ``/*.png`` rule
  (which only catches repo-root PNGs).  Three Phase-113 deferred
  UX nits archived to project memory before the report was
  deleted.

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 121.8a — Tests lint baseline (2026-05-24, rc134 →
  rc135).**  ``tests/**`` per-file-ignore extended with
  ``TID251`` — the Phase 121.3 banned-api rule that blocks direct
  generated-client imports is API-layer-only; tests legitimately
  bypass the facade for setup/teardown (creating and dropping
  catalog/schema/table fixtures the facade intentionally hides)
  and for error injection (monkey-patching the generated-client
  transport).  Auto-fixed three I001 import-order drifts and one
  F401 unused import.  Added ``# noqa: DOC502`` to
  ``api/dependencies.admin_uc`` — its two-line body delegates to
  ``require_admin`` for the raise, so pydoclint sees no ``raise``
  in the body, but the ``Raises:`` block accurately documents
  the propagated exception for callers.  Net effect:
  ``ruff check tests/ pointlessql/`` and
  ``pydoclint pointlessql/api/dependencies.py`` both report zero
  violations.

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 121.7b — Pagination dep rollout (2026-05-24, rc131 →
  rc132).**  Six list-endpoint routes migrated from ad-hoc
  ``offset = Query(...)``/``limit = Query(...)`` declarations to
  ``Depends(pagination)`` (introduced in Phase 121.2): three
  offset+limit-pair JSON endpoints (notifications, audit/search,
  data-products activity) plus three direct-SQLAlchemy
  limit-only endpoints where ``.offset(paging.offset)`` chains
  cleanly (social issues x2, workspace activity — adds offset
  support additively).  Nine other ad-hoc-pagination sites stay
  un-migrated: they delegate ``limit=`` to service helpers that
  do not accept ``offset``, so the migration would need service-
  signature changes (out of scope per the 121.7 plan).

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 121.7a — admin_uc final cleanup (2026-05-24, rc130 →
  rc131).**  ``volumes_routes.api_convert_volume_file_to_delta``
  — the last ``require_admin(request); client = get_uc_client
  (request)`` couplet outside ``federation_routes`` — migrated
  to ``Depends(admin_uc)``.  Fully enforces the Phase 121.6
  convention that admin-only UC routes use one combined dep.

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 121.6 — Four micro-extractions (2026-05-24, rc129 → rc130).**
  (i) ``social_routes._kind_dispatch.parse_ref()``: 125-LOC 13-way
  if/elif chain → ``RefKind`` frozen-dataclass registry in new
  ``social_routes/_ref_kinds.py`` mirroring the existing
  ``CitationKind`` pattern; dispatcher shrinks to a registry lookup
  + uniform ``BadRequestError``.  (ii) ``admin_uc()``: combined
  ``require_admin`` + ``get_uc_client`` FastAPI dep collapses the
  2-line setup across 22 federation routes into one
  ``Depends(admin_uc)`` injection.  (iii) ``_DataOpsMixin``
  per-concern split: ``pql/_pql_data.py`` shrunk from 678 LOC to a
  38-LOC composite over 9 new per-concern mixins (read/write/sql/
  vector/update_delete/aggregate/autoload/list/widgets); public PQL
  surface + import path + MRO identical.  (iv)
  ``render_page_with_fallback()``: 6 identical try/except
  ``CatalogUnavailableError`` + render-with-banner blocks in
  ``federation_routes.py`` collapse into one helper on
  ``api/dependencies.py``.  24 new pytest.

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 121.3 — Soyuz facade completion (2026-05-24, rc128 → rc129).**
  Ground-truth audit found 3 ostensible direct-client violations;
  two were legitimate sync helpers in ``services/``
  (``branch_tags.py``, ``soyuz_lineage.py``).  ``ml_routes.py``'s
  ``_fetch_linked_model_versions`` was the real API-layer violation;
  rewired through ``UnityCatalogClient.list_registered_models()`` +
  ``.list_model_versions()`` (now async, awaited from
  ``get_ml_context``).  New
  ``[tool.ruff.lint.flake8-tidy-imports.banned-api]`` rule blocks
  ``soyuz_catalog_client.api`` imports project-wide, with per-file
  ignores for the facade itself + the PQL sync layer + four
  legitimate sync-helper bypass sites.  4 new pytest.

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 121.5 — pydoclint tightening + D401 sweep (2026-05-24,
  rc127 → rc128).**  Re-scoped from "62% → 100% docstring sweep"
  after the audit showed the codebase was already 100% compliant.
  Attempted ``check-return-types = true`` + ``check-yield-types =
  true``; produced ~1400 DOC203/DOC404 false positives against the
  codebase's prose-style ``Returns: The X.`` sections.  Kept the
  pydoclint flags false with a documented note; instead added
  ``D401`` ("imperative mood") to the ruff D-rule select list — not
  in the google preset default but catches the "Cached X" /
  "Convenience wrapper" first-line anti-pattern.  15 violations
  surfaced + rewritten in the same sprint.

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 121.2 — Settings cache + pagination dep (2026-05-24,
  rc126 → rc127).**  ``get_settings()`` LRU-cached factory in
  ``pointlessql/config/__init__.py`` replaces 26 direct ``Settings()``
  call-sites across api/services/pql/cli/conventions/data_products.
  pydantic-settings was re-reading env vars on every construction;
  the cache makes 91 import sites pay-once.  Companion
  ``reset_settings_cache()`` + autouse fixture in
  ``tests/conftest.py`` keeps env-monkeypatching tests working.
  Shared ``PaginationParams`` dataclass + ``pagination()`` FastAPI
  dependency added in ``api/dependencies.py`` for future list
  routes (37 ad-hoc Query offset+limit declarations remain —
  best-effort migration deferred).  14 new pytest.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 120 — API-key ACLs + usage dashboard (2026-05-23,
  rc124 → rc125).**  Final wave of the three-phase API-key
  upgrade (118+119+120).  Adds the coarse-pre-filter layer below
  UC SELECT grants: per-key catalog/schema allowlist + per-key
  IP allowlist + 30-day usage dashboard.  Every existing key
  keeps unchanged behaviour (zero rows = unrestricted, same as
  pre-120 — admins opt in per key).  IP gate runs in
  ``auth_middleware`` immediately after the Bearer match;
  denials return 403 + ``IP_NOT_ALLOWED`` + a distinct
  ``api_key.access_denied.ip`` audit row.  Catalog gate runs in
  the public SQL Statement Execution API after parse + qualify;
  denials return the DBX-shape FAILED envelope with
  ``PERMISSION_DENIED`` + ``api_key.access_denied.catalog``
  audit.  Both gated on global ``api_key_acl.enforce_*`` config
  flags for incident-response escape hatches.  Five new admin
  endpoints: list/add/delete for both grant types.  Usage
  tracking via in-process ``collections.Counter`` flushed every
  30s into ``api_key_usage_buckets``; daily retention sweep
  prunes beyond 30d.  New per-key detail page
  ``/admin/api-keys/{name}`` with grants editor + 30-day bar
  chart (plain ``<canvas>`` — no Chart.js bundle for a 60-line
  histogram) + top-source-IPs table.  56 new pytest; new
  walkthrough at ``docs/admin/api-key-acls.md`` covering the
  enforcement model, all four CRUD endpoints, the usage
  dashboard, the layered model (IP → catalog → UC), audit
  catalogue, and known limitations.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 119 — API-key lifecycle: TTL + rotation + quarantine
  (2026-05-23, rc123 → rc124).**  Adds the three operational
  primitives that turn the Phase-118 token format into a
  credentials story you can run incident-response on.  Seven new
  ``api_keys`` columns (all NULL-able, default = "no constraint"
  so every existing key keeps unchanged behaviour): ``expires_at``,
  ``rotated_from_id`` (self-FK), ``rotated_at``, ``grace_until``,
  ``quarantined_at``, ``quarantine_reason``, ``expiry_warned_at``.
  ``verify_bearer`` now consults each gate in turn — quarantine,
  expiry, post-grace rotation — and emits a distinct
  ``api_key.auth_denied.*`` audit row per rejection so admins can
  debug "why is my key failing".  Four new admin endpoints:
  ``POST …/rotate`` (mints successor with same scopes + env;
  predecessor stays valid through configurable grace window
  default 24h), ``POST …/quarantine`` (soft-disable + required
  reason for audit context), ``POST …/unquarantine``, ``PATCH …``
  (update ``expires_at``).  New background sweep
  ``run_lifecycle_sweep`` runs hourly by default: auto-quarantines
  expired keys with reason ``"auto:expired"`` + emits one
  ``api_key.expiry_warning`` audit row per key entering the
  14-day-default warning window.  ``update_api_key_ttl`` clears
  the warning marker so a TTL bump re-arms naturally.  Admin UI
  gains status pills (revoked / quarantined / rotated / expiring
  / active), an action button-group (Rotate / Quarantine /
  Unquarantine / Revoke), and a TTL chooser in the create modal.
  19 new pytest; new walkthrough at
  ``docs/admin/api-key-lifecycle.md`` covering states, rotation
  playbook, quarantine-vs-revoke decision, TTL guidance, and the
  audit-event catalogue.

> from CHANGELOG.md (bucket: **Added**)

- **Phase 118 — API-key token format aufwertung (2026-05-23,
  rc122 → rc123).**  Replaces the opaque
  ``secrets.token_urlsafe(32)`` blob with a professional Stripe
  + GitHub PAT v2 style envelope:
  ``pql_{env}_v1_{body40}_{crc8}``.  Visible prefix discriminates
  ``live`` vs ``test`` keys at-a-glance (badged in the admin
  list), CRC32 suffix enables offline secret-scanner validation,
  and the GitHub-Secret-Scanning-Partner-Program regex is
  exported as a single-source-of-truth constant.  Backward
  compatible: legacy ``token_urlsafe`` keys keep working forever
  via a parse-v1-first-then-fall-through codepath; no forced
  rotation.  ``verify_bearer`` short-circuits v1-shaped tokens
  with a bad CRC before any DB lookup (typo / truncation /
  tamper → fast 401 with no DB cost).  ``create_api_key``
  accepts a new ``env: Literal["live", "test"]`` kwarg defaulting
  to ``"live"``; the admin POST body exposes it as ``env`` and
  rejects unknown values with 422.  New columns: ``token_format``
  ('legacy' | 'v1'), ``token_env`` ('legacy' | 'live' | 'test'),
  widened ``secret_prefix`` 8 → 32 chars.  18 new pytest; new
  walkthrough at ``docs/admin/api-key-format.md`` covering the
  format spec, the why-not-JWT rationale, the why-SHA-256
  rationale, and the GitHub Partner Program registration steps.
