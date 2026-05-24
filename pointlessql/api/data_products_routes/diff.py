"""``GET /api/data-products/{catalog}/{schema}/diff`` — live yaml↔Delta diff."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.data_products_routes._shared import diff_to_payload, load_one
from pointlessql.api.dependencies import current_workspace_id, get_uc_client
from pointlessql.data_products import diff_contract_against_delta_table

router = APIRouter(tags=["data-products"])


@router.get("/api/data-products/{catalog}/{schema}/diff")
async def diff_data_product(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Live-diff every declared table's contract against on-disk Delta schema.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"product_ref": "cat.sch", "tables": [{name, ...diff} | {error}]}``
        per declared table.  Tables not on disk surface ``error`` rather
        than failing the whole call.
    """
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    _row, contract, _email, _display = load_one(factory, workspace_id, catalog, schema)
    uc = get_uc_client(request)

    table_diffs: list[dict[str, Any]] = []
    for table_contract in contract.tables:
        full_name = f"{catalog}.{schema}.{table_contract.name}"
        try:
            uc_table = await uc.get_table(full_name)
        except Exception:  # noqa: BLE001 — UC unreachable / 404 / etc.
            # bare-broad-ok: live-diff degrades to per-table error
            # surface when UC misses; a single bad table must not
            # break the page render.
            table_diffs.append(diff_to_payload(table_contract.name, "table not in UC"))
            continue
        storage = uc_table.get("storage_location")
        if not isinstance(storage, str) or not storage:
            table_diffs.append(diff_to_payload(table_contract.name, "no storage_location"))
            continue
        try:
            diff_result = diff_contract_against_delta_table(table_contract, storage)
        except Exception as exc:  # noqa: BLE001 — Delta read failure
            # bare-broad-ok: same reasoning as the UC branch above —
            # a single Delta unreadable surfaces per-table without
            # blocking the rest.
            table_diffs.append(diff_to_payload(table_contract.name, f"delta read failed: {exc!r}"))
            continue
        table_diffs.append(diff_to_payload(table_contract.name, diff_result))

    return {"product_ref": f"{catalog}.{schema}", "tables": table_diffs}
