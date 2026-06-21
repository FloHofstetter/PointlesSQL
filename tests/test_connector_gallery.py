"""Tests for the ingest connector gallery."""

from __future__ import annotations

from pointlessql.models.ingest import INGEST_SOURCE_KINDS
from pointlessql.services.ingest import connector_gallery


def test_available_entries_match_working_kinds() -> None:
    gallery = connector_gallery.connector_gallery()
    available = {e["kind"] for e in gallery if e["status"] == "available"}
    # The available set is exactly the kinds that have a reader, so the
    # gallery can never advertise a pickable connector with no backend.
    assert available == set(INGEST_SOURCE_KINDS)


def test_coming_soon_entries_present_and_distinct() -> None:
    gallery = connector_gallery.connector_gallery()
    coming = [e for e in gallery if e["status"] == "coming_soon"]
    kinds = {e["kind"] for e in coming}
    # The Summit connector wave is represented.
    assert {
        "salesforce",
        "sql_server",
        "monday",
        "slack",
        "zoom",
        "rabbitmq",
        "pendo",
        "zoho_books",
        "jira",
        "github",
        "confluence",
        "sharepoint",
        "google_drive",
        "outlook",
    } <= kinds
    # Announced connectors never collide with the working ones.
    assert kinds.isdisjoint(set(INGEST_SOURCE_KINDS))


def test_maturity_reflects_rollout_status() -> None:
    by_kind = {e["kind"]: e for e in connector_gallery.connector_gallery()}
    # Working kinds report "available"; announced ones carry ga/beta.
    assert by_kind["postgres"]["maturity"] == "available"
    assert by_kind["confluence"]["maturity"] == "ga"
    assert by_kind["slack"]["maturity"] == "beta"
    for entry in by_kind.values():
        assert entry["maturity"] in {"available", "ga", "beta"}


def test_every_entry_is_render_ready() -> None:
    categories = {"file", "database", "cloud", "streaming", "saas", "knowledge"}
    for entry in connector_gallery.connector_gallery():
        assert {
            "kind",
            "label",
            "category",
            "icon",
            "status",
            "maturity",
            "description",
        } <= set(entry)
        assert entry["label"]
        assert entry["icon"].startswith("bi-")
        assert entry["category"] in categories


def test_gallery_groups_ordered_and_nonempty() -> None:
    groups = connector_gallery.gallery_groups()
    categories = [g["category"] for g in groups]
    # Display order: files → databases → cloud → streaming → SaaS → knowledge.
    assert categories == ["file", "database", "cloud", "streaming", "saas", "knowledge"]
    for group in groups:
        assert group["connectors"]
        assert all(c["category"] == group["category"] for c in group["connectors"])
