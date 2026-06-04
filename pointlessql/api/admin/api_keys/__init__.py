"""Admin CRUD for the ``api_keys`` table — package facade.

Three JSON concerns, all gated by :func:`require_admin`.  Plaintext
secrets are returned exactly once — at create time — and never
re-readable.  Revocation is soft (``revoked_at`` set; row stays so
historical audit attribution still resolves).

The previous flat ``api_keys.py`` module is split into per-concern
sub-modules behind one combined router so existing imports like
``from pointlessql.api.admin.api_keys import router`` keep working:

* ``keys``   — key CRUD + lifecycle (create / revoke / rotate / ttl).
* ``grants`` — per-key catalog + IP grant CRUD.
* ``usage``  — per-key usage summary.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.admin.api_keys.grants import router as _grants_router
from pointlessql.api.admin.api_keys.keys import router as _keys_router
from pointlessql.api.admin.api_keys.usage import router as _usage_router

router = APIRouter(tags=["admin-api-keys"])
router.include_router(_keys_router)
router.include_router(_grants_router)
router.include_router(_usage_router)

__all__ = ["router"]
