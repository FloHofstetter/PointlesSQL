"""Connection-options merging + libpq DSN construction."""

from __future__ import annotations

import re
from typing import Any

from pointlessql.exceptions import ValidationError

# Options that look like secrets are never read from the free-form
# connection ``options`` dict — they must come from a bound Credential.
# Case-insensitive: ``password``, ``PASS``, ``api_secret``, ``token``,
# ``access_key`` all match. ``key`` is intentionally broad because
# ``api_key``, ``private_key``, ``license_key`` all legitimately
# classify as secrets.
_SECRET_KEY_RE = re.compile(r"pass|secret|key|token", re.IGNORECASE)


def effective_options(
    connection: dict[str, Any], credential: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge connection options with secrets read from a Credential.

    The sprint contract: options with keys matching
    ``(?i)pass|secret|key|token`` are read from the bound Credential's
    ``additional_properties`` (the generated client's catch-all for
    non-spec fields — see ADR-0013 in soyuz-catalog). Non-secret
    options stay on the Connection's ``options`` dict. Missing
    Credential falls back to ``options`` so a local dev Postgres can
    skip the ceremony entirely.

    Args:
        connection: Raw ``ConnectionInfo.to_dict()`` payload.
        credential: Raw ``CredentialInfo.to_dict()`` payload or
            ``None`` when no credential is bound.

    Returns:
        The merged options dict, with secret keys overridden by the
        Credential when one is present.
    """
    options: dict[str, Any] = dict(connection.get("options") or {})
    if credential is None:
        return options
    # additional_properties is where soyuz stashes non-spec fields
    # like postgres-flavour secrets.
    cred_extras: dict[str, Any] = dict(credential.get("additional_properties") or {})
    for key, value in cred_extras.items():
        if _SECRET_KEY_RE.search(key):
            options[key] = value
    return options


def build_dsn(options: dict[str, Any]) -> str:
    """Translate a connection options dict to a libpq DSN string.

    Accepts the Databricks-style UC keys (``host``, ``port``,
    ``database``, ``user``, ``password``) as well as the raw libpq
    ``dbname``. Missing ``host`` is fatal because we would silently
    connect to localhost — better to fail fast with a clear error.

    Args:
        options: Merged connection options (see
            :func:`effective_options`).

    Returns:
        A space-separated ``key=value`` libpq DSN.

    Raises:
        ValidationError: When a required key (``host``) is missing.
    """
    host = options.get("host")
    if not host:
        raise ValidationError("Postgres connection options missing required key 'host'")
    pairs: list[str] = [f"host={host}"]
    port = options.get("port")
    if port:
        pairs.append(f"port={port}")
    database = options.get("database") or options.get("dbname")
    if database:
        pairs.append(f"dbname={database}")
    user = options.get("user")
    if user:
        pairs.append(f"user={user}")
    password = options.get("password")
    if password:
        pairs.append(f"password={password}")
    return " ".join(pairs)
