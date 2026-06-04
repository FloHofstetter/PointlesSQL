"""DB-backed Bearer-token API-key store.

API keys are persisted in the ``api_keys`` table so admins can
rotate them without a process restart and so the ``supervisor``
scope gating supervisor-only routes lives next to the secret it
authorises.

The legacy ``POINTLESSQL_API_KEYS`` env var stays valid as a
*bootstrap* path: every server start spills declared
``name:secret[:supervisor]`` pairs into the table idempotently via
:func:`bootstrap_from_env`, so clean-machine ``docker-compose``
deployments without an admin UI mounted still work.

Token verification uses :func:`hashlib.sha256` on the presented
secret and compares against the indexed ``secret_hash`` column.
API keys are high-entropy random tokens; SHA-256 is enough.

The implementation is split into focused sub-modules and re-exported
here so callers keep importing from ``pointlessql.services.api_keys``:

* ``_cache``  — :class:`KeyEntry`, the TTL verify cache, ``invalidate_cache``.
* ``_verify`` — ``verify_bearer`` (request hot path) + scope rechecks.
* ``_crud``   — create / revoke / list / rotate / quarantine / ttl + bootstrap.
"""

from __future__ import annotations

from pointlessql.services.api_keys._cache import KeyEntry, invalidate_cache
from pointlessql.services.api_keys._crud import (
    bootstrap_from_env,
    create_api_key,
    list_api_keys,
    parse_keys,
    quarantine_api_key,
    revoke_api_key,
    rotate_api_key,
    unquarantine_api_key,
    update_api_key_ttl,
)
from pointlessql.services.api_keys._verify import (
    is_auditor,
    is_supervisor,
    verify_bearer,
)

__all__ = [
    "KeyEntry",
    "bootstrap_from_env",
    "create_api_key",
    "invalidate_cache",
    "is_auditor",
    "is_supervisor",
    "list_api_keys",
    "parse_keys",
    "quarantine_api_key",
    "revoke_api_key",
    "rotate_api_key",
    "unquarantine_api_key",
    "update_api_key_ttl",
    "verify_bearer",
]
