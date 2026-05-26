"""Threaded discussion routes for data-products — split per surface.

The routes + helpers are organised along the natural axes:

* :mod:`._constants`      — audit-action strings, allowed
  categories/emojis, thread-depth cap, regex patterns.
* :mod:`._mentions`       — ``@email`` and ``@display_name`` extraction
  + DB resolution (including the ambiguous-token reporter).
* :mod:`._helpers`        — body-preview truncation, chain-depth walk,
  reaction aggregation, comment serialization.
* :mod:`._list`           — ``GET /comments`` threaded list.
* :mod:`._post`           — ``POST /comments`` with mention fan-out
  and governance events.
* :mod:`._accept_answer`  — ``POST .../{id}/accept-answer``.
* :mod:`._delete`         — soft-delete via ``DELETE``.

``router`` mounts each sub-router.  The four route handlers are
re-exported here so ``social_routes.comments`` (polymorphic
dispatcher) can keep importing them from
``pointlessql.api.data_products_routes.comments`` unchanged.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.data_products_routes.comments._accept_answer import (
    accept_answer,
)
from pointlessql.api.data_products_routes.comments._accept_answer import (
    router as _accept_answer_router,
)
from pointlessql.api.data_products_routes.comments._delete import (
    delete_data_product_comment,
)
from pointlessql.api.data_products_routes.comments._delete import (
    router as _delete_router,
)
from pointlessql.api.data_products_routes.comments._list import (
    list_data_product_comments,
)
from pointlessql.api.data_products_routes.comments._list import (
    router as _list_router,
)
from pointlessql.api.data_products_routes.comments._post import (
    post_data_product_comment,
)
from pointlessql.api.data_products_routes.comments._post import (
    router as _post_router,
)

router = APIRouter()
router.include_router(_list_router)
router.include_router(_post_router)
router.include_router(_accept_answer_router)
router.include_router(_delete_router)

__all__ = [
    "accept_answer",
    "delete_data_product_comment",
    "list_data_product_comments",
    "post_data_product_comment",
    "router",
]
