"""socialTabs Alpine factory + 2 new partials on disk.

Coverage:

* The new ``_endorsements_pane.html`` + ``_followers_pane.html``
  partials are present on disk so table.html and branch_detail.html
  can ``{% include %}`` them.
* The ``socialTabs`` factory is registered in ``bootstrap.js`` so
  Alpine resolves it at parse time on table / branch pages.
* The factory's source carries the load-bearing names the partials
  read (``endorsementsLoaded``, ``followerCount``, ``toggleFollow``
  etc.) so renaming inside the factory without updating partials
  trips this test rather than silently breaking the UI.
"""

from __future__ import annotations

from pathlib import Path


def _frontend() -> Path:
    return Path(__file__).resolve().parent.parent / "frontend"


def test_endorsements_pane_partial_exists() -> None:
    """The endorsement pane partial is on disk + non-empty."""
    path = (
        _frontend()
        / "templates"
        / "partials"
        / "social"
        / "_endorsements_pane.html"
    )
    assert path.exists(), f"missing partial: {path}"
    body = path.read_text(encoding="utf-8")
    assert "tab-endorsements" in body
    assert "endorsementsLoaded" in body
    assert "endorsementTypes" in body
    assert "toggleEndorsement" in body


def test_followers_pane_partial_exists() -> None:
    """The followers pane partial is on disk + non-empty."""
    path = (
        _frontend()
        / "templates"
        / "partials"
        / "social"
        / "_followers_pane.html"
    )
    assert path.exists(), f"missing partial: {path}"
    body = path.read_text(encoding="utf-8")
    assert "tab-followers" in body
    assert "followerCount" in body
    assert "toggleFollow" in body
    assert "followLocked" in body


def test_social_tabs_factory_registered_in_bootstrap() -> None:
    """``socialTabs`` is re-attached to window via bootstrap.js."""
    bootstrap = (_frontend() / "js" / "bootstrap.js").read_text(
        encoding="utf-8"
    )
    assert "from './social_tabs.js'" in bootstrap
    assert "window.socialTabs = socialTabs" in bootstrap


def test_social_tabs_factory_exposes_partial_bindings() -> None:
    """Every Alpine binding the partials reference is owned by the factory.

    Drift guard: if someone renames a state field on the factory
    without also updating the partial, the partial silently breaks
    in the browser (Alpine treats unknown names as undefined).  This
    test fails first so the rename never lands.
    """
    factory = (_frontend() / "js" / "social_tabs.js").read_text(
        encoding="utf-8"
    )
    for binding in (
        "endorsementsLoaded",
        "endorsements",
        "endorsementTypes",
        "endorsementBusy",
        "countForType",
        "mineForType",
        "toggleEndorsement",
        "followersLoaded",
        "followerCount",
        "following",
        "followBusy",
        "followLocked",
        "toggleFollow",
    ):
        assert binding in factory, f"socialTabs factory missing {binding!r}"
