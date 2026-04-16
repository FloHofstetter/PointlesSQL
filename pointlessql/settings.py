"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """PointlesSQL configuration.

    All fields can be overridden via environment variables prefixed with
    ``POINTLESSQL_``, e.g. ``POINTLESSQL_SOYUZ_CATALOG_URL``.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_")

    soyuz_catalog_url: str = "http://127.0.0.1:8080"

    host: str = "127.0.0.1"
    port: int = 8000

    jupyter_enabled: bool = True
    jupyter_port: int = 8888

    database_url: str = "sqlite:///./pointlessql.db"
    secret_key: str = "change-me-in-production"
    jwt_expiry_hours: int = 168  # 7 days

    # OIDC / OAuth2 — opt-in. Set both discovery_url and client_id to enable.
    oidc_discovery_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def oidc_enabled(self) -> bool:
        """Whether OIDC login is available."""
        return self.oidc_discovery_url is not None and self.oidc_client_id is not None
