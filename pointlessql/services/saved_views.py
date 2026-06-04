"""SavedView service layer.

Pure CRUD + parameter substitution + SELECT-only validation.
Run-time execution itself is implemented in the route layer (so it
can hold the live DuckDB connection, register cancel handlers, and
record query-history rows under the caller's identity).  This
module is HTTP-agnostic.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import desc, or_, select

from pointlessql.exceptions import ValidationError
from pointlessql.models import SAVED_VIEW_PARAM_TYPES, SavedView
from pointlessql.services._slug import make_slug

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

_PARAM_PLACEHOLDER_RE = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_PARAM_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def normalize_parameters(raw: Any) -> list[dict[str, Any]]:
    """Validate and normalise the ``parameters`` payload.

    Args:
        raw: Caller-supplied list (may be ``None``).

    Returns:
        A list of normalised ``{name, label, type, default,
        required}`` dicts.

    Raises:
        ValidationError: If the payload is not a list, contains
            non-dict entries, has duplicate parameter names, or
            references an unsupported parameter type.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError("parameters must be a list of declaration dicts.")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry_raw in cast(list[Any], raw):
        if not isinstance(entry_raw, dict):
            raise ValidationError("Each parameter must be a dict.")
        entry = cast(dict[str, Any], entry_raw)
        name = entry.get("name")
        if not isinstance(name, str) or not _PARAM_NAME_RE.match(name):
            raise ValidationError("Parameter 'name' must match [a-zA-Z_][a-zA-Z0-9_]*.")
        if name in seen:
            raise ValidationError(f"Duplicate parameter name: {name!r}")
        seen.add(name)
        ptype = entry.get("type", "string")
        if not isinstance(ptype, str) or ptype not in SAVED_VIEW_PARAM_TYPES:
            raise ValidationError(
                f"Parameter {name!r} has unsupported type {ptype!r}.  "
                f"Pick one of: {', '.join(SAVED_VIEW_PARAM_TYPES)}."
            )
        label = entry.get("label")
        default = entry.get("default")
        required = bool(entry.get("required", False))
        out.append(
            {
                "name": name,
                "label": label if isinstance(label, str) else name,
                "type": ptype,
                "default": default,
                "required": required,
            }
        )
    return out


def validate_sql_is_select(sql: str) -> None:
    """Refuse non-SELECT SQL at save time.

    Defence in depth: the run path re-validates, but rejecting the
    text up front keeps the save flow honest.  Raises so the route
    layer maps to 400 via the centralised error handler.  Any
    ``${name}`` placeholders are stripped to ``NULL`` for the parse
    pass so sqlglot sees a syntactically-valid statement.

    Args:
        sql: The verbatim SQL the user typed.

    Raises:
        ValidationError: If parsing fails or the classified
            statement type is not ``SELECT``.
    """
    from pointlessql.pql import SQLParseError, StmtType, parse_and_classify

    sanitised = _PARAM_PLACEHOLDER_RE.sub("NULL", sql)
    try:
        _ast, stype = parse_and_classify(sanitised)
    except SQLParseError as exc:
        raise ValidationError(f"SQL is not parseable: {exc}") from exc
    if stype is not StmtType.SELECT:
        raise ValidationError("Saved views must be SELECT statements only.")


def referenced_placeholders(sql: str) -> list[str]:
    """Return every ``${name}`` placeholder name found in *sql* in order.

    Args:
        sql: The view's SQL text.

    Returns:
        A list of placeholder names (may contain duplicates in the
        order they appear).
    """
    return _PARAM_PLACEHOLDER_RE.findall(sql)


def cross_check_placeholders(sql: str, parameters: list[dict[str, Any]]) -> None:
    """Confirm every ``${name}`` placeholder has a matching parameter.

    Args:
        sql: The view's SQL text.
        parameters: The normalised parameter list.

    Raises:
        ValidationError: If a placeholder has no matching declaration.
    """
    declared = {p["name"] for p in parameters}
    used = set(referenced_placeholders(sql))
    missing = used - declared
    if missing:
        raise ValidationError(f"Placeholders without declared parameters: {sorted(missing)}")


def render_sql_with_params(
    sql: str,
    parameters: list[dict[str, Any]],
    values: dict[str, Any],
) -> tuple[str, list[Any]]:
    """Rewrite ``${name}`` placeholders to positional ``?`` + bound values.

    The output ``rewritten`` string is safe to pass to
    :meth:`duckdb.DuckDBPyConnection.execute` with the positional
    ``params`` list — no string interpolation of caller data.

    Args:
        sql: The view's SQL text (may contain ``${name}`` markers).
        parameters: The normalised parameter list.
        values: User-supplied values keyed by parameter name.

    Returns:
        ``(rewritten_sql, positional_values)``.

    Raises:
        ValidationError: If a required parameter is missing, or a
            supplied value cannot be coerced to its declared type.
    """  # noqa: DOC502 — raised via the inner _replace callback
    by_name = {p["name"]: p for p in parameters}
    binds: list[Any] = []

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        decl = by_name.get(name)
        if decl is None:
            raise ValidationError(f"Unknown placeholder: ${{{name}}}")
        raw = values.get(name, decl.get("default"))
        if raw is None or raw == "":
            if decl.get("required"):
                raise ValidationError(f"Required parameter missing: {name}")
            binds.append(None)
            return "?"
        binds.append(_coerce(name, decl["type"], raw))
        return "?"

    rewritten = _PARAM_PLACEHOLDER_RE.sub(_replace, sql)
    return rewritten, binds


