"""Bitemporal-convention service layer.

Re-exports the processing-time injector so callers do
``from pointlessql.services import bitemporal`` without reaching into
the private sub-module.
"""

from __future__ import annotations

from pointlessql.services.bitemporal._stamp import inject_processing_time

__all__ = ["inject_processing_time"]
