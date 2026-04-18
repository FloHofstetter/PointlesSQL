# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added (Sprint 49) — SQL editor MVP

- **`POST /api/sql/execute` + `GET /sql` page.** First Phase 12 sprint.
  A dedicated ad-hoc SQL surface next to the Notebook tab: the user
  types ``SELECT … FROM catalog.schema.table`` in a CodeMirror-6
  editor, presses :kbd:`Cmd+Enter`, and sees the result table
  inline.  No history, no save, no export, no EXPLAIN, no cancel
  yet — those land in Sprints 50-53.
- **`PQL.sql()` + DuckDB-only engine for SQL.** Phase-5's
  ``POINTLESSQL_DELTA_ENGINE`` still drives :meth:`PQL.table` reads,
  but ad-hoc SQL is hard-wired to DuckDB (``duckdb`` was already a
  dep).  The new :meth:`pointlessql.pql.pql.PQL.sql` is a
  :func:`staticmethod` that opens a fresh DuckDB connection per
  request, registers every referenced Delta table as a view, runs
  the query, caps the result at ``POINTLESSQL_SQL_MAX_ROWS`` (default
  10 000), and returns a JSON-friendly ``SQLResult`` dataclass.
- **sqlglot-based 3-part-reference parser + rewriter.** New
  ``pointlessql/pql/sql_parser.py`` parses the user's SQL once with
  ``sqlglot.parse(dialect="duckdb")`` and returns a ``PreparedSQL``
  carrying (a) the distinct ``catalog.schema.table`` references in
  first-appearance order and (b) a rewritten form where each 3-part
  reference is collapsed to a single quoted identifier.  DuckDB
  reserves ``main`` as a catalog name and refuses to bind 3-part UC
  references natively; the route registers each Delta view at
  exactly that quoted identifier so the rewrite binds.  CTE
  aliases, subquery aliases, and 2-part / 1-part references are
  handled correctly (skipped or rejected).
- **Per-table SELECT enforcement.** The route fetches
  ``storage_location`` + effective permissions from soyuz-catalog
  for every referenced table and calls :func:`check_privilege` with
  ``SELECT``.  Admin short-circuits per the Phase 7 behaviour.  A
  missing grant raises :class:`AuthorizationError`, which the
  Sprint-44 RFC 9457 handler renders as
  ``application/problem+json`` with ``required_privilege=SELECT`` +
  ``full_name`` extension members.
- **Audit on execute.** Every successful call writes a
  ``query.executed`` audit row (per ROADMAP's Sprint-48 follow-up:
  Phase 12 audit actions use the ``resource.verb`` convention).
  The ``target`` is a truncated-SHA256 hash of the SQL so identical
  queries from different users collapse into one reverse-lookup key
  without blowing out the audit row width; ``detail`` carries a
  dict with ``row_count``, ``duration_ms``, referenced ``tables``,
  and the ``truncated`` flag.
- **CodeMirror 6 via CDN import-map.** The new ``pages/sql_editor.html``
  loads ``@codemirror/state``, ``@codemirror/view``,
  ``@codemirror/lang-sql`` and ``@codemirror/theme-one-dark``
  straight from ``cdn.jsdelivr.net`` through a ``<script type=
  "importmap">`` — matches the existing Bootstrap/Alpine/htmx CDN
  strategy.  Vendoring is deferred until a CSP or offline-install
  requirement makes it necessary.
- **Navbar + shortcut.** New "SQL" entry in
  ``components/nav_links.html`` (between Notebook and Jobs; shown
  to every logged-in user, not admin-gated — everyone is allowed
  to query what they have ``SELECT`` on).  ``g s`` added to the
  command-palette chord registry (``components/command_palette.html``)
  so ``g s`` from any page jumps to ``/sql``.
- **Settings.** New :class:`pointlessql.settings.SQLSettings`
  sub-model.  ``POINTLESSQL_SQL_ENABLED`` (default ``True``),
  ``POINTLESSQL_SQL_MAX_ROWS`` (default 10 000), and
  ``POINTLESSQL_SQL_QUERY_TIMEOUT_SECONDS`` (default 60 — the
  timeout knob is declared now; wiring lands in Sprint 52).  Set
  ``POINTLESSQL_SQL_ENABLED=false`` and the ``/sql`` page renders
  a disabled placeholder while ``/api/sql/execute`` returns a
  400 ``sql_execution_error``.
- **New exception ``SQLExecutionError``.** ``status_code=400``,
  ``error_code="sql_execution_error"``.  Covers both parse-time
  rejections (multi-statement, non-SELECT, 2-part refs) and
  DuckDB's own runtime errors (unknown column, type mismatch, …).
  Both surface the message verbatim so the user can fix their
  query without guessing.
- **Deps.** Added ``sqlglot>=26.0`` (resolved to 30.4.3 at lock
  time).  CodeMirror is CDN-loaded; no Python-side dep needed.
- Tests: 13 new unit tests in ``tests/test_sql_parser.py`` covering
  single refs, joins, CTE aliases, subqueries, deduplication,
  no-table queries, bad-format rejection, and the DuckDB rewrite
  output shape.  8 new route tests in ``tests/test_sql_execute.py``
  covering admin happy path, non-admin-without-SELECT 403,
  non-admin-with-SELECT happy path, malformed SQL 400, 2-part
  rejection 400, row-cap truncation, zero-table SELECT 1, and
  ``/sql`` page render.

### Added (Sprint 48) — audit-log hardening

- **Append-only ORM guards.** :class:`AuditLog` ``before_update``
  and ``before_delete`` SQLAlchemy event listeners raise a new
  :class:`AuditIntegrityError`; every existing audit row is
  effectively immutable at the ORM layer. The retention cleanup
  path opens a :class:`~contextvars.ContextVar` (the
  ``_allow_audit_mutation`` scope) to bypass the delete guard —
  that's the only way to remove a row through the ORM. Raw SQL
  can still bypass; deployments that need true WORM should layer
  PostgreSQL ``REVOKE DELETE`` on top. Pattern ported verbatim
  from ``shoreguard-fresh/shoreguard/services/audit.py:46–115``.
- **Async audit writes.** :func:`api.main._audit` now dispatches
  the INSERT via :func:`asyncio.to_thread`, so request handlers
  never block on the audit DB round-trip. The rate-limit
  middleware's ``rate_limit.blocked`` hook uses the same async
  path. All 22 call sites in ``api/main.py`` were rewritten to
  ``await _audit(…)``.
- **Structured ``detail`` and richer columns.** Alembic ``011``
  widens ``audit_log.detail`` from ``String(2000)`` to ``Text``
  and adds ``client_ip`` (IPv4/IPv6, nullable) + ``actor_role``
  (``admin``/``user``/``system``, defaults to ``user``). The
  :func:`log_action` helper accepts a JSON-encodable dict for
  ``detail`` and JSON-encodes it; plain-string callers still
  work for backwards compatibility.
- **Retention policy.** New :class:`AuditSettings` sub-model
  exposes ``POINTLESSQL_AUDIT_RETENTION_DAYS`` (default 365) and
  ``POINTLESSQL_AUDIT_CLEANUP_INTERVAL_SECONDS`` (default 86 400).
  A lifespan-owned background task calls
  :func:`cleanup_old_entries` on that cadence; failures are
  logged and swallowed. Setting ``retention_days=0`` disables
  the sweep entirely (pre-Sprint-48 behaviour).
- **JSON + CSV export.** New ``GET /admin/audit/export?fmt=json|csv``
  endpoint mirrors the viewer's filter surface (``since`` / ``action`` /
  ``user`` / ``target``) and streams a filename-stamped attachment,
  capped at 10 000 rows per call. Two new "Export" buttons in the
  Sprint-41 viewer build the same query string so operators get
  "what you see is what you download".
- **Viewer surfaces new columns.** The admin-audit template gains a
  Role badge column (admin/user/system styling) and a compact IP
  column. Existing search/sort/chip behaviour ported over the new
  ``data-sort-*`` attributes.

### Fixed (Sprint 48, tests)

- ``tests/test_admin_audit.py`` + ``tests/test_rate_limit.py``
  migrated from ``MagicMock(secret_key=…)`` fixtures to real
  :class:`Settings` instances (Sprint 47 missed these two files),
  and both now pin their engines to ``StaticPool +
  check_same_thread=False`` so the Sprint-48 async audit writes
  can hand the factory to ``asyncio.to_thread`` without the
  worker seeing an empty in-memory DB.

### Fixed (Sprint 47) — test-suite regressions

- **In-memory SQLite test schemas survive the worker thread.**
  ``asyncio.to_thread``-backed code paths (``_build_home_summary``'s
  ``_db_block``) hit the engine from a separate thread, and the
  default ``QueuePool`` + ``sqlite:///:memory:`` combination gives
  each worker its own empty database — tests that touched ``/`` or
  ``/catalogs/…`` reported "no such table: jobs" even though the
  root-conftest ran ``Base.metadata.create_all``. Fix: pin every
  in-memory engine to ``StaticPool`` + ``check_same_thread=False``
  in ``tests/conftest.py`` and ``tests/test_auth_routes.py``. No
  production code changes.
- **403 enforcement tests match the rendered title case.**
  ``test_enforcement.py`` still asserted the pre-Sprint-30
  ``"Access Denied"`` title; the current 403 template renders
  ``"Access denied"`` (lowercase ``d``) via ``_STATUS_TITLES`` and
  hardcoded copy. Two assertions updated.
- **``test_list_tables`` matches the current soyuz-catalog-client
  wire format.** ``ListTablesResponse(identifiers=…)`` → ``tables=…``
  after the v0.2 rename (the production ``pql.list_tables`` already
  reads ``response.tables``).

### Added (Sprint 46)

- **Graceful JWT signing-key rotation.** Final Phase 11 hardening
  sprint. A new optional ``POINTLESSQL_AUTH_SECRET_KEY_PREVIOUS``
  env var lets operators rotate the primary signing key without
  invalidating every outstanding session. New tokens are always
  signed with the primary key; ``verify_jwt`` tries the primary
  first and falls back to the previous key only if the primary
  rejects the token. Expired, tampered, or third-key tokens still
  fail under both. Rotation procedure:

  1. Set ``POINTLESSQL_AUTH_SECRET_KEY_PREVIOUS`` to the *current*
     (old) key value.
  2. Change ``POINTLESSQL_AUTH_SECRET_KEY`` to the new value.
     Restart / recreate the container so both settings are picked
     up at the same time.
  3. Wait for ``jwt_expiry_hours`` (default 168 h = 7 d) so every
     live session has either re-logged-in or naturally timed out.
     During this window, fresh logins emit tokens signed with the
     new key while existing cookies continue to verify under the
     old.
  4. Drop ``POINTLESSQL_AUTH_SECRET_KEY_PREVIOUS``. Any cookie
     still signed with the old key now fails verification and the
     user is bounced to ``/auth/login``.

  When ``secret_key_previous`` is unset (the default) the fallback
  path is disabled and a key change invalidates every live session
  immediately. Six new unit tests in ``tests/test_auth.py`` cover
  the happy path, fresh tokens during rotation, unknown keys,
  missing-fallback rejection, expiry preservation, and
  ``get_current_user``'s ``previous_key`` threading.

### Changed (Sprint 45) — BREAKING: nested Settings + renamed env vars

- **Flat `Settings` split into nine `BaseSettings` sub-models.** Fifth
  Phase 11 hardening sprint, porting the shoreguard-fresh nested-
  settings pattern 1:1.  Each sub-model owns its own ``env_prefix``:
  ``ServerSettings``, ``SoyuzSettings``, ``DatabaseSettings``,
  ``AuthSettings``, ``OIDCSettings``, ``LoggingSettings``,
  ``RateLimitSettings``, ``JupyterSettings``, ``SchedulerSettings``,
  ``DeltaSettings``.  Access moves from ``settings.secret_key`` to
  ``settings.auth.secret_key``, from ``settings.notebooks_dir`` to
  ``settings.jupyter.notebooks_dir``, etc.  Most environment
  variables are unchanged because the old flat prefix already
  overlapped — ``POINTLESSQL_RATE_LIMIT_*``,
  ``POINTLESSQL_SCHEDULER_*``, ``POINTLESSQL_OIDC_*``,
  ``POINTLESSQL_JUPYTER_*``, ``POINTLESSQL_SOYUZ_CATALOG_URL``,
  ``POINTLESSQL_LOG_LEVEL``, ``POINTLESSQL_LOG_FORMAT`` all still
  read the same value.  The breaking subset:

  | Old                                          | New                                              |
  | -------------------------------------------- | ------------------------------------------------ |
  | ``POINTLESSQL_HOST``                         | ``POINTLESSQL_SERVER_HOST``                      |
  | ``POINTLESSQL_PORT``                         | ``POINTLESSQL_SERVER_PORT``                      |
  | ``POINTLESSQL_BASE_URL``                     | ``POINTLESSQL_SERVER_BASE_URL``                  |
  | ``POINTLESSQL_DATABASE_URL``                 | ``POINTLESSQL_DB_URL``                           |
  | ``POINTLESSQL_SECRET_KEY``                   | ``POINTLESSQL_AUTH_SECRET_KEY``                  |
  | ``POINTLESSQL_JWT_EXPIRY_HOURS``             | ``POINTLESSQL_AUTH_JWT_EXPIRY_HOURS``            |
  | ``POINTLESSQL_ENGINE``                       | ``POINTLESSQL_DELTA_ENGINE``                     |
  | ``POINTLESSQL_NOTEBOOKS_DIR``                | ``POINTLESSQL_JUPYTER_NOTEBOOKS_DIR``            |
  | ``POINTLESSQL_NOTEBOOK_EXECUTE_TIMEOUT_SECONDS`` | ``POINTLESSQL_JUPYTER_EXECUTE_TIMEOUT_SECONDS`` |

  The ``docker-compose.yml`` and ``docker-compose.postgres.yml``
  default env blocks were updated in this sprint; the
  ``docker-compose.e2e.yml`` overlay accepts both the old and new
  ``BASE_URL`` name for a one-release transition.  Tests that built
  ``Settings`` with flat kwargs (``Settings(secret_key="…")``) must
  switch to nested dict kwargs (``Settings(auth={"secret_key":
  "…"})``).  The validator that anchors ``notebooks_dir`` to the
  startup CWD (BUG-28-02) and the ``oidc.enabled`` computed field
  both carried over unchanged — see ``pointlessql/settings.py`` for
  the new shape.

