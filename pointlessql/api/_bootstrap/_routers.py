"""Centralised ``app.include_router(...)`` block.

One function — :func:`register_routers` — that takes a ``FastAPI``
app and mounts every PointlesSQL route bundle on it.  The 34
imports + 34 ``include_router`` calls used to live inline in
``api/main.py``; lifting them here keeps ``main.py`` focused on
lifecycle (lifespan + filters + middleware) and makes adding a new
top-level route bundle a one-line edit instead of editing two
sections.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI


def register_routers(app: FastAPI) -> None:
    """Mount every top-level route bundle on ``app``.

    Imported routers are local to this function so the import graph
    stays inside the bootstrap call rather than the module's
    top-level — this keeps ``api.main``'s cold-start identical to
    the pre-split shape (each router module loads exactly once,
    when ``main.py`` calls us).
    """
    from pointlessql.api.admin import router as admin_router
    from pointlessql.api.agent_reviews_routes import router as agent_reviews_router
    from pointlessql.api.agent_runs_routes import router as agent_runs_router
    from pointlessql.api.agents_html_routes import router as agents_html_router
    from pointlessql.api.agents_routes import router as agents_router
    from pointlessql.api.alerts_routes import router as alerts_router
    from pointlessql.api.audit import router as audit_router
    from pointlessql.api.auth_routes import router as auth_router
    from pointlessql.api.branches_routes import router as branches_router
    from pointlessql.api.catalog_html_routes import router as catalog_html_router
    from pointlessql.api.catalog_routes import router as catalog_router
    from pointlessql.api.conventions_routes import router as conventions_router
    from pointlessql.api.dashboards_routes import router as dashboards_router
    from pointlessql.api.data_products_html_routes import (
        router as data_products_html_router,
    )
    from pointlessql.api.data_products_routes import router as data_products_router
    from pointlessql.api.dbt import router as dbt_router
    from pointlessql.api.federation_routes import router as federation_router
    from pointlessql.api.feed_html_routes import router as feed_html_router
    from pointlessql.api.feed_routes import router as feed_router
    from pointlessql.api.governance_routes import router as governance_router
    from pointlessql.api.home_routes import router as home_router
    from pointlessql.api.jobs_routes import router as jobs_router
    from pointlessql.api.lens import router as lens_router
    from pointlessql.api.lineage import router as lineage_router
    from pointlessql.api.mcp import router as mcp_router
    from pointlessql.api.me_routes import router as me_router
    from pointlessql.api.me_subscriptions_routes import (
        router as me_subscriptions_router,
    )
    from pointlessql.api.ml_routes import router as ml_router
    from pointlessql.api.mlflow_html_routes import router as mlflow_html_router
    from pointlessql.api.mlflow_proxy import router as mlflow_proxy_router
    from pointlessql.api.models_html_routes import router as models_html_router
    from pointlessql.api.models_routes import router as models_router
    from pointlessql.api.notebook_kernel_ws import router as notebook_kernel_ws_router
    from pointlessql.api.notebooks_routes import router as notebooks_router
    from pointlessql.api.notifications_routes import router as notifications_router
    from pointlessql.api.pql_introspect_routes import router as pql_introspect_router
    from pointlessql.api.pql_training_routes import router as pql_training_router
    from pointlessql.api.review_destinations_routes import (
        router as review_destinations_router,
    )
    from pointlessql.api.runs_routes import router as runs_router
    from pointlessql.api.saved_audit_queries_routes import (
        router as saved_audit_queries_router,
    )
    from pointlessql.api.settings_routes import router as settings_router
    from pointlessql.api.sql import router as sql_router
    from pointlessql.api.time_travel_routes import router as time_travel_router
    from pointlessql.api.topics_html_routes import router as topics_html_router
    from pointlessql.api.topics_routes import router as topics_router
    from pointlessql.api.users_html_routes import router as users_html_router
    from pointlessql.api.users_routes import router as users_router
    from pointlessql.api.volumes_routes import router as volumes_router
    from pointlessql.api.webhook_routes import router as webhook_router

    app.include_router(auth_router)
    app.include_router(catalog_router)
    app.include_router(catalog_html_router)
    app.include_router(conventions_router)
    app.include_router(sql_router)
    app.include_router(alerts_router)
    app.include_router(audit_router)
    app.include_router(saved_audit_queries_router)
    app.include_router(volumes_router)
    app.include_router(lineage_router)
    app.include_router(time_travel_router)
    app.include_router(governance_router)
    app.include_router(notebooks_router)
    app.include_router(notebook_kernel_ws_router)
    app.include_router(runs_router)
    app.include_router(agent_runs_router)
    app.include_router(agent_reviews_router)
    app.include_router(branches_router)
    app.include_router(pql_introspect_router)
    app.include_router(pql_training_router)
    app.include_router(federation_router)
    app.include_router(jobs_router)
    app.include_router(dashboards_router)
    app.include_router(home_router)
    app.include_router(admin_router)
    app.include_router(review_destinations_router)
    app.include_router(ml_router)
    app.include_router(mlflow_html_router)
    app.include_router(mlflow_proxy_router)
    app.include_router(dbt_router)
    app.include_router(models_router)
    app.include_router(models_html_router)
    app.include_router(data_products_router)
    app.include_router(data_products_html_router)
    app.include_router(notifications_router)
    app.include_router(me_router)
    app.include_router(me_subscriptions_router)
    app.include_router(users_router)
    app.include_router(users_html_router)
    app.include_router(topics_router)
    app.include_router(topics_html_router)
    app.include_router(feed_router)
    app.include_router(feed_html_router)
    app.include_router(settings_router)
    app.include_router(agents_router)
    app.include_router(agents_html_router)
    app.include_router(webhook_router)
    app.include_router(lens_router)
    app.include_router(mcp_router)
