"""Resolve which Hermes dashboard a given request should reach.

The manager is the single place that knows *where* Hermes lives for
an operator.  It hides two process models behind one ``resolve`` call
so the proxy never branches on configuration:

- ``mode="external"`` — Hermes runs elsewhere (a Docker service or a
  remote host); ``resolve`` returns the configured ``dashboard_url``
  and optional pre-shared token, nothing is spawned.
- ``mode="managed"`` — PointlesSQL owns the process.  In
  ``isolation="shared"`` one :class:`HermesInstance` serves everyone;
  the per-operator pool (``isolation="per_user"``) is a later step and
  resolves to the shared instance until then.

``HermesTarget`` is the small value the proxy consumes: an HTTP base,
a WebSocket base, and the token to inject.  When it wraps a managed
instance the proxy ``touch``-es it so idle instances can be reaped.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from pointlessql.config import HermesSettings
from pointlessql.services.hermes.instance import HermesInstance

_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HermesTarget:
    """A resolved Hermes endpoint the proxy forwards to.

    Attributes:
        base_url: HTTP base, e.g. ``http://127.0.0.1:9119``.
        ws_base_url: WebSocket base, e.g. ``ws://127.0.0.1:9119``.
        token: Pre-shared dashboard token to inject, or ``None`` when
            the upstream authenticates by cookie (gated mode).
        instance: The managed process behind this target, or ``None``
            for an external upstream.
    """

    base_url: str
    ws_base_url: str
    token: str | None
    instance: HermesInstance | None = None


def _ws_base(url: str) -> str:
    """Derive a WebSocket base URL from an HTTP one."""
    if url.startswith("https://"):
        return "wss://" + url[len("https://") :]
    if url.startswith("http://"):
        return "ws://" + url[len("http://") :]
    return url


class HermesInstanceManager:
    """Own the Hermes process model and resolve per-request targets.

    Args:
        settings: The resolved ``POINTLESSQL_HERMES_*`` block.
    """

    def __init__(self, settings: HermesSettings) -> None:
        self.settings = settings
        self._shared: HermesInstance | None = None
        self._per_user: dict[int, HermesInstance] = {}
        self._lock = asyncio.Lock()

    @property
    def is_managed(self) -> bool:
        """True when PointlesSQL owns the Hermes process(es)."""
        return self.settings.mode == "managed"

    def _shared_home(self) -> Path:
        """Home directory for the shared managed instance.

        Defaults to the operator's real ``~/.hermes`` so the embedded
        dashboard inherits their existing model + provider config; an
        explicit ``home_root`` overrides it.
        """
        if self.settings.home_root is not None:
            return self.settings.home_root
        return Path.home() / ".hermes"

    async def start_shared(self) -> HermesInstance:
        """Spawn the shared managed instance (called once at startup).

        Propagates :class:`HermesStartupError` from the subprocess
        launch when the dashboard never comes up healthy.

        Returns:
            HermesInstance: The started, health-checked process.
        """
        token = self.settings.session_token or secrets.token_urlsafe(32)
        instance = HermesInstance(
            command=self.settings.command,
            host=self.settings.host,
            port=self.settings.port_base,
            token=token,
            home=self._shared_home(),
            chat_enabled=self.settings.chat_enabled,
            startup_timeout_seconds=self.settings.startup_timeout_seconds,
        )
        await instance.start()
        self._shared = instance
        return instance

    def resolve(self, user_id: int | None = None) -> HermesTarget | None:
        """Resolve the Hermes target for an operator.

        Args:
            user_id: The authenticated PointlesSQL user id; reserved
                for the per-operator pool (currently unused — every
                operator shares one instance).

        Returns:
            HermesTarget when a destination exists, or ``None`` when
            managed mode is enabled but no instance is running yet (the
            proxy turns this into a 503).
        """
        if self.settings.mode == "external":
            return HermesTarget(
                base_url=self.settings.dashboard_url.rstrip("/"),
                ws_base_url=_ws_base(self.settings.dashboard_url.rstrip("/")),
                token=self.settings.session_token,
                instance=None,
            )

        instance = self._shared
        if instance is None:
            return None
        instance.touch()
        return HermesTarget(
            base_url=instance.base_url,
            ws_base_url=instance.ws_base_url,
            token=instance.token,
            instance=instance,
        )

    async def stop_all(self) -> None:
        """Stop every managed instance (called at shutdown)."""
        if self._shared is not None:
            await self._shared.stop()
            self._shared = None
        for instance in list(self._per_user.values()):
            await instance.stop()
        self._per_user.clear()

    async def status(self) -> dict[str, Any]:
        """Return a JSON-friendly snapshot for the admin status panel.

        Probes the resolved upstream's ``/api/status`` so the panel
        reflects real reachability rather than just "a process exists".

        Returns:
            dict: ``enabled`` / ``mode`` / ``isolation`` / ``managed`` /
            ``running`` / ``healthy`` / ``chat_enabled`` / ``base_url``.
        """
        target = self.resolve()
        healthy = False
        if target is not None:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{target.base_url}/api/status")
                    healthy = resp.status_code == 200
            except httpx.HTTPError:
                healthy = False
        return {
            "enabled": self.settings.enabled,
            "mode": self.settings.mode,
            "isolation": self.settings.isolation,
            "managed": self.is_managed,
            "running": target is not None,
            "healthy": healthy,
            "chat_enabled": self.settings.chat_enabled,
            "base_url": target.base_url if target is not None else None,
        }
