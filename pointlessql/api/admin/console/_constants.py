"""Shared constants for the admin-console route surfaces."""

from __future__ import annotations

from datetime import timedelta

ADMIN_AUDIT_LIMIT = 1000

ADMIN_AUDIT_SINCE_WINDOWS: dict[str, timedelta | None] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "all": None,
}

AUDIT_EXPORT_LIMIT = 10_000
