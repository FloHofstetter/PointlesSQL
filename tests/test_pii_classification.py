"""PII classification: heuristics, table scan, additive tagging."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import deltalake
import pandas as pd
import pytest

from pointlessql.services.pii_classification import (
    classify_name,
    classify_values,
    scan_scope,
    scan_table,
)

# ---------------------------------------------------------------------------
# heuristics
# ---------------------------------------------------------------------------


def test_name_heuristics() -> None:
    assert classify_name("customer_email") == "email"
    assert classify_name("E_Mail") == "email"
    assert classify_name("phoneNumber") == "phone"
    assert classify_name("iban") == "iban"
    assert classify_name("date_of_birth") == "birthdate"
    assert classify_name("street_address") == "address"
    assert classify_name("amount") is None
    assert classify_name("description") is None


def test_value_heuristics_email_and_threshold() -> None:
    emails = ["a@x.com", "b@y.org", "c@z.de", "d@w.io"]
    assert classify_values(emails) == "email"
    # one stray email in free text is below the match threshold.
    mixed = ["hello world", "a@x.com", "lorem ipsum", "dolor sit"]
    assert classify_values(mixed) is None
    # too few samples → no signal.
    assert classify_values(["a@x.com"]) is None


def test_value_heuristics_iban() -> None:
    ibans = ["DE89370400440532013000", "GB29NWBK60161331926819", "FR1420041010050500013M02606"]
    assert classify_values(ibans) == "iban"


# ---------------------------------------------------------------------------
# table scan
# ---------------------------------------------------------------------------


def _uc(
    columns: list[dict[str, str]],
    storage: str | None,
    existing_tags: dict[str, list[dict[str, str]]] | None = None,
) -> MagicMock:
    client = MagicMock()
    client.get_table = AsyncMock(return_value={"storage_location": storage, "columns": columns})

    async def get_tags(securable_type: str, full_name: str) -> list[dict[str, str]]:
        column = full_name.rsplit(".", 1)[-1]
        return (existing_tags or {}).get(column, [])

    client.get_tags = AsyncMock(side_effect=get_tags)
    client.update_tags = AsyncMock(return_value=[])
    return client


async def test_scan_tags_name_and_value_hits(tmp_path: Path) -> None:
    loc = str(tmp_path / "people")
    deltalake.write_deltalake(
        loc,
        pd.DataFrame(
            {
                "contact": ["a@x.com", "b@y.org", "c@z.de"],  # value signal only
                "phone": ["1", "2", "3"],  # name signal
                "amount": ["10", "20", "30"],  # neither
            }
        ),
    )
    columns = [
        {"name": "contact", "type_text": "string"},
        {"name": "phone", "type_text": "string"},
        {"name": "amount", "type_text": "string"},
    ]
    client = _uc(columns, loc)
    findings = await scan_table(client, "main.demo.people")
    by_column = {f.column: f for f in findings}
    assert by_column["contact"].kind == "email"
    assert by_column["contact"].source == "values"
    assert by_column["phone"].kind == "phone"
    assert by_column["phone"].source == "name"
    assert "amount" not in by_column
    assert all(f.applied for f in findings)
    assert client.update_tags.await_count == 2


async def test_scan_is_additive_only(tmp_path: Path) -> None:
    """A column with an existing pii tag is reported but never re-tagged."""
    columns = [{"name": "email", "type_text": "string"}]
    client = _uc(columns, None, existing_tags={"email": [{"key": "pii", "value": "custom"}]})
    findings = await scan_table(client, "main.demo.people")
    assert len(findings) == 1
    assert findings[0].applied is False
    client.update_tags.assert_not_awaited()


async def test_scan_scope_requires_target() -> None:
    with pytest.raises(ValueError, match="scan needs"):
        await scan_scope(MagicMock(), table=None, catalog=None, schema=None)


async def test_scan_scope_walks_schema(tmp_path: Path) -> None:
    columns = [{"name": "email", "type_text": "string"}]
    client = _uc(columns, None)
    client.list_tables = AsyncMock(return_value=[{"name": "t1"}, {"name": "t2"}])
    findings = await scan_scope(client, catalog="c", schema="s")
    tables = {f.table for f in findings}
    assert tables == {"c.s.t1", "c.s.t2"}


async def test_tag_write_failure_keeps_scanning(tmp_path: Path) -> None:
    columns = [
        {"name": "email", "type_text": "string"},
        {"name": "phone", "type_text": "string"},
    ]
    client = _uc(columns, None)

    calls: list[str] = []

    async def update_tags(securable: str, full_name: str, changes: Any) -> list[Any]:
        calls.append(full_name)
        if "email" in full_name:
            raise RuntimeError("boom")
        return []

    client.update_tags = AsyncMock(side_effect=update_tags)
    findings = await scan_table(client, "main.demo.people")
    by_column = {f.column: f for f in findings}
    assert by_column["email"].applied is False
    assert by_column["phone"].applied is True
    assert len(calls) == 2