### Changed (Sprint 44) — BREAKING: error envelope shape

- **Error responses migrated to RFC 9457 `application/problem+json`.**
  Fourth Phase 11 hardening sprint. The previous nested envelope
  `{"error": {"code": "...", "message": "...", "request_id": "..."}}`
  is replaced by a flat top-level body `{"type": "about:blank",
  "title": "<status title>", "status": <code>, "detail": "<message>",
  "code": "<identifier>", "request_id": "..."}` served with
  `Content-Type: application/problem+json`. Domain `AuthorizationError`
  surfaces its `required_privilege`, `securable_type`, and `full_name`
  as RFC 9457 extension members; FastAPI's `RequestValidationError`
  flows through the same envelope with an `errors` array extension.
  API clients that read the old nested `.error.code` / `.error.message`
  fields must switch to top-level `.code` / `.detail`. The only known
  clients — PointlesSQL's own frontend via `frontend/js/api.js` and
  two Alpine templates — were updated in the same sprint.

### Added (Sprint 44)

- **HTMX toast bridge for inline errors.** Non-boosted HTMX fragment
  requests (`HX-Request: true` without `HX-Boosted: true`) that raise
  a domain error now receive an empty body at the real error status
  plus an `HX-Trigger` header carrying a `pqlToast` event. A
  `base.html` listener forwards level + message + request_id into the
  existing Sprint-30 `window.pqlToast.error` API so the user sees an
  inline Bootstrap toast without losing the current page. Boosted
  navigations keep the branded HTML error page so htmx can still swap
  `#main-content`. The primary consumer is the upcoming Phase-12 SQL
  editor: a failed query can now surface as a toast without the
  editor losing focus.
- **Three new domain exceptions.** `SchedulerError` (scheduler
  plumbing failures pre-notebook-run), `NotebookRenderError`
  (nbconvert failures, previously misclassified as generic
  `EngineError`), and `PQLWriteError` (subclasses `EngineError` so
  existing catches keep working, but its own code lets the UI
  distinguish write failures from read/compute failures).
  `services/notebook_render.py` now raises `NotebookRenderError`
  instead of `EngineError`; `tests/test_notebook_render.py` updated.
- **Playbook `docs/e2e-walkthroughs/error-handling.md`** covers
  problem+json media type on `/api/*`, HTMX toast trigger without
  page swap, boosted-navigation HTML fallback, and 403 extension
  members.

### Added (Sprint 43)

- **Rate limiting on `/auth/*`.** Third Phase 11 hardening sprint. A
  new `rate_limit_middleware` enforces per-IP and per-email fixed-
  window caps on the auth surface: 10/10min per IP + 5/10min per
  submitted email on `POST /auth/login`, 5/1h per IP on
  `POST /auth/register`, and a shared 20/10min per-IP bucket across
  `GET /auth/sso` + `GET /auth/callback`. Buckets live in a new
  `rate_limit_events` table (Alembic migration `010`) so the limiter
  ships with zero new runtime dependencies — no Redis, no slowapi,
  no background sweeper. Opportunistic cleanup inside every check
  `DELETE`s rows older than the window, and the composite
  `(bucket, created_at)` index covers both the count and the
  delete. The middleware sits between CSRF (outer) and auth (inner)
  so cross-site forged floods still fail the cheap CSRF check
  before they can burn a slot, while CSRF-clean abuse is caught
  before bcrypt + JWT-decode run on every attempt. Rejections
  return 429 with a `Retry-After` header and emit an
  `audit_log` row with `action="rate_limit.blocked"` so the
  Sprint-41 `/admin/audit` viewer surfaces the feature without a
  second dashboard. The `rate_limit_trust_x_forwarded_for` setting
  defaults OFF and must be flipped on explicitly behind a known
  reverse proxy — otherwise any client could forge the header and
  escape the per-IP bucket; the per-email axis still catches
  distributed attacks that probe one account from many IPs. New
  playbook `docs/e2e-walkthroughs/rate-limit.md` and
  `tests/test_rate_limit.py` cover login + register + OIDC floors,
  window expiry, the `/healthz` and `/api/*` exemptions, body
  re-injection, and the audit hook.

### Added (Sprint 42)

