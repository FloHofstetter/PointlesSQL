"""``/api/data-products/{catalog}/{schema}/readme`` — versioned wiki (Phase 71.5).

Five endpoints:

* ``GET /readme`` — latest version, or 404 when none exist.
* ``GET /readme/history`` — list of versions (id, version_int,
  updated_at, updated_by).
* ``GET /readme/v/{version_int}`` — fetch a specific version.
* ``PUT /readme`` — steward + admin only.  Creates a new version
  (version_int = max(prev) + 1).  Idempotent on empty / unchanged
  bodies (no row inserted when body is unchanged).
* ``GET /readme/diff?from=A&to=B`` — unified diff between two
  versions for the History modal.
"""

from __future__ import annotations

import datetime
import difflib
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import desc, func, select

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.exceptions import AuthorizationError
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_readme import DataProductReadme
from pointlessql.services.social._target_resolver import resolve_dp_target

router = APIRouter(tags=["data-products"])


def _serialise_version(
    row: DataProductReadme,
    *,
    author_email: str | None,
    author_display_name: str | None,
) -> dict[str, Any]:
    """Render one README version as JSON."""
    return {
        "id": row.id,
        "data_product_id": row.data_product_id,
        "version_int": row.version_int,
        "body_md": row.body_md,
        "updated_by": {
            "user_id": row.updated_by_user_id,
            "email": author_email,
            "display_name": author_display_name,
        },
        "updated_at": row.updated_at.isoformat(),
    }


def _require_steward_or_admin(user: Any, row: Any) -> None:
    """Raise unless the caller is the DP's steward or an install-admin."""
    is_steward = (
        row.steward_user_id is not None and row.steward_user_id == user["id"]
    )
    is_admin = bool(user.get("is_admin"))
    if not (is_steward or is_admin):
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="readme-edit",
            securable_type="data_product",
            full_name=f"{row.catalog_name}.{row.schema_name}",
        )


@router.get("/api/data-products/{catalog}/{schema}/readme")
async def get_latest_readme(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Return the latest README for the product (404 when none)."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        latest = session.execute(
            select(DataProductReadme)
            .where(
                DataProductReadme.workspace_id == workspace_id,
                DataProductReadme.data_product_id == row.id,
            )
            .order_by(desc(DataProductReadme.version_int))
            .limit(1)
        ).scalar_one_or_none()
        if latest is None:
            # bare-http-ok: cleaner than a 200 + null body — clients can
            # branch on the status to render the "no README yet" state.
            raise HTTPException(status_code=404, detail="no readme")
        author = session.get(User, latest.updated_by_user_id)
        author_email = author.email if author else None
        author_display = author.display_name if author else None
    return _serialise_version(
        latest, author_email=author_email, author_display_name=author_display
    )


@router.get("/api/data-products/{catalog}/{schema}/readme/history")
async def list_readme_history(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """List every version (descending) — body bodies elided for size."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        rows = (
            session.execute(
                select(DataProductReadme)
                .where(
                    DataProductReadme.workspace_id == workspace_id,
                    DataProductReadme.data_product_id == row.id,
                )
                .order_by(desc(DataProductReadme.version_int))
            )
            .scalars()
            .all()
        )
        author_ids = {r.updated_by_user_id for r in rows}
        author_map: dict[int, tuple[str, str]] = {}
        if author_ids:
            users = (
                session.execute(select(User).where(User.id.in_(author_ids)))
                .scalars()
                .all()
            )
            author_map = {u.id: (u.email, u.display_name) for u in users}

    payload = [
        {
            "id": r.id,
            "version_int": r.version_int,
            "updated_at": r.updated_at.isoformat(),
            "updated_by": {
                "user_id": r.updated_by_user_id,
                "email": author_map.get(r.updated_by_user_id, (None, None))[0],
                "display_name": author_map.get(r.updated_by_user_id, (None, None))[1],
            },
            "body_len": len(r.body_md),
        }
        for r in rows
    ]
    return {"data_product_id": row.id, "versions": payload}


@router.get("/api/data-products/{catalog}/{schema}/readme/v/{version_int}")
async def get_readme_version(
    catalog: str,
    schema: str,
    version_int: int,
    request: Request,
) -> dict[str, Any]:
    """Fetch a specific version."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        version = session.execute(
            select(DataProductReadme).where(
                DataProductReadme.workspace_id == workspace_id,
                DataProductReadme.data_product_id == row.id,
                DataProductReadme.version_int == version_int,
            )
        ).scalar_one_or_none()
        if version is None:
            # bare-http-ok: missing version surfaces as 404.
            raise HTTPException(status_code=404, detail="version not found")
        author = session.get(User, version.updated_by_user_id)
        author_email = author.email if author else None
        author_display = author.display_name if author else None
    return _serialise_version(
        version, author_email=author_email, author_display_name=author_display
    )


