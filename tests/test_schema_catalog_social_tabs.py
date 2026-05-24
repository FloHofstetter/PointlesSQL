"""catalog + schema detail pages render the social tabs.

The catalog browser uses ``schemas.html`` for ``/catalogs/{cat}``
and ``tables.html`` for ``/catalogs/{cat}/schemas/{sch}``.  77.5
restructured both pages to wrap their existing card stacks in an
Overview tab and add 4 social tabs (Discussion / Endorsements /
Followers / README) driven by the kind-agnostic ``socialTabs``
factory.

Coverage:

* ``schemas.html`` template references the 5-tab nav strip +
  ``socialTabs({kind:"catalog",...})`` + the canonical social
  partials.
* ``tables.html`` template references the 5-tab nav strip +
  ``socialTabs({kind:"schema",...})`` + the canonical social
  partials.
* Star buttons on both pages use the post-77.8.E
  ``pqlStarToggle({kind, ref})`` shape.
"""

from __future__ import annotations

import pathlib

_TEMPLATES_ROOT = pathlib.Path(
    "/home/flo/git/PointlesSQL/frontend/templates"
)


def test_schemas_html_has_five_tab_nav_strip() -> None:
    """``schemas.html`` carries the 4 social tab buttons inside the offcanvas drawer.

    Post-77.5 the page itself is the Overview surface and the social
    tabs moved into a side-drawer — no separate Overview tab needed.
    """
    body = (_TEMPLATES_ROOT / "pages/schemas.html").read_text()
    for marker in (
        'data-pql-tab-key="discussion"',
        'data-pql-tab-key="endorsements"',
        'data-pql-tab-key="followers"',
        'data-pql-tab-key="readme"',
    ):
        assert marker in body, f"schemas.html missing nav-tab {marker}"


def test_schemas_html_carries_social_tabs_x_data() -> None:
    """``schemas.html`` wraps the tab-content in ``socialTabs(kind='catalog')``."""
    body = (_TEMPLATES_ROOT / "pages/schemas.html").read_text()
    assert 'socialTabs({' in body
    assert 'kind: "catalog"' in body


def test_schemas_html_star_button_uses_server_backed_shape() -> None:
    """The header star button uses ``pqlStarToggle({kind, ref})``."""
    body = (_TEMPLATES_ROOT / "pages/schemas.html").read_text()
    assert 'pqlStarToggle({kind: "catalog"' in body
    # No legacy ``name:`` field — the rewrite drops it.
    assert 'pqlStarToggle({kind: "catalog", name:' not in body


def test_schemas_html_includes_social_partials() -> None:
    """Endorsements + Followers panes come from the canonical partials."""
    body = (_TEMPLATES_ROOT / "pages/schemas.html").read_text()
    assert "_endorsements_pane.html" in body
    assert "_followers_pane.html" in body


def test_tables_html_has_five_tab_nav_strip() -> None:
    """``tables.html`` carries the 4 social tab buttons inside the offcanvas drawer.

    Post-77.5 the page itself is the Overview surface and the social
    tabs moved into a side-drawer — no separate Overview tab needed.
    """
    body = (_TEMPLATES_ROOT / "pages/tables.html").read_text()
    for marker in (
        'data-pql-tab-key="discussion"',
        'data-pql-tab-key="endorsements"',
        'data-pql-tab-key="followers"',
        'data-pql-tab-key="readme"',
    ):
        assert marker in body, f"tables.html missing nav-tab {marker}"


def test_tables_html_carries_social_tabs_x_data() -> None:
    """``tables.html`` wraps the tab-content in ``socialTabs(kind='schema')``."""
    body = (_TEMPLATES_ROOT / "pages/tables.html").read_text()
    assert 'socialTabs({' in body
    assert 'kind: "schema"' in body


def test_tables_html_star_button_uses_server_backed_shape() -> None:
    """The header star button uses ``pqlStarToggle({kind:"schema", ref})``."""
    body = (_TEMPLATES_ROOT / "pages/tables.html").read_text()
    assert 'pqlStarToggle({kind: "schema"' in body
    # No legacy ``catalog: ..., schema: ...`` two-field shape.
    assert 'pqlStarToggle({kind: "schema", catalog:' not in body


def test_tables_html_includes_social_partials() -> None:
    """Endorsements + Followers panes come from the canonical partials."""
    body = (_TEMPLATES_ROOT / "pages/tables.html").read_text()
    assert "_endorsements_pane.html" in body
    assert "_followers_pane.html" in body
