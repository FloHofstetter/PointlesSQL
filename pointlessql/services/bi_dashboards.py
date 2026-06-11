"""BI-dashboard CRUD, layout, and parameter substitution.

Business logic behind ``/api/bi``.  Widget data execution lives in
the route layer (it needs the UC client + the request principal for
SELECT enforcement); this module owns everything storage-shaped —
including :func:`substitute_params`, the type-checked literal
escaping that turns dashboard parameters into SQL fragments.
"""

from __future__ import annotations

import datetime
import json
import re
import uuid
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import delete, select

from pointlessql.models.bi_dashboards import (
    BI_WIDGET_KINDS,
    BiDashboard,
    BiDashboardWidget,
)
from pointlessql.models.catalog import SavedQuery

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

_UNSET: Any = object()
"""Sentinel distinguishing "leave unchanged" from "set to None"."""

_PARAM_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
"""``{{param}}`` placeholders inside widget SQL (identifier-only, so
``{{secrets/...}}`` references never match)."""

PARAM_TYPES: tuple[str, ...] = ("string", "number", "date")
"""Dashboard parameter types with a safe literal encoding."""


def _utcnow() -> datetime.datetime:
    """Return the current UTC wall-clock."""
    return datetime.datetime.now(datetime.UTC)


def _slugify(title: str) -> str:
    """Derive a collision-proof slug from *title* (mirrors saved queries)."""
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "dashboard"
    return f"{base}-{uuid.uuid4().hex[:6]}"


