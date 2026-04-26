"""Atom 1.0 + JSON Feed 1.1 rendering for the alert pull feeds.

The admin UI surfaces a per-user opaque token; any RSS/Atom reader
(Miniflux, FreshRSS, Reeder, NetNewsWire, Thunderbird, Feedly) can
subscribe to ``/alerts/feed.atom?token=<opaque>`` and dedup by entry
``<id>``.  The JSON companion is for feed readers that prefer it
(Reeder supports both; Feedly does Atom; JSON Feed is for Netnewsire
and custom scripts).  Covering both formats keeps the "no lock-in"
design goal intact without picking sides.
"""

from __future__ import annotations

import datetime
import html
import json
from typing import Any
from xml.etree import ElementTree as ET

_ATOM_NS = "http://www.w3.org/2005/Atom"


def _dt_parse(raw: str | None) -> datetime.datetime:
    """Return a timezone-aware datetime for *raw* or epoch fallback.

    Args:
        raw: ISO-formatted string or ``None``.

    Returns:
        UTC datetime; falls back to the Unix epoch when *raw* is
        missing or malformed.  Feed readers sort by ``fired_at``
        internally so the fallback only matters for seed runs.
    """
    if not raw:
        return datetime.datetime.fromtimestamp(0, tz=datetime.UTC)
    try:
        return datetime.datetime.fromisoformat(raw)
    except ValueError:
        return datetime.datetime.fromtimestamp(0, tz=datetime.UTC)


def _summary(event: dict[str, Any]) -> str:
    """Return a human-readable one-liner for *event*.

    Args:
        event: Row from :func:`pointlessql.services.alerts.list_events_for_owner`.

    Returns:
        Plain-text summary.
    """
    parts: list[str] = []
    outcome = event.get("outcome") or "fired"
    row_count = event.get("row_count")
    parts.append(f"{outcome.replace('_', ' ')}")
    if row_count is not None:
        parts.append(f"row_count={row_count}")
    parts.append(f"alert={event.get('alert_slug') or 'unknown'}")
    return " · ".join(parts)


def render_atom(
    events: list[dict[str, Any]],
    *,
    user_email: str,
    base_url: str,
) -> str:
    """Return an RFC 4287 Atom 1.0 feed document as a string.

    Args:
        events: Pre-filtered events, newest first.
        user_email: Feed-owner email, included in the ``<author>``.
        base_url: Absolute URL of the running deployment (for
            ``<id>`` + ``<link rel=self>``).

    Returns:
        The serialised XML including XML prolog.
    """
    base_url = base_url.rstrip("/")
    feed = ET.Element("feed", xmlns=_ATOM_NS)
    ET.SubElement(feed, "id").text = f"{base_url}/alerts/feed.atom"
    ET.SubElement(feed, "title").text = "PointlesSQL query alerts"
    link_self = ET.SubElement(feed, "link")
    link_self.set("rel", "self")
    link_self.set("href", f"{base_url}/alerts/feed.atom")
    link_html = ET.SubElement(feed, "link")
    link_html.set("rel", "alternate")
    link_html.set("type", "text/html")
    link_html.set("href", f"{base_url}/alerts")
    if events:
        updated = max(_dt_parse(e.get("fired_at")) for e in events)
    else:
        updated = datetime.datetime.now(datetime.UTC)
    ET.SubElement(feed, "updated").text = updated.isoformat()
    author = ET.SubElement(feed, "author")
    ET.SubElement(author, "name").text = user_email
    ET.SubElement(author, "email").text = user_email

    for event in events:
        entry = ET.SubElement(feed, "entry")
        ET.SubElement(
            entry, "id"
        ).text = f"urn:pointlessql:alert:{event.get('event_id') or event.get('id')}"
        ET.SubElement(entry, "title").text = (
            f"{event.get('alert_title') or event.get('alert_slug') or 'alert'} — {_summary(event)}"
        )
        entry_fired = _dt_parse(event.get("fired_at"))
        ET.SubElement(entry, "updated").text = entry_fired.isoformat()
        ET.SubElement(entry, "published").text = entry_fired.isoformat()
        alert_slug = event.get("alert_slug") or ""
        link = ET.SubElement(entry, "link")
        link.set("rel", "alternate")
        link.set("type", "text/html")
        link.set("href", f"{base_url}/alerts/{alert_slug}")
        content = ET.SubElement(entry, "content")
        content.set("type", "application/cloudevents+json")
        content.text = event.get("payload_json") or ""

    # ``ET.tostring`` returns bytes for ``encoding="utf-8"`` and
    # a str for ``encoding="unicode"``; pick unicode + add our own
    # XML prolog so callers get a str without a spurious BOM.
    body = ET.tostring(feed, encoding="unicode")
    return f'<?xml version="1.0" encoding="utf-8"?>\n{body}'


def render_json_feed(
    events: list[dict[str, Any]],
    *,
    user_email: str,
    base_url: str,
) -> dict[str, Any]:
    """Return a JSON Feed 1.1 dict for the given events.

    Args:
        events: Pre-filtered events, newest first.
        user_email: Feed-owner email, included in ``authors``.
        base_url: Absolute deployment URL.

    Returns:
        Dict ready for ``JSONResponse`` with
        ``Content-Type: application/feed+json``.
    """
    base_url = base_url.rstrip("/")
    items: list[dict[str, Any]] = []
    for event in events:
        event_id = event.get("event_id") or str(event.get("id"))
        alert_slug = event.get("alert_slug") or ""
        summary = _summary(event)
        title = f"{event.get('alert_title') or alert_slug or 'alert'} — {summary}"
        content_text = event.get("payload_json") or ""
        try:
            parsed = json.loads(content_text)
            content_payload: Any = parsed
        except ValueError, TypeError:
            content_payload = content_text
        items.append(
            {
                "id": event_id,
                "url": f"{base_url}/alerts/{alert_slug}",
                "title": title,
                "content_text": summary,
                "content_html": (f"<pre>{html.escape(content_text)}</pre>"),
                "date_published": event.get("fired_at"),
                "_pointlessql_cloudevent": content_payload,
                "authors": [{"name": user_email}],
            }
        )
    return {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "PointlesSQL query alerts",
        "home_page_url": f"{base_url}/alerts",
        "feed_url": f"{base_url}/alerts/feed.json",
        "authors": [{"name": user_email}],
        "items": items,
    }
