"""DataProductSpec validation (Phase 143)."""

from __future__ import annotations

import pytest

from pointlessql.services.data_product_as_code import (
    DataProductSpec,
    parse_spec,
)


def test_minimal_spec_parses() -> None:
    spec = parse_spec({"name": "Customers", "catalog": "main", "schema": "silver"})
    assert isinstance(spec, DataProductSpec)
    assert spec.name == "Customers"
    assert spec.catalog == "main"
    assert spec.schema == "silver"
    assert spec.output_ports == []


def test_extra_field_at_top_level_rejected() -> None:
    with pytest.raises(ValueError):
        parse_spec(
            {
                "name": "x",
                "catalog": "c",
                "schema": "s",
                "bogus": "field",
            }
        )


def test_blank_name_rejected() -> None:
    with pytest.raises(ValueError):
        parse_spec({"name": " ", "catalog": "c", "schema": "s"})


def test_yaml_parse() -> None:
    yaml_text = """
name: Customers
catalog: main
schema: silver
domain: customer
output_ports:
  - name: sql
    kind: sql
slos:
  - kind: freshness
    target_value: 60.0
    comparator: lte
"""
    spec = parse_spec(yaml_text)
    assert spec.domain == "customer"
    assert len(spec.output_ports) == 1
    assert spec.slos[0].comparator == "lte"


def test_invalid_yaml_raises_value_error() -> None:
    with pytest.raises(ValueError, match="yaml parse error"):
        parse_spec(": not valid : yaml :")


def test_round_trip_dump_and_reparse() -> None:
    spec = parse_spec(
        {
            "name": "Trips",
            "catalog": "mobility",
            "schema": "trips",
            "input_ports": [{"name": "iot", "kind": "operational_system"}],
            "output_ports": [{"name": "events", "kind": "event", "format": "json"}],
            "entities": [
                {
                    "name": "Trip",
                    "source_table": "trip_master",
                    "primary_key_columns": ["trip_id"],
                }
            ],
        }
    )
    dumped = spec.model_dump()
    re_parsed = parse_spec(dumped)
    assert re_parsed.model_dump() == dumped
