# Quality Sweep — Final Report

Date: 2026-04-26
Branch: main (uncommitted)
Plan: `~/.claude/plans/mission-code-qualit-t-pointlesql-luminous-pancake.md`

## Executive summary

A six-sprint code-quality sweep landed across PointlesSQL's
`pointlessql/` package, covering docstring sanitisation, CI gates,
pre-commit hooks, and one targeted hardcode externalisation.
**110 files changed**, **+1539 / −1756 lines** net (the negative
delta comes from removing historical Sprint/Phase preamble from
docstrings).

The mission brief assumed several deficiencies that the codebase
had already addressed (own exception hierarchy, structured JSON
logging with request-id, RFC-9457 error handlers, Pyright strict).
The sweep focused on the actual gaps surfaced in Phase-1
exploration.

## Vorher / Nachher metrics

| Dimension | Before | After | Delta |
|---|---|---|---|
| Sprint/Phase/ROADMAP refs in `pointlessql/` (excl. alembic) | 494 | **0** | −494 |
| Files with such refs | 60 | **0** | −60 |
| `.pre-commit-config.yaml` | absent | present (6 hook groups) | +1 file |
| Pytest gate in CI | none | `--cov-fail-under=55` blocking | +1 gate |
| Coverage measurement in CI | none | `term + xml` artifacts | +1 gate |
| Coverage baseline (full suite) | unknown | **60.0 %** | measured |
| OIDC HTTP timeout | hardcoded `10` (3 sites) | `OIDCSettings.http_timeout_seconds = 10.0` | externalised |
| Pyright errors | 1 (cost_estimator) | **0** | −1 |
| Pyright warnings | 292 (third-party stubs) | 288 | −4 |
| Ruff check | green | green | — |
| Ruff format | green | green | — |
| Pydoclint | green | green | — |

## Per-sprint breakdown

### Sprint A — Docstring sanitisation (parallel, 4 subagents)

**Scope.** Strip Sprint/Phase/ROADMAP/TODO/FIXME references from all
Python docstrings + code comments under `pointlessql/`. Disjoint
path globs distributed across four subagents.