def _coerce(name: str, ptype: str, raw: Any) -> Any:
    """Coerce *raw* to the declared parameter type.

    Args:
        name: Parameter name (for error messages).
        ptype: Declared parameter type.
        raw: Caller-supplied value.

    Returns:
        The coerced value ready to bind to DuckDB.

    Raises:
        ValidationError: When coercion fails.
    """
    if ptype == "string":
        return str(raw)
    if ptype == "boolean":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.lower() in ("1", "true", "yes", "on")
        return bool(raw)
    if ptype == "integer":
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{name} must be an integer.") from exc
    if ptype == "number":
        try:
            return float(raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{name} must be a number.") from exc
    if ptype == "date":
        if isinstance(raw, datetime.date):
            return raw.isoformat()
        try:
            return datetime.date.fromisoformat(str(raw)).isoformat()
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{name} must be an ISO date (YYYY-MM-DD).") from exc
    raise ValidationError(f"Unsupported parameter type: {ptype}")


def serialize(row: SavedView) -> dict[str, Any]:
    """Convert a row to the JSON-friendly dict used in API responses.

    Args:
        row: The saved-view row.

    Returns:
        A plain dict.
    """
    try:
        parameters = json.loads(row.parameters_json or "[]")
    except TypeError, ValueError:
        parameters = []
    return {
        "id": int(row.id),
        "workspace_id": int(row.workspace_id),
        "slug": row.slug,
        "title": row.title,
        "description": row.description,
        "sql_text": row.sql_text,
        "parameters": parameters,
        "owner_id": int(row.owner_id),
        "dp_id": row.dp_id,
        "target_fqn": row.target_fqn,
        "is_active": bool(row.is_active),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def can_mutate(row: SavedView, *, user_id: int, is_admin: bool) -> bool:
    """Return whether *user* may edit / delete *row*.

    Args:
        row: The saved-view row.
        user_id: Current user id.
        is_admin: Whether the current user is admin.

    Returns:
        ``True`` for owner + admin.
    """
    return is_admin or row.owner_id == user_id


def create_saved_view(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    owner_id: int,
    title: str,
    description: str | None,
    sql_text: str,
    parameters: list[dict[str, Any]] | None = None,
    dp_id: int | None = None,
    target_fqn: str | None = None,
) -> dict[str, Any]:
    """Insert a new saved-view row.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Workspace the view lives in.
        owner_id: User creating the view.
        title: Display title (required, non-empty).
        description: Optional blurb.
        sql_text: The verbatim SELECT (validated SELECT-only here).
        parameters: Normalised parameter declarations.
        dp_id: Optional DP scope.
        target_fqn: Optional table FQN scope.

    Returns:
        The serialised row.

    Raises:
        ValidationError: When title / SQL are empty, the SQL is
            not a SELECT, the parameters list is malformed, or a
            placeholder references an undeclared parameter.
    """
    title = (title or "").strip()
    if not title:
        raise ValidationError("title is required.")
    sql_text = (sql_text or "").strip()
    if not sql_text:
        raise ValidationError("sql_text is required.")
    validate_sql_is_select(sql_text)
    params_norm = normalize_parameters(parameters)
    cross_check_placeholders(sql_text, params_norm)
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = SavedView(
            workspace_id=workspace_id,
            owner_id=owner_id,
            slug=make_slug(title, fallback="view"),
            title=title,
            description=description if isinstance(description, str) else None,
            sql_text=sql_text,
            parameters_json=json.dumps(params_norm, separators=(",", ":")),
            dp_id=dp_id,
            target_fqn=target_fqn,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return serialize(row)


def list_visible(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    dp_id: int | None = None,
    target_fqn: str | None = None,
    include_inactive: bool = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List views visible to the workspace, optionally scoped to a DP/table.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Caller's workspace.
        dp_id: When set, limit to views with this dp scope.
        target_fqn: When set, limit to views with this FQN scope.
        include_inactive: When ``True`` include archived rows.
        limit: Row cap.

    Returns:
        Serialised rows, newest-updated first.
    """
    stmt = (
        select(SavedView)
        .where(SavedView.workspace_id == workspace_id)
        .order_by(desc(SavedView.updated_at))
        .limit(limit)
    )
    if not include_inactive:
        stmt = stmt.where(SavedView.is_active.is_(True))
    if dp_id is not None and target_fqn is not None:
        stmt = stmt.where(or_(SavedView.dp_id == dp_id, SavedView.target_fqn == target_fqn))
    elif dp_id is not None:
        stmt = stmt.where(SavedView.dp_id == dp_id)
    elif target_fqn is not None:
        stmt = stmt.where(SavedView.target_fqn == target_fqn)
    with factory() as session:
        rows = list(session.scalars(stmt).all())
    return [serialize(r) for r in rows]


def get_by_slug(
    factory: sessionmaker[Session],
    slug: str,
    *,
    workspace_id: int,
) -> dict[str, Any] | None:
    """Return the row for *slug* if it lives in *workspace_id*.

    Args:
        factory: SQLAlchemy session factory.
        slug: View slug.
        workspace_id: Caller's workspace; rows in other workspaces
            are invisible (404).

    Returns:
        The serialised row or ``None``.
    """
    with factory() as session:
        row = session.scalar(
            select(SavedView).where(
                SavedView.slug == slug,
                SavedView.workspace_id == workspace_id,
            )
        )
    if row is None:
        return None
    return serialize(row)


def get_row(
    factory: sessionmaker[Session],
    slug: str,
    *,
    workspace_id: int,
) -> SavedView | None:
    """Return the raw ORM row (used by the run endpoint).

    Args:
        factory: SQLAlchemy session factory.
        slug: View slug.
        workspace_id: Caller's workspace.

    Returns:
        The ORM row or ``None``.
    """
    with factory() as session:
        return session.scalar(
            select(SavedView).where(
                SavedView.slug == slug,
                SavedView.workspace_id == workspace_id,
            )
        )


def update_by_slug(
    factory: sessionmaker[Session],
    slug: str,
    *,
    workspace_id: int,
    user_id: int,
    is_admin: bool,
    title: str | None = None,
    description: str | None = None,
    sql_text: str | None = None,
    parameters: list[dict[str, Any]] | None = None,
    dp_id: int | None = None,
    target_fqn: str | None = None,
    is_active: bool | None = None,
) -> dict[str, Any] | None:
    """Partial-update a saved view; only owner + admin may mutate.

    Args:
        factory: SQLAlchemy session factory.
        slug: Row to update.
        workspace_id: Caller's workspace.
        user_id: Current user.
        is_admin: Whether current user is admin.
        title: New title or ``None`` to leave unchanged.
        description: New description or ``None`` to leave unchanged.
        sql_text: New SQL or ``None`` to leave unchanged.
        parameters: New parameters list or ``None`` to leave unchanged.
        dp_id: New DP scope or ``None``.
        target_fqn: New FQN scope or ``None``.
        is_active: New active flag or ``None``.

    Returns:
        The serialised row, or ``None`` when the row is missing /
        not visible / the caller is not authorised.

    Raises:
        ValidationError: On SQL / parameter validation failure.
    """
    with factory() as session:
        row = session.scalar(
            select(SavedView).where(
                SavedView.slug == slug,
                SavedView.workspace_id == workspace_id,
            )
        )
        if row is None:
            return None
        if not can_mutate(row, user_id=user_id, is_admin=is_admin):
            return None
        if title is not None:
            new_title = title.strip()
            if not new_title:
                raise ValidationError("title cannot be empty.")
            row.title = new_title
        if description is not None:
            row.description = description if description.strip() else None
        if sql_text is not None:
            new_sql = sql_text.strip()
            if not new_sql:
                raise ValidationError("sql_text cannot be empty.")
            validate_sql_is_select(new_sql)
            row.sql_text = new_sql
        if parameters is not None:
            params_norm = normalize_parameters(parameters)
            row.parameters_json = json.dumps(params_norm, separators=(",", ":"))
        cross_check_placeholders(
            row.sql_text,
            cast(list[dict[str, Any]], json.loads(row.parameters_json or "[]")),
        )
        if dp_id is not None:
            row.dp_id = dp_id or None
        if target_fqn is not None:
            row.target_fqn = target_fqn.strip() or None
        if is_active is not None:
            row.is_active = bool(is_active)
        row.updated_at = datetime.datetime.now(datetime.UTC)
        session.commit()
        session.refresh(row)
        return serialize(row)


def delete_by_slug(
    factory: sessionmaker[Session],
    slug: str,
    *,
    workspace_id: int,
    user_id: int,
    is_admin: bool,
) -> bool:
    """Hard-delete a saved view; only owner + admin.

    Args:
        factory: SQLAlchemy session factory.
        slug: Row to delete.
        workspace_id: Caller's workspace.
        user_id: Current user.
        is_admin: Whether the user is admin.

    Returns:
        ``True`` on a successful delete; ``False`` when the row
        was missing or the caller is not authorised.
    """
    with factory() as session:
        row = session.scalar(
            select(SavedView).where(
                SavedView.slug == slug,
                SavedView.workspace_id == workspace_id,
            )
        )
        if row is None:
            return False
        if not can_mutate(row, user_id=user_id, is_admin=is_admin):
            return False
        session.delete(row)
        session.commit()
        return True
