"""Per-output-port identity assertion (E10).

Reads the ``identity_requirements`` JSON on an output port and checks
the calling principal carries the declared OIDC audiences, API-key
scopes and minimum role.  Surfaces failures via
:class:`PortIdentityViolation` (subclass of
:class:`PermissionDeniedError` so the central error map renders 403).
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from pointlessql.exceptions import PermissionDeniedError

#: Valid role rank — higher position == more privileged.
ROLE_RANK: dict[str, int] = {
    "viewer": 0,
    "consumer": 1,
    "steward": 2,
    "admin": 3,
}


@dataclasses.dataclass(frozen=True)
class IdentityRequirements:
    """Parsed shape of the ``identity_requirements`` JSON.

    Attributes:
        oidc_audiences: Acceptable OIDC ``aud`` values (any-match).
        required_scopes: API-key scopes the caller must carry (all-match).
        min_role: Minimum role name from :data:`ROLE_RANK`.
    """

    oidc_audiences: tuple[str, ...]
    required_scopes: tuple[str, ...]
    min_role: str | None


class PortIdentityViolation(PermissionDeniedError):
    """Strict-mode signal: caller does not satisfy identity-requirements.

    Surfaces via the central error-handler as HTTP 403 with the
    failing constraint name in ``detail``.
    """

    def __init__(self, constraint: str, observed: Any) -> None:
        """Carry the failing constraint + observed value."""
        super().__init__(f"port identity constraint failed: {constraint}")
        self.constraint = constraint
        self.observed = observed

    def extension_members(self) -> dict[str, Any]:
        """Return JSON-serialisable detail for the FastAPI handler."""
        return {"constraint": self.constraint, "observed": self.observed}


def parse_requirements(raw: str | None) -> IdentityRequirements | None:
    """Decode the JSON-Text column.  ``None``/empty → no requirements."""
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except ValueError, TypeError:
        return None
    if not isinstance(payload, dict):
        return None
    audiences = payload.get("oidc_audiences") or []
    scopes = payload.get("required_scopes") or []
    min_role = payload.get("min_role")
    return IdentityRequirements(
        oidc_audiences=tuple(str(a) for a in audiences if a),
        required_scopes=tuple(str(s) for s in scopes if s),
        min_role=str(min_role) if isinstance(min_role, str) else None,
    )


def assert_port_identity(
    *,
    requirements_json: str | None,
    principal: dict[str, Any] | None,
) -> None:
    """Raise :class:`PortIdentityViolation` when the principal does not match.

    ``principal`` is the user-info dict produced by the auth
    middleware; it may carry ``oidc_aud`` (str or list), ``scopes``
    (list[str]), and ``role`` (str).

    No-op when the requirements JSON is empty/unparseable — the port
    is then open as before.

    Args:
        requirements_json: Raw JSON-Text from
            ``data_product_output_ports.identity_requirements``.
        principal: User-info dict; ``None`` means "anonymous".

    Raises:
        PortIdentityViolation: When any constraint fails.
    """
    requirements = parse_requirements(requirements_json)
    if requirements is None:
        return
    if principal is None:
        if requirements.oidc_audiences or requirements.required_scopes or requirements.min_role:
            raise PortIdentityViolation("authentication_required", None)
        return

    if requirements.oidc_audiences:
        raw_aud = principal.get("oidc_aud") or principal.get("aud")
        if isinstance(raw_aud, str):
            observed_audiences = {raw_aud}
        elif isinstance(raw_aud, (list, tuple, set)):
            observed_audiences = {str(a) for a in raw_aud}
        else:
            observed_audiences = set()
        if not (observed_audiences & set(requirements.oidc_audiences)):
            raise PortIdentityViolation("oidc_audiences", sorted(observed_audiences))

    if requirements.required_scopes:
        raw_scopes = principal.get("scopes") or []
        if isinstance(raw_scopes, str):
            observed_scopes = set(raw_scopes.split())
        else:
            observed_scopes = {str(s) for s in raw_scopes}
        missing = set(requirements.required_scopes) - observed_scopes
        if missing:
            raise PortIdentityViolation("required_scopes", sorted(missing))

    if requirements.min_role:
        observed_role = principal.get("role")
        required_rank = ROLE_RANK.get(requirements.min_role, 1_000_000)
        observed_rank = ROLE_RANK.get(str(observed_role or ""), -1)
        if principal.get("is_admin"):
            observed_rank = max(observed_rank, ROLE_RANK["admin"])
        if observed_rank < required_rank:
            raise PortIdentityViolation("min_role", observed_role)
