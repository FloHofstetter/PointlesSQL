"""API-key token format v1.

PointlesSQL's professional Bearer-token format, modelled after
Stripe + GitHub PAT v2:

```
pql_{env}_v1_{body40}_{crc8}
```

- ``pql``   — issuer prefix (constant, lowercase)
- ``{env}`` — ``live`` or ``test`` (test keys are visually distinct
  in audit logs; refusal-in-production gating is deferred)
- ``v1``    — format-version literal (parser keys off this exact
  token; future v2 bumps don't break v1 verification)
- ``{body40}`` — 40 chars from base62 (``A-Za-z0-9``), random;
  ≥235 bits of entropy
- ``{crc8}`` — 8 lowercase hex chars of ``CRC32(prefix_body)`` for
  offline secret-scanner validation; invalid CRC short-circuits
  ``verify_bearer`` before any DB roundtrip

Legacy keys (``secrets.token_urlsafe(32)``, 43-char base64-url)
coexist forever — :func:`parse_v1_token` returns ``None`` for them
and the caller falls back to the legacy SHA-256 lookup path.

The GitHub Secret Scanning Partner Program regex is exported as
:data:`V1_REGEX` so the format spec doc and the partner-program
registration form pull from one source of truth.
"""

from __future__ import annotations

import re
import secrets
import string
import zlib
from typing import Final, Literal

#: Allowed env tokens for the v1 format.  Lowercase, fixed-list.
_ENV_VALUES: Final[frozenset[str]] = frozenset({"live", "test"})

#: Base62 alphabet for the random body.
_BODY_ALPHABET: Final[str] = string.ascii_letters + string.digits

#: Length of the random body in characters.  40 base62 chars ≈ 238 bits.
_BODY_LEN: Final[int] = 40

#: Format-version literal embedded in every v1 token.
_VERSION: Final[str] = "v1"

#: GitHub Secret Scanning Partner Program regex for the v1 format.
V1_REGEX: Final[str] = r"pql_(live|test)_v1_[A-Za-z0-9]{40}_[0-9a-f]{8}"

_V1_PATTERN: Final[re.Pattern[str]] = re.compile(f"^{V1_REGEX}$")


def _crc8_for(prefix_body: str) -> str:
    """Return the 8-char lowercase hex CRC32 of *prefix_body*.

    Args:
        prefix_body: Everything before the trailing ``_{crc8}``
            segment, e.g. ``pql_live_v1_xK3aB7nQ...vI4o``.

    Returns:
        Zero-padded 8-char lowercase hex string.
    """
    return f"{zlib.crc32(prefix_body.encode('utf-8')) & 0xFFFFFFFF:08x}"


def generate_v1_token(env: Literal["live", "test"] = "live") -> str:
    """Mint a fresh ``pql_{env}_v1_{body40}_{crc8}`` token.

    Args:
        env: One of ``'live'`` or ``'test'``.  Defaults to ``'live'``.

    Returns:
        The full plaintext token.  Caller is responsible for
        SHA-256-hashing it before persistence.

    Raises:
        ValueError: When *env* is not ``'live'`` or ``'test'``.
    """
    if env not in _ENV_VALUES:
        raise ValueError(f"env must be one of {sorted(_ENV_VALUES)}, got {env!r}")
    body = "".join(secrets.choice(_BODY_ALPHABET) for _ in range(_BODY_LEN))
    prefix_body = f"pql_{env}_{_VERSION}_{body}"
    return f"{prefix_body}_{_crc8_for(prefix_body)}"


def parse_v1_token(token: str) -> tuple[Literal["live", "test"], str, str] | None:
    """Validate + decompose a v1 token.

    Format checked via the same regex registered with GitHub Secret
    Scanning.  CRC is validated against the body so a typo'd or
    truncated token short-circuits before any DB lookup.

    Args:
        token: Candidate Bearer secret.

    Returns:
        ``(env, body, crc8)`` triple when *token* matches the v1
        format and CRC validates; ``None`` otherwise (legacy keys,
        malformed input, bad CRC).
    """
    if not token:
        return None
    if _V1_PATTERN.match(token) is None:
        return None
    # ``split("_")`` on a v1 token yields exactly five parts:
    # ['pql', env, 'v1', body, crc].  The regex above already guarantees
    # the shape so the length check is defence-in-depth, not load-bearing.
    parts = token.split("_")
    if len(parts) != 5:
        return None
    _issuer, env_raw, _version, body, crc = parts
    prefix_body = f"pql_{env_raw}_{_VERSION}_{body}"
    if _crc8_for(prefix_body) != crc:
        return None
    env: Literal["live", "test"] = "live" if env_raw == "live" else "test"
    return env, body, crc


def display_prefix_for(token: str) -> str:
    """Return the human-visible prefix to store in ``secret_prefix``.

    For v1 tokens this is the issuer + env + version + first 10 chars
    of the body — enough to disambiguate keys in the UI without
    revealing the full secret.  For legacy tokens it falls back to
    the original 8-char prefix.

    Args:
        token: Full plaintext token.

    Returns:
        Up to 24 chars (v1) or exactly 8 chars (legacy).
    """
    parsed = parse_v1_token(token)
    if parsed is None:
        return token[:8]
    env, body, _crc = parsed
    return f"pql_{env}_{_VERSION}_{body[:10]}"


__all__ = [
    "V1_REGEX",
    "display_prefix_for",
    "generate_v1_token",
    "parse_v1_token",
]