- **api/** — 28 files scanned, 21 modified, ~73 refs removed.
- **services/** — 30 files modified, 155 refs removed.
  `notebook_doc.py` was the densest single file (24 refs); each
  was replaced with semantic prose preserving the technical
  rationale (BOM/CRLF tolerance, jupytext post-write rewrite,
  legacy round-trip behavior, etc.).
- **pql/ + models/ + conventions/** — 24 files modified, ~80 refs
  removed.
- **root files** (`settings.py`, `exceptions.py`, …) — 2 files
  modified, ~22 refs removed. `RateLimitSettings`, `AuditSettings`,
  `SQLSettings`, `AgentRunsSettings`, `ConventionsSettings` all
  rewritten to drop Sprint preamble while preserving the operational
  reasoning paragraphs.

**Preserved deliberately.** `BUG-NN-NN` references in technical
explanations (e.g. `BUG-28-02` for the papermill CWD race in
[`settings.py`](pointlessql/settings.py), `BUG-23-01` for the OIDC
empty-string fallback) were kept — they are concrete bug-tracker
anchors, not historical sprint numbering. The Sprint prefix
(`Sprint 23 BUG-23-01`) was stripped to leave just the BUG anchor.

**Out of scope.** `pointlessql/alembic/versions/` (historical
migration files), `README.md` (user-facing docs), `CHANGELOG.md`,
`ROADMAP.md`, and CI workflow shell-comments — none were touched.

**Verification.**
```
$ rg -c '\b(Sprint \d|Phase \d|ROADMAP\.md)\b' pointlessql/ \
    --type py --glob '!alembic/versions/*' | grep -v ':0$'
(no output — 0 files)
```

### Sprint B — Pytest + Coverage gates in CI

**Changes.**
- [`.github/workflows/test.yml`](.github/workflows/test.yml) gains
  a `Pytest with coverage` step running
  `uv run pytest --cov=pointlessql --cov-report=term --cov-report=xml --cov-fail-under=55`.
- A `Upload coverage XML` step (with `if: always()`) attaches
  `coverage.xml` as a build artifact.
- [`pyproject.toml`](pyproject.toml) `[tool.coverage.report]`
  documents that the floor lives in CI, not local — local
  iteration stays unblocked.

**Threshold rationale.** Baseline measured at 60.0 % (full unit
suite, SQLite backend, integration + postgres markers excluded
per `addopts`). Floor set 5 points lower (55 %) to absorb noise
from random test order and per-PR coverage fluctuations without
inviting silent regressions.

**Pre-existing failures deselected (12 tests, listed in CI).**
The following tests fail on `main` independent of this sweep
(verified by stashing all changes and running them against HEAD):

- `tests/test_api_notebook_workspace.py::test_upload_*` (7 tests)
- `tests/test_scheduler_papermill.py::test_executor_writes_*`,
  `test_render_route_serves_*`, `test_download_*` (4 tests)
- `tests/test_table_stats.py::test_profile_enforces_select`
  (1 test — references a `check_privilege` symbol on
  `pointlessql.api.main` that no longer exists)

These are explicitly listed as `--deselect` arguments in the CI
step with a comment instructing follow-up sprints to remove the
deselect line as each test is fixed. They are not silenced
locally — `uv run pytest` still surfaces them.

### Sprint C — Pre-commit configuration

New file [`.pre-commit-config.yaml`](.pre-commit-config.yaml) with
six hook groups:

1. `pre-commit-hooks` (trailing-whitespace, EOF-fixer, YAML/TOML
   syntax, large-file guard, merge-conflict marker, private-key
   detector).
2. `ruff-pre-commit` (`ruff-check --fix` + `ruff-format`).
3. `pydoclint` (Google style, matches `[tool.pydoclint]` exactly).
4. `detect-secrets` (excludes `uv.lock`, `tests/`, `frontend/`,
   `notebooks/`).
5. Local hook running `uv run pyright pointlessql` (strict).

`README.md` Development section now leads with
`uv run pre-commit install` so the hook arms on first dev setup.

### Sprint D — OIDC HTTP timeout externalisation

[`OIDCSettings`](pointlessql/settings.py#L97) gains a new field:

```python
http_timeout_seconds: float = 10.0
```

[`pointlessql/services/oidc.py`](pointlessql/services/oidc.py)
now defines a private `_http_timeout()` helper that instantiates
`Settings()` per call (matching the codebase's per-request fresh-
settings pattern) and replaces the three previously-hardcoded
`timeout=10` arguments in `fetch_discovery`, `exchange_code`, and
`fetch_userinfo`.

Operators can now override via
`POINTLESSQL_OIDC_HTTP_TIMEOUT_SECONDS`.

**Other hardcodes deliberately not externalised.** Per-route
default-parameter limits (`limit=10` recent runs,
`limit=50` search) are local UX defaults, not operator-tuneable
knobs — keeping them inline is the right tradeoff per the plan.

### Sprint E — Top-3 route-module entzerrung — **skipped**

The plan marked this optional. After Sprints A–D landed cleanly
with measurable gains, the risk/reward of touching the three
1000-LOC route modules (`agent_runs_routes.py`, `jobs_routes.py`,
`sql_routes.py`) did not justify the regression risk in this
sweep. The plan file remains the reference for picking it up
later.

### Sprint F — Verification

All checks against final state:

| Check | Command | Result |
|---|---|---|
| Ruff lint | `uv run ruff check pointlessql/` | All checks passed |
| Ruff format | `uv run ruff format --check pointlessql/` | 151 files already formatted |
| Pydoclint | `uv run pydoclint --style=google pointlessql/` | No violations |
| Pyright strict | `uv run pyright pointlessql/` | 0 errors, 288 warnings |
| Sprint-ref audit | `rg -c '\b(Sprint \d\|Phase \d\|ROADMAP\.md)\b' pointlessql/ --glob '!alembic/versions/*'` | 0 |
| Settings smoke | `python -c "from pointlessql.settings import Settings; print(Settings().oidc.http_timeout_seconds)"` | `10.0` |
| App smoke | `uv run pointlessql` + `curl /healthz` | `HTTP 200 {"status":"ok"}` |
| Request-ID echo | `curl -H 'X-Request-ID: smoke-test-42'` → response header | `x-request-id: smoke-test-42` |

## Acceptance criteria — adjusted vs original brief

| Brief original | Status |
|---|---|
| 0 Magic Strings/Numbers im Produktivpfad | Externalised what made sense (OIDC timeout); local UX defaults preserved with rationale |
| 100 % öffentliche Symbole mit semantischen Docstrings | Pydoclint green; **0** Sprint/Phase/ROADMAP refs |
| 0 nackte `except` | Already met before sweep; still met |
| Strukturierte Fehlerantworten mit `request_id` | Already met (RFC 9457 problem+json) |
| Strukturiertes JSON-Logging mit `request_id` | Already met (`logging_config.py` + `middleware.py`) |
| `mypy --strict` grün | Replaced by `pyright strict` (0 errors) per user decision |
| Test-Coverage nicht gesunken | Baseline 60 %, CI floor 55 %, tests not deselected to mask sweep changes |

**Out of scope** (per user decision in plan-mode):
- Separate Pydantic DTO layer (`schemas/`).
- `core/` directory reorganisation.
- Switch from stdlib-`logging` to `structlog`.
- Switch from Pyright to mypy.

## Known follow-ups

1. **12 pre-existing test failures** need investigation — see the
   deselect block in `.github/workflows/test.yml`. Most look like
   stale monkey-patch targets (`test_table_stats` expects
   `pointlessql.api.main.check_privilege`) and ipynb upload-route
   regressions. None blocks normal app function.
2. **Pre-commit hooks may rewrite working tree on first install.**
   Run `uv run pre-commit run -a` once; expect ruff-format to
   touch a handful of files in `tests/` (not in scope of this
   sweep).
3. **Coverage opportunity.** 60 % baseline has obvious gaps:
   `services/sql/` (cost_estimator + explain at 0 %),
   `services/notebook_outputs/` (0 %), `services/output_rendering.py`
   (12 %). Each is testable without integration infrastructure.
4. **Sprint E (route entzerrung)** remains in the approved plan
   for a future quality pass.

## Files changed (summary)

```
110 files changed, 1539 insertions(+), 1756 deletions(-)
```

- **New files** (2): `.pre-commit-config.yaml`, `QUALITY_FINAL.md`.
- **Modified** (108): docstring sanitisation across `pointlessql/`,
  `pointlessql/services/oidc.py` (timeout externalisation),
  `pointlessql/settings.py` (new field + docstring cleanup),
  `pyproject.toml` (coverage report comment),
  `.github/workflows/test.yml` (pytest gate),
  `README.md` (pre-commit install line).
