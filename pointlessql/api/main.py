"""FastAPI entrypoint for PointlesSQL."""

from __future__ import annotations

import hmac
import logging
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import (
    JSONResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import pointlessql
from pointlessql.api._bootstrap._lifespan import make_lifespan
from pointlessql.api._template_context import install_template_wrapper
from pointlessql.api._template_filters import register_template_filters
from pointlessql.api.dependencies import (
    require_admin as _require_admin,
)
from pointlessql.api.middleware import register_middleware
from pointlessql.api.volumes_routes import (
    DELTA_PRIMITIVE_TO_UC as _DELTA_PRIMITIVE_TO_UC,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from pointlessql.api.volumes_routes import (
    delta_field_to_uc as _delta_field_to_uc,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from pointlessql.config import configure_logging, get_settings
from pointlessql.db import get_session_factory, init_db
from pointlessql.services import api_keys as api_keys_service
from pointlessql.services import metrics as metrics_service

# Configure logging at module import time so it takes effect in every
# process that serves traffic — the uvicorn --reload worker imports
# this module but does not go through cli(). Idempotent; subsequent
# calls replace our own handlers without disturbing pytest's caplog.
_startup_settings = get_settings()
configure_logging(
    _startup_settings.logging.level,
    _startup_settings.logging.format,
    third_party_levels=_startup_settings.logging.third_party_levels,
)

logger = logging.getLogger(__name__)

# In a dev checkout the frontend dir is at the repo root; in an
# installed wheel hatchling force-includes it as pointlessql/_frontend.
_dev_dir = Path(__file__).resolve().parents[2] / "frontend"
_FRONTEND_DIR = _dev_dir if _dev_dir.is_dir() else Path(__file__).resolve().parents[1] / "_frontend"
_TEMPLATES = Jinja2Templates(directory=str(_FRONTEND_DIR / "templates"))
register_template_filters(_TEMPLATES)
install_template_wrapper(_TEMPLATES)


app = FastAPI(
    title="PointlesSQL",
    version="0.1.0",
    lifespan=make_lifespan(_TEMPLATES),
)

from pointlessql.api._bootstrap._routers import register_routers  # noqa: E402
from pointlessql.api.error_handlers import register_error_handlers  # noqa: E402

register_error_handlers(app)
register_routers(app)

_STYLE_CSS_PATH = _FRONTEND_DIR / "css" / "style.css"


_CSS_DIR = _FRONTEND_DIR / "css"
_ASSET_VERSION_RE = re.compile(r'url\("(\./[^"]+)\?v=ASSET_VERSION"\)')


@app.get("/static/css/style.css", include_in_schema=False)
async def _style_css() -> Response:  # pyright: ignore[reportUnusedFunction]
    """Serve the master stylesheet with per-import mtime cache-busters.

    Browsers cache ``@import`` URLs independently of their referring
    sheet, so the parent's cache-bust does not propagate.  Earlier the
    token expanded to ``pointlessql.__version__``; that meant dev
    iteration required a version bump to invalidate sub-imports.

    Instead we stamp each ``@import url("./foo.css?v=ASSET_VERSION")``
    with the imported file's own mtime.  In dev, editing a sub-sheet
    bumps its mtime → browser refetches that one file.  In prod the
    wheel's install-time mtime is stable → identical caching as
    before.  Files that are missing fall back to ``__version__``.
    """
    body = _STYLE_CSS_PATH.read_text()

    def _stamp(match: re.Match[str]) -> str:
        rel = match.group(1)
        target = (_CSS_DIR / rel.removeprefix("./")).resolve()
        try:
            mtime = int(target.stat().st_mtime)
            stamp = f"{pointlessql.__version__}-{mtime}"
        except OSError:
            stamp = pointlessql.__version__
        return f'url("{rel}?v={stamp}")'

    body = _ASSET_VERSION_RE.sub(_stamp, body)
    return Response(body, media_type="text/css")


_JS_DIR = _FRONTEND_DIR / "js"
_JS_IMPORT_RE = re.compile(r"""(['"])(\.\.?\/[^'"\s]+\.js)\1""")


def _js_with_cache_bust(rel_path: str) -> Response | None:
    """Serve a JS file with relative ``import`` URLs cache-busted.

    Mirrors the CSS sub-import stamping at :func:`_style_css` — the
    browser caches ES module imports under their bare URL, so a bump
    of the entrypoint asset version invalidates only the entrypoint,
    not its transitively-imported siblings.  We rewrite every
    ``from "./foo.js"`` / ``from "../bar.js"`` literal to include
    ``?v=<version>-<mtime>`` so any file that changes is automatically
    re-fetched on next page load.

    Args:
        rel_path: Path of the JS file relative to ``frontend/js``.

    Returns:
        A ``Response`` with the rewritten body, or ``None`` if the
        path falls outside ``frontend/js`` or doesn't exist.  Callers
        fall back to the static-file mount on ``None``.
    """
    target = (_JS_DIR / rel_path).resolve()
    try:
        target.relative_to(_JS_DIR.resolve())
    except ValueError:
        return None
    if not target.is_file():
        return None
    body = target.read_text()

    def _stamp(match: re.Match[str]) -> str:
        quote = match.group(1)
        rel = match.group(2)
        sibling = (target.parent / rel).resolve()
        try:
            mtime = int(sibling.stat().st_mtime)
            stamp = f"{pointlessql.__version__}-{mtime}"
        except OSError:
            stamp = pointlessql.__version__
        return f"{quote}{rel}?v={stamp}{quote}"

    rewritten = _JS_IMPORT_RE.sub(_stamp, body)
    return Response(rewritten, media_type="application/javascript")


@app.get("/static/js/{rel_path:path}", include_in_schema=False)
async def _serve_js(rel_path: str) -> Response:  # pyright: ignore[reportUnusedFunction]
    """Serve ``frontend/js/**`` with relative-import cache-busts.

    Falls back to a 404 ``Response`` if the file is missing — the
    static-files mount is registered *after* this route so a missing
    JS path never silently serves a directory listing.
    """
    out = _js_with_cache_bust(rel_path)
    if out is None:
        return Response(status_code=404)
    return out


app.mount(
    "/static",
    StaticFiles(directory=str(_FRONTEND_DIR)),
    name="static",
)

register_middleware(app)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Return service health."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(request: Request) -> Response:
    """Readiness probe: metadata DB answers and soyuz-catalog is reachable.

    ``/healthz`` is static liveness — it returns 200 even if the DB
    migration failed or soyuz is down.  ``/readyz`` actually exercises both
    dependencies so an orchestrator does not route traffic to an instance
    that cannot serve.  Unauthenticated (a probe carries no session); the
    body names which component is unhealthy without leaking URLs.

    Args:
        request: Incoming request, for the session factory + soyuz URL.

    Returns:
        JSON ``{status, db, soyuz}`` with HTTP 200 when both are healthy,
        else 503.
    """
    from sqlalchemy import text

    from pointlessql.api.health_routes import probe_soyuz
    from pointlessql.services._executor import run_sync

    def _check_db() -> None:
        with request.app.state.session_factory() as session:
            session.execute(text("SELECT 1"))

    db_status = "ok"
    try:
        await run_sync(_check_db)
    except Exception:  # noqa: BLE001 — readiness reports failure, never raises
        db_status = "down"
    soyuz_status = await probe_soyuz(request.app.state.settings.soyuz.catalog_url)
    ready = db_status == "ok" and soyuz_status == "ok"
    return JSONResponse(
        {"status": "ready" if ready else "not_ready", "db": db_status, "soyuz": soyuz_status},
        status_code=200 if ready else 503,
    )


def _authorize_metrics(request: Request) -> None:
    """Gate the ``/metrics`` scrape: public, scrape-token, or admin session.

    The metrics surface includes every job name in the install, so it is
    not world-readable by default. Resolution order: an operator who set
    ``metrics_public`` opts the route out of auth entirely; otherwise a
    configured ``metrics_token`` presented as a bearer token (compared in
    constant time) admits a least-privilege Prometheus scraper; failing
    both, the request falls through to the admin-session gate, which
    raises :class:`AuthorizationError` when the caller is not an admin.

    Args:
        request: Incoming FastAPI request.
    """
    obs = request.app.state.settings.observability
    if obs.metrics_public:
        return
    token: str | None = obs.metrics_token
    if token:
        header = request.headers.get("authorization") or ""
        presented = header[7:].strip() if header.lower().startswith("bearer ") else ""
        if presented and hmac.compare_digest(presented, token):
            return
    _require_admin(request)


@app.get("/metrics")
async def metrics(request: Request) -> Response:
    """Expose Prometheus metrics (scrape-token or admin-only).

    Returns the default text exposition format so any Prometheus
    scraper works without extra negotiation. Access is mediated by
    :func:`_authorize_metrics` — a least-privilege scrape token for
    headless Prometheus, with the admin session kept as a fallback —
    because the metrics surface includes the names of every job in the
    install, which is sensitive information on multi-tenant deployments.
    """
    _authorize_metrics(request)
    body, content_type = metrics_service.render_metrics()
    return Response(content=body, media_type=content_type)


# -- Routes --
#
# Every JSON + HTML route the app serves now lives in a dedicated
# ``api/<area>_routes.py`` module attached above via
# ``include_router()``.  The original monolith was split into 14
# focused routers (auth, catalog tree + HTML, sql, queries, alerts,
# volumes, governance, notebooks HTTP + WS, federation, jobs,
# dashboards, home, admin).  Exceptions raised inside any handler
# propagate to the centralised handler in
# ``api/error_handlers.py``.


def _run_dev_server() -> None:
    """Start the uvicorn dev server with the project-scoped reload watcher."""
    import uvicorn

    settings = get_settings()
    # Why: uvicorn's reload watcher defaults to the whole working directory.
    # That includes ``notebooks/``, so the editor's autosave triggers a server
    # reload — kernel + Pyright WebSockets get torn down mid-typing.  Pinning
    # reload_dirs to the source trees keeps autosave invisible to the watcher;
    # SQLite files (.db) and Delta tables (notebooks/, /tmp) stay outside
    # scope.
    project_root = Path(__file__).resolve().parent.parent
    uvicorn.run(
        "pointlessql.api.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=True,
        reload_dirs=[str(project_root), str(project_root.parent / "frontend")],
    )


# ---------------------------------------------------------------------------
# CLI surface — Typer app exposed via ``[project.scripts] pointlessql = "...:cli"``
# ---------------------------------------------------------------------------
#
# Why:  needed an admin-side helper to mint an auditor-scoped
# API key for the Audit-Reviewer-Agent's daily Hermes job. Rather than
# layering a separate console script, the existing ``pointlessql`` entry
# point grew a Typer app: the no-argument invocation still starts the dev
# server (backward-compat), and ``pointlessql admin <subcommand>`` exposes
# operational helpers.

import typer  # noqa: E402  # import below to keep heavy deps out of FastAPI import path

cli = typer.Typer(
    name="pointlessql",
    help="PointlesSQL CLI. Run with no arguments to start the dev server.",
    invoke_without_command=True,
    no_args_is_help=False,
)
_admin_cli = typer.Typer(help="Administrative helpers (key issuance, …).")
cli.add_typer(_admin_cli, name="admin")

from pointlessql.cli.bundles import bundles_cli  # noqa: E402  # CLI-only import

cli.add_typer(bundles_cli, name="bundle")


@cli.callback()
def _root(ctx: typer.Context) -> None:  # pyright: ignore[reportUnusedFunction]
    """Default to the dev server when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        _run_dev_server()


@_admin_cli.command("issue-auditor-key")
def _admin_issue_auditor_key(  # pyright: ignore[reportUnusedFunction]
    name: str = typer.Option(..., "--name", help="Unique key name (≤ 64 chars)."),
    supervisor: bool = typer.Option(
        False,
        "--supervisor",
        help="Also grant the supervisor scope (per-run write privileges).",
    ),
) -> None:
    """Issue a fresh auditor-scoped API key and print the plaintext token once.

    The token is stored as a salted hash in ``api_keys`` and cannot be
    recovered afterwards — copy it into the Hermes cron job's
    ``POINTLESSQL_API_KEY`` env overlay immediately.
    """
    settings = get_settings()
    init_db(settings.db.url)
    factory = get_session_factory()
    try:
        row, plaintext = api_keys_service.create_api_key(
            factory,
            name=name,
            auditor=True,
            supervisor=supervisor,
        )
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"name        = {row.name}")
    typer.echo(f"prefix      = {row.secret_prefix}")
    typer.echo(f"auditor     = {row.auditor}")
    typer.echo(f"supervisor  = {row.supervisor}")
    typer.echo(f"created_at  = {row.created_at.isoformat()}")
    typer.echo("")
    typer.echo("token (shown once — save it now):")
    typer.echo(plaintext)


@cli.command("lens-mcp")
def _lens_mcp_cmd() -> None:  # pyright: ignore[reportUnusedFunction]
    """Run the Lens read-only Q&A MCP server on stdio.

    Reads ``LENS_API_KEY`` (an analyst-scoped api_keys secret) from
    the env, resolves it to a workspace, and exposes every Lens tool
    to the connected MCP client (Claude Desktop, Cursor, etc.).
    Blocks until stdin closes.
    """
    from pointlessql.services.lens.mcp_server import (
        LensMcpAuthError,
        run_lens_mcp_stdio,
    )

    try:
        run_lens_mcp_stdio()
    except LensMcpAuthError as exc:
        typer.echo(f"lens-mcp: {exc}", err=True)
        raise typer.Exit(code=2) from exc


@cli.command("audit-export")
def _audit_export_cmd(  # pyright: ignore[reportUnusedFunction]
    out: Path = typer.Option(
        ...,
        "--out",
        help="Destination path for the data file.  Sidecars go next to it.",
    ),
    fmt: str = typer.Option(
        "json",
        "--fmt",
        help="Output format: 'json' (default) or 'csv'.",
    ),
    since: str | None = typer.Option(
        None,
        "--since",
        help="ISO-8601 cutoff (inclusive).  Omit for no lower bound.",
    ),
    until: str | None = typer.Option(
        None,
        "--until",
        help="ISO-8601 end (exclusive).  Omit for no upper bound.",
    ),
    action: str | None = typer.Option(
        None,
        "--action",
        help="Optional exact-match action filter.",
    ),
    actor: str | None = typer.Option(
        None,
        "--actor",
        help="Optional substring filter on user_email.",
    ),
    target: str | None = typer.Option(
        None,
        "--target",
        help="Optional substring filter on target.",
    ),
    db_url: str | None = typer.Option(
        None,
        "--db-url",
        help="SQLAlchemy URL override; defaults to POINTLESSQL_DB_URL.",
    ),
) -> None:
    """Export the audit log + tamper-evidence sidecars.

    Writes three mode-0600 files at ``--out``:

    * ``<out>`` — JSON array or CSV table.
    * ``<out>.sha256`` — sha256sum-compatible.
    * ``<out>.manifest.json`` — filters + count + tool version.

    Compliance buyers run ``sha256sum -c <out>.sha256`` to verify
    the data file wasn't tampered with after export, and match
    the manifest's ``entry_count`` + filter set against their
    expected scope.
    """
    from pointlessql.cli.audit_export import cli_entrypoint as audit_export_run

    if fmt not in ("json", "csv"):
        typer.echo(f"--fmt must be 'json' or 'csv' (got {fmt!r})", err=True)
        raise typer.Exit(code=2)
    code = audit_export_run(
        out=out,
        fmt=fmt,  # type: ignore[arg-type]
        since=since,
        until=until,
        action=action,
        actor=actor,
        target=target,
        db_url=db_url,
    )
    raise typer.Exit(code=code)


@cli.command("migrate-to-postgres")
def _migrate_to_postgres_cmd(  # pyright: ignore[reportUnusedFunction]
    source: str = typer.Option(
        ...,
        "--source",
        help="SQLAlchemy URL of the existing SQLite metadata DB.",
    ),
    target: str = typer.Option(
        ...,
        "--target",
        help="SQLAlchemy URL of the empty Postgres metadata DB.",
    ),
    batch_size: int = typer.Option(
        1000,
        "--batch-size",
        help="Rows per INSERT batch when streaming source rows.",
        min=1,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Read source row counts but skip writes; exit cleanly.",
    ),
) -> None:
    """Bulk-copy a SQLite PointlesSQL deployment to Postgres.

    Refuses to overwrite a non-empty target.  Runs ``alembic
    upgrade head`` against the target first so the schema chain
    matches.  Streams source rows in ``--batch-size`` chunks,
    syncs PG sequences past the largest copied id, rebuilds the
    PG-side FTS index, and verifies row counts (with a sample-hash
    for tables ≥ 100 rows).
    """
    from pointlessql.cli import migrate_to_postgres as mtp

    code = mtp.cli_entrypoint(
        source_url=source,
        target_url=target,
        batch_size=batch_size,
        dry_run=dry_run,
    )
    if code != 0:
        raise typer.Exit(code=code)
