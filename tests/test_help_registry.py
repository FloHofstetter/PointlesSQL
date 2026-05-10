"""Tests for the Phase-23 contextual-help registry.

Pin the invariants the macro relies on at render time:

* every slug resolves cleanly via :func:`get_help`
* missing slugs raise ``KeyError`` (loud-fail in templates)
* title and body fit inside the Bootstrap-popover default footprint
* ``learn_more`` URLs are well-formed mkdocs paths
* every slug in the registry is referenced from at least one
  template, every ``info('<slug>')`` call resolves in the
  registry — added in Sprint 23.5

Templates that use the registry pass slugs as plain strings; this
test sweep is the only thing that catches a typo before it ships.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pointlessql.web import HELP, HelpEntry, get_help

_TEMPLATES_ROOT = Path(__file__).resolve().parent.parent / "frontend" / "templates"
_INFO_CALL_RE = re.compile(r"info\(\s*['\"]([a-z0-9.\-]+)['\"]\s*\)")


def _scan_template_slugs() -> set[str]:
    """Return the set of every slug referenced in a Jinja
    ``{{ info('...') }}`` macro call across the template tree.

    The grep is regex-based to avoid spinning up a Jinja
    environment in tests; the macro itself enforces fail-loud
    on unknown slugs at render time.
    """
    slugs: set[str] = set()
    for path in _TEMPLATES_ROOT.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        slugs.update(_INFO_CALL_RE.findall(text))
    return slugs


def test_every_template_slug_resolves_in_registry() -> None:
    """Every ``{{ info('<slug>') }}`` call lands in :data:`HELP`."""
    referenced = _scan_template_slugs()
    missing = referenced - set(HELP.keys())
    assert not missing, f"templates reference slugs not in the registry: {missing}"


def test_every_registry_slug_used_in_some_template() -> None:
    """Every slug in :data:`HELP` is wired into at least one
    template.  Stale registry entries pile up over time as the
    UI is refactored — this catch tells us when a popover has
    no host any more.
    """
    referenced = _scan_template_slugs()
    unused = set(HELP.keys()) - referenced
    assert not unused, f"registry slugs not referenced by any template: {unused}"


def test_every_registered_slug_resolves() -> None:
    """``get_help`` round-trips every key in :data:`HELP`."""
    for slug, entry in HELP.items():
        assert get_help(slug) is entry


def test_missing_slug_raises_keyerror() -> None:
    """A typo in a template surfaces at render time, not silently."""
    with pytest.raises(KeyError):
        get_help("does.not.exist")


@pytest.mark.parametrize("slug", sorted(HELP.keys()))
def test_slug_naming_convention(slug: str) -> None:
    """Slugs follow ``<page>.<topic>`` lowercase-kebab.

    The macro embeds the slug in HTML attribute values; restricting
    to ASCII lower + digits + ``.`` + ``-`` rules out any escape
    surprise without an explicit sanitiser pass.
    """
    assert slug == slug.lower(), f"slug {slug!r} must be lowercase"
    assert "." in slug, f"slug {slug!r} must contain a dot separator"
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789.-")
    assert set(slug) <= allowed, f"slug {slug!r} contains forbidden chars"


@pytest.mark.parametrize("slug,entry", sorted(HELP.items()))
def test_entry_lengths_fit_popover(slug: str, entry: HelpEntry) -> None:
    """Title ≤ 60 chars, body ≤ 280 chars (Bootstrap popover default width)."""
    assert len(entry.title) <= 60, (
        f"slug {slug!r}: title {len(entry.title)} chars exceeds 60-char cap"
    )
    assert len(entry.body) <= 280, (
        f"slug {slug!r}: body {len(entry.body)} chars exceeds 280-char cap"
    )
    assert entry.title.strip() == entry.title, f"slug {slug!r}: title has stray whitespace"
    assert entry.body.strip() == entry.body, f"slug {slug!r}: body has stray whitespace"


@pytest.mark.parametrize("slug,entry", sorted(HELP.items()))
def test_learn_more_is_well_formed(slug: str, entry: HelpEntry) -> None:
    """``learn_more`` URLs are absolute mkdocs paths (no spaces, no ``..``)."""
    if entry.learn_more is None:
        return
    url = entry.learn_more
    assert url.startswith("/"), f"slug {slug!r}: learn_more must start with '/'"
    assert " " not in url, f"slug {slug!r}: learn_more contains whitespace"
    assert ".." not in url, f"slug {slug!r}: learn_more must not contain '..'"
    assert url == url.strip(), f"slug {slug!r}: learn_more has stray whitespace"


def test_phase23_hero_anchors_present() -> None:
    """The 5 Sprint-23.0 hero slugs are all registered.

    Sprint-23.0 wires these into runs_list, run_view, model,
    branches, and table templates.  Renaming any of them without
    updating the templates would silently break the popover.
    """
    expected = {
        "runs.what-is-a-run",
        "runs.what-is-an-operation",
        "models.what-is-promotion",
        "branches.what-is-a-delta-branch",
        "lineage.what-is-lineage",
    }
    assert expected <= set(HELP.keys()), (
        f"missing Sprint-23.0 hero slugs: {expected - set(HELP.keys())}"
    )


def test_sprint_23_4_sql_admin_anchors_present() -> None:
    """Sprint 23.4 wires 10 popovers across SQL editor (3
    anchors) and the admin surfaces (external-writes, audit
    sinks, workspace pins, api-key scopes, system keys, rate
    limits, agent reviews).  Pin the slugs to catch renames
    in CI.
    """
    expected = {
        "sql.run-modes",
        "sql.saved-queries",
        "sql.cost-gate",
        "admin.external-writes-review",
        "admin.audit-sinks",
        "admin.workspace-pins",
        "admin.api-key-scopes",
        "admin.system-keys",
        "admin.rate-limit-tiers",
        "admin.agent-reviews",
    }
    assert expected <= set(HELP.keys()), f"missing Sprint-23.4 slugs: {expected - set(HELP.keys())}"


def test_sprint_23_3_audit_branches_home_anchors_present() -> None:
    """Sprint 23.3 wires 12 popovers across the audit cockpit
    (inbox, search, by-table, queries), the branch-detail page,
    and the home cockpit.  Pin the slugs to catch renames in CI.
    """
    expected = {
        "audit.what-is-an-anomaly",
        "audit.severity-warn-vs-critical",
        "audit.anomaly-actions",
        "audit.fts-query-syntax",
        "audit.principal-summary",
        "audit.cross-workspace-lens",
        "audit.read-kind",
        "branches.preview-tab",
        "branches.promote-vs-discard",
        "branches.cleanup-loop",
        "home.what-is-the-cockpit",
        "home.anomaly-cards",
    }
    assert expected <= set(HELP.keys()), f"missing Sprint-23.3 slugs: {expected - set(HELP.keys())}"


def test_sprint_23_2_models_anchors_present() -> None:
    """Sprint 23.2 wires 6 popovers across the models index, the
    model-detail tabs (Overview, Versions, Lineage, MLflow) and
    the model-compare page.  Pin the slugs to catch renames in CI.
    """
    expected = {
        "models.what-is-the-registry",
        "models.versions-table",
        "models.linked-hermes-runs",
        "models.inference-lineage",
        "models.mlflow-vs-pointlessql",
        "models.compare-versions",
    }
    assert expected <= set(HELP.keys()), f"missing Sprint-23.2 slugs: {expected - set(HELP.keys())}"


def test_sprint_23_1_catalog_and_table_anchors_present() -> None:
    """Sprint 23.1 wires 8 popovers across the catalog tree, the
    schema-detail page, and five spots on the table-detail page
    (Type, Properties, Preview, View-at, Columns, Column-stats).
    Pin the slugs so a rename surfaces in CI rather than as a
    silent template KeyError.
    """
    expected = {
        "catalog.what-is-a-catalog",
        "schemas.what-is-a-schema",
        "tables.external-vs-managed",
        "tables.row-lineage-badge",
        "tables.column-trace-badge",
        "tables.time-travel-button",
        "tables.comments-vs-properties",
        "tables.column-statistics",
    }
    assert expected <= set(HELP.keys()), f"missing Sprint-23.1 slugs: {expected - set(HELP.keys())}"
