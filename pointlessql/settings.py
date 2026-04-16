"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """PointlesSQL configuration.

    All fields can be overridden via environment variables prefixed with
    ``POINTLESSQL_``, e.g. ``POINTLESSQL_SOYUZ_CATALOG_URL``.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_")

    soyuz_catalog_url: str = "http://127.0.0.1:8080"