- **CSRF protection for HTML form routes.** Second Phase 11 hardening
  sprint. A new `csrf_middleware` implements the OWASP
  double-submit-cookie pattern: every request without a `pql_csrf`
  cookie gets one (`HttpOnly`, `SameSite=Lax`, matches the JWT
  cookie's `max_age`), and every non-safe method outside `/api/`,
  `/static/`, or `/healthz` must echo that cookie back via either a
  `csrf_token` form field or an `X-CSRF-Token` header. The
  `base.html` HTMX hook auto-attaches the header for every
  boosted request from the `<meta name="csrf-token">` tag, so
  existing HTMX flows pick up protection with zero per-route edits.
  A new `{{ csrf_input() }}` Jinja macro wires the three non-boosted
  forms (login, register, logout). Token rotates on local-login,
  OIDC-login, and logout to prevent fixation; failed login keeps the
  existing cookie so retry works without a page reload. New playbook
  `docs/e2e-walkthroughs/csrf.md` and `tests/test_csrf.py` cover
  cookie issuance, both submission paths, rotation, the `/api/*`
  exemption, and body re-injection so downstream handlers still see
  posted fields.

### Added (Sprint 41)

- **Admin audit-log viewer at `/admin/audit`.** First sprint of
  Phase 11 (Hardening). The Sprint-7 `audit_log` table has been
  write-only since it landed; Sprint 41 adds the read side. Admins
  get a filterable, newest-first list view that reuses the `/jobs`
  `listTable` Alpine component, the `pql-list-*` CSS, and the
  existing `_require_admin` gate — no new frontend primitives. The
  route supports four server-side filters (`since=24h|7d|30d|all`,
  `action=`, `user=` substring, `target=` substring) plus a client-
  side "Mine only" chip. A new Alembic migration `009` adds
  `ix_audit_log_created` so the cross-user "latest N" ordering
  query has a supporting index. New "Admin" dropdown in the top
  navbar (admin-only, gated in `components/nav_links.html`)
  anchors the `/admin/*` namespace that Phase 11's remaining
  sprints will extend. New playbook
  `docs/e2e-walkthroughs/admin-audit.md` replays the flow.

### Changed

- **`ROADMAP.md`.** Opened ⏳ entries for four forward-looking
  phases with a deliberate sequence: hardening first, features
  second, public launch last. **Phase 11 (Hardening)** — CSRF
  on HTML forms, rate limiting on `/auth/*` and future
  `/api/sql/*`, graceful `secret_key` rotation, admin audit-log
  viewer reusing the `/jobs` list-table machinery.
  **Phase 12 (SQL editor + query history)** — CodeMirror `/sql`
  page, DuckDB-only `PQL.sql()` with sqlglot-based table
  resolution, `query_history` + `query_history_tables` Alembic
  migration, saved queries, export, EXPLAIN, `g s` shortcut.
  **Phase 13 (Agent workloads — sketch)** —
  `paperclip-adapter-pointlessql` companion repo, new
  `agent_run` job kind, `X-Principal`-into-sandbox for UC
  enforcement on agent queries, read-only `/agents` discovery
  page; plus two uncommitted follow-ons (ontology / Foundry-
  lite; OSINT pattern playbook). **Phase 14 (Public launch +
  external distribution — queued last)** — GHCR private→public
  flip + Phase-10-deferred packaging replay, multi-arch builds,
  public PyPI publish, optional Helm chart, positioning /
  license decisions. Phase 14 is deliberately queued for the
  end per the Phase 10 retrospective ("release engineering
  against a private audience generates self-inflicted
  friction"). No code touched — these entries anchor scope
  discussed in-session so later sessions pick up where this
  one left off.

## [0.1.0rc3] - 2026-04-18

### Added (Sprint 40)

- **`.github/workflows/docker.yml`.** On-tag image publish to
  GHCR. Builds both the PointlesSQL image (from `Dockerfile`) and
  the soyuz-catalog image (from `Dockerfile.soyuz` with a
  `build-contexts: soyuz-catalog=soyuz-catalog` overlay pointing at
  a just-cloned soyuz-catalog checkout). Pushes to
  `ghcr.io/flohofstetter/pointlessql:<tag>` and
  `ghcr.io/flohofstetter/soyuz-catalog:<pinned-soyuz-tag>`. The
  soyuz tag is parsed from `pyproject.toml`'s `[tool.uv.sources]`
  at workflow time so no hard-coded version lives in CI. A
  `verify-soyuz-tag-exists` step does `git ls-remote` with
  `SOYUZ_READ_TOKEN` before building — fails fast on a
  never-pushed tag, guarding against the Sprint 37 `v0.2.0rc1`
  failure mode. Prerelease tags (`rc*`, `a[0-9]*`, `b[0-9]*`,
  `dev[0-9]*`) do not get the `:latest` alias, matching the
  `release.yml` regex.
- **GHCR image labels.** Both `Dockerfile` and `Dockerfile.soyuz`
  grew `ARG VCS_REF` / `ARG VERSION` + `LABEL
  org.opencontainers.image.{source,revision,version,title,
  description,licenses}` on the runtime stage. `docker.yml`
  passes `--build-arg VCS_REF=${github.sha} --build-arg
  VERSION=${github.ref_name}`. The `source` label is what GHCR
  uses to link the package to the repo sidebar.
- **`docs/install.md`.** First formal install guide. Three
  flavours: Docker + GHCR images (recommended primary), pip
  install from git tag, source checkout for contributors. Each
  ends with an "expected state" assertion and a troubleshooting
  section calls out the usual landmines — `DOCKER_BUILDKIT=0`
  silently dropping `--mount=type=secret`, fine-grained PAT
  requiring per-repo grants vs. classic-PAT scopes just working,
  stale `/app/data` SQLite after a version bump.
- **`docs/e2e-walkthroughs/packaging.md`.** Eleventh playbook —
  the clean-machine flow. Preconditions assert the Sprint 40 tag
  has shipped and images exist on GHCR. Steps: `cd
  "$(mktemp -d)"`, assert anonymous `docker pull` fails
  (proves the images are private), `docker login ghcr.io`, re-pull
  succeeds, `curl` the compose file at the tag, `sed` flips
  `build:` → `image:`, `docker compose pull && up -d`, healthcheck
  poll, Playwright MCP `browser_navigate` asserts the home-page
  Welcome `<h1>`, `docker image inspect` confirms
  `org.opencontainers.image.source` labels, teardown. Found-bugs
  section left with the `(none at time of writing — fill in
  during the first live replay)` placeholder that matches
  Phase 7/8/9 convention. Index in
  `docs/e2e-walkthroughs/README.md` grew a third section
  (`Packaging`).

### Changed (Sprint 40)

- **`Dockerfile` dual auth.** The single `--mount=type=ssh` RUN
  grew a second mount: `--mount=type=secret,id=gh_pat`, both
  `required=false`. Inline shell branch prefers the token if
  `/run/secrets/gh_pat` is non-empty, else falls back to the
  ssh-agent path. Sprint 38's `docker compose build --ssh default`
  contributor flow still works; the new `GH_PAT=$(gh auth token)
  docker compose build` path is what CI + clean-machine users hit.
- **`docker-compose.yml`.** The `pointlessql` service's `build:`
  block grew `secrets: - gh_pat` alongside the existing `ssh:
  [default]`; a top-level `secrets: gh_pat: { environment:
  GH_PAT }` block wires the env var to the BuildKit secret file.
  Each service also grew a commented `# image: ghcr.io/…:<tag>`
  line above its `build:` block with a two-line explainer so
  clean-machine users can flip to the pull path with a
  comment-out-and-uncomment edit.
- **`README.md` quickstart.** "Quick start (Docker + GHCR
  images)" is now the primary top-level install path — `docker
  login ghcr.io` → `curl docker-compose.yml` → flip two lines →
  `docker compose pull && up`. The `../soyuz-catalog` sibling
  prerequisite is gone from this section. Source-build demoted to
  "Quick start (local development)" below it; both sections
  cross-link to `docs/install.md`.
- **`CLAUDE.md`.** "Docker builds" subsection rewritten for
  dual-auth; new "GHCR images" subsection documents the on-tag
  publish pipeline + the PAT-based pull flow. "Replaying the e2e
  walkthroughs" bumped playbook count ten → eleven.

### Docs (Sprint 40)

- **`ROADMAP.md`.** Sprint 40 flipped to ✅. Phase 10 flipped to
  ✅ done. Phase 10 close-out block added following the
  Phase 7/8/9 shape: what the phase bought (clean `git clone &&
  uv sync` for source, clean `docker login && compose pull && up`
  for users, every future release cuts a GH Release plus two
  GHCR images automatically), plus Deferred-to-Phase-11 list
  (multi-arch arm64, PyPI publish, Helm chart, public-GHCR flip).

## [0.1.0rc2] - 2026-04-18

### Fixed (Sprint 38 follow-on)

- **Dual-mode dev toggle.** The documented escape hatch — dropping
  a gitignored `uv.toml` with a `[sources]` block to flip
  `soyuz-catalog-client` to the sibling `../soyuz-catalog`
  checkout — was rejected by `uv` with `error: Failed to parse:
  uv.toml. The sources field is not allowed in a uv.toml file.
  sources is only applicable in the context of a project`. The
  mechanism never actually worked; Sprint 38's smoke test only
  covered the default-pinned path. Replaced with two helper
  scripts, `scripts/use-editable-soyuz.sh` and
  `scripts/use-pinned-soyuz.sh`, that swap `[tool.uv.sources]` in
  `pyproject.toml` in-place. The swap intentionally leaves the
  tree dirty so the escape-hatch state stays visible. `.gitignore`
  loses its `uv.toml` stanza (the mechanism is gone); `CLAUDE.md`
  "Wiring soyuz-catalog" rewrites the editable-hatch section.

### Changed (Sprint 39 follow-on — CI)

- **`.github/workflows/test.yml` + `release.yml`.** Torn out the
  broken sibling-checkout + `uv.toml`-drop construction. Both
  workflows now consume the private `soyuz-catalog` dep the same
  way a local checkout does: `uv sync` resolves the pinned
  `[tool.uv.sources]` git-tag source, authenticated by a single
  `git config --global url."https://x-access-token:${SOYUZ_READ_TOKEN}@github.com/".insteadOf "https://github.com/"`
  step before `uv sync`. Removed: the debug curl-probes step, the
  raw `git clone --branch v0.2.0rc2 …` sibling-checkout step, the
  `cat > uv.toml <<EOF [sources] …` override step, and every
  `working-directory: PointlesSQL` (the main checkout lives at
  the default path again).
- **`SOYUZ_READ_TOKEN` preflight.** Added a 2-check gate step
  before `uv sync`: length ≥ 30 bytes (catches empty/truncated
  paste) and `GET https://api.github.com/user` returning 200
  (catches a revoked, expired, or typo'd PAT). Fails with a
  `::error::` annotation whose prose tells the maintainer exactly
  where to re-paste. No token material is echoed. Cost is one
  HTTPS request per run; saves a minute of dep resolution on
  every bad-secret state.
- **Alembic gate needs a migrated target.** `alembic check` on a
  fresh runner produced `FAILED: Target database is not up to
  date.` — the runner has no `pointlessql.db`, so `check` has
  nothing to compare the ORM models against. Workflows now run
  `alembic upgrade head` before `alembic check` so the sqlite
  file exists at the latest revision. Locally unchanged — the
  developer's working DB is already at head.

### Notes on external fix (SOYUZ_READ_TOKEN)

The previous org-secret values were all rejected by GitHub
(the first at `3ceaf45` was 1 byte; the later re-pastes were
40-byte strings that GitHub returned HTTP 401 for on
`/user`). The 16-commit `fix(ci)` investigation on main was
this plus the `uv.toml` bug tangled up. Resolved by pasting a
freshly-generated fine-grained PAT with `Contents: Read` on
`FloHofstetter/soyuz-catalog` into the repo secret. File
content unchanged.



### Added (Sprint 39)

- **`cliff.toml`.** git-cliff template keyed to PointlesSQL's
  Conventional Commit scopes (`feat(ui)`, `fix(ui)`,
  `build(packaging)`, `docs(roadmap)`, `fix(alembic)`, …). Drives
  the release-notes body in `release.yml`.
- **`scripts/bump-version.sh`.** Single-`pyproject.toml` variant
  of soyuz-catalog's Sprint 19 bump-script. Guards: PEP 440
  syntax, clean tracked-file tree, on-main, tag-not-exists. In-
  place version bump, `uv lock`, anchored `[Unreleased]` →
  `[X.Y.Z] - <date>` flip in CHANGELOG.md (hand-written prose
  preserved verbatim), `chore(release): vX.Y.Z` commit, annotated
  tag. Does not push.
- **`.github/workflows/test.yml`.** First CI this repo has had.
  Jobs: ruff, pyright, pydoclint (Google), `alembic check`.
  Pytest stays out per the standing sprint-gate discipline.
  Private soyuz-catalog git-dep pulled via a `SOYUZ_READ_TOKEN`
  org-secret URL rewrite.
- **`.github/workflows/release.yml`.** On-tag `v*`. Runs the
  gate, `uv build`s the wheel + sdist, asserts the wheel carries
  `pointlessql/_frontend/` (force-included) and
  `pointlessql/alembic/versions/`, generates release-notes via
  `uvx git-cliff --latest --strip all`, and `gh release create`s
  with `--prerelease` auto-toggled on PEP 440 `rc*` / `a*` / `b*`
  / `dev*` shapes.

### Fixed (pre-Sprint-39 cleanup)

- **Alembic autogen drift.** `uv run alembic check` had been
  flagging six `remove_index` operations + one `add_constraint`
  on every run — the indexes were declared in migrations
  001/002/003/004/006 but never mirrored into the ORM models, so
  autogen wanted to drop them on every comparison. Declared each
  index in the owning model's `__table_args__`, including the
  partial unique `ix_users_oidc_identity`
  (`WHERE oidc_provider IS NOT NULL`) via dialect-specific
  `sqlite_where=` / `postgresql_where=` kwargs. No migration
  written — this is a model-side fix for latent drift; nothing
  in the database changes. Gate now green, so the new alembic-
  check CI step lands on solid ground.

### Changed (Sprint 38)

- **`pyproject.toml`.** `[tool.uv.sources]` swapped from an
  editable path dep (`../soyuz-catalog/soyuz-catalog-client`) to a
  private-repo git-tag pin
  (`git = "https://github.com/FloHofstetter/soyuz-catalog", tag = "v0.2.0rc2", subdirectory = "soyuz-catalog-client"`).
  First sprint where `git clone && uv sync` works on a clean
  host without a sibling `../soyuz-catalog` checkout.
- **`uv.lock`.** Regenerated against the git pin; the client is
  resolved from
  `source = { git = "…?subdirectory=soyuz-catalog-client&tag=v0.2.0rc2#<sha>" }`.
- **`Dockerfile`.** Collapsed from 3 stages to 2. The
  `soyuz-client-builder` stage and the sed-strip on
  `[tool.uv.sources]` are gone. The remaining builder stage
  fetches the client wheel over git via BuildKit
  `--mount=type=ssh`, reusing the contributor's ssh-agent. Sprint
  40 will replace this with GHCR image pulls and
  `--secret`-based `GH_TOKEN` auth.
- **`docker-compose.yml`.** `additional_contexts.soyuz-catalog`
  (only fed the now-removed Stage 1) replaced with
  `build.ssh: [default]` so `docker compose build` forwards
  ssh-agent to BuildKit. Invoke with
  `docker compose build --ssh default pointlessql`.
- **`CLAUDE.md`.** "Wiring soyuz-catalog" section rewritten.
  Default clean-machine flow documented first; the editable
  escape hatch (drop a gitignored `uv.toml` at repo root with
  `[sources] soyuz-catalog-client = { path = …, editable = true }`)
  documented second. Docker `--ssh default` requirement called
  out with a Sprint 40 forward-reference.
- **`.gitignore`.** `uv.toml` added so contributors' editable
  overrides never land in commits.

### Added (Sprint 37)

- Phase 10 (Packaging & private distribution) opened in
  [`ROADMAP.md`](ROADMAP.md). Distribution contract locked in as
  private GitHub tags over `[tool.uv.sources]` git-subdirectory
  pins; no public PyPI.
- Sprint 37 — forward-pulled soyuz-catalog Sprint 19 release
  engineering. Lands in the sibling repo `../soyuz-catalog/` at
  commit `be9c5c6`: `cliff.toml`, `scripts/bump-version.sh`
  (lockstep version bump + CHANGELOG `[Unreleased]` flip +
  annotated tag, does not push), and
  `.github/workflows/release.yml` (on-tag; runs the existing
  `check_client_drift.sh` gate, builds server + client wheels +
  sdists, attaches all four to the GitHub Release with git-cliff
  release notes).
- First tag cut in soyuz-catalog: `v0.2.0-rc1`. Sprint 38 will
  pin PointlesSQL's `soyuz-catalog-client` source against it,
  retiring the editable path-dep that currently blocks
  clean-machine `uv sync`.

### Added (Sprint 36)

- New `frontend/js/api.js` exposes `window.pqlApi.fetch(url, init)`
  returning `{ok, status, data, error}` and auto-emitting a
  `window.pqlToast.error(...)` on non-ok responses (opt out with
  `init.silent = true`). Soyuz error bodies have their `detail` /
  `message` / `error` field extracted; network failures report
  `status: 0`. Also exposes `pqlApi.reloadWithToast(message, opts)`
  for the toast-then-reload pattern (400 ms default delay).
- Migrated five Alpine components off their hand-rolled
  `fetch` + try/catch/error-string blocks onto `pqlApi.fetch`:
  `editable`, `properties_editor`, `tags_editor`, `permissions_editor`
  (including the `silent: true` effective-permissions background
  GET), and the four `federation.js` create/delete forms. The
  inline `this.error` hints stay; the toast fires on top so
  mutations fail loudly instead of burying the error in a tiny
  red span.
- Replaced every silent `window.location.reload()` after a
  mutation with `pqlApi.reloadWithToast(...)` — `job_row_actions`,
  `/jobs` create modal, `/jobs/{id}` run/pause/resume, the
  `/dashboards/{slug}` Refresh button, and the `sync_history_card`
  Sync-now button each surface a success/info toast before the
  400 ms reload.
- Expanded the Sprint-31 command-palette Alpine component into a
  keyboard-shortcut registry. The hard-coded help-modal `<dl>` now
  iterates a `shortcuts` array with `{keys, combiner, label}`
  entries. New bindings: `g h` / `g j` / `g d` Vim-style chords
  (go home / jobs / dashboards) with a 1 s pending window; `r`
  reloads the current list page when `<body data-pql-refresh="1">`
  is set. Editable-target and modifier guards match the existing
  `?` handler.
- Plumbed `list_page: True` through the five list-route template
  contexts (`/jobs`, `/dashboards`, `/connections`,
  `/external-locations`, `/credentials`); `base.html` renders
  `data-pql-refresh="1"` on the `<body>` when the flag is set, so
  `r`-to-refresh opts in without touching each page template.
- Global `:focus-visible` rule in `style.css` gives every
  focusable element the same 2 px accent outline. The Sprint-33
  `.pql-sortable:focus-visible` rule is kept for its tighter
  offset. A new `@media (prefers-reduced-motion: reduce)` block
  zeroes the `--pql-duration-*` tokens and forces
  `animation-duration: 0ms` + `transition-duration: 0ms` on
  every element so Bootstrap fades, Alpine x-transitions, and
  the offcanvas slide all respect the user preference.
- New playbook `docs/e2e-walkthroughs/ux-overhaul.md` covering
  shortcut chords, the toast flow (error → red toast, success →
  toast-then-reload), focus rings, and the reduced-motion branch.

### Added (Sprint 35)

- Breakpoint tokens `--pql-breakpoint-sm/md/lg/xl` (640 / 768 /
  1024 / 1280 px) added to the Sprint-29 token block. Reference
  values only — CSS `@media` rules cannot consume `var()`, so
  every media query in `style.css` repeats the literal; the token
  block is the canonical contract, documented in
  `docs/design-tokens.md`.
- `components/nav_links.html` extracts the inline base.html
  `<ul class="navbar-nav">` so the same link set renders in the
  top navbar at `>=640 px` and again as a "Navigation" footer
  inside the existing `offcanvas-md` sidebar drawer at `<640 px`.
  One hamburger, not two — the scope's separate `<640 px`
  hamburger was merged into the existing sidebar toggle.
- `listTable()` gains a `mobileSort: boolean` config flag. When
  true, mount renders a `.pql-list-sort-mobile <select>`
  (hidden at `>=sm`) populated from every sortable `<th
  data-sort-key>` with asc / desc options. A new
  `_onMobileSort(raw)` method sets `sortKey` + `sortDir` in one
  pick, complementing the tri-state desktop header cycle. Wired
  up on jobs, dashboards, external-locations, and the Sprint-34
  Columns card.
- CSS-only card transform at `<640 px`: `.pql-list-table` rows
  collapse into 2-column label / value stacks, with each `<td>`'s
  `data-label="…"` rendered as an uppercase key via
  `::before`. Applied to the four `listTable()` pages plus the
  Sprint-34 Schemas / Tables / Preview / Columns cards. Row-
  action cells opt out of the key rendering (no `::before`) and
  stay right-aligned.
- `.pql-notebook-mobile-notice` banner above the Jupyter iframe
  at `<768 px` — "JupyterLab is optimised for desktop…". The
  iframe itself stays mounted; the notice is a heads-up, not a
  blocker.
- Touch-target baseline `min-height: 44px` under
  `@media (hover: none)` for buttons, links, inputs, selects,
  chips, sortable headers. Scoped to touch-only devices so
  hover-capable laptops keep the compact Sprint-33 spacing.
- New playbook `docs/e2e-walkthroughs/mobile.md` exercising
  phone (375 × 812) / tablet (768 × 1024) / desktop (1280 × 800)
  viewports via `browser_resize` + `browser_navigate`; found-
  bugs section filled in clean.

### Added (Sprint 34)

- Catalog detail page (`/catalogs/{c}`) gains an inline Schemas card.
  Populated by `client.list_schemas` folded into the existing
  `asyncio.gather`; shows name (linked to schema detail), updated,
  and comment. Per-schema table counts were dropped from the original
  scope to avoid O(N) fan-out to soyuz-catalog — `schema.updated_at`
  alone keeps the card useful without the extra round-trips.
- Schema detail page (`/catalogs/{c}/schemas/{s}`) gains an inline
  Tables card with name (linked to table detail), type, format, column
  count, updated, and comment — sourced from the existing
  `list_tables` bypass path that already returns full `TableInfo`
  payloads.
- Table detail page (`/catalogs/{c}/schemas/{s}/tables/{t}`) gains a
  Preview card. New `GET /api/catalogs/{c}/schemas/{s}/tables/{t}/preview`
  runs `PQL().table(...)` inside `asyncio.to_thread` under the
  caller's `X-Principal`, caps at 10 rows server-side (no
  client-tunable `?limit=`), emits `Cache-Control: no-store` so row
  data does not persist in the browser disk cache after a permission
  revocation, and degrades to a single-card error banner on any
  engine/Delta failure instead of 500-ing the page. Engine-agnostic
  via a `_preview_head` helper that keeps DuckDB lazy
  (`rel.limit(n).df()`) and coerces polars through `to_pandas()`.
  Values flow through `fastapi.encoders.jsonable_encoder` so Decimal,
  datetime, bytes, and numpy scalars serialise cleanly.
- Columns table on the table detail page gains client-side search +
  sort via Sprint-33 `listTable()` when `columns|length >= 20`.
  Sortable keys: position, name, type, nullable. Below the threshold
  the table stays server-rendered unchanged (progressive enhancement).
- Lineage card (`components/lineage_card.html`) now groups upstream
  and downstream nodes by depth under per-depth subheadings
  ("Depth 1", "Depth 2", …) instead of a flat `sort(depth)` list
  with padding-left indent. The per-node depth badge stays —
  redundant-but-defensive survives a future collapse/filter. Node
  links (3-part `catalog.schema.table` names → table detail) were
  already present from an earlier sprint and are unchanged.
- "Open in notebook" button on the PQL snippet card (admin-only).
  New `POST /api/catalogs/{c}/schemas/{s}/tables/{t}/open-in-notebook`
  sanitises identifiers with `re.sub(r"[^A-Za-z0-9_-]", "_", …)`,
  appends `secrets.token_hex(3)` to defeat double-click filename
  collisions, writes an `nbformat.v4` notebook (markdown header +
  a `pql.table(...)`-pre-filled code cell) to
  `{notebooks_dir}/scratch/…`, re-validates the path via
  `resolve_upload_target` to block traversal escapes, and returns a
  `lab_url` the Alpine handler navigates to with
  `window.location.assign`. Writes an `open_in_notebook` audit entry.
- `notebook_workspace` skip-list extended: `scratch/` joins `runs/`
  as a top-level directory excluded from `list_workspace_tree` so
  machine-generated scratch notebooks never pollute the
  user-authored workspace view. Skip logic rewritten to match by
  name against a `_SKIP_TOP_LEVEL_DIRS` frozenset scoped to the
  notebooks root — same behaviour as before for `runs/`, adds
  `scratch/` without duplicating the absolute-path equality check.

### Added (Sprint 33)

- Shared `frontend/js/list_table.js` — `window.listTable(config)`
  Alpine factory that adds debounced (150 ms) client-side search,
  sortable column headers (asc → desc → none, driven by `aria-sort`
  + a CSS pseudo-element arrow so no className juggling is required),
  and optional filter chips on top of any Bootstrap `<table>` whose
  rows carry `data-search` + `data-sort-<key>` attributes.
  Progressive enhancement — rows stay rendered server-side and the
  page is still usable if JS never runs.
- Applied `listTable` to `/jobs`, `/dashboards`, `/connections`,
  `/credentials`, `/external-locations`. Chips configured per page:
  `Paused` + `Last run failed` on jobs, `Has bound job` on
  dashboards, one chip per distinct `connection_type` on
  connections, one chip per distinct `purpose` on credentials,
  none on external-locations.
- `frontend/js/humanize_cron.js` — `window.pqlHumanizeCron(expr)`
  turns the common 5-field cron shapes + the six `@`-macros into
  human-readable strings ("Daily at 00:00", "Weekly on Monday at
  08:30"), falls back to the raw expression for anything the helper
  doesn't recognise. Applied on the `/jobs` list Cron cell and the
  `/jobs/{id}` detail Configuration card; the cell's `title`
  attribute still shows the raw expression for hover tooltips.
- `frontend/js/relative_time.js` — extracted the Sprint 32 inline
  `window.pqlRelativeTime` helper into its own file so the
  `/jobs` "last run" column can reuse it without duplicating code.
  `home.html`'s local copy is now a one-line pointer comment; the
  helper's behaviour is unchanged.
- `GET /api/jobs` now emits `last_run_status`, `last_run_at` and
  `last_run_duration_s` per job. Populated by a new
  `_latest_run_per_job(session, job_ids)` helper that fetches the
  latest run per job in one round-trip via a `group_by(job_id)` +
  `max(started_at)` subquery, portable across SQLite and Postgres
  and riding the existing `(job_id, started_at)` index on
  `JobRun`. The same map also feeds the server-rendered `/jobs`
  row rendering.
- `/jobs` rows gain a "Last run" column — a
  `.pql-status-dot--{status}` + `pqlRelativeTime(iso)` pair
  mirroring the home dashboard's latest-runs table. Rows with no
  runs yet show `—`.
- Hover quick-actions on `/jobs` rows (admin-only) — a trailing
  `<td class="pql-row-actions">` whose buttons are revealed on
  `tr:hover` and `tr:focus-within` (always visible on touch
  devices via `@media (hover: none)`). "Run now" POSTs to the
  existing `/api/jobs/{id}/run`; "Pause" / "Resume" POSTs to
  `/pause` or `/unpause`. Both fire through `window.pqlToast` for
  the success/error banner and reload 400 ms later, matching the
  Sprint-36-direction already established by Sprint 32.
- `frontend/js/job_row_actions.js` — `window.jobRowActions({jobId,
  paused})` Alpine factory backing the new row-action buttons.
- CSS additions in `frontend/css/style.css`: `.pql-list-controls`,
  `.pql-chip` + `.pql-chip--active`, `.pql-sortable` with arrow
  pseudo-element, `.pql-row-actions` with hover/focus-within
  reveal.
- `docs/e2e-walkthroughs/list-polish.md` — Playwright MCP playbook
  covering search debounce, sortable cycle, chip AND-ing, cron
  humanization + raw-title tooltip, last-run column rendering,
  hover-reveal + toast-then-reload on Run-now / Pause, the
  non-admin column gating, the four other flat list pages, the
  `/api/jobs` JSON shape, and a Sprint-32 relative-time
  regression check.

### Added (Sprint 32)

- Home dashboard — the `/` route (formerly the welcome hero in
  `pages/catalogs.html`) is now a real dashboard. Welcome header,
  7-day success-rate sparkline (inline SVG, no Chart.js),
  10 most-recent job runs with status dots, a Recent catalogs card
  driven by `localStorage['pql.recentCatalogs']`, Your-dashboards
  card (owner-scoped), and a Quick actions cluster that keeps the
  admin-only "Create foreign catalog" modal reachable.
- 3-step onboarding checklist empty-state — shown only when the
  current user has no visible catalogs, no jobs, and no dashboards;
  suppressed when soyuz is unavailable so users whose data is fine
  are not told to "connect a data source". Admin gets the inline
  Create-foreign-catalog button; non-admin sees an
  "ask an admin" hint.
- `GET /api/home/summary` — one round-trip for every server-side
  card. Returns `{user, catalogs, jobs, dashboards, latest_runs,
  sparkline, onboarding}`. Soyuz `list_catalogs()` runs in parallel
  with the local DB work via `asyncio.gather` + `asyncio.to_thread`;
  a `CatalogUnavailableError` downgrades to `catalogs.unavailable =
  true` with a 200 response so the page still renders every local
  card. Visibility mirrors `/api/jobs` (latest_runs + sparkline
  filter `Job.run_as_user_id == user.id` for non-admins).
- Catalog-visit instrumentation in `base.html` — any page that
  threads `active_catalog` (catalog/schema/table detail) writes
  `{name, ts}` into `localStorage['pql.recentCatalogs']`, deduped
  by name, capped at 5. Pattern mirrors the Sprint-31 palette's
  `pql.recentSearches` writer.
- Sparkline CSS in `frontend/css/style.css` uses three semantic
  tints (`--pql-color-success-fg` / `--pql-color-warning-fg` /
  `--pql-color-danger-fg`) plus a neutral empty-day style, so the
  prepared light-mode variant comes for free. Bars have a 2 px
  floor and a nested `<title>` tooltip for native hover.
- `.pql-status-dot--{succeeded,failed,running,pending,skipped}` —
  compact status indicators reused by the latest-runs table.
- `pages/home.html` + `components/create_foreign_catalog_modal.html`
  (extracted from the old welcome page; the modal markup itself is
  unchanged). `pages/catalogs.html` deleted — `/` was its only
  caller. The Sprint-22 `catalog-browsing.md` playbook's step 1 was
  updated to assert the new Quick actions counter instead of the
  old `N catalogs available` pill.
- `docs/e2e-walkthroughs/home.md` — Playwright MCP playbook
  covering the twelve home-page assertions including the soyuz-down
  degradation (verified 200 + `catalogs.unavailable=true` + banner +
  local cards still render), the visit-tracking instrumentation,
  and the system-empty onboarding trigger.

### Fixed (Sprint 32, same-commit from playbook replay)

- **BUG-32-01**: the sparkline SVG didn't render because Alpine's
  `<template x-for>` inside `<svg>` fails — `<template>.content`
  is an HTML-namespaced DocumentFragment, so inner `<rect>` elements
  were parsed as unknown HTML and never bound. Surfaced as
  `ReferenceError: d is not defined` / `Document.importNode:
  Argument 1 is not an object.` in the browser console on first
  load. Fixed by computing `bar_height`, `bar_class`, and
  `bar_title` server-side in `_build_home_summary` and rendering
  the seven `<rect>`s via a plain Jinja `{% for %}` loop. The
  `homeSparkline()` Alpine factory survives only for the meta
  counters.
- **BUG-32-02**: the home-page two-column CSS Grid used
  `align-items: stretch` (the Grid default), which dehned the Job
  activity card and the Quick actions card to match whichever
  neighbour was tallest. Combined with `grid-row: 2 / span 2` on
  the Latest runs card, the Sparkline card acquired a dead lower
  half. Fixed by switching to two flex columns
  (`.pql-home-col--primary` / `--secondary`) — each card now hugs
  its natural height. Also added `justify-content: space-between`
  to `.pql-home-sparkline` so the SVG and its meta counters sit at
  opposite ends of the card header rather than clustering on the
  left.

### Added (Sprint 31)

- Global command palette — `Cmd+K` / `Ctrl+K` opens a centred dialog
  that searches catalogs, schemas, tables, connections, credentials,
  external locations, jobs, dashboards, and (admin-only) workspace
  notebooks in one shot. Prefix matches outrank substring matches;
  ties resolve by `updated_at` descending. Empty query renders
  `localStorage['pql.recentSearches']` (last 10, deduped by URL).
  `?` opens a keyboard-shortcuts help modal.
- `GET /api/search?q=&limit=` aggregates the seven sources via
  `asyncio.gather` (reusing `unitycatalog.get_tree()`,
  `list_connections/credentials/external_locations`, the local
  `Job` / `Dashboard` ORM queries, and
  `notebook_workspace.list_workspace_tree`). Per-source soyuz
  failures degrade gracefully: a `PointlessSQLError` from one
  fetcher logs at WARNING and the remaining sources still answer,
  so a soyuz blip never 502's the palette.
- `frontend/templates/components/command_palette.html` mounted once
  in `base.html` so the shortcut is global. Alpine factory
  `commandPalette()` owns palette + help-modal state, debounces
  search to 150 ms, drops stale responses by sequence number, and
  guards `?` against firing while focus is in an input or the
  palette itself.
- Navbar gains a ghost-button trigger (`.pql-cmdk-trigger`) with a
  platform-aware `⌘K` / `Ctrl+K` keycap hint and a mobile-only
  search-icon button below 768 px. Removed the `ms-auto` from the
  navbar `<ul>` and put it on the trigger so the button anchors the
  right-hand cluster.
- Design-token-native CSS for the palette, hit list, type badges
  (one accent per source family), help modal, and `<kbd>` keycaps;
  reuses `--pql-color-*`, `--pql-elev-3`, and `--pql-radius-md`
  from Sprint 29 so light mode works for free.
- `docs/e2e-walkthroughs/command-palette.md` — Playwright MCP
  playbook covering navbar trigger, Cmd+K, keyboard nav, recent
  searches, admin/non-admin notebook visibility split, the `?`
  help modal, and the soyuz-degraded fallback.

### Added (Sprint 30)

- New app-shell layer in `base.html`: mobile-aware responsive grid
  (`minmax(0, 1fr)` below `md`, `var(--pql-sidebar-width) minmax(0, 1fr)` ≥ md),
  sidebar wrapped in Bootstrap 5.3 `offcanvas-md` with a hamburger
  trigger visible only on narrow viewports. No new JS module — Bootstrap's
  built-in offcanvas handles open/close, backdrop, and Esc-to-close.
  Sprint 35 hardens touch targets and focus-trap.
- `frontend/templates/components/breadcrumbs.html` — declarative
  component that renders from a `breadcrumbs=[{label, href?}]` list;
  the final item (or any item without `href`) becomes the active
  terminal crumb. Migrated 8 pages: `jobs`, `dashboards`, `connections`,
  `external_locations`, `credentials`, `notebooks_workspace`,
  `schemas`, `tables`.
- `frontend/templates/components/empty.html` — reusable empty-state
  panel with optional `icon`, `title`, `message`, `action_href` /
  `action_label`, and a `flush` variant for use inside an existing
  card. Migrated the 6 list-page empty states (jobs, dashboards,
  connections, external_locations, credentials, notebooks_workspace)
  — in-card snippets (permissions, tags, lineage, properties,
  sync_history) remain opportunistic follow-up.
- New branded error pages: `pages/404.html` (bi-compass), `pages/500.html`
  (bi-exclamation-octagon, renders `request_id` for bug reports),
  both on the new app shell. `pages/403.html` refitted onto the same
  `components/empty.html` primitive — preserving the existing
  `required_privilege`/`securable_type`/`full_name` context.
- `pointlessql/api/error_handlers.py` — Accept-aware dispatch:
  `/api/` paths still always emit the JSON envelope; non-`/api/` paths
  honour an explicit `Accept: application/json` without `text/html`,
  otherwise render the HTML shell. Registered a `StarletteHTTPException`
  handler so unmapped 404s render the branded page (not FastAPI's
  default JSON), and an `Exception` catch-all that logs `exc_info` and
  returns the 500 shell or JSON envelope.
- `frontend/js/toast.js` — `window.pqlToast.{success, error, info}(msg, {timeout}?)`
  mounted once in `base.html`. Each call builds a Bootstrap toast in
  `#pql-toast-root`, applies a Sprint-29 semantic variant
  (`.pql-toast--{success|error|info}`), and removes the node on
  `hidden.bs.toast`. API only this sprint; Sprint 36 wires the five
  existing components onto an `apiFetch` helper that emits toasts
  on error.
- CSS additions in `frontend/css/style.css`: responsive `.pql-shell`
  grid, `.pql-sidebar-shell` offcanvas reset, `.pql-sidebar-toggle`,
  `.pql-breadcrumbs`, `.pql-empty` (+ `.pql-empty--{variant}` tints,
  `__icon` / `__title` / `__message` / `__meta` / `__action`),
  `.pql-error-shell` centered wrapper, and `.pql-toast` (+ variants).
  All colour pairs reuse Sprint-29 semantic tokens so light-mode
  inherits for free.

### Added (Sprint 29)

- Design-token system in `frontend/css/style.css`: spacing
  (`--pql-space-1..8`, 4-px scale), typography
  (`--pql-text-xs..3xl`, ~1.125 modular ratio), radius
  (`--pql-radius-sm|md|lg|pill`), elevation (`--pql-elev-0..3`,
  dark-mode-tuned), motion (`--pql-duration-fast|normal|slow` +
  `--pql-ease`), and semantic colour pairs (success / warning /
  danger / info / neutral — each with a `bg` + `fg` variable so
  chip text meets AA contrast against its own background). Brand
  accent `#76b900` preserved as `--pql-color-accent`
- Light-mode variant **prepared** via a
  `:root[data-bs-theme="light"]` override block — tokens flip
  automatically when the attribute changes. No toggle is wired
  yet; switching in DevTools is enough to verify downstream
  primitives adapt
- Inter font self-hosted (OFL-1.1, Latin subset) at
  `frontend/fonts/inter-regular.woff2` (23.7 kB) and
  `inter-semibold.woff2` (24.3 kB) — combined 48 kB, under the
  50 kB per-page budget. Two `@font-face` blocks with
  `font-display: swap`; `body { font-family: var(--pql-font-sans); }`
  picks it up globally. Regular is `<link rel="preload">`-ed in
  `base.html`; SemiBold is lazy-loaded on first use
- CSS-only primitives: `.pql-stack` (vertical flex with token
  gap; `--tight`/`--loose` modifiers), `.pql-cluster`
  (horizontal wrapping cluster), `.pql-card` (panel surface
  replacing the 18-site `card mb-4 p-4` pattern; sibling
  `.pql-card + .pql-card` auto-margins; `.pql-card--flush`
  strips padding for iframe wrappers), `.pql-badge` (pill-shaped
  status chip, semantic-palette modifiers `--success|warning|danger|info`)
- Proof-of-concept template migrations: `base.html` (font
  preload + Inter via body rule), `pages/login.html` (card ↦
  `.pql-card` + nested `.pql-stack` form layout), and
  `pages/catalogs.html` (welcome hero wrapped in `.pql-card` +
  `.pql-stack --loose`; catalog-count chip becomes
  `.pql-badge --info`). The remaining 27 templates stay on
  Bootstrap utilities and will migrate in Sprints 30 / 33 / 34
  as those sprints touch each surface
- `docs/design-tokens.md` reference — token tables with
  "when to use" notes, primitive snippets, light-mode override
  pattern, and contribution conventions (new tokens land
  alongside a doc update in the same commit)

### Added (Sprint 28)

- Alembic migration `008_dashboards.py` creating the
  `dashboards` table (slug unique, title, description,
  notebook_path, job_id FK nullable with `ON DELETE SET NULL`,
  owner_id FK, timestamps)
- New `Dashboard` ORM model in `pointlessql/models.py`
- `render_run_notebook` in `pointlessql/services/notebook_render.py`
  gains an `exclude_input: bool = False` keyword; when true,
  renders with `HTMLExporter(..., exclude_input=True)` and caches
  to a sibling `{run_id}.dashboard.html` sidecar so the
  code-visible and code-hidden variants coexist without clobbering
  each other
- `GET /jobs/{id}/runs/{rid}/notebook` gains an optional
  `?exclude_input=true` query param threaded through to the
  render helper
- Dashboard CRUD routes: `GET /api/dashboards` (list, any
  logged-in user), `GET /api/dashboards/tree` (sidebar shape),
  `POST /api/dashboards` (admin-only, validates slug against
  `^[a-z0-9][a-z0-9-]{0,199}$`), `PATCH /api/dashboards/{slug}`
  (admin-only; editable fields: title, description,
  notebook_path, job_id), `DELETE /api/dashboards/{slug}`
  (admin-only), `POST /api/dashboards/{slug}/refresh`
  (admin-only; triggers the bound job's `execute_run(...,
  trigger="manual")` via the same helper that powers the
  job-detail Run-now button)
- `GET /dashboards` list page + `GET /dashboards/{slug}` detail
  page rendering the latest succeeded run through an iframe
  pointed at `/jobs/.../notebook?exclude_input=true`; empty
  state when no job is bound or no successful run exists
- `GET /jobs/{id}/runs/{rid}/compare?to={other_rid}` — two
  Sprint-26 iframes side-by-side with run metadata headers; both
  run ids are validated to belong to the same job before render
  (no foreign-run leak). No cell-level diff highlighting (stub)
- "Compare runs" card on `pages/job_detail.html` (visible only
  when ≥ 2 completed runs exist) with two `<select>`s and a
  Compare button that navigates to the compare URL
- New templates: `pages/dashboards.html`,
  `pages/dashboard_detail.html`, `pages/run_compare.html`, and
  `components/dashboards_sidebar.html` (mirrors the Sprint 27
  workspace-tree component; `sessionStorage` key
  `pql.dashboards`)
- Navbar gains a **Dashboards** link (visible to every logged-in
  user — consumer surface, not admin-only); `base.html` swaps in
  the dashboards sidebar when `active_page == 'dashboards'`
- New playbook `docs/e2e-walkthroughs/dashboards.md` covering
  create-modal → detail with code-hidden iframe → Refresh →
  sidebar tree → non-admin visibility → run-compare from the
  job-detail card, plus the foreign-run 404 negative

### Added (Sprint 27)

- New `pointlessql/services/notebook_workspace.py` with
  `list_workspace_tree(notebooks_dir)` (nested listing with per-
  notebook `parameters_tagged: bool`; skips the executor `runs/`
  subdir) and `resolve_upload_target(notebooks_dir, relative_path)`
  (mirrors `resolve_notebook_path` but allows a not-yet-existing
  target and requires the parent directory to exist)
- `GET /api/notebooks/tree` — admin-only directory listing for
  the workspace browser
- `POST /api/notebooks/upload` — admin-only multipart upload of
  `.ipynb` files into the notebooks workspace; validates
  `.ipynb` extension, parses the body as JSON before writing,
  atomically replaces via a `.tmp` sidecar, and requires an
  explicit `overwrite=true` form field to clobber an existing
  file
- `GET /notebooks/workspace` — new admin-only HTML page with a
  flattened-tree component keyed on `sessionStorage`
  `pql.notebooks` / `pql.notebooks.open`, plus a per-leaf
  **Schedule…** button that navigates to
  `/jobs?prefill_kind=papermill&prefill_notebook_path=<path>`
- Create-job modal (`pages/jobs.html`) reads those query params
  on mount, pre-fills `kind=papermill` + `notebookPath`, chains
  `inspect()` for the typed-parameters form, opens the modal,
  and strips the query string via `history.replaceState`
- Navbar gains a **Workspace** link (admin-only) between
  Notebook and Jobs
- Playbook extension: Part G in
  `docs/e2e-walkthroughs/notebook-jobs.md` covers upload →
  schedule → run-now → Output artifacts card, plus non-admin
  403 and the overwrite / traversal / non-`.ipynb` negative paths

### Added (Sprint 26)

- `nbconvert>=7.0` dep and new `pointlessql/services/notebook_render.py`
  with `render_run_notebook(runs_dir, run_id)` — first call runs
  `HTMLExporter(template_name="lab")` on
  `runs/{run_id}.ipynb`, writes an atomic `.html` sidecar next to
  it, and returns the HTML; subsequent calls serve the sidecar
- `GET /jobs/{id}/runs/{rid}/notebook` — inline-renders a
  papermill run's output notebook for iframe embedding on the
  job-detail page
- `GET /jobs/{id}/runs/{rid}/notebook/download?format={ipynb,html}`
  — visibility-checked downloads of the raw notebook or its
  rendered sidecar. Replaces the originally planned
  `/notebooks/runs/` StaticFiles mount so non-owner logged-in
  users can't exfiltrate other users' run outputs by guessing
  `run_id`s. Both routes share `_load_papermill_run_output_path`
  which validates job ownership, papermill kind, and run
  ownership before touching disk
- New "Output artifacts" card on `job_detail.html` (between
  the DAG tasks and Recent runs cards, guarded by
  `job.kind == "papermill"`): auto-selects the most recent
  succeeded/failed run on page load, Rendered/JupyterLab view
  toggle wired to the two iframe sources, download links for
  `.ipynb` and `.html`
- Recent runs rows are now clickable on papermill jobs;
  `$dispatch("run-selected", { runId })` swaps the card's
  iframe to the clicked run's output. The Sprint 24 "Open in
  JupyterLab" anchor retains `@click.stop` so row-click and
  popout-click don't collide
- `docs/e2e-walkthroughs/notebook-jobs.md` Part F walks the
  card's auto-select, view-toggle, row-click swap, downloads,
  and the three 404 negatives

### Added (Sprint 25)

- `GET /api/notebooks/inspect?path=…` admin-only route wrapping
  `papermill.inspect_notebook` — returns
  `[{name, default, inferred_type, help}]` so the create-job modal
  can render one typed input per declared parameter instead of a
  free-form JSON textarea
- Create-job modal gains a "Load parameters" button, a typed form
  (`number` / `checkbox` / `text` / `textarea`) rendered via Alpine
  `x-for`, and a collapsed `<details>` "Advanced" fallback that
  keeps the raw JSON textarea for power users. Advanced mode wins
  over the typed form when the `useAdvanced` checkbox is ticked
- Job-detail Configuration card renders dedicated **Notebook** and
  **Parameters** rows for papermill jobs (nested `<dl>` for the
  parameters) instead of the catch-all `<pre>{{ config|tojson }}</pre>`
- Promoted `_resolve_notebook_path` → public `resolve_notebook_path`
  in `services/scheduler.py` so the inspect route reuses the same
  traversal-safe path resolver the executor uses
- Seed script writes `notebooks/smoke_typed_params.ipynb`
  (`count: int = 3`, `enabled: bool = True`, `label: str = "hello"`)
  for the new Part E playbook — one parameter per typed-input branch
- `docs/e2e-walkthroughs/notebook-jobs.md` Part E walks the
  inspect endpoint, the typed-form rendering + override, the
  Advanced raw-JSON fallback, and two negative inspect cases
  (missing file, traversal). Live-run findings appended to the
  Found-bugs section — no bugs surfaced

### Added (Sprint 24)

- Papermill job kind: `_papermill_executor` registered next to
  `pg_sync` and `python` in `scheduler_service.build_default_registry()`.
  Config shape `{notebook_path, parameters, timeout_seconds}`;
  output lands at `{notebooks_dir}/runs/{job_run_id}.ipynb` so the
  embedded JupyterLab serves it at `/lab/tree/runs/{run_id}.ipynb`
- `POINTLESSQL_PRINCIPAL` env var honoured by the `PQL` constructor
  (via `make_principal_client`) so notebook code running under the
  Papermill executor inherits the job's run-as user without extra
  wiring — the scheduler exports the env var into the kernel
  subprocess
- New settings `POINTLESSQL_NOTEBOOKS_DIR` (default `notebooks`) and
  `POINTLESSQL_NOTEBOOK_EXECUTE_TIMEOUT_SECONDS` (default `300`).
  `services/jupyter.py` now resolves its `--notebook-dir` through
  the setting so the executor and the embedded JupyterLab share a
  single source of truth
- Create-job modal (`frontend/templates/pages/jobs.html`) gains a
  `kind` select with `DAG (multi-task)` and `Papermill (single
  notebook)` options; Papermill-specific `notebook_path` +
  `parameters` inputs render conditionally
- Job detail page (`frontend/templates/pages/job_detail.html`)
  recent-runs table gains a trailing "Open in JupyterLab" column
  on rows of `kind=papermill` jobs whose run status is `succeeded`
  or `failed`
- `docs/e2e-walkthroughs/notebook-jobs.md` — Phase-8 playbook
  covering create via modal, Run-now, output-artifact verification,
  the JupyterLab deep-link, and four negative paths
  (missing path, traversal, missing file, failing cell)

### Added (Sprint 23)

- `docker-compose.e2e.yml` gains a `mock-oidc` service
  (`ghcr.io/navikt/mock-oauth2-server:latest`, host port 9090)
  and `${…:-default}` env passthroughs on the `pointlessql`
  service for `POINTLESSQL_SCHEDULER_TICK_SECONDS`
  (default `2` so DAG state transitions land in seconds during
  live walks), `POINTLESSQL_JUPYTER_ENABLED`,
  `POINTLESSQL_LOG_FORMAT`, and the four `POINTLESSQL_OIDC_*`
  / `POINTLESSQL_BASE_URL` knobs. All default to empty so the
  Sprint 22 data-surface playbooks keep working unchanged
- Five orchestration + operational playbooks under
  `docs/e2e-walkthroughs/`:
  - `jobs-dag.md` — single-task + DAG job creation, Run-now,
    retry + fail-skip propagation, Pause/Resume click, per-task
    log panel expand, and a `pg_sync`-kind cross-feature smoke
    driving Sprint 18's `run_sync()` against the Sprint 22
    `pg_mirror` foreign catalog
  - `notebook.md` — `/notebook` + `/api/jupyter/status` in
    `jupyter_enabled=true` (iframe src `http://localhost:8888/lab`,
    Alpine `jupyterLoader().ready` flips to true) and `=false`
    (template short-circuits to "Notebook Disabled" card) passes
  - `oidc.md` — SSO button absent with no OIDC env, then with
    the mock issuer a full authorize-code + PKCE round-trip that
    auto-creates a user with `oidc_provider` / `oidc_subject`
    bound; repeated sign-in reuses the existing row
  - `operational.md` — anonymous `/healthz`, admin `/metrics`
    `text/plain` with all three metric families, non-admin
    `/metrics` renders 403, JSON API errors carry a UUID
    `request_id`, `X-Request-ID` round-trips client-supplied
    values
  - `config-matrix.md` — primary walk (`engine=pandas,
    log=text, db=sqlite`) plus five delta walks for every
    non-default value of `POINTLESSQL_ENGINE`,
    `POINTLESSQL_LOG_FORMAT`, `POINTLESSQL_DATABASE_URL`, and
    their cartesian-product smoke
- `docs/e2e-walkthroughs/README.md` updated: cross-links to the
  ten playbooks, the host-env overlay table with the
  recreate-pointlessql workflow, and a Sprint-23 section on the
  `mock-oidc` + bridge-IP workaround for Docker DNS asymmetry
- `CLAUDE.md` "Replaying the e2e walkthroughs" section pinning
  the ten-playbook tree, the `--browser firefox` /
  `chrome-for-testing` MCP config requirement (Sprint 22 commit
  `3f1da76` backstory), and the "replay before landing HTML/JS"
  contract for future sprints
- Phase 7 close-out summary appended to `ROADMAP.md`: all five
  surfaced bugs fixed same-commit, none deferred

### Fixed (Sprint 23)

- **BUG-23-01**: `oidc_enabled` computed property in
  `pointlessql/settings.py` used `is not None`, treating the
  empty strings produced by the compose overlay's
  `${POINTLESSQL_OIDC_DISCOVERY_URL:-}` fallback as
  *configured*. The SSO button on `/auth/login` rendered and
  clicking it hit a `401 Failed to fetch OIDC discovery
  document`. Truthy check replaces the `is not None` so both
  `None` and `""` count as "not configured"
- **BUG-23-02**: `POST /api/jobs` in `pointlessql/api/main.py`
  committed the `Job` row before running
  `scheduler_service.validate_dag` over the task list, so a
  cycle / unknown-dep payload returned 422 but left the job row
  visible on `/jobs` forever. Refactored to `session.flush()`
  during the two-pass task insert and a single final
  `session.commit()` only after `validate_dag` succeeds —
  rejected payloads roll back cleanly when the session context
  exits

### Added (Sprint 22)

- `docker-compose.e2e.yml` overlay — `postgres-e2e` sidecar
  (postgres:17-alpine, port 5433) seeded from
  `scripts/pg-seed.sql` as the foreign-catalog target for the
  sync playbook; mounts `./scripts:/app/scripts:ro` on the
  `pointlessql` service so the seed script can run server-side
  with consistent `file:///app/warehouse/...` storage URIs
- `scripts/pg-seed.sql` — defensively idempotent Postgres
  `shop` schema (customers, products, orders) with a few seeded
  rows so the first foreign-catalog sync returns `added_count`
  equal to `schema + 3 tables`
- `scripts/seed-e2e.py` — idempotent driver that runs inside
  the PointlesSQL container: creates managed catalog `demo`,
  schemas `demo.sales` / `demo.hr` with `file://` storage
  roots, writes four Delta tables via `PQL.write_table` (50
  orders, 20 customers, 10 employees, 10 salaries), and
  registers a soyuz `Connection pg_e2e` pre-bound to the
  seeded Postgres so the foreign-catalog create modal picks it
  up without further setup
- `docs/e2e-walkthroughs/README.md` — operator doc: stack
  start/teardown, test-user credentials shared across playbooks,
  how Claude replays a playbook via the Playwright MCP tool set,
  selector conventions for a codebase without `data-test`
  attributes, rebuild note for stale cached container images
- Five Markdown playbooks under `docs/e2e-walkthroughs/`:
  `auth.md` (first-user admin bootstrap + non-admin + `/auth/me`
  + `/metrics` 403), `catalog-browsing.md` (welcome screen +
  sidebar-tree sessionStorage persistence + PQL-snippet copy
  button), `inline-editors.md` (`editable` +
  `properties_editor` + `tags_editor` + `permissions_card`
  grant/revoke across catalog/schema/table, driven via
  `Alpine.$data(card)` rather than DOM mutation so Alpine's
  reactive bindings don't swallow typed values), `federation.md`
  (admin CRUD of connections / credentials / external locations
  with `deleteConfirm`, non-admin 403 negative), and
  `foreign-catalog-sync.md` (create-foreign-catalog modal → Sync
  now → sync-history card → mirrored `pg_mirror.shop.*`
  tables in the sidebar)
- All five playbooks exercised live via Playwright MCP in
  Firefox against a freshly-composed stack. Playbooks record
  what each step's `browser_evaluate` returned so the next
  replay has a concrete expectation. Three bugs surfaced
  during the live run and were fixed in the same sprint:
  - **BUG-22-01 fixed**: `_wrap_catalog_errors` in
    `pointlessql/services/unitycatalog.py` now branches on
    `UnexpectedStatus.status_code` — 404 → `CatalogNotFoundError`,
    other 4xx → `ValidationError`, only 5xx / transport →
    `CatalogUnavailableError`. PATCH permissions with an
    invalid privilege (e.g. `SELECT` at catalog level) now
    returns `422 validation_error` passing the soyuz message
    through; PATCH on a non-existent catalog now returns
    `404 catalog_not_found`
  - **BUG-22-02 fixed**: the same decorator now catches
    `KeyError` / `TypeError` raised by a generated
    `Create*.from_dict()` (missing required request-body field)
    and re-raises `ValidationError`. `POST
    /api/external-locations` without `credential_name` now
    returns `422 validation_error: "Invalid request body:
    'credential_name'"` instead of a 500 leaking the KeyError
  - **BUG-22-03 fixed**:
    `createExternalLocationForm.submit()` in
    `frontend/js/federation.js` now rejects an empty
    `credentialName` with an inline error before issuing the
    request, matching the UC spec requirement surfaced by
    BUG-22-02

### Added (Sprint 21)

- `pointlessql/services/metrics.py` — Prometheus surface on its
  own `CollectorRegistry` so tests don't contaminate the global
  default. `Counter pointlessql_job_runs_total{status,job_name}`,
  `Histogram pointlessql_job_run_duration_seconds{job_name}`
  (buckets 0.05 s .. 3600 s, log-spaced, includes the Prom
  default 10 s), `Gauge pointlessql_scheduler_tick_lag_seconds`;
  `render_metrics()` / `record_run()` / `observe_tick_lag()`
  helpers
- `GET /metrics` admin-only (raises `AuthorizationError` via
  `_require_admin`); returns `generate_latest()` bytes with
  `text/plain; version=0.0.4`
- Optional per-job failure webhook: `jobs.on_failure_url`
  (Alembic migration 007, nullable `String(1000)`). Scheduler
  POSTs `{job_id, job_name, run_id, status, error, started_at,
  finished_at}` (ISO-8601) on a failed run via
  `_post_failure_webhook`. 5 s timeout, no retries, one-shot
  `httpx.AsyncClient.post`; `httpx.HTTPError` logged at WARN
  and swallowed so a broken receiver never affects run state.
  `_webhook_client_factory` exposed for test stubbing
- `docs/jobs.md` — authoring guide: executor signature
  (`job_run_id, user_info, config, uc_client`), publishing a
  custom kind via the `pointlessql.jobs` entry-point group, the
  scheduling JSON + `on_failure_url` payload shape, a worked
  `pql`-in-a-task summary-table example, notes on logging /
  retries / concurrency, observability, and when to add a
  built-in kind instead
- README.md gains a "Jobs" section linking to `docs/jobs.md`
- `tests/test_metrics.py` — 9 new tests (emission on success +
  failure, `/metrics` admin-only enforcement, webhook URL +
  payload keys + timeout, no-webhook path, broken-receiver
  does not abort the run). Sprint 19+20 scheduler tests still
  green (36 passed). Full suite not run in this sprint

### Changed (Sprint 21)

- `scheduler.py`: `execute_run` wraps a new `_execute_run_core`
  and emits telemetry around every run; `tick_once` emits
  telemetry for synthetic `skipped` rows too; `Scheduler._run`
  samples tick lag each iteration

### Added (Sprint 20)

- Alembic migration 006: `jobs.max_parallel_runs`; `job_tasks`
  gains `kind`, `depends_on` (JSON list of task ids),
  `max_retries`, `retry_backoff_seconds`; new `task_runs`
  (id, job_run_id FK, task_id FK, status, started_at,
  finished_at, attempts, error); `job_logs.task_id` nullable
  FK (batch-alter safe on SQLite)
- Topological DAG walk in `scheduler.py`: iterative three-color
  DFS validates the graph at create-time and raises
  `ValidationError("cycle detected in task graph: [...]")`
  with the offending path; unknown `depends_on` ids caught
  in the pre-pass; upstream-fail → downstream tasks marked
  `skipped` (not `failed`)
- Retry policy per task: linear backoff (delay between
  attempts `i` and `i+1` is `i * retry_backoff_seconds`);
  `_sleep` is a module-level hook so tests patch it;
  attempts counted on `TaskRun`
- Concurrency caps: layered `asyncio.Semaphore`. Global
  semaphore sized from
  `POINTLESSQL_SCHEDULER_MAX_CONCURRENT_RUNS` (default 4)
  allocated on `Scheduler.start()`; per-job semaphores are
  lazy, keyed by `job_id`, sized from
  `Job.max_parallel_runs` (default 1). Global acquired
  before per-job (consistent lock order). DB `running`-count
  query stays as the authoritative `skipped` writer so
  process restarts don't lose state
- `logging_config.py`: new `job_run_id_var` and `task_id_var`
  alongside Sprint 16's `request_id_var`. `JSONFormatter`,
  `RequestIdFilter`, and the `LogRecord` factory carry all
  three. Scheduler sets them per-task and resets in
  `finally`. Sprint 19's `request_id_var = f"job-{job_run_id}"`
  is kept for continuity
- `log_job(job_run_id, task_id, level, message)` writes every
  status transition and retry to `job_logs`, synchronously
  relative to the task call
- `POST /api/jobs` accepts a DAG create form: `tasks` array
  with `{name, kind, config, depends_on, max_retries}`;
  validates cycles/unknown deps before insert
- New routes: `GET /api/jobs/{id}/tasks`,
  `GET /api/jobs/{id}/runs/{run_id}/tasks`,
  `GET /api/jobs/{id}/runs/{run_id}/logs?task_id=...`
- UI: "New DAG job" modal on `jobs.html` (JSON textarea — no
  builder yet). Per-task table on `job_detail.html` with
  status, retry count, last error; expandable Alpine log
  panel fetches lines on demand
- Settings: `POINTLESSQL_SCHEDULER_MAX_CONCURRENT_RUNS`
  (default `4`)
- `tests/test_scheduler_dag.py` — 13 new tests (topology,
  fail-skip, retry success, retry exhaustion, cycle
  detection, self-loop, unknown dep, per-job cap, global
  semaphore serialization, contextvars set/reset via
  caplog, `log_job` writer, route-level cycle 422). Sprint
  19's 23 scheduler tests and Sprint 16's 8 logging tests
  still green. Full suite not run in this sprint

### Added (Sprint 19)

- Alembic migration 005: `jobs` (name unique, cron_expr,
  run_as_user_id FK, kind, config JSON, is_paused, timestamps),
  `job_runs` with `(job_id, started_at DESC)` index, plus
  `job_tasks` and `job_logs` pre-created for Sprint 20
- `pointlessql/services/scheduler.py` — in-process asyncio
  scheduler started from `_lifespan`; `croniter`-driven due
  detection; per-tick running-run query prevents overlap;
  paused jobs skipped; failed `run_as_user_id` resolution
  surfaces as a `failed` run with a clear error
- Kind registry: `pg_sync` wraps Sprint 18 `run_sync` with
  `config["catalog_name"]`; `python` resolves an entry point
  from the `pointlessql.jobs` group (tests register a fake)
- Run-as-user builds `UnityCatalogClient.for_principal(user.email)`
  so soyuz's X-Principal applies automatically — reuses Sprint 7
- Scheduler sets `request_id_var` to `f"job-{job_run_id}"`
  inside each per-run span so structured logs correlate
  without a new contextvar (Sprint 20 adds
  `job_run_id_var` + `task_id_var`)
- Settings: `POINTLESSQL_SCHEDULER_ENABLED` (default `True`)
  and `POINTLESSQL_SCHEDULER_TICK_SECONDS` (default `30`)
- Routes: `GET /jobs` (list, ownership-filtered for non-admin),
  `GET /jobs/{id}`, `POST /api/jobs` (admin-only),
  `POST /api/jobs/{id}/run`, `POST /api/jobs/{id}/pause`,
  `POST /api/jobs/{id}/unpause` — all audited
- `frontend/templates/pages/jobs.html`,
  `frontend/templates/pages/job_detail.html` with "Run now" /
  "Pause/Resume" buttons visible to admin or the owner
- Navbar "Jobs" entry between "Notebook" and existing
  dropdowns
- `tests/test_scheduler.py` covering tick logic with a
  patched clock, state transitions, overlap prevention,
  paused skip, run-as-user principal forwarding, `pg_sync`
  end-to-end, route admin-gating and ownership filter

New dep: `croniter`.

### Changed (Sprint 19)

- `tests/conftest.py` sets
  `POINTLESSQL_SCHEDULER_ENABLED=false` before app import
  so the loop never ticks in ordinary test runs; the
  scheduler suite re-enables it per-test via monkeypatch
- `.gitignore`: `*.db-shm`, `*.db-wal` (SQLite WAL
  artifacts now produced by the scheduler's DB writes)

### Added (Sprint 18)

- `pointlessql/services/pg_sync.py`: pure-function Postgres → UC sync
  worker. `PG_TO_UC_TYPE` map, `map_pg_type_to_uc` with DECIMAL
  precision passthrough and STRING fallback on unknown types,
  `diff_snapshots(pg, uc_tables) -> SyncDiff` (schemas/tables/
  columns added/changed/dropped), `apply_diff` driving the facade,
  `PostgresIntrospector` protocol + `PsycopgIntrospector` default
  backed by `information_schema.columns` via `psycopg.sql.SQL`,
  `run_sync` glue that persists a `SyncRun` row per execution
- `unitycatalog.py` facade: `create_schema`, `create_table`,
  `delete_table` for driving the sync — all wrapped in
  `_wrap_catalog_errors`
- `POST /api/catalogs/{name}/sync` (admin-only, audited) resolves
  the catalog's bound Connection + optional Credential, builds a
  libpq DSN, runs the sync, and returns the `SyncRun` snapshot
- Alembic migration 004: `sync_run` table (`catalog_name`,
  `started_at`, `finished_at`, `status`, `added_count`,
  `changed_count`, `dropped_count`, `error`) with
  `(catalog_name, started_at DESC)` index
- `SyncRun` ORM model
- `components/sync_history_card.html`: last-20 sync runs + admin
  "Sync now" button on the foreign-catalog detail page
- Secret handling: connection options with keys matching
  `(?i)pass|secret|key|token` are overridden from a bound
  Credential's `additional_properties` (see `_effective_options`);
  missing Credential falls back to `options`
- 46 new tests (309 total) covering type mapping (16 parametrized),
  diff logic, secret merging, DSN builder, `apply_diff` with mock
  UC, `run_sync` end-to-end with stub introspector, the
  admin-only sync route, audit log emission, the history card
  render, and an `@pytest.mark.integration` test against a
  real Postgres container (documented, skipped by default)

### Added (Sprint 17)

- `unitycatalog.py` facade: `create_catalog(data)` and
  `delete_catalog(name, force)` wrapping the generated client's
  `_create_catalog` / `_delete_catalog`; both go through
  `_wrap_catalog_errors` so transport failures surface as
  `CatalogUnavailableError`
- `POST /api/catalogs` route (admin-only, audited) accepting the
  full `CreateCatalogRequest` shape — `name`, optional `comment`,
  `properties`, `type=FOREIGN`, `connection_name`, and free-form
  `options` passthrough — for wiring up foreign catalogs
- "Create foreign catalog" button + modal on the catalogs page
  (`pages/catalogs.html`): admin-only, pre-populated connection
  dropdown, key/value options row editor, posts through a new
  `createForeignCatalogForm(...)` Alpine factory in `federation.js`
- `components/foreign_catalog_card.html`: bound-connection link +
  inline options editor on the catalog detail page, rendered when
  `catalog.connection_name` is set
- FOREIGN badge on the catalog detail heading
  (`pages/schemas.html`) and in the sidebar tree
  (`components/sidebar.html`, `bi-plug` icon) so foreign catalogs
  are visually distinct from managed ones
- `optionsEditor(...)` in `properties_editor.js` — PATCHes
  `{ options: {...} }` to the catalog; shares a new
  `_makeDictEditor(field, ...)` helper with the existing
  `propertiesEditor`
- `tests/test_foreign_catalog.py` — 8 tests covering POST happy
  path + non-admin 403, PATCH options forwards dict verbatim,
  foreign-card/FOREIGN-badge/connection-link rendering, modal
  visibility for admin vs non-admin users
- `tests/test_federation.py`: new `TestCatalogsCreate` (4 tests)
  exercising the facade's managed + foreign-catalog create and
  delete paths (263 total pass)

### Changed (Sprint 17)

- `properties_editor.js`: `propertiesEditor` refactored to a
  shared `_makeDictEditor` helper; behavior preserved (the
  "cannot clear all properties at once" quirk stays scoped to
  `field === 'properties'`)
- `/` home handler fetches connections for the create modal only
  when the current user is admin (empty list otherwise, no
  `list_connections` call)

### Added (Sprint 16)

- `pointlessql/logging_config.py` — centralized logging: a
  `request_id_var` contextvar, `RequestIdFilter`, opt-in
  `JSONFormatter`, idempotent `configure_logging(level, fmt)`.
  Also installs a `logging.setLogRecordFactory` so every record
  is stamped with the current `request_id` (works with pytest's
  `caplog` without per-handler hookup)
- Settings: `log_level` (default `"INFO"`) and `log_format`
  (`"text"` | `"json"`, default `"text"`); env overrides
  `POINTLESSQL_LOG_LEVEL`, `POINTLESSQL_LOG_FORMAT`
- Module-level loggers in `api/main.py`, `api/error_handlers.py`,
  and `services/unitycatalog.py`
- Startup log line from `_lifespan` (host, port, engine,
  log_format)
- `error_handlers.py` warns on every handled `PointlessSQLError`
  except `AuthorizationError` (authz denials are expected
  traffic, not anomalies)
- `services/unitycatalog.py` `_wrap_catalog_errors` logs the
  original transport exception before re-raising as
  `CatalogUnavailableError` — fixes prior silent-swallow
- `tests/test_logging_config.py` — 8 new tests covering
  formatter, filter, idempotency, and end-to-end request-ID
  propagation through a captured warning log (251 total pass)

### Changed (Sprint 16)

- `request_id_middleware` sets the `request_id_var` contextvar
  (in addition to `request.state.request_id`) and resets it in
  `finally`, so every log record emitted during the request
  carries the ID — service-layer code no longer has to receive
  the `Request` object to log it
- `api/main.py` calls `configure_logging(...)` at module import
  time so uvicorn `--reload` workers and direct `uvicorn` invocations
  both pick up the configured format; idempotent, coexists with
  pytest's `caplog`

### Changed (Sprint 15)

- `[tool.pydoclint]` configuration in `pyproject.toml`: Google
  style, types in signatures only, `__init__` docs merged into
  class docstrings
- Ruff `D107` ignored — pydoclint owns `__init__` docstring
  policy via `allow-init-docstring = false`
- Merged `__init__` docstrings into class docstrings for `PQL`,
  `DuckDBEngine`, `UnityCatalogClient` (DOC301)
- Restructured exception docstrings: constructor params in Args,
  class-level annotations in Attributes (DOC602/603/101/103)
- Accurate Raises sections in `PQL.table`, `PQL.write_table`,
  `find_or_create_oidc_user` (DOC501/503)
- pydoclint: 0 violations across all 27 source files

### Added (Sprint 14)

- `pointlessql/api/error_handlers.py` — centralized FastAPI
  exception handler for `PointlessSQLError` family; dispatches
  JSON error envelope for `/api/...` routes and 403.html for
  HTML authorization errors
- Consistent JSON error envelope on all API error responses:
  `{"error": {"code": "...", "message": "...", "request_id": "..."}}`
- Request-ID middleware: generates UUID4 per request (or
  forwards client `X-Request-ID`), attaches to error envelope
  and `X-Request-ID` response header
- `tests/test_error_handlers.py` — 13 new tests covering JSON
  envelope for each exception type, HTML 403 rendering,
  request-ID generation and forwarding, admin enforcement via
  centralized handler (243 total pass)

### Changed (Sprint 14)

- UC facade (`unitycatalog.py`): all public async methods
  wrapped with `_wrap_catalog_errors` decorator converting
  `httpx.HTTPError` / `UnexpectedStatus` →
  `CatalogUnavailableError` at the source — routes never see
  raw transport exceptions
- `_require_admin` raises `AuthorizationError` instead of
  returning a `JSONResponse`; `_deny_json`, `_deny_html`, and
  `_require_admin_html` removed
- ~40 duplicated try/except blocks removed from `main.py`
  (1164 → 815 lines); JSON API routes are now simple
  pass-through calls with exceptions propagating to the
  centralized handler
- HTML graceful-degradation routes (catalog/schema/table
  detail, federation pages) catch `CatalogUnavailableError`
  (domain exception) instead of raw `httpx.HTTPError`
- `httpx` and `UnexpectedStatus` no longer imported in
  `main.py`

### Added (Sprint 13)

- `pointlessql/exceptions.py` — domain exception hierarchy with
  `PointlessSQLError` base carrying `.status_code`, `.error_code`,
  `.detail`; six concrete types: `CatalogUnavailableError` (502),
  `CatalogNotFoundError` (404), `AuthenticationError` (401),
  `AuthorizationError` (403), `EngineError` (500),
  `ValidationError` (422, also inherits `ValueError`)
- `pointlessql/types.py` — `UserInfo` TypedDict replacing
  `dict[str, Any]` for authenticated user objects
- `tests/test_exceptions.py` — 17 new tests covering hierarchy,
  attributes, catchability, and backward compatibility
  (230 total pass)

### Changed (Sprint 13)

- Pyright: `typeCheckingMode` upgraded from `"standard"` to
  `"strict"` on source code; zero errors, 32 warnings (from
  incomplete third-party stubs)
- `AccessDenied` reparented as an alias for `AuthorizationError`
  in `services/authorization.py` (backward compatible)
- `OIDCError` reparented under `PointlessSQLError`
- PQL raises `CatalogUnavailableError` instead of `ConnectionError`,
  `CatalogNotFoundError` instead of `LookupError`,
  `ValidationError` instead of `ValueError`
- `make_engine()` raises `ValidationError` instead of `ValueError`
- `parse_full_name()` raises `ValidationError` instead of
  `ValueError`
- Broad exception catches narrowed: `except Exception` in
  `auth.py` → `except (ValueError, TypeError, PwdlibError)`,
  `except (JSONDecodeError, Exception)` in `oidc.py` →
  `except (JSONDecodeError, ValueError, UnicodeDecodeError)`
- `_STATE_COOKIE_NAME` in `oidc.py` renamed to `STATE_COOKIE_NAME`
  (was flagged by strict pyright as cross-module private access)
- `_get_user()` in `api/main.py` returns `UserInfo` instead of
  `dict[str, Any]`; `auth_middleware` and
  `_template_response_with_user` have explicit return type
  annotations

### Added (Sprint 12)

- `PolarsEngine` in `pointlessql/pql/engine.py` — reads Delta tables
  via PyArrow → `pl.from_arrow()`, returns `pl.DataFrame`; writes via
  `frame.to_arrow()` → `deltalake.write_deltalake()`
- `_POLARS_TYPE_MAP` + `_polars_type_to_uc()` for Polars dtype → UC
  type mapping
- `PolarsEngine` registered in engine factory and exported from
  `pql/__init__.py`
- Settings: `POINTLESSQL_ENGINE` now also accepts `"polars"`
- `POINTLESSQL_ENGINE` env var forwarded in `docker-compose.yml`
  (defaults to `"pandas"`)
- New dependency: `polars>=1.0`
- Engine compliance suite parameterized across all three engines;
  `TestPolarsEngineSpecific` with 3 Polars-specific tests; 2 new
  PQL constructor tests (9 new tests, 213 total pass)

### Added (Sprint 11)

- `pointlessql/pql/engine.py` — `Engine` protocol with `read()`,
  `write()`, and `columns_info()` methods; `PandasEngine` (default,
  preserving backward compatibility) and `DuckDBEngine` (reads Delta
  via PyArrow → DuckDB, returns `DuckDBPyRelation`)
- `make_engine()` factory to instantiate engines by name
- `columns_from_tuples()` in `_columns.py` — engine-agnostic column
  metadata builder for UC table registration
- Settings: `POINTLESSQL_ENGINE` (default `"pandas"`, also accepts
  `"duckdb"`) for engine selection via environment variable
- `PQL.__init__()` accepts `engine=` kwarg (string name or `Engine`
  instance); auto-selects from settings when omitted
- New dependencies: `duckdb>=1.0`, `pyarrow>=17.0`
- `tests/test_engine.py` — 20 new tests: parameterized engine
  protocol compliance suite (read, write, round-trip, column
  metadata) plus engine-specific tests for Pandas and DuckDB

### Changed (Sprint 11)

- `PQL.table()` and `PQL.write_table()` delegate all data I/O to
  the active engine instead of calling `deltalake` directly
- `PQL.__init__()` resolves `Settings` once and reuses it for both
  client creation and engine selection
- `columns_from_dataframe()` refactored to delegate to
  `columns_from_tuples()` internally (no behavior change)
- `pql/__init__.py` exports `Engine`, `PandasEngine`, `DuckDBEngine`,
  and `make_engine`

### Added (Sprint 10)

- `docker-compose.postgres.yml` — compose override that adds a
  Postgres service as PointlesSQL's metadata DB; usage:
  `docker compose -f docker-compose.yml -f docker-compose.postgres.yml up`
- `.env.example` — documents all `POINTLESSQL_*` env vars with
  defaults and descriptions
- Settings: `POINTLESSQL_BASE_URL` for OIDC callback URIs behind
  reverse proxies or inside Docker (falls back to request-derived
  URI when unset)
- `psycopg[binary]>=3.1` promoted from dev to main dependencies
  so Postgres URLs work at runtime
- Test fixture: `TEST_DATABASE_URL` env var to run the test suite
  against Postgres (or any SQLAlchemy-supported backend)

### Changed (Sprint 10)

- OIDC redirect_uri construction uses `POINTLESSQL_BASE_URL` when
  set, fixing SSO flows behind reverse proxies and in Docker
- Test `_auth_db` fixture drops all tables on teardown for clean
  isolation on persistent backends (Postgres)

### Added (Sprint 9)

- `Dockerfile` — 3-stage multi-stage build (soyuz-client-builder →
  builder → runtime) using `python:3.14-slim` and `uv pip install`
- `Dockerfile.soyuz` — 2-stage build for soyuz-catalog
- `docker-compose.yml` — full-stack orchestration with health checks,
  shared `./warehouse` volume for Delta storage, `depends_on` with
  `service_healthy` condition, configurable host ports via env vars
- `.dockerignore` for clean Docker builds
- Settings: `POINTLESSQL_HOST` (default `127.0.0.1`) and
  `POINTLESSQL_PORT` (default `8000`) for configurable bind address
- Frontend path fallback: installed wheel resolves
  `pointlessql/_frontend` when dev `frontend/` directory is absent
- README: Docker quick-start section with `docker compose up --build`

### Changed (Sprint 9)

- `cli()` reads host and port from `Settings` instead of hardcoding
- Jupyter subprocess uses `--allow-root` and binds to `settings.host`
  for Docker compatibility

### Added (Sprint 8)

- OIDC / OAuth2 authorization-code flow with PKCE — opt-in via
  `POINTLESSQL_OIDC_DISCOVERY_URL` and `POINTLESSQL_OIDC_CLIENT_ID`
  env vars; supports both public and confidential clients
- `pointlessql/services/oidc.py` — PKCE generation, HMAC-signed
  state cookie, discovery document caching, token exchange, userinfo
  fetch, find-or-create user provisioning with same-email linking
- `GET /auth/sso` route initiates the OIDC flow; `GET /auth/callback`
  handles the provider redirect and auto-provisions local users
- Login page shows conditional "Sign in with SSO" button alongside
  the existing email/password form
- Alembic migration 003: `password_hash` nullable for OIDC-only
  users, `oidc_provider` + `oidc_subject` columns with partial
  unique index
- `tests/test_oidc.py` — 33 new tests (177 total pass)

### Changed (Sprint 8)

- `User.password_hash` is now nullable to support OIDC-only accounts
- `auth.login()` handles `password_hash=None` gracefully (OIDC-only
  users cannot log in via email/password, preserving constant-time
  comparison)

### Added (Sprint 7)

- Authorization enforcement layer: PointlesSQL now checks effective
  permissions from soyuz-catalog before each operation. Non-admin
  users need `USE CATALOG`, `USE SCHEMA`, `SELECT`, `MODIFY`, or
  `MANAGE_GRANTS` depending on the operation
- Per-request `X-Principal` header forwarding: every soyuz-catalog
  HTTP call includes the authenticated user's email as the
  `X-Principal` header (via per-request client factory)
- Admin bypass: users with `is_admin=True` skip all permission checks
- Federation routes (connections, external locations, credentials)
  restricted to admin users only
- 403 Forbidden error page with privilege details and "contact an
  administrator" hint (`pages/403.html`)
- Audit log: `audit_log` table (Alembic migration 002) records
  who-did-what for all write operations — updates, tag changes,
  permission grants/revokes, federation CRUD
- `pointlessql/services/authorization.py` — `check_privilege`,
  `check_privilege_from_effective`, `has_privilege`, `AccessDenied`
- `pointlessql/services/audit.py` — `log_action` for append-only
  audit entries
- Permissions UI enhancements: current user's row highlighted with
  "you" badge in both Assigned and Effective tabs; grant/revoke
  controls hidden when user lacks `MANAGE_GRANTS`
- Non-admin test user fixture (`non_admin_cookies`) in conftest
- `tests/test_authorization.py` — 15 unit tests for authorization
  service (admin bypass, privilege matching, dict privilege format)
- `tests/test_enforcement.py` — 21 route-level enforcement tests
  (allowed/denied/admin bypass for catalogs, schemas, tables,
  updates, permissions, federation admin-only)
- `tests/test_audit.py` — 3 audit log service tests

### Changed (Sprint 7)

- All API routes use per-request `UnityCatalogClient` via
  `_get_uc_client(request)` instead of the shared singleton
- Detail pages enforce access using already-fetched effective
  permissions (no duplicate HTTP call)
- `permissions_card.html` and `permissions_editor.js` accept
  `canManage` and `currentUserEmail` parameters
- `test_api_errors.py` updated for per-request client pattern
  (monkeypatches `UnityCatalogClient.for_principal`)

### Added (Sprint 6)

- Alembic + SQLAlchemy 2.0 for PointlesSQL's own metadata DB
- Local user registration and login with bcrypt password hashing
- JWT cookie-based auth (`pql_session`, HttpOnly, HS256)
- Login and register pages
- Auth middleware protecting all routes
- First-user admin bootstrap
- Navbar shows current user and logout button

### Added (Sprint 5)

- Tags editor card on catalog, schema, and table detail pages — add
  and remove tags via PATCH to soyuz-catalog's tags endpoint, with
  Alpine.js interactive component (`tags_editor.html`, `tags_editor.js`)
- Permissions card with two Bootstrap nav-tabs (Assigned / Effective)
  on all detail pages — grant privileges via principal + privilege
  selector, revoke by clicking badge; effective permissions loaded
  on-demand (`permissions_card.html`, `permissions_editor.js`)
- Lineage card on table detail page showing upstream and downstream
  dependencies as depth-indented node lists with clickable links to
  related tables (`lineage_card.html`)
- Lakehouse Federation: full CRUD pages for connections, external
  locations, and credentials — list pages with create modals, detail
  pages with inline comment editing and delete-with-confirmation
  (`connections.html`, `connection.html`, `external_locations.html`,
  `external_location.html`, `credentials.html`, `credential.html`,
  `federation.js`)
- Federation dropdown in navbar (Connections, External Locations,
  Credentials)
- 21 new async facade methods in `unitycatalog.py` (tags, permissions,
  effective permissions, lineage, connections CRUD, external locations
  CRUD, credentials CRUD)
- 25 new JSON API routes + 6 HTML page routes in `main.py`
- `tests/test_tags_permissions.py` — unit tests for tags, permissions,
  effective permissions, and lineage facade methods
- `tests/test_federation.py` — unit tests for connections, external
  locations, and credentials facade CRUD
- Extended `tests/test_api_errors.py` with 11 new error-handling tests
  for all new JSON API endpoints

### Changed (Sprint 5)

- Detail page route handlers (`catalog_detail`, `schema_detail`,
  `table_detail`) now fetch tags, permissions, and effective permissions
  in parallel via `asyncio.gather`; `table_detail` additionally fetches
  lineage. Failure in any single fetch does not break the page
- `base.html` loads three new JS files: `tags_editor.js`,
  `permissions_editor.js`, `federation.js`

### Added (Sprint 4)

- E2E smoke test (`tests/test_e2e.py`): full roundtrip — create
  catalog/schema, write table via PQL, verify in web UI with correct
  columns and PQL snippet card
- `tests/conftest.py` with shared integration fixtures (`soyuz_client`,
  `e2e_env`)
- `tests/test_api_errors.py` — unit tests for API error handling
  (all JSON endpoints return 502 when soyuz-catalog is unreachable)
- PQL snippet card with copy-to-clipboard button on table detail page
- Jupyter loading spinner on notebook page: polls `/api/jupyter/status`
  until ready, shows error state with retry button after 30 s timeout

### Changed (Sprint 4)

- API JSON endpoints (`/api/tree`, `/api/catalogs`, `/api/schemas`,
  `/api/tables`, PATCH endpoints) return HTTP 502 with JSON error body
  when soyuz-catalog is unreachable (previously returned 500)
- `PQL.table()` and `PQL.write_table()` raise `ConnectionError` with
  a user-friendly message when soyuz-catalog is unreachable (previously
  raised raw `httpx.ConnectError`)
- Notebook page uses Alpine.js polling to wait for Jupyter readiness
  before loading the iframe; shows "Jupyter Not Available" error state
  if startup fails
- README.md rewritten with MVP setup docs, quick start, PQL usage
  examples, configuration table
- CLAUDE.md updated with Phase 1 completion, PQL/Jupyter/Alpine.js
  in stack, expanded layout section

### Previously added (Sprint 3)

- `pointlessql/services/jupyter.py` — async context manager that
  starts JupyterLab as a managed subprocess (SIGTERM/SIGKILL
  lifecycle, health-check polling, configurable port)
- `GET /notebook` route with embedded JupyterLab iframe; sidebar
  remains visible alongside the notebook for catalog browsing
- `GET /api/jupyter/status` JSON endpoint for subprocess status
- "Notebook" tab in the navbar (`base.html`)
- `{% block content_class %}` in `base.html` for per-page layout
  overrides (used by notebook page to remove content padding)
- Settings: `jupyter_enabled: bool = True`,
  `jupyter_port: int = 8888` (env overrides:
  `POINTLESSQL_JUPYTER_ENABLED`, `POINTLESSQL_JUPYTER_PORT`)
- `notebooks/getting_started.ipynb` — starter notebook demonstrating
  `PQL` read/write/list workflows
- New dependency: `jupyterlab>=4.0`
- `tests/test_jupyter.py` — 11 unit tests covering subprocess
  manager, route handlers, status API, and settings defaults

### Previously added (Sprint 2)

- `pointlessql/pql/` package — sync bridge between UC metadata and
  Delta Lake DataFrames, designed for notebooks and scripts
- `PQL` class with `table()` (read Delta as DataFrame),
  `write_table()` (write DataFrame + register metadata), and
  `list_catalogs()` / `list_schemas()` / `list_tables()` convenience
  methods
- New dependencies: `deltalake>=0.24`, `pandas>=2.2`
- `tests/test_pql.py` — unit tests with mocked soyuz client
- `tests/test_pql_integration.py` — integration round-trip test
  (create → write → read → verify)
- `PQL` re-exported from `pointlessql` package root

### Previously added (Sprint 1)

- `pointlessql/settings.py` — pydantic-settings module with
  `soyuz_catalog_url` setting (env override: `POINTLESSQL_SOYUZ_CATALOG_URL`)
- `pointlessql/services/soyuz_client.py` — factory for a configured
  `soyuz_catalog_client.Client` instance
- `tests/test_soyuz_client.py` — integration smoke tests against a
  live soyuz-catalog server (`@pytest.mark.integration`)
- `soyuz-catalog-client` as editable path dependency

### Changed

- `pointlessql/services/unitycatalog.py` — rewritten to delegate to
  the generated soyuz-catalog client instead of hand-rolled httpx
  calls. All methods convert attrs response objects to plain dicts
  via `.to_dict()` so templates stay unchanged
- `pointlessql/api/main.py` — lifespan uses `make_soyuz_client()`
  factory; error handling catches `UnexpectedStatus` alongside
  `httpx.HTTPError`

### Fixed

- Fixed code-gen bug in soyuz-catalog-client: `list_tables`
  `_parse_response` now handles the 200 status and returns
  `ListTablesResponse` instead of treating success as an unexpected
  status
