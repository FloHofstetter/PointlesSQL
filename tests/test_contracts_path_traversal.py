"""Contract drafts cannot be written outside their workspace directory.

``catalog``/``schema`` flow from the request body into a
``catalog__schema.yaml`` filename joined onto the workspace draft dir, so
an unvalidated ``../`` let an authenticated user write yaml anywhere the
process could.  These tests pin the UC-identifier validator on the
contract model and the defence-in-depth resolved-path guard.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from pointlessql.api.data_products_routes.contracts import (
    _assert_within_dir,  # pyright: ignore[reportPrivateUsage]
)
from pointlessql.exceptions import BadRequestError
from pointlessql.pql._contracts import contract as build_contract

_TABLES = [
    {
        "name": "orders",
        "columns": [{"name": "id", "type": "long", "nullable": False}],
        "primary_key": ["id"],
    }
]


@pytest.mark.parametrize("catalog", ["../evil", "a/b", "..", "x/../y", "with space"])
def test_contract_rejects_unsafe_catalog(catalog: str) -> None:
    """A catalog name with a path separator fails model validation."""
    with pytest.raises(ValidationError):
        build_contract(catalog, "ok", tables=_TABLES)


@pytest.mark.parametrize("schema", ["../evil", "a/b", "sales.gold"])
def test_contract_rejects_unsafe_schema(schema: str) -> None:
    """A schema name with a path separator / dot fails model validation."""
    with pytest.raises(ValidationError):
        build_contract("main", schema, tables=_TABLES)


def test_contract_accepts_normal_identifiers() -> None:
    """Ordinary catalog/schema names still build."""
    draft = build_contract("main", "sales_gold", tables=_TABLES)
    assert draft.contract.catalog == "main"


def test_assert_within_dir_guard(tmp_path: Path) -> None:
    """The resolved-path guard rejects escapes, allows contained paths."""
    _assert_within_dir(tmp_path, tmp_path / "main__sales.yaml")
    with pytest.raises(BadRequestError):
        _assert_within_dir(tmp_path, tmp_path / ".." / "escape.yaml")


@pytest.mark.asyncio
async def test_save_route_rejects_traversal(admin_client: httpx.AsyncClient) -> None:
    """POST /api/contracts/save with a traversal catalog returns 400."""
    res = await admin_client.post(
        "/api/contracts/save",
        json={"catalog": "../../etc/evil", "schema": "x", "tables": _TABLES},
    )
    assert res.status_code == 400, res.text