@router.put("/api/data-products/{catalog}/{schema}/readme")
async def upsert_readme(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Save a new README version.  Steward + admin only.

    Body: ``{"body_md": str}``.  Empty body is allowed (explicit
    "clear the README" — still creates a versioned row so the
    history shows the action).

    No-op when body matches the latest version (no new row, returns
    the existing one).
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, row)

    body = await request.json()
    body_md = body.get("body_md", "")
    if not isinstance(body_md, str):
        # bare-http-ok: payload contract — body must be string.
        raise HTTPException(status_code=400, detail="body_md must be a string")

    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        latest = session.execute(
            select(DataProductReadme)
            .where(
                DataProductReadme.workspace_id == workspace_id,
                DataProductReadme.data_product_id == row.id,
            )
            .order_by(desc(DataProductReadme.version_int))
            .limit(1)
        ).scalar_one_or_none()
        if latest is not None and latest.body_md == body_md:
            # No-op: return existing row instead of creating a v+1
            # that is byte-identical.
            author = session.get(User, latest.updated_by_user_id)
            return _serialise_version(
                latest,
                author_email=author.email if author else None,
                author_display_name=author.display_name if author else None,
            )

        next_version = (
            session.execute(
                select(func.coalesce(func.max(DataProductReadme.version_int), 0)).where(
                    DataProductReadme.workspace_id == workspace_id,
                    DataProductReadme.data_product_id == row.id,
                )
            ).scalar_one()
            + 1
        )
        target = resolve_dp_target(
            session,
            workspace_id=workspace_id,
            catalog_name=catalog,
            schema_name=schema,
        )
        new_row = DataProductReadme(
            workspace_id=workspace_id,
            data_product_id=row.id,
            social_target_id=target.id,
            version_int=int(next_version),
            body_md=body_md,
            updated_by_user_id=user["id"],
            updated_at=now,
        )
        session.add(new_row)
        session.commit()
        session.refresh(new_row)

        author = session.get(User, new_row.updated_by_user_id)
        author_email = author.email if author else None
        author_display = author.display_name if author else None

    return _serialise_version(
        new_row, author_email=author_email, author_display_name=author_display
    )


@router.get("/api/data-products/{catalog}/{schema}/readme/diff")
async def readme_diff(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Return a unified diff between two README versions.

    Query params: ``from=<int>`` + ``to=<int>``.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)

    qs = request.query_params
    try:
        from_v = int(qs.get("from", ""))
        to_v = int(qs.get("to", ""))
    except (TypeError, ValueError):
        # bare-http-ok: both query params required + integer.
        raise HTTPException(
            status_code=400, detail="from and to must be integer query params"
        ) from None

    with factory() as session:
        rows = (
            session.execute(
                select(DataProductReadme).where(
                    DataProductReadme.workspace_id == workspace_id,
                    DataProductReadme.data_product_id == row.id,
                    DataProductReadme.version_int.in_([from_v, to_v]),
                )
            )
            .scalars()
            .all()
        )
    by_v = {r.version_int: r for r in rows}
    if from_v not in by_v or to_v not in by_v:
        # bare-http-ok: one of the requested versions doesn't exist.
        raise HTTPException(status_code=404, detail="version not found")

    a = by_v[from_v].body_md.splitlines()
    b = by_v[to_v].body_md.splitlines()
    diff_lines = list(
        difflib.unified_diff(
            a,
            b,
            fromfile=f"v{from_v}",
            tofile=f"v{to_v}",
            lineterm="",
        )
    )
    return {
        "data_product_id": row.id,
        "from_version": from_v,
        "to_version": to_v,
        "diff": "\n".join(diff_lines),
    }
