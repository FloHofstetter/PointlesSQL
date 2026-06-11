"""Asset-bundle CLI: validate / plan / apply / export.

In-process commands against the metadata DB (no running server
needed): the Typer sub-app is mounted on the ``pointlessql`` entry
point as ``pointlessql bundle <command>``.  ``apply`` requires
``--run-as`` because the CLI has no session principal to default the
job run-as user from.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer

from pointlessql.services import asset_bundles as bundles_service

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

bundles_cli = typer.Typer(
    name="bundle",
    help="Declarative asset bundles: jobs, pipelines, and BI dashboards as YAML.",
)


def _session_factory() -> sessionmaker[Session]:
    """Initialise the metadata DB and return its session factory."""
    from pointlessql.config import get_settings
    from pointlessql.db import get_session_factory, init_db

    settings = get_settings()
    init_db(settings.db.url)
    return get_session_factory()


def _load_bundle(file: Path) -> bundles_service.BundleSpec:
    """Read + parse *file*; exits with code 1 on any validation error.

    Args:
        file: Path to the bundle YAML.

    Returns:
        The validated bundle spec.

    Raises:
        typer.Exit: With code 1 when the file is unreadable or the
            spec does not validate.
    """
    try:
        text = file.read_text()
    except OSError as exc:
        typer.echo(f"error: cannot read {file}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    try:
        return bundles_service.parse_bundle(text)
    except ValueError as exc:
        typer.echo(f"error: invalid bundle: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _echo_table(headers: list[str], rows: list[list[str]]) -> None:
    """Print a padded plain-text table."""
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    line = "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
    typer.echo(line)
    typer.echo("-" * len(line))
    for row in rows:
        typer.echo("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))


def _csv_names(raw: str | None) -> list[str] | None:
    """Turn a comma-separated option into the exporter's selector shape.

    ``None`` (option omitted) selects everything, an empty string
    selects nothing, otherwise the trimmed comma-separated names.
    """
    if raw is None:
        return None
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


@bundles_cli.command("validate")
def validate_cmd(
    file: Path = typer.Argument(..., help="Bundle YAML file to validate."),
) -> None:
    """Parse + validate a bundle file without touching the DB."""
    spec = _load_bundle(file)
    typer.echo(f"bundle      = {spec.bundle.name}")
    typer.echo(f"jobs        = {len(spec.jobs)}")
    typer.echo(f"pipelines   = {len(spec.pipelines)}")
    typer.echo(f"dashboards  = {len(spec.dashboards)}")
    typer.echo("OK")


@bundles_cli.command("plan")
def plan_cmd(
    file: Path = typer.Argument(..., help="Bundle YAML file to plan."),
    workspace: int = typer.Option(1, "--workspace", help="Workspace id to plan against."),
) -> None:
    """Diff a bundle against the live DB and print the plan.

    Exits with code 1 when a declared resource cannot be diffed
    (bad pipeline SQL, ambiguous widget matching).
    """
    spec = _load_bundle(file)
    factory = _session_factory()
    try:
        plan = bundles_service.plan_bundle(factory, spec=spec, workspace_id=workspace)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _echo_table(
        ["RESOURCE", "IDENTITY", "ACTION", "CHANGES"],
        [
            [entry.resource_type, entry.identity, entry.action, "; ".join(entry.changes)]
            for entry in plan.entries
        ],
    )
    if plan.orphans:
        typer.echo("")
        typer.echo("orphans (unmanaged live resources — never deleted):")
        for orphan in plan.orphans:
            typer.echo(f"  {orphan.resource_type}: {orphan.identity}")


@bundles_cli.command("apply")
def apply_cmd(
    file: Path = typer.Argument(..., help="Bundle YAML file to apply."),
    run_as: str = typer.Option(
        ...,
        "--run-as",
        help="Apply principal e-mail; default run-as for jobs without one.",
    ),
    workspace: int = typer.Option(1, "--workspace", help="Workspace id to apply into."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Compute per-resource actions without writing."
    ),
) -> None:
    """Reconcile a bundle into the DB (idempotent).

    Exits with code 1 when ``--run-as`` does not resolve to a user
    or any resource fails to apply.
    """
    from sqlalchemy import select

    from pointlessql.models import User

    spec = _load_bundle(file)
    factory = _session_factory()
    with factory() as session:
        actor_id = session.scalar(select(User.id).where(User.email == run_as))
    if actor_id is None:
        typer.echo(f"error: --run-as user {run_as!r} not found", err=True)
        raise typer.Exit(code=1)
    outcome = bundles_service.apply_bundle(
        factory,
        spec=spec,
        workspace_id=workspace,
        actor_user_id=int(actor_id),
        actor_email=run_as,
        dry_run=dry_run,
    )
    if outcome.dry_run:
        typer.echo("dry run — no writes performed")
    _echo_table(
        ["RESOURCE", "IDENTITY", "ACTION", "ERROR"],
        [
            [result.resource_type, result.identity, result.action, result.error or ""]
            for result in outcome.results
        ],
    )
    if outcome.has_errors():
        typer.echo(f"\n{outcome.error_count()} resource(s) failed", err=True)
        raise typer.Exit(code=1)


@bundles_cli.command("export")
def export_cmd(
    workspace: int = typer.Option(1, "--workspace", help="Workspace id to export from."),
    jobs: str | None = typer.Option(
        None, "--jobs", help="Comma-separated job names; omit for all, '' for none."
    ),
    pipelines: str | None = typer.Option(
        None, "--pipelines", help="Comma-separated pipeline slugs; omit for all, '' for none."
    ),
    dashboards: str | None = typer.Option(
        None, "--dashboards", help="Comma-separated dashboard slugs; omit for all, '' for none."
    ),
    out: Path | None = typer.Option(
        None, "--out", "-o", help="Write the YAML here instead of stdout."
    ),
) -> None:
    """Export live resources as a bundle YAML document.

    Exits with code 1 when a selected resource cannot be represented
    as a bundle spec.
    """
    factory = _session_factory()
    try:
        spec = bundles_service.export_bundle(
            factory,
            workspace_id=workspace,
            jobs=_csv_names(jobs),
            pipelines=_csv_names(pipelines),
            dashboards=_csv_names(dashboards),
        )
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    text = bundles_service.bundle_to_yaml(spec)
    if out is not None:
        out.write_text(text)
        typer.echo(f"wrote {out}")
    else:
        typer.echo(text, nl=False)
