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
    from pointlessql.api.access_requests_routes import router as access_requests_router
    from pointlessql.api.admin import router as admin_router
    from pointlessql.api.agent_memory_registry_routes import router as agent_memory_registry_router
    from pointlessql.api.agent_reviews_routes import router as agent_reviews_router
    from pointlessql.api.agent_runs_routes import router as agent_runs_router
    from pointlessql.api.agents_html_routes import router as agents_html_router
    from pointlessql.api.agents_routes import router as agents_router
    from pointlessql.api.alerts_routes import router as alerts_router
    from pointlessql.api.apps_html_routes import router as apps_html_router
    from pointlessql.api.apps_proxy import router as apps_proxy_router
    from pointlessql.api.apps_routes import router as apps_router
    from pointlessql.api.audit import router as audit_router
    from pointlessql.api.auth_routes import router as auth_router
    from pointlessql.api.bi_dashboards_routes import router as bi_dashboards_router
    from pointlessql.api.bi_html_routes import router as bi_html_router
    from pointlessql.api.bi_snapshot_routes import router as bi_snapshot_router
    from pointlessql.api.branches_routes import router as branches_router
    from pointlessql.api.bundles_routes import router as bundles_router
    from pointlessql.api.catalog_html_routes import router as catalog_html_router
    from pointlessql.api.catalog_routes import router as catalog_router
    from pointlessql.api.classification_routes import router as classification_router
    from pointlessql.api.command_center_routes import router as command_center_router
    from pointlessql.api.conventions_routes import router as conventions_router
    from pointlessql.api.csp_report_routes import router as csp_report_router
    from pointlessql.api.dashboards_routes import router as dashboards_router
    from pointlessql.api.data_products_html_routes import (
        router as data_products_html_router,
    )
    from pointlessql.api.data_products_routes import router as data_products_router
    from pointlessql.api.dataframe_studio_routes import (
        html_router as dataframe_studio_html_router,
    )
    from pointlessql.api.dataframe_studio_routes import (
        router as dataframe_studio_router,
    )
    from pointlessql.api.dbt import router as dbt_router
    from pointlessql.api.domains_html_routes import router as domains_html_router
    from pointlessql.api.dp_canvas_coedit_ws import router as dp_canvas_coedit_ws_router
    from pointlessql.api.dp_canvas_html_routes import router as dp_canvas_html_router
    from pointlessql.api.excel_routes import router as excel_router
    from pointlessql.api.external_sql_routes import router as external_sql_router
    from pointlessql.api.federation_routes import router as federation_router
    from pointlessql.api.feed_html_routes import router as feed_html_router
    from pointlessql.api.feed_routes import router as feed_router
    from pointlessql.api.genie_code_routes import router as genie_code_router
    from pointlessql.api.genie_routes import router as genie_router
    from pointlessql.api.glossary_html_routes import router as glossary_html_router
    from pointlessql.api.glossary_relations_routes import (
        router as glossary_relations_router,
    )
    from pointlessql.api.governance_routes import router as governance_router
    from pointlessql.api.health_routes import router as health_router
    from pointlessql.api.help_routes import router as help_router
    from pointlessql.api.hermes_routes import router as hermes_router
    from pointlessql.api.home_routes import router as home_router
    from pointlessql.api.ingest_html_routes import router as ingest_html_router
    from pointlessql.api.ingest_routes import router as ingest_router
    from pointlessql.api.ingest_stream_routes import router as ingest_stream_router
    from pointlessql.api.issues_html_routes import router as issues_html_router
    from pointlessql.api.jobs_routes import router as jobs_router
    from pointlessql.api.lens import router as lens_router
    from pointlessql.api.lineage import router as lineage_router
    from pointlessql.api.lineage_query_routes import (
        router as lineage_query_router,
    )
    from pointlessql.api.mcp import router as mcp_router
    from pointlessql.api.me_routes import router as me_router
    from pointlessql.api.me_subscriptions_routes import (
        router as me_subscriptions_router,
    )
    from pointlessql.api.memory_html_routes import router as memory_html_router
    from pointlessql.api.memory_routes import router as memory_api_router
    from pointlessql.api.mesh_canvas_routes import (
        html_router as mesh_canvas_html_router,
    )
    from pointlessql.api.mesh_canvas_routes import (
        router as mesh_canvas_router,
    )
    from pointlessql.api.mesh_routes import router as mesh_router
    from pointlessql.api.metric_views_routes import router as metric_views_router
    from pointlessql.api.ml_routes import router as ml_router
    from pointlessql.api.mlflow_html_routes import router as mlflow_html_router
    from pointlessql.api.mlflow_proxy import router as mlflow_proxy_router
    from pointlessql.api.models_html_routes import router as models_html_router
    from pointlessql.api.models_routes import router as models_router
    from pointlessql.api.notebook_chat_routes import (
        router as notebook_chat_router,
    )
    from pointlessql.api.notebook_chat_ws import (
        router as notebook_chat_ws_router,
    )
    from pointlessql.api.notebook_coedit_agent_routes import (
        router as notebook_coedit_agent_router,
    )
    from pointlessql.api.notebook_coedit_ws import (
        router as notebook_coedit_ws_router,
    )
    from pointlessql.api.notebook_kernel_ws import router as notebook_kernel_ws_router
    from pointlessql.api.notebooks_routes import router as notebooks_router
    from pointlessql.api.notifications_routes import router as notifications_router
    from pointlessql.api.notifications_stream import router as notifications_stream_router
    from pointlessql.api.online_tables_routes import router as online_tables_router
    from pointlessql.api.pipelines_routes import router as pipelines_router
    from pointlessql.api.pql_introspect_routes import router as pql_introspect_router
    from pointlessql.api.pql_training_routes import router as pql_training_router
    from pointlessql.api.quality_routes import router as quality_router
    from pointlessql.api.review_destinations_routes import (
        router as review_destinations_router,
    )
    from pointlessql.api.runs_routes import router as runs_router
    from pointlessql.api.saved_audit_queries_routes import (
        router as saved_audit_queries_router,
    )
    from pointlessql.api.saved_views_routes import router as saved_views_router
    from pointlessql.api.secrets_routes import router as secrets_router
    from pointlessql.api.serving_html_routes import router as serving_html_router
    from pointlessql.api.serving_routes import router as serving_router
    from pointlessql.api.settings_routes import router as settings_router
    from pointlessql.api.sharing_html_routes import router as sharing_html_router
    from pointlessql.api.sharing_routes import router as sharing_router
    from pointlessql.api.social_routes import router as social_router
    from pointlessql.api.sql import router as sql_router
    from pointlessql.api.sql_chat_routes import router as sql_chat_router
    from pointlessql.api.sql_chat_ws import router as sql_chat_ws_router
    from pointlessql.api.time_travel_routes import router as time_travel_router
    from pointlessql.api.topics_html_routes import router as topics_html_router
    from pointlessql.api.topics_routes import router as topics_router
    from pointlessql.api.users_html_routes import router as users_html_router
    from pointlessql.api.users_routes import router as users_router
    from pointlessql.api.volumes_routes import router as volumes_router
    from pointlessql.api.webhook_routes import router as webhook_router
    from pointlessql.api.workspaces_routes import router as workspaces_public_router

    app.include_router(auth_router)
    app.include_router(catalog_router)
    app.include_router(catalog_html_router)
    app.include_router(conventions_router)
    app.include_router(csp_report_router)
    app.include_router(sql_router)
    app.include_router(sql_chat_router)
    app.include_router(sql_chat_ws_router)
    app.include_router(external_sql_router)
    app.include_router(notebook_chat_router)
    app.include_router(notebook_chat_ws_router)
    app.include_router(alerts_router)
    app.include_router(audit_router)
    app.include_router(saved_audit_queries_router)
    app.include_router(saved_views_router)
    app.include_router(volumes_router)
    app.include_router(lineage_router)
    app.include_router(lineage_query_router)
    app.include_router(time_travel_router)
    app.include_router(governance_router)
    app.include_router(notebooks_router)
    app.include_router(notebook_kernel_ws_router)
    app.include_router(notebook_coedit_ws_router)
    app.include_router(notebook_coedit_agent_router)
    app.include_router(runs_router)
    app.include_router(command_center_router)
    app.include_router(agent_runs_router)
    app.include_router(agent_memory_registry_router)
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
    app.include_router(hermes_router)
    app.include_router(dbt_router)
    app.include_router(models_router)
    app.include_router(models_html_router)
    app.include_router(data_products_router)
    app.include_router(data_products_html_router)
    app.include_router(dp_canvas_html_router)
    app.include_router(dp_canvas_coedit_ws_router)
    app.include_router(domains_html_router)
    app.include_router(glossary_html_router)
    app.include_router(glossary_relations_router)
    app.include_router(mesh_router)
    app.include_router(mesh_canvas_router)
    app.include_router(mesh_canvas_html_router)
    app.include_router(dataframe_studio_router)
    app.include_router(dataframe_studio_html_router)
    app.include_router(social_router)
    app.include_router(issues_html_router)
    app.include_router(notifications_router)
    app.include_router(notifications_stream_router)
    app.include_router(me_router)
    app.include_router(me_subscriptions_router)
    app.include_router(users_router)
    app.include_router(users_html_router)
    app.include_router(topics_router)
    app.include_router(topics_html_router)
    app.include_router(excel_router)
    app.include_router(feed_router)
    app.include_router(feed_html_router)
    app.include_router(settings_router)
    app.include_router(agents_router)
    app.include_router(agents_html_router)
    app.include_router(memory_html_router)
    app.include_router(memory_api_router)
    app.include_router(webhook_router)
    app.include_router(lens_router)
    app.include_router(mcp_router)
    app.include_router(workspaces_public_router)
    app.include_router(ingest_router)
    app.include_router(ingest_html_router)
    app.include_router(secrets_router)
    app.include_router(classification_router)
    app.include_router(quality_router)
    app.include_router(apps_router)
    app.include_router(apps_html_router)
    app.include_router(apps_proxy_router)
    app.include_router(access_requests_router)
    app.include_router(bundles_router)
    app.include_router(bi_dashboards_router)
    app.include_router(bi_snapshot_router)
    app.include_router(bi_html_router)
    app.include_router(metric_views_router)
    app.include_router(pipelines_router)
    app.include_router(genie_code_router)
    app.include_router(genie_router)
    app.include_router(ingest_stream_router)
    app.include_router(online_tables_router)
    app.include_router(serving_html_router)
    app.include_router(sharing_html_router)
    app.include_router(serving_router)
    app.include_router(sharing_router)
    app.include_router(help_router)
    app.include_router(health_router)
