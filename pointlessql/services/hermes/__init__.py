"""Managed-Hermes lifecycle + routing services.

This package owns the embedded Hermes agent dashboard: spawning it as
a child process (:mod:`instance`) and deciding which process a given
request reaches (:mod:`manager`).  The HTTP + WebSocket proxies under
:mod:`pointlessql.api.hermes_routes` consume the resolved targets.
"""

from __future__ import annotations

from pointlessql.services.hermes.instance import (
    HermesInstance,
    HermesStartupError,
    hermes_available,
)
from pointlessql.services.hermes.manager import HermesInstanceManager, HermesTarget

__all__ = [
    "HermesInstance",
    "HermesInstanceManager",
    "HermesStartupError",
    "HermesTarget",
    "hermes_available",
]
