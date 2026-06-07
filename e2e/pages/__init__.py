"""Page objects for the e2e browser journeys.

Re-export facade: import page objects from ``e2e.pages`` rather than the
private submodules, so a future internal reshuffle (splitting a surface
into its own module) never changes a journey's import line.

The base class lives in :mod:`e2e.pages._base`; per-surface page objects are
added here as their journeys land.
"""

from __future__ import annotations

from e2e.pages._base import DEFAULT_TIMEOUT_MS, BasePage

__all__ = ["DEFAULT_TIMEOUT_MS", "BasePage"]