def create_dashboard(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    title: str,
    description: str | None,
    owner_id: int,
) -> BiDashboard:
    """Create an empty dashboard canvas.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Owning workspace.
        title: Human-readable name (slug derives from it).
        description: Optional free-form description.
        owner_id: Creating user's id.

    Returns:
        The persisted dashboard row (detached).

    Raises:
        ValueError: On an empty title.
    """
    cleaned = title.strip()
    if not cleaned:
        raise ValueError("title must be a non-empty string")
    now = _utcnow()
    row = BiDashboard(
        workspace_id=workspace_id,
        slug=_slugify(cleaned),
        title=cleaned,
        description=description,
        owner_id=owner_id,
        created_at=now,
        updated_at=now,
    )
    with factory() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def list_dashboards(
    factory: sessionmaker[Session], *, workspace_id: int
) -> list[tuple[BiDashboard, int]]:
    """List the workspace's dashboards with their widget counts.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.

    Returns:
        ``(dashboard, widget_count)`` pairs, newest-updated first.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(BiDashboard)
                .where(BiDashboard.workspace_id == workspace_id)
                .order_by(BiDashboard.updated_at.desc())
            )
        )
        result: list[tuple[BiDashboard, int]] = []
        for row in rows:
            count = len(
                list(
                    session.scalars(
                        select(BiDashboardWidget.id).where(BiDashboardWidget.dashboard_id == row.id)
                    )
                )
            )
            session.expunge(row)
            result.append((row, count))
    return result


def get_dashboard(
    factory: sessionmaker[Session], *, workspace_id: int, slug: str
) -> BiDashboard | None:
    """Return the workspace's dashboard by slug, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.
        slug: Dashboard slug.

    Returns:
        The detached row, or ``None`` when absent.
    """
    with factory() as session:
        row = session.scalar(
            select(BiDashboard).where(
                BiDashboard.workspace_id == workspace_id,
                BiDashboard.slug == slug,
            )
        )
        if row is not None:
            session.expunge(row)
    return row


def get_dashboard_by_token(factory: sessionmaker[Session], *, token: str) -> BiDashboard | None:
    """Return the published dashboard behind *token*, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        token: Public-share token from the URL.

    Returns:
        The detached row, or ``None`` for unknown/revoked tokens.
    """
    if not token:
        return None
    with factory() as session:
        row = session.scalar(select(BiDashboard).where(BiDashboard.public_token == token))
        if row is not None:
            session.expunge(row)
    return row


def update_dashboard(
    factory: sessionmaker[Session],
    *,
    dashboard_id: int,
    title: Any = _UNSET,
    description: Any = _UNSET,
    params: Any = _UNSET,
) -> BiDashboard | None:
    """Patch title / description / params on a dashboard.

    Args:
        factory: SQLAlchemy session factory.
        dashboard_id: Primary key.
        title: New title, or unset to keep.
        description: New description (``None`` clears), or unset.
        params: New parameter-spec list, or unset.  Validated via
            :func:`validate_params`.

    Returns:
        The refreshed detached row, or ``None`` when absent.

    Raises:
        ValueError: On an empty title or malformed params.
    """
    with factory() as session:
        row = session.get(BiDashboard, dashboard_id)
        if row is None:
            return None
        if title is not _UNSET:
            cleaned = str(title).strip()
            if not cleaned:
                raise ValueError("title must be a non-empty string")
            row.title = cleaned
        if description is not _UNSET:
            row.description = description
        if params is not _UNSET:
            row.params = json.dumps(validate_params(params))
        row.updated_at = _utcnow()
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def delete_dashboard(factory: sessionmaker[Session], *, dashboard_id: int) -> bool:
    """Delete a dashboard and its widgets, snapshots, and schedule.

    Children go explicitly in the same transaction (same rationale
    as the secret-scope delete: SQLite only cascades with the FK
    pragma on).  The snapshot schedule goes through its own delete
    helper first so the hidden backing job disappears with it.

    Args:
        factory: SQLAlchemy session factory.
        dashboard_id: Primary key.

    Returns:
        ``True`` when a row was deleted.
    """
    from pointlessql.models import BiDashboardSnapshot
    from pointlessql.services.bi_snapshots import delete_schedule

    delete_schedule(factory, dashboard_id=dashboard_id)
    with factory() as session:
        row = session.get(BiDashboard, dashboard_id)
        if row is None:
            return False
        session.execute(
            delete(BiDashboardWidget).where(BiDashboardWidget.dashboard_id == dashboard_id)
        )
        session.execute(
            delete(BiDashboardSnapshot).where(BiDashboardSnapshot.dashboard_id == dashboard_id)
        )
        session.delete(row)
        session.commit()
    return True


def set_publish(factory: sessionmaker[Session], *, dashboard_id: int, publish: bool) -> str | None:
    """Publish (mint a token) or unpublish (revoke it).

    Args:
        factory: SQLAlchemy session factory.
        dashboard_id: Primary key.
        publish: ``True`` mints/keeps a token, ``False`` clears it.

    Returns:
        The active token after the call (``None`` when unpublished
        or the dashboard is absent).
    """
    with factory() as session:
        row = session.get(BiDashboard, dashboard_id)
        if row is None:
            return None
        if publish and not row.public_token:
            row.public_token = uuid.uuid4().hex
        elif not publish:
            row.public_token = None
        row.updated_at = _utcnow()
        session.commit()
        token = row.public_token
    return token


def validate_params(params: Any) -> list[dict[str, Any]]:
    """Validate a dashboard parameter-spec list.

    Args:
        params: Candidate list of ``{"name", "label"?, "type",
            "default"?}`` dicts.

    Returns:
        The normalised spec list.

    Raises:
        ValueError: On non-list input, duplicate / malformed names,
            or unknown types.
    """
    if not isinstance(params, list):
        raise ValueError("params must be a list")
    seen: set[str] = set()
    normalised: list[dict[str, Any]] = []
    for raw_entry in cast("list[object]", params):
        if not isinstance(raw_entry, dict):
            raise ValueError("each param must be an object")
        entry = cast("dict[str, Any]", raw_entry)
        name = str(entry.get("name", "")).strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"param name {name!r} must be an identifier")
        if name in seen:
            raise ValueError(f"duplicate param name {name!r}")
        seen.add(name)
        ptype = str(entry.get("type", "string"))
        if ptype not in PARAM_TYPES:
            raise ValueError(f"param type must be one of {', '.join(PARAM_TYPES)}")
        normalised.append(
            {
                "name": name,
                "label": str(entry.get("label") or name),
                "type": ptype,
                "default": entry.get("default"),
            }
        )
    return normalised


def substitute_params(sql_text: str, *, specs: list[dict[str, Any]], values: dict[str, Any]) -> str:
    """Replace ``{{param}}`` placeholders with type-checked literals.

    Strings become single-quoted literals with quote doubling,
    numbers are parsed and re-emitted from the parsed value (so a
    payload can never smuggle SQL through a "number"), dates are
    ISO-validated and emitted as ``DATE '...'``.  An unknown
    placeholder, a missing value, or a value that fails its type's
    validation propagates a :class:`ValueError` out of the
    substitution.

    Args:
        sql_text: Widget SQL possibly containing placeholders.
        specs: The dashboard's validated parameter specs.
        values: Caller-supplied parameter values (falls back to each
            spec's ``default``).

    Returns:
        The substituted SQL.
    """
    spec_by_name = {str(spec["name"]): spec for spec in specs}

    def _literal(match: re.Match[str]) -> str:
        name = match.group(1)
        spec = spec_by_name.get(name)
        if spec is None:
            raise ValueError(f"unknown dashboard parameter {name!r}")
        raw = values.get(name, spec.get("default"))
        if raw is None:
            raise ValueError(f"no value for dashboard parameter {name!r}")
        ptype = str(spec.get("type", "string"))
        if ptype == "number":
            try:
                parsed = float(str(raw))
            except ValueError as exc:
                raise ValueError(f"parameter {name!r} is not a number: {raw!r}") from exc
            return repr(int(parsed)) if parsed.is_integer() else repr(parsed)
        if ptype == "date":
            try:
                day = datetime.date.fromisoformat(str(raw))
            except ValueError as exc:
                raise ValueError(f"parameter {name!r} is not an ISO date: {raw!r}") from exc
            return f"DATE '{day.isoformat()}'"
        escaped = str(raw).replace("'", "''")
        return f"'{escaped}'"

    return _PARAM_RE.sub(_literal, sql_text)


def add_widget(
    factory: sessionmaker[Session],
    *,
    dashboard_id: int,
    kind: str,
    title: str | None,
    sql_text: str | None,
    saved_query_id: int | None,
    markdown: str | None,
    chart_spec: dict[str, Any] | None,
    position: dict[str, Any] | None,
) -> BiDashboardWidget:
    """Add one widget to a dashboard.

    Args:
        factory: SQLAlchemy session factory.
        dashboard_id: Owning dashboard's primary key.
        kind: One of :data:`BI_WIDGET_KINDS`.
        title: Optional widget header.
        sql_text: Inline SQL for data-backed kinds.
        saved_query_id: Saved-query reference (alternative to
            ``sql_text``).
        markdown: Body for ``markdown`` widgets.
        chart_spec: ECharts encoding dict (stored as JSON).
        position: Gridstack rectangle dict (stored as JSON).

    An unknown kind or an inconsistent source combination for the
    kind propagates the validator's :class:`ValueError`.

    Returns:
        The persisted widget row (detached).
    """
    _validate_widget_source(
        kind, sql_text=sql_text, saved_query_id=saved_query_id, markdown=markdown
    )
    now = _utcnow()
    row = BiDashboardWidget(
        dashboard_id=dashboard_id,
        kind=kind,
        title=title,
        sql_text=sql_text,
        saved_query_id=saved_query_id,
        markdown=markdown,
        chart_spec=json.dumps(chart_spec or {}),
        position=json.dumps(position or {"x": 0, "y": 0, "w": 6, "h": 4}),
        created_at=now,
        updated_at=now,
    )
    with factory() as session:
        session.add(row)
        _touch_dashboard(session, dashboard_id)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def _validate_widget_source(
    kind: str,
    *,
    sql_text: str | None,
    saved_query_id: int | None,
    markdown: str | None,
) -> None:
    """Reject kind/source combinations the view page cannot render."""
    if kind not in BI_WIDGET_KINDS:
        raise ValueError(f"kind must be one of {', '.join(BI_WIDGET_KINDS)}")
    if kind == "markdown":
        if not markdown:
            raise ValueError("markdown widgets need a markdown body")
        return
    has_sql = bool(sql_text and sql_text.strip())
    if has_sql == bool(saved_query_id):
        raise ValueError(f"{kind} widgets need exactly one of sql_text / saved_query_id")


def _touch_dashboard(session: Session, dashboard_id: int) -> None:
    """Bump the owning dashboard's ``updated_at`` inside *session*."""
    dashboard = session.get(BiDashboard, dashboard_id)
    if dashboard is not None:
        dashboard.updated_at = _utcnow()


def update_widget(
    factory: sessionmaker[Session],
    *,
    widget_id: int,
    title: Any = _UNSET,
    sql_text: Any = _UNSET,
    saved_query_id: Any = _UNSET,
    markdown: Any = _UNSET,
    chart_spec: Any = _UNSET,
    position: Any = _UNSET,
) -> BiDashboardWidget | None:
    """Patch a widget's fields.

    A patch that leaves the widget without a consistent data source
    for its kind propagates the validator's :class:`ValueError`.

    Args:
        factory: SQLAlchemy session factory.
        widget_id: Primary key.
        title: New header, or unset.
        sql_text: New inline SQL, or unset.
        saved_query_id: New saved-query ref, or unset.
        markdown: New markdown body, or unset.
        chart_spec: New ECharts encoding dict, or unset.
        position: New gridstack rectangle dict, or unset.

    Returns:
        The refreshed detached row, or ``None`` when absent.
    """
    with factory() as session:
        row = session.get(BiDashboardWidget, widget_id)
        if row is None:
            return None
        if title is not _UNSET:
            row.title = title
        if sql_text is not _UNSET:
            row.sql_text = sql_text
        if saved_query_id is not _UNSET:
            row.saved_query_id = saved_query_id
        if markdown is not _UNSET:
            row.markdown = markdown
        if chart_spec is not _UNSET:
            row.chart_spec = json.dumps(chart_spec or {})
        if position is not _UNSET:
            row.position = json.dumps(position or {})
        _validate_widget_source(
            row.kind,
            sql_text=row.sql_text,
            saved_query_id=row.saved_query_id,
            markdown=row.markdown,
        )
        row.updated_at = _utcnow()
        _touch_dashboard(session, row.dashboard_id)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def delete_widget(factory: sessionmaker[Session], *, widget_id: int) -> bool:
    """Delete one widget.

    Args:
        factory: SQLAlchemy session factory.
        widget_id: Primary key.

    Returns:
        ``True`` when a row was deleted.
    """
    with factory() as session:
        row = session.get(BiDashboardWidget, widget_id)
        if row is None:
            return False
        _touch_dashboard(session, row.dashboard_id)
        session.delete(row)
        session.commit()
    return True


def list_widgets(factory: sessionmaker[Session], *, dashboard_id: int) -> list[BiDashboardWidget]:
    """List a dashboard's widgets (stable id order; layout is client-side).

    Args:
        factory: SQLAlchemy session factory.
        dashboard_id: Owning dashboard's primary key.

    Returns:
        Detached widget rows.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(BiDashboardWidget)
                .where(BiDashboardWidget.dashboard_id == dashboard_id)
                .order_by(BiDashboardWidget.id)
            )
        )
        for row in rows:
            session.expunge(row)
    return rows


def get_widget(
    factory: sessionmaker[Session], *, dashboard_id: int, widget_id: int
) -> BiDashboardWidget | None:
    """Return one widget of one dashboard, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        dashboard_id: Owning dashboard's primary key (guards against
            cross-dashboard widget ids in the URL).
        widget_id: Widget primary key.

    Returns:
        The detached row, or ``None`` when absent/mismatched.
    """
    with factory() as session:
        row = session.get(BiDashboardWidget, widget_id)
        if row is None or row.dashboard_id != dashboard_id:
            return None
        session.expunge(row)
    return row


def update_layout(
    factory: sessionmaker[Session],
    *,
    dashboard_id: int,
    positions: dict[int, dict[str, Any]],
) -> int:
    """Bulk-update widget rectangles after a gridstack drag.

    Args:
        factory: SQLAlchemy session factory.
        dashboard_id: Owning dashboard's primary key.
        positions: ``widget_id → {"x", "y", "w", "h"}`` map.

    Returns:
        Number of widgets updated.
    """
    updated = 0
    now = _utcnow()
    with factory() as session:
        for widget_id, rect in positions.items():
            row = session.get(BiDashboardWidget, widget_id)
            if row is None or row.dashboard_id != dashboard_id:
                continue
            row.position = json.dumps({k: int(rect.get(k, 0)) for k in ("x", "y", "w", "h")})
            row.updated_at = now
            updated += 1
        if updated:
            _touch_dashboard(session, dashboard_id)
        session.commit()
    return updated


def resolve_widget_sql(factory: sessionmaker[Session], *, widget: BiDashboardWidget) -> str | None:
    """Return the SQL a data-backed widget should run.

    Args:
        factory: SQLAlchemy session factory.
        widget: The widget row.

    Returns:
        Inline SQL, the referenced saved query's text, or ``None``
        for markdown widgets / unbound references.
    """
    if widget.kind == "markdown":
        return None
    if widget.sql_text and widget.sql_text.strip():
        return widget.sql_text
    if widget.saved_query_id is None:
        return None
    with factory() as session:
        saved = session.get(SavedQuery, widget.saved_query_id)
        return saved.sql_text if saved is not None else None
