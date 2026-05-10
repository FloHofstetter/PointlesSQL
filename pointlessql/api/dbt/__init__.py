"""dbt route surface, split per concern.

Three flat sibling modules (dbt_routes 1059 + dbt_html_routes 52
+ dbt_proxy 111 = 1222 LOC) consolidated into one
``pointlessql.api.dbt`` package whose ``__init__.py`` composes the
combined router.

Layout:

* ``routes`` — ``/api/dbt/*`` execution + project-management API.
* ``html``   — ``/dbt/*`` UI page renderers.
* ``proxy``  — reverse-proxy for the embedded ``dbt docs`` server
                 (the hosted-docs subprocess output).
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.dbt.html import router as _html_router
from pointlessql.api.dbt.proxy import router as _proxy_router
from pointlessql.api.dbt.routes import router as _routes_router

router = APIRouter()
router.include_router(_routes_router)
router.include_router(_html_router)
router.include_router(_proxy_router)

__all__ = ["router"]
