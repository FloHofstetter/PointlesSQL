# Test suite

The pytest suite drives both lanes (SQLite default + the
Phase-30 Postgres dialect lane) and is the second-most-touched
asset in the repo after the production code.  Phase 31 closed
the structural slowness — a baseline run of 1461 tests went
from ~30 minutes (SQLite, single worker) to about a minute.

## Running the suite

```bash
# SQLite, single worker — the default workstation flow
uv run pytest -q

# SQLite + parallel workers (xdist)
uv run pytest -q -n auto

# Postgres lane (live PG must already be reachable)
TEST_DATABASE_URL=postgresql+psycopg://pointlessql:pointlessql@localhost:5432/pointlessql \
    uv run pytest -q

# Just one file with full tracebacks
uv run pytest -q tests/test_audit_fts.py --tb=short

# Top-N slowest tests — use this when wall-time creeps back up
uv run pytest -q --durations=20
```

The integration-marker tests (`@pytest.mark.integration`) and the
postgres-marker tests (`@pytest.mark.postgres`) are deselected by
default through `pyproject.toml`'s `addopts = "-m 'not integration'"`.
The PG-marker subset only runs when `TEST_DATABASE_URL` points at a
live PG; the integration subset only runs when a soyuz-catalog
server is reachable.

## Bench script

```bash
scripts/bench_test_suite.sh                   # SQLite, single worker
PYTEST_XDIST=auto scripts/bench_test_suite.sh # SQLite, parallel
BACKEND=postgres TEST_DATABASE_URL=… scripts/bench_test_suite.sh
```

Writes a timestamped `--durations=20` snapshot under `.bench/` plus
the wall-clock from `time`.  Useful for diff'ing the cost of a
fixture change.

## How the conftest stays fast (Phase 31)

`tests/conftest.py` does three load-bearing tricks; all three are
test-only and do not affect production behaviour:

1. **Bcrypt at rounds=4 (Phase 31.1).** The conftest rebinds
   `pointlessql.services.auth._hasher` to a `BcryptHasher(rounds=4)`
   at import time.  The algorithm, salt, and cookie format are
   unchanged — only the work factor.  Every test that calls
   `auth.register` / `auth.login` (or fixtures that wrap them)
   pays ~16 ms per hash instead of ~250 ms, which compounds to
   roughly 24 minutes of saved wall clock per single-worker run.

2. **Session-scope schema + per-test wipe (Phase 31.2).** The
   `_test_engine` session-scope fixture builds the engine and
   schema exactly once per worker.  The autouse `_auth_db`
   function-scope fixture runs at every test entry but only:

   - drops audit-FTS artefacts (vtable + triggers on SQLite,
     `audit_search_index` + functions on PG),
   - wipes rows (`TRUNCATE TABLE … RESTART IDENTITY CASCADE` on
     PG; `DELETE FROM …` in FK-reverse order on SQLite, plus a
     `DELETE FROM sqlite_sequence` reset),
   - re-inserts the seeded workspace + admin + non-admin users
     using a password hash cached at module import,
   - issues fresh JWT cookies via `auth.create_jwt` (no DB read,
     no bcrypt).

   This skips the previous flow of `Base.metadata.create_all` +
   `Base.metadata.drop_all` (≈90 DDL statements) per test, which
   was the single biggest cost on PG.

3. **Lifespan-fast env var (Phase 31.3).** `tests/conftest.py`
   sets `POINTLESSQL_TEST_LIFESPAN_FAST=1` before
   `pointlessql.api.main` is imported.  When that flag is set,
   the FastAPI lifespan skips `init_db` (which runs alembic
   upgrade head against the on-disk default URL), the audit /
   lineage / branch / external-writes background asyncio tasks,
   and the `bootstrap_from_env` API-key sync.  The conftest has
   already pre-wired everything those code paths normally
   provide.  Real production startup is untouched — the env var
   is only set inside the test process.

## Editing tests safely

- **Don't disable the autouse `_auth_db` fixture.**  Even pure
  unit tests (e.g. `test_auth.py`) rely on the seeded session
  factory landing on `app.state.session_factory`.  If a test
  needs an isolated DB, build its own engine via `tmp_path`
  inside the test (see `test_migrate_to_postgres.py`).
- **`app.state` mutations** (e.g.
  `app.state.uc_client = mock`) are safe; the per-test reseed in
  the next test re-establishes the `session_factory` baseline.
  Per the Phase-31.3 audit, no test today leaks state across
  fixtures, but adding a snapshot/restore fixture is the
  cheapest fix if a future test introduces a leak.
- **Tests that need real bcrypt rounds** (e.g. timing-attack
  proofs) should monkey-patch `auth._hasher` back to its
  production setting in their own fixture and restore on teardown.
- **Tests that need the full lifespan** (rare — alembic-upgrade
  verification, real soyuz-client roundtrip) should
  `monkeypatch.delenv("POINTLESSQL_TEST_LIFESPAN_FAST",
  raising=False)` and restore via the fixture's cleanup.

## CI lanes

Two GitHub Actions jobs:

- `test.yml::gate` — SQLite + xdist (`-n auto`), the lint /
  pyright / pydoclint / alembic gates, and coverage with
  `--cov-fail-under=55`.
- `test.yml::postgres` — single-worker (workers can't share a
  live PG database safely), runs the full suite against PG
  including the `@pytest.mark.postgres` subset that only this
  lane unblocks.

Both lanes use the same deselect list — the small set of tests
that were already failing when the gate was introduced.  When a
deselected test is fixed, delete its line so the gate fails
visibly if a previously-green test starts to break.
