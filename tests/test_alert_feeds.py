"""Behavioural tests for the alert RSS/Atom + JSON Feed renderers.

These pin the exact serialised shape of both feed formats — element
text, attributes, URLs, the ``updated`` aggregation and the
summary/date-parse helpers — so that a regression in any literal,
attribute name or control-flow branch is caught.
"""

from __future__ import annotations

import datetime
from typing import Any
from xml.etree import ElementTree as ET

from pointlessql.services.alert_feeds import (
    _dt_parse,
    _summary,
    render_atom,
    render_json_feed,
)

_ATOM = "{http://www.w3.org/2005/Atom}"
_EPOCH = datetime.datetime.fromtimestamp(0, tz=datetime.UTC)


def _event(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "event_id": "evt-1",
        "id": 99,
        "alert_slug": "q1",
        "alert_title": "Q1 breach",
        "outcome": "breach_detected",
        "row_count": 5,
        "fired_at": "2026-01-02T03:04:05+00:00",
        "payload_json": '{"specversion": "1.0"}',
    }
    base.update(over)
    return base


# --- _dt_parse ------------------------------------------------------------


def test_dt_parse_none_returns_epoch_utc() -> None:
    out = _dt_parse(None)
    assert out == _EPOCH
    assert out.tzinfo is datetime.UTC
    assert out.year == 1970 and out.month == 1 and out.day == 1


def test_dt_parse_empty_string_returns_epoch() -> None:
    assert _dt_parse("") == _EPOCH


def test_dt_parse_malformed_returns_epoch() -> None:
    assert _dt_parse("not-a-date") == _EPOCH


def test_dt_parse_valid_iso_roundtrips_exactly() -> None:
    out = _dt_parse("2026-01-02T03:04:05+00:00")
    assert out == datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.UTC)


# --- _summary -------------------------------------------------------------


def test_summary_full_event() -> None:
    assert _summary(_event()) == "breach detected · row_count=5 · alert=q1"


def test_summary_defaults_when_fields_missing() -> None:
    # outcome -> "fired", row_count omitted -> no segment,
    # alert_slug -> "unknown".
    assert _summary({}) == "fired · alert=unknown"


def test_summary_row_count_zero_is_kept() -> None:
    # 0 is not None, so the segment must still render.
    out = _summary({"outcome": "ok", "row_count": 0, "alert_slug": "z"})
    assert out == "ok · row_count=0 · alert=z"


def test_summary_underscores_in_outcome_become_spaces() -> None:
    assert _summary({"outcome": "no_data_returned"}).startswith("no data returned · ")


# --- render_atom ----------------------------------------------------------


def _atom_tree(events: list[dict[str, Any]], **kw: Any) -> ET.Element:
    kw.setdefault("user_email", "owner@example.com")
    kw.setdefault("base_url", "https://pql.example.com")
    xml = render_atom(events, **kw)
    assert xml.startswith('<?xml version="1.0" encoding="utf-8"?>\n')
    return ET.fromstring(xml.split("\n", 1)[1])


def test_atom_feed_level_metadata() -> None:
    feed = _atom_tree([_event()])
    assert feed.tag == f"{_ATOM}feed"
    assert feed.findtext(f"{_ATOM}id") == "https://pql.example.com/alerts/feed.atom"
    assert feed.findtext(f"{_ATOM}title") == "PointlesSQL query alerts"
    author = feed.find(f"{_ATOM}author")
    assert author is not None
    assert author.findtext(f"{_ATOM}name") == "owner@example.com"
    assert author.findtext(f"{_ATOM}email") == "owner@example.com"


def test_atom_feed_links() -> None:
    feed = _atom_tree([_event()])
    links = feed.findall(f"{_ATOM}link")
    by_rel = {ln.get("rel"): ln for ln in links}
    assert by_rel["self"].get("href") == "https://pql.example.com/alerts/feed.atom"
    alt = by_rel["alternate"]
    assert alt.get("type") == "text/html"
    assert alt.get("href") == "https://pql.example.com/alerts"


def test_atom_base_url_trailing_slash_stripped() -> None:
    feed = _atom_tree([_event()], base_url="https://pql.example.com/")
    assert feed.findtext(f"{_ATOM}id") == "https://pql.example.com/alerts/feed.atom"


def test_atom_updated_is_max_fired_at() -> None:
    feed = _atom_tree(
        [
            _event(fired_at="2026-01-02T00:00:00+00:00"),
            _event(fired_at="2026-03-09T12:00:00+00:00"),
            _event(fired_at="2026-02-01T00:00:00+00:00"),
        ]
    )
    assert feed.findtext(f"{_ATOM}updated") == "2026-03-09T12:00:00+00:00"


def test_atom_empty_events_updated_is_recent_not_epoch() -> None:
    feed = _atom_tree([])
    updated = datetime.datetime.fromisoformat(feed.findtext(f"{_ATOM}updated"))
    assert updated.tzinfo is not None
    # "now" branch, not the epoch fallback.
    assert updated.year >= 2025
    assert not feed.findall(f"{_ATOM}entry")


