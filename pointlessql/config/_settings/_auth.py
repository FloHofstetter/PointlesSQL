"""Auth + OIDC settings and the group-mapping parser.

Three concerns colocated because they all participate in login-time
identity resolution:

* :class:`AuthSettings` — JWT signing key + rotation grace key.
* :class:`OIDCSettings` — provider discovery + optional group → workspace
  + scope mapping (parsed eagerly at settings construction so a typo
  fails loud at boot rather than silently misrouting users).
* :class:`GroupMapping` — frozen value object holding one parsed entry.

:func:`_parse_group_map` is the parser; :data:`_VALID_SCOPES` is the
scope-name allowlist. Both are module-private — callers consume
``OIDCSettings.parsed_group_map`` instead.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_SECRET_KEY = "change-me-in-production"  # pragma: allowlist secret
"""Public placeholder JWT signing key shipped as the field default.

It lets a fresh ``git clone`` boot on loopback with zero configuration,
but it is public knowledge — anyone could forge a session (including an
admin one) signed with it.  :func:`secret_key_is_insecure` flags it so
the startup gate can refuse it once the server binds a reachable host.
"""

_MIN_SECRET_KEY_LENGTH = 16

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
"""Bind addresses that keep the server unreachable from other hosts.

Booting on one of these is treated as local development, where the
insecure default key is tolerated.
"""


def secret_key_is_insecure(secret_key: str) -> bool:
    """Return whether *secret_key* is unfit to sign production sessions.

    A key is insecure when it is the public
    :data:`INSECURE_DEFAULT_SECRET_KEY` placeholder, empty, or shorter
    than :data:`_MIN_SECRET_KEY_LENGTH` characters — too little entropy
    to resist offline brute forcing of issued tokens.

    Args:
        secret_key: The configured ``POINTLESSQL_AUTH_SECRET_KEY`` value.

    Returns:
        ``True`` when the key must not be used on a publicly reachable
        server.
    """
    return secret_key == INSECURE_DEFAULT_SECRET_KEY or len(secret_key) < _MIN_SECRET_KEY_LENGTH


class AuthSettings(BaseSettings):
    """JWT signing and session lifetime.

    Reads ``POINTLESSQL_AUTH_*`` environment variables.  ``secret_key``
    MUST be overridden in production.  ``jwt_expiry_hours`` defaults
    to 168 (seven days).

    ``secret_key_previous`` is an optional grace-period
    key: when rotating the primary key operators set
    ``POINTLESSQL_AUTH_SECRET_KEY_PREVIOUS`` to the *old* value before
    changing ``POINTLESSQL_AUTH_SECRET_KEY`` to the new one, wait for
    the current ``jwt_expiry_hours`` window so every outstanding
    session re-signs on its next request, then drop the previous-
    key env var.  New tokens are always signed with the primary key;
    verification falls back to the previous key only if the primary
    rejects the token.  When unset, the rotation fallback is
    disabled and a changed primary key invalidates every live
    session immediately.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_AUTH_")

    secret_key: str = INSECURE_DEFAULT_SECRET_KEY
    secret_key_previous: str | None = None
    jwt_expiry_hours: int = 168  # 7 days
    cookie_secure: bool | None = None
    """Whether session/CSRF cookies carry the ``Secure`` attribute.

    ``None`` (default) auto-detects from the request scheme — ``Secure``
    on https, not on plain http — so a clean checkout works over
    loopback http while a TLS deployment marks cookies ``Secure``
    automatically.  Set ``POINTLESSQL_AUTH_COOKIE_SECURE=true``/``false``
    to force it (e.g. behind a TLS-terminating proxy that forwards
    http)."""


class GroupMapping(BaseModel):
    """One parsed entry from :attr:`OIDCSettings.group_map_raw`.

    Attributes:
        model_config: Pydantic configuration; ``frozen=True`` keeps
            instances immutable so cached parses never mutate.
        workspace_id: Workspace the user lands in when this group
            matches.  ``None`` keeps whatever workspace the user
            already had — useful for "scope-only" mappings that
            don't move the user between tenants.
        is_admin: Whether matching this group grants admin scope.
        is_supervisor: Whether matching this group grants supervisor
            scope (mirrors :class:`ApiKey.supervisor`).
        is_auditor: Whether matching this group grants auditor scope
            (mirrors :class:`ApiKey.auditor`).
    """

    model_config = ConfigDict(frozen=True)

    workspace_id: int | None = None
    is_admin: bool = False
    is_supervisor: bool = False
    is_auditor: bool = False


