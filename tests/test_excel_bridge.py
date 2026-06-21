"""Tests for the Excel add-in bridge (OData feed + Office.js manifest)."""

from __future__ import annotations

from xml.etree import ElementTree

import httpx
import pytest

from pointlessql.services import excel_bridge


def test_to_odata_feed_shapes_rows() -> None:
    feed = excel_bridge.to_odata_feed(
        "main.sales.orders", ["region", "total"], [["EU", 10], ["US", 20]]
    )
    assert feed["@odata.context"] == "$metadata#main.sales.orders"
    assert feed["value"] == [{"region": "EU", "total": 10}, {"region": "US", "total": 20}]


def test_to_odata_feed_dict_columns_and_empty() -> None:
    feed = excel_bridge.to_odata_feed("v", [{"name": "id"}], [[1]])
    assert feed["value"] == [{"id": 1}]
    assert excel_bridge.to_odata_feed("v", ["a"], [])["value"] == []


def test_service_document_lists_entity_sets() -> None:
    doc = excel_bridge.odata_service_document("https://host/api/excel/odata/", ["m1", "m2"])
    urls = [e["url"] for e in doc["value"]]
    assert urls == ["https://host/api/excel/odata/m1", "https://host/api/excel/odata/m2"]
    assert doc["@odata.context"].endswith("/$metadata")


def test_office_manifest_is_well_formed_xml() -> None:
    xml = excel_bridge.office_manifest(base_url="https://host/")
    root = ElementTree.fromstring(xml)  # raises on malformed XML
    assert root.tag.endswith("OfficeApp")
    # The base URL is woven into the source/asset locations.
    assert "https://host/excel/taskpane.html" in xml
    assert "ReadWriteDocument" in xml


@pytest.mark.asyncio
async def test_route_manifest(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/api/excel/manifest.xml")
    assert resp.status_code == 200, resp.text
    assert "application/xml" in resp.headers.get("content-type", "")
    ElementTree.fromstring(resp.text)


@pytest.mark.asyncio
async def test_route_odata_service_empty_without_schema(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/api/excel/odata")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["value"] == []
    assert "@odata.context" in data
