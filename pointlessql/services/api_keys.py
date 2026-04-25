"""Bearer-token API-key gate (Sprint 13.7.0.5).

Front-loaded as part of Phase 13.7 so the
``hermes-plugin-pointlessql`` Bearer-token client lands without a
parallel "localhost-trust then API-key" migration. Closes the
multi-tenant auth gap recorded as Tier-3 in
``project_phase13_audit_gaps.md`` ahead of the Phase-14 visibility
flip.

The gate is configured through a single env var
``POINTLESSQL_API_KEYS`` whose value is a list of
``name:secret`` pairs separated by newline OR comma. When the var
is empty / unset the gate is disabled and Bearer headers are
ignored — this preserves the local-dev / single-user
``agent_drift_monitor`` walkthrough that has no Bearer to send.

Token verification uses :func:`hmac.compare_digest` to avoid
character-by-character timing leaks. Names are returned to the
caller for audit attribution; secrets never leave this module.
"""

from __future__ import annotations

import hmac
import logging
import os

logger = logging.getLogger(__name__)


def parse_keys(raw: str | None) -> dict[str, str]:
    """Parse the ``POINTLESSQL_API_KEYS`` env value.

    Accepts ``name:secret`` pairs separated by newlines and / or
    commas. Whitespace around each pair is stripped; empty pairs
    are silently dropped. Duplicate names raise — silent overwrite
    would mask a deployment typo.

    Args:
        raw: The raw env-var value, or ``None`` when the variable
            is unset.

    Returns:
        A mapping ``{name: secret}``. Empty when the gate should
        stay disabled (raw value missing or whitespace-only).

    Raises:
        ValueError: When a pair lacks a colon, when the name or
            secret is empty after stripping, or when the same name
            appears twice.
    """
    if raw is None or not raw.strip():
        return {}
    keys: dict[str, str] = {}
    for chunk in raw.replace(",", "\n").splitlines():
        pair = chunk.strip()
        if not pair:
            continue
        if ":" not in pair:
            raise ValueError(
                f"POINTLESSQL_API_KEYS entry {pair!r} must be in "
                f"'name:secret' form"
            )
        name, _, secret = pair.partition(":")
        name = name.strip()
        secret = secret.strip()
        if not name or not secret:
            raise ValueError(
                f"POINTLESSQL_API_KEYS entry {pair!r} has an empty "
                f"name or secret"
            )
        if name in keys:
            raise ValueError(
                f"POINTLESSQL_API_KEYS entry name {name!r} is "
                f"duplicated"
            )
        keys[name] = secret
    return keys


def load_from_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """Read and parse ``POINTLESSQL_API_KEYS`` from the process env.

    Args:
        env: Optional override for tests. Defaults to
            :data:`os.environ`.

    Returns:
        The parsed key mapping (possibly empty).
    """
    source = env if env is not None else os.environ
    return parse_keys(source.get("POINTLESSQL_API_KEYS"))


def verify_bearer(
    authorization_header: str | None,
    keys: dict[str, str],
) -> str | None:
    """Match an ``Authorization: Bearer <secret>`` header to a key.

    Args:
        authorization_header: Raw value of the ``Authorization``
            HTTP header, or ``None`` when absent.
        keys: The mapping returned by :func:`parse_keys` /
            :func:`load_from_env`.

    Returns:
        The matched key name, or ``None`` when the header is
        missing, malformed, or the secret does not match any
        configured key. ``None`` is also returned when ``keys`` is
        empty (gate disabled) so the caller can short-circuit.
    """
    if not keys or not authorization_header:
        return None
    header = authorization_header.strip()
    if not header.lower().startswith("bearer "):
        return None
    presented = header[7:].strip()
    if not presented:
        return None
    presented_bytes = presented.encode("utf-8")
    for name, secret in keys.items():
        if hmac.compare_digest(presented_bytes, secret.encode("utf-8")):
            return name
    return None


def is_enabled(keys: dict[str, str]) -> bool:
    """Return ``True`` when the gate is configured.

    Args:
        keys: The key mapping (typically pulled from
            ``app.state.api_keys``).

    Returns:
        ``True`` iff at least one ``name:secret`` pair was parsed.
    """
    return bool(keys)
