"""axe-core accessibility harness for the e2e browser journeys.

Injects a pinned axe-core build into a Playwright page and runs the WCAG
rule set, returning the violations bucketed by impact.  This is the
non-frontend half of the accessibility work: the harness + the
violations-floor ratchet live under ``e2e/`` and ``scripts/`` and touch no
template, so they can land without colliding with in-flight frontend work.
The actual a11y fixes (landmarks, skip links, focus management, widget
alternatives) are frontend changes tracked separately.

axe-core is loaded from a pinned CDN URL rather than vendored, so there is
no JS asset to maintain; pin bumps are explicit edits to
:data:`AXE_CORE_URL`.
"""

from __future__ import annotations

from typing import Any

# Pinned axe-core build.  Bump deliberately (and re-baseline the floor).
AXE_CORE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"

_IMPACTS = ("critical", "serious", "moderate", "minor")


def run_axe(page: Any) -> dict[str, list[dict[str, Any]]]:
    """Run axe-core against the current page; return violations by impact.

    Injects the axe-core bundle (if not already present), runs ``axe.run``
    over the whole document, and groups the violations into
    critical / serious / moderate / minor buckets.

    Args:
        page: A live Playwright ``Page`` already navigated to the surface
            under test.

    Returns:
        A dict mapping each impact level to its list of violation objects
        (each carries axe's ``id``, ``help``, and ``nodes``).
    """
    page.add_script_tag(url=AXE_CORE_URL)
    results: dict[str, Any] = page.evaluate("() => axe.run(document)")
    buckets: dict[str, list[dict[str, Any]]] = {impact: [] for impact in _IMPACTS}
    for violation in results.get("violations", []):
        impact = violation.get("impact") or "minor"
        buckets.setdefault(impact, []).append(violation)
    return buckets


def impact_counts(buckets: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    """Return the per-impact violation counts for a :func:`run_axe` result."""
    return {impact: len(buckets.get(impact, [])) for impact in _IMPACTS}


def summarise(buckets: dict[str, list[dict[str, Any]]]) -> str:
    """Render a one-line, human-readable summary of the violation buckets."""
    counts = impact_counts(buckets)
    return ", ".join(f"{impact}={counts[impact]}" for impact in _IMPACTS)
