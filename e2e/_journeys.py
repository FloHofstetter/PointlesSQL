"""Journey registry — maps each automated e2e test to its source playbook.

Every Playwright journey under ``e2e/`` replays one deterministic Markdown
playbook in ``docs/e2e-walkthroughs/``.  This registry is the traceability
spine: for each automated test it records which playbook it replays and
whether the journey needs a live soyuz-catalog.

The coverage ledger (:mod:`e2e.test_e2e_coverage_ledger`) reads this
registry to prove that every playbook classified ``automated`` is backed by
a real registered journey, and that every registered journey points at a
real playbook.

The module is **pure data** — no Playwright import, no app import — so the
ledger meta-tests run without a live server or a browser.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Journey:
    """One automated browser/API journey and its provenance.

    Attributes:
        test_id: The ``module::function`` pytest node id (without the
            ``e2e/`` prefix), uniquely identifying the test.
        module: The ``e2e/`` module filename the test lives in.
        playbook: The source playbook filename under
            ``docs/e2e-walkthroughs/`` this journey replays.
        requires_soyuz: Whether the journey needs a live soyuz-catalog
            (catalog / lineage / federation data fetched on GET).  Such
            tests carry the ``requires_soyuz`` marker and auto-skip when
            soyuz is unreachable.
        note: Short human note on what the journey asserts.
    """

    test_id: str
    module: str
    playbook: str
    requires_soyuz: bool = False
    note: str = ""


def _j(
    test_id: str, module: str, playbook: str, note: str, *, requires_soyuz: bool = False
) -> Journey:
    """Construct a :class:`Journey` (positional-light helper for the table)."""
    return Journey(
        test_id=test_id,
        module=module,
        playbook=playbook,
        requires_soyuz=requires_soyuz,
        note=note,
    )


# test_id -> Journey.  Register every automated e2e test here.  Adding a test
# without a matching entry (or vice versa) fails a ledger meta-test.
JOURNEYS: dict[str, Journey] = {
    "test_smoke::test_healthz_responds_via_live_server": _j(
        "test_smoke::test_healthz_responds_via_live_server",
        "test_smoke.py",
        "operational.md",
        "health endpoint returns the JSON envelope over the live server",
    ),
    "test_smoke::test_homepage_renders_for_authenticated_admin": _j(
        "test_smoke::test_homepage_renders_for_authenticated_admin",
        "test_smoke.py",
        "operational.md",
        "authenticated admin lands off the login page",
    ),
    "test_notebook_coedit_multi_tab::test_phase105_7_multi_tab_coedit_core_invariants": _j(
        "test_notebook_coedit_multi_tab::test_phase105_7_multi_tab_coedit_core_invariants",
        "test_notebook_coedit_multi_tab.py",
        "notebook-coedit-multi-tab.md",
        "two browser tabs converge on a shared CRDT notebook edit",
    ),
}


def automated_playbooks() -> set[str]:
    """Return the set of playbook filenames backed by ≥1 registered journey."""
    return {journey.playbook for journey in JOURNEYS.values()}


def journeys_for_playbook(playbook: str) -> list[Journey]:
    """Return all registered journeys that replay *playbook*."""
    return [journey for journey in JOURNEYS.values() if journey.playbook == playbook]
