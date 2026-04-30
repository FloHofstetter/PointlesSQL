# CLI reference

The `pointlessql` command exposes two surfaces: the dev-server
entry point (no arguments) and an `admin` group for
operational helpers.

```text
pointlessql            # start the dev server on POINTLESSQL_SERVER_HOST:PORT
pointlessql admin --help
```

The CLI is built with [Typer](https://typer.tiangolo.com/);
source lives in
[`pointlessql/api/main.py`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/main.py)
(`cli` Typer app, ~50 lines).  When the project is installed via
`uv sync` or `pip install pointlessql`, the
`[project.scripts] pointlessql = "pointlessql.api.main:cli"`
entry point makes the command available on `$PATH`.

## `pointlessql`

Starts the FastAPI dev server in `uvicorn --reload` mode with
the project source trees pinned as the reload watch dirs (so
notebook autosaves don't tear down the kernel + Pyright
WebSockets — see BUG-64-03 in the source comments).

```bash
$ pointlessql
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

Configurable via the `POINTLESSQL_SERVER_*` env vars (see
[Configuration](configuration.md#server)).

For production deploys, run uvicorn directly with `--workers N`
or front it with gunicorn:

```bash
uv run uvicorn pointlessql.api.main:app \
  --host 0.0.0.0 --port 8000 --workers 4
```

The `--reload` flag is dev-only.

## `pointlessql admin issue-auditor-key`

Mint a fresh API key with the `auditor` scope and (optionally)
the `supervisor` scope.  Prints the plaintext token exactly
once — copy it into the Hermes cron job's
`POINTLESSQL_API_KEY` env overlay immediately, because the
token is hashed before storage and cannot be recovered.

### Synopsis

```bash
pointlessql admin issue-auditor-key --name <name> [--supervisor]
```

### Options

| Flag | Required | Description |
|---|---|---|
| `--name TEXT` | yes | Unique key name, ≤ 64 chars.  Shown in the admin API-keys list and on every audit row that key produced. |
| `--supervisor` | no | Also grant the supervisor scope (per-run write privileges).  Without this flag the key is auditor-only. |

### Output

```text
$ pointlessql admin issue-auditor-key --name=daily-review
name        = daily-review
prefix      = pql_audit_xx
auditor     = True
supervisor  = False
created_at  = 2026-04-30T12:34:56+00:00

token (shown once — save it now):
pql_audit_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Key minted; token printed. |
| `2` | `ValueError` from the service (typically: name already exists). |

### Where the row lands

The key is INSERTed into the `api_keys` table (Alembic
migration `025_api_keys` on the squashed baseline).  The
plaintext token is salted-hashed before storage; only the
returned `secret_prefix` (first 12 chars of the token) is
queryable later.  See [Auth](../concepts/auth.md) for the
verification flow.

## What's *not* in the CLI

Things you might expect but won't find:

- **`pointlessql migrate`** — use `uv run alembic upgrade head`
  directly.  PointlesSQL runs Alembic on first-boot anyway.
- **`pointlessql seed`** — use
  `uv run python scripts/seed-e2e.py` directly.  See the
  [Quickstart](../getting-started/quickstart.md).
- **`pointlessql user create`** — humans register through the UI
  (`/auth/register`); first registration becomes admin.
- **`pointlessql backup`** — out of scope.  The own-DB is just
  SQLite or Postgres, back it up with the standard tools.