class OIDCSettings(BaseSettings):
    """OpenID Connect (opt-in) provider configuration.

    Reads ``POINTLESSQL_OIDC_*`` environment variables.  Set both
    ``discovery_url`` (the provider's ``.well-known/openid-configuration``
    URL) and ``client_id`` to enable the SSO login path.  The
    ``client_secret`` may be omitted for PKCE-only public clients.

    Optional group → workspace + scope mapping is also supported: set
    ``POINTLESSQL_OIDC_GROUP_MAP`` to a string like
    ``admins:ws=1,scopes=admin;data-team:ws=2,scopes=supervisor``
    and the OIDC login flow will route users into the named workspace
    and grant the listed scopes.  Format errors fail loud at settings
    construction so a typo in the env var never silently grants the
    wrong privileges.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_OIDC_")

    discovery_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    http_timeout_seconds: float = 10.0
    scope: str = "openid email profile"
    """Space-separated OAuth2 scopes requested at the authorize step.

    The default omits ``groups`` for back-compat with installs that
    rely on the install-default workspace.  Set to
    ``"openid email profile groups"`` (or your IdP's equivalent claim
    scope) to flow group memberships into the login mapper.
    """
    groups_claim_name: str = "groups"
    """Userinfo claim that carries the user's IdP group list.

    Different providers surface this under different keys:
    ``cognito:groups`` for AWS Cognito, ``roles`` for Keycloak in some
    configurations, ``groups`` for Okta and Auth0.  Override via
    ``POINTLESSQL_OIDC_GROUPS_CLAIM_NAME`` if the default doesn't
    match.
    """
    group_map_raw: str = ""
    """Group → workspace + scope mapping, semicolon-separated.

    Empty string disables the feature (every OIDC user lands in the
    install-default workspace with no extra scopes).  Format::

        group_a:ws=1,scopes=admin;group_b:ws=2,scopes=supervisor|auditor

    ``ws=`` is optional (mapping then only grants scopes, leaves the
    user's default workspace alone).  ``scopes=`` accepts a
    pipe-separated subset of ``admin|supervisor|auditor`` or the empty
    string.  A typo at any layer raises ``RuntimeError`` at settings
    construction.
    """

    @computed_field  # type: ignore[prop-decorator]
    @property
    def enabled(self) -> bool:
        """Whether OIDC login is available.

        Empty-string env overrides (e.g. ``POINTLESSQL_OIDC_DISCOVERY_URL=``
        passed through a docker-compose ``${VAR:-}`` fallback) should
        count as "not configured" — truthy check catches both ``None``
        and ``""`` so the SSO button stays hidden and ``/auth/sso``
        does not attempt a discovery call with an empty URL.

        Returns:
            bool: ``True`` iff both ``discovery_url`` and ``client_id``
                are set to non-empty strings.
        """
        return bool(self.discovery_url) and bool(self.client_id)

    @model_validator(mode="after")
    def _validate_group_map(self) -> OIDCSettings:
        """Parse :attr:`group_map_raw` early so typos surface at startup.

        Side effect: caches the parsed dict on a private attribute so
        :attr:`parsed_group_map` returns it without re-parsing on every
        login.  :func:`_parse_group_map` raises ``ValueError`` on
        malformed syntax; pydantic-settings re-raises as
        ``ValidationError`` at ``Settings()`` construction time, which
        is the fail-loud-at-boot behaviour we want.

        Returns:
            OIDCSettings: ``self`` (model validators must return the
                instance for pydantic to keep it).
        """
        # Bypass __setattr__'s "frozen" guard via object.__setattr__
        # so the cache write doesn't trip pydantic's immutability.
        parsed = _parse_group_map(self.group_map_raw)
        object.__setattr__(self, "_parsed_group_map", parsed)
        return self

    @property
    def parsed_group_map(self) -> dict[str, GroupMapping]:
        """Return the cached :attr:`group_map_raw` lookup table.

        Empty dict when the env var is unset / empty.  Each key is an
        IdP group name; the value is the parsed
        :class:`GroupMapping`.
        """
        return getattr(self, "_parsed_group_map", {})


_VALID_SCOPES: frozenset[str] = frozenset({"admin", "supervisor", "auditor"})


def _parse_group_map(raw: str) -> dict[str, GroupMapping]:
    """Parse :attr:`OIDCSettings.group_map_raw` into a typed dict.

    Format (semicolon-separated entries; per entry comma-separated
    fields)::

        group_name:ws=N,scopes=admin|supervisor|auditor;next_group:...

    Both ``ws=`` and ``scopes=`` are optional; an entry with neither
    is degenerate and rejected.  Whitespace around tokens is tolerated.

    Args:
        raw: The env-var value verbatim.

    Returns:
        Dict keyed by group name, value is a :class:`GroupMapping`.

    Raises:
        ValueError: On unparseable syntax, unknown scope name, or
            non-integer workspace ID.  Settings construction
            propagates this as a ``ValidationError``.
    """
    if not raw or not raw.strip():
        return {}
    out: dict[str, GroupMapping] = {}
    for entry in raw.split(";"):
        chunk = entry.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise ValueError(f"OIDC group_map entry {chunk!r}: expected 'group:ws=N,scopes=...'")
        group_name, _, body = chunk.partition(":")
        group_name = group_name.strip()
        if not group_name:
            raise ValueError(f"OIDC group_map entry {chunk!r}: empty group name")
        ws_id: int | None = None
        scopes: set[str] = set()
        for field in body.split(","):
            token = field.strip()
            if not token:
                continue
            key, eq, val = token.partition("=")
            if not eq:
                raise ValueError(
                    f"OIDC group_map[{group_name!r}]: field {token!r} must be 'key=value'"
                )
            key = key.strip()
            val = val.strip()
            if key == "ws":
                try:
                    ws_id = int(val)
                except ValueError as exc:
                    raise ValueError(
                        f"OIDC group_map[{group_name!r}]: ws={val!r} must be int"
                    ) from exc
            elif key == "scopes":
                if val == "":
                    continue
                for scope in val.split("|"):
                    scope_clean = scope.strip()
                    if scope_clean not in _VALID_SCOPES:
                        raise ValueError(
                            f"OIDC group_map[{group_name!r}]: unknown scope {scope_clean!r}; "
                            f"must be one of {sorted(_VALID_SCOPES)}"
                        )
                    scopes.add(scope_clean)
            else:
                raise ValueError(
                    f"OIDC group_map[{group_name!r}]: unknown field {key!r}; "
                    "expected 'ws' or 'scopes'"
                )
        if ws_id is None and not scopes:
            raise ValueError(f"OIDC group_map[{group_name!r}]: must set ws=, scopes=, or both")
        out[group_name] = GroupMapping(
            workspace_id=ws_id,
            is_admin="admin" in scopes,
            is_supervisor="supervisor" in scopes,
            is_auditor="auditor" in scopes,
        )
    return out