def test_atom_entry_fields() -> None:
    feed = _atom_tree([_event()])
    entries = feed.findall(f"{_ATOM}entry")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.findtext(f"{_ATOM}id") == "urn:pointlessql:alert:evt-1"
    assert entry.findtext(f"{_ATOM}title") == (
        "Q1 breach — breach detected · row_count=5 · alert=q1"
    )
    assert entry.findtext(f"{_ATOM}updated") == "2026-01-02T03:04:05+00:00"
    assert entry.findtext(f"{_ATOM}published") == "2026-01-02T03:04:05+00:00"
    link = entry.find(f"{_ATOM}link")
    assert link.get("rel") == "alternate"
    assert link.get("type") == "text/html"
    assert link.get("href") == "https://pql.example.com/alerts/q1"
    content = entry.find(f"{_ATOM}content")
    assert content.get("type") == "application/cloudevents+json"
    assert content.text == '{"specversion": "1.0"}'


def test_atom_entry_id_falls_back_to_id_when_event_id_missing() -> None:
    feed = _atom_tree([_event(event_id=None)])
    assert feed.find(f"{_ATOM}entry").findtext(f"{_ATOM}id") == ("urn:pointlessql:alert:99")


def test_atom_entry_title_falls_back_to_slug_then_alert() -> None:
    feed = _atom_tree([_event(alert_title=None)])
    assert feed.find(f"{_ATOM}entry").findtext(f"{_ATOM}title").startswith("q1 — ")
    feed2 = _atom_tree([_event(alert_title=None, alert_slug=None)])
    assert feed2.find(f"{_ATOM}entry").findtext(f"{_ATOM}title").startswith("alert — ")


def test_atom_entry_content_empty_when_payload_missing() -> None:
    feed = _atom_tree([_event(payload_json=None)])
    content = feed.find(f"{_ATOM}entry").find(f"{_ATOM}content")
    assert content.text in ("", None)


def test_atom_entry_link_href_empty_slug_when_slug_missing() -> None:
    # alert_slug -> "" fallback, so the href has a trailing slash only.
    feed = _atom_tree([_event(alert_slug=None)])
    link = feed.find(f"{_ATOM}entry").find(f"{_ATOM}link")
    assert link.get("href") == "https://pql.example.com/alerts/"


# --- render_json_feed -----------------------------------------------------


def _json_feed(events: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    kw.setdefault("user_email", "owner@example.com")
    kw.setdefault("base_url", "https://pql.example.com")
    return render_json_feed(events, **kw)


def test_json_feed_envelope() -> None:
    out = _json_feed([])
    assert out["version"] == "https://jsonfeed.org/version/1.1"
    assert out["title"] == "PointlesSQL query alerts"
    assert out["home_page_url"] == "https://pql.example.com/alerts"
    assert out["feed_url"] == "https://pql.example.com/alerts/feed.json"
    assert out["authors"] == [{"name": "owner@example.com"}]
    assert out["items"] == []


def test_json_feed_base_url_trailing_slash_stripped() -> None:
    out = _json_feed([], base_url="https://pql.example.com/")
    assert out["home_page_url"] == "https://pql.example.com/alerts"


def test_json_feed_item_fields_with_parsed_payload() -> None:
    out = _json_feed([_event()])
    (item,) = out["items"]
    assert item["id"] == "evt-1"
    assert item["url"] == "https://pql.example.com/alerts/q1"
    assert item["title"] == "Q1 breach — breach detected · row_count=5 · alert=q1"
    assert item["content_text"] == "breach detected · row_count=5 · alert=q1"
    # html.escape() escapes quotes too (quote=True is the default).
    assert item["content_html"] == ("<pre>{&quot;specversion&quot;: &quot;1.0&quot;}</pre>")
    assert item["date_published"] == "2026-01-02T03:04:05+00:00"
    assert item["_pointlessql_cloudevent"] == {"specversion": "1.0"}
    assert item["authors"] == [{"name": "owner@example.com"}]


def test_json_feed_id_falls_back_to_str_id() -> None:
    out = _json_feed([_event(event_id=None)])
    assert out["items"][0]["id"] == "99"


def test_json_feed_url_has_empty_slug_when_slug_missing() -> None:
    out = _json_feed([_event(alert_slug=None)])
    assert out["items"][0]["url"] == "https://pql.example.com/alerts/"


def test_json_feed_title_falls_back_to_slug_then_alert() -> None:
    # alert_title missing -> slug; both missing -> literal "alert".
    slug_only = _json_feed([_event(alert_title=None)])
    assert slug_only["items"][0]["title"].startswith("q1 — ")
    neither = _json_feed([_event(alert_title=None, alert_slug=None)])
    assert neither["items"][0]["title"].startswith("alert — ")


def test_json_feed_content_empty_when_payload_missing() -> None:
    out = _json_feed([_event(payload_json=None)])
    item = out["items"][0]
    assert item["content_html"] == "<pre></pre>"
    assert item["_pointlessql_cloudevent"] == ""


def test_json_feed_invalid_payload_falls_back_to_raw_text() -> None:
    out = _json_feed([_event(payload_json="not json{")])
    item = out["items"][0]
    assert item["_pointlessql_cloudevent"] == "not json{"
    assert item["content_html"] == "<pre>not json{</pre>"


def test_json_feed_html_escapes_payload() -> None:
    out = _json_feed([_event(payload_json="<script>&")])
    assert out["items"][0]["content_html"] == "<pre>&lt;script&gt;&amp;</pre>"
