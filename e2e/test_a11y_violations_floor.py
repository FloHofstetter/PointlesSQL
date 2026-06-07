"""Accessibility violations-floor gate (axe-core over key surfaces).

Runs axe-core against a small set of always-available, soyuz-free surfaces
and asserts the aggregate violation counts stay at or below the committed
floor (``scripts/wcag_aa_violations_floor.json``).  ``critical`` and
``serious`` are held at zero; ``moderate`` / ``minor`` start generous and
ratchet down as the frontend a11y waves land.

This needs a real browser, so it is part of the e2e job (not the unit
suite).  The surface list starts with the pure-UI shells (home, login) and
expands as the catalog/lineage/notebook surfaces are wired into the broader
e2e tranches.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from e2e.a11y_helpers import impact_counts, run_axe, summarise

pytestmark = pytest.mark.e2e

_FLOOR_PATH = Path(__file__).resolve().parent.parent / "scripts" / "wcag_aa_violations_floor.json"

# Soyuz-free surfaces safe to audit without a live catalog.  ``/auth/login``
# is public; ``/`` renders the authenticated home shell.
_SURFACES = ("/", "/auth/login")


def _load_floor() -> dict[str, int]:
    """Load the committed violations floor."""
    data = json.loads(_FLOOR_PATH.read_text(encoding="utf-8"))
    return {k: int(v) for k, v in data.items() if not k.startswith("_")}


def test_a11y_violations_floor(playwright_context: Any, live_server_url: str) -> None:
    """Aggregate axe-core violations across key surfaces stay within the floor."""
    floor = _load_floor()
    totals = {"critical": 0, "serious": 0, "moderate": 0, "minor": 0}
    detail: list[str] = []
    page = playwright_context.new_page()
    try:
        for surface in _SURFACES:
            page.goto(f"{live_server_url}{surface}", wait_until="domcontentloaded")
            buckets = run_axe(page)
            for impact, count in impact_counts(buckets).items():
                totals[impact] += count
            detail.append(f"{surface}: {summarise(buckets)}")
    finally:
        page.close()

    breaches = [
        f"{impact}: {totals[impact]} > floor {floor[impact]}"
        for impact in totals
        if impact in floor and totals[impact] > floor[impact]
    ]
    assert not breaches, (
        "axe-core violations exceed the WCAG-AA floor:\n  "
        + "\n  ".join(breaches)
        + "\nper-surface:\n  "
        + "\n  ".join(detail)
    )
