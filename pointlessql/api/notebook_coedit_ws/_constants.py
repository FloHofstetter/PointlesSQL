"""Wire-protocol tag bytes + module-level constants for the co-edit hub."""

from __future__ import annotations

from typing import Final

from pointlessql.services.notebook import coedit as coedit_service

# Wire-protocol tag bytes (kept in sync with the future
# ``frontend/js/notebook/coedit.js`` Sprint-105.3 mixin).
TAG_SYNC_STEP1: Final[int] = 0x00
TAG_SYNC_STEP2: Final[int] = 0x01
TAG_SYNC_UPDATE: Final[int] = 0x02
TAG_AWARENESS_UPDATE: Final[int] = 0x03
TAG_CELL_UUID_REMAP: Final[int] = 0x04
# agent-presence ride-along; defined alongside its
# REST emitter in ``notebook_coedit_agent_routes.py`` but Phase 109
# needs the constant for the cross-worker dispatch switch.
TAG_AGENT_PRESENCE: Final[int] = 0x05

# Tags that ride the Phase-109 cross-worker bus.  Handshake bytes
# (sync_step1/2) stay strictly local — they are per-client and
# the answering hub has the authoritative state.
BUS_RELAYED_TAGS: Final[frozenset[int]] = frozenset(
    {TAG_SYNC_UPDATE, TAG_AWARENESS_UPDATE, TAG_CELL_UUID_REMAP, TAG_AGENT_PRESENCE}
)

# Importing ``coedit_service`` to keep the type aliases for
# ``CELLS_ORDER_KEY`` / ``CELLS_TEXT_KEY`` co-located.
CELLS_ORDER_KEY: Final[str] = coedit_service.CELLS_ORDER_KEY
CELLS_TEXT_KEY: Final[str] = coedit_service.CELLS_TEXT_KEY

# Per-subscriber outbound queue cap.  At 256 frames a slow client
# disconnects long before they can OOM the host; faster clients
# never come close.
QUEUE_MAXSIZE: Final[int] = 256

# Hub-level periodic flush cadence.  One second strikes the balance
# between losing-at-most-one-second-of-edits on crash and avoiding
# per-keystroke DB roundtrips.
FLUSH_INTERVAL_S: Final[float] = 1.0
