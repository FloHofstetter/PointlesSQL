"""Mutation-kill tests for ``pointlessql.pql._contracts.contract``.

Pins the draft-contract factory defaults and the conditional inclusion of
the optional ``steward_email`` / ``sla_minutes`` payload fields — mutations
the broader ``test_pql_contract.py`` suite executed but did not detect.
"""

from __future__ import annotations

from pointlessql.pql._contracts import contract

TABLES = [
    {
        "name": "orders",
        "columns": [{"name": "id", "type": "long", "nullable": False}],
        "primary_key": ["id"],
    }
]


def test_contract_defaults_version_and_description() -> None:
    """A draft contract defaults to the ``0.1.0-draft`` version and empty description."""
    # kills version="0.1.0-draft" -> "XX0.1.0-draftXX"/"0.1.0-DRAFT" and description="" -> "XXXX"
    payload = contract("main", "sales", tables=TABLES).as_dict()
    assert payload["version"] == "0.1.0-draft"
    assert payload["description"] == ""


def test_contract_steward_email_round_trips_when_set() -> None:
    """A provided steward email lands under the ``steward_email`` key verbatim."""
    # kills `is not None`->`is None`, `= steward_email`->`= None`, and the key mutants
    payload = contract("main", "sales", tables=TABLES, steward_email="s@x.com").as_dict()
    assert payload["steward_email"] == "s@x.com"


def test_contract_sla_minutes_round_trips_when_set() -> None:
    """A provided SLA lands under the ``sla_minutes`` key verbatim."""
    # kills `is not None`->`is None`, `= sla_minutes`->`= None`, and the key mutants
    payload = contract("main", "sales", tables=TABLES, sla_minutes=30).as_dict()
    assert payload["sla_minutes"] == 30
