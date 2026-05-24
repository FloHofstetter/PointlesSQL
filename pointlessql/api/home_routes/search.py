"""``GET /api/search`` — Cmd+K command-palette aggregator.

Merges soyuz catalog / schema / table / federation hits with local
jobs, dashboards, and (for admins) workspace notebooks.  Scoring
favours prefix over substring; ties resolve by ``updated_at``
descending.  Per-source try/except so a partial outage degrades to
"those hits missing" instead of failing the whole palette — the
shortcut would feel fragile otherwise.

Operator syntax (Phase 80.6, Slack convention):

* ``@<term>`` narrows to user hits.
* ``#<term>`` narrows to topic hits.

Empty string returns ``[]`` — the frontend renders the localStorage
recent-searches in that case so we avoid the roundtrip.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from fastapi import APIRouter, Request

from pointlessql.api.dependencies import get_uc_client, get_user
from pointlessql.api.home_routes._helpers import epoch_seconds, score_match
from pointlessql.config import Settings
from pointlessql.exceptions import PointlessSQLError
from pointlessql.services.notebook import _workspace as notebook_workspace_service
from pointlessql.types import TableFqn

logger = logging.getLogger(__name__)

router = APIRouter(tags=["home"])


@router.get("/api/search")
async def api_search(request: Request, q: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """Aggregate global search hits for the Cmd+K command palette.

    Merges catalog / schema / table / federation objects from soyuz with
    local jobs, dashboards, and (for admins) workspace notebooks. Scoring
    favours prefix matches over substring matches; ties resolve by
    ``updated_at`` descending. An empty query returns ``[]``; the frontend
    renders the localStorage recent-searches in that case so we avoid the
    roundtrip entirely.

    Each soyuz source is wrapped individually: a partial outage (e.g. the
    connections list is momentarily 502) degrades to "those hits missing"
    rather than 502'ing the whole palette, which would make the shortcut
    disproportionately fragile for a supplementary navigation surface.
    """
    raw = q.strip()
    if not raw:
        return []
    limit = max(1, min(int(limit), 100))

    # Slack convention.  ``@<term>``
    # narrows to ``user`` results; ``#<term>`` narrows to ``topic``
    # results.  The leading sigil is stripped before scoring; a bare
    # ``@`` or ``#`` (no term) lists every member of the selected kind
    # — matches the Slack/Linear muscle-memory for "show me people /
    # topics" without making the user type a substring first.
    kind_filter: str | None = None
    if raw.startswith("@"):
        kind_filter = "user"
        raw = raw[1:]
    elif raw.startswith("#"):
        kind_filter = "topic"
        raw = raw[1:]
    needle = raw.casefold()
    if not needle and kind_filter is None:
        return []

    user = get_user(request)
    client = get_uc_client(request)
    workspace_id = int(getattr(request.state, "workspace_id", 0) or 0)

    async def _soyuz_tree() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            tree = await client.get_tree()
        except PointlessSQLError:
            logger.warning("search: soyuz tree unavailable", exc_info=True)
            return out
        for cat in tree:
            cat_name = str(cat.get("name") or "")
            cat_score = score_match(needle, cat_name)
            if cat_score is not None:
                out.append(
                    {
                        "type": "catalog",
                        "label": cat_name,
                        "description": str(cat.get("comment") or ""),
                        "url": f"/catalogs/{cat_name}",
                        "updated_at": epoch_seconds(cat.get("updated_at")),
                        "score": cat_score,
                    },
                )
            schemas_raw = cast(list[dict[str, Any]], cat.get("schemas") or [])
            for schema in schemas_raw:
                s_name = str(schema.get("name") or "")
                s_score = score_match(needle, s_name)
                if s_score is not None:
                    out.append(
                        {
                            "type": "schema",
                            "label": f"{cat_name}.{s_name}",
                            "description": str(schema.get("comment") or ""),
                            "url": f"/catalogs/{cat_name}/schemas/{s_name}",
                            "updated_at": epoch_seconds(schema.get("updated_at")),
                            "score": s_score,
                        },
                    )
                tables_raw = cast(list[dict[str, Any]], schema.get("tables") or [])
                for table in tables_raw:
                    t_name = str(table.get("name") or "")
                    t_score = score_match(needle, t_name)
                    if t_score is None:
                        continue
                    out.append(
                        {
                            "type": "table",
                            "label": TableFqn.from_parts(cat_name, s_name, t_name),
                            "description": str(table.get("comment") or ""),
                            "url": (f"/catalogs/{cat_name}/schemas/{s_name}/tables/{t_name}"),
                            "updated_at": epoch_seconds(table.get("updated_at")),
                            "score": t_score,
                        },
                    )
        return out

    async def _soyuz_federation() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        sources: list[tuple[str, Any, str]] = [
            ("connection", client.list_connections, "/connections/{name}"),
            ("credential", client.list_credentials, "/credentials/{name}"),
            (
                "external_location",
                client.list_external_locations,
                "/external-locations/{name}",
            ),
        ]
        for type_name, fetcher, url_tmpl in sources:
            try:
                rows = await fetcher()
            except PointlessSQLError:
                logger.warning("search: %s list unavailable", type_name, exc_info=True)
                continue
            for row in rows:
                name = str(row.get("name") or "")
                score = score_match(needle, name)
                if score is None:
                    continue
                out.append(
                    {
                        "type": type_name,
                        "label": name,
                        "description": str(row.get("comment") or ""),
                        "url": url_tmpl.format(name=name),
                        "updated_at": epoch_seconds(row.get("updated_at")),
                        "score": score,
                    },
                )
        return out

    def _local_jobs() -> list[dict[str, Any]]:
        from sqlalchemy import select as _select

        from pointlessql.models import Job as JobModel

        out: list[dict[str, Any]] = []
        factory = request.app.state.session_factory
        with factory() as session:
            stmt = _select(JobModel)
            if not user.get("is_admin"):
                stmt = stmt.where(JobModel.run_as_user_id == user["id"])
            for row in session.scalars(stmt).all():
                score = score_match(needle, row.name)
                if score is None:
                    continue
                out.append(
                    {
                        "type": "job",
                        "label": row.name,
                        "description": f"{row.kind} · {row.cron_expr}",
                        "url": f"/jobs/{row.id}",
                        "updated_at": epoch_seconds(row.updated_at),
                        "score": score,
                    },
                )
        return out

    def _local_dashboards() -> list[dict[str, Any]]:
        from sqlalchemy import select as _select

        from pointlessql.models import Dashboard as DashboardModel

        out: list[dict[str, Any]] = []
        factory = request.app.state.session_factory
        with factory() as session:
            for row in session.scalars(_select(DashboardModel)).all():
                title_score = score_match(needle, row.title)
                slug_score = score_match(needle, row.slug)
                score = title_score
                if slug_score is not None and (score is None or slug_score > score):
                    score = slug_score
                if score is None:
                    continue
                out.append(
                    {
                        "type": "dashboard",
                        "label": row.title,
                        "description": row.description or row.slug,
                        "url": f"/dashboards/{row.slug}",
                        "updated_at": epoch_seconds(row.updated_at),
                        "score": score,
                    },
                )
        return out

    def _local_notebooks() -> list[dict[str, Any]]:
        # Matches the admin boundary on /api/notebooks/tree.
        if not user.get("is_admin"):
            return []
        settings_obj: Settings = request.app.state.settings
        try:
            tree = notebook_workspace_service.list_workspace_tree(
                settings_obj.jupyter.notebooks_dir.resolve(),
            )
        except Exception:  # noqa: BLE001 — search must never fail the page
            logger.warning("search: notebook tree unavailable", exc_info=True)
            return []
        out: list[dict[str, Any]] = []

        def _walk(nodes: list[dict[str, Any]]) -> None:
            for node in nodes:
                kind = node.get("kind")
                if kind == "notebook":
                    name = str(node.get("name") or "")
                    path = str(node.get("path") or "")
                    score = score_match(needle, name) or score_match(needle, path)
                    if score is None:
                        continue
                    out.append(
                        {
                            "type": "notebook",
                            "label": name,
                            "description": path,
                            "url": f"/notebooks/workspace?path={path}",
                            "updated_at": 0.0,
                            "score": score,
                        },
                    )
                elif kind == "dir":
                    children = cast(list[dict[str, Any]], node.get("children") or [])
                    _walk(children)

        _walk(tree)
        return out

    def _local_phase80(  # noqa: C901 — flat dispatch over 8 entity kinds
    ) -> list[dict[str, Any]]:
        """Search the entity kinds.

        Covers data products, topics, issues, users, agents,
        workspaces, and saved queries.

        Best-effort: any model missing on an upgrade race or DB
        hiccup downgrades to an empty list rather than 502-ing the
        palette.  All queries are workspace-scoped where the model
        carries ``workspace_id``.
        """
        out: list[dict[str, Any]] = []
        factory = request.app.state.session_factory
        try:
            from sqlalchemy import or_
            from sqlalchemy import select as _select

            from pointlessql.models import (
                Agent,
                DataProduct,
                SavedQuery,
                Topic,
                Workspace,
            )
            from pointlessql.models.auth import User
            from pointlessql.models.social._issue import Issue
            from pointlessql.models.workspace._core import WorkspaceMember

            with factory() as session:
                # Data products
                dp_stmt = _select(DataProduct)
                if workspace_id:
                    dp_stmt = dp_stmt.where(DataProduct.workspace_id == workspace_id)
                for row in session.scalars(dp_stmt).all():
                    fqn = f"{row.catalog_name}.{row.schema_name}"
                    score = score_match(needle, fqn) or score_match(needle, row.description or "")
                    if score is None:
                        continue
                    out.append(
                        {
                            "type": "data_product",
                            "label": fqn,
                            "description": (row.description or "")[:120],
                            "url": (f"/data-products/{row.catalog_name}/{row.schema_name}"),
                            "updated_at": epoch_seconds(getattr(row, "updated_at", None)),
                            "score": score,
                        },
                    )
                # Topics
                topic_stmt = _select(Topic)
                if workspace_id:
                    topic_stmt = topic_stmt.where(Topic.workspace_id == workspace_id)
                for row in session.scalars(topic_stmt).all():
                    name = getattr(row, "display_name", None) or row.slug
                    desc = getattr(row, "description_md", "") or ""
                    score = (
                        score_match(needle, name)
                        or score_match(needle, row.slug)
                        or score_match(needle, desc)
                    )
                    if score is None:
                        continue
                    out.append(
                        {
                            "type": "topic",
                            "label": name,
                            "description": desc[:120],
                            "url": f"/topics/{row.slug}",
                            "updated_at": epoch_seconds(getattr(row, "created_at", None)),
                            "score": score,
                        },
                    )
                # Issues
                issue_stmt = _select(Issue)
                if workspace_id:
                    issue_stmt = issue_stmt.where(Issue.workspace_id == workspace_id)
                for row in session.scalars(issue_stmt).all():
                    title = getattr(row, "title", "")
                    score = score_match(needle, title)
                    if score is None:
                        continue
                    out.append(
                        {
                            "type": "issue",
                            "label": f"#{row.id}: {title}",
                            "description": getattr(row, "state", "") or "",
                            "url": f"/issues/{row.id}",
                            "updated_at": epoch_seconds(getattr(row, "updated_at", None)),
                            "score": score,
                        },
                    )
                # Users (workspace members)
                user_stmt = _select(User).join(
                    WorkspaceMember,
                    WorkspaceMember.user_id == User.id,
                )
                if workspace_id:
                    user_stmt = user_stmt.where(WorkspaceMember.workspace_id == workspace_id)
                for row in session.scalars(user_stmt).all():
                    score = score_match(needle, row.display_name or "") or score_match(
                        needle, row.email
                    )
                    if score is None:
                        continue
                    out.append(
                        {
                            "type": "user",
                            "label": row.display_name or row.email,
                            "description": row.email,
                            "url": f"/users/{row.id}",
                            "updated_at": epoch_seconds(getattr(row, "created_at", None)),
                            "score": score,
                        },
                    )
                # Agents
                agent_stmt = _select(Agent)
                if workspace_id:
                    agent_stmt = agent_stmt.where(Agent.workspace_id == workspace_id)
                for row in session.scalars(agent_stmt).all():
                    slug = getattr(row, "slug", "")
                    name = getattr(row, "display_name", None) or slug
                    score = score_match(needle, slug) or score_match(needle, name)
                    if score is None:
                        continue
                    out.append(
                        {
                            "type": "agent",
                            "label": name,
                            "description": slug,
                            "url": f"/agents/{slug}",
                            "updated_at": epoch_seconds(getattr(row, "updated_at", None)),
                            "score": score,
                        },
                    )
                # Workspaces the caller is a member of
                ws_stmt = (
                    _select(Workspace)
                    .join(
                        WorkspaceMember,
                        WorkspaceMember.workspace_id == Workspace.id,
                    )
                    .where(WorkspaceMember.user_id == user["id"])
                )
                for row in session.scalars(ws_stmt).all():
                    name = getattr(row, "name", row.slug)
                    score = score_match(needle, name) or score_match(needle, row.slug)
                    if score is None:
                        continue
                    out.append(
                        {
                            "type": "workspace",
                            "label": name,
                            "description": f"slug: {row.slug}",
                            "url": f"/workspaces/{row.slug}",
                            "updated_at": epoch_seconds(getattr(row, "updated_at", None)),
                            "score": score,
                        },
                    )
                # Saved queries (the saved_queries table powers
                # /audit/queries + SQL editor saves)
                try:
                    sq_stmt = _select(SavedQuery)
                    for row in session.scalars(sq_stmt).all():
                        title = getattr(row, "title", "") or ""
                        body = getattr(row, "sql_body", "") or ""
                        score = score_match(needle, title) or score_match(needle, body[:200])
                        if score is None:
                            continue
                        out.append(
                            {
                                "type": "saved_query",
                                "label": title or f"query #{row.id}",
                                "description": (body or "")[:120],
                                "url": f"/audit/queries/{row.id}",
                                "updated_at": epoch_seconds(getattr(row, "updated_at", None)),
                                "score": score,
                            },
                        )
                except Exception:  # noqa: BLE001 — SavedQuery may not exist
                    # bare-broad-ok: SavedQuery rows are best-effort —
                    # an upgrade-race or partial schema downgrades to
                    # empty saved-query hits without breaking the palette.
                    logger.debug("search: saved-query block failed", exc_info=True)
                _ = or_  # marker the import is intentional
        except Exception:  # noqa: BLE001 — palette must never fail the page
            logger.debug("search: phase 80.6 entity search failed", exc_info=True)
            return []
        return out

    tree_hits, fed_hits = await asyncio.gather(_soyuz_tree(), _soyuz_federation())
    hits: list[dict[str, Any]] = []
    hits.extend(tree_hits)
    hits.extend(fed_hits)
    hits.extend(_local_jobs())
    hits.extend(_local_dashboards())
    hits.extend(_local_notebooks())
    hits.extend(_local_phase80())

    if kind_filter is not None:
        hits = [h for h in hits if h["type"] == kind_filter]

    hits.sort(key=lambda h: (-float(h["score"]), -float(h["updated_at"])))
    return hits[:limit]
