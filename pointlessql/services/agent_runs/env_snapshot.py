"""Hardware/library fingerprint snapshot.

Captures a compact JSON blob describing the host environment so an
audit reviewer can answer "what env produced this row?" from the
Run-detail UI alone.  The snapshot is **advisory only** — it
captures the engineer's declared intent, not a guarantee of
bit-identical reproducibility (CUDA non-determinism, parallel
dataloaders, atomic-add ordering all leak through even with full
state capture, see ROADMAP.md lines 2325-2332).

Captured fields:

* ``python``: ``sys.version``, ``sys.platform``, ``platform.machine()``,
  ``platform.processor()``, ``os.cpu_count()``.
* ``packages``: ``importlib.metadata.distributions()`` collapsed to
  ``{name: version}`` for the top 200 packages by name length (the
  ROADMAP-suggested 4 KiB cap).
* ``gpu``: When ``torch`` is importable AND ``torch.cuda.is_available()``,
  one entry per CUDA device with ``name`` + ``total_memory``.

The blob is cached at **module-import time** so subsequent
:func:`record_operation` calls don't re-walk ``importlib.metadata``
on every write.  A subprocess fork that adds a package mid-process
won't see the new entry — acceptable for an advisory fingerprint;
the cost of a fresh per-op walk would dominate over a small
training loop.

Best-effort end-to-end: every sub-step is wrapped in
``try/except Exception`` and degrades to an empty / partial dict
rather than raising into :func:`record_operation`.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import sys
from typing import Any

_logger = logging.getLogger(__name__)

# Hard cap so a host with thousands of pip packages doesn't blow up
# the audit row.  4 KiB-ish at JSON-encode time matches the
# ROADMAP-line 2399 expectation.
_PACKAGE_CAP = 200
_BLOB_BYTE_CAP = 4096


def _snapshot_python() -> dict[str, Any]:
    """Return the Python/CPU lines of the snapshot.

    Returns:
        ``{"version", "platform", "machine", "processor",
        "cpu_count"}`` or an empty dict on failure.
    """
    try:
        return {
            "version": sys.version.split()[0],  # "3.14.3" not the full banner
            "platform": sys.platform,
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        }
    except Exception:  # noqa: BLE001 — best-effort
        _logger.debug("env_snapshot: python block failed", exc_info=True)
        return {}


def _snapshot_packages() -> dict[str, str]:
    """Return ``{name: version}`` for the top-N installed packages.

    Returns:
        Sorted-by-name dict capped at :data:`_PACKAGE_CAP`.  Empty
        dict on failure.
    """
    try:
        from importlib.metadata import distributions
    except Exception:  # noqa: BLE001 — best-effort
        return {}
    try:
        result: dict[str, str] = {}
        for dist in distributions():
            try:
                name = dist.metadata["Name"]
                version = dist.version
            except Exception:  # noqa: BLE001
                continue
            if name and version:
                result[name] = version
            if len(result) >= _PACKAGE_CAP:
                break
        return dict(sorted(result.items()))
    except Exception:  # noqa: BLE001 — best-effort
        _logger.debug("env_snapshot: packages block failed", exc_info=True)
        return {}


def _snapshot_gpu() -> list[dict[str, Any]] | None:
    """Return GPU info if torch + CUDA are available.

    Returns:
        A list of ``{"name", "total_memory"}`` dicts, or ``None``
        when torch isn't importable / CUDA isn't available.
    """
    try:
        import importlib

        torch = importlib.import_module("torch")
    except Exception:  # noqa: BLE001 — torch is an optional extra
        return None
    try:
        if not torch.cuda.is_available():
            return None
        n = torch.cuda.device_count()
        result: list[dict[str, Any]] = []
        for i in range(n):
            try:
                props = torch.cuda.get_device_properties(i)
                result.append(
                    {
                        "name": getattr(props, "name", f"cuda:{i}"),
                        "total_memory": getattr(props, "total_memory", None),
                    }
                )
            except Exception:  # noqa: BLE001 — per-device best-effort
                continue
        return result
    except Exception:  # noqa: BLE001 — best-effort
        _logger.debug("env_snapshot: gpu block failed", exc_info=True)
        return None


def _build_snapshot() -> str | None:
    """Assemble the JSON-encoded snapshot, capping at :data:`_BLOB_BYTE_CAP`.

    Returns:
        A JSON string when at least the python block was captured,
        ``None`` when nothing could be gathered (extremely rare —
        means even ``sys.version`` access raised).
    """
    snapshot: dict[str, Any] = {}
    py = _snapshot_python()
    if py:
        snapshot["python"] = py
    packages = _snapshot_packages()
    if packages:
        snapshot["packages"] = packages
    gpu = _snapshot_gpu()
    if gpu is not None:
        snapshot["gpu"] = gpu

    if not snapshot:
        return None

    encoded = json.dumps(snapshot, sort_keys=True, default=str)
    if len(encoded) <= _BLOB_BYTE_CAP:
        return encoded

    # Drop packages first — single biggest contributor.
    snapshot.pop("packages", None)
    encoded = json.dumps(snapshot, sort_keys=True, default=str)
    if len(encoded) <= _BLOB_BYTE_CAP:
        encoded = encoded[:-1] + ',"packages_truncated":true}'
        return encoded
    # If we still don't fit, just emit the python block.
    return json.dumps({"python": snapshot.get("python", {})}, sort_keys=True)


_cached_snapshot: str | None = _build_snapshot()


def cached_env_snapshot() -> str | None:
    """Return the process-cached env snapshot.

    Re-evaluating the snapshot on every audit-row write would
    dominate hot-path latency on hosts with hundreds of installed
    packages.  This getter exposes the import-time cache so the
    cost is paid once per process.

    Returns:
        A JSON string or ``None`` when the snapshot could not be
        built at all.
    """
    return _cached_snapshot


def reset_cache_for_tests(value: str | None = None) -> None:
    """Test-only helper: reset the module cache to *value* or rebuild.

    Args:
        value: When provided, set the cache to this exact JSON
            string.  When ``None``, rebuild via :func:`_build_snapshot`.
    """
    global _cached_snapshot
    _cached_snapshot = value if value is not None else _build_snapshot()
